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
    RankableCandidate,
    _legacy_eligibility,
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


def _other(strategy="flag_continuation"):
    """A non-MAGNA53 candidate, built DIRECTLY rather than through a strategy scorer.

    It used to be built by `score_9m_day2`, which was deleted with the Day-2 entry (#515,
    2026-08-02). Constructing the candidate here is the more honest fixture anyway: these two
    tests are about the DEPRECATION GATE, which is generic over strategy names — binding them to
    one strategy's scorer made a retired strategy load-bearing for unrelated coverage."""
    return RankableCandidate(
        ticker="SUGR", alert_date=date(2026, 7, 20), strategy=strategy,
        setup_quality=80.0, catalyst=100.0, volume=60.0, regime=100.0, composite=85.0,
    )


def test_deprecated_strategy_is_ineligible():
    # A deprecated strategy can never be a real legacy auto-entry, so it must be 'ineligible',
    # not counted as a contender. (9m_day2 was the original case — deprecated as a standalone
    # ENTRY 2026-07-05, deleted outright 2026-08-02; the gate itself is unchanged and generic.)
    assert _legacy_eligibility(_other(), 70,
                               deprecated_strategies={"flag_continuation"}) == "ineligible"


def test_non_deprecated_non_magna_stays_unclassified():
    # A non-deprecated, non-MAGNA53 strategy (e.g. a shadow strategy under
    # evaluation) is genuinely unknown -> 'unclassified', never guessed.
    assert _legacy_eligibility(_other(), 70, deprecated_strategies=frozenset()) == "unclassified"
