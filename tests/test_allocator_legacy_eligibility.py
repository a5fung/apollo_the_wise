"""#415 — legacy-eligibility flag correctness (allocator real-contest filter).

The `legacy_eligible` flag on `unified_allocation_decided` feeds the eventual
allocator-vs-FCFS routing decision (it filters "real contests" out of the
inflated raw contested-day count). A wrong value would poison that evidence, so
this freezes the criterion:

- MAGNA53 HIGH-tier (ep_score >= the regime EP threshold) -> 'eligible'
- MAGNA53 below the threshold                            -> 'ineligible'
- every non-MAGNA53 strategy                             -> 'unclassified'
  (the legacy entry gate isn't a simple field on those candidates; we mark it
  unknown rather than guess — a tri-state string so 'unknown' can never be
  silently read as 'ineligible').
"""
from datetime import date

from agents.market_intelligence.cross_strategy_allocator import (
    _legacy_eligibility,
    score_9m_day2,
    score_magna53,
)


def _magna(ep_score):
    return score_magna53(
        ticker="TEST", alert_date=date(2026, 7, 20), ep_score=ep_score,
        catalyst_quality="strong", pm_rvol=3.0, gap_pct=5.0, regime_label="Bull",
    )


def test_magna53_high_tier_is_eligible():
    assert _legacy_eligibility(_magna(75), ep_threshold=70) == "eligible"
    # boundary is inclusive — a score exactly at the threshold grades HIGH
    assert _legacy_eligibility(_magna(70), ep_threshold=70) == "eligible"


def test_magna53_below_threshold_is_ineligible():
    assert _legacy_eligibility(_magna(69), ep_threshold=70) == "ineligible"
    assert _legacy_eligibility(_magna(50), ep_threshold=70) == "ineligible"


def test_threshold_is_regime_relative():
    # Same score, stricter regime threshold flips the flag — the cutoff must
    # track the regime (ep_threshold ranges 65..80), not a hardcoded 70.
    c = _magna(72)
    assert _legacy_eligibility(c, ep_threshold=70) == "eligible"
    assert _legacy_eligibility(c, ep_threshold=75) == "ineligible"


def _sugar():
    return score_9m_day2(
        ticker="SUGR", alert_date=date(2026, 7, 20), close_in_range_pct=0.9,
        gap_proxy_pct=8.0, vol_ratio_adv=6.0, regime_label="Bull",
    )


def test_deprecated_strategy_is_ineligible():
    # 9m_day2 is deprecated as a standalone ENTRY (2026-07-05) — it can never be
    # a real legacy auto-entry, so it must be 'ineligible', not counted as a
    # contender. (The 9M stock CONDITION that feeds other setups is separate.)
    assert _legacy_eligibility(_sugar(), 70, deprecated_strategies={"9m_day2"}) == "ineligible"


def test_non_deprecated_non_magna_stays_unclassified():
    # A non-deprecated, non-MAGNA53 strategy (e.g. a shadow strategy under
    # evaluation) is genuinely unknown -> 'unclassified', never guessed.
    assert _legacy_eligibility(_sugar(), 70, deprecated_strategies=frozenset()) == "unclassified"
