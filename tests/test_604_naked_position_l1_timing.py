"""#604 — the naked_position L1 fired at exactly 16:15:00 on every historical
occurrence (2026-08-28, 2026-07-27, 2026-06-23) because that is the ONE time
the old post_eod_audit sweep checked it, and 16:15 sits right after the 16:00
DAY-order stop expiry with no replacement stop placed yet — a known,
after-hours (or, on the two dates before the 16:20 refresh job existed,
overnight-until-next-morning), harmless window where a stop cannot execute
anyway. (End-to-end verified only for 08-28 so far; 07-27/06-23 are pending
the operator running scripts/probes/_604_naked_l1_historical.sql — see that
file's header for why their lifecycle differs from 08-28's.)

THE FIX is a detection-TIMING change only (no stop-placement or refresh-job
code touched): naked_position is pulled out of the 16:15 sweep and checked
instead at 15:55 ET (before the 16:00 expiry — catches a genuinely bare
position DURING market hours) and 16:27 ET (after the 16:20 refresh has had
time to land — catches a refresh that genuinely failed). Same predicate
(`check_naked_position`), same broker-classification + Telegram path
(`_emit_l1` / `classify_naked_positions`) as before; only WHEN it's asked
changed.

This file proves:
  1. the 16:15 sweep (run_post_eod_audit) no longer asks naked_position at all
  2. the two new jobs are scheduled OUTSIDE the 16:00-16:20 gap (one before,
     one after, with a buffer past 16:20)
  3. a genuinely bare position STILL ALARMS when the standalone check runs —
     covers both "bare during market hours" (the 15:55 slot) and "still bare
     after the refresh ran and failed" (the 16:27 slot); the check itself
     doesn't know or care which slot called it, which is exactly the point —
     nothing about WHAT counts as naked changed
  4. a covered position stays quiet (no false alarm manufactured by the fix)
  5. the two new jobs are classified INTELLIGENCE, not EXECUTION-owned (they
     are the same DB-read + on-breach broker-read shape run_post_eod_audit
     always was) — this is what decides the deploy scope for #604
"""
import re
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import system_audit
from agents.market_intelligence.audit_invariants import INV_NAKED_POSITION
from tests.conftest import make_mock_pool

_SCHED_SRC = (Path(__file__).resolve().parents[1]
              / "agents/market_intelligence/scheduler.py").read_text()


def _wire_emit_l1(monkeypatch, captured_names: list[str]):
    """Capture which invariant names actually reach _emit_l1, without doing
    any real classification/Telegram/DB work — isolates 'was naked_position
    even ASKED ABOUT' from the (unmodified, already-tested-elsewhere) emit
    machinery."""
    async def _fake_emit_l1(name, body):
        captured_names.append(name)
    monkeypatch.setattr(system_audit, "_emit_l1", _fake_emit_l1)


# ── 1. the 16:15 sweep no longer asks naked_position ─────────────────────────


@pytest.mark.asyncio
async def test_post_eod_audit_never_asks_naked_position(monkeypatch):
    fired: list[str] = []
    _wire_emit_l1(monkeypatch, fired)

    async def _fake_naked(conn, **kwargs):
        # If this is ever called, the sweep is asking naked_position — the
        # exact defect. Would fire if asked (proves a silent skip isn't
        # hiding a real breach, it's just never being polled here).
        return (False, {"name": "naked_position"})

    async def _fake_other(conn, **kwargs):
        return (False, {"name": "some_other_invariant"})

    monkeypatch.setattr(
        system_audit, "all_invariants",
        lambda **kw: [
            (INV_NAKED_POSITION, _fake_naked, {}),
            ("some_other_invariant", _fake_other, {}),
        ],
    )
    monkeypatch.setattr(system_audit, "_scan_metrics", AsyncMock(return_value=(0, 0, 0)))
    monkeypatch.setattr(system_audit, "_current_regime", AsyncMock(return_value=None))
    pool, conn = make_mock_pool()
    monkeypatch.setattr(system_audit, "get_pool", AsyncMock(return_value=pool))

    result = await system_audit.run_post_eod_audit()

    assert fired == ["some_other_invariant"], (
        f"naked_position must be skipped in the 16:15 sweep — got {fired}"
    )
    assert result["l1"] == 1, "the OTHER invariant must still fire normally"


# ── 2. the two new jobs sit outside the 16:00-16:20 gap ─────────────────────


def _cron_kwargs_near(job_id_marker: str) -> dict:
    """Grab the CronTrigger(...) call immediately preceding an add_job whose
    id= matches job_id_marker, and parse hour=/minute= out of it. Mirrors the
    AST-light source-inspection style test_stop_always_during_market_hours.py
    already uses for this same scheduler.py file."""
    idx = _SCHED_SRC.index(f'id="{job_id_marker}"')
    window = _SCHED_SRC[max(0, idx - 400):idx]
    m = re.search(r"CronTrigger\(([^)]*)\)[^)]*$", window, re.S)
    assert m, f"couldn't find a CronTrigger(...) preceding id=\"{job_id_marker}\""
    block = m.group(1)
    hour = int(re.search(r"hour=(\d+)", block).group(1))
    minute = int(re.search(r"minute=(\d+)", block).group(1))
    return {"hour": hour, "minute": minute}


def test_pre_close_check_runs_before_the_1600_expiry():
    t = _cron_kwargs_near("naked_position_pre_close_check")
    assert (t["hour"], t["minute"]) < (16, 0), (
        f"pre-close check must run BEFORE the 16:00 day-order expiry, got {t}"
    )


def test_post_refresh_check_runs_after_the_1620_refresh():
    t = _cron_kwargs_near("naked_position_post_refresh_check")
    assert (t["hour"], t["minute"]) > (16, 20), (
        f"post-refresh check must run AFTER the 16:20 post_close_stop_refresh, got {t}"
    )


def test_post_eod_audit_slot_is_unchanged_still_1615():
    """The 16:15 job itself didn't move — only what it asks changed. Every
    OTHER invariant it carries (reason_coverage_hole, stale_order_placed,
    etc.) still wants to run right after 16:05 cleanup / 16:10 recap."""
    t = _cron_kwargs_near("post_eod_audit")
    assert (t["hour"], t["minute"]) == (16, 15)


def test_neither_new_job_lands_inside_the_gap():
    for job_id in ("naked_position_pre_close_check", "naked_position_post_refresh_check"):
        t = _cron_kwargs_near(job_id)
        assert not ((16, 0) <= (t["hour"], t["minute"]) <= (16, 20)), (
            f"{job_id} at {t} falls back inside the expiry->refresh gap #604 exists to avoid"
        )


# ── 3. a genuine bare position STILL ALARMS through the standalone check ────
# The check itself carries no time-of-day logic (see run_naked_position_check's
# body: it's the unmodified check_naked_position predicate + the unmodified
# _emit_l1/classify path) — the SAME call proves both real scenarios the DoD
# calls out, because timing is owned entirely by WHICH job calls it, not by
# anything inside it:
#   - called from the 15:55 job -> a hit here is bare DURING MARKET HOURS
#   - called from the 16:27 job -> a hit here is bare AFTER THE REFRESH RAN,
#     i.e. the refresh genuinely failed


@pytest.mark.asyncio
async def test_naked_position_check_alarms_on_a_real_bare_position(monkeypatch):
    fired: list[tuple] = []

    async def _fake_emit_l1(name, body):
        fired.append((name, body["count"]))
    monkeypatch.setattr(system_audit, "_emit_l1", _fake_emit_l1)

    pool, conn = make_mock_pool()
    stale_filled_at = datetime.now() - timedelta(hours=6)
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "IBM", "alert_date": stale_filled_at.date(), "status": "filled",
         "stop_order_id": None, "filled_at": stale_filled_at},
    ])
    monkeypatch.setattr(system_audit, "get_pool", AsyncMock(return_value=pool))

    result = await system_audit.run_naked_position_check()

    assert result["l1"] == 1, "a real bare row must still fire the L1, unconditionally of time"
    assert fired == [(INV_NAKED_POSITION, 1)]


@pytest.mark.asyncio
async def test_naked_position_check_quiet_when_covered(monkeypatch):
    """No manufactured false-quiet: a properly-covered book must NOT alarm —
    the fix must not have become a blanket suppression in either direction."""
    fired: list[tuple] = []

    async def _fake_emit_l1(name, body):
        fired.append(name)
    monkeypatch.setattr(system_audit, "_emit_l1", _fake_emit_l1)

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])  # every filled row has a stop
    monkeypatch.setattr(system_audit, "get_pool", AsyncMock(return_value=pool))

    result = await system_audit.run_naked_position_check()

    assert result["l1"] == 0
    assert fired == []


@pytest.mark.asyncio
async def test_naked_position_check_end_to_end_reaches_telegram_and_audit_row(monkeypatch):
    """Full path (not just the _emit_l1 boundary): a real bare row drives
    classify_naked_positions + the audit-log write + the Telegram send, the
    same as it always did — #604 changed WHEN this runs, not WHAT it does."""
    import agents.market_intelligence.audit_invariants as audit_invariants
    import agents.market_intelligence.briefing as briefing

    audit_calls: list[str] = []

    async def _capture_audit(event_type, summary, detail=""):
        audit_calls.append(detail)
    monkeypatch.setattr(system_audit, "log_audit_event", _capture_audit)

    async def _zero(*a, **k):
        return 0
    monkeypatch.setattr(system_audit, "count_today_anomalies", _zero)

    sent: list[str] = []

    async def _send(text):
        sent.append(text)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    stale_filled_at = datetime.now() - timedelta(hours=6)
    real_row = {"ticker": "SOLS", "alert_date": stale_filled_at.date(), "status": "filled",
                "stop_order_id": None, "filled_at": stale_filled_at}

    async def _classify(body):
        body = dict(body)
        body["real_naked"] = [real_row]
        body["db_drift"] = []
        return body
    monkeypatch.setattr(audit_invariants, "classify_naked_positions", _classify)

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[real_row])
    monkeypatch.setattr(system_audit, "get_pool", AsyncMock(return_value=pool))

    result = await system_audit.run_naked_position_check()

    assert result["l1"] == 1
    assert len(audit_calls) == 1, "the breach must still write an mi_audit_log row"
    assert len(sent) == 1 and "NAKED POSITION" in sent[0], "and still Telegram the operator"


# ── 4. the two new jobs are INTELLIGENCE-owned, like post_eod_audit always was


def test_new_jobs_are_intelligence_not_execution_owned():
    from agents.market_intelligence import scheduler as sched
    for job_id in ("naked_position_pre_close_check", "naked_position_post_refresh_check"):
        assert job_id in sched.INTELLIGENCE_OWNED_JOB_IDS, (
            f"{job_id} must be classified INTELLIGENCE — same DB-read + "
            f"on-breach-only broker-read shape as post_eod_audit"
        )
        assert job_id not in sched.EXECUTION_OWNED_JOB_IDS
