"""#723 design probe (read-only, market hours 11-09): time the two whole-market price sources and measure freshness.
No writes, no orders. Prints counts, timings and ages only."""
import asyncio, time
from datetime import datetime
from zoneinfo import ZoneInfo
from agents.market_intelligence import collector as c
ET = ZoneInfo("America/New_York")

async def main():
    now = datetime.now(ET)
    t0 = time.monotonic(); snaps = await c.get_snapshot_all("probe_723"); t1 = time.monotonic()
    ages = []
    for s in list(snaps.values()):
        ts = (s.get("lastTrade") or {}).get("t") or s.get("updated")
        if ts:
            ages.append((now.timestamp() * 1e9 - float(ts)) / 60e9)
    ages.sort()
    has_day = sum(1 for s in snaps.values() if (s.get("day") or {}).get("h"))
    print(f"POLYGON whole-market: {len(snaps)} tickers in {t1-t0:.1f}s; with today's high {has_day}; "
          f"last-trade age minutes p10/p50/p90 = {ages[len(ages)//10]:.1f}/{ages[len(ages)//2]:.1f}/{ages[9*len(ages)//10]:.1f}" if ages else f"POLYGON: {len(snaps)} tickers, no ages")
    syms = sorted(snaps)[:1000]
    stats = {}
    t2 = time.monotonic(); rt = await c.get_alpaca_snapshots_batch(syms, stats=stats); t3 = time.monotonic()
    print(f"ALPACA SIP batch: {len(rt)} of {len(syms)} symbols in {t3-t2:.1f}s ({stats}); extrapolated 5,000 names ~{(t3-t2)*5:.0f}s serial")
asyncio.run(main())
