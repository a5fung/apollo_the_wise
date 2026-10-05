"""2026-10-05 read-only: render /flags exactly as the operator sees it (#598 header check) + PURR's transition row."""
import asyncio
from agents.market_intelligence.agent import MarketIntelligenceAgent
from agents.market_intelligence.db import get_pool
from shared.models import AgentRequest


async def main():
    a = MarketIntelligenceAgent()
    r = await a._handle_flag_query(AgentRequest(task="flags", user_id=0, conversation_id="probe"))
    txt = getattr(r, "result", None) or getattr(r, "content", None) or str(r)
    print(str(txt)[:2500])
    pool = await get_pool()
    async with pool.acquire() as c:
        for row in await c.fetch("""SELECT LEFT(detail, 900) d FROM mi_audit_log WHERE event_type='flag_stage_transition'
                                    AND created_at > now() - interval '6 hours'"""):
            print("ROW:", row["d"])


asyncio.run(main())
