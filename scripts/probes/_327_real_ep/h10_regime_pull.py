"""#327 H10 — ONE read-only SELECT of mi_market_regime for the fire window (2026-04-01 -> 2026-10-05).
Run inside apollo-market (docker exec -w /app ... python /tmp/x.py); stdout captured once to h10_regime.tsv.
No writes. created_at is pulled so a backfilled label (written after the day it describes) can be told apart
from a label the sizing path could actually have seen the morning after."""
import asyncio

from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT regime_date, regime, vix, qqq_ema_bullish, created_at
               FROM mi_market_regime
               WHERE regime_date BETWEEN DATE '2026-04-01' AND DATE '2026-10-05'
               ORDER BY regime_date"""
        )
    print("regime_date|regime|vix|qqq_ema_bullish|created_at")
    for r in rows:
        print("|".join("" if r[k] is None else str(r[k]) for k in
                       ("regime_date", "regime", "vix", "qqq_ema_bullish", "created_at")))


asyncio.run(main())
