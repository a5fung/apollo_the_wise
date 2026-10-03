"""#466 - the swallowed failures the zero-tolerance gate forced into the open.

Each test drives the REAL function with its dependency failing and asserts BOTH halves of the
contract: the failure is now LOGGED (with the exception and the context a person debugging
at 3am needs), AND the original fallback is exactly what it was (same return value, same
fail-open / fail-soft direction, no new raise). Nothing here changes behaviour - the proof
of that across all 26 touched files is the AST-normalised diff in the commit message.

Sites chosen to span the kinds: a data fetch (fundamentals), a fail-soft guess that feeds a
trade-grade decision (earnings_calendar, catalyst_materiality), a fail-open calendar
(health_checks), a DB-dedup lookup that fails open (news_source_quality), an inner
audit/Telegram guard (failure_policy), a hot loop that now reports ONE aggregate
(minute_volume), a Redis-backed UX read (telegram), a cross-service tool call (orchestrator)
and an unreachable-service probe (router).
"""
import logging
import sys
import types

import pytest


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


def _joined(caplog):
    return " | ".join(r.getMessage() for r in _warnings(caplog))


# ── fundamentals: a yfinance shape/fetch failure is no longer invisible ─────────

def test_gross_margin_trend_failure_logs_and_still_says_unknown(caplog):
    from agents.market_intelligence.fundamentals import _gross_margin_trend
    with caplog.at_level(logging.WARNING):
        out = _gross_margin_trend(object())          # no .empty -> AttributeError inside
    assert out == "unknown"
    assert "gross-margin trend" in _joined(caplog)


@pytest.mark.asyncio
async def test_get_fundamentals_info_fetch_failure_names_the_ticker(monkeypatch, caplog):
    from agents.market_intelligence import fundamentals

    class _T:
        quarterly_income_stmt = None
        quarterly_financials = None
        income_stmt = None
        financials = None
        calendar = None
        earnings_estimate = None
        revenue_estimate = None

        @property
        def info(self):
            raise RuntimeError("yahoo 429")

    fake = types.SimpleNamespace(Ticker=lambda sym: _T())
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    with caplog.at_level(logging.WARNING):
        out = await fundamentals.get_fundamentals("ZZZZ")
    assert out["ticker"] == "ZZZZ" and "error" not in out        # still degrades gracefully
    msg = _joined(caplog)
    assert "ZZZZ" in msg and ".info fetch failed" in msg and "yahoo 429" in msg


# ── earnings_calendar: the fail-soft guess feeding the boost gate is now logged ─────

def test_revenue_stage_lookup_failure_logs_and_stays_fail_soft_true(monkeypatch, caplog):
    from agents.market_intelligence import earnings_calendar

    class _Boom:
        def __init__(self, sym):
            raise ConnectionError("yfinance down")

        calendar = None

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_Boom))
    with caplog.at_level(logging.WARNING):
        out = earnings_calendar._check_revenue_stage_sync("QQQQ")
    assert out is True                                           # direction unchanged
    assert "QQQQ" in _joined(caplog) and "yfinance down" in _joined(caplog)


@pytest.mark.asyncio
async def test_revenue_stage_async_wrapper_failure_logs_and_stays_fail_soft(monkeypatch, caplog):
    from agents.market_intelligence import earnings_calendar

    def _raise(_t):
        raise RuntimeError("thread pool gone")

    earnings_calendar._REV_STAGE_CACHE.pop("WWWW", None)
    monkeypatch.setattr(earnings_calendar, "_check_revenue_stage_sync", _raise)
    with caplog.at_level(logging.WARNING):
        out = await earnings_calendar.is_revenue_stage("WWWW")
    earnings_calendar._REV_STAGE_CACHE.pop("WWWW", None)
    assert out is True
    assert "WWWW" in _joined(caplog) and "thread pool gone" in _joined(caplog)


# ── catalyst_materiality: a non-credit LLM failure used to abstain with no trace ─────

@pytest.mark.asyncio
async def test_materiality_llm_failure_logs_then_abstains(monkeypatch, caplog):
    from agents.market_intelligence import catalyst_materiality as cm
    from agents.market_intelligence import llm_health

    async def _boom(*a, **k):
        raise TimeoutError("judge timed out")

    alerted = []

    async def _alert(label, exc):
        alerted.append((label, type(exc).__name__))

    monkeypatch.setattr(cm, "judge_materiality_llm", _boom)
    monkeypatch.setattr(llm_health, "maybe_alert_credit_exhausted", _alert)
    with caplog.at_level(logging.WARNING):
        out = await cm.assess_materiality(
            object(), company="ACME", sector="Tech", market_cap=None,
            catalyst="record quarter", analysis="")
    assert out == (None, "abstain")                              # fail-OPEN contract unchanged
    assert alerted == [("catalyst materiality", "TimeoutError")]  # the credit alert still fires
    assert "ACME" in _joined(caplog) and "judge timed out" in _joined(caplog)


# ── health_checks: a dead calendar lookup is fail-open AND audible ──────────────────

def test_trading_day_calendar_failure_logs_and_fails_open(monkeypatch, caplog):
    from datetime import date
    from agents.market_intelligence import health_checks, trading_calendar

    def _boom(_d):
        raise RuntimeError("calendar service down")

    monkeypatch.setattr(trading_calendar, "get_market_status", _boom)
    with caplog.at_level(logging.WARNING):
        assert health_checks._is_trading_day(date(2026, 10, 3)) is True
    assert "calendar service down" in _joined(caplog)


# ── news_source_quality: a failed dedup read sends the page (fail-open) and says why ──

@pytest.mark.asyncio
async def test_drift_dedup_lookup_failure_logs_and_fails_open(monkeypatch, caplog):
    from agents.market_intelligence import db, news_source_quality

    async def _boom():
        raise ConnectionError("pool exhausted")

    monkeypatch.setattr(db, "get_pool", _boom)
    with caplog.at_level(logging.WARNING):
        out = await news_source_quality._drift_telegram_already_sent_recently()
    assert out is False                                          # => the Telegram is SENT
    assert "pool exhausted" in _joined(caplog)


# ── failure_policy: the audit row / page that could not be written is no longer vanishing ──

@pytest.mark.asyncio
async def test_advisory_fail_open_logs_a_failed_audit_write_and_still_returns_default(monkeypatch, caplog):
    from agents.market_intelligence import db
    from agents.market_intelligence.failure_policy import advisory_fail_open

    async def _audit_boom(*a, **k):
        raise ConnectionError("db shares the outage")

    monkeypatch.setattr(db, "log_audit_event", _audit_boom)

    @advisory_fail_open(default="DEFAULT", audit_event="x_failed", label="probe")
    async def f():
        raise ValueError("original failure")

    with caplog.at_level(logging.WARNING):
        assert await f() == "DEFAULT"
    msg = _joined(caplog)
    assert "original failure" in msg                             # pre-existing line
    assert "audit row for the failure above NOT written" in msg and "db shares the outage" in msg


@pytest.mark.asyncio
async def test_trade_state_fail_loud_logs_failed_audit_and_telegram_and_still_reraises(monkeypatch, caplog):
    from agents.market_intelligence import briefing, db
    from agents.market_intelligence.failure_policy import trade_state_fail_loud

    async def _audit_boom(*a, **k):
        raise ConnectionError("audit down")

    async def _tg_boom(*a, **k):
        raise ConnectionError("telegram down")

    monkeypatch.setattr(db, "log_audit_event", _audit_boom)
    monkeypatch.setattr(briefing, "send_telegram_message", _tg_boom)

    @trade_state_fail_loud(label="probe")
    async def f():
        raise ValueError("trade-state failure")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="trade-state failure"):   # still re-raises
            await f()
    msg = _joined(caplog)
    assert "audit row for the failure above NOT written" in msg and "audit down" in msg
    assert "Telegram page for the failure above NOT sent" in msg and "telegram down" in msg


# ── minute_volume: malformed bars are skipped as before, but ONE aggregate says how many ──

@pytest.mark.asyncio
async def test_malformed_bars_are_skipped_and_counted_in_one_warning(monkeypatch, caplog):
    from agents.market_intelligence import minute_volume

    async def _bars(ticker, a, b):
        return [{"t": "not-a-timestamp", "v": 5}, {"t": "also-bad", "v": 7},
                {"t": None, "v": 9},                           # normal skip (not malformed)
                {"t": "bad-three", "v": 1}]

    monkeypatch.setattr(minute_volume, "get_minute_bars", _bars)
    with caplog.at_level(logging.WARNING):
        out = await minute_volume._refresh_one_ticker("MMMM", "2026-01-01", "2026-02-01")
    assert out == []                                             # insufficient history, as before
    agg = [r for r in _warnings(caplog) if "malformed" in r.getMessage()]
    assert len(agg) == 1                                         # ONE line, not one per bar
    assert "MMMM" in agg[0].getMessage() and "3 of 4" in agg[0].getMessage()


@pytest.mark.asyncio
async def test_clean_bars_produce_no_malformed_warning(monkeypatch, caplog):
    from agents.market_intelligence import minute_volume

    async def _bars(ticker, a, b):
        return [{"t": None, "v": 9}]

    monkeypatch.setattr(minute_volume, "get_minute_bars", _bars)
    with caplog.at_level(logging.WARNING):
        assert await minute_volume._refresh_one_ticker("MMMM", "2026-01-01", "2026-02-01") == []
    assert not [r for r in _warnings(caplog) if "malformed" in r.getMessage()]


# ── telegram: a Redis/DB blip in onboarding state is logged, defaults unchanged ──────

@pytest.mark.asyncio
async def test_persona_lookup_failure_logs_and_reports_not_configured(monkeypatch, caplog):
    import core.memory
    from channels.telegram import TelegramChannel

    async def _boom(*a, **k):
        raise ConnectionError("memory db down")

    monkeypatch.setattr(core.memory, "search_memories", _boom)
    with caplog.at_level(logging.WARNING):
        assert await TelegramChannel._is_persona_configured(object(), 42) is False
        assert await TelegramChannel._load_persona(object(), 42) == ("Apollo", None)
    msg = _joined(caplog)
    assert msg.count("memory db down") == 2 and "42" in msg


@pytest.mark.asyncio
async def test_onboarding_state_redis_failure_logs_and_keeps_defaults(monkeypatch, caplog):
    import core.confirmations
    from channels.telegram import TelegramChannel

    async def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(core.confirmations, "get_redis", _boom)
    with caplog.at_level(logging.WARNING):
        assert await TelegramChannel._get_onboarding_state(object(), 7) is None
        assert await TelegramChannel._set_onboarding_state(object(), 7, "x") is None
        assert await TelegramChannel._clear_onboarding_state(object(), 7) is None
    assert _joined(caplog).count("redis down") == 3


# ── orchestrator: a failed cross-service tool call is logged and the reply text is unchanged ──

@pytest.mark.asyncio
async def test_tweet_tool_failure_logs_and_returns_the_same_text(monkeypatch, caplog):
    from core.orchestrator import Apollo

    obj = object.__new__(Apollo)

    async def _boom(*a, **k):
        raise ConnectionError("market agent unreachable")

    monkeypatch.setattr(obj, "_call_market_endpoint", _boom, raising=False)
    with caplog.at_level(logging.WARNING):
        out = await Apollo._post_tweet(obj, {"text": "hello"})
    assert out == "Tweet failed: market agent unreachable"       # byte-identical reply
    assert "/tweet" in _joined(caplog) and "market agent unreachable" in _joined(caplog)


# ── router: an unreachable market agent is still None, now with a reason in the log ──────

@pytest.mark.asyncio
async def test_pipeline_status_unreachable_logs_and_returns_none(monkeypatch, caplog):
    import core.router as router

    class _Boom:
        def __init__(self, *a, **k):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(router, "get_agent_url", lambda name: "http://market.invalid")
    monkeypatch.setattr(router.httpx, "AsyncClient", _Boom)
    with caplog.at_level(logging.WARNING):
        assert await router.get_market_pipeline_status() is None
    assert "connection refused" in _joined(caplog)
