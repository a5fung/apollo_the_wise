"""#687 ruling (3), operator 2026-10-01 ("Yes"): a stop that cannot be placed because the price is
already through it → SELL AT MARKET, as the triggered stop would have.

Built where a PLANNED SALE's cancelled stop is being put back — the place the exit rule has
already decided to sell:
  * `order_manager._restore_stop_after_failed_exit` — the 16:45 close-below sale (`execute_full_exit`)
    or the 19:01 opening-auction sale (`execute_depth_open_sale`) was rejected;
  * `trade_stream._handle_cancel_or_reject` §3 — the queued closing order died unfilled.
Before: the broker's "stop price must be less than current price" rejection paged "STOP NOT
RESTORED — UNPROTECTED" and left the shares bare. Now: the shares the restore would have covered
(the broker's free count — a resting +8R profit-take third keeps its own OCO) are sold at market as
a `full_exit` row, and the page says so. A sale that fails too still pages UNPROTECTED.

Ruling (iii), operator 2026-10-02, extended it to the OTHER stop-placing sites (the coverage
reconciler, the sync orphan repair, `update_stop`, the stop-ACK watchdog, the stream's partial-exit
restore, the OCO-cancel handler): tests/test_687_ruling_iii_stop_breach_everywhere.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
from tests.test_646_full_exit_never_returns_naked import STOP_PRICE, _wire

BREACH = Exception('{"code":42210000,"message":"stop price must be less than current price"}')


def _sale_on_second_close(h, *, second_raises=None):
    """First close_position (the planned sale) is rejected; the second (the breach sale) works."""
    calls: list = []

    async def _close(ticker, qty=None, account_mode=None):
        calls.append(qty)
        if len(calls) == 1:
            raise Exception("insufficient qty available")
        if second_raises:
            raise second_raises
        return {"id": "breach-sale-1", "status": "accepted"}

    h["close"].side_effect = _close
    return calls


@pytest.mark.asyncio
async def test_a_failed_1645_sale_whose_restore_is_through_the_price_sells_at_market(monkeypatch):
    h = _wire(monkeypatch, close_raises=True)
    calls = _sale_on_second_close(h)
    h["place"].side_effect = BREACH

    assert await om.execute_full_exit(382, "sma_trail_stop") is False
    assert calls == [None, 2], calls                      # whole position, then the 2 free shares
    rows = [a for a in h["executed"] if "INSERT INTO mi_live_orders" in a[0]]
    assert len(rows) == 1 and rows[0][2] == "breach-sale-1" and rows[0][6] == "sma_trail_stop", rows
    page = h["sent"][-1]
    assert "SOLD AT MARKET" in page and "UNPROTECTED" not in page, h["sent"]
    assert f"${STOP_PRICE:.2f}" in page


@pytest.mark.asyncio
async def test_a_breach_sale_that_also_fails_still_pages_unprotected(monkeypatch):
    h = _wire(monkeypatch, close_raises=True)
    _sale_on_second_close(h, second_raises=Exception("broker down"))
    h["place"].side_effect = BREACH
    await om.execute_full_exit(382, "sma_trail_stop")
    assert "UNPROTECTED" in h["sent"][-1], h["sent"]


@pytest.mark.asyncio
async def test_any_other_restore_failure_keeps_mains_page_and_sells_nothing(monkeypatch):
    h = _wire(monkeypatch, close_raises=True)
    calls = _sale_on_second_close(h)
    h["place"].side_effect = Exception("insufficient qty available")
    await om.execute_full_exit(382, "sma_trail_stop")
    assert calls == [None], calls
    assert "UNPROTECTED" in h["sent"][-1], h["sent"]


@pytest.mark.asyncio
async def test_the_breach_sale_sells_only_the_free_shares_beside_a_resting_third(monkeypatch):
    """The restore's own count: position 6 − the OCO third's 2 = 4. The third keeps its OCO."""
    from tests.test_646_full_exit_never_returns_naked import _oco_parent
    h = _wire(monkeypatch, close_raises=True, remaining=6, position_qty=6,
              open_orders=[_oco_parent(qty=2)])
    calls = _sale_on_second_close(h)
    h["place"].side_effect = BREACH
    await om.execute_full_exit(382, "sma_trail_stop")
    assert calls[-1] == 4, calls


@pytest.mark.asyncio
async def test_a_rejected_auction_sale_whose_restore_is_through_the_price_sells_at_market(monkeypatch):
    from tests.test_depth_exit_rule import _sale_wire
    h = _sale_wire(monkeypatch, opg_raises=Exception("opg rejected"))
    h["place_stop"].side_effect = BREACH
    sold: list = []

    async def _close(ticker, qty=None, account_mode=None):
        sold.append(qty)
        return {"id": "breach-sale-2", "status": "accepted"}

    monkeypatch.setattr(om.alpaca, "close_position", _close)
    assert await om.execute_depth_open_sale(501) is False
    assert sold == [6], sold
    page = h["sent"][-1]
    assert "SOLD AT MARKET" in page and "stays open" not in page, h["sent"]


# ── the stream: a queued closing order died unfilled ─────────────────────────────────────────

def _stream(monkeypatch, *, place_exc, close_exc=None):
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 6,
                   "stop_price": 55.20, "stop_order_id": None},
        position_qty=6.0,
    )
    h["conn"].fetchval = AsyncMock(return_value="sma_trail_stop")
    monkeypatch.setattr(ts.alpaca, "get_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    h["place_stop"].side_effect = place_exc
    close = AsyncMock(side_effect=close_exc,
                      return_value={"id": "breach-sale-3", "status": "accepted"})
    monkeypatch.setattr(om.alpaca, "close_position", close)
    executed: list = []

    class _C:
        async def execute(self, *a, **k):
            executed.append(a)

        async def fetchrow(self, *a, **k):
            return None

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    return ts, h, close, executed, _cancel_data(order_id="sell-1")


@pytest.mark.asyncio
async def test_a_dead_queued_sale_whose_restore_is_through_the_price_sells_at_market(monkeypatch):
    ts, h, close, executed, data = _stream(monkeypatch, place_exc=BREACH)
    await ts._handle_cancel_or_reject(data, "canceled", "live")
    close.assert_awaited_once()
    assert close.await_args.kwargs["qty"] == 6
    assert executed and executed[0][6] == "sma_trail_stop", executed
    assert any("at market now" in m for m in h["sent"]), h["sent"]
    assert not any("STOP RESTORE FAILED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_dead_queued_sale_with_any_other_restore_failure_keeps_mains_page(monkeypatch):
    # not a held-shares refusal ("insufficient qty" is one since 2026-10-10: that refusal is retried
    # in the background - tests/test_687_stream_dead_sale_restore_retry.py)
    ts, h, close, _, data = _stream(monkeypatch, place_exc=Exception("account is restricted"))
    await ts._handle_cancel_or_reject(data, "canceled", "live")
    close.assert_not_awaited()
    assert any("STOP RESTORE FAILED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_breach_sale_that_fails_in_the_stream_still_pages_restore_failed(monkeypatch):
    ts, h, close, _, data = _stream(monkeypatch, place_exc=BREACH,
                                    close_exc=Exception("broker down"))
    await ts._handle_cancel_or_reject(data, "canceled", "live")
    assert any("STOP RESTORE FAILED" in m for m in h["sent"]), h["sent"]


# ── scope: since ruling (iii), operator 2026-10-02, the OTHER stop-placing sites sell too ──────
# (the coverage reconciler, the sync orphan repair, update_stop, the stop-ACK watchdog, the stream's
# partial-exit restore, the OCO-cancel handler) — proved in
# tests/test_687_ruling_iii_stop_breach_everywhere.py.
