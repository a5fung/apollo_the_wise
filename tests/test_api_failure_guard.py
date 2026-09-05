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
    # Fix-1 (2026-07-14) update: the TELEGRAM is still deduped by the DB
    # lookback (same provider+class already alerted this window — the legacy
    # row has no tg= marker, which counts as alert-carrying), but the AUDIT ROW
    # is now written for EVERY failure (tg=0 = no Telegram accompanied it).
    db = _DBStub(existing=[
        {"event_type": "api_failure_fmp", "summary": "FMP API FAILURE class=http_4xx HTTP 403"},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(403))

    assert sent == []                       # Telegram suppressed (same provider+class)
    assert len(db.written) == 1             # ... but the audit row ALWAYS lands
    assert "tg=0" in db.written[0][1]


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
    # Fix-1 (2026-07-14) update: the pre-gate collapses the TELEGRAM burst
    # (still exactly one send), but every failure now writes its audit row —
    # the second row carries tg=0 (no Telegram accompanied it).
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("polygon", _http_status_error(503))
    await llm_health.alert_api_failure("polygon", _http_status_error(503))

    assert len(sent) == 1
    assert len(db.written) == 2
    assert "tg=1" in db.written[0][1]
    assert "tg=0" in db.written[1][1]


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


# ── (5) #370 alpaca input-side: the AMBIENT broker READS alert, keep their propagation ──
#
# alpaca is the 4th provider (the broker, real-money-critical). Scope = the bulk READS only
# (get_account / get_all_positions / get_open_orders) — on a pure read any exception genuinely IS
# an API failure. The submit/bracket paths are EXCLUDED (a naked-guard RuntimeError there is a
# safety-success, not an outage, and they're already loud via the entry pipeline).

def test_classify_alpaca_retry_exception():
    # alpaca-py's retry-exhausted wrapper carries no status code; treat as transport so a
    # persistent broker outage still alerts (the corner case the status-code path misses).
    class RetryException(Exception):
        pass
    assert llm_health.classify_api_failure(RetryException("retries exhausted")) == "transport"


@pytest.mark.asyncio
async def test_alpaca_get_account_alerts_then_reraises(monkeypatch):
    import agents.market_intelligence.broker.alpaca_client as ac
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append((provider, context))
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    class _Boom:
        def get_account(self):
            raise _http_status_error(503)
    monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _Boom())

    with pytest.raises(httpx.HTTPStatusError):        # get_account RE-RAISES (propagation preserved)
        await ac.get_account(account_mode="live")
    assert alerts == [("alpaca", "get_account")]      # alerted BEFORE the re-raise


@pytest.mark.asyncio
async def test_alpaca_get_all_positions_alerts_then_returns_empty(monkeypatch):
    import agents.market_intelligence.broker.alpaca_client as ac
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append((provider, context))
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    class _Boom:
        def get_all_positions(self):
            raise _http_status_error(500)
    monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _Boom())

    out = await ac.get_all_positions(account_mode="live")
    assert out == []                                  # [] fallback PRESERVED (no behavior change)
    assert alerts == [("alpaca", "get_all_positions")]  # but the silent [] is now LOUD


@pytest.mark.asyncio
async def test_alpaca_get_open_orders_alerts_then_returns_empty(monkeypatch):
    import agents.market_intelligence.broker.alpaca_client as ac
    alerts: list = []

    async def _spy(provider, exc, context=""):
        alerts.append((provider, context))
    monkeypatch.setattr(llm_health, "maybe_alert_api_failure", _spy)

    class _Boom:
        def get_orders(self, request):
            raise _http_status_error(502)
    monkeypatch.setattr(ac, "get_trading_client", lambda mode=None: _Boom())

    out = await ac.get_open_orders(account_mode="live")
    assert out == []
    assert alerts == [("alpaca", "get_open_orders")]


# ── (6) #406 — the REAL registration, not the stubbed maybe_alert_api_failure ──
#
# Every test above (and every alpaca_client call site) stubs
# `llm_health.maybe_alert_api_failure` itself, so none of them ever exercised
# `_API_PROVIDERS` / `_PROVIDER_CLASS` for "alpaca" — the exact gap that let
# alpaca silently fall through to "other" (mis-bucketed event_type) with the
# wrong-domain data-API consequence sentence. These call the REAL
# `alert_api_failure("alpaca", ...)` with only db/Telegram mocked, so a
# regression of either the registration or the provider-class copy fails here.

@pytest.mark.asyncio
async def test_alpaca_registered_not_bucketed_as_other(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("alpaca", _http_status_error(503),
                                       context="get_account")

    assert len(db.written) == 1
    event_type, summary, _detail = db.written[0]
    assert event_type == "api_failure_alpaca"          # NOT api_failure_other
    assert "class=http_5xx" in summary


@pytest.mark.asyncio
async def test_alpaca_alert_uses_broker_domain_consequence(monkeypatch):
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("alpaca", _http_status_error(503),
                                       context="get_account")

    assert len(sent) == 1
    msg = sent[0]
    assert "BROKER-API" in msg
    assert "position sync" in msg.lower() and "trade state" in msg.lower()
    # the wrong-domain data-API sentence must NOT appear
    assert "catalyst grade" not in msg.lower()
    assert "news corpus" not in msg.lower()


@pytest.mark.asyncio
async def test_data_provider_alert_keeps_data_domain_consequence(monkeypatch):
    # Guard the other direction: a genuine data-API provider must keep the
    # ORIGINAL sentence — the #406 fix must not bleed broker copy onto data.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("polygon", _http_status_error(500))

    assert len(sent) == 1
    msg = sent[0]
    assert "DATA-API" in msg
    assert "catalyst grade" in msg.lower() and "news corpus" in msg.lower()
    assert "position sync" not in msg.lower() and "trade state" not in msg.lower()


# ── (7) Fix-1 (2026-07-14) — TRANSIENT vs ACTIONABLE Telegram triage ──────────
#
# The alert-vs-audit rule: self-healing/transient failures (Perplexity timeout,
# FMP per-symbol 402) → mi_audit_log ONLY; Telegram is reserved for actionable
# (auth/credit) or SUSTAINED (real-outage) failures. The audit row is ALWAYS
# written either way — visibility never drops, only the push-noise does.

from datetime import datetime as _dt, timedelta as _td, timezone as _tz


def _utc_ago(minutes: float) -> "_dt":
    return _dt.now(_tz.utc) - _td(minutes=minutes)


@pytest.mark.asyncio
async def test_transient_timeout_writes_audit_but_no_telegram(monkeypatch):
    # THE reported noise: a single Perplexity timeout (fail-open, self-recovers)
    # must not page the operator — audit row only.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("perplexity", httpx.ReadTimeout("slow"),
                                       context="news search")

    assert sent == []                        # NO Telegram for a single blip
    assert len(db.written) == 1              # audit row ALWAYS written
    et, summary, _ = db.written[0]
    assert et == "api_failure_perplexity"
    assert "class=timeout" in summary
    assert "tg=0" in summary


@pytest.mark.asyncio
async def test_fmp_per_symbol_402_is_audit_only(monkeypatch):
    # The other reported noise: FMP per-symbol HTTP 402 (plan-tier gate on SOME
    # symbols, fail-open, most symbols work) — audit row only, no Telegram.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(402),
                                       context="GET /profile")

    assert sent == []
    assert len(db.written) == 1
    assert "class=http_4xx" in db.written[0][1]
    assert "tg=0" in db.written[0][1]


@pytest.mark.asyncio
async def test_auth_401_still_alerts_immediately(monkeypatch):
    # ACTIONABLE stays immediate: a 401 (revoked/invalid key) is terminal and
    # operator-actionable — the triage must NOT demote it.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("fmp", _http_status_error(401))

    assert len(sent) == 1
    assert "tg=1" in db.written[0][1]


@pytest.mark.asyncio
async def test_sustained_timeout_escalates_to_telegram(monkeypatch):
    # A timeout persisting across scan cycles IS a real outage: ≥3 same-class
    # failures in the window spanning ≥30 min → Telegram (labeled SUSTAINED).
    db = _DBStub(existing=[
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0 — news search",
         "created_at": _utc_ago(45)},
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0 — news search",
         "created_at": _utc_ago(20)},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("perplexity", httpx.ReadTimeout("slow"),
                                       context="news search")

    assert len(sent) == 1                    # sustained outage DOES page
    assert "SUSTAINED" in sent[0]
    assert len(db.written) == 1
    assert "tg=1" in db.written[0][1]


@pytest.mark.asyncio
async def test_tight_burst_without_time_spread_stays_quiet(monkeypatch):
    # ≥3 failures inside ONE fetch loop (a few minutes) is one blip, not an
    # outage — the ≥30-min spread requirement keeps it audit-only. (This is
    # what keeps a per-symbol FMP 402 burst from re-creating the daily noise.)
    db = _DBStub(existing=[
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0",
         "created_at": _utc_ago(3)},
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0",
         "created_at": _utc_ago(1)},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("perplexity", httpx.ReadTimeout("slow"))

    assert sent == []
    assert len(db.written) == 1
    assert "tg=0" in db.written[0][1]


@pytest.mark.asyncio
async def test_sustained_alert_deduped_within_window(monkeypatch):
    # Once the sustained escalation HAS paged (a tg=1 row in the window), the
    # next transient failure writes its row but does not re-page.
    db = _DBStub(existing=[
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0",
         "created_at": _utc_ago(90)},
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=1",
         "created_at": _utc_ago(40)},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("perplexity", httpx.ReadTimeout("slow"))

    assert sent == []
    assert len(db.written) == 1
    assert "tg=0" in db.written[0][1]


@pytest.mark.asyncio
async def test_alpaca_broker_timeout_stays_immediate(monkeypatch):
    # BROKER CARVE-OUT: alpaca is real-money-critical — a timeout on a broker
    # read is NEVER demoted to audit-only; it pages immediately as before.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("alpaca", httpx.ReadTimeout("slow"),
                                       context="get_account")

    assert len(sent) == 1
    assert "BROKER-API" in sent[0]
    assert "tg=1" in db.written[0][1]


def test_is_transient_api_failure_row_parses_summary_markers():
    # The morning-brief banner classifies rows from their summary markers.
    assert llm_health.is_transient_api_failure_row({
        "event_type": "api_failure_perplexity",
        "summary": "PERPLEXITY API FAILURE class=timeout tg=0 — news search",
    }) is True
    assert llm_health.is_transient_api_failure_row({
        "event_type": "api_failure_fmp",
        "summary": "FMP API FAILURE class=http_4xx HTTP 402 tg=0 — GET /profile",
    }) is True
    # 403 = auth/plan revocation → actionable, stays loud
    assert llm_health.is_transient_api_failure_row({
        "event_type": "api_failure_fmp",
        "summary": "FMP API FAILURE class=http_4xx HTTP 403 tg=1",
    }) is False
    # broker rows are never quiet
    assert llm_health.is_transient_api_failure_row({
        "event_type": "api_failure_alpaca",
        "summary": "ALPACA API FAILURE class=timeout tg=1 — get_account",
    }) is False
    # non-api_failure rows and unparseable summaries stay loud
    assert llm_health.is_transient_api_failure_row({
        "event_type": "validation_error", "summary": "class=timeout"}) is False
    assert llm_health.is_transient_api_failure_row({
        "event_type": "api_failure_fmp", "summary": "garbled"}) is False


def test_briefing_banner_downgrades_transient_api_rows():
    # The 🔴 other-errs bucket must NOT contain transient api_failure rows —
    # they collapse to the single quiet 🔵 line. Actionable ones stay 🔴.
    from agents.market_intelligence.briefing import _format_morning_briefing

    text = _format_morning_briefing(
        regime={"regime": "Bull", "ep_threshold": 70},
        ep_alerts=[],
        briefing_date="2026-07-14",
        overnight_errors=[
            {"event_type": "api_failure_perplexity",
             "summary": "PERPLEXITY API FAILURE class=timeout tg=0 — news search"},
            {"event_type": "api_failure_fmp",
             "summary": "FMP API FAILURE class=http_4xx HTTP 403 tg=1"},
        ],
    )
    assert "1 transient data-API blip(s)" in text          # quiet 🔵 line
    assert "PERPLEXITY API FAILURE" not in text            # not echoed as 🔴
    assert "FMP API FAILURE class=http_4xx HTTP 403" in text  # actionable stays loud


# ── PROBE-ORIGIN carve-out (2026-09-04 alert sweep, #623) ─────────────────────
#
# A probe hitting a live collector helper from the same process/key as the app
# must never page the operator or corrupt a genuine live escalation, but the
# audit trail must still capture it. APOLLO_CALL_ORIGIN=probe is the marker.

@pytest.mark.asyncio
async def test_probe_origin_writes_audit_row_but_never_alerts(monkeypatch):
    monkeypatch.setenv("APOLLO_CALL_ORIGIN", "probe")
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    # A non-transient class (http_4xx) would normally page immediately.
    await llm_health.alert_api_failure("polygon", _http_status_error(400),
                                       context="GET /v3/reference/tickers/(3458 rows)")

    assert sent == []
    assert len(db.written) == 1
    et, summary, _ = db.written[0]
    assert et == "api_failure_polygon"
    assert "origin=probe" in summary
    assert "tg=0" in summary
    # The live pre-gate/dedup state must be untouched by a probe call — a live
    # failure on the same (provider, class) right after must still be free to fire.
    assert llm_health._last_api_alert_ts == {}


@pytest.mark.asyncio
async def test_probe_origin_does_not_weaken_a_following_live_alert(monkeypatch):
    # THE "did not weaken the live alarm" proof: a probe failure immediately
    # followed by a real live failure on the same (provider, class) must still
    # page — the probe call must leave no dedup/sustained state behind.
    db = _DBStub(existing=[])
    sent = _patch_db_and_telegram(monkeypatch, db)

    monkeypatch.setenv("APOLLO_CALL_ORIGIN", "probe")
    await llm_health.alert_api_failure("polygon", _http_status_error(400),
                                       context="GET /v3/reference/tickers/(3458 rows)")
    assert sent == []

    monkeypatch.delenv("APOLLO_CALL_ORIGIN", raising=False)
    await llm_health.alert_api_failure("polygon", _http_status_error(400),
                                       context="GET /v3/reference/tickers/AAPL")

    assert len(sent) == 1                    # the live call still pages
    assert len(db.written) == 2
    assert "origin=probe" not in db.written[1][1]


@pytest.mark.asyncio
async def test_probe_origin_rows_excluded_from_sustained_lookback(monkeypatch):
    # Three probe-origin timeouts sitting in the lookback window must NOT count
    # toward a live timeout's sustained-escalation threshold (>=3, >=30min spread).
    db = _DBStub(existing=[
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0 origin=probe — probe run",
         "created_at": _utc_ago(45)},
        {"event_type": "api_failure_perplexity",
         "summary": "PERPLEXITY API FAILURE class=timeout tg=0 origin=probe — probe run",
         "created_at": _utc_ago(20)},
    ])
    sent = _patch_db_and_telegram(monkeypatch, db)

    await llm_health.alert_api_failure("perplexity", httpx.ReadTimeout("slow"),
                                       context="news search")

    assert sent == []                        # a single LIVE timeout stays quiet —
    assert len(db.written) == 1              # the probe rows above must not have
    assert "tg=0" in db.written[0][1]         # been counted toward "sustained"
    assert "origin=probe" not in db.written[0][1]


def test_morning_briefing_merge_drops_probe_origin_rows():
    # The morning digest's own audit-log queries would otherwise re-surface a
    # probe-origin api_failure row (it was never Telegrammed, but nothing about
    # the %api_failure% audit-log query itself excludes it) as a 🔴 overnight
    # engine event. _merge_overnight_error_rows is the one place that filters it
    # before _format_morning_briefing ever sees the list.
    from agents.market_intelligence.briefing import _merge_overnight_error_rows

    merged = _merge_overnight_error_rows(
        [{"id": 1, "event_type": "validation_error", "summary": "class=timeout"}],
        [{"id": 2, "event_type": "api_failure_polygon",
          "summary": "POLYGON API FAILURE class=http_4xx HTTP 400 tg=0 origin=probe "
                     "— GET /v3/reference/tickers/(3458 rows)"},
         {"id": 3, "event_type": "api_failure_fmp",
          "summary": "FMP API FAILURE class=http_4xx HTTP 403 tg=1"}],
        [],
    )
    ids = {r["id"] for r in merged}
    assert ids == {1, 3}                     # the probe row (id 2) is dropped
    assert all("origin=probe" not in (r.get("summary") or "") for r in merged)


def test_morning_briefing_merge_dedups_by_id_across_lists():
    from agents.market_intelligence.briefing import _merge_overnight_error_rows

    row = {"id": 7, "event_type": "validation_error", "summary": "class=timeout"}
    merged = _merge_overnight_error_rows([row], [row], [])
    assert len(merged) == 1
