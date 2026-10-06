"""2026-10-06 read-only: where an 'EP bar 75' could have reached him today (regime rows + any stored outbound text)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("SELECT regime_date, regime, ep_threshold FROM mi_market_regime ORDER BY regime_date DESC LIMIT 4"):
            print("regime:", dict(r))
        tabs = [r["table_name"] for r in await c.fetch("""SELECT table_name FROM information_schema.columns
                 WHERE table_schema='public' AND column_name IN ('message','text','body','content') AND table_name LIKE 'mi_%'""")]
        print("text tables:", tabs)
        for t in tabs:
            col = await c.fetchval("""SELECT column_name FROM information_schema.columns WHERE table_name=$1
                                      AND column_name IN ('message','text','body','content') LIMIT 1""", t)
            ts = await c.fetchval("""SELECT column_name FROM information_schema.columns WHERE table_name=$1
                                     AND column_name IN ('created_at','sent_at','ts') LIMIT 1""", t)
            if not ts:
                continue
            rows = await c.fetch(f"""SELECT LEFT("{col}", 300) x FROM "{t}" WHERE "{ts}" > now() - interval '20 hours'
                                     AND ("{col}" ILIKE '%75%') AND ("{col}" ILIKE '%bar%' OR "{col}" ILIKE '%filter%' OR "{col}" ILIKE '%threshold%') LIMIT 3""")
            for r in rows:
                print(f"[{t}]", r["x"].replace(chr(10), ' / '))


asyncio.run(main())
