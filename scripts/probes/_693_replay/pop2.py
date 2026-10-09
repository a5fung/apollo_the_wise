"""#693 replay — what persisted state can rebuild 10-05's validator inputs (read-only)."""
import asyncio, json
from agents.market_intelligence.db import get_pool
ET = "AT TIME ZONE 'America/New_York'"
async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for r in await c.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name LIKE '%changelog%' OR table_name LIKE 'mi_theme%' OR table_name LIKE '%override%' OR table_name LIKE '%desc%') ORDER BY 1"):
            print(r['table_name'])
        print([ (r['column_name'], r['data_type']) for r in await c.fetch("SELECT column_name,data_type FROM information_schema.columns WHERE table_name='mi_themes'")])
        print([ (r['column_name'], r['data_type']) for r in await c.fetch("SELECT column_name,data_type FROM information_schema.columns WHERE table_name='mi_ticker_overrides'")])
        print("mi_themes rows by theme_date recent:", [dict(r) for r in await c.fetch("SELECT theme_date, count(*) n, max(created_at) FROM mi_themes WHERE theme_date >= '2026-10-01' GROUP BY 1 ORDER BY 1")] )
        print("\n== 10-05 audit events between 17:00 and 17:15 by type")
        for r in await c.fetch(f"""SELECT event_type, count(*) n, min((created_at {ET})::time)::text t0 FROM mi_audit_log
             WHERE created_at {ET} BETWEEN '2026-10-05 16:59' AND '2026-10-05 17:20' GROUP BY 1 ORDER BY 3"""):
            print("  ", dict(r))
asyncio.run(main())
