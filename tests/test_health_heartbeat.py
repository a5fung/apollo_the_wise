"""The guard's own HEARTBEAT — "the silent-failure guard itself hasn't run" (PLAN #370 increment 4).

THE most important gap #370 closes: increments 1+3 catch OTHER silent failures, but they both run in
the 17:30 `_post_nightly_audit_job`. If THAT job dies, NOTHING runs and NOTHING alerts — the guard
fails silently, the worst possible case. The heartbeat (hosted independently in the 09:00 morning
briefing) detects the dead guard.

The bar is HIGHER than usual: a BUGGY heartbeat gives FALSE CONFIDENCE the guard is alive when it
isn't. So we prove, mostly mock-free, that:
  (1) the last sweep audit older than the expected cutoff → ALERT fires (Telegram + audit) — the
      stale-guard case, the DoD demonstration;
  (2) a fresh sweep audit (since the last expected run) → NO Telegram, `health_heartbeat_ok` audit;
  (3) NO sweep audit at all → ALERT (the guard has never run / its audit is broken);
  (4) a DB error in the check → LOUD (degraded Telegram + `health_heartbeat_error`), NEVER a silent
      `health_heartbeat_ok`.

Mirrors `test_health_checks_null_sweep.py`: the PURE decisions (`_expected_sweep_cutoff`,
`_evaluate_heartbeat`) are tested directly with zero mocking first, then integration tests drive the
real path via a fake conn with the ET clock pinned.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_heartbeat,
    _expected_sweep_cutoff,
    run_health_heartbeat,
)

_ET = ZoneInfo("America/New_York")


# ── Pure decision: _expected_sweep_cutoff (no mocking) ────────────────────────


def test_cutoff_weekday_morning_is_last_night_1730():
    # Tuesday 09:00 → the sweep ran last night (Monday 17:30 ET).
    now = datetime(2026, 6, 23, 9, 0, tzinfo=_ET)  # a Tuesday
    cutoff = _expected_sweep_cutoff(now)
    assert cutoff == datetime(2026, 6, 22, 17, 30, tzinfo=_ET)  # Monday 17:30


def test_cutoff_monday_morning_rolls_back_over_weekend_to_friday():
    # THE Monday false-fire guard: Monday 09:00 → the last sweep ran FRIDAY 17:30 (no weekend sweep).
    # A flat 26h threshold would false-fire here (~63h); the cutoff correctly expects Friday.
    now = datetime(2026, 6, 22, 9, 0, tzinfo=_ET)  # a Monday
    cutoff = _expected_sweep_cutoff(now)
    assert cutoff == datetime(2026, 6, 19, 17, 30, tzinfo=_ET)  # the prior Friday 17:30


def test_cutoff_after_1730_is_tonight():
    # Wednesday 18:00 → tonight's 17:30 sweep is already due+past → cutoff is today.
    now = datetime(2026, 6, 24, 18, 0, tzinfo=_ET)  # a Wednesday, after 17:30
    cutoff = _expected_sweep_cutoff(now)
    assert cutoff == datetime(2026, 6, 24, 17, 30, tzinfo=_ET)


def test_cutoff_sunday_rolls_back_to_friday():
    # Sunday (any hour) → no sweep Sat/Sun → cutoff is the prior Friday 17:30.
    now = datetime(2026, 6, 21, 11, 0, tzinfo=_ET)  # a Sunday
    cutoff = _expected_sweep_cutoff(now)
    assert cutoff == datetime(2026, 6, 19, 17, 30, tzinfo=_ET)  # Friday


# ── Pure decision: _evaluate_heartbeat (no mocking) ───────────────────────────


def test_stale_audit_flags():
    cutoff = datetime(2026, 6, 22, 17, 30, tzinfo=_ET)
    latest = cutoff - timedelta(days=1)  # a day before the expected run → stale
    verdict = _evaluate_heartbeat(latest, cutoff)
    assert verdict is not None
    assert verdict["reason"] == "stale"


def test_fresh_audit_does_not_flag():
    cutoff = datetime(2026, 6, 22, 17, 30, tzinfo=_ET)
    latest = cutoff + timedelta(minutes=5)  # the sweep landed just after the expected run → alive
    assert _evaluate_heartbeat(latest, cutoff) is None


def test_audit_exactly_at_cutoff_does_not_flag():
    # Boundary: a sweep audit AT the cutoff counts as fresh (>=).
    cutoff = datetime(2026, 6, 22, 17, 30, tzinfo=_ET)
    assert _evaluate_heartbeat(cutoff, cutoff) is None


def test_no_audit_ever_flags_never():
    cutoff = datetime(2026, 6, 22, 17, 30, tzinfo=_ET)
    verdict = _evaluate_heartbeat(None, cutoff)
    assert verdict is not None
    assert verdict["reason"] == "never"


# ── Integration: real path via a fake conn + pinned ET clock ──────────────────


class _FakeConn:
    """Stand-in for an asyncpg conn. `fetchval` returns the configured MAX(created_at) for the sweep
    events. If `raise_on_fetch` is set, it raises — to exercise the LOUD-on-DB-failure path."""

    def __init__(self, latest_ts, raise_on_fetch: bool = False):
        self._latest_ts = latest_ts
        self._raise = raise_on_fetch

    async def fetchval(self, sql, *args):
        if self._raise:
            raise RuntimeError("simulated DB outage")
        assert "mi_audit_log" in sql and "MAX(created_at)" in sql
        return self._latest_ts


@pytest.fixture
def _captured_telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


@pytest.fixture
def _captured_audit(monkeypatch):
    events: list[tuple] = []

    async def _audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(health_checks, "log_audit_event", _audit)
    return events


@pytest.fixture
def _pinned_now(monkeypatch):
    """Pin the heartbeat's ET clock to Tuesday 09:00 (so the expected cutoff is Monday 17:30)."""
    now = datetime(2026, 6, 23, 9, 0, tzinfo=_ET)  # a Tuesday morning
    monkeypatch.setattr(health_checks, "_now_et", lambda: now)
    return now


@pytest.mark.asyncio
async def test_stale_guard_fires_telegram_and_audit(_captured_telegram, _captured_audit, _pinned_now):
    # DoD demonstration: the last sweep audit is from 3 days ago (well before Monday 17:30) → the
    # guard has gone dark → the ALERT MUST fire. This is the "the sweeps may be dead" case.
    stale = datetime(2026, 6, 20, 17, 30, tzinfo=_ET)  # Saturday — older than the Monday cutoff
    conn = _FakeConn(latest_ts=stale)

    summary = await run_health_heartbeat(conn)

    assert summary["status"] == "alert"
    # ONE grouped Telegram, naming the dead-guard condition.
    assert len(_captured_telegram) == 1
    assert "SILENT-FAILURE GUARD HASN'T RUN" in _captured_telegram[0]
    # Audit row written with the stale event type.
    assert any(e[0] == "health_heartbeat_stale" for e in _captured_audit)
    # And it did NOT falsely report ok.
    assert not any(e[0] == "health_heartbeat_ok" for e in _captured_audit)


@pytest.mark.asyncio
async def test_fresh_guard_no_telegram_audit_only(_captured_telegram, _captured_audit, _pinned_now):
    # The sweeps ran last night (Monday 17:30) → fresh → NO Telegram, audit-only ok.
    fresh = datetime(2026, 6, 22, 17, 30, 12, tzinfo=_ET)  # Monday 17:30, just after the expected run
    conn = _FakeConn(latest_ts=fresh)

    summary = await run_health_heartbeat(conn)

    assert summary["status"] == "ok"
    assert _captured_telegram == []  # Telegram reserved for real failures
    assert any(e[0] == "health_heartbeat_ok" for e in _captured_audit)
    assert not any(e[0] == "health_heartbeat_stale" for e in _captured_audit)


@pytest.mark.asyncio
async def test_no_sweep_audit_ever_fires_alert(_captured_telegram, _captured_audit, _pinned_now):
    # No sweep audit at all (MAX → NULL) → the guard has never run / its audit is broken → ALERT.
    conn = _FakeConn(latest_ts=None)

    summary = await run_health_heartbeat(conn)

    assert summary["status"] == "alert"
    assert len(_captured_telegram) == 1
    assert "ever" in _captured_telegram[0].lower()
    assert any(e[0] == "health_heartbeat_stale" for e in _captured_audit)
    assert not any(e[0] == "health_heartbeat_ok" for e in _captured_audit)


@pytest.mark.asyncio
async def test_db_error_is_loud_not_silent(_captured_telegram, _captured_audit, _pinned_now):
    # A heartbeat that CANNOT run its own check must FAIL LOUD — NEVER silently report ok.
    conn = _FakeConn(latest_ts=None, raise_on_fetch=True)

    summary = await run_health_heartbeat(conn)

    assert summary["status"] == "error"
    # Degraded Telegram sent — the operator is told the guard is UNVERIFIED, not "fine".
    assert len(_captured_telegram) == 1
    assert "HEARTBEAT BROKEN" in _captured_telegram[0]
    # Degraded audit written; and CRITICALLY no false `health_heartbeat_ok`.
    assert any(e[0] == "health_heartbeat_error" for e in _captured_audit)
    assert not any(e[0] == "health_heartbeat_ok" for e in _captured_audit)
