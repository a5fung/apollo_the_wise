"""
Shared invariant library for L1 hard-breach checks.

Single source of truth for invariants used by both
`scripts/readiness_check.py` (CLI cutover gate) and
`agents/market_intelligence/system_audit.py` (scheduled scanner).

Each invariant is an async function taking an asyncpg connection plus any
window kwargs and returning a tuple `(passed: bool, detail: dict)`. The
detail dict carries enough to populate an L1 Telegram alert body:

    {
      "name": str,           # stable invariant key (constant)
      "count": int,          # number of breaching rows
      "summary": str,        # one-line human description
      "offending": list,     # up to N sample rows for the body
      "drill_sql": str,      # SQL the user can paste to inspect
      "code_pointers": list, # file::function references for the user
    }

`passed=False` means the invariant breached. The audit caller decides
whether to Telegram (via system_audit) or print to stdout (readiness_check).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# ── Invariant key constants (stable across system_audit + readiness_check) ─

INV_NAKED_POSITION = "naked_position"
INV_REASON_COVERAGE = "reason_coverage_hole"
INV_AUDIT_ERROR_WINDOW = "silent_audit_error_window"
INV_REGIME_STUCK_CRISIS = "regime_stuck_crisis"
INV_FEED_HEALTH_24H = "feed_health_24h"
INV_STUCK_FILLED_ROW = "stuck_filled_row"
INV_ZOMBIE_THEME = "zombie_theme"
INV_STALE_ORDER_PLACED = "stale_order_placed"
INV_COOLDOWN_SURGE = "cooldown_surge"
INV_HIGH_NO_TERMINAL = "high_ep_no_terminal_state"
INV_JOB_NO_SHOW = "job_no_show"

# ── Existing 6 (from readiness_check.py) ───────────────────────────────────


async def check_naked_position(conn) -> tuple[bool, dict]:
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, stop_order_id, filled_at
        FROM mi_live_trades
        WHERE status = 'filled'
          AND stop_order_id IS NULL
          AND (filled_at IS NULL OR filled_at < NOW() - INTERVAL '60 seconds')
        ORDER BY alert_date DESC
        """
    )
    return (len(rows) == 0, {
        "name": INV_NAKED_POSITION,
        "count": len(rows),
        "summary": f"{len(rows)} filled rows without stop_order_id past 60s grace",
        "offending": [
            f"{r['ticker']} {r['alert_date']} filled_at={r['filled_at']}"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT ticker, alert_date, status, stop_order_id, filled_at\n"
            "FROM mi_live_trades\n"
            "WHERE status='filled' AND stop_order_id IS NULL\n"
            "  AND filled_at < NOW() - INTERVAL '60 seconds';"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/alpaca_client.py::extract_stop_leg_id",
            "agents/market_intelligence/broker/order_manager.py::submit_entry",
            "agents/market_intelligence/broker/trade_stream.py::_process_entry_fill",
        ],
    })


async def check_reason_coverage(conn, *, since: date) -> tuple[bool, dict]:
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, skip_reason
        FROM mi_live_trades
        WHERE alert_date >= $1
          AND status IS NULL
          AND skip_reason IS NULL
        ORDER BY alert_date DESC
        """,
        since,
    )
    return (len(rows) == 0, {
        "name": INV_REASON_COVERAGE,
        "count": len(rows),
        "summary": f"{len(rows)} silent-drop rows (status NULL AND skip_reason NULL)",
        "offending": [f"{r['ticker']} {r['alert_date']}" for r in rows[:10]],
        "drill_sql": (
            f"SELECT ticker, alert_date FROM mi_live_trades\n"
            f"WHERE alert_date >= '{since}' AND status IS NULL AND skip_reason IS NULL;"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/entry_pipeline.py::submit_trade_entry",
            "agents/market_intelligence/broker/skip_reasons.py",
        ],
    })


async def check_audit_error_window(conn, *, since: datetime) -> tuple[bool, dict]:
    rows = await conn.fetch(
        """
        SELECT event_type, COUNT(*) AS n
        FROM mi_audit_log
        WHERE event_type LIKE '%_error'
          AND created_at >= $1
        GROUP BY event_type
        ORDER BY n DESC
        """,
        since,
    )
    total = sum(int(r["n"]) for r in rows)
    return (total == 0, {
        "name": INV_AUDIT_ERROR_WINDOW,
        "count": total,
        "summary": f"{total} '*_error' events since {since:%Y-%m-%d %H:%M}" if total else "clean",
        "offending": [f"{r['event_type']}: {r['n']}" for r in rows[:10]],
        "drill_sql": (
            f"SELECT event_type, summary, detail, created_at FROM mi_audit_log\n"
            f"WHERE event_type LIKE '%_error' AND created_at >= '{since.isoformat()}'\n"
            f"ORDER BY created_at DESC LIMIT 50;"
        ),
        "code_pointers": [],
    })


async def check_regime_stuck_crisis(conn, *, days: int = 30) -> tuple[bool, dict]:
    """Crisis regime continuously for more than `days` calendar days."""
    rows = await conn.fetch(
        """
        SELECT regime_date, regime
        FROM mi_market_regime
        WHERE regime_date >= CURRENT_DATE - ($1 || ' days')::INTERVAL
        ORDER BY regime_date DESC
        """,
        str(days + 5),  # small buffer to detect "all crisis in window"
    )
    if not rows:
        return (True, {
            "name": INV_REGIME_STUCK_CRISIS,
            "count": 0,
            "summary": "no regime rows in window",
            "offending": [],
            "drill_sql": "",
            "code_pointers": [],
        })
    # Count consecutive Crisis days from most recent backwards.
    streak = 0
    for r in rows:
        if (r["regime"] or "").lower() == "crisis":
            streak += 1
        else:
            break
    breached = streak > days
    latest_regime = (rows[0]["regime"] or "Unknown")
    return (not breached, {
        "name": INV_REGIME_STUCK_CRISIS,
        "count": streak,
        "latest_regime": latest_regime,
        "latest_regime_date": str(rows[0]["regime_date"]),
        "summary": f"{streak}-day Crisis streak (latest {rows[0]['regime_date']})",
        "offending": [
            f"{r['regime_date']} {r['regime']}" for r in rows[:5]
        ],
        "drill_sql": (
            "SELECT regime_date, regime FROM mi_market_regime\n"
            "ORDER BY regime_date DESC LIMIT 35;"
        ),
        "code_pointers": [
            "agents/market_intelligence/regime_engine.py",
        ],
    })


async def check_feed_health_24h(conn) -> tuple[bool, dict]:
    row = await conn.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE event_type = 'orb_subscribe_failed') AS subscribe_fail,
          COUNT(*) FILTER (WHERE event_type = 'bar_stream_disconnect') AS disconnect
        FROM mi_audit_log
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        """
    )
    fails = int(row["subscribe_fail"] or 0)
    drops = int(row["disconnect"] or 0)
    return (fails == 0, {
        "name": INV_FEED_HEALTH_24H,
        "count": fails,
        "summary": f"{fails} subscribe-fail · {drops} disconnect (24h)",
        "offending": [],
        "drill_sql": (
            "SELECT event_type, summary, detail, created_at FROM mi_audit_log\n"
            "WHERE event_type IN ('orb_subscribe_failed','bar_stream_disconnect')\n"
            "  AND created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC;"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/bar_stream.py",
        ],
    })


# ── New 5 (April incidents) ────────────────────────────────────────────────


async def check_stuck_filled_row(conn) -> tuple[bool, dict]:
    """Filled rows still 'filled' with remaining shares 24h+ later — INTC OTO bug class."""
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, filled_at, remaining_shares,
               stop_order_id, total_pnl
        FROM mi_live_trades
        WHERE status = 'filled'
          AND filled_at < NOW() - INTERVAL '24 hours'
          AND COALESCE(remaining_shares, 0) > 0
        ORDER BY filled_at DESC
        """
    )
    return (len(rows) == 0, {
        "name": INV_STUCK_FILLED_ROW,
        "count": len(rows),
        "summary": f"{len(rows)} 'filled' rows with shares > 24h old",
        "offending": [
            f"{r['ticker']} {r['alert_date']} remaining={r['remaining_shares']} "
            f"stop_order_id={r['stop_order_id']}"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT id, ticker, alert_date, status, filled_at, stop_order_id,\n"
            "       remaining_shares, total_pnl FROM mi_live_trades\n"
            "WHERE status='filled' AND filled_at < NOW() - INTERVAL '24 hours'\n"
            "  AND COALESCE(remaining_shares, 0) > 0;"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/alpaca_client.py::extract_stop_leg_id",
            "agents/market_intelligence/broker/trade_stream.py::_process_stop_fill",
        ],
    })


async def check_zombie_theme(conn, *, stale_after_days: int = 7) -> tuple[bool, dict]:
    """Theme name last seen > N days but never marked Retired — 135-cooldown class."""
    rows = await conn.fetch(
        """
        SELECT name, MAX(theme_date) AS last_seen,
               (CURRENT_DATE - MAX(theme_date)) AS days_stale
        FROM mi_themes
        WHERE stage != 'Retired'
        GROUP BY name
        HAVING (CURRENT_DATE - MAX(theme_date)) > $1
        ORDER BY days_stale DESC
        """,
        stale_after_days,
    )
    return (len(rows) == 0, {
        "name": INV_ZOMBIE_THEME,
        "count": len(rows),
        "summary": f"{len(rows)} themes last seen > {stale_after_days}d but not Retired",
        "offending": [
            f"{r['name']} last_seen={r['last_seen']} ({r['days_stale']}d stale)"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT name, MAX(theme_date) AS last_seen,\n"
            "       (CURRENT_DATE - MAX(theme_date)) AS days_stale\n"
            "FROM mi_themes WHERE stage != 'Retired'\n"
            f"GROUP BY name HAVING (CURRENT_DATE - MAX(theme_date)) > {stale_after_days}\n"
            "ORDER BY days_stale DESC;"
        ),
        "code_pointers": [
            "agents/market_intelligence/db.py::get_active_themes",
            "agents/market_intelligence/theme_engine.py::_save_themes",
        ],
    })


async def check_stale_order_placed(conn) -> tuple[bool, dict]:
    """status='order_placed' from a prior trading day — CHE late-entry class."""
    rows = await conn.fetch(
        """
        SELECT ticker, alert_date, status, entry_order_id, created_at
        FROM mi_live_trades
        WHERE status = 'order_placed'
          AND alert_date < CURRENT_DATE
        ORDER BY alert_date DESC
        """
    )
    return (len(rows) == 0, {
        "name": INV_STALE_ORDER_PLACED,
        "count": len(rows),
        "summary": f"{len(rows)} 'order_placed' rows from prior trading days",
        "offending": [
            f"{r['ticker']} {r['alert_date']} order={r['entry_order_id']}"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT ticker, alert_date, status, entry_order_id\n"
            "FROM mi_live_trades\n"
            "WHERE status='order_placed' AND alert_date < CURRENT_DATE;"
        ),
        "code_pointers": [
            "agents/market_intelligence/scheduler.py::_orb_window_cleanup_job",
            "agents/market_intelligence/broker/order_manager.py::cancel_unfilled_entries",
        ],
    })


async def check_cooldown_surge(conn, *, multiplier: float = 5.0) -> tuple[bool, dict]:
    """Today's cooldowns added > multiplier × 30-day median — 135-cooldown class."""
    today_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM mi_validation_cooldowns
        WHERE removed_at::date = CURRENT_DATE
        """
    )
    today_n = int(today_row["n"] or 0)

    # Trimmed 30-day median (drop top 10% / bottom 10%).
    history_rows = await conn.fetch(
        """
        SELECT removed_at::date AS d, COUNT(*) AS n
        FROM mi_validation_cooldowns
        WHERE removed_at::date BETWEEN CURRENT_DATE - INTERVAL '30 days' AND CURRENT_DATE - INTERVAL '1 day'
        GROUP BY 1
        ORDER BY 1
        """
    )
    counts = sorted(int(r["n"]) for r in history_rows)
    if len(counts) >= 5:
        trim = len(counts) // 10
        kept = counts[trim: len(counts) - trim] if trim else counts
        median = kept[len(kept) // 2] if kept else 0
    else:
        median = max(counts) if counts else 0
    threshold = max(int(multiplier * median), 5)  # min 5 to avoid 0-baseline false positives
    breached = today_n > threshold
    return (not breached, {
        "name": INV_COOLDOWN_SURGE,
        "count": today_n,
        "summary": f"{today_n} cooldowns today vs ~{median} median (threshold {threshold})",
        "offending": [],
        "drill_sql": (
            "SELECT theme_name, COUNT(*) FROM mi_validation_cooldowns\n"
            "WHERE removed_at::date = CURRENT_DATE\n"
            "GROUP BY theme_name ORDER BY 2 DESC LIMIT 15;"
        ),
        "code_pointers": [
            "agents/market_intelligence/db.py::get_active_themes",
            "agents/market_intelligence/theme_engine.py::_validate_theme_membership",
        ],
    })


async def check_high_no_terminal(conn) -> tuple[bool, dict]:
    """HIGH EP today with no matching live_trades row of any status — URI class.

    Only meaningful at 16:15 ET (after EOD cleanup). The 9:31 cron + bar stream
    should have written a row — entry, skip, or block — for every HIGH alert
    by then.
    """
    rows = await conn.fetch(
        """
        SELECT a.ticker, a.alert_date, a.score_tier, a.ep_score, a.gap_pct
        FROM mi_ep_alerts a
        LEFT JOIN mi_live_trades lt
          ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
        WHERE a.alert_date = CURRENT_DATE
          AND a.score_tier = 'HIGH'
          AND lt.id IS NULL
        ORDER BY a.ep_score DESC
        """
    )
    return (len(rows) == 0, {
        "name": INV_HIGH_NO_TERMINAL,
        "count": len(rows),
        "summary": f"{len(rows)} HIGH EP alerts today with no live_trades row at all",
        "offending": [
            f"{r['ticker']} score={r['ep_score']:.1f} gap={r['gap_pct']:.1f}%"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT a.ticker, a.alert_date, a.score_tier, a.ep_score\n"
            "FROM mi_ep_alerts a LEFT JOIN mi_live_trades lt\n"
            "  ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date\n"
            "WHERE a.alert_date=CURRENT_DATE AND a.score_tier='HIGH' AND lt.id IS NULL;"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/live_tracker.py::process_new_alerts_live",
            "agents/market_intelligence/broker/bar_stream.py::_handle_bar",
            "agents/market_intelligence/scheduler.py::_ep_scan_job",
        ],
    })


# Job-name → "expected by HH:MM ET on weekdays". Only weekdays — Apollo doesn't
# run weekend market jobs.
_EXPECTED_JOBS: dict[str, time] = {
    "morning_briefing": time(9, 30),
    "nightly_data_pull": time(17, 30),
    "evening_briefing": time(20, 30),
}


async def check_job_no_show(conn, *, now_et: datetime | None = None) -> tuple[bool, dict]:
    """Jobs that should have run by `now_et` today have no `mi_job_log` row.

    Only checks the three durably-logged daily jobs. Weekends are exempt
    (US equity market closed → jobs intentionally skip).
    """
    now_et = now_et or datetime.now(_ET)
    if now_et.weekday() >= 5:  # Sat/Sun
        return (True, {
            "name": INV_JOB_NO_SHOW,
            "count": 0,
            "summary": "weekend — jobs intentionally not run",
            "offending": [],
            "drill_sql": "",
            "code_pointers": [],
        })
    today = now_et.date()
    expected_now = [
        name for name, t in _EXPECTED_JOBS.items() if now_et.time() >= t
    ]
    if not expected_now:
        return (True, {
            "name": INV_JOB_NO_SHOW,
            "count": 0,
            "summary": "no jobs expected to have run yet today",
            "offending": [],
            "drill_sql": "",
            "code_pointers": [],
        })
    rows = await conn.fetch(
        """
        SELECT job_name FROM mi_job_log
        WHERE run_date = $1 AND job_name = ANY($2::text[])
        """,
        today, expected_now,
    )
    ran = {r["job_name"] for r in rows}
    missing = sorted(set(expected_now) - ran)
    return (not missing, {
        "name": INV_JOB_NO_SHOW,
        "count": len(missing),
        "summary": f"{len(missing)} expected jobs missing today: {', '.join(missing) or 'none'}",
        "offending": missing,
        "drill_sql": (
            f"SELECT job_name, ran_at FROM mi_job_log\n"
            f"WHERE run_date = '{today}' ORDER BY ran_at;"
        ),
        "code_pointers": [
            "agents/market_intelligence/scheduler.py",
        ],
    })


# ── Registry: ordered list of (key, callable, kwargs-builder) ──────────────


def all_invariants(*, since: date, since_dt: datetime, now_et: datetime | None = None) -> list[tuple[str, Any, dict]]:
    """Return the full ordered list of invariant calls for a single sweep.

    Caller passes the time-window kwargs once; each entry is
    `(name, async_fn, kwargs)`. Lets system_audit.py and readiness_check.py
    iterate uniformly without each duplicating the call signatures.
    """
    return [
        (INV_NAKED_POSITION, check_naked_position, {}),
        (INV_REASON_COVERAGE, check_reason_coverage, {"since": since}),
        (INV_AUDIT_ERROR_WINDOW, check_audit_error_window, {"since": since_dt}),
        (INV_REGIME_STUCK_CRISIS, check_regime_stuck_crisis, {}),
        (INV_FEED_HEALTH_24H, check_feed_health_24h, {}),
        (INV_STUCK_FILLED_ROW, check_stuck_filled_row, {}),
        (INV_ZOMBIE_THEME, check_zombie_theme, {}),
        (INV_STALE_ORDER_PLACED, check_stale_order_placed, {}),
        (INV_COOLDOWN_SURGE, check_cooldown_surge, {}),
        (INV_HIGH_NO_TERMINAL, check_high_no_terminal, {}),
        (INV_JOB_NO_SHOW, check_job_no_show, {"now_et": now_et}),
    ]
