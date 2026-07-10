"""#447 — the main /trades summary must show the REAL-MONEY (live) book, not a paper+live blend.
Pins that EVERY mi_live_trades query in `_build_summary` carries `account_mode = 'live'` — before
this, the realized total summed the dormant historical PAPER book too and read paper-dominated.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentName
    with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
        agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
        agent.agent_name = AgentName.MARKET_INTELLIGENCE
    return agent


def test_trades_summary_filters_account_mode_live():
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"winners": 0, "losers": 0, "realized": 0})

    async def run():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=AsyncMock(return_value=None)):
            req = AgentRequest(task="/trades_detail summary 2026-07-10", user_id=1, conversation_id="t")
            return await _make_agent()._handle_trades_detail(req)

    resp = asyncio.run(run())
    assert resp.success

    sqls = ([c.args[0] for c in conn.fetch.await_args_list]
            + [c.args[0] for c in conn.fetchrow.await_args_list])
    live_sqls = [s for s in sqls if "mi_live_trades" in s]
    assert live_sqls, "expected the summary to query mi_live_trades"
    for s in live_sqls:
        assert "account_mode = 'live'" in s, \
            f"a /trades summary mi_live_trades query is NOT filtered to the live book:\n{s}"
