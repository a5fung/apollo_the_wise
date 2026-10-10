"""#687 — the stream's expired / cancelled FULL-EXIT sale must re-place its stop (Day B, 2026-10-09).

THE EVIDENCE (`scripts/probes/_1008/dayB_pep_expiry_logs.out`): PEP's opening-auction sale EXPIRED
unfilled at 09:30:57. `trade_stream._handle_cancel_or_reject` §3 asked
`_broker_free_qty_for_restore(..., exclude_ids=(stop_order_id,))`, which still counted the JUST-EXPIRED
sale as holding every share -> `restore_qty <= 0 and source == 'broker'` -> "No stop re-placed"
and it returned. PEP had no stop 09:30:57 -> 09:35:00.

THE NARROW FIX (card 1 of docs/roadmap/weekend_build_cards_2026-10-10.md; the branch STAYS, so its
pages, its pointer reason `cancel_or_reject_restored` and the convergence cases s14/s15/s40 are
unchanged):
  1. the event's own (dead) sale id is excluded from the held count;
  2. a placement refused because the broker still HOLDS the shares hands off to
     `order_manager._retry_restore_while_shares_held` (0.5 s polls, <= 15 s) in a BACKGROUND task kept
     alive by a module-level strong-ref set, because alpaca-py awaits stream handlers one at a time;
  3. `signal_type` rides the branch's SELECT so the retry's mode-bound order id names the strategy.

The worlds come from the convergence harness (`tests/_convergence_687_harness.py` - NOT edited: its
sha256 is pinned by `test_687_toggle_off_convergence.py`, whose green run is the proof that s14/s15/s40
did not move). Time is fake: the harness makes `asyncio.sleep` yield once, so 30 polls cost nothing.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import alpaca_client as ac
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests._convergence_687_harness import (
    BREACH,
    World,
    _bsell,
    _mirror,
    _position,
    _trade,
    _ws_order,
)

HELD = ('{"available":"0","code":40310000,"existing_qty":"10","held_for_orders":"10",'
        '"message":"insufficient qty available for order (requested: 10, available: 0)"}')
OTHER_REFUSAL = '{"code":40010001,"message":"qty must be > 0"}'


async def _drive(w, *steps):
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)


def _placed(w) -> list:
    return [c["args"] for c in w.calls if c["method"] == "place_stop_order"]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


async def _drain():
    """The step a test runs INSIDE the `_drive` span to let the background retry finish."""
    tasks = list(ts._RESTORE_RETRY_BG_TASKS)
    if tasks:
        await asyncio.gather(*tasks)


def _day_b_world(event="expired", *, sale_status="new", available=0.0):
    """Day B: a 10-sh position with NO stop on it (pointer NULL), a queued full-exit sale that the
    stream has just been told is dead - but the broker still LISTS it as live and still holds every
    share for it."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, available)
    _bsell(w, "sell-q", "KOD", 10, status=sale_status)
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted",
            exit_reason="sma_trail_stop")
    return w


def _event(event="expired"):
    return lambda: ts._handle_cancel_or_reject(
        _ws_order("sell-q", "KOD", status=event), event, "live")


def _free_after(w, n_sleeps):
    """A step: from the n-th poll sleep on, the broker has released the dead sale's shares."""
    async def _arm():
        state = {"n": 0}
        real = asyncio.sleep

        async def _sleep(*a, **k):
            state["n"] += 1
            if state["n"] >= n_sleeps:
                w.positions["KOD"]["qty_available"] = 10.0
                for o in w.broker_orders:
                    if o["id"] == "sell-q":
                        o["status"] = "expired"
            await real(0)
        asyncio.sleep = _sleep                          # restored by the harness on exit
    return _arm


# ── 1. the dead sale is no longer counted as holding the shares ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_dead_sale_the_broker_still_lists_live_does_not_hide_the_stop():
    w = _day_b_world()
    await _drive(w, _event("expired"))
    assert [p["qty"] for p in _placed(w)] == [10], w.calls     # placed on the FIRST attempt
    assert not ts._RESTORE_RETRY_BG_TASKS, "no retry needed: the first attempt took"
    [page] = w.pages
    assert page.endswith("Position still open. Stop re-placed @$58.00 for 10 sh."), page
    assert "No stop re-placed" not in page
    assert w.trades[401]["stop_order_id"], w.trades[401]
    reasons = [json.loads(a["detail"] or "{}").get("reason") for a in w.audits]
    assert "cancel_or_reject_restored" in reasons, w.audits


@pytest.mark.asyncio
async def test_a_resting_third_still_holds_its_own_shares_beside_the_dead_sale():
    """The exclusion drops ONLY the dead sale: a live +8R OCO third keeps the 3 shares it holds."""
    w = _day_b_world()
    w.positions["KOD"]["qty"] = 13.0
    H._boco(w, "oco-1", "KOD", 3)
    await _drive(w, _event("expired"))
    assert [p["qty"] for p in _placed(w)] == [10], w.calls


# ── 2. refused for held shares -> the background retry places it ─────────────────────────────────

@pytest.mark.asyncio
async def test_held_refusal_is_retried_in_the_background_and_the_handler_returns_first():
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]
    seen = {}

    async def _after_handler():
        seen["placed"] = len(_placed(w))
        seen["pages"] = list(w.pages)
        seen["tasks"] = len(ts._RESTORE_RETRY_BG_TASKS)

    await _drive(w, _free_after(w, 2), _event("expired"), _after_handler, _drain)

    assert seen == {"placed": 1, "pages": [], "tasks": 1}, seen   # only the refused attempt, no page yet
    assert [p["qty"] for p in _placed(w)] == [10, 10], w.calls
    [page] = w.pages
    assert page.endswith("Position still open. Stop re-placed @$58.00 for 10 sh."), page
    [row] = _audits(w, "stop_restore_retried")
    assert row["qty"] == 10 and row["stop_price"] == 58.0 and row["attempts"] == 2, row
    assert not _audits(w, "stop_restore_retry_ended")
    assert w.trades[401]["stop_order_id"], w.trades[401]
    reasons = [json.loads(a["detail"] or "{}").get("reason") for a in w.audits]
    assert "cancel_or_reject_restored" in reasons, w.audits
    assert not ts._RESTORE_RETRY_BG_TASKS, "the strong-ref set drains when the task ends"


@pytest.mark.asyncio
async def test_the_retry_names_the_strategy_on_its_client_order_id(monkeypatch):
    """The fake connection returns the whole row whatever the SELECT asks for, so the order id alone
    cannot show the column is fetched (review 10-10: dropping `signal_type` from the SELECT stayed
    green, and in prod `trade_row["signal_type"]` would then raise inside the except, with no page).
    The SELECT the branch sends is recorded and must name the column."""
    seen_sql: list[str] = []
    real = H.FakeConn._trades_query

    def _spy(self, kind, s, args):
        seen_sql.append(s)
        return real(self, kind, s, args)

    monkeypatch.setattr(H.FakeConn, "_trades_query", _spy)
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]
    await _drive(w, _free_after(w, 1), _event("cancelled"), _drain)
    retry = _placed(w)[1]
    assert str(retry["client_order_id"]).startswith("apollo_live_magna53_KOD_"), retry
    branch = [q for q in seen_sql if "remaining_shares, stop_price, stop_order_id" in q]
    assert branch and all("signal_type" in q for q in branch), seen_sql


@pytest.mark.asyncio
async def test_the_retry_does_not_count_the_dead_sale_as_held_when_a_poll_read_is_empty():
    """`also_exclude_ids` reaches the retry's own free-share read: a poll whose position read comes
    back empty asks `_broker_free_qty_for_restore`, and the dead sale must not make that read think
    every share is covered (that would end the wait as 'covered' instead of waiting)."""
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]
    state = {"polls": 0}

    async def _blank_first_poll():
        real = ac.get_position

        async def _gp(ticker, account_mode=None):
            state["polls"] += 1
            if state["polls"] == 2:      # call 1 = the branch's sizing read, call 2 = the first poll
                return None
            return await real(ticker, account_mode=account_mode)
        ac.get_position = _gp

    await _drive(w, _free_after(w, 3), _blank_first_poll, _event("expired"), _drain)
    assert len(_placed(w)) == 2 and not _audits(w, "stop_restore_retry_ended"), (w.calls, w.audits)


# ── 3. the window runs out -> the existing FAILED page + the ended row ───────────────────────────

@pytest.mark.asyncio
async def test_held_throughout_the_window_ends_with_the_existing_failed_page():
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]
    await _drive(w, _event("expired"), _drain)
    assert len(_placed(w)) == 1, "never re-placed while the broker showed the shares held"
    [page] = w.pages
    assert "CLOSE EXPIRED + STOP RESTORE FAILED* for KOD" in page, page
    assert "Position may be unprotected" in page, page
    [row] = _audits(w, "stop_restore_retry_ended")
    assert row["outcome"] == om.RESTORE_FAILED and row["polls"] == om._RESTORE_RETRY_POLLS, row
    assert not _audits(w, "stop_restore_retried")


# ── 4. the other outcomes map to the branch's existing pages ─────────────────────────────────────

@pytest.mark.asyncio
async def test_price_through_the_stop_during_the_retry_sells_at_market_with_the_existing_page():
    w = _day_b_world()
    w.place_errors = [Exception(HELD), Exception(BREACH)]
    await _drive(w, _free_after(w, 1), _event("expired"), _drain)
    [page] = w.pages
    assert "Close order EXPIRED" in page and "already below the stop $58.00" in page, page
    assert "selling 10 sh at market now (Order sell-" in page, page
    assert any(c["method"] == "close_position" for c in w.calls), w.calls
    assert _audits(w, "stop_restore_retry_ended")[0]["outcome"] == om.RESTORE_SOLD


@pytest.mark.asyncio
async def test_a_flat_broker_during_the_retry_pages_the_existing_flat_text():
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]

    async def _vanish_on_first_poll():
        real = asyncio.sleep

        async def _sleep(*a, **k):
            w.positions.pop("KOD", None)
            await real(0)
        asyncio.sleep = _sleep

    await _drive(w, _vanish_on_first_poll, _event("expired"), _drain)
    [page] = w.pages
    assert page.endswith("\n" + om.FLAT_RESTORE_PAGE_BODY) and "Close order EXPIRED" in page, page
    assert len(_placed(w)) == 1


@pytest.mark.asyncio
async def test_another_refusal_stays_inline_and_never_spawns_a_task():
    w = _day_b_world()
    w.place_errors = [Exception(OTHER_REFUSAL)]
    await _drive(w, _event("rejected"))
    assert not ts._RESTORE_RETRY_BG_TASKS
    [page] = w.pages
    assert "CLOSE REJECTED + STOP RESTORE FAILED* for KOD" in page, page
    assert len(_placed(w)) == 1


@pytest.mark.asyncio
async def test_an_exception_inside_the_background_task_sends_the_failed_page(monkeypatch):
    w = _day_b_world()
    w.place_errors = [Exception(HELD)]

    async def _boom(*a, **k):
        raise RuntimeError("retry exploded")
    monkeypatch.setattr(om, "_retry_restore_while_shares_held", _boom)
    await _drive(w, _event("expired"), _drain)
    [page] = w.pages
    assert "STOP RESTORE FAILED* for KOD" in page and "retry exploded" in page, page
