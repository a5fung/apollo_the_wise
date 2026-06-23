"""#151 REAL-POSTGRES cross-connection advisory-lock serialization test.

THIS is the test that proves topology-robustness. The asyncio-unit tests prove
nothing about cross-PROCESS safety because an asyncio.Lock is per-process and the
production split runs execute_partial_exit and _ensure_stop_coverage in DIFFERENT
processes (EXECUTION_MODE=http). A Postgres *advisory* lock is the only mechanism
that serializes them, and the only way to verify that is against a real Postgres.

Run it against the test/prod DB by setting APOLLO_TEST_DSN, e.g.:

    APOLLO_TEST_DSN="postgresql://user:pass@host:5432/apollo" \
        python -m pytest tests/test_advisory_lock_real_pg.py -v

Without that env var the test SKIPS (it must NOT be faked with mocks — a mock
would assert nothing about the real `pg_try_advisory_lock` semantics). This is
the gate the operator runs before any un-pause: it must PASS against the same
Postgres the live system uses.

What it proves (the exact partial-vs-reconciler contract):
  * Connection A acquires pg_advisory_lock(ns, trade_id)  — the partial holds it.
  * Connection B's pg_try_advisory_lock(ns, trade_id) returns FALSE — the
    reconciler defers (it would SKIP _ensure_stop_coverage).
  * A unlocks.
  * B's pg_try_advisory_lock now returns TRUE — coverage may proceed.
These are SEPARATE sessions (independent asyncpg.connect), modelling the two
processes; a same-session re-lock would (mis)succeed, so we deliberately use two
connections.
"""
import os

import pytest

# The namespace constant MUST match the one the production code uses, or the test
# would be locking a different key than the code under test.
from agents.market_intelligence.broker.order_manager import _TRADE_LOCK_NAMESPACE

_DSN = os.environ.get("APOLLO_TEST_DSN")
_TRADE_ID = 9_990_001  # arbitrary, unlikely to collide with a real trade lock

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="real-PG advisory-lock gate: set APOLLO_TEST_DSN to run "
           "(must run against the test/prod DB before any partial-exit un-pause)",
)


@pytest.mark.asyncio
async def test_advisory_lock_serializes_across_two_connections():
    import asyncpg

    ns = _TRADE_LOCK_NAMESPACE
    conn_a = await asyncpg.connect(_DSN)
    conn_b = await asyncpg.connect(_DSN)
    try:
        # Clean slate: make sure neither holds the lock from a prior aborted run.
        await conn_a.fetchval("SELECT pg_advisory_unlock_all()")
        await conn_b.fetchval("SELECT pg_advisory_unlock_all()")

        # A (the partial) takes the blocking lock.
        await conn_a.fetchval("SELECT pg_advisory_lock($1, $2)", ns, _TRADE_ID)

        # B (the reconciler) tries — must FAIL (lock held by a DIFFERENT session).
        got_b = await conn_b.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)", ns, _TRADE_ID
        )
        assert got_b is False, (
            "pg_try_advisory_lock must return FALSE while another connection "
            "holds the lock — this is what makes _ensure_stop_coverage SKIP a "
            "trade with a partial in-flight"
        )

        # A (the partial) finishes and unlocks.
        unlocked = await conn_a.fetchval(
            "SELECT pg_advisory_unlock($1, $2)", ns, _TRADE_ID
        )
        assert unlocked is True

        # B now succeeds — coverage may proceed once the partial released.
        got_b2 = await conn_b.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)", ns, _TRADE_ID
        )
        assert got_b2 is True, (
            "after the holder unlocks, the try-lock must succeed — the reconciler "
            "is free to repair coverage"
        )
        # Release B's lock so we leave the DB clean.
        await conn_b.fetchval("SELECT pg_advisory_unlock($1, $2)", ns, _TRADE_ID)
    finally:
        await conn_a.close()
        await conn_b.close()


@pytest.mark.asyncio
async def test_session_lock_auto_released_on_connection_close():
    """Session-level locks auto-release when the holding connection closes — the
    backstop if a process dies mid-hold. Prove it: A locks, A closes (no explicit
    unlock), a fresh connection C can then acquire."""
    import asyncpg

    ns = _TRADE_LOCK_NAMESPACE
    conn_a = await asyncpg.connect(_DSN)
    await conn_a.fetchval("SELECT pg_advisory_unlock_all()")
    await conn_a.fetchval("SELECT pg_advisory_lock($1, $2)", ns, _TRADE_ID + 1)
    await conn_a.close()  # die mid-hold, no explicit unlock

    conn_c = await asyncpg.connect(_DSN)
    try:
        got = await conn_c.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)", ns, _TRADE_ID + 1
        )
        assert got is True, (
            "session-level advisory lock must auto-release when the holding "
            "connection closes (the dead-process backstop)"
        )
        await conn_c.fetchval("SELECT pg_advisory_unlock($1, $2)", ns, _TRADE_ID + 1)
    finally:
        await conn_c.close()
