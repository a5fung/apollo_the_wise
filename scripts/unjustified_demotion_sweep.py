"""Unjustified Demotion Sweep — the winner-killing guard (#244 / W3, ADR 0011 go-live HARD gate).

The Holistic Grade Judge (#240) can move a grade DOWN (demote). The dangerous error is a
WRONG demotion: the low-float squeeze / theme-less "dog" that the judge graded down but that
then RIPPED — a fat-tail winner the judge would have kept us out of once it's load-bearing
(Wave 2). This read-only sweep isolates exactly those cases for operator review.

DESIGN (advisor-reviewed 2026-06-08): the guard joins the demote cohort to MAX FAVORABLE
EXCURSION computed DIRECTLY from mi_daily_closes (the LATERAL pattern from missed_outcomes.py
:341), NOT to mi_ep_missed_outcomes. Reasons:
  - REGIME-INDEPENDENT: "did this ticker run after alert_date" is pure price data — identical
    whether the name was entered (W1 shadow: floor still enters) or suppressed (W2: judge
    demote blocks entry). missed_outcomes EXCLUDES traded names, so it can't see a
    floor-entered judge-demote in shadow; raw prices can.
  - ONE uniform threshold (missed_outcomes stores MFE-as-fraction-from-open; the trades table
    stores realized R off the actual entry/stop — a UNION of the two can't share a threshold).
  - MFE is the better "did it run" signal than realized R for a review tool — no stop/exit noise.

PROXY NOTE: ADR 0011 frames this as "≥ +3R within 5d". No would-be ORB-low stop is stored, and
reconstructing it needs intraday bars (not worth it for a review tool). We use the MFE FRACTION
with a tunable threshold: ~+15-20% ≈ +3R at a typical ~5-7% ORB-low stop. The operator reviews
the flagged names regardless; the threshold only controls what surfaces.

Run (read-only): docker exec apollo-market python scripts/unjustified_demotion_sweep.py
Empty until the judge shadow columns accrue (first real fire 2026-06-09). Build-ahead-of-data.
"""
import argparse
import asyncio
from datetime import timedelta

from agents.market_intelligence import db
from agents.market_intelligence.collector import et_today
from scripts._judge_review_sql import _MFE_EXPR, _MFE_JOINS

# +18% MFE ≈ +3R at a ~6% ORB-low stop. Tunable; documented as a proxy, not true R.
DEFAULT_MFE_THRESHOLD = 0.18
DEFAULT_WINDOW_DAYS = 30

# Demote cohort × MFE-from-prices (regime-independent) — shared LATERAL with the delta
# review (_judge_review_sql): open_d0 = alert-day open; high_5d over the 6 bars from
# alert_date inclusive.
_SWEEP_SQL = f"""
WITH demotes AS (
    SELECT ticker, alert_date, baseline_floor_tier, judge_tier, judge_direction,
           judge_materiality_tier, judge_rationale, gap_pct, ep_score, catalyst_quality
    FROM mi_ep_alerts
    WHERE judge_direction = 'demote' AND alert_date >= $1
),
with_mfe AS (
    SELECT d.*, d0.open_price AS open_d0, h5.h AS high_5d, {_MFE_EXPR}
    FROM demotes d
    {_MFE_JOINS}
)
SELECT ticker, alert_date, baseline_floor_tier, judge_tier, judge_materiality_tier,
       mfe_5d, gap_pct, ep_score, catalyst_quality, judge_rationale
FROM with_mfe
WHERE mfe_5d >= $2
ORDER BY mfe_5d DESC NULLS LAST
"""

# Sister cross-tab: judge_tier × baseline_floor_tier counts over the window (the full
# promote/hold/demote distribution context for the flagged demotes).
_CROSSTAB_SQL = """
SELECT COALESCE(baseline_floor_tier, '(null)') AS floor_tier,
       COALESCE(judge_tier, '(null)')          AS judge_tier,
       COALESCE(judge_direction, '(null)')     AS direction,
       COUNT(*)::INT AS n
FROM mi_ep_alerts
WHERE alert_date >= $1 AND judge_tier IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
"""


async def main(window_days: int, mfe_threshold: float) -> None:
    cutoff = et_today() - timedelta(days=window_days)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        flagged = await conn.fetch(_SWEEP_SQL, cutoff, mfe_threshold)
        crosstab = await conn.fetch(_CROSSTAB_SQL, cutoff)

    print(f"=== Unjustified Demotion Sweep — last {window_days}d (since {cutoff}), "
          f"MFE ≥ +{mfe_threshold:.0%} ===\n")

    if not flagged:
        print("  No flagged demotions (cohort empty until judge shadow cols accrue, or none ran).")
    else:
        print(f"  ⚠ {len(flagged)} judge-DEMOTED name(s) that then ran ≥ +{mfe_threshold:.0%} "
              f"(MFE 5d) — operator review:\n")
        for r in flagged:
            mfe = r["mfe_5d"]
            print(f"  {r['ticker']:<6} {r['alert_date']}  MFE +{mfe:.0%}  "
                  f"floor={r['baseline_floor_tier']}→judge={r['judge_tier']} "
                  f"mat={r['judge_materiality_tier']} gap={r['gap_pct']}% "
                  f"floor_cat={r['catalyst_quality']}")
            if r["judge_rationale"]:
                print(f"         rationale: {r['judge_rationale'][:160]}")

    print(f"\n=== judge_tier × baseline_floor_tier (last {window_days}d) ===")
    if not crosstab:
        print("  (no judged rows yet)")
    else:
        for r in crosstab:
            print(f"  floor={r['floor_tier']:<9} judge={r['judge_tier']:<9} "
                  f"{r['direction']:<8} n={r['n']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--mfe-threshold", type=float, default=DEFAULT_MFE_THRESHOLD,
                    help="MFE fraction proxy for +3R (default 0.18 ≈ +3R at a ~6%% ORB stop)")
    args = ap.parse_args()
    asyncio.run(main(args.window_days, args.mfe_threshold))
