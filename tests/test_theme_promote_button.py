"""One-tap theme-promote button (operator 2026-08-17: "is it possible make this even
easier like with one-click" — typing the long synthesis-alert theme name by hand).
Delivery-mechanism ONLY: promotion itself still runs through the existing
theme_engine.promote_candidate_by_name — THE LINE (never change what promotion does).

Three pieces under test:
  A. briefing.send_telegram_message gains an optional reply_markup, JSON-serialized,
     attached to exactly the LAST chunk of a split message.
  B. theme_synthesis.theme_candidate_short_id / build_synthesis_keyboard — the
     64-byte-safe identifier scheme a long theme name can't fit into callback_data.
  C. agent.py's internal-only /promotetheme_id resolves the id and promotes via the
     SAME promote_candidate_by_name the typed /promotetheme command calls.
  D. channels/telegram.py's tpromo: callback — authorization (the load-bearing piece)
     and the POST-to-market-agent + reply wiring.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agents.market_intelligence import agent as agent_mod
from agents.market_intelligence import briefing
from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te
from agents.market_intelligence import theme_synthesis as ts
from agents.market_intelligence.agent import MarketIntelligenceAgent, _render_promote_result

_LONG_NAME = "Resilient PNT: GPS-Alternative Timing & Navigation Infrastructure"


def _cand(name, tickers, thesis="thesis", source="rs_slope_synthesis"):
    return {"name": name, "tickers": list(tickers), "thesis": thesis, "source": source}


# ═══════════════════════════════════════════════════════════════════════════════════
# A — briefing.send_telegram_message: reply_markup wiring
# ═══════════════════════════════════════════════════════════════════════════════════

class _RecordingClient:
    """httpx.AsyncClient stand-in that records EVERY post() call (not just the last),
    so a split-message test can inspect which chunk(s) carried reply_markup."""
    posts: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _RecordingClient.posts.append(json)
        return SimpleNamespace(status_code=200, text="{}",
                                raise_for_status=lambda: None)


@pytest.fixture(autouse=True)
def _telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    _RecordingClient.posts = []


@pytest.mark.asyncio
async def test_existing_caller_with_no_markup_is_unchanged(monkeypatch):
    """An existing send_telegram_message(text) call — no reply_markup passed — must
    produce a byte-identical payload to before this param existed: no 'reply_markup'
    key at all."""
    monkeypatch.setattr(briefing.httpx, "AsyncClient", _RecordingClient)
    ok = await briefing.send_telegram_message("hello world")
    assert ok is True
    assert len(_RecordingClient.posts) == 1
    assert "reply_markup" not in _RecordingClient.posts[0]


@pytest.mark.asyncio
async def test_reply_markup_attached_and_json_serialized(monkeypatch):
    monkeypatch.setattr(briefing.httpx, "AsyncClient", _RecordingClient)
    markup = {"inline_keyboard": [[{"text": "✅ Promote", "callback_data": "tpromo:abc"}]]}
    ok = await briefing.send_telegram_message("short message", reply_markup=markup)
    assert ok is True
    payload = _RecordingClient.posts[0]
    assert "reply_markup" in payload
    # Telegram's raw Bot API takes reply_markup as a JSON-serialized STRING (the one
    # form valid under every request encoding) — not a bare nested dict.
    assert isinstance(payload["reply_markup"], str)
    assert json.loads(payload["reply_markup"]) == markup


@pytest.mark.asyncio
async def test_reply_markup_attaches_only_to_last_chunk_on_split(monkeypatch):
    monkeypatch.setattr(briefing.httpx, "AsyncClient", _RecordingClient)
    # Forces a 2-chunk split (>4000 chars, splittable at the "\n\n" boundary — see
    # send_telegram_message's own split logic).
    text = ("A" * 3000) + "\n\n" + ("B" * 3000)
    markup = {"inline_keyboard": [[{"text": "✅ Promote", "callback_data": "tpromo:abc"}]]}
    ok = await briefing.send_telegram_message(text, reply_markup=markup)
    assert ok is True
    assert len(_RecordingClient.posts) == 2, "expected the message to split into 2 chunks"
    assert "reply_markup" not in _RecordingClient.posts[0], "markup leaked onto an earlier chunk"
    assert "reply_markup" in _RecordingClient.posts[1], "markup missing from the LAST chunk"


# ═══════════════════════════════════════════════════════════════════════════════════
# B — theme_synthesis: short-id scheme + keyboard builder
# ═══════════════════════════════════════════════════════════════════════════════════

def test_short_id_deterministic_and_distinct():
    a1 = ts.theme_candidate_short_id("Rare & Orphan Biotech Re-Rating")
    a2 = ts.theme_candidate_short_id("Rare & Orphan Biotech Re-Rating")
    b = ts.theme_candidate_short_id("Drone Defense Spending")
    assert a1 == a2
    assert a1 != b


def test_keyboard_one_button_per_cohort_with_resolvable_callback_data():
    kept = [
        {"name": "Drone Defense Spending", "tickers": ["RCAT", "AVAV", "KTOS"],
         "thesis": "t", "confidence": "medium"},
        {"name": _LONG_NAME, "tickers": ["TRMB", "IRDM", "KVHI"],
         "thesis": "t2", "confidence": "high"},
    ]
    kb = ts.build_synthesis_keyboard(kept)
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    for row, cohort in zip(rows, kept):
        assert len(row) == 1
        btn = row[0]
        assert btn["callback_data"] == f"tpromo:{ts.theme_candidate_short_id(cohort['name'])}"


def test_callback_data_stays_under_telegrams_64_byte_cap():
    """THE trap the task names explicitly: the theme name itself is already over 64
    bytes, so callback_data must carry a short id, never the name."""
    kb = ts.build_synthesis_keyboard([{"name": _LONG_NAME, "tickers": ["A", "B", "C"],
                                        "thesis": "t", "confidence": "low"}])
    cb = kb["inline_keyboard"][0][0]["callback_data"]
    assert len(_LONG_NAME.encode("utf-8")) > 64, "fixture name should itself exceed the cap"
    assert len(cb.encode("utf-8")) <= 64, f"callback_data too long: {cb!r} ({len(cb.encode())} bytes)"


def test_button_label_uses_raw_name_not_html_escaped():
    """Button text is NOT parsed as HTML/Markdown by Telegram — running it through the
    format_synthesis_digest HTML-escape helpers would put a literal '&amp;' on the
    operator's button."""
    kb = ts.build_synthesis_keyboard(
        [{"name": "AI & Robotics <Phase 2>", "tickers": ["A", "B", "C"],
          "thesis": "t", "confidence": "low"}])
    text = kb["inline_keyboard"][0][0]["text"]
    assert "AI & Robotics" in text
    assert "&amp;" not in text


# ═══════════════════════════════════════════════════════════════════════════════════
# C — agent.py: /promotetheme_id resolution + shared render path
# ═══════════════════════════════════════════════════════════════════════════════════

def _request(text):
    req = MagicMock()
    req.task = text
    return req


class _FakeAgent:
    """Bare agent shape — matches tests/test_operator_commands_partialnow_syncnow.py's
    idiom: just enough to call unbound handler methods without MarketIntelligenceAgent's
    full __init__ cost."""
    def _ok(self, request, *, result):
        return SimpleNamespace(success=True, result=result, error=None)

    def _error(self, request, error):
        return SimpleNamespace(success=False, result=None, error=error)


@pytest.mark.asyncio
async def test_promotetheme_id_does_not_land_on_promotetheme_handler():
    """/promotetheme is a strict text-prefix of /promotetheme_id — pin that the two
    dispatch keys never collapse into each other (one regex/ordering slip away). Both
    handlers are mocked (not just the wrong one) so a real DB/secrets call is never
    triggered by whichever handler genuinely runs."""
    agent = MarketIntelligenceAgent()
    wrong_mock = AsyncMock(return_value=object())
    right_mock = AsyncMock(return_value=object())
    with patch.object(agent, "_handle_promotetheme", new=wrong_mock), \
         patch.object(agent, "_handle_promotetheme_id", new=right_mock):
        await agent._handle_slash_command(_request("/promotetheme_id abc123"))
    wrong_mock.assert_not_awaited()
    right_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_promotetheme_does_not_land_on_promotetheme_id_handler():
    agent = MarketIntelligenceAgent()
    wrong_mock = AsyncMock(return_value=object())
    right_mock = AsyncMock(return_value=object())
    with patch.object(agent, "_handle_promotetheme_id", new=wrong_mock), \
         patch.object(agent, "_handle_promotetheme", new=right_mock):
        await agent._handle_slash_command(_request("/promotetheme Some Name"))
    wrong_mock.assert_not_awaited()
    right_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_promotetheme_id_dispatches_not_unknown_command():
    """Mirrors test_syncnow_dispatches_to_handler_not_unknown — the real dispatch dict
    must route /promotetheme_id to _handle_promotetheme_id, never 'Unknown command'.
    This is internal-only (never a registered /-menu command, only the button sends
    it), so it's the one place a routing typo would go completely unnoticed."""
    agent = MarketIntelligenceAgent()
    sentinel = object()
    with patch.object(agent, "_handle_promotetheme_id",
                       new=AsyncMock(return_value=sentinel)) as handler_mock:
        resp = await agent._handle_slash_command(_request("/promotetheme_id abc123"))
    assert resp is sentinel
    handler_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_promotetheme_id_resolves_and_promotes_via_same_function(monkeypatch):
    """The tap must resolve the hash back to the exact candidate name and call the
    SAME promote_candidate_by_name the typed /promotetheme command uses — no
    reimplemented promotion logic."""
    cand = _cand("Rare & Orphan Biotech Re-Rating", ["RARE", "MIRM", "RGNX", "AGIO"])
    short_id = ts.theme_candidate_short_id(cand["name"])
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    promote_mock = AsyncMock(return_value={
        "status": "promoted", "name": cand["name"], "tickers": cand["tickers"],
        "n_members": 4, "canonicalized": False,
    })
    monkeypatch.setattr(te, "promote_candidate_by_name", promote_mock)

    agent = _FakeAgent()
    resp = await MarketIntelligenceAgent._handle_promotetheme_id(
        agent, _request(f"/promotetheme_id {short_id}"))

    promote_mock.assert_awaited_once()
    called_name = promote_mock.await_args.args[0]
    assert called_name == cand["name"]           # resolved to the EXACT candidate name
    assert resp.result == _render_promote_result(
        {"status": "promoted", "name": cand["name"], "tickers": cand["tickers"],
         "n_members": 4, "canonicalized": False}, cand["name"])
    assert "✅ Promoted" in resp.result
    assert "Rare & Orphan Biotech Re-Rating" in resp.result


@pytest.mark.asyncio
async def test_promotetheme_id_stale_hash_refuses_without_promoting(monkeypatch):
    """A hash with no match in the current 7-day window (aged out / superseded) must
    refuse cleanly — never guess, never crash, never call promote_candidate_by_name."""
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Some Other Cohort", ["X", "Y", "Z"])]))
    promote_mock = AsyncMock()
    monkeypatch.setattr(te, "promote_candidate_by_name", promote_mock)

    agent = _FakeAgent()
    resp = await MarketIntelligenceAgent._handle_promotetheme_id(
        agent, _request("/promotetheme_id deadbeef0000"))

    assert resp.success is True                  # a clean refusal, not an error
    assert "no longer in the 7-day shadow window" in resp.result
    promote_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_promotetheme_id_too_few_surfaces_plain_refusal(monkeypatch):
    """judge_theme_gap.py's too_few guard (< 3 merged members) must surface in plain
    words through the button path too, not fail silently."""
    cand = _cand("Tiny Cohort", ["A", "B"])
    short_id = ts.theme_candidate_short_id(cand["name"])
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    monkeypatch.setattr(te, "promote_candidate_by_name", AsyncMock(return_value={
        "status": "too_few", "name": "Tiny Cohort", "n_members": 2,
    }))

    agent = _FakeAgent()
    resp = await MarketIntelligenceAgent._handle_promotetheme_id(
        agent, _request(f"/promotetheme_id {short_id}"))

    assert resp.success is True
    assert "Tiny Cohort" in resp.result
    assert "need ≥3" in resp.result
    assert "Not promoted" in resp.result


@pytest.mark.asyncio
async def test_promotetheme_id_double_tap_is_harmless_and_says_so(monkeypatch):
    """Two taps on the SAME button: both must succeed with no exception, both must
    resolve to the SAME candidate name (no drift between calls), and the SECOND tap's
    message must NOT read as a fresh '✅ Promoted' — it must say the theme is already
    live, matching promote_candidate_by_name's own idempotent 'noop' status."""
    cand = _cand("Coal Mining & Exploration", ["A", "B", "C", "D"])
    short_id = ts.theme_candidate_short_id(cand["name"])
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    promote_mock = AsyncMock(side_effect=[
        {"status": "promoted", "name": cand["name"], "tickers": cand["tickers"],
         "n_members": 4, "canonicalized": False},
        {"status": "noop", "name": cand["name"]},
    ])
    monkeypatch.setattr(te, "promote_candidate_by_name", promote_mock)

    agent = _FakeAgent()
    resp1 = await MarketIntelligenceAgent._handle_promotetheme_id(
        agent, _request(f"/promotetheme_id {short_id}"))
    resp2 = await MarketIntelligenceAgent._handle_promotetheme_id(
        agent, _request(f"/promotetheme_id {short_id}"))

    assert resp1.success and resp2.success
    assert "✅ Promoted" in resp1.result
    assert "✅ Promoted" not in resp2.result
    assert "already a live theme" in resp2.result
    assert promote_mock.await_count == 2
    n1, n2 = promote_mock.await_args_list[0].args[0], promote_mock.await_args_list[1].args[0]
    assert n1 == n2 == cand["name"]               # same resolved candidate both times


def test_render_promote_result_noop_never_reads_as_fresh_success():
    text = _render_promote_result({"status": "noop", "name": "X"}, "X")
    assert "already a live theme — left intact" in text
    assert "✅" not in text


# ═══════════════════════════════════════════════════════════════════════════════════
# D — channels/telegram.py: tpromo: callback (authorization is the load-bearing piece)
# ═══════════════════════════════════════════════════════════════════════════════════

from channels.telegram import TelegramChannel  # noqa: E402
from tests.conftest import fake_httpx_client  # noqa: E402


def _make_channel():
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._secrets = SimpleNamespace(
        telegram_allowed_user_ids=[42],
        internal_api_secret="test-secret",
    )
    return channel


def _cb_update(data, user_id=42):
    query = SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    return SimpleNamespace(callback_query=query)


@pytest.fixture()
def _stub_auth(monkeypatch):
    """core.router.auth_headers() reads INTERNAL_API_SECRET before any mocked httpx
    client is touched (see tests/test_telegram_market_task_fallback.py) — stub the
    auth boundary so this is environment-independent."""
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    monkeypatch.setattr("core.router.auth_headers", lambda: {"X-Apollo-Secret": "test"})


@pytest.mark.asyncio
async def test_unauthorized_tap_never_promotes():
    """THE load-bearing check: a callback query is a SEPARATE update type from a text
    message and does not inherit the message-path allowlist automatically — it must be
    checked explicitly. A non-allowed user tapping the button must be refused before
    the promote handler is ever reached."""
    channel = _make_channel()
    channel._handle_theme_promote_callback = AsyncMock()

    update = _cb_update("tpromo:abc123", user_id=999)  # NOT in telegram_allowed_user_ids
    await channel._handle_callback_query(update, None)

    channel._handle_theme_promote_callback.assert_not_awaited()
    update.callback_query.answer.assert_awaited_once_with("Unauthorized")


@pytest.mark.asyncio
async def test_authorized_tap_dispatches_to_promote_callback():
    channel = _make_channel()
    channel._handle_theme_promote_callback = AsyncMock()

    update = _cb_update("tpromo:abc123", user_id=42)   # IS in telegram_allowed_user_ids
    await channel._handle_callback_query(update, None)

    channel._handle_theme_promote_callback.assert_awaited_once()
    args = channel._handle_theme_promote_callback.await_args.args
    assert args[1] == "tpromo:abc123"


@pytest.mark.asyncio
async def test_promote_callback_posts_task_and_replies_with_result(monkeypatch, _stub_auth):
    channel = _make_channel()
    monkeypatch.setattr("shared.registry.get_agent_url", lambda name: "http://market-agent:9000")
    monkeypatch.setattr("core.router.get_agent_url", lambda name: "http://market-agent:9000")
    fake_client = fake_httpx_client(json_body={
        "request_id": "rid", "agent": "market_intelligence", "success": True,
        "result": "✅ Promoted *Coal Mining & Exploration* to a live theme (4 members).",
    })
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    query = SimpleNamespace(
        data="tpromo:abc123", from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await channel._handle_theme_promote_callback(query, "tpromo:abc123")

    assert fake_client.last_post["kwargs"]["json"]["task"] == "/promotetheme_id abc123"
    query.message.reply_text.assert_awaited_once()
    sent_text = query.message.reply_text.await_args.args[0]
    assert "Coal Mining & Exploration" in sent_text


# ═══════════════════════════════════════════════════════════════════════════════════
# E — run_theme_synthesis: the alert actually goes out WITH the keyboard
# ═══════════════════════════════════════════════════════════════════════════════════
# The keyboard-builder tests in section B call build_synthesis_keyboard directly; this
# pins the ONE line that wires it into the real alert (run_theme_synthesis's
# send_telegram_message call) — deleting that line makes the whole feature invisible
# while every other test here stays green. Mock scaffolding follows
# tests/test_theme_synthesis_truncation.py's established pattern for this function.

import agents.market_intelligence.collector as collector_mod  # noqa: E402


class _SynthBlock:
    def __init__(self, type_, input_=None):
        self.type = type_
        self.input = input_ or {}


class _SynthResp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _SynthMessages:
    def __init__(self, resp):
        self._resp = resp

    async def create(self, **kwargs):
        return self._resp


class _SynthClient:
    def __init__(self, resp):
        self.messages = _SynthMessages(resp)


@pytest.mark.asyncio
async def test_run_theme_synthesis_sends_alert_with_one_button_per_kept_cohort(monkeypatch):
    from datetime import date

    monkeypatch.setattr(collector_mod, "et_today", lambda: date(2026, 8, 17))
    monkeypatch.setattr(collector_mod, "last_trading_day", lambda: date(2026, 8, 17))

    async def _velocity(d, limit=30):
        return [{"ticker": f"T{i}", "rs_composite": 95.0} for i in range(8)]

    async def _turners(d, limit=40):
        return []

    async def _descs(tickers):
        return {}

    async def _themes(*a, **k):
        return []

    async def _persist(rd, kept):
        return len(kept)

    monkeypatch.setattr(dbmod, "get_rs_velocity", _velocity)
    monkeypatch.setattr(dbmod, "get_rs_turners", _turners)
    monkeypatch.setattr(dbmod, "get_descriptions_batch", _descs)
    monkeypatch.setattr(dbmod, "get_active_themes", _themes)
    monkeypatch.setattr(dbmod, "persist_synthesis_theme_candidates", _persist)
    monkeypatch.setattr(dbmod, "log_audit_event", AsyncMock())

    cohorts = [{"name": "Test Cohort", "tickers": ["T1", "T2", "T3"],
                "confidence": "high", "thesis": "a coherent cross-ticker thesis"}]
    resp = _SynthResp("tool_use", [_SynthBlock("tool_use", {"cohorts": cohorts})])
    monkeypatch.setattr(te, "_get_anthropic_client", lambda: _SynthClient(resp))

    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(briefing, "send_telegram_message", send_mock)

    result = await ts.run_theme_synthesis()

    assert result["n_kept"] == 1
    send_mock.assert_awaited_once()
    kb = send_mock.await_args.kwargs.get("reply_markup")
    assert kb is not None, "run_theme_synthesis did not pass reply_markup — the alert has no button"
    assert len(kb["inline_keyboard"]) == 1
    btn = kb["inline_keyboard"][0][0]
    assert btn["callback_data"] == f"tpromo:{ts.theme_candidate_short_id('Test Cohort')}"
