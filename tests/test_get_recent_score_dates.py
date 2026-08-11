"""Regression tests for `db.get_recent_score_dates` — the #479 §1.7b session-date
helper feeding `briefing._fetch_unanchored_sessions`.

LIVE INCIDENT (2026-08-11): a stray single-row write landed on Saturday
2026-08-08 (`score_single_ticker` writes to `mi_stock_scores` keyed off raw
`et_today()`, so an ad-hoc single-ticker query on a non-trading day writes a
row dated that non-trading day — see CHANGELOG / this task's report for the
4 historical occurrences: OKTA 5/30, RACE 7/05, CRCL 7/12, FIGS 8/08, all
Sat/Sun, all exactly 1 row). The raw DISTINCT-dates query counted that
Saturday as a "session", pulling a day the theme engine never ran into the
5-session unanchored window and permanently red-lighting
`_fetch_unanchored_sessions`'s zero-theme-rows guard until the date aged out
(5 straight nights of "session fetch failed" in the evening brief).

Fix: filter candidate dates through `trading_calendar.get_market_status`
(NYSE-holiday-aware, not a raw weekday test and not a row-count threshold)
and over-fetch/expand the query window so a filtered-out stray never shrinks
the returned session count below `n` when enough real sessions exist.

MUTATION CHECK (recorded here, not re-run by CI): deleting the
`if get_market_status(r["score_date"]).is_trading_day` filter (so the
function goes back to raw DISTINCT dates) makes
`test_filters_stray_weekend_row_from_first_batch`,
`test_expands_query_window_when_first_batch_is_stray_heavy`, and
`test_real_prod_incident_data_excludes_2026_08_08` all FAIL (each asserts
2026-08-08 / a stubbed non-trading date is ABSENT from the result) —
confirming the assertions have teeth. Verified by hand: reverted the filter,
ran this file, all three went red with `2026-08-08` present in the returned
list; restored the fix, all three went green again.
"""
from __future__ import annotations

import asyncio
from collections import namedtuple
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

import agents.market_intelligence.db as db
import agents.market_intelligence.trading_calendar as trading_calendar

_FakeStatus = namedtuple("FakeStatus", ["is_trading_day", "reason"])


def _mock_calendar(monkeypatch, *, non_trading: set[date]):
    """Deterministic calendar stub — patches the SOURCE module
    (`trading_calendar.get_market_status`), which is what `db.py`'s local
    `from agents.market_intelligence.trading_calendar import get_market_status`
    re-resolves at call time (same pattern as test_l2_holiday_awareness.py /
    test_job_audit.py's `_wire` docstring)."""
    def _stub(d):
        if d in non_trading:
            return _FakeStatus(False, "non-trading (test)")
        return _FakeStatus(True, "trading day (test)")
    monkeypatch.setattr(trading_calendar, "get_market_status", _stub)


def _wire_fetch(monkeypatch, batches: list[list[dict]]):
    """conn.fetch returns `batches[call_index]` (clamped to the LIMIT
    param), one element consumed per LIMIT-doubling round trip. Records
    every (sql, as_of, limit) call for assertions."""
    pool, conn = make_mock_pool()
    calls = []
    call_idx = {"i": 0}

    async def _fetch(sql, as_of_d, limit):
        calls.append((sql, as_of_d, limit))
        i = min(call_idx["i"], len(batches) - 1)
        call_idx["i"] += 1
        return batches[i][:limit]
    conn.fetch = _fetch
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    return calls


def _rows(*dates: date) -> list[dict]:
    return [{"score_date": d} for d in dates]


def _run(coro):
    return asyncio.run(coro)


# ── Core filtering behavior ─────────────────────────────────────────────────

def test_filters_stray_weekend_row_from_first_batch(monkeypatch):
    """A single stray Saturday inside the first over-fetched batch is
    dropped, and the next real trading day fills its slot — n stays 6, the
    stray is simply not one of the sessions."""
    _mock_calendar(monkeypatch, non_trading={date(2026, 8, 8)})
    batch = _rows(
        date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 8),  # stray Saturday
        date(2026, 8, 7), date(2026, 8, 6), date(2026, 8, 5),
        date(2026, 8, 4), date(2026, 8, 3), date(2026, 7, 31),
        date(2026, 7, 30), date(2026, 7, 29), date(2026, 7, 28),
    )
    calls = _wire_fetch(monkeypatch, [batch])
    result = _run(db.get_recent_score_dates(date(2026, 8, 11), 6))

    assert date(2026, 8, 8) not in result
    assert result == [date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 7),
                       date(2026, 8, 6), date(2026, 8, 5), date(2026, 8, 4)]
    assert len(calls) == 1  # enough valid sessions in the first batch — no expansion needed
    assert calls[0][2] == 12  # fetch_n = max(6*2, 6+4) = 12


def test_expands_query_window_when_first_batch_is_stray_heavy(monkeypatch):
    """If the first over-fetched window is mostly non-trading rows (more
    strays than the padding can absorb), the function doubles the query
    window and tries again rather than silently returning a short list.

    Synthetic sequential dates (index 0 = newest) so the trading/non-trading
    split is exact and doesn't depend on real weekday arithmetic: indices
    0-4 are strays, 5 onward are all real trading sessions."""
    anchor = date(2026, 8, 20)
    cand = [anchor - timedelta(days=i) for i in range(14)]
    non_trading = set(cand[0:5])  # indices 0-4 -> 5 strays
    _mock_calendar(monkeypatch, non_trading=non_trading)

    # n=3 -> fetch_n starts at max(3*2, 3+4) = 7. First 7 candidates (idx 0-6)
    # contain only 2 trading days (idx 5, 6) -> short of n=3, must expand.
    first_batch = _rows(*cand[0:7])
    second_batch = _rows(*cand[0:14])  # fetch_n doubles to 14
    calls = _wire_fetch(monkeypatch, [first_batch, second_batch])
    result = _run(db.get_recent_score_dates(anchor, 3))

    assert not (set(result) & non_trading)
    assert result == [cand[5], cand[6], cand[7]]  # newest-first trading days
    assert len(calls) == 2  # had to expand once
    assert calls[0][2] == 7
    assert calls[1][2] == 14  # doubled


def test_returns_fewer_than_n_when_table_is_exhausted(monkeypatch):
    """When the table simply doesn't have n valid sessions (fewer rows
    returned than the LIMIT asked for), the function stops expanding and
    returns whatever real sessions it found instead of looping forever."""
    _mock_calendar(monkeypatch, non_trading={date(2026, 8, 8)})
    # Only 3 rows exist in the whole table, one of which is the stray.
    only_batch = _rows(date(2026, 8, 8), date(2026, 8, 7), date(2026, 8, 6))
    calls = _wire_fetch(monkeypatch, [only_batch])
    result = _run(db.get_recent_score_dates(date(2026, 8, 11), 6))

    assert result == [date(2026, 8, 7), date(2026, 8, 6)]
    assert len(calls) == 1  # len(rows)=3 < fetch_n=12 -> table exhausted, no second round trip


def test_no_strays_matches_pre_fix_behavior(monkeypatch):
    """Sanity: with an all-trading-day table (the normal case), behavior is
    unchanged from the pre-fix raw-DISTINCT-dates query."""
    _mock_calendar(monkeypatch, non_trading=set())
    batch = _rows(date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 7),
                  date(2026, 8, 6), date(2026, 8, 5), date(2026, 8, 4),
                  date(2026, 8, 3))
    _wire_fetch(monkeypatch, [batch])
    result = _run(db.get_recent_score_dates(date(2026, 8, 11), 6))
    assert result == [date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 7),
                       date(2026, 8, 6), date(2026, 8, 5), date(2026, 8, 4)]


# ── Prod-data regression pin (real trading_calendar, NOT mocked) ───────────

def test_real_prod_incident_data_excludes_2026_08_08():
    """End-to-end against the ACTUAL rows measured on prod tonight
    (2026-08-11), through the REAL (unmocked) trading_calendar — the direct
    proof that tonight's `⚠️ Unanchored persistent-set check could not run`
    incident is fixed. UNANCHORED_SESSIONS_NEEDED is 6 in production; this
    pins that exact call."""
    from agents.market_intelligence.brief_composer import UNANCHORED_SESSIONS_NEEDED
    assert UNANCHORED_SESSIONS_NEEDED == 6

    # `docker exec apollo-postgres psql -U apollo -d apollo -tAc
    #  "SELECT score_date, count(*) FROM mi_stock_scores
    #   WHERE score_date >= '2026-07-25' GROUP BY score_date ORDER BY score_date DESC;"`
    # measured live 2026-08-11 (row counts confirm 08-08 is the 1-row stray, all
    # others are full ~2400-row sessions):
    prod_rows = _rows(
        date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 8),  # stray, 1 row
        date(2026, 8, 7), date(2026, 8, 6), date(2026, 8, 5),
        date(2026, 8, 4), date(2026, 8, 3), date(2026, 7, 31),
        date(2026, 7, 30), date(2026, 7, 29), date(2026, 7, 28),
        date(2026, 7, 27),
    )

    async def _go():
        pool, conn = make_mock_pool()

        async def _fetch(sql, as_of_d, limit):
            return prod_rows[:limit]
        conn.fetch = _fetch
        import unittest.mock as um
        with um.patch.object(db, "get_pool", AsyncMock(return_value=pool)):
            return await db.get_recent_score_dates(date(2026, 8, 11), UNANCHORED_SESSIONS_NEEDED)

    result = _run(_go())
    assert date(2026, 8, 8) not in result, "stray Saturday leaked back into the session list"
    assert result == [date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 7),
                       date(2026, 8, 6), date(2026, 8, 5), date(2026, 8, 4)]
