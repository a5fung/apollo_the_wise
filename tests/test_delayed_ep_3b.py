"""#270 Step 3 Phase 6a — 3b intraday FIRST5/GDL detection + the faithful mixed-path harvest.

Pins the ported entry detection (entry = the fixed first-5-min-OR high; stop = OR low),
the Polygon→RTH-minute adapter, and that realized_r harvests over a REAL minute+daily path
(never a daily approximation of the day-0 scale-out — the error this arc closed).
"""
from datetime import datetime, timezone

import agents.market_intelligence.delayed_ep as de


def _utc_ms(h, mi):
    return int(datetime(2026, 6, 16, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def test_polygon_to_rth_minutes_filters_premarket():
    raw = [
        {"t": _utc_ms(12, 0),  "o": 1, "h": 1, "l": 1, "c": 1, "v": 1},        # 8:00 ET pre-market
        {"t": _utc_ms(13, 30), "o": 10, "h": 10, "l": 9.5, "c": 9.8, "v": 1},  # 9:30 ET
        {"t": _utc_ms(13, 35), "o": 9.8, "h": 10.5, "l": 9.8, "c": 10.4, "v": 1},  # 9:35 ET
    ]
    bars = de.polygon_to_rth_minutes(raw, "2026-06-16")
    assert [b["m"] for b in bars] == [570, 575]      # pre-market dropped; RTH (9:30, 9:35) kept


def test_detect_first5_break():
    mb = [{"m": 570, "o": 9.6, "h": 10.0, "l": 9.5, "c": 9.8},
          {"m": 571, "o": 9.8, "h": 9.9, "l": 9.7, "c": 9.85},
          {"m": 575, "o": 9.9, "h": 10.5, "l": 9.9, "c": 10.4}]   # breaks OR high 10.0
    res = de.detect_first5_break(mb, gdl=9.0)
    assert res == (10.0, 9.5, 2)                     # entry = OR high, stop = OR low, break idx


def test_detect_first5_no_break():
    mb = [{"m": 570, "o": 9.6, "h": 10.0, "l": 9.5, "c": 9.8},
          {"m": 575, "o": 9.9, "h": 9.95, "l": 9.8, "c": 9.9}]    # never exceeds OR high
    assert de.detect_first5_break(mb, gdl=9.0) is None


def test_detect_gdl_reclaim():
    mb = [{"m": 570, "o": 8.5, "h": 8.9, "l": 8.4, "c": 8.8},
          {"m": 571, "o": 8.8, "h": 9.3, "l": 8.8, "c": 9.2}]     # close 9.2 > gdl 9.0
    res = de.detect_gdl_reclaim(mb, gdl=9.0)
    assert res == (9.2, 9.0, 1)


def test_simulate_first5_harvests_real_path():
    mb = [{"m": 570, "o": 9.6, "h": 10.0, "l": 9.5, "c": 9.8},
          {"m": 575, "o": 9.9, "h": 10.5, "l": 9.9, "c": 10.4},   # break (idx 1): entry 10, stop 9.5
          {"m": 576, "o": 10.4, "h": 11.6, "l": 10.3, "c": 11.5}]  # day-0 hits +1R (10.5) AND +3R (11.5)
    entry, stop, bidx = de.detect_first5_break(mb, gdl=9.0)
    daily_forward = [{"o": 11.5, "h": 12.0, "l": 11.0, "c": 11.8}]
    sim = de.simulate_first5(entry, stop, mb, bidx, daily_forward)
    assert sim is not None
    assert sim["realized_r"] > 0 and isinstance(sim["realized_r"], float)
    assert sim["fills"]                              # non-empty scale-out record (day0_fills)
    # +1R/+3R both banked day-0 → ~2.0R (0.5*1 + 0.5*3) on the real minute geometry.
    assert abs(sim["realized_r"] - 2.0) < 0.51
