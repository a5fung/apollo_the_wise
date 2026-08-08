"""#512 — `core.job_audit.audit_run` must not vanish a job killed mid-run.

`asyncio.CancelledError` is BaseException (not Exception) since Python 3.8, so the
existing `except Exception` handler silently missed it: `minute_volume_curves_refresh`
was killed by an 18:42 ET restart 2026-07-31 mid-Polygon-rate-limit-sleep and wrote
NOTHING to mi_job_runs or mi_audit_log — confirmed live by an empty `%job%`/`%fail%`
sweep of mi_audit_log for that window.

Fix: `audit_run` now catches `asyncio.CancelledError` explicitly, records status=
'interrupted' (never 'failed'/'success' — the process died, outcome genuinely
unknown), writes one audit-log event named to ride the existing `%error%` Telegram
sweeps (never a synchronous httpx call inside the cancellation handler — that's the
"drain jobs before shutdown" anti-pattern PLAN #512 explicitly forbids), and
RE-RAISES unchanged so cooperative cancellation still propagates.

MUTATION CHECK (recorded here, not re-run by CI): reverting the new
`except asyncio.CancelledError:` clause (so cancellation falls through to the
existing bare `except Exception` / propagates uncaught) makes
`test_cancelled_job_is_recorded_as_interrupted_and_reraised` FAIL — the UPDATE
to mi_job_runs never happens (status stays 'running' from `_record_start`),
confirming the assertion has teeth.
"""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock

from core import job_audit
from core.job_audit import audit_run

from tests.conftest import make_mock_pool


def _wire(monkeypatch, *, run_id=42):
    """Patch the DB surface `audit_run` reaches via LOCAL imports
    (`from agents.market_intelligence.db import get_pool` / `log_audit_event`
    inside the function bodies) — monkeypatching the *source* module's
    attributes is what a local import re-resolves at call time."""
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"id": run_id})
    conn.execute = AsyncMock(return_value="UPDATE 1")
    audit = AsyncMock()

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "log_audit_event", audit)
    monkeypatch.setattr(job_audit, "notify_job_failure", AsyncMock())
    return pool, conn, audit


@pytest.mark.asyncio
async def test_cancelled_job_is_recorded_as_interrupted_and_reraised(monkeypatch):
    pool, conn, audit = _wire(monkeypatch)

    with pytest.raises(asyncio.CancelledError):
        async with audit_run("minute_volume_curves_refresh", expected_min_rows=50000) as run:
            run.rows_written = None
            raise asyncio.CancelledError()

    # the finish UPDATE landed with status='interrupted' — never 'failed'/'aborted'/'success'
    conn.execute.assert_awaited_once()
    sql, args = conn.execute.await_args.args[0], conn.execute.await_args.args[1:]
    assert "UPDATE mi_job_runs" in sql
    run_id, duration_s, status, rows_written, error_message = args
    assert run_id == 42
    assert status == "interrupted"
    assert "failed" not in (error_message or "").lower()
    assert "success" not in (error_message or "").lower()

    # audited loudly, event-type ends in "_error" so it rides the existing %error% sweeps
    audit.assert_awaited_once()
    event_type, summary = audit.await_args.args[0], audit.await_args.args[1]
    assert event_type.endswith("_error")
    assert "minute_volume_curves_refresh" in summary


@pytest.mark.asyncio
async def test_cancelled_job_never_calls_notify_job_failure(monkeypatch):
    """Point 2 from review: a synchronous Telegram POST inside the cancellation
    handler is exactly the 'drain before shutdown' anti-pattern PLAN #512 forbids
    (money containers must restart fast). The interrupted case must ride the
    existing %error% audit-log sweeps instead of making its own network call here."""
    pool, conn, audit = _wire(monkeypatch)
    notify = job_audit.notify_job_failure

    with pytest.raises(asyncio.CancelledError):
        async with audit_run("minute_volume_curves_refresh") as run:
            raise asyncio.CancelledError()

    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_job_write_failure_still_reraises_cancellation(monkeypatch):
    """Even if the DB is unreachable when we try to record the interruption, the
    ORIGINAL CancelledError must still propagate — never swallowed, cooperative
    cancellation depends on it."""
    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(job_audit, "notify_job_failure", AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        async with audit_run("some_job") as run:
            raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_ordinary_exception_still_recorded_failed_unchanged(monkeypatch):
    """Regression: the pre-existing Exception path (status='failed') must be untouched
    by the new CancelledError branch — CancelledError is BaseException, not a subclass
    of Exception, so the two branches are disjoint by construction."""
    pool, conn, audit = _wire(monkeypatch)

    with pytest.raises(ValueError):
        async with audit_run("some_job") as run:
            raise ValueError("boom")

    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args[1:]
    status = args[2]
    assert status == "failed"
    audit.assert_not_awaited()   # unchanged: the 'failed' path never wrote an audit-log event


@pytest.mark.asyncio
async def test_clean_run_writes_success_no_interrupted_event(monkeypatch):
    """Guard-that-always-fires check: a normal, uninterrupted run must never touch the
    'interrupted' status or fire the cancellation audit event."""
    pool, conn, audit = _wire(monkeypatch)

    async with audit_run("some_job", expected_min_rows=10) as run:
        run.rows_written = 20

    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args[1:]
    assert args[2] == "success"
    audit.assert_not_awaited()
