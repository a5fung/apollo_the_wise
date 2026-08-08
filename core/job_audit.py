"""Job-run telemetry context manager.

Wraps every scheduled job to record start/finish/duration/rows_written/status
in `mi_job_runs`. Catches the two degradation modes that `notify_job_failure`
misses today:

- **Slow run** — job exits clean but took 8x normal time (no exception fires).
  Surfaces via L2 anomaly on `job_duration_s_p95` per job_id, using existing
  baseline + MAD machinery in `system_audit.py`.

- **Silent zero** — job exits clean but wrote 0 rows when it should have
  written ≥ N. Status flips to 'empty_result', Telegram fires immediately.

- **Killed mid-run** (#512) — a process kill (deploy/OOM/SIGTERM) delivers
  `asyncio.CancelledError` at whatever await point the job happened to be
  suspended on (e.g. mid rate-limit sleep). `except Exception` does NOT catch
  this — `CancelledError` is `BaseException`, not `Exception`, since Python
  3.8 — which is exactly why `minute_volume_curves_refresh`'s 2026-07-31 kill
  wrote nothing (no audit row, no alert; confirmed by an empty `mi_audit_log`
  sweep for that window). Status flips to 'interrupted' (never 'failed' — the
  work may have completed; we only know the process died) and the exception
  is RE-RAISED unchanged so cooperative cancellation still propagates —
  swallowing `CancelledError` can hang shutdown. This write is BEST-EFFORT:
  it races the same process teardown that caused the problem, so it is not
  the only backstop — `scheduler.py::_reap_stale_running_runs` (#528)
  reconciles any row still 'running' from a PRIOR process at the next boot,
  regardless of whether this write landed.

Usage:

    async def _crypto_nightly_ingest_job():
        async with audit_run("crypto_nightly_ingest", expected_min_rows=10) as run:
            result = await run_nightly()
            run.rows_written = result.get("rows_scored", 0)

`expected_min_rows=None` opts out of the empty-result invariant — for jobs
like briefings, alerts, monitors that don't write tabular rows.

Exceptions inside the context are recorded as status='failed' and re-raised
so existing `notify_job_failure` callers in scheduler.py keep working.
CancelledError is recorded as status='interrupted' (see above) and re-raised.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from core.notifications import notify_job_failure

logger = logging.getLogger(__name__)


class JobRun:
    """Mutable handle the wrapped job uses to set rows_written."""

    def __init__(self, job_id: str, expected_min_rows: Optional[int]):
        self.job_id = job_id
        self.expected_min_rows = expected_min_rows
        self.rows_written: Optional[int] = None
        self.run_id: Optional[int] = None


async def _record_start(job_id: str, expected_min_rows: Optional[int]) -> Optional[int]:
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO mi_job_runs (job_id, started_at, status, expected_min_rows)
                VALUES ($1, NOW(), 'running', $2)
                RETURNING id
                """,
                job_id, expected_min_rows,
            )
            return row["id"] if row else None
    except Exception as e:
        logger.error(f"audit_run: failed to record start for {job_id}: {e}", exc_info=True)
        return None


async def _record_finish(
    run_id: Optional[int],
    job_id: str,
    started_at: float,
    status: str,
    rows_written: Optional[int],
    error_message: Optional[str],
) -> None:
    duration_s = time.monotonic() - started_at
    if run_id is None:
        return
    try:
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE mi_job_runs
                SET finished_at = NOW(),
                    duration_s = $2,
                    status = $3,
                    rows_written = $4,
                    error_message = $5
                WHERE id = $1
                """,
                run_id, duration_s, status, rows_written, error_message,
            )
    except Exception as e:
        logger.error(f"audit_run: failed to record finish for {job_id}: {e}", exc_info=True)


def audit_wrap(fn, job_id: str, expected_min_rows: Optional[int] = None):
    """Wrap a scheduled-job callable with `audit_run` telemetry.

    Use at APScheduler registration site:

        _scheduler.add_job(
            audit_wrap(_nightly_data_pull, "nightly_data_pull", expected_min_rows=5000),
            CronTrigger(...), id=JOB_NIGHTLY_DATA_PULL, ...
        )

    If `fn` returns an int, it's treated as `rows_written` for the empty-result
    invariant. Other return values are ignored.
    """
    async def wrapped(*args, **kwargs):
        async with audit_run(job_id, expected_min_rows) as run:
            result = await fn(*args, **kwargs)
            # bool is int in Python; exclude so a True/False return doesn't
            # silently set rows_written=1 and trip empty_result.
            if isinstance(result, int) and not isinstance(result, bool):
                run.rows_written = result
            return result
    wrapped.__name__ = getattr(fn, "__name__", job_id)
    return wrapped


@asynccontextmanager
async def audit_run(job_id: str, expected_min_rows: Optional[int] = None):
    """Context manager that records a scheduled-job invocation in `mi_job_runs`.

    Yields a `JobRun` handle; the wrapped job sets `run.rows_written` if it
    declares an `expected_min_rows`. Exceptions are recorded as status='failed'
    and re-raised so existing notify_job_failure handlers fire. CancelledError
    (#512 — process killed mid-run) is recorded separately as status=
    'interrupted' and re-raised — see module docstring.
    """
    started_at = time.monotonic()
    run = JobRun(job_id, expected_min_rows)
    run.run_id = await _record_start(job_id, expected_min_rows)
    try:
        yield run
    except asyncio.CancelledError:
        # #512: BaseException, not Exception — must be caught explicitly or it
        # skips the `except Exception` below entirely and this job vanishes
        # with no trace. Never claim 'failed'/'success' here: the process died,
        # so whether the work completed is genuinely unknown (#528 found a case
        # where it had). Best-effort — the write itself races the same
        # teardown that's cancelling us — so keep this branch FAST (no network
        # calls): _record_finish is one UPDATE, and the audit-log event name
        # ends in "_error" so it rides the existing %error% Telegram sweeps
        # (briefing.py, system_review.py, system_audit.py) instead of making
        # its own httpx round-trip inside a cancellation handler. If neither
        # write lands before the process dies, scheduler.py's boot-time reap
        # (#528) is the guaranteed backstop on next start.
        reason = "cancelled — process shutdown/restart mid-run; outcome unknown, check downstream tables"
        await _record_finish(
            run.run_id, job_id, started_at,
            status="interrupted",
            rows_written=run.rows_written,
            error_message=reason,
        )
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "job_cancelled_error",
                f"{job_id}: {reason}",
                json.dumps({"job_id": job_id, "rows_written": run.rows_written}),
            )
        except Exception as e:
            logger.warning(f"audit_run: failed to log cancellation audit event for {job_id}: {e}")
        raise
    except Exception as e:
        await _record_finish(
            run.run_id, job_id, started_at,
            status="failed",
            rows_written=run.rows_written,
            error_message=str(e)[:500],
        )
        raise
    else:
        # Determine terminal status. Convention:
        #   expected_min_rows is None         → no check (jobs that don't count rows)
        #   rows_written is None              → opt-out (job skipped, e.g. holiday)
        #   rows_written < expected_min_rows  → empty_result
        status = "success"
        if expected_min_rows is not None and run.rows_written is not None \
                and run.rows_written < expected_min_rows:
            status = "empty_result"
        await _record_finish(
            run.run_id, job_id, started_at,
            status=status,
            rows_written=run.rows_written,
            error_message=None,
        )
        if status == "empty_result":
            msg = (
                f"{job_id} produced {run.rows_written or 0} rows "
                f"(expected ≥ {expected_min_rows})"
            )
            logger.error(f"audit_run: empty_result — {msg}")
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "job_empty_result",
                    f"{job_id}: {run.rows_written or 0} rows (expected ≥ {expected_min_rows})",
                    json.dumps({
                        "job_id": job_id,
                        "rows_written": run.rows_written,
                        "expected_min_rows": expected_min_rows,
                    }),
                )
            except Exception as e:
                logger.warning(f"audit_run: failed to log audit event for {job_id}: {e}")
            try:
                await notify_job_failure(job_id, f"empty_result — {msg}")
            except Exception as e:
                logger.warning(f"audit_run: failed to notify for {job_id}: {e}")
