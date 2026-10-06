"""2026-10-06 read-only: #624 low-cap lane — rows recorded so far and how many have a settled outcome."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_lowcap_lane_signals'")]
        print("cols:", cols)
        dcol = next((x for x in ("scan_date", "signal_date", "alert_date") if x in cols), None)
        print(dict(await c.fetchrow(f"""SELECT count(*) n, count(DISTINCT {dcol}) sessions, min({dcol}) first, max({dcol}) last
                                        FROM mi_lowcap_lane_signals""")))
        for oc in ("realized_r", "outcome_r", "r_multiple", "settled_r"):
            if oc in cols:
                print(oc, dict(await c.fetchrow(f"""SELECT count({oc}) settled,
                         count(*) FILTER (WHERE {oc} >= 3) ge3, round(avg({oc})::numeric,2) mean FROM mi_lowcap_lane_signals""")))


asyncio.run(main())
