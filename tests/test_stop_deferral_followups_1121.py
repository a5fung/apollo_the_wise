"""Follow-ups to the 2026-11-21 after-hours stop deferrals (operator "Let's do it", 2026-11-21).
Bug-fix class: no stop level, share count, raise-only rule or safeguard changed.

(a) A stop RAISE the broker refused after hours (`move_stop_price_only` wrote
    `stop_raise_deferred_extended_hours` and left the old stop resting) used to be retried only by
    the next 16:45 run — itself after hours. The 09:35 `morning_stop_refresh` now makes that raise
    in the regular session, to the level RECORDED on the deferral row. Still refused there → the
    in-session path, unchanged: `update_stop` → #687 ruling (iii), the shares are sold at market.
(b) The 17:00 / 19:00 / 21:10 "UNPROTECTED" pages name the reason when the position has no stop
    because a stop was refused against an after-hours price. Same pages, same slots.
(c) The breakout stop-to-the-fill in `finalize_partial_exit` is left as it is: it runs when a
    third FILLS, and no order here can fill outside the regular session (pinned below).

Clock: the #687 harness's fake world (`World.regular_session`), as the other 11-21 tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import agents.market_intelligence.scheduler as sched
import tests._convergence_687_harness as H
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from tests._convergence_687_harness import BREACH, World, _bstop, _position, _trade

HELD = ('{"available":"0","code":40310000,"existing_qty":"10","held_for_orders":"10",'
        '"message":"insufficient qty available for order (requested: 10, available: 0)"}')
RAISE_DEFERRED = "stop_raise_deferred_extended_hours"
SALE_DEFERRED = "stop_breach_sale_deferred_extended_hours"


async def _drive(w, *steps):
    import sys

    import agents.market_intelligence.broker as broker_pkg
    name = "agents.market_intelligence.broker.alpaca_client"
    before = (getattr(broker_pkg, "alpaca_client", None), sys.modules.get(name))
    broker_pkg.alpaca_client = sys.modules[name] = om.alpaca
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)
        broker_pkg.alpaca_client, sys.modules[name] = before


def _methods(w) -> list[str]:
    return [c["method"] for c in w.calls]


def _calls(w, method) -> list[dict]:
    return [c["args"] for c in w.calls if c["method"] == method]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _morning():
    return lt._stop_refresh(include_same_day=False, label="Morning")


def _post_close():
    return lt._stop_refresh(include_same_day=True, label="post-close")


def _session(w, is_open):
    async def _set():
        w.regular_session = is_open
    return _set


def _raise_deferred_at_1645(target=61.5, source="trail") -> World:
    """KOD, 10 sh, stop resting at $58. After hours the trail raise to `target` is refused as
    above the market — the REAL deferral, written by `move_stop_price_only` itself."""
    w = World()
    w.regular_session = False
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.replace_errors = [Exception(BREACH)]
    w._deferral = lambda: om.move_stop_price_only(401, target, stop_source=source)
    return w


def _retried(w) -> list[dict]:
    return [r["deferred_raise_retried"] for r in _audits(w, "stop_refresh_ran")
            if "deferred_raise_retried" in r]


# ── (a) the deferred raise is made in the regular session ─────────────────────────────────────

@pytest.mark.asyncio
async def test_a_raise_deferred_after_hours_is_made_at_the_morning_refresh():
    w = _raise_deferred_at_1645()
    out, _, n = await _drive(w, w._deferral, _session(w, True), _morning)
    assert out is False and len(_audits(w, RAISE_DEFERRED)) == 1
    # ONE more replace, at the recorded level, the share count not sent; nothing cancelled or sold
    assert _methods(w).count("replace_order") == 2
    assert _calls(w, "replace_order")[1]["stop_price"] == 61.5
    assert _calls(w, "replace_order")[1]["qty"] is None
    for forbidden in ("cancel_order", "place_stop_order", "close_position"):
        assert forbidden not in _methods(w), (forbidden, w.calls)
    t = w.trades[401]
    assert t["stop_price"] == 61.5 and t["stop_order_id"] != "stop-1", t
    assert w.broker_order(t["stop_order_id"])["stop_price"] == 61.5
    [moved] = _audits(w, "stop_updated")
    assert moved["mechanism"] == "price_only_replace" and moved["stop_source"] == "trail"
    assert _retried(w) == [[{"ticker": "KOD", "trade_id": 401, "from": 58.0, "target": 61.5,
                            "stop_source": "trail", "outcome": "raised"}]]
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["already_covered"] == ["KOD"] and ran["unprotected"] == [] and n == 0
    assert w.pages == [], w.pages


@pytest.mark.asyncio
async def test_a_raise_still_refused_in_session_sells_as_a_refused_raise_always_did():
    """Stated plainly: in the regular session a raise refused as above the market follows the
    in-session path — `update_stop` cancels, two refused placements, #687 ruling (iii) sells."""
    w = _raise_deferred_at_1645()

    async def _still_below():
        w.regular_session = True
        w.replace_errors = [Exception(BREACH)]
        w.place_errors = [Exception(BREACH) for _ in range(6)]

    await _drive(w, w._deferral, _still_below, _morning)
    assert [c["qty"] for c in _calls(w, "close_position")] == [10]
    [sale] = _audits(w, "stop_breach_market_sale")
    assert sale["site"] == "order_manager.update_stop"
    assert _retried(w)[0][0]["outcome"] == "sold_at_market"
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["sold_at_market"] == ["KOD"] and ran["unprotected"] == []
    assert not any("No stop on" in p for p in w.pages), w.pages
    assert len([p for p in w.pages if "Price already below the stop" in p]) == 1, w.pages


@pytest.mark.asyncio
async def test_the_retry_replays_the_latest_recorded_level_only():
    """Two evenings deferred: the newer row's level is the one made — no trail is recomputed."""
    w = _raise_deferred_at_1645()

    async def _second_evening():
        w.replace_errors = [Exception(BREACH)]
        return await om.move_stop_price_only(401, 62.25, stop_source="trail")

    await _drive(w, w._deferral, _second_evening, _session(w, True), _morning)
    assert len(_audits(w, RAISE_DEFERRED)) == 2
    assert [c["stop_price"] for c in _calls(w, "replace_order")] == [61.5, 62.25, 62.25]
    assert w.trades[401]["stop_price"] == 62.25


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh, in_session", [(_post_close, False), (_morning, False)])
async def test_no_retry_outside_the_regular_session(refresh, in_session):
    """The 16:20 pass is after hours, and the 09:35 cron also fires on a market holiday: neither
    retries (it would only be refused and deferred again)."""
    w = _raise_deferred_at_1645()
    await _drive(w, w._deferral, _session(w, in_session), refresh)
    assert _methods(w).count("replace_order") == 1, w.calls
    assert not _retried(w) and w.trades[401]["stop_price"] == 58.0
    assert _audits(w, "stop_refresh_ran")[0]["already_covered"] == ["KOD"]


@pytest.mark.asyncio
async def test_the_post_close_pass_never_retries_even_in_session():
    w = _raise_deferred_at_1645()
    await _drive(w, w._deferral, _session(w, True), _post_close)
    assert _methods(w).count("replace_order") == 1 and not _retried(w)


@pytest.mark.asyncio
async def test_a_later_successful_stop_move_supersedes_the_deferral():
    """The deferral must be the trade's LATEST stop-move event. Here a smaller raise went through
    afterwards; the older, higher level is not replayed."""
    w = _raise_deferred_at_1645()

    async def _a_later_move():
        return await om.move_stop_price_only(401, 59.0, stop_source="breakeven")

    _, later, _, _ = await _drive(w, w._deferral, _a_later_move, _session(w, True), _morning)
    assert later is True and w.trades[401]["stop_price"] == 59.0
    assert [c["stop_price"] for c in _calls(w, "replace_order")] == [61.5, 59.0]
    assert not _retried(w)


@pytest.mark.asyncio
async def test_no_retry_when_the_stop_is_already_at_or_above_the_recorded_level():
    w = _raise_deferred_at_1645()

    async def _stop_is_higher_now():
        w.regular_session = True
        w.trades[401]["stop_price"] = 61.5
        w.broker_order("stop-1")["stop_price"] = 61.5

    await _drive(w, w._deferral, _stop_is_higher_now, _morning)
    assert _methods(w).count("replace_order") == 1 and not _retried(w)


@pytest.mark.asyncio
async def test_the_broker_stop_price_also_bounds_the_retry():
    """Raise-only against the BROKER too: the row says $58 but the live stop already rests higher."""
    w = _raise_deferred_at_1645()

    async def _broker_is_higher():
        w.regular_session = True
        w.broker_order("stop-1")["stop_price"] = 62.0

    await _drive(w, w._deferral, _broker_is_higher, _morning)
    assert _methods(w).count("replace_order") == 1 and not _retried(w)


@pytest.mark.asyncio
async def test_a_book_with_no_deferral_makes_no_broker_write_at_the_morning_refresh():
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    await _drive(w, _morning)
    assert set(_methods(w)) == {"get_order"}, w.calls
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["already_covered"] == ["KOD"]
    assert "deferred_raise_retried" not in ran and "deferred_raise_read_error" not in ran


@pytest.mark.asyncio
async def test_an_unreadable_log_skips_the_retry_and_never_the_refresh(monkeypatch):
    w = _raise_deferred_at_1645()

    async def _boom(conn):
        raise RuntimeError("audit log unreadable")

    monkeypatch.setattr(lt, "_deferred_stop_raises", _boom)
    await _drive(w, w._deferral, _session(w, True), _morning)
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["already_covered"] == ["KOD"] and "audit log unreadable" in ran["deferred_raise_read_error"]
    assert _methods(w).count("replace_order") == 1


@pytest.mark.asyncio
async def test_a_retry_that_leaves_no_stop_is_paged_as_any_unprotected_position():
    """The replace is refused for held shares, so `update_stop` cancels the old stop — and then
    cannot place the new one. The refresh pages it, as it does for any position it cannot protect."""
    w = _raise_deferred_at_1645()

    async def _held_then_unplaceable():
        w.regular_session = True
        w.replace_errors = [Exception(HELD)]
        w.place_errors = [Exception(HELD) for _ in range(8)]

    await _drive(w, w._deferral, _held_then_unplaceable, _morning)
    assert _retried(w)[0][0]["outcome"] == "not_raised_no_stop"
    assert _audits(w, "stop_refresh_ran")[0]["unprotected"] == ["KOD"]
    assert any("No stop on KOD" in p for p in w.pages), w.pages
    assert "close_position" not in _methods(w)


@pytest.mark.asyncio
async def test_a_retry_refused_by_the_raise_only_floor_leaves_the_old_stop_and_no_page():
    """The broker's stop went up between the refresh's read and the move: nothing to raise. The
    old stop rests, the position is covered, nobody is paged."""
    w = _raise_deferred_at_1645()
    seen = {"n": 0}

    async def _in_session():
        w.regular_session = True

    await _drive(w, w._deferral, _in_session)
    real = lt._deferred_raise_target

    def _then_the_broker_moves(deferral, stop_price, order):
        target = real(deferral, stop_price, order)
        if target is not None:
            seen["n"] += 1
            w.broker_order("stop-1")["stop_price"] = 63.0
        return target

    lt._deferred_raise_target = _then_the_broker_moves
    try:
        await _drive(w, _morning)
    finally:
        lt._deferred_raise_target = real
    assert seen["n"] == 1
    assert w.broker_order("stop-1")["status"] in H.LIVE_ORDER_STATUSES
    assert "close_position" not in _methods(w)
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["unprotected"] == [] and not any("No stop on" in p for p in w.pages), (ran, w.pages)


@pytest.mark.asyncio
async def test_the_deferral_row_already_records_the_target_and_its_source():
    """(a) replays `new_stop_price` + `stop_source` from the row the real deferral writes, and the
    refresh's read finds it as that trade's latest stop-move event."""
    w = _raise_deferred_at_1645(target=61.5, source="depth_trail")

    async def _read():
        return await lt._deferred_stop_raises(H.FakeConn(w))

    _, found = await _drive(w, w._deferral, _read)
    [row] = _audits(w, RAISE_DEFERRED)
    assert (row["new_stop_price"], row["stop_source"]) == (61.5, "depth_trail")
    assert list(found) == [401] and found[401]["new_stop_price"] == 61.5


# ── (b) the evening pages name the reason ─────────────────────────────────────────────────────

def _stop_refused_after_hours() -> World:
    """A live position whose DAY stop expired at the close; the 16:20 refresh's re-placement is
    refused against an after-hours price → no sale, no stop (the real `update_stop` deferral,
    which also writes `stop_update_failed` + `naked_position_detected` after its deferral row)."""
    w = World()
    w.regular_session = False
    _trade(w)
    _position(w, "KOD", 10, 10)
    _bstop(w, "stop-1", "KOD", 10, 58.0, status="expired")
    w.place_errors = [Exception(BREACH) for _ in range(40)]
    return w


def _slot(name):
    return lambda: sched._coverage_watch_job(name)


def _unprotected_pages(w) -> list[str]:
    return [p for p in w.pages if "UNPROTECTED" in p]


@pytest.mark.asyncio
@pytest.mark.parametrize("slot, headline", [
    ("post_close", "UNPROTECTED AFTER THE CLOSE"),
    ("late", "STILL UNPROTECTED THIS EVENING"),
    ("evening", "STILL UNPROTECTED AFTER THE 9 PM REPAIR"),
])
async def test_the_evening_page_names_the_after_hours_deferral(slot, headline):
    w = _stop_refused_after_hours()
    await _drive(w, _post_close, _slot(slot))
    assert _audits(w, SALE_DEFERRED) and _audits(w, "stop_update_failed")
    [page] = _unprotected_pages(w)                       # still paged, once per slot
    assert headline in page
    assert "• KOD: holds 10 sh, live stop covers 0 sh\n  Why: " in page
    assert om.stop_breach_deferred_note(58.0) in page
    assert "NO sale was queued" in page and "sold at market then" in page
    assert "close_position" not in _methods(w)


@pytest.mark.asyncio
async def test_a_gap_with_no_deferral_pages_exactly_as_before():
    """The harness's pinned s19 world: a genuine gap, the repair refused for another reason."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    w.place_errors = [Exception("insufficient qty available")]
    await _drive(w, _slot("post_close"))
    [page] = _unprotected_pages(w)
    assert page == (
        "🚨 *UNPROTECTED AFTER THE CLOSE*\n"
        "• KOD: holds 10 sh, live stop covers 0 sh\n\n"
        "Extended hours are still trading, and the automatic repair above did not hold.\n"
        "`/syncnow live` re-runs the same repair now.")


def _seed(w, event_type, **detail):
    w.audits.append({"event_type": event_type, "summary": "KOD", "created_at": H.NOW_UTC,
                     "detail": json.dumps({"trade_id": 401, "ticker": "KOD", **detail})})


def _bare_gap() -> World:
    w = World()
    w.regular_session = False
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    return w


@pytest.mark.asyncio
async def test_the_watchdogs_deferral_is_named_too():
    w = _bare_gap()
    _seed(w, "stop_ack_deferred_extended_hours", stop_target=57.5)
    await _drive(w, _slot("evening"))
    [page] = _unprotected_pages(w)
    assert f"  Why: {om.stop_breach_deferred_note(57.5)}" in page


@pytest.mark.asyncio
@pytest.mark.parametrize("later", ["stop_coverage_repaired", "stop_updated", "stop_ack_timeout_remediated"])
async def test_a_stop_placed_after_the_deferral_ends_it(later):
    """A stop went on after the deferral and is gone again: the deferral is not why."""
    w = _bare_gap()
    _seed(w, SALE_DEFERRED, stop_price=58.0, site="order_manager.update_stop")
    _seed(w, later, new_stop_id="stop-9")
    await _drive(w, _slot("evening"))
    [page] = _unprotected_pages(w)
    assert "Why:" not in page and "• KOD: holds 10 sh" in page


@pytest.mark.asyncio
async def test_a_deferred_raise_is_never_given_as_the_reason():
    """`stop_raise_deferred_extended_hours` leaves the OLD stop resting — "no stop is resting"
    would be false for it, so it is not a reason for a gap."""
    w = _bare_gap()
    _seed(w, RAISE_DEFERRED, new_stop_price=61.5, old_stop_price=58.0)
    await _drive(w, _slot("evening"))
    [page] = _unprotected_pages(w)
    assert "Why:" not in page


@pytest.mark.asyncio
async def test_another_trades_deferral_is_not_borrowed():
    w = _bare_gap()
    w.audits.append({"event_type": SALE_DEFERRED, "summary": "ZZZ", "created_at": H.NOW_UTC,
                     "detail": json.dumps({"trade_id": 999, "ticker": "ZZZ", "stop_price": 12.0})})
    await _drive(w, _slot("evening"))
    assert "Why:" not in _unprotected_pages(w)[0]


@pytest.mark.asyncio
async def test_an_unreadable_log_still_pages_without_the_reason(monkeypatch):
    w = _stop_refused_after_hours()

    async def _run():
        real_pool = om.get_pool

        async def _no_pool_for_the_reason(*a, **k):
            raise RuntimeError("pool gone")

        real = om.stop_deferral_reasons

        async def _reasons(ids):
            om.get_pool = _no_pool_for_the_reason
            try:
                return await real(ids)
            finally:
                om.get_pool = real_pool

        om.stop_deferral_reasons = _reasons
        try:
            await sched._coverage_watch_job("evening")
        finally:
            om.stop_deferral_reasons = real

    await _drive(w, _post_close, _run)
    [page] = _unprotected_pages(w)
    assert "• KOD: holds 10 sh, live stop covers 0 sh" in page and "Why:" not in page
    assert not any("[job failure]" in p for p in w.pages), w.pages


# ── (c) left as it is — the premise, pinned ───────────────────────────────────────────────────

def test_no_order_here_can_fill_outside_the_regular_session():
    """`finalize_partial_exit`'s breakout stop-to-the-fill runs when a third FILLS. It still calls
    `update_stop` on a refused replace because no order this system places is eligible to fill
    outside the regular session. If an extended-hours order is ever added, that step needs the
    after-hours rule `move_stop_price_only` has — this test is the reminder."""
    broker = Path(om.__file__).parent
    offenders = [p.name for p in sorted(broker.glob("*.py"))
                 if "extended_hours=" in p.read_text() or "extended_hours:" in p.read_text()]
    assert offenders == [], offenders
