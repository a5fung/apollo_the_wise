"""simplify GROUP 5 (2026-07-03) — _build_enriched_corpus's 4 independent SEC/Benzinga/
Perplexity fetches now run via asyncio.gather instead of 4 sequential awaits. These tests
pin the two behaviors the refactor must preserve byte-identical:

1. Reuse-or-fetch kwargs semantics — an already-provided piece (or dilution_computed=True)
   short-circuits with ZERO I/O, same as the pre-gather inline `if x is None:` checks.
2. The 4 fetches actually run CONCURRENTLY, not sequentially — the latency win the group
   card asks for. Proven via a synchronization barrier that only releases once all 4 have
   started: under a (regressed) sequential implementation this spins forever, so
   asyncio.wait_for's timeout turns a silent revert into a clean test failure rather than
   a false pass.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import ep_detector


_TODAY = date(2026, 7, 3)
_PROFILE = {"companyName": "Test Co", "marketCap": 1_000_000_000}


@pytest.mark.asyncio
async def test_already_provided_pieces_skip_io_and_state_sink(monkeypatch):
    calls = []

    async def fake_sec(ticker, forms=None, **kw):
        calls.append(("sec", forms))
        return []

    async def fake_benzinga(ticker, include_content=True):
        calls.append("benzinga")
        return []

    async def fake_pplx(prompt, recency="week"):
        calls.append("perplexity")
        return "fresh answer"

    monkeypatch.setattr(ep_detector, "get_sec_recent_filings", fake_sec)
    monkeypatch.setattr(ep_detector, "get_alpaca_news", fake_benzinga)
    monkeypatch.setattr(ep_detector, "search_news_perplexity", fake_pplx)
    monkeypatch.setattr(
        ep_detector, "_classify_catalyst_claude",
        AsyncMock(return_value=("routine", "analysis text")),
    )

    state_sink = {}
    quality, analysis, ext_filings, dilution, prior_agr, recent_earn = (
        await ep_detector._build_enriched_corpus(
            "TEST", _TODAY, _PROFILE,
            ext_filings=[],                    # already provided -> no ext_filings SEC call
            dilution=None, dilution_computed=True,  # already computed -> no dilution SEC call
            benzinga_items=[],                 # already provided -> no benzinga call
            perplexity_answer="cached answer",  # already provided -> no perplexity call
            news_for_classify=[],
            state_sink=state_sink,
        )
    )

    assert calls == []              # nothing fetched — all 4 pieces reused
    assert state_sink == {}         # no fresh fetch -> no incremental write
    assert quality == "routine" and analysis == "analysis text"
    assert ext_filings == [] and dilution is None


@pytest.mark.asyncio
async def test_partial_reuse_only_fetches_the_missing_pieces(monkeypatch):
    """ext_filings + benzinga provided; dilution + perplexity must still be freshly
    fetched, and ONLY those two write into state_sink."""
    calls = []

    async def fake_sec(ticker, forms=None, **kw):
        calls.append(("sec", forms))
        return []   # dilution fetch's SEC call — recent_dilution_filing([]) -> None

    async def fake_pplx(prompt, recency="week"):
        calls.append("perplexity")
        return "fresh answer"

    async def fake_benzinga_should_not_be_called(ticker, include_content=True):
        raise AssertionError("benzinga must not be re-fetched — already provided")

    monkeypatch.setattr(ep_detector, "get_sec_recent_filings", fake_sec)
    monkeypatch.setattr(ep_detector, "get_alpaca_news", fake_benzinga_should_not_be_called)
    monkeypatch.setattr(ep_detector, "search_news_perplexity", fake_pplx)
    monkeypatch.setattr(
        ep_detector, "_classify_catalyst_claude",
        AsyncMock(return_value=("strong", "analysis")),
    )

    state_sink = {}
    await ep_detector._build_enriched_corpus(
        "TEST", _TODAY, _PROFILE,
        ext_filings=[{"filed": "2026-06-01", "items": "1.01", "text": "x" * 250}],
        dilution=None, dilution_computed=False,   # NOT yet computed -> fetch
        benzinga_items=[],                        # already provided -> no fetch
        perplexity_answer=None,                   # NOT yet computed -> fetch
        news_for_classify=[],
        state_sink=state_sink,
    )

    # Exactly the 2 missing pieces were fetched — order-independent (concurrent).
    assert sorted(calls, key=str) == sorted(
        [("sec", ("424B5", "8-K")), "perplexity"], key=str
    )
    # ext_filings was provided so its OWN key must not appear; dilution's SEC fetch ran
    # and must be the only SEC-shaped write.
    assert "ext_filings" not in state_sink
    assert "dilution" in state_sink and state_sink["dilution"] is None


@pytest.mark.asyncio
async def test_four_fetches_run_concurrently_not_sequentially(monkeypatch):
    """Synchronization-barrier proof: each fake fetch spins until all 4 have entered.
    Under a sequential-await implementation this deadlocks (the 2nd fetch never even
    STARTS until the 1st returns, so the 1st's spin-wait for a 4th entrant never
    resolves) — asyncio.wait_for's timeout converts that into a clean assertion
    failure instead of a hang or a false pass."""
    entered: list[str] = []

    async def _barrier(name: str):
        entered.append(name)
        while len(entered) < 4:
            await asyncio.sleep(0)

    async def fake_sec(ticker, forms=None, **kw):
        name = "dilution_sec" if forms == ("424B5", "8-K") else "ext_filings_sec"
        await _barrier(name)
        return []

    async def fake_benzinga(ticker, include_content=True):
        await _barrier("benzinga")
        return []

    async def fake_pplx(prompt, recency="week"):
        await _barrier("perplexity")
        return "answer"

    monkeypatch.setattr(ep_detector, "get_sec_recent_filings", fake_sec)
    monkeypatch.setattr(ep_detector, "get_alpaca_news", fake_benzinga)
    monkeypatch.setattr(ep_detector, "search_news_perplexity", fake_pplx)
    monkeypatch.setattr(
        ep_detector, "_classify_catalyst_claude",
        AsyncMock(return_value=("routine", "analysis")),
    )

    await asyncio.wait_for(
        ep_detector._build_enriched_corpus("TEST", _TODAY, _PROFILE),
        timeout=2.0,
    )

    assert sorted(entered) == sorted(
        ["ext_filings_sec", "dilution_sec", "benzinga", "perplexity"]
    )
