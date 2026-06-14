"""CLASS B breadth color rule (#271) — unit tests for the pure level→color function."""
from agents.market_intelligence.breadth_color_rules import (
    class_b_color, CAUTION, BULL, NEUTRAL,
    CLASS_B_UP_EXHAUSTION, CLASS_B_DOWN_WASHOUT,
)


def test_up_thrust_extreme_is_amber():
    assert class_b_color(CLASS_B_UP_EXHAUSTION + 0.5, 0.5) == CAUTION
    assert class_b_color(CLASS_B_UP_EXHAUSTION, 0.0) == CAUTION  # boundary inclusive


def test_washout_extreme_is_green():
    assert class_b_color(1.0, CLASS_B_DOWN_WASHOUT + 0.3) == BULL
    assert class_b_color(0.0, CLASS_B_DOWN_WASHOUT) == BULL  # boundary inclusive


def test_mid_range_is_neutral():
    assert class_b_color(1.0, 0.5) == NEUTRAL
    assert class_b_color(None, None) == NEUTRAL
    assert class_b_color(CLASS_B_UP_EXHAUSTION - 0.1, CLASS_B_DOWN_WASHOUT - 0.1) == NEUTRAL


def test_up_side_wins_when_both_extreme():
    assert class_b_color(CLASS_B_UP_EXHAUSTION + 1, CLASS_B_DOWN_WASHOUT + 1) == CAUTION


def test_none_on_one_side_uses_other():
    assert class_b_color(None, CLASS_B_DOWN_WASHOUT + 0.5) == BULL
    assert class_b_color(CLASS_B_UP_EXHAUSTION + 0.5, None) == CAUTION
