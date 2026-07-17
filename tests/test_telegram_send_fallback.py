"""send_telegram_message Markdown-400 fallback — offset-snippet diagnostics.

2026-07-16: the evening brief hit "can't find end of the entity starting at
byte offset 4205"; the audit row logged only chunk[:300], so the offending
section was undiagnosable. The 400 handler now decodes the UTF-8 byte offset
Telegram reports and logs the surrounding snippet in the warning + both audit
events. These tests pin: (1) the snippet is cut at the BYTE offset (multibyte
content before the culprit must not skew it), (2) the plain-text retry still
delivers, (3) a body without an offset degrades gracefully (empty snippet).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import briefing


class _Resp:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self.text = json.dumps(body or {})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status on failure response")


class _FakeClient:
    """httpx.AsyncClient stand-in returning queued responses per post()."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    def __call__(self, *a, **k):   # constructor shim: httpx.AsyncClient(timeout=15)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posts.append(json)
        return self._responses.pop(0)


def _entity_error_body(offset: int) -> dict:
    return {"ok": False, "error_code": 400,
            "description": f"Bad Request: can't parse entities: Can't find end "
                           f"of the entity starting at byte offset {offset}"}


@pytest.mark.asyncio
async def test_markdown_400_logs_snippet_at_byte_offset(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    # Multibyte content BEFORE the culprit: 50 emoji = 200 UTF-8 bytes but only
    # 50 chars — a char-indexed cut would land far from the marker.
    prefix = "🔥" * 50
    text = prefix + "CULPRIT_MARKER stray * here"
    offset = text.encode().index(b"CULPRIT_MARKER")

    fake = _FakeClient([_Resp(400, _entity_error_body(offset)), _Resp(200, {"ok": True})])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message(text)

    assert ok is True
    assert len(fake.posts) == 2                      # markdown try + plain retry
    assert "parse_mode" not in fake.posts[1]          # retry was plain text
    event, _summary, detail = audit.await_args.args[:3]
    assert event == "telegram_markdown_fallback"
    assert "CULPRIT_MARKER" in detail                 # the snippet names the culprit


@pytest.mark.asyncio
async def test_utf16_offset_interpretation_also_captured(monkeypatch):
    """If Telegram's reported offset is UTF-16 code units (its documented
    entity convention), the UTF-8-byte window lands deep in preceding emoji and
    misses the culprit — the u16 window must still capture it."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    prefix = "🔥" * 80                      # 160 UTF-16 units, 320 UTF-8 bytes
    text = prefix + "CULPRIT16 stray * here"
    utf16_offset = len(prefix.encode("utf-16-le")) // 2   # marker at unit 160

    fake = _FakeClient([_Resp(400, _entity_error_body(utf16_offset)), _Resp(200, {"ok": True})])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message(text)

    assert ok is True
    detail = audit.await_args.args[2]
    assert "CULPRIT16" in detail            # the u16 window names the culprit


@pytest.mark.asyncio
async def test_markdown_400_without_offset_degrades_gracefully(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")

    fake = _FakeClient([
        _Resp(400, {"ok": False, "error_code": 400, "description": "Bad Request: message is too long"}),
        _Resp(200, {"ok": True}),
    ])
    audit = AsyncMock()
    with patch.object(briefing.httpx, "AsyncClient", fake), \
         patch.object(briefing, "log_audit_event", audit):
        ok = await briefing.send_telegram_message("*hello*")

    assert ok is True
    detail = audit.await_args.args[2]
    assert "offset_snippet=''" in detail              # no offset → empty snippet, no crash
