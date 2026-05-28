"""Regression tests for #136 partial-exit replace_order race fix (2026-05-27).

Bug: execute_partial_exit cancelled the existing stop then submitted a
new stop with reduced qty. Alpaca accepts the cancel synchronously but
the share-reservation system clears asynchronously — at ~43ms between
the cancel and new-submit (IBM 2026-05-27), Alpaca rejected the new
stop with "insufficient qty available" because held_for_orders still
showed the full position. Position left with stop_order_id=NULL.

Fix: use Alpaca's atomic replace_order_by_id (no share release window).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Reuse the existing alpaca-SDK stub from conftest.py (auto-loaded).


def _make_order_dict(order_id, qty, stop_price=None):
    return {
        "id": order_id, "side": "OrderSide.SELL", "type": "OrderType.STOP",
        "qty": qty, "filled_qty": 0, "stop_price": stop_price,
        "status": "new", "client_order_id": None,
    }


@pytest.mark.asyncio
async def test_replace_order_passes_qty_and_stop_price():
    """replace_order() must forward both qty and stop_price to the broker
    via ReplaceOrderRequest. The IBM bug was that the partial flow used
    cancel+new; the fix uses replace + must carry both fields atomically."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_returned = MagicMock(
        id="new_order_id", client_order_id=None, symbol="IBM",
        side="sell", type="stop", qty="18", filled_qty="0",
        filled_avg_price=None, stop_price="230.94", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )
    fake_client.replace_order_by_id.return_value = fake_returned

    captured: dict = {}
    def _stub_request_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ), patch.object(
        alpaca_client, "ReplaceOrderRequest", side_effect=_stub_request_ctor,
    ):
        result = await alpaca_client.replace_order(
            "old_stop_id_xyz",
            qty=18,
            stop_price=230.94,
            account_mode="paper",
        )

    assert captured["qty"] == "18"
    assert captured["stop_price"] == "230.94"
    fake_client.replace_order_by_id.assert_called_once()
    assert fake_client.replace_order_by_id.call_args.args[0] == "old_stop_id_xyz"
    assert result["id"] == "new_order_id"


@pytest.mark.asyncio
async def test_replace_order_propagates_broker_errors():
    """If the broker rejects the replace (e.g., order already filled), the
    exception must propagate so execute_partial_exit's outer try/except can
    fall through to the partial_exit_aborted path."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_client.replace_order_by_id.side_effect = RuntimeError(
        "order already filled"
    )

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ):
        with pytest.raises(RuntimeError, match="order already filled"):
            await alpaca_client.replace_order(
                "old_stop_id", qty=18, stop_price=230.94,
                account_mode="paper",
            )


@pytest.mark.asyncio
async def test_replace_order_omits_unset_fields():
    """qty-only replace (no stop_price change) should omit stop_price from
    the request — avoids accidentally overriding the broker's stop with
    None."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_returned = MagicMock(
        id="x", client_order_id=None, symbol="IBM",
        side="sell", type="stop",
        qty="10", filled_qty="0", filled_avg_price=None,
        stop_price="100.0", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )
    fake_client.replace_order_by_id.return_value = fake_returned

    captured: dict = {}
    def _stub_request_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with patch.object(
        alpaca_client, "get_trading_client", return_value=fake_client,
    ), patch.object(
        alpaca_client, "ReplaceOrderRequest", side_effect=_stub_request_ctor,
    ):
        await alpaca_client.replace_order(
            "old", qty=10, account_mode="paper",
        )

    assert captured.get("qty") == "10"
    assert "stop_price" not in captured  # not passed, must not appear
