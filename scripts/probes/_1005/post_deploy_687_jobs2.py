"""2026-10-05 read-only: #687 positive checks from mi_job_runs (the audit_wrap record of each run)."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_job_runs' ORDER BY ordinal_position")]
        print("cols:", cols)
        ts = "started_at" if "started_at" in cols else cols[2]
        rows = await c.fetch(f"""SELECT * FROM mi_job_runs WHERE {ts} > now() - interval '7 hours'
                                 AND (job_id ILIKE '%depth%' OR job_id ILIKE '%close%below%' OR job_id ILIKE '%eod%'
                                      OR job_id ILIKE '%16%45%' OR job_id ILIKE '%exit%' OR job_id = 'live_position_update') ORDER BY {ts}""")
        for r in rows:
            print({k: (str(v)[:80] if v is not None else None) for k, v in dict(r).items()})


asyncio.run(main())
