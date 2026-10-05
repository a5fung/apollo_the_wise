"""2026-10-05 read-only: #394 — every row on tonight's coil board has last_eval = tonight's scan date, order holds."""
import asyncio
from agents.market_intelligence.db import get_consolidation_board


async def main():
    rows = await get_consolidation_board()
    print("rows:", len(rows))
    print("last_eval values:", sorted({str(r.get("last_eval")) for r in rows}))
    print("NULL orderliness:", sum(1 for r in rows if r.get("orderliness") is None))
    for r in rows[:30]:
        print(f"  {r.get('ticker'):6s} state={r.get('state')} streak={r.get('tight_close_streak')} today_pct={r.get('today_pct')} ord={r.get('orderliness')}")


asyncio.run(main())
