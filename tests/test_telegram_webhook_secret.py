"""#312 review, finding 8 (2026-11-07) — the Telegram webhook route accepts only Telegram's own POSTs.

`POST /telegram/webhook` took any body and handed it to the bot application; the allowlist gates
then checked the user id THE UPDATE CLAIMED. So any process that could reach orchestrator:8000 on
the compose network could post a forged `callback_query` with his user id and press any button —
the ladder's Demote included. Now `set_webhook` registers a `secret_token` (derived from
INTERNAL_API_SECRET, no new secret to provision), Telegram echoes it in
`X-Telegram-Bot-Api-Secret-Token` on every update, and the route drops a POST without it before
parsing the body. The route is mounted in polling mode too, where no legitimate POST exists.

Red on fa36a4fd: the first two tests (a POST without the header was processed, 200).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from channels import webhooks

SECRET = "f" * 64
HEADER = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture
def client(monkeypatch):
    app_stub = SimpleNamespace(bot=None, process_update=AsyncMock())
    webhooks.configure(app_stub, None)
    monkeypatch.setattr(webhooks, "get_secrets",
                        lambda: SimpleNamespace(telegram_webhook_secret_token=SECRET))
    with TestClient(webhooks.app) as c:
        yield c, app_stub


def test_a_post_without_telegrams_secret_header_is_dropped(client):
    c, app_stub = client
    r = c.post("/telegram/webhook", json={"update_id": 1})
    assert r.status_code == 403 and r.json() == {"ok": False, "error": "forbidden"}
    assert app_stub.process_update.call_count == 0


def test_a_post_with_the_wrong_secret_is_dropped(client):
    c, app_stub = client
    r = c.post("/telegram/webhook", json={"update_id": 1}, headers={HEADER: "e" * 64})
    assert r.status_code == 403
    assert app_stub.process_update.call_count == 0


def test_telegrams_own_post_is_processed(client):
    c, app_stub = client
    r = c.post("/telegram/webhook", json={"update_id": 1}, headers={HEADER: SECRET})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert app_stub.process_update.call_count == 1
    assert app_stub.process_update.call_args.args[0].update_id == 1


@pytest.mark.asyncio
async def test_set_webhook_registers_the_secret_token():
    from channels.telegram import TelegramChannel
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._secrets = SimpleNamespace(telegram_webhook_secret_token=SECRET)
    channel._app = SimpleNamespace(bot=SimpleNamespace(set_webhook=AsyncMock()))
    channel._register_commands = AsyncMock()
    await channel.set_webhook("https://apollo.example/")
    kwargs = channel._app.bot.set_webhook.await_args.kwargs
    assert kwargs["secret_token"] == SECRET
    assert kwargs["url"] == "https://apollo.example/" and "callback_query" in kwargs["allowed_updates"]


def test_the_secret_is_derived_from_the_internal_api_secret_unless_overridden(monkeypatch):
    from shared.secrets import Secrets
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-one")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    a = Secrets().telegram_webhook_secret_token
    assert len(a) == 64 and all(ch in "0123456789abcdef" for ch in a)   # Telegram: 1-256 of [A-Za-z0-9_-]
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-two")
    assert Secrets().telegram_webhook_secret_token != a                 # bound to the secret, not a constant
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "explicit_override-1")
    assert Secrets().telegram_webhook_secret_token == "explicit_override-1"


# ── Re-review 2026-11-07 finding 3: a failed set_webhook at boot must not leave the bot deaf ──────────────────────
# With the secret check above, a set_webhook that FAILS at boot leaves Telegram posting to the OLD, secret-less
# registration and every update is dropped (/pause and the Demote button included) — before the check the old
# registration kept working. Prod runs POLLING (WEBHOOK_BASE_URL unset on the server, checked read-only 11-07), where
# this path never runs; in webhook mode the boot now retries and, still refused, FAILS LOUDLY instead of running deaf.

@pytest.mark.asyncio
async def test_boot_retries_set_webhook_and_a_later_success_is_enough(monkeypatch):
    from channels import telegram as tg
    monkeypatch.setattr(tg, "SET_WEBHOOK_RETRY_DELAYS", (0.0, 0.0), raising=False)
    channel = SimpleNamespace(set_webhook=AsyncMock(side_effect=[RuntimeError("telegram 502"),
                                                                 RuntimeError("telegram 502"), None]))
    await tg.set_webhook_or_fail(channel, "https://apollo.example/telegram/webhook")
    assert channel.set_webhook.await_count == 3
    assert all(c.args == ("https://apollo.example/telegram/webhook",) for c in channel.set_webhook.await_args_list)


@pytest.mark.asyncio
async def test_boot_fails_loudly_when_telegram_keeps_refusing_the_webhook(monkeypatch):
    from channels import telegram as tg
    monkeypatch.setattr(tg, "SET_WEBHOOK_RETRY_DELAYS", (0.0, 0.0), raising=False)
    channel = SimpleNamespace(set_webhook=AsyncMock(side_effect=RuntimeError("telegram 502")))
    with pytest.raises(RuntimeError, match="502"):
        await tg.set_webhook_or_fail(channel, "https://apollo.example/telegram/webhook")
    assert channel.set_webhook.await_count == tg.SET_WEBHOOK_ATTEMPTS == 3
