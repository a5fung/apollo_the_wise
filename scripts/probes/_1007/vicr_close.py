"""2026-10-07 read-only, after the close: VICR's day (low/close) vs the depth stop and the updated line."""
import asyncio
from agents.market_intelligence.collector import get_snapshot_all
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT trade_date, close FROM mi_daily_closes WHERE ticker='VICR' AND trade_date < '2026-10-07'
                                ORDER BY trade_date DESC LIMIT 19""")
    snaps = await get_snapshot_all()
    s = snaps.get("VICR") or {}
    day = s.get("day") or {}
    print("snapshot day:", {k: day.get(k) for k in ("o", "h", "l", "c", "v")}, "prevDay close:", (s.get("prevDay") or {}).get("c"))
    close = float(day.get("c") or 0)
    prior = [float(r["close"]) for r in rows]
    sma10 = (close + sum(prior[:9])) / 10
    sma20 = (close + sum(prior[:19])) / 20
    print(f"today close {close:.2f} | updated SMA10 {sma10:.2f} SMA20 {sma20:.2f} line {max(sma10, sma20):.2f} | depth stop (from yesterday's line) 274.06")


asyncio.run(main())
