"""#337 — MONTHLY judge-judgment review (aggregate "is the judge calling EPs right?").

The importable home for the review logic so the scheduler (monthly_backward_check_sweep) can run
it without importing from scripts/. `scripts/monthly_judge_review.py` is a thin CLI over this.

READ-ONLY. Distinct from /why (per-ticker, #336): this is the AGGREGATE view over a window.

DRAWN FROM what we already run:
  • the alerts⋈outcomes join verified in eval_catalyst_materiality (o.scan_date = a.alert_date),
  • the promote/hold/demote framing of the judge_delta_digest (the ALERT-TIER axis; the
    judge never sets the catalyst grade),
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
       -- #233 second-opinion telemetry: the three reads of one catalyst.
       a.catalyst_quality, a.gemini_validation, a.judge_grade,
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

# #233 (operator-signed 2026-08-27). The date the second-opinion block began being RENDERED to
# the judge — rubric rule 7. Everything before it is the natural-agreement baseline; everything
# after is the judge having been TOLD about the disagreement.
#
# ⚠ THIS IS THE DOUBLE-COUNTING TEST the operator asked for by name. The judge already reads
# Perplexity's [Web summary] text, so its grade is not an independent witness; rule 7 tells the
# judge to re-read the evidence rather than treat the disagreement as a vote. If that instruction
# holds, `sided_with_second_opinion` should be roughly FLAT across this boundary. A jump means
# the judge is voting with the second model instead of re-reading — one source counted twice.
_SECOND_OPINION_LIVE_FROM = "2026-08-27"


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
    # #233 — cohorts split on whether the judge was TOLD about the disagreement.
    so = {"before": {"n": 0, "sided": 0}, "after": {"n": 0, "sided": 0}}
    for r in rows:
        # Only alerts where the second model DISAGREED with the label are in scope: agreement
        # renders nothing, so it cannot double-count. `judge_grade` is NULL on rows written
        # before it was persisted (2026-08-27) — those are simply not measurable, not "no".
        _lab, _so_g, _jg = (r.get("catalyst_quality"), r.get("gemini_validation"),
                            r.get("judge_grade"))
        if _lab and _so_g and _jg and _so_g != _lab:
            era = ("after" if str(r.get("alert_date")) >= _SECOND_OPINION_LIVE_FROM
                   else "before")
            so[era]["n"] += 1
            if _jg == _so_g:
                so[era]["sided"] += 1
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
        "second_opinion": so,
    }


def format_judge_review(agg, days):
    """Pure formatter — the monthly judge-review digest. SURFACES facts, prescribes nothing."""
    L = [f"⚖️  MONTHLY JUDGE REVIEW — last {days}d",
         f"judge-driven grades: {agg['n']}  ·  with settled 5d outcome: {agg['settled']}",
         ""]
    dc = agg["dir_counts"]
    # TWO different things, deliberately on TWO lines (2026-08-27): dir_counts is the judge's
    # OWN note (raw model output, often answered on the catalyst-grade axis), while
    # agreement_rate is the FACT of whether the tier moved. One line held both and read as
    # a single verdict.
    L.append(f"Judge's own note:  promote {dc.get('promote',0)} · hold {dc.get('hold',0)} · "
             f"demote {dc.get('demote',0)}")
    L.append(f"Alert tier vs our score:  the judge kept our score's tier on "
             f"{agg['agreement_rate']:.0f}% of them")
    L.append("")
    L.append("By the judge's own note (fwd 5d — directional only, win% is drift-saturated):")
    for d in ("promote", "hold", "demote"):
        L.append(f"   {d:8s} {_stat_line(agg['by_dir'][d])}")
    L.append("")
    L.append("By the alert tier the judge set (fwd 5d):")
    for tier in ("HIGH", "MODERATE", "none"):
        if tier in agg["by_tier"]:
            L.append(f"   {tier:9s} {_stat_line(agg['by_tier'][tier])}")
    L.append("")
    # #233 — the double-counting watch the operator asked for by name (2026-08-27).
    so = agg.get("second_opinion") or {}
    b, a = so.get("before") or {"n": 0, "sided": 0}, so.get("after") or {"n": 0, "sided": 0}
    if b["n"] or a["n"]:
        L.append("🔁 SECOND OPINION — when another model graded the catalyst differently, how "
                 "often did the judge land on ITS grade?")

        def _pct(c):
            return f"{c['sided']}/{c['n']} = {100*c['sided']/c['n']:.0f}%" if c["n"] else "n/a"
        L.append(f"   before it was told (natural agreement): {_pct(b)}")
        L.append(f"   after  it was told (rule 7 live):       {_pct(a)}")
        L.append("   Flat across the two = the judge is re-reading the evidence, as instructed.")
        L.append("   A jump = it is voting with the second model, which counts one source twice")
        L.append("   (that model's web summary is already in the judge's evidence).")
        if b["n"] < 20 or a["n"] < 20:
            L.append("   ⚠ under 20 in a cohort — not yet readable, do not act on it.")
        L.append("")
    ud = agg["unjustified_demotes"]
    # Renamed 2026-08-02 (operator ruling). "UNJUSTIFIED" ASSERTED an error the data cannot show:
    # he reviewed both flagged names — CLF (net loss behind a tripled EBITDA) and WKC (profit surge
    # from transient fuel-price volatility) — and ruled the judge CORRECT on both: *"aligned, the
    # stocks looks fine but not true EP moving."* A 5-day run does not make a name an EP, so the
    # heading was labelling correct judgements as errors purely because price rose. Neutral now: it
    # asks a question instead of asserting one.
    L.append(f"🔎 DEMOTIONS THAT SUBSEQUENTLY RAN (≥+{_UNJUSTIFIED_DEMOTE_5D:.0f}% in 5d) — {len(ud)}. Not necessarily wrong; the 5d move is not an EP verdict:")
    if not ud:
        L.append("   (none this window)")
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
