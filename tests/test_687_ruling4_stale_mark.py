"""#687 ruling (4), operator 2026-10-01 ("Yes"): a stale "sell at the next open" mark is CLEARED,
PAGED, and the NEXT CLOSE DECIDES (depth path, toggle OFF — nothing stamped today).

Built in part B (5da040ca) as a design default; the ruling makes it his. The 19:01 half (a mark
from an earlier ET session: nothing cancelled or sold, mark cleared, `depth_sale_mark_stale` audit,
page) is pinned by tests/test_depth_exit_rule.py::test_a_mark_from_an_earlier_session_is_never_sold_on.
These pin the other half — "the next close decides": the 16:45 job re-decides on today's true close
whatever a stale mark says.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from tests.test_depth_exit_rule import (
    DEPTH_STOP, TODAY, _audited, _install_1645, _row, _sale_wire, _step,
)

YESTERDAY = TODAY - timedelta(days=1)


@pytest.mark.asyncio
async def test_a_close_below_the_line_re_marks_a_stale_row_for_today(monkeypatch):
    conn, calls = _install_1645(
        monkeypatch, _row("depth", depth_sell_pending_on=YESTERDAY), _step("sma_stopped", 70.40, 69.10))
    await lt.update_open_positions_live()
    marks = [a for a in conn.executed if "depth_sell_pending_on" in a[0]]
    assert len(marks) == 1 and marks[0][4] == TODAY, marks
    calls["execute_full_exit"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_close_back_above_the_line_never_acts_on_the_stale_mark(monkeypatch):
    conn, calls = _install_1645(
        monkeypatch, _row("depth", depth_sell_pending_on=YESTERDAY), _step("updated", 70.40, 72.00))
    await lt.update_open_positions_live()
    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]], conn.executed
    calls["execute_full_exit"].assert_not_awaited()


@pytest.mark.asyncio
async def test_the_1901_run_on_a_stale_mark_clears_pages_and_sells_nothing(monkeypatch):
    h = _sale_wire(monkeypatch, row=_row("depth", remaining_shares=6, stop_price=DEPTH_STOP,
                                         status="filled", signal_type="magna53",
                                         depth_sell_pending_on=YESTERDAY))
    assert await om.execute_depth_open_sale(501) is False
    h["cancel"].assert_not_awaited()
    h["orders"].assert_not_awaited()
    assert ("clear_mark",) in h["events"]
    assert _audited(h, "depth_sale_mark_stale")
    assert any("the next close decides" in m for m in h["sent"]), h["sent"]
