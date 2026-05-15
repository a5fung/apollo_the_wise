"""Regression test for the CRMD-class AmbiguousParameter bug (2026-05-14).

Walks every parameterized UPDATE on the trade-lifecycle hot path and calls
asyncpg's `connection.prepare(sql)`. Type-deduction failures raise at
prepare time — so this catches CRMD-class column-type bugs at unit-test
time rather than at first live entry fill.

Requires a Postgres available (uses production `get_pool()`). When the
test environment doesn't have a DB, skipped via env var.
"""
from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("APOLLO_TEST_DB") != "1",
    reason="Set APOLLO_TEST_DB=1 to run DB-dependent tests (requires Postgres).",
)


@pytest.mark.asyncio
async def test_trade_lifecycle_updates_prepare_cleanly():
    """Every UPDATE in `scripts.preflight_db_updates.TRADE_LIFECYCLE_UPDATES`
    must prepare against the current schema without AmbiguousParameterError
    or similar type-deduction failure.
    """
    from agents.market_intelligence.db import get_pool
    from scripts.preflight_db_updates import TRADE_LIFECYCLE_UPDATES

    pool = await get_pool()
    failures: list[tuple[str, str]] = []
    async with pool.acquire() as conn:
        for label, sql in TRADE_LIFECYCLE_UPDATES:
            try:
                await conn.prepare(sql)
            except Exception as e:
                failures.append((label, f"{type(e).__name__}: {e}"))

    assert not failures, (
        "Trade-lifecycle UPDATE prepare failures (CRMD-class bug surface):\n"
        + "\n".join(f"  {l}: {e}" for l, e in failures)
    )
