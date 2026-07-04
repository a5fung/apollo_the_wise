"""S3/F13 — the AgentRequest -> POST {url}/task -> reply boilerplate was hand-copied at
6+ sites in channels/telegram.py and had already diverged: the /themes-arg lookup
(_handle_themes_command) had NO plain-text retry on a Telegram Markdown-400 (e.g. an
underscore-heavy theme name) — a bad-Markdown reply fell straight into the generic
`except Exception` and surfaced a raw "Error: ..." instead of degrading gracefully like
/ideas already did. Fixed by extracting _post_market_task + _reply_with_fallback as the
single funnel; this pins the /themes-arg fix plus the two helpers' own contracts.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from telegram.constants import ParseMode

from channels.telegram import TelegramChannel
from tests.conftest import fake_httpx_client


def _make_channel():
    """A TelegramChannel with just the attributes _handle_themes_command /
    _post_market_task / _reply_with_fallback touch — bypasses __init__ (no live
    bot token needed)."""
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._secrets = SimpleNamespace(
        telegram_allowed_user_ids=[42],
        internal_api_secret="test-secret",
    )
    return channel


def _make_update(args):
    user = SimpleNamespace(id=42)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = SimpleNamespace(effective_user=user, message=message)
    context = SimpleNamespace(args=args)
    return update, context, message


def _fake_market_agent_client():
    """Stand-in for httpx.AsyncClient — always returns a canned market-agent
    result so we can isolate the Telegram-send fallback (simplify GROUP 6,
    2026-07-03 — was a hand-rolled class, now the shared `fake_httpx_client`
    builder). Payload is a full AgentResponse shape (simplify GROUP 3,
    2026-07-03: _post_market_task now delegates to core.router.call_agent,
    which parses the JSON via `AgentResponse(**response.json())` — a bare
    {"result": ...} dict fails that validation). The returned class records
    the posted task on `.last_post["kwargs"]["json"]`."""
    return fake_httpx_client(json_body={
        "request_id": "test-request-id",
        "agent": "market_intelligence",
        "success": True,
        "result": "Chip_Stocks members: NVDA, AMD_Corp, INTC",
    })


@pytest.mark.asyncio
async def test_themes_arg_markdown_400_falls_back_to_plain_text(monkeypatch):
    channel = _make_channel()
    update, context, message = _make_update(["Chip_Stocks"])

    # First reply_text (Markdown) 400s like Telegram does on an unmatched `_`
    # in dynamic content; the plain-text retry (no parse_mode) must succeed.
    message.reply_text = AsyncMock(
        side_effect=[Exception("400 Bad Request: can't parse entities"), MagicMock()]
    )

    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    # core.router.get_agent_url is a separately-bound name (`from shared.registry import
    # get_agent_url`) — call_agent (which _post_market_task now delegates to) reads THIS
    # binding, so it needs its own patch (simplify GROUP 3, 2026-07-03).
    monkeypatch.setattr("core.router.get_agent_url", lambda name: "http://market-agent:9000")
    fake_client = _fake_market_agent_client()
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    await channel._handle_themes_command(update, context)

    # Graceful degrade, NOT the old "Error: ..." hard-fail behavior.
    assert message.reply_text.call_count == 2
    first_call, second_call = message.reply_text.call_args_list
    assert first_call.kwargs.get("parse_mode") == ParseMode.MARKDOWN
    assert "parse_mode" not in second_call.kwargs

    sent_text = second_call.args[0]
    assert "Chip_Stocks members" in sent_text
    assert not sent_text.startswith("Error:")

    # The market agent was actually asked for the lookup, not skipped.
    assert fake_client.last_post["kwargs"]["json"]["task"] == "/themes_lookup Chip_Stocks"


@pytest.mark.asyncio
async def test_themes_arg_both_sends_fail_no_unhandled_exception(monkeypatch):
    channel = _make_channel()
    update, context, message = _make_update(["Chip_Stocks"])
    message.reply_text = AsyncMock(side_effect=Exception("still 400"))

    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr("core.router.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_market_agent_client())

    # _reply_with_fallback only guards the FIRST attempt; a second failure is a
    # real (rare) delivery failure and should propagate, not be swallowed —
    # matching the pre-refactor /ideas contract (its own second reply_text call
    # was also unguarded).
    with pytest.raises(Exception, match="still 400"):
        await channel._handle_themes_command(update, context)
    assert message.reply_text.call_count == 2


@pytest.mark.asyncio
async def test_post_market_task_returns_none_when_agent_unregistered(monkeypatch):
    channel = _make_channel()
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: None)

    result = await channel._post_market_task("/themes_detail SUMMARY", user_id=42)
    assert result is None


@pytest.mark.asyncio
async def test_post_market_task_returns_result_text(monkeypatch):
    channel = _make_channel()
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr("core.router.get_agent_url", lambda name: "http://market-agent:9000")
    fake_client = _fake_market_agent_client()
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    result = await channel._post_market_task("/themes_detail SUMMARY", user_id=42)
    assert result == "Chip_Stocks members: NVDA, AMD_Corp, INTC"
    assert fake_client.last_post["kwargs"]["json"]["user_id"] == 42
