"""#505 — parent pass DRY RUN over today's live theme board. READ-ONLY, $0.

What it prints, for the latest `mi_themes` snapshot:
  1. Every live theme's RESOLVED parent under ruling (5) (operator 2026-07-27:
     ecosystem is the default parent): CHILD of a real theme / ROOT under its
     ecosystem / CATCH-ALL root under E-UNASSIGNED — via the SAME
     `theme_ecosystems.resolve_theme_parent` the /themes render uses.
  2. Exactly what an ARMED night would ask the ADR-0025 adjudicator — via the
     SAME pure `theme_engine.propose_parent_candidates` the nightly pass calls,
     fed the SAME inputs (live merge cooldowns, Arm B's uncapped territory,
     sector map): child → best candidate parent + why, tonight's capped slice
     and the whole backfill queue.
  3. Counts: themes / already parented / would-ask / roots / catch-all, the 5
     biggest families, and the backfill priced as ONE number (pricing_for).

The verdicts themselves need the paid adjudicator — that is the flip gate, not
this probe. `--adjudicate` runs the REAL `adjudicate_merge_pair` on the queue
(log_spend=False, needs ANTHROPIC_API_KEY) — OPERATOR-authorised only; never
run it from here without his word.

Reads prod over ssh (psql, SELECTs only). Run from the repo root:
    python scripts/probes/_505_parent_pass_dry_run.py [--out FILE] [--adjudicate]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence import theme_engine as te  # noqa: E402
from agents.market_intelligence import theme_ecosystems as tx  # noqa: E402
from agents.market_intelligence.theme_merge_arm import (  # noqa: E402
    build_adjudication_prompt, pair_key, propose_merge_pairs,
)
from shared.llm_models import HAIKU, pricing_for  # noqa: E402

HOST = "apollo@87.99.134.162"
PSQL = "docker exec -i apollo-postgres psql -U apollo -d apollo -At -F '|' -c"
SEP = "|"
TICK_SEP = ","

Q_BOARD = (
    "SELECT name, stage, COALESCE(parent_theme,''), source, "
    "array_to_string(tickers, ','), COALESCE(score,0) "
    "FROM mi_themes WHERE theme_date=(SELECT MAX(theme_date) FROM mi_themes) "
    "ORDER BY score DESC, name"
)
Q_DATE = "SELECT MAX(theme_date) FROM mi_themes"
Q_ECO = "SELECT theme_name, e_code FROM mi_theme_ecosystems"
Q_COOL = "SELECT theme_a, theme_b, verdict FROM mi_theme_merge_cooldowns WHERE cooldown_until > NOW()"
Q_SECT = (
    "SELECT ticker, sector FROM mi_stock_scores "
    "WHERE score_date=(SELECT MAX(score_date) FROM mi_stock_scores) "
    "AND sector IS NOT NULL AND sector <> 'Unknown'"
)


def psql(query: str) -> list[list[str]]:
    """Unaligned, tuples-only psql over ssh. Skips any `(N rows)` footer line
    defensively (scripts/probes/README.md — #623 fed one to Polygon)."""
    out = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", HOST, f'{PSQL} "{query}"'],
        check=True, capture_output=True, text=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        if not line.strip() or line.startswith("("):
            continue
        rows.append(line.split(SEP))
    return rows


def load_board() -> tuple[str, list[dict]]:
    day = psql(Q_DATE)[0][0]
    board = []
    for name, stage, parent, source, tickers, score in psql(Q_BOARD):
        board.append({
            "name": name, "stage": stage, "parent_theme": parent or None, "source": source,
            "tickers": [t for t in tickers.split(TICK_SEP) if t], "score": float(score),
            "description": "",  # the adjudication prompt wants one; --adjudicate refetches it
        })
    return day, board


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="also write the report here")
    ap.add_argument("--adjudicate", action="store_true",
                    help="OPERATOR-AUTHORISED ONLY: run the real adjudicator on the queue")
    args = ap.parse_args()

    day, board = load_board()
    eco_map = {n: c for n, c in psql(Q_ECO)}
    cooldown_rows = psql(Q_COOL)
    cooldown_pairs = {pair_key(a, b) for a, b, _v in cooldown_rows}
    sectors = {t: s for t, s in psql(Q_SECT)}

    live = [t for t in board if t["stage"] != "Retired" and t["tickers"]]
    arm_b = propose_merge_pairs(live, cooldown_pairs=cooldown_pairs,
                                sectors_by_ticker=sectors, max_pairs=None)
    arm_b_pairs = {pair_key(a["name"], o["name"]) for a, o in arm_b}
    queue = te.propose_parent_candidates(board, eco_map, cooldown_pairs=cooldown_pairs,
                                         arm_b_pairs=arm_b_pairs, cap=None)
    tonight = queue[:te.PARENT_PASS_CAP_PER_NIGHT]
    would_ask = {c["child"]: c for c in queue}

    # ── 1. resolved parent per theme ────────────────────────────────────────
    kinds = Counter()
    by_eco: dict[str, list[tuple]] = defaultdict(list)
    for t in sorted(live, key=lambda t: (eco_map.get(t["name"], tx.E_UNASSIGNED), -t["score"])):
        kind, parent = tx.resolve_theme_parent(t, eco_map)
        kinds[kind] += 1
        ask = would_ask.get(t["name"])
        by_eco[eco_map.get(t["name"], tx.E_UNASSIGNED)].append((t, kind, parent, ask))

    L: list[str] = []
    P = L.append
    P(f"#505 PARENT PASS — DRY RUN over the live board of {day} (read-only, $0)")
    P(f"toggle theme_parent_pass: OFF (nothing below was written; this is what an armed night would do)")
    P("")
    n_live = len(live)
    n_child = kinds["child"]
    P(f"THEMES {n_live} live (non-Retired) · already PARENTED {n_child} · "
      f"ROOT under ecosystem {kinds['root']} · CATCH-ALL (E-UNASSIGNED) {kinds['catch_all']}")
    P(f"Every theme has a parent under ruling (5): {n_child + kinds['root'] + kinds['catch_all']} of {n_live}")
    P(f"Fading themes on the board (left alone by the pass): {sum(1 for t in live if t['stage'] == 'Fading')}")
    P(f"shadow_promoted themes on the board: {sum(1 for t in live if t['source'] == 'shadow_promoted')} "
      f"(the path that never reached the adjudicator in July — {sum(1 for c in queue if c['child_source'] == 'shadow_promoted')} of them are in tonight's queue)")
    P("")
    P(f"WOULD ASK the adjudicator: {len(queue)} childless theme(s) have an eligible same-ecosystem "
      f"candidate parent; cap {te.PARENT_PASS_CAP_PER_NIGHT}/night → {tonight and len(tonight)} tonight, "
      f"queue drains in ~{-(-len(queue) // te.PARENT_PASS_CAP_PER_NIGHT)} armed nights")
    P(f"  excluded from the ask: {len(cooldown_pairs)} live merge-cooldown pair(s), "
      f"{len(arm_b_pairs)} pair(s) in Arm B's own territory (its uncapped Stage-A pairing)")
    childless_live = [t for t in live if t["stage"] != "Fading" and not t["parent_theme"]]
    no_cand = [t for t in childless_live
               if t["name"] not in would_ask and eco_map.get(t["name"], tx.E_UNASSIGNED) != tx.E_UNASSIGNED]
    P(f"  childless non-Fading themes with NO eligible candidate (alone in their ecosystem, or every "
      f"broader theme is cooled-down / Arm-B territory): {len(no_cand)} → stay ROOT")
    # Cost as ONE number (pricing_for): prompt length from the REAL prompt builder.
    price = pricing_for(HAIKU)
    by_name = {t["name"]: t for t in board}
    in_tok = sum(len(build_adjudication_prompt(by_name[c["parent"]], by_name[c["child"]], sectors)) / 4
                 for c in queue)
    out_tok = 350 * len(queue)
    cost = in_tok / 1e6 * price["input"] + out_tok / 1e6 * price["output"]
    P(f"BACKFILL COST (whole queue, {HAIKU}): ~${cost:.2f} for {len(queue)} call(s) "
      f"(~{in_tok/ max(len(queue),1):.0f} prompt tokens each); steady state ≤{te.PARENT_PASS_CAP_PER_NIGHT} calls/night")
    P("")

    # ── ticker-containment check (the July mechanism's trigger) ─────────────
    P("TICKER CONTAINMENT (Route A's trigger: ≥0.8 of the child's members inside a broader theme, ≥3 shared):")
    hits = 0
    for c in live:
        if c["stage"] == "Fading":
            continue
        ct = set(c["tickers"])
        for p in live:
            if p is c or len(p["tickers"]) <= len(ct):
                continue
            inter = len(ct & set(p["tickers"]))
            if len(ct) >= te.SUBTHEME_MIN_MEMBERS and inter >= te.MIN_SHARED_FOR_MERGE \
                    and inter / len(ct) >= te.SUBTHEME_C_MIN:
                hits += 1
                P(f"  '{c['name']}' ({len(ct)}, {c['source']}) inside '{p['name']}' ({len(p['tickers'])}) "
                  f"— {inter} shared, containment {inter/len(ct):.2f}, current parent: {c['parent_theme'] or '-'}")
    P(f"  → {hits} pair(s) on the whole board. Ticker overlap cannot be the gate; it is a priority signal.")
    P("")

    # ── tonight's asks + the full queue ─────────────────────────────────────
    P(f"TONIGHT'S {len(tonight)} ASK(S) (highest signal first):")
    for c in tonight:
        P(f"  '{c['child']}' [{c['child_source']}, {c['child_members']}] → '{c['parent']}' [{c['parent_members']}]  ({c['why']})")
    if len(queue) > len(tonight):
        P(f"REST OF THE QUEUE ({len(queue) - len(tonight)}):")
        for c in queue[len(tonight):]:
            P(f"  '{c['child']}' [{c['child_source']}, {c['child_members']}] → '{c['parent']}' [{c['parent_members']}]  "
              f"(shared tickers {c['shared_tickers']}, tokens {c['shared_tokens']})")
    P("")

    # ── families ─────────────────────────────────────────────────────────────
    P("5 BIGGEST FAMILIES (existing parent → children on the board today):")
    fam: dict[str, list[str]] = defaultdict(list)
    for t in live:
        p = tx.containment_parent(t)
        if p:
            fam[p].append(t["name"])
    for parent, kids in sorted(fam.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]:
        P(f"  '{parent}' ← {len(kids)}: " + " · ".join(f"'{k}'" for k in kids))
    if not fam:
        P("  (none)")
    P("")
    P("5 BIGGEST FAMILIES IF EVERY ASK CAME BACK PARENT_CHILD (upper bound, not a prediction):")
    fam2: dict[str, list[str]] = defaultdict(list, {k: list(v) for k, v in fam.items()})
    for c in queue:
        fam2[c["parent"]].append(c["child"] + "?")
    for parent, kids in sorted(fam2.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]:
        P(f"  '{parent}' ← {len(kids)}: " + " · ".join(f"'{k}'" for k in kids))
    P("")

    # ── per-theme resolved parent, grouped by ecosystem ─────────────────────
    P("RESOLVED PARENT PER THEME (ruling (5)): kind · theme [stage, source, members] → parent   (ask = tonight's/queued candidate)")
    codes = sorted(by_eco, key=lambda c: (c == tx.E_UNASSIGNED, -len(by_eco[c]), c))
    for code in codes:
        rows = by_eco[code]
        P(f"— {code} ({len(rows)} themes; {sum(1 for r in rows if r[1] == 'child')} child, "
          f"{sum(1 for r in rows if r[1] != 'child')} root)")
        for t, kind, parent, ask in rows:
            tag = {"child": "CHILD ", "root": "ROOT  ", "catch_all": "CATCH "}[kind]
            line = f"  {tag} '{t['name']}' [{t['stage']}, {t['source']}, {len(t['tickers'])}] → {parent}"
            if ask:
                line += f"   ask: → '{ask['parent']}' ({'tonight' if ask in tonight else 'queued'})"
            P(line)
    P("")
    P("NOT IN THIS REPORT: verdicts. PARENT_CHILD/DISTINCT/MERGE come from the paid adjudicator — the flip gate.")

    report = "\n".join(L)
    print(report)
    if args.out:
        Path(args.out).write_text(report + "\n")

    if args.adjudicate:
        asyncio.run(_adjudicate(queue, by_name, sectors, args.out))
    return 0


async def _adjudicate(queue, by_name, sectors, out_path):
    """OPERATOR-AUTHORISED ONLY. Real verdicts for the queue, log_spend=False."""
    from agents.market_intelligence.theme_merge_arm import adjudicate_merge_pair
    from shared.llm_client import make_async_anthropic
    client = make_async_anthropic()
    lines = ["", "ADJUDICATED (real verdicts, no spend rows):"]
    tally = Counter()
    for c in queue:
        v = await adjudicate_merge_pair(by_name[c["parent"]], by_name[c["child"]], client=client,
                                        sectors_by_ticker=sectors, log_spend=False)
        verdict = v.get("verdict")
        if verdict == "PARENT_CHILD" and v.get("child", "B") == "A":
            verdict = "PARENT_CHILD_INVERTED"
        tally[verdict] += 1
        lines.append(f"  '{c['child']}' → '{c['parent']}': {verdict}  {str(v.get('reason') or '')[:160]!r}")
    lines.append(f"  tally: {dict(tally)}")
    text = "\n".join(lines)
    print(text)
    if out_path:
        with open(out_path, "a") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    sys.exit(main())
