#!/usr/bin/env python3
"""Post-deploy smoke (READ-ONLY): confirm the DEPLOYED collector.get_sec_recent_filings works."""
import asyncio

from agents.market_intelligence.collector import get_sec_recent_filings


async def main():
    for t in ("RUM", "PGY"):
        r = await get_sec_recent_filings(t)
        print(f"{t}: {len(r)} filing(s)")
        for f in r:
            txt = f.get("text", "")
            print(f"  {f['form']} {f['filed']} items={f['items']} chars={len(txt)} "
                  f"nvidia={'NVIDIA' in txt or 'Blackwell' in txt}")


asyncio.run(main())
