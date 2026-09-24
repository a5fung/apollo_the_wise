"""A split re-fetch must cover the ticker's WHOLE stored history, not a fixed 250 days.

2026-09-24: the five-year reload put ~1,260 sessions per ticker in mi_daily_closes while
`_apply_one` re-fetched only 250 calendar days on a split — so every older row stayed in
pre-split units and the series carried a cliff (QH read in the tens of thousands before
2025-11-10). These tests pin the window to the earliest stored row.
"""
import asyncio
from datetime import date, timedelta

from agents.market_intelligence import splits_ingest as si


class _Conn:
    def __init__(self, earliest):
        self.earliest = earliest

    async def fetchval(self, sql, *args):
        assert "min(trade_date)" in sql
        return self.earliest


class _Pool:
    def __init__(self, earliest):
        self.conn = _Conn(earliest)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _patch(monkeypatch, earliest, today=date(2026, 9, 24)):
    import agents.market_intelligence.db as db

    async def _get_pool():
        return _Pool(earliest)
    monkeypatch.setattr(db, "get_pool", _get_pool)
    monkeypatch.setattr(si, "et_today", lambda: today)


def test_window_reaches_the_earliest_stored_row(monkeypatch):
    earliest = date(2021, 9, 27)
    _patch(monkeypatch, earliest)
    days = asyncio.run(si._stored_history_days("QH"))
    assert date(2026, 9, 24) - timedelta(days=days) <= earliest
    assert days > si.HISTORY_DAYS


def test_short_history_keeps_the_minimum_window(monkeypatch):
    _patch(monkeypatch, date(2026, 8, 1))
    assert asyncio.run(si._stored_history_days("NEWCO")) == si.HISTORY_DAYS


def test_no_rows_keeps_the_minimum_window(monkeypatch):
    _patch(monkeypatch, None)
    assert asyncio.run(si._stored_history_days("NONE")) == si.HISTORY_DAYS


def test_apply_one_requests_the_stored_history_window(monkeypatch):
    """The call site, not just the helper: `_apply_one` must pass the stored-history window."""
    earliest = date(2021, 9, 27)
    _patch(monkeypatch, earliest)
    seen = {}

    async def _fetch(ticker, days=si.HISTORY_DAYS):
        seen["days"] = days
        return []   # no bars → the skip branch; the window is what is under test

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(si, "fetch_ticker_history", _fetch)
    monkeypatch.setattr(si, "log_audit_event", _noop)
    monkeypatch.setattr(si, "mark_split_applied", _noop)
    asyncio.run(si._apply_one({"ticker": "QH", "execution_date": date(2026, 7, 1),
                               "split_from": 1, "split_to": 10}))
    assert date(2026, 9, 24) - timedelta(days=seen["days"]) <= earliest
