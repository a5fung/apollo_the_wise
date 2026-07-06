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
  - FL-3 "night" is bucketed by ET calendar date. Because `backup_restore_check`
    cron fires ~23:30 ET (03:30 UTC, the NEXT UTC day) and the evening briefing
    fires at 20:00 ET, TODAY's own backup-check has not run yet when the
    briefing does — so the walk's end boundary is YESTERDAY (the most recently
    fully-completed ops night), not today.
  - FL-4 "day" = trading day; by 20:00 ET the last 15-min reconcile cycle
    (ends 16:45 ET) has already run, so TODAY can be included once it's a
    trading day. Anchored at 2026-07-06 (detector built 7/5, but 7/5 was a
    Saturday — first live cycles Monday 7/6 per the roadmap doc).
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
import re
import sys
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
PLAN_MD = REPO / "PLAN.md"

# ── FL clock constants ──────────────────────────────────────────────────────
FL1_SOAK_START = date(2026, 6, 30)
FL1_TARGET = 10

FL3_START = date(2026, 7, 5)
FL3_TARGET = 7

FL4_START = date(2026, 7, 6)  # first live coverage-drift reconcile cycle (Monday)
FL4_TARGET = 5

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

# BLOCKING task IDs extracted from v1-closeout-productization.md §4a (as of
# 2026-07-05); see module docstring for why this is hardcoded rather than
# regex-parsed live.
BLOCKING_TASK_IDS = frozenset({
    # verify-class
    347, 256, 405, 317, 150, 413, 276, 303,
    # small-build class (S-A=#421, S-B=#422, S-D=#423, S-E=#424; S-C folded into #378)
    421, 422, 378, 423, 424, 404, 412, 290, 195, 280, 420,
    # careful-path class
    184, 287, 261, 417, 183,
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

def compute_fl1(l1_dates: set[date], repair_dates: set[date], start: date, end: date) -> dict:
    """FL-1 live-loop soak: consecutive trading days since `start` with zero
    L1 invariant breaches AND zero manual trade-state repairs."""
    days = _trading_days(start, end)
    reset_dates: dict[date, str] = {}
    for d in days:
        if d in l1_dates:
            reset_dates[d] = "L1 invariant breach"
        elif d in repair_dates:
            reset_dates[d] = "manual repair"
    n, reason, last_date = _streak_with_last_reset(days, reset_dates)
    return {"n": n, "target": FL1_TARGET, "reset_reason": _fmt_reason(reason, last_date)}


def compute_fl3(rows: list[dict], start: date, end: date) -> dict:
    """FL-3 ops autonomy: consecutive nights with backup_restore_check_ok AND
    watchdog_heartbeat AND no service_down. `rows` = [{event_type, d}, ...]
    already ET-date-bucketed (see gather_status's SQL)."""
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


def compute_fl4(drift_dates: set[date], start: date, end: date) -> dict:
    """FL-4 mirror completeness: consecutive trading days with zero
    coverage_drift_alerted (D1/D2-HIGH) rows."""
    days = _trading_days(start, end)
    reset_dates = {d: "coverage-drift D1/D2-HIGH" for d in days if d in drift_dates}
    n, reason, last_date = _streak_with_last_reset(days, reset_dates)
    return {"n": n, "target": FL4_TARGET, "reset_reason": _fmt_reason(reason, last_date)}


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
    base = (
        f"FL-1 {_c(fl1)} · FL-3 {_c(fl3)} · FL-4 {_c(fl4)} · FL-8 {_c(fl8)} · "
        f"blocking {blocking_s} open · decl ~{status['decl_estimate']}"
    )
    resets = status.get("resets") or []
    if resets:
        reasons = "; ".join(f"{r['clock']} reset ({r['reason']})" for r in resets)
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
    fl1 = compute_fl1(l1_dates, repair_dates, FL1_SOAK_START, end_trading)

    ops_rows = await conn.fetch(
        """
        SELECT event_type, (created_at AT TIME ZONE 'America/New_York')::date AS d
        FROM mi_audit_log
        WHERE event_type = ANY($1::text[])
          AND created_at >= $2
        """,
        ["backup_restore_check_ok", "watchdog_heartbeat", "service_down"], FL3_START,
    )
    fl3 = compute_fl3([dict(r) for r in ops_rows], FL3_START, today - timedelta(days=1))

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
    fl4 = compute_fl4(drift_dates, FL4_START, end_trading)

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
    try:
        raw = row["detail"]
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"v1_closeout_status: prior snapshot unparsable: {e}")
        return None


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
