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

    # Numerics stay numeric — the #136 str(x) wrapping was the bug (fixed
    # 2026-05-28; see test_replace_order_kwargs_numeric.py). These assertions
    # were stale on the old str contract.
    assert captured["qty"] == 18
    assert captured["stop_price"] == 230.94
    fake_client.replace_order_by_id.assert_called_once()
    assert fake_client.replace_order_by_id.call_args.args[0] == "old_stop_id_xyz"
    assert result["id"] == "new_order_id"


@pytest.mark.asyncio
async def test_partial_exit_paused_takes_no_action():
    """#151 HARD PAUSE (2026-06-22, operator): while _PARTIAL_EXIT_PAUSED, execute_partial_exit
    returns False and touches NOTHING — it never reaches the breaker query, the stop replace, or
    the sell — so the position keeps its FULL stop + size. Applies even to force=True (/partialnow),
    since the pending_replace-race breaks that path too. The breaker mock raises if reached."""
    from agents.market_intelligence.broker import order_manager

    audited = []
    async def _audit(evt, *a, **k):
        audited.append(evt)
        return None

    with patch.object(order_manager, "_PARTIAL_EXIT_PAUSED", True), \
         patch.object(order_manager, "log_audit_event", _audit), \
         patch.object(order_manager, "_consecutive_partial_exit_failures",
                      AsyncMock(side_effect=AssertionError("breaker reached PAST the pause guard"))):
        ok = await order_manager.execute_partial_exit(221, 66, force=True)
    assert ok is False
    assert audited == ["partial_exit_paused"]


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

    assert captured.get("qty") == 10  # numeric (stale str assertion fixed)
    assert "stop_price" not in captured  # not passed, must not appear


def test_round_stop_to_tick_floors_away_from_trigger():
    """RCAT 2026-06-01: the partial-exit replace submitted a 3-decimal stop
    (11.955, from the ORB low) raw → Alpaca rejected it (42210000 sub-penny)
    → atomic replace failed, the old stop stayed live, but the abort handler
    fired a false-naked alert. _round_stop_to_tick floors to Alpaca's tick
    (>$1 → $0.01; <=$1 → $0.0001), away from the trigger so a protective
    sell-stop never rounds toward current price."""
    from agents.market_intelligence.broker.alpaca_client import _round_stop_to_tick
    assert _round_stop_to_tick(11.955) == 11.95     # the RCAT case
    assert _round_stop_to_tick(8.40) == 8.40        # already valid — untouched
    assert _round_stop_to_tick(230.94) == 230.94    # already valid — untouched
    assert _round_stop_to_tick(5.001) == 5.00       # floors to penny
    assert _round_stop_to_tick(0.50055) == 0.5005   # sub-$1 keeps 4 decimals


@pytest.mark.asyncio
async def test_replace_order_rounds_subpenny_stop_before_submit():
    """The submission-boundary guard: replace_order must round stop_price to
    the tick BEFORE building ReplaceOrderRequest, so a sub-penny value can
    never reach Alpaca (which rejects it, failing the atomic replace)."""
    from agents.market_intelligence.broker import alpaca_client

    fake_client = MagicMock()
    fake_client.replace_order_by_id.return_value = MagicMock(
        id="new_id", client_order_id=None, symbol="RCAT",
        side="sell", type="stop", qty="1020", filled_qty="0",
        filled_avg_price=None, stop_price="11.95", limit_price=None,
        status="new", created_at=None, filled_at=None, legs=None,
    )

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
            "old_stop_id", qty=1020, stop_price=11.955, account_mode="paper",
        )

    assert captured["stop_price"] == 11.95, (
        f"sub-penny 11.955 must be floored to 11.95 before submit; "
        f"got {captured['stop_price']!r}"
    )
    assert not isinstance(captured["stop_price"], str)


def test_is_share_reservation_lag_matches_only_clean_rejection():
    """#150: the sell-retry must fire on Alpaca's share-reservation lag
    ('insufficient qty available' / held_for_orders) — a clean rejection where
    NO order was placed (safe to retry) — but NOT on ambiguous errors like a
    network timeout (which may have placed the order → retry would oversell)."""
    from agents.market_intelligence.broker.order_manager import (
        _is_share_reservation_lag,
    )
    # Retryable: clean broker rejection, no order placed.
    assert _is_share_reservation_lag(Exception("insufficient qty available")) is True
    assert _is_share_reservation_lag(
        Exception('{"code":40310000,"message":"insufficient qty available for RCAT"}')
    ) is True
    assert _is_share_reservation_lag(Exception("held_for_orders: 26")) is True
    # NOT retryable: ambiguous/hard errors must fall through to rollback so we
    # never re-submit a sell that might have already been accepted.
    assert _is_share_reservation_lag(Exception("Read timed out")) is False
    assert _is_share_reservation_lag(Exception("connection reset by peer")) is False
    assert _is_share_reservation_lag(Exception("order already filled")) is False
