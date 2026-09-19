"""#664 — how deep is the thread pool every broker call borrows from?

`alpaca_client._sdk()` is `asyncio.wait_for(asyncio.to_thread(fn))`, so EVERY
broker call — read and write — takes a thread from the event loop's DEFAULT
executor. That pool is `min(32, cpus + 4)` wide (SEVEN on apollo-execution's
3 CPUs) and is shared with every other `to_thread` caller in the process. Seven
concurrent hangs would make `submit_order` for a STOP queue behind them instead
of failing fast, and a queued stop is indistinguishable from a slow one at the
call site. Until this module nothing measured the depth; the ceiling was argued
from `min(32, cpus + 4)` and the distribution was unknown.

WHAT IS RECORDED, per call, in memory (no I/O on the call path — ever):
  * `wait_ms`   — time from `_sdk` entry to the moment a worker thread actually
                  starts `fn`. Measured ON THE WORKER THREAD, so it is the real
                  slot wait, not a loop-side guess.
  * `queued`    — at submit, `running + pending >= pool width`: this call had no
                  free slot and HAD to wait. An idle pool still shows ~0.1 ms of
                  thread handoff, so "nonzero wait" alone does not discriminate;
                  `queued` does.
  * `depth`     — how many `_sdk` calls were executing on threads when this one
                  started (itself included). Its maximum is stated against the
                  pool width in every rollup.
  * `backlog`   — the executor's own work-queue size at submit (guarded read of
                  a CPython private; `None` when unavailable). Every `to_thread`
                  user in the process shares that queue, so this is the only
                  cross-user signal: `alpaca_client.get_minute_bars_range`,
                  `bar_stream`, `twitter`, `earnings_calendar`, `correlation_engine`
                  all bypass `_sdk` and are invisible to `depth`.
  * `overrun_s` — for a call whose CALLER timed out (`wait_for` budget hit): how
                  long the worker thread kept its slot PAST the budget. The
                  timeout releases the caller, never the thread — and alpaca-py's
                  REST client (`alpaca/common/rest.py`) passes NO HTTP timeout to
                  `requests`, so a hung socket holds a slot until TCP gives up.
                  This number, not depth, is what decides whether the money path
                  deserves its own executor. ⚖ Deciding that is the operator's
                  (THE LINE); this module only measures.

WHAT IS NOT DONE HERE — deliberately:
  * No timeout, executor or call-path change. `_sdk`'s shape is unchanged; the
    recorder is the `fn` argument to `to_thread`, nothing more.
  * No lock that could serialise concurrent calls. One `threading.Lock` guards
    integer counter updates for nanoseconds; the broker call runs outside it.
  * No DB write on the call path. `flush_to_audit_log()` (driven by the
    `sdk_pool_rollup` scheduler job, every 5 minutes) turns the in-memory
    interval into ONE `mi_audit_log` row, plus a `sdk_pool_saturated` row when
    any call in the interval had to wait for a slot.
  * The recorder CANNOT throw into the broker call: every hook runs under
    `_safe`, which counts the failure (`record_errors`, reported in every
    rollup) and logs it at WARNING (rate-limited to one line a minute). A
    rollup carrying `record_errors > 0` is a defect in THIS module, and a
    rollup that never appears during market hours is a dead recorder, not a
    quiet pool — `position_coverage_check` calls the broker every 15 minutes
    09:31-15:55 ET, so every market-hours interval has calls to report.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# Wait-time histogram edges (ms, upper bound exclusive) → bucket label. Fixed
# buckets keep the recorder O(1) in memory however many calls an interval sees.
_WAIT_BUCKETS_MS: tuple[tuple[float, str], ...] = (
    (1, "<1"), (5, "1-5"), (50, "5-50"), (250, "50-250"),
    (1000, "250-1000"), (5000, "1000-5000"), (float("inf"), ">=5000"),
)
# Bounds chosen so a FULL snapshot (every cap hit, every name at its longest)
# serialises with margin under the 8,000-character `mi_audit_log.detail` budget
# (`db._fit_audit_detail`) — pinned by a test at <= 6,500. A truncated JSON row
# is the same defect as no row. The first cut (20 samples, untruncated names)
# measured 8,043: over the budget by timing digits alone.
QUEUED_SAMPLE_CAP = 12
BY_FN_CAP = 32
FN_NAME_MAX = 32   # alpaca-py's longest method here is 22 chars; anything longer is not one
_WARN_EVERY_S = 60.0


def default_pool_width() -> int:
    """CPython's default-executor width: `min(32, cpus + 4)` (3.8+; 3.13 counts
    the process's usable CPUs). The formula is the fallback — a live loop's
    executor is read directly when it exists."""
    counter = getattr(os, "process_cpu_count", None)
    cpus = (counter() if counter is not None else None) or os.cpu_count() or 1
    return min(32, cpus + 4)


class _Call:
    """One `_sdk` call's timeline. Loop side writes `t_submit`/`queued`/`backlog`
    and `timed_out`; the worker thread writes the rest."""
    __slots__ = ("fn", "timeout", "t_submit", "t_start", "t_end", "wall_start",
                 "wait_ms", "depth", "queued", "backlog", "timed_out",
                 "counted_pending", "counted_running")

    def __init__(self) -> None:
        self.fn = "?"
        self.timeout = 0.0
        self.t_submit = time.monotonic()
        self.t_start = None
        self.t_end = None
        self.wall_start = None
        self.wait_ms = None
        self.depth = None
        self.queued = False
        self.backlog = None
        self.timed_out = False
        # Which LIVE counter this call currently occupies. The counters move
        # FIRST inside each locked block and the flags move with them, so a hook
        # that fails half-way (or a hook that never ran) can never leave
        # `running`/`pending` skewed for the life of the process — found by the
        # recorder-failure test: one failed start hook drove `running` to -1
        # permanently, which would have broken `queued` detection for good.
        self.counted_pending = False
        self.counted_running = False

    def as_sample(self) -> dict:
        run_ms = None
        if self.t_start is not None and self.t_end is not None:
            run_ms = round((self.t_end - self.t_start) * 1000.0, 1)
        t_et = None
        if self.wall_start is not None:
            t_et = datetime.fromtimestamp(self.wall_start, _ET).isoformat(timespec="milliseconds")
        return {
            "t_et": t_et,
            "fn": self.fn,
            "wait_ms": None if self.wait_ms is None else round(self.wait_ms, 1),
            "depth": self.depth,
            "backlog": self.backlog,
            "timeout_s": self.timeout,
            "timed_out": self.timed_out,
            "run_ms": run_ms,
        }


def _fn_name(fn) -> str:
    name = getattr(fn, "__name__", None)
    if not (isinstance(name, str) and name):
        name = type(fn).__name__
    return name[:FN_NAME_MAX]


class PoolTelemetry:
    """In-memory recorder for `_sdk` slot waits and depth. Thread-safe; every
    public hook is guarded so a recorder bug can never reach the broker call."""

    def __init__(self, pool_width: int | None = None) -> None:
        self._lock = threading.Lock()
        self._pool_width_override = pool_width
        # LIVE state — survives `snapshot(reset=True)`; these are not interval stats.
        self._running = 0
        self._pending = 0
        self._last_warn_mono = 0.0
        # The width the LAST submit saw. A snapshot can be taken off-loop (a
        # test, an ops script) where the live executor is unreadable; reporting
        # the formula there would misstate the pool the calls actually ran in.
        self._pool_width_seen: int | None = None
        self._reset_locked()

    # ── interval stats ────────────────────────────────────────────────────────

    def _reset_locked(self) -> None:
        self._t_reset = time.monotonic()
        self._calls = 0
        self._queued_calls = 0
        self._max_depth = 0
        self._max_pending = 0
        self._max_backlog = 0
        self._wait_max_ms = 0.0
        self._wait_sum_ms = 0.0
        self._wait_hist = {label: 0 for _, label in _WAIT_BUCKETS_MS}
        self._run_max_ms = 0.0
        self._timeouts = 0
        self._overruns = 0
        self._overrun_max_s = 0.0
        self._by_fn: dict[str, dict] = {}
        self._by_fn_dropped = 0
        self._queued_samples: list[_Call] = []
        self._queued_samples_dropped = 0
        self._record_errors = 0

    # ── executor introspection (guarded CPython privates) ─────────────────────

    def _executor(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # not on a loop thread (tests, snapshot from a job)
            return None
        return getattr(loop, "_default_executor", None)

    def _pool_width(self) -> int:
        if self._pool_width_override:
            return self._pool_width_override
        width = getattr(self._executor(), "_max_workers", None)
        if isinstance(width, int) and width > 0:
            return width
        return default_pool_width()

    def _executor_backlog(self) -> int | None:
        queue = getattr(self._executor(), "_work_queue", None)
        qsize = getattr(queue, "qsize", None)
        return int(qsize()) if callable(qsize) else None

    # ── the never-throw guard ─────────────────────────────────────────────────

    def _count_error(self) -> int:
        """A recorder failure is ALWAYS counted (`record_errors` surfaces in every
        rollup). Returns the running count when a WARNING line is due — at most
        one a minute, so a broken hook cannot flood the log at broker-call rate —
        and 0 when the failure was counted but this line is rate-limited."""
        now = time.monotonic()
        with self._lock:
            self._record_errors += 1
            if (now - self._last_warn_mono) >= _WARN_EVERY_S:
                self._last_warn_mono = now
                return self._record_errors
        return 0

    def _safe(self, hook, call: _Call, where: str) -> None:
        try:
            hook(call)
        except Exception as e:
            if n := self._count_error():
                logger.warning(f"sdk_pool_telemetry recorder failed in {where} (#{n} this "
                               f"interval; the broker call itself is unaffected): {e!r}")

    # ── loop side ─────────────────────────────────────────────────────────────

    def submit(self, fn, timeout: float) -> _Call:
        """Called on the loop thread as `_sdk` is entered, BEFORE the executor
        submission. Returns the call token; never raises."""
        call = _Call()
        try:
            call.fn = _fn_name(fn)
            call.timeout = float(timeout)
            width = self._pool_width()
            backlog = self._executor_backlog()
            with self._lock:
                self._pending += 1
                call.counted_pending = True
                self._pool_width_seen = width
                # `>= width` against the count BEFORE this call joined
                call.queued = (self._running + self._pending - 1) >= width
                call.backlog = backlog
                self._calls += 1
                if self._pending > self._max_pending:
                    self._max_pending = self._pending
                if backlog is not None and backlog > self._max_backlog:
                    self._max_backlog = backlog
                if call.queued:
                    self._queued_calls += 1
                    if len(self._queued_samples) < QUEUED_SAMPLE_CAP:
                        self._queued_samples.append(call)
                    else:
                        self._queued_samples_dropped += 1
        except Exception as e:
            if n := self._count_error():
                logger.warning(f"sdk_pool_telemetry recorder failed in submit (#{n} this "
                               f"interval; the broker call itself is unaffected): {e!r}")
        return call

    def mark_timeout(self, call: _Call) -> None:
        """The CALLER's `wait_for` budget expired. The worker thread is still
        holding its slot — `_thread_end` will record the overrun when it returns."""
        try:
            with self._lock:
                self._timeouts += 1
                call.timed_out = True
        except Exception as e:
            if n := self._count_error():
                logger.warning(f"sdk_pool_telemetry recorder failed in mark_timeout (#{n} this "
                               f"interval; the broker call itself is unaffected): {e!r}")

    # ── worker-thread side ────────────────────────────────────────────────────

    def run(self, call: _Call, fn, /, *args, **kwargs):
        """The `fn` argument `_sdk` hands to `to_thread`. Runs ON the worker
        thread: bookkeeping around the real call, which is passed through with
        its arguments, return value and exceptions untouched. Positional-only
        leading parameters so a forwarded kwarg can never collide with them."""
        self._safe(self._thread_start, call, "thread_start")
        try:
            return fn(*args, **kwargs)
        finally:
            self._safe(self._thread_end, call, "thread_end")

    def _thread_start(self, call: _Call) -> None:
        now = time.monotonic()
        call.t_start = now
        call.wall_start = time.time()
        wait_ms = (now - call.t_submit) * 1000.0
        call.wait_ms = wait_ms
        for edge, label in _WAIT_BUCKETS_MS:
            if wait_ms < edge:
                bucket = label
                break
        with self._lock:
            if call.counted_pending:
                self._pending -= 1
                call.counted_pending = False
            self._running += 1
            call.counted_running = True
            call.depth = self._running
            if self._running > self._max_depth:
                self._max_depth = self._running
            self._wait_hist[bucket] += 1
            self._wait_sum_ms += wait_ms
            if wait_ms > self._wait_max_ms:
                self._wait_max_ms = wait_ms
            per = self._by_fn.get(call.fn)
            if per is None:
                if len(self._by_fn) < BY_FN_CAP:
                    per = self._by_fn[call.fn] = {"calls": 0, "wait_max_ms": 0.0, "run_max_ms": 0.0}
                else:
                    self._by_fn_dropped += 1
            if per is not None:
                per["calls"] += 1
                if wait_ms > per["wait_max_ms"]:
                    per["wait_max_ms"] = wait_ms

    def _thread_end(self, call: _Call) -> None:
        now = time.monotonic()
        call.t_end = now
        run_ms = (now - (call.t_start if call.t_start is not None else now)) * 1000.0
        with self._lock:
            if call.counted_running:
                self._running -= 1
                call.counted_running = False
            elif call.counted_pending:   # the start hook never moved it
                self._pending -= 1
                call.counted_pending = False
            if run_ms > self._run_max_ms:
                self._run_max_ms = run_ms
            per = self._by_fn.get(call.fn)
            if per is not None and run_ms > per["run_max_ms"]:
                per["run_max_ms"] = run_ms
            if call.timed_out:
                self._overruns += 1
                overrun_s = (now - call.t_submit) - call.timeout
                if overrun_s > self._overrun_max_s:
                    self._overrun_max_s = overrun_s

    # ── read side ─────────────────────────────────────────────────────────────

    def current(self) -> dict:
        """Live occupancy right now (not interval stats)."""
        with self._lock:
            return {"running": self._running, "pending": self._pending}

    def snapshot(self, reset: bool = False) -> dict:
        """The interval's stats as a JSON-ready dict; `reset=True` starts a new
        interval (live `running`/`pending` are NOT reset — they are state)."""
        try:
            from agents.market_intelligence.constants import SERVICE_ROLE
        except ImportError:  # module usable standalone (tests, ops scripts)
            SERVICE_ROLE = "unknown"
        with self._lock:
            calls = self._calls
            pool_max = self._pool_width_seen or self._pool_width()
            snap = {
                "service_role": SERVICE_ROLE,
                "pool_max": pool_max,
                "interval_s": round(time.monotonic() - self._t_reset, 1),
                "calls": calls,
                "queued_calls": self._queued_calls,
                "max_depth": self._max_depth,
                "max_pending": self._max_pending,
                "max_backlog": self._max_backlog,
                "wait_max_ms": round(self._wait_max_ms, 1),
                "wait_mean_ms": round(self._wait_sum_ms / calls, 2) if calls else 0.0,
                "wait_hist_ms": dict(self._wait_hist),
                "run_max_ms": round(self._run_max_ms, 1),
                "timeouts": self._timeouts,
                "overruns": self._overruns,
                "overrun_max_s": round(self._overrun_max_s, 2),
                "by_fn": {
                    name: {"calls": p["calls"],
                           "wait_max_ms": round(p["wait_max_ms"], 1),
                           "run_max_ms": round(p["run_max_ms"], 1)}
                    for name, p in sorted(self._by_fn.items())
                },
                "by_fn_dropped": self._by_fn_dropped,
                "queued_samples": [c.as_sample() for c in self._queued_samples],
                "queued_samples_dropped": self._queued_samples_dropped,
                "record_errors": self._record_errors,
                "running": self._running,
                "pending": self._pending,
            }
            if reset:
                self._reset_locked()
        return snap


# The ONE recorder for the process. `alpaca_client._sdk` records into it; the
# `sdk_pool_rollup` scheduler job flushes it. Each service role runs its own
# process with its own default executor, so each has its own numbers
# (`service_role` is stamped on every row).
TELEMETRY = PoolTelemetry()


def summarize(snap: dict) -> str:
    """One plain line for the audit `summary` column."""
    return (
        f"{snap['service_role']}: {snap['calls']} _sdk calls in {snap['interval_s']:.0f}s — "
        f"depth max {snap['max_depth']} of pool {snap['pool_max']}, "
        f"{snap['queued_calls']} waited for a slot (wait max {snap['wait_max_ms']:.0f}ms), "
        f"{snap['timeouts']} caller timeouts, {snap['overruns']} threads outlived their "
        f"budget (max {snap['overrun_max_s']:.1f}s past it), recorder errors {snap['record_errors']}"
    )


async def flush_to_audit_log(telemetry: PoolTelemetry | None = None) -> dict:
    """Turn the interval since the last flush into `mi_audit_log` rows.

    Writes `sdk_pool_rollup` when the interval saw any call OR any recorder error
    (a recorder failing on a quiet pool is still a finding), and additionally
    `sdk_pool_saturated` when at least one call had to wait for a slot. Writes
    NOTHING for a genuinely idle interval — during market hours that cannot
    happen (the 15-minute coverage detector calls the broker), so a missing
    market-hours row means the recorder or the job is dead, never a quiet pool.
    Returns what it did so the caller (and tests) can tell the two apart.
    """
    tel = telemetry if telemetry is not None else TELEMETRY
    snap = tel.snapshot(reset=True)
    if snap["calls"] == 0 and snap["record_errors"] == 0:
        return {"written": 0, "reason": "no_calls", "snapshot": snap}
    from agents.market_intelligence.audit_events import SDK_POOL_ROLLUP, SDK_POOL_SATURATED
    from agents.market_intelligence.db import log_audit_event
    written = [SDK_POOL_ROLLUP]
    await log_audit_event(SDK_POOL_ROLLUP, summarize(snap), json.dumps(snap))
    if snap["queued_calls"] > 0:
        await log_audit_event(
            SDK_POOL_SATURATED,
            f"{snap['service_role']}: {snap['queued_calls']} of {snap['calls']} _sdk calls had NO "
            f"free thread and waited (max {snap['wait_max_ms']:.0f}ms) — pool {snap['pool_max']}, "
            f"depth max {snap['max_depth']}, executor backlog max {snap['max_backlog']}",
            json.dumps({
                "pool_max": snap["pool_max"],
                "max_depth": snap["max_depth"],
                "max_backlog": snap["max_backlog"],
                "queued_calls": snap["queued_calls"],
                "queued_samples": snap["queued_samples"],
                "queued_samples_dropped": snap["queued_samples_dropped"],
            }),
        )
        written.append(SDK_POOL_SATURATED)
    return {"written": len(written), "events": written, "snapshot": snap}
