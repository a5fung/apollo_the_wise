"""#337 — MONTHLY judge-judgment review (aggregate "is the judge calling EPs right?").

The importable home for the review logic so the scheduler (monthly_backward_check_sweep) can run
it without importing from scripts/. `scripts/monthly_judge_review.py` is a thin CLI over this.

READ-ONLY. Distinct from /why (per-ticker, #336): this is the AGGREGATE view over a window.

DRAWN FROM what we already run:
  • the alerts⋈outcomes join verified in eval_catalyst_materiality (o.scan_date = a.alert_date),
  • the promote/hold/demote framing of the judge_delta_digest,
  • the SURFACES-NEVER-PRESCRIBES discipline of the weekly system review
    (feedback_weekly_review_surface_not_prescribe): this report states facts; it proposes NO code.

METRIC HONESTY (feedback_validate_metric_before_decision): fwd-from-gap-close win% is
drift-dominated/saturated and CANNOT by itself say a call was right. The report leads with the
signals that DO discriminate — direction-vs-outcome + the Unjustified-Demotion sweep (winners the
judge demoted, ADR 0011's named guard) — and labels win% directional-only. The verdict on the
judge is OPERATOR labels on the sampled rows, never this module's own score.
"""
import statistics

from agents.market_intelligence.ep_grade_judge import format_tier_transition

_SQL = """
SELECT a.ticker, a.alert_date, a.score_tier, a.baseline_floor_tier,
       a.judge_tier, a.judge_direction, a.judge_materiality_tier, a.fire_axes,
       a.grounded_text,
       o.fwd_5d_pct,
       t.realized_pnl, t.traded
FROM mi_ep_alerts a
LEFT JOIN mi_ep_scan_outcomes o ON o.ticker = a.ticker AND o.scan_date = a.alert_date
-- Aggregate trades per (ticker, alert_date) FIRST so a multi-leg trade can't fan-out the alert
-- row and double-count the judge decision. Only CLOSED legs count toward realized P&L (the
-- codebase-wide convention; open/partial legs carry total_pnl=0 / unrealized and must not leak).
LEFT JOIN (
    SELECT ticker, alert_date,
           SUM(total_pnl) FILTER (WHERE status = 'closed') AS realized_pnl,
           TRUE AS traded
    FROM mi_live_trades GROUP BY ticker, alert_date
) t ON t.ticker = a.ticker AND t.alert_date = a.alert_date
WHERE a.alert_date >= (CURRENT_DATE - ($1::int))
  AND a.grade_engine_authority = 'judge'      -- the judge actually drove the grade
ORDER BY a.alert_date DESC, a.ticker
"""

# A demote that ran up at least this much in 5d = a winner the judge demoted (ADR 0011 guard).
_UNJUSTIFIED_DEMOTE_5D = 5.0


def recompute_has_direct_source(grounded_text):
    """(has_direct, has_markers) from the STORED corpus, deterministically. build_grounded_text
    prefixes each source: '[SEC <form> filed …]', '[Benzinga …]', '[Web summary] …'. A direct
    source = an SEC filing or a Benzinga wire present (mirrors corpus_provenance's
    sec_*/benzinga_pr rule, ep_detector.py). `has_markers` is False for pre-W1 / thin-grounded rows that carry no
    section markers at all — excluded from the assessable denominator."""
    if not grounded_text:
        return False, False
    has_markers = ("[SEC " in grounded_text or "[Benzinga " in grounded_text
                   or "[Web summary]" in grounded_text)
    has_direct = ("[SEC " in grounded_text or "[Benzinga " in grounded_text)
    return has_direct, has_markers


def _stat_line(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n=0"
    wr = 100 * sum(1 for v in vals if v > 0) / len(vals)
    return (f"n={len(vals)} mean={statistics.mean(vals):+.1f}% "
            f"median={statistics.median(vals):+.1f}% win(dir-only)={wr:.0f}%")


def aggregate_judge_review(rows):
    """Pure aggregation over judge-decision rows. No I/O — fixture-tested."""
    n = len(rows)
    dir_counts = {"promote": 0, "hold": 0, "demote": 0, "none": 0}
    agree = 0
    by_dir = {"promote": [], "hold": [], "demote": []}
    by_tier = {}
    unjustified_demotes = []
    settled = 0
    direct_assessable = 0
    direct_present = 0
    traded_n = 0
    traded_pnl = 0.0
    for r in rows:
        has_direct, has_markers = recompute_has_direct_source(r.get("grounded_text"))
        if has_markers:
            direct_assessable += 1
            if has_direct:
                direct_present += 1
        if r.get("traded"):
            traded_n += 1
            traded_pnl += float(r.get("realized_pnl") or 0.0)
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
        "direct_assessable": direct_assessable, "direct_present": direct_present,
        "traded_n": traded_n, "traded_pnl": traded_pnl,
    }


def format_judge_review(agg, days):
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
                 f"{format_tier_transition(r.get('baseline_floor_tier'), r.get('judge_tier'))}"
                 f"  fwd5d {r['fwd_5d_pct']:+.1f}%")
    L.append("")
    da, dp = agg.get("direct_assessable", 0), agg.get("direct_present", 0)
    pct = (100 * dp / da) if da else 0.0
    L.append("🔌 has_direct_source footprint (#329 — judge blind to it until #335):")
    L.append(f"   {dp}/{da} assessable rows had a DIRECT source the judge was shown 'no' for ({pct:.0f}%)")
    L.append("")
    L.append(f"💵 Realized (alerts that became trades): traded {agg.get('traded_n',0)} · "
             f"total P&L ${agg.get('traded_pnl',0.0):+,.0f}")
    L.append("")
    L.append("📋 For OPERATOR labeling (the actual verdict — sample): run /why TICKER on the above")
    L.append("   demotes + the top promotes; label each call right/wrong. This report never self-scores.")
    return "\n".join(L)


async def run(days=30, send=False):
    """Fetch + format. `send=True` pushes to Telegram (the monthly-sweep path)."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(_SQL, days)]
    text = format_judge_review(aggregate_judge_review(rows), days)
    if send:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(text)
    return text
