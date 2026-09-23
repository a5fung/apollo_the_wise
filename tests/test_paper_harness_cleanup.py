"""#439 part-b — the paper-integration harness must leave ZERO resting test orders in-run.
Pins `_sweep_test_orders_until_clear`: it cancels every harness-COID order, retries through
Alpaca's replace-pending window (a cancel there is rejected 42210000), confirms none remain,
and never touches a non-harness (real) order.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence.integration import paper_alpaca as pa
from agents.market_intelligence.broker import alpaca_client


def _test_order(oid, coid="apollo_paper_integration_test_1_stop"):
    return {"id": oid, "client_order_id": coid}


@pytest.mark.asyncio
async def test_sweep_until_clear_noop_when_empty(monkeypatch):
    monkeypatch.setattr(alpaca_client, "get_open_orders", AsyncMock(return_value=[]))
    cancel = AsyncMock()
    monkeypatch.setattr(alpaca_client, "cancel_order", cancel)
    await pa._sweep_test_orders_until_clear(timeout_s=1.0, poll_s=0.0)
    cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_until_clear_cancels_then_confirms_gone(monkeypatch):
    # order present, then gone after the cancel → clears with exactly one cancel.
    monkeypatch.setattr(alpaca_client, "get_open_orders",
                        AsyncMock(side_effect=[[_test_order("A")], []]))
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(alpaca_client, "cancel_order", cancel)
    await pa._sweep_test_orders_until_clear(timeout_s=1.0, poll_s=0.0)
    cancel.assert_awaited_once_with("A", account_mode="paper")


@pytest.mark.asyncio
async def test_sweep_until_clear_retries_through_replace_pending(monkeypatch):
    # The exact race that left orders resting: first cancel rejected (42210000) and the order is
    # STILL open next poll; the retry cancels it, then it's gone → clears, nothing left resting.
    monkeypatch.setattr(alpaca_client, "get_open_orders",
                        AsyncMock(side_effect=[[_test_order("B")], [_test_order("B")], []]))
    cancel = AsyncMock(side_effect=[Exception("original order pending replacement"), True])
    monkeypatch.setattr(alpaca_client, "cancel_order", cancel)
    await pa._sweep_test_orders_until_clear(timeout_s=2.0, poll_s=0.0)
    assert cancel.await_count == 2   # retried past the transient rejection


@pytest.mark.asyncio
async def test_sweep_until_clear_never_touches_a_real_order(monkeypatch):
    # A real resting order (non-harness COID) must NEVER be swept — the sweep is COID-scoped.
    monkeypatch.setattr(alpaca_client, "get_open_orders", AsyncMock(
        return_value=[{"id": "R", "client_order_id": "apollo_live_magna53_WULF_123"}]))
    cancel = AsyncMock()
    monkeypatch.setattr(alpaca_client, "cancel_order", cancel)
    await pa._sweep_test_orders_until_clear(timeout_s=1.0, poll_s=0.0)
    cancel.assert_not_awaited()
