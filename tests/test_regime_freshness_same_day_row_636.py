"""A closes row dated TODAY must not be able to move the regime-freshness threshold.

WHY (#636, operator-signed 2026-09-10). `_last_ingested_session` answers "the last session we
already hold closes for", and that answer gates whether the regime row is STALE — which decides
whether an ORB entry is sized in full or floored to a quarter.

The query used to say `trade_date <= today`. That was CORRECT only because today's closes have not
been ingested by 9:31 (they land ~17:52-18:00 ET). So the correctness of the sizing path rested on
the schedule of an unrelated job. If a row dated today ever existed before the bell — the ingest
rescheduled, a backfill, a manual re-run, some future intraday writer — the threshold would become
TODAY, every regime row dated yesterday would read stale, and every entry would be floored to a
quarter size. Every day. Until somebody noticed.

That is the same quarter-size bug #630 fixed, re-entered through a door nobody was watching. `<`
is behaviour-identical today and removes the coupling. These tests pin BOTH halves: the normal
answer is unchanged, and a same-day row cannot move it.
"""
from datetime import date

import pytest

from agents.market_intelligence.broker import order_manager as om


class _Conn:
    """Answers the real query against an in-memory closes table, honouring its WHERE clause."""

    def __init__(self, sessions):
        self.sessions = sessions
        self.seen_sql = None

    async def fetchval(self, sql, arg, timeout=None):
        self.seen_sql = sql
        if "<=" in sql:
            eligible = [d for d in self.sessions if d <= arg]
        else:
            eligible = [d for d in self.sessions if d < arg]
        return max(eligible) if eligible else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self, timeout=None):
        return self._conn


def _wire(monkeypatch, sessions):
    conn = _Conn(sessions)

    async def _pool():
        return _Pool(conn)

    monkeypatch.setattr(om, "get_pool", _pool)
    om._LAST_SESSION_CACHE.clear()
    return conn


# Mon 09-07 was Labor Day: no session, so no closes row for it.
_SESSIONS = [date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9)]


@pytest.mark.asyncio
async def test_the_ordinary_morning_answer_is_unchanged(monkeypatch):
    """The whole point of `<` is that today's behaviour does not move."""
    _wire(monkeypatch, _SESSIONS)
    assert await om._last_ingested_session(date(2026, 9, 10)) == date(2026, 9, 9)


@pytest.mark.asyncio
async def test_a_same_day_closes_row_cannot_move_the_threshold(monkeypatch):
    """THE REGRESSION. Closes for TODAY land early; the threshold must still be yesterday.

    Under `<=` this returned 2026-09-10, which makes a regime row dated 09-09 read STALE and
    floors every entry of the day to a quarter size.
    """
    _wire(monkeypatch, _SESSIONS + [date(2026, 9, 10)])
    got = await om._last_ingested_session(date(2026, 9, 10))
    assert got == date(2026, 9, 9), (
        "a closes row dated today moved the freshness threshold — every regime row would read "
        "stale and every entry would be quarter-sized")


@pytest.mark.asyncio
async def test_the_holiday_case_still_works(monkeypatch):
    """#630's original bug: the day after Labor Day must not read the shut Monday as a session."""
    _wire(monkeypatch, [date(2026, 9, 3), date(2026, 9, 4)])
    assert await om._last_ingested_session(date(2026, 9, 8)) == date(2026, 9, 4)


@pytest.mark.asyncio
async def test_the_query_is_strict(monkeypatch):
    """Pin the SQL itself: `<=` here is the defect, and a refactor must not reintroduce it."""
    conn = _wire(monkeypatch, _SESSIONS)
    await om._last_ingested_session(date(2026, 9, 10))
    assert "<=" not in conn.seen_sql, "the freshness query went back to <=, re-coupling sizing to the ingest schedule"
    assert "<" in conn.seen_sql


@pytest.mark.asyncio
async def test_no_closes_at_all_returns_none(monkeypatch):
    """None routes the caller to the calendar rule, which floors — the safe direction."""
    _wire(monkeypatch, [])
    assert await om._last_ingested_session(date(2026, 9, 10)) is None
