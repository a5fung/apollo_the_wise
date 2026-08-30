"""Regression tests for #554 — the shared "does this score_date look like a
real run" guard (`db._pick_latest_complete_score_date` /
`db.latest_complete_score_date` / `db._resolve_score_date`).

LIVE INCIDENT: `score_single_ticker` (rs_engine.py) writes its ONE on-demand
row keyed off the CALENDAR date, so a single held-name lookup on a non-trading
day creates a score_date whose entire population is that one row. Measured on
prod: exactly ONE row on 2026-05-30, 07-05, 07-12, 08-08 (all Sat/Sun). 19
call sites across agent.py/db.py/outcome_tracker.py/rs_engine.py/
state_alerts.py/theme_engine.py/scripts used a raw MAX(score_date) or
`ORDER BY score_date DESC LIMIT 1` (one — scripts/export_theme_snapshot.sql —
was already fixed separately) and could silently pick that stray day.

REAL PROD DATA used below (captured read-only, 2026-08-29, via
`SELECT score_date, COUNT(*) FROM mi_stock_scores ... GROUP BY score_date`):
  - The 2026-08-08 stray Saturday: exactly 1 row, surrounded by real
    ~2,400-row trading days (08-03 through 08-28).
  - The 2026-03-19/03-20 PARTIAL RUN (a nightly batch that died partway
    through, not a stray non-trading-day write): 168 and 172 rows against a
    ~9,780-row baseline the same week. This is the "other half" the task
    calls out — no write-site fix (score_single_ticker's date bug) ever
    prevents a batch dying mid-run, so this guard has to catch BOTH shapes
    forever, not just the Saturday one.

MUTATION CHECK (by inspection, not re-run by CI — matches
test_get_recent_score_dates.py's convention): removing the
`if n >= threshold: ... else keep scanning` filter in
`_pick_latest_complete_score_date` (i.e. reverting to "return counts[0][0]
if on_or_after not violated") makes every `test_*_excludes_*` test below
fail, since each pins the stray/partial date as ABSENT from the result while
feeding it in as `counts[0]` (the newest entry).

The raw-SQL-text sibling (`latest_complete_score_date_sql`, used where a
caller's tests pin an exact conn.fetch/fetchrow call count — theme_engine.py,
db.get_flag_universe, db.get_pipeline_status) implements the SAME bar in SQL
and was verified read-only against prod directly (not unit-tested here, since
this sandbox has no live Postgres): bounding it at 2026-08-08 returns
2026-08-07 (skips the stray); unbounded, it returns the real current latest
(2026-08-28 at capture time) — confirming the SQL and Python versions agree
on the real incident shape.
"""
from __future__ import annotations

import asyncio
from datetime import date

from tests.conftest import make_mock_pool

import agents.market_intelligence.db as db


def _run(coro):
    return asyncio.run(coro)


# ── Real prod shapes, captured read-only 2026-08-29 ─────────────────────────
# Newest-first (score_date, row_count) pairs, exactly as
# `latest_complete_score_date`'s SQL would return them.

_STRAY_SATURDAY_WINDOW = [
    (date(2026, 8, 8), 1),        # the stray — FIGS single-ticker lookup, non-trading day
    (date(2026, 8, 7), 2411),
    (date(2026, 8, 6), 2415),
    (date(2026, 8, 5), 2423),
    (date(2026, 8, 4), 2426),
    (date(2026, 8, 3), 2415),
    (date(2026, 7, 31), 2389),
    (date(2026, 7, 30), 2401),
    (date(2026, 7, 29), 2405),
    (date(2026, 7, 28), 2420),
]

_PARTIAL_RUN_WINDOW = [
    (date(2026, 3, 20), 172),     # the partial run — batch died at ~1.8% of expected
    (date(2026, 3, 19), 168),     # the day before it: same shape, two in a row
    (date(2026, 3, 13), 9797),
    (date(2026, 3, 6), 9784),
    (date(2026, 2, 27), 9809),
    (date(2026, 2, 20), 9772),
    (date(2026, 2, 13), 9780),
    (date(2026, 2, 6), 9767),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. The pure filter — REAL prod shapes, no mocking
# ═══════════════════════════════════════════════════════════════════════════

def test_excludes_stray_1row_saturday():
    """The exact 2026-08-08 incident: a 1-row day is newest, but the fix
    must walk past it to the real latest run."""
    result = db._pick_latest_complete_score_date(_STRAY_SATURDAY_WINDOW)
    assert result == date(2026, 8, 7)
    assert result != date(2026, 8, 8)


def test_excludes_partial_run_even_when_two_in_a_row():
    """The OTHER shape the task calls out: a nightly batch dying partway
    through, not a non-trading-day write. 168 and 172 rows are BOTH below the
    bar (0.5 * median(9797, 9784, 9809, ...) ≈ 4884) — real evidence that a
    single stray day never contaminates the 10-window median past its own bar,
    even with two low-count days back to back."""
    result = db._pick_latest_complete_score_date(_PARTIAL_RUN_WINDOW)
    assert result == date(2026, 3, 13)
    assert result not in (date(2026, 3, 19), date(2026, 3, 20))


def test_no_strays_matches_naive_latest():
    """Sanity: with an all-real-run table (the normal case), the fix returns
    exactly what a raw MAX(score_date) would have returned."""
    window = [(date(2026, 8, 28), 2414), (date(2026, 8, 27), 2415),
              (date(2026, 8, 26), 2432), (date(2026, 8, 25), 2463)]
    assert db._pick_latest_complete_score_date(window) == date(2026, 8, 28)


def test_empty_input_returns_none():
    assert db._pick_latest_complete_score_date([]) is None


def test_on_or_after_bound_can_exhaust_to_none():
    """state_alerts.py's 12-18-day lookback band shape: if the ONLY date
    inside the band is a stray, the function must return None (no usable
    prior date) — NEVER fall through to the stray just because it's the only
    candidate in range. Median is still computed from the full 10-window
    (not just the in-band slice) — see the docstring for why: `on_or_after`
    here restricts the band to ONLY 2026-08-08 (the next-newest entry,
    08-07, is older than the floor and stops the walk), while the median
    that sets the bar still comes from the real ~2,400-row trailing days."""
    result = db._pick_latest_complete_score_date(
        _STRAY_SATURDAY_WINDOW, on_or_after=date(2026, 8, 8),
    )
    assert result is None


def test_on_or_after_bound_finds_real_date_in_band():
    """Same band shape, but the real 08-07 row is also in range — must be
    picked over the stray, and the walk-back respects the floor once past it."""
    result = db._pick_latest_complete_score_date(
        _STRAY_SATURDAY_WINDOW, on_or_after=date(2026, 8, 6),
    )
    assert result == date(2026, 8, 7)


# ═══════════════════════════════════════════════════════════════════════════
# 2. The async wrapper — wiring (mocked fetch, real-shape return rows)
# ═══════════════════════════════════════════════════════════════════════════

def _wire_fetch_rows(rows: list[tuple[date, int]]):
    pool, conn = make_mock_pool()
    calls = []

    async def _fetch(sql, *args):
        calls.append(args)
        return [{"score_date": d, "n": n} for d, n in rows]
    conn.fetch = _fetch
    return pool, conn, calls


def test_latest_complete_score_date_skips_stray_end_to_end():
    """`latest_complete_score_date` takes `conn` directly (callers already
    hold one via `pool.acquire()`), so no pool mocking needed here."""
    pool, conn, calls = _wire_fetch_rows(_STRAY_SATURDAY_WINDOW)
    result = _run(db.latest_complete_score_date(conn))
    assert result == date(2026, 8, 7)


def test_latest_complete_score_date_default_bound_is_far_future():
    """No on_or_before ⇒ the fetch's bound param must not exclude today's
    (or any future) row — matches the old unbounded MAX(score_date)."""
    pool, conn, calls = _wire_fetch_rows(_STRAY_SATURDAY_WINDOW)
    _run(db.latest_complete_score_date(conn))
    assert calls[0][0] == date(9999, 12, 31)


def test_latest_complete_score_date_passes_through_on_or_before():
    pool, conn, calls = _wire_fetch_rows([(date(2026, 8, 7), 2411)])
    _run(db.latest_complete_score_date(conn, on_or_before=date(2026, 8, 7)))
    assert calls[0][0] == date(2026, 8, 7)


# ═══════════════════════════════════════════════════════════════════════════
# 3. `_resolve_score_date` — the double-bug trap (a stray day AS `requested`)
# ═══════════════════════════════════════════════════════════════════════════
# Before #554, `_resolve_score_date` checked `count(*) FROM mi_stock_scores
# WHERE score_date = requested` and returned `requested` on ANY nonzero
# count — so a caller resolving et_today() on the exact stray Saturday got
# the stray handed straight back (count=1 passed the check), never reaching
# the MAX(score_date) fallback at all. This is the trap the fix must close:
# `requested` itself must clear the completeness bar, not just "have a row".

def test_resolve_score_date_does_not_return_stray_as_requested(monkeypatch):
    """The exact double-bug shape: requested == the stray Saturday itself."""
    pool, conn, calls = _wire_fetch_rows(_STRAY_SATURDAY_WINDOW)
    result = _run(db._resolve_score_date(conn, date(2026, 8, 8)))
    assert result == date(2026, 8, 7)
    assert result != date(2026, 8, 8)


def test_resolve_score_date_returns_requested_when_it_is_complete():
    """Unchanged behavior for the common case: requested IS a real run."""
    pool, conn, calls = _wire_fetch_rows(_STRAY_SATURDAY_WINDOW[1:])  # no stray in range
    result = _run(db._resolve_score_date(conn, date(2026, 8, 7)))
    assert result == date(2026, 8, 7)


def test_resolve_score_date_falls_back_to_requested_when_no_data_at_all():
    """No mi_stock_scores rows at all (e.g. brand-new system) — must not
    crash or return None; falls back to `requested` itself, matching the
    original function's contract."""
    pool, conn, calls = _wire_fetch_rows([])
    result = _run(db._resolve_score_date(conn, date(2026, 8, 8)))
    assert result == date(2026, 8, 8)
