"""#528 — boot-time reconciliation of orphaned `mi_job_runs` 'running' rows.

`nightly_data_pull` id=118746 started 17:00:00 ET, was killed mid-run by a 17:07 deploy,
and sat status='running' with a NULL finished_at for DAYS — the OLD reaper (shipped
2026-05-03) only matched rows `started_at < NOW() - INTERVAL '2 hours'`, so a row had to
wait for BOTH a 2h age AND another restart before it could ever get caught; with no
restart in that window it just never fired. The WORK had completed (12,293
mi_daily_closes rows that evening) — so the fix must never claim 'failed'/'success',
only 'interrupted' (the honest "we don't know, the process died" state).

Fix: `_reap_stale_running_runs(boot_time)` sweeps every 'running' row with
`started_at < boot_time` — `boot_time` is captured before this process has fired a
single job, so no time-based guessing is needed; the row is caught on the VERY NEXT
boot. Role-scoped (#256 W2 split, `apollo-execution` vs `apollo-market`/intelligence
share `mi_job_runs`) so one container's restart can never reap a job genuinely still
running in the OTHER, un-restarted container.

MUTATION CHECK (recorded here, not re-run by CI): reverting the role-scoping (dropping
the `job_id` clause so ALL 'running' rows are swept unconditionally) makes
`test_execution_restart_does_not_reap_intelligence_job` FAIL — an execution-container
boot would mark a genuinely-still-running intelligence job 'interrupted' and page a
false alert.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import scheduler as sched
from agents.market_intelligence import constants
from tests.conftest import make_mock_pool

_ET_NOW = datetime(2026, 8, 8, 17, 10, tzinfo=sched._ET)


def _wire(monkeypatch, *, rows, role="combined"):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(sched, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(sched, "log_audit_event", audit)
    notify = AsyncMock()
    monkeypatch.setattr(sched, "notify_owner", notify)
    monkeypatch.setattr(constants, "SERVICE_ROLE", role)
    return pool, conn, audit, notify


@pytest.mark.asyncio
async def test_reaps_row_started_before_boot_time_as_interrupted(monkeypatch):
    row = {"job_id": "nightly_data_pull", "started_at": _ET_NOW - timedelta(minutes=10)}
    pool, conn, audit, notify = _wire(monkeypatch, rows=[row])

    await sched._reap_stale_running_runs(_ET_NOW)

    conn.fetch.assert_awaited_once()
    sql, args = conn.fetch.await_args.args[0], conn.fetch.await_args.args[1:]
    assert "status='interrupted'" in sql
    assert "SET status='aborted'" not in sql   # never the old failure-flavored label
    assert "status='running' AND started_at < $1" in sql
    assert args[0] == _ET_NOW
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "stale_runs_reaped"
    notify.assert_awaited_once()               # surfaced — a genuine interruption was found
    assert "interrupted" in notify.await_args.args[0].lower()
    assert "failed" not in notify.await_args.args[0].lower()   # #528: never claim failure


@pytest.mark.asyncio
async def test_no_stale_rows_produces_nothing(monkeypatch):
    """The 'guard that always fires is not a guard' check: a normal boot with zero
    orphaned rows must write NO audit event and send NO Telegram."""
    pool, conn, audit, notify = _wire(monkeypatch, rows=[])

    await sched._reap_stale_running_runs(_ET_NOW)

    audit.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_combined_role_sweeps_every_job_id(monkeypatch):
    pool, conn, audit, notify = _wire(monkeypatch, rows=[], role="combined")

    await sched._reap_stale_running_runs(_ET_NOW)

    sql = conn.fetch.await_args.args[0]
    assert "job_id = ANY" not in sql   # combined: no scoping clause at all


@pytest.mark.asyncio
async def test_execution_role_scopes_to_execution_owned_ids(monkeypatch):
    pool, conn, audit, notify = _wire(monkeypatch, rows=[], role="execution")

    await sched._reap_stale_running_runs(_ET_NOW)

    sql, args = conn.fetch.await_args.args[0], conn.fetch.await_args.args[1:]
    assert "AND job_id = ANY($3::text[])" in sql
    assert set(args[2]) == set(sched.EXECUTION_OWNED_JOB_IDS)


@pytest.mark.asyncio
async def test_intelligence_role_excludes_execution_owned_ids(monkeypatch):
    pool, conn, audit, notify = _wire(monkeypatch, rows=[], role="intelligence")

    await sched._reap_stale_running_runs(_ET_NOW)

    sql, args = conn.fetch.await_args.args[0], conn.fetch.await_args.args[1:]
    assert "AND NOT (job_id = ANY($3::text[]))" in sql
    assert set(args[2]) == set(sched.EXECUTION_OWNED_JOB_IDS)


@pytest.mark.asyncio
async def test_execution_restart_does_not_reap_intelligence_job(monkeypatch):
    """The advisor-caught blocker: apollo-execution and apollo-market (intelligence)
    are SEPARATE containers sharing mi_job_runs. An execution-container reap must be
    scoped so it can never touch a job that belongs to intelligence (and is possibly
    still genuinely running there) — this test proves the SQL sent for role=execution
    would exclude 'nightly_data_pull' (an intelligence-owned job) regardless of what
    the (mocked) DB returns, by asserting the scoping clause + id set are correct."""
    pool, conn, audit, notify = _wire(monkeypatch, rows=[], role="execution")

    await sched._reap_stale_running_runs(_ET_NOW)

    args = conn.fetch.await_args.args[1:]
    swept_ids = set(args[2])
    assert "nightly_data_pull" not in swept_ids       # intelligence-owned — never in execution's sweep set
    assert "orb_window_cleanup" in swept_ids           # a real execution-owned id, for sanity


@pytest.mark.asyncio
async def test_reap_db_failure_is_logged_not_raised(monkeypatch):
    """A DB outage during the reap must not crash scheduler boot."""
    pool, conn = make_mock_pool()
    monkeypatch.setattr(sched, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(sched, "log_audit_event", AsyncMock())
    monkeypatch.setattr(sched, "notify_owner", AsyncMock())
    monkeypatch.setattr(constants, "SERVICE_ROLE", "combined")

    await sched._reap_stale_running_runs(_ET_NOW)   # must not raise
