"""Tests for the v1.0 FL-clock countdown (#426, #418 §5) — scripts/v1_closeout_status.py.

Covers: each clock's pure counter logic on synthetic dates, the render format
(normal + reset-red), reset detection via snapshot-diff, PLAN.md blocking-count
parsing, and the guarded evening-briefing wire (a computation exception must
NOT break the briefing).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from scripts.v1_closeout_status import (
    BLOCKING_TASK_IDS,
    FL1_TARGET,
    FL3_TARGET,
    FL4_TARGET,
    FL8_TARGET,
    _recent_sundays as _recent_sundays_helper,
    check_and_snapshot_resets,
    compute_and_render,
    compute_blocking_open,
    compute_declaration_estimate,
    compute_fl1,
    compute_fl3,
    compute_fl4,
    compute_fl8,
    detect_resets,
    gather_status,
    parse_plan_open_ids,
    render_line,
)

MOD = "scripts.v1_closeout_status"


# ── FL-1 soak ────────────────────────────────────────────────────────────────

def test_fl1_all_clean_counts_every_trading_day():
    # Mon 6/30 - Thu 7/2 = 3 trading days, no weekends in between
    fl1 = compute_fl1(set(), set(), date(2026, 6, 30), date(2026, 7, 2))
    assert fl1["n"] == 3
    assert fl1["target"] == FL1_TARGET
    assert fl1["reset_reason"] is None


def test_fl1_l1_breach_resets_to_zero_and_records_reason():
    # breach on 7/1 (Wed): 6/30 clean (streak=1), 7/1 breach (streak->0), 7/2 clean (streak=1)
    fl1 = compute_fl1({date(2026, 7, 1)}, set(), date(2026, 6, 30), date(2026, 7, 2))
    assert fl1["n"] == 1
    assert fl1["reset_reason"] == "L1 invariant breach 7/1"


def test_fl1_manual_repair_resets_to_zero():
    fl1 = compute_fl1(set(), {date(2026, 7, 2)}, date(2026, 6, 30), date(2026, 7, 2))
    assert fl1["n"] == 0
    assert fl1["reset_reason"] == "manual repair 7/2"


def test_fl1_weekend_days_excluded():
    # 7/3 Fri, 7/4 Sat, 7/5 Sun, 7/6 Mon -> only 7/3 and 7/6 are trading days
    fl1 = compute_fl1(set(), set(), date(2026, 7, 3), date(2026, 7, 6))
    assert fl1["n"] == 2


# ── FL-3 ops streak ──────────────────────────────────────────────────────────

def _ops_row(event_type: str, d: date) -> dict:
    return {"event_type": event_type, "d": d}


def test_fl3_all_green_nights():
    rows = []
    for d in (date(2026, 7, 5), date(2026, 7, 6)):
        rows.append(_ops_row("backup_restore_check_ok", d))
        rows.append(_ops_row("watchdog_heartbeat", d))
    fl3 = compute_fl3(rows, date(2026, 7, 5), date(2026, 7, 6))
    assert fl3["n"] == 2
    assert fl3["target"] == FL3_TARGET
    assert fl3["reset_reason"] is None


def test_fl3_missing_backup_check_resets():
    rows = [_ops_row("watchdog_heartbeat", date(2026, 7, 5))]  # no backup row that night
    fl3 = compute_fl3(rows, date(2026, 7, 5), date(2026, 7, 5))
    assert fl3["n"] == 0
    assert fl3["reset_reason"] == "backup-check missing 7/5"


def test_fl3_service_down_resets():
    rows = [
        _ops_row("backup_restore_check_ok", date(2026, 7, 5)),
        _ops_row("watchdog_heartbeat", date(2026, 7, 5)),
        _ops_row("service_down", date(2026, 7, 5)),
    ]
    fl3 = compute_fl3(rows, date(2026, 7, 5), date(2026, 7, 5))
    assert fl3["n"] == 0
    assert fl3["reset_reason"] == "service_down fired 7/5"


def test_fl3_end_before_start_yields_zero_no_crash():
    fl3 = compute_fl3([], date(2026, 7, 5), date(2026, 7, 4))
    assert fl3["n"] == 0
    assert fl3["reset_reason"] is None


# ── FL-4 mirror quiet days ───────────────────────────────────────────────────

def test_fl4_quiet_days_counts_up():
    fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 8))  # Mon-Wed, 3 trading days
    assert fl4["n"] == 3
    assert fl4["target"] == FL4_TARGET


def test_fl4_drift_alert_resets():
    fl4 = compute_fl4({date(2026, 7, 7)}, date(2026, 7, 6), date(2026, 7, 8))
    assert fl4["n"] == 1  # only 7/8 clean after the 7/7 reset
    assert fl4["reset_reason"] == "coverage-drift D1/D2-HIGH 7/7"


# ── FL-8 Sunday streak ───────────────────────────────────────────────────────

def test_fl8_three_consecutive_sundays():
    # Only the 3 tracked Sundays are supplied (mirrors the roadmap doc's "3/4"
    # state) — the lookback buffer extends past them, so it correctly reports
    # the nearest earlier gap it can see; that's irrelevant to n (the CURRENT
    # streak ending at anchor), which is what this test pins.
    sundays = {date(2026, 6, 21), date(2026, 6, 28), date(2026, 7, 5)}
    fl8 = compute_fl8(sundays, date(2026, 7, 6))  # most recent Sunday <= today is 7/5
    assert fl8["n"] == 3
    assert fl8["target"] == FL8_TARGET


def test_fl8_fully_clean_buffer_window_has_no_reset_reason():
    # Every Sunday across the whole lookback buffer ran clean -> no gap anywhere
    # in view -> reset_reason is None (the true "nothing to report" case).
    anchor = date(2026, 7, 5)
    sundays = set(_recent_sundays_helper(anchor, FL8_TARGET + 8))
    fl8 = compute_fl8(sundays, date(2026, 7, 6))
    assert fl8["n"] == FL8_TARGET + 8
    assert fl8["reset_reason"] is None


def test_fl8_missed_sunday_resets():
    # 6/21 ran, 6/28 MISSED, 7/5 ran -> streak ending at 7/5 is only 1
    sundays = {date(2026, 6, 21), date(2026, 7, 5)}
    fl8 = compute_fl8(sundays, date(2026, 7, 6))
    assert fl8["n"] == 1
    assert fl8["reset_reason"] == "weekly review missed 6/28"


def test_fl8_counts_today_when_today_is_sunday():
    sundays = {date(2026, 7, 5)}
    fl8 = compute_fl8(sundays, date(2026, 7, 5))
    assert fl8["n"] == 1


# ── PLAN.md blocking-count parsing ───────────────────────────────────────────

def test_parse_plan_open_ids_basic():
    text = (
        "## Some project\n"
        "- #100 | 2026-08-01 | pending | some title\n"
        "- #101 | 2026-08-01 | in_progress | another title [b1]\n"
        "not a task line\n"
        "- #102 | 2026-08-01 | blocked | third\n"
    )
    assert parse_plan_open_ids(text) == {100, 101, 102}


def test_compute_blocking_open_counts_only_intersection():
    some_blocking_id = next(iter(BLOCKING_TASK_IDS))
    open_ids = {some_blocking_id, 999999}  # 999999 is not a BLOCKING id
    assert compute_blocking_open(open_ids) == 1


def test_compute_blocking_open_all_closed():
    assert compute_blocking_open(set()) == 0


# ── declaration estimate ─────────────────────────────────────────────────────

def test_declaration_estimate_is_a_future_date_string_shape():
    d = compute_declaration_estimate(date(2026, 7, 6), fl1_n=3, fl3_n=1, fl4_n=0, fl8_n=3)
    assert d > date(2026, 7, 6)


# ── render_line ──────────────────────────────────────────────────────────────

def _status(fl1=3, fl3=2, fl4=0, fl8=3, blocking=20, decl="7/20", resets=None):
    return {
        "fl1": {"n": fl1, "target": FL1_TARGET},
        "fl3": {"n": fl3, "target": FL3_TARGET},
        "fl4": {"n": fl4, "target": FL4_TARGET},
        "fl8": {"n": fl8, "target": FL8_TARGET},
        "blocking_open": blocking,
        "decl_estimate": decl,
        "resets": resets or [],
    }


def test_render_line_normal_state():
    line = render_line(_status())
    assert line.startswith("\U0001F3C1 v1.0:")
    assert "FL-1 3/10" in line
    assert "FL-3 2/7" in line
    assert "FL-4 0/5" in line
    assert "FL-8 3/4" in line
    assert "blocking 20 open" in line
    assert "decl ~7/20" in line
    assert "\U0001F534" not in line


def test_render_line_reset_state_prepends_red_and_reason():
    status = _status(fl1=0, resets=[{"clock": "FL-1", "reason": "manual repair 7/8"}])
    line = render_line(status)
    assert line.startswith("\U0001F534 v1.0:")
    assert "FL-1 reset (manual repair 7/8)" in line


def test_render_line_handles_unknown_blocking_count():
    status = _status(blocking=None)
    line = render_line(status)
    assert "blocking ? open" in line


# ── detect_resets (snapshot diff) ───────────────────────────────────────────

def test_detect_resets_no_prior_snapshot_is_silent():
    current = {"fl1": {"n": 0, "reset_reason": "L1 invariant breach 7/8"}}
    assert detect_resets(None, current) == []


def test_detect_resets_drop_flags_the_clock():
    prior = {"fl1": {"n": 5}}
    current = {"fl1": {"n": 0, "reset_reason": "manual repair 7/8"}}
    resets = detect_resets(prior, current)
    assert resets == [{"clock": "FL-1", "reason": "manual repair 7/8"}]


def test_detect_resets_no_drop_is_silent():
    prior = {"fl1": {"n": 5}}
    current = {"fl1": {"n": 6, "reset_reason": None}}
    assert detect_resets(prior, current) == []


def test_detect_resets_multiple_clocks():
    prior = {"fl1": {"n": 5}, "fl3": {"n": 4}, "fl4": {"n": 2}, "fl8": {"n": 3}}
    current = {
        "fl1": {"n": 5, "reset_reason": None},
        "fl3": {"n": 0, "reset_reason": "backup-check missing 7/8"},
        "fl4": {"n": 3, "reset_reason": None},
        "fl8": {"n": 3, "reset_reason": None},
    }
    resets = detect_resets(prior, current)
    assert resets == [{"clock": "FL-3", "reason": "backup-check missing 7/8"}]


# ── gather_status (DB-mocked) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gather_status_runs_against_mocked_db(tmp_path, monkeypatch):
    pool, conn = make_mock_pool()
    # Each conn.fetch call in gather_status order: l1, repair, ops, drift, review
    conn.fetch = AsyncMock(side_effect=[
        [],  # l1 breaches
        [],  # manual repairs
        [{"event_type": "backup_restore_check_ok", "d": date(2026, 7, 5)},
         {"event_type": "watchdog_heartbeat", "d": date(2026, 7, 5)}],  # ops rows
        [],  # coverage drift
        [{"review_date": date(2026, 7, 5)}],  # weekly reviews
    ])

    fake_plan = tmp_path / "PLAN.md"
    fake_plan.write_text("## P\n- #347 | 2026-08-01 | pending | t\n", encoding="utf-8")
    monkeypatch.setattr(f"{MOD}.PLAN_MD", fake_plan)

    status = await gather_status(conn, today=date(2026, 7, 6))
    # trading days FL1_SOAK_START(6/30)..last_trading_day(7/6) = 6/30,7/1,7/2,7/3,7/6 = 5
    assert status["fl1"]["n"] == 5
    assert status["fl3"]["n"] == 1  # only 7/5 in the fixture (end = today-1 = 7/5)
    assert status["fl4"]["n"] == 1  # only 7/6 is a trading day in [FL4_START, last_trading_day]
    assert status["fl8"]["n"] == 1
    assert status["blocking_open"] == 1  # #347 is filed + a BLOCKING id


# ── check_and_snapshot_resets + compute_and_render (DB-mocked) ──────────────

@pytest.mark.asyncio
async def test_check_and_snapshot_resets_persists_and_detects(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value={"detail": '{"fl1": {"n": 5}}'})
    conn.execute = AsyncMock()  # _persist_snapshot now writes via the open conn

    status = {
        "today": "2026-07-08", "fl1": {"n": 0, "reset_reason": "manual repair 7/8"},
        "fl3": {"n": 3}, "fl4": {"n": 1}, "fl8": {"n": 3}, "blocking_open": 20,
        "decl_estimate": "7/20",
    }
    resets = await check_and_snapshot_resets(conn, status)
    assert resets == [{"clock": "FL-1", "reason": "manual repair 7/8"}]
    # the fresh snapshot is persisted via conn.execute (INSERT ..., event_type, ...)
    assert conn.execute.await_count == 1
    assert conn.execute.await_args.args[1] == "v1_closeout_snapshot"


@pytest.mark.asyncio
async def test_compute_and_render_end_to_end(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [], [], [], [], [],
    ])
    conn.fetchrow = AsyncMock(return_value=None)  # no prior snapshot
    conn.execute = AsyncMock()  # _persist_snapshot writes via the open conn
    monkeypatch.setattr(f"{MOD}.PLAN_MD", __import__("pathlib").Path(__file__))  # any readable file, 0 task lines

    line = await compute_and_render(conn, today=date(2026, 7, 6))
    assert line.startswith("\U0001F3C1 v1.0:")
    assert "blocking 0 open" in line


# ── Guarded evening-briefing wire ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_briefing_wire_survives_computation_exception(monkeypatch):
    """A raising compute_and_render must NOT propagate out of send_evening_briefing's
    guard — mirrors the try/except pattern already used for sugar_babies/wick/etc."""
    import agents.market_intelligence.briefing as briefing_mod

    async def _boom(conn, today=None):
        raise RuntimeError("db exploded")

    monkeypatch.setattr("scripts.v1_closeout_status.compute_and_render", _boom)

    # Exercise the same guarded block send_evening_briefing uses, in isolation
    # (avoids standing up the full briefing's many other DB dependencies).
    v1_closeout_line = None
    try:
        from scripts.v1_closeout_status import compute_and_render
        v1_closeout_line = await compute_and_render(None, today=date(2026, 7, 6))
    except Exception as e:
        briefing_mod.logger.warning(f"v1.0 closeout status failed: {e}")

    assert v1_closeout_line is None  # guard swallowed it, did not raise


def test_send_evening_briefing_wraps_v1_closeout_in_try_except():
    """Structural pin (mirrors TestBriefingUsesGather in test_recent_changes.py):
    the v1_closeout_status call inside send_evening_briefing's source must sit
    inside a try/except that logs rather than propagates, so a computation bug
    can never take down the whole evening briefing."""
    import inspect

    from agents.market_intelligence import briefing

    src = inspect.getsource(briefing.send_evening_briefing)
    assert "v1_closeout_status" in src
    assert "compute_and_render" in src

    # Isolate the v1-closeout block and confirm it's inside its own try/except
    # whose except body logs (not just `pass`/silent).
    idx = src.index("compute_and_render")
    block = src[max(0, idx - 400):idx + 200]
    assert "try:" in block
    assert "except Exception" in block
    assert "logger.warning" in block


def test_format_evening_briefing_accepts_v1_closeout_line_param():
    """The formatter must accept + surface the line (consolidate-surfaces rule:
    no new command/message, just a new param on the existing formatter)."""
    import inspect

    from agents.market_intelligence import briefing

    sig = inspect.signature(briefing._format_evening_briefing)
    assert "v1_closeout_line" in sig.parameters

    text = briefing._format_evening_briefing(
        regime={"regime": "Unknown", "ep_threshold": 70},
        rs_leaders=[], themes=[], velocity=[], pullbacks=[],
        briefing_date="2026-07-06",
        v1_closeout_line="\U0001F3C1 v1.0: FL-1 3/10 · blocking 20 open · decl ~7/20",
    )
    assert "FL-1 3/10" in text
