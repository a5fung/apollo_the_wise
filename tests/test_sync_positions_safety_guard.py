"""Regression test for sync_positions mass-close safety guard.

Incident 2026-05-27 23:01 ET: docker exec python one-shot ran
sync_positions outside the agent's credential bootstrap. Alpaca client
failed (`ALPACA_PAPER_API_KEY` missing in env-vars-not-remapped sub-
process), get_all_positions returned 0. Code then assumed "Alpaca has
0 positions" = "all positions liquidated by user" and mass-closed 3
active DB trades (PURR/IBM/CRSR). Manual SQL restore required.

Fix: when Alpaca returns 0 positions BUT DB has N>0 active filled
trades, that's a broker-side failure signal (creds, 5xx, network) —
NOT a real liquidation event. Audit + abort the sync rather than
destroy DB state.

Trade-off: if a user actually liquidates everything manually via
Alpaca dashboard, this guard delays the DB-side reconciliation until
operator triggers manually. That's the safer side of the trade-off.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_db_trade(trade_id, ticker, remaining=10, status="filled"):
    return {
        "id": trade_id, "ticker": ticker,
        "remaining_shares": remaining, "entry_price": 100.0,
        "status": status, "stop_order_id": None,
        "stop_price": 95.0, "orb_low": 95.0,
        "signal_type": "magna53",
    }


def _stub_pool(db_trades):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=db_trades)
    conn.execute = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = conn
    ctx.__aexit__.return_value = None
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_zero_alpaca_positions_with_db_active_aborts():
    """The exact 2026-05-27 23:01 ET incident: Alpaca returns [], DB
    has 3 active filled trades. Sync must NOT mass-close — must abort
    + audit instead."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    db_trades = [
        _make_db_trade(161, "PURR", remaining=632),
        _make_db_trade(167, "IBM", remaining=26),
        _make_db_trade(172, "CRSR", remaining=2073),
    ]
    pool, conn = _stub_pool(db_trades)
    audit_log_calls = []

    async def _audit(event_type, summary=None, detail=None):
        audit_log_calls.append((event_type, summary, detail))

    with patch(
        "agents.market_intelligence.broker.order_manager.alpaca.get_all_positions",
        new=AsyncMock(return_value=[]),  # ← empty: broker-side failure or true zero
    ), patch(
        "agents.market_intelligence.broker.order_manager.get_pool",
        new=AsyncMock(return_value=pool),
    ), patch(
        "agents.market_intelligence.broker.order_manager.log_audit_event",
        new=_audit,
    ):
        result = await _sync_positions_for_mode("paper")

    # Audit row was emitted
    assert any(
        c[0] == "sync_positions_aborted_alpaca_empty" for c in audit_log_calls
    ), "must emit sync_positions_aborted_alpaca_empty audit"

    # Result message indicates abort
    assert len(result) == 1
    assert "ABORTED" in result[0]
    assert "3 DB-active" in result[0]

    # CRITICAL: no UPDATE mi_live_trades SET status='closed' was executed
    closed_executes = [
        call for call in conn.execute.call_args_list
        if call.args and "status = 'closed'" in (call.args[0] or "")
    ]
    assert closed_executes == [], (
        "must not mass-close DB trades on Alpaca-empty-while-DB-active"
    )


@pytest.mark.asyncio
async def test_zero_alpaca_zero_db_normal_path():
    """When both Alpaca AND DB show no active trades, the guard
    doesn't fire — sync proceeds normally (empty list discrepancies)."""
    from agents.market_intelligence.broker.order_manager import (
        _sync_positions_for_mode,
    )

    pool, conn = _stub_pool([])  # no DB trades

    async def _noop(*args, **kwargs):
        pass

    with patch(
        "agents.market_intelligence.broker.order_manager.alpaca.get_all_positions",
        new=AsyncMock(return_value=[]),
    ), patch(
        "agents.market_intelligence.broker.order_manager.get_pool",
        new=AsyncMock(return_value=pool),
    ), patch(
        "agents.market_intelligence.broker.order_manager.log_audit_event",
        new=_noop,
    ):
        result = await _sync_positions_for_mode("paper")

    # Empty Alpaca + empty DB = no discrepancies, no abort message
    assert result == []
