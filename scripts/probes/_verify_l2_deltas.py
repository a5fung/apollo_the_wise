"""Verify L2 top-event-deltas fix on real prod data.

Pre-fix bug: sparse-firing events (Mon/Wed/Fri theme validation)
reported with baseline=0 and 'NEW today' even when they'd fired
129×/14d. Fix discriminates daily-ish vs sparse-firing events.

Run: docker exec apollo-market python -m scripts._verify_l2_deltas
"""
import asyncio
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.system_audit import _top_event_deltas


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        deltas = await _top_event_deltas(conn, top_n=10)
        if not deltas:
            print("No event deltas returned (no events in last 24h).")
            return
        for d in deltas:
            tag = (
                f"today={d['today_count']:4d} "
                f"base={d['baseline_median']:6.2f} ({d['baseline_label']}) "
                f"fired={d['firing_days']:2d}/13d "
                f"total={d['window_total']:4d} "
                f"ratio={d['ratio']:5.2f}x "
                f"is_new={d['is_new']}"
            )
            print(f"  {d['event_type']:40s} {tag}")


if __name__ == "__main__":
    asyncio.run(main())
