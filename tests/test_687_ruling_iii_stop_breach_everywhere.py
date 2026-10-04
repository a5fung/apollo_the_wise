"""#687 ruling (iii), operator 2026-10-02 ("the rest is ok" to the rec): ruling (3) — a stop that
cannot be placed because the price is already through it → SELL AT MARKET, as a triggered stop
would — extended from the failed-exit restore to the OTHER stop-placing sites.

Each site, when (and only when) the broker refuses its stop with the price-through rejection
(`order_manager._is_stop_above_market`, ruling (3)'s own recognition), sells the free shares at
market through `_sell_at_market_for_refused_stop` → `_sell_free_shares_after_stop_breach`. Per
site this file proves: the refusal sells ONCE; any other refusal keeps today's behaviour; a sale
that cannot happen (fails, or nothing free) still leaves today's page. The de-dupe block at the end
proves no site sells a second time after ruling (3)'s own sale (or another site's) in the same
tick — through the broker hold, the pending book row, and the closed row after the fill.

Driven through the #687 convergence harness's fake world (one book + one broker, every broker
call recorded), so a stray broker call is visible here too.
"""
from __future__ import annotations

import json

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests._convergence_687_harness import (
    BREACH,
    World,
    _bsell,
    _bstop,
    _mirror,
    _position,
    _trade,
    _ws_order,
)

OTHER = "insufficient qty available"


def _breach(w, n=8):
    w.place_errors = [Exception(BREACH) for _ in range(n)]


async def _drive(w, *steps):
    """Run each step in the fake world, in order (one tick); return their results."""
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)


def _sales(w) -> list:
    """Every market sale the code sent (close_position), by quantity (None = whole position)."""
    return [c["args"].get("qty") for c in w.calls if c["method"] == "close_position"]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _sale_pages(w) -> list[str]:
    return [p for p in w.pages if "Price already below the stop" in p]


def _full_exit_rows(w) -> list[dict]:
    return [o for o in w.orders if o["purpose"] == "full_exit"]


def _reconcile(qty=10.0, stop=58.0):
    return lambda: om._ensure_stop_coverage_outcome(401, "KOD", qty, stop, "magna53", "live")


# ── Site 1 — the coverage reconciler's place branch (`_ensure_stop_coverage_outcome`) ─────────

@pytest.mark.asyncio
async def test_site1_a_price_through_refusal_sells_the_free_shares_once():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    out, again = await _drive(w, _reconcile(), _reconcile())
    assert _sales(w) == [10], w.calls
    assert out.status == om.COVERAGE_REPAIRED and out.reason == "stop_breach_sold_at_market", out
    assert "SOLD AT MARKET" in out.message
    rows = _full_exit_rows(w)
    assert len(rows) == 1 and rows[0]["exit_reason"] == "stop_hit" and rows[0]["qty"] == 10, rows
    assert len(_sale_pages(w)) == 1, w.pages
    assert _audits(w, "stop_coverage_breach")[0]["sold_qty"] == 10   # the retry still stops on it
    assert _audits(w, "stop_breach_market_sale")[0]["site"] == "order_manager.ensure_stop_coverage"
    # the second pass in the same tick: the queued sale is a pending exit → covered, nothing sold
    assert again.status == om.COVERAGE_COVERED, again


@pytest.mark.asyncio
async def test_site1_any_other_refusal_keeps_todays_flag_and_sells_nothing():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    w.place_errors = [Exception(OTHER)]
    [out] = await _drive(w, _reconcile())
    assert _sales(w) == [] and w.pages == []
    assert out.status == om.COVERAGE_FLAGGED and out.reason == "place_coverage_stop_failed", out


@pytest.mark.asyncio
async def test_site1_a_failed_sale_keeps_todays_breach_flag():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    w.close_errors = [Exception("broker down")]
    [out] = await _drive(w, _reconcile())
    assert _sales(w) == [10] and _sale_pages(w) == []
    assert out.status == om.COVERAGE_FLAGGED and out.reason == "stop_above_market_breach", out
    assert "no auto-exit" in out.message
    assert _audits(w, "stop_breach_sale_failed"), w.audits


@pytest.mark.asyncio
async def test_site1_nothing_free_at_the_broker_sells_nothing():
    """An order the books do not know holds every share: nothing free → today's flag."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 0)
    _bsell(w, "manual-1", "KOD", 10, status="new")
    _breach(w)
    [out] = await _drive(w, _reconcile())
    assert _sales(w) == [] and _sale_pages(w) == []
    assert out.reason == "stop_above_market_breach", out
    assert _audits(w, "stop_breach_sale_skipped"), w.audits


@pytest.mark.asyncio
async def test_site1_a_naked_position_still_pages_when_the_sale_fails():
    """Through the position sync: every stop refused, every sale fails → the digest still pages."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    w.close_errors = [Exception("broker down") for _ in range(4)]
    await _drive(w, lambda: om._sync_positions_for_mode("live"))
    assert _sale_pages(w) == []
    digest = [p for p in w.pages if "Position Sync Discrepancies" in p]
    assert digest and "ABOVE market" in digest[0] and "Operator decision needed" in digest[0], w.pages


# ── Site 2 — the position sync's orphan repair (3 attempts), then its own coverage pass ───────

def _orphan_world():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    return w


def _sync():
    return lambda: om._sync_positions_for_mode("live")


def _digest(w) -> str:
    pages = [p for p in w.pages if "Position Sync Discrepancies" in p]
    assert len(pages) == 1, w.pages
    return pages[0]


@pytest.mark.asyncio
async def test_site2_the_orphan_repair_sells_once_and_the_same_syncs_coverage_pass_does_not():
    w = _orphan_world()
    _breach(w)
    await _drive(w, _sync())
    assert _sales(w) == [10], w.calls
    assert [c["method"] for c in w.calls].count("place_stop_order") == 3   # the orphan's 3 only
    assert len(_sale_pages(w)) == 1
    assert "Orphaned position KOD" in _digest(w) and "SOLD AT MARKET" in _digest(w)
    assert "Failed to remediate" not in _digest(w)
    assert not [d for d in _audits(w, "stop_ack_remediation_failed")
                if d.get("reason") == "place_stop_failed_3_attempts"]
    assert _audits(w, "stop_breach_market_sale")[0]["site"] == "order_manager.sync_orphan_remediation"


@pytest.mark.asyncio
async def test_site2_any_other_refusal_keeps_todays_digest_and_sells_nothing():
    w = _orphan_world()
    w.place_errors = [Exception(OTHER) for _ in range(4)]
    await _drive(w, _sync())
    assert _sales(w) == []
    assert "Failed to remediate orphaned stop for KOD" in _digest(w)


@pytest.mark.asyncio
async def test_site2_keys_on_the_last_attempt_only():
    """Attempts 1-2 through the price, the last one refused otherwise → today's failure line."""
    w = _orphan_world()
    w.place_errors = [Exception(BREACH), Exception(BREACH), Exception(OTHER), Exception(OTHER)]
    await _drive(w, _sync())
    assert _sales(w) == []
    assert "Failed to remediate orphaned stop for KOD" in _digest(w)


@pytest.mark.asyncio
async def test_site2_a_failed_sale_keeps_todays_failure_line():
    w = _orphan_world()
    _breach(w)
    w.close_errors = [Exception("broker down") for _ in range(2)]
    await _drive(w, _sync())
    assert _sale_pages(w) == []
    assert "Failed to remediate orphaned stop for KOD" in _digest(w)
    assert "ABOVE market" in _digest(w)              # the coverage pass's breach flag, as today


# ── Site 6 — the OCO-cancel handler (its re-protect runs through the reconciler) ──────────────

def _oco_world():
    w = World()
    _trade(w, remaining=2, stop_id=None, partial_taken=True, breakeven_active=True,
           stop_price=60.0)
    _position(w, "KOD", 2, 2)
    w.broker_orders.append({"id": "oco-1", "symbol": "KOD", "side": "sell", "type": "limit",
                            "qty": 2.0, "filled_qty": 0.0, "status": "canceled",
                            "order_class": "oco", "limit_price": 90.0})
    _bstop(w, "leg-1", "KOD", 2, 60.0, status="canceled")
    _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, status="new",
            raw={"order_class": "oco",
                 "legs": [{"id": "leg-1", "type": "stop", "stop_price": 60.0}]})
    return w


def _oco_cancel():
    return lambda: ts._handle_cancel_or_reject(_ws_order("oco-1", "KOD"), "canceled", "live")


@pytest.mark.asyncio
async def test_site6_oco_died_unfilled_and_its_restore_is_through_the_price_sells_once():
    w = _oco_world()
    _breach(w)
    await _drive(w, _oco_cancel())
    assert _sales(w) == [2], w.calls
    assert len(_sale_pages(w)) == 1
    oco_page = [p for p in w.pages if "OCO CANCELLED" in p]
    assert oco_page and "SOLD AT MARKET" in oco_page[0], w.pages


@pytest.mark.asyncio
async def test_site6_any_other_refusal_keeps_todays_page_and_sells_nothing():
    w = _oco_world()
    w.place_errors = [Exception(OTHER)]
    await _drive(w, _oco_cancel())
    assert _sales(w) == []
    oco_page = [p for p in w.pages if "OCO CANCELLED" in p]
    assert oco_page and "failed to place coverage stop" in oco_page[0], w.pages


@pytest.mark.asyncio
async def test_site6_a_failed_sale_still_pages_the_breach():
    w = _oco_world()
    _breach(w)
    w.close_errors = [Exception("broker down")]
    await _drive(w, _oco_cancel())
    assert _sale_pages(w) == []
    oco_page = [p for p in w.pages if "OCO CANCELLED" in p]
    assert oco_page and "no auto-exit" in oco_page[0], w.pages


# ── Site 4 — the stop-ACK watchdog's fallback stop (at the entry's orb_low) ───────────────────

def _watchdog_world():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    return w


def _watchdog():
    import agents.market_intelligence.scheduler as sched
    return sched._stop_ack_timeout_watchdog_job


@pytest.mark.asyncio
async def test_site4_a_refused_fallback_sells_once_across_two_ticks(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _watchdog_world()
    _breach(w)
    await _drive(w, _watchdog(), _watchdog())
    assert _sales(w) == [10], w.calls
    assert len(_sale_pages(w)) == 1 and not any("CRITICAL" in p for p in w.pages), w.pages
    sold = _audits(w, "stop_ack_breach_sold_at_market")
    assert len(sold) == 1 and sold[0]["sold_qty"] == 10, w.audits
    assert [a["summary"] for a in w.audits
            if a["event_type"] == "stop_ack_breach_sold_at_market"][0].startswith("KOD #401")
    assert _full_exit_rows(w)[0]["exit_reason"] == "stop_hit"


@pytest.mark.asyncio
async def test_site4_any_other_refusal_keeps_the_critical_page_and_sells_nothing(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _watchdog_world()
    w.place_errors = [Exception(OTHER)]
    await _drive(w, _watchdog())
    assert _sales(w) == [] and _sale_pages(w) == []
    assert any("CRITICAL: POSITION NAKED" in p for p in w.pages), w.pages


@pytest.mark.asyncio
async def test_site4_a_failed_sale_still_pages_critical(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _watchdog_world()
    _breach(w)
    w.close_errors = [Exception("broker down")]
    await _drive(w, _watchdog())
    assert _sale_pages(w) == []
    assert any("CRITICAL: POSITION NAKED" in p for p in w.pages), w.pages
    assert _audits(w, "stop_breach_sale_failed") and _audits(w, "stop_ack_remediation_failed")


@pytest.mark.asyncio
async def test_site4_the_next_tick_after_the_sale_filled_does_not_act_again(monkeypatch):
    """The sale filled at the broker, the books not yet: without the dedup row the next tick would
    find no stop and no covering order, re-place, and page CRITICAL on a position already sold."""
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _watchdog_world()
    _breach(w)

    async def _sale_fills_at_the_broker():
        for o in w.broker_orders:
            if o["type"] == "market":
                o["status"], o["filled_qty"] = "filled", o["qty"]
        w.positions.pop("KOD", None)

    await _drive(w, _watchdog(), _sale_fills_at_the_broker, _watchdog())
    assert _sales(w) == [10]
    assert [c["method"] for c in w.calls].count("place_stop_order") == 1, w.calls
    assert not any("CRITICAL" in p for p in w.pages), w.pages


# ── Site 3 — `update_stop` (a trail raise / a re-place the broker refuses; keyed on the TERMINAL
#    refusal, after the existing 3-second retry) ─────────────────────────────────────────────

def _raise_world():
    w = World()
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    return w


def _raise():
    return lambda: om.update_stop(401, 61.5, stop_source="trail")


def _naked_pages(w):
    return [p for p in w.pages if "STOP FAILED — position NAKED" in p]


@pytest.mark.asyncio
async def test_site3_a_trail_raise_refused_through_the_price_sells_once():
    w = _raise_world()
    _breach(w)
    [out] = await _drive(w, _raise())
    assert out is om.STOP_SOLD_AT_MARKET and not out          # falsy: no stop was placed
    assert _sales(w) == [10], w.calls
    pages = _sale_pages(w)
    assert len(pages) == 1 and "trail would have triggered" in pages[0], w.pages
    assert _naked_pages(w) == []
    assert w.trades[401]["stop_order_id"] is None             # no dead pointer left for the sync
    assert not _audits(w, "stop_update_failed") and not _audits(w, "naked_position_detected")
    assert _full_exit_rows(w)[0]["exit_reason"] == "stop_hit"


@pytest.mark.asyncio
async def test_site3_keys_on_the_terminal_refusal_only():
    """Attempt 1 through the price, attempt 2 something else → today's NAKED path, nothing sold;
    attempt 1 something else, attempt 2 through the price → sold."""
    w = _raise_world()
    w.place_errors = [Exception(BREACH), Exception(OTHER)]
    [out] = await _drive(w, _raise())
    assert out is False and _sales(w) == [] and len(_naked_pages(w)) == 1

    w = _raise_world()
    w.place_errors = [Exception(OTHER), Exception(BREACH)]
    [out] = await _drive(w, _raise())
    assert out is om.STOP_SOLD_AT_MARKET and _sales(w) == [10]


@pytest.mark.asyncio
async def test_site3_a_failed_sale_keeps_the_naked_page():
    w = _raise_world()
    _breach(w)
    w.close_errors = [Exception("broker down")]
    [out] = await _drive(w, _raise())
    assert out is False and _sale_pages(w) == [] and len(_naked_pages(w)) == 1
    assert _audits(w, "stop_update_failed") and _audits(w, "stop_breach_sale_failed")


@pytest.mark.asyncio
async def test_site3_an_old_stop_whose_cancel_failed_still_holds_the_shares_nothing_sold():
    """Our cancel did not go through and the old stop still rests: it holds every share at the
    broker, so nothing is free to sell → today's path."""
    from agents.market_intelligence.broker import alpaca_client as ac
    w = _raise_world()
    _breach(w)

    async def _cancel_refused():
        async def _no(order_id, account_mode=None):
            w.calls.append({"method": "cancel_order", "args": {"order_id": order_id}})
            return False
        ac.cancel_order = _no                                  # restored by the harness on exit

    [_, out] = await _drive(w, _cancel_refused, _raise())
    assert out is False and _sales(w) == [] and len(_naked_pages(w)) == 1
    assert _audits(w, "stop_breach_sale_skipped")


@pytest.mark.asyncio
async def test_site3_the_morning_refresh_does_not_page_no_stop_after_the_sale_filled():
    """09:35: a DAY stop expired overnight, the re-place is refused through the price, the sale fills
    in milliseconds. The refresh must not then page "No stop on KOD" for a position already sold."""
    from agents.market_intelligence.broker import alpaca_client as ac
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 10)
    _bstop(w, "stop-1", "KOD", 10, 58.0, status="expired")
    _breach(w)

    async def _sales_fill_at_once():
        real = ac.close_position

        async def _close_and_fill(*a, **k):
            out = await real(*a, **k)
            o = w.broker_order(out["id"])
            o["status"], o["filled_qty"] = "filled", o["qty"]
            w.positions.pop("KOD", None)
            return out
        ac.close_position = _close_and_fill                    # restored by the harness on exit

    [_, placed] = await _drive(
        w, _sales_fill_at_once, lambda: lt._stop_refresh(include_same_day=True, label="Morning"))
    assert _sales(w) == [10] and placed == 0
    assert not any("No stop on" in p for p in w.pages), w.pages
    assert len(_sale_pages(w)) == 1
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["sold_at_market"] == ["KOD"] and ran["unprotected"] == [] and ran["placed"] == 0


# ── Site 5 — the stream's partial-exit restore (a plain partial sell died unfilled) ───────────

def _partial_world():
    """10 sh; the partial reduced the stop to 7 (stop-r) and put 3 up for sale (sell-p), which died."""
    w = World()
    _trade(w, stop_id="stop-r")
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-r", "KOD", 7, 58.0)
    _bsell(w, "sell-p", "KOD", 3, status="canceled")
    _mirror(w, "sell-p", 401, "KOD", "partial_exit", 3, status="accepted",
            exit_reason="partial_profit", raw={"order_class": "simple"})
    return w


def _partial_died():
    return lambda: ts._handle_cancel_or_reject(_ws_order("sell-p", "KOD"), "canceled", "live")


def _restore_failed_pages(w):
    return [p for p in w.pages if "STOP RESTORE FAILED" in p]


@pytest.mark.asyncio
async def test_site5_a_restore_refused_through_the_price_sells_the_whole_rest_once():
    w = _partial_world()
    _breach(w)
    await _drive(w, _partial_died())
    assert _sales(w) == [10], w.calls             # the cancelled reduced stop no longer holds 7
    assert len(_sale_pages(w)) == 1 and _restore_failed_pages(w) == [], w.pages
    assert w.trades[401]["stop_order_id"] is None  # no dead pointer left for the sync
    assert _full_exit_rows(w)[0]["exit_reason"] == "stop_hit"


@pytest.mark.asyncio
async def test_site5_the_just_cancelled_stop_still_listed_live_is_not_counted_as_holding():
    """Alpaca acknowledges a cancel before it settles: for a moment the reduced stop can still be
    listed `new`. It is the stop this path cancelled, so its 7 shares are free to sell."""
    from agents.market_intelligence.broker import alpaca_client as ac
    w = _partial_world()
    _breach(w)

    async def _cancel_acked_not_settled():
        async def _ack(order_id, account_mode=None):
            w.calls.append({"method": "cancel_order", "args": {"order_id": order_id}})
            return True                                        # the order stays listed `new`
        ac.cancel_order = _ack                                 # restored by the harness on exit

    await _drive(w, _cancel_acked_not_settled, _partial_died())
    assert _sales(w) == [10], w.calls


@pytest.mark.asyncio
async def test_site5_any_other_refusal_keeps_todays_page_and_sells_nothing():
    w = _partial_world()
    w.place_errors = [Exception(OTHER)]
    await _drive(w, _partial_died())
    assert _sales(w) == [] and len(_restore_failed_pages(w)) == 1, w.pages
    assert w.trades[401]["stop_order_id"] == "stop-r"   # main leaves it; the sync heals it


@pytest.mark.asyncio
async def test_site5_a_failed_sale_still_pages_restore_failed():
    w = _partial_world()
    _breach(w)
    w.close_errors = [Exception("broker down")]
    await _drive(w, _partial_died())
    assert _sale_pages(w) == [] and len(_restore_failed_pages(w)) == 1, w.pages


# ══ DE-DUPE — a sale goes out ONCE, not again from another site in the same tick ══════════════
#
# Ruling (3)'s own path sells first (the 16:45 sale is refused, its stop restore is refused through
# the price → `_restore_stop_after_failed_exit` sells the 10 free shares). Every price stays through
# every stop from then on, so ANY site that reached its own placement would be refused and try to
# sell. Three layers stop it, each proved: (a) the queued sale is a live sell order holding the
# shares at the broker; (b) it is a pending `full_exit` row in the books (the fallback when the
# broker cannot be read); (c) once filled, the row is closed and the position gone.

def _ruling3_sold_world():
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    w.close_errors = [Exception("insufficient qty available: available 0, held_for_orders 10")]
    _breach(w, n=20)
    return w


def _ruling3_sale():
    return lambda: om.execute_full_exit(401, "sma_trail_stop")


def _then_every_site(w):
    """Each of the six sites, in one tick, on the same trade (sites 5 and 6 are handed a plain
    partial and an OCO third that just died, right before they run)."""
    async def _a_dying_partial_and_oco():
        _bsell(w, "sell-p", "KOD", 3, status="canceled")
        _mirror(w, "sell-p", 401, "KOD", "partial_exit", 3, status="accepted",
                exit_reason="partial_profit", raw={"order_class": "simple"})
        w.broker_orders.append({"id": "oco-1", "symbol": "KOD", "side": "sell", "type": "limit",
                                "qty": 2.0, "filled_qty": 0.0, "status": "canceled",
                                "order_class": "oco", "limit_price": 90.0})
        _bstop(w, "leg-1", "KOD", 2, 60.0, status="canceled")
        _mirror(w, "oco-1", 401, "KOD", "partial_exit", 2, status="new",
                raw={"order_class": "oco",
                     "legs": [{"id": "leg-1", "type": "stop", "stop_price": 60.0}]})

    return [
        _reconcile(),                                                        # site 1
        _sync(),                                                             # site 2
        _raise(),                                                            # site 3
        lambda: lt._stop_refresh(include_same_day=True, label="Post-close"),  # site 3 (refresh)
        _watchdog(),                                                         # site 4
        _a_dying_partial_and_oco,
        lambda: ts._handle_cancel_or_reject(                                 # site 5
            _ws_order("sell-p", "KOD"), "canceled", "live"),
        _oco_cancel(),                                                       # site 6
    ]


def _skips(w) -> list[tuple[str, str]]:
    return [(d["site"], d["qty_source"]) for d in _audits(w, "stop_breach_sale_skipped")]


@pytest.mark.asyncio
async def test_dedupe_no_site_sells_again_after_ruling_3s_sale_in_the_same_tick(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _ruling3_sold_world()

    async def _setup_after_the_sale():
        w.trades[401]["stop_order_id"] = None      # the watchdog's shape (a filled row, no stop)

    await _drive(w, _ruling3_sale(), _setup_after_the_sale, *_then_every_site(w))
    # the refused whole-position sale at 16:45, then ruling (3)'s 10 — and nothing else
    assert _sales(w) == [None, 10], [c for c in w.calls if c["method"] == "close_position"]
    assert len(_full_exit_rows(w)) == 1
    assert _sale_pages(w) == []                    # ruling (3)'s page is its own wording
    # sites 1-4 stop at their own pending-exit / broker-covered guards (layer b); site 5 reaches its
    # placement, is refused, and the shared path finds the shares held by the queued sale (layer a)
    assert _skips(w) == [("trade_stream.partial_exit_cancel_restore", "broker")], w.audits
    assert _audits(w, "stop_remediation_skipped_pending_exit")         # the sync's orphan repair
    assert _audits(w, "stop_ack_broker_covered")                       # the watchdog


@pytest.mark.asyncio
async def test_dedupe_after_the_sale_filled_no_site_sells_again(monkeypatch):
    """Layer (c): the sale filled, the position is gone, the row is closed. A caller still holding
    the old count (the sync passes its start-of-run broker quantity) reaches its placement, is
    refused, and the shared path re-reads the book at sale time → 0 → nothing sent."""
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _ruling3_sold_world()

    async def _the_sale_filled_and_the_row_closed():
        for o in w.broker_orders:
            if o["type"] == "market":
                o["status"], o["filled_qty"] = "filled", o["qty"]
        for o in w.orders:
            if o["purpose"] == "full_exit":
                o["status"] = "filled"
        w.positions.pop("KOD", None)
        w.trades[401].update(status="closed", remaining_shares=0, stop_order_id=None)

    await _drive(w, _ruling3_sale(), _the_sale_filled_and_the_row_closed, *_then_every_site(w))
    assert _sales(w) == [None, 10], [c for c in w.calls if c["method"] == "close_position"]
    assert len(_full_exit_rows(w)) == 1
    # site 1 (called with the stale quantity) reaches its placement, is refused, and the shared path
    # re-reads the book at sale time: closed row + no position → 0 (layer c)
    assert ("order_manager.ensure_stop_coverage", "fallback:position_unreadable") in _skips(w)


@pytest.mark.asyncio
async def test_dedupe_the_shared_path_itself_sizes_zero_in_each_state():
    """The three layers, one at a time, straight through `_sell_at_market_for_refused_stop`."""
    from agents.market_intelligence.broker import alpaca_client as ac

    def _call():
        return om._sell_at_market_for_refused_stop(
            401, "KOD", "live", stop_price=58.0, site="test.dedupe",
            refusal=Exception(BREACH))

    # (a) the queued sale holds the shares at the broker
    w = _ruling3_sold_world()
    [_, out] = await _drive(w, _ruling3_sale(), _call)
    assert out is None and _sales(w) == [None, 10]
    assert _audits(w, "stop_breach_sale_skipped")[0]["qty_source"] == "broker"

    # (b) the broker cannot be read: the book fallback nets the pending sale → 0
    w = _ruling3_sold_world()

    async def _broker_unreadable():
        async def _none(ticker, account_mode=None):
            return None
        ac.get_position = _none                                # restored by the harness on exit

    [_, _, out] = await _drive(w, _ruling3_sale(), _broker_unreadable, _call)
    assert out is None and _sales(w) == [None, 10]
    assert _audits(w, "stop_breach_sale_skipped")[0]["qty_source"].startswith("fallback")

    # (c) filled and closed: no position, no open row → 0
    w = _ruling3_sold_world()

    async def _filled():
        w.positions.pop("KOD", None)
        w.trades[401].update(status="closed", remaining_shares=0)

    [_, _, out] = await _drive(w, _ruling3_sale(), _filled, _call)
    assert out is None and _sales(w) == [None, 10]



@pytest.mark.asyncio
async def test_site3_a_raising_sale_path_never_escapes_update_stop(monkeypatch):
    """2026-10-03 review fix: if the shared sale path RAISES (its order-row insert failed after the
    broker accepted), update_stop must not raise into the 16:45 loop (no per-trade try there): it
    logs and takes today's NAKED path, which pages him."""
    w = _raise_world()
    _breach(w)

    async def _boom(*a, **k):
        raise RuntimeError("mi_live_orders insert failed")
    monkeypatch.setattr(om, "_sell_at_market_for_refused_stop", _boom)
    [out] = await _drive(w, _raise())
    assert out is False
    assert len(_naked_pages(w)) == 1
