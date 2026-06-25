"""#380 / #370 — DATA-API loud-failure guard.

The class this closes: a data API (Polygon / FMP / Perplexity-news) returns a
4xx/5xx or times out, the wrapper raises, and the CALLER swallows it (fail-open
→ empty fallback) — so the catalyst grade / RS universe / news corpus silently
degrades. The FMP /api/v3/ 403 hid for months exactly this way (0 FMP errors in
72h of logs because nothing surfaced it). The guard alerts AT THE WRAPPER's catch
point, deduped per (provider, error-class), then lets the wrapper propagate as
it already did.

Covers:
  (1) classify_api_failure buckets httpx HTTP/transport/timeout errors and
      returns None for a non-network exception (a code bug must NOT cry wolf).
  (2) alert_api_failure fires an audit row + Telegram, deduped per
      (provider, error-class) — a 5xx after a 4xx is NOT suppressed.
  (3) PROPAGATION per wrapper: _fmp_get / _polygon_get RE-RAISE (caller fallback
      still runs); search_news_perplexity still returns "" (contract unchanged).
  (4) the Perplexity site does NOT double-fire credit + api_failure on a 401/402.
"""
from __future__ import annotations

import httpx
import pytest

from agents.market_intelligence import llm_health

_REQ = httpx.Request("GET", "https://example.com/x")


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("expected raise_for_status to raise")


# ── (1) classifier — positive HTTP/transport/timeout match, None on code bugs ──

def test_classify_buckets_4xx_and_5xx():
    assert llm_health.classify_api_failure(_http_status_error(403)) == "http_4xx"
    assert llm_health.classify_api_failure(_http_status_error(402)) == "http_4xx"
    assert llm_health.classify_api_failure(_http_status_error(500)) == "http_5xx"
    assert llm_health.classify_api_failure(_http_status_error(503)) == "http_5xx"


def test_classify_buckets_timeout_and_connect():
    assert llm_health.classify_api_failure(httpx.ReadTimeout("slow")) == "timeout"
    assert llm_health.classify_api_failure(httpx.ConnectTimeout("slow")) == "timeout"
    assert llm_health.classify_api_failure(httpx.ConnectError("refused")) == "connect"


def test_classify_buckets_generic_transport_error():
    # A non-connect/timeout httpx transport failure → "transport".
    assert llm_health.classify_api_failure(httpx.RemoteProtocolError("boom")) == "transport"


def test_classify_returns_none_for_non_network_exceptions():
    # THE guard against crying wolf: a parsing/code bug is NOT "the provider is
    # down" — it must classify to None so no API-down alert fires.
    import json
    assert llm_health.classify_api_failure(ValueError("bad")) is None
    assert llm_health.classify_api_failure(KeyError("missing")) is None
    assert llm_health.classify_api_failure(
        json.JSONDecodeError("x", "doc", 0)) is None


def test_classify_includes_429_for_data_layer():
    # Deliberate inverse of the credit classifier: a 429 reaching the data-API
    # except is sustained (Polygon retries 3× first) and SHOULD surface.
    assert llm_health.classify_api_failure(_http_status_error(429)) == "http_4xx"


def test_classify_carves_out_404_as_non_alerting():
    # A 404 is "this ITEM doesn't exist" (per-call data condition), NOT a
    # provider outage. Polygon per-ticker endpoints 404 on delisted/unknown
    # tickers all day — alerting on those would be chronic false "Polygon DOWN"
    # noise. The real target (FMP block / auth revocation) is 401/403, which
    # stays loud. So 404 → None; 403 → http_4xx (loud).
    assert llm_health.classify_api_failure(_http_status_error(404)) is None
    assert llm_health.classify_api_failure(_http_status_error(403)) == "http_4xx"
    assert llm_health.classify_api_failure(_http_status_error(401)) == "http_4xx"


@pytest.mark.asyncio
async def test_404_does_not_alert_end_to_end(monkeypatch):
    # End-to-end: a 404 reaching alert_api_failure writes no row + sends nothing.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)
    await llm_health.alert_api_failure("polygon", _http_status_error(404),
                                       context="GET /v3/reference/tickers/ZZZZ")
    assert db.written == []
    assert sent == []


def test_classify_never_raises():
    assert llm_health.classify_api_failure(object()) is None  # type: ignore[arg-type]


# ── (2) alert path: audit row + Telegram, deduped per (provider, error-class) ──

@pytest.fixture(autouse=True)
def _reset_pregate(monkeypatch):
    monkeypatch.setattr(llm_health, "_last_api_alert_ts", {})


class _DBStub:
    """Stands in for db.get_audit_log + db.log_audit_event. `existing` controls
    the dedup lookback; `written` records audit rows actually written."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.written: list[tuple] = []

    async def get_audit_log(self, *, event_type=None, since_hours=None, limit=None):
        return [r for r in self.existing if r.get("event_type") == event_type][:limit or 1]

    async def log_audit_event(self, event_type, summary, detail=""):
        self.written.append((event_type, summary, detail))


def _patch_db_and_telegram(monkeypatch, db):
    import agents.market_intelligence.db as db_mod
    monkeypatch.setattr(db_mod, "get_audit_log", db.get_audit_log)
    monkeypatch.setattr(db_mod, "log_audit_event", db.log_audit_event)

    sent: list[str] = []

    async def fake_send(msg, parse_mode=None):
        sent.append(msg)
        return True

    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", fake_send)
    return sent


@pytest.mark.asyncio
async def test_alert_fires_audit_and_telegram(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(403), context="GET /income-statement")

    assert len(db.written) == 1
    et, summary, _detail = db.written[0]
    assert et == "api_failure_fmp"
    assert "class=http_4xx" in summary          # the dedup marker is present
    assert "HTTP 403" in summary
    assert len(sent) == 1
    assert "FMP" in sent[0].upper()


@pytest.mark.asyncio
async def test_no_alert_on_non_network_exception(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("polygon", ValueError("parse bug"))

    assert db.written == []
    assert sent == []


@pytest.mark.asyncio
async def test_dedup_suppresses_same_provider_and_class(monkeypatch):
    db = _DBStub(existing=[
        {"event_type": "api_failure_fmp", "summary": "FMP API FAILURE class=http_4xx HTTP 403"},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(403))

    assert db.written == []      # suppressed by the DB lookback (same provider+class)
    assert sent == []


@pytest.mark.asyncio
async def test_dedup_does_not_suppress_different_class(monkeypatch):
    # A 5xx right after a 4xx must STILL alert — the dedup key includes the class,
    # so a flapping 500 after a 403 is not swallowed for 6h.
    db = _DBStub(existing=[
        {"event_type": "api_failure_fmp", "summary": "FMP API FAILURE class=http_4xx HTTP 403"},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(500))

    assert len(db.written) == 1
    assert "class=http_5xx" in db.written[0][1]
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_dedup_is_per_provider(monkeypatch):
    db = _DBStub(existing=[
        {"event_type": "api_failure_polygon", "summary": "POLYGON API FAILURE class=http_5xx HTTP 500"},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(500))  # different provider

    assert len(db.written) == 1
    assert db.written[0][0] == "api_failure_fmp"
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_inproc_pregate_collapses_same_class_burst(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("polygon", _http_status_error(503))
    await llm_health.alert_api_failure("polygon", _http_status_error(503))

    assert len(sent) == 1
    assert len(db.written) == 1


@pytest.mark.asyncio
async def test_maybe_alert_never_raises(monkeypatch):
    # Safe from any wrapper's except — even if classification explodes.
    def _boom(exc):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(llm_health, "classify_api_failure", _boom)
    await llm_health.maybe_alert_api_failure("fmp", _http_status_error(403))  # no raise


# ── (3) PROPAGATION per wrapper (the part most likely to ship broken) ──
#
# Each wrapper must keep its EXISTING propagation: the LOUDNESS is the alert, NOT
# a contract change. _fmp_get / _polygon_get re-raise; search_news_perplexity
# returns "".

@pytest.mark.asyncio
async def test_fmp_get_alerts_then_reraises(monkeypatch):
    import agents.market_intelligence.collector as collector

    monkeypatch.setenv("FMP_API_KEY", "k")
    alerts: list[tuple] = []

    async def _spy(provider, exc, context=""):
        alerts.append((provider, type(exc).__name__))

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    class _Resp:
        status_code = 403
        def raise_for_status(self):
            raise _http_status_error(403)
        def json(self):
            return {}

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    with pytest.raises(httpx.HTTPStatusError):       # propagation PRESERVED (re-raise)
        await collector._fmp_get("/income-statement", {"symbol": "AAPL"})

    assert alerts == [("fmp", "HTTPStatusError")]    # alerted BEFORE the re-raise


@pytest.mark.asyncio
async def test_polygon_get_alerts_then_reraises(monkeypatch):
    import agents.market_intelligence.collector as collector

    monkeypatch.setenv("POLYGON_API_KEY", "k")
    alerts: list[tuple] = []

    async def _spy(provider, exc, context=""):
        alerts.append((provider, type(exc).__name__))

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    class _Resp:
        status_code = 500
        def raise_for_status(self):
            raise _http_status_error(500)
        def json(self):
            return {}

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    with pytest.raises(httpx.HTTPStatusError):       # re-raise so callers' fallback runs
        await collector._polygon_get("/v2/aggs/x")

    assert alerts == [("polygon", "HTTPStatusError")]


@pytest.mark.asyncio
async def test_polygon_get_does_not_alert_on_retried_429(monkeypatch):
    # A 429 that is RETRIED and then succeeds must NOT alert — only a sustained
    # final failure reaches the guard.
    import agents.market_intelligence.collector as collector

    monkeypatch.setenv("POLYGON_API_KEY", "k")
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    async def _no_sleep(*a, **k):
        return None
    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)

    seq = [429, 200]

    class _Resp:
        def __init__(self, code):
            self.status_code = code
        def raise_for_status(self):
            if self.status_code >= 400:
                raise _http_status_error(self.status_code)
        def json(self):
            return {"ok": True}

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            return _Resp(seq.pop(0))

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    out = await collector._polygon_get("/v2/aggs/x")
    assert out == {"ok": True}
    assert alerts == []                              # the retried 429 did NOT alert


@pytest.mark.asyncio
async def test_perplexity_returns_empty_and_alerts_on_5xx(monkeypatch):
    # Perplexity contract is UNCHANGED: it returns "" on failure. A non-credit
    # 5xx must alert via the data-API guard (NOT the credit alarm).
    import agents.market_intelligence.collector as collector

    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    api_alerts: list = []
    credit_alerts: list = []

    async def _api_spy(provider, exc, context=""):
        api_alerts.append(provider)

    async def _credit_spy(context, exc, provider="anthropic"):
        credit_alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _api_spy)
    monkeypatch.setattr(llm_health, "maybe_alert_credit_exhausted", _credit_spy)

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            raise _http_status_error(503)            # server error, not credit

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    out = await collector.search_news_perplexity("why did X gap up?")
    assert out == ""                                 # contract preserved
    assert api_alerts == ["perplexity"]              # data-API guard fired
    # The credit-exhaustion path is invoked unconditionally but a 503 is not a
    # credit error, so it is a no-op there — the maybe_ wrapper still gets called.


@pytest.mark.asyncio
async def test_perplexity_402_does_not_double_fire(monkeypatch):
    # A 402 IS a credit error — it must fire the credit alarm but NOT also the
    # data-API alarm (the operator-hated double-ping).
    import agents.market_intelligence.collector as collector

    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    api_alerts: list = []

    async def _api_spy(provider, exc, context=""):
        api_alerts.append(provider)

    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _api_spy)

    # Leave maybe_alert_credit_exhausted real but stub its DB/telegram so it
    # doesn't touch a pool; we only care that api_failure is NOT called.
    async def _noop_credit(context, exc, provider="anthropic"):
        return None
    monkeypatch.setattr(llm_health, "maybe_alert_credit_exhausted", _noop_credit)

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            raise _http_status_error(402)            # Payment Required = credit

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda *a, **k: _Client())

    out = await collector.search_news_perplexity("why did X gap up?")
    assert out == ""
    assert api_alerts == []                          # NO data-API alarm on a credit 402
