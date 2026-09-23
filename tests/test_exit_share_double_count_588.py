"""#588 — the stop leg must record the shares that ACTUALLY sold.

ETON 2026-08-14 (live money): 17 shares entered. At 09:35 the +2R carve-out placed
a RESTING limit for 5 and armed a breakeven stop on the other 12. At 09:45 that
12-share stop filled — and `attempt_day1_reentry` wrote the leg as **17**, because
it booked `remaining_shares` blind and the partial had not COMMITTED yet (the
deferred-commit pattern: remaining only drops when the sell fills). At 15:58 the
resting limit finally filled and its 5 were counted a second time:

    sum(exits[].shares) = 22 on a 17-share trade; booked $19.32 vs a true $20.08.

PLTR 2026-08-04 escaped on BOTH counts, which is why this was not universal:
its stop hit on day 14 (a different write path) AND its partial had committed two
weeks earlier, so `remaining_shares` was already net.

#588 was RECORDING ONLY: the share count fed the exit leg, its P&L and the Telegram
text, and the row still closed at zero with the limit resting.

⚠ #591 (operator ruling 2026-08-24) SUPERSEDED that scoping — the row must stay OPEN
while shares remain, so `remaining_shares` and `status` DO move now when a resting
exit is still working. The close path is unchanged when nothing rests, which is what
`test_r3_close_state_is_unchanged_when_nothing_is_resting` below pins. The stay-open
behaviour lives in `tests/test_day1_stop_leaves_row_open_591.py`.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from unittest.mock import AsyncMock

from agents.market_intelligence import audit_invariants as inv
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts

from tests.conftest import make_mock_pool


ETON_ENTRY = 55.2012
ETON_STOP_FILL = 55.05


def _eton_row(*, remaining=17, exits=None, alert_date=date(2026, 8, 14)):
    """The ETON row as it stood at 09:45:11 — the partial still resting."""
    return {
        "id": 367, "ticker": "ETON", "entry_price": ETON_ENTRY, "entry_shares": 17,
        "remaining_shares": remaining, "orb_high": 55.4427, "orb_low": 53.01,
        "stop_price": 53.01, "atr_14": 2.696, "stop_order_id": "11b25e11",
        "entry_attempt": 1, "exits": exits if exits is not None else [],
        "ep_score": 96, "catalyst_quality": "game_changer", "gap_pct": 23.3,
        "regime": "Bull", "alert_date": alert_date, "account_mode": "live",
        "signal_type": "magna53",
    }


def _wire_reentry(monkeypatch, row, *, held: int):
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


def _exits_written(conn):
    upd = [c for c in conn.execute.call_args_list if "UPDATE mi_live_trades" in c.args[0]]
    assert len(upd) == 1, f"expected exactly one trade UPDATE, got {len(upd)}"
    written = upd[0].args[2]
    return upd[0], (written if isinstance(written, list) else json.loads(written))


# ── The ETON shape ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eton_shape_records_the_stop_fill_not_the_whole_position(monkeypatch):
    """THE BUG, replayed: 12-share stop fill on a 17-share row with 5 still resting.

    MUTATION-PROVEN: reverting to `shares = trade["remaining_shares"]` reddens this —
    the leg goes back to 17 and the reconstruction below sums to 22.
    """
    conn, audited, _ = _wire_reentry(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=12)

    _, exits = _exits_written(conn)
    assert len(exits) == 1
    leg = exits[0]
    assert leg["reason"] == "stop_hit"
    assert leg["shares"] == 12, "the stop sold 12 — 17 double-counts the resting partial"
    assert leg["pnl"] == pytest.approx((ETON_STOP_FILL - ETON_ENTRY) * 12)
    assert any(e == "stop_leg_shares_netted" for e, *_ in audited)


@pytest.mark.asyncio
async def test_eton_shape_reconstructs_to_seventeen_once_the_partial_lands(monkeypatch):
    """The whole point: 12 (stop) + 5 (the limit that filled at 15:58) = 17 entered,
    and the booked P&L becomes the true $20.08 instead of $19.32."""
    conn, _, _ = _wire_reentry(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=12)

    _, exits = _exits_written(conn)
    exits.append({"reason": "partial_profit", "shares": 5, "price": 59.58,
                  "pnl": (59.58 - ETON_ENTRY) * 5})

    assert sum(e["shares"] for e in exits) == 17
    assert sum(e["pnl"] for e in exits) == pytest.approx(20.0796, abs=1e-3)


@pytest.mark.asyncio
async def test_polling_path_nets_the_resting_partial_when_qty_is_unknown(monkeypatch):
    """No filled_qty available: fall back to remaining MINUS shares a resting exit
    order is holding — the same subtraction `update_stop` already applies."""
    conn, audited, _ = _wire_reentry(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="polling")

    _, exits = _exits_written(conn)
    assert exits[0]["shares"] == 12
    assert any(e == "stop_leg_shares_netted" for e, *_ in audited)


@pytest.mark.asyncio
async def test_zero_filled_qty_is_treated_as_unknown_not_as_sold_nothing(monkeypatch):
    """The WS payload falls back to 0 when the broker sends no quantity. Recording a
    0-share stop leg would erase the trade's entire loss, so 0 means UNKNOWN and the
    netted remainder is used instead."""
    conn, _, _ = _wire_reentry(monkeypatch, _eton_row(), held=5)

    await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=0)

    _, exits = _exits_written(conn)
    assert exits[0]["shares"] == 12


# ── The PLTR shape — nothing may move ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pltr_shape_is_byte_identical_when_no_exit_is_resting(monkeypatch):
    """PLTR's partial had COMMITTED, so remaining was already net (6 -> 4) and
    nothing is held. The leg must record exactly what it always did, and the
    netting audit row must NOT fire on a clean trade."""
    row = _eton_row(remaining=4)
    row.update({"id": 307, "ticker": "PLTR", "entry_price": 149.0545, "entry_shares": 6})
    conn, audited, _ = _wire_reentry(monkeypatch, row, held=0)

    await om.attempt_day1_reentry(307, 170.3875, source="websocket")

    _, exits = _exits_written(conn)
    assert exits[0]["shares"] == 4
    assert exits[0]["pnl"] == pytest.approx((170.3875 - 149.0545) * 4)
    assert not any(e == "stop_leg_shares_netted" for e, *_ in audited)


@pytest.mark.asyncio
async def test_r3_close_state_is_unchanged_when_nothing_is_resting(monkeypatch):
    """The common case — a FULL stop-out with no exit order working — closes exactly
    as it always has: zeroed, closed, same skip_reason.

    Was `test_r3_close_state_is_byte_identical` at held=5. #591 (operator ruling)
    changed that case on purpose: with 5 shares still resting the row now stays OPEN.
    Retargeted to held=0 so it keeps pinning what genuinely must not move.
    """
    conn, _, _ = _wire_reentry(monkeypatch, _eton_row(), held=0)

    result = await om.attempt_day1_reentry(367, ETON_STOP_FILL, source="websocket", filled_qty=17)

    call, _ = _exits_written(conn)
    sql = call.args[0]
    assert "status = 'closed'" in sql
    assert "remaining_shares = 0" in sql
    assert "block:r3_reentry_disabled" in sql
    assert result["action"] == "closed" and result["reason"] == "r3_disabled"


# ── The two callers must hand over the quantity they already hold ──────────────


@pytest.mark.asyncio
async def test_polling_caller_threads_the_brokers_filled_qty(monkeypatch):
    """`_check_day1_reentry` already fetches the stop order; dropping its
    `filled_qty` was the live hole that let the ETON shape recur."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{
        "id": 367, "ticker": "ETON", "stop_order_id": "11b25e11",
        "stop_price": 53.01, "account_mode": "live",
    }])
    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.collector.et_today",
                        lambda: date(2026, 8, 14))
    monkeypatch.setattr(om.alpaca, "get_order", AsyncMock(return_value={
        "status": "filled", "filled_avg_price": ETON_STOP_FILL, "filled_qty": 12.0,
    }))
    spy = AsyncMock(return_value={"ticker": "ETON", "action": "closed"})
    monkeypatch.setattr(om, "attempt_day1_reentry", spy)

    await om._check_day1_reentry()

    assert spy.await_args.kwargs["filled_qty"] == 12.0


@pytest.mark.asyncio
async def test_websocket_caller_threads_its_filled_qty(monkeypatch):
    """The WS full-stop-out branch hands its own fill quantity to the re-entry path."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    spy = AsyncMock(return_value={"ticker": "ETON", "action": "closed"})
    monkeypatch.setattr(om, "attempt_day1_reentry", spy)
    monkeypatch.setattr("agents.market_intelligence.collector.et_today",
                        lambda: date(2026, 8, 14))
    claim = {"id": 367, "ticker": "ETON", "alert_date": date(2026, 8, 14),
             "entry_attempt": 1, "entry_price": ETON_ENTRY, "remaining_shares": 17,
             "exits": [], "hold_days": 0}

    await ts._process_stop_fill(claim, ETON_STOP_FILL, pool, "live", filled_qty=17)

    assert spy.await_args.kwargs["filled_qty"] == 17


# ── The guard ──────────────────────────────────────────────────────────────────


class _FetchConn:
    def __init__(self, rows):
        self._rows = rows
        self.sql = None
        self.args = None

    async def fetch(self, sql, *args):
        self.sql, self.args = sql, args
        return self._rows


@pytest.mark.asyncio
async def test_invariant_fires_on_a_double_counted_row():
    conn = _FetchConn([{
        "id": 367, "ticker": "ETON", "account_mode": "live",
        "alert_date": date(2026, 8, 14), "entry_shares": 17, "exit_shares": 22,
    }])

    ok, body = await inv.check_exit_share_sum(conn)

    assert ok is False
    assert body["name"] == inv.INV_EXIT_SHARE_SUM
    assert body["count"] == 1
    assert "ETON" in body["offending"][0] and "22" in body["offending"][0]


@pytest.mark.asyncio
async def test_invariant_passes_on_a_clean_book():
    conn = _FetchConn([])

    ok, body = await inv.check_exit_share_sum(conn)

    assert ok is True and body["count"] == 0


@pytest.mark.asyncio
async def test_invariant_is_narrowed_so_it_cannot_cry_wolf():
    """Each clause here corresponds to a real prod row that is NOT a defect:
    open trades (legs sum to less), re-entered trades (legs legitimately sum to a
    multiple of entry_shares — 5 such paper rows), a 2026-04 legacy leg keyed
    `qty` instead of `shares`, and the pre-fix rows the operator has not decided
    to backfill. Dropping any clause turns the guard into a nightly false alarm.

    The still-working-exit clause is deliberately NOT here any more — see
    `test_invariant_no_longer_excuses_a_row_closed_with_an_exit_still_working`."""
    conn = _FetchConn([])

    await inv.check_exit_share_sum(conn)

    assert "status = 'closed'" in conn.sql
    assert "COALESCE(t.entry_attempt, 1) = 1" in conn.sql
    assert "x ? 'shares'" in conn.sql
    assert "> 0.001" in conn.sql, "float tolerance — legs are written as both 17 and 17.0"
    assert conn.args == (inv.EXIT_SHARE_SUM_SINCE,)
    assert inv.EXIT_SHARE_SUM_SINCE == date(2026, 8, 24)


@pytest.mark.asyncio
async def test_invariant_no_longer_excuses_a_row_closed_with_an_exit_still_working():
    """#591: the exclusion is GONE, deliberately.

    It existed because the day-1 stop path closed the row at zero while a carve-out
    limit rested, so a correctly-recorded ETON read 12 of 17 for six hours. The
    operator ruled that close is a bug and `attempt_day1_reentry` now holds the row
    OPEN — and this check only ever looks at CLOSED rows, so the state it tolerated
    cannot occur. Keeping it would MASK any other path that closes a row early.
    """
    conn = _FetchConn([])

    await inv.check_exit_share_sum(conn)

    assert "mi_live_orders" not in conn.sql
    assert "partial_exit" not in conn.sql


def test_invariant_is_registered_in_the_sweep():
    names = [n for n, _, _ in inv.all_invariants(
        since=date(2026, 8, 24),
        since_dt=__import__("datetime").datetime(2026, 8, 24),
        now_et=None,
    )]
    assert inv.INV_EXIT_SHARE_SUM in names
