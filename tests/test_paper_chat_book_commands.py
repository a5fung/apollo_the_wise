"""2026-11-19 — a command typed in the Apollo Paper chat answers from the PAPER book.

Operator: typing /trades in the paper chat returned the LIVE book (real-money badge, live totals).
Routing: update.effective_chat.id == int(TELEGRAM_PAPER_CHAT_ID) -> paper; any other chat, or the
variable unset / blank / malformed -> live, never an exception. The book rides to the market agent as
a trailing `paper` token on the /trades_detail task and through every button's callback_data.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from channels import telegram as tg
from channels.telegram import TelegramChannel
from tests.conftest import fake_httpx_client

PAPER = -5382801675
MAIN = 111222333


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))


def _channel():
    ch = TelegramChannel.__new__(TelegramChannel)
    ch._secrets = SimpleNamespace(telegram_allowed_user_ids=[42], internal_api_secret="s")
    ch._post_market_task = AsyncMock(return_value="body")
    ch._reply_with_fallback = AsyncMock()
    return ch


def _update(chat_id):
    message = MagicMock()
    message.reply_text = AsyncMock()
    return SimpleNamespace(effective_user=SimpleNamespace(id=42),
                           effective_chat=SimpleNamespace(id=chat_id), message=message)


# ── routing ──────────────────────────────────────────────────────────────────

def test_paper_chat_is_paper_other_chat_is_live():
    assert tg.book_for_chat(PAPER) == "paper"
    assert tg.book_for_chat(MAIN) == "live"
    assert tg.book_for_chat(None) == "live"
    assert tg.book_for_update(SimpleNamespace(effective_chat=None)) == "live"


@pytest.mark.parametrize("raw", ["", "   ", "abc", "'-5382801675'", "-53.8"])
def test_unset_or_malformed_env_is_live_and_never_raises(monkeypatch, raw):
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", raw)
    assert tg.book_for_chat(PAPER) == "live"
    monkeypatch.delenv("TELEGRAM_PAPER_CHAT_ID")
    assert tg.book_for_chat(PAPER) == "live"


def test_env_name_matches_the_market_agent_sender():
    from agents.market_intelligence.constants import PAPER_CHAT_ENV
    assert tg.PAPER_CHAT_ENV == PAPER_CHAT_ENV


# ── /trades ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trades_in_paper_chat_asks_for_the_paper_book_with_paper_buttons():
    ch, upd = _channel(), _update(PAPER)
    await ch._handle_trades_command(upd, SimpleNamespace(args=[]))
    task = ch._post_market_task.await_args.args[0]
    assert task.startswith("/trades_detail summary ") and task.endswith(" paper")
    markup = ch._reply_with_fallback.await_args.kwargs["reply_markup"]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data and all(d.endswith(":paper") for d in data)
    assert all(len(d.encode()) <= 64 for d in data)


@pytest.mark.asyncio
async def test_trades_in_other_chat_is_unchanged_live():
    ch, upd = _channel(), _update(MAIN)
    await ch._handle_trades_command(upd, SimpleNamespace(args=[]))
    task = ch._post_market_task.await_args.args[0]
    assert "paper" not in task
    markup = ch._reply_with_fallback.await_args.kwargs["reply_markup"]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data and not any("paper" in d for d in data)


@pytest.mark.asyncio
async def test_trades_ticker_form_follows_the_chat():
    ch = _channel()
    await ch._handle_trades_command(_update(PAPER), SimpleNamespace(args=["figs"]))
    task = ch._post_market_task.await_args.args[0]
    assert task.endswith(" paper") and " FIGS " in task
    ch2 = _channel()
    await ch2._handle_trades_command(_update(MAIN), SimpleNamespace(args=["figs"]))
    assert "paper" not in ch2._post_market_task.await_args.args[0]


# ── callback round trip ──────────────────────────────────────────────────────

def _query(data, chat_id):
    q = MagicMock()
    q.from_user = SimpleNamespace(id=42)
    q.message = SimpleNamespace(chat_id=chat_id)
    q.edit_message_text = AsyncMock()
    q.data = data
    return q


async def _press(monkeypatch, data, chat_id):
    import httpx
    ch = _channel()
    fake = fake_httpx_client(json_body={"result": "ok"})
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market")
    q = _query(data, chat_id)
    await ch._handle_drill_down_callback(q, data)
    sent = fake.last_post["kwargs"]["json"]["task"]
    markup = q.edit_message_text.await_args.kwargs["reply_markup"]
    return sent, [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["trades:closed:2026-11-19:paper", "trades:skipped:paper",
                                  "trades:summary:paper"])
async def test_a_paper_button_stays_paper_and_re_emits_paper_buttons(monkeypatch, data):
    sent, buttons = await _press(monkeypatch, data, PAPER)
    assert sent.startswith("/trades_detail ") and sent.endswith(" paper")
    assert buttons and all(b.endswith(":paper") for b in buttons)
    # a dated token is always present so the trailing token is positional
    assert len(sent.split()) == 4


@pytest.mark.asyncio
async def test_a_live_button_in_the_main_chat_is_unchanged(monkeypatch):
    sent, buttons = await _press(monkeypatch, "trades:closed:2026-11-19", MAIN)
    assert sent == "/trades_detail closed 2026-11-19"
    assert not any("paper" in b for b in buttons)
    sent, _ = await _press(monkeypatch, "trades:skipped", MAIN)
    assert sent == "/trades_detail skipped"


@pytest.mark.asyncio
async def test_an_old_unsuffixed_button_pressed_in_the_paper_chat_is_paper(monkeypatch):
    sent, buttons = await _press(monkeypatch, "trades:closed:2026-11-19", PAPER)
    assert sent.endswith(" paper") and all(b.endswith(":paper") for b in buttons)


# ── help text ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_help_names_the_paper_chat_behaviour_and_drops_the_dead_paper_button():
    ch = _channel()
    ch._load_persona = AsyncMock(return_value=("Apollo", None))
    upd = _update(MAIN)
    await ch._handle_help(upd, SimpleNamespace(args=[]))
    text = upd.message.reply_text.await_args.args[0]
    assert "Apollo Paper chat" in text and "[Paper]" not in text
