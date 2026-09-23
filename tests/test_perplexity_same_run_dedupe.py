"""Perplexity was the single largest line on the bill, and most of it was repeat questions.

Measured over the 7 days to 2026-08-07: `perplexity_news_search` ran 371 calls for **$5.08 —
22.7% of ALL LLM spend**, more than any Claude caller. The operator's standing instruction that
week was *"I want to control spend and not see more growth and bring it back down."*

The shape of that bill matters: Perplexity charges a flat **per-request search fee** that dwarfs
the token cost, so the only lever is CALL COUNT. And eleven call sites funnel through one
function, several asking the identical question about the same ticker inside a single scan —
`ep_detector` alone asks *"What caused {ticker} stock to gap up?"* from two separate paths with
the same recency.

These tests pin the two properties that make the memo safe rather than merely cheap:

  1. **It is narrow.** Only a byte-identical (query, recency, system_prompt) is collapsed.
     Different phrasings are different questions and must still cost a call — a fuzzy cache
     would silently answer one question with another's answer.
  2. **It never caches a failure.** This is the week's own lesson, learned the expensive way:
     `catalyst_metrics_extractor` persisted a FAILED extraction, every later scan served the
     failure back, the call stopped being made, and the first fix was inert because of it. A
     transient error must never become a sticky one.
"""
import asyncio

import pytest

from agents.market_intelligence import collector


@pytest.fixture(autouse=True)
def _clean_cache():
    collector._PPLX_CACHE.clear()
    yield
    collector._PPLX_CACHE.clear()


class _Resp:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        # #603 (2026-08-27) — Agent API shape. The answer is an `output` item of
        # type 'message'; there is no `choices`. Two search_results items sit
        # BEFORE it deliberately, so an index-based parser would fail here.
        return {"status": "completed", "model": "openai/gpt-5.6-luna",
                "output": [{"type": "search_results", "results": []},
                           {"type": "search_results", "results": []},
                           {"type": "message",
                            "content": [{"type": "output_text", "text": self._text}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20,
                          "cost": {"total_cost": 0.0112}}}


def _patch_transport(monkeypatch, answers):
    """Stand in for the HTTP call, counting how many actually go out."""
    calls = []

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            calls.append(kw.get("json", {}).get("messages"))
            return _Resp(answers[min(len(calls) - 1, len(answers) - 1)])

    monkeypatch.setattr(collector.httpx, "AsyncClient", _Client)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    async def _noop(**kw):
        return 0.0
    import agents.market_intelligence.spend_tracker as st
    monkeypatch.setattr(st, "log_perplexity_call", _noop)
    return calls


def test_the_identical_question_costs_one_request_not_two(monkeypatch):
    """The concrete case: ep_detector asks the same gap-cause question from two paths."""
    calls = _patch_transport(monkeypatch, ["NVDA beat on datacenter revenue."])
    q = "What caused NVDA stock to gap up? Latest catalyst and news."

    a = asyncio.run(collector.search_news_perplexity(q, recency="week"))
    b = asyncio.run(collector.search_news_perplexity(q, recency="week"))

    assert a == b == "NVDA beat on datacenter revenue."
    assert len(calls) == 1, (
        f"the repeat question went out to Perplexity again ({len(calls)} requests) — that is a "
        "second search fee for an answer already in hand")


def test_a_different_question_is_never_answered_from_another_ones_cache(monkeypatch):
    """A fuzzy or over-broad key would hand one ticker's catalyst to another. The memo must be
    exact-match only."""
    calls = _patch_transport(monkeypatch, ["NVDA answer", "AMD answer"])

    a = asyncio.run(collector.search_news_perplexity("What caused NVDA to gap up?"))
    b = asyncio.run(collector.search_news_perplexity("What caused AMD to gap up?"))

    assert a == "NVDA answer" and b == "AMD answer"
    assert len(calls) == 2


def test_recency_and_system_prompt_are_part_of_the_key(monkeypatch):
    """Same words, different search window, is a different question — the overnight brief asks
    recency='day' where the EP path asks 'week'."""
    calls = _patch_transport(monkeypatch, ["day answer", "week answer", "custom answer"])
    q = "What is happening with SPY?"

    asyncio.run(collector.search_news_perplexity(q, recency="day"))
    asyncio.run(collector.search_news_perplexity(q, recency="week"))
    asyncio.run(collector.search_news_perplexity(q, recency="day", system_prompt="be terse"))

    assert len(calls) == 3, "recency/system_prompt collapsed into one cache entry"


def test_a_failed_search_is_never_stored(monkeypatch):
    """THE lesson of 2026-08-07: catalyst_metrics_extractor cached a FAILED extraction, every
    later scan served the failure back, and the call stopped being made at all. An empty answer
    here means the search failed — it must be retried, not memoised."""
    calls = _patch_transport(monkeypatch, ["", "the real answer"])
    q = "What caused ZZZZ stock to gap up?"

    first = asyncio.run(collector.search_news_perplexity(q, recency="week"))
    second = asyncio.run(collector.search_news_perplexity(q, recency="week"))

    assert first == ""
    assert second == "the real answer", (
        "an empty (failed) search was cached — a transient failure just became a sticky one, "
        "which is exactly the bug that made the 08-07 extraction fix inert")
    assert len(calls) == 2


def test_an_expired_entry_is_refetched(monkeypatch):
    """News is the one thing that must not go stale. 15 minutes covers a scan chain, no more."""
    calls = _patch_transport(monkeypatch, ["stale", "fresh"])
    q = "overnight macro"

    assert asyncio.run(collector.search_news_perplexity(q)) == "stale"
    # age every entry past the TTL without sleeping
    for k, (stamped, ans) in list(collector._PPLX_CACHE.items()):
        collector._PPLX_CACHE[k] = (stamped - collector._PPLX_CACHE_TTL_S - 1, ans)
    assert asyncio.run(collector.search_news_perplexity(q)) == "fresh"
    assert len(calls) == 2


def test_the_ttl_stays_short():
    """A long TTL turns a cost fix into a staleness bug on the one dataset where freshness is
    the product."""
    assert collector._PPLX_CACHE_TTL_S <= 1800, (
        f"perplexity cache TTL is {collector._PPLX_CACHE_TTL_S}s — long enough to serve stale "
        "news into a live scan")


def test_the_cache_cannot_grow_without_bound(monkeypatch):
    """This lives in a long-running container; an unbounded dict keyed on free-text queries is
    a slow leak."""
    _patch_transport(monkeypatch, ["a"])
    for i in range(collector._PPLX_CACHE_MAX + 40):
        collector._pplx_cache_put((f"q{i}", "week", None), "answer")
    assert len(collector._PPLX_CACHE) <= collector._PPLX_CACHE_MAX


def test_a_human_asking_for_news_never_gets_a_cached_answer(monkeypatch):
    """The TTL was reasoned about for automated scan chains. The two interactive paths in
    agent.py answer a PERSON asking "what's happening with X" — serving them a 15-minute-old
    answer when they explicitly asked for current news is a staleness bug wearing a cost fix's
    clothes. `fresh=True` opts out."""
    calls = _patch_transport(monkeypatch, ["first", "second"])
    q = "What is happening with NVDA stock?"

    a = asyncio.run(collector.search_news_perplexity(q, fresh=True))
    b = asyncio.run(collector.search_news_perplexity(q, fresh=True))

    assert (a, b) == ("first", "second")
    assert len(calls) == 2, "fresh=True still served a cached answer to an interactive caller"


def test_the_interactive_agent_paths_actually_pass_fresh():
    """Pins the wiring, not just the capability — the escape hatch is worthless unwired."""
    import pathlib
    src = pathlib.Path("agents/market_intelligence/agent.py").read_text(encoding="utf-8")
    for marker in ("What is happening with {ticker} stock?",
                   "What happened with {ticker} stock recently?"):
        i = src.find(marker)
        assert i > 0, f"interactive perplexity call site not found: {marker}"
        assert "fresh=True" in src[i:i + 400], (
            f"the interactive path '{marker}' no longer opts out of the news cache — a human "
            "asking for current news can be served a 15-minute-old answer")
