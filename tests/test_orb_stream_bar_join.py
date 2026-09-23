"""2026-08-13 — the stream-delivered ORB bar is the PRIMARY source; REST is fallback.

Incident: 09:31:20 ET, HLIT/CRMD/CGEM (three HIGH EP alerts) all skipped
`infra:no_bar: 3 retries exhausted`. The WebSocket bar stream had DELIVERED the
09:30 opening bar (bar_stream._handle_bar logged full OHLCV and triggered the
ORB entry), but `entry_pipeline.fetch_orb_bar_with_retry` threw it away and
re-fetched the same minute over REST (`alpaca_client.get_first_bar`), which had
not yet aggregated it. Same class on 2026-04-23/24 (1 + 3 skips). Not a feed
outage — we asked the wrong source, seconds too early.

Fix under test: `_handle_bar` caches the 09:30 bar in `bar_stream._first_bars`;
`fetch_orb_bar_with_retry` consults `bar_stream.get_cached_first_bar` on EVERY
attempt (a stream bar can land during a retry sleep) and only falls through to
the unchanged REST path. Invariants pinned here:

1. Stream bar used when REST is empty (the incident shape) — no retry exhaust.
2. REST fallback intact when the cache is empty (never zero sources).
3. A stream bar arriving mid-retry is picked up on the next attempt.
4. ORB definition unchanged: only the true 09:30 ET minute is ever served —
   stale prior-day bars and non-open minutes are refused at READ time too.
5. A malformed cached bar (high < low etc.) falls back to REST.
6. Any cache-lookup exception falls back to REST (fail-open).
7. reset_daily_state clears the cache.

MUTATION PROOF (run manually, each mutation reverted after):
  M1 remove the cache consult in fetch_orb_bar_with_retry
     → test_stream_bar_used_when_rest_empty + test_stream_bar_arriving_mid_retry FAIL.
  M2 make the cache path terminal (return None instead of falling to REST)
     → test_rest_fallback_when_cache_empty + test_stale_prior_day_bar_not_used FAIL.
  M3 remove get_cached_first_bar's read-side date/minute guard
     → test_stale_prior_day_bar_not_used + test_non_930_bar_refused_at_read FAIL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import bar_stream as bs
from agents.market_intelligence.broker import entry_pipeline as ep

TODAY = date(2026, 8, 13)
# 09:30 ET == 13:30 UTC on 2026-08-13 (EDT)
OPEN_TS = datetime(2026, 8, 13, 13, 30, tzinfo=timezone.utc)

CGEM_BAR = {
    "open": 20.72, "high": 21.00, "low": 19.95, "close": 19.95,
    "volume": 44311, "timestamp": OPEN_TS.isoformat(),
}


def _stream_bar_obj(symbol="CGEM", ts=OPEN_TS, **kw):
    """Fake alpaca Bar as pushed to _handle_bar."""
    fields = dict(open=20.72, high=21.00, low=19.95, close=19.95,
                  volume=44311, vwap=20.31)
    fields.update(kw)
    return SimpleNamespace(symbol=symbol, timestamp=ts, **fields)


@pytest.fixture(autouse=True)
def _clean_stream_state(monkeypatch):
    """Isolated bar_stream module state + no real sleeps/audit/DB in ep."""
    bs._first_bars.clear()
    bs._processed_today.clear()
    bs._subscribed.clear()
    monkeypatch.setattr(ep, "BAR_RETRY_DELAY_SEC", 0)
    monkeypatch.setattr(ep, "log_audit_event", AsyncMock())
    yield
    bs._first_bars.clear()
    bs._processed_today.clear()
    bs._subscribed.clear()


async def _prime_cache_via_handle_bar(monkeypatch, bar_obj):
    """Populate the cache through the REAL store site (_handle_bar), with the
    downstream entry trigger and the DB write-through mocked out."""
    from agents.market_intelligence.broker import alpaca_client, live_tracker
    monkeypatch.setattr(live_tracker, "process_new_alerts_live",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(alpaca_client, "_persist_first_bar", AsyncMock())
    await bs._handle_bar(bar_obj)


# ── 1. The incident shape: REST empty, stream bar in hand ────────────────────


@pytest.mark.asyncio
async def test_stream_bar_used_when_rest_empty(monkeypatch):
    """REST has not aggregated the 09:30 minute (returns None forever). The
    stream already delivered the bar. The pipeline must use it — immediately,
    with zero REST-retry exhaust and no infra:no_bar."""
    await _prime_cache_via_handle_bar(monkeypatch, _stream_bar_obj())

    rest = AsyncMock(return_value=None)  # the 2026-08-13 REST behaviour
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("CGEM", TODAY, "ORB")

    assert bar is not None, "infra:no_bar — the delivered stream bar was thrown away"
    assert (bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]) == \
        (20.72, 21.00, 19.95, 19.95, 44311)
    # Primary means primary: served before any REST call on attempt 1.
    assert rest.await_count == 0
    # Verify-live marker: the source is attributable in the audit log.
    events = [c.args[0] for c in ep.log_audit_event.await_args_list]
    assert "orb_bar_stream_used" in events


@pytest.mark.asyncio
async def test_cached_bar_matches_rest_shape(monkeypatch):
    """The two sources must agree on what the ORB bar IS — same dict keys as
    alpaca_client.get_first_bar's return, so every downstream consumer
    (fade guard, spec builders, audit) is source-agnostic."""
    await _prime_cache_via_handle_bar(monkeypatch, _stream_bar_obj())
    bar = bs.get_cached_first_bar("CGEM", TODAY)
    assert set(bar.keys()) == {"open", "high", "low", "close", "volume", "timestamp"}


# ── 2. REST fallback intact — never zero sources ─────────────────────────────


@pytest.mark.asyncio
async def test_rest_fallback_when_cache_empty(monkeypatch):
    """No stream bar (not subscribed / stream down / late open): today's REST
    behaviour, byte-identical."""
    rest_bar = dict(CGEM_BAR)
    rest = AsyncMock(return_value=rest_bar)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("HLIT", TODAY, "ORB")

    assert bar is rest_bar
    assert rest.await_count == 1


@pytest.mark.asyncio
async def test_both_empty_still_exhausts_and_returns_none(monkeypatch):
    """No cache, REST empty → the pre-fix terminal shape (3 attempts, None)."""
    rest = AsyncMock(return_value=None)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("HLIT", TODAY, "ORB")

    assert bar is None
    assert rest.await_count == ep.BAR_RETRY_MAX


@pytest.mark.asyncio
async def test_cache_lookup_exception_falls_back_to_rest(monkeypatch):
    """A broken cache may never block the entry: lookup raises → REST serves."""
    monkeypatch.setattr(bs, "get_cached_first_bar",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rest_bar = dict(CGEM_BAR)
    rest = AsyncMock(return_value=rest_bar)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("CGEM", TODAY, "ORB")

    assert bar is rest_bar


# ── 3. Race: stream bar lands during a retry sleep ───────────────────────────


@pytest.mark.asyncio
async def test_stream_bar_arriving_mid_retry(monkeypatch):
    """CGEM's bar triggered processing of HLIT whose own bar arrived moments
    later: attempt 1 finds neither cache nor REST; the bar lands; attempt 2
    must serve it from the cache without waiting for REST to catch up."""
    async def rest_never_catches_up(ticker, today):
        # Side effect stands in for "the HLIT bar event fired during the sleep".
        bs._first_bars["HLIT"] = dict(CGEM_BAR)
        return None

    rest = AsyncMock(side_effect=rest_never_catches_up)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("HLIT", TODAY, "ORB")

    assert bar is not None and bar["high"] == 21.00
    assert rest.await_count == 1  # cache hit on attempt 2, before the 2nd REST call


# ── 4. ORB definition unchanged: only the true 09:30 ET minute is served ─────


@pytest.mark.asyncio
async def test_stale_prior_day_bar_not_used(monkeypatch):
    """A prior-day 09:30 bar left in the cache (missed daily reset) must be
    refused — REST (today's behaviour) decides instead."""
    stale = dict(CGEM_BAR,
                 timestamp=datetime(2026, 8, 12, 13, 30, tzinfo=timezone.utc).isoformat())
    bs._first_bars["CGEM"] = stale
    rest_bar = dict(CGEM_BAR, high=22.22)
    rest = AsyncMock(return_value=rest_bar)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("CGEM", TODAY, "ORB")

    assert bar is rest_bar, "stale prior-day bar defined the ORB range"


@pytest.mark.asyncio
async def test_non_930_bar_never_stored(monkeypatch):
    """Store-side gate: a late-opening name's first bar (09:32) is ignored by
    _handle_bar, so the cache stays empty and the REST path keeps its
    earliest-in-window semantics — entering off the wrong minute is impossible."""
    late_ts = datetime(2026, 8, 13, 13, 32, tzinfo=timezone.utc)
    await _prime_cache_via_handle_bar(monkeypatch, _stream_bar_obj(ts=late_ts))
    assert bs._first_bars == {}


def test_non_930_bar_refused_at_read():
    """Read-side belt-and-braces: even a non-09:30 bar injected into the cache
    is refused at read time."""
    bs._first_bars["CGEM"] = dict(
        CGEM_BAR, timestamp=datetime(2026, 8, 13, 13, 32, tzinfo=timezone.utc).isoformat())
    assert bs.get_cached_first_bar("CGEM", TODAY) is None


# ── 5. Malformed bar → REST fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_insane_cached_bar_falls_back_to_rest(monkeypatch):
    """high < low can never define an ORB range: refuse the cached bar, let
    REST answer."""
    bs._first_bars["CGEM"] = dict(CGEM_BAR, high=19.00)  # high < low 19.95
    rest_bar = dict(CGEM_BAR)
    rest = AsyncMock(return_value=rest_bar)
    monkeypatch.setattr(ep.alpaca, "get_first_bar", rest)

    bar = await ep.fetch_orb_bar_with_retry("CGEM", TODAY, "ORB")

    assert bar is rest_bar


def test_zero_volume_or_nonpositive_price_refused():
    bs._first_bars["A"] = dict(CGEM_BAR, volume=0)
    bs._first_bars["B"] = dict(CGEM_BAR, low=0.0, open=0.0, close=0.0, high=0.0)
    assert bs.get_cached_first_bar("A", TODAY) is None
    assert bs.get_cached_first_bar("B", TODAY) is None


# ── 6/7. Hygiene ─────────────────────────────────────────────────────────────


def test_reset_daily_state_clears_cache():
    bs._first_bars["CGEM"] = dict(CGEM_BAR)
    bs.reset_daily_state()
    assert bs._first_bars == {}


@pytest.mark.asyncio
async def test_handle_bar_still_triggers_entry_and_dedups(monkeypatch):
    """The caching is a ride-along: _handle_bar's existing contract (trigger
    ORB processing once, dedup re-delivery) is unchanged."""
    from agents.market_intelligence.broker import alpaca_client, live_tracker
    trigger = AsyncMock(return_value=[])
    monkeypatch.setattr(live_tracker, "process_new_alerts_live", trigger)
    monkeypatch.setattr(alpaca_client, "_persist_first_bar", AsyncMock())

    await bs._handle_bar(_stream_bar_obj())
    await bs._handle_bar(_stream_bar_obj())  # re-delivery

    assert trigger.await_count == 1
    assert "CGEM" in bs._processed_today
    assert bs.get_cached_first_bar("CGEM", TODAY) is not None
