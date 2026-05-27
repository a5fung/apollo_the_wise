"""Regression tests for L2 detector holiday awareness (#120, 2026-05-26).

Memorial Day 2026-05-25 (Monday) ran with the existing scheduler firing
'9m_alerts_per_day' = 0 sample. The trimmed-median baseline then
absorbs the 0, and the next trading day (Tuesday 5/26) sees a normal
value that drifts upward against a contaminated baseline → false-
positive L2.

Fix: short-circuit `_compute_anomaly` and `_record_metric_sample` on
non-trading days, and defense-in-depth filter on read in
`_fetch_history` / `_regime_conditional_baseline` so already-recorded
holiday samples don't poison live baselines.

These tests pin the holiday gate; trading-calendar correctness is
exchange_calendars's responsibility.
"""
from collections import namedtuple
from datetime import date

import pytest

from agents.market_intelligence import system_audit
from agents.market_intelligence.system_audit import _is_non_trading_day


_FakeStatus = namedtuple("FakeStatus", ["is_trading_day", "reason"])


def _mock_calendar(monkeypatch, *, trading_dates: set[date]):
    """Replace get_market_status with a deterministic lookup so tests
    don't depend on exchange_calendars being installed locally."""
    def _stub(d):
        if d in trading_dates:
            return _FakeStatus(True, "trading day (test)")
        return _FakeStatus(False, "non-trading (test)")
    monkeypatch.setattr(system_audit, "get_market_status", _stub)


# ── Helper behavior with deterministic calendar ──────────────────────────────

def test_holiday_returns_true(monkeypatch):
    """A non-trading date returns True."""
    _mock_calendar(monkeypatch, trading_dates={date(2026, 5, 26)})
    assert _is_non_trading_day(date(2026, 5, 25)) is True  # Memorial Day


def test_trading_day_returns_false(monkeypatch):
    _mock_calendar(monkeypatch, trading_dates={date(2026, 5, 26)})
    assert _is_non_trading_day(date(2026, 5, 26)) is False


def test_calendar_exception_fails_open(monkeypatch):
    """If exchange_calendars raises, treat as trading day so genuine
    breakage still fires alerts. The fail-open log warning is enough."""
    def _boom(_d):
        raise RuntimeError("exchange_calendars not installed")
    monkeypatch.setattr(system_audit, "get_market_status", _boom)
    assert _is_non_trading_day(date(2026, 5, 25)) is False


# ── Integration: _record_metric_sample skips on holidays ─────────────────────

@pytest.mark.asyncio
async def test_record_metric_sample_skipped_on_holiday(monkeypatch):
    """When et_today() is a holiday, _record_metric_sample is a no-op."""
    _mock_calendar(monkeypatch, trading_dates={date(2026, 5, 26)})
    monkeypatch.setattr(system_audit, "et_today", lambda: date(2026, 5, 25))

    captured = []
    async def _fake_log(event_type, summary=None, detail=None):
        captured.append((event_type, summary, detail))

    monkeypatch.setattr(system_audit, "log_audit_event", _fake_log)

    await system_audit._record_metric_sample("test_metric", 42.0)
    assert captured == [], "should have skipped logging on Memorial Day"


@pytest.mark.asyncio
async def test_record_metric_sample_writes_on_trading_day(monkeypatch):
    """When et_today() is a regular trading day, _record_metric_sample writes
    the audit row as usual."""
    _mock_calendar(monkeypatch, trading_dates={date(2026, 5, 26)})
    monkeypatch.setattr(system_audit, "et_today", lambda: date(2026, 5, 26))

    captured = []
    async def _fake_log(event_type, summary=None, detail=None):
        captured.append((event_type, summary, detail))

    monkeypatch.setattr(system_audit, "log_audit_event", _fake_log)

    await system_audit._record_metric_sample("test_metric", 42.0)
    assert len(captured) == 1
    assert captured[0][0] == "metric_sample"
    assert captured[0][1] == "test_metric"
    assert "42" in (captured[0][2] or "")


# ── Integration: _compute_anomaly short-circuits ─────────────────────────────

@pytest.mark.asyncio
async def test_compute_anomaly_short_circuits_on_holiday(monkeypatch):
    """The classifier returns None immediately on a non-trading day —
    fetch_today is never called."""
    _mock_calendar(monkeypatch, trading_dates={date(2026, 5, 26)})
    monkeypatch.setattr(system_audit, "et_today", lambda: date(2026, 5, 25))

    call_count = {"n": 0}
    async def _fake_fetch(_conn):
        call_count["n"] += 1
        return 99.0

    spec = system_audit.MetricSpec(
        name="dummy", fetch_today=_fake_fetch, drill_sql="-- noop",
    )

    result = await system_audit._compute_anomaly(
        conn=None, metric=spec, current_regime=None,
    )
    assert result is None
    assert call_count["n"] == 0, "fetch_today must not run on a non-trading day"
