"""#687 RULING (ii), operator 2026-10-02 — a PLAIN resting profit-take limit is LEFT RESTING and the
other shares follow the close-below exit (replaces f8d5069e, which skipped the whole sale).

The plain limit is the rare #566 fallback when the profit-take OCO cannot be priced: a sell LIMIT at
the target with no stop of its own. His words: *"treat it as a wash/no-op as if it didn't get hit…
keep original stop and wait for next profit take"* — the same treatment as the +8R OCO third (his
2026-09-29 ruling 3): the sale sells the broker position minus the shares live resting sell orders
hold (other than the trade's own stop, which is cancelled), and NOTHING else is cancelled. When the
resting orders hold every share there is nothing to sell — the existing skip, nothing cancelled.

Pinned at both sale sites that share `_size_sale_beside_resting_orders`: the 16:45 sale
(`execute_full_exit`, today's rule) and the 19:01 opening-auction sale (`execute_depth_open_sale`).
"""
from __future__ import annotations

import pytest

from agents.market_intelligence.broker import order_manager as om
from tests.test_646_full_exit_never_returns_naked import (
    OCO_ROW, _audit_rows, _oco_parent, _stop, _wire,
)

PLAIN_ROW = {"alpaca_order_id": "lim-1", "purpose": "partial_exit", "qty": 2}


def _plain_limit(order_id="lim-1", qty=2):
    return {"id": order_id, "side": "sell", "type": "limit", "qty": qty, "filled_qty": 0,
            "status": "new", "order_class": "simple"}


@pytest.mark.asyncio
async def test_the_1645_sale_leaves_the_plain_limit_resting_and_sells_the_free_shares(monkeypatch):
    """6 sh held: 2 under a plain resting limit, 4 behind the trailing stop. The 4 are sold; the
    only order cancelled is the trade's stop; the limit is never touched."""
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6, available=4,
              pending_orders=[PLAIN_ROW], open_orders=[_stop(), _plain_limit()])
    assert await om.execute_full_exit(382, "sma_trail_stop") is True
    assert [c.args[0] for c in h["cancel"].await_args_list] == ["stop-1"], \
        "only the trade's stop may be cancelled — the plain limit is left resting"
    h["close"].assert_awaited_once()
    assert h["close"].await_args.kwargs.get("qty") == 4
    h["place"].assert_not_awaited()
    assert not [r for r in rows if r[0] == "full_exit_skipped"], rows
    page = next(m for m in h["sent"] if "Closing order placed" in m)
    assert "2 sh stay under the resting profit-take" in page, page
    assert "no stop of its own" in page and "breakeven stop" not in page, (
        "the page must not claim a breakeven stop the plain limit does not have: " + page)


@pytest.mark.asyncio
async def test_nothing_is_sold_or_cancelled_when_the_plain_limit_holds_every_share(monkeypatch):
    """2 sh held, both under the plain limit: nothing free → the existing skip, nothing touched."""
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=2, position_qty=2, available=0,
              pending_orders=[PLAIN_ROW], open_orders=[_plain_limit()])
    assert await om.execute_full_exit(382, "sma_trail_stop") is False
    h["cancel"].assert_not_awaited()
    h["close"].assert_not_awaited()
    h["place"].assert_not_awaited()
    skips = [r for r in rows if r[0] == "full_exit_skipped"]
    assert len(skips) == 1 and '"skip_code": "resting_orders_hold_all_shares"' in skips[0][2], rows
    assert any("plain limit with no stop of its own" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_the_1901_auction_sale_leaves_the_plain_limit_resting(monkeypatch):
    from tests.test_depth_exit_rule import _sale_wire
    h = _sale_wire(monkeypatch, pending_rows=[PLAIN_ROW], position_qty=6,
                   open_orders=[{"id": "stop-1", "side": "sell", "type": "stop", "qty": 4,
                                 "filled_qty": 0, "status": "new", "order_class": "simple"},
                                _plain_limit()])
    assert await om.execute_depth_open_sale(501) is True
    assert [e for e in h["events"] if e[0] == "cancel"] == [("cancel", "stop-1")], h["events"]
    assert [e[1] for e in h["events"] if e[0] == "opg"] == [4], h["events"]
    assert any("no stop of its own" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_the_oco_third_is_unchanged(monkeypatch):
    """Positive control — the 09-29 case: same sale, its page still names the OCO's own stop."""
    _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6, available=4,
              pending_orders=[OCO_ROW], open_orders=[_stop(), _oco_parent()])
    assert await om.execute_full_exit(382, "sma_trail_stop") is True
    assert h["close"].await_args.kwargs.get("qty") == 4
    assert any("(its own target and breakeven stop)." in m for m in h["sent"]), h["sent"]
