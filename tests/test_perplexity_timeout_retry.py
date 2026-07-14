"""Fix-2a (2026-07-14) — search_news_perplexity: ONE bounded retry on timeout.

The 2026-07 CPI-morning miss: a single transient Perplexity timeout blanked the
morning-brief overnight summary (fail-open "") with no second attempt, so the
brief said "no clear catalyst" on a CPI day. The fix: exactly one fresh retry
on TIMEOUT only; every other failure keeps the prior single-attempt fail-open
path (alert + return "") — behavior-preserving on the happy path and on
non-timeout failures.
"""
from __future__ import annotations

import httpx
import pytest

import agents.market_intelligence.collector as collector
from agents.market_intelligence import llm_health

_REQ = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, request=_REQ)
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
            "choices": [{"message": {"content": "CPI printed hot; indexes sold off."}}],
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
    # Cost meter is additive-only; keep it away from the DB in tests.
    import agents.market_intelligence.spend_tracker as spend_tracker

    async def _noop_meter(**kwargs):
        return None

    monkeypatch.setattr(spend_tracker, "log_perplexity_call", _noop_meter)


@pytest.mark.asyncio
async def test_timeout_then_success_retries_once(monkeypatch):
    # THE fix: a single transient timeout no longer blanks the result.
    calls = _install_client(monkeypatch, [httpx.ReadTimeout("slow"), _OKResp()])
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    out = await collector.search_news_perplexity("what moved the market?")

    assert out == "CPI printed hot; indexes sold off."
    assert len(calls) == 2               # exactly one retry
    assert alerts == []                  # a recovered blip never alerts


@pytest.mark.asyncio
async def test_double_timeout_fails_open_and_alerts_once(monkeypatch):
    # Retry also times out → prior contract exactly: alert path + return "".
    calls = _install_client(monkeypatch, [httpx.ReadTimeout("slow")])
    api_alerts: list = []
    credit_alerts: list = []

    async def _api_spy(provider, exc, context=""):
        api_alerts.append(type(exc).__name__)

    async def _credit_spy(context, exc, provider="anthropic"):
        credit_alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _api_spy)
    monkeypatch.setattr(llm_health, "maybe_alert_credit_exhausted", _credit_spy)

    out = await collector.search_news_perplexity("q")

    assert out == ""                     # fail-open contract UNCHANGED
    assert len(calls) == 2               # one retry, then give up (bounded)
    assert api_alerts == ["ReadTimeout"]  # exactly one alert, with the final exc


@pytest.mark.asyncio
async def test_non_timeout_failure_does_not_retry(monkeypatch):
    # Behavior-preserving: a 503 (or any non-timeout failure) keeps the prior
    # SINGLE-attempt path — no retry, alert, return "".
    calls = _install_client(monkeypatch, [_http_status_error(503)])
    api_alerts: list = []

    async def _api_spy(provider, exc, context=""):
        api_alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _api_spy)

    out = await collector.search_news_perplexity("q")

    assert out == ""
    assert len(calls) == 1               # no retry for non-timeout failures
    assert api_alerts == ["perplexity"]


@pytest.mark.asyncio
async def test_happy_path_single_attempt(monkeypatch):
    # Happy path: one successful attempt, result returned untouched.
    calls = _install_client(monkeypatch, [_OKResp()])
    out = await collector.search_news_perplexity("q")
    assert out == "CPI printed hot; indexes sold off."
    assert len(calls) == 1
