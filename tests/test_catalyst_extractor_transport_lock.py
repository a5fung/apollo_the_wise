"""Structural output lock on the earnings-metrics extractor (2026-08-10).

`catalyst_metrics_extractor._call_claude_extraction` was the last high-risk caller on the
freeform raw-JSON transport — no `system=` lock, no `tools=` — and it is the caller whose
failure opened #543: on the sonnet-5 move its output grew past the old ceiling (truncating
mid-JSON, #542) and a thinking block arrived first (breaking the positional read, #544).
Both prior fixes were patches (bigger ceiling, safer reader); nothing constrained the
response SHAPE, so nothing stopped the output growing again on the next model change.

These tests pin the structural lock chosen by the 2026-08-10 /simplify altitude review —
the `system=` JSON-API lock, byte-identical to theme_validation's, which measurably holds
output growth to ~1.0x across model changes (vs >=2.7x freeform; shared/output_ceilings.py)
— plus the two loudness rules around it:

  * a TRUNCATED response is discarded, never parsed (a cut landing after a closing brace
    would otherwise parse and grade on a cut answer — the exact judge-transport trap);
  * a persisted transport FAILURE is never served as a cached result (#543 DoD — one
    transient API failure must not become a permanent skip for that ticker+date).
"""
import asyncio
import json

import pytest

# The lock string the theme engine's validation call carries — the measured-sufficient
# weak form of the structural lock. The extractor must carry the SAME bytes so the two
# stay one pattern.
_EXPECTED_LOCK = ("You are a JSON API. Respond with valid JSON only. "
                  "No prose, no markdown, no explanation.")


def _run(coro):
    return asyncio.run(coro)


# ── fake transport ────────────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient; captures the outgoing request payload."""
    captured = None
    payload = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.captured = json
        return _FakeResponse(_FakeAsyncClient.payload)


def _sonnet5_response(text, stop_reason="end_turn"):
    """A realistic sonnet-5 raw-HTTP body: thinking block FIRST (the 08-06 outage shape),
    then the text answer; usage present so the cost meter logs a row."""
    return {
        "id": "msg_test", "type": "message", "role": "assistant",
        "model": "claude-sonnet-5", "stop_reason": stop_reason, "stop_sequence": None,
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": text},
        ],
        "usage": {"input_tokens": 4000, "output_tokens": 1500,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }


@pytest.fixture()
def wired(monkeypatch):
    """Wire the fake transport + a recording cost logger into the real module."""
    import httpx
    from agents.market_intelligence import spend_tracker

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.captured = None
    _FakeAsyncClient.payload = None

    cost_calls = []

    async def _record(**kwargs):
        cost_calls.append(kwargs)

    monkeypatch.setattr(spend_tracker, "log_anthropic_call_safe", _record)
    return cost_calls


# ── the lock is on the wire ───────────────────────────────────────────────────────────────

def test_request_carries_the_json_api_system_lock(wired):
    """The structural fix itself: the request must carry the system lock. Without it the
    transport is back to freeform and the output is unbounded on the next model change."""
    from agents.market_intelligence.catalyst_metrics_extractor import _call_claude_extraction

    _FakeAsyncClient.payload = _sonnet5_response('{"extraction_quality": "low"}')
    _run(_call_claude_extraction("prompt"))

    assert _FakeAsyncClient.captured is not None, "no request captured"
    assert _FakeAsyncClient.captured.get("system") == _EXPECTED_LOCK, (
        "the extractor's request no longer carries the JSON-API system lock — the "
        "transport is freeform again, the exact defect class behind #542/#543")


def test_the_lock_does_not_touch_the_user_prompt(wired):
    """TRANSPORT change, not a grading change: the user prompt must pass through verbatim."""
    from agents.market_intelligence.catalyst_metrics_extractor import _call_claude_extraction

    _FakeAsyncClient.payload = _sonnet5_response('{"extraction_quality": "low"}')
    _run(_call_claude_extraction("THE EXACT PROMPT BYTES"))

    assert _FakeAsyncClient.captured["messages"] == [
        {"role": "user", "content": "THE EXACT PROMPT BYTES"}]


# ── sonnet-5 shape parses; cost logging is intact ─────────────────────────────────────────

def test_thinking_first_fenced_response_parses_and_logs_cost(wired):
    """The realistic sonnet-5 shape (thinking first, fenced JSON) must yield the parsed
    dict, and the cost row must keep caller='catalyst_metrics_extractor' so api_usage
    history stays continuous."""
    from agents.market_intelligence.catalyst_metrics_extractor import _call_claude_extraction

    answer = {"q_revenue_usd": {"value": 82900000, "yoy_pct": 11.6,
                                "sources": ["polygon"], "confidence": "high"},
              "extraction_quality": "high"}
    _FakeAsyncClient.payload = _sonnet5_response("```json\n" + json.dumps(answer) + "\n```")

    result = _run(_call_claude_extraction("prompt"))

    assert result == answer
    assert len(wired) == 1
    assert wired[0]["caller"] == "catalyst_metrics_extractor"
    assert wired[0]["response"] is _FakeAsyncClient.payload


# ── truncation is discarded, never parsed ─────────────────────────────────────────────────

def test_truncated_response_is_discarded_even_when_it_parses(wired):
    """The trap the judge transport measured (#543): a max_tokens cut can land where the
    partial STILL parses (e.g. right after a closing brace) and would grade on a cut
    answer. stop_reason is the model's own report — a truncated response is a failure,
    parseable or not."""
    from agents.market_intelligence.catalyst_metrics_extractor import _call_claude_extraction

    _FakeAsyncClient.payload = _sonnet5_response(
        '{"extraction_quality": "high"}', stop_reason="max_tokens")

    result = _run(_call_claude_extraction("prompt"))

    assert result is None, (
        "a max_tokens-truncated response was parsed and returned — grading on a cut "
        "answer is the AMRC/RDW failure mode (#543)")
    # The cost row must still land (it is what fires the live truncation alarm).
    assert len(wired) == 1 and wired[0]["caller"] == "catalyst_metrics_extractor"


# ── a persisted failure is never served as cache (#543 DoD) ───────────────────────────────

class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, row):
        self._row = row

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._row))


def _wire_lookup_row(monkeypatch, raw_json):
    from agents.market_intelligence import catalyst_metrics_extractor as cme

    row = {"q_revenue_yoy_pct": None, "extraction_quality": "low", "raw_json": raw_json}

    async def _pool():
        return _FakePool(row)

    monkeypatch.setattr(cme, "get_pool", _pool)
    return cme


def test_lookup_never_serves_a_transport_failure_as_cache(monkeypatch):
    """ep_detector persists whatever extract_earnings_metrics returns — including the
    extraction_call_failed placeholder. Served as cache, one transient API failure became
    a PERMANENT skip for that ticker+date (#543 DoD: 'never persist a failure as a cached
    result'). A failure row must read as no-cache so callers re-extract."""
    from datetime import date

    cme = _wire_lookup_row(monkeypatch, {
        "extraction_quality": "low", "extraction_error": "extraction_call_failed",
        "_polygon_news_count": 3, "_alpaca_news_count": 2,
    })
    assert _run(cme.lookup_cached_metrics("TEST", date(2026, 8, 10))) is None


def test_lookup_still_serves_real_extractions_including_low_quality(monkeypatch):
    """A low-quality-but-REAL extraction (sparse corpus, no extraction_error) is a
    legitimate cached result — the fail-closed gate logic reads it. Only transport
    failures are barred."""
    from datetime import date

    real = {"extraction_quality": "low", "q_revenue_usd": None,
            "reasoning_brief": "corpus sparse"}
    cme = _wire_lookup_row(monkeypatch, dict(real))
    assert _run(cme.lookup_cached_metrics("TEST", date(2026, 8, 10))) == real
