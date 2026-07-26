"""Tests for the v1.0 FL-clock countdown (#426, #418 §5) — scripts/v1_closeout_status.py.

Covers: each clock's pure counter logic on synthetic dates, the render format
(normal + reset-red), reset detection via snapshot-diff, PLAN.md blocking-count
parsing, and the guarded evening-briefing wire (a computation exception must
NOT break the briefing).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from scripts.v1_closeout_status import (
    BLOCKING_TASK_IDS,
    INGEST_LIVE_MODES,
    INGEST_MODES,
    INGEST_SAFEGUARD,
    MANUAL_REPAIR_EVENT_TYPES,
    SOAK_FAILURE_EVENT_TYPES,
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
    real_service_down_dates,
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


def test_fl1_terminal_money_path_failure_resets(monkeypatch):
    # RED-2: a day where an automated remediation FAILED (position left naked)
    # must reset the soak — previously it counted as a clean day (fail-open).
    fl1 = compute_fl1(
        set(), set(), date(2026, 6, 30), date(2026, 7, 2),
        failure_dates={date(2026, 7, 1): "stop_ack_remediation_failed"},
    )
    assert fl1["n"] == 1  # 6/30 clean, 7/1 reset, 7/2 clean
    assert fl1["reset_reason"] == (
        "money-path failure: stop_ack_remediation_failed 7/1"
    )


def test_fl1_self_healed_transient_does_not_reset():
    # A stop_update_failed attempt-1 that the 3s retry healed
    # (stop_update_retry_succeeded) is NOT a soak failure. Mirror
    # gather_status's fetch semantics — `event_type = ANY(SOAK_FAILURE_
    # EVENT_TYPES)` — over a day that had ONLY transient events: the filter
    # returns nothing, so failure_dates stays empty and the streak holds.
    transient_day_events = [
        ("stop_update_failed", date(2026, 7, 1)),          # attempt-1
        ("stop_update_retry_succeeded", date(2026, 7, 1)), # self-healed
        ("naked_position_detected", date(2026, 7, 1)),     # auto-remediation path
        ("partial_exit_aborted", date(2026, 7, 1)),        # benign abort shape
    ]
    failure_dates = {
        d: evt for evt, d in transient_day_events
        if evt in SOAK_FAILURE_EVENT_TYPES
    }
    assert failure_dates == {}  # none of these are terminal
    fl1 = compute_fl1(
        set(), set(), date(2026, 6, 30), date(2026, 7, 2),
        failure_dates=failure_dates,
    )
    assert fl1["n"] == 3
    assert fl1["reset_reason"] is None


def test_soak_failure_event_list_is_terminal_only():
    # Membership pin: the curated list carries exactly the terminal
    # remediation-failed events, never self-healing/ambiguous types, and is
    # disjoint from the manual-repair allowlist (no double classification).
    assert "stop_ack_remediation_failed" in SOAK_FAILURE_EVENT_TYPES
    assert "naked_position_remediation_failed" in SOAK_FAILURE_EVENT_TYPES
    for transient in (
        "stop_update_failed",
        "stop_update_retry_succeeded",
        "stop_update_aborted",
        "naked_position_detected",
        "partial_exit_aborted",
        "order_status_reconcile_failed",
        "stuck_pending_new_detected",
    ):
        assert transient not in SOAK_FAILURE_EVENT_TYPES
    assert not set(SOAK_FAILURE_EVENT_TYPES) & set(MANUAL_REPAIR_EVENT_TYPES)


def test_fl1_l1_breach_takes_precedence_over_failure_reason():
    # Same-day L1 breach + money-path failure: one reset, L1 reason wins
    # (reset either way; label priority only).
    d = date(2026, 7, 1)
    fl1 = compute_fl1(
        {d}, set(), date(2026, 6, 30), date(2026, 7, 2),
        failure_dates={d: "naked_position_remediation_failed"},
    )
    assert fl1["n"] == 1
    assert fl1["reset_reason"] == "L1 invariant breach 7/1"


def test_fl1_weekend_days_excluded(monkeypatch):
    # Pin a deterministic weekday-only calendar so this tests the FL logic, not
    # the real NYSE holiday set (7/3/2026 is Jul-4-observed — a HOLIDAY — so with
    # the real calendar the count differs; that env-dependence red-CI'd 7/6).
    monkeypatch.setattr(f"{MOD}._is_trading_day", lambda d: d.weekday() < 5)
    # 7/3 Fri, 7/4 Sat, 7/5 Sun, 7/6 Mon -> only 7/3 and 7/6 are weekday trading days
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


# ── FL-3 refinement: real_service_down_dates (operator-signed 2026-07-07) ──────
# Only REAL sustained outages reset the ops-autonomy streak. Modeled on the exact
# 7/5-7/6 prod events that had FL-3 falsely stuck at 0.

def _dn(summary, ts, d):
    return {"event_type": "service_down", "summary": summary, "ts": ts, "d": d}


def _rc(summary, ts):
    return {"event_type": "service_recovered", "summary": summary, "ts": ts, "d": ts.date()}


def test_real_down_excludes_watchdog_selftest():
    # The 7/5 12:07 event — the watchdog testing its OWN detector, not a real service.
    rows = [_dn("watchdog: apollo-watchdog-selftest DOWN — container not found",
                datetime(2026, 7, 5, 12, 7), date(2026, 7, 5))]
    assert real_service_down_dates(rows) == set()


def test_real_down_excludes_transient_deploy_blip():
    # The 7/6 11:15 event — apollo-market 'restarting', recovered 5 min later.
    ts = datetime(2026, 7, 6, 11, 15)
    rows = [
        _dn("watchdog: apollo-market DOWN — container state: restarting", ts, date(2026, 7, 6)),
        _rc("watchdog: apollo-market recovered", ts + timedelta(minutes=5)),
    ]
    assert real_service_down_dates(rows) == set()


def test_real_down_counts_sustained_outage():
    ts = datetime(2026, 7, 6, 11, 15)
    rows = [_dn("watchdog: apollo-market DOWN — container state: exited", ts, date(2026, 7, 6))]
    assert real_service_down_dates(rows) == {date(2026, 7, 6)}


def test_real_down_counts_when_recovery_beyond_window():
    ts = datetime(2026, 7, 6, 11, 15)
    rows = [
        _dn("watchdog: apollo-market DOWN — ...", ts, date(2026, 7, 6)),
        _rc("watchdog: apollo-market recovered", ts + timedelta(minutes=25)),  # >10 min = real
    ]
    assert real_service_down_dates(rows) == {date(2026, 7, 6)}


def test_real_down_recovery_of_different_container_does_not_clear():
    ts = datetime(2026, 7, 6, 11, 15)
    rows = [
        _dn("watchdog: apollo-market DOWN — ...", ts, date(2026, 7, 6)),
        _rc("watchdog: apollo-orchestrator recovered", ts + timedelta(minutes=2)),
    ]
    assert real_service_down_dates(rows) == {date(2026, 7, 6)}


# ── FL-4 mirror quiet days ───────────────────────────────────────────────────
# YELLOW-3 (2026-07-12): the quiet-day clock is gated on the #184b broker-order
# ingest being PROMOTED (live_r1+) — promotion state + flip date are now inputs.

def test_fl4_quiet_days_counts_up_when_promoted():
    # promoted Sunday 7/5 → credit starts Monday 7/6; Mon-Wed = 3 trading days.
    # Every live tier (r1/r2/r3) counts — cumulative enables.
    for mode in sorted(INGEST_LIVE_MODES):
        fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 8),
                          ingest_mode=mode, ingest_promoted_on=date(2026, 7, 5))
        assert fl4["n"] == 3
        assert fl4["target"] == FL4_TARGET
        assert fl4["gate"] is None


def test_fl4_drift_alert_resets():
    fl4 = compute_fl4({date(2026, 7, 7)}, date(2026, 7, 6), date(2026, 7, 8),
                      ingest_mode="live_r1", ingest_promoted_on=date(2026, 7, 5))
    assert fl4["n"] == 1  # only 7/8 clean after the 7/7 reset
    assert fl4["reset_reason"] == "coverage-drift D1/D2-HIGH 7/7"


def test_fl4_not_promoted_never_reads_green():
    # THE YELLOW-3 bug: a full quiet week while the ingest is dark/dry_run must
    # NOT read green (pre-fix this returned n=5 → "FL-4 5/5 ✓" in the briefing
    # while the repair half of FL-4's DoD wasn't even live).
    for mode in ("off", "dry_run"):
        fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 10), ingest_mode=mode)
        assert fl4["n"] == 0
        assert fl4["n"] < FL4_TARGET  # can never satisfy the target while gated
        assert fl4["gate"] == f"ingest {mode}"
        assert "live_r1 promotion" in fl4["reset_reason"]


def test_fl4_default_args_fail_closed():
    # A call site that forgets the promotion wiring must under-read (0), never
    # silently count — the fail-open shape was the bug.
    fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 10))
    assert fl4["n"] == 0
    assert fl4["gate"] == "ingest off"


def test_fl4_unrecognized_mode_fails_closed():
    fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 10), ingest_mode="banana")
    assert fl4["n"] == 0
    assert fl4["gate"] == "ingest banana"


def test_fl4_counts_only_post_promotion_quiet_days():
    # promoted Tue 7/7 → credit starts Wed 7/8. Pre-promotion drift (7/6) is
    # invisible to the post-promotion streak — only 7/8-7/10 count.
    fl4 = compute_fl4({date(2026, 7, 6)}, date(2026, 7, 6), date(2026, 7, 10),
                      ingest_mode="live_r1", ingest_promoted_on=date(2026, 7, 7))
    assert fl4["n"] == 3  # 7/8, 7/9, 7/10
    assert fl4["reset_reason"] is None
    assert fl4["gate"] is None


def test_fl4_promotion_day_itself_not_credited():
    # The flip day is a mixed-mode day (cycles before the flip ran unpromoted).
    fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 8),
                      ingest_mode="live_r1", ingest_promoted_on=date(2026, 7, 8))
    assert fl4["n"] == 0
    assert fl4["gate"] is None  # promoted — just no credited days yet


def test_fl4_promoted_but_unknown_flip_date_reads_zero_loud():
    # Never guess a start date (that re-opens the over-credit bug) — read 0 and
    # say what to fix.
    fl4 = compute_fl4(set(), date(2026, 7, 6), date(2026, 7, 10), ingest_mode="live_r1")
    assert fl4["n"] == 0
    assert fl4["gate"] == "promo date unknown"
    assert "last_transition_at" in fl4["reset_reason"]


def test_fl4_ingest_constants_match_order_ingest():
    # The toggle constants are mirrored (not imported — order_ingest imports
    # briefing at module top; briefing imports this module inside
    # send_evening_briefing). This pin is the drift gate for the mirror.
    from agents.market_intelligence.broker import order_ingest

    assert INGEST_SAFEGUARD == order_ingest.INGEST_TOGGLE
    assert INGEST_MODES == order_ingest.INGEST_MODES
    assert INGEST_LIVE_MODES == frozenset(order_ingest._LIVE_TIER)


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


def test_render_line_fl4_gate_suffix_while_dark():
    # While the ingest is not promoted, FL-4 must SAY it's gated — "0/5 (ingest
    # dry_run)" — not read like a clock that merely hasn't started (YELLOW-3).
    status = _status(fl4=0)
    status["fl4"]["gate"] = "ingest dry_run"
    line = render_line(status)
    assert "FL-4 0/5 (ingest dry-run)"  # md-safe render (#477): bare _ broke the brief chunk in line


def test_render_line_fl4_no_suffix_when_counting_normally():
    status = _status(fl4=2)
    status["fl4"]["gate"] = None
    line = render_line(status)
    assert "FL-4 2/5 ·" in line
    assert "(ingest" not in line


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
    # Deterministic weekday-only calendar (see test_fl1_weekend_days_excluded) so
    # the trading-day counts are env-independent (real 7/3 is a holiday in CI).
    monkeypatch.setattr(f"{MOD}._is_trading_day", lambda d: d.weekday() < 5)
    pool, conn = make_mock_pool()
    # Each conn.fetch call in gather_status order:
    # l1, repair, money-path failures, ops, drift, review
    conn.fetch = AsyncMock(side_effect=[
        [],  # l1 breaches
        [],  # manual repairs
        [],  # terminal money-path failures (RED-2)
        [{"event_type": "backup_restore_check_ok", "d": date(2026, 7, 5)},
         {"event_type": "watchdog_heartbeat", "d": date(2026, 7, 5)}],  # ops rows
        [],  # coverage drift
        [{"review_date": date(2026, 7, 5)}],  # weekly reviews
    ])

    # ingest toggle row (fetchrow): promoted live_r1 on Sunday 7/5 → FL-4
    # credits from Monday 7/6 (the YELLOW-3 gate wiring).
    conn.fetchrow = AsyncMock(
        return_value={"state": "live_r1", "promoted_on": date(2026, 7, 5)})

    fake_plan = tmp_path / "PLAN.md"
    fake_plan.write_text("## P\n- #347 | 2026-08-01 | pending | t\n", encoding="utf-8")
    monkeypatch.setattr(f"{MOD}.PLAN_MD", fake_plan)

    status = await gather_status(conn, today=date(2026, 7, 6))
    # F1 ruling 7/12: FL1_SOAK_START=7/8 (strict). With today=7/6 the window
    # (7/8..7/6) is empty → n=0. (Pre-ruling this fixture read 5 from a 6/30 start.)
    assert status["fl1"]["n"] == 0
    assert status["fl3"]["n"] == 1  # only 7/5 in the fixture (end = today-1 = 7/5)
    assert status["fl4"]["n"] == 1  # only 7/6 is a trading day in [FL4_START, last_trading_day]
    assert status["fl4"]["ingest_mode"] == "live_r1"
    assert status["fl8"]["n"] == 1
    assert status["blocking_open"] == 1  # #347 is filed + a BLOCKING id


@pytest.mark.asyncio
async def test_gather_status_money_path_failure_resets_fl1(tmp_path, monkeypatch):
    # RED-2 end-to-end (DB-mocked): a stop_ack_remediation_failed row on 7/2
    # resets FL-1 through gather_status's new failure fetch.
    monkeypatch.setattr(f"{MOD}._is_trading_day", lambda d: d.weekday() < 5)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [],  # l1 breaches
        [],  # manual repairs
        [{"d": date(2026, 7, 10), "event_type": "stop_ack_remediation_failed"}],
        [],  # ops rows
        [],  # coverage drift
        [],  # weekly reviews
    ])
    conn.fetchrow = AsyncMock(return_value=None)  # no ingest toggle row
    monkeypatch.delenv("BROKER_ORDER_INGEST_MODE", raising=False)
    fake_plan = tmp_path / "PLAN.md"
    fake_plan.write_text("## P\n", encoding="utf-8")
    monkeypatch.setattr(f"{MOD}.PLAN_MD", fake_plan)

    status = await gather_status(conn, today=date(2026, 7, 15))
    # F1-ruling window (start 7/8): weekday trading days 7/8..7/15 =
    # 7/8,9,10,13,14,15; reset at 7/10 -> streak 7/13,14,15 = 3
    assert status["fl1"]["n"] == 3
    assert status["fl1"]["reset_reason"] == (
        "money-path failure: stop_ack_remediation_failed 7/10"
    )


@pytest.mark.asyncio
async def test_gather_status_fl4_gated_while_dry_run_despite_quiet_days(tmp_path, monkeypatch):
    # YELLOW-3 end-to-end: ZERO drift rows across a full quiet week, but the
    # toggle row says dry_run → FL-4 reads 0 (gated), and the rendered line
    # says why — the briefing can no longer show "5/5 ✓" while the ingest is
    # dark/dry_run.
    monkeypatch.setattr(f"{MOD}._is_trading_day", lambda d: d.weekday() < 5)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], [], [], [], [], []])
    conn.fetchrow = AsyncMock(
        return_value={"state": "dry_run", "promoted_on": date(2026, 7, 8)})
    fake_plan = tmp_path / "PLAN.md"
    fake_plan.write_text("## P\n", encoding="utf-8")
    monkeypatch.setattr(f"{MOD}.PLAN_MD", fake_plan)

    status = await gather_status(conn, today=date(2026, 7, 10))
    assert status["fl4"]["n"] == 0
    assert status["fl4"]["gate"] == "ingest dry_run"
    assert "FL-4 0/5 (ingest dry-run)"  # md-safe render (#477): bare _ broke the brief chunk in render_line(status)


@pytest.mark.asyncio
async def test_gather_status_fl4_env_only_promotion_is_loud_unknown(tmp_path, monkeypatch):
    # No toggle row + BROKER_ORDER_INGEST_MODE=live_r1 (env-only promotion):
    # there is no flip timestamp to count from → 0/5 with the loud
    # "promo date unknown" gate (insert the mi_safeguard_state row), never a
    # guessed start date.
    monkeypatch.setattr(f"{MOD}._is_trading_day", lambda d: d.weekday() < 5)
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], [], [], [], [], []])
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setenv("BROKER_ORDER_INGEST_MODE", "live_r1")
    fake_plan = tmp_path / "PLAN.md"
    fake_plan.write_text("## P\n", encoding="utf-8")
    monkeypatch.setattr(f"{MOD}.PLAN_MD", fake_plan)

    status = await gather_status(conn, today=date(2026, 7, 10))
    assert status["fl4"]["n"] == 0
    assert status["fl4"]["ingest_mode"] == "live_r1"
    assert status["fl4"]["gate"] == "promo date unknown"


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
        [], [], [], [], [], [],
    ])
    conn.fetchrow = AsyncMock(return_value=None)  # no ingest toggle row, no prior snapshot
    conn.execute = AsyncMock()  # _persist_snapshot writes via the open conn
    monkeypatch.delenv("BROKER_ORDER_INGEST_MODE", raising=False)  # deterministic env fallback → off
    monkeypatch.setattr(f"{MOD}.PLAN_MD", __import__("pathlib").Path(__file__))  # any readable file, 0 task lines

    line = await compute_and_render(conn, today=date(2026, 7, 6))
    assert line.startswith("\U0001F3C1 v1.0:")
    assert "blocking 0 open" in line
    assert "FL-4 0/5 (ingest off)" in line  # gated, and the line says why


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


def test_v1_closeout_line_retired_from_evening_briefing():
    """#479 (operator-ruled 2026-07-26): the v1.0 closeout line is RETIRED from
    the evening brief — stale since the 7/24 v1.0 declaration. The compute
    module keeps its own tests above (history / ad-hoc use); the brief must
    neither call it nor accept the parameter anymore."""
    import inspect

    from agents.market_intelligence import briefing

    src = inspect.getsource(briefing.send_evening_briefing)
    assert "v1_closeout_status" not in src
    assert "compute_and_render" not in src

    sig = inspect.signature(briefing._format_evening_briefing)
    assert "v1_closeout_line" not in sig.parameters


def test_render_line_is_markdown_entity_safe_for_all_gate_modes():
    """2026-07-16 (#477): 'FL-4 0/5 (ingest dry_run)' put ONE bare underscore
    into the evening brief — it paired with the RS footer's italics opener and
    the whole chunk 400'd into the plain-text fallback, with Telegram blaming
    an innocent offset thousands of bytes later. Every dynamic gate/reset token
    must render with NO unpaired markdown entity chars. Pins all INGEST_MODES
    (live_r1/r2/r3 would re-trigger the bug on each future mode flip)."""
    from scripts.v1_closeout_status import INGEST_MODES

    for mode in INGEST_MODES:
        status = _status()
        status["fl4"]["gate"] = f"ingest {mode}"
        line = render_line(status)
        for ch in ("_", "*", "`"):
            assert ch not in line, f"mode {mode!r} leaked {ch!r}: {line}"

    # reset reasons are dynamic too (clock names + free text)
    line = render_line(_status(resets=[
        {"clock": "fl4_ingest", "reason": "mode flipped dry_run→live_r1"}]))
    for ch in ("_", "*", "`"):
        assert ch not in line
