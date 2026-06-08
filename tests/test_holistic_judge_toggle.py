"""W2b (#243 / ADR 0011): the Holistic Grade Judge authority toggle must FAIL-CLOSED —
any error reading it resolves to the conviction floor, never the judge. This is the
load-bearing safety invariant, so it gets its own test independent of a live DB.
"""
import asyncio

from agents.market_intelligence import db


def test_toggle_read_fails_closed_on_db_error(monkeypatch):
    async def _boom():
        raise RuntimeError("db unreachable")
    monkeypatch.setattr(db, "get_pool", _boom)
    # Exception path → floor (False), never judge.
    assert asyncio.run(db.get_holistic_judge_enabled()) is False


def test_toggle_read_fails_closed_on_missing_row(monkeypatch):
    class _Conn:
        async def fetchrow(self, *a, **k):
            return None  # no toggle row yet (dormant default)

    class _Acq:
        async def __aenter__(self):
            return _Conn()
        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _pool():
        return _Pool()
    monkeypatch.setattr(db, "get_pool", _pool)
    # Missing row → off (floor), not on.
    assert asyncio.run(db.get_holistic_judge_enabled()) is False
