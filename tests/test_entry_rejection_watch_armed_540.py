"""#540 HEARTBEAT — `_handle_cancel_or_reject`'s rejection-watch trace.

THE BUG (as filed): the `entry_order_rejected` capture (audit_events.ENTRY_ORDER_REJECTED,
written inside `_handle_cancel_or_reject`) writes ONLY when a rejection actually
lands on a row still in a TRACKED status. It had not fired once since
2026-08-07 — three days BEFORE the #540 capture itself shipped 2026-08-10 —
making a month of silence indistinguishable from a dead capture. The common,
EXPECTED reason for silence: the 10:00 ET unfilled-cleanup job already flips
an unfilled entry's status away from the tracked set before this WS event
lands (see the #475 comment in trade_stream.py), so `entry_trade` comes back
None and the capture correctly stays quiet.

FIX: the SAME handler now records, when its own `entry_trade` lookup comes
back empty for a BUY-side order, that the check ran and found nothing NEW —
the #452 exposure_family "checked" idea (tests/test_exposure_family_452.py)
applied to the function ENTRY_ORDER_REJECTED already lives in. An earlier
draft placed this in `submit_entry()` (order_manager.py) instead — that only
proves an order was SUBMITTED (already provable via `orb_order_placed`) and
says nothing about whether THIS handler still runs; moved here after review.

Reuses `_run_reject` from tests/test_broker_reject_reason_540.py — the
established harness for driving `_handle_cancel_or_reject` — rather than
re-deriving the wiring.
"""
from __future__ import annotations

import json

import pytest

from tests.test_broker_reject_reason_540 import _INSM_ROW, _run_reject
from agents.market_intelligence.audit_events import ENTRY_REJECTION_WATCH_ARMED


def _watch_armed_calls(audit):
    return [c for c in audit.await_args_list if c.args[0] == ENTRY_REJECTION_WATCH_ARMED]


@pytest.mark.asyncio
async def test_watch_armed_fires_when_the_row_is_already_routine_cancelled(monkeypatch):
    """The exact case #540 could not distinguish from a dead capture: a buy-side
    order dies, but the row is no longer in a tracked status (the routine 10:00 ET
    cleanup got there first) — entry_trade is None, and the check must still
    leave a trace instead of going silent."""
    from types import SimpleNamespace

    data = SimpleNamespace(
        order=SimpleNamespace(id="ord-routine-1", symbol="RTNE", side="buy"),
        reason=None,
    )
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "canceled", entry_row=None,
    )

    armed = _watch_armed_calls(audit)
    assert len(armed) == 1, "a buy-side order with no tracked row must still leave a trace"
    detail = json.loads(armed[0].args[2])
    assert detail["ticker"] == "RTNE"
    assert detail["entry_trade_found"] is False
    assert detail["event_norm"] == "cancelled"


@pytest.mark.asyncio
async def test_watch_armed_does_not_fire_when_the_capture_already_wrote_a_row(monkeypatch):
    """The additive rule: when entry_trade IS found (the actual capture fires),
    the heartbeat must NOT also fire — it exists for the silent case only."""
    from types import SimpleNamespace

    data = SimpleNamespace(
        order=SimpleNamespace(id="ord-tracked-1", symbol="INSM", side="buy"),
        reason=None,
    )
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "rejected", entry_row=_INSM_ROW,
    )

    assert _watch_armed_calls(audit) == []


@pytest.mark.asyncio
async def test_watch_armed_does_not_fire_for_sell_side_orders(monkeypatch):
    """Stop-loss legs, exits, OCO members are all sell-side and are handled by
    their own sections below — the entry-rejection watch must stay scoped to
    buy-side (entry-shaped) orders, or it stops meaning anything specific."""
    from types import SimpleNamespace

    data = SimpleNamespace(
        order=SimpleNamespace(id="ord-sell-1", symbol="SELX", side="sell"),
        reason=None,
    )
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "canceled", entry_row=None,
    )

    assert _watch_armed_calls(audit) == []


@pytest.mark.asyncio
async def test_watch_armed_write_failure_does_not_block_downstream_handling(monkeypatch):
    """A telemetry write failure here must never block the stop-loss/exit
    handling that follows it in the same function: make the audit write raise
    and assert the caller's behaviour (no exception escapes) is unchanged."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import agents.market_intelligence.broker.trade_stream as ts
    from tests.conftest import make_mock_pool

    data = SimpleNamespace(
        order=SimpleNamespace(id="ord-routine-2", symbol="RTN2", side="buy"),
        reason=None,
    )
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    raising_audit = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(ts, "log_audit_event", raising_audit)
    monkeypatch.setattr(ts, "send_telegram_message", AsyncMock(return_value=True))

    # Must not raise — the failing write is swallowed, same as ENTRY_ORDER_REJECTED's own wrapper.
    await ts._handle_cancel_or_reject(data, "canceled", "live")

    assert raising_audit.await_count >= 1, "the (failing) write must still have been attempted"
