"""Regression tests for #583 — mi_ep_missed_outcomes rows outside
refresh_missed_outcomes's 30-day rolling window were never re-validated, so
once a row aged past the window it kept its ORIGINAL classification forever,
even after a later fix changed what the categorisation/inclusion logic would
produce for it.

VERIFIED IN PROD (2026-08-22): 279 of 298 `high_unentered` rows and 19 of 57
`window_missed` rows had no matching source row left in mi_ep_alerts at all
(orphaned by the #268 `source='live'` fix, which excludes replay-sourced
alerts going forward but never touched rows written before it shipped). A
gate-ranking table built 2026-08-21 credited both categories with 5
"≥100%-winner" names sourced entirely from these orphans — the true count
for both was zero.

THE FIX: `reconcile_missed_outcomes_categories()` diffs the FULL stored
table against a full-history recompute of the CURRENT categorisation/
inclusion logic (no rolling window at all — that window was the bug) and:
  - DELETEs rows the current logic no longer produces at all ("orphans").
  - UPDATEs rows whose stored category no longer matches a fresh recompute
    ("miscategorized" — zero found in prod today, but this is the guard for
    the NEXT categorisation fix, which is the exact bug class #583 names:
    "when the categorisation logic is FIXED, the old rows keep the old
    classification forever").
  - Backfills rows the current logic says should exist but don't yet
    ("missing" — the 2026-08-15 cancelled/order_failed capture-hole fix's
    own blind spot: 27 HIGH alerts dated 2026-05-11..2026-07-15 with
    status='cancelled' were silently counted as TRADED until that fix
    shipped, and by then they'd already aged past the 30-day window, so the
    windowed UPSERT could never reach them).

`refresh_missed_outcomes()` itself is UNCHANGED — its windowed UPSERT
correctly handles new alerts and maturing forward returns and was never the
part of the mechanism that was broken; `reconcile_missed_outcomes_categories`
is the missing full-history guard.

Same house idiom as test_missed_outcomes_cancelled_capture.py: mocked
asyncpg pool (tests/conftest.py::make_mock_pool), no live Postgres in this
environment.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.missed_outcomes import (
    _MISSED_OUTCOMES_BACKFILL_SQL,
    _MISSED_OUTCOMES_TRUTH_SQL,
    reconcile_missed_outcomes_categories,
)

MOD = "agents.market_intelligence.missed_outcomes"


# ── the core #583 guard: no rolling lower bound in the reconcile queries ────

def test_truth_sql_has_no_rolling_lower_bound():
    """The whole #583 bug WAS a lower-bound date filter (`alert_date >= $1`)
    on the categorisation query — a row older than that bound was invisible
    to every future refresh, forever. The reconcile query must carry ONLY an
    upper bound, so no row can ever again fall permanently out of reach."""
    assert "alert_date >=" not in _MISSED_OUTCOMES_TRUTH_SQL
    assert "scan_date >=" not in _MISSED_OUTCOMES_TRUTH_SQL
    assert "alert_date <= $1" in _MISSED_OUTCOMES_TRUTH_SQL
    assert "scan_date <= $1" in _MISSED_OUTCOMES_TRUTH_SQL


def test_backfill_sql_has_no_rolling_lower_bound():
    assert "alert_date >=" not in _MISSED_OUTCOMES_BACKFILL_SQL
    assert "scan_date >=" not in _MISSED_OUTCOMES_BACKFILL_SQL


def test_backfill_sql_guards_daily_closes_fanout_behind_not_exists_stored():
    """Cost guard: the NOT EXISTS(already stored) check must run in each
    lineage CTE BEFORE the mi_daily_closes join, so the expensive fanout is
    bounded by the (small) missing-row count, not by full source-table
    history — this is what keeps the reconcile cheap forever."""
    assert _MISSED_OUTCOMES_BACKFILL_SQL.count("FROM mi_ep_missed_outcomes existing") == 3


# ── behavioral: orphan pruned, match left alone, miscategorized corrected,
#    missing backfilled — one action type per test, isolated ───────────────

def _stored(**kw):
    return kw


@pytest.mark.asyncio
async def test_orphaned_row_is_pruned():
    """A stored row whose (ticker, alert_date, source) the current logic no
    longer produces at all — #583's actual prod finding (279 of 298
    high_unentered rows, source row long gone from mi_ep_alerts) — must be
    DELETEd, not left to sit with a stale classification forever."""
    pool, conn = make_mock_pool()
    truth = []  # current logic produces nothing for this ticker/date
    stored = [_stored(id=1, ticker="AEHR", alert_date=date(2026, 2, 11),
                       source="high_unentered", skip_reason=None,
                       skip_category="high_unentered")]
    conn.fetch = AsyncMock(side_effect=[truth, stored])
    conn.execute = AsyncMock(return_value=None)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result["orphaned_pruned"] == 1
    assert result["miscategorized_fixed"] == 0
    assert result["missing_backfilled"] == 0
    delete_calls = [c for c in conn.execute.call_args_list if c.args and "DELETE" in c.args[0]]
    assert len(delete_calls) == 1
    assert delete_calls[0].args[1] == [1]


@pytest.mark.asyncio
async def test_matching_row_is_left_alone():
    """A row still reproducible with the SAME category must not be touched —
    no DELETE, no UPDATE, no wasted write."""
    pool, conn = make_mock_pool()
    key_row = dict(ticker="ARX", alert_date=date(2026, 5, 14),
                    source="high_unentered",
                    skip_reason="window:out_of_orb: detected 09:50 ET",
                    skip_category="window_missed")
    truth = [key_row]
    stored = [_stored(id=2, **key_row)]
    conn.fetch = AsyncMock(side_effect=[truth, stored])
    conn.execute = AsyncMock(return_value=None)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result["orphaned_pruned"] == 0
    assert result["miscategorized_fixed"] == 0
    assert result["missing_backfilled"] == 0
    assert not any("DELETE" in c.args[0] for c in conn.execute.call_args_list if c.args)
    assert not any("UPDATE" in c.args[0] for c in conn.execute.call_args_list if c.args)


@pytest.mark.asyncio
async def test_miscategorized_row_is_corrected_not_deleted():
    """A row still reproducible but under a DIFFERENT category than what's
    stored — the guard for the NEXT categorisation fix (#583's named failure
    mode verbatim: 'when the categorisation logic is FIXED, the old rows
    keep the old classification forever'). Must UPDATE in place, never
    delete+lose real history."""
    pool, conn = make_mock_pool()
    truth = [dict(ticker="XYZ", alert_date=date(2026, 6, 1), source="scan_filter",
                   skip_reason="filter:new_bucket", skip_category="new_category")]
    stored = [_stored(id=3, ticker="XYZ", alert_date=date(2026, 6, 1), source="scan_filter",
                       skip_reason="filter:new_bucket", skip_category="filter_other")]
    conn.fetch = AsyncMock(side_effect=[truth, stored])
    conn.execute = AsyncMock(return_value=None)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result["orphaned_pruned"] == 0
    assert result["miscategorized_fixed"] == 1
    update_calls = [c for c in conn.execute.call_args_list if c.args and "UPDATE" in c.args[0]]
    assert len(update_calls) == 1
    _, ids, cats, reasons = update_calls[0].args
    assert ids == [3]
    assert cats == ["new_category"]
    assert reasons == ["filter:new_bucket"]


@pytest.mark.asyncio
async def test_missing_row_triggers_backfill_insert():
    """Current logic says a row should exist (the 2026-08-15 fix's own
    capture hole: a HIGH silently miscounted as traded until that fix
    shipped, by which point it had aged past the 30-day window) but the
    table has none — the backfill INSERT must run."""
    pool, conn = make_mock_pool()
    truth = [dict(ticker="BZH", alert_date=date(2026, 5, 11), source="high_unentered",
                   skip_reason="ORB window unfilled", skip_category="high_unentered")]
    stored = []
    conn.fetch = AsyncMock(side_effect=[truth, stored])

    async def _execute(sql, *args):
        if sql == _MISSED_OUTCOMES_BACKFILL_SQL:
            return "INSERT 0 1"  # real asyncpg shape — pins the count-parsing fix
        return None
    conn.execute = AsyncMock(side_effect=_execute)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result["missing_expected"] == 1
    assert result["missing_backfilled"] == 1
    backfill_calls = [
        c for c in conn.execute.call_args_list
        if c.args and c.args[0] == _MISSED_OUTCOMES_BACKFILL_SQL
    ]
    assert len(backfill_calls) == 1
    assert backfill_calls[0].args[1] == date(2026, 8, 22)


@pytest.mark.asyncio
async def test_backfill_insert_undercount_is_reported_not_hidden():
    """#583 review note: `ON CONFLICT DO NOTHING` means the INSERT can land
    FEWER rows than expected (e.g. a row appeared between the diff fetch and
    the insert). `missing_backfilled` must reflect what the DB actually did,
    not the Python-side prediction — a silently-optimistic audit number is
    the same class of blind spot #583 exists to close."""
    pool, conn = make_mock_pool()
    truth = [
        dict(ticker="AAA", alert_date=date(2026, 6, 1), source="scan_filter",
             skip_reason="filter:adv_too_low", skip_category="adv_low"),
        dict(ticker="BBB", alert_date=date(2026, 6, 2), source="scan_filter",
             skip_reason="filter:adv_too_low", skip_category="adv_low"),
    ]
    stored = []
    conn.fetch = AsyncMock(side_effect=[truth, stored])

    async def _execute(sql, *args):
        if sql == _MISSED_OUTCOMES_BACKFILL_SQL:
            return "INSERT 0 1"  # only 1 of the 2 expected actually landed
        return None
    conn.execute = AsyncMock(side_effect=_execute)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result["missing_expected"] == 2
    assert result["missing_backfilled"] == 1


@pytest.mark.asyncio
async def test_no_missing_rows_skips_backfill_insert():
    """No wasted write when nothing is missing — the common nightly case."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], []])
    conn.execute = AsyncMock(return_value=None)

    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        result = await reconcile_missed_outcomes_categories(as_of=date(2026, 8, 22))

    assert result == {
        "orphaned_pruned": 0, "miscategorized_fixed": 0,
        "missing_backfilled": 0, "missing_expected": 0, "as_of": "2026-08-22",
    }
    assert not any(
        c.args and c.args[0] == _MISSED_OUTCOMES_BACKFILL_SQL
        for c in conn.execute.call_args_list
    )
