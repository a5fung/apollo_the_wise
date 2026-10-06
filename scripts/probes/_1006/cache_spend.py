"""2026-10-06 read-only: where direct API spend goes (last 30 days) and how much is already cached —
to size Anthropic's 'prompt cache hit rate is low' email."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        tot = await c.fetchrow("""SELECT round(sum(cost_usd)::numeric,2) usd, sum(input_tokens) inp, sum(output_tokens) outp,
                                  sum(cache_creation) cw, sum(cache_read) cr, count(*) n
                                  FROM api_usage WHERE created_at > now() - interval '30 days'""")
        print("30d total:", dict(tot))
        print("caller | model | calls | usd | input_tok | avg_in | output_tok | cache_write | cache_read")
        for r in await c.fetch("""SELECT caller, model, count(*) n, round(sum(cost_usd)::numeric,2) usd, sum(input_tokens) inp,
                                  round(avg(input_tokens)) avg_in, sum(output_tokens) outp, sum(cache_creation) cw, sum(cache_read) cr
                                  FROM api_usage WHERE created_at > now() - interval '30 days'
                                  GROUP BY 1,2 ORDER BY 4 DESC LIMIT 25"""):
            print(" | ".join(str(v) for v in r.values()))


asyncio.run(main())
