import asyncio
from agents.market_intelligence.db import get_pool
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::time::text t, event_type, summary, left(detail,700) d FROM mi_audit_log
             WHERE created_at AT TIME ZONE 'America/New_York' BETWEEN '2026-10-05 17:05' AND '2026-10-05 17:09:30'
             AND event_type IN ('theme_thesis_merged','theme_discovered','theme_member_rehomed','theme_rehome_join_carry_ran','theme_birth_validated','theme_merge_parent_child','theme_merge_executed','theme_auto_retired','theme_carryforward_filter_stripped','theme_merge_pairs_proposed')
             ORDER BY created_at"""):
            print(r['t'][:8], r['event_type'], '|', r['summary'], '|', r['d']); print()
asyncio.run(main())
