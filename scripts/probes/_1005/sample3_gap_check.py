"""#594 sample #3 (2026-10-05, read-only): was there a real gap on the named day? Daily bars around
the date + the alert row as stored, for each arm-A name."""
import asyncio
from datetime import date, timedelta
from agents.market_intelligence.db import get_pool

NAMES = [("SOLS", date(2026, 8, 28)), ("CHRN", date(2026, 8, 27)), ("AGX", date(2026, 9, 3)),
         ("SNOW", date(2026, 9, 3)), ("DG", date(2026, 8, 27))]


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts'")}
        want = [x for x in ("ticker", "alert_date", "gap_pct", "prev_close", "price", "current_price",
                            "ep_score", "score_tier", "catalyst_quality", "created_at", "news_summary")
                if x in cols]
        for t, d in NAMES:
            bars = await c.fetch(
                "SELECT trade_date, open_price, high_price, low_price, close, volume FROM mi_daily_closes "
                "WHERE ticker = $1 AND trade_date BETWEEN $2 AND $3 ORDER BY trade_date", t,
                d - timedelta(days=6), d + timedelta(days=3))
            al = await c.fetch(f"SELECT {', '.join(want)} FROM mi_ep_alerts WHERE ticker = $1 "
                               f"AND alert_date = $2", t, d)
            print(f"===== {t} {d}")
            prev = None
            for b in bars:
                g = (f"{(b['open_price'] / prev - 1) * 100:+.1f}% open-gap" if prev else "")
                print(f"  {b['trade_date']} O {b['open_price']} H {b['high_price']} L {b['low_price']} "
                      f"C {b['close']} V {b['volume']}  {g}")
                prev = b["close"]
            for a in al:
                print("  ALERT:", {k: (str(v)[:160] if v is not None else None) for k, v in dict(a).items()})


asyncio.run(main())
