"""LIVN 5/6 RVOL@T discriminator — Wave B #2 sanity check.

Run inside apollo-market container:
    docker exec -i apollo-market python /app/scripts/discrim_livn_rvol.py

Verifies the unified RVOL@T fix would have cleared LIVN at the right minute,
well before the 9:45 ORB cutoff.
"""
import asyncio
import datetime
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.collector import get_minute_bars, _ET
from agents.market_intelligence.db import get_pool


async def discrim(ticker: str, scan_date: datetime.date):
    bars = await get_minute_bars(ticker, scan_date, scan_date)
    if not bars:
        print(f"{ticker}: NO BARS")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT et_clock_minute, mean_cum_vol, sample_n
            FROM mi_minute_volume_curves
            WHERE ticker = $1 AND anchor = 'session'
            ORDER BY et_clock_minute
            """,
            ticker,
        )
    base_map = {r["et_clock_minute"]: (r["mean_cum_vol"], r["sample_n"]) for r in rows}

    cum = 0
    print(f"=== {ticker} {scan_date} session-anchor RVOL@T ===")
    print("clock_min  et     cum_vol      baseline   rvol@t   sample_n")
    print("-" * 65)
    for b in bars:
        ts_et = datetime.datetime.fromtimestamp(b["t"] / 1000, tz=_ET)
        if ts_et.date() != scan_date:
            continue
        et_min = ts_et.hour * 60 + ts_et.minute
        if et_min < 570 or et_min > 595:
            continue
        cum += b["v"]
        base, n = base_map.get(et_min, (None, 0))
        if base and base > 0:
            rvol = cum / base
            print(
                f"{et_min:>8d}   {ts_et.strftime('%H:%M')}  "
                f"{int(cum):>10d}  {base:>10.0f}   {rvol:>6.2f}x   n={n}"
            )
        else:
            print(
                f"{et_min:>8d}   {ts_et.strftime('%H:%M')}  "
                f"{int(cum):>10d}  NO_BASELINE"
            )


async def main():
    await discrim("LIVN", datetime.date(2026, 5, 6))


if __name__ == "__main__":
    asyncio.run(main())
