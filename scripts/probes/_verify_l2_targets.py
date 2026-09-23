"""Verify L2 fix specifically on the events that triggered the bug."""
import asyncio
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.system_audit import _top_event_deltas


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        deltas = await _top_event_deltas(conn, top_n=50)
        targets = (
            "ticker_revalidated_out",
            "validation_cooldown_triggered",
            "dual_account_creds_resolved",
        )
        for d in deltas:
            et = d["event_type"]
            if et in targets or "revalidated" in et or "cooldown" in et:
                print(f"  {et:35s} today={d['today_count']:3d} "
                      f"base={d['baseline_median']:6.2f} ({d['baseline_label']}) "
                      f"fired={d['firing_days']:2d}/13d "
                      f"total={d['window_total']:4d} "
                      f"ratio={d['ratio']:.2f}x is_new={d['is_new']}")


if __name__ == "__main__":
    asyncio.run(main())
