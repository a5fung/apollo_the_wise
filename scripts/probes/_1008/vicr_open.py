import asyncio
from agents.market_intelligence.collector import get_snapshot_all
async def main():
    s = (await get_snapshot_all()).get("VICR") or {}
    print("VICR day:", {k: (s.get("day") or {}).get(k) for k in ("o", "h", "l", "c")}, "prevDay c:", (s.get("prevDay") or {}).get("c"))
asyncio.run(main())
