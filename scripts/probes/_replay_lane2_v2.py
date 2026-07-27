"""#167 Lane-2 grouping v2 — forward-era REPLAY driver (operator-run, read-only by default).

Replays the NEW v2 behavior (grounded input + 10-trading-day rolling window +
same-day anchor) over the forward-era alert history by calling the REAL
`theme_engine.discover_narrative_themes` with the `lane2_grouping_v2` flag
forced ON **in-process only** (the DB toggle is never touched) and
`persist=False` (ZERO writes). The v1 baseline for comparison is production's
actual history — v1 already ran live over these dates, so it is not re-run.

Modes
-----
--no-llm            Deterministic leg only: per-day gate decision, pool
                    composition, dedup outcome, anchor set, input-source mix,
                    prompt size. No API call, no key needed. SAFE ANYWHERE.
--offline FILE      Serve alerts from a JSON pull (see query below) instead of
                    the live DB — lets the replay run off-box. Without it, the
                    script reads the DB via db.get_ep_alerts_window (SELECT
                    only; intended to be run in the market-agent container).
--persist-backfill  OPERATOR-ONLY: persist replay proposals under the
                    SEGREGATED source 'narrative_cogap_backfill' (the #167
                    hindsight-segregation lane, same as
                    _backfill_narrative_discovery.py) so
                    `theme_engine.evaluate_narrative_themes(days=60,
                    include_backfill=True)` can score them (fwd_5d/10d,
                    live_unified). ⚠ Replaces prior narrative_cogap_backfill
                    rows for replayed dates; FORWARD rows are protected by the
                    DO NOTHING guard in persist_narrative_theme_candidates.
                    Default is persist=False — no writes at all.

The LLM leg uses the production model (shared.llm_models.THEME_MODEL =
claude-sonnet-4-6) at max_tokens=1500 — identical to live. Requires
ANTHROPIC_API_KEY. ~25-30 gated days × ~8-15k input tokens ≈ $1-2 total at
Sonnet rates ($3/MTok in, $15/MTok out).

Offline data pull (prod, SELECT only):
  ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo -tA -c \"
    SELECT COALESCE(json_agg(row_to_json(t)), '[]') FROM (
      SELECT DISTINCT ON (a.ticker, a.alert_date)
             a.alert_date, a.ticker, a.ep_score, a.gap_pct,
             a.catalyst, a.claude_analysis, a.grounded_text
      FROM mi_ep_alerts a
      WHERE a.alert_date BETWEEN '2026-05-20' AND '2026-07-24'
        AND COALESCE(a.source, 'live') = 'live'
      ORDER BY a.ticker, a.alert_date, a.ep_score DESC) t;\"" > lane2_alerts.json

Run:  python scripts/probes/_replay_lane2_v2.py --offline lane2_alerts.json \
          --start 2026-06-08 --end 2026-07-24 [--no-llm] [--out replay.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence import theme_engine  # noqa: E402
from agents.market_intelligence.theme_engine import (  # noqa: E402
    LANE2_WINDOW_TRADING_DAYS, _build_lane2_v2_prompt, _dedupe_lane2_pool,
    _lane2_input_text, _lane2_window_start, discover_narrative_themes,
)


def _load_offline(path: str) -> list[dict]:
    rows = json.loads(Path(path).read_text())
    for r in rows:
        r["alert_date"] = date.fromisoformat(r["alert_date"])
    return rows


def _trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


async def _replay_one(scan_d: date, rows_for_window, *, no_llm: bool,
                      persist_backfill: bool) -> dict:
    """One replay day through the REAL discover_narrative_themes (flag forced ON
    in-process; DB toggle untouched)."""
    async def fake_flag():
        return True

    async def fake_window(d_from, d_to):
        return [r for r in rows_for_window if d_from <= r["alert_date"] <= d_to]

    async def _noop_audit(*a, **k):
        return None

    async def _noop_spend(**k):
        return None

    patches = [
        patch("agents.market_intelligence.db.get_lane2_grouping_v2_enabled", fake_flag),
        patch("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", _noop_spend),
        # audit rows are prod telemetry — a replay must not write them even on-box
        patch("agents.market_intelligence.db.log_audit_event", _noop_audit),
    ]
    if rows_for_window is not None:
        patches.append(patch("agents.market_intelligence.db.get_ep_alerts_window", fake_window))

    ctxs = [p.start() for p in patches]
    try:
        if no_llm:
            # Deterministic leg: gate/pool/prompt only — replicates the exact
            # pre-LLM path of discover_narrative_themes v2 using the same
            # helpers the live function calls.
            window_rows = await fake_window(_lane2_window_start(scan_d), scan_d) \
                if rows_for_window is not None else []
            pool, today_tk = _dedupe_lane2_pool(window_rows, scan_d)
            src = {"grounded": 0, "analysis": 0, "catalyst": 0, "none": 0}
            for a in pool:
                src[_lane2_input_text(a)[1]] += 1
            gated = bool(today_tk) and len(pool) >= 2
            prompt = _build_lane2_v2_prompt(pool, today_tk) if gated else ""
            return {
                "date": str(scan_d), "gated": gated,
                "today": sorted(today_tk), "pool": [
                    {"ticker": a["ticker"], "alert_date": str(a["alert_date"]),
                     "ep": a.get("ep_score"), "src": _lane2_input_text(a)[1]}
                    for a in pool],
                "input_sources": src,
                "prompt_chars": len(prompt), "est_input_tokens": len(prompt) // 4,
            }
        out = await discover_narrative_themes(
            scan_d, persist=persist_backfill, backfilled=True)
        return {"date": str(scan_d), **{k: v for k, v in out.items() if k != "date"}}
    finally:
        for p in patches:
            p.stop()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="JSON alert pull (see module docstring)")
    ap.add_argument("--start", default="2026-06-08")
    ap.add_argument("--end", default="2026-07-24")
    ap.add_argument("--no-llm", action="store_true",
                    help="deterministic gate/pool/prompt replay only — no API call")
    ap.add_argument("--persist-backfill", action="store_true",
                    help="OPERATOR-ONLY: write proposals under narrative_cogap_backfill")
    ap.add_argument("--out", help="write per-day results JSON here")
    args = ap.parse_args()

    rows = _load_offline(args.offline) if args.offline else None
    if args.persist_backfill and args.no_llm:
        ap.error("--persist-backfill requires the LLM leg")

    results = []
    for scan_d in _trading_days(date.fromisoformat(args.start), date.fromisoformat(args.end)):
        r = await _replay_one(scan_d, rows, no_llm=args.no_llm,
                              persist_backfill=args.persist_backfill)
        results.append(r)
        if args.no_llm:
            flag = "GATED" if r["gated"] else "  -  "
            src = r["input_sources"]
            print(f"{r['date']}  {flag}  today={len(r['today']):2d} pool={len(r['pool']):2d} "
                  f"g/a/c={src['grounded']}/{src['analysis']}/{src['catalyst']} "
                  f"~{r['est_input_tokens']:5d} tok  today:{','.join(r['today'])}")
        else:
            print(f"{r['date']}  themes={r.get('themes', 0)}  {r.get('names', [])}"
                  f"{'  ERR:' + str(r['error'])[:80] if r.get('error') else ''}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.out}")

    n_gated = sum(1 for r in results if r.get("gated") or r.get("themes", 0) or r.get("names"))
    print(f"\n{len(results)} weekdays replayed · window={LANE2_WINDOW_TRADING_DAYS}td "
          f"· {n_gated} day(s) past the v2 gate" if args.no_llm else "")


if __name__ == "__main__":
    asyncio.run(main())
