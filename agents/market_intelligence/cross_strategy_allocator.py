"""Cross-strategy unified allocator (#31, Phase 1A — shadow).

Replaces the implicit cron-order FCFS slot grab (5/7 incident: 9M Day 2 took
all available slots before MAGNA53 ORB monitor at 9:31). Strategies emit
candidates to mi_pending_allocations during their scan; this module scores
them on a shared 0-100 composite and (eventually) selects top-N by composite.

**Phase 1A scope (shadow): score + emit audit telemetry only.** Legacy
submission paths run unchanged. The shadow row records `shadow_rank` +
`shadow_allocated`; an `unified_allocation_decided` audit event captures the
full ranking. Compare actual fills vs allocator picks over N days before
flipping Phase 1B (active submission).

**Scoring (per memo 2026-05-08, Z-norm DROPPED post-spike)**:
- setup_quality (40%): MAGNA53 = ep_score; 9M Day 2 = blend(close_in_range,
  gap%); future strategies bring their own setup→0-100 mapping.
- catalyst (30%): MAGNA53 catalyst_quality grade; 9M Day 2 = 100 (virgin 9M
  is intrinsic catalyst).
- volume (20%): pm_rvol (MAGNA53) or vol_ratio_adv (9M Day 2), capped to a
  strategy-specific saturation point, normalized to 0-100.
- regime (10%): Bull=100, Crisis=60. Currently constant per scan; future
  per-strategy fit possible.

Composite = weighted sum, no normalization. The 0-100 cap is the
normalization. ep_score cap saturation (#42) is the ranking-signal weakness
that Phase 2 (track-record dim) addresses; not encoded as Z-norm here.

Tie-breaker hierarchy (per memo Q2): pm_rvol → gap_pct → strategy priority
(MAGNA53 > 9M > Flag).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Phase 1 weights — see module docstring for rationale
W_SETUP = 0.40
W_CATALYST = 0.30
W_VOLUME = 0.20
W_REGIME = 0.10

CATALYST_GRADE = {
    "game_changer": 100.0,
    "strong": 70.0,
    "routine": 30.0,
    "mna": 0.0,
}

# Strategy priority for tie-breaking (lower index = higher priority)
STRATEGY_PRIORITY = {
    "magna53": 0,
    "9m_day2": 1,
    "flag_continuation": 2,
}


@dataclass
class RankableCandidate:
    """One strategy's candidate, scored for cross-strategy allocation."""
    ticker: str
    alert_date: date
    strategy: str
    setup_quality: float        # 0-100
    catalyst: float             # 0-100
    volume: float               # 0-100
    regime: float               # 0-100
    composite: float            # weighted sum
    # Tie-breakers — duplicated from raw_dimensions for cheap sort access
    pm_rvol: Optional[float] = None
    gap_pct: Optional[float] = None
    # Pass-through context (free-form per strategy)
    raw_dimensions: dict[str, Any] = field(default_factory=dict)
    # Set after persistence; carries the queue row id for status updates
    db_id: Optional[int] = None


def score_magna53(
    *,
    ticker: str,
    alert_date: date,
    ep_score: float,
    catalyst_quality: Optional[str],
    pm_rvol: Optional[float],
    gap_pct: Optional[float],
    regime_label: str = "Bull",
) -> RankableCandidate:
    """Map a MAGNA53 EP HIGH/MODERATE alert to a RankableCandidate."""
    setup = float(ep_score or 0)
    catalyst = CATALYST_GRADE.get(catalyst_quality or "routine", 30.0)
    pm_rv = float(pm_rvol or 0)
    volume = min(50.0, pm_rv) / 50.0 * 100.0
    regime = 60.0 if regime_label == "Crisis" else 100.0
    composite = (
        W_SETUP * setup + W_CATALYST * catalyst
        + W_VOLUME * volume + W_REGIME * regime
    )
    return RankableCandidate(
        ticker=ticker, alert_date=alert_date, strategy="magna53",
        setup_quality=setup, catalyst=catalyst, volume=volume,
        regime=regime, composite=composite,
        pm_rvol=pm_rv, gap_pct=float(gap_pct) if gap_pct is not None else None,
        raw_dimensions={
            "ep_score": setup,
            "catalyst_quality": catalyst_quality,
            "pm_rvol": pm_rv,
            "gap_pct": gap_pct,
            "regime": regime_label,
        },
    )


def score_9m_day2(
    *,
    ticker: str,
    alert_date: date,
    close_in_range_pct: float,
    gap_proxy_pct: float,
    vol_ratio_adv: Optional[float],
    regime_label: str = "Bull",
) -> RankableCandidate:
    """Map a 9M Day 2 sugar baby to a RankableCandidate.

    Setup quality blends close-in-range (top-quartile breakouts vs mid-range
    weakness) with gap magnitude. Catalyst is intrinsic (virgin 9M day per
    Pradeep Bonde methodology — no need for news classification).
    """
    close_pct = float(close_in_range_pct or 0) * 100.0  # 0-1 → 0-100
    gap = float(gap_proxy_pct or 0)
    gap_score = min(30.0, max(0.0, gap)) / 30.0 * 100.0
    setup = 0.5 * close_pct + 0.5 * gap_score
    catalyst = 100.0
    vr = float(vol_ratio_adv) if vol_ratio_adv is not None else 5.0
    volume = min(10.0, vr) / 10.0 * 100.0
    regime = 60.0 if regime_label == "Crisis" else 100.0
    composite = (
        W_SETUP * setup + W_CATALYST * catalyst
        + W_VOLUME * volume + W_REGIME * regime
    )
    return RankableCandidate(
        ticker=ticker, alert_date=alert_date, strategy="9m_day2",
        setup_quality=setup, catalyst=catalyst, volume=volume,
        regime=regime, composite=composite,
        pm_rvol=None, gap_pct=gap,
        raw_dimensions={
            "close_in_range_pct": close_in_range_pct,
            "gap_proxy_pct": gap_proxy_pct,
            "vol_ratio_adv": vr,
            "regime": regime_label,
        },
    )


def _tie_break_key(c: RankableCandidate) -> tuple:
    """Composite desc → pm_rvol desc → gap_pct desc → strategy priority asc.
    Returns a tuple suitable as `sort(key=...)` (negate descs)."""
    return (
        -c.composite,
        -(c.pm_rvol or 0.0),
        -(c.gap_pct or 0.0),
        STRATEGY_PRIORITY.get(c.strategy, 99),
    )


def rank_candidates(candidates: list[RankableCandidate]) -> list[RankableCandidate]:
    """Sorted in allocation order: best first, ties broken per Q2 hierarchy."""
    return sorted(candidates, key=_tie_break_key)


def select_top_n(
    candidates: list[RankableCandidate], n: int,
) -> tuple[list[RankableCandidate], list[RankableCandidate]]:
    """(winners, losers) — winners are the first n in rank order."""
    if n <= 0:
        return [], list(candidates)
    ranked = rank_candidates(candidates)
    return ranked[:n], ranked[n:]


def _legacy_eligibility(c: RankableCandidate, ep_threshold: float) -> str:
    """#415 real-contest filter — was this candidate ever LEGACY-auto-entry-
    eligible, independent of the allocator's own rank?

    Lets future allocator-vs-FCFS analysis count only GENUINE contests instead
    of MODERATE-tier / excess-quality candidates that never had a chance under
    either path (the "inflated contested-day count" caveat in
    allocator_1b_comparison_2026-07-03.md §8).

    - MAGNA53 legacy auto-entry = HIGH tier = ep_score >= the regime EP
      threshold (the same threshold ep_detector grades HIGH against).
    - 9m_day2 / flag_continuation: the legacy entry gate is NOT a simple field
      on the candidate here, so we return 'unclassified' rather than GUESS a
      rule — a wrong flag would poison the very real-contest filter this feeds
      (audit-only telemetry, but it informs a real routing decision). Returns a
      tri-state string, never a bare bool, so 'unknown' can never be silently
      read as 'ineligible'.
    """
    if c.strategy == "magna53":
        ep_score = c.raw_dimensions.get("ep_score", c.setup_quality) or 0.0
        return "eligible" if ep_score >= ep_threshold else "ineligible"
    return "unclassified"


def candidates_from_pending_rows(
    rows: list[dict],
    regime_label: str = "Bull",
) -> list[RankableCandidate]:
    """Reconstruct RankableCandidate objects from mi_pending_allocations rows.

    Each row carries strategy + composite_score + raw_dimensions. We re-score
    in-process so a regime change between enqueue and allocator-run reflects
    in the allocator's decision (regime is a relatively cheap re-score; setup
    + volume are sticky).
    """
    out: list[RankableCandidate] = []
    for r in rows:
        raw = r.get("raw_dimensions") or {}
        if isinstance(raw, str):
            import json as _json
            raw = _json.loads(raw)
        strat = r["strategy"]
        try:
            if strat == "magna53":
                c = score_magna53(
                    ticker=r["ticker"],
                    alert_date=r["alert_date"],
                    ep_score=raw.get("ep_score") or 0,
                    catalyst_quality=raw.get("catalyst_quality"),
                    pm_rvol=raw.get("pm_rvol"),
                    gap_pct=raw.get("gap_pct"),
                    regime_label=regime_label,
                )
            elif strat == "9m_day2":
                c = score_9m_day2(
                    ticker=r["ticker"],
                    alert_date=r["alert_date"],
                    close_in_range_pct=raw.get("close_in_range_pct") or 0,
                    gap_proxy_pct=raw.get("gap_proxy_pct") or 0,
                    vol_ratio_adv=raw.get("vol_ratio_adv"),
                    regime_label=regime_label,
                )
            else:
                logger.warning(f"allocator: unknown strategy '{strat}' for {r['ticker']} — skipped")
                continue
            c.db_id = r["id"]
            out.append(c)
        except Exception as e:
            logger.error(
                f"allocator: scoring failed for {r['ticker']} ({strat}): {e}",
                exc_info=True,
            )
    return out


async def run_shadow_allocation(target_date: date) -> dict:
    """Phase 1A entry point — drains queue, scores, marks shadow ranks,
    emits audit event. Does NOT submit orders.

    Returns summary dict: {n_candidates, n_winners, top_picks, lower_ranked}.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.regime import get_current_regime
    from agents.market_intelligence.constants import MAX_CONCURRENT_LIVE_POSITIONS

    rows = await db.get_pending_allocations_for_date(target_date)
    if not rows:
        await db.log_audit_event(
            "unified_allocation_decided",
            f"empty queue for {target_date}",
            detail='{"target_date":"' + target_date.isoformat() + '","n_candidates":0}',
        )
        return {"n_candidates": 0, "n_winners": 0, "top_picks": [], "lower_ranked": []}

    regime = await get_current_regime()
    ep_threshold = regime.get("ep_threshold", 70)  # #415: MAGNA53 HIGH-tier cutoff for legacy_eligible
    candidates = candidates_from_pending_rows(rows, regime_label=regime.get("regime", "Bull"))
    ranked = rank_candidates(candidates)

    # Slots: MAX - currently_open. Live trades only — paper has no slot pressure.
    open_count = await db.get_open_position_count()
    slots = max(0, MAX_CONCURRENT_LIVE_POSITIONS - (open_count or 0))
    winners = ranked[:slots]
    losers = ranked[slots:]

    # Stamp shadow_rank + shadow_allocated on the queue rows.
    rank_ordered_ids = [c.db_id for c in ranked if c.db_id is not None]
    selected_ids = [c.db_id for c in winners if c.db_id is not None]
    await db.mark_pending_allocations_evaluated(rank_ordered_ids, selected_ids)

    # Audit event payload — full ranking + winners
    import json as _json
    detail = _json.dumps({
        "target_date": target_date.isoformat(),
        "regime": regime.get("regime", "Bull"),
        "open_positions": open_count,
        "slots_available": slots,
        "n_candidates": len(candidates),
        "n_winners": len(winners),
        "winners": [
            {"rank": i + 1, "ticker": c.ticker, "strategy": c.strategy,
             "composite": round(c.composite, 2), "setup": round(c.setup_quality, 2),
             "legacy_eligible": _legacy_eligibility(c, ep_threshold)}
            for i, c in enumerate(winners)
        ],
        "lower_ranked": [
            {"rank": slots + i + 1, "ticker": c.ticker, "strategy": c.strategy,
             "composite": round(c.composite, 2),
             "legacy_eligible": _legacy_eligibility(c, ep_threshold)}
            for i, c in enumerate(losers[:10])  # cap detail size
        ],
        # #415: the next-ranked candidate that would cascade into a slot if a
        # winner is intercepted downstream (DATA only — logging who is next, NOT
        # implementing cascade *behavior*, which is an open operator design fork).
        "first_cascade_candidate": (
            {"rank": slots + 1, "ticker": losers[0].ticker,
             "strategy": losers[0].strategy,
             "composite": round(losers[0].composite, 2),
             "legacy_eligible": _legacy_eligibility(losers[0], ep_threshold)}
            if losers else None
        ),
    })[:4500]  # mi_audit_log.detail is TEXT but trim to keep events grep-friendly

    summary = (
        f"slots={slots} winners={[c.ticker for c in winners]} "
        f"n={len(candidates)} ({len(losers)} lower-ranked)"
    )
    await db.log_audit_event("unified_allocation_decided", summary, detail=detail)

    return {
        "n_candidates": len(candidates),
        "n_winners": len(winners),
        "slots": slots,
        "open_positions": open_count,
        "top_picks": [c.ticker for c in winners],
        "lower_ranked": [c.ticker for c in losers],
    }
