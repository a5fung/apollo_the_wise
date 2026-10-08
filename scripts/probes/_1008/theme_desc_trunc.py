"""2026-10-08 read-only: the theme_descriptions truncation at 500/500 on claude-haiku-5-5."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::date d, model, count(*) n, max(output_tokens) mx,
                                  round(avg(output_tokens)) av, count(*) FILTER (WHERE stop_reason='max_tokens') trunc,
                                  round(avg(input_tokens)) avg_in, max(input_tokens) max_in
                                  FROM api_usage WHERE caller='theme_descriptions' AND created_at > now() - interval '6 days'
                                  GROUP BY 1,2 ORDER BY 1,2"""):
            print(dict(r))
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, model, input_tokens, output_tokens, stop_reason
                                  FROM api_usage WHERE caller='theme_descriptions' AND stop_reason='max_tokens'
                                  AND created_at > now() - interval '6 days' ORDER BY created_at"""):
            print("TRUNC:", dict(r))
        for r in await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, 300) s FROM mi_audit_log
                                  WHERE (event_type ILIKE '%model%resol%' OR event_type ILIKE '%model_adopt%' OR event_type ILIKE '%canary%')
                                  AND created_at > now() - interval '6 days' ORDER BY created_at DESC LIMIT 6"""):
            print("MODEL:", f"{r['t']:%m-%d %H:%M}", r["event_type"], r["s"])


asyncio.run(main())
