"""#566 DEFECT 2 — the accounting half, and it is the worse one.

ETON 2026-08-14: the reduced 2/3 stop (12 sh) filled and `_process_stop_fill` /
`_finalize_stop_fill_locked` marked the trade `status=closed, remaining_shares=0`
while the broker still held 5 shares behind the resting limit — no stop, no
trail, invisible to every surface reading the row. When the limit later filled,
the row went to `remaining_shares = -5`.

The invariant, pinned here for every terminal outcome:
  - a partial exit must NEVER mark a trade closed while shares remain;
  - remaining_shares must NEVER go negative (clamped at 0 + a LOUD
    `remaining_shares_clamped` audit row — a clamp firing means an earlier
    write already lied);
  - a fill that exhausts the position DOES close the trade (leaving
    remaining=0 on an open row is the mirror-image lie);
  - a partial-qty stop fill never triggers Day-1 re-entry (re-entering on top
    of shares still held would double the position);
  - a terminal partial_fill event for an order tracked ONLY in mi_live_orders
    (the resting limit / OCO parent / OCO leg) still routes to its finalizer.

Terminal outcomes covered: limit fills (part / last / over-fill replay of
ETON), stop fills (partial-qty / full / OCO-leg / over-fill), neither
(placement-side GTC pinned in test_oco_carveout_566), partial fill (routing +
cancel-commit in test_oco_cancel_handler_566).

Mutation checks recorded per test.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool


@asynccontextmanager
async def _noop_lock(_tid):
    yield


def _trade_row(*, remaining=17, status="filled", exits=None, entry=55.20,
               stop_order_id="stop23", ticker="ETON"):
    return {
        "id": 731, "ticker": ticker, "account_mode": "live",
        "remaining_shares": remaining, "status": status,
        "exits": exits or [], "entry_price": entry,
        "stop_order_id": stop_order_id, "entry_attempt": 1,
    }


def _wire_finalizer(monkeypatch, trade_row):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=trade_row)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    sent: list = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "_trade_advisory_lock", lambda tid: _noop_lock(tid))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "send_telegram_message", _tg)
    return conn, audited, sent


def _updates(conn, table="mi_live_trades"):
    return [c for c in conn.execute.call_args_list if f"UPDATE {table}" in c.args[0]]


# ── finalize_partial_exit — the limit side ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_fill_decrements_and_does_not_close_when_shares_remain(monkeypatch):
    """OCO limit fills 5 of 17 -> remaining 12, trade stays OPEN."""
    conn, audited, _ = _wire_finalizer(monkeypatch, _trade_row(remaining=17))

    await om.finalize_partial_exit(731, 5, 59.58, "limit-1")

    upd = _updates(conn)
    assert len(upd) == 1
    sql = upd[0].args[0]
    assert "status = 'closed'" not in sql and "closed_at" not in sql
    assert upd[0].args[3] == 12  # new remaining
    assert not any(e == "remaining_shares_clamped" for e, *_ in audited)


@pytest.mark.asyncio
async def test_limit_fill_of_the_last_shares_closes_the_trade(monkeypatch):
    """The 2/3 stopped earlier (row now open at 5); the OCO limit fills the last
    5 -> the trade CLOSES (status/closed_at/stop pointer cleared) in the same
    atomic UPDATE. MUTATION-PROVEN: forcing close_now=False (reverting the
    close-at-zero branch) reddens this test — remaining would sit at 0 on an
    'open' row forever."""
    conn, audited, sent = _wire_finalizer(monkeypatch, _trade_row(remaining=5))

    await om.finalize_partial_exit(731, 5, 59.58, "limit-1")

    upd = _updates(conn)
    assert len(upd) == 1
    sql = upd[0].args[0]
    assert "status = 'closed'" in sql and "closed_at = NOW()" in sql \
        and "stop_order_id = NULL" in sql, \
        "exhausting the position must CLOSE the row — remaining=0 on an open row is a lie"
    assert upd[0].args[3] == 0
    assert any(e == "partial_exit_committed" for e, *_ in audited)
    assert any("closed" in m.lower() for m in sent)


@pytest.mark.asyncio
async def test_limit_fill_on_an_already_zeroed_row_clamps_at_zero_never_negative(monkeypatch):
    """THE ETON REPLAY: the row was (wrongly) already closed at remaining=0 when
    the 5-share limit filled. Pre-fix this wrote remaining_shares=-5. It must
    clamp at 0 and scream. MUTATION-PROVEN: reverting new_remaining to the raw
    subtraction reddens this test (args[2] == -5)."""
    conn, audited, _ = _wire_finalizer(
        monkeypatch, _trade_row(remaining=0, status="closed"))

    await om.finalize_partial_exit(731, 5, 59.58, "limit-1")

    upd = _updates(conn)
    assert len(upd) == 1
    assert upd[0].args[3] == 0, "remaining_shares must NEVER go negative"
    assert "status = 'closed'" not in upd[0].args[0], "an already-closed row is not re-closed"
    clamps = [d for e, s, d in audited if e == "remaining_shares_clamped"]
    assert clamps, "the clamp must be RECORDED loudly — books already disagreed with the broker"
    detail = json.loads(clamps[0])
    assert detail["raw_remaining"] == -5 and detail["prior_remaining"] == 0


@pytest.mark.asyncio
async def test_limit_fill_is_idempotent_per_order_id(monkeypatch):
    """A duplicate WS fill for an order_id already in exits[] no-ops (pre-existing
    contract, re-pinned because the rewrite touched this function)."""
    row = _trade_row(remaining=12,
                     exits=[{"order_id": "limit-1", "shares": 5, "pnl": 1.0}])
    conn, _, _ = _wire_finalizer(monkeypatch, row)

    await om.finalize_partial_exit(731, 5, 59.58, "limit-1")

    assert _updates(conn) == []


# ── finalize_stop_fill — the stop side ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partial_qty_stop_fill_decrements_and_never_closes(monkeypatch):
    """THE CORE DEFECT-2 FIX: the reduced 2/3 stop (12 sh) fills on a 17-sh row
    -> remaining 5, trade stays OPEN; the tracked stop pointer is released via
    the SQL CASE (it just filled) while a non-matching pointer would survive.
    MUTATION-PROVEN: reverting _finalize_stop_fill_locked to the unconditional
    close (the pre-#566 body) reddens this test on all three assertions."""
    conn, audited, sent = _wire_finalizer(monkeypatch, _trade_row(remaining=17))

    await om.finalize_stop_fill(731, 12, 55.20, "stop23")

    upd = _updates(conn)
    assert len(upd) == 1
    sql = upd[0].args[0]
    assert "status = 'closed'" not in sql and "closed_at" not in sql, \
        "a partial-qty stop fill must NEVER mark the trade closed — shares remain at the broker"
    assert upd[0].args[3] == 5
    assert "CASE WHEN stop_order_id = $5" in sql, (
        "the pointer is nulled ONLY when the filled order IS the tracked stop — an "
        "unconditional NULL would drop the 2/3's stop pointer on an OCO-leg fill")
    assert upd[0].args[5] == "stop23"
    assert any("remain" in m for m in sent), "the operator must see that shares remain"


@pytest.mark.asyncio
async def test_oco_leg_stop_fill_decrements_without_matching_the_tracked_pointer(monkeypatch):
    """The OCO sibling stop (5 sh) fills while the 2/3's own stop still rests:
    remaining 17 -> 12, open, and the CASE receives the LEG's id (not the
    tracked pointer), so stop_order_id survives at the DB layer."""
    conn, _, _ = _wire_finalizer(monkeypatch, _trade_row(remaining=17))

    await om.finalize_stop_fill(731, 5, 55.20, "oco_leg_1")

    upd = _updates(conn)
    assert len(upd) == 1
    assert upd[0].args[3] == 12
    assert upd[0].args[5] == "oco_leg_1"
    assert "status = 'closed'" not in upd[0].args[0]


@pytest.mark.asyncio
async def test_full_qty_stop_fill_still_closes_exactly_as_before(monkeypatch):
    """PIN: the historical full-stop-out close is byte-compatible — status,
    remaining 0, pointer nulled, closed_at stamped."""
    conn, audited, _ = _wire_finalizer(monkeypatch, _trade_row(remaining=12))

    await om.finalize_stop_fill(731, 12, 55.20, "stop23")

    upd = _updates(conn)
    assert len(upd) == 1
    sql = upd[0].args[0]
    assert "status = 'closed'" in sql and "closed_at = NOW()" in sql \
        and "stop_order_id = NULL" in sql
    assert any(e == "stop_exit_committed" for e, *_ in audited)


@pytest.mark.asyncio
async def test_stop_fill_overfill_clamps_at_zero_with_loud_audit(monkeypatch):
    conn, audited, _ = _wire_finalizer(monkeypatch, _trade_row(remaining=5))

    await om.finalize_stop_fill(731, 12, 55.20, "stop23")

    upd = _updates(conn)
    assert "remaining_shares = 0" in upd[0].args[0]
    assert any(e == "remaining_shares_clamped" for e, *_ in audited)


# ── trade_stream._process_stop_fill — the WS path that actually zeroed ETON ─────────


def _wire_stop_fill(monkeypatch, fresh_row, *, alert_date_is_today=False):
    from datetime import date

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=fresh_row)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    sent: list = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    reentry_mock = AsyncMock(return_value={"action": "reentry_attempted"})
    today = date(2026, 8, 14)
    monkeypatch.setattr("agents.market_intelligence.collector.et_today", lambda: today)
    monkeypatch.setattr(om, "attempt_day1_reentry", reentry_mock)
    monkeypatch.setattr(om, "_trade_advisory_lock", lambda tid: _noop_lock(tid))
    monkeypatch.setattr(ts, "log_audit_event", _audit)
    monkeypatch.setattr(ts, "send_telegram_message", _tg)

    claim_trade = {
        "id": 731, "ticker": "ETON", "alert_date": today if alert_date_is_today
        else date(2026, 8, 13),
        "entry_attempt": 1, "entry_price": 55.20,
        "remaining_shares": fresh_row["remaining_shares"],
        "exits": [], "hold_days": 1,
    }
    return pool, conn, claim_trade, reentry_mock, audited, sent


@pytest.mark.asyncio
async def test_ws_partial_qty_stop_fill_decrements_keeps_open_and_never_reenters(monkeypatch):
    """THE ETON WRITE, replayed through the exact WS path: 12-sh stop fill on a
    17-sh day-1 row. Must (a) NOT attempt Day-1 re-entry (shares are still
    held — re-entering would double the position), (b) decrement to 5 and
    restore status='filled', (c) book P&L on 12 shares, not 17.
    MUTATION-PROVEN: dropping `full_stop_out` from the re-entry gate reddens
    (a); reverting the close branch to unconditional reddens (b)."""
    fresh = {"remaining_shares": 17, "exits": [], "status": "stop_processing"}
    pool, conn, claim, reentry, audited, sent = _wire_stop_fill(
        monkeypatch, fresh, alert_date_is_today=True)

    await ts._process_stop_fill(claim, 55.20, pool, "live", filled_qty=12)

    reentry.assert_not_called()
    upd = [c for c in conn.execute.call_args_list if "UPDATE mi_live_trades" in c.args[0]]
    assert len(upd) == 1
    sql = upd[0].args[0]
    assert "status = 'filled'" in sql and "status = 'closed'" not in sql
    assert upd[0].args[3] == 5  # new remaining
    # P&L booked on the 12 that actually sold — ETON booked 17 here pre-fix.
    exits_written = upd[0].args[2] if isinstance(upd[0].args[2], list) else json.loads(upd[0].args[2])
    assert exits_written[-1]["shares"] == 12
    assert any("remain" in m for m in sent)


@pytest.mark.asyncio
async def test_ws_full_stop_fill_on_day1_still_attempts_reentry(monkeypatch):
    """PIN: the historical full-stop-out day-1 path is unchanged — re-entry runs."""
    fresh = {"remaining_shares": 17, "exits": [], "status": "stop_processing"}
    pool, conn, claim, reentry, _, _ = _wire_stop_fill(
        monkeypatch, fresh, alert_date_is_today=True)

    await ts._process_stop_fill(claim, 55.20, pool, "live", filled_qty=17)

    reentry.assert_awaited_once()


@pytest.mark.asyncio
async def test_ws_full_stop_fill_day2_closes_exactly_as_before(monkeypatch):
    fresh = {"remaining_shares": 12, "exits": [], "status": "stop_processing"}
    pool, conn, claim, reentry, _, _ = _wire_stop_fill(monkeypatch, fresh)

    await ts._process_stop_fill(claim, 55.20, pool, "live", filled_qty=12)

    reentry.assert_not_called()
    upd = [c for c in conn.execute.call_args_list if "UPDATE mi_live_trades" in c.args[0]]
    assert len(upd) == 1
    assert "status = 'closed'" in upd[0].args[0]


@pytest.mark.asyncio
async def test_ws_unknown_filled_qty_preserves_historical_full_close(monkeypatch):
    """filled_qty=None (legacy caller / missing payload) keeps the pre-#566
    behaviour byte-for-byte: full close on all remaining."""
    fresh = {"remaining_shares": 12, "exits": [], "status": "stop_processing"}
    pool, conn, claim, reentry, _, _ = _wire_stop_fill(monkeypatch, fresh)

    await ts._process_stop_fill(claim, 55.20, pool, "live", filled_qty=None)

    upd = [c for c in conn.execute.call_args_list if "UPDATE mi_live_trades" in c.args[0]]
    assert "status = 'closed'" in upd[0].args[0]


# ── _handle_partial_fill — terminal routing for mi_live_orders-only orders ──────────


def _partial_fill_data(*, order_id="oco-parent-1", cum=5.0, total=5.0,
                       order_class="oco"):
    order = SimpleNamespace(
        id=order_id, symbol="ETON", filled_qty=cum, qty=total,
        filled_avg_price=59.58, side="sell", order_class=order_class,
    )
    return SimpleNamespace(order=order, qty=2.0, price=59.58)


@pytest.mark.asyncio
async def test_terminal_partial_for_mi_live_orders_only_order_routes_to_finalizer(monkeypatch):
    """The resting limit / OCO parent is NOT an entry/stop pointer on the trade
    row — pre-#566 the trade lookup returned None, is_terminal_partial stayed
    False, and a terminal state reported through partial_fill events (the ARM
    5/07 shape) was silently dropped. The mi_live_orders fallback closes that.
    MUTATION-PROVEN: deleting the fallback lookup reddens this test (finalizer
    never called)."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[
        None,                                  # entry/stop pointer lookup — no match
        {"id": 731, "ticker": "ETON"},         # #566 mi_live_orders fallback
        {"trade_id": 731, "purpose": "partial_exit", "exit_reason": None, "qty": 5.0},
    ])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", AsyncMock())
    monkeypatch.setattr(ts, "send_telegram_message", AsyncMock(return_value=True))
    finalize_mock = AsyncMock()
    monkeypatch.setattr(om, "finalize_partial_exit", finalize_mock)

    await ts._handle_partial_fill(_partial_fill_data(cum=5.0, total=5.0), "live")

    finalize_mock.assert_awaited_once_with(731, 5, 59.58, "oco-parent-1")


@pytest.mark.asyncio
async def test_nonterminal_oco_parent_partial_fill_records_the_unprobed_state(monkeypatch):
    """A multi-share OCO parent PARTIALLY filled (cum < total) is the ONE
    unprobed broker outcome (#566 build flag 1 — a 1-share OCO cannot
    partial-fill). No commit happens (deferred to the terminal event, the
    pre-existing contract), but the observation is recorded loudly so the
    sibling-leg behaviour can be verified at the broker the first time it
    happens for real."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[
        None,
        {"id": 731, "ticker": "ETON"},
    ])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(ts, "log_audit_event", _audit)
    sent: list = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _tg)
    finalize_mock = AsyncMock()
    monkeypatch.setattr(om, "finalize_partial_exit", finalize_mock)

    await ts._handle_partial_fill(_partial_fill_data(cum=2.0, total=5.0), "live")

    finalize_mock.assert_not_called()
    assert any(e == "oco_partial_fill_observed" for e, *_ in audited), \
        "the unprobed state must leave a durable observation marker"
    assert any("UNVERIFIED" in m for m in sent), \
        "the live Telegram must say the sibling-leg adjustment is unverified"
