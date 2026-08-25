"""#591 — the day-1 stop-out may NOT close the row while an exit is still working.

ETON 2026-08-14 (live money): 17 shares entered. At 09:35 the +2R carve-out placed a
RESTING limit for 5 and armed a stop on the other 12. At 09:45 that 12-share stop
filled and `attempt_day1_reentry` closed the row at `remaining_shares = 0` — while
five real shares sat live at the broker. They did not fill until 15:58, for +$21.89.
Prod pins the sequence: audit rows `r3_day1_reentry_blocked ETON 09:45:11` and
`position_unprotected: live stop qty 12 < 17 shares held` at 09:45:00, and
`mi_live_orders` id 295 (qty 5, purpose 'partial_exit', filled_at 19:58 UTC).

Put to the operator as a fork — keep the trade open, or cancel the resting order?
His ruling: *"if profit take is pending then why close it?"* The fork was false;
cancelling a resting profitable order was never an option. This is a BUG.

The row now stays OPEN at the shares still outstanding and closes only when the exit
that owns them resolves. The trigger is `new_remaining > 0` — the SAME branch
`trade_stream._process_stop_fill` has used since #566, because path divergence
between the websocket and polling stop-fill handlers is what produced this whole bug
family.

Also here: `get_pending_exit_qty` missed Alpaca's single-l `canceled` spelling, so a
cancelled exit order counted as "still working" and every stop sized against it came
out SMALL. Money-path behaviour, enumerated against the live and paper book before
shipping — it moves the pending quantity on zero trades
(`scripts/probes/_591_state_capture.sql` Q2/Q2B).
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.market_intelligence import audit_invariants as inv
from agents.market_intelligence.broker import order_manager as om

from tests.conftest import make_mock_pool


ETON_ENTRY = 55.2012
ETON_STOP_FILL = 55.05
ETON_LIMIT_FILL = 59.58


def _eton_row(*, remaining=17, status="filled", exits=None):
    """The ETON row as it stood at 09:45:11 — the 5-share partial still resting."""
    return {
        "id": 367, "ticker": "ETON", "entry_price": ETON_ENTRY, "entry_shares": 17,
        "remaining_shares": remaining, "orb_high": 55.4427, "orb_low": 53.01,
        "stop_price": 53.01, "atr_14": 2.696, "stop_order_id": "11b25e11",
        "entry_attempt": 1, "exits": exits if exits is not None else [],
        "ep_score": 96, "catalyst_quality": "game_changer", "gap_pct": 23.3,
        "regime": "Bull", "alert_date": date(2026, 8, 14), "account_mode": "live",
        "signal_type": "magna53", "status": status,
    }


def _wire(monkeypatch, row, *, held: int):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audited: list = []
    sent: list = []

    async def _audit(evt, summary="", detail=""):
        audited.append((evt, summary, detail))

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(om, "get_manual_halt_state", AsyncMock(return_value="off"))
    monkeypatch.setattr(om, "get_pending_exit_qty", AsyncMock(return_value=held))
    monkeypatch.setattr(om, "log_audit_event", _audit)
    monkeypatch.setattr(om, "send_telegram_message", _tg)
    monkeypatch.delenv("R3_DAY1_REENTRY_ENABLED", raising=False)
    return conn, audited, sent


def _trade_update(conn):
    """The single `UPDATE mi_live_trades` the call made, as (sql, args)."""
    upd = [c for c in conn.execute.call_args_list if "UPDATE mi_live_trades" in c.args[0]]
    assert len(upd) == 1, f"expected exactly one trade UPDATE, got {len(upd)}"
    return upd[0].args[0], upd[0].args


# ── THE BUG: five shares outside the books for six hours ──────────────────────


@pytest.mark.asyncio
async def test_eton_shape_leaves_the_row_open_at_the_shares_still_working(monkeypatch):
    """12 of 17 stopped, 5 resting → the row stays OPEN at 5. It used to close at 0.

    MUTATION-PROVEN: deleting the `if new_remaining > 0:` branch reddens this — the
    row goes back to `status='closed', remaining_shares=0` with 5 live shares.
    """
    conn, audited, sent = _wire(monkeypatch, _eton_row(), held=5)

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling", filled_qty=12)

    sql, args = _trade_update(conn)
    assert "status = 'filled'" in sql, "the position is real — the row must stay OPEN"
    assert "status = 'closed'" not in sql
    assert "closed_at" not in sql, "an open row has no close timestamp"
    assert "remaining_shares = $3" in sql and args[3] == 5
    assert "stop_order_id = NULL" in sql, "the day-1 stop is consumed; its pointer is dead"
    assert result["action"] == "stays_open"
    assert result["remaining_shares"] == 5
    assert any(e == "stop_fill_position_stays_open" for e, *_ in audited)
    assert "stays open" in sent[0]


@pytest.mark.asyncio
async def test_the_stop_leg_still_records_only_what_the_stop_sold(monkeypatch):
    """#588 must survive #591: the leg is 12, and total_pnl matches the leg sum."""
    conn, _, _ = _wire(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling", filled_qty=12)

    _, args = _trade_update(conn)
    exits = args[2] if isinstance(args[2], list) else json.loads(args[2])
    assert len(exits) == 1 and exits[0]["shares"] == 12
    assert exits[0]["reason"] == "stop_hit"
    assert args[4] == pytest.approx(sum(e["pnl"] for e in exits))


@pytest.mark.asyncio
async def test_no_reentry_is_attempted_while_shares_are_still_held(monkeypatch):
    """Re-entry is a FULL-stop-out concept. Buying on top of 5 live shares would
    double the position — the same gate `_process_stop_fill` applies via
    `full_stop_out`. Proven by the broker never being asked for a price."""
    conn, _, _ = _wire(monkeypatch, _eton_row(), held=5)
    monkeypatch.setenv("R3_DAY1_REENTRY_ENABLED", "true")
    latest = AsyncMock(return_value={"price": 56.0})
    monkeypatch.setattr(om.alpaca, "get_latest_trade", latest)
    monkeypatch.setattr(om.alpaca, "place_bracket_order", AsyncMock())
    monkeypatch.setattr(om.alpaca, "place_limit_buy_with_stop", AsyncMock())

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling", filled_qty=12)

    assert result["action"] == "stays_open"
    latest.assert_not_awaited()
    om.alpaca.place_bracket_order.assert_not_awaited()
    om.alpaca.place_limit_buy_with_stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_polling_loop_cannot_re_process_the_held_open_row(monkeypatch):
    """Leaving the row `status='filled'` with shares remaining would re-arm the
    polling scan on every tick and append a duplicate stop leg each time. Nulling
    `stop_order_id` is what keeps it out — the scan requires a non-null pointer."""
    conn, _, _ = _wire(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling", filled_qty=12)

    sql, _ = _trade_update(conn)
    assert "stop_order_id = NULL" in sql
    import inspect
    scan = inspect.getsource(om._check_day1_reentry)
    assert "stop_order_id IS NOT NULL" in scan


# ── The limit finally fills: THAT is what closes the trade ────────────────────


@pytest.mark.asyncio
async def test_the_resting_limit_filling_is_what_closes_the_trade(monkeypatch):
    """The whole point of the ruling: the row closes on the REAL final state.

    Drives the held-open row (remaining 5, one 12-share stop leg) through the actual
    partial-exit finalizer — the path the 15:58 fill takes — and asserts the close.
    """
    stop_leg = {
        "time": "2026-08-14T13:45:11+00:00", "price": ETON_STOP_FILL,
        "reason": "stop_hit", "shares": 12,
        "pnl": (ETON_STOP_FILL - ETON_ENTRY) * 12, "attempt": 1, "source": "polling",
    }
    row = _eton_row(remaining=5, exits=[stop_leg])
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(om, "log_audit_event", AsyncMock())
    monkeypatch.setattr(om, "send_telegram_message", AsyncMock(return_value=True))

    await om._finalize_partial_exit_locked(367, 5, ETON_LIMIT_FILL, "ee925e6b")

    sql, args = _trade_update(conn)
    assert "status = 'closed'" in sql and "closed_at = NOW()" in sql
    assert args[3] == 0, "all 17 shares are now accounted for"
    exits = args[2] if isinstance(args[2], list) else json.loads(args[2])
    assert sum(e["shares"] for e in exits) == 17, "12 stopped + 5 sold = 17 entered"
    assert args[4] == pytest.approx(20.0796, abs=1e-3), "the true P&L, not $19.32"


# ── The common case must not move ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_full_stop_out_with_nothing_resting_still_closes_immediately(monkeypatch):
    """THE unchanged path, and the common one: whole position stopped, no exit order
    working. Closes at zero exactly as before, same skip_reason, same return."""
    conn, audited, _ = _wire(monkeypatch, _eton_row(), held=0)

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=17)

    sql, args = _trade_update(conn)
    assert "status = 'closed'" in sql
    assert "remaining_shares = 0" in sql
    assert "closed_at = NOW()" in sql
    assert "block:r3_reentry_disabled" in sql
    assert result["action"] == "closed" and result["reason"] == "r3_disabled"
    exits = args[2] if isinstance(args[2], list) else json.loads(args[2])
    assert exits[0]["shares"] == 17
    assert not any(e == "stop_fill_position_stays_open" for e, *_ in audited)


@pytest.mark.asyncio
async def test_unknown_fill_quantity_with_nothing_resting_still_closes(monkeypatch):
    """The polling/WS payload with no quantity: `shares` falls back to the whole
    tracked remainder, so nothing is left over and the row closes as it always did."""
    conn, _, _ = _wire(monkeypatch, _eton_row(), held=0)

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling")

    sql, _ = _trade_update(conn)
    assert "status = 'closed'" in sql and "remaining_shares = 0" in sql
    assert result["action"] == "closed"


@pytest.mark.asyncio
async def test_a_stale_pending_exit_mirror_still_closes_on_the_broker_event(monkeypatch):
    """ADR 0008 — the broker wins. If the stop's confirmed fill consumed everything
    the books tracked while `mi_live_orders` still reserves shares, our MIRROR is
    stale (the broker could not have filled shares held for another order). Close on
    the confirmed event and say so loudly; never inflate remaining_shares to match a
    mirror that is already known wrong."""
    conn, audited, _ = _wire(monkeypatch, _eton_row(), held=5)

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=17)

    sql, _ = _trade_update(conn)
    assert "status = 'closed'" in sql and "remaining_shares = 0" in sql
    assert result["action"] == "closed"
    assert any(e == "pending_exit_mirror_stale" for e, *_ in audited)


# ── The cancelled-spelling correction ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_exit_qty_treats_both_cancel_spellings_as_terminal(monkeypatch):
    """Alpaca emits `canceled` AND `cancelled`. Only the double-l one was listed, so
    a single-l cancelled exit order counted as still working forever — every caller
    that sizes a stop against this number placed a stop that was too SMALL.

    #591-review refactor: the terminal set moved from an inline SQL literal to
    `PENDING_EXIT_TERMINAL_STATUSES` (SSoT), bound as `status != ALL($2::text[])`
    — so assert the BOUND PARAMETER carries both spellings; there is no longer a
    literal in the SQL text to grep for."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=0)
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    await om.get_pending_exit_qty(367)

    sql, _trade_id, statuses = conn.fetchval.await_args.args
    assert "canceled" in statuses, "the single-l spelling was the gap"
    assert "cancelled" in statuses, "the double-l spelling must stay"
    assert set(statuses) == om.PENDING_EXIT_TERMINAL_STATUSES
    assert "purpose IN ('partial_exit', 'full_exit')" in sql


@pytest.mark.asyncio
async def test_a_single_l_cancelled_exit_order_no_longer_reserves_shares(monkeypatch):
    """Behaviour, not spelling: the corrected filter must EXCLUDE such a row. Driven
    through a fake that applies the query's own bound status-list parameter, so
    reverting `PENDING_EXIT_TERMINAL_STATUSES` to the double-l-only spelling reddens
    this. Zero trades in the live or paper book move
    (`scripts/probes/_591_state_capture.sql` Q2B) — the fix is a no-op today."""
    orders = [
        {"qty": 5, "status": "canceled"},    # must NOT count — the bug
        {"qty": 7, "status": "cancelled"},   # already did not count
        {"qty": 3, "status": "new"},         # genuinely working
    ]

    async def _fetchval(_sql, _trade_id, statuses):
        return sum(o["qty"] for o in orders if o["status"] not in statuses)

    pool, conn = make_mock_pool()
    conn.fetchval = _fetchval
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))

    assert await om.get_pending_exit_qty(367) == 3


# ── The #588 invariant exclusion, reconsidered ───────────────────────────────


@pytest.mark.asyncio
async def test_invariant_stops_excusing_rows_closed_with_an_exit_still_working():
    """The exclusion existed only to tolerate the state this fix removes. It now
    masks the defect instead of the noise, so it is gone — a closed row whose legs
    do not sum to entry is a breach regardless of what rests at the broker."""

    class _C:
        sql = None

        async def fetch(self, sql, *args):
            self.sql = sql
            return []

    conn = _C()
    ok, _ = await inv.check_exit_share_sum(conn)

    assert ok is True
    assert "mi_live_orders" not in conn.sql
    assert inv.EXIT_SHARE_SUM_SINCE == date(2026, 8, 24), "cutoff deliberately unchanged"


# ── Trade-state write authority ──────────────────────────────────────────────


def test_the_stay_open_write_is_inside_an_authorized_writer():
    """`remaining_shares` / `status` / `stop_order_id` are column-write-authority
    gated (`scripts/audit_column_writes.py`, a deploy preflight that has refused a
    deploy this month). The new UPDATE lives in `attempt_day1_reentry`, which is
    already on the allow-list for all three — no new co-owner is introduced."""
    import scripts.audit_column_writes as acw

    for col in ("status", "remaining_shares", "stop_order_id", "exits", "total_pnl"):
        assert "order_manager.attempt_day1_reentry" in acw.ALLOWED_WRITERS[col], col


def test_the_stay_open_branch_is_not_a_demotion_inside_an_except():
    """ADR 0008 fence: a trade-state demotion inside an `except` needs a reviewed
    `# broker-confirmed:` escape. This write is not in an except block at all, and
    it is the opposite of a demotion — the row stays OPEN. Pinned so a later
    refactor cannot quietly move it under one."""
    import inspect

    src = inspect.getsource(om.attempt_day1_reentry)
    branch = src.split("if new_remaining > 0:")[1].split("attempt = trade[")[0]
    assert "except" not in branch
    assert "broker-confirmed:" in branch, "the stop_order_id NULL carries its evidence"
