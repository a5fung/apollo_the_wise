"""#600 — a re-protect can no longer re-arm a stop BELOW the last level the broker held.

THE DEFECT. `_ensure_stop_coverage`'s place branch (and its siblings: the sync
orphan remediation, the two WS cancel-restore paths in trade_stream, and
`update_stop`'s terminal-old-stop carve-out) placed at `mi_live_trades.stop_price`
with no reference to the broker. That column is DELIBERATELY allowed to sit low:
execute_partial_exit's breakeven replace keeps the successor stop POINTER while
WITHHOLDING stop_price when the outcome was unconfirmed (the DB understating
protection is the safe direction — pinned in test_resting_mode_breakeven_548.py),
and the market-mode fold-in never writes it at all. So when that breakeven stop
later died, the repair re-armed the position ~1R below where it had been — every
5 minutes since #596 gave the repair a retry cadence.

WHY NOT `update_stop`'s floor. That floor (2026-08-10) compares a requested move
against the LIVE broker stop and REFUSES a non-raise. A re-protect is placing
precisely because there is NO live stop, so routing through it would apply no
floor at all (its terminal/NULL carve-out), size from DB remaining_shares instead
of broker qty (the 109-vs-28 incident), and cancel the pointer first. Wrong tool.

THE FIX. One pure helper, `_floor_reprotect_price(base, broker_order)`: the price
to place is `base` raised to the pointer's broker `stop_price` when that order is
readable and was ever accepted (`rejected` never rested — ignored). It NEVER
refuses: no pointer, unreadable order, no stop_price, a raising DB read → `base`,
and the placement goes ahead. An unprotected position is strictly worse than a
stop that is ~1R low — that fail direction is the single most important thing
here and every no-truth path is pinned below.

BOTH DIRECTIONS are proven at every site: a stale-low DB price is placed at the
broker's level, AND a legitimate placement with nothing to compare against still
happens at the DB price.
"""
from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool
from tests.test_never_naked_invariant import _patches as _cov_patches, _run as _cov_run
from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending, _wire
from tests.test_stop_reason_560 import _make_ws_pool
from tests.test_sync_orphan_soak_emitters import _make_db_trade, _run_sync
from tests.test_update_stop_raise_only_floor import (
    DB_STOP, OLD_STOP_ID, _harness as _us_harness, _run as _us_run,
    _stop_price_updates, _trade as _us_trade,
)

DB_PRICE = 15.00        # what mi_live_trades.stop_price says (stale — breakeven withheld)
BROKER_PRICE = 15.30    # what the broker's stop (now dead) actually rested at
POINTER = "be_successor_stop"
FLOOR_EVENT = "stop_reprotect_floor_applied"


def _order(status="canceled", stop_price=BROKER_PRICE, order_id=POINTER, **extra):
    d = {"id": order_id, "status": status, "stop_price": stop_price,
         "side": "sell", "type": "stop", "qty": 60, "filled_qty": 0}
    d.update(extra)
    return d


def _floor_rows(audited):
    """audited entries may be (evt, summary, detail) tuples or bare evt strings."""
    out = []
    for row in audited:
        evt = row[0] if isinstance(row, tuple) else row
        if evt == FLOOR_EVENT:
            out.append(row)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 1. The pure helper — every branch, in isolation
# ══════════════════════════════════════════════════════════════════════════════


def test_pure_floor_raises_to_a_higher_broker_price():
    price, info = om._floor_reprotect_price(DB_PRICE, _order())
    assert price == BROKER_PRICE
    assert info["raised"] is True
    assert info["floor_source"] == "broker_pointer"
    assert info["broker_stop_price"] == BROKER_PRICE
    assert info["broker_status"] == "canceled"


@pytest.mark.parametrize("status", [
    "canceled", "cancelled", "expired", "replaced", "done_for_day", "filled",
    "partially_filled", "new", "accepted", "held", "OrderStatus.CANCELED",
])
def test_pure_floor_honours_every_status_the_broker_ever_accepted(status):
    """A cancelled/expired/replaced/filled stop's price WAS protection; a live
    one still is. All of them floor."""
    price, info = om._floor_reprotect_price(DB_PRICE, _order(status=status))
    assert price == BROKER_PRICE and info["raised"] is True


def test_pure_floor_ignores_a_rejected_order():
    """`rejected` never rested at the broker — its price was never protection.
    Flooring to it would re-submit a price the broker already refused."""
    price, info = om._floor_reprotect_price(DB_PRICE, _order(status="rejected"))
    assert price == DB_PRICE and info["raised"] is False
    assert info["floor_source"] == "ignored_status:rejected"


@pytest.mark.parametrize("order, source", [
    (None, "no_broker_order"),
    ({}, "no_broker_order"),
    (_order(stop_price=None), "no_stop_price"),
    (_order(stop_price="not-a-number"), "unparseable_stop_price"),
], ids=["none", "empty", "no_price", "unparseable"])
def test_pure_floor_with_no_broker_truth_returns_base_unchanged(order, source):
    price, info = om._floor_reprotect_price(DB_PRICE, order)
    assert price == DB_PRICE and info["raised"] is False
    assert info["floor_source"] == source


@pytest.mark.parametrize("broker", [DB_PRICE, DB_PRICE - 0.50, DB_PRICE + 1e-12],
                         ids=["equal", "lower", "within_epsilon"])
def test_pure_floor_never_lowers_and_treats_equal_as_no_op(broker):
    price, info = om._floor_reprotect_price(DB_PRICE, _order(stop_price=broker))
    assert price == DB_PRICE and info["raised"] is False
    assert info["floor_source"] == "base_not_below_broker"


@pytest.mark.parametrize("base", [1.0, 15.0, 15.29, 15.30, 15.31, 400.0])
@pytest.mark.parametrize("broker", [None, 0.5, 15.0, 15.30, 999.0, "x"])
@pytest.mark.parametrize("status", ["canceled", "rejected", "new", None])
def test_pure_floor_output_is_never_below_base(base, broker, status):
    """The one invariant the whole fix rests on: the helper only ever RAISES."""
    price, _ = om._floor_reprotect_price(base, _order(status=status, stop_price=broker))
    assert price >= base


# ══════════════════════════════════════════════════════════════════════════════
# 2. The async wrapper — broker read, fail-open, audit only when it raised
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_apply_floor_reads_the_pointer_and_audits_when_it_raises():
    audited = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    with patch.object(om.alpaca, "get_order", AsyncMock(return_value=_order())) as g, \
         patch.object(om, "log_audit_event", _audit):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, POINTER, "live", site="unit")

    assert price == BROKER_PRICE
    g.assert_awaited_once_with(POINTER, account_mode="live")
    rows = _floor_rows(audited)
    assert len(rows) == 1
    d = json.loads(rows[0][2])
    assert d["db_price"] == DB_PRICE and d["placed_price"] == BROKER_PRICE
    assert d["broker_order_id"] == POINTER and d["site"] == "unit"
    assert d["trade_id"] == 7 and d["account_mode"] == "live"


@pytest.mark.asyncio
async def test_apply_floor_with_no_pointer_skips_the_broker_read_and_is_quiet():
    audited = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    with patch.object(om.alpaca, "get_order", AsyncMock()) as g, \
         patch.object(om, "log_audit_event", _audit):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit")

    assert price == DB_PRICE
    g.assert_not_awaited()
    assert not _floor_rows(audited)


@pytest.mark.asyncio
@pytest.mark.parametrize("read", [
    AsyncMock(return_value=None),
    AsyncMock(side_effect=RuntimeError("alpaca 500")),
], ids=["get_order_none", "get_order_raises"])
async def test_apply_floor_fail_open_on_an_unreadable_broker(read):
    """FAIL DIRECTION: no broker truth → the DB price, and NO refusal. This is
    the opposite of update_stop's live-stop floor (which refuses on unreadable),
    and deliberately so — there is no live stop here to leave in place."""
    with patch.object(om.alpaca, "get_order", read), \
         patch.object(om, "log_audit_event", AsyncMock()):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, POINTER, "live", site="unit")
    assert price == DB_PRICE


@pytest.mark.asyncio
async def test_apply_floor_fetch_false_uses_the_order_it_was_handed():
    """The sync orphan loop and update_stop already hold the dead order — no
    second broker call."""
    with patch.object(om.alpaca, "get_order", AsyncMock()) as g, \
         patch.object(om, "log_audit_event", AsyncMock()):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, POINTER, "live", site="unit",
            broker_order=_order(), fetch=False)
    assert price == BROKER_PRICE
    g.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_stop_pointer_fails_open_to_none_when_the_db_read_raises():
    with patch.object(om, "get_pool", AsyncMock(side_effect=RuntimeError("no pool"))):
        assert await om._current_stop_pointer(7) is None


@pytest.mark.asyncio
async def test_current_stop_pointer_reads_the_row():
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=POINTER)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._current_stop_pointer(7) == POINTER
    assert conn.fetchval.await_args.args[1] == 7


# ══════════════════════════════════════════════════════════════════════════════
# 3. THE TICKET — _ensure_stop_coverage's place branch (retry cadence: every 5 min)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_place_branch_stale_low_db_price_is_placed_at_the_broker_level():
    """THE #600 defect. Broker has NO live stop (the breakeven successor died),
    DB says $15.00 (stale — the #548 uncertain branch withheld $15.30), the
    pointer still names that dead successor. Pre-fix: re-armed at $15.00, ~1R
    below where the position had been. Now: $15.30, with a durable audit row."""
    h = _cov_patches([], pending_qty=0, stop_pointer=POINTER,
                     get_order=AsyncMock(return_value=_order()))
    result = await _cov_run(h, broker_qty=60, stop_price=DB_PRICE, account_mode="live")

    h["place"].assert_called_once()
    assert h["place"].call_args.args[2] == BROKER_PRICE, h["place"].call_args
    assert h["set_stop"].called
    assert FLOOR_EVENT in h["audited"]
    repaired = [d for e, _, d in h["audit_details"] if e == "stop_coverage_repaired"][0]
    assert repaired["stop_price"] == BROKER_PRICE
    assert repaired["db_stop_price"] == DB_PRICE
    assert result is not None and "15.30" in result and "15.00" not in result


@pytest.mark.asyncio
async def test_place_branch_with_no_pointer_still_places_at_the_db_price():
    """The other direction: NULL pointer (post-remediation naked shape). There is
    nothing to floor against — the stop MUST still be placed, at the DB price,
    with no broker read and no floor audit. A floor that refused here would turn
    a bounded ~1R defect into an unprotected position."""
    get_order = AsyncMock(return_value=_order())
    h = _cov_patches([], pending_qty=0, stop_pointer=None, get_order=get_order)
    result = await _cov_run(h, broker_qty=60, stop_price=DB_PRICE)

    h["place"].assert_called_once()
    assert h["place"].call_args.args[2] == DB_PRICE
    get_order.assert_not_awaited()
    assert FLOOR_EVENT not in h["audited"]
    assert "stop_coverage_repaired" in h["audited"]
    assert result is not None and "15.00" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("get_order", [
    AsyncMock(return_value=None),
    AsyncMock(side_effect=RuntimeError("alpaca 500")),
    AsyncMock(return_value=_order(stop_price=None)),
    AsyncMock(return_value=_order(status="rejected")),
], ids=["unreadable_none", "unreadable_raises", "no_price", "rejected_pointer"])
async def test_place_branch_with_no_usable_broker_truth_still_places_at_the_db_price(get_order):
    """Pointer set but the broker gives nothing usable → DB price, placement
    happens. Never a refusal."""
    h = _cov_patches([], pending_qty=0, stop_pointer=POINTER, get_order=get_order)
    await _cov_run(h, broker_qty=60, stop_price=DB_PRICE)
    h["place"].assert_called_once()
    assert h["place"].call_args.args[2] == DB_PRICE
    assert FLOOR_EVENT not in h["audited"]
    assert "stop_coverage_repaired" in h["audited"]


@pytest.mark.asyncio
async def test_place_branch_db_price_already_at_or_above_broker_is_unchanged():
    h = _cov_patches([], pending_qty=0, stop_pointer=POINTER,
                     get_order=AsyncMock(return_value=_order(stop_price=DB_PRICE)))
    await _cov_run(h, broker_qty=60, stop_price=DB_PRICE)
    assert h["place"].call_args.args[2] == DB_PRICE
    assert FLOOR_EVENT not in h["audited"]


@pytest.mark.asyncio
async def test_place_branch_floored_price_that_breaches_converges_exactly_as_before():
    """The one observable consequence of the floor: if the market has ALREADY
    traded through the last broker level, the floored placement breaches. That
    must behave exactly like a breach at an accurate DB price always has —
    ONE attempt, `stop_coverage_breach` (with both prices), no stop_order_id
    write, no retry loop (the retry state machine ends on a breach)."""
    place = AsyncMock(side_effect=Exception(
        '{"code":42210000,"message":"stop price must be less than current price"}'))
    h = _cov_patches([], pending_qty=0, stop_pointer=POINTER, place=place,
                     get_order=AsyncMock(return_value=_order()))
    result = await _cov_run(h, broker_qty=60, stop_price=DB_PRICE)

    assert place.call_count == 1
    assert place.call_args.args[2] == BROKER_PRICE
    assert "stop_coverage_breach" in h["audited"]
    breach = [d for e, _, d in h["audit_details"] if e == "stop_coverage_breach"][0]
    assert breach["intended_stop_price"] == BROKER_PRICE
    assert breach["db_stop_price"] == DB_PRICE
    h["set_stop"].assert_not_called()
    assert result is not None and "ABOVE market" in result and "15.30" in result


@pytest.mark.asyncio
async def test_place_branch_no_db_price_still_flags_before_any_floor_read():
    """The pre-existing no-anchor guard runs first — no pointer read, no place."""
    get_order = AsyncMock(return_value=_order())
    h = _cov_patches([], pending_qty=0, stop_pointer=POINTER, get_order=get_order)
    result = await _cov_run(h, broker_qty=60, stop_price=None)
    h["place"].assert_not_called()
    get_order.assert_not_awaited()
    assert "stop_coverage_no_price" in h["audited"]
    assert result is not None and "manual intervention" in result


# ══════════════════════════════════════════════════════════════════════════════
# 4. Sibling: sync_positions orphan remediation (16:05 / 21:00 — the ticket's
#    "once at 16:05" exposure lives HERE, not in the coverage branch)
# ══════════════════════════════════════════════════════════════════════════════


def _sync_patches(db_trades, place_stop, audit_calls, *, get_order):
    p1, p2, p3, p4 = _run_sync(db_trades, [{"symbol": "FIGS", "qty": 60}], audit_calls, place_stop)
    p5 = patch(f"{om.__name__}.alpaca.get_order", new=get_order)
    return [p1, p2, p3, p4, p5]


@pytest.mark.asyncio
async def test_sync_remediation_stale_low_db_price_is_placed_at_the_dead_stops_level():
    """DB pointer names a stop the broker reports canceled @ $15.30; DB stop_price
    $15.00. The orphan loop confirms it dead, NULLs the pointer, adopts nothing,
    then remediates — at $15.30, from the SAME broker read (no second call)."""
    audit_calls, place_stop = [], AsyncMock(return_value={"id": "remed-1"})
    get_order = AsyncMock(return_value=_order())
    trade = _make_db_trade(41, "FIGS", remaining=60, stop_price=DB_PRICE)
    trade["stop_order_id"] = POINTER
    with ExitStack() as st:
        for p in _sync_patches([trade], place_stop, audit_calls, get_order=get_order):
            st.enter_context(p)
        discrepancies = await om._sync_positions_for_mode("live")

    place_stop.assert_awaited_once()
    assert place_stop.await_args.args[2] == BROKER_PRICE
    get_order.assert_awaited_once()  # the loop's own read — the floor added none
    assert _floor_rows(audit_calls)
    assert any("stop=$15.30" in d for d in discrepancies), discrepancies


@pytest.mark.asyncio
async def test_sync_remediation_with_null_pointer_places_at_the_db_price():
    audit_calls, place_stop = [], AsyncMock(return_value={"id": "remed-1"})
    get_order = AsyncMock(return_value=_order())
    trade = _make_db_trade(42, "FIGS", remaining=60, stop_price=DB_PRICE)  # pointer None
    with ExitStack() as st:
        for p in _sync_patches([trade], place_stop, audit_calls, get_order=get_order):
            st.enter_context(p)
        await om._sync_positions_for_mode("live")

    place_stop.assert_awaited_once()
    assert place_stop.await_args.args[2] == DB_PRICE
    get_order.assert_not_awaited()
    assert not _floor_rows(audit_calls)


@pytest.mark.asyncio
async def test_sync_remediation_dead_order_without_a_price_places_at_the_db_price():
    audit_calls, place_stop = [], AsyncMock(return_value={"id": "remed-1"})
    trade = _make_db_trade(43, "FIGS", remaining=60, stop_price=DB_PRICE)
    trade["stop_order_id"] = POINTER
    with ExitStack() as st:
        for p in _sync_patches([trade], place_stop, audit_calls,
                               get_order=AsyncMock(return_value=_order(stop_price=None))):
            st.enter_context(p)
        await om._sync_positions_for_mode("live")
    place_stop.assert_awaited_once()
    assert place_stop.await_args.args[2] == DB_PRICE
    assert not _floor_rows(audit_calls)


@pytest.mark.asyncio
async def test_sync_remediation_dead_order_does_not_leak_into_the_next_trade():
    """Two orphans: the first's dead pointer @ $15.30, the second has NO pointer.
    The second must be placed at ITS DB price — a leaked `order` from the first
    row would floor it wrongly."""
    audit_calls, place_stop = [], AsyncMock(return_value={"id": "remed"})
    t1 = _make_db_trade(44, "FIGS", remaining=60, stop_price=DB_PRICE)
    t1["stop_order_id"] = POINTER
    t2 = _make_db_trade(45, "FIGS", remaining=60, stop_price=10.00)
    with ExitStack() as st:
        p1, p2, p3, p4 = _run_sync(
            [t1, t2], [{"symbol": "FIGS", "qty": 60}], audit_calls, place_stop)
        for p in (p1, p2, p3, p4,
                  patch(f"{om.__name__}.alpaca.get_order", new=AsyncMock(return_value=_order()))):
            st.enter_context(p)
        await om._sync_positions_for_mode("live")
    prices = [c.args[2] for c in place_stop.await_args_list]
    assert prices == [BROKER_PRICE, 10.00], prices


# ══════════════════════════════════════════════════════════════════════════════
# 5. Siblings: trade_stream's two WS cancel-restore paths
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ws_partial_cancel_restore_reads_the_live_stop_before_cancelling_it(monkeypatch):
    """The cancel-then-re-place shape (the same defect update_stop had on
    2026-08-10, on a path that never went through update_stop): a PLAIN partial
    was cancelled; the handler cancels the current stop and restores full-size.
    With the current stop LIVE at $15.30 and DB at $15.00, it must restore at
    $15.30 — read BEFORE the cancel — never lower."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 60,
                   "stop_price": DB_PRICE, "stop_order_id": POINTER},
        leg_order=_order(status="accepted"),
    )
    await ts._handle_cancel_or_reject(_cancel_data(order_id="plain-limit-1"), "canceled", "live")

    h["get_order"].assert_awaited_once_with(POINTER, account_mode="live")
    h["cancel"].assert_awaited_once_with(POINTER, account_mode="live")
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[2] == BROKER_PRICE
    assert any("@$15.30" in m for m in h["sent"]), h["sent"]
    assert h["set_stop"].await_args.kwargs["reason"] == "cancel_or_reject_restored"


@pytest.mark.asyncio
async def test_ws_partial_cancel_restore_with_unreadable_stop_still_restores_at_db_price(monkeypatch):
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 60,
                   "stop_price": DB_PRICE, "stop_order_id": POINTER},
        leg_order=None,  # get_order → None
    )
    await ts._handle_cancel_or_reject(_cancel_data(order_id="plain-limit-1"), "canceled", "live")
    h["cancel"].assert_awaited_once()
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[2] == DB_PRICE
    assert any("@$15.00" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_ws_full_exit_cancel_restore_floors_to_the_cancelled_stops_level(monkeypatch):
    """execute_full_exit cancelled the stop; the pointer is nulled only on the
    fill commit, so it still names that cancelled order @ $15.30. The restore
    must re-place there, not at the stale $15.00."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 60,
                   "stop_price": DB_PRICE, "stop_order_id": POINTER},
        leg_order=_order(status="canceled"),
    )
    await ts._handle_cancel_or_reject(_cancel_data(order_id="plain-limit-1"), "canceled", "live")
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[2] == BROKER_PRICE
    assert any("@$15.30" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_ws_full_exit_cancel_restore_with_null_pointer_places_at_db_price(monkeypatch):
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 60,
                   "stop_price": DB_PRICE, "stop_order_id": None},
        leg_order=_order(status="canceled"),
    )
    await ts._handle_cancel_or_reject(_cancel_data(order_id="plain-limit-1"), "canceled", "live")
    h["get_order"].assert_not_awaited()
    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[2] == DB_PRICE


# ══════════════════════════════════════════════════════════════════════════════
# 6. Sibling: update_stop's terminal-old-stop carve-out (_stop_refresh's path)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("dead_status", ["canceled", "expired", "replaced", "filled"])
async def test_update_stop_after_a_dead_stop_never_places_below_its_level(dead_status):
    """_stop_refresh calls update_stop(trade, DB stop_price) after a stop died.
    The 08-10 carve-out (no REFUSE on a terminal stop) stands; the dead stop's
    own price is now the floor. DB $15.00, dead stop @ $15.30 → placed at
    $15.30, DB stop_price written as $15.30, floor audited, still `stop_updated`."""
    async def _dead(order_id, account_mode=None):
        return _order(status=dead_status, order_id=order_id)

    h = _us_harness(om, _us_trade(), _dead)
    ok = await _us_run(om, h, DB_STOP)  # the re-protect idiom: requested == DB

    assert ok is True
    assert h["place"].await_args.kwargs["stop_price"] == BROKER_PRICE
    writes = _stop_price_updates(h)
    assert writes and writes[-1].args[3] == BROKER_PRICE
    events = [e for e, *_ in h["audited"]]
    assert FLOOR_EVENT in events and "stop_updated" in events
    assert "stop_update_aborted" not in events


@pytest.mark.asyncio
async def test_update_stop_after_a_dead_stop_keeps_a_higher_requested_price():
    async def _dead(order_id, account_mode=None):
        return _order(status="canceled", order_id=order_id)

    h = _us_harness(om, _us_trade(), _dead)
    ok = await _us_run(om, h, 15.50)
    assert ok is True
    assert h["place"].await_args.kwargs["stop_price"] == 15.50
    assert FLOOR_EVENT not in [e for e, *_ in h["audited"]]


@pytest.mark.asyncio
async def test_update_stop_after_a_rejected_stop_places_the_requested_price():
    """`rejected` is terminal but never rested — no floor, exactly as 08-10."""
    async def _rej(order_id, account_mode=None):
        return _order(status="rejected", order_id=order_id)

    h = _us_harness(om, _us_trade(), _rej)
    ok = await _us_run(om, h, DB_STOP)
    assert ok is True
    assert h["place"].await_args.kwargs["stop_price"] == DB_STOP
    assert FLOOR_EVENT not in [e for e, *_ in h["audited"]]


@pytest.mark.asyncio
async def test_update_stop_live_stop_refuse_floor_is_untouched():
    """The 08-10 behaviour on a LIVE stop must not have changed: below the live
    broker stop is still REFUSED (not raised-and-placed) — cancel+re-place at
    the same level only opens a no-stop window."""
    async def _live(order_id, account_mode=None):
        return _order(status="accepted", order_id=order_id)

    h = _us_harness(om, _us_trade(), _live)
    ok = await _us_run(om, h, 15.10)
    assert ok is False
    h["cancel"].assert_not_awaited()
    h["place"].assert_not_awaited()
    assert any(e == "stop_update_aborted" and '"raise_only_floor"' in d
               for e, _, d in h["audited"])


# ══════════════════════════════════════════════════════════════════════════════
# 6. #600 fork 2 (2026-09-04) — the common intraday path was DARK: a WS
#    cancel/expiry/reject nulls stop_order_id (T1.5a, unchanged) BEFORE any
#    re-protect can read it, so #600's floor had nothing to consume. This
#    preserves the dead stop's own price+status at the moment of nulling
#    (`_preserve_dead_stop_price`), and lets `_apply_reprotect_floor` consume
#    it via an opt-in `consult_dead_stop` fallback (`_read_preserved_dead_stop`)
#    ONLY when there is still no live broker truth — never a live pointer, never
#    a refusal, never a lower price.
# ══════════════════════════════════════════════════════════════════════════════

DEAD_PRICE = 16.40


# ── 6a. The pure raise-only property holds for a PRESERVED dict too, not just
#        a live get_order() result — same shape, same _floor_reprotect_price. ──


@pytest.mark.parametrize("base", [1.0, 15.0, 15.30, 400.0])
@pytest.mark.parametrize("preserved_price", [None, 0.5, 15.30, 999.0, "x"])
@pytest.mark.parametrize("preserved_status", ["canceled", "rejected", "expired", None])
def test_pure_floor_never_lowers_for_a_preserved_dead_stop_shaped_dict(
        base, preserved_price, preserved_status):
    """_read_preserved_dead_stop hands _floor_reprotect_price the exact same
    dict shape (id/status/stop_price) a live get_order() result has — this
    pins that raise-only holds for that shape too, and that a preserved
    'rejected' entry is ignored by the SAME rule as a live one."""
    dead_stop = {"id": "dead-1", "status": preserved_status, "stop_price": preserved_price}
    price, info = om._floor_reprotect_price(base, dead_stop)
    assert price >= base
    if preserved_status == "rejected":
        assert info["raised"] is False


# ── 6b. _preserve_dead_stop_price — the write side, atomic ratchet ─────────────


@pytest.mark.asyncio
async def test_preserve_writes_and_audits_when_the_ratchet_accepts():
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=501)  # RETURNING id -> the guard matched
    audited = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    with patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(om, "log_audit_event", _audit):
        await om._preserve_dead_stop_price(501, "dead-1", DEAD_PRICE, "canceled", "live")

    conn.fetchval.assert_awaited_once()
    assert conn.fetchval.await_args.args[1:] == (501, DEAD_PRICE, "dead-1", "canceled")
    assert len(audited) == 1 and audited[0][0] == "dead_stop_price_preserved"
    detail = json.loads(audited[0][2])
    assert detail == {
        "trade_id": 501, "account_mode": "live",
        "order_id": "dead-1", "status": "canceled", "price": DEAD_PRICE,
    }


@pytest.mark.asyncio
async def test_preserve_is_quiet_when_the_ratchet_guard_blocks_the_write():
    """Simulates the real Postgres outcome when the new price is NOT strictly
    above the already-preserved one: the WHERE guard matches zero rows,
    RETURNING id yields no row, fetchval -> None. Must not audit — a tie or a
    lower dead-stop price must never look like it raised anything."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        await om._preserve_dead_stop_price(501, "dead-1", DEAD_PRICE, "canceled", "live")
    audit.assert_not_awaited()


def test_preserve_ratchet_sql_only_accepts_a_strictly_higher_price():
    """MUTATION GUARD: the whole mechanism rests on the WHERE guard comparing
    with '>' (strictly higher only) — pin the exact text so a flipped
    comparison is caught here at the source, not just empirically."""
    import inspect
    src = inspect.getsource(om._preserve_dead_stop_price)
    assert "$2 > dead_stop_price" in src
    assert "dead_stop_price IS NULL" in src


@pytest.mark.asyncio
async def test_preserve_skips_the_write_entirely_with_no_price():
    """No stop_price on the dead order (e.g. a malformed WS payload) — no DB
    call at all, matching _floor_reprotect_price's own 'no_stop_price' no-op."""
    with patch.object(om, "get_pool", AsyncMock()) as gp:
        await om._preserve_dead_stop_price(501, "dead-1", None, "canceled", "live")
    gp.assert_not_awaited()


@pytest.mark.asyncio
async def test_preserve_skips_the_write_with_an_unparseable_price():
    with patch.object(om, "get_pool", AsyncMock()) as gp:
        await om._preserve_dead_stop_price(501, "dead-1", "garbage", "canceled", "live")
    gp.assert_not_awaited()


@pytest.mark.asyncio
async def test_preserve_fails_open_when_the_write_raises():
    """FAIL DIRECTION: a DB error while preserving must never propagate — the
    caller (_handle_cancel_or_reject) must still go on to null the pointer."""
    with patch.object(om, "get_pool", AsyncMock(side_effect=RuntimeError("db down"))), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        await om._preserve_dead_stop_price(501, "dead-1", DEAD_PRICE, "canceled", "live")
    audit.assert_not_awaited()


# ── 6c. _read_preserved_dead_stop — the read side, fail-open ──────────────────


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_returns_the_broker_order_shape():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "dead_stop_price": DEAD_PRICE, "dead_stop_status": "canceled",
        "dead_stop_order_id": "dead-1",
    })
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        result = await om._read_preserved_dead_stop(501)
    assert result == {"id": "dead-1", "status": "canceled", "stop_price": DEAD_PRICE}


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_returns_none_when_nothing_preserved():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "dead_stop_price": None, "dead_stop_status": None, "dead_stop_order_id": None,
    })
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._read_preserved_dead_stop(501) is None


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_returns_none_when_the_row_is_missing():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._read_preserved_dead_stop(501) is None


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_fails_open_on_a_db_error():
    with patch.object(om, "get_pool", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await om._read_preserved_dead_stop(501) is None


# ── 6d. _apply_reprotect_floor's consult_dead_stop fallback ───────────────────


@pytest.mark.asyncio
async def test_apply_floor_default_never_consults_the_dead_stop_fallback():
    """THE #600-BEHAVIOUR-UNCHANGED GUARANTEE: consult_dead_stop defaults
    False. Even when a preserved value exists and WOULD raise the price, it
    must never be read unless the caller opts in — every pre-fork-2 caller and
    test must see byte-for-byte the same behaviour."""
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-1", "status": "canceled", "stop_price": 99.0})) as rd, \
         patch.object(om, "log_audit_event", AsyncMock()):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit")
    assert price == DB_PRICE
    rd.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_floor_consults_the_dead_stop_when_no_pointer_and_opted_in():
    audited = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-9", "status": "canceled", "stop_price": BROKER_PRICE})), \
         patch.object(om, "log_audit_event", _audit):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit", consult_dead_stop=True)
    assert price == BROKER_PRICE
    rows = _floor_rows(audited)
    assert len(rows) == 1
    d = json.loads(rows[0][2])
    assert d["broker_order_id"] == "dead-9"
    assert d["floor_source"] == "preserved_broker_pointer"
    assert d["placed_price"] == BROKER_PRICE and d["db_price"] == DB_PRICE


@pytest.mark.asyncio
async def test_apply_floor_ignores_a_preserved_rejected_stop():
    """A preserved 'rejected' stop never rested — ignored by the SAME rule as
    a live one, via the SAME _floor_reprotect_price code path (no second place
    this rule could drift out of sync)."""
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-9", "status": "rejected", "stop_price": 999.0})), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit", consult_dead_stop=True)
    assert price == DB_PRICE
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_floor_falls_through_when_nothing_was_preserved():
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(return_value=None)), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit", consult_dead_stop=True)
    assert price == DB_PRICE
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_floor_dead_stop_fallback_with_unparseable_price_still_places_at_base():
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-9", "status": "canceled", "stop_price": "garbage"})), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit", consult_dead_stop=True)
    assert price == DB_PRICE
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_floor_dead_stop_fallback_fails_open_when_the_read_raises():
    """Belt-and-suspenders: _read_preserved_dead_stop already fails open
    internally, but _apply_reprotect_floor must not trust that alone — even if
    it somehow raised, the placement must still go ahead at the base price."""
    with patch.object(om, "_read_preserved_dead_stop",
                       AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(om, "log_audit_event", AsyncMock()) as audit:
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, None, "live", site="unit", consult_dead_stop=True)
    assert price == DB_PRICE
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_floor_live_broker_truth_beats_the_dead_stop_fallback():
    """When the live pointer DOES resolve to a real broker order, the dead-stop
    fallback must never even be consulted — live truth always wins over a
    preserved (necessarily older) value."""
    with patch.object(om.alpaca, "get_order",
                       AsyncMock(return_value=_order(stop_price=DB_PRICE))), \
         patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-9", "status": "canceled", "stop_price": 999.0})) as rd, \
         patch.object(om, "log_audit_event", AsyncMock()):
        price = await om._apply_reprotect_floor(
            7, "FIGS", DB_PRICE, POINTER, "live", site="unit", consult_dead_stop=True)
    assert price == DB_PRICE
    rd.assert_not_awaited()


# ── 6d-2. END-TO-END: the `consult_dead_stop=True` kwarg AT THE CALL SITE ─────
#         (not just the helper) — pins that the wiring itself, not only the
#         mechanism it calls, is load-bearing. Deleting the kwarg at either
#         site must redden exactly one of these two.


@pytest.mark.asyncio
async def test_place_branch_consults_the_dead_stop_fallback_when_no_pointer():
    """_ensure_stop_coverage's place branch: no live pointer at all, but a
    preserved dead-stop price exists — must be consulted and floor the
    placement. Reddens if `consult_dead_stop=True` is ever deleted from the
    `_apply_reprotect_floor(...)` call inside `_ensure_stop_coverage`."""
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-1", "status": "canceled", "stop_price": BROKER_PRICE})):
        h = _cov_patches([], pending_qty=0, stop_pointer=None)
        result = await _cov_run(h, broker_qty=60, stop_price=DB_PRICE, account_mode="live")

    h["place"].assert_called_once()
    assert h["place"].call_args.args[2] == BROKER_PRICE, h["place"].call_args
    assert FLOOR_EVENT in h["audited"]
    repaired = [d for e, _, d in h["audit_details"] if e == FLOOR_EVENT][0]
    assert repaired["floor_source"] == "preserved_broker_pointer"
    assert result is not None and "15.30" in result


@pytest.mark.asyncio
async def test_sync_remediation_consults_the_dead_stop_fallback_when_no_pointer():
    """sync_positions' orphan remediation: `existing_stop_id` is already NULL
    entering the loop (the WS event beat this sync), but a preserved dead-stop
    price exists — must be consulted. Reddens if `consult_dead_stop=True` is
    ever deleted from the `_apply_reprotect_floor(...)` call inside
    `_sync_positions_for_mode`."""
    audit_calls, place_stop = [], AsyncMock(return_value={"id": "remed-1"})
    trade = _make_db_trade(44, "FIGS", remaining=60, stop_price=DB_PRICE)  # pointer None
    with patch.object(om, "_read_preserved_dead_stop", AsyncMock(
             return_value={"id": "dead-1", "status": "canceled", "stop_price": BROKER_PRICE})), \
         ExitStack() as st:
        for p in _sync_patches([trade], place_stop, audit_calls,
                               get_order=AsyncMock(return_value=None)):
            st.enter_context(p)
        await om._sync_positions_for_mode("live")

    place_stop.assert_awaited_once()
    assert place_stop.await_args.args[2] == BROKER_PRICE
    assert _floor_rows(audit_calls)


# ── 6e. The wiring — _handle_cancel_or_reject preserves BEFORE it nulls ───────


def _priced_ws_data(order_id="dead-stop-1", symbol="FIGS", stop_price=DEAD_PRICE,
                     status="canceled"):
    order = SimpleNamespace(
        id=order_id, symbol=symbol, status=status, stop_price=stop_price,
        filled_qty=0, filled_avg_price=0, side="sell", type="stop", qty=41,
        canceled_at=None, failed_at=None, expired_at=None, updated_at=None,
    )
    return SimpleNamespace(order=order, event=status, reason=None)


def _wire_stop_cancel(monkeypatch, stop_row, *, dup_rows=None):
    """The stop-leg cancel branch (section 2) with NO evidence of a
    replacement — reaches the genuinely-naked alarm, mirroring
    test_576_false_money_path_alerts.py's _fire_naked_branch harness."""
    pool, conn, audit, sent, capture = _make_ws_pool(stop_row, None, None, dup_rows=dup_rows or [])
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop",
                         AsyncMock(side_effect=[None, None]))
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    return sent


@pytest.mark.asyncio
async def test_cancel_handler_preserves_the_dead_price_before_nulling_the_pointer(monkeypatch):
    """THE WIRING (#600 fork 2). _handle_cancel_or_reject must capture the dead
    stop's own broker price+status BEFORE T1.5a's cancel_or_reject_null fires
    — and that null call itself must be BYTE-FOR-BYTE UNCHANGED (same trade
    id, None, same reason, same account_mode) per the hard constraint that the
    assume-naked fail-safe does not change."""
    stop_row = {
        "id": 501, "ticker": "FIGS", "remaining_shares": 41.0,
        "stop_price": 13.74, "entry_price": 14.50, "hard_stop": 13.00,
    }
    sent = _wire_stop_cancel(monkeypatch, stop_row)

    calls = []

    async def _preserve(*args, **kwargs):
        calls.append(("preserve", args))

    async def _set_stop(*args, **kwargs):
        calls.append(("set_stop", args, kwargs))

    monkeypatch.setattr(om, "_preserve_dead_stop_price", _preserve)
    monkeypatch.setattr(om, "set_stop_order_id", _set_stop)

    await ts._handle_cancel_or_reject(
        _priced_ws_data(order_id="dead-stop-1", stop_price=DEAD_PRICE, status="canceled"),
        "canceled", "live",
    )

    names = [c[0] for c in calls]
    assert names == ["preserve", "set_stop"], f"preserve must run BEFORE the null: {names}"
    assert calls[0][1] == (501, "dead-stop-1", DEAD_PRICE, "canceled", "live")
    assert calls[1][1] == (501, None)
    assert calls[1][2] == {"reason": "cancel_or_reject_null", "account_mode": "live"}
    # Unchanged: this is still a real naked position with no corroborating
    # evidence — the genuinely-naked alarm must still fire exactly as before.
    assert any("unprotected" in m.lower() for m in sent)


@pytest.mark.asyncio
async def test_cancel_handler_preserves_on_expiry_too_same_wiring(monkeypatch):
    """The EOD 'expired' event takes a different branch AFTER the null (the
    informational 'stop expired (expected)' message, not the naked alarm) —
    but the preserve-then-null wiring above it must be identical."""
    stop_row = {
        "id": 502, "ticker": "FIGS", "remaining_shares": 41.0,
        "stop_price": 13.74, "entry_price": 14.50, "hard_stop": 13.00,
    }
    sent = _wire_stop_cancel(monkeypatch, stop_row)

    calls = []

    async def _preserve(*args, **kwargs):
        calls.append(("preserve", args))

    async def _set_stop(*args, **kwargs):
        calls.append(("set_stop", args, kwargs))

    monkeypatch.setattr(om, "_preserve_dead_stop_price", _preserve)
    monkeypatch.setattr(om, "set_stop_order_id", _set_stop)

    await ts._handle_cancel_or_reject(
        _priced_ws_data(order_id="dead-stop-2", stop_price=DEAD_PRICE, status="expired"),
        "expired", "live",
    )

    names = [c[0] for c in calls]
    assert names == ["preserve", "set_stop"]
    assert calls[0][1] == (502, "dead-stop-2", DEAD_PRICE, "expired", "live")
    assert any("EOD stop expired" in m for m in sent)


@pytest.mark.asyncio
async def test_cancel_handler_preserves_a_rejected_stops_price_too(monkeypatch):
    """A stop that was placed (hence named as the trade's pointer) and then
    REJECTED before ever resting still gets preserved — tagged 'rejected' so
    the CONSUMPTION side (_floor_reprotect_price's ignored-status rule) is the
    one place that decides it never protected anything. Preserving
    indiscriminately here and filtering once downstream avoids a second copy
    of the rejected-is-ignored rule drifting out of sync."""
    stop_row = {
        "id": 503, "ticker": "FIGS", "remaining_shares": 41.0,
        "stop_price": 13.74, "entry_price": 14.50, "hard_stop": 13.00,
    }
    _wire_stop_cancel(monkeypatch, stop_row)

    calls = []

    async def _preserve(*args, **kwargs):
        calls.append(("preserve", args))

    monkeypatch.setattr(om, "_preserve_dead_stop_price", _preserve)
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())

    await ts._handle_cancel_or_reject(
        _priced_ws_data(order_id="dead-stop-3", stop_price=DEAD_PRICE, status="rejected"),
        "rejected", "live",
    )

    assert len(calls) == 1
    assert calls[0][1] == (503, "dead-stop-3", DEAD_PRICE, "rejected", "live")
