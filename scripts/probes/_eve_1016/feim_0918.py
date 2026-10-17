"""READ-ONLY: was FEIM in the coil scan's universe on 2026-09-18? (advisor review item 4)"""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_anticipation_universe
async def main():
    for d in (date(2026,9,17), date(2026,9,18), date(2026,9,21)):
        u = await get_anticipation_universe(d)
        tick = {x["ticker"] if isinstance(x, dict) else x for x in u}
        print(d, "universe", len(tick), "FEIM in it:", "FEIM" in tick)
asyncio.run(main())
