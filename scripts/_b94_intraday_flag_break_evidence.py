"""Backward check: intraday flag-break detector signal evidence.

Trigger: #94 ADR 0005 shipped Commit 1 2026-05-23 — real-time intraday
detector that catches the MOMENT a TIGHTENING/COILED/TRIGGERED ticker
breaks above its base_high with volume confirmation.

Per `feedback_methodology_insights_need_periodic_revalidation.md`:
every methodology insight (filter shape, threshold, signal) must have
a monthly auto-refresh so yesterday's "proven" finding doesn't
silently become today's stale assumption.

This script computes the forward-return distribution of detected
intraday flag-breaks and surfaces the decision-gate metrics for
graduation to operator-confirm entry (Phase 2 of ADR 0005).

Method:
  1. Pull all mi_flag_breaks where break_date <= CURRENT_DATE - 12d
     (10d forward-return window settled)
  2. Filter parent_invalidated_eod = FALSE per Gemini contract
     (excludes structurally-failed breakouts)
  3. Compute forward returns from break-day open to settle-day close.
     Entry = break-day OPEN (not break_price — that's the detection
     moment; real entry would be next available bar after detection)
  4. Slice by parent_stage, by Sugar Baby cohort membership, by
     break magnitude band, by volume conviction band
  5. Decision matrix per feedback_sample_size_discipline:
     - N≥10 + avg ret_5d ≥ +3% + WR (≥+5%) ≥ 35%: PROMOTE to Phase 2
       (operator-confirm entry via /flagbreak ENTER TICKER)
     - N≥10 + signal weak: revise detector criteria
     - N<10: continue observing

Run: docker exec apollo-market python -m scripts._b94_intraday_flag_break_evidence
"""
import asyncio
from collections import defaultdict


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    print("=" * 100)
    print("#94 Intraday flag-break detector — signal evidence")
    print("=" * 100)
    print()

    async with pool.acquire() as conn:
        # Cohort: breaks settled (10d window elapsed) + not invalidated EOD
        rows = await conn.fetch("""
            SELECT b.ticker, b.break_date, b.parent_stage,
                   b.base_high, b.break_price, b.pct_above_base_high,
                   b.volume_pct_of_adv, b.in_sugar_baby_cohort,
                   b.minutes_since_open,
                   -- Forward returns from break-day open (realistic entry per
                   -- feedback_validate_metric_before_decision; the break_price
                   -- is detection moment, not actionable entry)
                   d0.open_price AS entry_px,
                   d5.close       AS close_d5,
                   d10.close      AS close_d10,
                   CASE WHEN d0.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d0.open_price - 1) * 100
                        ELSE NULL END AS ret_5d,
                   CASE WHEN d0.open_price > 0 AND d10.close IS NOT NULL
                        THEN (d10.close / d0.open_price - 1) * 100
                        ELSE NULL END AS ret_10d
            FROM mi_flag_breaks b
            LEFT JOIN mi_daily_closes d0
                ON d0.ticker = b.ticker AND d0.trade_date = b.break_date
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date > b.break_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = b.ticker AND trade_date > b.break_date
                ORDER BY trade_date ASC OFFSET 9 LIMIT 1
            ) d10 ON TRUE
            WHERE b.break_date <= CURRENT_DATE - INTERVAL '7 days'
              AND b.parent_invalidated_eod = FALSE
            ORDER BY b.break_date DESC
        """)

        # Count of invalidated rows (for context — shows reconciliation working)
        invalidated_count = await conn.fetchval("""
            SELECT COUNT(*) FROM mi_flag_breaks WHERE parent_invalidated_eod = TRUE
        """)

    settled_5d = [r for r in rows if r["ret_5d"] is not None]
    settled_10d = [r for r in rows if r["ret_10d"] is not None]

    print(f"Total breaks (parent_invalidated_eod=FALSE): {len(rows)}")
    print(f"Settled 5d window: {len(settled_5d)}")
    print(f"Settled 10d window: {len(settled_10d)}")
    print(f"Invalidated EOD (excluded): {invalidated_count}")
    print()

    if not settled_10d:
        print("→ No settled 10d window data yet. Need ~2 weeks of accumulated breaks.")
        print("  Decision gate cannot run until break_date <= CURRENT_DATE - 12d data exists.")
        return

    # Overall aggregate
    avg_5d = sum(r["ret_5d"] for r in settled_5d) / len(settled_5d) if settled_5d else 0
    avg_10d = sum(r["ret_10d"] for r in settled_10d) / len(settled_10d)
    winners_5d = sum(1 for r in settled_5d if r["ret_5d"] >= 5)
    winners_10d = sum(1 for r in settled_10d if r["ret_10d"] >= 5)
    big_winners_10d = sum(1 for r in settled_10d if r["ret_10d"] >= 10)
    wr_5d = 100 * winners_5d / len(settled_5d) if settled_5d else 0
    wr_10d = 100 * winners_10d / len(settled_10d) if settled_10d else 0
    wr_big_10d = 100 * big_winners_10d / len(settled_10d) if settled_10d else 0

    print("=" * 100)
    print("AGGREGATE — all intraday breaks (settled 10d, parent_invalidated_eod=FALSE)")
    print("=" * 100)
    print(f"N (10d settled):  {len(settled_10d)}")
    print(f"avg 5d:           {avg_5d:+.2f}%")
    print(f"avg 10d:          {avg_10d:+.2f}%")
    print(f"WR ≥+5% (10d):    {winners_10d}/{len(settled_10d)} ({wr_10d:.1f}%)")
    print(f"WR ≥+10% (10d):   {big_winners_10d}/{len(settled_10d)} ({wr_big_10d:.1f}%)")
    print()

    # Slice by parent_stage
    print("=" * 100)
    print("BY PARENT STAGE")
    print("=" * 100)
    by_stage: dict[str, list] = defaultdict(list)
    for r in settled_10d:
        by_stage[r["parent_stage"]].append(r["ret_10d"])
    print(f"{'STAGE':<13} {'N':>5} {'avg_10d':>10} {'WR_5pct':>10} {'WR_10pct':>10}")
    print("-" * 55)
    for stage in ["TRIGGERED", "COILED", "TIGHTENING"]:
        items = by_stage.get(stage, [])
        if not items:
            continue
        a = sum(items) / len(items)
        w5 = sum(1 for v in items if v >= 5)
        w10 = sum(1 for v in items if v >= 10)
        print(f"{stage:<13} {len(items):>5} {a:>+9.2f}% "
              f"{w5}/{len(items):<3} ({100*w5//len(items):>2}%)   "
              f"{w10}/{len(items):<3} ({100*w10//len(items):>2}%)")
    print()

    # Slice by Sugar Baby cohort membership (read-side context, not coupling)
    print("=" * 100)
    print("BY SUGAR BABY COHORT MEMBERSHIP (context only)")
    print("=" * 100)
    in_cohort = [r["ret_10d"] for r in settled_10d if r["in_sugar_baby_cohort"]]
    not_in_cohort = [r["ret_10d"] for r in settled_10d if not r["in_sugar_baby_cohort"]]
    if in_cohort:
        a = sum(in_cohort) / len(in_cohort)
        w = sum(1 for v in in_cohort if v >= 5)
        print(f"In cohort:     N={len(in_cohort):<3} avg={a:+.2f}% WR≥+5%={w}/{len(in_cohort)} ({100*w//len(in_cohort)}%)")
    if not_in_cohort:
        a = sum(not_in_cohort) / len(not_in_cohort)
        w = sum(1 for v in not_in_cohort if v >= 5)
        print(f"Not in cohort: N={len(not_in_cohort):<3} avg={a:+.2f}% WR≥+5%={w}/{len(not_in_cohort)} ({100*w//len(not_in_cohort)}%)")
    print()

    # Decision gate
    print("=" * 100)
    print("DECISION GATE — graduation to Phase 2 (operator-confirm /flagbreak entry)")
    print("=" * 100)
    n = len(settled_10d)
    if n < 10:
        print(f"→ N<10 ({n} settled 10d). CONTINUE OBSERVING.")
        print(f"  Current rate ≈ depends on market regime; estimated N≥10 in 2-4 weeks.")
        print(f"  Re-evaluate via monthly quarterly_review.py sweep.")
    elif avg_10d > 3 and wr_10d > 35:
        print(f"→ PROMOTE to Phase 2.")
        print(f"  N={n} settled, avg_10d={avg_10d:+.2f}%, WR≥+5%={wr_10d:.1f}%.")
        print(f"  Design operator-confirm entry: `/flagbreak ENTER TICKER` submits")
        print(f"  bracket order (stop at base_low, sized via mi_strategies multiplier).")
        print(f"  See ADR 0005 §Out of scope for Phase 2 deliverables.")
    elif wr_10d < 25 or avg_10d < 0:
        print(f"→ SIGNAL WEAK at N>=10. Detector needs REVISION before Phase 2:")
        print(f"  - Tighten volume-pace threshold (currently ≥100% ADV projection)?")
        print(f"  - Tighten opening-30min guard (currently ≥15% ADV raw floor)?")
        print(f"  - Require minimum pct_above_base_high (currently ANY positive)?")
        print(f"  - Filter to cohort × break only?")
    else:
        print(f"→ MARGINAL at N>=10. Continue observing; review at N≥30.")
        print(f"  N={n}, avg_10d={avg_10d:+.2f}%, WR={wr_10d:.1f}%.")
    print()
    print("Caveats per feedback_validate_metric_before_decision:")
    print("  - Forward returns from break-day OPEN as entry approximation; actual")
    print("    intraday-trigger entry would fill at the break price moment")
    print("    (slightly different — usually better since break price < day open")
    print("    for some patterns, worse for others). Phase 2 design must use")
    print("    minute-bar simulation to validate against actionable entry.")
    print("  - 5d/10d windows may be too short for continuation-flag holds.")
    print("    Consider 15d/20d once data accumulates.")
    print("  - Sample skew: regime sensitivity. Re-evaluate across regime shifts.")
    print()
    print("Cross-references:")
    print("  - feedback_methodology_insights_need_periodic_revalidation.md")
    print("  - data_gated_reviews.yaml::intraday_flag_break_signal_n10")
    print("  - ADR 0005 §Out of scope (Phase 2 entry execution design)")


if __name__ == "__main__":
    asyncio.run(main())
