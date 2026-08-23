"""#533 Change 6 — the catalyst-tier FLIP MONITOR (2026-08-22, operator-signed).

The flip is a negative test (operator: "flip now and revert when wrong ... and have a
condition to test if we're right or not and monitor"), so the monitor IS the safety story:
these tests pin the three revert triggers, the acting-side resolution (never inferred from
dates), the once-per-member P1 dedupe, the stand-down when the revert flag is off, and that
the alert message names the trigger, the numbers, and the EXACT revert command.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import health_checks as hc
from agents.market_intelligence import db as _db
from agents.market_intelligence import briefing as _brief

_FRI = date(2026, 8, 21)  # a Friday


def _weekday(d: date) -> bool:
    return d.weekday() < 5


# ── pure evaluators ──────────────────────────────────────────────────────────────────


def test_high_drop_fires_only_when_fall_exceeds_50_pct():
    assert hc._evaluate_lattice_high_drop(0.9, 2.0) is not None      # 55% fall -> fire
    assert hc._evaluate_lattice_high_drop(1.0, 2.0) is None          # exactly 50% -> no
    assert hc._evaluate_lattice_high_drop(1.5, 2.0) is None          # 25% fall -> no
    f = hc._evaluate_lattice_high_drop(0.5, 2.0)
    assert f["drop_pct"] == 75.0 and f["recent_avg"] == 0.5 and f["prior_avg"] == 2.0


def test_high_drop_never_fires_from_a_zero_baseline():
    """Nothing to fall FROM — a cold lane is trigger (c)'s job, not (b)'s."""
    assert hc._evaluate_lattice_high_drop(0.0, 0.0) is None


def test_acting_tier_is_decided_by_live_side_never_by_date():
    assert hc._lattice_acting_tier("lattice", "strong", "routine") == "routine"
    assert hc._lattice_acting_tier("llm", "routine", "strong") == "routine"
    assert hc._lattice_acting_tier(None, "routine", "strong") == "routine"  # pre-column rows = llm era


def test_fixture_loader_returns_members_and_skips_excluded():
    members = hc._load_must_not_miss_members()
    assert members is not None
    assert ("MRNA", "2026-08-19") in members
    assert all(t != "TDIC" for t, _ in members)  # excluded=True member stays out


def test_fixture_loader_returns_None_not_empty_on_import_failure(monkeypatch):
    """None (never []) so the caller can tell 'P1 trigger DARK' from 'no members'."""
    import types
    monkeypatch.setitem(sys.modules, "tests.fixtures.must_not_miss_eps",
                        types.ModuleType("tests.fixtures.must_not_miss_eps"))
    assert hc._load_must_not_miss_members() is None


# ── the runner ───────────────────────────────────────────────────────────────────────


class _FakeConn:
    """Routes by SQL substring; fetchrow (audit dedupe) returns None unless set."""

    def __init__(self, shadow_rows=None, alert_rows=None, dedupe_hit=False):
        self.shadow_rows = shadow_rows or []
        self.alert_rows = alert_rows or []
        self.dedupe_hit = dedupe_hit

    async def fetch(self, sql, *args):
        if "mi_catalyst_tier_shadow" in sql:
            return self.shadow_rows
        if "mi_ep_alerts" in sql:
            return self.alert_rows
        return []

    async def fetchrow(self, sql, *args):
        return {"?": 1} if self.dedupe_hit else None


def _patch_common(monkeypatch, toggle=True):
    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(_db, "get_runtime_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)
    monkeypatch.setattr(hc, "_is_trading_day", _weekday)
    return audit, tg


def _alert_rows(day, recent_high, prior_high, zero_last_n=0):
    """Weekday rows over the 37-day span: prior window prior_high HIGHs/day, recent window
    recent_high HIGHs/day; the last zero_last_n trading days get 0 rows entirely."""
    rows, zeroed = [], 0
    d, i = day, 0
    while i < hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS:
        if _weekday(d):
            in_recent = i < hc._LATTICE_RECENT_DAYS
            if in_recent and zeroed < zero_last_n:
                zeroed += 1  # no row at all — a genuinely silent day
            else:
                high = recent_high if in_recent else prior_high
                rows.append({"alert_date": d, "n": max(high, 1), "high_n": high})
        from datetime import timedelta
        d -= timedelta(days=1)
        i += 1
    return rows


@pytest.mark.asyncio
async def test_stands_down_when_the_revert_flag_is_off(monkeypatch):
    audit, tg = _patch_common(monkeypatch, toggle=False)
    out = await hc.run_catalyst_lattice_monitor(conn=_FakeConn(), today=_FRI)
    assert out["enabled"] is False and out["triggers"] == []
    tg.assert_not_called()
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_healthy_day_is_totally_silent(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == [] and out["errors"] == []
    tg.assert_not_called()
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_a_member_graded_routine_by_the_acting_side(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "lattice"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    kinds = [t["kind"] for t in out["triggers"]]
    assert kinds == ["p1_member_routine"]
    msg = tg.call_args[0][0]
    assert "MRNA" in msg and "P1 MISS" in msg
    assert hc._LATTICE_REVERT_SQL in msg          # the EXACT revert command
    events = [c.args[0] for c in audit.call_args_list]
    assert "catalyst_lattice_monitor_alert" in events
    assert "catalyst_lattice_p1_miss" in events


@pytest.mark.asyncio
async def test_trigger_a_same_side_llm_row_uses_llm_grade_and_dedupe_holds(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    # live_side='llm': the LLM grade acted; lattice saying routine must NOT fire
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "llm"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == []
    # and an ALREADY-announced miss stays announced-once (dedupe row present)
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "lattice"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3),
        dedupe_hit=True)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == []


@pytest.mark.asyncio
async def test_trigger_b_high_collapse_names_the_numbers(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["high_volume_drop"]
    t = out["triggers"][0]
    assert t["recent_avg"] == 1.0 and t["prior_avg"] == 4.0 and t["drop_pct"] == 75.0
    msg = tg.call_args[0][0]
    assert "HIGH-ALERT COLLAPSE" in msg and "75.0%" in msg
    assert hc._LATTICE_REVERT_SQL in msg


@pytest.mark.asyncio
async def test_trigger_c_two_consecutive_zero_alert_trading_days(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    # last 2 trading days silent; earlier recent days busy enough that (b) stays quiet
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=2))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["zero_alert_days"]
    assert out["triggers"][0]["days"] == ["2026-08-21", "2026-08-20"]
    msg = tg.call_args[0][0]
    assert "ZERO-ALERT DAYS" in msg and "2026-08-21" in msg
    assert hc._LATTICE_REVERT_SQL in msg


@pytest.mark.asyncio
async def test_one_zero_day_does_not_fire_trigger_c(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=1))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert all(t["kind"] != "zero_alert_days" for t in out["triggers"])


@pytest.mark.asyncio
async def test_unreachable_fixture_is_loud_never_silent(monkeypatch):
    """P1 trigger going DARK is itself alert-worthy — a warning fires (3-day dedupe),
    an error is recorded, and the other two triggers still run."""
    audit, tg = _patch_common(monkeypatch)
    monkeypatch.setattr(hc, "_load_must_not_miss_members", lambda: None)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert {"fixture": "unreachable"} in out["errors"]
    assert out["triggers"] == []
    warn = tg.call_args[0][0]
    assert "DARK" in warn and "must_not_miss" in warn


def test_revert_sql_targets_the_one_flag():
    """The command the operator gets must flip exactly the `catalyst_tier_lattice`
    safeguard row the runtime toggle reads — the documented #400a idiom."""
    assert "'catalyst_tier_lattice'" in hc._LATTICE_REVERT_SQL
    assert "'global'" in hc._LATTICE_REVERT_SQL and "'off'" in hc._LATTICE_REVERT_SQL
    assert "ON CONFLICT (safeguard, account_mode)" in hc._LATTICE_REVERT_SQL
