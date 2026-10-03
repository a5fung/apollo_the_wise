"""#687 ruling (2), operator 2026-10-01 ("Yes"): silence the two FALSE "unprotected" pages.

(i) ON EVERY PLANNED SALE. The 16:45 close-below sale (`execute_full_exit`) and the 19:01
    opening-auction sale (`execute_depth_open_sale`) cancel the stop ON PURPOSE. The stream's
    stop-cancel handler (`trade_stream._handle_cancel_or_reject` §2) found no replacement stop and
    paged "Stop order CANCELED — Position unprotected" every time. The sale now writes a
    `planned_sale_stop_cancel` row naming the exact stop immediately before it cancels; the
    handler finds it and records the cancel instead of paging. The sale pages its own outcome.
(ii) ON A POSITION HELD ONLY BY ITS OCO THIRD. After the two thirds sell beside a resting +8R
    profit-take (#687 a+b), the row stays open at the third's size, fully held by the OCO. The
    16:20 / 09:35 stop refresh could not size a stop (pending exits cover everything) and paged
    "No stop on X ... unprotected". It now asks the broker the #527 detector's own coverage
    question (live stops + OCO parents + our queued closing order) and pages only on a real gap.

THE CONSTRAINT THAT MATTERS MOST: a GENUINELY uncovered position must STILL page — proven below for
both pages (a hand-cancelled stop with no marker; no stop and no resting exit at the refresh; a
plain resting LIMIT, which protects nothing — the #566 rule).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests.test_646_full_exit_never_returns_naked import _wire as _exit_wire
from tests.test_stop_reason_560 import _make_ws_pool, _ws_data

TRADE_ID = 382
STOP_ID = "stop-1"


def _marker(trade_id=TRADE_ID, stop_id=STOP_ID):
    return {"event_type": om.PLANNED_SALE_STOP_CANCEL,
            "detail": json.dumps({"trade_id": trade_id, "stop_order_id": stop_id,
                                  "ticker": "OKTA", "reason": "sma_trail_stop"})}


async def _fire_stop_cancel(monkeypatch, audit_rows, *, order_id=STOP_ID):
    """§2 with no replacement found on either look (the planned-sale shape)."""
    stop_row = {"id": TRADE_ID, "ticker": "OKTA", "remaining_shares": 2.0, "stop_price": 165.57,
                "entry_price": 160.0, "hard_stop": 150.0}
    pool, conn, audit, sent, capture = _make_ws_pool(stop_row, None, None, dup_rows=audit_rows)
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", audit)
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock())
    confirm = AsyncMock(side_effect=[None, None])
    monkeypatch.setattr(ts, "_broker_confirm_replacement_stop", confirm)
    monkeypatch.setattr(ts, "_STOP_CANCEL_RECHECK_DELAY_S", 0)
    monkeypatch.setattr(ts, "send_telegram_message", capture)
    await ts._handle_cancel_or_reject(_ws_data(order_id=order_id, symbol="OKTA"),
                                      "canceled", "live")
    return sent, audit, confirm, conn


# ── (i) the planned sale's own stop cancel ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_stop_our_planned_sale_cancelled_is_not_paged_unprotected(monkeypatch):
    sent, audit, confirm, _ = await _fire_stop_cancel(monkeypatch, [_marker()])
    assert sent == [], sent
    silent = [c for c in audit.await_args_list
              if c.args[0] == "stop_cancel_by_planned_sale_silent"]
    assert len(silent) == 1, audit.await_args_list
    assert json.loads(silent[0].args[2])["cancelled_order_id"] == STOP_ID
    assert confirm.await_count == 2, "the broker look is unchanged — only the page is silenced"


@pytest.mark.asyncio
async def test_a_genuinely_cancelled_stop_still_pages_unprotected(monkeypatch):
    """No marker (cancelled by hand / by the broker): the page goes out exactly as before."""
    sent, audit, _, _ = await _fire_stop_cancel(monkeypatch, [])
    assert len(sent) == 1 and "Position unprotected" in sent[0], sent
    assert not [c for c in audit.await_args_list
                if c.args[0] == "stop_cancel_by_planned_sale_silent"]


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [
    [_marker(stop_id="some-other-stop")],            # a planned sale cancelled ANOTHER stop
    [_marker(trade_id=999)],                         # ... on another trade
    [{"event_type": om.PLANNED_SALE_STOP_CANCEL, "detail": "not json"}],
    [{"event_type": "partial_exit_stop_telegram_pending",
      "detail": json.dumps({"trade_id": TRADE_ID, "stop_order_id": STOP_ID})}],
])
async def test_only_an_exact_marker_silences_the_page(monkeypatch, rows):
    sent, _, _, _ = await _fire_stop_cancel(monkeypatch, rows)
    assert len(sent) == 1 and "Position unprotected" in sent[0], sent


@pytest.mark.asyncio
async def test_an_unreadable_marker_still_pages(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")
    sent, _, _, _ = await _fire_stop_cancel(monkeypatch, _boom)
    assert len(sent) == 1 and "Position unprotected" in sent[0], sent


def _audit_capture(monkeypatch, events):
    async def _audit(evt, summary=None, detail=None, *a, **k):
        events.append((evt, json.loads(detail) if detail else None))
    monkeypatch.setattr(om, "log_audit_event", _audit)


@pytest.mark.asyncio
async def test_the_1645_sale_writes_the_marker_before_it_cancels(monkeypatch):
    events: list = []
    h = _exit_wire(monkeypatch, close_raises=False, lock_events=events)
    _audit_capture(monkeypatch, events)
    assert await om.execute_full_exit(TRADE_ID, "sma_trail_stop") is True
    marks = [i for i, e in enumerate(events) if e[0] == om.PLANNED_SALE_STOP_CANCEL]
    cancel_at = events.index(("cancel",))
    assert len(marks) == 1 and marks[0] < cancel_at, events
    detail = events[marks[0]][1]
    assert detail["trade_id"] == TRADE_ID and detail["stop_order_id"] == STOP_ID, detail
    h["cancel"].assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_marker_write_never_costs_the_sale(monkeypatch):
    h = _exit_wire(monkeypatch, close_raises=False)
    monkeypatch.setattr(om, "log_audit_event", AsyncMock(side_effect=Exception("db down")))
    assert await om.execute_full_exit(TRADE_ID, "sma_trail_stop") is True
    h["close"].assert_awaited_once()


@pytest.mark.asyncio
async def test_the_1901_auction_sale_writes_the_marker_before_it_cancels(monkeypatch):
    from tests.test_depth_exit_rule import _sale_wire
    h = _sale_wire(monkeypatch)

    async def _audit(evt, summary=None, detail=None, *a, **k):
        h["events"].append(("audit", evt))

    monkeypatch.setattr(om, "log_audit_event", _audit)
    assert await om.execute_depth_open_sale(501) is True
    names = [e[1] if e[0] == "audit" else e[0] for e in h["events"]]
    assert om.PLANNED_SALE_STOP_CANCEL in names, names
    assert names.index(om.PLANNED_SALE_STOP_CANCEL) < names.index("cancel"), names


# ── (ii) the stop refresh on a position held only by its OCO third ───────────────────────────

class _RConn:
    def __init__(self, trades):
        self.trades = trades

    async def fetch(self, *a, **k):
        return self.trades


class _RAcq:
    def __init__(self, c):
        self.c = c

    async def __aenter__(self):
        return self.c

    async def __aexit__(self, *e):
        return False


class _RPool:
    def __init__(self, c):
        self.c = c

    def acquire(self, *a, **k):
        return _RAcq(self.c)


def _oco_parent(qty=1, status="new"):
    return {"id": "oco-1", "side": "sell", "type": "limit", "order_class": "oco",
            "qty": qty, "filled_qty": 0, "status": status}


def _plain_limit(qty=1):
    return {"id": "lim-1", "side": "sell", "type": "limit", "order_class": "simple",
            "qty": qty, "filled_qty": 0, "status": "new"}


def _queued_sell(qty=1, order_id="sell-1"):
    return {"id": order_id, "side": "sell", "type": "market", "order_class": "simple",
            "qty": qty, "filled_qty": 0, "status": "accepted"}


async def _run_refresh(monkeypatch, open_orders, *, queued_ids=(), orders_raise=False,
                       label="Post-close"):
    trade = {"id": 404, "ticker": "KOD", "remaining_shares": 1, "stop_price": 63.15,
             "stop_order_id": None, "account_mode": "live"}
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=_RPool(_RConn([trade]))))
    monkeypatch.setattr(lt, "update_stop", AsyncMock(return_value=False))
    sent: list = []
    monkeypatch.setattr(lt, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    audited: list = []

    async def _audit(evt, summary=None, detail=None, *a, **k):
        audited.append((evt, json.loads(detail) if detail else None))
    monkeypatch.setattr(lt, "log_audit_event", _audit)

    async def _orders(*a, **k):
        if orders_raise:
            raise RuntimeError("broker down")
        return [dict(o) for o in open_orders]
    monkeypatch.setattr(om.alpaca, "get_open_orders", _orders)
    monkeypatch.setattr(om, "_pending_full_exit_order_ids", AsyncMock(return_value=set(queued_ids)))
    await lt._stop_refresh(include_same_day=True, label=label)
    return sent, audited


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Post-close", "Morning"])
async def test_a_position_held_only_by_its_oco_third_is_not_paged(monkeypatch, label):
    sent, audited = await _run_refresh(monkeypatch, [_oco_parent()], label=label)
    assert sent == [], sent
    assert not [e for e in audited if e[0] == "stop_refresh_failed"], audited
    ran = [d for e, d in audited if e == "stop_refresh_ran"]
    assert ran and ran[0]["covered_by_resting_exit"] == ["KOD"], ran


@pytest.mark.asyncio
async def test_our_queued_closing_order_is_not_paged(monkeypatch):
    sent, _ = await _run_refresh(monkeypatch, [_queued_sell()], queued_ids={"sell-1"})
    assert sent == [], sent


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Post-close", "Morning"])
async def test_a_genuinely_uncovered_position_still_pages(monkeypatch, label):
    sent, audited = await _run_refresh(monkeypatch, [], label=label)
    assert len(sent) == 1 and "No stop on KOD" in sent[0], sent
    assert [e for e in audited if e[0] == "stop_refresh_failed"], audited


@pytest.mark.asyncio
async def test_a_plain_resting_limit_protects_nothing_and_still_pages(monkeypatch):
    """#566: a bare limit above the market protects nothing on a decline."""
    sent, _ = await _run_refresh(monkeypatch, [_plain_limit()])
    assert len(sent) == 1 and "No stop on KOD" in sent[0], sent


@pytest.mark.asyncio
async def test_a_sell_order_that_is_not_ours_does_not_count_as_a_queued_exit(monkeypatch):
    sent, _ = await _run_refresh(monkeypatch, [_queued_sell(order_id="someone-else")],
                                 queued_ids={"sell-1"})
    assert len(sent) == 1, sent


@pytest.mark.asyncio
async def test_a_dead_oco_parent_does_not_count(monkeypatch):
    sent, _ = await _run_refresh(monkeypatch, [_oco_parent(status="canceled")])
    assert len(sent) == 1, sent


@pytest.mark.asyncio
async def test_an_unreadable_broker_still_pages(monkeypatch):
    sent, _ = await _run_refresh(monkeypatch, [_oco_parent()], orders_raise=True)
    assert len(sent) == 1 and "No stop on KOD" in sent[0], sent
