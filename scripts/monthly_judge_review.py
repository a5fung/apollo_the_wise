"""#337 v1 — MONTHLY judge-judgment review (aggregate "is the judge calling EPs right?").

READ-ONLY. Distinct from /why (per-ticker, #336): this is the AGGREGATE view over a window of
judge decisions, for periodic (monthly) review of the load-bearing grade judge.

DRAWN FROM what we already have:
  • the alerts⋈outcomes join verified in eval_catalyst_materiality (o.scan_date = a.alert_date),
  • the promote/hold/demote framing of the judge_delta_digest,
  • the SURFACES-NEVER-PRESCRIBES discipline of the weekly system review
    (feedback_weekly_review_surface_not_prescribe): this report states facts; it proposes NO code.

METRIC HONESTY (feedback_validate_metric_before_decision): fwd-from-gap-close win% is
drift-dominated/saturated and CANNOT by itself say a call was right. So the report leads with the
signals that DO discriminate — the direction-vs-outcome split and the Unjustified-Demotion sweep
(absolute winners the judge demoted, ADR 0011's named guard) — and labels win% as directional only.
The verdict on the judge is OPERATOR labels on the sampled rows, never this script's own score.

v1 is a STANDALONE on-demand report (start + iterate). Refine path: fold into the existing
monthly_backward_check_sweep (auto-run + Telegram) once the format settles; add realized-R and the
has_direct_source footprint (ep_grade_decision) as columns mature.

Run (read-only, on the server):
  docker exec apollo-market python /app/scripts/monthly_judge_review.py --days 30
"""
import argparse
import asyncio
import statistics

from agents.market_intelligence.db import get_pool

_SQL = """
SELECT a.ticker, a.alert_date, a.score_tier, a.baseline_floor_tier,
       a.judge_tier, a.judge_direction, a.judge_materiality_tier, a.fire_axes,
       a.judge_rationale, o.fwd_5d_pct, o.fwd_10d_pct
FROM mi_ep_alerts a
LEFT JOIN mi_ep_scan_outcomes o ON o.ticker = a.ticker AND o.scan_date = a.alert_date
WHERE a.alert_date >= (CURRENT_DATE - ($1::int))
  AND a.grade_engine_authority = 'judge'      -- the judge actually drove the grade
ORDER BY a.alert_date DESC, a.ticker
"""

# A demote that ran up at least this much in 5d = a winner the judge demoted (ADR 0011 guard).
_UNJUSTIFIED_DEMOTE_5D = 5.0


def _stat_line(vals: list) -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n=0"
    wr = 100 * sum(1 for v in vals if v > 0) / len(vals)
    return (f"n={len(vals)} mean={statistics.mean(vals):+.1f}% "
            f"median={statistics.median(vals):+.1f}% win(dir-only)={wr:.0f}%")


def aggregate_judge_review(rows: list) -> dict:
    """Pure aggregation over judge-decision rows (each: judge_tier, judge_direction,
    baseline_floor_tier, fwd_5d_pct, ...). No I/O — fixture-tested."""
    n = len(rows)
    dir_counts = {"promote": 0, "hold": 0, "demote": 0, "none": 0}
    agree = 0
    by_dir = {"promote": [], "hold": [], "demote": []}
    by_tier = {}
    unjustified_demotes = []
    settled = 0
    for r in rows:
        d = (r.get("judge_direction") or "none").lower()
        dir_counts[d] = dir_counts.get(d, 0) + 1
        if r.get("judge_tier") and r.get("judge_tier") == r.get("baseline_floor_tier"):
            agree += 1
        f5 = r.get("fwd_5d_pct")
        if f5 is not None:
            settled += 1
            if d in by_dir:
                by_dir[d].append(f5)
            by_tier.setdefault(r.get("judge_tier") or "?", []).append(f5)
            if d == "demote" and f5 >= _UNJUSTIFIED_DEMOTE_5D:
                unjustified_demotes.append(r)
    return {
        "n": n, "settled": settled,
        "dir_counts": dir_counts,
        "agreement_rate": (100 * agree / n) if n else 0.0,
        "by_dir": by_dir, "by_tier": by_tier,
        "unjustified_demotes": unjustified_demotes,
    }


def format_judge_review(agg: dict, days: int) -> str:
    """Pure formatter — the monthly judge-review digest. SURFACES facts, prescribes nothing."""
    L = [f"⚖️  MONTHLY JUDGE REVIEW — last {days}d",
         f"judge-driven grades: {agg['n']}  ·  with settled 5d outcome: {agg['settled']}",
         ""]
    dc = agg["dir_counts"]
    L.append(f"Direction vs floor:  promote {dc.get('promote',0)} · hold {dc.get('hold',0)} · "
             f"demote {dc.get('demote',0)}   (judge==floor tier {agg['agreement_rate']:.0f}%)")
    L.append("")
    L.append("By direction (fwd 5d — directional only, win% is drift-saturated):")
    for d in ("promote", "hold", "demote"):
        L.append(f"   {d:8s} {_stat_line(agg['by_dir'][d])}")
    L.append("")
    L.append("By judge tier (fwd 5d):")
    for tier in ("HIGH", "MODERATE", "none"):
        if tier in agg["by_tier"]:
            L.append(f"   {tier:9s} {_stat_line(agg['by_tier'][tier])}")
    L.append("")
    ud = agg["unjustified_demotes"]
    L.append(f"⚠️  UNJUSTIFIED-DEMOTION sweep (judge demoted, ran ≥+{_UNJUSTIFIED_DEMOTE_5D:.0f}% in 5d) — {len(ud)}:")
    if not ud:
        L.append("   (none — no winners demoted this window)")
    for r in ud[:15]:
        L.append(f"   {r['alert_date']} {r['ticker']:6s} "
                 f"{r.get('baseline_floor_tier')}→{r.get('judge_tier')}  fwd5d {r['fwd_5d_pct']:+.1f}%")
    L.append("")
    L.append("📋 For OPERATOR labeling (the actual verdict — sample): run /why TICKER on the above")
    L.append("   demotes + the top promotes; label each call right/wrong. This report never self-scores.")
    return "\n".join(L)


async def run(days: int, send: bool = False) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(_SQL, days)]
    text = format_judge_review(aggregate_judge_review(rows), days)
    print(text)
    if send:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(text)
    return text


async def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--send", action="store_true", help="also push to Telegram")
    args = ap.parse_args()
    await run(args.days, send=args.send)


if __name__ == "__main__":
    asyncio.run(_main())
