"""#693 replay — prove the paid run wrote nothing: rows a writing run WOULD have left (13:45-14:10 ET 10-09)."""
import asyncio, os, datetime
from agents.market_intelligence.db import get_pool
W = "BETWEEN '2026-10-09 13:45' AND '2026-10-09 14:10'"
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("api_usage theme_validation rows in window:", await c.fetchval(
            f"SELECT count(*) FROM api_usage WHERE caller='theme_validation' AND created_at AT TIME ZONE 'America/New_York' {W}"))
        print("api_usage claude-sonnet-5-5 rows in window (any caller):", await c.fetchval(
            f"SELECT count(*) FROM api_usage WHERE model='claude-sonnet-5-5' AND created_at AT TIME ZONE 'America/New_York' {W}"))
        print("audit rows in window (validation/rewrite/cooldown types):", await c.fetchval(
            f"""SELECT count(*) FROM mi_audit_log WHERE created_at AT TIME ZONE 'America/New_York' {W}
                AND (event_type LIKE '%valid%' OR event_type LIKE '%rewrite%' OR event_type LIKE '%cooldown%')"""))
        print("cooldown rows written 10-09:", await c.fetchval(
            "SELECT count(*) FROM mi_validation_cooldowns WHERE (removed_at AT TIME ZONE 'America/New_York')::date='2026-10-09'"))
    p = "/app/logs/llm_samples/agents.market_intelligence.theme_engine___validate_theme_membership.json"
    print("validator sample file mtime (UTC):", datetime.datetime.utcfromtimestamp(os.path.getmtime(p)))
asyncio.run(main())
