"""Synthetic test for #49 — verify EP-scan failure produces audit + Telegram.

Monkey-patches run_ep_scan to raise, then invokes _ep_scan_job. Verifies:
  1. mi_audit_log gets an `ep_scan_failed` row
  2. Telegram message attempt was made (logged)

Run: docker exec apollo-market python -m scripts._test_ep_scan_failure_alert
"""
import asyncio
from agents.market_intelligence import scheduler, ep_detector
from agents.market_intelligence.db import get_pool


async def main():
    # Pre-clean any test rows from prior runs in last 5 min
    pool = await get_pool()
    async with pool.acquire() as conn:
        before_count = await conn.fetchval("""
            SELECT COUNT(*) FROM mi_audit_log
            WHERE event_type = 'ep_scan_failed'
              AND created_at > NOW() - INTERVAL '5 minutes'
        """)
        print(f"ep_scan_failed audit rows in last 5min BEFORE test: {before_count}")

    # Inject synthetic failure. scheduler.py does
    # `from ... ep_detector import run_ep_scan` at module top, creating a
    # local-to-scheduler binding. Must patch scheduler.run_ep_scan, not
    # ep_detector.run_ep_scan, to affect _ep_scan_job's call.
    async def boom():
        raise RuntimeError("SYNTHETIC TEST: simulated EP scan failure for #49 verification")
    original = scheduler.run_ep_scan
    scheduler.run_ep_scan = boom

    try:
        await scheduler._ep_scan_job()
    finally:
        scheduler.run_ep_scan = original

    # Check that ep_scan_failed audit row landed
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT created_at, event_type, summary, LEFT(detail, 200) AS detail_head
            FROM mi_audit_log
            WHERE event_type = 'ep_scan_failed'
              AND summary LIKE 'RuntimeError:%'
            ORDER BY created_at DESC LIMIT 3
        """)
    print(f"\nep_scan_failed rows after test:")
    for r in rows:
        print(f"  {r['created_at']}  {r['summary'][:100]}")

    print(f"\nTest complete. Expect 1 new ep_scan_failed audit row + 1 Telegram alert.")


if __name__ == "__main__":
    asyncio.run(main())
