"""Breakout v1 PAPER — his ruling 2026-10-29 late ("Friday, and option a"; verbatim: the last entry of
docs/methodology/operator_shared_notes.md): on a +2R touch whose resting limit did NOT fill,
  (i)  on session 3, with the close above the fill, the still-resting +2R limit is CANCELLED (the cancel confirmed; a fill
       in the race IS the third) and the third sold at the close — exactly one third ever, never two;
  (ii) the protective stop stays where it was until a third ACTUALLY sells — placing the +2R limit no longer moves a
       breakout row's stop to breakeven.

The 15:45 job's cancel-and-sell (incl. the race) is pinned in tests/test_breakout_pp_exit.py (`test_1545_*`), and the
daily-bar replay's defined divergence there. THIS file pins the shared code, which changes only behind an explicit
'breakout_pp' / 'breakout_v1' condition:
  * `execute_partial_exit` — a breakout row's stop is never moved at placement (the #548 resting-mode Step 2b, the
    third's OCO sibling stop, the market-mode fold-in); an EP row in the same harness still gets all three (unchanged);
  * `finalize_partial_exit` — when a breakout row's third FILLS (in full) the stop on the rest moves to the fill; an EP
    row, a partly filled order, or a closed row: nothing more happens;
  * `scan_profit_triggers` — once the session-3 step has cancelled a breakout trade's +2R limit, it is never re-placed
    (one third ever); an EP row never reads the marker;
  * the trade stream's cancel handler — a MARKED, UNFILLED breakout cancel is not re-protected (the step sells those
    shares); with any fill, no marker, or an EP order the handler runs unchanged.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.broker import breakout_pp_exit as bpe
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests import test_oco_cancel_handler_566 as cxh
from tests import test_oco_carveout_566 as oco
from tests import test_resting_mode_breakeven_548 as r548
from tests.conftest import make_mock_pool

BREAKOUT = {"exit_rule": "breakout_pp", "signal_type": "breakout_v1"}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# (ii) placement never moves a breakout row's stop — and an EP row's placement is unchanged
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _no_ban(monkeypatch):
    """The +2R placement's under-lock ban read (finding 4) — not marked, so the placement goes on (the harnesses patch
    `om.get_pool`, not the exit module's)."""
    ban = AsyncMock(return_value=False)
    monkeypatch.setattr(bpe, "third_replacement_banned", ban)
    return ban


@pytest.mark.asyncio
async def test_resting_placement_does_not_move_a_breakout_rows_stop(monkeypatch):
    ban = _no_ban(monkeypatch)
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live, trade_overrides=BREAKOUT)
    ok = await r548._run(om, h)
    assert ok is True
    # only the Step-1 quantity reduction AT THE CURRENT STOP; no price-only replace to breakeven
    assert h["calls"] == [("replace", "old_stop_id", r548.NEW_REMAINING, r548.STOP_PRICE)]
    assert not [c for c in h["conn"].execute.call_args_list if "SET stop_price" in c.args[0]]
    events = [e for e, *_ in h["audited"]]
    assert "partial_exit_breakeven_armed" not in events
    assert "breakout_pp_stop_held_at_placement" in events
    held = [d for e, _s, d in h["audited"] if e == "breakout_pp_stop_held_at_placement"]
    assert json.loads(held[0])["stop_price"] == r548.STOP_PRICE
    assert not [c for c in h["set_stop"].call_args_list if c.kwargs.get("reason") == "breakeven_replacement"]
    ban.assert_awaited_once_with(r548.TRADE_ID)                   # the placement re-checked the ban under the lock


@pytest.mark.asyncio
async def test_resting_placement_on_an_ep_row_still_moves_the_stop_to_breakeven(monkeypatch):
    """The EP (magna53) row in the same harness: Step 2b runs exactly as before — the control for the gate above."""
    ban = _no_ban(monkeypatch)
    for st in ("magna53", "smallcap_ep"):
        h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live,
                          trade_overrides={"signal_type": st})
        assert await r548._run(om, h) is True
        assert ("replace", "new_stop_id", None, r548.BREAKEVEN_PRICE) in h["calls"]
        assert [c for c in h["conn"].execute.call_args_list
                if "SET stop_price" in c.args[0] and c.args[1:] == (r548.TRADE_ID, r548.BREAKEVEN_PRICE)]
        events = [e for e, *_ in h["audited"]]
        assert "partial_exit_breakeven_armed" in events and "breakout_pp_stop_held_at_placement" not in events
    ban.assert_not_awaited()                                       # an EP row never reads the breakout ban


@pytest.mark.asyncio
async def test_the_oco_sibling_stop_of_a_breakout_third_sits_at_the_current_stop_not_breakeven(monkeypatch):
    _no_ban(monkeypatch)
    h = oco._harness(om, trade_overrides=dict(BREAKOUT, account_mode="paper"))
    assert await oco._run(om, h) is True
    args = h["oco_sell"].await_args.args
    assert args[2] == pytest.approx(oco.LIMIT_PRICE) and args[3] == pytest.approx(oco.STOP_PRICE)
    # the EP control: max(stop, entry) as before
    h = oco._harness(om)
    assert await oco._run(om, h) is True
    assert h["oco_sell"].await_args.args[3] == pytest.approx(oco.BREAKEVEN_PRICE)


@pytest.mark.asyncio
async def test_a_market_mode_third_on_a_breakout_row_keeps_the_stop_where_it_was():
    """The session-3 third is a market sale; the #548 fold-in would raise the 2/3's stop at Step 1, BEFORE the sale —
    and keep it raised if the sale then aborted. On a breakout row it never runs; on an EP row it still does."""
    for overrides, want_stop in ((BREAKOUT, r548.STOP_PRICE), ({}, r548.BREAKEVEN_PRICE)):
        h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live,
                          trade_overrides=overrides)
        with ExitStack() as stack:
            for p in h["patches"]:
                stack.enter_context(p)
            stack.enter_context(patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=False)))
            ok = await om.execute_partial_exit(r548.TRADE_ID, r548.SHARES, force=True)
        assert ok is True
        assert h["calls"][0] == ("replace", "old_stop_id", r548.NEW_REMAINING, want_stop), overrides


@pytest.mark.asyncio
async def test_the_close_sale_after_a_cancel_adopts_the_unchanged_stop_and_sells(monkeypatch):
    """After the session-3 cancel the 2/3's stop already holds the shares the close sale leaves (qty 40 -> 40) at the
    same price (no fold-in on a breakout row), so the broker answers the Step-1 replace "order parameters are not
    changed": the shared adopt path takes the one live stop and the market sale goes out."""
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live, trade_overrides=BREAKOUT)

    async def _unchanged(order_id, *, qty=None, stop_price=None, limit_price=None, account_mode=None,
                         client_order_id=None):
        h["calls"].append(("replace", order_id, qty, stop_price))
        raise RuntimeError('{"code":42210000,"message":"order parameters are not changed"}')
    live_stop = {"id": "old_stop_id", "symbol": r548.TICKER, "side": "sell", "type": "stop", "status": "accepted",
                 "qty": float(r548.NEW_REMAINING), "stop_price": r548.STOP_PRICE}
    market = AsyncMock(return_value={"id": "market_sell_id", "status": "new"})
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        stack.enter_context(patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=False)))
        stack.enter_context(patch.object(om.alpaca, "replace_order", _unchanged))
        stack.enter_context(patch.object(om.alpaca, "get_open_orders", AsyncMock(return_value=[live_stop])))
        stack.enter_context(patch.object(om.alpaca, "place_market_sell", market))
        ok = await om.execute_partial_exit(r548.TRADE_ID, r548.SHARES, force=True)
    assert ok is True
    assert h["calls"] == [("replace", "old_stop_id", r548.NEW_REMAINING, r548.STOP_PRICE)]
    market.assert_awaited_once()
    assert market.await_args.args[:2] == (r548.TICKER, r548.SHARES)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# the stop moves to the fill when a third ACTUALLY sells
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _fin_row(**over):
    r = {"id": 701, "ticker": "BRK", "account_mode": "paper", "remaining_shares": 9, "status": "filled", "exits": [],
         "entry_price": 10.30, "stop_price": 10.10, "stop_order_id": "stop-2", "entry_attempt": 1,
         "exit_rule": "breakout_pp", "signal_type": "breakout_v1"}
    r.update(over)
    return r


def _wire_fin(monkeypatch, row, *, order_qty=3.0, order_status="filled"):
    pool, conn = make_mock_pool()
    order_row = {"qty": order_qty, "status": order_status} if order_qty is not None else None

    async def _fetchrow(sql, *a):
        return row if "FROM mi_live_trades" in sql else order_row
    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.fetchval = AsyncMock(return_value=order_qty)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "_trade_advisory_lock", lambda tid: r548._noop_lock()(tid))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock())
    upd = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "update_stop", upd)
    return conn, audited, upd


def test_a_breakout_third_that_fills_moves_the_stop_on_the_rest_to_the_fill(monkeypatch):
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row())
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_awaited_once_with(701, 10.30, stop_source="breakeven")
    assert any(e == "breakout_pp_stop_to_fill_after_third" for e, *_ in audited)


def test_an_ep_third_that_fills_takes_no_extra_step(monkeypatch):
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(exit_rule=None, signal_type="magna53"))
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_not_awaited()
    assert conn.fetchrow.await_count == 1 and conn.fetchval.await_count == 0     # not one extra read on an EP row
    assert all("FROM mi_live_trades" in c.args[0] for c in conn.fetchrow.await_args_list)
    assert not [e for e, *_ in audited if e.startswith("breakout_pp")]


def test_a_partly_filled_third_or_a_closing_fill_or_a_stop_already_at_cost_moves_nothing(monkeypatch):
    # a partly filled order (the cancel path): left to the stream's re-protect, the 16:45 job lifts it
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(), order_qty=3.0)
    asyncio.run(om.finalize_partial_exit(701, 1, 10.70, "lim-9"))
    upd.assert_not_awaited()
    assert any(e == "breakout_pp_stop_to_fill_deferred" for e, *_ in audited)
    # the fill that empties the row closes it: nothing left to protect
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(remaining_shares=3))
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_not_awaited()
    # a stop already at the fill
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(stop_price=10.30))
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_not_awaited()
    # a duplicate fill event (idempotent): no second move
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(exits=[{"order_id": "lim-9"}]))
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_not_awaited()


def test_a_failed_stop_move_after_the_third_never_raises_into_the_fill_handler(monkeypatch):
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row())
    upd.side_effect = RuntimeError("broker down")
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    assert any(e == "breakout_pp_stop_to_fill_failed" for e, *_ in audited)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# (i) one third ever: the +2R poll never re-places a limit the session-3 step cancelled
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _poll_row(**over):
    r = {"id": 701, "ticker": "BRK", "entry_price": 10.30, "hard_stop": 10.10, "stop_price": 10.10, "orb_low": None,
         "signal_type": "breakout_v1", "remaining_shares": 9, "partial_taken": False,
         "filled_at": datetime(2026, 10, 26, 13, 37), "account_mode": "paper"}
    r.update(over)
    return r


def _wire_poll(monkeypatch, row, *, marked):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[row])
    conn.fetchval = AsyncMock(return_value=11.0)          # the high since the fill: past +2R
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "_load_strategy_exit_overrides", AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.constants.PROFIT_TRIGGER_R", 2.0)
    monkeypatch.setattr(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "_profit_trigger_already_announced", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    epe = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "execute_partial_exit", epe)
    mark = AsyncMock(return_value=marked)
    monkeypatch.setattr(bpe, "third_replacement_banned", mark)          # the poll's fail-CLOSED read (finding 4)
    monkeypatch.setattr(bpe, "planned_third_cancel_marked", AsyncMock(side_effect=AssertionError("the stream's reader")))

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, 15, 45, tzinfo=tz)
    monkeypatch.setattr(om, "datetime", _Now)
    return epe, mark


def test_the_poll_never_re_places_the_2r_limit_on_a_breakout_trade_whose_limit_was_cancelled(monkeypatch):
    epe, mark = _wire_poll(monkeypatch, _poll_row(), marked=True)
    out = asyncio.run(om.scan_profit_triggers())
    epe.assert_not_awaited()
    mark.assert_awaited_once_with(701)
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancelled_no_replace"}]
    epe, mark = _wire_poll(monkeypatch, _poll_row(), marked=False)            # no cancel yet: the +2R third as before
    asyncio.run(om.scan_profit_triggers())
    epe.assert_awaited_once()
    assert epe.await_args.kwargs["limit_price"] == pytest.approx(10.70)


def test_the_poll_never_reads_the_breakout_marker_for_an_ep_row(monkeypatch):
    """An EP row that reaches its sale (so the check is not vacuous): the marker is never read, the +2R third goes out
    exactly as before — even with a marker 'present'."""
    epe, mark = _wire_poll(monkeypatch, _poll_row(signal_type="magna53", orb_low=10.20), marked=True)
    asyncio.run(om.scan_profit_triggers())
    mark.assert_not_awaited()
    epe.assert_awaited_once()
    assert epe.await_args.args == (701, 3) and epe.await_args.kwargs["limit_price"] == pytest.approx(10.50)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# the trade stream: a marked, unfilled breakout cancel is not re-protected
# ═══════════════════════════════════════════════════════════════════════════════════════════════
BREAKOUT_OCO_RAW = json.dumps({
    "id": "lim-9", "order_class": "oco", "type": "limit", "side": "sell", "qty": 3.0,
    "client_order_id": "apollo_paper_breakout_v1_BRK_1761750000000",
    "legs": [{"id": "leg-9", "type": "stop", "status": "held", "qty": 3.0, "stop_price": 10.10}]})


def _stream(monkeypatch, *, raw, filled_qty=0.0, marked=True):
    h = cxh._wire(monkeypatch, pending_exit_row=cxh._pending(raw=raw, trade_id=701),
                  trade_row={"id": 701, "ticker": "BRK", "stop_price": 10.10, "signal_type": "breakout_v1"},
                  leg_order={"id": "leg-9", "status": "canceled"}, position_qty=9.0)
    mark = AsyncMock(return_value=marked)
    monkeypatch.setattr(bpe, "planned_third_cancel_marked", mark)
    data = cxh._cancel_data(order_id="lim-9", filled_qty=filled_qty, avg=(10.70 if filled_qty else None))
    asyncio.run(ts._handle_cancel_or_reject(data, "canceled", "paper"))
    return h, mark


def test_the_stream_leaves_a_marked_unfilled_breakout_cancel_to_the_session3_step(monkeypatch):
    h, mark = _stream(monkeypatch, raw=BREAKOUT_OCO_RAW)
    mark.assert_awaited_once_with(701, "lim-9")
    h["ensure_cov"].assert_not_awaited()
    h["place_stop"].assert_not_awaited()
    h["cancel"].assert_not_awaited()
    assert [e for e, *_ in h["audited"]] == ["breakout_pp_planned_third_cancel_seen"]


def test_the_stream_still_re_protects_a_breakout_cancel_with_no_marker_or_with_a_fill(monkeypatch):
    h, _m = _stream(monkeypatch, raw=BREAKOUT_OCO_RAW, marked=False)            # not ours: the third is uncovered
    h["ensure_cov"].assert_awaited_once()
    h, mark = _stream(monkeypatch, raw=BREAKOUT_OCO_RAW, filled_qty=1.0)          # a fill in the race: the stream
    mark.assert_not_awaited()                                                   # books it and covers the rest
    h["finalize"].assert_awaited_once_with(701, 1, 10.70, "lim-9")
    h["ensure_cov"].assert_awaited_once()


def test_the_stream_never_reads_the_breakout_marker_for_an_ep_order(monkeypatch):
    h, mark = _stream(monkeypatch, raw=cxh.OCO_PARENT_RAW)
    mark.assert_not_awaited()
    h["ensure_cov"].assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# the marker itself
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_marker_names_the_trade_and_the_order_and_a_failed_read_is_not_marked(monkeypatch):
    rows = [{"event_type": bpe.PLANNED_THIRD_CANCEL, "detail": json.dumps({"trade_id": 701, "order_id": "lim-9"})},
            {"event_type": bpe.PLANNED_THIRD_CANCEL, "detail": "not json"}]
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool, _c = make_mock_pool()
    pool.acquire.return_value.__aenter__.return_value = conn
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-9")) is True
    assert asyncio.run(bpe.planned_third_cancel_marked(701)) is True
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-8")) is False
    assert asyncio.run(bpe.planned_third_cancel_marked(702)) is False
    assert sorted(conn.fetch.await_args.args[1]) == sorted([bpe.PLANNED_THIRD_CANCEL,
                                                           bpe.PLANNED_THIRD_CANCEL_WITHDRAWN])
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-9")) is False


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# pre-merge 2026-10-31 — finding 5: a third reported through partial-fill events sizes the stop on the whole rest
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_third_filled_in_full_through_partial_fill_events_is_marked_filled_before_the_stop_is_sized(monkeypatch):
    """The stream's terminal partial-fill path leaves the order row 'partially_filled' (cum_filled == qty), which
    `get_pending_exit_qty` still counts as a pending exit — `update_stop` would then size the stop as remaining MINUS
    the third again. The row is set 'filled' (compare-and-set) BEFORE the move; the move still happens."""
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(), order_qty=3.0, order_status="partially_filled")
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    cas = [c for c in conn.execute.await_args_list if "UPDATE mi_live_orders SET status = 'filled'" in c.args[0]]
    assert len(cas) == 1 and cas[0].args[1] == "lim-9" and "status = 'partially_filled'" in cas[0].args[0]
    upd.assert_awaited_once_with(701, 10.30, stop_source="breakeven")
    events = [e for e, *_ in audited]
    assert events.index("breakout_pp_third_row_marked_filled") < events.index("breakout_pp_stop_to_fill_after_third")
    # a REAL partial (cum < qty) still defers, and the row is not touched
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(), order_qty=3.0, order_status="partially_filled")
    asyncio.run(om.finalize_partial_exit(701, 2, 10.70, "lim-9"))
    upd.assert_not_awaited()
    assert not [c for c in conn.execute.await_args_list if "mi_live_orders" in c.args[0]]
    assert any(e == "breakout_pp_stop_to_fill_deferred" for e, *_ in audited)
    # a row already 'filled': no CAS, the move as before
    conn, audited, upd = _wire_fin(monkeypatch, _fin_row(), order_qty=3.0, order_status="filled")
    asyncio.run(om.finalize_partial_exit(701, 3, 10.70, "lim-9"))
    upd.assert_awaited_once()
    assert not [c for c in conn.execute.await_args_list if "mi_live_orders" in c.args[0]]


def test_the_locked_finalizer_is_annotated_to_return_the_stop_to_fill_flag():
    """Finding 7: '-> None' hid the flag the caller depends on; a reader or type checker dropping the return would
    silently disable the stop move after a third."""
    import inspect
    assert inspect.signature(om._finalize_partial_exit_locked).return_annotation == "str | None"
    assert om._BREAKOUT_PP_STOP_TO_FILL == "breakout_pp_stop_to_fill"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# pre-merge 2026-10-31 — finding 4: one third ever, re-checked UNDER THE LOCK (the race with the session-3 sale)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_a_breakout_placement_is_refused_under_the_lock_once_the_session3_step_marked_its_cancel(monkeypatch):
    """The poll read the marker as absent, the 15:45 step wrote it (and sold at the close) before the poll's
    execute_partial_exit took the lock: the ban is re-read under the lock and the +2R limit is NOT placed — no stop
    touched, no order sent, one audit row."""
    ban = AsyncMock(return_value=True)
    monkeypatch.setattr(bpe, "third_replacement_banned", ban)
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live, trade_overrides=BREAKOUT)
    assert await r548._run(om, h) is False
    assert h["calls"] == []
    ban.assert_awaited_once_with(r548.TRADE_ID)
    refused = [d for e, _s, d in h["audited"] if e == "breakout_pp_partial_refused_under_lock"]
    assert len(refused) == 1 and "planned cancel" in json.loads(refused[0])["reason"]


@pytest.mark.asyncio
async def test_a_breakout_partial_is_refused_under_the_lock_once_a_third_has_sold(monkeypatch):
    """`partial_taken` flipped between the caller's read and the lock (the session-3 market sale filled, or the +2R
    limit did): no second third, on either path (a placement or a market sale)."""
    ban = AsyncMock(return_value=False)
    monkeypatch.setattr(bpe, "third_replacement_banned", ban)
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live,
                      trade_overrides=dict(BREAKOUT, partial_taken=True))
    assert await r548._run(om, h) is False
    assert h["calls"] == [] and not ban.await_count
    assert [e for e, *_ in h["audited"] if e == "breakout_pp_partial_refused_under_lock"] == [
        "breakout_pp_partial_refused_under_lock"]
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live,
                      trade_overrides=dict(BREAKOUT, partial_taken=True))        # the market-mode sale, same answer
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        stack.enter_context(patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=False)))
        assert await om.execute_partial_exit(r548.TRADE_ID, r548.SHARES, force=True) is False
    assert h["calls"] == [] and not ban.await_count
    assert [e for e, *_ in h["audited"] if e == "breakout_pp_partial_refused_under_lock"] == [
        "breakout_pp_partial_refused_under_lock"]


@pytest.mark.asyncio
async def test_the_session3_market_sale_runs_past_its_own_marker_and_an_ep_row_never_reads_it(monkeypatch):
    """The 15:45 step writes the marker and THEN sells the third at market (no limit_price): the ban must not refuse
    the step's own sale. An EP row never reads the ban at all."""
    ban = AsyncMock(return_value=True)
    monkeypatch.setattr(bpe, "third_replacement_banned", ban)
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live, trade_overrides=BREAKOUT)
    with ExitStack() as stack:
        for p in h["patches"]:
            stack.enter_context(p)
        stack.enter_context(patch.object(om, "_profit_take_resting_limit_enabled", AsyncMock(return_value=False)))
        assert await om.execute_partial_exit(r548.TRADE_ID, r548.SHARES, force=True) is True
    assert h["calls"][0] == ("replace", "old_stop_id", r548.NEW_REMAINING, r548.STOP_PRICE)
    ban.assert_not_awaited()
    h = r548._harness(om, be_result="be_stop_id", get_order_fake=r548._get_order_all_live,
                      trade_overrides={"signal_type": "magna53"})
    assert await r548._run(om, h) is True
    ban.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# pre-merge 2026-10-31 — findings 1 + 2: a withdrawn marker hands a LATE settle back to the stream's re-protect
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _marker_log(monkeypatch, rows):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool, _c = make_mock_pool()
    pool.acquire.return_value.__aenter__.return_value = conn
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=pool))


def test_the_stream_re_protects_a_late_settle_once_the_step_withdrew_its_marker_and_never_doubles_a_stop(monkeypatch):
    """The step's cancel was unconfirmed at 15:45 (marker withdrawn, cover converged from broker truth); the cancel
    settles minutes later and its event reaches the stream. The real reader sees the withdrawal (newer than the
    marker): NOT planned -> the OCO-parent path -> the sibling leg is dead -> `_ensure_stop_coverage` from broker
    truth (idempotent: after the step's own re-protect it reads the target met and places nothing). No bare
    place_stop_order on top of anything, ever."""
    marker = {"event_type": bpe.PLANNED_THIRD_CANCEL, "detail": json.dumps({"trade_id": 701, "order_id": "lim-9"})}
    withdrawn = {"event_type": bpe.PLANNED_THIRD_CANCEL_WITHDRAWN,
                 "detail": json.dumps({"trade_id": 701, "order_id": "lim-9"})}
    h = cxh._wire(monkeypatch, pending_exit_row=cxh._pending(raw=BREAKOUT_OCO_RAW, trade_id=701),
                  trade_row={"id": 701, "ticker": "BRK", "stop_price": 10.10, "signal_type": "breakout_v1"},
                  leg_order={"id": "leg-9", "status": "canceled"}, position_qty=9.0)
    _marker_log(monkeypatch, [withdrawn, marker])                                 # newest first
    asyncio.run(ts._handle_cancel_or_reject(cxh._cancel_data(order_id="lim-9"), "canceled", "paper"))
    h["ensure_cov"].assert_awaited_once_with(701, "ETON", 9.0, 10.10, "breakout_v1", "paper")
    h["place_stop"].assert_not_awaited()
    h["cancel"].assert_not_awaited()
    assert [e for e, *_ in h["audited"]] == ["oco_parent_cancelled_unfilled"]
    # the marker alone (the step IS selling): left alone, exactly as before
    h = cxh._wire(monkeypatch, pending_exit_row=cxh._pending(raw=BREAKOUT_OCO_RAW, trade_id=701),
                  trade_row={"id": 701, "ticker": "BRK", "stop_price": 10.10, "signal_type": "breakout_v1"},
                  leg_order={"id": "leg-9", "status": "canceled"}, position_qty=9.0)
    _marker_log(monkeypatch, [marker])
    asyncio.run(ts._handle_cancel_or_reject(cxh._cancel_data(order_id="lim-9"), "canceled", "paper"))
    h["ensure_cov"].assert_not_awaited()
    assert [e for e, *_ in h["audited"]] == ["breakout_pp_planned_third_cancel_seen"]


@pytest.mark.asyncio
async def test_the_coverage_repair_places_nothing_when_the_live_stop_already_meets_the_target(monkeypatch):
    """The idempotency the late-settle path rests on, on the real `_ensure_stop_coverage_outcome`: the step already
    widened the 2/3's stop to the whole position; the stream's later pass reads it covered and sends NO order."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lock(_tid):
        yield True
    monkeypatch.setattr(om, "_trade_advisory_try_lock", _lock)
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    live_stop = {"id": "stop-9", "symbol": "BRK", "side": "sell", "type": "stop", "status": "accepted", "qty": 9.0,
                 "stop_price": 10.10, "order_class": "simple"}
    monkeypatch.setattr(om.alpaca, "get_open_orders", AsyncMock(return_value=[live_stop]))
    place = AsyncMock()
    replace = AsyncMock()
    monkeypatch.setattr(om.alpaca, "place_stop_order", place)
    monkeypatch.setattr(om.alpaca, "replace_order", replace)
    out = await om._ensure_stop_coverage_outcome(701, "BRK", 9.0, 10.10, "breakout_v1", "paper")
    assert out.status == om.COVERAGE_COVERED and out.message is None
    place.assert_not_awaited()
    replace.assert_not_awaited()
