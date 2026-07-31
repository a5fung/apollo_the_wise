"""#509 model auto-resolution — agents/market_intelligence/db.py's traceability
queries: get_latest_model_resolution / insert_model_resolution /
get_model_resolution_asof / get_judge_grade_decisions_for_date.

The `mi_model_resolution` table doesn't exist in prod yet (this feature is
unshipped) so these are mock-pool unit tests, not a live-DB integration test;
the date-cast SQL SHAPE itself was verified read-only against prod's
mi_audit_log (a real timestamptz column) — see the docstrings in db.py.
"""
import asyncio
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import make_mock_pool

from agents.market_intelligence import db


def _run(coro):
    return asyncio.run(coro)


def _mock_pool(monkeypatch):
    pool, conn = make_mock_pool()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    return conn


# ─── get_latest_model_resolution ─────────────────────────────────────────────

def test_get_latest_model_resolution_returns_row(monkeypatch):
    conn = _mock_pool(monkeypatch)
    row = {"role": "JUDGE_MODEL", "model": "claude-opus-5", "source": "cache",
           "prev_model": "claude-opus-4-8", "resolved_at": datetime.now(timezone.utc),
           "effective_date": date(2026, 7, 31)}
    conn.fetchrow = AsyncMock(return_value=row)
    result = _run(db.get_latest_model_resolution("JUDGE_MODEL"))
    assert result == row
    conn.fetchrow.assert_awaited_once()
    assert conn.fetchrow.await_args.args[1] == "JUDGE_MODEL"


def test_get_latest_model_resolution_none_when_absent(monkeypatch):
    conn = _mock_pool(monkeypatch)
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(db.get_latest_model_resolution("JUDGE_MODEL")) is None


# ─── insert_model_resolution ─────────────────────────────────────────────────

def test_insert_model_resolution_passes_correct_args(monkeypatch):
    conn = _mock_pool(monkeypatch)
    conn.execute = AsyncMock()
    _run(db.insert_model_resolution("JUDGE_MODEL", "claude-opus-5", "cache",
                                     "claude-opus-4-8", detail="note"))
    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args
    assert args[1:] == ("JUDGE_MODEL", "claude-opus-5", "cache", "claude-opus-4-8", "note")


def test_insert_model_resolution_handles_none_prev_and_truncates_detail(monkeypatch):
    conn = _mock_pool(monkeypatch)
    conn.execute = AsyncMock()
    long_detail = "x" * 3000
    _run(db.insert_model_resolution("JUDGE_MODEL", "claude-opus-5", "pin", None, detail=long_detail))
    args = conn.execute.await_args.args
    assert args[4] is None  # prev_model
    assert len(args[5]) == 2000


# ─── get_model_resolution_asof ───────────────────────────────────────────────

def test_get_model_resolution_asof_passes_role_and_date(monkeypatch):
    conn = _mock_pool(monkeypatch)
    row = {"role": "JUDGE_MODEL", "model": "claude-opus-4-8", "source": "pin",
           "resolved_at": datetime.now(timezone.utc), "effective_date": date(2026, 8, 14)}
    conn.fetchrow = AsyncMock(return_value=row)
    result = _run(db.get_model_resolution_asof("JUDGE_MODEL", date(2026, 8, 14)))
    assert result == row
    args = conn.fetchrow.await_args.args
    assert args[1] == "JUDGE_MODEL"
    assert args[2] == date(2026, 8, 14)


def test_get_model_resolution_asof_none_when_no_history(monkeypatch):
    conn = _mock_pool(monkeypatch)
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(db.get_model_resolution_asof("JUDGE_MODEL", date(2026, 8, 14))) is None


# ─── get_judge_grade_decisions_for_date ──────────────────────────────────────

def test_get_judge_grade_decisions_parses_detail_json(monkeypatch):
    conn = _mock_pool(monkeypatch)
    rows = [
        {"detail": json.dumps({"judge_model": "claude-opus-4-8", "judge_tier": "HIGH"})},
        {"detail": json.dumps({"judge_model": "claude-opus-4-8", "judge_tier": "MODERATE"})},
    ]
    conn.fetch = AsyncMock(return_value=rows)
    out = _run(db.get_judge_grade_decisions_for_date(date(2026, 7, 31)))
    assert len(out) == 2
    assert out[0]["judge_tier"] == "HIGH"
    args = conn.fetch.await_args.args
    assert args[1] == date(2026, 7, 31)


def test_get_judge_grade_decisions_skips_malformed_rows(monkeypatch):
    # Mirrors system_audit._judge_decision_rows_today's established safety —
    # mi_audit_log.detail is TEXT and can hold malformed rows; a crash here
    # would repeat the 7/11 corpus-mine incident on a second call site.
    conn = _mock_pool(monkeypatch)
    rows = [
        {"detail": json.dumps({"judge_model": "claude-opus-4-8", "judge_tier": "HIGH"})},
        {"detail": "{not valid json"},
        {"detail": "null"},  # valid JSON, not a dict
        {"detail": None},
    ]
    conn.fetch = AsyncMock(return_value=rows)
    out = _run(db.get_judge_grade_decisions_for_date(date(2026, 7, 31)))
    assert len(out) == 1
    assert out[0]["judge_tier"] == "HIGH"


def test_get_judge_grade_decisions_empty_day(monkeypatch):
    conn = _mock_pool(monkeypatch)
    conn.fetch = AsyncMock(return_value=[])
    assert _run(db.get_judge_grade_decisions_for_date(date(2026, 7, 31))) == []
