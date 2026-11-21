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


# --- window must start at the order's own submission (CYRX 2026-11-17) ---
from datetime import datetime as _dt
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker.gap_through_telemetry import _order_window

_ETZ = ZoneInfo("America/New_York")


def _w(sub, canc=None):
    s = _dt(2026, 11, 17, *sub, tzinfo=_ETZ) if sub else None
    c = _dt(2026, 11, 17, *canc, tzinfo=_ETZ) if canc else None
    return _order_window(s, c)


def _cls(bars, win, trig, lim):
    start, end, _ = win
    inw = [(t, h, l) for t, h, l in bars if start <= t.time() <= end]
    return _classify_canonical(inw, trig, lim) if inw else "data_unavailable"


def _b(h, m, hi, lo):
    return (_dt(2026, 11, 17, h, m, tzinfo=_ETZ), hi, lo)


def test_cyrx_bar_before_submission_is_not_would_have_filled():
    bars = [_b(9, 44, 20.3949, 20.20), _b(9, 45, 20.29, 20.10), _b(9, 50, 20.25, 20.0)]
    win = _w((9, 45, 30), (10, 0, 5))
    assert win[2] == "post_submit"
    assert _cls(bars, win, 20.37, 20.37) == "clean_miss"
    # the old fixed 09:31-10:00 window reproduces the bug
    assert _classify_canonical(bars, 20.37, 20.37) == "would_have_filled"


def test_bar_after_submission_still_would_have_filled():
    bars = [_b(9, 44, 20.1, 20.0), _b(9, 46, 20.40, 20.30), _b(9, 47, 20.45, 20.30)]
    assert _cls(bars, _w((9, 45, 30), (10, 0, 5)), 20.37, 20.37) == "would_have_filled"


def test_no_submit_time_falls_back_to_orb_window():
    win = _w(None)
    assert win[2] == "orb_window_no_submit_time"
    bars = [_b(9, 44, 20.40, 20.30)]
    assert _cls(bars, win, 20.37, 20.37) == "would_have_filled"


def test_late_breakout_order_runs_submission_to_cancel():
    win = _w((13, 10, 20), (14, 30))
    assert (win[0].hour, win[0].minute, win[1].hour, win[1].minute) == (13, 10, 14, 30)
    bars = [_b(11, 0, 21, 20.9), _b(13, 20, 21, 20.3)]
    assert _cls(bars, win, 20.37, 20.37) == "would_have_filled"
    # uncancelled late order runs to the close, not 10:00
    assert _w((13, 10, 20))[1].hour == 16
