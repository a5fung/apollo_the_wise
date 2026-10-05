"""2026-10-05 read-only: RUM around 2026-06-04 — he says it gapped DOWN; the sample said +13.2% open gap."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes "
                             "WHERE ticker='RUM' AND trade_date BETWEEN $1 AND $2 ORDER BY trade_date",
                             date(2026, 5, 26), date(2026, 6, 10))
        al = await c.fetch("SELECT alert_date, gap_pct, ep_score, score_tier, catalyst_quality, created_at FROM mi_ep_alerts "
                           "WHERE ticker='RUM' AND alert_date BETWEEN $1 AND $2", date(2026, 6, 1), date(2026, 6, 8))
    prev = None
    for r in rows:
        g = f"{(r['open_price']/prev-1)*100:+.1f}%" if prev else ""
        print(r["trade_date"], "O", r["open_price"], "H", r["high_price"], "L", r["low_price"], "C", r["close"], "V", r["volume"], g)
        prev = r["close"]
    for a in al:
        print("ALERT", dict(a))


asyncio.run(main())
