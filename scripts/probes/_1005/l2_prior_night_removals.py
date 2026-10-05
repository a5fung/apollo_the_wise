"""2026-10-05 read-only: the description-validator removals on the three prior validation nights
(09-28, 09-30, 10-02), to compare their wrong-removal rate with tonight's. NO writes."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        for d in ("2026-09-28", "2026-09-30", "2026-10-02"):
            rows = await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::time t, summary, detail FROM mi_audit_log
                WHERE event_type='ticker_revalidated_out'
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $1 ORDER BY created_at""", date.fromisoformat(d))
            print(f"== {d}: {len(rows)}")
            for r in rows:
                print(f"  {r['t']} | {(r['summary'] or '')[:110]} | {(r['detail'] or '')[:150]}")
        print("== llm rewrite adoption rows (theme model)")
        for r in await c.fetch("""SELECT (created_at AT TIME ZONE 'America/New_York')::text t, LEFT(summary,160) s FROM mi_audit_log
            WHERE event_type ILIKE 'llm_request_rewrite%' AND created_at > now() - interval '10 days' ORDER BY created_at"""):
            print("  ", r["t"], r["s"])

asyncio.run(main())
