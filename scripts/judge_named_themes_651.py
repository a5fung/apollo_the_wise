#!/usr/bin/env python3
"""#651 — judge-named themes: the historical pass, the capture loader, THE REPORT, and the
surface preview.

Four modes, all off the alert path, none touching a grade/entry/exit/size/theme (THE LINE):

  --surface [--dry-run]
        The nightly trigger, by hand: every recurring judge-named group the engine never had
        and has not been paged yet -> seed a shadow candidate (source 'judge_named') + ONE
        Telegram page with the existing one-tap promote button. WITH --dry-run it reads
        everything and writes/sends NOTHING — prints what WOULD fire ($0). Run the dry run in
        prod after deploy: the first real run pages the historical never-matched groups.

  --historical [--since 2026-07-01] [--limit 400] --capture PATH [--commit]
        Extract the group names the judge wrote into mi_ep_alerts.judge_rationale for every
        alert not yet recorded. WITHOUT --commit it is a DRY RUN: counts the pending
        population, spends nothing, writes nothing. WITH --commit: one Haiku call per alert,
        each raw result appended to PATH (JSONL) BEFORE the row is written — capture once,
        read many (CLAUDE.md cost rule). Priced up front: ~105 alerts x ~360 tokens on Haiku
        4.5 ($1/$5 per M) ~ $0.07 total. Prints the actual spend at the end.

  --load-capture PATH
        Insert the rows of an earlier capture into mi_judge_named_themes. ZERO API spend —
        this is how a pass captured before the table existed in prod lands without re-running.

  --report [--capture PATH] [--themes-json PATH] [--out PATH]
        The read that answers the goal: which judge-named groups recur across >=2 tickers,
        whether mi_themes ever held a matching name, and the lead time in days for each
        (positive = the judge was earlier). Rows come from the table, or from a capture file
        (--capture); the engine's timeline comes from mi_themes (+ mi_theme_renames lineage),
        or from a portfolio-app2 theme snapshot JSON (--themes-json, no DB needed).

Run inside apollo-market (it has the modules, the DB and ANTHROPIC_API_KEY), e.g.:
  docker exec apollo-market python scripts/judge_named_themes_651.py --historical \
      --capture /app/logs/651_capture.jsonl --commit
  docker exec apollo-market python scripts/judge_named_themes_651.py --report
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

# The container sets PYTHONPATH=/app; a local `python scripts/...` run does not — same pattern
# as scripts/backfill_theme_ecosystems.py so the --report --themes-json path works off-box.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _d(v) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def load_capture_rows(path: Path) -> list[dict]:
    """Capture JSONL -> the row shape lead_time_report consumes (sentinel for empty groups)."""
    from agents.market_intelligence.judge_named_themes import NONE_KEY
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        groups = rec.get("groups") or [{"name": NONE_KEY, "canonical_key": NONE_KEY,
                                        "evidence": None, "judge_says_untracked": None}]
        for g in groups:
            rows.append({
                "ticker": rec["ticker"], "alert_date": _d(rec["alert_date"]),
                "alert_id": rec.get("alert_id"), "group_name": g.get("name") or g["canonical_key"],
                "canonical_key": g["canonical_key"], "evidence": g.get("evidence"),
                "judge_says_untracked": g.get("judge_says_untracked"), "model": rec.get("model"),
            })
    return rows


def load_theme_history_json(path: Path) -> list[dict]:
    """portfolio-app2's apollo_themes_snapshot.json -> (name, theme_date) rows."""
    d = json.loads(path.read_text(encoding="utf-8"))
    themes = d.get("themes") if isinstance(d, dict) else d
    return [{"name": t["name"], "theme_date": _d(t["theme_date"])} for t in themes
            if t.get("name") and t.get("theme_date")]


async def _historical(args) -> int:
    from agents.market_intelligence.judge_named_themes import extract_pending
    out = await extract_pending(limit=args.limit, since=_d(args.since),
                                capture_path=args.capture, commit=args.commit)
    if not args.commit:
        print(f"DRY RUN — {out['n_pending']} alert(s) pending extraction since {args.since} "
              f"(limit {args.limit}); nothing spent, nothing written. Add --commit to run.")
        return 0
    print(f"extracted {out['n_alerts']} alert(s): {out['n_named']} named >=1 group, "
          f"{out['n_rows_written']} row(s) written, {out['n_failed']} failed (left pending)")
    print(f"tokens in/out {out['input_tokens']}/{out['output_tokens']} -> "
          f"ACTUAL SPEND ~${out['est_cost_usd']:.4f}; capture: {args.capture}")
    return 0


async def _load_capture(args) -> int:
    from agents.market_intelligence.db import get_pool, insert_judge_named_theme_row
    rows = load_capture_rows(Path(args.load_capture))
    pool = await get_pool()
    n = 0
    async with pool.acquire() as conn:
        for r in rows:
            await insert_judge_named_theme_row(
                conn, r["ticker"], r["alert_date"], r.get("alert_id"), r["group_name"],
                r["canonical_key"], r.get("evidence"), r.get("judge_says_untracked"), r.get("model"))
            n += 1
    print(f"loaded {n} row(s) from {args.load_capture} (idempotent; $0)")
    return 0


async def _report(args) -> int:
    from agents.market_intelligence.judge_named_themes import format_report, lead_time_report
    edges: list = []
    if args.capture:
        rows = load_capture_rows(Path(args.capture))
    else:
        from agents.market_intelligence.db import get_judge_named_theme_rows, get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await get_judge_named_theme_rows(conn)
    if args.themes_json:
        hist = load_theme_history_json(Path(args.themes_json))
        print("(theme timeline from snapshot JSON — rename lineage NOT applied)")
    else:
        from agents.market_intelligence.db import get_pool, get_theme_name_history, get_theme_rename_edges
        pool = await get_pool()
        async with pool.acquire() as conn:
            hist = await get_theme_name_history(conn)
            edges = await get_theme_rename_edges(conn)
    rep = lead_time_report(rows, hist, rename_edges=edges)
    text = format_report(rep)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        Path(str(args.out) + ".json").write_text(json.dumps(rep, default=str, indent=1), encoding="utf-8")
        print(f"\nwritten: {args.out} (+ .json)")
    return 0


async def _surface(args) -> int:
    from agents.market_intelligence.judge_named_themes import surface_new_candidates
    out = await surface_new_candidates(dry_run=args.dry_run)
    head = "DRY RUN — would fire" if args.dry_run else "fired"
    print(f"{out['n_recurring']} recurring group(s): {out['n_matched']} matched a theme, "
          f"{out['n_unmatched']} unmatched, {out['n_already_surfaced']} already surfaced")
    cands = out["would_fire"] if args.dry_run else out["fired"]
    print(f"{head}: {len(cands)}")
    for c in cands:
        print(f"  {c['key']}  ->  '{c['name']}'  on {len(c['tickers'])} tickers: {', '.join(c['tickers'])}")
    if not args.dry_run:
        print(f"re-seeded (still being named): {out['n_refreshed']}; send failed: {out['n_send_failed']}; "
              f"seed failed: {out['n_seed_failed']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--surface", action="store_true", help="run the nightly trigger by hand")
    p.add_argument("--dry-run", action="store_true", help="with --surface: print what would fire, write/send nothing")
    p.add_argument("--historical", action="store_true")
    p.add_argument("--since", default="2026-07-01")
    p.add_argument("--limit", type=int, default=400)
    p.add_argument("--capture", default=None, help="JSONL capture path (append)")
    p.add_argument("--commit", action="store_true", help="spend money and write rows")
    p.add_argument("--load-capture", default=None)
    p.add_argument("--report", action="store_true")
    p.add_argument("--themes-json", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    if args.surface:
        return asyncio.run(_surface(args))
    if args.historical:
        if args.commit and not args.capture:
            p.error("--commit requires --capture: the paid output must be captured to a file first")
        return asyncio.run(_historical(args))
    if args.load_capture:
        return asyncio.run(_load_capture(args))
    if args.report:
        return asyncio.run(_report(args))
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
