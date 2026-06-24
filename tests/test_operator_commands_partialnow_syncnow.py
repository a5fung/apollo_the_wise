"""Regression tests for /partialnow + /syncnow operator commands (#138, 2026-05-28).

Post-IBM-cascade follow-up. Pre-fix: operator had to manually invoke
partial-exit / sync-positions via `docker exec python -c`, which
bypassed the credential bootstrap (root cause of 2026-05-27 mass-close).
These commands route through the agent process so #137 safety guards
stay intact.

Tests pin: parse paths, defensive checks (already-partial'd, no-position,
mode arg), audit emission, error formatting. Broker mutations are mocked
— this isn't a sync_positions test, just the operator-command wiring.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _request(text):
    req = MagicMock()
    req.task = text
    return req


class _FakeAgent:
    """Bare agent shape — just enough to call the handler methods."""
    def _ok(self, request, *, result):
        return MagicMock(ok=True, result=result)


@pytest.mark.asyncio
async def test_partialnow_no_ticker_returns_usage():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    agent = _FakeAgent()
    # Borrow the unbound method
    handler = MarketIntelligenceAgent._handle_partial_now_command
    resp = await handler(agent, _request("/partialnow"))
    assert "Usage" in resp.result
    assert "partialnow" in resp.result.lower()


@pytest.mark.asyncio
async def test_partialnow_no_open_position():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import db as db_mod
    from agents.market_intelligence import trading_calendar
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)

    fake_now = datetime(2026, 5, 28, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    agent = _FakeAgent()
    with patch.object(agent_mod, "datetime") as dt_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True), \
         patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        dt_mock.now.return_value = fake_now
        resp = await MarketIntelligenceAgent._handle_partial_now_command(
            agent, _request("/partialnow AAPL"),
        )
    assert "No open filled position" in resp.result
    assert "AAPL" in resp.result


@pytest.mark.asyncio
async def test_partialnow_skips_already_partial():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import db as db_mod
    from agents.market_intelligence import trading_calendar
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "id": 1, "ticker": "IBM", "remaining_shares": 100,
        "partial_taken": True, "entry_price": 250.0, "stop_price": 245.0,
        "signal_type": "magna53", "account_mode": "paper",
    })

    fake_now = datetime(2026, 5, 28, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    agent = _FakeAgent()
    with patch.object(agent_mod, "datetime") as dt_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True), \
         patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        dt_mock.now.return_value = fake_now
        resp = await MarketIntelligenceAgent._handle_partial_now_command(
            agent, _request("/partialnow IBM"),
        )
    assert "partial_taken=TRUE" in resp.result or "already" in resp.result.lower()


@pytest.mark.asyncio
async def test_partialnow_blocks_after_hours_without_confirm():
    """#141 guard: outside 9:30-16:50 ET, /partialnow without CONFIRM returns
    a warning explaining the after-hours Alpaca paper risk class."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import trading_calendar

    agent = _FakeAgent()
    with patch.object(trading_calendar, "is_market_hours_now_et", return_value=False):
        resp = await MarketIntelligenceAgent._handle_partial_now_command(
            agent, _request("/partialnow IBM"),
        )
    assert "outside safe window" in resp.result.lower()
    assert "CONFIRM" in resp.result
    assert "IBM" in resp.result


@pytest.mark.asyncio
async def test_partialnow_after_hours_with_confirm_proceeds():
    """#141 guard: append CONFIRM, get past the gate; then normal execution path."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import trading_calendar
    from agents.market_intelligence import db as db_mod
    from agents.market_intelligence.broker import order_manager
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "id": 99, "ticker": "IBM", "remaining_shares": 60,
        "partial_taken": False, "entry_price": 250.0, "stop_price": 245.0,
        "signal_type": "magna53", "account_mode": "paper",
    })

    agent = _FakeAgent()
    with patch.object(trading_calendar, "is_market_hours_now_et", return_value=False), \
         patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(order_manager, "execute_partial_exit", new=AsyncMock(return_value=True)), \
         patch.object(db_mod, "log_audit_event", new=AsyncMock()):
        resp = await MarketIntelligenceAgent._handle_partial_now_command(
            agent, _request("/partialnow IBM CONFIRM"),
        )
    assert "Partial exit submitted" in resp.result


@pytest.mark.asyncio
async def test_partialnow_executes_and_returns_summary():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import db as db_mod
    from agents.market_intelligence import trading_calendar
    from agents.market_intelligence.broker import order_manager
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "id": 42, "ticker": "AAPL", "remaining_shares": 90,
        "partial_taken": False, "entry_price": 200.0, "stop_price": 195.0,
        "signal_type": "magna53", "account_mode": "paper",
    })

    fake_now = datetime(2026, 5, 28, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    agent = _FakeAgent()
    with patch.object(agent_mod, "datetime") as dt_mock, \
         patch.object(trading_calendar, "is_market_hours_now_et", return_value=True), \
         patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(order_manager, "execute_partial_exit", new=AsyncMock(return_value=True)), \
         patch.object(db_mod, "log_audit_event", new=AsyncMock()) as audit_mock:
        dt_mock.now.return_value = fake_now
        resp = await MarketIntelligenceAgent._handle_partial_now_command(
            agent, _request("/partialnow AAPL"),
        )

    assert "Partial exit submitted" in resp.result
    assert "AAPL" in resp.result
    assert "30" in resp.result  # 90 // 3 = 30 shares
    assert audit_mock.called


@pytest.mark.asyncio
async def test_syncnow_no_discrepancies():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import db as db_mod

    agent = _FakeAgent()
    with patch.object(order_manager, "sync_positions", new=AsyncMock(return_value=[])), \
         patch.object(db_mod, "log_audit_event", new=AsyncMock()):
        resp = await MarketIntelligenceAgent._handle_sync_now_command(
            agent, _request("/syncnow"),
        )
    assert "no DB↔broker discrepancies" in resp.result


@pytest.mark.asyncio
async def test_syncnow_with_discrepancies():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import db as db_mod

    agent = _FakeAgent()
    discrepancies = ["AAPL stop_order_id mismatch", "IBM position qty diverged"]
    with patch.object(order_manager, "sync_positions",
                      new=AsyncMock(return_value=discrepancies)), \
         patch.object(db_mod, "log_audit_event", new=AsyncMock()):
        resp = await MarketIntelligenceAgent._handle_sync_now_command(
            agent, _request("/syncnow"),
        )
    assert "2 discrepancies" in resp.result
    assert "AAPL" in resp.result
    assert "IBM" in resp.result
    assert "Safety guard intact" in resp.result


@pytest.mark.asyncio
async def test_syncnow_mode_arg_routes_to_single_mode():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence.broker import order_manager
    from agents.market_intelligence import db as db_mod

    agent = _FakeAgent()
    with patch.object(order_manager, "_sync_positions_for_mode",
                      new=AsyncMock(return_value=[])) as mode_mock, \
         patch.object(order_manager, "sync_positions",
                      new=AsyncMock(return_value=[])) as all_mock, \
         patch.object(db_mod, "log_audit_event", new=AsyncMock()):
        resp = await MarketIntelligenceAgent._handle_sync_now_command(
            agent, _request("/syncnow paper"),
        )
    # Per-mode path used; all-modes path NOT used
    mode_mock.assert_called_once_with("paper")
    all_mock.assert_not_called()
    assert "paper" in resp.result


@pytest.mark.parametrize("raw, expected", [
    ("/syncnow", "/syncnow"),            # clean → unchanged
    ("/SyncNow", "/syncnow"),            # case folded
    ("/syncnow​", "/syncnow"),      # trailing zero-width space (the 2026-06-04 bug)
    ("​/syncnow", "/syncnow"),      # leading zero-width
    ("/syncnow@ApolloBot", "/syncnow"),  # @botname suffix (group-chat form)
    ("/partialnow", "/partialnow"),
    ("/9m", "/9m"),                      # digits preserved
    ("/ur", "/ur"),                      # short command preserved
])
def test_normalize_slash_cmd_maps_to_dispatch_key(raw, expected):
    """A valid command must never be silently rejected by an invisible char /
    @botname / case mismatch — _normalize_slash_cmd folds them to the canonical
    dispatch key. Regression for 2026-06-04 '/syncnow → Unknown command' while
    /syncnow WAS in the Available list (an invisible char made cmd != the key)."""
    from agents.market_intelligence.agent import _normalize_slash_cmd
    assert _normalize_slash_cmd(raw) == expected


# ── Dispatch-routing regression (#184c, 2026-06-24) ──────────────────────────
# The normalize tests above and the handler tests at the top of this file both
# stop SHORT of the actual gap that produced "Unknown command": neither drives
# the real `_handle_slash_command` dispatch DICT. So a removed dispatch entry, a
# key/method name mismatch, or a normalize regression that breaks /syncnow
# specifically would all pass the existing suite yet still fall through to
# "Unknown command" in production. These tests pin the end-to-end dispatch:
# /syncnow (clean + the 2026-06-04 invisible-char variants) must LAND on
# _handle_sync_now_command and must NEVER return "Unknown command".

@pytest.mark.parametrize("raw", [
    "/syncnow",            # clean
    "/SyncNow",            # case folded
    "/syncnow​",      # trailing zero-width space (the 2026-06-04 bug)
    "​/syncnow",      # leading zero-width
    "/syncnow@ApolloBot",  # @botname suffix (group-chat form)
    "/syncnow paper",      # mode arg still resolves the bare command key
])
@pytest.mark.asyncio
async def test_syncnow_dispatches_to_handler_not_unknown(raw):
    """The real `_handle_slash_command` dispatch dict must route /syncnow (and
    its invisible-char / @botname / case / mode-arg forms) to
    _handle_sync_now_command — never fall through to 'Unknown command'.

    Regression for 2026-06-04: /syncnow WAS wired in all three places yet
    returned 'Unknown command' because the parsed token != the dispatch key.
    Pins routing, not just the normalizer-in-isolation (#184c)."""
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    # A real instance is required: _handle_slash_command builds its dispatch dict
    # from `self._handle_*` for EVERY command, so a bare fake agent can't even
    # construct the table. We patch only the target handler on this instance.
    agent = MarketIntelligenceAgent()
    sentinel = object()
    with patch.object(
        agent, "_handle_sync_now_command",
        new=AsyncMock(return_value=sentinel),
    ) as handler_mock:
        resp = await agent._handle_slash_command(_request(raw))
    assert resp is sentinel, "/syncnow did not route to _handle_sync_now_command"
    assert handler_mock.await_count == 1


@pytest.mark.asyncio
async def test_syncnow_routes_through_execute_task_slash_fast_path():
    """A leading '/' must take the slash fast-path in execute_task and reach
    _handle_slash_command (the same path the orchestrator HTTP POST exercises),
    so /syncnow can never be captured by an earlier NLP keyword rule."""
    from unittest.mock import AsyncMock, patch
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest

    agent = MarketIntelligenceAgent()
    sentinel = object()
    with patch.object(
        agent, "_handle_slash_command",
        new=AsyncMock(return_value=sentinel),
    ) as slash_mock:
        resp = await agent.execute_task(
            AgentRequest(task="/syncnow", user_id=1, conversation_id="t"),
        )
    assert resp is sentinel
    slash_mock.assert_awaited_once()
