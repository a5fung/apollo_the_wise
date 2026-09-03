"""Shared row-SQL + judge-payload assembly for the #250 judge eval scripts
(judge_backfill_replay.py, eval_judge_models.py) — READ-ONLY helpers.

Extracted 2026-06-09 review pass: both scripts had copy-pasted the profile-fetch →
cap-coercion → rule_materiality → payload-assembly block (and near-identical SQL),
the lockstep-divergence trap (#236 class, feedback_single_source_of_truth). The
LIVE copy in ep_detector._judge_shadow deliberately stays inline — hot path, its
own concurrency/fail-open framing; THIS module is the one source for the offline
eval pair only.

Re-homed 2026-07-03 (S1/F4, #261 prerequisite): moved from `scripts/` to
`agents/market_intelligence/` because the #343 chart-axis shadow job in
scheduler.py (production code) imports it — prod code must not depend on
scripts/, which the #261 reorg would otherwise be free to shuffle out from
under it. `scripts/_judge_replay_common.py` is now a thin re-export so the
offline eval scripts keep working unchanged.
"""
from agents.market_intelligence.catalyst_materiality import (
    extract_deal_value, rule_materiality,
)
from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import EP_JUDGE_PAYLOAD_COLS
from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs

# Floor = COALESCE(baseline_floor_tier, score_tier): baseline_floor_tier is NULL on
# pre-W2 rows (added ~2026-06-08 15:10 ET); score_tier is the floor verdict that
# actually drove them. detected_at = the grade timestamp (grounded-reconstruction cut).
# Column list = db.EP_JUDGE_PAYLOAD_COLS (the ONE source — see its docstring; #236 lockstep class).
REPLAY_SQL = f"""
SELECT {EP_JUDGE_PAYLOAD_COLS}
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
    except Exception:  # loud-ok: fail-soft by design (see docstring) — feeds the
                        # #343 shadow's materiality tier + offline eval scripts only,
                        # never trade state; a miss degrades to unknown market_cap.
        pass
    try:
        market_cap = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap = None
    return market_cap, sector, company


#: Explicit opt-out for `has_direct_source` auto-recovery. Only eval_judge_enrich's BLIND arm
#: wants the un-recovered value; everything else wants the truth. A sentinel rather than None so
#: "I did not think about it" and "I deliberately want it blind" stop being the same argument —
#: they were, and that is how 8 of 10 callers ended up silently grading a different prompt.
BLIND = object()


def build_judge_payload(row, grounded_text, market_cap, sector, active_narratives=None,
                        tape=None, has_direct_source=None, theme_stage=None, theme_score=None,
                        revenue_stage=None, second_opinion=None, setup_class=None):
    """(payload, rule_mat) — mirrors run_ep_scan._judge_shadow's assembly exactly:
    W4 deterministic deal/cap rule tier + assemble_judge_inputs over the row.
    `active_narratives` (lane2-judge-theme-axis): point-in-time PRIOR-day Lane-2
    cohorts for this row's alert_date — None keeps the payload pre-change-identical.
    `tape` (#299 v2.0-P2): the point-in-time tape-feature dict — None keeps the payload
    byte-identical (the with-vs-without arm of eval_tape_judge passes the computed dict).
    `theme_stage`/`theme_score` (#329 Path A enrich): inputs the LIVE call site does not thread
    — None keeps the payload byte-identical (the BLIND arm of eval_judge_enrich); the ENRICHED
    arm passes them to measure the verdict delta.

    `has_direct_source`/`revenue_stage`: ⚠ THE LIVE SCAN NOW THREADS BOTH (2026-09-01), so a
    caller that leaves them None is NO LONGER mirroring live — it is grading a DIFFERENT prompt
    than production. That is deliberate only for eval_judge_enrich's BLIND arm. Every other
    caller should pass what it can: `has_direct_source` is recoverable from a stored row with
    `judge_review.recompute_has_direct_source(grounded_text)` (the markers are emitted by
    build_grounded_text and sit at the head of the string, so truncation cannot remove them);
    `revenue_stage` is NOT recoverable — it is computed live on earnings day and never
    persisted, so None ("not checked") is the honest value on a replayed row, not a gap.
    `second_opinion` IS rendered into the prompt (ep_grade_judge ~379) and IS passed by the live
    call; `setup_class` is passed live but deliberately never rendered. Both are exposed here so a
    replay caller CAN mirror live — none does yet, because neither is in the stored column set the
    shadow cohort selects. Exposed rather than omitted: an absent parameter is a gap nobody can
    close, while a None one is a gap the guard can name.

    🔑 **`has_direct_source` IS NOW RECOVERED HERE, NOT AT THE CALL SITE (2026-09-02).** The
    recovery was first wired into the one caller that prompted it (the chart-axis shadow job) —
    and a cleanup pass then found the OTHER EIGHT callers still passing None, i.e. still being
    told a confident "no direct source" on every row, which is the exact defect this thread
    exists to remove. `recompute_has_direct_source` needs only `grounded_text`, which this
    function already receives, so there was never a reason for each caller to remember. Pass
    `has_direct_source=BLIND` to opt OUT (eval_judge_enrich's blind arm); pass a real bool to
    override; leave it None and you get the truth.

    `tests/test_judge_payload_completeness.py` fails the build if this signature drifts from
    `assemble_judge_inputs`."""
    if has_direct_source is BLIND:
        has_direct_source = None
    elif has_direct_source is None and grounded_text:
        # `has_markers` False = the row carries no section markers at all (pre-W1 / thin), where
        # the honest answer is UNKNOWN — so None stands rather than a manufactured False.
        from agents.market_intelligence.judge_review import recompute_has_direct_source
        _hd, _hm = recompute_has_direct_source(grounded_text)
        has_direct_source = _hd if _hm else None
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
                                    active_narratives=active_narratives, tape=tape,
                                    has_direct_source=has_direct_source,
                                    theme_stage=theme_stage, theme_score=theme_score,
                                    revenue_stage=revenue_stage,
                                    second_opinion=second_opinion, setup_class=setup_class)
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
