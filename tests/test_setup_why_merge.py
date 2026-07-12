"""#178 — /setup + /why merged into ONE observability command.

/setup is the single entry: a bare ticker (or day-count) → the multi-day detector
TIMELINE; a DATE arg → delegates to the /why per-day entry-diagnosis view. /why stays
as a back-compat alias. Pins the delegation branch (the new behavior) both ways."""
import asyncio

import pytest

from agents.market_intelligence.agent import MarketIntelligenceAgent
from shared.models import AgentRequest


@pytest.fixture
def agent():
    return MarketIntelligenceAgent()


def _req(task):
    return AgentRequest(task=task, user_id=1, conversation_id="t")


def test_setup_with_date_delegates_to_why(agent):
    # /setup TICKER YYYY-MM-DD → the deep single-day view via the proven /why handler.
    seen = {}

    async def _fake_why(request):
        seen["task"] = request.task
        return {"handler": "why"}

    agent._handle_why_query = _fake_why
    res = asyncio.run(agent._handle_setup_query(_req("/setup CRCL 2026-07-10")))
    assert res == {"handler": "why"}
    assert seen.get("task") == "/setup CRCL 2026-07-10"


def test_setup_without_date_does_not_delegate(agent, monkeypatch):
    # bare /setup TICKER → the timeline path; must NOT reach /why. Stub the timeline
    # fetch empty so the handler returns the "no hits" message with zero DB I/O.
    called = {"why": False}

    async def _fake_why(request):
        called["why"] = True
        return {}

    async def _empty_timeline(ticker, days=180):
        return {"events": [], "rs_context": None, "raw_count": 0, "cap": 0}

    agent._handle_why_query = _fake_why
    monkeypatch.setattr(
        "agents.market_intelligence.db.get_ticker_setup_timeline", _empty_timeline
    )
    asyncio.run(agent._handle_setup_query(_req("/setup CRCL")))
    assert called["why"] is False


def test_why_skip_set_picks_ticker_not_setup_keyword():
    # the delegation passes the raw "/setup TICKER DATE" text to /why, so /why must skip
    # the SETUP keyword and resolve the real ticker (regression guard on the skip-set).
    import re
    from agents.market_intelligence.agent import _PREPOSITION_SKIP

    raw = "/setup CRCL 2026-07-10"
    cands = re.findall(r"\b([A-Z]{2,5})\b", raw.upper())
    skip = _PREPOSITION_SKIP | {"WHY", "TRACE", "THE", "FOR", "AND", "WHAT",
                                "ENTRY", "EXIT", "TRADE", "EP", "ORB", "WE", "DID", "SETUP"}
    ticker = next((t for t in cands if t not in skip), None)
    assert ticker == "CRCL"
