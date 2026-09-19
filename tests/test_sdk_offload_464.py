"""#464 — blocking alpaca-py calls must not run on the event loop.

alpaca-py's clients are SYNCHRONOUS network I/O. Called bare inside `async def`, a
hung Alpaca endpoint freezes the ENTIRE loop: WebSocket fill handling, every
scheduled job, and the order-status reconcile that exists to catch exactly that.
Latent since day one (money-path audit R3, 2026-07-12).
"""
import ast
import asyncio
import pathlib
import re

import pytest

SRC_PATH = pathlib.Path("agents/market_intelligence/broker/alpaca_client.py")
SRC = SRC_PATH.read_text()

# Every SDK method that performs network I/O. A bare call to any of these inside an
# `async def` blocks the loop.
BLOCKING = (
    "submit_order", "get_account", "get_order_by_id", "get_orders",
    "cancel_order_by_id", "replace_order_by_id", "get_all_positions",
    "get_open_position", "close_position", "get_stock_bars",
    "get_stock_latest_trade",
)


def test_no_blocking_sdk_call_runs_on_the_event_loop():
    """THE guard. Fails on the next bare `client.<blocking>()` anyone adds."""
    # Strip comments and docstrings first: one docstring EXPLAINS the hazard by
    # quoting a bare bar-fetch call, and a guard that flags prose is a guard
    # people learn to ignore.
    code = "\n".join(
        (ln.split("#", 1)[0] if "#" in ln else ln) for ln in SRC.splitlines())
    code = re.sub(""" + r"(?:.|\n)*?" + """, "", code)
    offenders = []
    for m in re.finditer(r"client\.(\w+)\s*\(", code):
        name = m.group(1)
        if name not in BLOCKING:
            continue
        # the call must be an argument to _sdk / to_thread, not invoked directly
        window = code[max(0, m.start() - 90):m.start()]
        if "_sdk(" in window or "to_thread(" in window:
            continue
        line = code[:m.start()].count("\n") + 1
        offenders.append(f"{SRC_PATH}:{line} client.{name}(")
    assert not offenders, (
        "blocking SDK call(s) not offloaded — a hung endpoint would freeze the "
        f"event loop:\n  " + "\n  ".join(offenders))


def test_sdk_helper_bounds_the_call():
    """Offloading alone is not enough — an un-bounded thread still leaks a worker
    and never returns to the caller. The timeout is what makes it a hang BREAKER."""
    fn = next(n for n in ast.walk(ast.parse(SRC))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_sdk")
    body = ast.get_source_segment(SRC, fn)
    assert "asyncio.wait_for" in body and "asyncio.to_thread" in body


def test_timeout_surfaces_as_an_exception_not_a_hang():
    """BEHAVIOURAL. Every call site is already inside try/except returning a failure
    sentinel, so a timeout must degrade to the same path as any other API error."""
    import importlib
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")

    def slow():
        import time
        time.sleep(5)

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        asyncio.run(ac._sdk(slow, timeout=0.05))


def test_offload_preserves_ordering_within_a_coroutine():
    """The safety case for to_thread: it does NOT reorder awaits inside a coroutine,
    so read-modify-write sequences keep their order. What changes is that OTHER
    tasks may interleave — which is the point, and the DB side is already guarded by
    the #151 per-trade advisory locks."""
    import importlib
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    seen = []

    async def seq():
        for i in range(5):
            await ac._sdk(lambda n=i: seen.append(n))
    asyncio.run(seq())
    assert seen == [0, 1, 2, 3, 4]


# ── #664 — the pool is SEVEN threads wide and nothing measured its depth ────────
# `_sdk` borrows a thread from the loop's DEFAULT executor (min(32, cpus+4) = 7 on
# apollo-execution's 3 CPUs), shared with every other `to_thread` caller in the
# process. Seven concurrent hangs would make a STOP placement queue rather than
# fail fast, and a queued stop is indistinguishable from a slow one at the call
# site. These tests pin the instrumentation that makes the depth measurable.
# Instrumentation ONLY: no timeout, executor or call-path change (THE LINE).

def _run_with_pool(coro_fn, workers: int):
    """Run `coro_fn()` on a fresh loop whose DEFAULT executor is `workers` wide —
    the test-side stand-in for the container's 7. `ex.shutdown(wait=True)` also
    joins any thread that outlived a timed-out caller, so thread-side bookkeeping
    is complete before the caller inspects it."""
    from concurrent.futures import ThreadPoolExecutor

    async def main():
        loop = asyncio.get_running_loop()
        ex = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="t664")
        loop.set_default_executor(ex)
        try:
            return await coro_fn()
        finally:
            ex.shutdown(wait=True)
    return asyncio.run(main())


def _telemetry(ac):
    tel = ac._pool_telemetry
    tel.snapshot(reset=True)  # clean slate — other tests in this file drive _sdk too
    return tel


def test_eighth_concurrent_call_records_a_nonzero_slot_wait():
    """THE DoD test (#664). Eight simultaneous `_sdk` calls into a 7-thread pool:
    the first seven get a thread at once, the eighth must WAIT for a slot, and the
    recorder must say so — as a `queued` call with a wait about as long as one
    hold, not as a 0 or a null. An idle pool still shows ~0.1 ms of thread handoff,
    so `queued` (running+pending >= pool width at submit) is the discriminating
    signal, not "nonzero" alone. max_depth is the POOL's 7, never the callers' 8."""
    import importlib
    import time
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    tel = _telemetry(ac)

    def hold():
        time.sleep(0.3)

    async def drive():
        await asyncio.gather(*[ac._sdk(hold) for _ in range(8)])

    _run_with_pool(drive, 7)
    snap = tel.snapshot(reset=True)
    assert snap["calls"] == 8, snap
    assert snap["pool_max"] == 7, snap
    assert snap["max_depth"] == 7, snap          # the pool, not the callers
    assert snap["queued_calls"] == 1, snap        # exactly the eighth
    assert len(snap["queued_samples"]) == 1, snap
    eighth = snap["queued_samples"][0]
    assert eighth["wait_ms"] >= 200, eighth        # waited ~one full hold
    assert eighth["fn"] == "hold", eighth
    assert snap["wait_max_ms"] == eighth["wait_ms"], snap
    # the seven direct handoffs did NOT wait: they all land in the sub-50ms buckets
    direct = snap["wait_hist_ms"]["<1"] + snap["wait_hist_ms"]["1-5"] + snap["wait_hist_ms"]["5-50"]
    assert direct == 7, snap["wait_hist_ms"]
    assert snap["record_errors"] == 0, snap
    assert snap["timeouts"] == 0 and snap["overruns"] == 0, snap


def test_seven_concurrent_calls_do_not_queue():
    """The control for the test above: with the pool exactly full nothing waits, so
    a `queued` reading is a real saturation signal and not a constant artefact."""
    import importlib
    import time
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    tel = _telemetry(ac)

    async def drive():
        await asyncio.gather(*[ac._sdk(time.sleep, 0.2) for _ in range(7)])

    _run_with_pool(drive, 7)
    snap = tel.snapshot(reset=True)
    assert snap["calls"] == 7 and snap["max_depth"] == 7, snap
    assert snap["queued_calls"] == 0 and snap["queued_samples"] == [], snap


def test_recorder_failure_cannot_break_the_broker_call(monkeypatch, caplog):
    """LIVE-PATH contract: if recording fails, the broker call still happens and
    returns its own value. The failure is NOT swallowed silently — it is counted
    and logged (a recorder that eats its own failure is where bugs hide longest)."""
    import importlib
    import logging
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    tel = _telemetry(ac)

    def boom(call):
        raise RuntimeError("recorder bug")
    monkeypatch.setattr(tel, "_thread_start", boom)
    monkeypatch.setattr(tel, "_last_warn_mono", 0.0)

    with caplog.at_level(logging.WARNING):
        assert _run_with_pool(lambda: ac._sdk(lambda: 42), 7) == 42
    snap = tel.snapshot(reset=True)
    assert snap["record_errors"] >= 1, snap
    assert any("sdk_pool_telemetry" in r.getMessage() and "recorder bug" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]


def test_fn_exception_propagates_unchanged_and_depth_returns_to_zero():
    import importlib
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    tel = _telemetry(ac)

    def raiser():
        raise ValueError("broker said no")

    with pytest.raises(ValueError, match="broker said no"):
        _run_with_pool(lambda: ac._sdk(raiser), 7)
    live = tel.current()
    assert live["running"] == 0 and live["pending"] == 0, live
    assert tel.snapshot(reset=True)["calls"] == 1


def test_timeout_releases_the_caller_but_the_thread_keeps_its_slot():
    """The occupancy the task is about: `wait_for` frees the CALLER at the budget,
    the worker thread keeps running (a slot is held until the SDK call returns —
    alpaca-py sets no HTTP timeout). Recorded as an OVERRUN, never a decrement."""
    import importlib
    import time
    ac = importlib.import_module("agents.market_intelligence.broker.alpaca_client")
    tel = _telemetry(ac)

    async def drive():
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await ac._sdk(time.sleep, 0.3, timeout=0.05)
        live = tel.current()
        assert live["running"] == 1, live   # caller is gone, the slot is not

    _run_with_pool(drive, 7)   # shutdown(wait=True) joins the thread
    snap = tel.snapshot(reset=True)
    assert snap["timeouts"] == 1 and snap["overruns"] == 1, snap
    assert snap["overrun_max_s"] > 0.1, snap
    assert tel.current()["running"] == 0
