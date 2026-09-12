"""#646 (a1) (2026-09-11) — nothing checked whether the 9 PM repair actually worked.

WHAT THE TASK GOT WRONG, corrected here because the test file is where a premise
should die: #646's line said a stop lost after ~16:30 sits bare "until the next
session's 09:31 — on a Friday ~64 hours". It does not. `evening_position_backstop`
runs 21:00 ET mon-fri and calls `sync_positions`, whose orphan loop re-places a
missing stop — which is exactly what protected OKTA on 2026-09-11 at 21:00, hours
before the crash-half fix was deployed. The real exposure that night was 16:02 to
21:00, about five hours, four of them inside extended-hours trading.

WHAT IS ACTUALLY MISSING, and is what this file pins: nothing verifies that 21:00
pass SUCCEEDED. `sync_positions`' orphan loop writes the stop pointer ONLY inside
its `if new_order:` branch; when its place attempts are exhausted it writes
`stop_ack_remediation_failed` and NO pointer, and the next look is 09:00. So the one
repairer standing between a bare position and the open can fail and say so only in an
audit row nobody reads at 21:0x.

THE DISCRIMINATING READING, since a check that cannot fail is this month's defect
class: the job writes `coverage_verified_evening` on EVERY run. A healthy night reads
covered == examined; the night sync_positions exhausts its attempts reads a gap and
pages. And "no page" can be told apart from "the job never ran" by the 09:00
heartbeat, which asserts the row exists.

⚠ DETECTION ONLY — pinned below. Whether this slot should also re-drive
`_ensure_stop_coverage` is the operator's fork; `check_position_coverage`'s own
docstring reserves it in writing.

MUTATION-PROVEN, each against the test it reddens:
  - drop `notify=False` at the call site -> test_the_job_bypasses_the_detectors_day_dedup;
  - make the audit row conditional on a gap -> test_a_clean_night_still_writes_its_row;
  - remove the `while cutoff.weekday() >= 5` rollback -> test_monday_morning_expects_fridays_run.
"""
from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from tests.test_position_coverage_check_527 import _trade, _live_stop, _wire

_ET = ZoneInfo("America/New_York")


# ── the job ───────────────────────────────────────────────────────────────────


def _wire_job(monkeypatch, *, result, live_enabled=True):
    """Patch the 21:10 job's surface: the detector, the audit log, Telegram."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence import constants as const

    audited: list[tuple] = []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    sent: list[str] = []

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    detector = AsyncMock(return_value=result)
    monkeypatch.setattr(om, "check_position_coverage", detector)
    monkeypatch.setattr(sch, "log_audit_event", _audit)
    monkeypatch.setattr(sch, "send_telegram_message", _tg)
    monkeypatch.setattr(sch, "notify_job_failure", AsyncMock())
    monkeypatch.setattr(const, "LIVE_TRADING_ENABLED", live_enabled)
    # the broker write surface — nothing here may ever be touched
    writes = {name: AsyncMock() for name in
              ("place_stop_order", "cancel_order", "replace_order", "close_position")}
    for name, mock in writes.items():
        if hasattr(om.alpaca, name):
            monkeypatch.setattr(om.alpaca, name, mock)
    return {"detector": detector, "audited": audited, "sent": sent, "writes": writes}


def _clean(n=3):
    return {"examined": n, "covered": n, "gaps": [], "check_failed": [], "deferred": []}


def _gap():
    return {"examined": 3, "covered": 2,
            "gaps": [{"trade_id": 382, "ticker": "OKTA", "target": 2.0, "live_qty": 0.0}],
            "check_failed": [], "deferred": []}


@pytest.mark.asyncio
async def test_a_clean_night_still_writes_its_row(monkeypatch):
    """THE DISCRIMINATING HALF. On a covered book the job must still leave a row —
    without it, a quiet night and a dead job are the same silence, which is the
    reading this repo refuses to accept."""
    from agents.market_intelligence import scheduler as sch
    h = _wire_job(monkeypatch, result=_clean(3))

    await sch._evening_coverage_verify_job()

    rows = [r for r in h["audited"] if r[0] == "coverage_verified_evening"]
    assert len(rows) == 1
    payload = json.loads(rows[0][2])
    assert payload["examined"] == 3 and payload["covered"] == 3
    assert payload["gaps"] == []
    assert not h["sent"], "a covered book must not page him — a guard that always fires is not a guard"


@pytest.mark.asyncio
async def test_a_position_still_bare_after_9pm_pages_him(monkeypatch):
    """The night sync_positions exhausted its attempts. He is told the ticker, the
    shares, that the 9 PM repair already tried, and what happens next."""
    from agents.market_intelligence import scheduler as sch
    h = _wire_job(monkeypatch, result=_gap())

    await sch._evening_coverage_verify_job()

    assert len(h["sent"]) == 1
    msg = h["sent"][0]
    assert "OKTA" in msg
    assert "2 sh" in msg
    assert "9:00 AM" in msg, "he must be told the true next automatic attempt"
    assert "/syncnow live" in msg, "give him the lever, not just the alarm"
    rows = [r for r in h["audited"] if r[0] == "coverage_verified_evening"]
    assert len(rows) == 1 and json.loads(rows[0][2])["gaps"], "the gap is durable, not just a Telegram"


@pytest.mark.asyncio
async def test_an_unreadable_broker_also_pages(monkeypatch):
    """FAIL-SAFE. A coverage read that failed is NOT 'covered' — it is unknown, and
    unknown at 9 PM on live money gets said out loud."""
    from agents.market_intelligence import scheduler as sch
    res = _clean(2)
    res["check_failed"] = [{"ticker": "HOOD", "error": "timeout"}]
    h = _wire_job(monkeypatch, result=res)

    await sch._evening_coverage_verify_job()

    assert len(h["sent"]) == 1 and "HOOD" in h["sent"][0]
    assert "coverage unknown" in h["sent"][0].lower()


@pytest.mark.asyncio
async def test_the_job_bypasses_the_detectors_day_dedup(monkeypatch):
    """THE WIRING PIN. The detector's own Telegram is deduped once per trade per ET
    day, so on any ticker it already paged intraday the evening page would be
    SWALLOWED — and "the 9 PM repair did not hold" is a new fact about that ticker."""
    from agents.market_intelligence import scheduler as sch
    h = _wire_job(monkeypatch, result=_gap())

    await sch._evening_coverage_verify_job()

    h["detector"].assert_awaited_once()
    assert h["detector"].await_args.kwargs.get("notify") is False


@pytest.mark.asyncio
async def test_the_job_places_cancels_and_replaces_nothing(monkeypatch):
    """THE LINE. `check_position_coverage`'s docstring reserves a second
    order-emission site for the operator. This job detects and reports, full stop —
    the repair arm waits on his ruling."""
    from agents.market_intelligence import scheduler as sch
    h = _wire_job(monkeypatch, result=_gap())

    await sch._evening_coverage_verify_job()

    for name, mock in h["writes"].items():
        mock.assert_not_called()


@pytest.mark.asyncio
async def test_the_job_noops_when_live_trading_is_off(monkeypatch):
    """Same guard every sibling money job carries."""
    from agents.market_intelligence import scheduler as sch
    h = _wire_job(monkeypatch, result=_gap(), live_enabled=False)

    await sch._evening_coverage_verify_job()

    h["detector"].assert_not_awaited()
    assert not h["sent"] and not h["audited"]


# ── registration + partition ──────────────────────────────────────────────────


def test_registered_at_2110_mon_fri_and_execution_owned():
    """21:10 is the first minute after which nothing else is scheduled to touch a
    stop until 09:00 — and it MUST be execution-owned, because an intelligence
    container holds no Alpaca credentials and an empty broker read there looks
    exactly like an empty broker (proven in prod 2026-09-11)."""
    import re
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    src = open("agents/market_intelligence/scheduler.py").read()
    block = re.search(
        r'id="evening_coverage_verify"', src)
    assert block, "the job is not registered"
    window = src[max(0, block.start() - 600): block.start()]
    assert "_evening_coverage_verify_job" in window
    assert re.search(r"CronTrigger\(hour=21,\s*minute=10,\s*day_of_week=\"mon-fri\"", window), window[-400:]
    assert "evening_coverage_verify" in EXECUTION_OWNED_JOB_IDS
    assert "evening_coverage_verify" not in INTELLIGENCE_OWNED_JOB_IDS


# ── the detector's notify switch ──────────────────────────────────────────────


async def _run(ctx, **kwargs):
    from agents.market_intelligence.broker.order_manager import check_position_coverage
    with ExitStack() as stack:
        for cm in ctx:
            stack.enter_context(cm)
        return await check_position_coverage(**kwargs)


@pytest.mark.asyncio
async def test_notify_false_keeps_the_durable_row_and_drops_only_the_message():
    """The switch moves the messenger, never the verdict."""
    ctx, audited, telegram_mock, _ = _wire([_trade(1, "OKTA", 2.0)], {"OKTA": []})

    result = await _run(ctx, notify=False)

    assert len(result["gaps"]) == 1
    assert any(e == "position_unprotected" for e, *_ in audited), "the durable row must still land"
    telegram_mock.assert_not_called()


@pytest.mark.asyncio
async def test_the_existing_caller_is_unchanged_by_default():
    """The 09:31-15:55 detector keeps sending its own page — the default must not
    have moved."""
    ctx, audited, telegram_mock, _ = _wire([_trade(1, "OKTA", 2.0)], {"OKTA": []})

    result = await _run(ctx)

    assert len(result["gaps"]) == 1
    telegram_mock.assert_called_once()


@pytest.mark.asyncio
async def test_notify_false_is_silent_on_a_covered_book_too():
    """No accidental new noise: covered is covered, row or no row."""
    ctx, audited, telegram_mock, _ = _wire([_trade(1, "AAPL", 4.0)],
                                           {"AAPL": [_live_stop("s1", 4.0)]})

    result = await _run(ctx, notify=False)

    assert result["covered"] == 1 and not result["gaps"]
    assert not audited
    telegram_mock.assert_not_called()


# ── the verifier's own liveness ───────────────────────────────────────────────


def test_tuesday_morning_expects_last_nights_run():
    from agents.market_intelligence.health_checks import _expected_evening_verify_cutoff
    cutoff = _expected_evening_verify_cutoff(datetime(2026, 9, 15, 9, 0, tzinfo=_ET))  # Tue
    assert (cutoff.month, cutoff.day, cutoff.hour, cutoff.minute) == (9, 14, 21, 10)   # Mon


def test_monday_morning_expects_fridays_run():
    """The weekend widens the window by itself — a Monday 09:00 check must expect
    FRIDAY 21:10, not Sunday's non-existent run, or it false-fires every week."""
    from agents.market_intelligence.health_checks import _expected_evening_verify_cutoff
    cutoff = _expected_evening_verify_cutoff(datetime(2026, 9, 14, 9, 0, tzinfo=_ET))  # Mon
    assert cutoff.weekday() == 4                                                       # Friday
    assert (cutoff.month, cutoff.day, cutoff.hour, cutoff.minute) == (9, 11, 21, 10)


def test_late_evening_expects_tonights_run():
    from agents.market_intelligence.health_checks import _expected_evening_verify_cutoff
    cutoff = _expected_evening_verify_cutoff(datetime(2026, 9, 16, 22, 0, tzinfo=_ET))  # Wed 22:00
    assert (cutoff.day, cutoff.hour, cutoff.minute) == (16, 21, 10)


def test_saturday_rolls_back_to_friday():
    from agents.market_intelligence.health_checks import _expected_evening_verify_cutoff
    cutoff = _expected_evening_verify_cutoff(datetime(2026, 9, 12, 10, 0, tzinfo=_ET))  # Sat
    assert cutoff.weekday() == 4 and cutoff.day == 11


@pytest.mark.asyncio
async def test_heartbeat_pages_when_the_verifier_never_ran(monkeypatch):
    from agents.market_intelligence import health_checks as hc
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=None)
    audited, sent = [], []

    async def _audit(evt, summary=None, detail=None):
        audited.append(evt)

    monkeypatch.setattr(hc, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(hc, "log_audit_event", _audit)
    monkeypatch.setattr(hc, "_now_et", lambda: datetime(2026, 9, 15, 9, 0, tzinfo=_ET))
    import agents.market_intelligence.briefing as br
    monkeypatch.setattr(br, "send_telegram_message", AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))

    out = await hc.run_evening_verify_heartbeat()

    assert out["status"] == "alert"
    assert "evening_verify_heartbeat_stale" in audited
    assert sent and "last night's stops" in sent[0]


@pytest.mark.asyncio
async def test_heartbeat_is_quiet_when_the_verifier_ran(monkeypatch):
    from agents.market_intelligence import health_checks as hc
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(return_value=datetime(2026, 9, 14, 21, 10, 5, tzinfo=_ET))
    audited, sent = [], []

    async def _audit(evt, summary=None, detail=None):
        audited.append(evt)

    monkeypatch.setattr(hc, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(hc, "log_audit_event", _audit)
    monkeypatch.setattr(hc, "_now_et", lambda: datetime(2026, 9, 15, 9, 0, tzinfo=_ET))
    import agents.market_intelligence.briefing as br
    monkeypatch.setattr(br, "send_telegram_message", AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))

    out = await hc.run_evening_verify_heartbeat()

    assert out["status"] == "ok"
    assert audited == ["evening_verify_heartbeat_ok"]
    assert not sent


@pytest.mark.asyncio
async def test_heartbeat_fails_loud_when_it_cannot_check(monkeypatch):
    """A heartbeat that cannot run its own check must never report healthy."""
    from agents.market_intelligence import health_checks as hc
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetchval = AsyncMock(side_effect=RuntimeError("db down"))
    audited, sent = [], []

    async def _audit(evt, summary=None, detail=None):
        audited.append(evt)

    monkeypatch.setattr(hc, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(hc, "log_audit_event", _audit)
    monkeypatch.setattr(hc, "_now_et", lambda: datetime(2026, 9, 15, 9, 0, tzinfo=_ET))
    import agents.market_intelligence.briefing as br
    monkeypatch.setattr(br, "send_telegram_message", AsyncMock(side_effect=lambda m, *a, **k: sent.append(m)))

    out = await hc.run_evening_verify_heartbeat()

    assert out["status"] == "error"
    assert "evening_verify_heartbeat_error" in audited
    assert "evening_verify_heartbeat_ok" not in audited
