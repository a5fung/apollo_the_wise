"""#461 REAL-POSTGRES per-mode cap-lock serialization test (sibling of the
#151 gate in `tests/test_advisory_lock_real_pg.py`).

The asyncio race tests (`tests/test_461_cap_toctou_race.py`) prove the STEP-6
recheck logic over a fake lock; only a real Postgres proves the mechanism the
fix actually leans on — `pg_advisory_xact_lock` blocking a DIFFERENT
connection/session (the cross-process case, EXECUTION_MODE=http), the
hashtext(account_mode) keying, and the commit-before-release ordering that
guarantees the next waiter's recount sees the previous holder's committed row.

Run against the test/prod DB:

    APOLLO_TEST_DSN="postgresql://user:pass@host:5432/apollo" \
        python -m pytest tests/test_461_cap_lock_real_pg.py -v

Without the env var the tests SKIP (must NOT be faked with mocks). Row-writing
uses a SYNTHETIC account_mode ('t461') that no real paper/live count ever
selects (every cap query filters account_mode), and deletes its rows in
`finally` — the prod tables are never left dirty and no real cap slot is ever
touched. Lock keys are ephemeral (xact-scoped), so taking the real 'live' /
'paper' keys for the isolation assertion is harmless.
"""
import asyncio
import os
from datetime import date

import pytest

# Must be the SAME constants/SQL the production code uses, or we'd be testing
# a different lock key / count than the code under test.
from agents.market_intelligence.broker.entry_pipeline import _CAP_LOCK_NAMESPACE
from agents.market_intelligence.broker.live_tracker import count_open_positions

_DSN = os.environ.get("APOLLO_TEST_DSN")
_MODE = "t461"          # synthetic mode: invisible to every real cap count
_TICKER = "ZZT461"      # synthetic ticker, deleted in finally

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="real-PG cap-lock gate: set APOLLO_TEST_DSN to run "
           "(prove the xact lock + recount against the real Postgres before deploy)",
)

_LOCK_SQL = "SELECT pg_advisory_xact_lock($1, hashtext($2))"


async def _clean_synthetic(conn):
    """DELETE the synthetic-mode rows THROUGH the mi_live_trades delete-guard.
    Prod blocks trade-row deletes unless `mi.allow_trade_delete` is set (a real
    safety feature — a raw DELETE fails against prod); `SET LOCAL` scopes the
    escape to this one txn. Sweeps ALL `account_mode=_MODE` rows, so a re-run
    also clears any row a prior blocked-cleanup left behind. The synthetic mode
    is exclusive to this test — no real 'live'/'paper' row is ever in scope."""
    async with conn.transaction():
        await conn.execute("SET LOCAL mi.allow_trade_delete = 'yes'")
        await conn.execute(
            "DELETE FROM mi_live_trades WHERE account_mode = $1", _MODE,
        )


@pytest.mark.asyncio
async def test_cap_xact_lock_serializes_and_recount_sees_committed_row():
    """The exact STEP-6 contract: while A's transaction holds the mode key,
    B blocks; A commits its confirmed row; B then acquires and its recount
    (the REAL count_open_positions SQL) sees A's row."""
    import asyncpg

    conn_a = await asyncpg.connect(_DSN)
    conn_b = await asyncpg.connect(_DSN)
    cleanup = await asyncpg.connect(_DSN)
    try:
        await _clean_synthetic(cleanup)
        baseline = await count_open_positions(conn_b, _MODE)
        assert baseline == 0

        # A: open txn, take the mode key, insert a countable ('confirmed') row.
        tr_a = conn_a.transaction()
        await tr_a.start()
        await conn_a.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, _MODE)
        await conn_a.execute(
            """
            INSERT INTO mi_live_trades (ticker, alert_date, status, account_mode, signal_type)
            VALUES ($1, $2, 'confirmed', $3, 'magna53')
            """,
            _TICKER, date(2001, 1, 1), _MODE,
        )

        b_seen: list[int] = []

        async def _b_recount():
            tr_b = conn_b.transaction()
            await tr_b.start()
            await conn_b.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, _MODE)
            b_seen.append(await count_open_positions(conn_b, _MODE))
            await tr_b.commit()

        task = asyncio.create_task(_b_recount())
        await asyncio.sleep(0.5)
        assert not task.done(), (
            "B must BLOCK on the same-mode cap key while A's transaction holds it "
            "— cross-connection serialization is the whole fix"
        )

        # A commits → the xact lock releases AFTER the row is committed.
        await tr_a.commit()
        await asyncio.wait_for(task, timeout=5)
        assert b_seen == [baseline + 1], (
            "the next waiter's recount MUST see the previous holder's committed "
            f"row (saw {b_seen}, expected [{baseline + 1}])"
        )
    finally:
        try:
            await _clean_synthetic(cleanup)
        finally:
            await conn_a.close()
            await conn_b.close()
            await cleanup.close()


@pytest.mark.asyncio
async def test_paper_key_acquires_while_live_key_held():
    """#66 isolation: while a holder sits on the 'live' cap key, the 'paper'
    key acquires immediately — hashtext('paper') != hashtext('live'), so paper
    entries never serialize against live. No table writes; keys are ephemeral."""
    import asyncpg

    conn_a = await asyncpg.connect(_DSN)
    conn_c = await asyncpg.connect(_DSN)
    try:
        tr_a = conn_a.transaction()
        await tr_a.start()
        await conn_a.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, "live")

        tr_c = conn_c.transaction()
        await tr_c.start()
        await asyncio.wait_for(
            conn_c.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, "paper"),
            timeout=2,
        )  # must NOT block
        await tr_c.rollback()
        await tr_a.rollback()  # rollback also releases the xact lock — no cleanup
    finally:
        await conn_a.close()
        await conn_c.close()


@pytest.mark.asyncio
async def test_xact_lock_auto_releases_on_rollback():
    """Error path: a failed STEP-6 transaction (rollback) must release the cap
    key with no unlock bookkeeping — the next entry proceeds immediately."""
    import asyncpg

    conn_a = await asyncpg.connect(_DSN)
    conn_b = await asyncpg.connect(_DSN)
    try:
        tr_a = conn_a.transaction()
        await tr_a.start()
        await conn_a.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, _MODE)
        await tr_a.rollback()  # simulated pipeline error inside the txn

        tr_b = conn_b.transaction()
        await tr_b.start()
        await asyncio.wait_for(
            conn_b.fetchval(_LOCK_SQL, _CAP_LOCK_NAMESPACE, _MODE),
            timeout=2,
        )  # must acquire immediately — no leaked lock
        await tr_b.rollback()
    finally:
        await conn_a.close()
        await conn_b.close()
