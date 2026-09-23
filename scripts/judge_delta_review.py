"""Judge delta review — the operator's flip-authorization surface (#244 / W3, ADR 0011).

Lists EVERY judge PROMOTION and DEMOTION over a window so the operator can eyeball
judgment-correctness BEFORE flipping holistic_judge_enabled ON (the HARD gate — the agent
never self-certifies the demotion list). Complements the Unjustified Demotion Sweep
(scripts/unjustified_demotion_sweep.py, which flags only the demotes that then RAN ≥+18%):
this shows the FULL bidirectional delta with context, the sweep is the winner-killing alarm.

Each row carries our-score→judge alert tier, materiality, the judge's rationale, and the
5d MFE (did the name actually run, from mi_daily_closes) so a promotion's payoff / a
demotion's avoided-or-missed move is visible at a glance.

Run (read-only): docker exec apollo-market python scripts/judge_delta_review.py [--window-days N]
Empty until the judge shadow columns accrue (first real fire 2026-06-09). Build-ahead-of-data.
"""
import argparse
import asyncio
from datetime import timedelta

from agents.market_intelligence import db
from agents.market_intelligence.collector import et_today
from scripts._judge_review_sql import _MFE_EXPR, _MFE_JOINS

# MFE from prices (regime-independent) — shared LATERAL with the sweep (_judge_review_sql).
_DELTA_SQL = f"""
WITH deltas AS (
    SELECT ticker, alert_date, baseline_floor_tier, judge_tier, judge_direction,
           judge_materiality_tier, judge_rationale, gap_pct, ep_score, catalyst_quality
    FROM mi_ep_alerts
    WHERE judge_direction = $2 AND alert_date >= $1 AND judge_tier IS NOT NULL
),
with_mfe AS (
    SELECT d.*, {_MFE_EXPR}
    FROM deltas d
    {_MFE_JOINS}
)
SELECT * FROM with_mfe ORDER BY mfe_5d DESC NULLS LAST
"""


def _fmt(rows, kind: str) -> None:
    if not rows:
        print(f"  (no {kind}s in window)")
        return
    from agents.market_intelligence.ep_grade_judge import format_tier_transition
    for r in rows:
        mfe = f"+{r['mfe_5d']:.0%}" if r["mfe_5d"] is not None else "n/a"
        tier_part = format_tier_transition(r["baseline_floor_tier"], r["judge_tier"])
        print(f"  {r['ticker']:<6} {r['alert_date']}  {tier_part:<22} "
              f"MFE {mfe:<6} mat={r['judge_materiality_tier']} gap={r['gap_pct']}% "
              f"catalyst grade={r['catalyst_quality']}")
        if r["judge_rationale"]:
            print(f"         {r['judge_rationale'][:170]}")


async def main(window_days: int) -> None:
    cutoff = et_today() - timedelta(days=window_days)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        promotions = await conn.fetch(_DELTA_SQL, cutoff, "promote")
        demotions = await conn.fetch(_DELTA_SQL, cutoff, "demote")

    print(f"=== Judge delta review — last {window_days}d (since {cutoff}) ===\n")
    print(f"▲ PROMOTIONS ({len(promotions)}) — our score under-rated it, judge lifted the tier "
          f"(fat-tail outlier capture; high MFE = the win our score would have missed):")
    _fmt(promotions, "promotion")
    print(f"\n▼ DEMOTIONS ({len(demotions)}) — judge cut a gap-only / immaterial HIGH "
          f"(HIGH MFE here = a POSSIBLE WRONG demotion — cross-check the sweep):")
    _fmt(demotions, "demotion")
    print("\nReview both lists for judgment-correctness before flipping the judge ON "
          "(scripts/set_holistic_judge.py on). Run unjustified_demotion_sweep.py for the "
          "winner-killing alarm.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=7)
    args = ap.parse_args()
    asyncio.run(main(args.window_days))
