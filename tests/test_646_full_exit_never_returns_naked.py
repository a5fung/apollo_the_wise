"""A failed full exit may leave the position OPEN. It may never leave it UNPROTECTED.

WHY (2026-09-11, OKTA, LIVE MONEY). The SMA trail fired at the close, `execute_full_exit` cancelled
the protective stop, and the sell was rejected — all inside one second:

    16:45:00  Full exit: cancelled stop 2f5ac5cb... (success=True)
    16:45:00  Failed to close position: available 0, held_for_orders 2
    16:45:00  WS event: canceled | OKTA          <- the cancel CONFIRMATION lands after

Alpaca acknowledges a cancel immediately but does not release `held_for_orders` until it settles,
so the very next call is rejected for insufficient quantity. **The cancel did not fail; the sell
raced it.** The function then sent one Telegram and returned False with the stop gone: 2 shares
naked from Friday 16:45, with no scheduled repair until Monday 09:31 — about 64 hours.

⚠ The #600 WS restore did NOT cover this. It keys off a PENDING exit order, and an exit that was
rejected never creates one — so the safety net cannot see the case that needs it most. The fix
belongs where the failure is known: inside `execute_full_exit`.

Alpaca has no atomic cancel-and-close for a single symbol (`close_position` takes no
`cancel_orders` flag; only `close_all_positions` does, and closing the whole book is not an option),
so cancel → wait → sell is the only available shape.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import order_manager as om

STOP_PRICE = 165.57
SHARES = 2


def _wire(monkeypatch, *, close_raises, available=SHARES, place_ok=True,
          remaining=SHARES, position_qty=None, pending_orders=(), open_orders=(),
          lock_events=None):
    """Minimal harness: a trade with a live stop, and an alpaca whose close either works or not.

    #687: `pending_orders` are the trade's `mi_live_orders` exit rows still working (dicts with
    alpaca_order_id / purpose / qty); `open_orders` is what the broker lists for the ticker.
    `lock_events` (a list) records the per-trade lock's enter/exit around the broker calls.
    """
    trade = {"id": 382, "ticker": "OKTA", "remaining_shares": remaining,
             "stop_price": STOP_PRICE, "stop_order_id": "stop-1", "account_mode": "live"}
    pending_orders = [dict(r) for r in pending_orders]
    executed: list = []

    class _Conn:
        async def fetchrow(self, q, *a):
            if "mi_live_trades" in q:
                return trade
            return pending_orders[0] if pending_orders else None
        async def fetch(self, q, *a, **k):
            return pending_orders if "mi_live_orders" in q else []
        async def execute(self, *a, **k):
            executed.append(a)
            return "UPDATE 1"
        async def fetchval(self, *a, **k):
            return None

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self, *a, **k): return _Acq()

    events = lock_events if lock_events is not None else []

    @asynccontextmanager
    async def _lock(trade_id):
        events.append(("lock", trade_id))
        try:
            yield
        finally:
            events.append(("unlock", trade_id))

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(om, "_trade_advisory_lock", _lock)
    monkeypatch.setattr(om, "current_account_mode", lambda: "live")
    sent = []
    monkeypatch.setattr(om, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "mode_prefix", lambda m: "")

    cancel = AsyncMock(side_effect=lambda *a, **k: events.append(("cancel",)) or True)
    close = AsyncMock(side_effect=Exception("insufficient qty available") if close_raises
                      else (lambda *a, **k: events.append(("sell", k.get("qty"))) or {"id": "sell-1"}))
    place = AsyncMock(return_value={"id": "stop-2"} if place_ok else {})
    position = AsyncMock(return_value={
        "qty": SHARES if position_qty is None else position_qty, "qty_available": available})
    # #687 ruling (i): a None single-position read is disambiguated by the positions LIST
    # (`get_all_positions(raise_on_error=True)`): a failure RAISES (unreadable → the books), an
    # empty list is FLAT. Default: the same position, listed.
    all_positions = AsyncMock(return_value=[{
        "symbol": "OKTA", "qty": SHARES if position_qty is None else position_qty,
        "qty_available": available}])
    orders = AsyncMock(return_value=[dict(o) for o in open_orders])
    monkeypatch.setattr(om.alpaca, "cancel_order", cancel)
    monkeypatch.setattr(om.alpaca, "close_position", close)
    monkeypatch.setattr(om.alpaca, "place_stop_order", place)
    monkeypatch.setattr(om.alpaca, "get_position", position)
    monkeypatch.setattr(om.alpaca, "get_all_positions", all_positions)
    monkeypatch.setattr(om.alpaca, "get_open_orders", orders)
    monkeypatch.setattr(om, "_EXIT_RELEASE_SLEEP_S", 0)
    # #687 2026-10-06: a restore refused for held shares now waits up to ~15 s for the release —
    # zero the poll sleep so a persistent refusal here costs no wall-clock time.
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0)
    return {"cancel": cancel, "close": close, "place": place, "pos": position, "sent": sent,
            "all_pos": all_positions, "orders": orders, "executed": executed, "events": events,
            "trade": trade}


@pytest.mark.asyncio
async def test_the_okta_case_a_rejected_sell_restores_the_stop(monkeypatch):
    """THE REGRESSION. Before the fix this returned False with nothing in place."""
    h = _wire(monkeypatch, close_raises=True)
    ok = await om.execute_full_exit(382, "sma_trail_stop")
    assert ok is False, "a rejected sell must still report failure"
    h["place"].assert_awaited_once()
    assert h["place"].await_args.args[2] == STOP_PRICE, "restored at the wrong price"
    assert h["place"].await_args.args[1] == SHARES


@pytest.mark.asyncio
async def test_the_page_says_the_position_is_protected_again(monkeypatch):
    """He acts on the Telegram, so the Telegram must say which state he is in."""
    h = _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    # ⚠ "RESTORED" alone is a substring of "STOP NOT RESTORED" — asserting it passes in BOTH
    # states, which is a test that cannot fail. Assert the positive sentence.
    assert any("Stop RESTORED" in m and "NOT RESTORED" not in m for m in h["sent"]), h["sent"]
    assert any("protected" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_failed_restore_says_UNPROTECTED_loudly(monkeypatch):
    """The one case where he must act himself — it may never be reported as routine."""
    h = _wire(monkeypatch, close_raises=True, place_ok=False)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert any("UNPROTECTED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_successful_exit_does_not_re_place_a_stop(monkeypatch):
    """The fix must not resurrect a stop on a position that actually closed."""
    h = _wire(monkeypatch, close_raises=False)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["place"].assert_not_awaited()


@pytest.mark.asyncio
async def test_it_waits_for_the_broker_to_free_the_shares_before_selling(monkeypatch):
    """The race itself: the shares are held when the cancel returns, so do not sell yet."""
    h = _wire(monkeypatch, close_raises=False, available=0)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert h["pos"].await_count >= om._EXIT_RELEASE_ATTEMPTS, (
        "it sold without waiting for the shares to be released")


@pytest.mark.asyncio
async def test_the_wait_is_an_optimisation_never_a_gate(monkeypatch):
    """A broker that reports oddly must NOT be able to block an exit — still try the sell."""
    h = _wire(monkeypatch, close_raises=False, available=0)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["close"].assert_awaited_once()


# ── A rejected exit must leave a ROW, not just a Telegram (#646 (d), 2026-09-11) ──────────────
#
# Reconstructing tonight's incident meant reading container logs an hour later and inferring the
# rest, because the rejection wrote nothing to mi_audit_log. A money-path failure that exists only
# in a chat message is the same recording gap as #184's four unexplained June cancels — those are
# permanently unknowable now, because container logs rotate.

@pytest.mark.asyncio
async def test_a_rejected_exit_writes_an_audit_row(monkeypatch):
    rows = []
    monkeypatch.setattr(om, "log_audit_event",
                        AsyncMock(side_effect=lambda e, s, d=None, **k: rows.append((e, s, d))))
    _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    assert any(e == "full_exit_rejected" for e, *_ in rows), [r[0] for r in rows]


@pytest.mark.asyncio
async def test_the_row_carries_what_a_diagnosis_needs(monkeypatch):
    """Ticker, reason, shares and the broker's own error — so the next one is one query, not an hour."""
    import json as _json
    rows = []
    monkeypatch.setattr(om, "log_audit_event",
                        AsyncMock(side_effect=lambda e, s, d=None, **k: rows.append((e, s, d))))
    _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    detail = _json.loads(next(d for e, _s, d in rows if e == "full_exit_rejected"))
    assert detail["ticker"] == "OKTA"
    assert detail["reason"] == "sma_trail_stop"
    assert detail["shares"] == SHARES
    assert detail["stop_price"] == STOP_PRICE
    assert "insufficient qty" in detail["error"]


@pytest.mark.asyncio
async def test_a_failed_audit_write_does_not_swallow_the_restore(monkeypatch):
    """The row is the diagnosis; the restore is the money. The row may never cost the restore."""
    monkeypatch.setattr(om, "log_audit_event", AsyncMock(side_effect=Exception("db down")))
    h = _wire(monkeypatch, close_raises=True)
    await om.execute_full_exit(382, "sma_trail_stop")
    h["place"].assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════════════════
# #687 (2026-10-01) — the close-below-line exit beside a resting +8R profit-take, its lock, and
# the restore sizing. The OCO third rests with its own target and breakeven stop (operator
# ruling 2026-09-29: it KEEPS them on a close-below sale); the other two thirds sit behind the
# trailing stop and are what the sale must sell. Each test below fails on the pre-#687 code.
# ══════════════════════════════════════════════════════════════════════════════════════════

OCO_ROW = {"alpaca_order_id": "oco-1", "purpose": "partial_exit", "qty": 2}


def _stop(order_id="stop-1", qty=4, status="new"):
    return {"id": order_id, "side": "sell", "type": "stop", "qty": qty, "filled_qty": 0,
            "status": status, "order_class": "simple"}


def _oco_parent(order_id="oco-1", qty=2, status="new"):
    return {"id": order_id, "side": "sell", "type": "limit", "qty": qty, "filled_qty": 0,
            "status": status, "order_class": "oco"}


def _audit_rows(monkeypatch):
    rows = []
    monkeypatch.setattr(om, "log_audit_event",
                        AsyncMock(side_effect=lambda e, s, d=None, **k: rows.append((e, s, d))))
    return rows


@pytest.mark.asyncio
async def test_a_resting_profit_take_no_longer_skips_the_sale(monkeypatch):
    """(a) THE BUG: 6 sh held, 2 under a resting OCO profit-take, 4 behind the trailing stop.
    Before: the dedup saw the pending partial and skipped the WHOLE exit (INFO log, False).
    After: the 4 stop-covered shares are sold and the OCO third is left alone."""
    _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6, available=4,
              pending_orders=[OCO_ROW], open_orders=[_stop(), _oco_parent()])
    ok = await om.execute_full_exit(382, "sma_trail_stop")

    assert ok is True, "a resting profit-take must not block selling the other two thirds"
    h["cancel"].assert_awaited_once()                     # the 2/3's stop, nothing else
    assert h["cancel"].await_args.args[0] == "stop-1"
    h["close"].assert_awaited_once()
    assert h["close"].await_args.kwargs.get("qty") == 4
    inserted = [a for a in h["executed"] if "INSERT INTO mi_live_orders" in a[0]]
    assert inserted and inserted[0][4] == 4.0, "the queued-sale row must carry the 4 sold"
    assert any("2 sh stay under the resting profit-take" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_the_sale_never_asks_for_more_than_the_broker_holds_free(monkeypatch):
    """(a) DB says 6 (2 resting), broker holds only 5: sell 5 − 2 = 3, never 4."""
    _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=5, available=3,
              pending_orders=[OCO_ROW], open_orders=[_stop(qty=3), _oco_parent()])
    await om.execute_full_exit(382, "sma_trail_stop")
    assert h["close"].await_args.kwargs.get("qty") == 3


@pytest.mark.asyncio
async def test_a_skip_that_remains_is_audited_and_paged(monkeypatch):
    """(a) Only the OCO third is left (2 sh, all held by it): nothing to sell. The skip is no
    longer an INFO line — it writes `full_exit_skipped` and pages, and touches NOTHING."""
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=2, position_qty=2, available=0,
              pending_orders=[OCO_ROW], open_orders=[_oco_parent()])
    ok = await om.execute_full_exit(382, "sma_trail_stop")

    assert ok is False
    h["cancel"].assert_not_awaited()
    h["close"].assert_not_awaited()
    assert any(e == "full_exit_skipped" for e, *_ in rows), [r[0] for r in rows]
    assert any("Full exit NOT placed" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_an_unreadable_broker_beside_a_resting_profit_take_cancels_nothing(monkeypatch):
    """(a) Cannot size the sale → do not cancel the stop (the position stays protected), page."""
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False, remaining=6, position_qty=6,
              pending_orders=[OCO_ROW])
    h["orders"].side_effect = Exception("broker 503")
    ok = await om.execute_full_exit(382, "sma_trail_stop")

    assert ok is False
    h["cancel"].assert_not_awaited()
    h["close"].assert_not_awaited()
    assert any(e == "full_exit_skipped" for e, *_ in rows)


@pytest.mark.asyncio
async def test_a_pending_full_exit_skip_is_paged_not_silent(monkeypatch):
    """(a) The dedup on an already-queued closing order stays — but it is audited and paged."""
    rows = _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=False,
              pending_orders=[{"alpaca_order_id": "sell-0", "purpose": "full_exit", "qty": 2}])
    ok = await om.execute_full_exit(382, "sma_trail_stop")

    assert ok is False
    h["cancel"].assert_not_awaited()
    assert any(e == "full_exit_skipped" for e, *_ in rows)
    assert h["sent"], "the skip must page"


@pytest.mark.asyncio
async def test_the_cancel_and_the_sell_happen_inside_the_per_trade_lock(monkeypatch):
    """(a)/(e) The whole cancel → sell sequence runs under the #151 per-trade lock."""
    events: list = []
    _wire(monkeypatch, close_raises=False, lock_events=events)
    await om.execute_full_exit(382, "sma_trail_stop")
    names = [e[0] for e in events]
    assert names[0] == "lock" and names[-1] == "unlock", names
    assert "cancel" in names and "sell" in names, names


# ── (c) the restore is sized from the broker, not from remaining_shares ─────────────────────

@pytest.mark.asyncio
async def test_the_restore_is_sized_from_the_broker_not_remaining_shares(monkeypatch):
    """(c) THE BUG: 6 held, the OCO parent holds 2, the stop was cancelled. The restore asked
    for 6 (remaining_shares, which still counts the OCO third) → the broker rejected it → the
    page said UNPROTECTED while the 4 really were naked. It must ask for 4."""
    h = _wire(monkeypatch, close_raises=False, position_qty=6, open_orders=[_oco_parent()])
    out = await om._restore_stop_after_failed_exit(382, "OKTA", 6, STOP_PRICE, "live")

    assert out == om.RESTORE_PLACED
    assert h["place"].await_args.args[1] == 4
    assert h["place"].await_args.args[2] == STOP_PRICE


@pytest.mark.asyncio
async def test_the_just_cancelled_stop_is_never_counted_as_held(monkeypatch):
    """(c) Alpaca acks a cancel before it settles, so the dying stop can still be listed `new`.
    Counting it would report "covered" a second before the stop is gone — a false all-clear.
    The exit's own cancelled stop is excluded: restore the 4, fail loudly if it was not gone."""
    h = _wire(monkeypatch, close_raises=False, position_qty=6,
              open_orders=[_stop(qty=4), _oco_parent()])
    out = await om._restore_stop_after_failed_exit(382, "OKTA", 6, STOP_PRICE, "live",
                                                   cancelled_stop_id="stop-1")
    assert out == om.RESTORE_PLACED
    assert h["place"].await_args.args[1] == 4


@pytest.mark.asyncio
async def test_another_live_stop_holding_every_share_is_reported_covered(monkeypatch):
    """(c) A DIFFERENT stop (not the one the exit cancelled) still holds the shares: placing a
    second one would be rejected and page a false UNPROTECTED. Report it as covered instead."""
    h = _wire(monkeypatch, close_raises=False, position_qty=6,
              open_orders=[_stop(order_id="stop-9", qty=4), _oco_parent()])
    out = await om._restore_stop_after_failed_exit(382, "OKTA", 6, STOP_PRICE, "live",
                                                   cancelled_stop_id="stop-1")
    assert out == om.RESTORE_COVERED
    h["place"].assert_not_awaited()


@pytest.mark.asyncio
async def test_the_exit_passes_its_cancelled_stop_to_the_restore(monkeypatch):
    """(c) End to end: the sale is rejected while the broker still lists the cancelled stop as
    `new` — the restore must still go out for the 4 free shares, never "covered"."""
    _audit_rows(monkeypatch)
    h = _wire(monkeypatch, close_raises=True, remaining=6, position_qty=6, available=4,
              pending_orders=[OCO_ROW], open_orders=[_stop(), _oco_parent()])
    ok = await om.execute_full_exit(382, "sma_trail_stop")
    assert ok is False
    h["place"].assert_awaited_once()
    assert h["place"].await_args.args[1] == 4
    assert any("Stop RESTORED" in m for m in h["sent"]), h["sent"]


@pytest.mark.asyncio
async def test_a_pending_cancel_stop_does_not_count_as_held(monkeypatch):
    """(c) A stop we just cancelled can still be listed as pending_cancel — it protects nothing
    and must not shrink the restore."""
    h = _wire(monkeypatch, close_raises=False, position_qty=6,
              open_orders=[_stop(qty=4, status="pending_cancel"), _oco_parent()])
    await om._restore_stop_after_failed_exit(382, "OKTA", 6, STOP_PRICE, "live")
    assert h["place"].await_args.args[1] == 4


@pytest.mark.asyncio
async def test_an_unreadable_broker_restores_from_the_fallback_never_zero(monkeypatch):
    """(c) An UNREADABLE broker (the single-position read returned nothing and the positions list
    read failed) → the caller's count, never zero (a read hiccup must not leave the position bare).
    #687 ruling (i) 2026-10-02 split "unreadable" from "flat" — the flat case is the next test."""
    h = _wire(monkeypatch, close_raises=False)
    h["pos"].return_value = None
    h["all_pos"].side_effect = Exception("HTTP 503 Service Unavailable")
    out = await om._restore_stop_after_failed_exit(382, "OKTA", 3, STOP_PRICE, "live")
    assert out == om.RESTORE_PLACED
    assert h["place"].await_args.args[1] == 3


@pytest.mark.asyncio
async def test_a_flat_broker_places_nothing(monkeypatch):
    """⚖ #687 ruling (i), operator 2026-10-02: the broker shows NO position (a real zero — the
    single read returned nothing and the list read succeeded without the ticker) → nothing to
    protect, no stop placed, RESTORE_FLAT. Before this the books stood in and a sell stop was
    placed on shares we did not hold."""
    h = _wire(monkeypatch, close_raises=False)
    h["pos"].return_value = None
    h["all_pos"].return_value = []
    out = await om._restore_stop_after_failed_exit(382, "OKTA", 3, STOP_PRICE, "live")
    assert out == om.RESTORE_FLAT
    h["place"].assert_not_awaited()
    line = om._restore_outcome_line(out, STOP_PRICE)
    assert "no position" in line.lower() and "UNPROTECTED" not in line


@pytest.mark.asyncio
async def test_the_stream_restore_after_a_cancelled_close_is_sized_from_the_broker(monkeypatch):
    """(c) trade_stream: the queued sale was cancelled/expired at the broker. The restore asked
    for int(remaining_shares) = 6 while the OCO third held 2 → rejected → "STOP RESTORE FAILED".
    It must ask for the 4 that are actually free."""
    from agents.market_intelligence.broker import trade_stream as ts
    from tests.test_oco_cancel_handler_566 import PLAIN_RAW, _cancel_data, _pending
    from tests.test_oco_cancel_handler_566 import _wire as _ws_wire

    h = _ws_wire(
        monkeypatch,
        pending_exit_row=_pending(purpose="full_exit", raw=PLAIN_RAW),
        trade_row={"id": 731, "ticker": "ETON", "remaining_shares": 6,
                   "stop_price": 55.20, "stop_order_id": None},
        position_qty=6.0,
    )
    monkeypatch.setattr(ts.alpaca, "get_open_orders", AsyncMock(return_value=[_oco_parent()]))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=2))
    await ts._handle_cancel_or_reject(_cancel_data(order_id="sell-1"), "canceled", "live")

    h["place_stop"].assert_awaited_once()
    assert h["place_stop"].await_args.args[1] == 4
    assert any("for 4 sh" in m for m in h["sent"]), h["sent"]


# ── (b) a full exit that leaves the profit-take third at the broker keeps the row open ──────

def _finalize_harness(monkeypatch, *, remaining):
    trade = {"id": 404, "ticker": "KOD", "remaining_shares": remaining, "entry_price": 63.15,
             "exits": [], "account_mode": "live", "stop_order_id": None}
    executed: list = []

    class _Conn:
        async def fetchrow(self, q, *a):
            return trade
        async def execute(self, *a, **k):
            executed.append(a)
            return "UPDATE 1"

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self, *a, **k): return _Acq()

    @asynccontextmanager
    async def _lock(_trade_id):
        yield

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(om, "_trade_advisory_lock", _lock)
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "mode_prefix", lambda m: "")
    sent: list = []
    monkeypatch.setattr(om, "send_telegram_message",
                        AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))
    return executed, sent


@pytest.mark.asyncio
async def test_a_partial_full_exit_fill_keeps_the_trade_open(monkeypatch):
    """(b) THE BUG: 4 of 6 sold, the 2-share profit-take third still at the broker. Before:
    status='closed', remaining_shares=0 — a closed trade the broker still holds. After: the row
    stays OPEN at 2."""
    executed, sent = _finalize_harness(monkeypatch, remaining=6)
    await om.finalize_full_exit(404, 4, 70.00, "sell-1", "sma_trail_stop")

    updates = [a for a in executed if "UPDATE mi_live_trades" in a[0]]
    assert len(updates) == 1
    sql, *params = updates[0]
    assert "status = 'closed'" not in sql, "a trade the broker still holds was recorded closed"
    assert "closed_at" not in sql
    assert params[2] == 2, f"remaining must drop to the 2 still held, got {params[2]}"
    assert any("2 sh remain" in m for m in sent), sent


@pytest.mark.asyncio
async def test_a_full_exit_fill_of_everything_still_closes_the_trade(monkeypatch):
    """(b) The common case — nothing resting — is unchanged: the fill closes the row at 0."""
    executed, sent = _finalize_harness(monkeypatch, remaining=6)
    await om.finalize_full_exit(404, 6, 70.00, "sell-1", "sma_trail_stop")
    sql = next(a[0] for a in executed if "UPDATE mi_live_trades" in a[0])
    assert "status = 'closed'" in sql and "remaining_shares = 0" in sql
    assert any("Closed" in m for m in sent), sent


# ── (e) the stop-ACK watchdog cannot re-place a stop between the exit's cancel and its sell ─

@pytest.mark.asyncio
async def test_the_watchdog_cannot_re_place_a_stop_mid_exit(monkeypatch):
    """(e) THE RACE, interleaved: the watchdog's 30-second tick lands between the exit's
    stop-cancel and its sell. The WS cancel handler has already nulled `stop_order_id`, and no
    sell is at the broker yet, so the pre-#687 watchdog (no lock) saw a naked position and
    placed a fallback stop at the ORIGINAL orb_low — reserving the shares the sale needed.
    It must defer to the exit's per-trade lock instead."""
    from datetime import datetime

    from agents.market_intelligence import briefing, db, scheduler

    held: set = set()

    @asynccontextmanager
    async def _lock(trade_id):
        held.add(trade_id)
        try:
            yield
        finally:
            held.discard(trade_id)

    @asynccontextmanager
    async def _try_lock(trade_id):
        yield trade_id not in held

    h = _wire(monkeypatch, close_raises=False)
    monkeypatch.setattr(om, "_trade_advisory_lock", _lock)
    monkeypatch.setattr(om, "_trade_advisory_try_lock", _try_lock)

    stuck_row = {"id": 382, "ticker": "OKTA", "account_mode": "live", "orb_low": 150.0,
                 "entry_shares": SHARES, "remaining_shares": SHARES,
                 "filled_at": datetime(2026, 9, 29, 13, 31), "entry_order_id": "entry-1"}

    class _WConn:
        async def fetch(self, *a, **k):
            return [stuck_row]
        async def fetchval(self, *a, **k):
            return None
        async def fetchrow(self, *a, **k):
            return {"status": "filled", "stop_order_id": None}

    class _WAcq:
        async def __aenter__(self): return _WConn()
        async def __aexit__(self, *a): return False

    class _WPool:
        def acquire(self, *a, **k): return _WAcq()

    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_WPool()))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock())

    async def _cancel_then_tick(*a, **k):
        await scheduler._stop_ack_timeout_watchdog_job()     # the tick lands HERE
        return True

    h["cancel"].side_effect = _cancel_then_tick
    ok = await om.execute_full_exit(382, "sma_trail_stop")

    assert ok is True
    h["place"].assert_not_awaited()   # no fallback stop was placed between cancel and sell
    h["close"].assert_awaited_once()


@pytest.mark.asyncio
async def test_the_watchdog_still_remediates_a_genuinely_naked_unlocked_trade(monkeypatch):
    """(e) The lock must not blind it: with nothing holding the trade, the same tick on a
    naked position still places the fallback stop."""
    from datetime import datetime

    from agents.market_intelligence import briefing, db, scheduler

    @asynccontextmanager
    async def _try_lock(trade_id):
        yield True

    h = _wire(monkeypatch, close_raises=False)
    monkeypatch.setattr(om, "_trade_advisory_try_lock", _try_lock)
    stuck_row = {"id": 382, "ticker": "OKTA", "account_mode": "live", "orb_low": 150.0,
                 "entry_shares": SHARES, "remaining_shares": SHARES,
                 "filled_at": datetime(2026, 9, 29, 13, 31), "entry_order_id": "entry-1"}

    class _WConn:
        async def fetch(self, *a, **k):
            return [stuck_row]
        async def fetchval(self, *a, **k):
            return None
        async def fetchrow(self, *a, **k):
            return {"status": "filled", "stop_order_id": None}

    class _WAcq:
        async def __aenter__(self): return _WConn()
        async def __aexit__(self, *a): return False

    class _WPool:
        def acquire(self, *a, **k): return _WAcq()

    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_WPool()))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock())
    await scheduler._stop_ack_timeout_watchdog_job()

    h["place"].assert_awaited_once()
    assert h["place"].await_args.args[2] == 150.0


# ══════════════════════════════════════════════════════════════════════════════════════════
# #687 cut-back — the ONE review-round item kept: the position sync never lowers the books under
# a queued sale (commit d2bc8c93). A loss CREATED by (a)+(b) on paper: the soft-reserved queued
# sale lowered the books to the OCO third's count, and the morning fill then closed the row
# (prior − sold → 0) while the third was still held.
# ══════════════════════════════════════════════════════════════════════════════════════════

def _sync_world(monkeypatch, *, db_trades, positions, reservation=(0, False),
                reservation_raises=None):
    """`_sync_positions_for_mode` with a fake pool that records every UPDATE, no broker stop to
    adopt, the coverage invariant stubbed (its own tests cover it), and `_pending_exit_reservation`
    set per test."""
    import json as _json

    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[dict(t) for t in db_trades])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audit: list = []

    async def _audit(event, summary="", detail=None, **k):
        audit.append((event, summary, _json.loads(detail) if detail else None))

    place = AsyncMock(return_value={"id": "remediated-1"})
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "_try_adopt_existing_stop", AsyncMock(return_value=None))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=0))
    monkeypatch.setattr(om, "set_stop_order_id", AsyncMock(return_value=True))
    monkeypatch.setattr(om, "_ensure_stop_coverage", AsyncMock(return_value=None))
    monkeypatch.setattr(om, "_read_preserved_dead_stop", AsyncMock(return_value=None))
    monkeypatch.setattr(om.alpaca, "get_all_positions", AsyncMock(return_value=positions))
    monkeypatch.setattr(om.alpaca, "place_stop_order", place)
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(return_value=None))
    monkeypatch.setattr(om, "_pending_exit_reservation",
                        AsyncMock(return_value=reservation, side_effect=reservation_raises))

    def _qty_writes():
        return [c.args[2] for c in conn.execute.await_args_list
                if "SET remaining_shares = $2" in c.args[0]]

    return {"conn": conn, "audit": audit, "place": place, "qty_writes": _qty_writes}


def _open_trade(remaining, **over):
    t = {"id": 404, "ticker": "KOD", "remaining_shares": remaining, "entry_price": 63.15,
         "status": "filled", "stop_order_id": "stop-live", "stop_price": 60.0, "orb_low": 58.0,
         "signal_type": "magna53"}
    t.update(over)
    return t


@pytest.mark.asyncio
async def test_the_sync_does_not_lower_the_books_under_a_queued_sale(monkeypatch):
    """THE ROOT OF THE FAKE CLOSE: 10 held; a 7-share sale is queued after hours beside the
    3-share OCO third. Paper soft-reserves the 7 and reports 3. The sync used to write 3 onto
    the row, so the morning fill took the books 3 − 7 → 0 and CLOSED the trade with the third
    still held. Now the books stay at 10 (3 reported + 10 reserved by our own pending exits)."""
    w = _sync_world(monkeypatch, db_trades=[_open_trade(10)],
                    positions=[{"symbol": "KOD", "qty": 3.0}], reservation=(10, True))
    await om._sync_positions_for_mode("paper")

    assert w["qty_writes"]() == [], "the sync lowered the books under a queued sale"
    assert [e for e, *_ in w["audit"] if e == "sync_qty_held_for_pending_exit"]


@pytest.mark.asyncio
async def test_the_sync_never_raises_the_books_while_a_sale_is_queued(monkeypatch):
    """The bound on what the lowering branch writes: broker + reserved (13) is ABOVE the books
    (10). The branch only ever lowers: nothing written, never 13."""
    w = _sync_world(monkeypatch, db_trades=[_open_trade(10)],
                    positions=[{"symbol": "KOD", "qty": 3.0}], reservation=(10, True))
    await om._sync_positions_for_mode("paper")
    assert 13 not in w["qty_writes"]() and w["qty_writes"]() == []


@pytest.mark.asyncio
async def test_the_sync_lowers_to_broker_plus_reserved_when_the_books_overstate(monkeypatch):
    """The books (12) overstate even counting the queued sale: broker 3 + reserved 7 = 10 →
    the row is lowered to 10, not to the soft-reserved 3."""
    w = _sync_world(monkeypatch, db_trades=[_open_trade(12)],
                    positions=[{"symbol": "KOD", "qty": 3.0}], reservation=(7, True))
    await om._sync_positions_for_mode("paper")
    assert w["qty_writes"]() == [10.0]


@pytest.mark.asyncio
async def test_the_sync_still_lowers_to_the_broker_with_no_sale_queued(monkeypatch):
    """No closing order pending → today's behaviour: the broker count is written."""
    w = _sync_world(monkeypatch, db_trades=[_open_trade(10)],
                    positions=[{"symbol": "KOD", "qty": 6.0}], reservation=(3, False))
    await om._sync_positions_for_mode("paper")
    assert w["qty_writes"]() == [6.0]


@pytest.mark.asyncio
async def test_an_unreadable_reservation_never_lowers_the_books(monkeypatch):
    w = _sync_world(monkeypatch, db_trades=[_open_trade(10)],
                    positions=[{"symbol": "KOD", "qty": 3.0}],
                    reservation_raises=Exception("db timeout"))
    await om._sync_positions_for_mode("paper")
    assert w["qty_writes"]() == []
    assert [e for e, *_ in w["audit"] if e == "sync_qty_lower_deferred"]
