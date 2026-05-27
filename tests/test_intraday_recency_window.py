"""Regression tests for _recent_low_in_window (#124, 2026-05-26).

The fix replaces day_low (cumulative high-water) with min(low) over the
last K=30 minutes for MA-pullback and support-test detector gates. These
tests pin the helper's behavior:
  - Returns (None, None) on fetch failure or empty bar window
  - Returns the lowest bar's (low, time_in_scan_tz) on success
  - Respects the k_minutes window (start = scan_time - k_minutes)
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_returns_none_on_empty_bars():
    from agents.market_intelligence.flag_detector import _recent_low_in_window
    with patch(
        "agents.market_intelligence.collector._polygon_get",
        new=AsyncMock(return_value={"results": []}),
    ):
        low, when = await _recent_low_in_window("TEST", datetime.now(timezone.utc))
    assert low is None
    assert when is None


@pytest.mark.asyncio
async def test_returns_none_on_fetch_failure():
    from agents.market_intelligence.flag_detector import _recent_low_in_window
    with patch(
        "agents.market_intelligence.collector._polygon_get",
        new=AsyncMock(side_effect=RuntimeError("polygon 500")),
    ):
        low, when = await _recent_low_in_window("TEST", datetime.now(timezone.utc))
    assert low is None
    assert when is None


@pytest.mark.asyncio
async def test_returns_lowest_bar_and_its_time():
    from agents.market_intelligence.flag_detector import _recent_low_in_window
    scan_t = datetime(2026, 5, 26, 19, 20, tzinfo=timezone.utc)
    # Three bars; lowest at the middle one (t = scan-20min, low=18.50)
    bars = [
        {"t": int((scan_t - timedelta(minutes=25)).timestamp() * 1000), "l": 19.00, "h": 19.10, "o": 19.05, "c": 19.08, "v": 100},
        {"t": int((scan_t - timedelta(minutes=20)).timestamp() * 1000), "l": 18.50, "h": 18.80, "o": 18.70, "c": 18.65, "v": 200},
        {"t": int((scan_t - timedelta(minutes=10)).timestamp() * 1000), "l": 19.20, "h": 19.40, "o": 19.25, "c": 19.35, "v": 150},
    ]
    with patch(
        "agents.market_intelligence.collector._polygon_get",
        new=AsyncMock(return_value={"results": bars}),
    ):
        low, when = await _recent_low_in_window("TEST", scan_t)
    assert low == 18.50
    assert when is not None
    # Should be the middle bar's time (scan-20min) — within 1 minute tolerance
    delta = abs((scan_t - when).total_seconds())
    assert 1100 < delta < 1300  # ~20 minutes = 1200 sec


@pytest.mark.asyncio
async def test_fresh_touch_within_window_is_kept():
    """A touch 10 minutes ago should still register — fresh pullback."""
    from agents.market_intelligence.flag_detector import _recent_low_in_window
    scan_t = datetime(2026, 5, 26, 14, 0, tzinfo=timezone.utc)
    bars = [
        {"t": int((scan_t - timedelta(minutes=10)).timestamp() * 1000), "l": 100.00, "h": 100.10, "o": 100.05, "c": 100.08, "v": 100},
    ]
    with patch(
        "agents.market_intelligence.collector._polygon_get",
        new=AsyncMock(return_value={"results": bars}),
    ):
        low, when = await _recent_low_in_window("TEST", scan_t, k_minutes=30)
    assert low == 100.00
    assert when is not None
    delta = abs((scan_t - when).total_seconds())
    assert 550 < delta < 650  # ~10 minutes
