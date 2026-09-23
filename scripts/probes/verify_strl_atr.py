"""Verify STRL ATR-14 against user's reported $43.25."""
import asyncio
from datetime import date
from agents.market_intelligence.backtester.filters import compute_atr_14
from agents.market_intelligence.db import get_pool


async def main():
    today = date(2026, 5, 5)
    atr, atr_pct = await compute_atr_14("STRL", today)
    print(f"SMA Wilder-TR ATR-14 (filters.py): ${atr:.2f} ({atr_pct:.2f}%)")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trade_date, high_price, low_price, close
            FROM mi_daily_closes
            WHERE ticker = $1 AND trade_date <= $2 AND trade_date >= $2 - INTERVAL '60 days'
              AND high_price IS NOT NULL AND low_price IS NOT NULL
            ORDER BY trade_date ASC
            """,
            "STRL",
            today,
        )

    print(f"\nBars: {len(rows)}, last_close=${float(rows[-1]['close']):.2f}")
    print(f"\nDate         O/H/L/C          TR")
    print("-" * 60)
    trs = []
    for i in range(1, len(rows)):
        h = float(rows[i]["high_price"])
        l = float(rows[i]["low_price"])
        c = float(rows[i]["close"])
        pc = float(rows[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        print(f"{rows[i]['trade_date']}   H={h:7.2f} L={l:7.2f} C={c:7.2f} pC={pc:7.2f}  TR={tr:6.2f}")

    print(f"\nLast 14 TRs avg (SMA): ${sum(trs[-14:])/14:.2f}")
    print(f"Last 20 TRs avg:       ${sum(trs[-20:])/20:.2f}")

    if len(trs) >= 14:
        rma = sum(trs[:14]) / 14
        for tr in trs[14:]:
            rma = (rma * 13 + tr) / 14
        print(f"Wilder RMA (running): ${rma:.2f}")

    # Also try last-14-sessions-ending-yesterday (some platforms)
    if len(trs) >= 15:
        print(f"SMA on TRs[-15:-1] (excl today): ${sum(trs[-15:-1])/14:.2f}")


asyncio.run(main())
