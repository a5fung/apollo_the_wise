"""#687 RULING (i), operator 2026-10-02: the failed-exit stop restore tells a FLAT broker from an
UNREADABLE one — a real zero places nothing; an unreadable read still restores from the books.

His words: "(i) failed-exit stop restore on a flat/unreadable broker read -> keep restoring from the
books for now; later separate 'no position' from 'can't read' so a real zero places nothing".

THE DEFECT. `alpaca_client.get_position` returns None for BOTH "the broker says no position" (404) and
"the read failed", so `_broker_free_qty_for_restore` treated both as UNKNOWN and fell back to the
books — on a genuinely flat broker the restore then placed a SELL STOP on shares we do not hold (a
trigger would open a short, or be rejected) and the page said UNPROTECTED for a position that no
longer exists.

THE SHAPE. `get_position` is untouched (its signature and its None-for-everything contract are pinned
below — every other caller keeps the behaviour it has). When it returns None the restore sizing
disambiguates with `get_all_positions(raise_on_error=True)`, which already has the exact semantics:
a failed read RAISES (→ the books fallback, as before, after the deduped alpaca alert fires inside
it), a successful list without the ticker is FLAT (→ `(0, 'broker_flat')`, nothing placed), and a
list that still shows the ticker is a readable broker (→ sized from it, as a readable broker always
was). Every consumer of the sizing handles 'broker_flat' as "nothing to protect, place NOTHING".

The worlds come from the convergence harness (`tests/_convergence_687_harness.py`), so the same fake
broker + book that pins the toggle-OFF paths drives these.
"""
from __future__ import annotations

import json

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import alpaca_client as ac
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests._convergence_687_harness import (
    BREACH,
    NO_POSITION,
    TODAY,
    World,
    _bsell,
    _bstop,
    _mirror,
    _position,
    _trade,
    _ws_order,
)

UNREADABLE = Exception("HTTP 503 Service Unavailable")


async def _drive(w, *steps):
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)


def _calls(w) -> list[str]:
    return [c["method"] for c in w.calls]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _placed(w) -> list:
    return [c["args"] for c in w.calls if c["method"] == "place_stop_order"]


def _flat_world() -> World:
    """A trade whose stop is gone and whose position is gone with it — the broker is FLAT."""
    w = World()
    _trade(w)
    return w


# ── the sizing helper itself ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sizing_a_flat_broker_is_zero_named_flat_and_reads_no_orders():
    w = _flat_world()
    [out] = await _drive(w, lambda: om._broker_free_qty_for_restore("KOD", "live", 10.0))
    assert out == (0, "broker_flat")
    # the single-position read, then the list read that confirms "no position" — no orders read
    assert _calls(w) == ["get_position", "get_all_positions"], w.calls
    assert w.calls[1]["args"]["raise_on_error"] is True, w.calls[1]


@pytest.mark.asyncio
async def test_sizing_an_unreadable_broker_falls_back_to_the_books_exactly_as_before():
    w = _flat_world()
    w.list_errors = [UNREADABLE]
    [out] = await _drive(w, lambda: om._broker_free_qty_for_restore("KOD", "live", 10.0))
    assert out == (10, "fallback:position_unreadable")
    assert _calls(w) == ["get_position", "get_all_positions"], w.calls


@pytest.mark.asyncio
async def test_sizing_a_position_the_list_still_shows_is_sized_from_the_broker():
    """The single read returned nothing but the list shows the position: the broker IS readable, so
    the count is the broker's (position minus shares held by live resting sells), as it always was."""
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 7)
    _bsell(w, "manual-1", "KOD", 3, status="new")

    async def _single_read_blank():
        async def _none(ticker, account_mode=None):
            return None
        ac.get_position = _none                                # restored by the harness on exit

    [_, out] = await _drive(
        w, _single_read_blank, lambda: om._broker_free_qty_for_restore("KOD", "live", 10.0))
    assert out == (7, "broker")
    assert _calls(w) == ["get_all_positions", "get_open_orders"], w.calls


@pytest.mark.asyncio
async def test_sizing_a_readable_single_read_never_touches_the_list():
    """Today's path for a readable broker is unchanged: one position read, one orders read."""
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 10)
    [out] = await _drive(w, lambda: om._broker_free_qty_for_restore("KOD", "live", 4.0))
    assert out == (10, "broker")
    assert _calls(w) == ["get_position", "get_open_orders"], w.calls


# ── `_restore_stop_after_failed_exit` ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restore_on_a_flat_broker_places_nothing_and_says_flat():
    w = _flat_world()
    [out] = await _drive(
        w, lambda: om._restore_stop_after_failed_exit(401, "KOD", 10, 58.0, "live",
                                                       cancelled_stop_id="stop-1"))
    assert out == om.RESTORE_FLAT
    assert _placed(w) == [], w.calls
    assert out not in (om.RESTORE_COVERED, om.RESTORE_FAILED, om.RESTORE_PLACED, om.RESTORE_SOLD)
    rows = _audits(w, "restore_skipped_broker_flat")
    assert len(rows) == 1, w.audits
    assert rows[0]["trade_id"] == 401 and rows[0]["ticker"] == "KOD"
    assert rows[0]["account_mode"] == "live" and rows[0]["stop_price"] == 58.0
    assert rows[0]["site"] == "order_manager.restore_after_failed_exit"


@pytest.mark.asyncio
async def test_restore_on_an_unreadable_broker_restores_from_the_books_unchanged():
    w = _flat_world()
    w.list_errors = [UNREADABLE]
    [out] = await _drive(
        w, lambda: om._restore_stop_after_failed_exit(401, "KOD", 10, 58.0, "live"))
    assert out == om.RESTORE_PLACED
    assert [p["qty"] for p in _placed(w)] == [10]
    assert _audits(w, "restore_skipped_broker_flat") == []


def test_the_flat_page_sentence_is_plain_and_is_not_the_unprotected_or_covered_page():
    line = om._restore_outcome_line(om.RESTORE_FLAT, 58.0)
    low = line.lower()
    assert "no position" in low and "/syncnow" in low, line
    assert "no stop" in low and "nothing to protect" in low, line
    assert "unprotected" not in low and "manual action" not in low, line
    assert "resting" not in low and "restored" not in low, line
    # Review 2026-10-04: the first draft promised "the position sync reconciles the books". It does
    # not, in two real cases (the sync books the exit only off a broker-confirmed fill, and aborts
    # entirely when this was the account's last position). The sentence must say the row is still
    # open — not promise a reconcile. Until ruling (a) (operator 2026-10-04) it also warned that the
    # 17:00/19:00 coverage repair, sizing from the BOOKS, "may re-place a stop"; the repair now
    # reads the broker before placing, so the sentence says that instead — never the old warning.
    assert "reconciles the books" not in low, line
    assert "books still show" in low and "by hand" in low, line
    assert "coverage repair" in low and "reads the broker" in low, line
    assert "will not re-place a stop while it shows no position" in low, line
    assert "may re-place" not in low, line
    assert "only open position" in low, line
    # one sentence for both pages — the stream's dead-sale page must carry the same words
    assert line == "\n" + om.FLAT_RESTORE_PAGE_BODY
    # and the other outcomes keep their sentences
    assert "UNPROTECTED" in om._restore_outcome_line(om.RESTORE_FAILED, 58.0)
    assert "resting" in om._restore_outcome_line(om.RESTORE_COVERED, 58.0)


# ── the consumers end to end ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_1645_exit_refused_on_a_flat_broker_pages_flat_and_places_nothing():
    """The stop filled between the cancel and the sell: the sale is refused (no position), the
    restore reads a flat broker, and the page says so — not UNPROTECTED, no stop on air."""
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.vanish_on_sell = True
    w.close_errors = [Exception(NO_POSITION)]
    [out] = await _drive(w, lambda: om.execute_full_exit(401, "sma_trail_stop"))
    assert out is False
    assert _placed(w) == [], w.calls
    assert len(w.pages) == 1, w.pages
    page = w.pages[0]
    assert "Full exit FAILED" in page and "no position" in page.lower(), page
    assert "UNPROTECTED" not in page and "RESTORED" not in page, page
    assert len(_audits(w, "restore_skipped_broker_flat")) == 1


@pytest.mark.asyncio
async def test_1645_exit_refused_on_an_unreadable_broker_restores_from_the_books():
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.vanish_on_sell = True
    w.close_errors = [Exception("insufficient qty available: available 0, held_for_orders 10")]
    w.list_errors = [UNREADABLE]
    [out] = await _drive(w, lambda: om.execute_full_exit(401, "sma_trail_stop"))
    assert out is False
    assert [p["qty"] for p in _placed(w)] == [10]
    assert any("Stop RESTORED" in p for p in w.pages), w.pages


@pytest.mark.asyncio
async def test_stream_dead_sale_on_a_flat_broker_pages_flat_and_places_nothing():
    w = World()
    _trade(w, stop_id=None)
    _bsell(w, "sell-q", "KOD", 10, status="canceled")
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    await _drive(w, lambda: ts._handle_cancel_or_reject(_ws_order("sell-q", "KOD"), "canceled",
                                                        "live"))
    assert _placed(w) == [], w.calls
    assert len(w.pages) == 1, w.pages
    page = w.pages[0]
    assert "Close order CANCELLED" in page and "no position" in page.lower(), page
    assert "RESTORE FAILED" not in page and "unprotected" not in page.lower(), page
    assert "resting" not in page.lower(), page
    # the same words as the failed-exit page (review 2026-10-04: neither may promise the sync
    # reconciles the row; since ruling (a) both say the coverage repair reads the broker too)
    assert page.endswith("\n" + om.FLAT_RESTORE_PAGE_BODY), page
    rows = _audits(w, "restore_skipped_broker_flat")
    assert len(rows) == 1 and rows[0]["site"] == "trade_stream.full_exit_cancel_restore", w.audits


@pytest.mark.asyncio
async def test_stream_dead_sale_on_an_unreadable_broker_restores_from_the_books():
    w = World()
    _trade(w, stop_id=None)
    _bsell(w, "sell-q", "KOD", 10, status="canceled")
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    w.list_errors = [UNREADABLE]
    await _drive(w, lambda: ts._handle_cancel_or_reject(_ws_order("sell-q", "KOD"), "canceled",
                                                        "live"))
    assert [p["qty"] for p in _placed(w)] == [10]
    assert any("Stop re-placed" in p for p in w.pages), w.pages


@pytest.mark.asyncio
async def test_depth_sale_refused_on_a_flat_broker_does_not_say_the_position_stays_open():
    """The depth flow's failed-sale page (toggle OFF today) appends 'The position stays open…' to every
    restore outcome but a sale; a flat broker has no position to stay open."""
    w = World()
    _trade(w, exit_rule=om.DEPTH_EXIT_RULE, depth_sell_pending_on=TODAY)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.vanish_on_sell = True
    w.opg_errors = [Exception(NO_POSITION)]
    [out] = await _drive(w, lambda: om.execute_depth_open_sale(401, "sma_trail_stop"))
    assert out is False
    assert _placed(w) == [], w.calls
    [page] = [p for p in w.pages if "Opening-auction sale FAILED" in p]
    assert "no position" in page.lower(), page
    assert "stays open" not in page and "UNPROTECTED" not in page, page


@pytest.mark.asyncio
async def test_a_refused_stop_sale_on_a_flat_broker_sells_nothing_and_names_the_case():
    """Ruling (iii)'s shared sale path sizes from the same helper: flat → 0 → nothing sold, and its
    skip row names 'broker_flat' (it already sold nothing at 0; this pins the name)."""
    w = _flat_world()
    [out] = await _drive(w, lambda: om._sell_at_market_for_refused_stop(
        401, "KOD", "live", stop_price=58.0, site="test.flat", refusal=Exception(BREACH)))
    assert out is None
    assert "close_position" not in _calls(w), w.calls
    skips = _audits(w, "stop_breach_sale_skipped")
    assert len(skips) == 1 and skips[0]["qty_source"] == "broker_flat", w.audits


# ── `get_position` is untouched for every other caller ───────────────────────────────────────

@pytest.mark.asyncio
async def test_get_position_takes_no_opt_in_flag_so_no_other_caller_changes(monkeypatch):
    """The disambiguation lives in the restore sizing, not in `get_position`: it still binds exactly
    `(ticker, account_mode)` — an opt-in flag is refused — so the 30-odd other callers (agent,
    live_tracker, trade_stream, the sync, the probes) call and get back exactly what they did."""
    class _Client:
        def get_open_position(self, ticker):
            raise Exception("HTTP 500 boom")

    monkeypatch.setattr(ac, "get_trading_client", lambda *a, **k: _Client())
    with pytest.raises(TypeError):
        await ac.get_position("KOD", account_mode="live", raise_on_error=True)
    assert await ac.get_position("KOD", "live") is None          # positional, as live_tracker calls it
    assert await ac.get_position("KOD", account_mode="live") is None


@pytest.mark.asyncio
async def test_get_position_still_returns_none_for_a_404_and_for_any_other_error(monkeypatch):
    class _Client:
        def __init__(self, exc):
            self.exc = exc

        def get_open_position(self, ticker):
            raise self.exc

    monkeypatch.setattr(ac, "get_trading_client",
                        lambda *a, **k: _Client(Exception(NO_POSITION)))
    assert await ac.get_position("KOD", account_mode="live") is None
    monkeypatch.setattr(ac, "get_trading_client",
                        lambda *a, **k: _Client(Exception("HTTP 500 boom")))
    assert await ac.get_position("KOD", account_mode="live") is None


@pytest.mark.asyncio
async def test_the_sale_sizing_path_still_treats_a_blank_read_as_unreadable_and_lists_nothing():
    """Nothing wider than the ruling: the OTHER consumer of a None position on the exit path —
    `_size_sale_beside_resting_orders` (sizing the SALE beside a resting profit-take) — keeps
    today's behaviour: a blank read is 'broker_unreadable', the sale is skipped, the stop is left
    alone, and NO positions-list read is made. Only the restore sizing disambiguates."""
    w = World()
    _trade(w, remaining=6, partial_taken=True, breakeven_active=True, stop_price=60.0)
    _bstop(w, "stop-1", "KOD", 4, 60.0)
    w.broker_orders.append({"id": "oco-1", "symbol": "KOD", "side": "sell", "type": "limit",
                            "qty": 2.0, "filled_qty": 0.0, "status": "new",
                            "order_class": "oco", "limit_price": 90.0})
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, raw={"order_class": "oco"})
    [out] = await _drive(w, lambda: om.execute_full_exit(401, "sma_trail_stop"))
    assert out is False
    assert "get_all_positions" not in _calls(w) and "cancel_order" not in _calls(w), w.calls
    assert "close_position" not in _calls(w), w.calls
    skips = [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == "full_exit_skipped"]
    assert skips and skips[0].get("skip_code") == "broker_unreadable", w.audits
