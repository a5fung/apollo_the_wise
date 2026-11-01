"""#482 hour lane (2026-11-01): a LATE fill's `open` row and its catch-up are ONE transaction.

The 10-27 simplify note: "a LATE-fill hour row's insert and its catch-up update are two statements, not
one transaction — a failure between them leaves an open row the exit step quarantines". Now
`db.insert_shadow_trade(row, catch_up=...)` runs the INSERT and the catch-up UPDATE inside one
`conn.transaction()`.

What a fake connection CAN prove (and what it cannot): both statements execute inside the transaction
context, on the same connection, and the UPDATE's exception propagates OUT of that context — which is
what makes asyncpg roll the INSERT back. The rollback itself is asyncpg's; it is not simulated here.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence import db

ROW = {"ticker": "AAA", "alert_date": date(2026, 10, 20), "bar_size_minutes": 60, "signal_type": "magna53",
       "status": "open", "entry_price": 11.0, "stop_price": 8.0, "hard_stop": 8.0, "risk_dollars": 3.0,
       "entry_shares": 1.0, "remaining_shares": 1.0}
CATCH_UP = {"running_closes": [10.9, 11.1], "exits": [], "remaining_shares": 1.0, "partial_taken": False,
            "breakeven_active": False, "total_pnl": 0.0, "hold_days": 2, "stop_price": 8.0}


class _Conn:
    """Records every statement with the transaction depth it ran at, and what left the transaction."""

    def __init__(self, *, insert_returns=7, update_raises: Exception | None = None):
        self.log: list[tuple[str, int]] = []
        self.depth = 0
        self.exits: list = []
        self._id = insert_returns
        self._raise = update_raises

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self_):
                conn.depth += 1
                return self_

            async def __aexit__(self_, exc_type, exc, tb):
                conn.depth -= 1
                conn.exits.append(exc_type)
                return False
        return _Tx()

    async def fetchrow(self, sql, *args):
        self.log.append(("INSERT", self.depth))
        assert sql is db.SHADOW_TRADE_INSERT_SQL
        return {"id": self._id} if self._id is not None else None

    async def execute(self, sql, *args):
        self.log.append(("UPDATE", self.depth))
        assert sql.startswith("UPDATE mi_orb_shadow_trades SET ") and sql.endswith(" WHERE id = $1")
        assert args[0] == self._id and args[1:] == tuple(db.shadow_trade_update_sql(CATCH_UP)[1])
        if self._raise is not None:
            raise self._raise
        return "UPDATE 1"


def _pool(monkeypatch, conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)

    async def get_pool():
        return pool
    monkeypatch.setattr(db, "get_pool", get_pool)


@pytest.mark.asyncio
async def test_insert_and_catch_up_run_inside_one_transaction_on_one_connection(monkeypatch):
    conn = _Conn()
    _pool(monkeypatch, conn)
    assert await db.insert_shadow_trade(ROW, catch_up=CATCH_UP) == 7
    assert conn.log == [("INSERT", 1), ("UPDATE", 1)] and conn.exits == [None]


@pytest.mark.asyncio
async def test_a_failing_catch_up_leaves_the_transaction_with_the_exception_so_the_insert_rolls_back(monkeypatch):
    conn = _Conn(update_raises=RuntimeError("connection reset between the two statements"))
    _pool(monkeypatch, conn)
    with pytest.raises(RuntimeError):
        await db.insert_shadow_trade(ROW, catch_up=CATCH_UP)
    assert conn.log == [("INSERT", 1), ("UPDATE", 1)]
    assert conn.exits == [RuntimeError]                  # the exception left the transaction: no commit


@pytest.mark.asyncio
async def test_the_unique_conflict_inserts_nothing_and_applies_no_catch_up(monkeypatch):
    conn = _Conn(insert_returns=None)
    _pool(monkeypatch, conn)
    assert await db.insert_shadow_trade(ROW, catch_up=CATCH_UP) is None
    assert conn.log == [("INSERT", 1)] and conn.exits == [None]


@pytest.mark.asyncio
async def test_without_a_catch_up_the_insert_is_the_plain_statement_as_before(monkeypatch):
    conn = _Conn()
    _pool(monkeypatch, conn)
    assert await db.insert_shadow_trade(ROW) == 7
    assert conn.log == [("INSERT", 0)] and conn.exits == []


def test_the_catch_up_update_is_the_prepared_exit_step_statement():
    """Both catch-up shapes (still open; closed inside the missed sessions) are the exit step's own
    UPDATE, which scripts/preflight_db_updates.py prepares at deploy — no new statement to register."""
    from datetime import datetime
    assert db.shadow_trade_update_sql(CATCH_UP)[0] == db.SHADOW_TRADE_EXIT_STEP_UPDATE_SQL.replace(
        ", status = $10, closed_at = $11", "")
    closed = {**CATCH_UP, "status": "closed", "closed_at": datetime(2026, 10, 27, 16, 50)}
    assert db.shadow_trade_update_sql(closed)[0] == db.SHADOW_TRADE_EXIT_STEP_UPDATE_SQL


@pytest.mark.asyncio
async def test_a_crash_inside_the_combined_write_is_a_counted_error_and_no_row(monkeypatch):
    """Through the tracker: the combined write raising is the per-candidate crash path — counted,
    nothing recorded, the candidate retried the next night (the row never existed)."""
    from datetime import timedelta
    from agents.market_intelligence.broker import shadow_orb_tracker as sot
    from tests.test_482_shadow_hour_lane import _Captured, _five_row, _hour_day, _ms, _patch_common
    alert, today = date(2026, 10, 20), date(2026, 10, 27)
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                  daily_bars=AsyncMock(return_value=[{"o": 11, "h": 11.2, "l": 10.8, "c": 11.0,
                                                      "t": _ms(date(2026, 10, 26))}]))

    async def _insert(row, *, catch_up=None):
        assert catch_up is not None
        raise RuntimeError("lost the connection mid-transaction")
    monkeypatch.setattr(sot, "insert_shadow_trade", _insert)
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    counts = await sot.run_shadow_hour_pass(today)
    assert counts["error"] == 1 and counts["open"] == 0 and cap.inserts == [] and cap.updates == []
    assert today - alert == timedelta(days=7)
