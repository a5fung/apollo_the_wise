"""2026-11-19 — /trade and /why are book-aware (paper chat -> paper book, elsewhere -> live) and
/trade answers in the chat it was typed in. Companion to test_paper_chat_book_commands.py."""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from shared.models import AgentRequest
from tests.conftest import make_mock_pool
from tests.test_paper_chat_book_commands import MAIN, PAPER, _channel, _update  # noqa: F401


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))


def _wire_agent_db(monkeypatch):
    """Capture every mi_live_trades query (sql, params) the /trade and /why handlers run."""
    pool, conn = make_mock_pool()
    seen: list[tuple[str, tuple]] = []

    async def _fetchrow(sql, *args):
        if "mi_live_trades" in sql:
            seen.append((sql, args))
            if "MAX(d)" in sql:
                return {"d": None}
        return None

    async def _fetch(sql, *args):
        if "mi_live_trades" in sql:
            seen.append((sql, args))
        return []

    conn.fetchrow = _fetchrow
    conn.fetch = _fetch
    conn.fetchval = AsyncMock(return_value=None)
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map", AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date", AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record", AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    return seen


def _agent_call(method, task, context=None):
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    req = AgentRequest(task=task, user_id=1, conversation_id="t", context=context or {})
    return asyncio.run(getattr(MarketIntelligenceAgent(), method)(req))


def _bound_modes(seen):
    out = []
    for sql, args in seen:
        m = re.search(r"account_mode\s*=\s*(?:ANY\()?\$(\d+)", sql)
        assert m, f"mi_live_trades query with no bound account_mode:\n{sql}"
        out.append(args[int(m.group(1)) - 1])
    return out


@pytest.mark.parametrize("task", ["/trade FIGS", "/trade FIGS 2026-11-18"])
def test_trade_binds_the_book_on_every_trade_query(monkeypatch, task):
    seen = _wire_agent_db(monkeypatch)
    res = _agent_call("_handle_trade_query", task, {"book": "paper"})
    assert seen and {tuple(m) for m in _bound_modes(seen)} == {("paper",)}
    assert "PAPER" in res.result and "no paper trade row" in res.result
    seen.clear()
    res = _agent_call("_handle_trade_query", task)             # no context -> BOTH books, bound explicitly
    assert seen and {tuple(m) for m in _bound_modes(seen)} == {("live", "paper")}
    assert "PAPER" not in res.result


def test_why_binds_the_book_on_every_trade_query(monkeypatch):
    for ctx, mode in (({"book": "paper"}, ("paper",)), ({}, ("live", "paper"))):
        seen = _wire_agent_db(monkeypatch)
        _agent_call("_handle_why_query", "/why FIGS", ctx)                 # no date: latest-day arm + trade arm
        _agent_call("_handle_why_query", "/why FIGS 2026-11-18", ctx)      # dated: trade arm
        assert len(seen) >= 2 and {tuple(m) for m in _bound_modes(seen)} == {mode}


def test_why_empty_answer_is_badged_paper_only_in_the_paper_book(monkeypatch):
    _wire_agent_db(monkeypatch)
    res = _agent_call("_handle_why_query", "/why FIGS 2026-11-18", {"book": "paper", "reply_in_place": True})
    assert "PAPER" in res.result and "no alert / trade / audit events" in res.result
    res = _agent_call("_handle_why_query", "/why FIGS 2026-11-18", {"reply_in_place": True})
    assert "PAPER" not in res.result and "no alert / trade / audit events" in res.result


def _one_trade(monkeypatch):
    """A /trade fixture that finds a row, so the delivery branch runs. Returns the list of direct
    Telegram POSTs the handler attempted (the network is stubbed to fail)."""
    pool, conn = make_mock_pool()
    row = {"id": 1, "ticker": "FIGS", "alert_date": date(2026, 11, 18), "status": "filled",
           "entry_price": 10.0, "stop_price": 9.0, "entry_shares": 10, "remaining_shares": 10,
           "total_pnl": 0.0, "hold_days": 1, "exits": None,
           "closed_at": datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc), "entry_attempt": 1}
    conn.fetchrow = AsyncMock(return_value=row)
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map", AsyncMock(return_value={}))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    posts = []

    class _NoNet:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            posts.append((a, k))
            raise RuntimeError("no network in tests")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _NoNet)
    return posts


def test_trade_in_place_returns_the_text_and_never_posts_directly(monkeypatch):
    posts = _one_trade(monkeypatch)
    res = _agent_call("_handle_trade_query", "/trade FIGS", {"reply_in_place": True, "book": "paper"})
    assert "trade #1" in res.result and "tradingview.com" in res.result and "PAPER" in res.result
    assert posts == [], "in-place /trade must not POST to Telegram itself"


def test_trade_without_the_flag_keeps_the_direct_post_path(monkeypatch):
    """The keyword router ('FIGS trade') and the chat assistant never set reply_in_place: they keep
    the agent's own direct post (with the chart button), unchanged."""
    posts = _one_trade(monkeypatch)
    res = _agent_call("_handle_trade_query", "/trade FIGS")
    assert posts, "the unflagged path must still attempt the direct Telegram post"
    assert "trade #1" in res.result      # the post failed here -> the body is returned


async def _dispatched_context(cmd, chat_id):
    ch = _channel()
    ch._reply = AsyncMock()
    upd = _update(chat_id)
    upd.message.text = f"{cmd} FIGS"
    await ch._dispatch_market_slash(upd, SimpleNamespace(args=["FIGS"]))
    return ch._post_market_task.await_args.kwargs["context"]


@pytest.mark.asyncio
async def test_dispatch_stamps_book_and_in_place_only_for_trade_and_why():
    c = await _dispatched_context("/trade", PAPER)
    assert c["book"] == "paper" and c["reply_in_place"] is True
    c = await _dispatched_context("/trade", MAIN)
    assert "book" not in c and c["reply_in_place"] is True
    c = await _dispatched_context("/why", PAPER)
    assert c["book"] == "paper" and c["reply_in_place"] is True
    c = await _dispatched_context("/why", MAIN)
    assert "book" not in c and "reply_in_place" not in c      # /why elsewhere: unchanged
    c = await _dispatched_context("/regime", PAPER)
    assert "book" not in c and "reply_in_place" not in c


def test_paper_summary_empty_state_says_no_paper_positions():
    from agents.market_intelligence import agent as agent_mod
    from agents.market_intelligence import execution_client
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"winners": 0, "losers": 0, "realized": 0})

    async def go(task):
        with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)), \
             patch.object(execution_client, "get_account", new=AsyncMock(return_value={"equity": 1.0})):
            return await MarketIntelligenceAgent()._handle_trades_detail(
                AgentRequest(task=task, user_id=1, conversation_id="t"))

    assert "No paper positions." in asyncio.run(go("/trades_detail summary 2026-11-19 paper")).result
    live = asyncio.run(go("/trades_detail summary 2026-11-19")).result
    assert "No open positions." in live and "No paper positions." not in live


# ── outside the paper chat BOTH books are read, each row tagged ──────────────

def _row(mode, rid, d=date(2026, 11, 18)):
    return {"id": rid, "ticker": "CAKE", "alert_date": d, "status": "filled", "entry_price": 10.0,
            "stop_price": 9.0, "entry_shares": 10, "remaining_shares": 10, "total_pnl": 0.0,
            "hold_days": 1, "exits": None, "closed_at": None, "entry_attempt": 1, "account_mode": mode,
            "skip_reason": None, "orb_high": 10.0, "orb_low": 9.5, "proposed_at": None,
            "confirmed_at": None, "entry_order_id": None}


def _db_with_rows(monkeypatch, rows):
    """A fake DB that honours `account_mode = ANY($n)` against `rows`, newest id first."""
    pool, conn = make_mock_pool()

    async def _fetchrow(sql, *args):
        if "mi_live_trades" not in sql:
            return None
        m = re.search(r"account_mode\s*=\s*ANY\(\$(\d+)\)", sql)
        assert m, f"unbound account_mode:\n{sql}"
        modes = args[int(m.group(1)) - 1]
        hit = sorted((r for r in rows if r["account_mode"] in modes), key=lambda r: -r["id"])
        if "MAX(d)" in sql:
            return {"d": hit[0]["alert_date"] if hit else None}
        return hit[0] if hit else None

    conn.fetchrow = _fetchrow
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map", AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date", AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record", AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
                        AsyncMock(return_value=None))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)


def test_main_chat_trade_finds_a_paper_only_name_and_tags_it_paper(monkeypatch):
    _db_with_rows(monkeypatch, [_row("paper", 7)])
    res = _agent_call("_handle_trade_query", "/trade CAKE", {"reply_in_place": True})     # no book stamp
    assert "trade #7" in res.result and "📄 PAPER " in res.result and "LIVE" not in res.result


def test_paper_chat_trade_is_paper_only(monkeypatch):
    _db_with_rows(monkeypatch, [_row("live", 9), _row("paper", 7)])
    res = _agent_call("_handle_trade_query", "/trade CAKE", {"book": "paper", "reply_in_place": True})
    assert "trade #7" in res.result and "trade #9" not in res.result and "not real money" in res.result
    _db_with_rows(monkeypatch, [_row("live", 9)])
    res = _agent_call("_handle_trade_query", "/trade CAKE", {"book": "paper", "reply_in_place": True})
    assert "no paper trade row" in res.result


def test_main_chat_trade_with_both_books_dated_tags_each_row(monkeypatch):
    rows = [_row("live", 9), _row("paper", 7)]
    _db_with_rows(monkeypatch, rows)
    live = _agent_call("_handle_trade_query", "/trade CAKE 2026-11-18", {"reply_in_place": True}).result
    assert "trade #9" in live and "💰 LIVE-$ " in live          # newest id first; its own book's tag
    _db_with_rows(monkeypatch, rows[1:])
    paper = _agent_call("_handle_trade_query", "/trade CAKE 2026-11-18", {"reply_in_place": True}).result
    assert "trade #7" in paper and "📄 PAPER " in paper


def test_main_chat_why_reads_a_paper_row_and_names_its_book(monkeypatch):
    _db_with_rows(monkeypatch, [_row("paper", 7)])
    res = _agent_call("_handle_why_query", "/why CAKE 2026-11-18", {"reply_in_place": True}).result
    assert "Book: 📄 PAPER" in res and "no mi_live_trades row" not in res
    _db_with_rows(monkeypatch, [_row("live", 9)])
    res = _agent_call("_handle_why_query", "/why CAKE 2026-11-18", {"reply_in_place": True}).result
    assert "Book:" not in res          # a live row keeps the #716 layout (no book line; live is the default)
    _db_with_rows(monkeypatch, [_row("live", 9)])
    res = _agent_call("_handle_why_query", "/why CAKE 2026-11-18", {"book": "paper", "reply_in_place": True}).result
    assert "Book:" not in res          # paper chat: paper-only, and a live row is invisible there


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd", ["/timestop", "/partialnow"])
async def test_manual_overrides_refuse_in_the_paper_chat_and_act_elsewhere(cmd):
    # His ruling 2026-11-19: paper trades run on their own, so the real-money overrides refuse
    # in the paper chat (no task reaches the market agent) and still work in the main chat.
    ch = _channel()
    upd = _update(PAPER)
    upd.message.text = f"{cmd} FIGS"
    await ch._dispatch_market_slash(upd, SimpleNamespace(args=["FIGS"]))
    ch._post_market_task.assert_not_awaited()
    assert "not available in the paper chat" in upd.message.reply_text.await_args.args[0]

    ch = _channel()
    upd = _update(MAIN)
    upd.message.text = f"{cmd} FIGS"
    await ch._dispatch_market_slash(upd, SimpleNamespace(args=["FIGS"]))
    ch._post_market_task.assert_awaited_once()
