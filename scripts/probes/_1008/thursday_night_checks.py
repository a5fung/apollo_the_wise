"""2026-10-06 read-only: Tuesday-night verifies — #655 wait, #543 sweep, #580/#693 night 2, #598 PURR, #635 quiet."""
import asyncio
from agents.market_intelligence.db import get_pool

T = "created_at >= (date_trunc('day', now() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York')"


async def ev(c, names, limit=30, n=230):
    rows = await c.fetch(f"""SELECT created_at AT TIME ZONE 'America/New_York' t, event_type, LEFT(summary, {n}) s, LEFT(detail, 400) d
                             FROM mi_audit_log WHERE event_type = ANY($1) AND {T} ORDER BY created_at LIMIT {limit}""", names)
    for r in rows:
        print(f"  {r['t']:%H:%M:%S} {r['event_type']:<34} {r['s']}")
    if not rows:
        print("  (none)", names)
    return rows


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("== #655 rule B (one-night wait)")
        rows = await c.fetch(f"""SELECT detail::json->>'theme' th, (detail::json->>'members')::int m, detail::json->>'prior_members' p
                                 FROM mi_audit_log WHERE event_type='theme_retired_small_fading' AND {T}""")
        for r in rows:
            print("  ", dict(r))
        print("  B rows:", len(rows), "| any prior_members >=3 or null:", sum(1 for r in rows if r["p"] is None or int(r["p"]) >= 3))
        await ev(c, ["theme_correctness_check"], 3, 400)
        print("== #543 dead-column sweep")
        await ev(c, ["dead_column_suspect", "dead_column_detected"])
        print("== #580 breadth")
        d = await c.fetchval("SELECT max(theme_date) FROM mi_themes")
        print("  theme_date", d)
        for r in await c.fetch("""SELECT stage, count(*) n, count(*) FILTER (WHERE pct_above_20sma = 0) zero,
                                  count(*) FILTER (WHERE pct_above_20sma IS NULL) nul FROM mi_themes WHERE theme_date=$1 GROUP BY 1""", d):
            print("  ", dict(r))
        fades = await c.fetch(f"""SELECT summary FROM mi_audit_log WHERE event_type='theme_breadth_fade' AND {T}""")
        print("  breadth fades tonight:", len(fades))
        for r in fades:
            print("    ", r["summary"][:120])
        print("== #693 night 2")
        await ev(c, ["llm_request_rewrite_adopted", "theme_parent_pass_ran", "theme_synthesis_run"], 10, 200)
        for r in await c.fetch(f"""SELECT event_type, count(*) n FROM mi_audit_log WHERE {T} AND
                                   (event_type ILIKE '%refus%' OR event_type ILIKE '%parse_fail%') GROUP BY 1"""):
            print("  ", dict(r))
        print("== #598 flag transitions today (PURR must not repeat)")
        await ev(c, ["flag_stage_transition"], 20, 160)
        print("== #635 error rows today")
        await ev(c, ["ep_repoll_upgrade_error", "ep_candidate_parse_error", "drawdown_breaker_read_error"])


asyncio.run(main())


async def extra():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        n = await c.fetchval("""SELECT count(*) FROM mi_audit_log WHERE event_type='ep_candidate_parse_error'
                                AND (created_at AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date""")
        print("== F8 ep_candidate_parse_error rows today:", n)
        s = await c.fetchval("""SELECT count(*) FROM mi_ep_scan_log WHERE scan_date=(now() AT TIME ZONE 'America/New_York')::date""")
        print("   EP scan-log rows today (the scan ran):", s)

asyncio.run(extra())
