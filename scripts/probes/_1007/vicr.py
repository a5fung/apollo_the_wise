"""2026-10-07 read-only: VICR stop-out — the trade row, the stop fill, and the trailing line (max SMA10/SMA20),
ADR20 and the #687 depth-rule stop level, so the close can be judged against both rules."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        t = await c.fetchrow("""SELECT * FROM mi_live_trades WHERE ticker='VICR' AND account_mode='live' ORDER BY id DESC LIMIT 1""")
        keep = {k: v for k, v in dict(t).items() if v is not None and any(s in k for s in
                ("id", "status", "entry_price", "shares", "stop", "exit", "close", "pnl", "partial", "orb", "alert_date", "rule"))}
        print("trade:", keep)
        rows = await c.fetch("""SELECT trade_date, close, high_price, low_price FROM mi_daily_closes WHERE ticker='VICR'
                                ORDER BY trade_date DESC LIMIT 25""")
        closes = [float(r["close"]) for r in rows]
        ranges = [(float(r["high_price"]) - float(r["low_price"])) / float(r["close"]) for r in rows[:20]]
        sma10 = sum(closes[:10]) / 10; sma20 = sum(closes[:20]) / 20; adr = sum(ranges) / len(ranges)
        line = max(sma10, sma20)
        print(f"as of {rows[0]['trade_date']}: close {closes[0]:.2f} SMA10 {sma10:.2f} SMA20 {sma20:.2f} line {line:.2f} "
              f"ADR20 {adr*100:.2f}% depth stop {line*(1-adr):.2f}")
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 200) s FROM mi_audit_log
                                  WHERE (summary ILIKE '%VICR%') AND created_at > now() - interval '10 hours' ORDER BY created_at LIMIT 10"""):
            print(f"  {r['t']:%H:%M:%S} {r['event_type']:<30} {r['s']}")


asyncio.run(main())
