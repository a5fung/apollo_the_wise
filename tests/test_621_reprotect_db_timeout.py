"""#621 — the re-protect-floor DB chain now has a time limit.

THE DEFECT (found 2026-09-04, closed 2026-09-05). `asyncpg.create_pool(...)` in
`db.py::get_pool` sets no `command_timeout`, and nothing in the re-protect-floor
chain — `_trade_advisory_try_lock`, `get_pending_exit_qty`, `_current_stop_pointer`,
`_read_preserved_dead_stop` — bounded its own `pool.acquire()` or query either. A
hung Postgres or a saturated 5-connection pool blocked one of these forever, with
no code-level escape, directly in front of `place_stop_order`
(`_apply_reprotect_floor` -> `alpaca.place_stop_order`). The broker call sitting
right beside these reads WAS already bounded (`alpaca_client._sdk`, 30s/45s) —
this closes the asymmetry on the DB side.

THE FIX. A single module constant, `order_manager._REPROTECT_DB_TIMEOUT` (5.0s),
passed as `timeout=` to `pool.acquire()` and to the query itself (asyncpg's own
per-call bound — NOT an external `asyncio.wait_for` wrapped around a pooled
connection, which can leave a still-running command's connection in a bad state
for the next borrower). Scoped to this chain only, in `order_manager.py`, plus
ONE write in `db.py::log_audit_event` (see its own docstring) — not a pool-wide
`command_timeout`, which would need auditing every `executemany` batch writer
elsewhere in `db.py` to exempt legitimately long ones.

FAIL DIRECTION IS THE WHOLE POINT. `_current_stop_pointer` and
`_read_preserved_dead_stop` already fail open to None on ANY exception (proven
below to include TimeoutError, both from the query itself and from a saturated
`pool.acquire()`) — a timeout must join that SAME path, never a new one that
refuses to place a stop. `get_pending_exit_qty` and `_trade_advisory_try_lock`
are NOT given a new except clause: failing open to 0 pending-exit-qty would
UNDER-count what's already being sold and OVERSIZE the stop request, which is
the FTRE 5/9 class of bug (Alpaca rejects on insufficient qty -> naked) — worse
than the existing raise. Their timeout must propagate exactly like any other DB
error already does.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence.broker import order_manager as om
from tests.conftest import make_mock_pool

TRADE_ID = 9001
DB_PRICE = 12.50


# ══════════════════════════════════════════════════════════════════════════════
# 1. _current_stop_pointer — FAIL-OPEN chain, both failure shapes
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_current_stop_pointer_query_timeout_fails_open_to_none():
    """The query itself hangs past the bound (asyncio.TimeoutError from
    asyncpg's own `timeout=`) -> the existing `except Exception` catches it,
    same as any other DB error -> None, same as before #621."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=asyncio.TimeoutError("query hang"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._current_stop_pointer(TRADE_ID) is None


@pytest.mark.asyncio
async def test_current_stop_pointer_pool_saturation_timeout_fails_open_to_none():
    """The 5-connection pool is saturated -> `pool.acquire(timeout=...)` times
    out BEFORE any query runs -> still caught by the same `except Exception` ->
    None. This is the scenario named in #621: 'the 5-connection pool saturates'."""
    pool, conn = make_mock_pool()
    acquire_cm = pool.acquire.return_value
    acquire_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError("pool saturated"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._current_stop_pointer(TRADE_ID) is None


@pytest.mark.asyncio
async def test_current_stop_pointer_binds_both_acquire_and_query():
    """Pins the bound itself, not just the None — a future refactor that
    silently drops `timeout=` would still return None on a real raise (the
    existing pre-#621 test already proves that) but would NOT actually end a
    hang. Assert the real mechanism is wired."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value="some_order_id")
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        await om._current_stop_pointer(TRADE_ID)
    assert pool.acquire.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT
    assert conn.fetchval.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT


# ══════════════════════════════════════════════════════════════════════════════
# 2. _read_preserved_dead_stop — the #600-fork-2 fallback, same fail-open contract
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_query_timeout_fails_open_to_none():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=asyncio.TimeoutError("query hang"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._read_preserved_dead_stop(TRADE_ID) is None


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_pool_saturation_fails_open_to_none():
    pool, conn = make_mock_pool()
    acquire_cm = pool.acquire.return_value
    acquire_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError("pool saturated"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        assert await om._read_preserved_dead_stop(TRADE_ID) is None


@pytest.mark.asyncio
async def test_read_preserved_dead_stop_binds_both_acquire_and_query():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        await om._read_preserved_dead_stop(TRADE_ID)
    assert pool.acquire.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT
    assert conn.fetchrow.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT


# ══════════════════════════════════════════════════════════════════════════════
# 3. get_pending_exit_qty / _trade_advisory_try_lock — NO new fail-open
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_pending_exit_qty_timeout_propagates_not_fail_open():
    """A timeout must NOT be swallowed into a fake 0 — that would undercount
    pending exits, oversize the stop request, and reproduce the FTRE 5/9 class
    of bug. It must raise, exactly like any other DB error already does."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=asyncio.TimeoutError("query hang"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        with pytest.raises(asyncio.TimeoutError):
            await om.get_pending_exit_qty(TRADE_ID)
    assert pool.acquire.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT
    assert conn.fetchval.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT


@pytest.mark.asyncio
async def test_trade_advisory_try_lock_pool_saturation_propagates():
    """The non-blocking try-lock's OWN `pool.acquire()` (getting a connection to
    run pg_try_advisory_lock on, not the lock itself) is now bounded. A
    saturated pool must still raise -- not silently report 'lock not acquired'
    (which would make the reconciler wrongly defer to a phantom in-flight
    partial) and not silently report 'lock acquired' (which would let the
    reconciler run coverage with concurrent-partial protection believed held
    when it is not)."""
    pool = AsyncMock()
    pool.acquire = AsyncMock(side_effect=asyncio.TimeoutError("pool saturated"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        with pytest.raises(asyncio.TimeoutError):
            async with om._trade_advisory_try_lock(TRADE_ID):
                pass  # pragma: no cover — must not reach here
    assert pool.acquire.call_args.kwargs.get("timeout") == om._REPROTECT_DB_TIMEOUT


@pytest.mark.asyncio
async def test_trade_advisory_lock_blocking_variant_left_unbounded():
    """#621 deliberately does NOT touch `_trade_advisory_lock` (the BLOCKING
    lock `execute_partial_exit` holds) — bounding it would change WHEN a
    partial exit gives up waiting for the lock, which is a safeguard-behaviour
    change (THE LINE), not a hang fix. Pin that its `pool.acquire()` call still
    carries no timeout kwarg."""
    pool, conn = make_mock_pool()
    # _trade_advisory_lock awaits pool.acquire() directly (not the `async with`
    # form make_mock_pool wires) — swap in a plain AsyncMock for this shape.
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        async with om._trade_advisory_lock(TRADE_ID):
            pass
    assert "timeout" not in pool.acquire.call_args.kwargs


# ══════════════════════════════════════════════════════════════════════════════
# 4. End-to-end: a timing-out pointer still results in the stop being placed
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_apply_reprotect_floor_places_at_base_price_when_pointer_read_times_out():
    """THE point of the whole fix. Before #621 this DB read could hang forever
    and `place_stop_order` would never be reached. Now: the read times out in
    bounded time, fails open to None (proven above), and `_apply_reprotect_floor`
    has no broker truth to floor against -> returns `base_price` unchanged,
    the exact pre-#600 placement price. The hang ends; a stop still gets
    placed, never nothing."""
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=asyncio.TimeoutError("db hang"))
    with patch.object(om, "get_pool", AsyncMock(return_value=pool)):
        pointer = await om._current_stop_pointer(TRADE_ID)
        assert pointer is None  # the read timed out and failed open

        price = await om._apply_reprotect_floor(
            TRADE_ID, "IBM", DB_PRICE, pointer, "live",
            site="test_621",
        )
    assert price == DB_PRICE
