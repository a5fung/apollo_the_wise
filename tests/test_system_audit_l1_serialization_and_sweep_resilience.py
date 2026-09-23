"""2026-08-10 incident: the post-EOD audit job died with
`TypeError: Object of type date is not JSON serializable` at `system_audit.py:1527` in
`_emit_l1`, called from `_check_invariants`. The breach LOST was `naked_position` — the ONE L1
that means real money may be sitting unprotected. The operator got nothing: no Telegram, no
audit row.

Two independent defects, both pinned here:

1. `audit_invariants.check_naked_position` puts raw asyncpg-Record-derived dicts (carrying
   `alert_date` — a `date` — and `filled_at` — a `datetime`) into `offending_rows`, and
   `classify_naked_positions` copies them into `real_naked` / `db_drift`. `_emit_l1` then
   `json.dumps`s all of it. Every other invariant only ever carries pre-formatted strings, so
   `naked_position` was the only one that could hit this — and it is the highest-severity one.

2. `_emit_l1` sat OUTSIDE the try/except in `_check_invariants` (only the invariant-fetch call
   `fn(conn, **kwargs)` was guarded). `naked_position` runs FIRST in `all_invariants`, so its
   emit failure propagated out of the loop and aborted the entire nightly sweep — every later
   invariant (reason coverage, error window, regime, feed health, zombie theme, stale orders,
   cooldown surge, high-no-terminal, job no-show) silently never ran.
"""
import json
from datetime import date, datetime

import pytest

import agents.market_intelligence.audit_invariants as audit_invariants
import agents.market_intelligence.briefing as briefing
from agents.market_intelligence import system_audit


def _wire_common(monkeypatch, captured: list[str]):
    """Capture every log_audit_event(detail=...) call; make Telegram sends no-ops that
    never raise; make count_today_anomalies always report a fresh (non-deduped) day."""

    async def _capture_audit(event_type, summary, detail=""):
        captured.append(detail)
    monkeypatch.setattr(system_audit, "log_audit_event", _capture_audit)

    async def _zero(*a, **k):
        return 0
    monkeypatch.setattr(system_audit, "count_today_anomalies", _zero)

    async def _send_ok(_text):
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send_ok)


def _naked_position_body(rows: list[dict]) -> dict:
    return {
        "name": "naked_position",
        "count": len(rows),
        "summary": f"{len(rows)} filled rows without stop_order_id past 60s grace",
        "offending_rows": rows,
        "offending": [f"{r['ticker']} {r['alert_date']} filled_at={r['filled_at']}" for r in rows],
        "drill_sql": "-- noop",
        "code_pointers": [],
    }


# ── Defect 1: date/datetime in the L1 body must not blow up the write ───────


@pytest.mark.asyncio
async def test_naked_position_body_with_date_and_datetime_is_written(monkeypatch):
    """Mirrors the real naked_position shape: offending_rows / real_naked / db_drift entries
    carrying alert_date (date) and filled_at (datetime). Must write the audit row, not raise."""
    captured: list[str] = []
    _wire_common(monkeypatch, captured)

    real_row = {
        "ticker": "QBTS", "alert_date": date(2026, 8, 9), "status": "filled",
        "stop_order_id": None, "filled_at": datetime(2026, 8, 9, 14, 32, 5),
    }

    async def _classify(body):
        body = dict(body)
        body["real_naked"] = [real_row]
        body["db_drift"] = []
        return body
    monkeypatch.setattr(audit_invariants, "classify_naked_positions", _classify)

    await system_audit._emit_l1("naked_position", _naked_position_body([real_row]))

    assert len(captured) == 1, "the highest-severity L1 must write an audit row, not raise"
    persisted = json.loads(captured[0])  # json.loads must succeed — proves it's valid JSON
    assert persisted["level"] == 1
    assert persisted["key"] == "naked_position"


# ── Defect 1, #140 angle: the real_naked / db_drift / classified split must SURVIVE ─────────
# ── serialization — that distinction (not just "did it write") is the whole point of the ───
# ── #140 follow-up comment in _emit_l1: a naked-position alert whose severity evaporates ────
# ── cannot be triaged afterwards. ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_real_naked_vs_db_drift_distinction_survives_serialization(monkeypatch):
    captured: list[str] = []
    _wire_common(monkeypatch, captured)

    real_row = {
        "ticker": "QBTS", "alert_date": date(2026, 8, 9), "status": "filled",
        "stop_order_id": None, "filled_at": datetime(2026, 8, 9, 14, 32, 5),
    }
    drift_row = {
        "ticker": "IBM", "alert_date": date(2026, 8, 8), "status": "filled",
        "stop_order_id": None, "filled_at": datetime(2026, 8, 8, 9, 46, 12),
    }

    async def _classify(body):
        body = dict(body)
        body["real_naked"] = [real_row]
        body["db_drift"] = [drift_row]
        return body
    monkeypatch.setattr(audit_invariants, "classify_naked_positions", _classify)

    await system_audit._emit_l1("naked_position", _naked_position_body([real_row, drift_row]))

    persisted = json.loads(captured[0])
    assert persisted["classified"] is True
    assert [r["ticker"] for r in persisted["real_naked"]] == ["QBTS"]
    assert [r["ticker"] for r in persisted["db_drift"]] == ["IBM"]
    # the date/datetime fields themselves must have round-tripped to strings, not vanished
    assert persisted["real_naked"][0]["alert_date"] == "2026-08-09"
    assert persisted["db_drift"][0]["filled_at"] == "2026-08-08 09:46:12"


# ── Defect 2: an _emit_l1 failure must not abort the rest of the L1 sweep ───────────────────


@pytest.mark.asyncio
async def test_emit_l1_failure_does_not_abort_the_invariant_sweep(monkeypatch):
    """naked_position runs first in all_invariants; a real emit failure there must not stop
    the remaining invariants from running (the actual 2026-08-10 blast radius)."""
    calls: list[str] = []

    async def _fn_naked(conn, **kwargs):
        return (False, {"name": "naked_position"})

    async def _fn_reason_coverage(conn, **kwargs):
        return (False, {"name": "reason_coverage_hole"})

    async def _fn_job_no_show(conn, **kwargs):
        return (False, {"name": "job_no_show"})

    monkeypatch.setattr(
        system_audit, "all_invariants",
        lambda **kw: [
            ("naked_position", _fn_naked, {}),
            ("reason_coverage_hole", _fn_reason_coverage, {}),
            ("job_no_show", _fn_job_no_show, {}),
        ],
    )

    async def _emit_l1_fake(name, body):
        calls.append(name)
        if name == "naked_position":
            raise TypeError("Object of type date is not JSON serializable")
    monkeypatch.setattr(system_audit, "_emit_l1", _emit_l1_fake)

    fired = await system_audit._check_invariants(
        conn=None,
        since=date(2026, 8, 9),
        since_dt=datetime(2026, 8, 9, 0, 0),
        now_et=datetime(2026, 8, 10, 16, 15),
    )

    assert calls == ["naked_position", "reason_coverage_hole", "job_no_show"], (
        "later invariants must still run after an earlier one's emit raises"
    )
    # the failed emit must not be counted as a fired breach; the two that succeeded must be
    assert fired == 2
