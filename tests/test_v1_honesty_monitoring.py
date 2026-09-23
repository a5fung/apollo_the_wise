"""v1.0-readiness honesty fixes (RED-3, 2026-07-12) — monitoring pins.

RED-3a: the 16:12 ET account_equity_snapshot job (feeds the drawdown breaker +
kill-scale bands) is watched by the job no-show invariant. It completes into
`mi_job_runs` via audit_wrap (it never writes `mi_job_log`), so the watchdog
accepts a status='success' mi_job_runs row today as completion evidence.

RED-3b: `drawdown_check_unavailable` (no "error" in the name) is explicitly
fetched + surfaced by the post-nightly silent-error alert — a fail-open
drawdown check is no longer silent.
"""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.audit_invariants import (
    _EXPECTED_JOBS,
    _MI_JOB_RUNS_SUCCESS_JOBS,
    check_job_no_show,
)

_ET = ZoneInfo("America/New_York")

# Wednesday 2026-07-08, 19:00 ET — all _EXPECTED_JOBS deadlines except
# evening_briefing (20:30) have passed.
_WED_EVENING = datetime(2026, 7, 8, 19, 0, tzinfo=_ET)


# ── RED-3a: 16:12 equity-snapshot job in the no-show watchdog ────────────────

def test_equity_snapshot_job_is_watched():
    assert "account_equity_snapshot" in _EXPECTED_JOBS
    # Deadline must sit AFTER the 16:12 ET cron fire (scheduler.py registers
    # CronTrigger(hour=16, minute=12)) so a normal run is never flagged.
    assert _EXPECTED_JOBS["account_equity_snapshot"] > time(16, 12)
    # Completion evidence for this job lives in mi_job_runs (audit_wrap), not
    # mi_job_log — the watchdog must know to look there.
    assert "account_equity_snapshot" in _MI_JOB_RUNS_SUCCESS_JOBS


@pytest.mark.asyncio
async def test_no_show_flags_missing_equity_snapshot():
    pool, conn = make_mock_pool()
    # fetch order in check_job_no_show: mi_job_log rows, mi_job_runs success
    # rows (runs-tracked job expected), mi_job_runs running rows.
    conn.fetch = AsyncMock(side_effect=[
        [{"job_name": "morning_briefing"}, {"job_name": "nightly_data_pull"}],
        [],  # no success run today — the job silently stopped
        [],  # nothing currently running
    ])
    ok, payload = await check_job_no_show(conn, now_et=_WED_EVENING)
    assert not ok
    assert "account_equity_snapshot" in payload["offending"]


@pytest.mark.asyncio
async def test_no_show_accepts_mi_job_runs_success_row():
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [{"job_name": "morning_briefing"}, {"job_name": "nightly_data_pull"}],
        [{"job_id": "account_equity_snapshot"}],  # clean run today
        [],
    ])
    ok, payload = await check_job_no_show(conn, now_et=_WED_EVENING)
    assert ok
    assert payload["offending"] == []


@pytest.mark.asyncio
async def test_no_show_quiet_before_equity_snapshot_deadline():
    # 16:30 ET: only morning_briefing (9:30) is expected; the equity job's
    # 16:45 deadline hasn't passed, so no success-row query is even issued
    # (side_effect has exactly the two fetches the code should make).
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [{"job_name": "morning_briefing"}],
        [],  # running check
    ])
    ok, payload = await check_job_no_show(
        conn, now_et=datetime(2026, 7, 8, 16, 30, tzinfo=_ET),
    )
    assert ok
    assert payload["offending"] == []


# ── RED-3b: drawdown_check_unavailable surfaces in the nightly alert ─────────

def _fake_audit_log(drawdown_rows):
    calls = []

    async def fake_get_audit_log(limit=40, event_type=None, since_hours=2,
                                 event_type_like=None):
        calls.append({
            "event_type": event_type,
            "event_type_like": event_type_like,
            "since_hours": since_hours,
        })
        if event_type == "drawdown_check_unavailable":
            return drawdown_rows
        return []

    return fake_get_audit_log, calls


@pytest.mark.asyncio
async def test_drawdown_unavailable_surfaces_in_nightly_alert(monkeypatch):
    import agents.market_intelligence.scheduler as sched

    fake_get, calls = _fake_audit_log([{
        "id": 101,
        "event_type": "drawdown_check_unavailable",
        "summary": "snapshot failed for live: APIError",
    }])
    sent = []

    async def fake_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(sched, "get_audit_log", fake_get)
    monkeypatch.setattr(sched, "send_telegram_message", fake_send)

    await sched._check_nightly_silent_errors()

    assert len(sent) == 1
    assert "drawdown_check_unavailable" in sent[0]
    assert "FAIL-OPEN" in sent[0]
    # Fetched by exact event type with AT LEAST the widened 6h window (the event fires
    # at 16:12; the nightly check can run past 18:12 — 2h would straddle it).
    # #625 (2026-09-05): the sweep's lookback became a watermark, so this window is now
    # `max(6, hours-since-last-sweep + 1)` and is often WIDER than 6. The invariant this
    # test defends is "never narrower than 6h", which is what the 16:12-vs-18:12 reasoning
    # above actually requires — the literal `== 6` was a proxy for it, and pinning the
    # exact number would fail every time the window legitimately widens.
    dd_calls = [c for c in calls if c["event_type"] == "drawdown_check_unavailable"]
    assert dd_calls and dd_calls[0]["since_hours"] >= 6


@pytest.mark.asyncio
async def test_nightly_alert_quiet_when_no_events(monkeypatch):
    import agents.market_intelligence.scheduler as sched

    fake_get, _calls = _fake_audit_log([])
    sent = []

    async def fake_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(sched, "get_audit_log", fake_get)
    monkeypatch.setattr(sched, "send_telegram_message", fake_send)

    await sched._check_nightly_silent_errors()
    assert sent == []
