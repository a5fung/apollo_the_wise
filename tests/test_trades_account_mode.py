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

    _assert_every_live_trades_query_bound_to(conn, "live")


def _assert_every_live_trades_query_bound_to(conn, mode):
    """Every mi_live_trades query filters account_mode with a BOUND parameter whose value is `mode`
    (2026-11-19: the book became a parameter so the paper chat reads the paper book through the SAME
    queries; a literal 'live' no longer appears, so the invariant is checked on the bound value)."""
    calls = list(conn.fetch.await_args_list) + list(conn.fetchrow.await_args_list)
    live_calls = [c for c in calls if "mi_live_trades" in c.args[0]]
    assert live_calls, "expected the summary to query mi_live_trades"
    for c in live_calls:
        sql, params = c.args[0], c.args[1:]
        import re
        m = re.search(r"account_mode = \$(\d+)", sql)
        assert m, f"a mi_live_trades query is NOT filtered by account_mode:\n{sql}"
        assert params[int(m.group(1)) - 1] == mode, (
            f"account_mode bound to {params[int(m.group(1)) - 1]!r}, wanted {mode!r}:\n{sql}")


def _run_detail(task):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from shared.models import AgentRequest

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"winners": 0, "losers": 0, "realized": 0})

    async def run():
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_position", new=AsyncMock(return_value=None)), \
             patch.object(execution_client, "get_account", new=AsyncMock(return_value={"equity": 1000.0})):
            req = AgentRequest(task=task, user_id=1, conversation_id="t")
            return await _make_agent()._handle_trades_detail(req)

    return asyncio.run(run()), conn


def test_trades_summary_paper_reads_only_the_paper_book_and_says_so():
    resp, conn = _run_detail("/trades_detail summary 2026-11-19 paper")
    assert resp.success
    _assert_every_live_trades_query_bound_to(conn, "paper")
    assert "PAPER" in resp.result and "not real money" in resp.result
    assert "LIVE (real money)" not in resp.result


def test_trades_summary_paper_without_a_date_still_paper():
    resp, conn = _run_detail("/trades_detail summary paper")
    _assert_every_live_trades_query_bound_to(conn, "paper")
    assert "not real money" in resp.result


def test_closed_and_skipped_views_follow_the_book():
    for view in ("closed", "skipped"):
        for task, mode in ((f"/trades_detail {view} 2026-11-19 paper", "paper"),
                           (f"/trades_detail {view} 2026-11-19", "live"),
                           (f"/trades_detail {view}", "live")):
            resp, conn = _run_detail(task)
            _assert_every_live_trades_query_bound_to(conn, mode)
            assert ("PAPER" in resp.result) == (mode == "paper"), (task, resp.result)


def test_default_summary_is_live_and_keeps_its_live_badge():
    resp, conn = _run_detail("/trades_detail summary 2026-11-19")
    _assert_every_live_trades_query_bound_to(conn, "live")
    assert "LIVE (real money)" in resp.result and "PAPER" not in resp.result


def test_ticker_view_in_paper_book_is_paper_rows_only():
    from agents.market_intelligence import constants
    with patch.object(constants, "LIVE_TRADING_ENABLED", True):
        resp, conn = _run_detail("/trades_detail FIGS 2026-11-19 paper")
    sqls = [(c.args[0], c.args[1:]) for c in conn.fetch.await_args_list]
    ticker_sql = [(q, a) for q, a in sqls if "ticker = $" in q][0]
    assert "paper" in ticker_sql[1] and "FIGS" in ticker_sql[1]
    assert "IN ('live', 'paper')" not in ticker_sql[0]
    tot = [c for c in conn.fetchrow.await_args_list if "mi_live_trades" in c.args[0]]
    assert tot and all("account_mode = 'paper'" in c.args[0] for c in tot)
    assert "paper" in resp.result.lower() and "FIGS" in resp.result
