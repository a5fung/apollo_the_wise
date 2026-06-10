"""#259 — the two failure-policy decorators (declared, not re-decided)."""
import asyncio

import pytest

from agents.market_intelligence.failure_policy import (
    advisory_fail_open, trade_state_fail_loud)


def _run(coro):
    return asyncio.run(coro)


# ── advisory_fail_open ───────────────────────────────────────────────────────
def test_advisory_passthrough_on_success():
    @advisory_fail_open(default=-1)
    async def ok():
        return 42
    assert _run(ok()) == 42


def test_advisory_returns_default_on_exception():
    @advisory_fail_open(default=-1)
    async def boom():
        raise RuntimeError("nope")
    assert _run(boom()) == -1


def test_advisory_callable_default_stays_fresh():
    @advisory_fail_open(default=list)
    async def boom():
        raise ValueError("x")
    a, b = _run(boom()), _run(boom())
    assert a == [] and b == [] and a is not b


def test_advisory_writes_audit_row(monkeypatch):
    calls = []

    async def fake_audit(event, summary, detail=""):
        calls.append((event, summary))

    import agents.market_intelligence.db as db
    monkeypatch.setattr(db, "log_audit_event", fake_audit)

    @advisory_fail_open(default=None, audit_event="my_advisory_failed")
    async def boom():
        raise KeyError("k")
    assert _run(boom()) is None
    assert calls and calls[0][0] == "my_advisory_failed"
    assert "KeyError" in calls[0][1]


def test_advisory_rejects_sync_function():
    with pytest.raises(TypeError):
        @advisory_fail_open()
        def sync_fn():
            return 1


# ── trade_state_fail_loud ────────────────────────────────────────────────────
def test_loud_reraises_after_alerting(monkeypatch):
    audits, telegrams = [], []

    async def fake_audit(event, summary, detail=""):
        audits.append(event)

    async def fake_send(text, *a, **kw):
        telegrams.append(text)
        return True

    import agents.market_intelligence.db as db
    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(db, "log_audit_event", fake_audit)
    monkeypatch.setattr(briefing, "send_telegram_message", fake_send)

    @trade_state_fail_loud()
    async def boom():
        raise RuntimeError("broker said no")

    with pytest.raises(RuntimeError):
        _run(boom())
    assert audits == ["trade_state_failure"]
    assert telegrams and "broker said no" in telegrams[0]


def test_loud_escapes_exception_text(monkeypatch):
    telegrams = []

    async def fake_audit(*a, **kw):
        pass

    async def fake_send(text, *a, **kw):
        telegrams.append(text)
        return True

    import agents.market_intelligence.db as db
    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(db, "log_audit_event", fake_audit)
    monkeypatch.setattr(briefing, "send_telegram_message", fake_send)

    @trade_state_fail_loud(reraise=False)
    async def boom():
        raise ValueError("qty <1> & weird")

    assert _run(boom()) is None
    assert "&lt;1&gt; &amp; weird" in telegrams[0]


def test_loud_survives_telegram_outage(monkeypatch):
    async def fake_audit(*a, **kw):
        pass

    async def dead_send(*a, **kw):
        raise ConnectionError("telegram down")

    import agents.market_intelligence.db as db
    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(db, "log_audit_event", fake_audit)
    monkeypatch.setattr(briefing, "send_telegram_message", dead_send)

    @trade_state_fail_loud()
    async def boom():
        raise RuntimeError("original")

    with pytest.raises(RuntimeError, match="original"):
        _run(boom())
