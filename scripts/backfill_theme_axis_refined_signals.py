#!/usr/bin/env python3
"""Meta-rubric STEP-1 refined-signal backfill (#367): populate the two new relevance signals
onto the 452 historical rows scripts/backfill_theme_axis_shadow.py (#369, STEP-0.5) already
wrote to mi_theme_axis_shadow.

WHY A SEPARATE SCRIPT (mirrors backfill_theme_axis_shadow.py's shape, doesn't replace it):
the STEP-0 backfill already populated theme heat + structural (ticker) attribution correctly
— re-running the full writer would recompute those unnecessarily and re-fetch grounded_text.
This script is surgical: it re-derives the theme cohort (get_theme_heat_asof — mi_theme_axis_shadow
itself only stores theme_name, not the member list) for each ALREADY-LOGGED themed row, then
computes ONLY the two new #367 STEP-1 signals — company-NAME attribution (the #369 fix) and
co-movement — and UPDATEs just those columns. Themeless rows are skipped (no cohort to
attribute to or co-move with; the writer already leaves them NULL/0/False).

READ-ONLY-COMPUTED w.r.t. trade state / grade — this touches only mi_theme_axis_shadow (the
6 new STEP-1 columns) and, as a side effect of company-name resolution, may ADD rows to the
mi_ticker_overrides.company_name cache (an additive, benign persistent lookup — never removes
or overwrites description/sector/industry). Never touches mi_ep_alerts or any live grade.

Per THE LINE: this script is committed RUNNABLE but NOT run against prod by the agent that
wrote it — the parent session runs it (requires network access for uncached company names +
a live DB pool, same runtime as the market agent).

Usage (run inside apollo-market, which has the modules + DB):
  python scripts/backfill_theme_axis_refined_signals.py [--since-days N]            # DRY-RUN
  python scripts/backfill_theme_axis_refined_signals.py [--since-days N] --commit   # write
"""
from __future__ import annotations

import asyncio
import sys

from agents.market_intelligence.db import get_daily_moves, get_pool, get_theme_heat_asof
from agents.market_intelligence.theme_axis_shadow import (
    _ensure_company_names,
    compute_co_movement,
    compute_name_attribution,
    compute_step1_signals,
)


async def _compute_refined_signals(conn, ticker: str, alert_date, grounded_text: str | None):
    """Re-derive the cohort for one already-logged themed row and compute both #367 STEP-1
    signals. Returns None if the row is themeless as-of alert_date (nothing to backfill)."""
    heat = await get_theme_heat_asof(conn, ticker, alert_date)
    if heat is None:
        return None

    # ONE shared pipeline with the live writer (d2-review G1) — divergence here
    # would corrupt the health-read comparison.
    _s1 = await compute_step1_signals(conn, ticker, alert_date, grounded_text, heat["tickers"])
    name_score, name_attributable, matched_names = (
        _s1["name_score"], _s1["name_attributable"], _s1["matched_names"])
    ticker_move, cohort_move, co_moving = (
        _s1["ticker_move"], _s1["cohort_move"], _s1["co_moving"])

    return {
        "name_attribution_score": name_score,
        "name_attributable": name_attributable,
        "matched_names": matched_names,
        "cohort_move": cohort_move,
        "ticker_move": ticker_move,
        "co_moving": co_moving,
    }


async def main() -> None:
    args = sys.argv[1:]
    since_days = 120
    if "--since-days" in args:
        since_days = int(args[args.index("--since-days") + 1])
    commit = "--commit" in args

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.ticker, s.alert_date, s.theme_name, e.grounded_text
            FROM mi_theme_axis_shadow s
            JOIN mi_ep_alerts e ON e.ticker = s.ticker AND e.alert_date = s.alert_date
            WHERE s.alert_date >= CURRENT_DATE - $1::int
              AND s.themeless_flag = FALSE
            ORDER BY s.alert_date
            """,
            since_days,
        )
        print(
            f"{len(rows)} themed mi_theme_axis_shadow rows (last {since_days}d) "
            "eligible for STEP-1 refined-signal backfill"
        )

        if not commit:
            print("\n--- DRY-RUN sample (first 5; NO writes) ---")
            for r in rows[:5]:
                sig = await _compute_refined_signals(
                    conn, r["ticker"], r["alert_date"], r["grounded_text"])
                if sig is None:
                    print(f"  {r['alert_date']} {r['ticker']:6} (now themeless as-of -- skip)")
                    continue
                print(
                    f"  {r['alert_date']} {r['ticker']:6} theme={(r['theme_name'] or '')[:20]:20} "
                    f"name_score={sig['name_attribution_score']} "
                    f"name_attr={sig['name_attributable']} "
                    f"cohort_move={sig['cohort_move']} ticker_move={sig['ticker_move']} "
                    f"co_moving={sig['co_moving']} matched={sig['matched_names'][:4]}"
                )
            print(f"\n(total {len(rows)} rows would be processed with --commit)")
            return

        n = 0
        skipped = 0
        for r in rows:
            sig = await _compute_refined_signals(
                conn, r["ticker"], r["alert_date"], r["grounded_text"])
            if sig is None:
                skipped += 1
                continue
            await conn.execute(
                """
                UPDATE mi_theme_axis_shadow SET
                    name_attribution_score = $3,
                    name_attributable = $4,
                    matched_names = $5,
                    cohort_move = $6,
                    ticker_move = $7,
                    co_moving = $8
                WHERE ticker = $1 AND alert_date = $2
                """,
                r["ticker"], r["alert_date"],
                sig["name_attribution_score"], sig["name_attributable"], sig["matched_names"],
                sig["cohort_move"], sig["ticker_move"], sig["co_moving"],
            )
            n += 1
        print(f"\nbackfilled STEP-1 refined signals onto {n} rows ({skipped} now-themeless skipped)")


if __name__ == "__main__":
    asyncio.run(main())
