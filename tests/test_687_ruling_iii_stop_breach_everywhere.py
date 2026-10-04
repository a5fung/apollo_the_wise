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
