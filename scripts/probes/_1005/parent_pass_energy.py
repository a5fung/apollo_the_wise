"""2026-10-05 read-only: what the #505 parent pass has decided about energy themes (audit rows)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""
            SELECT created_at::date d, event_type, LEFT(detail::text, 260) det FROM mi_audit_log
            WHERE event_type ILIKE '%parent%' AND created_at > now() - interval '10 days'
              AND (detail::text ILIKE '%gas%' OR detail::text ILIKE '%oil%' OR detail::text ILIKE '%energy%'
                   OR detail::text ILIKE '%drill%' OR detail::text ILIKE '%E-ENER%')
            ORDER BY created_at DESC LIMIT 12""")
        for r in rows:
            print(r["d"], r["event_type"], r["det"])
        n = await c.fetchval("""SELECT count(*) FROM mi_audit_log WHERE event_type ILIKE '%parent%'
                                AND created_at > now() - interval '10 days'""")
        print("all parent-pass rows, 10 days:", n)


asyncio.run(main())
