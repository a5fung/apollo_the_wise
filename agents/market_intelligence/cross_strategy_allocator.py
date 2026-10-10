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

**#312 Step A (2026-10-10, operator-signed 2026-09-14 "aligned, A, then B if
this becomes necessary"): the ranking is computed at 09:28 ET against the
PRE-ENTRY book.** It used to run at 09:35, four minutes after the 09:31 ORB
submits, reading the live open count — so 6 of the 7 winners that ever filled
were counted twice (once as an open position consuming a slot, once as the
winner of a slot that remained; `docs/analysis/unified_allocator_phase_1b_2026-09-14.md`
§2). Slots are now `cap − live positions with alert_date < target_date`
(`db.get_open_position_count(account_mode="live", before_alert_date=...)`), and
the audit row carries `ranked_at_et` + `ranked_ids` so a name that arrives after
the ranking is identifiable from the two tables alone (the Step B bar).
SSoT: `docs/architecture/cross_strategy_allocator.md`.

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
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Phase 1 weights — see module docstring for rationale
W_SETUP = 0.40
W_CATALYST = 0.30
W_VOLUME = 0.20
W_REGIME = 0.10

CATALYST_GRADE = {
    "game_changer": 100.0,
    "strong": 70.0,
    "routine": 30.0,
    # A price-fixing buyout (signed target paid in cash / mixed / unknown, or a signed shell) is
    # blocked by the M&A filter; a name the filter RELEASES on price (#692b, 2026-10-03) carries
    # the grader's `quality_if_no_deal` instead of 'mna', so 0.0 here never weights a released name.
    "mna": 0.0,
}

# Strategy priority for tie-breaking (lower index = higher priority)
STRATEGY_PRIORITY = {
    "magna53": 0,
    # 9m_day2 removed 2026-08-02 (#515) with its scorer -- no candidate can carry that strategy.
    "flag_continuation": 1,
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


# score_9m_day2 REMOVED 2026-08-02 (#515). The Day-2 ENTRY strategy is retired, and with the
# `_9m_day2_orb_job` gone the ONLY writer of `mi_pending_allocations` is `enqueue_pending_allocation`
# at ep_detector.py, which enqueues `strategy="magna53"` and nothing else -- so no row this scorer
# could rank can ever be created again. Verified against prod before removing: the 80 residual
# `9m_day2` rows are all `alert_date <= 2026-07-14`, and `get_pending_allocations_for_date` reads
# SAME-DAY rows only, so they are unreachable too. A straggler would fall to the `else:` arm below,
# which logs "unknown strategy" and skips -- the correct handling for a retired strategy anyway.
# (The 9M stock CHARACTER that feeds other setups is a separate live signal and is untouched.)


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


def _legacy_eligibility(
    c: RankableCandidate,
    ep_threshold: float,
    deprecated_strategies: "frozenset[str] | set[str]" = frozenset(),
) -> str:
    """#415 real-contest filter — was this candidate ever LEGACY-auto-entry-
    eligible, independent of the allocator's own rank?

    Lets future allocator-vs-FCFS analysis count only GENUINE contests instead
    of MODERATE-tier / excess-quality candidates that never had a chance under
    either path (the "inflated contested-day count" caveat in
    allocator_1b_comparison_2026-07-03.md §8).

    - A DEPRECATED strategy (e.g. 9m_day2, deprecated as a standalone ENTRY on
      2026-07-05) can never be a real legacy auto-entry -> 'ineligible'. (Its
      candidates are also blocked upstream at enqueue; this is the correct label
      for any straggler. The 9M stock CONDITION that feeds other setups is a
      separate live signal — see 357_sugar_babies_role_memo.)
    - MAGNA53 legacy auto-entry = HIGH tier = ep_score >= the regime EP
      threshold (the same threshold ep_detector grades HIGH against).
    - Any other non-deprecated strategy (e.g. a shadow strategy under
      evaluation): 'unclassified' rather than GUESS a rule — a wrong flag would
      poison the very real-contest filter this feeds. Tri-state string, never a
      bare bool, so 'unknown' can never be silently read as 'ineligible'.
    """
    if c.strategy in deprecated_strategies:
        return "ineligible"
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

    #312 Step A: slots are read from the PRE-ENTRY LIVE book — positions whose
    `alert_date` precedes `target_date` — never from a live count that already
    holds the morning's 09:31 fills (the double count the 09:35 timing produced).
    The audit row records when the ranking was taken (`ranked_at_et`) and which
    queue rows it saw (`ranked_ids`), so the Step B question — do names arriving
    AFTER the ranking outrank its winners? — is answerable by joining
    `mi_pending_allocations` rows for the day that are NOT in `ranked_ids`
    against the frozen winner composites in the same row.

    Returns summary dict: {n_candidates, n_winners, top_picks, lower_ranked}.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.regime import get_current_regime
    from agents.market_intelligence.constants import MAX_CONCURRENT_LIVE_POSITIONS

    ranked_at = datetime.now(_ET)
    rows = await db.get_pending_allocations_for_date(target_date)
    if not rows:
        await db.log_audit_event(
            "unified_allocation_decided",
            f"empty queue for {target_date}",
            # Same keys as the full row (ranked_ids = []) so the Step B join
            # `id NOT IN ranked_ids` never meets a NULL on a quiet morning.
            detail='{"target_date":"' + target_date.isoformat() + '","n_candidates":0'
                   + ',"ranked_at_et":"' + ranked_at.isoformat() + '","ranked_ids":[]}',
        )
        return {"n_candidates": 0, "n_winners": 0, "top_picks": [], "lower_ranked": []}

    regime = await get_current_regime()
    ep_threshold = regime.get("ep_threshold", 70)  # #415: MAGNA53 HIGH-tier cutoff for legacy_eligible
    deprecated_strategies = await db.get_deprecated_strategy_signal_types()  # #415: their candidates = legacy-ineligible
    candidates = candidates_from_pending_rows(rows, regime_label=regime.get("regime", "Bull"))
    ranked = rank_candidates(candidates)

    # Slots: MAX - positions open BEFORE today's entries, on the LIVE book only (paper
    # has no slot pressure; the lowcap lane's paper rows share this table, #624). A
    # row with alert_date == target_date is one of today's entries — it is being
    # RANKED here, so it must not also be COUNTED as occupying a slot (#312 Step A).
    open_count = await db.get_open_position_count(
        account_mode="live", before_alert_date=target_date,
    )
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
        # #312 Step A: the book is `alert_date < target_date`, live only — the
        # pre-entry book, not whatever is open at the tick.
        "open_positions": open_count,
        "slots_available": slots,
        "ranked_at_et": ranked_at.isoformat(),
        "ranked_ids": rank_ordered_ids,  # the queue rows this ranking SAW (Step B: late arrivals = day's rows not in here)
        "n_candidates": len(candidates),
        "n_winners": len(winners),
        "winners": [
            {"rank": i + 1, "ticker": c.ticker, "strategy": c.strategy,
             "composite": round(c.composite, 2), "setup": round(c.setup_quality, 2),
             "legacy_eligible": _legacy_eligibility(c, ep_threshold, deprecated_strategies)}
            for i, c in enumerate(winners)
        ],
        "lower_ranked": [
            {"rank": slots + i + 1, "ticker": c.ticker, "strategy": c.strategy,
             "composite": round(c.composite, 2),
             "legacy_eligible": _legacy_eligibility(c, ep_threshold, deprecated_strategies)}
            for i, c in enumerate(losers[:10])  # cap detail size
        ],
        # #415: the next-ranked candidate that would cascade into a slot if a
        # winner is intercepted downstream (DATA only — logging who is next, NOT
        # implementing cascade *behavior*, which is an open operator design fork).
        "first_cascade_candidate": (
            {"rank": slots + 1, "ticker": losers[0].ticker,
             "strategy": losers[0].strategy,
             "composite": round(losers[0].composite, 2),
             "legacy_eligible": _legacy_eligibility(losers[0], ep_threshold, deprecated_strategies)}
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
