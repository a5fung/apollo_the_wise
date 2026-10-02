"""#566 build flag 2 — the WS cancel handler is the check that could REGRESS.

When an OCO's sibling stop leg FILLS, the broker CANCELS the parent (the
resting limit). That cancel event lands in `_handle_cancel_or_reject` section 3
(purpose='partial_exit'), whose pre-#566 behaviour for ANY cancelled partial
was: cancel the trade's stop_order_id, then place a FULL-remaining stop. On an
OCO parent that sequence is catastrophic: it kills the 2/3's GOOD breakeven
stop, then the full-size restore is rejected 40310000 (the third's shares are
gone) — the position ends up genuinely naked, announced as protected. That is
the same wrong-reading class (`get_open_orders` hides the held leg / an event
misread as naked) that produced this whole task.

Pinned here:
  - OCO parent cancelled + sibling leg FILLED  -> NO stop cancel, NO restore,
    audit only (the leg's own fill event owns the accounting);
  - OCO parent cancelled + leg dead too (operator cancelled the pair) -> the
    third IS uncovered -> re-protect via _ensure_stop_coverage (broker-truth,
    idempotent), still never the blind cancel-and-restore;
  - leg UNREADABLE -> fail-safe = same as dead (re-protect; _ensure_stop_coverage
    no-ops if actually covered);
  - a PLAIN (non-OCO) cancelled partial keeps the historical restore
    byte-for-byte;
  - a cancelled partial that had PARTIALLY FILLED commits the filled portion
    via finalize_partial_exit BEFORE any restore (those shares SOLD — dropping
    them is defect 2's mirror image).

Mutation checks recorded per test.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool


OCO_PARENT_RAW = json.dumps({
    "id": "oco-parent-1", "order_class": "oco", "type": "limit", "side": "sell",
    "qty": 5.0,
    "legs": [{"id": "oco-leg-1", "type": "stop", "status": "held",
              "qty": 5.0, "stop_price": 55.20}],
})
PLAIN_RAW = json.dumps({"id": "plain-limit-1", "order_class": "simple",
                        "type": "limit", "side": "sell", "qty": 5.0})


def _cancel_data(*, order_id="oco-parent-1", filled_qty=0.0, avg=None):
    order = SimpleNamespace(
        id=order_id, symbol="ETON", status="canceled",
        filled_qty=filled_qty, filled_avg_price=avg, qty=5.0, side="sell",
        type="limit", limit_price=59.58, stop_price=None,
        canceled_at=None, failed_at=None, expired_at=None, updated_at=None,
    )
    return SimpleNamespace(order=order, event="canceled", reason=None)


def _wire(monkeypatch, *, pending_exit_row, trade_row=None, leg_order=None,
          position_qty=17.0):
    """Mock the handler's DB/broker surface for one cancel event.

    fetchrow order: entry-trade lookup (None), stop-trade lookup (None), the
    pending-exit UPDATE..RETURNING, then (branch-dependent) the trade-row read.
    """
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[None, None, pending_exit_row, trade_row])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    sent: list = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", _audit)
    monkeypatch.setattr(ts, "send_telegram_message", _tg)

    get_order_mock = AsyncMock(return_value=leg_order)
    cancel_mock = AsyncMock(return_value=True)
    place_stop_mock = AsyncMock(return_value={"id": "restored-1", "status": "new"})
    get_pos_mock = AsyncMock(return_value={"qty": position_qty,
                                           "qty_available": 0.0})
    monkeypatch.setattr(ts.alpaca, "get_order", get_order_mock)
    monkeypatch.setattr(ts.alpaca, "cancel_order", cancel_mock)
    monkeypatch.setattr(ts.alpaca, "place_stop_order", place_stop_mock)
    monkeypatch.setattr(ts.alpaca, "get_position", get_pos_mock)

    ensure_cov_mock = AsyncMock(return_value="repaired to broker truth")
    monkeypatch.setattr(om, "_ensure_stop_coverage", ensure_cov_mock)
    set_stop_mock = AsyncMock()
    monkeypatch.setattr(om, "set_stop_order_id", set_stop_mock)
    finalize_mock = AsyncMock()
    monkeypatch.setattr(om, "finalize_partial_exit", finalize_mock)

    return {
        "conn": conn, "audited": audited, "sent": sent,
        "get_order": get_order_mock, "cancel": cancel_mock,
        "place_stop": place_stop_mock, "ensure_cov": ensure_cov_mock,
        "set_stop": set_stop_mock, "finalize": finalize_mock,
    }


def _pending(purpose="partial_exit", raw=OCO_PARENT_RAW, trade_id=731):
    return {"trade_id": trade_id, "purpose": purpose, "raw_response": raw}


# ── World A: sibling leg filled — the pair unwound as designed ─────────────────────


@pytest.mark.asyncio
async def test_oco_parent_cancel_with_filled_leg_never_touches_the_good_stop(monkeypatch):
    """THE REGRESSION TEST (#566 build flag 2, explicitly): parent cancelled
    because the sibling stop leg FILLED. The handler must NOT cancel the 2/3's
    stop and must NOT place any restore. MUTATION-PROVEN: deleting the
    `_is_oco_parent` branch (routing OCO parents down the plain-partial path)
    reddens this test — cancel_order fires on the good stop and a full-size
    place_stop_order follows."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(),
        # trade_row would only be read by the (wrong) plain path — give it one
        # anyway so the mutated code runs far enough to redden the assertions.
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 17,
                   "stop_price": 55.20, "stop_order_id": "stop23"},
        leg_order={"id": "oco-leg-1", "status": "filled", "stop_price": 55.20},
    )

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "live")

    h["cancel"].assert_not_called()
    h["place_stop"].assert_not_called()
    h["ensure_cov"].assert_not_called()
    assert any(e == "oco_parent_cancelled_sibling_filled" for e, *_ in h["audited"])


# ── World B: the whole OCO died unfilled — re-protect from broker truth ────────────


@pytest.mark.asyncio
async def test_oco_parent_cancel_with_dead_leg_reprotects_via_coverage_not_blind_restore(monkeypatch):
    """Operator cancelled the parent -> both legs die as a unit (probe Q3) ->
    the third is uncovered. Repair goes through _ensure_stop_coverage (sizes
    from broker qty minus pending exits, idempotent) — never the blind
    cancel-and-full-restore."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(),
        trade_row={"id": 731, "ticker": "ETON", "stop_price": 55.20,
                   "signal_type": "magna53"},
        leg_order={"id": "oco-leg-1", "status": "canceled", "stop_price": 55.20},
    )

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "live")

    h["cancel"].assert_not_called()
    h["place_stop"].assert_not_called()
    h["ensure_cov"].assert_awaited_once()
    args = h["ensure_cov"].call_args.args
    assert args[0] == 731 and args[1] == "ETON" and args[2] == 17.0
    assert any(e == "oco_parent_cancelled_unfilled" for e, *_ in h["audited"])
    assert any("OCO" in m for m in h["sent"])


@pytest.mark.asyncio
async def test_oco_parent_cancel_with_unreadable_leg_fails_safe_to_reprotect(monkeypatch):
    """A leg the broker cannot show us is NOT proof the third exited — fail-safe
    treats it as uncovered and re-protects (coverage repair no-ops if the leg
    actually filled and the shares are gone). MUTATION-PROVEN: treating an
    unreadable leg as 'filled' (skipping re-protect) reddens this test."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(),
        trade_row={"id": 731, "ticker": "ETON", "stop_price": 55.20,
                   "signal_type": "magna53"},
        leg_order=None,  # get_order returned None — read failed
    )

    await ts._handle_cancel_or_reject(_cancel_data(), "canceled", "live")

    h["ensure_cov"].assert_awaited_once()
    h["cancel"].assert_not_called()
    h["place_stop"].assert_not_called()


# ── Plain partial cancel — historical restore pinned unchanged ─────────────────────


@pytest.mark.asyncio
async def test_plain_partial_cancel_keeps_the_historical_full_restore(monkeypatch):
    """PIN: a cancelled PLAIN resting limit still runs the pre-#566 restore —
    cancel the reduced stop, place one sized for the full remaining. The OCO
    branch must not swallow the plain path."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 17,
                   "stop_price": 55.20, "stop_order_id": "stop23"},
    )

    await ts._handle_cancel_or_reject(
        _cancel_data(order_id="plain-limit-1"), "canceled", "live")

    h["cancel"].assert_awaited_once_with("stop23", account_mode="live")
    h["place_stop"].assert_awaited_once()
    ps_args = h["place_stop"].call_args.args
    assert ps_args[0] == "ETON" and ps_args[1] == 17
    h["ensure_cov"].assert_not_called()


# ── Partial fill before the cancel — the filled portion must be committed ──────────


@pytest.mark.asyncio
async def test_cancelled_partial_with_fills_commits_the_filled_portion_first(monkeypatch):
    """2 of 5 sold before the cancel: those shares LEFT the account — they must
    hit the books via finalize_partial_exit (idempotent per order_id) before
    any restore sizing. MUTATION-PROVEN: deleting the filled-portion commit
    reddens this test (finalize never called)."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 15,
                   "stop_price": 55.20, "stop_order_id": "stop23"},
    )

    await ts._handle_cancel_or_reject(
        _cancel_data(order_id="plain-limit-1", filled_qty=2.0, avg=59.10),
        "canceled", "live")

    h["finalize"].assert_awaited_once_with(731, 2, 59.10, "plain-limit-1")
    # restore still runs for the plain shape, sized off the post-commit re-read
    h["place_stop"].assert_awaited_once()


@pytest.mark.asyncio
async def test_oco_parent_cancel_with_fills_commits_before_the_leg_check(monkeypatch):
    """Same commit rule on the OCO shape: a partially-filled parent cancelled by
    the stop side firing must not lose the filled shares."""
    h = _wire(
        monkeypatch,
        pending_exit_row=_pending(),
        trade_row={"id": 731, "ticker": "ETON", "stop_price": 55.20,
                   "signal_type": "magna53"},
        leg_order={"id": "oco-leg-1", "status": "filled", "stop_price": 55.20},
    )

    await ts._handle_cancel_or_reject(
        _cancel_data(filled_qty=2.0, avg=59.58), "canceled", "live")

    h["finalize"].assert_awaited_once_with(731, 2, 59.58, "oco-parent-1")
    h["cancel"].assert_not_called()
    h["place_stop"].assert_not_called()
