import asyncio
from agents.market_intelligence import db


async def m():
    pool = await db.get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""
            SELECT event_type, COUNT(*) n, MAX(created_at) last
            FROM mi_audit_log
            WHERE created_at >= NOW() - INTERVAL '8 hours'
              AND (event_type ILIKE '%validation%' OR event_type ILIKE '%theme%')
            GROUP BY event_type ORDER BY last DESC LIMIT 15
        """)
        if not rows:
            print("(no theme/validation audit events in last 8h — #213 5:30pm ET job not fired yet)")
        for r in rows:
            print(f"{r['event_type']:<42} n={r['n']:<4} last={r['last']}")


asyncio.run(m())
