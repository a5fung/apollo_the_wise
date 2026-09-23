"""PLAN #216 — nightly regression guard for double/multi-encoded JSONB columns
(`run_jsonb_encoding_check` in health_checks.py).

WHY THIS EXISTS. `db.py`'s jsonb codec auto-json.dumps()es every jsonb bind param; several
write-path call sites ALSO json.dumps()ed before binding `$N::jsonb`, double-encoding the
value — the column holds a JSON *string* containing JSON text instead of a real object/array
(measured on prod 2026-08-17, ~4,300 rows across 9 tables; see PLAN.md #216).
`scripts/_216_jsonb_repair.py` is the one-time cleanup; this file pins the GUARD that keeps
the bug from silently coming back: it counts jsonb_typeof(col)='string' rows per column,
records tonight's count as tomorrow's baseline (mirrors run_db_growth_check), and speaks
only when a column's count GROWS beyond what was last recorded.

Same bar as test_health_checks_null_sweep.py: prove, mock-free, the PURE decision first
(_evaluate_jsonb_growth), then drive the real SQL-shaped path through a fake conn.
"""
from __future__ import annotations

import json
import re

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence import db as _db
from agents.market_intelligence import briefing as _brief
from agents.market_intelligence.health_checks import (
    _evaluate_jsonb_growth,
    run_jsonb_encoding_check,
)


# ── Pure decision: _evaluate_jsonb_growth (no mocking) ─────────────────────────────────


def test_no_baseline_yet_stays_silent():
    """First run ever: nothing to compare against — measure, don't judge (same first-run
    behavior as run_db_growth_check / run_null_rate_sweep)."""
    assert _evaluate_jsonb_growth({"mi_signal_outcomes.detail": 500}, None) == []


def test_growth_beyond_baseline_is_flagged():
    current = {"mi_signal_outcomes.detail": 12}
    baseline = {"mi_signal_outcomes.detail": 3}
    flags = _evaluate_jsonb_growth(current, baseline)
    assert len(flags) == 1
    assert flags[0] == {"key": "mi_signal_outcomes.detail", "before": 3, "after": 12, "delta": 9}


def test_flat_or_shrinking_count_is_not_flagged():
    # Equal to baseline -> quiet.
    assert _evaluate_jsonb_growth({"t.c": 5}, {"t.c": 5}) == []
    # Shrunk (e.g. after an operator repair run) -> quiet, definitely not an alarm.
    assert _evaluate_jsonb_growth({"t.c": 0}, {"t.c": 5}) == []


def test_a_brand_new_column_not_in_baseline_is_judged_against_zero():
    # A column discovered for the first time tonight (baseline predates it) is compared
    # against an implicit 0 — any string-typed rows on it register as growth. This is the
    # expected cold-start shape (see the header comment), not a bug.
    flags = _evaluate_jsonb_growth({"new_table.col": 4}, {"other.col": 0})
    assert flags == [{"key": "new_table.col", "before": 0, "after": 4, "delta": 4}]


def test_only_the_grown_columns_are_flagged_not_the_whole_batch():
    current = {"a.x": 10, "b.y": 3}
    baseline = {"a.x": 10, "b.y": 1}
    flags = _evaluate_jsonb_growth(current, baseline)
    assert [f["key"] for f in flags] == ["b.y"]


# ── Fake conn — routes by SQL substring, mirrors test_grading_health_543's _mock_conn ──


class _FakeConn:
    def __init__(self, jsonb_columns, counts, baseline_detail=None, recent_alerted=()):
        self.jsonb_columns = jsonb_columns          # list[(table, column)]
        self.counts = counts                        # {"table.column": n}
        self.baseline_detail = baseline_detail       # json str, or None (no prior run)
        self.recent_alerted = list(recent_alerted)   # already-dedup'd column keys

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            return [{"table_name": t, "column_name": c} for t, c in self.jsonb_columns]
        if "jsonb_encoding_alert" in sql:
            return [{"k": k} for k in self.recent_alerted]
        raise AssertionError(f"unrouted fetch: {sql}")

    async def fetchval(self, sql, *args):
        m = re.search(r'FROM "([^"]+)" WHERE jsonb_typeof\("([^"]+)"\)', sql)
        assert m, f"unrouted fetchval: {sql}"
        key = f"{m.group(1)}.{m.group(2)}"
        return self.counts.get(key, 0)

    async def fetchrow(self, sql, *args):
        if "jsonb_encoding_check" in sql:
            return None if self.baseline_detail is None else {"detail": self.baseline_detail}
        raise AssertionError(f"unrouted fetchrow: {sql}")


def _patch_audit_and_telegram(monkeypatch):
    audit_calls = []

    async def _audit(event_type, summary, detail=""):
        audit_calls.append({"event_type": event_type, "summary": summary, "detail": detail})

    sent = []

    async def _send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(_db, "log_audit_event", _audit)
    monkeypatch.setattr(_brief, "send_telegram_message", _send)
    return audit_calls, sent


# ── run_jsonb_encoding_check — integration over the fake conn ──────────────────────────


@pytest.mark.asyncio
async def test_first_run_ever_records_baseline_and_stays_silent(monkeypatch):
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 2440},
        baseline_detail=None,  # no prior run
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["counts"] == {"mi_signal_outcomes.detail": 2440}
    assert out["flags"] == []
    assert out["spoke"] is False
    assert sent == []
    # The measurement row must still be written — it becomes tomorrow's baseline.
    assert any(c["event_type"] == "jsonb_encoding_check" for c in audit_calls)
    written = next(c for c in audit_calls if c["event_type"] == "jsonb_encoding_check")
    assert json.loads(written["detail"])["counts"] == {"mi_signal_outcomes.detail": 2440}


@pytest.mark.asyncio
async def test_growth_since_last_run_alerts(monkeypatch):
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 50},
        baseline_detail=json.dumps({"counts": {"mi_signal_outcomes.detail": 3}}),
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["flags"] == [{"key": "mi_signal_outcomes.detail", "before": 3, "after": 50, "delta": 47}]
    assert out["spoke"] is True
    assert len(sent) == 1
    assert "mi_signal_outcomes.detail" in sent[0]
    assert "50" in sent[0] and "3" in sent[0]
    assert any(c["event_type"] == "jsonb_encoding_alert" for c in audit_calls)


@pytest.mark.asyncio
async def test_flat_count_stays_quiet(monkeypatch):
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 3},
        baseline_detail=json.dumps({"counts": {"mi_signal_outcomes.detail": 3}}),
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["flags"] == []
    assert out["spoke"] is False
    assert sent == []


@pytest.mark.asyncio
async def test_shrinking_count_after_a_repair_run_is_not_an_alarm(monkeypatch):
    """The operator-run repair script drives the count DOWN — that must never look like a
    problem, since a shrink is the fix working, not a regression."""
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 0},
        baseline_detail=json.dumps({"counts": {"mi_signal_outcomes.detail": 2440}}),
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["flags"] == []
    assert sent == []


@pytest.mark.asyncio
async def test_already_announced_column_within_dedupe_window_stays_quiet(monkeypatch):
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 60},
        baseline_detail=json.dumps({"counts": {"mi_signal_outcomes.detail": 3}}),
        recent_alerted=["mi_signal_outcomes.detail"],  # already alerted inside the window
    )
    out = await run_jsonb_encoding_check(conn=conn)
    # Growth is still detected/returned (the caller-visible flag)...
    assert out["flags"] != []
    # ...but Telegram does not re-fire for an already-announced column.
    assert sent == []
    assert out["spoke"] is False


@pytest.mark.asyncio
async def test_a_fresh_column_is_not_masked_by_a_different_already_announced_one(monkeypatch):
    """Per-column dedupe: one already-announced column must not silence a DIFFERENT column
    regressing on the same night (the exact reason detector-liveness dedupes per-table)."""
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail"), ("mi_weekly_watchlists", "sources")],
        counts={"mi_signal_outcomes.detail": 60, "mi_weekly_watchlists.sources": 400},
        baseline_detail=json.dumps({"counts": {
            "mi_signal_outcomes.detail": 3, "mi_weekly_watchlists.sources": 0,
        }}),
        recent_alerted=["mi_signal_outcomes.detail"],  # only ONE of the two already announced
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["spoke"] is True
    assert "mi_weekly_watchlists.sources" in sent[0]
    assert "mi_signal_outcomes.detail" not in sent[0]


@pytest.mark.asyncio
async def test_one_bad_column_does_not_blind_the_rest(monkeypatch):
    """A single column's COUNT query failing must not kill the whole sweep."""
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)

    class _PartiallyBrokenConn(_FakeConn):
        async def fetchval(self, sql, *args):
            if "mi_broken_table" in sql:
                raise RuntimeError("relation does not exist")
            return await super().fetchval(sql, *args)

    conn = _PartiallyBrokenConn(
        jsonb_columns=[("mi_broken_table", "col"), ("mi_signal_outcomes", "detail")],
        counts={"mi_signal_outcomes.detail": 3},
        baseline_detail=None,
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert "mi_signal_outcomes.detail" in out["counts"]
    assert "mi_broken_table.col" not in out["counts"]
    assert len(out["errors"]) == 1
    assert out["errors"][0]["column"] == "mi_broken_table.col"


@pytest.mark.asyncio
async def test_it_discovers_columns_rather_than_hardcoding_the_table_list(monkeypatch):
    """PLAN #216 explicitly warns the 9-table list is today's measurement, not a spec —
    discovery must go through information_schema, covering a table never named in the diagnosis."""
    audit_calls, sent = _patch_audit_and_telegram(monkeypatch)
    conn = _FakeConn(
        jsonb_columns=[("mi_never_mentioned_anywhere", "payload")],
        counts={"mi_never_mentioned_anywhere.payload": 7},
        baseline_detail=None,
    )
    out = await run_jsonb_encoding_check(conn=conn)
    assert out["counts"] == {"mi_never_mentioned_anywhere.payload": 7}


def test_discovery_excludes_views_not_just_base_tables():
    """A VIEW with a jsonb column must not be counted here — `information_schema.columns`
    returns view columns too, and a COUNT(*) over jsonb_typeof(view_col) would run the
    view's whole underlying query every night for nothing."""
    import inspect
    src = inspect.getsource(health_checks._jsonb_columns)
    assert "BASE TABLE" in src


def test_it_is_wired_into_the_nightly_audit_and_alerts():
    """A check nobody runs is a function."""
    sched = open("agents/market_intelligence/scheduler.py").read()
    assert "run_jsonb_encoding_check" in sched
    i = sched.index("run_jsonb_encoding_check")
    block = sched[i:i + 1500]
    assert "notify_job_failure" in block, "own try/except like every sibling check"
