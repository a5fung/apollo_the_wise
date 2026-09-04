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
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool
from tests.test_never_naked_invariant import _patches as _cov_patches, _run as _cov_run
from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending, _wire
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
