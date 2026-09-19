"""`broker/sdk_pool_telemetry.py` — the recorder behind `alpaca_client._sdk` (#664).

The 8-concurrent-call DoD test and the never-throw-into-the-broker-call contract
live beside `_sdk` in `tests/test_sdk_offload_464.py` (they drive the real
wrapper). These test the recorder and the flush on their own: what a rollup
carries, that it stays readable, that a failure is counted and rate-limited
rather than eaten, and that an idle interval writes nothing while a busy one
writes exactly what the DoD reads.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import sdk_pool_telemetry as spt
from agents.market_intelligence.db import _AUDIT_DETAIL_MAX


def _drive(tel: spt.PoolTelemetry, fn, *, timeout=30.0, timed_out=False):
    """One call's full lifecycle, inline (no executor) — the recorder does not
    care which thread calls its hooks, only their order."""
    call = tel.submit(fn, timeout)
    if timed_out:
        tel.mark_timeout(call)
    return tel.run(call, fn)


def test_snapshot_reset_starts_a_new_interval_but_keeps_live_occupancy():
    tel = spt.PoolTelemetry(pool_width=7)
    _drive(tel, lambda: 1)
    _drive(tel, lambda: 2)
    first = tel.snapshot(reset=True)
    assert first["calls"] == 2 and first["max_depth"] == 1 and first["pool_max"] == 7
    assert first["by_fn"]["<lambda>"]["calls"] == 2
    second = tel.snapshot()
    assert second["calls"] == 0 and second["max_depth"] == 0, second
    assert tel.current() == {"running": 0, "pending": 0}


def test_queued_is_decided_against_the_pool_width_at_submit():
    """Seven in flight (never started, so pending) → the eighth submit is queued;
    the seventh is not. `running + pending` BEFORE the call joins is the count."""
    tel = spt.PoolTelemetry(pool_width=7)
    calls = [tel.submit(lambda: None, 30.0) for _ in range(8)]
    assert [c.queued for c in calls] == [False] * 7 + [True]
    snap = tel.snapshot()
    assert snap["queued_calls"] == 1 and snap["max_pending"] == 8 and snap["pending"] == 8


def test_queued_samples_are_capped_and_the_overflow_is_counted():
    tel = spt.PoolTelemetry(pool_width=1)
    tel.submit(lambda: None, 30.0)                     # fills the 1-wide pool
    for _ in range(spt.QUEUED_SAMPLE_CAP + 5):
        tel.submit(lambda: None, 30.0)                 # every one of these is queued
    snap = tel.snapshot()
    assert snap["queued_calls"] == spt.QUEUED_SAMPLE_CAP + 5
    assert len(snap["queued_samples"]) == spt.QUEUED_SAMPLE_CAP
    assert snap["queued_samples_dropped"] == 5


def test_a_full_snapshot_fits_the_audit_detail_budget():
    """A truncated JSON row is the same defect as no row (`db._fit_audit_detail`).
    Fill every bounded structure to its cap with the longest realistic names and
    check the serialised rollup stays under the 8,000-character budget."""
    tel = spt.PoolTelemetry(pool_width=1)
    long_name = "replace_order_by_id_with_a_deliberately_long_name"
    for i in range(spt.BY_FN_CAP + 3):                 # by_fn cap + dropped counter
        fn = (lambda: None)
        fn.__name__ = f"{i:02d}_{long_name}"   # distinct INSIDE the truncated prefix
        _drive(tel, fn, timeout=45.0, timed_out=True)
    holder = tel.submit(lambda: None, 30.0)            # occupy the pool …
    for i in range(spt.QUEUED_SAMPLE_CAP + 2):         # … so these all queue
        fn = (lambda: None)
        fn.__name__ = f"{i:02d}_{long_name}"   # distinct INSIDE the truncated prefix
        _drive(tel, fn, timeout=45.0, timed_out=True)
    tel.run(holder, lambda: None)
    snap = tel.snapshot()
    # 3 named functions past the cap + the holder's own `<lambda>` = 4 dropped
    assert len(snap["by_fn"]) == spt.BY_FN_CAP and snap["by_fn_dropped"] == 4
    assert len(snap["queued_samples"]) == spt.QUEUED_SAMPLE_CAP
    assert all(len(name) <= spt.FN_NAME_MAX for name in snap["by_fn"]), "names are truncated"
    body = json.dumps(snap)
    # margin, not just under: timing digits alone moved the first cut by 40+ chars
    assert len(body) <= 6500 < _AUDIT_DETAIL_MAX, (len(body), _AUDIT_DETAIL_MAX)
    assert json.loads(body)["queued_samples"][0]["timed_out"] is True


def test_timeout_then_thread_end_records_one_overrun():
    tel = spt.PoolTelemetry(pool_width=7)
    call = tel.submit(time.sleep, 0.01)
    tel.mark_timeout(call)                             # caller gave up at 10ms …
    tel.run(call, time.sleep, 0.05)                    # … the thread ran on for 50ms
    snap = tel.snapshot()
    assert snap["timeouts"] == 1 and snap["overruns"] == 1
    assert 0.02 < snap["overrun_max_s"] < 1.0, snap["overrun_max_s"]
    assert tel.current()["running"] == 0


def test_recorder_failure_is_counted_every_time_and_logged_once_a_minute(monkeypatch, caplog):
    """fallback != silent (#381): a broken hook is COUNTED on every call (the
    rollup shows it) and LOGGED at WARNING — but one line a minute, so a fault at
    broker-call rate cannot flood the log. The broker call still returns."""
    tel = spt.PoolTelemetry(pool_width=7)

    def broken(call):
        raise RuntimeError("bookkeeping bug")
    monkeypatch.setattr(tel, "_thread_start", broken)

    with caplog.at_level(logging.WARNING, logger=spt.__name__):
        results = [_drive(tel, lambda: "broker result") for _ in range(5)]
    assert results == ["broker result"] * 5
    snap = tel.snapshot()
    assert snap["record_errors"] == 5, snap
    warnings = [r for r in caplog.records if "bookkeeping bug" in r.getMessage()]
    assert len(warnings) == 1, [r.getMessage() for r in caplog.records]
    assert "thread_start" in warnings[0].getMessage()
    # the live counters did NOT skew: a call whose start hook failed is released by its end hook
    assert tel.current() == {"running": 0, "pending": 0}


def test_pool_width_falls_back_to_the_cpython_formula_off_loop():
    tel = spt.PoolTelemetry()
    assert tel._pool_width() == spt.default_pool_width()
    assert 5 <= spt.default_pool_width() <= 32


def test_pool_width_reads_the_live_executor_on_loop():
    from concurrent.futures import ThreadPoolExecutor
    tel = spt.PoolTelemetry()

    async def main():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=3))
        return tel._pool_width(), tel._executor_backlog()
    width, backlog = asyncio.run(main())
    assert width == 3 and backlog == 0


# ── the flush ──────────────────────────────────────────────────────────────────

def _flush(tel):
    with patch("agents.market_intelligence.db.log_audit_event", new=AsyncMock()) as m:
        result = asyncio.run(spt.flush_to_audit_log(tel))
    return result, m


def test_idle_interval_writes_nothing_and_says_so():
    tel = spt.PoolTelemetry(pool_width=7)
    result, m = _flush(tel)
    assert result == {"written": 0, "reason": "no_calls", "snapshot": result["snapshot"]}
    m.assert_not_called()


def test_busy_interval_writes_one_rollup_row_that_carries_the_dod_fields():
    tel = spt.PoolTelemetry(pool_width=7)
    _drive(tel, lambda: None)
    _drive(tel, lambda: None)
    result, m = _flush(tel)
    assert result["written"] == 1 and result["events"] == ["sdk_pool_rollup"]
    (event, summary, detail), _ = m.call_args
    assert event == "sdk_pool_rollup"
    assert "2 _sdk calls" in summary and "depth max 1 of pool 7" in summary
    row = json.loads(detail)
    for key in ("calls", "max_depth", "pool_max", "queued_calls", "wait_max_ms",
                "wait_hist_ms", "timeouts", "overruns", "overrun_max_s", "record_errors",
                "service_role", "by_fn", "queued_samples", "max_backlog"):
        assert key in row, key
    assert row["calls"] == 2 and row["max_depth"] == 1 and row["pool_max"] == 7
    assert tel.snapshot()["calls"] == 0        # the flush started a new interval


def test_saturated_interval_writes_the_saturated_row_too():
    tel = spt.PoolTelemetry(pool_width=1)
    holder = tel.submit(lambda: None, 30.0)
    _drive(tel, lambda: None)                  # queued behind the holder
    tel.run(holder, lambda: None)
    result, m = _flush(tel)
    assert result["written"] == 2 and result["events"] == ["sdk_pool_rollup", "sdk_pool_saturated"]
    events = [c.args[0] for c in m.call_args_list]
    assert events == ["sdk_pool_rollup", "sdk_pool_saturated"]
    sat = json.loads(m.call_args_list[1].args[2])
    assert sat["queued_calls"] == 1 and len(sat["queued_samples"]) == 1
    assert sat["queued_samples"][0]["fn"] == "<lambda>"


def test_recorder_errors_on_a_quiet_pool_still_write_a_rollup():
    """A recorder failing on a quiet interval is a finding about the recorder;
    it must not hide behind 'no calls'."""
    tel = spt.PoolTelemetry(pool_width=7)
    tel._count_error()
    result, m = _flush(tel)
    assert result["written"] == 1
    assert json.loads(m.call_args.args[2])["record_errors"] == 1


def test_scheduler_job_is_execution_owned_and_registered():
    """The partition check is bidirectional: an execution-owned id must be
    registered unconditionally, and a registered job must be classified."""
    from agents.market_intelligence import scheduler as sched
    assert "sdk_pool_rollup" in sched.EXECUTION_OWNED_JOB_IDS
    assert "sdk_pool_rollup" not in sched.INTELLIGENCE_OWNED_JOB_IDS
    import inspect
    assert inspect.iscoroutinefunction(sched._sdk_pool_rollup_job)


def test_scheduler_job_flushes_and_survives_a_flush_failure(caplog):
    from agents.market_intelligence import scheduler as sched
    with patch("agents.market_intelligence.broker.sdk_pool_telemetry.flush_to_audit_log",
               new=AsyncMock(return_value={"written": 1})) as ok:
        asyncio.run(sched._sdk_pool_rollup_job())
    ok.assert_awaited_once()
    with patch("agents.market_intelligence.broker.sdk_pool_telemetry.flush_to_audit_log",
               new=AsyncMock(side_effect=RuntimeError("db down"))), \
            caplog.at_level(logging.ERROR):
        asyncio.run(sched._sdk_pool_rollup_job())      # must not raise into the scheduler
    assert any("sdk_pool_rollup failed" in r.getMessage() and "db down" in r.getMessage()
               for r in caplog.records)
