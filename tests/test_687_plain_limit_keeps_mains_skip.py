"""#687 cut-back (2026-10-02): a PLAIN resting profit-take limit keeps main's skip.

His 2026-09-29 ruling lets the close-below sale go ahead BESIDE a resting +8R profit-take because
that third is an OCO — it keeps its own target AND breakeven stop. A plain resting sell LIMIT has
no stop of its own; selling around it (or, review fix 9, cancelling it and selling everything) is a
policy nobody ruled. So it keeps main's behaviour — nothing sold, nothing cancelled, the stop stays
— with the skip recorded and paged (as #687 (a) records every skip that remains). Listed for him.
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
async def test_the_1645_sale_beside_a_plain_limit_sells_and_cancels_nothing(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6, available=0,
              pending_orders=[PLAIN_ROW], open_orders=[_stop(), _plain_limit()])
    assert await om.execute_full_exit(382, "sma_trail_stop") is False
    h["cancel"].assert_not_awaited()
    h["close"].assert_not_awaited()
    h["place"].assert_not_awaited()
    skips = [r for r in rows if r[0] == "full_exit_skipped"]
    assert len(skips) == 1 and '"skip_code": "plain_resting_limit"' in skips[0][2], rows
    assert any("plain resting sell limit" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_the_oco_third_still_sells_the_other_two_thirds(monkeypatch):
    """Positive control — the ruled case is unchanged."""
    _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6, available=4,
              pending_orders=[OCO_ROW], open_orders=[_stop(), _oco_parent()])
    assert await om.execute_full_exit(382, "sma_trail_stop") is True
    assert h["close"].await_args.kwargs.get("qty") == 4


@pytest.mark.asyncio
async def test_the_1901_auction_sale_beside_a_plain_limit_sells_nothing(monkeypatch):
    from tests.test_depth_exit_rule import _audited, _sale_wire
    h = _sale_wire(monkeypatch, pending_rows=[PLAIN_ROW],
                   open_orders=[{"id": "stop-1", "side": "sell", "type": "stop", "qty": 4,
                                 "filled_qty": 0, "status": "new", "order_class": "simple"},
                                _plain_limit()])
    assert await om.execute_depth_open_sale(501) is False
    h["cancel"].assert_not_awaited()
    assert not [e for e in h["events"] if e[0] == "opg"]
    assert ("clear_mark",) in h["events"]
    assert _audited(h, "full_exit_skipped")
