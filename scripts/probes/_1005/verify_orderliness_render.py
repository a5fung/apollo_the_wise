"""2026-10-05 read-only: (1) render /anticipation exactly as the operator sees it and count board lines
carrying the orderliness phrase; (2) does mi_delayed_entry_trigger carry a settle/update timestamp, so the
'filled same evening' claim for its outcome columns can be judged by write time rather than row-creation."""
import asyncio
from agents.market_intelligence.agent import MarketIntelligenceAgent
from agents.market_intelligence.db import get_pool
from shared.models import AgentRequest

T = "AT TIME ZONE 'America/New_York'"


async def main():
    a = MarketIntelligenceAgent()
    r = await a._handle_anticipation_query(AgentRequest(task="anticipation", user_id=0, conversation_id="probe"))
    txt = str(getattr(r, "result", None) or getattr(r, "content", None) or r)
    lines = txt.splitlines()
    print("== /anticipation render: lines with 'overnight gaps':", sum("overnight gaps" in l for l in lines))
    print(txt[:2200])
    pool = await get_pool()
    async with pool.acquire() as c:
        cols = [x["column_name"] for x in await c.fetch(
            """SELECT column_name FROM information_schema.columns WHERE table_schema='public'
               AND table_name='mi_delayed_entry_trigger' AND (data_type LIKE 'timestamp%' OR data_type='date')
               ORDER BY ordinal_position""")]
        print("== mi_delayed_entry_trigger time columns:", cols)
        for tc in cols:
            if tc == "created_at":
                continue
            v = await c.fetchval(f"""SELECT ((min("{tc}"))::text) FROM mi_delayed_entry_trigger
                                     WHERE realized_r_075 IS NOT NULL""")
            v2 = await c.fetchval(f"""SELECT ((min("{tc}"))::text) FROM mi_delayed_entry_trigger
                                      WHERE ep_adr20_dollar IS NOT NULL""")
            print(f"   min({tc}) where realized_r_075 set: {v} | where ep_adr20_dollar set: {v2}")


asyncio.run(main())
