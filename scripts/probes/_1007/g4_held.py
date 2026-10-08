"""2026-10-07 read-only: #655 G4 miss tonight — the small (<3 member) live themes, split by whether they were
already small the night before (rule B's one-night wait holds the ones that were not)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        d1 = await c.fetchval("SELECT max(theme_date) FROM mi_themes")
        d0 = await c.fetchval("SELECT max(theme_date) FROM mi_themes WHERE theme_date < $1", d1)
        rows = await c.fetch("""SELECT name, stage, coalesce(array_length(tickers,1),0) n, rs_avg FROM mi_themes
                                WHERE theme_date=$1 AND stage <> 'Retired' AND coalesce(array_length(tickers,1),0) < 3""", d1)
        print("tonight", d1, "prior", d0, "| small live themes:", len(rows))
        for r in rows:
            p = await c.fetchval("SELECT coalesce(array_length(tickers,1),0) FROM mi_themes WHERE theme_date=$1 AND name=$2", d0, r["name"])
            why = "HELD by the wait (was >=3)" if (p or 0) >= 3 else ("new tonight" if p is None else "small before; not weak-Fading" )
            print(f"  {r['name'][:60]:60s} {r['stage']:<12} n={r['n']} rs_avg={r['rs_avg']} prior={p} -> {why}")


asyncio.run(main())
