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


# ── #635 F5 (2026-09-30): a `*_failed` event can no longer be silent ─────────────────────
# RED-3b generalized. The nightly sweep matched `%error%` / `%rate_limited%` / `%api_failure%`
# and one hand-carved event; an audit-only `*_failed` name matched none of them and surfaced
# only in the weekly review. The sweep now also queries `NIGHTLY_SWEEP_FAILED_LIKE` and counts
# every `*_failed` event that is not on `NIGHTLY_SWEEP_FAILED_ALLOWLIST` (events that already
# Telegram at emit). The population tests DERIVE the emitters from the source - a hand-listed
# set of names is exactly how RED-3b hid for a month.
#
# MUTATION CHECKS (run by hand 2026-09-30, recorded here, not re-run by CI):
#   * delete the `failed_rows = await get_audit_log(...)` query in scheduler.py
#       -> test_a_failed_event_with_no_page_of_its_own_reaches_the_digest and
#          test_every_unpaged_failed_emitter_reaches_the_digest FAIL
#   * delete the `elif "_failed" in evt ...` branch -> the same two FAIL
#   * empty NIGHTLY_SWEEP_FAILED_ALLOWLIST -> test_an_already_loud_failed_event_is_not_repeated FAILS
#   * delete the Telegram call beside an allowlisted emit -> test_allowlisted_events_really_page_at_every_emit_site FAILS
#   * delete the `failed_rows` merge in agent._handle_audit_log -> test_show_errors_lists_failed_events_too FAILS

import agents.market_intelligence.scheduler as sched  # noqa: E402
from tests._audit_emitters import (  # noqa: E402
    calls_a_telegram_sender, like_to_regex, static_audit_emitters,
)


def _fake_by_like(rows_by_like):
    """get_audit_log double that answers by the LIKE pattern the sweep asked for."""
    calls = []

    async def fake(limit=40, event_type=None, since_hours=2, event_type_like=None):
        calls.append(event_type_like or event_type)
        return list(rows_by_like.get(event_type_like, []))

    return fake, calls


async def _run_sweep(monkeypatch, rows_by_like):
    fake, calls = _fake_by_like(rows_by_like)
    sent = []

    async def fake_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(sched, "get_audit_log", fake)
    monkeypatch.setattr(sched, "send_telegram_message", fake_send)
    await sched._check_nightly_silent_errors()
    return sent, calls


def _failed_row(i, event_type, summary="x"):
    return {"id": i, "event_type": event_type, "summary": summary}


@pytest.mark.asyncio
async def test_a_failed_event_with_no_page_of_its_own_reaches_the_digest(monkeypatch):
    """`order_status_reconcile_failed` is the headline F5 case (advisor-ruled audit-only) and
    `coverage_drift_check_failed` a crashed check. Neither Telegrams. Both must reach the
    nightly digest - as NAMES and COUNTS, never the row summary (tickers / order ids / `_`)."""
    rows = [_failed_row(i, "order_status_reconcile_failed", f"ZZ_TICKER_{i} order a_b_c fail")
            for i in range(1, 4)]
    rows.append(_failed_row(9, "coverage_drift_check_failed", "coverage-drift check crashed for live"))
    sent, calls = await _run_sweep(monkeypatch, {sched.NIGHTLY_SWEEP_FAILED_LIKE: rows})

    assert sched.NIGHTLY_SWEEP_FAILED_LIKE in calls          # the sweep really asked for them
    assert len(sent) == 1
    assert "`order_status_reconcile_failed` ×3" in sent[0]
    assert "`coverage_drift_check_failed` ×1" in sent[0]
    assert "ZZ_TICKER" not in sent[0] and "a_b_c" not in sent[0]   # no summary echo (Markdown 400 hazard)


@pytest.mark.asyncio
async def test_an_already_loud_failed_event_is_not_repeated(monkeypatch):
    """`unfilled_cancel_failed` sends its own "cancel FAILED ... investigate broker side"
    Telegram; a nightly line would only repeat a page he already got."""
    rows = [_failed_row(1, "unfilled_cancel_failed"), _failed_row(2, "stop_update_failed")]
    sent, _ = await _run_sweep(monkeypatch, {sched.NIGHTLY_SWEEP_FAILED_LIKE: rows})
    assert sent == []


@pytest.mark.asyncio
async def test_a_noisy_night_collapses_to_one_line_per_event_and_caps_the_list(monkeypatch):
    rows = [_failed_row(i, "vol_landmark_eod_failed") for i in range(1, 121)]       # one per ticker
    rows += [_failed_row(1000 + i, f"shadow_{i}_failed") for i in range(8)]
    sent, _ = await _run_sweep(monkeypatch, {sched.NIGHTLY_SWEEP_FAILED_LIKE: rows})
    assert len(sent) == 1
    body = sent[0]
    assert "`vol_landmark_eod_failed` ×120" in body
    assert body.count("🟠") == 6                        # capped
    assert "…3 more failed event type(s)" in body      # 9 distinct names, 6 shown


@pytest.mark.asyncio
async def test_an_event_named_both_error_and_failed_is_counted_once(monkeypatch):
    row = _failed_row(7, "thing_failed_error", "boom")
    sent, _ = await _run_sweep(monkeypatch, {"%error%": [row],
                                             sched.NIGHTLY_SWEEP_FAILED_LIKE: [row]})
    assert len(sent) == 1
    assert "1 engine event(s)" in sent[0]
    assert "🟠" not in sent[0]                          # it is an `other` row, not a failed-only one



def test_allowlisted_events_really_page_at_every_emit_site():
    """The allowlist means "already loud at emit". Derive every emit site of every allowlisted
    event and require a Telegram sender in the same function (or the function that encloses
    it). If someone later deletes the page beside an audit row, this fails and the event has to
    come OFF the allowlist - it cannot quietly stay on it."""
    emitters = static_audit_emitters()
    problems = []
    for ev in sorted(sched.NIGHTLY_SWEEP_FAILED_ALLOWLIST):
        sites = emitters.get(ev)
        if not sites:
            problems.append(f"{ev}: no static emit site found (stale or mistyped allowlist entry)")
            continue
        for rel, line, chain in sites:
            if not any(calls_a_telegram_sender(fn) for fn in chain):
                problems.append(f"{ev} @ {rel}:{line}: no Telegram sender in the enclosing function")
    assert not problems, "\n".join(problems)


def test_the_population_is_derived_not_listed():
    """Name the members - a count floor cannot catch a scanner that stopped reading."""
    emitters = static_audit_emitters()
    failed = {e for e in emitters if "_failed" in e and "error" not in e}
    for known in ("order_status_reconcile_failed", "coverage_drift_check_failed",
                  "telegram_send_failed", "partial_exit_sell_failed", "unfilled_cancel_failed",
                  "ep_scan_failed"):
        assert known in failed, f"{known} is no longer derived - the scanner stopped seeing it"
    silent = failed - sched.NIGHTLY_SWEEP_FAILED_ALLOWLIST
    assert {"order_status_reconcile_failed", "coverage_drift_check_failed"} <= silent
    assert not ({"unfilled_cancel_failed", "ep_scan_failed"} & silent)


@pytest.mark.asyncio
async def test_every_unpaged_failed_emitter_reaches_the_digest(monkeypatch):
    """THE T7 RULE, end to end. For every `*_failed` event the source can emit (derived, not
    listed), one row of that name through the REAL sweep must put it in the digest - unless it
    is allowlisted as already-loud, in which case it must NOT be repeated."""
    like = like_to_regex(sched.NIGHTLY_SWEEP_FAILED_LIKE)
    emitters = static_audit_emitters()
    names = sorted(e for e in emitters if "error" not in e and "_failed" in e)
    assert names, "no *_failed emitters derived - the scanner is not reading"
    wrong = []
    for ev in names:
        assert like.match(ev), f"{ev} would not be fetched by the sweep's own pattern"
        sent, _ = await _run_sweep(
            monkeypatch, {sched.NIGHTLY_SWEEP_FAILED_LIKE: [_failed_row(1, ev)]})
        if ev in sched.NIGHTLY_SWEEP_FAILED_ALLOWLIST:
            if sent:
                wrong.append(f"{ev}: allowlisted but the digest repeated it")
        elif not sent or f"`{ev}`" not in sent[0]:
            wrong.append(f"{ev}: silent - never reached the nightly digest")
    assert not wrong, "\n".join(wrong)


@pytest.mark.asyncio
async def test_show_errors_lists_failed_events_too(monkeypatch):
    """The digest tells him to type `show errors`; that command never listed a `*_failed` row."""
    from unittest.mock import MagicMock
    from agents.market_intelligence import agent as agent_mod
    asked = []

    async def fake_get(limit=30, event_type=None, since_hours=48, event_type_like=None):
        asked.append(event_type_like or event_type)
        if event_type_like == sched.NIGHTLY_SWEEP_FAILED_LIKE:
            return [{"id": 41, "created_at": datetime(2026, 9, 30, 18, 0),
                     "event_type": "order_status_reconcile_failed", "summary": "live: 2 failed"}]
        return []

    monkeypatch.setattr(agent_mod, "get_audit_log", fake_get)
    agent = agent_mod.MarketIntelligenceAgent.__new__(agent_mod.MarketIntelligenceAgent)
    agent.agent_name = "market_intelligence"
    req = MagicMock()
    req.request_id = "t-635"
    req.task = "show errors 24h"

    resp = await agent._handle_audit_log(req)

    assert sched.NIGHTLY_SWEEP_FAILED_LIKE in asked
    assert resp.success is True
    assert "live: 2 failed" in resp.result
