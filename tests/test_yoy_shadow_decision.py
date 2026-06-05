"""Unit tests for #149 deterministic q_rev YoY shadow decision.

The shadow does NOT change the live gate — it records what the gate decision
WOULD be if the missing prior-year YoY were recovered from yfinance. The value
is gating BETTER IN BOTH DIRECTIONS: positive-YoY names get kept, but
below-threshold names correctly STAY DOWN on real data (not a missing-data
proxy). These cases mirror the 8 real affected names probed 2026-06-05.
"""
from agents.market_intelligence.ep_detector import _yoy_shadow_decision

GATE = 5.0  # EARNINGS_REVENUE_GATE_MIN_YOY (5% "company actually growing")


def test_positive_yoy_above_threshold_kept():
    # HSAI +29.6, SNOW +33.5, ESLT +15.5, JOYY +12.4, RL +16.6 → kept
    for yoy in (29.6, 33.5, 15.5, 12.4, 16.6):
        recovered, corrected = _yoy_shadow_decision(yoy, GATE)
        assert recovered is True
        assert corrected == "kept", f"{yoy} should be kept"


def test_below_threshold_stays_down_on_real_data():
    # BBWI -3.2, QFIN -26.6, LION -15.3 → recovered but below 5% → stay_down.
    # This is the "gate better in both directions" half: real data keeps them
    # correctly down rather than a missing-data proxy.
    for yoy in (-3.2, -26.6, -15.3):
        recovered, corrected = _yoy_shadow_decision(yoy, GATE)
        assert recovered is True
        assert corrected == "stay_down", f"{yoy} should stay down"


def test_exact_threshold_is_kept():
    recovered, corrected = _yoy_shadow_decision(5.0, GATE)
    assert recovered is True
    assert corrected == "kept"


def test_no_yoy_found_is_not_recovered_and_stays_down():
    for missing in (None, "n/a", {}):
        recovered, corrected = _yoy_shadow_decision(missing, GATE)
        assert recovered is False
        assert corrected == "stay_down"


def test_bool_is_not_treated_as_numeric_yoy():
    # isinstance(True, int) is True in Python — guard against a stray bool
    # leaking in as a "recovered" YoY. (Defensive: yfinance yoy_pct is float.)
    recovered, corrected = _yoy_shadow_decision(True, GATE)
    # True == 1, which is < 5 → stay_down regardless; assert it doesn't crash
    # and doesn't get "kept".
    assert corrected == "stay_down"
