"""#168 — consolidated EOD entry-technique digest formatter.

Verifies the surfacing behaviour that replaces the ~23/day per-tick shadow
pings: suppress entirely on zero-fire days, omit empty detectors, cap long
lists, and mark sugar-baby-cohort tickers.
"""
from datetime import date
from agents.market_intelligence.flag_detector import _build_intraday_signals_digest

D = date(2026, 6, 8)


def test_all_empty_suppressed():
    per = [("🎯", "Flag-break", []), ("📉", "MA-pullback", [])]
    assert _build_intraday_signals_digest(D, per) is None


def test_empty_detectors_omitted():
    per = [
        ("🎯", "Flag-break", [("AAPL", False, "COILED"), ("NVDA", True, "TRIGGERED")]),
        ("📉", "MA-pullback", []),            # omitted
        ("🛡", "Support-test", [("MSFT", False, "TIGHTENING")]),
    ]
    msg = _build_intraday_signals_digest(D, per)
    assert msg is not None
    assert "Flag-break* (2)" in msg
    assert "Support-test* (1)" in msg
    assert "MA-pullback" not in msg          # empty section dropped
    assert "🎯🍬NVDA" in msg                  # stage emoji + cohort marker
    assert "🌀AAPL" in msg                    # COILED stage emoji, no cohort
    assert "🍬AAPL" not in msg                # non-cohort unmarked
    assert "3 shadow signals across 2 techniques" in msg
    assert "/detectors" in msg               # only the registered command


def test_long_list_capped():
    rows = [(f"T{i}", False, "COILED") for i in range(20)]
    msg = _build_intraday_signals_digest(D, [("🎯", "Flag-break", rows)])
    assert "…+5" in msg                       # 20 - 15 cap
    assert "Flag-break* (20)" in msg          # count reflects full total


def test_no_entries_disclaimer():
    msg = _build_intraday_signals_digest(D, [("🎯", "Flag-break", [("X", False, "COILED")])])
    assert "telemetry only, no entries" in msg
