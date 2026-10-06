"""get_open_live_trades feeds the ADR 0014 mgmt judge and the #508 'LIVE MONEY — OPEN NOW' block.
2026-10-06: with no account_mode filter it returned the #687 paper rehearsal's KO/PEP, which the
operator then saw judged and listed as live money (dual-account invariant 3)."""
import asyncio

from agents.market_intelligence import db


class _Conn:
    def __init__(self):
        self.sql = None

    async def fetch(self, sql, *args):
        self.sql = sql
        return []


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def test_open_live_trades_reads_only_the_live_book_and_never_test_rows(monkeypatch):
    conn = _Conn()

    async def _pool():
        return _Pool(conn)

    monkeypatch.setattr(db, "get_pool", _pool)
    assert asyncio.run(db.get_open_live_trades()) == []
    flat = " ".join(conn.sql.split())
    # source-pin-ok: the filter is SQL text and there is no local Postgres to run it against
    assert "account_mode = 'live'" in flat
    assert "signal_type IS DISTINCT FROM 'integration_test'" in flat
