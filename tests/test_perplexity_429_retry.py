"""Fix-2b (2026-08-12) — search_news_perplexity: ONE bounded retry on HTTP 429.

Two mornings running (2026-08-11 into 2026-08-12), a Perplexity 429 fired the
data-API-failure alert during the nightly chain. Root cause confirmed from
prod mi_audit_log: 3 `api_failure_perplexity` 429s landed in the same
millisecond (17:10:36 ET, 2026-08-11) right after theme discovery logged 6
newly-discovered themes surviving. `run_theme_engine` scores every survivor
concurrently via `asyncio.gather(*[_score_new_theme(...) for raw in
new_raw])`, and each call reaches `_news_check`'s `_SEARCH_SEM`
(semaphore(5) in theme_engine.py) — so 5 of the 6 fired at once. NOT
over-use (36 total calls that day, 183 the day before with zero 429s) — a
concurrency burst. The client had a bounded retry for TIMEOUT only — a 429
went straight to the alert + fail-open "" path with no second attempt,
silently degrading the news corpus for whichever tickers were in the burst.

The fix: extend the existing ONE-bounded-retry shape to 429, honoring
`Retry-After` (falling back to a short fixed default, capped, when the header
is absent/unparseable). Non-429/non-timeout failures (5xx, other 4xx,
connect) are unchanged — see test_perplexity_timeout_retry.py.
"""
from __future__ import annotations

import httpx
import pytest

import agents.market_intelligence.collector as collector
from agents.market_intelligence import llm_health

_REQ = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")


def _http_status_error(code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, headers=headers or {}, request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("expected raise_for_status to raise")


class _OKResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "Contract win drove the move."}}],
            "usage": {},
        }


def _install_client(monkeypatch, behaviors: list):
    """Install a stub AsyncClient whose post() consumes `behaviors` in order —
    an Exception instance is raised, anything else is returned. Returns the
    call-count list."""
    calls: list[int] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            behavior = behaviors[min(len(calls), len(behaviors) - 1)]
            calls.append(1)
            if isinstance(behavior, Exception):
                raise behavior
            return behavior

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())
    return calls


@pytest.fixture(autouse=True)
def _env_and_stubs(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    # Same-run dedupe cache is a module global — clear it so tests (and other
    # test files reusing the query string "q") never observe a stale hit.
    collector._PPLX_CACHE.clear()

    # Cost meter is additive-only; keep it away from the DB in tests.
    import agents.market_intelligence.spend_tracker as spend_tracker

    async def _noop_meter(**kwargs):
        return None

    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)

    # Don't actually sleep in tests — capture the requested duration instead.
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(collector.asyncio, "sleep", _fake_sleep)

    # Jitter uses random.uniform(1.0, 1.5) — pin it to a fixed 1.25x so the
    # backoff-duration assertions below stay exact instead of range checks,
    # while still exercising (and mutation-proving) the multiply itself.
    jitter_calls: list[tuple] = []

    def _fixed_jitter(lo, hi):
        jitter_calls.append((lo, hi))
        return 1.25

    monkeypatch.setattr(collector.random, "uniform", _fixed_jitter)

    yield sleeps
    collector._PPLX_CACHE.clear()


@pytest.mark.asyncio
async def test_429_then_success_retries_once_honoring_retry_after(monkeypatch, _env_and_stubs):
    sleeps = _env_and_stubs
    calls = _install_client(
        monkeypatch,
        [_http_status_error(429, headers={"Retry-After": "3"}), _OKResp()],
    )
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    out = await collector.search_news_perplexity("what moved the market?")

    assert out == "Contract win drove the move."
    assert len(calls) == 2               # exactly one retry
    assert alerts == []                  # a recovered blip never alerts
    assert sleeps == [3.75]              # honored Retry-After (3s) * fixed 1.25 jitter


@pytest.mark.asyncio
async def test_429_without_retry_after_uses_default_backoff(monkeypatch, _env_and_stubs):
    sleeps = _env_and_stubs
    calls = _install_client(monkeypatch, [_http_status_error(429), _OKResp()])

    out = await collector.search_news_perplexity("q")

    assert out == "Contract win drove the move."
    assert len(calls) == 2
    assert sleeps == [collector._PPLX_429_BACKOFF_DEFAULT_S * 1.25]  # default (2s) * fixed jitter


@pytest.mark.asyncio
async def test_429_retry_after_capped_at_max_backoff(monkeypatch, _env_and_stubs):
    sleeps = _env_and_stubs
    calls = _install_client(
        monkeypatch,
        [_http_status_error(429, headers={"Retry-After": "9999"}), _OKResp()],
    )

    out = await collector.search_news_perplexity("q")

    assert out == "Contract win drove the move."
    assert len(calls) == 2
    # capped at MAX_S BEFORE jitter — worst case is MAX_S * 1.5 (jitter fixed to 1.25 here)
    assert sleeps == [collector._PPLX_429_BACKOFF_MAX_S * 1.25]


@pytest.mark.asyncio
async def test_429_jitter_uses_configured_bounds(monkeypatch, _env_and_stubs):
    # Independently verify the jitter call itself is random.uniform(1.0, 1.5) —
    # overrides the fixture's fixed-1.25 stub for this test only.
    jitter_calls: list[tuple] = []

    def _spy_jitter(lo, hi):
        jitter_calls.append((lo, hi))
        return 1.0

    monkeypatch.setattr(collector.random, "uniform", _spy_jitter)
    _install_client(monkeypatch, [_http_status_error(429, headers={"Retry-After": "3"}), _OKResp()])

    await collector.search_news_perplexity("q")

    assert jitter_calls == [(1.0, 1.5)]


@pytest.mark.asyncio
async def test_double_429_fails_open_and_alerts_once(monkeypatch, _env_and_stubs):
    # Retry also 429s → prior contract exactly: alert path + return "" — bounded, not infinite.
    calls = _install_client(monkeypatch, [_http_status_error(429, headers={"Retry-After": "1"})])
    api_alerts: list = []

    async def _api_spy(provider, exc, context=""):
        api_alerts.append(type(exc).__name__)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _api_spy)

    out = await collector.search_news_perplexity("q")

    assert out == ""                          # fail-open contract UNCHANGED
    assert len(calls) == 2                    # one retry, then give up (bounded)
    assert api_alerts == ["HTTPStatusError"]   # exactly one alert, with the final exc
