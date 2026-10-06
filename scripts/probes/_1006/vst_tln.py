"""2026-10-06 read-only: what live rows 412 (VST) and 413 (TLN) are."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("SELECT id, ticker, status, skip_reason, signal_type, account_mode FROM mi_live_trades WHERE id IN (412, 413)"):
            print(dict(r))


asyncio.run(main())
