"""Shared row-SQL + judge-payload assembly for the #250 judge eval scripts
(judge_backfill_replay.py, eval_judge_models.py) — READ-ONLY helpers.

Extracted 2026-06-09 review pass: both scripts had copy-pasted the profile-fetch →
cap-coercion → rule_materiality → payload-assembly block (and near-identical SQL),
the lockstep-divergence trap (#236 class, feedback_single_source_of_truth). The
LIVE copy in ep_detector._judge_shadow deliberately stays inline — hot path, its
own concurrency/fail-open framing; THIS module is the one source for the offline
eval pair only.
"""
from agents.market_intelligence.catalyst_materiality import (
    extract_deal_value, rule_materiality,
)
from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs

# Floor = COALESCE(baseline_floor_tier, score_tier): baseline_floor_tier is NULL on
# pre-W2 rows (added ~2026-06-08 15:10 ET); score_tier is the floor verdict that
# actually drove them. detected_at = the grade timestamp (grounded-reconstruction cut).
REPLAY_SQL = """
SELECT ticker, alert_date, detected_at,
       COALESCE(baseline_floor_tier, score_tier) AS floor_tier,
       score_tier, catalyst_quality, catalyst, claude_analysis,
       in_active_theme, in_narrative_cohort, gap_pct, pm_rvol, vol_percentile,
       ep_score, grounded_text
FROM mi_ep_alerts
WHERE alert_date >= (CURRENT_DATE - ($1::int))
  AND score_tier IN ('HIGH', 'MODERATE')
ORDER BY alert_date, ticker
"""


async def fetch_profile(ticker):
    """(market_cap_float|None, sector|None, company|None) — FMP profile, fail-soft.
    Owns the float coercion (FMP marketCap can be a string — the #173-class trap)."""
    market_cap = sector = company = None
    try:
        prof = await get_fmp_profile(ticker) or {}
        market_cap = prof.get("marketCap")
        sector, company = prof.get("sector"), prof.get("companyName")
    except Exception:
        pass
    try:
        market_cap = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap = None
    return market_cap, sector, company


def build_judge_payload(row, grounded_text, market_cap, sector, active_narratives=None):
    """(payload, rule_mat) — mirrors run_ep_scan._judge_shadow's assembly exactly:
    W4 deterministic deal/cap rule tier + assemble_judge_inputs over the row.
    `active_narratives` (lane2-judge-theme-axis): point-in-time PRIOR-day Lane-2
    cohorts for this row's alert_date — None keeps the payload pre-change-identical."""
    rule_mat = rule_materiality(
        extract_deal_value(f"{row['catalyst'] or ''} {row['claude_analysis'] or ''}"),
        market_cap)
    r = {
        "ticker": row["ticker"], "score_tier": row["score_tier"],
        "catalyst_quality": row["catalyst_quality"], "catalyst": row["catalyst"],
        "claude_analysis": row["claude_analysis"], "in_active_theme": row["in_active_theme"],
        "in_narrative_cohort": row["in_narrative_cohort"], "gap_pct": row["gap_pct"],
        "pm_rvol": row["pm_rvol"], "vol_percentile": row["vol_percentile"],
        "ep_score": row["ep_score"],
    }
    payload = assemble_judge_inputs(r, grounded_text=grounded_text, market_cap=market_cap,
                                    sector=sector, materiality_tier=rule_mat,
                                    active_narratives=active_narratives)
    return payload, rule_mat


async def fetch_narratives_for(alert_date):
    """Point-in-time Lane-2 cohorts for one alert_date (lane2-judge-theme-axis replay).

    Same db helper + same `days=5` window as run_ep_scan's live fetch — replay and
    live can never select cohorts differently (the as_of branch enforces PRIOR days
    only; same-day rows are lookahead). Backfill rows ARE included, tagged:
    admissible for REPLAY evaluation only (live reads forward-only by construction;
    the operator weighs the hindsight caveat when reviewing flipped verdicts)."""
    from agents.market_intelligence.db import get_narrative_theme_candidates
    return await get_narrative_theme_candidates(
        days=5, include_backfill=True, as_of=alert_date)


async def resolve_grounded_text(row, company, grounded: bool):
    """(grounded_text, ginfo|None) — the one grounded-vs-stored branch shared by
    judge_backfill_replay and eval_judge_models (#252). grounded=True reconstructs
    the point-in-time corpus (SEC+wires <= detected_at, no web); else the stored
    grounded_text (real on post-W1 rows, thin stored catalyst otherwise)."""
    from scripts._grounded_reconstruct import reconstruct_grounded_text
    if grounded:
        return await reconstruct_grounded_text(
            row["ticker"], row["alert_date"], row["detected_at"],
            company_name=company or "")
    return row["grounded_text"], None
