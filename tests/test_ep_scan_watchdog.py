"""Regression tests for the EP scan watchdog DB ground-truth check.

Pre-fix (2026-05-28): watchdog read the in-process counter
`_ep_scans_completed_today`. Container restart mid-session reset the
counter to 0 → false-positive "No EP scan completed today" Telegram
even though scans had run successfully in the prior process.

Post-fix: watchdog queries `mi_job_runs` for actual ep_scan success
rows today. Process-restart-resilient. Same shape as the post-IBM
sync_positions safety guard (#137).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import scheduler


_ET = ZoneInfo("America/New_York")


def _make_pool(scan_count: int, alert_count: int = 0):
    """Build a mock asyncpg pool whose conn.fetchval returns scan_count
    on the first call (the ep_scan job count) and alert_count on the
    second (the mi_ep_alerts count, only queried on OK branch)."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=[scan_count, alert_count])
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


@pytest.mark.asyncio
async def test_watchdog_alerts_when_no_scans_in_db():
    """0 ep_scan success rows → Telegram alert fires."""
    pool, _conn = _make_pool(scan_count=0)
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    market_status = MagicMock(is_trading_day=True, reason="open")
    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send), \
         patch.object(scheduler, "get_market_status", return_value=market_status), \
         patch.object(scheduler, "datetime") as _dt:
        _dt.now.return_value = datetime(2026, 5, 28, 10, 5, tzinfo=_ET)
        await scheduler._ep_scan_watchdog()

    assert len(sent) == 1
    assert "EP Scan Watchdog" in sent[0]
    assert "No EP scan completed today" in sent[0]


@pytest.mark.asyncio
async def test_watchdog_silent_when_scans_succeeded_in_db():
    """≥1 ep_scan success row → OK branch, no Telegram."""
    pool, _conn = _make_pool(scan_count=7, alert_count=6)
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    market_status = MagicMock(is_trading_day=True, reason="open")
    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send), \
         patch.object(scheduler, "get_market_status", return_value=market_status), \
         patch.object(scheduler, "datetime") as _dt:
        _dt.now.return_value = datetime(2026, 5, 28, 10, 5, tzinfo=_ET)
        await scheduler._ep_scan_watchdog()

    assert sent == []


@pytest.mark.asyncio
async def test_watchdog_skips_on_non_trading_day():
    """Memorial Day / holiday → return early, no DB query, no Telegram."""
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    market_status = MagicMock(is_trading_day=False, reason="holiday: Memorial Day")
    with patch.object(scheduler, "get_pool", new=AsyncMock()) as _pool_mock, \
         patch.object(scheduler, "send_telegram_message", new=_fake_send), \
         patch.object(scheduler, "get_market_status", return_value=market_status), \
         patch.object(scheduler, "datetime") as _dt:
        _dt.now.return_value = datetime(2026, 5, 25, 10, 5, tzinfo=_ET)  # Memorial Day Mon
        await scheduler._ep_scan_watchdog()

    assert sent == []
    _pool_mock.assert_not_called()


@pytest.mark.asyncio
async def test_watchdog_db_query_failure_is_logged_not_raised():
    """If the DB query raises, the watchdog logs but doesn't crash the scheduler."""
    pool = MagicMock()
    pool.acquire = MagicMock(side_effect=RuntimeError("pool down"))
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    market_status = MagicMock(is_trading_day=True, reason="open")
    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send), \
         patch.object(scheduler, "get_market_status", return_value=market_status), \
         patch.object(scheduler, "datetime") as _dt:
        _dt.now.return_value = datetime(2026, 5, 28, 10, 5, tzinfo=_ET)
        # Should not raise
        await scheduler._ep_scan_watchdog()

    # No Telegram on infrastructure failure — safer to be silent than misalert
    assert sent == []
