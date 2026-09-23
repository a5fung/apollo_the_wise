"""Volume conviction is a real reading again, not a constant (operator-directed 2026-09-04).

Before this, every candidate scored after 09:30 was handed a hardcoded neutral 50, which
awards 0 points — so CHPT on 2026-09-03, trading eleven times its all-time-high volume,
scored identically to a dead stock. The operator flagged that on day one.

BUG FIX, not a criteria change: no weight, tier or bar moved. These tests pin the three
behaviours that matter — an extreme session now scores, an ordinary one still does not,
and a ticker with no history still falls back to neutral rather than to zero-conviction.
"""
from agents.market_intelligence.ep_detector import _volume_percentile
from agents.market_intelligence.ep_rubric import SCORE_WEIGHTS


def _points(pct):
    """Points the live tier table awards for a given percentile."""
    for cut, pts in SCORE_WEIGHTS["vol_conviction"]["tiers"]:
        if pct >= cut:
            return pts
    return SCORE_WEIGHTS["vol_conviction"]["default"]


def test_record_volume_now_scores_where_the_constant_scored_nothing():
    """CHPT's shape: today's volume above every day in its own history."""
    history = [100_000.0] * 200
    pct = _volume_percentile(969_501.0, history)
    assert pct == 100.0
    assert _points(pct) > 0, "a record-volume session must earn points"
    assert _points(50.0) == 0, "the old hardcoded neutral awarded nothing — that was the bug"


def test_an_ordinary_part_day_session_still_earns_nothing():
    """The reason the hardcode existed: a part-day cumulative is small against full-day
    history. That must still land below both tier cuts, or the fix would admit noise."""
    history = [1_000_000.0] * 200
    pct = _volume_percentile(120_000.0, history)
    assert pct == 0.0
    assert _points(pct) == 0


def test_no_history_falls_back_to_neutral_never_to_zero_conviction():
    """A ticker we have no history for must read neutral, not 'no conviction' — the
    fail-open direction. `_volume_percentile` returns 50 on an empty history, and the
    live branch only uses the honest reading when a history actually exists."""
    assert _volume_percentile(5_000_000.0, []) == 50.0
    assert _points(50.0) == 0


def test_the_tier_table_itself_is_unchanged_by_this_fix():
    """Guards the bug-fix claim: this change moved an INPUT, never a weight."""
    assert SCORE_WEIGHTS["vol_conviction"]["tiers"] == [(90, 5), (70, 3)]
    assert SCORE_WEIGHTS["vol_conviction"]["default"] == 0
