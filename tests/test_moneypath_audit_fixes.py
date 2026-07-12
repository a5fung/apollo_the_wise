"""Money-path audit fixes (2026-07-12, register R1/R2/R6) — behavior pins.

R2: attempt_day1_reentry is now behind BOTH kill switches (was: bypassed both —
    the /pause hole, latent while R3_DAY1_REENTRY_ENABLED=false).
R1: the three fill finalizers hold the per-trade #151 advisory lock for the whole
    read-modify-write (was: the only trade-state writers outside the lock).
R6: check_fills refetches the stop leg on a miss + skips rows the WS already
    processed (was: COALESCE(NULL,…) no-op + a duplicate fill Telegram).
"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence.broker import order_manager as om

MOD = "agents.market_intelligence.broker.order_manager"

_TRADE = {
    "id": 7, "ticker": "TSTX", "entry_price": 10.0, "entry_shares": 100,
    "remaining_shares": 100, "orb_high": 10.5, "orb_low": 9.5, "stop_price": 9.5,
    "atr_14": 0.4, "stop_order_id": "stp-1", "entry_attempt": 1, "exits": [],
    "ep_score": 70, "catalyst_quality": "strong", "gap_pct": 8.0, "regime": "Bull",
    "alert_date": None, "account_mode": "live", "signal_type": "magna53",
}


# ── R2: the re-entry kill-switch gates ──────────────────────────────────────
@pytest.mark.asyncio
async def test_reentry_blocked_when_kill_switch_off(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=_TRADE)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "LIVE_TRADING_ENABLED", False)
    audit = AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)

    res = await om.attempt_day1_reentry(7, 9.4, source="websocket")

    assert res["action"] == "reentry_blocked_kill_switch"
    assert audit.await_args.args[0] == "reentry_blocked_by_kill_switch"


@pytest.mark.asyncio
@pytest.mark.parametrize("halt", ["on", "unreadable"])
async def test_reentry_blocked_by_manual_halt_live_mode(monkeypatch, halt):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=_TRADE)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(om, "get_manual_halt_state", AsyncMock(return_value=halt))
    audit = AsyncMock()
    monkeypatch.setattr(om, "log_audit_event", audit)

    res = await om.attempt_day1_reentry(7, 9.4, source="websocket")

    assert res["action"] == "reentry_blocked_halt"
    assert audit.await_args.args[0] == "reentry_blocked_by_halt"


@pytest.mark.asyncio
async def test_reentry_halt_not_consulted_for_paper(monkeypatch):
    """Paper re-entry proceeds past the gates (halt is a LIVE-only switch)."""
    trade = {**_TRADE, "account_mode": "paper", "alert_date": None}
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=trade)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "LIVE_TRADING_ENABLED", True)
    halt = AsyncMock(return_value="on")
    monkeypatch.setattr(om, "get_manual_halt_state", halt)
    # let the function continue into its body; it will fail/return past the gates
    # on the mocked alpaca — we only pin that the halt was NOT consulted.
    monkeypatch.setattr(om, "alpaca", MagicMock(get_latest_price=AsyncMock(return_value=None)))

    try:
        await om.attempt_day1_reentry(7, 9.4, source="websocket")
    except Exception:
        pass  # the mocked body may fail past the gates — the pin is gate-order only

    halt.assert_not_awaited()


# ── R1: finalizers hold the per-trade advisory lock ─────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("public,locked", [
    ("finalize_partial_exit", "_finalize_partial_exit_locked"),
    ("finalize_full_exit", "_finalize_full_exit_locked"),
    ("finalize_stop_fill", "_finalize_stop_fill_locked"),
])
async def test_finalizers_take_the_advisory_lock(monkeypatch, public, locked):
    entered = {"n": 0}

    @asynccontextmanager
    async def fake_lock(trade_id):
        entered["n"] += 1
        assert trade_id == 7
        yield

    inner = AsyncMock()
    monkeypatch.setattr(om, "_trade_advisory_lock", fake_lock)
    monkeypatch.setattr(om, locked, inner)

    if public == "finalize_full_exit":
        await om.finalize_full_exit(7, 50, 10.0, "ord-1", "test_reason")
    else:
        await getattr(om, public)(7, 50, 10.0, "ord-1")

    assert entered["n"] == 1
    inner.assert_awaited_once()


# ── R6: check_fills refetch + WS-dedup skip ────────────────────────────────
@pytest.mark.asyncio
async def test_check_fills_skips_row_already_processed_by_ws(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[{
        "id": 7, "ticker": "TSTX", "entry_order_id": "ent-1", "entry_shares": 100,
        "orb_low": 9.5, "stop_price": 9.5, "entry_attempt": 1, "account_mode": "paper",
    }], []])  # 2nd fetch = the Day-1 stop-out poll -> empty
    conn.execute = AsyncMock(return_value="UPDATE 0")  # WS won the claim
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    fake_alpaca = MagicMock()
    fake_alpaca.get_order = AsyncMock(return_value={
        "status": "filled", "filled_avg_price": 10.1, "filled_qty": 100,
    })
    fake_alpaca.extract_stop_leg_id = MagicMock(return_value="stp-9")
    monkeypatch.setattr(om, "alpaca", fake_alpaca)
    tg = AsyncMock()
    monkeypatch.setattr(om, "send_telegram_message", tg)

    results = await om.check_fills()

    assert results == []          # no duplicate fill processing
    tg.assert_not_awaited()       # and no duplicate Telegram


@pytest.mark.asyncio
async def test_check_fills_refetches_stop_leg_on_miss(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[{
        "id": 7, "ticker": "TSTX", "entry_order_id": "ent-1", "entry_shares": 100,
        "orb_low": 9.5, "stop_price": 9.5, "entry_attempt": 1, "account_mode": "paper",
    }], []])  # 2nd fetch = the Day-1 stop-out poll -> empty
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchval = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    fake_alpaca = MagicMock()
    # first get_order: the poll (legs omitted); second: the refetch (legs present)
    fake_alpaca.get_order = AsyncMock(side_effect=[
        {"status": "filled", "filled_avg_price": 10.1, "filled_qty": 100},
        {"status": "filled", "legs": [{"id": "stp-9", "stop_price": 9.5, "type": "stop"}]},
    ])
    fake_alpaca.extract_stop_leg_id = MagicMock(side_effect=[None, "stp-9"])
    monkeypatch.setattr(om, "alpaca", fake_alpaca)
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock())

    await om.check_fills()

    assert fake_alpaca.get_order.await_count == 2          # the refetch happened
    assert fake_alpaca.extract_stop_leg_id.call_count == 2
    # the trade UPDATE carried the refetched stop id as $5
    args = conn.execute.await_args_list[0].args
    assert "stp-9" in args
