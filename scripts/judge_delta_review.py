"""Judge delta review — the operator's flip-authorization surface (#244 / W3, ADR 0011).

Lists EVERY judge PROMOTION and DEMOTION over a window so the operator can eyeball
judgment-correctness BEFORE flipping holistic_judge_enabled ON (the HARD gate — the agent
never self-certifies the demotion list). Complements the Unjustified Demotion Sweep
(scripts/unjustified_demotion_sweep.py, which flags only the demotes that then RAN ≥+18%):
this shows the FULL bidirectional delta with context, the sweep is the winner-killing alarm.

Each row carries floor→judge tier, materiality, the judge's load-bearing rationale, and the
5d MFE (did the name actually run, from mi_daily_closes) so a promotion's payoff / a
demotion's avoided-or-missed move is visible at a glance.

Run (read-only): docker exec apollo-market python scripts/judge_delta_review.py [--window-days N]
Empty until the judge shadow columns accrue (first real fire 2026-06-09). Build-ahead-of-data.
"""
import argparse
import asyncio

from agents.market_intelligence import db
from agents.market_intelligence.collector import et_today

# MFE from prices (regime-independent) — same LATERAL as missed_outcomes.py:341 / the sweep.
_DELTA_SQL = """
WITH deltas AS (
    SELECT ticker, alert_date, baseline_floor_tier, judge_tier, judge_direction,
           judge_materiality_tier, judge_rationale, gap_pct, ep_score, catalyst_quality
    FROM mi_ep_alerts
    WHERE judge_direction = $2 AND alert_date >= $1 AND judge_tier IS NOT NULL
),
with_mfe AS (
    SELECT d.*,
           CASE WHEN d0.open_price > 0 AND h5.h IS NOT NULL
                THEN (h5.h - d0.open_price) / d0.open_price END AS mfe_5d
    FROM deltas d
    LEFT JOIN LATERAL (
        SELECT open_price FROM mi_daily_closes
        WHERE ticker = d.ticker AND trade_date = d.alert_date
    ) d0 ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(high_price) AS h FROM (
            SELECT high_price FROM mi_daily_closes
            WHERE ticker = d.ticker AND trade_date >= d.alert_date
            ORDER BY trade_date ASC LIMIT 6
        ) x
    ) h5 ON TRUE
)
SELECT * FROM with_mfe ORDER BY mfe_5d DESC NULLS LAST
"""


def _fmt(rows, kind: str) -> None:
    if not rows:
        print(f"  (no {kind}s in window)")
        return
    for r in rows:
        mfe = f"+{r['mfe_5d']:.0%}" if r["mfe_5d"] is not None else "n/a"
        print(f"  {r['ticker']:<6} {r['alert_date']}  {r['baseline_floor_tier']}→{r['judge_tier']:<8} "
              f"MFE {mfe:<6} mat={r['judge_materiality_tier']} gap={r['gap_pct']}% "
              f"floor_cat={r['catalyst_quality']}")
        if r["judge_rationale"]:
            print(f"         {r['judge_rationale'][:170]}")


async def main(window_days: int) -> None:
    cutoff = et_today() - __import__("datetime").timedelta(days=window_days)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        promotions = await conn.fetch(_DELTA_SQL, cutoff, "promote")
        demotions = await conn.fetch(_DELTA_SQL, cutoff, "demote")

    print(f"=== Judge delta review — last {window_days}d (since {cutoff}) ===\n")
    print(f"▲ PROMOTIONS ({len(promotions)}) — floor under-rated, judge lifted "
          f"(fat-tail outlier capture; high MFE = the win the floor would have missed):")
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
