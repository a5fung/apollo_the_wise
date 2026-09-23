"""Manually trigger partial exits on GOOGL #56 (17 sh) and TEAM #57 (76 sh).

Post-rollback: bogus DB rows cleared. SCOSM defer-to-fill is live.
These calls place market sells (queued AH for next-day open fill);
WS fill event will commit DB + Telegram with real fill prices.
"""
import asyncio
from agents.market_intelligence.broker.order_manager import execute_partial_exit


async def main():
    for trade_id, shares in ((56, 17), (57, 76)):
        print(f"--- execute_partial_exit({trade_id}, {shares}) ---")
        ok = await execute_partial_exit(trade_id, shares)
        print(f"  result: {ok}")


asyncio.run(main())
