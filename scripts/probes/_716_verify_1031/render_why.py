"""#716 verify: render /why from the LIVE apollo-market container through the deployed handler, with
delivery stubbed so nothing is sent to Telegram (the handler's only side effect). Read-only."""
import asyncio, sys
from shared.models import AgentRequest
from agents.market_intelligence.agent import MarketIntelligenceAgent


class _Stub:
    async def _why_deliver(self, request, ticker, body):
        return body

    def _ok(self, request, result="", **kw):
        return result


async def main(tasks):
    for task in tasks:
        req = AgentRequest(task=task, user_id=0, conversation_id="verify-716")
        out = await MarketIntelligenceAgent._handle_why_query(_Stub(), req)
        print("=====", task)
        print(out if isinstance(out, str) else getattr(out, "result", out))


asyncio.run(main(sys.argv[1:]))
