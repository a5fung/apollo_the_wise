"""Regression tests for the 2026-08-15 cancelled/order_failed capture-hole fix
(docs/roadmap/ep_profitability_program.md "STOP-GEOMETRY SWEEP" 2026-08-15).

THE DEFECT: missed_outcomes.py's `traded` CTE originally excluded only
status='skipped' rows (`status IS DISTINCT FROM 'skipped'`). A `cancelled`
row (chase cap, 10:00 ET unfilled-ORB sweep, broker cancel) or `order_failed`
row (submit failed after retry — the SAME chase-cap event, just on the retry
branch: order_manager.py's `_skip_chase_capped(_cap_reason, "order_failed")`)
satisfies that predicate, so it was silently counted as TRADED and got no
outcome row in EITHER population. EROC (2026-08-12, setup:chase_cap_exceeded)
is the concrete case this hid.

These tests exercise the ACTUAL SQL text `refresh_missed_outcomes()` sends to
`conn.execute` (extracted via regex, not hand-copied) so a revert of either
changed line — not just a revert of the shared constant — is caught. No live
Postgres is available in this environment (confirmed: no docker, no psql, no
local postgres binary) and the house test suite mocks asyncpg everywhere
(tests/conftest.py::make_mock_pool) rather than running an integration DB, so
this file follows that same established idiom.
"""
from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.missed_outcomes import (
    DECLINED_NEVER_FILLED_STATUSES,
    refresh_missed_outcomes,
)

MOD = "agents.market_intelligence.missed_outcomes"


# ── helpers: pull the REAL predicates out of the REAL executed SQL ──────────

def _extract_in_list(sql: str, anchor: str) -> tuple[str, ...]:
    """Find `<anchor> (…)` in the SQL text and return the quoted literals
    inside the parens as a tuple of bare strings. Raises (loud, not a silent
    False) if the anchor text isn't found at all — a shape change big enough
    to break this regex is itself worth a hard failure, not a swallowed skip.
    """
    m = re.search(re.escape(anchor) + r"\s*\(([^)]*)\)", sql)
    assert m, f"pattern {anchor!r} not found in executed SQL — predicate shape changed"
    return tuple(part.strip().strip("'") for part in m.group(1).split(","))


async def _run_and_capture_sql(fetch_rows=None) -> str:
    """Run refresh_missed_outcomes() against a mocked pool and return the SQL
    text of the big WITH-traded-AS(...) INSERT statement (as opposed to the
    schema-creation DDL or the trailing per-source COUNT query, which also go
    through conn.execute/conn.fetch on the same mocked connection)."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=fetch_rows or [])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)):
        await refresh_missed_outcomes(end_date=date(2026, 8, 15))
    calls = [c.args[0] for c in conn.execute.call_args_list if c.args]
    matches = [sql for sql in calls if "WITH traded AS" in sql]
    assert len(matches) == 1, f"expected exactly one main refresh query, found {len(matches)}"
    return matches[0]


# ── constant-level tests (the shared source of truth for both predicates) ───

def test_cancelled_is_declined_never_filled():
    assert "cancelled" in DECLINED_NEVER_FILLED_STATUSES


def test_order_failed_is_declined_never_filled():
    # Same chase-cap event, retry branch — order_manager.py line ~650 sets
    # THIS status instead of 'cancelled' for an identical never-filled case.
    assert "order_failed" in DECLINED_NEVER_FILLED_STATUSES


def test_skipped_still_declined_never_filled():
    # Pre-existing #199 behavior must not regress.
    assert "skipped" in DECLINED_NEVER_FILLED_STATUSES


def test_filled_and_closed_are_not_declined():
    # 'closed' covers both a normal stop-out/EOD-flatten AND the 10:00 ET
    # cleanup's exits-preserved branch for a filled-then-failed-reentry row —
    # both are REAL trades with REAL P&L and must stay traded.
    assert "filled" not in DECLINED_NEVER_FILLED_STATUSES
    assert "closed" not in DECLINED_NEVER_FILLED_STATUSES


# ── behavioral tests against the actual executed SQL ─────────────────────────

@pytest.mark.asyncio
async def test_cancelled_row_excluded_from_traded_population():
    """(a) half of the fix: a cancelled-without-fill row must NOT satisfy the
    `traded` CTE, so it falls through to the declined (missed-outcomes)
    population via NOT EXISTS(traded)."""
    sql = await _run_and_capture_sql()
    traded_excluded = _extract_in_list(sql, "AND status NOT IN")
    assert "cancelled" in traded_excluded
    assert "order_failed" in traded_excluded


@pytest.mark.asyncio
async def test_filled_row_stays_in_traded_population():
    """(b) a real fill must NOT be excluded from `traded` — i.e. must not be
    reclassified as declined."""
    sql = await _run_and_capture_sql()
    traded_excluded = _extract_in_list(sql, "AND status NOT IN")
    assert "filled" not in traded_excluded
    assert "closed" not in traded_excluded


@pytest.mark.asyncio
async def test_cancelled_row_reason_attribution_wired_up():
    """(a) other half: the skip_reason LATERAL in `high_unentered` must ALSO
    pick up cancelled/order_failed rows' skip_reason (e.g.
    setup:chase_cap_exceeded), not just status='skipped' rows — otherwise a
    cancelled row lands in the declined population with skip_reason=NULL,
    unattributable."""
    sql = await _run_and_capture_sql()
    lateral_included = _extract_in_list(sql, "AND lt.status IN")
    assert "cancelled" in lateral_included
    assert "order_failed" in lateral_included
    assert "skipped" in lateral_included  # #199 behavior preserved


@pytest.mark.asyncio
async def test_filled_row_never_misattributed_a_decline_reason():
    """A filled/closed row must never feed the skip_reason LATERAL — it has
    no decline to attribute (and, being excluded from the prior test's
    traded-exclusion, never reaches high_unentered's NOT EXISTS(traded) gate
    in the first place)."""
    sql = await _run_and_capture_sql()
    lateral_included = _extract_in_list(sql, "AND lt.status IN")
    assert "filled" not in lateral_included
    assert "closed" not in lateral_included


@pytest.mark.asyncio
async def test_traded_and_lateral_predicates_share_one_status_set():
    """(c) no double-count: the SAME constant drives both predicates, so a
    status is either (i) traded (excluded from both: not in traded-exclusion,
    never reaches the LATERAL at all because NOT EXISTS(traded) already
    dropped it) or (ii) declined-with-reason (in both sets) — never both.
    'filled' is structurally never in DECLINED_NEVER_FILLED_STATUSES, and
    mi_live_trades has a UNIQUE (ticker, alert_date, account_mode) constraint
    with every re-entry attempt (attempt_day1_reentry, order_manager.py) an
    UPDATE on that same row rather than a new INSERT — so a ticker-day whose
    row eventually reaches 'filled' can only ever be classified traded,
    regardless of any earlier cancelled/order_failed state on a prior
    attempt. A cancelled/order_failed row is a terminal dead end in this
    codebase (attempt_day1_reentry's precondition is status='filled' AND
    remaining_shares>0 — a cancelled/order_failed row can never reach it), so
    'cancel then later fill' cannot occur for the same row today; this test
    pins the invariant the argument depends on so a future change that makes
    it possible (e.g. a manual retry-a-cancelled-entry feature) gets caught
    here for re-review rather than silently double-counting."""
    sql = await _run_and_capture_sql()
    traded_excluded = set(_extract_in_list(sql, "AND status NOT IN"))
    lateral_included = set(_extract_in_list(sql, "AND lt.status IN"))
    assert traded_excluded == lateral_included == set(DECLINED_NEVER_FILLED_STATUSES)
    assert "filled" not in traded_excluded and "filled" not in lateral_included
