"""Trip-test for the partial-exit circuit breaker (#151 c, success-aware).

The breaker (`_consecutive_partial_exit_failures`) was verified to read 0/CLOSED
against live data — but a 0 can't distinguish "correctly closed" from a query
bug that always returns ~0. A breaker that never trips is false safety. This
proves it BOTH opens on consecutive failures AND closes on a success, exercising
the REAL SQL against the REAL schema (a mocked-pool unit test would miss a query
bug). Mirrors the G6 / watchdog "prove it trips, not just green" discipline.

Method (sentinel-marked synthetic `mi_audit_log` rows, cleaned up in finally):
  1. Insert a `partial_exit_committed` anchor, then THRESHOLD genuine-failure
     rows after it → assert breaker reads >= THRESHOLD (OPEN).
  2. Insert a newer `partial_exit_committed` → assert breaker reads 0 (CLOSED) —
     a success resets the count.
  3. Delete all sentinel rows; verify none remain.

`mi_audit_log` is NOT under the protect_trade_tables delete trigger, so cleanup
is a plain DELETE. No Alpaca creds / market needed — pure DB logic. Safe to
re-run anytime; run before shipping any change to the breaker.

Exit 0 = breaker trips + resets correctly. Exit 1 = assertion failed (real bug).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("breaker_triptest")

_SENTINEL = "_breaker_triptest"  # marker in detail JSON for cleanup


async def _insert(conn, event_type: str) -> None:
    await conn.execute(
        "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ($1, $2, $3)",
        event_type,
        f"TRIPTEST {event_type} (synthetic — ignore)",
        json.dumps({_SENTINEL: True}),
    )


async def _cleanup(conn) -> int:
    res = await conn.execute(
        f"DELETE FROM mi_audit_log WHERE detail LIKE '%{_SENTINEL}%'"
    )
    # asyncpg returns 'DELETE <n>'
    try:
        return int(res.split()[-1])
    except Exception:
        return -1


async def run() -> int:
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.broker.order_manager import (
        _consecutive_partial_exit_failures,
        _PARTIAL_EXIT_BREAKER_THRESHOLD as THRESH,
    )

    pool = await get_pool()
    ok = True
    try:
        async with pool.acquire() as conn:
            # Pre-clean any leftover sentinel rows from a crashed prior run.
            await _cleanup(conn)

            # 1. Anchor success, then THRESH genuine failures after it → OPEN.
            await _insert(conn, "partial_exit_committed")
            for _ in range(THRESH):
                await _insert(conn, "partial_exit_sell_failed")

        open_count = await _consecutive_partial_exit_failures()
        if open_count >= THRESH:
            logger.info(f"OPEN check PASS: {open_count} failures since last success "
                        f"(>= threshold {THRESH}) → breaker would OPEN")
        else:
            ok = False
            logger.error(f"OPEN check FAIL: counted {open_count}, expected >= {THRESH}. "
                         f"Breaker would NOT trip on real failures — query bug?")

        # 2. Newer success resets the window → CLOSED.
        async with pool.acquire() as conn:
            await _insert(conn, "partial_exit_committed")
        closed_count = await _consecutive_partial_exit_failures()
        if closed_count == 0:
            logger.info(f"CLOSE check PASS: {closed_count} failures after a fresh "
                        f"success → breaker CLOSES on success")
        else:
            ok = False
            logger.error(f"CLOSE check FAIL: counted {closed_count}, expected 0. "
                         f"Success does not reset the window.")
    except Exception as e:
        ok = False
        logger.error(f"trip-test raised: {type(e).__name__}: {e}")
    finally:
        async with pool.acquire() as conn:
            n = await _cleanup(conn)
        logger.info(f"cleanup: deleted {n} sentinel row(s)")
        # Hard-verify nothing leaked.
        async with pool.acquire() as conn:
            left = await conn.fetchval(
                f"SELECT COUNT(*) FROM mi_audit_log WHERE detail LIKE '%{_SENTINEL}%'"
            )
        if left:
            ok = False
            logger.error(f"CLEANUP INCOMPLETE: {left} sentinel row(s) remain — remove manually")

    if ok:
        logger.info("PASS — partial-exit breaker trips on failures + closes on success")
        return 0
    logger.error("FAIL — see assertions above")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
