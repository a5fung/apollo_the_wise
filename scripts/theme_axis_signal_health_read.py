#!/usr/bin/env python3
"""Meta-rubric STEP-1 health read (#367 DoD): the attribution distribution + the
disagreement-rate between signal (a) company-name attribution and signal (b) co-movement,
over mi_theme_axis_shadow.

THIS IS A HEALTH GAUGE ONLY -- NEVER A FLIP-GATE (#329, 6/24 operator decision, reaffirmed for
STEP-1: "disagreement-rate is a review-load regulator + health gauge ONLY, NEVER a flip-gate").
It measures which of the two refined signals actually separates "theme is the driver" from
"uses theme vocabulary" -- the #368 STEP-2 weighting decision is the operator's call over a
LABELED cohort, not this script's output.

Read-only: only ever SELECTs from mi_theme_axis_shadow. Requires a live DB pool -- if one
isn't reachable in the current environment (e.g. this offline agent worktree, no Postgres/
Docker running), it prints exactly that and exits cleanly rather than fabricating numbers;
the parent session (which has prod DB access) runs it for the real read.

Usage:
  python scripts/theme_axis_signal_health_read.py [--since-days N]
"""
from __future__ import annotations

import asyncio
import sys


async def _run(since_days: int) -> None:
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, alert_date, themeless_flag,
                   structural_attribution_score, structural_attributable,
                   name_attribution_score, name_attributable,
                   cohort_move, ticker_move, co_moving
            FROM mi_theme_axis_shadow
            WHERE alert_date >= CURRENT_DATE - $1::int
            ORDER BY alert_date
            """,
            since_days,
        )

    n = len(rows)
    themeless = sum(1 for r in rows if r["themeless_flag"])
    themed = [r for r in rows if not r["themeless_flag"]]

    print(f"=== #367 STEP-1 theme-axis signal HEALTH READ (health gauge only -- never a flip-gate) ===")
    print(f"N = {n} scored EP HIGHs (last {since_days}d) -- {themeless} themeless / {len(themed)} themed\n")

    if not themed:
        print("No themed rows in window -- nothing to read yet.")
        return

    # ── Attribution distribution: STEP-0 (ticker) vs STEP-1(a) (name) ──────────────────
    struct_attr = sum(1 for r in themed if r["structural_attributable"])
    name_attr = sum(1 for r in themed if r["name_attributable"])
    print("Attribution distribution (of themed rows):")
    print(f"  STEP-0 structural (ticker/keyword) attributable: {struct_attr}/{len(themed)} "
          f"({100*struct_attr/len(themed):.0f}%)")
    print(f"  STEP-1(a) company-NAME attributable:              {name_attr}/{len(themed)} "
          f"({100*name_attr/len(themed):.0f}%)")

    # ── Co-movement distribution ────────────────────────────────────────────────────────
    co_moving_true = sum(1 for r in themed if r["co_moving"] is True)
    co_moving_false = sum(1 for r in themed if r["co_moving"] is False)
    co_moving_unknown = sum(1 for r in themed if r["co_moving"] is None)
    print(f"\nSTEP-1(b) co-movement distribution:")
    print(f"  co-moving:     {co_moving_true}/{len(themed)}")
    print(f"  not co-moving: {co_moving_false}/{len(themed)}")
    print(f"  not computable (no cohort/ticker price data): {co_moving_unknown}/{len(themed)}")

    # ── Disagreement rate: signal (a) vs signal (b), over rows where BOTH are computable ──
    both_computable = [r for r in themed if r["co_moving"] is not None]
    if both_computable:
        disagree = sum(
            1 for r in both_computable if bool(r["name_attributable"]) != bool(r["co_moving"])
        )
        rate = 100 * disagree / len(both_computable)
        print(f"\nDisagreement rate, name_attributable vs co_moving "
              f"(N={len(both_computable)} both-computable): {disagree}/{len(both_computable)} "
              f"({rate:.0f}%)")
    else:
        print("\nDisagreement rate: not computable yet (no rows with both signals present).")

    # ── Secondary: STEP-0 (ticker) vs STEP-1(a) (name) agreement -- the #369 finding itself ──
    struct_vs_name_disagree = sum(
        1 for r in themed if bool(r["structural_attributable"]) != bool(r["name_attributable"])
    )
    print(f"\nSTEP-0 (ticker) vs STEP-1(a) (name) disagreement: "
          f"{struct_vs_name_disagree}/{len(themed)} ({100*struct_vs_name_disagree/len(themed):.0f}%) "
          "-- expected to be large; this is the #369 finding made quantitative "
          "(ticker-intersection under-detects vs name-matching).")

    if len(both_computable) < 25:
        print(f"\n⚠ SMALL-N CAVEAT: only {len(both_computable)} both-computable rows -- do not "
              "read this rate as settled; it will move as N grows. Small-N is expected this "
              "early (#329 6/24: 'small-N caveat -- don't read low early counts as green').")


def main() -> None:
    args = sys.argv[1:]
    since_days = 120
    if "--since-days" in args:
        since_days = int(args[args.index("--since-days") + 1])
    try:
        asyncio.run(_run(since_days))
    except Exception as e:
        print(
            "Could not reach the live DB pool from this environment "
            f"({type(e).__name__}: {e}).\n"
            "This script is ready to run as-is inside apollo-market (or any environment with "
            "DB access) -- it is READ-ONLY (SELECT from mi_theme_axis_shadow only) and never "
            "a flip-gate. Run it there to produce the real health read."
        )


if __name__ == "__main__":
    main()
