"""2026-10-08 read-only: every caller now on claude-haiku-5-5 — output vs its registered ceiling, truncations, vs haiku-4-5 last week."""
import asyncio
from agents.market_intelligence.db import get_pool
from shared.output_ceilings import CEILINGS


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT caller, model, count(*) n, round(avg(output_tokens)) av, max(output_tokens) mx,
                                count(*) FILTER (WHERE stop_reason='max_tokens') trunc
                                FROM api_usage WHERE created_at > now() - interval '8 days'
                                AND model IN ('claude-haiku-5-5', 'claude-haiku-4-5-20251001')
                                GROUP BY 1,2 ORDER BY 1,2""")
        for r in rows:
            cap = CEILINGS.get(r["caller"])
            print(f"{r['caller']:<34} {r['model']:<26} n={r['n']:<4} avg={r['av']:<6} max={r['mx']:<5} trunc={r['trunc']}  cap={cap.max_tokens if cap else '?'}")


asyncio.run(main())
