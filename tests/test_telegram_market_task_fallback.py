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


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient — records the posted task, always returns
    a canned market-agent result so we can isolate the Telegram-send fallback."""

    last_json = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json, headers):
        _FakeAsyncClient.last_json = json
        return _FakeResp({"result": "Chip_Stocks members: NVDA, AMD_Corp, INTC"})


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
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

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
    assert _FakeAsyncClient.last_json["task"] == "/themes_lookup Chip_Stocks"


@pytest.mark.asyncio
async def test_themes_arg_both_sends_fail_no_unhandled_exception(monkeypatch):
    channel = _make_channel()
    update, context, message = _make_update(["Chip_Stocks"])
    message.reply_text = AsyncMock(side_effect=Exception("still 400"))

    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

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
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await channel._post_market_task("/themes_detail SUMMARY", user_id=42)
    assert result == "Chip_Stocks members: NVDA, AMD_Corp, INTC"
    assert _FakeAsyncClient.last_json["user_id"] == 42
