"""theme_assignment_steady_state_cost review (2026-10-05, read-only): cost/night AND the uncovered pool it
works on, as a PAIR; max_tokens truncations; the value side (avg theme membership, themes <= 3 members)
vs the 2026-08-10 baseline (460 theme rows / avg 3.3 members / 350 of 460 at <= 3)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cost = await c.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) n,
                   round(sum(cost_usd)::numeric, 3) usd, sum(output_tokens) out_tok,
                   sum(CASE WHEN stop_reason = 'max_tokens' THEN 1 ELSE 0 END) trunc
              FROM api_usage WHERE caller = 'theme_assignment' AND created_at >= NOW() - INTERVAL '21 days'
             GROUP BY 1 ORDER BY 1""")
        pool_rows = await c.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, left(summary, 160) s
              FROM mi_audit_log WHERE event_type IN ('assignment_comove_summary', 'assignment_pool_size',
                   'theme_assignment_summary') AND created_at >= NOW() - INTERVAL '21 days'
             ORDER BY created_at""")
        board = await c.fetchrow("""
            WITH b AS (SELECT DISTINCT ON (name) name, tickers, stage FROM mi_themes
                        WHERE theme_date >= (NOW() AT TIME ZONE 'America/New_York')::date - 7
                        ORDER BY name, theme_date DESC)
            SELECT count(*) n, round(avg(cardinality(tickers))::numeric, 2) avg_members,
                   sum(CASE WHEN cardinality(tickers) <= 3 THEN 1 ELSE 0 END) le3
              FROM b WHERE stage <> 'Retired'""")
    print("== theme_assignment cost by night (21d)")
    for r in cost:
        print(f"  {r['d']} calls {r['n']:>3}  ${r['usd']}  out_tok {r['out_tok']}  max_tokens {r['trunc']}")
    print("== pool / summary rows (21d)")
    for r in pool_rows[-12:]:
        print(f"  {r['d']} {r['s']}")
    print(f"== live board: {dict(board)}")


asyncio.run(main())
