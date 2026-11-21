"""PLAN.md #728 (2026-11-21) — two bug fixes on the stop path. Same stop price, same share count, raise-only.

A. PRICE-ONLY STOP MOVES go through one atomic price-only `alpaca.replace_order` on the live stop
   (`order_manager.move_stop_price_only` -> `_replace_stop_price_only`), not `update_stop`'s
   cancel-then-place. 90 days of prod to 11-18: 43 live first-attempt refusals (the cancelled stop
   still held the shares) and 9 live `stop_update_failed` (no stop until the next pass).
   Per caller, in the #687 harness's fake world (every broker call is recorded):
     * the 16:45 job's four moves — the trail raise, the depth stop, the breakout stop-to-the-fill
       on a later day and on the breakout day — and the stop refresh: ONE `replace_order` with the
       share count NOT sent, and no `cancel_order` / `place_stop_order`;
     * `update_stop` still runs, unchanged, whenever nothing was changed at the broker: no live stop
       (the re-protect), a share count that is not the rest of the position, not a raise, or a
       replace the broker PROVABLY refused;
     * a raise the broker refuses as "above the market" still reaches #687 ruling (iii) through
       `update_stop` — sold in the regular session, deferred outside it (operator ruling 11-20);
     * after an ACCEPTED replace `update_stop` is never called (unconfirmed / dead -> paged).

B. Operator ruling 2026-11-20 (1): the stop-ACK watchdog's fallback stop goes at the trade's own
   LAST stop (the row's `stop_price`, never below the last level the broker held), not `orb_low`;
   `orb_low` only when the row has no stop price, and the audit row says which.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from tests._convergence_687_harness import (
    BREACH,
    TODAY,
    World,
    _bars,
    _bstop,
    _mirror,
    _position,
    _trade,
)

HELD = ('{"available":"0","code":40310000,"existing_qty":"10","held_for_orders":"10",'
        '"message":"insufficient qty available for order (requested: 10, available: 0)"}')
RISING_BAR = {"o": 74.0, "h": 76.0, "l": 73.5, "c": 75.0, "v": 2_000_000}


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


def _assert_one_price_only_replace(w, *, price, qty=10, old_id="stop-1"):
    """THE DoD check: the move was one replace at `price`, the share count not sent — and nothing
    was cancelled, placed or sold."""
    for forbidden in ("cancel_order", "place_stop_order", "close_position"):
        assert forbidden not in _methods(w), (forbidden, w.calls)
    [rep] = _calls(w, "replace_order")
    assert rep["order_id"] == old_id and rep["stop_price"] == price, rep
    assert rep["qty"] is None and rep["limit_price"] is None, "PRICE-ONLY: the share count is never sent"
    assert rep["client_order_id"], "invariant 1: a mode-bound client order id at every submission"
    # the broker book: the old stop consumed, ONE live stop, same share count, the new price
    live = [o for o in w.broker_orders if o["status"] in H.LIVE_ORDER_STATUSES and o["type"] == "stop"]
    assert [(o["qty"], o["stop_price"]) for o in live] == [(float(qty), price)], w.broker_orders
    assert w.broker_order(old_id)["status"] == "replaced"
    # the books follow the broker; the positive verify-live observable is written
    t = w.trades[401]
    assert t["stop_order_id"] == live[0]["id"] and t["stop_price"] == price, t
    [row] = _audits(w, "stop_updated")
    assert row["mechanism"] == "price_only_replace" and row["new_stop_price"] == price
    assert (row["old_stop_id"], row["new_stop_id"]) == (old_id, live[0]["id"])
    for quiet in ("stop_update_started", "stop_update_retry_triggered", "stop_update_failed",
                  "stop_price_replace_fallback"):
        assert not _audits(w, quiet), (quiet, w.audits)


def _open_trade(w, **over):
    kw = dict(stop_price=58.0, hold_days=8, running_closes=[70.0] * 8, partial_taken=True,
              breakeven_active=True, alert_date=date(2026, 9, 24))
    kw.update(over)
    _trade(w, **kw)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    _bars(w, RISING_BAR)
    return w


def _job():
    return lambda: lt.update_open_positions_live(TODAY)


# ══════════════════════════════════════════════════════════════════════════════════════════
# A. one test per caller — a price-only move never cancels and never places
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_1645_trail_raise_is_one_price_only_replace():
    """`update_open_positions_live`, the trail branch (the line 58.00 -> 70.50 on a LIVE trade)."""
    w = _open_trade(World())
    [out] = await _drive(w, _job())
    assert out == [{"ticker": "KOD", "action": "updated", "effective_stop": 70.5, "hold_days": 12}]
    _assert_one_price_only_replace(w, price=70.5)
    assert w.pages == [], "a confirmed move is silent, as a first-attempt update_stop success was"
    assert _audits(w, "stop_updated")[0]["account_mode"] == "live"


@pytest.mark.asyncio
async def test_1645_depth_stop_raise_is_one_price_only_replace():
    """`update_open_positions_live`, the depth branch (`depth_trail`)."""
    w = _open_trade(World(), exit_rule="depth")
    await _drive(w, _job())
    [rep] = _calls(w, "replace_order")
    _assert_one_price_only_replace(w, price=rep["stop_price"])
    assert 58.0 < rep["stop_price"] < 70.5, "one ADR20 under the line — the depth level, unchanged"
    assert _audits(w, "stop_updated")[0]["stop_source"] == "depth_trail"


@pytest.mark.asyncio
async def test_1645_breakout_stop_to_the_fill_on_a_later_day_is_one_price_only_replace():
    """`update_open_positions_live`, the breakout (paper) branch on a later session: after a third
    sold, a stop still under the fill is lifted to the fill."""
    w = _open_trade(World(), hold_days=3, running_closes=[70.0] * 3, exit_rule="breakout_pp",
                    signal_type="breakout_v1", account_mode="paper")
    await _drive(w, _job())
    _assert_one_price_only_replace(w, price=60.0)
    assert _audits(w, "stop_updated")[0]["stop_source"] == "breakeven"


@pytest.mark.asyncio
async def test_1645_breakout_stop_to_the_fill_on_the_breakout_day_is_one_price_only_replace():
    """`update_open_positions_live`, the breakout-day backstop (the day the guard below it skips)."""
    w = _open_trade(World(), hold_days=0, running_closes=[], exit_rule="breakout_pp",
                    signal_type="breakout_v1", account_mode="paper", alert_date=TODAY)
    await _drive(w, _job())
    _assert_one_price_only_replace(w, price=60.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("label, same_day", [("Post-close", True), ("Morning", False)])
async def test_stop_refresh_moves_a_live_stop_by_one_price_only_replace(label, same_day):
    """`_stop_refresh` re-places only a stop that is not new/accepted/held. When that stop is still
    LIVE at the broker (another working status) and under the row's stop price, the move is the
    same price-only replace. (Its ordinary case — a DEAD stop — is the next test.)"""
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 57.0, status="accepted_for_bidding")
    [n] = await _drive(w, lambda: lt._stop_refresh(include_same_day=same_day, label=label))
    assert n == 1
    _assert_one_price_only_replace(w, price=58.0)
    assert w.pages == []
    assert _audits(w, "stop_refresh_ran")[0]["unprotected"] == []


@pytest.mark.asyncio
async def test_stop_refresh_after_a_dead_stop_is_still_update_stops_re_protect():
    """NOT a price-only move: the DAY stop expired, so there is nothing live to replace — no
    `replace_order`; `update_stop` places the stop at the row's price, as before #728."""
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 10)
    _bstop(w, "stop-1", "KOD", 10, 58.0, status="expired")
    [n] = await _drive(w, lambda: lt._stop_refresh(include_same_day=True, label="Post-close"))
    assert n == 1 and "replace_order" not in _methods(w)
    [placed] = _calls(w, "place_stop_order")
    assert (placed["qty"], placed["stop_price"]) == (10, 58.0)
    assert not _audits(w, "stop_price_replace_fallback"), "the routine re-protect writes no extra row"
    assert _audits(w, "stop_updated") and "mechanism" not in _audits(w, "stop_updated")[0]


def test_the_tracker_cannot_reach_update_stop_at_all():
    """The population, by construction: `live_tracker` does not hold the name `update_stop`, so no
    stop move there can cancel-then-place directly — each goes through `move_stop_price_only`
    (the five call sites are each driven above)."""
    assert not hasattr(lt, "update_stop")
    assert lt.move_stop_price_only is om.move_stop_price_only


# ══════════════════════════════════════════════════════════════════════════════════════════
# A. the semantics that must not change
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_trail_raise_never_arms_the_breakeven_flag():
    """The confirmed-move write is pointer + price ONLY (`_mark_stop_replaced`). The breakout
    precedent's writer also sets `breakeven_active`; a trail raise must not."""
    w = World()
    _trade(w, stop_price=58.0)                    # breakeven_active False
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is True
    _assert_one_price_only_replace(w, price=61.5)
    assert w.trades[401]["breakeven_active"] is False


@pytest.mark.asyncio
async def test_not_a_raise_changes_nothing_and_update_stops_floor_records_it():
    """Raise-only against the BROKER stop: no replace, no cancel, no placement."""
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 62.0)          # the broker already holds a higher stop
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is False
    assert not ({"replace_order", "cancel_order", "place_stop_order"} & set(_methods(w))), w.calls
    assert _audits(w, "stop_update_aborted")[0]["reason"] == "raise_only_floor"
    assert w.broker_order("stop-1")["status"] == "new" and w.trades[401]["stop_price"] == 58.0


@pytest.mark.asyncio
async def test_a_share_count_change_still_uses_cancel_then_place():
    """Scope = price-only moves. With a third queued to sell, the stop must shrink to the rest —
    the broker cannot change a stop's share count in place, so `update_stop` runs as before."""
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    _mirror(w, "sell-p", 401, "KOD", "partial_exit", 3)
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is True and "replace_order" not in _methods(w)
    assert "cancel_order" in _methods(w)
    [placed] = _calls(w, "place_stop_order")
    assert (placed["qty"], placed["stop_price"]) == (7, 61.5)
    assert _audits(w, "stop_price_replace_fallback")[0]["replace_skipped"] == "stop_qty_not_the_rest"


@pytest.mark.asyncio
async def test_a_provably_refused_replace_falls_back_to_update_stop():
    """The broker refuses the replace and the old stop reads back live at its old price — nothing
    changed, so today's cancel-then-place runs and its result is returned."""
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.replace_errors = [Exception(HELD)]
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is True
    assert _methods(w).count("replace_order") == 1 and "cancel_order" in _methods(w)
    assert [(c["qty"], c["stop_price"]) for c in _calls(w, "place_stop_order")] == [(10, 61.5)]
    assert _audits(w, "stop_price_replace_fallback")[0]["replace_skipped"] == "replace_refused:Exception"
    assert w.trades[401]["stop_price"] == 61.5


# ── #687 ruling (iii) is still reached IN SESSION; after hours a refused raise keeps the old stop ──

def _refused_through_the_price(*, in_session):
    w = World()
    w.regular_session = in_session
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.replace_errors = [Exception(BREACH)]                    # the replace: "stop price must be less than …"
    w.place_errors = [Exception(BREACH) for _ in range(6)]    # and so is every placement after it
    return w


@pytest.mark.asyncio
async def test_a_replace_refused_as_above_the_market_still_sells_in_the_regular_session():
    w = _refused_through_the_price(in_session=True)
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is om.STOP_SOLD_AT_MARKET
    assert [c["qty"] for c in _calls(w, "close_position")] == [10]
    [sale] = _audits(w, "stop_breach_market_sale")
    assert sale["site"] == "order_manager.update_stop", "the SAME ruling (iii) site as before #728"
    assert len([p for p in w.pages if "Price already below the stop" in p]) == 1, w.pages
    # the order of events: the refused replace, then update_stop's cancel + two refused placements
    m = [x for x in _methods(w) if x in ("replace_order", "cancel_order", "place_stop_order", "close_position")]
    assert m == ["replace_order", "cancel_order", "place_stop_order", "place_stop_order", "close_position"]


def _old_stop_still_resting(w, out):
    """Operator 2026-11-21: after hours a refused RAISE leaves the OLD stop resting — nothing
    cancelled, placed or sold, and the row still names the resting stop at its price."""
    assert out is False
    for forbidden in ("cancel_order", "place_stop_order", "close_position"):
        assert forbidden not in _methods(w), (forbidden, w.calls)
    assert _methods(w).count("replace_order") == 1
    old = w.broker_order("stop-1")
    assert old["status"] in H.LIVE_ORDER_STATUSES and old["stop_price"] == 58.0, old
    t = w.trades[401]
    assert t["stop_order_id"] == "stop-1" and t["stop_price"] == 58.0, t
    [row] = _audits(w, "stop_raise_deferred_extended_hours")
    assert (row["new_stop_price"], row["old_stop_price"], row["old_stop_id"]) == (61.5, 58.0, "stop-1")
    assert row["broker_stop_price"] == 58.0 and "must be less than" in row["stop_error"]
    for quiet in ("stop_update_started", "stop_update_failed", "naked_position_detected",
                  "stop_breach_sale_deferred_extended_hours", "stop_breach_market_sale",
                  "stop_price_replace_fallback", "stop_updated"):
        assert not _audits(w, quiet), (quiet, w.audits)
    assert w.pages == [], w.pages


@pytest.mark.asyncio
async def test_a_raise_refused_as_above_the_market_outside_the_session_keeps_the_old_stop():
    w = _refused_through_the_price(in_session=False)
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    _old_stop_still_resting(w, out)


@pytest.mark.asyncio
async def test_any_other_refused_replace_outside_the_session_still_falls_back():
    """Only the above-the-market refusal is deferred; a held-shares refusal is unchanged."""
    w = _refused_through_the_price(in_session=False)
    w.replace_errors, w.place_errors = [Exception(HELD)], []
    [out] = await _drive(w, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is True and "cancel_order" in _methods(w)
    assert not _audits(w, "stop_raise_deferred_extended_hours")
    assert w.trades[401]["stop_price"] == 61.5


@pytest.mark.asyncio
async def test_the_1645_job_itself_keeps_the_old_stop_after_hours_and_does_not_raise():
    """The real setting: 16:45 ET is outside the regular session. The trail raise is refused
    through an after-hours price -> the old stop rests, nothing sold, and the job finishes."""
    w = _open_trade(World())
    w.regular_session = False
    w.replace_errors = [Exception(BREACH)]
    w.place_errors = [Exception(BREACH) for _ in range(6)]
    [out] = await _drive(w, _job())
    assert out and out[0]["action"] == "updated"
    for forbidden in ("cancel_order", "place_stop_order", "close_position"):
        assert forbidden not in _methods(w), (forbidden, w.calls)
    assert w.broker_order("stop-1")["status"] in H.LIVE_ORDER_STATUSES
    assert len(_audits(w, "stop_raise_deferred_extended_hours")) == 1
    assert (w.trades[401]["stop_order_id"], w.trades[401]["stop_price"]) == ("stop-1", 58.0)


@pytest.mark.asyncio
async def test_the_next_pass_retries_a_deferred_raise():
    """Deferred after hours, then the same raise on a later pass the broker accepts."""
    w = _refused_through_the_price(in_session=False)
    w.place_errors = []
    move = lambda: om.move_stop_price_only(401, 61.5, stop_source="trail")  # noqa: E731
    out1, out2 = await _drive(w, move, move)
    assert out1 is False and out2 is True
    assert "cancel_order" not in _methods(w)
    assert w.trades[401]["stop_price"] == 61.5 and w.broker_order("stop-1")["status"] == "replaced"


@pytest.mark.asyncio
async def test_the_refresh_gets_update_stops_markers_back_unchanged():
    """`_stop_refresh` tells the outcomes apart by IDENTITY — the entry point must hand
    `update_stop`'s return straight back."""
    for in_session, key in ((True, "sold_at_market"), (False, "no_stop_sale_deferred_extended_hours")):
        w = World()
        w.regular_session = in_session
        _trade(w)
        _position(w, "KOD", 10, 10)
        _bstop(w, "stop-1", "KOD", 10, 58.0, status="expired")
        w.place_errors = [Exception(BREACH) for _ in range(6)]
        await _drive(w, lambda: lt._stop_refresh(include_same_day=True, label="Post-close"))
        ran = _audits(w, "stop_refresh_ran")[0]
        assert ran[key] == ["KOD"] and ran["unprotected"] == [], ran


# ── after an ACCEPTED replace, never cancel-then-place on top of it ───────────────────────────

def _live_world():
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    return w


def _wrap_replace(after):
    """A step that wraps the fake broker's replace (installed by `_drive`) with `after(result)`."""
    async def _step():
        real = om.alpaca.replace_order

        async def _wrapped(*a, **k):
            return await after(await real(*a, **k))
        om.alpaca.replace_order = _wrapped
    return _step


@pytest.mark.asyncio
async def test_a_replace_that_raised_after_the_broker_took_it_is_never_followed_by_a_cancel():
    """A write timeout that landed: the old stop reads back consumed. Not proof of a refusal — the
    pointer and price are left alone, he is asked to verify, nothing is cancelled or placed."""
    w = _live_world()

    async def _timeout(_res):
        raise TimeoutError("write timeout")

    _, out = await _drive(w, _wrap_replace(_timeout),
                          lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is False
    assert not ({"cancel_order", "place_stop_order", "close_position"} & set(_methods(w))), w.calls
    assert w.trades[401]["stop_price"] == 58.0 and w.trades[401]["stop_order_id"] == "stop-1"
    [row] = _audits(w, "stop_price_replace_unconfirmed")
    assert row["replace_outcome"] == "raised_ambiguous" and row["mechanism"] == "price_only_replace"
    assert len(w.pages) == 1 and "not confirmed" in w.pages[0] and w.pages[0].startswith("💰 LIVE-$")


@pytest.mark.asyncio
async def test_an_accepted_replace_not_confirmed_live_points_at_the_successor_and_withholds_the_price():
    w = _live_world()

    async def _pending(res):
        w.broker_order(res["id"])["status"] = "pending_new"
        return res

    _, out = await _drive(w, _wrap_replace(_pending),
                          lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is False
    assert not ({"cancel_order", "place_stop_order"} & set(_methods(w))), w.calls
    t = w.trades[401]
    assert t["stop_order_id"] == "replaced-stop-1", "the pointer follows the broker"
    assert t["stop_price"] == 58.0, "the price is withheld — the books understating the stop is the safe side"
    assert _audits(w, "stop_price_replace_unconfirmed")[0]["replace_outcome"] == "unverified"
    assert len(w.pages) == 1 and "not confirmed" in w.pages[0]


@pytest.mark.asyncio
async def test_a_successor_that_reads_back_dead_is_re_protected_and_paged_not_cancel_placed_blind():
    w = _live_world()

    async def _dead(res):
        o = w.broker_order(res["id"])
        o["status"] = "rejected"
        w.positions["KOD"]["qty_available"] = 10.0
        return res

    _, out = await _drive(w, _wrap_replace(_dead),
                          lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    assert out is False and "cancel_order" not in _methods(w)
    # re-protected from broker truth at the row's (unchanged) stop — never left without one
    assert [(c["qty"], c["stop_price"]) for c in _calls(w, "place_stop_order")] == [(10, 58.0)]
    assert w.trades[401]["stop_price"] == 58.0 and w.trades[401]["stop_order_id"]
    assert len(w.pages) == 1 and "read back dead" in w.pages[0]


@pytest.mark.asyncio
async def test_the_entry_point_never_raises_into_the_1645_loop(monkeypatch):
    """The 16:45 loop has no per-trade try. A raise out of the replace step is AFTER the broker
    write by construction -> audited, paged, False; never the cancel-then-place path."""
    w = _live_world()

    async def _boom(*a, **k):
        raise RuntimeError("db gone after the replace")

    async def _arm():
        om._replace_stop_price_only, _arm.saved = _boom, om._replace_stop_price_only

    try:
        _, out = await _drive(w, _arm, lambda: om.move_stop_price_only(401, 61.5, stop_source="trail"))
    finally:
        om._replace_stop_price_only = _arm.saved
    assert out is False
    assert not ({"cancel_order", "place_stop_order"} & set(_methods(w)))
    assert _audits(w, "stop_price_replace_unconfirmed")[0]["replace_outcome"] == "raised_after_replace"
    assert len(w.pages) == 1


def test_the_new_writer_is_registered_with_both_column_write_gates():
    """`_mark_stop_replaced` writes the stop pointer + price: it must be an authorized writer of
    both columns and its statement must be prepared at deploy (Gate 5 B)."""
    import scripts.audit_column_writes as acw
    import scripts.preflight_db_updates as pdu
    for col in ("stop_price", "stop_order_id"):
        assert "order_manager._mark_stop_replaced" in acw.ALLOWED_WRITERS[col], col
    assert "order_manager._mark_stop_replaced" not in acw.ALLOWED_WRITERS["breakeven_active"]
    labels = [v for v in vars(pdu).values() if isinstance(v, list) and v and isinstance(v[0], tuple)]
    assert any("order_manager._mark_stop_replaced" in t[0] for lst in labels for t in lst)


# ══════════════════════════════════════════════════════════════════════════════════════════
# B. the stop-ACK watchdog places at the trade's LAST stop (operator ruling 2026-11-20 (1))
# ══════════════════════════════════════════════════════════════════════════════════════════

def _watchdog():
    import agents.market_intelligence.scheduler as sched
    return sched._stop_ack_timeout_watchdog_job


def _no_stop_world(**over):
    w = World()
    _trade(w, stop_id=None, **over)               # orb_low 57.5 in the fixture
    _position(w, "KOD", 10, 10)
    return w


@pytest.mark.asyncio
@pytest.mark.parametrize("last_stop", [58.0, 70.5, 54.0])
async def test_watchdog_places_the_fallback_at_the_trades_last_stop_not_orb_low(monkeypatch, last_stop):
    """58.00 = the entry stop; 70.50 = a trailed stop (orb_low would LOWER it by 13 dollars);
    54.00 = an entry − 2R stop BELOW the opening-range low (orb_low would tighten it)."""
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _no_stop_world(stop_price=last_stop)
    await _drive(w, _watchdog())
    [placed] = _calls(w, "place_stop_order")
    assert (placed["qty"], placed["stop_price"]) == (10, last_stop) and placed["stop_price"] != 57.5
    [row] = _audits(w, "stop_ack_timeout_remediated")
    assert row["stop_target"] == last_stop and row["stop_target_source"] == "last_stop"
    assert f"Fallback stop placed at ${last_stop:.2f} (the trade’s last stop)" in w.pages[0]
    assert w.trades[401]["stop_order_id"] and w.trades[401]["stop_price"] == last_stop


@pytest.mark.asyncio
async def test_watchdog_never_places_below_the_last_level_the_broker_held(monkeypatch):
    """#600, as the coverage repair and the sync's orphan repair: the row's stop price can
    understate the broker (an unconfirmed breakeven move withholds it) — the price preserved when
    the pointer was nulled is the floor."""
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _no_stop_world(stop_price=58.0, dead_stop_price=60.0, dead_stop_status="canceled",
                       dead_stop_order_id="stop-old")
    await _drive(w, _watchdog())
    assert [c["stop_price"] for c in _calls(w, "place_stop_order")] == [60.0]
    row = _audits(w, "stop_ack_timeout_remediated")[0]
    assert row["stop_target"] == 60.0 and row["stop_target_source"] == "last_stop+broker_floor"


@pytest.mark.asyncio
async def test_watchdog_uses_orb_low_only_when_the_row_has_no_stop_price_and_says_so(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _no_stop_world(stop_price=None)
    await _drive(w, _watchdog())
    assert [c["stop_price"] for c in _calls(w, "place_stop_order")] == [57.5]
    row = _audits(w, "stop_ack_timeout_remediated")[0]
    assert row["stop_target_source"] == "orb_low_no_last_stop"
    assert "opening-range low" in w.pages[0] and "last stop" not in w.pages[0]


@pytest.mark.asyncio
async def test_watchdog_with_neither_a_stop_price_nor_an_orb_low_places_nothing_and_pages(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _no_stop_world(stop_price=None, orb_low=None)
    await _drive(w, _watchdog())
    assert _calls(w, "place_stop_order") == []
    assert _audits(w, "stop_ack_remediation_failed")[0]["reason"] == "missing_qty_or_stop"
    assert "NO FALLBACK" in w.pages[0]


@pytest.mark.asyncio
async def test_watchdog_last_stop_refused_through_the_price_still_reaches_ruling_iii(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _no_stop_world(stop_price=70.5)
    w.place_errors = [Exception(BREACH) for _ in range(6)]
    await _drive(w, _watchdog())
    assert [c["qty"] for c in _calls(w, "close_position")] == [10]
    row = _audits(w, "stop_ack_breach_sold_at_market")[0]
    assert row["stop_target"] == 70.5 and row["stop_target_source"] == "last_stop"
