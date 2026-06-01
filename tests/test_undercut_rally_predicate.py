"""Unit tests for the U&R (Undercut & Rally) pure predicate (#98, Morales/OWL).

Two load-bearing subtleties the matrix pins (advisor 2026-05-31):
  - undercut-depth LOWER bound keeps U&R from overlapping the support-test
    detector's <=2% touch band — the DEPTH is what distinguishes the two setups;
  - undercut-depth UPPER cap keeps a breakdown from being mislabeled a U&R.
"""
from agents.market_intelligence.flag_detector import is_undercut_rally


def test_shallow_undercut_then_reclaim_is_ur():
    # base_low=10, undercut to 9.5 (5% below — inside (2, 8]), reclaimed to 10.1
    assert is_undercut_rally(10.0, 9.5, 10.1) is True


def test_reclaim_exactly_at_base_low_is_ur():
    # default reclaim floor 0% → current == base_low qualifies as reclaimed
    assert is_undercut_rally(10.0, 9.5, 10.0) is True


def test_deep_undercut_is_breakdown_not_ur():
    # 10% undercut (> 8% cap) = breakdown, not a shakeout
    assert is_undercut_rally(10.0, 9.0, 10.1) is False


def test_no_reclaim_still_below_base_is_not_ur():
    # undercut 5% but price still under base_low → not reclaimed
    assert is_undercut_rally(10.0, 9.5, 9.8) is False


def test_shallow_touch_is_support_test_not_ur():
    # 1% undercut (<= 2% min) is the support-test detector's band, not U&R
    assert is_undercut_rally(10.0, 9.9, 10.1) is False


def test_just_above_2pct_is_ur_lower_edge():
    # 2.5% undercut — just into the U&R band (above support-test's <=2%)
    assert is_undercut_rally(10.0, 9.75, 10.05) is True


def test_below_2pct_is_support_test_band():
    # 1.5% undercut — support-test territory, not U&R
    assert is_undercut_rally(10.0, 9.85, 10.05) is False


def test_no_undercut_at_all_is_not_ur():
    # low never went below base_low → undercut_pct negative
    assert is_undercut_rally(10.0, 10.2, 10.5) is False


def test_just_inside_8pct_cap_is_ur():
    # 7.5% undercut — clearly inside the (2, 8] band (avoid float-razor at exactly 8%)
    assert is_undercut_rally(10.0, 9.25, 10.05) is True


def test_just_over_8pct_cap_is_breakdown():
    # 8.5% undercut — over the cap, a breakdown not a shakeout
    assert is_undercut_rally(10.0, 9.15, 10.05) is False


def test_zero_or_negative_inputs_are_safe():
    assert is_undercut_rally(0.0, 9.5, 10.1) is False
    assert is_undercut_rally(10.0, 0.0, 10.1) is False
    assert is_undercut_rally(10.0, 9.5, 0.0) is False


def test_custom_thresholds_respected():
    # widen max cap to admit a 10% undercut
    assert is_undercut_rally(10.0, 9.0, 10.1, max_undercut_pct=12.0) is True
    # require a +1% reclaim buffer → 10.05 fails, 10.2 passes
    assert is_undercut_rally(10.0, 9.5, 10.05, reclaim_floor_pct=1.0) is False
    assert is_undercut_rally(10.0, 9.5, 10.2, reclaim_floor_pct=1.0) is True
