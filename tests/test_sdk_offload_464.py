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
