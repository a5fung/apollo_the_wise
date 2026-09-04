"""v1.0 FL-clock countdown — the daily anti-idle driving surface (#426, #418 §5).

Computes the four measurable finish-line clocks from `docs/roadmap/v1-closeout-
productization.md` §2 (FL-1 live-loop soak, FL-3 ops-autonomy streak, FL-4 mirror
quiet-days, FL-8 learning-loop Sunday streak) plus the BLOCKING open-task count,
and renders ONE compact line that gets appended to the existing evening briefing
(consolidate-surfaces rule — no new command). See briefing.py::send_evening_briefing.

Architecture (pure computation vs I/O, so the clock logic is unit-testable without
a DB): each `compute_flN(...)` function takes already-fetched dates/rows and is
pure. `gather_status(conn, today)` does the DB/file reads and calls the pure
functions. `render_line(status)` is pure formatting. `detect_resets(prior,
current)` is pure (snapshot diff). The only write is `_persist_snapshot`, via the
existing `log_audit_event` (self-acquiring, never raises) — restart-safe/DB-
sourced per `feedback_scheduler_aggregators_db_sourced` (no module-level state).

ASSUMPTIONS (stated per the build card's conservative-if-unclear instruction):
  - Trading-day calendar = holiday-aware via `trading_calendar.get_market_status`
    (2026-07-06 /simplify: was weekday-only, which miscounted observed holidays
    like 2026-07-03; now uses the NYSE-calendar helper, with a weekday fallback
    if that module is unavailable).
  - FL-1 "manual trade-state repair" has NO single mechanical audit event type —
    every past incident's one-off remediation script invented its own event_type
    (see MANUAL_REPAIR_EVENT_TYPES below). The allowlist covers every such event
    type that exists in the repo TODAY (2026-07-06); a future incident with a
    novel event-type name would be silently missed until this list is extended.
    L1-invariant-breach detection (mi_audit_log 'anomaly_detected', level=1) IS
    mechanical/reliable via `system_audit._emit_l1` and is the primary signal.
    RED-2 (2026-07-12): terminal money-path failures (automated remediation
    FAILED, position left naked — see SOAK_FAILURE_EVENT_TYPES) ALSO reset the
    soak; previously such a CRITICAL day counted as clean (fail-open).
  - FL-3 "night" is bucketed by ET calendar date. Because `backup_restore_check`
    cron fires ~23:30 ET (03:30 UTC, the NEXT UTC day) and the evening briefing
    fires at 20:00 ET, TODAY's own backup-check has not run yet when the
    briefing does — so the walk's end boundary is YESTERDAY (the most recently
    fully-completed ops night), not today.
  - FL-4 "day" = trading day; by 20:00 ET the last 15-min reconcile cycle
    (ends 16:45 ET) has already run, so TODAY can be included once it's a
    trading day. Anchored at 2026-07-06 (detector built 7/5, but 7/5 was a
    Saturday — first live cycles Monday 7/6 per the roadmap doc).
    YELLOW-3 (2026-07-12): the quiet-day clock is additionally GATED on the
    #184b broker-order ingest (the repair half FL-4's DoD rides on) being
    PROMOTED to live (live_r1+). Pre-fix the meter counted drift-quiet days
    regardless of promotion state, so the briefing could read "5/5 ✓" while
    the ingest was still dark/dry_run — the meter measured a different thing
    than the F2 gate. This is a METER change only; the ingest toggle itself
    is read (never written) here.
  - BLOCKING open count: per the build card's fallback clause, this hardcodes
    the §4a BLOCKING task-ID list (see BLOCKING_TASK_IDS below) rather than
    parsing the markdown table live — the DoD prose in each §4a row cross-
    references OTHER task numbers (e.g. "#151 discipline", "#137 degraded-read
    guard") that a blanket `#\\d+` regex over the section would incorrectly
    sweep in. The static "what's on the list" half is hand-extracted once from
    the doc (update BLOCKING_TASK_IDS if §4a changes); the "still open" half is
    live — checked against PLAN.md's CURRENT task lines every run (PLAN.md only
    lists OPEN tasks; a closed task is removed from the file entirely, per
    scripts/check_plan.py's schema). S-A/S-B/S-D/S-E resolved to their filed
    numeric IDs #421/#422/#423/#424 per the 2026-07-05 glide path (verified
    live in PLAN.md 2026-07-06).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
PLAN_MD = REPO / "PLAN.md"

# ── FL clock constants ──────────────────────────────────────────────────────
# F1 SOAK RULING (operator, 2026-07-12 — the readiness-redteam RED-1 reconcile):
# STRICT — the 7/6 phantom-reap + 7/7 jsonb-cleanup repairs reset the clock; the
# clean streak starts 7/8. This constant IS the ruling; do not move it without a
# new operator ruling (the meter and the walk pack must never disagree again).
# 10 trading days from 7/8 → completes EOD 7/21, green 7/22.
FL1_SOAK_START = date(2026, 7, 8)
FL1_TARGET = 10

FL3_START = date(2026, 7, 5)
FL3_TARGET = 7

FL4_START = date(2026, 7, 6)  # first live coverage-drift reconcile cycle (Monday)
FL4_TARGET = 5

# FL-4 promotion gate (YELLOW-3 meter honesty, 2026-07-12): quiet days are only
# credited while the #184b broker-order ingest is PROMOTED (live_r1+). These
# mirror broker/order_ingest.py's INGEST_TOGGLE / INGEST_MODES / _LIVE_TIER —
# NOT imported, because order_ingest imports briefing at module top and
# briefing imports this module inside send_evening_briefing (a top-level import
# here would create an order-sensitive cycle). Drift is pinned by
# test_fl4_ingest_constants_match_order_ingest.
INGEST_SAFEGUARD = "broker_order_ingest"
INGEST_MODES = ("off", "dry_run", "live_r1", "live_r2", "live_r3")
INGEST_LIVE_MODES = frozenset({"live_r1", "live_r2", "live_r3"})

FL8_TARGET = 4

SNAPSHOT_EVENT = "v1_closeout_snapshot"

# Hand-curated allowlist of one-off manual trade-state repair scripts' audit
# event types (see module docstring — no single mechanical signal exists).
MANUAL_REPAIR_EVENT_TYPES = [
    # NOT phantom_pending_confirmation_reaped (#287): operator-signed 2026-07-06 —
    # reaping rows that NEVER became positions (no fill, no order) is DB hygiene,
    # not a repair of a live-loop position. FL-1 measures the loop running clean;
    # one-off phantom cleanup does not reset the soak. (The reap already can't
    # touch a real position — it broker-confirms absence first.)
    "naked_position_reconciled",             # scripts/reconcile_orphan_stop.py
    "manual_reconcile_9m_day2_stop_clobber", # scripts/_reconcile_9m_day2_stop_clobber.py
    "manual_reconcile_bw_pre_fill",          # scripts/probes/_reconcile_2026_05_14_bugs.py
    "manual_reconcile_phantom_splits",       # scripts/probes/_reconcile_2026_05_14_bugs.py
]

# TERMINAL money-path failure events (RED-2 fix, 2026-07-12). The soak was
# fail-open: it reset only on L1 breaches + the manual-repair scripts above, so
# a day where an AUTOMATED remediation FAILED and left a position naked —
# a CRITICAL "MANUAL INTERVENTION REQUIRED" day — counted as CLEAN. These
# event types are emitted ONLY on terminal outcomes (the loop could not
# self-heal; hands were required), never on self-healed transients:
SOAK_FAILURE_EVENT_TYPES = [
    # scheduler.py::_stop_ack_timeout_watchdog — filled position with NULL
    # stop_order_id >30s, and EITHER remediation was impossible (qty/orb_low
    # missing) OR the fallback stop submit itself raised. Both paths Telegram
    # "CRITICAL ... MANUAL INTERVENTION REQUIRED"; the position stays naked.
    "stop_ack_remediation_failed",
    # trade_stream.py::_process_entry_fill — entry-fill DB UPDATE raised AND
    # the immediate fallback stop failed (or no orb_low anchor existed):
    # "POSITION NAKED AND UNRECOVERABLE ... MANUAL INTERVENTION REQUIRED NOW".
    "naked_position_remediation_failed",
]
# Deliberately EXCLUDED (transient / self-healing / ambiguous event types —
# adding them would reset the soak on days the loop actually ran clean):
#   stop_update_retry_triggered   (#607, 2026-09-04) attempt-1 place_stop_order
#                                 failure — self-heals via the 3s retry
#                                 (stop_update_retry_succeeded); was named
#                                 `stop_update_failed` (attempt=1) before the
#                                 2026-09-04 rename split it out, so pre-rename
#                                 rows of this shape are named `stop_update_failed`
#                                 in the DB, not this — no code here reads
#                                 `attempt`, so nothing to bridge: both names sit
#                                 outside this list either way.
#   stop_update_failed            terminal only since #607 (2026-09-04) — both
#                                 attempts raised. Still excluded here (not a
#                                 vocabulary artifact): it nulls the pointer for
#                                 sync remediation, and if the naked state
#                                 PERSISTS, that is caught by the L1
#                                 naked-position invariant (already resets) —
#                                 counting it here too would double-reset the
#                                 same incident.
#   naked_position_detected       detection marker with an automated remediation
#                                 path attached (sync_positions Path C / adopt);
#                                 persistence again lands as an L1 breach.
#   partial_exit_aborted          shared type spanning benign aborts (dedup,
#                                 trade-not-found, replace rejected with old stop
#                                 confirmed LIVE) and re-protected under-coverage.
#   order_status_reconcile_failed per-order fetch error, retried next 15-min cycle.
#   stuck_pending_new_detected    entry order stalled pre-fill — no position/money
#                                 at risk yet; operator-decision alert, not a failure.

# BLOCKING task IDs extracted from v1-closeout-productization.md §4a (as of
# 2026-07-05); see module docstring for why this is hardcoded rather than
# regex-parsed live.
BLOCKING_TASK_IDS = frozenset({
    # verify-class
    347, 256, 405, 317, 150, 413, 276, 303,
    # small-build class (S-A=#421, S-B=#422, S-D=#423, S-E=#424; S-C folded into #378)
    421, 422, 378, 423, 424, 404, 412, 290, 195, 280, 420,
    # careful-path class (#184 + #261 RE-HOMED to #419 Phase-2 by operator 2026-07-24
    # at the v1.0 declaration — ruled not v1.0-blocking: #184's R1 stop-repair is live +
    # R2/R3 are propose-only; #261 is a scripts-folder reorg with no trading impact.)
    287, 417, 183,
})

_PLAN_TASK_RE = re.compile(r"^- #(\d+)\s*\|")


# ── Calendar helpers ─────────────────────────────────────────────────────────

def _is_trading_day(d: date) -> bool:
    """Holiday-aware (2026-07-06 /simplify reuse). The weekday check is the outer
    gate — reliable and dependency-free — because `get_market_status` FAILS OPEN
    to is_trading_day=True when `exchange_calendars` isn't installed (which would
    otherwise count weekends). On a weekday, consult the NYSE-calendar helper to
    exclude observed holidays (e.g. 2026-07-03 Jul-4-observed); if that module is
    unavailable, a weekday is assumed trading (same as the old weekday-only
    approximation, so no regression where the calendar is absent)."""
    if d.weekday() >= 5:
        return False
    try:
        from agents.market_intelligence.trading_calendar import get_market_status
        return get_market_status(d).is_trading_day
    except Exception:
        return True


def _trading_days(start: date, end: date) -> list[date]:
    """Trading days (holiday-aware) in [start, end] inclusive."""
    return [d for d in _calendar_days(start, end) if _is_trading_day(d)]


def _calendar_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _most_recent_sunday(d: date) -> date:
    offset = (d.weekday() - 6) % 7
    return d - timedelta(days=offset)


def _recent_sundays(anchor: date, count: int) -> list[date]:
    """`count` Sundays ending at (and including) anchor, ascending."""
    return [anchor - timedelta(weeks=(count - 1 - i)) for i in range(count)]


def _add_trading_days(start: date, n: int) -> date:
    d = start
    remaining = n
    while remaining > 0:
        d += timedelta(days=1)
        if _is_trading_day(d):
            remaining -= 1
    return d


def _fmt_date(d: date) -> str:
    return f"{d.month}/{d.day}"


def _fmt_reason(reason: str | None, d: date | None) -> str | None:
    if reason is None or d is None:
        return None
    return f"{reason} {_fmt_date(d)}"


def _streak_with_last_reset(
    days: list[date], reset_dates: dict[date, str]
) -> tuple[int, str | None, date | None]:
    """Walk `days` in order; the streak resets to 0 on any day present in
    `reset_dates` (value = the reason). Returns (final_streak, last_reset_
    reason, last_reset_date) — the reason/date of the MOST RECENT reset point
    found in the window (None if the streak never broke across the window)."""
    streak = 0
    last_reason: str | None = None
    last_date: date | None = None
    for d in days:
        if d in reset_dates:
            streak = 0
            last_reason = reset_dates[d]
            last_date = d
        else:
            streak += 1
    return streak, last_reason, last_date


# ── Pure per-clock computations ─────────────────────────────────────────────

def compute_fl1(
    l1_dates: set[date],
    repair_dates: set[date],
    start: date,
    end: date,
    failure_dates: dict[date, str] | None = None,
) -> dict:
    """FL-1 live-loop soak: consecutive trading days since `start` with zero
    L1 invariant breaches, zero manual trade-state repairs, AND zero terminal
    money-path failures (RED-2: `failure_dates` maps ET date → the
    SOAK_FAILURE_EVENT_TYPES event(s) that fired that day)."""
    days = _trading_days(start, end)
    failure_dates = failure_dates or {}
    reset_dates: dict[date, str] = {}
    for d in days:
        if d in l1_dates:
            reset_dates[d] = "L1 invariant breach"
        elif d in repair_dates:
            reset_dates[d] = "manual repair"
        elif d in failure_dates:
            reset_dates[d] = f"money-path failure: {failure_dates[d]}"
    n, reason, last_date = _streak_with_last_reset(days, reset_dates)
    return {"n": n, "target": FL1_TARGET, "reset_reason": _fmt_reason(reason, last_date)}


_WATCHDOG_TARGET_RE = re.compile(r"watchdog:\s*(\S+)\s+(?:DOWN|recovered)", re.IGNORECASE)
_SELFTEST_CONTAINER = "apollo-watchdog-selftest"
_TRANSIENT_RECOVERY_MIN = 10

# #442 (2026-08-08): infra/service_watchdog.sh's audit_event() calls for
# service_down/service_recovered now carry a structured `detail` JSON field —
# {"container": "<svc>", "state": "down"|"recovered"} — alongside the
# human-readable `summary` prose they always sent (see infra/ops_lib.sh's
# audit_event() + the two call sites in infra/service_watchdog.sh). FL-3 was
# recovering the container name by REGEX-PARSING that prose; if the wording
# ever drifted, the regex silently returned None and both the selftest
# exclusion and the transient-pairing below stopped matching — over-counting
# resets. `_watchdog_target` now reads `detail` FIRST and only falls back to
# the regex for rows written before this field existed. That fallback is
# GUARANTEED-ROWS-ONLY-BEFORE this date; it stays live (and LOUD — see the
# logger.warning below) purely to keep FL-3 working on history already in
# `mi_audit_log`. ⚠ Requires infra/service_watchdog.sh to actually be
# redeployed to the production host (it runs there via cron) — until that
# happens, EVERY row, including new ones, still lacks `detail` and hits the
# fallback. Once every row in FL-3's window carries `detail`, delete the
# fallback branch (and this constant) for real.
WATCHDOG_STRUCTURED_SINCE = date(2026, 8, 8)


def _parse_audit_detail(raw: object) -> dict | None:
    """`mi_audit_log.detail` -> dict, or None when it is absent/unparsable.

    ONE parser for this column, because it is documented as able to hold
    malformed rows and this file plus db.py had each grown their own — the
    copies had already drifted apart (a dropped isinstance guard, a different
    exception tuple). The column is TEXT today so asyncpg hands back a str,
    but the guard stays: it costs nothing and is the difference between a
    silent fallback and a correct read if it ever becomes JSONB.
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):   # JSONDecodeError subclasses ValueError
        return None
    return parsed if isinstance(parsed, dict) else None


def _watchdog_target(row: dict) -> str | None:
    """The container a watchdog service_down/service_recovered event is
    about. PRIMARY: `row['detail']`, the structured JSON object the watchdog
    writes directly (immune to prose rewording — #442). FALLBACK: regex over
    `row['summary']` (e.g. 'watchdog: apollo-market DOWN — ...') for rows
    that predate the structured field — see WATCHDOG_STRUCTURED_SINCE."""
    parsed = _parse_audit_detail(row.get("detail"))
    if parsed and parsed.get("container"):
        return parsed["container"]
    # No usable structured field on this row — legacy history, or the
    # watchdog script hasn't been redeployed yet. Fall back to the old
    # regex, but LOUDLY: this is the exact silent-failure shape #442 closes,
    # so every hit here (whether or not the regex itself still resolves) is
    # logged rather than swallowed.
    summary = row.get("summary")
    m = _WATCHDOG_TARGET_RE.search(summary or "")
    target = m.group(1) if m else None
    logger.warning(
        "v1_closeout_status: watchdog audit row has no structured 'detail' "
        "field (#442 fallback to summary-regex parsing); resolved target=%r "
        "from summary=%r — expected only for rows before %s or an "
        "undeployed watchdog script",
        target, summary, WATCHDOG_STRUCTURED_SINCE,
    )
    return target


def real_service_down_dates(rows: list[dict], transient_min: int = _TRANSIENT_RECOVERY_MIN) -> set:
    """From service_down / service_recovered rows (each {event_type, ts, summary,
    detail, d}), return the ET dates that had a REAL sustained outage — the only
    ones that should reset FL-3's ops-autonomy streak.

    Refinement (operator-signed 2026-07-07): FL-3 measures UNATTENDED-ops failures, so
    two service_down classes are NOT real outages and are excluded:
      1. the watchdog's own synthetic self-test container (`apollo-watchdog-selftest`) —
         it is intentionally 'down', a test of the detector, not a service; and
      2. a down that `service_recovered` for the SAME container within `transient_min`
         minutes — a planned deploy/restart blip, not an autonomy failure.
    Anything else (no recovery, or recovery beyond the window) counts as a real reset.
    Container identity comes from `_watchdog_target` (structured `detail` field first,
    regex-on-`summary` fallback for pre-#442 history — see that function)."""
    downs = [r for r in rows if r.get("event_type") == "service_down"]
    recovers = [r for r in rows if r.get("event_type") == "service_recovered"]
    # Resolve each row's target ONCE up front (not inside the O(downs*recovers)
    # pairing loop below) — a legacy row with no `detail` logs a warning inside
    # _watchdog_target, and re-resolving the same recover row once per down row
    # would multiply that warning by len(downs) for no benefit.
    recover_targets = [(r, _watchdog_target(r)) for r in recovers]
    real: set = set()
    for d in downs:
        target = _watchdog_target(d)
        if target == _SELFTEST_CONTAINER:
            continue
        t = d.get("ts")
        transient = t is not None and any(
            rt == target
            and r.get("ts") is not None
            and r["ts"] >= t
            and (r["ts"] - t).total_seconds() <= transient_min * 60
            for r, rt in recover_targets
        )
        if not transient and d.get("d") is not None:
            real.add(d["d"])
    return real


def compute_fl3(rows: list[dict], start: date, end: date) -> dict:
    """FL-3 ops autonomy: consecutive nights with backup_restore_check_ok AND
    watchdog_heartbeat AND no REAL service_down. `rows` = [{event_type, d}, ...]
    already ET-date-bucketed (see gather_status's SQL) — the service_down rows here
    are only the REAL sustained outages (gather_status pre-filters selftest/transient
    downs via `real_service_down_dates`, the 2026-07-07 operator-signed refinement)."""
    by_date: dict[date, set[str]] = {}
    for r in rows:
        by_date.setdefault(r["d"], set()).add(r["event_type"])

    if end < start:
        return {"n": 0, "target": FL3_TARGET, "reset_reason": None}

    nights = _calendar_days(start, end)
    reset_dates: dict[date, str] = {}
    for d in nights:
        types = by_date.get(d, set())
        if "service_down" in types:
            reset_dates[d] = "service_down fired"
        elif "backup_restore_check_ok" not in types:
            reset_dates[d] = "backup-check missing"
        elif "watchdog_heartbeat" not in types:
            reset_dates[d] = "watchdog heartbeat missing"
    n, reason, last_date = _streak_with_last_reset(nights, reset_dates)
    return {"n": n, "target": FL3_TARGET, "reset_reason": _fmt_reason(reason, last_date)}


def compute_fl4(
    drift_dates: set[date],
    start: date,
    end: date,
    ingest_mode: str = "off",
    ingest_promoted_on: date | None = None,
) -> dict:
    """FL-4 mirror completeness: consecutive trading days with zero
    coverage_drift_alerted (D1/D2-HIGH) rows, credited ONLY while the #184b
    broker-order ingest is PROMOTED to live (`ingest_mode` in
    INGEST_LIVE_MODES). YELLOW-3 meter honesty (2026-07-12):
      - mode off/dry_run (or unrecognized) → n=0; `gate` names the mode so the
        rendered line can't read green while the ingest is dark;
      - promoted but flip date unknown → n=0, loud (fix the toggle row) —
        never guess a start date, that re-opens the over-credit bug;
      - promoted → quiet days count from the first trading day STRICTLY AFTER
        `ingest_promoted_on` (the flip day itself is a mixed-mode day: cycles
        before the flip ran unpromoted).
    Defaults are FAIL-CLOSED (off/None) — a call site that forgets the wiring
    under-reads, never over-reads. Extra keys vs the other clocks: `ingest_mode`
    (telemetry) + `gate` (compact render suffix; None when counting normally)."""
    base = {"target": FL4_TARGET, "ingest_mode": ingest_mode, "gate": None}
    if ingest_mode not in INGEST_LIVE_MODES:
        return {**base, "n": 0, "gate": f"ingest {ingest_mode}",
                "reset_reason": (f"ingest {ingest_mode} — quiet days count only "
                                 f"after live_r1 promotion")}
    if ingest_promoted_on is None:
        return {**base, "n": 0, "gate": "promo date unknown",
                "reset_reason": ("ingest live but promotion date unknown — set "
                                 "mi_safeguard_state.last_transition_at")}
    days = _trading_days(max(start, ingest_promoted_on + timedelta(days=1)), end)
    reset_dates = {d: "coverage-drift D1/D2-HIGH" for d in days if d in drift_dates}
    n, reason, last_date = _streak_with_last_reset(days, reset_dates)
    return {**base, "n": n, "reset_reason": _fmt_reason(reason, last_date)}


def compute_fl8(review_sundays: set[date], today: date) -> dict:
    """FL-8 learning loop: consecutive Sundays the weekly review ran (a row
    exists in mi_system_reviews for window_days=7)."""
    anchor = _most_recent_sunday(today)
    window = _recent_sundays(anchor, FL8_TARGET + 8)  # buffer so a real streak isn't truncated
    reset_dates = {s: "weekly review missed" for s in window if s not in review_sundays}
    n, reason, last_date = _streak_with_last_reset(window, reset_dates)
    return {"n": n, "target": FL8_TARGET, "reset_reason": _fmt_reason(reason, last_date)}


def parse_plan_open_ids(text: str) -> set[int]:
    """Every `- #<id> | ...` line in PLAN.md is an OPEN task (closed tasks are
    removed from the file entirely — see scripts/check_plan.py's schema)."""
    ids = set()
    for line in text.splitlines():
        m = _PLAN_TASK_RE.match(line)
        if m:
            ids.add(int(m.group(1)))
    return ids


def compute_blocking_open(open_ids: set[int]) -> int:
    return len(BLOCKING_TASK_IDS & open_ids)


def compute_declaration_estimate(today: date, fl1_n: int, fl3_n: int, fl4_n: int, fl8_n: int) -> date:
    """Rough date estimate: the LATEST of the 4 clocks' own naive projections
    (each clock's own remaining-count times its own day-unit). Not a promise —
    a driving-surface estimate, per the build card."""
    candidates = [
        _add_trading_days(today, max(0, FL1_TARGET - fl1_n)),
        today + timedelta(days=max(0, FL3_TARGET - fl3_n)),
        _add_trading_days(today, max(0, FL4_TARGET - fl4_n)),
        today + timedelta(days=7 * max(0, FL8_TARGET - fl8_n)),
    ]
    return max(candidates)


# ── Reset detection (pure, snapshot-diff) ───────────────────────────────────

def detect_resets(prior: dict | None, current: dict) -> list[dict]:
    """Compare the prior persisted snapshot's FL counters to this run's. A DROP
    in FL-1/FL-3/FL-4/FL-8's count since the last run means that clock RESET
    since we last looked (each counter is monotonic-non-decreasing except on a
    genuine reset event). BLOCKING-open-count is deliberately excluded from
    reset detection — it dropping is progress (a task closed), not a reset;
    it rising is scope growth, not a driving-surface alarm."""
    if prior is None:
        return []
    resets = []
    for key, label in (("fl1", "FL-1"), ("fl3", "FL-3"), ("fl4", "FL-4"), ("fl8", "FL-8")):
        p = (prior.get(key) or {}).get("n")
        c = (current.get(key) or {}).get("n")
        if p is not None and c is not None and c < p:
            reason = (current.get(key) or {}).get("reset_reason") or "streak reset (see mi_audit_log)"
            resets.append({"clock": label, "reason": reason})
    return resets


def _md_safe(text: str) -> str:
    """Neutralize legacy-Markdown entity chars in DYNAMIC tokens bound for the
    brief. A single bare `_` (e.g. the FL-4 gate 'ingest dry_run', 2026-07-16)
    flips the entity parity of the WHOLE Telegram chunk: it pairs with the next
    innocent `_` (the RS footer's italics opener) and the chunk 400s at an
    offset thousands of bytes away — the brief then falls back to plain text.
    Hyphens read identically to the operator and can't open an entity. All
    INGEST_MODES (dry_run, live_r1/r2/r3) carry `_`, so this bites on every
    future mode flip too, not just dry_run. (Not briefing._md_escape: briefing
    imports THIS module — circular — and 'dry-run' reads cleaner than
    'dry\\_run' in the one-line HUD context.)"""
    return str(text).replace("_", "-").replace("*", "·").replace("`", "'")


def render_line(status: dict) -> str:
    """Pure formatting: one compact line for the evening briefing."""
    fl1, fl3, fl4, fl8 = status["fl1"], status["fl3"], status["fl4"], status["fl8"]

    def _c(clock: dict) -> str:
        # Cap the displayed numerator at the target so a clock past its bar reads
        # e.g. "4/4 ✓" not "11/4" (a long-running streak overshoots the target).
        n, t = clock["n"], clock["target"]
        return f"{t}/{t} ✓" if n >= t else f"{n}/{t}"

    blocking = status.get("blocking_open")
    blocking_s = str(blocking) if blocking is not None else "?"
    # FL-4 carries a promotion-gate suffix (YELLOW-3): while the #184b ingest is
    # dark/dry-run the count is pinned at 0 and the line SAYS WHY — "FL-4 0/5
    # (ingest dry-run)" — instead of silently reading like a running clock.
    fl4_gate = f" ({_md_safe(fl4['gate'])})" if fl4.get("gate") else ""
    base = (
        f"FL-1 {_c(fl1)} · FL-3 {_c(fl3)} · FL-4 {_c(fl4)}{fl4_gate} · FL-8 {_c(fl8)} · "
        f"blocking {blocking_s} open · decl ~{status['decl_estimate']}"
    )
    resets = status.get("resets") or []
    if resets:
        reasons = "; ".join(
            f"{_md_safe(r['clock'])} reset ({_md_safe(r['reason'])})" for r in resets)
        return f"\U0001F534 v1.0: {base} — {reasons}"
    return f"\U0001F3C1 v1.0: {base}"


# ── DB-sourced gather (the only I/O) ────────────────────────────────────────

async def gather_status(conn, today: date | None = None) -> dict:
    """Compute all 4 FL clocks + BLOCKING count from DB ground truth (NOT
    module state — every field is re-queried each call, restart-safe)."""
    from shared.dates import et_today, last_trading_day

    today = today or et_today()
    end_trading = last_trading_day(today)

    l1_rows = await conn.fetch(
        """
        SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d
        FROM mi_audit_log
        WHERE event_type = 'anomaly_detected'
          AND detail LIKE '%"level": 1%'
          AND created_at >= $1
        """,
        FL1_SOAK_START,
    )
    l1_dates = {r["d"] for r in l1_rows}

    repair_rows = await conn.fetch(
        """
        SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d
        FROM mi_audit_log
        WHERE event_type = ANY($1::text[])
          AND created_at >= $2
        """,
        MANUAL_REPAIR_EVENT_TYPES, FL1_SOAK_START,
    )
    repair_dates = {r["d"] for r in repair_rows}

    # RED-2 (2026-07-12): terminal money-path failure days also reset the soak.
    # Keep event_type per date so the reset reason names WHAT failed.
    failure_rows = await conn.fetch(
        """
        SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d,
               event_type
        FROM mi_audit_log
        WHERE event_type = ANY($1::text[])
          AND created_at >= $2
        """,
        SOAK_FAILURE_EVENT_TYPES, FL1_SOAK_START,
    )
    _failures_by_day: dict[date, set[str]] = {}
    for r in failure_rows:
        _failures_by_day.setdefault(r["d"], set()).add(r["event_type"])
    failure_dates = {d: ", ".join(sorted(evts)) for d, evts in _failures_by_day.items()}

    fl1 = compute_fl1(
        l1_dates, repair_dates, FL1_SOAK_START, end_trading,
        failure_dates=failure_dates,
    )

    ops_rows = await conn.fetch(
        """
        SELECT event_type, summary, detail, created_at AS ts,
               (created_at AT TIME ZONE 'America/New_York')::date AS d
        FROM mi_audit_log
        WHERE event_type = ANY($1::text[])
          AND created_at >= $2
        """,
        ["backup_restore_check_ok", "watchdog_heartbeat", "service_down", "service_recovered"],
        FL3_START,
    )
    # `detail` added #442 (was event_type/summary/ts/d only) — real_service_down_dates
    # reads it to resolve the container without regex-parsing `summary` prose.
    ops_rows = [dict(r) for r in ops_rows]
    # FL-3 refinement (operator 2026-07-07): only REAL sustained outages reset the streak —
    # selftest/transient-deploy-blip downs are filtered out (see real_service_down_dates).
    # compute_fl3 reads only event_type + d, so one filter over the original rows suffices:
    # keep the two heartbeat types, plus service_down ONLY on a real-outage date.
    real_down = real_service_down_dates(ops_rows)
    fl3_rows = [
        r for r in ops_rows
        if r["event_type"] in ("backup_restore_check_ok", "watchdog_heartbeat")
        or (r["event_type"] == "service_down" and r["d"] in real_down)
    ]
    fl3 = compute_fl3(fl3_rows, FL3_START, today - timedelta(days=1))

    drift_rows = await conn.fetch(
        """
        SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d
        FROM mi_audit_log
        WHERE event_type = 'coverage_drift_alerted'
          AND created_at >= $1
        """,
        FL4_START,
    )
    drift_dates = {r["d"] for r in drift_rows}

    # FL-4 promotion gate (YELLOW-3): READ the same toggle row order_ingest.
    # get_ingest_mode() resolves (its precedence: DB state → env → off, fail-
    # closed). promoted_on = the row's LAST flip timestamp as an ET date —
    # GREATEST(last_transition_at, updated_at) because the review's documented
    # dry_run→live_r1 UPDATE recipe bumps only updated_at; taking the latest of
    # the two can only UNDER-credit (restart the clock on a later flip), never
    # over-credit pre-promotion days. Postgres GREATEST ignores NULLs (NULL only
    # when both are — the loud "promo date unknown" path in compute_fl4).
    ingest_row = await conn.fetchrow(
        """
        SELECT state,
               (GREATEST(last_transition_at, updated_at)
                  AT TIME ZONE 'America/New_York')::date AS promoted_on
        FROM mi_safeguard_state
        WHERE safeguard = $1 AND account_mode = 'global'
        """,
        INGEST_SAFEGUARD,
    )
    if ingest_row is not None:
        raw_mode = ingest_row["state"]
        ingest_promoted_on = ingest_row["promoted_on"]
    else:
        raw_mode = os.environ.get("BROKER_ORDER_INGEST_MODE", "off").lower()
        ingest_promoted_on = None  # env-only promotion has no flip timestamp → loud-unknown path
    ingest_mode = raw_mode if raw_mode in INGEST_MODES else "off"  # unrecognized → off (fail closed)

    fl4 = compute_fl4(drift_dates, FL4_START, end_trading,
                      ingest_mode=ingest_mode, ingest_promoted_on=ingest_promoted_on)

    review_rows = await conn.fetch(
        "SELECT DISTINCT review_date FROM mi_system_reviews WHERE window_days = 7"
    )
    review_sundays = {r["review_date"] for r in review_rows}
    fl8 = compute_fl8(review_sundays, today)

    try:
        plan_text = PLAN_MD.read_text(encoding="utf-8")
        blocking_open = compute_blocking_open(parse_plan_open_ids(plan_text))
    except OSError as e:
        logger.warning(f"v1_closeout_status: PLAN.md read failed: {e}")
        blocking_open = None

    decl = compute_declaration_estimate(today, fl1["n"], fl3["n"], fl4["n"], fl8["n"])

    return {
        "today": today.isoformat(),
        "fl1": fl1, "fl3": fl3, "fl4": fl4, "fl8": fl8,
        "blocking_open": blocking_open,
        "decl_estimate": _fmt_date(decl),
    }


async def _fetch_prior_snapshot(conn) -> dict | None:
    row = await conn.fetchrow(
        "SELECT detail FROM mi_audit_log WHERE event_type = $1 ORDER BY created_at DESC LIMIT 1",
        SNAPSHOT_EVENT,
    )
    if not row:
        return None
    parsed = _parse_audit_detail(row["detail"])
    if parsed is None:
        logger.warning("v1_closeout_status: prior snapshot detail absent or unparsable")
    return parsed


async def _persist_snapshot(conn, status: dict) -> None:
    # Reuse the caller's open conn (2026-07-06 /simplify efficiency) rather than
    # log_audit_event's own get_pool()+acquire() — the caller already holds one,
    # so this avoided a second concurrent pool checkout + round trip.
    detail = json.dumps({
        "fl1": {"n": status["fl1"]["n"]},
        "fl3": {"n": status["fl3"]["n"]},
        "fl4": {"n": status["fl4"]["n"]},
        "fl8": {"n": status["fl8"]["n"]},
        "blocking_open": status["blocking_open"],
        "as_of": status["today"],
    }, default=str)
    await conn.execute(
        "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ($1, $2, $3)",
        SNAPSHOT_EVENT, f"v1.0 closeout snapshot {status['today']}", detail,
    )


async def check_and_snapshot_resets(conn, status: dict) -> list[dict]:
    """Fetch the prior persisted snapshot, diff against `status`, persist a
    fresh snapshot for next time. Returns the reset list (possibly empty)."""
    prior = await _fetch_prior_snapshot(conn)
    resets = detect_resets(prior, status)
    await _persist_snapshot(conn, status)
    return resets


async def compute_and_render(conn, today: date | None = None) -> str:
    """Top-level entry point for the evening-briefing wire: gather + reset-
    check-and-snapshot + render, in one call."""
    from shared.dates import et_today

    today = today or et_today()
    status = await gather_status(conn, today)
    status["resets"] = await check_and_snapshot_resets(conn, status)
    return render_line(status)


# ── CLI (live smoke) ─────────────────────────────────────────────────────────

async def _run_live(today: date | None) -> str:
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await compute_and_render(conn, today=today)


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--today", type=str, default=None, help="Override today's date (YYYY-MM-DD).")
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else None
    print(asyncio.run(_run_live(today)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
