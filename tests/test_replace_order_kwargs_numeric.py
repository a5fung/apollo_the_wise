"""Regression test for replace_order str-vs-numeric kwargs bug (IBM 2026-05-28).

Pre-fix: `replace_order` wrapped qty/stop_price/limit_price as `str(x)` before
building the alpaca-py ReplaceOrderRequest. Pydantic validators inside
ReplaceOrderRequest expect numbers; the `str` value raises
`TypeError: '<=' not supported between instances of 'str' and 'int'`
during validation — BEFORE the HTTP call to Alpaca. Effect:
  - replace_order_by_id never reaches Alpaca
  - Original order stays alive broker-side
  - Caller catches TypeError, clears stop_order_id, fires "naked position"
    Telegram — but broker is still protected (DB-drift, not naked)

IBM trade #167 partial-take at 16:45 ET 2026-05-28 hit this exact path.

Post-fix: pass numerics as numbers. Test pins the kwargs shape by
inspecting what `ReplaceOrderRequest` receives.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_replace_order_passes_numeric_kwargs():
    """Replace_order must pass qty/stop_price/limit_price as numbers,
    not str. The bug fired in alpaca-py Pydantic validation when these
    were stringified."""
    from agents.market_intelligence.broker import alpaca_client

    captured: dict = {}

    class _FakeReplaceRequest:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_client = MagicMock()
    fake_order = MagicMock()
    fake_order.id = "new-id"
    fake_order.symbol = "IBM"
    fake_order.side = "sell"
    fake_order.type = "stop"
    fake_order.qty = 18
    fake_order.filled_qty = 0
    fake_order.filled_avg_price = None
    fake_order.stop_price = 230.94
    fake_order.limit_price = None
    fake_order.status = "accepted"
    fake_order.created_at = None
    fake_order.filled_at = None
    fake_order.client_order_id = "test-coid"
    fake_order.legs = []
    fake_client.replace_order_by_id.return_value = fake_order

    with patch.object(alpaca_client, "ReplaceOrderRequest", new=_FakeReplaceRequest), \
         patch.object(alpaca_client, "get_trading_client", return_value=fake_client):
        await alpaca_client.replace_order(
            "old-order-id",
            qty=18,
            stop_price=230.94,
            account_mode="paper",
            client_order_id="apollo_paper_magna53_IBM_123",
        )

    # The crux: numerics must remain numerics. Bug shipped them as str(x).
    assert captured.get("qty") == 18
    assert not isinstance(captured.get("qty"), str), (
        f"qty must be numeric (alpaca-py Pydantic validates `<= 0`); "
        f"got {type(captured.get('qty')).__name__}({captured.get('qty')!r})"
    )
    assert captured.get("stop_price") == 230.94
    assert not isinstance(captured.get("stop_price"), str), (
        f"stop_price must be numeric; "
        f"got {type(captured.get('stop_price')).__name__}"
    )
    assert captured.get("client_order_id") == "apollo_paper_magna53_IBM_123"


@pytest.mark.asyncio
async def test_replace_order_with_limit_price_also_numeric():
    """Limit price has the same numeric-vs-str invariant as stop_price."""
    from agents.market_intelligence.broker import alpaca_client

    captured: dict = {}

    class _FakeReplaceRequest:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_client = MagicMock()
    fake_order = MagicMock()
    fake_order.id = "new-id"
    fake_order.symbol = "X"
    fake_order.side = "buy"
    fake_order.type = "limit"
    fake_order.qty = 5
    fake_order.filled_qty = 0
    fake_order.filled_avg_price = None
    fake_order.stop_price = None
    fake_order.limit_price = 99.5
    fake_order.status = "accepted"
    fake_order.created_at = None
    fake_order.filled_at = None
    fake_order.client_order_id = "test"
    fake_order.legs = []
    fake_client.replace_order_by_id.return_value = fake_order

    with patch.object(alpaca_client, "ReplaceOrderRequest", new=_FakeReplaceRequest), \
         patch.object(alpaca_client, "get_trading_client", return_value=fake_client):
        await alpaca_client.replace_order(
            "id", qty=5, limit_price=99.5, account_mode="paper",
        )

    assert captured.get("limit_price") == 99.5
    assert not isinstance(captured.get("limit_price"), str)
