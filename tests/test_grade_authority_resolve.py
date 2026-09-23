"""W2c (#243 / ADR 0011): the load-bearing grade-authority decision — toggle OFF is
byte-identical to shadow (no override), toggle ON lets the judge tier drive (promote /
demote / 'none'-suppress), and a None verdict FAILS OPEN to the floor. Locked here
independent of the scan loop.
"""
from agents.market_intelligence.ep_detector import _resolve_grade_authority


def test_toggle_off_never_overrides():
    # Even with a strong judge verdict, OFF keeps the floor + no DB override.
    assert _resolve_grade_authority(False, {"tier": "HIGH"}, "MODERATE") == ("MODERATE", "floor", False)
    assert _resolve_grade_authority(False, None, "HIGH") == ("HIGH", "floor", False)


def test_toggle_on_promote_moderate_to_high():
    # The fat-tail capture: floor MODERATE, judge promotes → HIGH drives entry.
    assert _resolve_grade_authority(True, {"tier": "HIGH"}, "MODERATE") == ("HIGH", "judge", True)


def test_toggle_on_demote_high_to_none_suppresses():
    # Judge 'none' on a floor HIGH → score_tier 'none' (downstream = no alert/entry).
    assert _resolve_grade_authority(True, {"tier": "none"}, "HIGH") == ("none", "judge", True)


def test_toggle_on_demote_high_to_moderate():
    assert _resolve_grade_authority(True, {"tier": "MODERATE"}, "HIGH") == ("MODERATE", "judge", True)


def test_toggle_on_null_verdict_fails_open_to_floor():
    # Judge timeout/malformed → keep the floor tier, authority 'fallback' (counted).
    assert _resolve_grade_authority(True, None, "HIGH") == ("HIGH", "fallback", True)
