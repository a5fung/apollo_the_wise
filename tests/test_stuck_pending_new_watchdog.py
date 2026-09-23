"""Regression tests for the stuck-pending_new watchdog (#142, 2026-05-28).

Triggered by RDW 2026-05-26: ORB entry stayed in Alpaca pending_new the
entire session because APScheduler misfired the 10:00 ET orb_window_cleanup
job that day. Defensive layer in reconcile_order_states catches stuck
orders regardless of why cleanup missed.

Threshold: 15 min stuck during market hours = alert. No auto-cancel
(operator decides per post-mortem discipline).
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool

_ET = ZoneInfo("America/New_York")


def _row(submitted_at, ticker="RDW", purpose="orb_entry"):
    """Build a row-like dict the reconcile loop yields."""
    return {
        "alpaca_order_id": "3e234281-1283-4ed8-8083-00c74f05c815",
        "ticker": ticker,
        "status": "pending_new",
        "trade_id": 169,
        "purpose": purpose,
        "submitted_at": submitted_at,
    }


def _market_open():
    return MagicMock(is_trading_day=True, reason="open")


def _holiday():
    return MagicMock(is_trading_day=False, reason="holiday: Memorial Day")


@pytest.mark.asyncio
async def test_alerts_on_15min_stuck_during_market_hours():
    """RDW pattern: stuck 30 min during market hours → Telegram + audit fire."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)

    submitted = datetime.now(_ET) - timedelta(minutes=30)
    row = _row(submitted_at=submitted)

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(order_manager, "send_telegram_message", new=_fake_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True):
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    assert audit_mock.called
    audit_args = audit_mock.call_args[0]
    assert audit_args[0] == "stuck_pending_new_detected"
    assert "RDW" in audit_args[1]
    assert len(sent) == 1
    assert "RDW" in sent[0]
    assert "pending_new" in sent[0].lower()


@pytest.mark.asyncio
async def test_no_alert_when_under_threshold():
    """5 min stuck = within normal routing variance → no alert."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)

    submitted = datetime.now(_ET) - timedelta(minutes=5)
    row = _row(submitted_at=submitted)

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(order_manager, "send_telegram_message", new=_fake_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True):
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    assert not audit_mock.called
    assert sent == []


@pytest.mark.asyncio
async def test_no_alert_outside_market_hours():
    """Pre-market / after-hours pending_new is legitimate (orders queued
    awaiting open routing). Don't alert."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)
    submitted = datetime(2026, 5, 26, 6, 0, tzinfo=_ET)
    row = _row(submitted_at=submitted)

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(order_manager, "send_telegram_message", new=_fake_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=False):
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    assert not audit_mock.called
    assert sent == []


@pytest.mark.asyncio
async def test_no_alert_on_non_trading_day():
    """Market holiday → no alert even if stuck >15 min. The shared
    `is_market_hours_now_et` helper returns False on holidays via
    `get_market_status().is_trading_day`."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)

    submitted = datetime.now(_ET) - timedelta(minutes=60)
    row = _row(submitted_at=submitted)

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(order_manager, "send_telegram_message", new=_fake_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=False):
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    assert not audit_mock.called
    assert sent == []


@pytest.mark.asyncio
async def test_dedups_via_existing_audit_row():
    """Already alerted today (audit row exists) → silent."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=1)  # dedup row exists

    submitted = datetime.now(_ET) - timedelta(minutes=120)
    row = _row(submitted_at=submitted)

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(order_manager, "send_telegram_message", new=_fake_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True):
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    assert not audit_mock.called
    assert sent == []


@pytest.mark.asyncio
async def test_telegram_failure_does_not_break_audit():
    """If Telegram throws, the audit row was already written — guarantees
    durable record of the detection per `feedback_no_silent_trading_failures`."""
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import trading_calendar
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)

    submitted = datetime.now(_ET) - timedelta(minutes=20)
    row = _row(submitted_at=submitted)

    async def _broken_send(text, *args, **kwargs):
        raise RuntimeError("telegram down")

    with patch.object(order_manager, "send_telegram_message", new=_broken_send), \
         patch.object(order_manager, "log_audit_event", new=AsyncMock()) as audit_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True):
        # Should not raise
        await order_manager._maybe_alert_stuck_pending_new(conn, row, "paper", submitted_at=submitted)

    # Audit must have been written before Telegram attempt
    assert audit_mock.called
