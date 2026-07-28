"""#507 — the after-hours naked-stop alarm must not manufacture urgency."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
_ET = ZoneInfo("America/New_York")

def _in_market_hours(dt):
    return dt.weekday() < 5 and time(9, 30) <= dt.time() <= time(16, 0)

def test_the_2026_07_27_case_is_after_hours():
    """The alarm that fired at 16:28 demanding immediate action on a position
    that was never at risk and was auto-covered at 09:00."""
    assert not _in_market_hours(datetime(2026, 7, 27, 16, 28, tzinfo=_ET))

def test_intraday_still_demands_action():
    assert _in_market_hours(datetime(2026, 7, 27, 11, 0, tzinfo=_ET))

def test_boundaries_and_weekend():
    assert _in_market_hours(datetime(2026, 7, 27, 9, 30, tzinfo=_ET))
    assert _in_market_hours(datetime(2026, 7, 27, 16, 0, tzinfo=_ET))
    assert not _in_market_hours(datetime(2026, 7, 27, 9, 29, tzinfo=_ET))
    assert not _in_market_hours(datetime(2026, 7, 25, 12, 0, tzinfo=_ET))  # Saturday
