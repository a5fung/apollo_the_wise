"""#672 — a skipped nightly job must be LOUD, and the pull must not run forever.

THE INCIDENT, not a hypothetical. On 2026-09-18 `nightly_data_pull` deadlocked and held the
scheduler past every queued job's `misfire_grace_time`. APScheduler skipped **23 jobs** — the
evening briefing among them — emitted EVENT_JOB_MISSED for each, and **nothing was listening**;
the scheduler had no listeners at all.

⚠ The job ids used below are deliberately NOT the ranking-shadow one, even though it was among
the 23: that module's own test greps `agents/` and `tests/` for its name as a THE LINE proxy for
a decision-path import, and a mention here is a false positive. Reworded rather than widening
that guard — a safety guard must not be relaxed to accommodate prose. Nobody knew until the gap was found by hand the next
morning.

A skipped job is invisible in a way a failed one is not: `audit_wrap` only records a run that
STARTED, so a job that never starts writes no row anywhere. 09-18 was reconstructable at all only
because the hung pull had opened its own row first. The other 23 left no trace.

Every test here exercises BEHAVIOUR — the real listener, the real flush, the real bounded wrapper,
and the function the scheduler ACTUALLY registers. No source text is read.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from agents.market_intelligence import scheduler as sched


# ── the listener is actually wired to the scheduler ───────────────────────────────────────

def test_the_scheduler_registers_a_missed_job_listener(monkeypatch):
    """MUTATION: deleting the `add_listener(_on_job_missed, EVENT_JOB_MISSED)` line reddens this.
    Verified before commit. Without it the whole file below tests a function nothing calls."""
    from apscheduler.events import EVENT_JOB_MISSED
    from tests.test_job_partition import _CapturingScheduler

    captured = {}

    class _Spy(_CapturingScheduler):
        def add_listener(self, callback, mask=None):
            captured.setdefault("calls", []).append((callback, mask))
            super().add_listener(callback, mask)

    monkeypatch.setattr(sched, "AsyncIOScheduler", _Spy)

    async def _go():
        sched.start_scheduler()
    asyncio.run(_go())

    calls = captured.get("calls", [])
    assert calls, "start_scheduler registered NO listeners — a missed job would again be silent"
    assert any(cb is sched._on_job_missed and mask == EVENT_JOB_MISSED for cb, mask in calls), (
        f"the missed-job listener is not registered for EVENT_JOB_MISSED; got {calls}")


def test_the_nightly_pull_the_scheduler_registers_is_the_BOUNDED_one(monkeypatch):
    """The wiring, not the wrapper's existence. A bounded function that nothing schedules is
    exactly the shape of a fix that does nothing.

    MUTATION: pointing the registration back at `_nightly_data_pull` reddens this."""
    from tests.test_job_partition import _CapturingScheduler
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)

    holder = {}
    real = sched._apply_role_partition

    def _spy(scheduler, role):
        holder["jobs"] = list(scheduler.get_jobs())
        return real(scheduler, role)

    monkeypatch.setattr(sched, "_apply_role_partition", _spy)

    async def _go():
        sched.start_scheduler()
    asyncio.run(_go())

    job = next((j for j in holder.get("jobs", []) if j.id == sched.JOB_NIGHTLY_DATA_PULL), None)
    assert job is not None, "nightly_data_pull is not registered at all"

    # follow the audit_wrap closure to the function it will actually await — runtime
    # introspection of a closure, never source text.
    names = set()
    stack = [job.func]
    while stack:
        f = stack.pop()
        names.add(getattr(f, "__name__", ""))
        for cell in (getattr(f, "__closure__", None) or ()):
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if callable(v) and getattr(v, "__name__", "") not in names:
                stack.append(v)
    assert "_nightly_data_pull_bounded" in names, (
        f"the scheduler still runs the UNBOUNDED pull — a hang would again be open-ended. "
        f"Registered chain: {sorted(n for n in names if n)}")


# ── the flush turns a burst into one alert, without losing a single row ───────────────────

@pytest.mark.asyncio
async def test_a_burst_of_missed_jobs_is_ONE_alert_that_names_every_job(monkeypatch):
    """Friday's shape: one stall skips a whole chain. Alerting per job would have sent 23
    Telegrams in an hour, which is how an alert trains you to ignore it — but the RECORD must
    still be complete.

    MUTATION: flushing per event (no buffer) sends 3 messages here instead of 1; dropping the
    executemany leaves `rows` empty. Both verified RED."""
    sent, rows, audits = [], [], []

    class _Conn:
        async def executemany(self, sql, args):
            rows.extend(args)

    class _Pool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(s): return _Conn()
                async def __aexit__(s, *a): return False
            return _Ctx()

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(dbmod, "get_pool", lambda: asyncio.sleep(0, result=_Pool()))
    monkeypatch.setattr(dbmod, "log_audit_event",
                        lambda ev, msg: audits.append((ev, msg)) or asyncio.sleep(0))
    monkeypatch.setattr(sched, "notify_owner", lambda m: sent.append(m) or asyncio.sleep(0))
    monkeypatch.setattr(sched, "_MISSED_FLUSH_DELAY_S", 0)
    sched._missed_buffer.clear()
    sched._missed_loop = asyncio.get_running_loop()
    sched._missed_flush_task = None

    class _Ev:
        def __init__(self, jid, hh):
            self.job_id = jid
            self.scheduled_run_time = datetime(2026, 9, 18, hh, 30)

    for jid, hh in (("evening_briefing", 18), ("wick_forward_returns", 17), ("parabolic_scan", 17)):
        sched._on_job_missed(_Ev(jid, hh))

    assert sched._missed_flush_task is not None, "no flush was scheduled — the burst is silent"
    await sched._missed_flush_task

    assert len(sent) == 1, f"a burst must coalesce into ONE alert, got {len(sent)}"
    for jid in ("evening_briefing", "wick_forward_returns", "parabolic_scan"):
        assert jid in sent[0], f"{jid} was missed but not named in the alert"
    assert len(rows) == 3, f"every miss must be RECORDED even when the alert is summarised; got {len(rows)}"
    assert all(r[0] and "missed" not in str(r[1]) for r in rows)
    assert audits and audits[0][0] == "jobs_missed", "no durable audit row for the misses"


@pytest.mark.asyncio
async def test_the_listener_never_raises_into_the_scheduler(monkeypatch):
    """A listener that throws propagates into APScheduler's dispatch loop — turning a REPORTING
    gap into an outage. It must swallow everything.

    MUTATION: removing the try/except makes this raise AttributeError."""
    sched._missed_buffer.clear()

    class _Broken:
        @property
        def job_id(self):
            raise RuntimeError("boom")

    sched._on_job_missed(_Broken())          # must not raise


# ── the pull cannot run forever ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_pull_is_cancelled_at_the_ceiling_and_says_it_was_partial(monkeypatch):
    """The 2026-09-18 hang ran 7.3 h because nothing bounded it.

    MUTATION: removing the `wait_for` hangs this test rather than passing it — which is why the
    assertion is on the RAISED TimeoutError and on what the alert SAYS, not on a duration."""
    sent, audits = [], []

    async def _never_returns():
        await asyncio.sleep(3600)

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(sched, "_nightly_data_pull", _never_returns)
    monkeypatch.setattr(sched, "_NIGHTLY_PULL_MAX_S", 0.05)
    monkeypatch.setattr(dbmod, "log_audit_event",
                        lambda ev, msg: audits.append((ev, msg)) or asyncio.sleep(0))
    monkeypatch.setattr(sched, "notify_owner", lambda m: sent.append(m) or asyncio.sleep(0))

    with pytest.raises(asyncio.TimeoutError):
        await sched._nightly_data_pull_bounded()

    assert audits and audits[0][0] == "nightly_pull_timeout"
    assert sent, "the operator was not told the pull was cancelled"
    assert "PARTIAL" in audits[0][1] or "partial" in audits[0][1].lower(), (
        "the alert must say the outcome is PARTIAL and unknown — claiming a clean failure is the "
        "same over-claim the stale-run reaper was written to avoid")


@pytest.mark.asyncio
async def test_a_pull_that_finishes_in_time_is_untouched(monkeypatch):
    """The other half — the cap must not change the normal path. Without this, a wrapper that
    always raised would pass every test above."""
    async def _quick():
        return "done"
    monkeypatch.setattr(sched, "_nightly_data_pull", _quick)
    monkeypatch.setattr(sched, "_NIGHTLY_PULL_MAX_S", 30)
    assert await sched._nightly_data_pull_bounded() == "done"


# ── the two seams the first pass ASSERTED but never exercised ─────────────────────────────

@pytest.mark.asyncio
async def test_the_ceiling_reaches_mi_job_runs_as_a_REAL_FAILURE(monkeypatch):
    """Added on advisor review 2026-09-19. The wrapper's own docstring claims the timeout
    "re-raises so `audit_wrap` records the run as a real failure" — and no test went through
    `audit_wrap` at all, so that claim was prose.

    It is not a pedantic gap. `asyncio.wait_for` CANCELS the coroutine it is bounding, and
    `audit_run` treats `CancelledError` and `Exception` completely differently: cancellation
    records status='interrupted' and deliberately declines to say whether the work finished,
    while a real exception records status='failed' and fires `record_job_failure` (the #501
    Telegram path). If the TimeoutError ever arrived as a cancellation instead, the 45-minute
    cap would write the row that means "the process died, outcome unknown" — which is exactly
    the reading 2026-09-18 already had, and the cap would have bought nothing.

    So this exercises the REAL `audit_wrap` over the REAL bounded wrapper and pins the status.
    """
    from core import job_audit

    finishes, failures = [], []

    async def _never_returns():
        await asyncio.sleep(3600)

    import agents.market_intelligence.db as dbmod
    monkeypatch.setattr(sched, "_nightly_data_pull", _never_returns)
    monkeypatch.setattr(sched, "_NIGHTLY_PULL_MAX_S", 0.05)
    monkeypatch.setattr(dbmod, "log_audit_event", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(sched, "notify_owner", lambda m: asyncio.sleep(0))

    async def _start(job_id, expected_min_rows):
        return 4242

    async def _finish(run_id, job_id, started_at, status, rows_written, error_message, **kw):
        finishes.append({"run_id": run_id, "job_id": job_id, "status": status,
                         "error": error_message})

    monkeypatch.setattr(job_audit, "_record_start", _start)
    monkeypatch.setattr(job_audit, "_record_finish", _finish)
    monkeypatch.setattr(job_audit, "record_job_failure",
                        lambda job_id, e: failures.append((job_id, e)) or asyncio.sleep(0))

    wrapped = job_audit.audit_wrap(sched._nightly_data_pull_bounded,
                                   "nightly_data_pull", expected_min_rows=2200)

    with pytest.raises(asyncio.TimeoutError):
        await wrapped()

    assert finishes, "the capped run wrote NO mi_job_runs row — 09-18's exact reading"
    got = finishes[-1]["status"]
    assert got == "failed", (
        f"the 45-minute cap recorded status={got!r}. Only 'failed' means the job is treated as a "
        f"real failure: 'interrupted' says the outcome is unknown (the reading the incident "
        f"already produced) and 'success' would hide it entirely.")
    assert failures, "record_job_failure never fired, so the #501 Telegram path stays silent"


def test_a_miss_that_can_never_be_RECORDED_says_so(monkeypatch, caplog):
    """The absence-shaped failure inside the absence guard, found on advisor review 2026-09-19.

    `_on_job_missed` is sync and schedules its flush with `_missed_loop.create_task`, which is a
    SILENT no-op on a loop that is not running. The first version returned quietly when the
    binding was missing — so a miss would log one WARNING and reach neither `mi_job_runs` nor
    Telegram, which is 2026-09-18's exact reading reproduced inside the guard built to end it.

    MUTATION: restoring the bare `return` reddens the ERROR assertion. Verified RED.
    """
    import logging

    monkeypatch.setattr(sched, "_missed_loop", None)
    sched._missed_buffer.clear()

    class _Ev:
        job_id = "evening_briefing"
        scheduled_run_time = datetime(2026, 9, 18, 17, 30)

    with caplog.at_level(logging.ERROR):
        sched._on_job_missed(_Ev())

    assert sched._missed_buffer, "the miss was not even buffered"
    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "a miss that can never reach mi_job_runs or Telegram was swallowed at WARNING — the "
        "exact shape of failure #672 exists to end")
    sched._missed_buffer.clear()


def test_the_live_call_site_binds_the_RUNNING_loop(monkeypatch):
    """The live binding: whatever `start_scheduler` captures must be the loop that is actually
    running, or `_on_job_missed`'s `create_task` is scheduled where nothing will run it. This
    catches a capture that binds None, a freshly-made loop, or a loop from another thread.

    ⚠ TWO honest limits, both checked rather than assumed (advisor review 2026-09-19):
    - It does NOT discriminate `get_event_loop()` from `get_running_loop()`. Swapping the getter
      back leaves all 9 tests green, because inside a running coroutine `get_event_loop()` returns
      that same running loop. Verified — the mutation was run. `get_running_loop()` is still the
      right call (it raises instead of inventing a loop), but this test is not what holds it.
    - The `except RuntimeError` fallback beside it is unreachable today: `start_scheduler` already
      calls `asyncio.create_task` for the stale-run reaper, so a sync call raises there first.
      Stated, not tested — a test would have to assert on a path that cannot execute."""
    from tests.test_job_partition import _CapturingScheduler
    monkeypatch.setattr(sched, "AsyncIOScheduler", _CapturingScheduler)
    monkeypatch.setattr(sched, "_missed_loop", None)

    async def _go():
        sched.start_scheduler()
        return asyncio.get_running_loop()

    running = asyncio.run(_go())
    assert sched._missed_loop is running, (
        f"bound {sched._missed_loop!r}, but the live loop is {running!r} — create_task on the "
        f"wrong loop is silent")
