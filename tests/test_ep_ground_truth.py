"""Unit tests for the operator ground-truth pipeline (#254).

Covers the pure arg-parsers (_parse_review_args / _parse_spotted_args) and the
read/write command handlers with the DB writers mocked. The end-to-end DB
write→readback probe lives in scripts/_probe_ground_truth_254.py (runs against
a real pool via docker exec — telemetry table, read-only re trade state).
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.agent import _parse_review_args, _parse_spotted_args


def _request(text):
    req = MagicMock()
    req.task = text
    return req


class _FakeAgent:
    def _ok(self, request, *, result):
        return MagicMock(ok=True, result=result)


# ── Parser: /review ─────────────────────────────────────────────────────────────

def test_review_parse_minimal():
    p = _parse_review_args("/review FSLR agree")
    assert p == {"ticker": "FSLR", "event_date": None, "verdict": "agree", "note": None}


def test_review_parse_with_date_and_note():
    p = _parse_review_args("/review aapl 2026-04-15 toohigh thin catalyst, hollow PR")
    assert p["ticker"] == "AAPL"
    assert p["event_date"] == "2026-04-15"
    assert p["verdict"] == "toohigh"
    assert p["note"] == "thin catalyst, hollow PR"


def test_review_parse_all_verdicts():
    for v in ("agree", "toohigh", "toolow", "notep"):
        assert _parse_review_args(f"/review RCAT {v}")["verdict"] == v


def test_review_parse_rejects_bad_verdict():
    assert _parse_review_args("/review FSLR maybe") is None


def test_review_parse_rejects_missing_verdict():
    assert _parse_review_args("/review FSLR") is None


def test_review_parse_rejects_no_ticker():
    assert _parse_review_args("/review") is None
    assert _parse_review_args("/review 123 agree") is None


def test_review_parse_lowercases_ticker():
    assert _parse_review_args("/review fslr agree")["ticker"] == "FSLR"


# ── Parser: /spotted ────────────────────────────────────────────────────────────

def test_spotted_parse_minimal():
    p = _parse_spotted_args("/spotted FSLR game_changer")
    assert p["ticker"] == "FSLR"
    assert p["grade"] == "game_changer"
    assert p["event_date"] is None
    assert p["narrative"] is None
    assert p["source"] == "operator"


def test_spotted_parse_full_with_handle_source():
    p = _parse_spotted_args(
        "/spotted FSLR 2026-04-15 game_changer solar policy tailwind, backlog beat via @qullamaggie")
    assert p["event_date"] == "2026-04-15"
    assert p["grade"] == "game_changer"
    assert "solar policy" in p["narrative"]
    assert p["source"] == "tweet:@qullamaggie"


def test_spotted_parse_all_grades():
    for g in ("game_changer", "strong", "routine", "mna", "none", "not_ep"):
        assert _parse_spotted_args(f"/spotted X {g} story")["grade"] == g


def test_spotted_parse_rejects_bad_grade():
    assert _parse_spotted_args("/spotted FSLR amazing huge move") is None


def test_spotted_parse_rejects_no_grade():
    assert _parse_spotted_args("/spotted FSLR") is None


# ── Handler: /review write path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_handler_writes_and_confirms():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_review_command
    agent = _FakeAgent()

    captured = {}

    async def _fake_upsert(**kw):
        captured.update(kw)
        return {"root_cause": kw.get("root_cause")}

    with patch("agents.market_intelligence.db.snapshot_system_tier",
               new=AsyncMock(return_value="HIGH")), \
         patch("agents.market_intelligence.db.upsert_ep_ground_truth", new=_fake_upsert):
        resp = await handler(agent, _request("/review FSLR 2026-04-15 agree solid beat"))

    assert captured["ticker"] == "FSLR"
    assert captured["kind"] == "review"
    assert captured["verdict"] == "agree"
    assert captured["root_cause"] == "judge_correct"   # agree → judge_correct
    assert captured["system_tier"] == "HIGH"
    assert captured["event_date"] == date(2026, 4, 15)
    assert captured["narrative"] == "solid beat"
    assert "Review logged" in resp.result


@pytest.mark.asyncio
async def test_review_handler_toohigh_no_root_cause():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_review_command
    agent = _FakeAgent()
    captured = {}

    async def _fake_upsert(**kw):
        captured.update(kw)
        return {"root_cause": kw.get("root_cause")}

    with patch("agents.market_intelligence.db.snapshot_system_tier",
               new=AsyncMock(return_value="MODERATE")), \
         patch("agents.market_intelligence.db.upsert_ep_ground_truth", new=_fake_upsert):
        await handler(agent, _request("/review ABVX 2026-06-03 toohigh gap-down recovery"))

    # over/under-grade causes are multi-valued → left NULL (not fabricated)
    assert captured["verdict"] == "toohigh"
    assert captured["root_cause"] is None


@pytest.mark.asyncio
async def test_review_handler_bare_lists_corpus():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_review_command
    agent = _FakeAgent()
    # bare /review delegates to the read view → bind it on the fake
    agent._handle_reviews_query = MarketIntelligenceAgent._handle_reviews_query.__get__(agent)
    with patch("agents.market_intelligence.db.get_recent_ground_truth",
               new=AsyncMock(return_value=[])):
        resp = await handler(agent, _request("/review"))
    # delegates to the read view (empty-corpus hint), NOT a usage error
    assert "ground-truth" in resp.result.lower()


@pytest.mark.asyncio
async def test_review_handler_bad_input_shows_usage():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_review_command
    agent = _FakeAgent()
    resp = await handler(agent, _request("/review FSLR notaverdict"))
    assert "Usage" in resp.result


# ── Handler: /spotted inject path ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spotted_handler_uncaught_flags_coverage_gap():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_spotted_command
    agent = _FakeAgent()
    captured = {}

    async def _fake_upsert(**kw):
        captured.update(kw)
        return {}

    with patch("agents.market_intelligence.db.snapshot_system_tier",
               new=AsyncMock(return_value=None)), \
         patch("agents.market_intelligence.db.upsert_ep_ground_truth", new=_fake_upsert):
        resp = await handler(
            agent, _request("/spotted FSLR 2026-04-15 game_changer big solar beat"))

    assert captured["kind"] == "injected"
    assert captured["operator_grade"] == "game_changer"
    assert captured["system_tier"] is None
    assert "coverage gap" in resp.result.lower()


@pytest.mark.asyncio
async def test_spotted_handler_caught_adds_to_corpus():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_spotted_command
    agent = _FakeAgent()

    async def _fake_upsert(**kw):
        return {}

    with patch("agents.market_intelligence.db.snapshot_system_tier",
               new=AsyncMock(return_value="HIGH")), \
         patch("agents.market_intelligence.db.upsert_ep_ground_truth", new=_fake_upsert):
        resp = await handler(agent, _request("/spotted FSLR game_changer beat"))
    assert "caught it" in resp.result.lower()


@pytest.mark.asyncio
async def test_spotted_handler_bad_input_shows_usage():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    handler = MarketIntelligenceAgent._handle_spotted_command
    agent = _FakeAgent()
    resp = await handler(agent, _request("/spotted FSLR"))
    assert "Usage" in resp.result
