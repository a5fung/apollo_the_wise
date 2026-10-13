"""#687 (2026-10-14, KO paper trade 421) — a full-exit sale that PART-FILLS and then dies books the
share(s) it sold as ONE `exits[]` leg + its realised P&L, and writes NOTHING the stop restore reads.

THE DEFECT (prod 2026-10-13): a planned full-exit sale (3 sh) part-filled 1 @ $90.36 at the open and
the other 2 EXPIRED. `trade_stream._handle_cancel_or_reject` §3's full-exit branch re-placed a stop sized
from the BROKER (2 sh) — right — but the 1 sold share was never recorded: no `exits[]` leg, no realised
P&L (`remaining_shares` stayed 3 until sync healed it).

WHY THIS DESIGN (the parked first design, `c5bf1dfa`, lowered `remaining_shares` at booking time and
five review rounds each found a case where the stop restore then protected FEWER shares than base,
because the restore's database fallback READS `remaining_shares`): correct only fields the safety path
does not read. The new code writes `exits` + `total_pnl` of ONE row and nothing else; it runs in its own
background task BESIDE the restore (the restore code is unchanged); sync keeps healing the share count.

THE PROOF this file carries:
  * the equivalence MATRIX — for every world x delivery x restore-read-failure mode, a run with the
    booking STUBBED OUT (= the code before this change) and the real run hand the restore the same
    inputs and place the same orders: broker calls, every column except exits/total_pnl, the order
    mirror, the non-booking pages and audit rows are IDENTICAL;
  * the writer touches exactly {exits, total_pnl} (SET clause + the `audit_column_writes` deploy gate);
  * every double-count path the design names counts the sold shares ONCE.

Worlds come from the convergence harness (NOT edited — its sha256 is pinned by
`test_687_toggle_off_convergence.py`). A booking-asserting test fails when the booking is removed:
see `test_the_booking_assertions_are_not_vacuous` (and the mutation pass recorded in the commit).

LIMIT: the harness's advisory lock never blocks, so no test here can make the booking WAIT on a held
lock; what is pinned instead is that the booking runs beside the restore (a booking that never finishes
does not delay the stop), and the foreign-lock world only shows the restore equivalence.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence import audit_invariants as inv
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

ROOT = Path(__file__).resolve().parents[1]
TID = 421
ENTRY = 90.85            # KO paper trade 421: (90.36 - 90.85) x 1 = -0.49, the P&L he is told about
STOP = 77.22
FILL_PX = 90.36
ET = ZoneInfo("America/New_York")
BOOKING_EVENTS = ("full_exit_dead_fill_booked", "full_exit_dead_fill_duplicate",
                  "full_exit_dead_fill_booking_error", "full_exit_dead_fill_unpriced_error")
KO_PAGE = ("📄 PAPER 📤 *KO: 1 of 3 sh sold before the close order EXPIRED*\n"
           "Sold @$90.36, P&L −$0.49 — now in the books. The other 2 did not sell; "
           "the stop page says how they are protected.")


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────

async def _drain():
    """Wait for every background task the handler spawned (the restore retry AND the booking)."""
    for _ in range(5):
        tasks = list(ts._RESTORE_RETRY_BG_TASKS) + list(ts._DEAD_SALE_BOOKING_BG_TASKS)
        if not tasks:
            return
        await asyncio.gather(*tasks)


async def _drive(w, *steps):
    """Run the steps on the fake world, then DRAIN the background tasks BEFORE the fake world is
    uninstalled (a booking that ran after it would hit the real pool)."""
    undo = H._install(w)
    try:
        out = [await step() for step in steps]
        await _drain()
        return out
    finally:
        H._uninstall(undo)


def _ko_world(*, remaining=3, qty=3, broker_qty=2, available=None, mode="paper",
              sale_status="expired", mirror_status="partially_filled", **trade_over):
    """KO, paper: `remaining` sh on the books, a queued sale for `qty` that part-filled and then
    died, the broker holding `broker_qty`. The stop was cancelled by the sale; the pointer is NULL."""
    w = H.World()
    H._trade(w, tid=TID, ticker="KO", remaining=remaining, stop_id=None, stop_price=STOP,
             **{"entry_price": ENTRY, "account_mode": mode, **trade_over})
    if broker_qty:
        H._position(w, "KO", broker_qty, broker_qty if available is None else available)
    H._bsell(w, "sell-q", "KO", qty, status=sale_status)
    H._mirror(w, "sell-q", TID, "KO", "full_exit", qty, status=mirror_status,
              exit_reason="sma_trail_stop")
    return w


def _stale_pending_world():
    """Books 10, the dead sale (12 sh) sold 2, the broker holds 8, and a STALE pending partial-exit
    row of 3 sh that nothing has closed (it counts in `get_pending_exit_qty`)."""
    w = _ko_world(remaining=10, qty=12, broker_qty=8)
    H._mirror(w, "stale-p", TID, "KO", "partial_exit", 3, status="new")
    return w


def _event(event="expired", *, filled=1.0, avg=FILL_PX, qty=3.0):
    order = SimpleNamespace(
        id="sell-q", symbol="KO", status=event, filled_qty=filled,
        filled_avg_price=avg if filled else None, qty=qty, side="sell", type="market",
        limit_price=None, stop_price=None, canceled_at=None, failed_at=None, expired_at=None,
        updated_at=None)
    return SimpleNamespace(order=order, event=event, reason=None, price=avg, qty=filled)


def _handle(event="expired", mode="paper", **kw):
    ev = _event(event, **kw)
    return lambda: ts._handle_cancel_or_reject(ev, event, mode)


def _placed(w) -> list:
    return [(c["args"]["qty"], c["args"]["stop_price"]) for c in w.calls
            if c["method"] == "place_stop_order"]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _row(w):
    return {k: (list(v) if isinstance(v, list) else v) for k, v in w.trades[TID].items()}


def _is_booking_page(p: str) -> bool:
    return "before the close order" in p      # pages B, E and U; the restore's pages never say it


def _booking_pages(w) -> list[str]:
    return [p for p in w.pages if _is_booking_page(p)]


def _other_pages(w) -> list[str]:
    return [p for p in w.pages if not _is_booking_page(p)]


def _teach_zero_literal(m):
    """The harness's SQL interpreter stores a bare literal (`remaining_shares = 0`) as an opaque
    expression; teach THIS test's copy the one literal the close-at-zero UPDATE writes."""
    real_apply = H._apply_set

    def _apply(sql, row, args):
        real_apply(sql, row, args)
        for k, v in list(row.items()):
            if v == ("expr", "0"):
                row[k] = 0
    m.setattr(H, "_apply_set", _apply)


def _stub_booking(m):
    """The code BEFORE this change: the stream schedules no booking."""
    m.setattr(ts, "_schedule_dead_full_exit_booking", lambda *a, **k: None)


@contextlib.contextmanager
def _restore_reads_fail(mode):
    """From the moment the STREAM's restore starts sizing (its first `_broker_free_qty_for_restore`
    call) break the named broker read, so the restore falls to its DATABASE fallback
    (`remaining - pending exits`) — the input a lowered `remaining_shares` once corrupted."""
    rec = {"phase": False}
    real_impl = H._broker_impl
    real_free = om._broker_free_qty_for_restore

    def _impl(world):
        fns = real_impl(world)
        gp, gap, goo = fns["get_position"], fns["get_all_positions"], fns["get_open_orders"]

        async def _gp(ticker, account_mode=None):
            if rec["phase"] and mode == "position_unreadable":
                return None
            return await gp(ticker, account_mode=account_mode)

        async def _gap(account_mode=None, **k):
            if rec["phase"] and mode == "position_unreadable":
                raise Exception("positions down")
            return await gap(account_mode=account_mode, **k)

        async def _goo(*a, **k):
            if rec["phase"] and mode == "orders_unreadable":
                raise Exception("orders down")
            return await goo(*a, **k)
        fns.update(get_position=_gp, get_all_positions=_gap, get_open_orders=_goo)
        return fns

    async def _free(ticker, account_mode, fallback_qty, **k):
        rec["phase"] = True
        return await real_free(ticker, account_mode, fallback_qty, **k)

    H._broker_impl = _impl
    om._broker_free_qty_for_restore = _free
    try:
        yield rec
    finally:
        H._broker_impl = real_impl
        om._broker_free_qty_for_restore = real_free


def _sync_heal(w):
    """What `_sync_lowered_qty` does after the sale part-filled: books -> the broker's count."""
    pos = w.positions.get("KO")
    w.trades[TID]["remaining_shares"] = min(w.trades[TID]["remaining_shares"],
                                            int(pos["qty"]) if pos else 0)


def _fire_restored_stop(w, *, price=STOP - 1.0):
    """The stop the restore placed FILLS at the broker; the WS fill event reaches the stream."""
    stop_id = w.trades[TID]["stop_order_id"]
    qty = next((q for q, _p in reversed(_placed(w))), None)
    if not stop_id or qty is None:
        return None
    return lambda: ts._handle_fill(
        H._ws_order(stop_id, "KO", filled_qty=float(qty), avg=float(price), status="filled"),
        w.trades[TID]["account_mode"])


# ── (a) KO: part-filled 1 of 3, the other 2 expired - the real 10-13 case ────────────────────────

def _assert_ko_booked(w):
    """The KO end state with the fix. Shared by the positive test and by the not-vacuous check."""
    t = w.trades[TID]
    assert len(t["exits"]) == 1, t["exits"]
    [leg] = t["exits"]
    assert (leg["shares"], leg["price"], leg["order_id"], leg["reason"], leg["source"],
            leg["attempt"]) == (1, FILL_PX, "sell-q", "sma_trail_stop", "dead_order:expired", 1), leg
    assert leg["pnl"] == pytest.approx(-0.49)
    assert t["total_pnl"] == pytest.approx(-0.49)
    assert t["remaining_shares"] == 3, "the share count is sync's to heal, never this code's"
    assert t["status"] == "filled" and t["closed_at"] is None


@pytest.mark.asyncio
async def test_ko_part_fill_then_expiry_books_one_leg_and_never_the_share_count():
    w = _ko_world()                                              # books 3, broker 2, sold 1
    before = _row(w)
    await _drive(w, _handle("expired"))
    t = w.trades[TID]
    _assert_ko_booked(w)

    # the restore is untouched: sized from the BROKER (2) at the row's stop price, pointer re-set
    assert _placed(w) == [(2, STOP)], w.calls
    placed_ids = [o["id"] for o in w.broker_orders if o["type"] == "stop"]
    assert t["stop_order_id"] == placed_ids[-1]

    # ONLY exits / total_pnl move (the pointer moves because the pre-existing restore re-points it)
    assert {k for k in before if before[k] != _row(w)[k]} == {"exits", "total_pnl", "stop_order_id"}
    for k in ("remaining_shares", "status", "closed_at", "stop_price", "partial_taken",
              "breakeven_active", "hard_stop", "entry_shares", "depth_sell_pending_on"):
        assert t[k] == before[k], k
    # no order cancelled, sold or resized by the booking
    assert {c["method"] for c in w.calls} <= {"get_position", "get_all_positions", "get_open_orders",
                                              "get_order", "place_stop_order",
                                              "make_client_order_id"}, w.calls
    assert "close_position" not in {c["method"] for c in w.calls}

    # the audit row and the ONE booking page (+ the pre-existing restore page, wording frozen)
    [booked] = _audits(w, "full_exit_dead_fill_booked")
    assert (booked["trade_id"], booked["order_id"], booked["event_norm"], booked["shares"],
            booked["order_qty"], booked["fill_price"], booked["source"],
            booked["remaining_shares_unchanged"]) == (
        TID, "sell-q", "expired", 1.0, 3.0, FILL_PX, "dead_order:expired", 3), booked
    assert booked["pnl"] == pytest.approx(-0.49)
    assert booked["total_pnl_before"] == 0 and booked["total_pnl_after"] == pytest.approx(-0.49)
    assert _booking_pages(w) == [KO_PAGE], w.pages
    assert _other_pages(w) == ["📄 PAPER ⚠️ *Close order EXPIRED:* KO\n"
                               "Position still open. Stop re-placed @$77.22 for 2 sh."]
    # never a name that resets the partial-exit failure breaker
    assert not [a for a in w.audits if a["event_type"] == "partial_exit_committed"]


@pytest.mark.asyncio
async def test_the_booking_assertions_are_not_vacuous(monkeypatch):
    """With the booking removed (the code before this change) the KO assertions FAIL — so a green
    `test_ko_part_fill...` is evidence of the booking, not of a lenient assert."""
    w = _ko_world()
    with monkeypatch.context() as m:
        _stub_booking(m)
        await _drive(w, _handle("expired"))
    with pytest.raises(AssertionError):
        _assert_ko_booked(w)
    assert w.trades[TID]["exits"] == [] and w.trades[TID]["total_pnl"] is None
    assert not _audits(w, "full_exit_dead_fill_booked") and not _booking_pages(w)
    # and the end state the stub leaves is exactly "nothing booked, restore as ever"
    assert _placed(w) == [(2, STOP)] and w.trades[TID]["remaining_shares"] == 3


@pytest.mark.parametrize("event,shown", [("cancelled", "CANCELLED"), ("canceled", "CANCELLED"),
                                          ("rejected", "REJECTED")])
@pytest.mark.asyncio
async def test_a_cancel_and_a_reject_book_the_leg_too(event, shown):
    w = _ko_world()
    await _drive(w, _handle(event))
    [leg] = w.trades[TID]["exits"]
    assert leg["source"] == f"dead_order:{'cancelled' if event.startswith('cancel') else event}"
    assert w.trades[TID]["remaining_shares"] == 3
    [page] = _booking_pages(w)
    assert f"before the close order {shown}*" in page, page


def test_booking_page_wording():
    prefix = ts.mode_prefix("paper")
    page = lambda *a: ts._dead_full_exit_booked_page(prefix, *a)   # noqa: E731
    assert page("KO", "expired", 1.0, 3.0, FILL_PX, -0.49) == KO_PAGE
    full = page("KO", "cancelled", 3.0, 3.0, 91.0, 1.5)
    assert "all 3 sh sold before the close order CANCELLED*" in full
    assert full.endswith("Sold @$91.00, P&L +$1.50 — now in the books."), full
    unknown_qty = page("KO", "rejected", 2.0, 0.0, 91.0, -3.0)
    assert "2 sh sold before the close order REJECTED*" in unknown_qty and " of " not in unknown_qty
    assert "The rest did not sell" in unknown_qty


# ── (b) THE MATRIX: booking-stubbed (= base) vs real ─────────────────────────────────────────────

def _oco_third_world():
    """Books 6 = the 4-sh dead sale + a +8R profit-take THIRD of 2 resting under its own OCO. The
    sale sold 1 and died; the broker holds 5, of which the OCO holds 2 (free 3)."""
    w = _ko_world(remaining=6, qty=4, broker_qty=5, available=3, partial_taken=True,
                  breakeven_active=True)
    H._boco(w, "oco-1", "KO", 2)
    H._mirror(w, "oco-1", TID, "KO", "partial_exit", 2, raw={"order_class": "oco"})
    return w


WORLDS = {
    "ko": (lambda: _ko_world(), dict(filled=1.0, qty=3.0)),
    "live_books30_sold10_broker20": (lambda: _ko_world(remaining=30, qty=30, broker_qty=20,
                                                       mode="live"),
                                     dict(filled=10.0, qty=30.0, mode="live")),
    "beside_a_resting_oco_third": (_oco_third_world, dict(filled=1.0, qty=4.0)),
    "stale_pending_books10_sold2_broker8": (_stale_pending_world, dict(filled=2.0, qty=12.0)),
    "books_below_broker": (lambda: _ko_world(remaining=6, qty=10, broker_qty=8),
                           dict(filled=2.0, qty=10.0)),
    "broker_flat": (lambda: _ko_world(remaining=2, qty=3, broker_qty=0), dict(filled=2.0, qty=3.0)),
}
DELIVERIES = ["once", "twice", "twice_after_sync", "after_the_restored_stop_filled"]
RESTORE_READS = ["read_ok", "position_unreadable", "orders_unreadable", "pending_unreadable"]


async def _run(world_factory, ev_kw, delivery, read_mode, *, stub, monkeypatch, foreign_lock=False):
    w = world_factory()
    if foreign_lock:
        w.foreign_locks = {TID}
    with monkeypatch.context() as m:
        _teach_zero_literal(m)
        if stub:
            _stub_booking(m)
        if read_mode == "pending_unreadable":
            async def _boom(trade_id):
                raise RuntimeError("pending exits read down")
            m.setattr(om, "get_pending_exit_qty", _boom)
        restore_mode = read_mode if read_mode in ("position_unreadable", "orders_unreadable") \
            else "read_ok"
        with _restore_reads_fail(restore_mode):
            await _drive(w, _handle("expired", **ev_kw))
            if delivery == "twice":
                await _drive(w, _handle("expired", **ev_kw))
            elif delivery == "twice_after_sync":
                _sync_heal(w)
                await _drive(w, _handle("expired", **ev_kw))
            elif delivery == "after_the_restored_stop_filled":
                fire = _fire_restored_stop(w)
                if fire is not None:
                    await _drive(w, fire)
                await _drive(w, _handle("expired", **ev_kw))
    return w


def _without_exits_and_pnl(w):
    row = dict(w.trades[TID])
    row.pop("exits")
    row.pop("total_pnl")
    return row


def _audit_rows(w):
    return [(a["event_type"], a["summary"], a["detail"]) for a in w.audits
            if a["event_type"] not in BOOKING_EVENTS]


def _assert_restore_identical(real, base, *, what=""):
    assert real.calls == base.calls, f"{what}: broker calls differ"
    assert _without_exits_and_pnl(real) == _without_exits_and_pnl(base), f"{what}: row differs"
    assert real.orders == base.orders, f"{what}: order mirror differs"
    assert _other_pages(real) == _other_pages(base), f"{what}: restore pages differ"
    assert _audit_rows(real) == _audit_rows(base), f"{what}: non-booking audit rows differ"


@pytest.mark.parametrize("read_mode", RESTORE_READS)
@pytest.mark.parametrize("delivery", DELIVERIES)
@pytest.mark.parametrize("world", list(WORLDS))
@pytest.mark.asyncio
async def test_matrix_every_restore_input_and_order_is_identical_to_the_stubbed_run(
        world, delivery, read_mode, monkeypatch):
    factory, ev_kw = WORLDS[world]
    base = await _run(factory, ev_kw, delivery, read_mode, stub=True, monkeypatch=monkeypatch)
    real = await _run(factory, ev_kw, delivery, read_mode, stub=False, monkeypatch=monkeypatch)

    _assert_restore_identical(real, base, what=f"{world}/{delivery}/{read_mode}")

    # ...and the booking itself really happened, exactly once, in the real run only
    assert base.trades[TID]["exits"] == [] or all(
        e.get("source") != "dead_order:expired" for e in base.trades[TID]["exits"])
    dead = [e for e in real.trades[TID]["exits"] if e.get("order_id") == "sell-q"]
    assert len(dead) == 1, (world, delivery, read_mode, real.trades[TID]["exits"])
    assert dead[0]["shares"] == ev_kw["filled"] and dead[0]["source"] == "dead_order:expired"
    assert len(_audits(real, "full_exit_dead_fill_booked")) == 1
    assert len(_booking_pages(real)) == 1, "a duplicate delivery never pages the booking twice"
    if delivery in ("twice", "twice_after_sync"):
        assert len(_audits(real, "full_exit_dead_fill_duplicate")) == 1


@pytest.mark.asyncio
async def test_matrix_foreign_trade_lock_restore_is_identical(monkeypatch):
    """A foreign holder of the trade's try-lock (the world's `foreign_locks`) defers every try-lock
    user in the restore chain identically in both runs. The harness's BLOCKING lock never waits, so
    this cell shows the restore equivalence only — not the booking's wait (see the module LIMIT)."""
    factory, ev_kw = WORLDS["ko"]
    base = await _run(factory, ev_kw, "once", "read_ok", stub=True, monkeypatch=monkeypatch,
                      foreign_lock=True)
    real = await _run(factory, ev_kw, "once", "read_ok", stub=False, monkeypatch=monkeypatch,
                      foreign_lock=True)
    _assert_restore_identical(real, base, what="foreign lock")
    assert len(real.trades[TID]["exits"]) == 1


@pytest.mark.parametrize("world", ["ko", "stale_pending_books10_sold2_broker8"])
@pytest.mark.asyncio
async def test_matrix_a_booking_that_raises_leaves_the_restore_identical(world, monkeypatch):
    factory, ev_kw = WORLDS[world]
    base = await _run(factory, ev_kw, "once", "read_ok", stub=True, monkeypatch=monkeypatch)

    async def _boom(*a, **k):
        raise RuntimeError("db down")
    with monkeypatch.context() as m:
        m.setattr(om, "book_dead_full_exit_leg", _boom)
        real = await _run(factory, ev_kw, "once", "read_ok", stub=False, monkeypatch=m)
    _assert_restore_identical(real, base, what="booking raises")
    assert real.trades[TID]["exits"] == []
    [err] = _audits(real, "full_exit_dead_fill_booking_error")
    assert err["trade_id"] == TID and err["order_id"] == "sell-q" and "db down" in err["error"]
    [page] = _booking_pages(real)
    assert page.startswith("📄 PAPER 🚨 *KO: ") and "the books could NOT be updated*" in page
    assert f"fix trade {TID} by hand (its exits and P&L)." in page


# ── the restore never waits for the booking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_booking_that_never_finishes_does_not_delay_the_stop(monkeypatch):
    """The booking is a background task started BEFORE the restore's first await and never awaited by
    it: with the booking blocked, the handler still returns with the 2-sh stop placed. (The lock wait
    is the booking's alone.)"""
    w = _ko_world()
    gate = asyncio.Event()

    async def _stuck(*a, **k):
        await gate.wait()
        return {"outcome": "already_booked", "ticker": "KO"}
    monkeypatch.setattr(om, "book_dead_full_exit_leg", _stuck)
    undo = H._install(w)
    try:
        await _handle("expired")()
        assert _placed(w) == [(2, STOP)], "the stop is placed while the booking is still waiting"
        [task] = list(ts._DEAD_SALE_BOOKING_BG_TASKS)
        assert not task.done()
        gate.set()
        await _drain()
    finally:
        H._uninstall(undo)
    assert not ts._DEAD_SALE_BOOKING_BG_TASKS


@pytest.mark.asyncio
async def test_the_booking_is_scheduled_before_the_restore_reads_anything(monkeypatch):
    """The schedule call is the FIRST statement of the full-exit branch — before the restore's row
    read. Break THAT read: the handler raises (as it always did), yet the booking was already
    scheduled, and it still lands. (Nothing the restore reads can move the booking, and the booking
    waits on nothing the restore does.)"""
    w = _ko_world()
    real_fetchrow = H.FakeConn.fetchrow

    async def _fetchrow(self, sql, *a, **k):
        if "signal_type" in sql and "FROM mi_live_trades WHERE id = $1" in " ".join(sql.split()):
            raise RuntimeError("row read down")
        return await real_fetchrow(self, sql, *a, **k)
    monkeypatch.setattr(H.FakeConn, "fetchrow", _fetchrow)
    undo = H._install(w)
    try:
        with pytest.raises(RuntimeError, match="row read down"):
            await _handle("expired")()
        assert len(ts._DEAD_SALE_BOOKING_BG_TASKS) == 1
        await _drain()
    finally:
        H._uninstall(undo)
    _assert_ko_booked(w)


# ── (c) a duplicate delivery -> one leg ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_c_the_same_event_delivered_twice_books_one_leg_and_pages_once():
    w = _ko_world()
    await _drive(w, _handle("expired"))
    total_after_first = w.trades[TID]["total_pnl"]
    await _drive(w, _handle("expired"))                          # the broker re-delivers it
    t = w.trades[TID]
    assert len(t["exits"]) == 1 and t["total_pnl"] == total_after_first
    assert t["remaining_shares"] == 3
    assert len(_audits(w, "full_exit_dead_fill_booked")) == 1
    [dup] = _audits(w, "full_exit_dead_fill_duplicate")
    assert dup["order_id"] == "sell-q"
    assert len(_booking_pages(w)) == 1, "no second booking page on a duplicate"
    assert not _audits(w, "full_exit_dead_fill_booking_error")


@pytest.mark.asyncio
async def test_c_a_late_fill_event_of_the_same_order_is_a_noop_and_so_is_the_reverse_order(monkeypatch):
    # dead event first, then a (never expected) late 'fill' of the same order: finalize_full_exit
    # finds the booking's order_id and writes nothing
    w = _ko_world()
    await _drive(w, _handle("expired"))
    pages_before = list(w.pages)
    await _drive(w, lambda: ts._handle_fill(
        H._ws_order("sell-q", "KO", filled_qty=1.0, avg=FILL_PX, status="filled"), "paper"))
    t = w.trades[TID]
    assert len(t["exits"]) == 1 and t["remaining_shares"] == 3 and t["status"] == "filled"
    assert w.pages == pages_before, "the no-op finalizer pages nothing"

    # fill first (books + decrements, as on base), THEN the dead event: the booking is the no-op
    w2 = _ko_world(mirror_status="expired")
    await _drive(w2, lambda: om.finalize_full_exit(TID, 1, FILL_PX, "sell-q", "sma_trail_stop"))
    assert w2.trades[TID]["remaining_shares"] == 2 and len(w2.trades[TID]["exits"]) == 1
    await _drive(w2, _handle("expired"))
    assert len(w2.trades[TID]["exits"]) == 1 and w2.trades[TID]["remaining_shares"] == 2
    assert len(_audits(w2, "full_exit_dead_fill_duplicate")) == 1
    assert not _audits(w2, "full_exit_dead_fill_booked")


# ── (d) nothing sold / no price ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sql_log(monkeypatch):
    log = []
    real = H.FakeConn._run

    async def _run_logged(self, kind, sql, *args, **kw):
        log.append((kind, H._norm(sql)))
        return await real(self, kind, sql, *args, **kw)
    monkeypatch.setattr(H.FakeConn, "_run", _run_logged)
    return log


@pytest.mark.asyncio
async def test_d_filled_zero_schedules_nothing_and_the_whole_run_equals_base(monkeypatch, sql_log):
    spy = AsyncMock()
    monkeypatch.setattr(ts, "_book_dead_full_exit_sale", spy)
    ev_kw = dict(filled=0.0, avg=None, qty=3.0)

    base = _ko_world(broker_qty=3)
    with monkeypatch.context() as m:
        _stub_booking(m)
        await _drive(base, _handle("expired", **ev_kw))
    base_sql = list(sql_log)
    sql_log.clear()

    w = _ko_world(broker_qty=3)
    await _drive(w, _handle("expired", **ev_kw))
    spy.assert_not_called()
    assert not ts._DEAD_SALE_BOOKING_BG_TASKS
    assert sql_log == base_sql, "not one extra query when nothing sold"
    _assert_restore_identical(w, base, what="filled 0")
    assert w.trades[TID]["exits"] == [] and w.trades[TID]["total_pnl"] is None
    assert not [a for a in w.audits if a["event_type"] in BOOKING_EVENTS]
    assert not _booking_pages(w)
    assert _placed(w) == [(3, STOP)]


@pytest.mark.parametrize("avg", [0.0, None])
@pytest.mark.asyncio
async def test_d_shares_but_no_price_writes_nothing_pages_and_leaves_the_restore_alone(avg,
                                                                                         monkeypatch):
    base = _ko_world(broker_qty=3)
    with monkeypatch.context() as m:
        _stub_booking(m)
        await _drive(base, _handle("expired", filled=1.0, avg=avg))
    w = _ko_world(broker_qty=3)
    await _drive(w, _handle("expired", filled=1.0, avg=avg))
    assert w.trades[TID]["exits"] == [] and w.trades[TID]["total_pnl"] is None
    _assert_restore_identical(w, base, what="no price")
    [err] = _audits(w, "full_exit_dead_fill_unpriced_error")
    assert (err["trade_id"], err["order_id"], err["shares"]) == (TID, "sell-q", 1.0), err
    assert _booking_pages(w) == [
        f"📄 PAPER ⚠️ *KO: 1 sh sold before the close order EXPIRED, but the broker gave no price* "
        f"— not recorded; fix trade {TID} by hand."]
    assert not _audits(w, "full_exit_dead_fill_booked")


# ── (6) the failure shapes: an error row + a page, never a raise, never a changed restore ────────

@pytest.mark.parametrize("why", ["not_found_other_account", "no_entry_price", "exception"])
@pytest.mark.asyncio
async def test_failures_leave_an_error_row_and_a_page_and_the_handler_never_raises(why, monkeypatch):
    if why == "not_found_other_account":
        # the event is PAPER but the row belongs to the LIVE book: invariant 3 (every trade query
        # filters on account_mode) means the booking finds nothing and writes nothing
        w = _ko_world(mode="live")
    elif why == "no_entry_price":
        w = _ko_world(entry_price=None)
    else:
        w = _ko_world()

        async def _boom(*a, **k):
            raise RuntimeError("pool exhausted")
        monkeypatch.setattr(om, "book_dead_full_exit_leg", _boom)
    before = _row(w)
    await _drive(w, _handle("expired"))                          # must not raise
    assert w.trades[TID]["exits"] == [] and w.trades[TID]["total_pnl"] == before["total_pnl"]
    [err] = _audits(w, "full_exit_dead_fill_booking_error")
    assert err["trade_id"] == TID and err["order_id"] == "sell-q"
    [page] = _booking_pages(w)
    assert "the books could NOT be updated*" in page and f"fix trade {TID} by hand" in page
    assert not _audits(w, "full_exit_dead_fill_booked")
    # the stop restore still ran (it protects the shares still held)
    assert _placed(w), "the restore must be unaffected"
    assert w.trades[TID]["remaining_shares"] == before["remaining_shares"]


@pytest.mark.asyncio
async def test_a_failing_audit_or_page_inside_the_booking_task_still_never_raises(monkeypatch):
    """Only the BOOKING's own audit rows / pages fail (the restore's must keep working, they protect
    the money): the task swallows the failures and the booking itself still lands."""
    w = _ko_world()
    undo = H._install(w)
    try:
        real_send, real_log = ts.send_telegram_message, ts.log_audit_event

        async def _send(msg, *a, **k):
            if _is_booking_page(str(msg)):
                raise RuntimeError("telegram down")
            return await real_send(msg, *a, **k)

        async def _log(event_type, *a, **k):
            if event_type in BOOKING_EVENTS:
                raise RuntimeError("audit down")
            return await real_log(event_type, *a, **k)
        monkeypatch.setattr(ts, "send_telegram_message", _send)
        monkeypatch.setattr(ts, "log_audit_event", _log)
        await _handle("expired")()
        await _drain()                                           # the task swallowed everything
    finally:
        H._uninstall(undo)
    assert len(w.trades[TID]["exits"]) == 1                      # the booking itself still landed
    assert _placed(w) == [(2, STOP)]


def test_scheduler_never_raises_on_a_hostile_order():
    class _Bad:
        @property
        def filled_qty(self):
            raise RuntimeError("boom")
    ts._schedule_dead_full_exit_booking({"trade_id": 1}, _Bad(), "o", "KO", "expired", "paper")
    ts._schedule_dead_full_exit_booking({"trade_id": 1}, SimpleNamespace(filled_qty="x"), "o",
                                        "KO", "expired", "paper")
    assert not ts._DEAD_SALE_BOOKING_BG_TASKS


# ── (7) a closed row absorbs the leg ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_7_a_closed_row_absorbs_the_leg_and_nothing_else_moves():
    w = _ko_world(status="closed", closed_at="NOW", closed_on=H.TODAY)
    w.trades[TID]["remaining_shares"] = 0
    before = _row(w)
    await _drive(w, _handle("expired"))
    t = w.trades[TID]
    [leg] = t["exits"]
    assert leg["shares"] == 1 and leg["order_id"] == "sell-q"
    assert t["total_pnl"] == pytest.approx(-0.49)
    assert {k for k in before if before[k] != _row(w)[k]} == {"exits", "total_pnl"}
    assert (t["status"], t["closed_at"], t["remaining_shares"]) == ("closed", "NOW", 0)
    assert _placed(w) == [], "a closed row has nothing to protect: no stop"


# ── (e) the double-count paths: the sold shares are counted ONCE ─────────────────────────────────

class _ShareSumConn:
    """`audit_invariants.check_exit_share_sum` runs jsonb SQL the fake pool cannot; this evaluates the
    same predicate (closed, single-attempt, every leg has `shares`, |sum - entry_shares| > 0.001) over
    the fake book so the REAL function and its verdict shape run. (The SQL itself is pinned by
    tests/test_exit_share_double_count_588.py.)"""
    def __init__(self, w):
        self.w = w

    async def fetch(self, sql, *args):
        assert "FROM mi_live_trades t" in sql
        out = []
        for t in self.w.trades.values():
            legs = t["exits"] or []
            total = sum(float(x["shares"]) for x in legs if "shares" in x)
            if (t["status"] == "closed" and (t.get("entry_attempt") or 1) == 1 and t["closed_at"]
                    and legs and all("shares" in x for x in legs)
                    and abs(total - t["entry_shares"]) > 0.001):
                out.append({"id": t["id"], "ticker": t["ticker"], "account_mode": t["account_mode"],
                            "alert_date": t["alert_date"], "entry_shares": t["entry_shares"],
                            "exit_shares": total})
        return out


def _legs_shares(w):
    return sum(float(e["shares"]) for e in w.trades[TID]["exits"])


def _total_matches_legs(w):
    return w.trades[TID]["total_pnl"] == pytest.approx(
        sum(e["pnl"] for e in w.trades[TID]["exits"]))


@pytest.mark.asyncio
async def test_e_a_later_ws_stop_fill_with_no_sync_counts_each_sold_share_once(monkeypatch):
    """No sync between: the 2 shares exit via the restored stop at 85.00 while the books still say 3.
    Row stays OPEN with 1 phantom (identical on base), legs 1@90.36 + 2@85.00, total P&L = truth."""
    _teach_zero_literal(monkeypatch)
    w = _ko_world()
    await _drive(w, _handle("expired"))
    fire = _fire_restored_stop(w, price=85.0)
    await _drive(w, fire)
    t = w.trades[TID]
    assert [(e["shares"], e["price"]) for e in t["exits"]] == [(1, FILL_PX), (2, 85.0)]
    assert _legs_shares(w) == 3
    assert t["total_pnl"] == pytest.approx((FILL_PX - ENTRY) * 1 + (85.0 - ENTRY) * 2)
    assert _total_matches_legs(w)
    assert t["status"] == "filled" and t["remaining_shares"] == 1 and t["stop_order_id"] is None


@pytest.mark.asyncio
async def test_e_sync_heal_then_the_stop_fill_closes_with_legs_equal_to_entry(monkeypatch):
    """Booking, sync heals 3 -> 2, then the restored 2-sh stop fills: the row CLOSES at zero, the
    legs add up to the 3 shares entered (L1 `check_exit_share_sum` passes), total P&L = truth.
    The same run with the booking stubbed (= base) breaches that invariant."""
    async def run(stub):
        w = _ko_world()
        with monkeypatch.context() as m:
            _teach_zero_literal(m)
            if stub:
                _stub_booking(m)
            await _drive(w, _handle("expired"))
            _sync_heal(w)
            await _drive(w, _fire_restored_stop(w, price=85.0))
        return w

    w = await run(stub=False)
    t = w.trades[TID]
    assert t["status"] == "closed" and t["remaining_shares"] == 0
    assert _legs_shares(w) == 3 == t["entry_shares"]
    assert t["total_pnl"] == pytest.approx((FILL_PX - ENTRY) * 1 + (85.0 - ENTRY) * 2)
    ok, body = await inv.check_exit_share_sum(_ShareSumConn(w))
    assert ok, body

    base = await run(stub=True)
    assert _legs_shares(base) == 2 != base.trades[TID]["entry_shares"]
    ok, body = await inv.check_exit_share_sum(_ShareSumConn(base))
    assert not ok and body["count"] == 1, "base breaches the L1 exit-share check; the booking fixes it"


async def _gone_world(monkeypatch, *, heal):
    """KO booked, then the broker is FLAT and the restored stop is FILLED there (its WS event lost)."""
    w = _ko_world()
    with monkeypatch.context() as m:
        _teach_zero_literal(m)
        await _drive(w, _handle("expired"))
        if heal:
            _sync_heal(w)
        stop_id = w.trades[TID]["stop_order_id"]
        order = w.broker_order(stop_id)
        order.update(status="filled", filled_qty=2.0, filled_avg_price=85.0,
                     filled_at="2026-10-01T14:00:00+00:00")
        w.positions.pop("KO", None)
        undo = H._install(w)
        try:
            line = await om._resolve_position_gone(dict(w.trades[TID]), "paper")
        finally:
            H._uninstall(undo)
    return w, line


@pytest.mark.parametrize("heal", [True, False])
@pytest.mark.asyncio
async def test_e_resolve_position_gone_books_only_the_tracked_stop_so_nothing_is_counted_twice(
        heal, monkeypatch):
    w, line = await _gone_world(monkeypatch, heal=heal)
    t = w.trades[TID]
    ids = [e.get("order_id") for e in t["exits"]]
    assert ids.count("sell-q") == 1 and len(ids) == 2, ids       # the dead sale once, the stop once
    assert t["total_pnl"] == pytest.approx((FILL_PX - ENTRY) * 1 + (85.0 - ENTRY) * 2)
    assert _total_matches_legs(w)
    assert "missed stop fill booked" in line
    if heal:
        assert t["status"] == "closed" and _legs_shares(w) == 3 == t["entry_shares"]
        ok, _ = await inv.check_exit_share_sum(_ShareSumConn(w))
        assert ok
    else:
        # books said 3 (a phantom 1 remains, as on base): open, legs still add up once each
        assert t["status"] == "filled" and t["remaining_shares"] == 1 and _legs_shares(w) == 3


# ── (3) the writer touches exits + total_pnl and NOTHING else ───────────────────────────────────

def test_3_the_deploy_gate_allows_this_writer_exits_and_total_pnl_only():
    import scripts.audit_column_writes as acw
    sites = [s for s in acw.audit_file(ROOT / "agents/market_intelligence/broker/order_manager.py")
             if s["function"] == "_book_dead_full_exit_leg_locked"]
    assert [(s["kind"], s["columns"]) for s in sites] == [("UPDATE", ["exits", "total_pnl"])]
    me = "order_manager._book_dead_full_exit_leg_locked"
    assert {col for col, fns in acw.ALLOWED_WRITERS.items() if me in fns} == {"exits", "total_pnl"}
    for col in ("remaining_shares", "status", "closed_at", "stop_price", "stop_order_id",
                "partial_taken", "breakeven_active", "hard_stop", "entry_shares"):
        assert me not in acw.ALLOWED_WRITERS[col], col
    assert acw.main("check") == 0


@pytest.mark.asyncio
async def test_3_the_writer_issues_one_select_and_one_update_of_exits_and_total_pnl_under_the_lock(
        monkeypatch, sql_log):
    """Behaviour, not source text: drive the writer and read what it ISSUED. The lock brackets the
    read and the write; the only UPDATE sets exactly exits + total_pnl; no broker call, no audit row,
    no page happens inside it (the caller reports after the lock is released)."""
    import scripts.audit_column_writes as acw
    w = _ko_world()
    real_lock = om._trade_advisory_lock

    @contextlib.asynccontextmanager
    async def _spy_lock(trade_id):
        sql_log.append(("LOCK", trade_id))
        async with real_lock(trade_id):
            yield
        sql_log.append(("UNLOCK", trade_id))
    monkeypatch.setattr(om, "_trade_advisory_lock", _spy_lock)

    [res] = await _drive(w, lambda: om.book_dead_full_exit_leg(
        TID, "paper", "sell-q", 1, FILL_PX, "sma_trail_stop", "dead_order:expired"))
    assert res["outcome"] == "booked"
    issued = [(k, q) for k, q in sql_log if "pg_advisory" not in str(q)]
    kinds = [k if k in ("LOCK", "UNLOCK") else q.split()[0] for k, q in issued]
    assert kinds == ["LOCK", "SELECT", "UPDATE", "UNLOCK"], issued
    [update] = [q for k, q in issued if k not in ("LOCK", "UNLOCK") and q.startswith("UPDATE")]
    cols = acw.extract_columns_from_set_clause(update.split(" SET ", 1)[1].split(" WHERE ", 1)[0])
    assert cols == {"exits", "total_pnl"}
    # dual-account invariant 3: both statements filter on account_mode
    assert all("account_mode = $" in q for k, q in issued
               if k not in ("LOCK", "UNLOCK") and "mi_live_trades" in q), issued
    assert w.calls == [] and w.pages == [] and w.audits == [], "no I/O inside the writer"


@pytest.mark.asyncio
async def test_3_the_writer_is_scoped_to_the_account_mode_of_the_event():
    w = _ko_world(mode="paper")
    before = _row(w)
    [res] = await _drive(w, lambda: om.book_dead_full_exit_leg(
        TID, "live", "sell-q", 1, FILL_PX, "sma_trail_stop", "dead_order:expired"))
    assert res == {"outcome": "not_found"} and _row(w) == before


@pytest.mark.asyncio
async def test_3_no_entry_price_writes_nothing_never_a_zero_basis_leg():
    w = _ko_world(entry_price=None)
    before = _row(w)
    [res] = await _drive(w, lambda: om.book_dead_full_exit_leg(
        TID, "paper", "sell-q", 1, FILL_PX, "sma_trail_stop", "dead_order:expired"))
    assert res["outcome"] == "no_entry_price" and _row(w) == before


def test_3_preflight_registers_the_update():
    import scripts.preflight_db_updates as pf
    [sql] = [s for lbl, s in pf.TRADE_LIFECYCLE_UPDATES if "_book_dead_full_exit_leg_locked" in lbl]
    assert re.sub(r"\s+", " ", sql).strip() == (
        "UPDATE mi_live_trades SET exits = $2::jsonb, total_pnl = $3 WHERE id = $1 AND account_mode = $4")


# ── the writer itself ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_writer_recomputes_total_from_the_legs_never_adds():
    """total_pnl is recomputed = sum(leg pnl), so a stale total (e.g. a legacy row where it drifted)
    is corrected rather than carried — the invariant every other writer of this column keeps."""
    w = _ko_world(total_pnl=999.0, exits=[{"shares": 1, "price": 95.0, "pnl": 5.0, "order_id": "x",
                                           "reason": "partial_profit"}])
    [res] = await _drive(w, lambda: om.book_dead_full_exit_leg(
        TID, "paper", "sell-q", 1, FILL_PX, "sma_trail_stop", "dead_order:expired"))
    assert res["outcome"] == "booked" and res["total_pnl_before"] == 999.0
    assert w.trades[TID]["total_pnl"] == pytest.approx(5.0 - 0.49)
    assert len(w.trades[TID]["exits"]) == 2


# ── (9) the safeguards count the booked leg (existing rulings) ───────────────────────────────────

@pytest.mark.asyncio
async def test_9_the_daily_loss_gate_counts_a_losing_dead_leg_dated_today_and_never_a_profit():
    w = _ko_world()
    await _drive(w, _handle("expired"))
    [leg] = w.trades[TID]["exits"]
    today = datetime.fromisoformat(leg["time"]).astimezone(ET).date()
    rows = [{"exits": w.trades[TID]["exits"]}]
    assert lt._partial_losses_realized_on(rows, today) == pytest.approx(-0.49)

    # a PROFIT dead leg counts nothing and offsets nothing
    w2 = _ko_world()
    await _drive(w2, _handle("expired", avg=95.0))
    today2 = datetime.fromisoformat(w2.trades[TID]["exits"][0]["time"]).astimezone(ET).date()
    assert w2.trades[TID]["exits"][0]["pnl"] > 0
    assert lt._partial_losses_realized_on([{"exits": w2.trades[TID]["exits"]}], today2) == 0.0
