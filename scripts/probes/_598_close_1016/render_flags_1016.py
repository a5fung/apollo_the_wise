"""2026-10-16 #598 close, READ-ONLY: render /flags with the SAME handler the operator uses and print the
COILED header lines, then the flag-digest send rows. Writes nothing.
Run inside apollo-market (copy in with docker cp, unique name c598_render_flags.py):
    python /tmp/c598_render_flags.py
"""
import asyncio
from agents.market_intelligence.agent import MarketIntelligenceAgent
from agents.market_intelligence.db import get_pool
from shared.models import AgentRequest


async def main():
    a = MarketIntelligenceAgent()
    r = await a._handle_flag_query(AgentRequest(task="flags", user_id=0, conversation_id="probe"))
    txt = str(getattr(r, "result", None) or getattr(r, "content", None) or r)
    print(txt[:3500])
    print("HEADER_COILED_LINES:", [l for l in txt.splitlines() if "COILED" in l and "*" in l])
    print("OLD_HEADER_PRESENT:", "actionable setup" in txt)
    pool = await get_pool()
    async with pool.acquire() as c:
        for row in await c.fetch("""SELECT created_at, summary, LEFT(detail, 600) d FROM mi_audit_log
                                    WHERE event_type='flag_digest_sent' AND created_at > now() - interval '5 days'
                                    ORDER BY created_at"""):
            print("DIGEST:", row["created_at"], row["summary"], row["d"])


asyncio.run(main())
