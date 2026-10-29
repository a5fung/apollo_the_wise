"""2026-10-29 (GKOS, operator "go") — the opening-bar wait covers a stream bar that lands after the
old ~20 s budget, and a bar delivered mid-wait is served within one cache poll.

Incident: 09:31:00 a [bar_stream] trigger started GKOS's entry before GKOS's own 09:30 bar had
reached the stream; three attempts 10 s apart (cache + REST) found nothing and the pipeline gave up
at 09:31:20.8 with `infra:no_bar`. A second [bar_stream] trigger fired at 09:31:21.9, and the skip
row written a second earlier blocked it (the same-day dedupe). GKOS then ran about 7% above its
opening-range high.

Fix under test (entry_pipeline): REST attempts 3 -> 6 (same 10 s cadence), and the stream cache is
re-read every BAR_CACHE_POLL_SEC during each wait. The same-day dedupe and the insert-time
ON CONFLICT are unchanged; the third test pins that two pipelines waiting on one ticker still place
one trade.

MUTATION PROOF (run by hand, reverted after):
  M1 BAR_RETRY_MAX back to 3            -> test_bar_landing_after_the_old_budget_is_served FAILS.
  M2 _sleep_until_stream_bar -> a plain asyncio.sleep(seconds)
                                        -> test_mid_wait_bar_is_served_within_a_poll FAILS.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import bar_stream as bs
from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker.skip_reasons import WINDOW_DUPLICATE
from tests.test_461_cap_toctou_race import _TODAY, FakeDB, _submit, _wire
from tests.test_orb_stream_bar_join import CGEM_BAR, TODAY

_REAL_FETCH = ep.fetch_orb_bar_with_retry


@pytest.fixture(autouse=True)
def _clean_stream_state(monkeypatch):
    bs._first_bars.clear()
    bs._processed_today.clear()
    bs._subscribed.clear()
    monkeypatch.setattr(ep, "log_audit_event", AsyncMock())
    yield
    bs._first_bars.clear()
    bs._processed_today.clear()
    bs._subscribed.clear()


def _bar_for(day):
    """CGEM_BAR's OHLCV stamped 09:30 ET on `day` (13:30 UTC — both dates are EDT)."""
    return dict(CGEM_BAR, timestamp=f"{day.isoformat()}T13:30:00+00:00")


@pytest.mark.asyncio
async def test_bar_landing_after_the_old_budget_is_served(monkeypatch):
    """The GKOS shape: REST never returns the bar and the stream delivers it during the third REST
    attempt — after the point the old 3-attempt loop returned None. It must now be served."""
    monkeypatch.setattr(ep, "BAR_RETRY_DELAY_SEC", 0)

    async def rest(ticker, today):
        if rest.await_count >= 3:
            bs._first_bars["GKOS"] = _bar_for(TODAY)
        return None

    rest = AsyncMock(side_effect=rest)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("GKOS", TODAY, "ORB")

    assert bar is not None and bar["high"] == 21.00
    assert rest.await_count == 3                     # served from the cache before a 4th REST call
    used = [c for c in ep.log_audit_event.await_args_list if c.args[0] == "orb_bar_stream_used"]
    assert len(used) == 1 and "waited=" in used[0].args[1]


@pytest.mark.asyncio
async def test_mid_wait_bar_is_served_within_a_poll(monkeypatch):
    """A bar that lands early in a 1.0 s wait is served after one 0.01 s poll, not at the next
    attempt — the old loop slept the whole delay before looking again."""
    monkeypatch.setattr(ep, "BAR_RETRY_DELAY_SEC", 1.0)
    monkeypatch.setattr(ep, "BAR_CACHE_POLL_SEC", 0.01)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", AsyncMock(return_value=None))

    async def deliver():
        await asyncio.sleep(0.05)
        bs._first_bars["GKOS"] = _bar_for(TODAY)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    bar, _ = await asyncio.gather(ep.fetch_orb_bar_with_retry("GKOS", TODAY, "ORB"), deliver())

    assert bar is not None
    assert loop.time() - t0 < 0.5


@pytest.mark.asyncio
async def test_no_bar_at_all_still_ends_in_none_after_every_attempt(monkeypatch):
    monkeypatch.setattr(ep, "BAR_RETRY_DELAY_SEC", 0)
    rest = AsyncMock(return_value=None)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    assert await ep.fetch_orb_bar_with_retry("GKOS", TODAY, "ORB") is None
    assert rest.await_count == ep.BAR_RETRY_MAX == 6


@pytest.mark.asyncio
async def test_two_pipelines_waiting_on_one_ticker_place_one_trade(monkeypatch):
    """The longer wait widens an existing race: the first pipeline is still waiting when the bar
    lands and the stream starts a second one for the same ticker. Both reach the insert; the
    unique key lets one through and the other returns the silent duplicate. One order."""
    db = FakeDB()
    _wire(monkeypatch, db)
    monkeypatch.setattr(ep, "fetch_orb_bar_with_retry", _REAL_FETCH)   # the real wait, not the gate
    monkeypatch.setattr(ep, "BAR_RETRY_DELAY_SEC", 0.2)
    monkeypatch.setattr(ep, "BAR_CACHE_POLL_SEC", 0.01)
    rest = AsyncMock(return_value=None)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)
    import agents.market_intelligence.broker.order_manager as om

    async def bar_lands_and_stream_retriggers():
        while rest.await_count < 1:                                        # pipeline 1 has missed once
            await asyncio.sleep(0.005)
        bs._first_bars["SAME"] = _bar_for(_TODAY)
        return await _submit("SAME")

    results = await asyncio.wait_for(
        asyncio.gather(_submit("SAME"), bar_lands_and_stream_retriggers()), timeout=10,
    )

    actions = sorted(r["action"] for r in results)
    assert actions == sorted([ep.ACTION_AUTO_ENTERED, ep.ACTION_SKIPPED]), results
    assert next(r for r in results if r["action"] == ep.ACTION_SKIPPED)["reason"] == WINDOW_DUPLICATE
    assert len([r for r in db.rows if r["ticker"] == "SAME"]) == 1
    assert om.submit_entry.await_count == 1
