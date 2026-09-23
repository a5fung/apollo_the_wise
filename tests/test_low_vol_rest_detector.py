"""Unit tests for the #97 low-volume-rest pure signal (evaluate_low_vol_rest).

A rest = quiet (light volume) + tight (small intraday range) + holding INSIDE the
base (not broken out/down). Entry-technique #4.
"""
from __future__ import annotations

from agents.market_intelligence.flag_detector import (
    evaluate_low_vol_rest,
    _LOW_VOL_REST_VOL_CEIL_PCT,
    _LOW_VOL_REST_RANGE_CEIL_PCT,
)

# A clean resting setup: base 10–11, price 10.6 (mid-base), tight 1.4% range,
# light volume (40% ADV).
_BASE = dict(base_low=10.0, base_high=11.0, prev_close=10.5, adv_20=1_000_000)


def _rest(**over):
    args = dict(_BASE, day_high=10.7, day_low=10.55, current_price=10.6,
                projected_full_day=400_000)
    args.update(over)
    return evaluate_low_vol_rest(**args)


def test_clean_rest_fires():
    m = _rest()
    assert m is not None
    assert m["vol_pct_of_adv"] == 40.0
    assert 0 < m["range_pct"] <= _LOW_VOL_REST_RANGE_CEIL_PCT
    assert 40 < m["pos_in_base_pct"] < 80  # ~60% up in the base


def test_heavy_volume_rejected():
    # projected > 60% ADV — not "dried up", so not a rest.
    assert _rest(projected_full_day=900_000) is None


def test_wide_range_rejected():
    # 6% intraday range — too active to be a quiet rest.
    assert _rest(day_high=11.0, day_low=10.37) is None


def test_broken_out_rejected():
    # Price above base_high = a break-out (flag-break's job), not a rest.
    assert _rest(current_price=11.2, day_high=11.3) is None


def test_breaking_down_rejected():
    # Price at/below base_low = breaking down, not holding.
    assert _rest(current_price=9.98, day_low=9.9) is None


def test_holding_just_above_base_low_fires():
    # Resting low in the base but holding above base_low with margin.
    m = _rest(current_price=10.08, day_low=10.04, day_high=10.18)
    assert m is not None
    assert m["pos_in_base_pct"] < 20  # near the bottom of the base


def test_bad_inputs_return_none():
    assert evaluate_low_vol_rest(
        base_low=0, base_high=11, day_high=10.7, day_low=10.5,
        current_price=10.6, prev_close=10.5, projected_full_day=400_000, adv_20=1_000_000,
    ) is None
    assert evaluate_low_vol_rest(
        base_low=10, base_high=11, day_high=10.7, day_low=10.5,
        current_price=10.6, prev_close=10.5, projected_full_day=400_000, adv_20=0,
    ) is None
