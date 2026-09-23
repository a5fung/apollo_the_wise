"""Unit tests for the EOD ORB-cancellation reclassifier core (#183).

_classify_canonical must be ORDER-INDEPENDENT: get_minute_bars is not guaranteed
chronological, and "first trigger-hit" + "bars at/after it" are order-dependent.
A caller passing unsorted bars (AVAV 5/28) misclassified would_have_filled as
gap_through until the sort was moved into the function.
"""
from datetime import datetime as dt

from agents.market_intelligence.broker.gap_through_telemetry import _classify_canonical


def _t(h, m):
    return dt(2026, 5, 28, h, m)


def test_classify_is_order_independent():
    # Earliest trigger-hit is 09:48 (then a low of 99 <= limit 100 = a fill).
    # A LATER 09:55 hit has low 101 (no fill). Sorted, this is would_have_filled;
    # unsorted, a naive impl picks 09:55 as "first" and returns gap_through.
    unsorted = [(_t(9, 55), 102, 101), (_t(9, 48), 100, 99),
                (_t(9, 40), 98, 97), (_t(9, 50), 103, 100)]
    assert _classify_canonical(unsorted, 100, 100) == "would_have_filled"
    assert _classify_canonical(sorted(unsorted), 100, 100) == "would_have_filled"


def test_clean_miss_when_trigger_never_hit():
    bars = [(_t(9, 40), 98, 97), (_t(9, 50), 99, 98)]
    assert _classify_canonical(bars, 100, 100) == "clean_miss"


def test_gap_through_when_price_runs_past_limit():
    # Trigger 100 hit at 09:40, but every low after stays above the limit (100).
    bars = [(_t(9, 40), 101, 100.5), (_t(9, 45), 105, 102), (_t(9, 50), 108, 104)]
    assert _classify_canonical(bars, 100, 100) == "gap_through"


def test_would_have_filled_low_touches_limit():
    bars = [(_t(9, 40), 101, 100.5), (_t(9, 45), 102, 99.9)]
    assert _classify_canonical(bars, 100, 100) == "would_have_filled"
