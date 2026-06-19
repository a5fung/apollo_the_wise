"""Pull FLEX 5/6 9:30-10:00 ET minute bars to diagnose why ORB stop-limit didn't fill."""
import asyncio
import datetime
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.collector import get_minute_bars, _ET


async def main():
    scan = datetime.date(2026, 5, 6)
    bars = await get_minute_bars("FLEX", scan, scan)
    print("min_et  open    high    low     close   volume")
    print("-" * 50)
    for b in bars:
        ts = datetime.datetime.fromtimestamp(b["t"] / 1000, tz=_ET)
        if ts.date() != scan:
            continue
        m = ts.hour * 60 + ts.minute
        if m < 569 or m > 600:  # 9:29 to 10:00
            continue
        print(
            f"{ts.strftime('%H:%M')}   "
            f"{float(b['o']):6.2f}  {float(b['h']):6.2f}  "
            f"{float(b['l']):6.2f}  {float(b['c']):6.2f}  "
            f"{int(b['v']):>9d}"
        )


if __name__ == "__main__":
    asyncio.run(main())
