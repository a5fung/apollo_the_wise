"""2026-10-07 read-only: PENG — what our system did (alert, grade, trade) for the operator-labelled EP list."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        a = await c.fetchrow("""SELECT * FROM mi_ep_alerts WHERE ticker='PENG' AND alert_date='2026-10-07' ORDER BY id LIMIT 1""")
        if a:
            print({k: v for k, v in dict(a).items() if k in ("alert_date", "ep_score", "score_tier", "gap_pct", "catalyst_quality",
                   "prev_close", "rel_volume", "in_active_theme", "alert_time", "created_at") and v is not None})
            print("catalyst:", (a.get("catalyst") or a.get("catalyst_summary") or "")[:300] if "catalyst" in a.keys() or "catalyst_summary" in a.keys() else "")
        t = await c.fetchrow("""SELECT id, status, entry_price, entry_shares, stop_price, orb_high, orb_low, risk_dollars
                                FROM mi_live_trades WHERE ticker='PENG' AND account_mode='live' ORDER BY id DESC LIMIT 1""")
        print("trade:", dict(t) if t else None)


asyncio.run(main())
