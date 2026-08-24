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
INV_ZOMBIE_THEME = "zombie_theme"
INV_STALE_ORDER_PLACED = "stale_order_placed"
INV_COOLDOWN_SURGE = "cooldown_surge"
INV_HIGH_NO_TERMINAL = "high_ep_no_terminal_state"
INV_JOB_NO_SHOW = "job_no_show"
INV_EXIT_SHARE_SUM = "exit_share_sum_mismatch"

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
        "offending_rows": [dict(r) for r in rows[:10]],  # for downstream classifier
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


async def classify_naked_positions(body: dict) -> dict:
    """Distinguish real-naked from DB-drift cases (#140, 2026-05-28).

    For each row flagged by `check_naked_position`, query broker for open
    stop orders on that ticker.
      - Broker confirms NO stop order → 🚨 REAL NAKED (real $ risk)
      - Broker DOES have a stop order → ⚠️ DB-DRIFT (operational, no risk)

    Adds 'real_naked' and 'db_drift' lists to body. Fail-open: if broker
    query throws, treat as REAL NAKED (safer to over-alert).

    Triggered by IBM cascade 2026-05-27 post-mortem (#140): after manual
    SQL re-sync mismatched DB↔broker state, the existing invariant fired
    🚨 even when broker had stops. Operator-visible severity was
    indistinguishable from a genuine naked position.
    """
    from agents.market_intelligence import execution_client as alpaca_client  # facade (#256): read-only

    rows = body.get("offending_rows") or []
    real_naked: list[dict] = []
    db_drift: list[dict] = []

    for r in rows:
        ticker = r.get("ticker")
        if not ticker:
            continue
        try:
            # raise_on_error=True (F16 sweep, #456, 2026-07-26): makes the
            # except below the LIVE path for a genuine broker-read failure,
            # not just a genuinely-empty book. No behavior change — this
            # classifier already fails open to REAL NAKED on any exception
            # (documented above: "safer to over-alert"), which is exactly
            # what the default [] fallback produced anyway; this just makes
            # the intent explicit instead of relying on an internal swallow.
            open_orders = await alpaca_client.get_open_orders(ticker=ticker, raise_on_error=True)
            # An open sell-side stop or stop-limit on the position is broker
            # coverage. get_open_orders returns standalone orders (not OTO
            # parents) so we check the order's own fields directly — using
            # extract_stop_leg_id here would always return None because it
            # walks .legs which standalone stops don't have.
            has_stop = any(
                (o.get("side") or "").lower().endswith("sell")
                and (
                    bool(o.get("stop_price"))
                    or "stop" in str(o.get("type") or "").lower()
                )
                for o in open_orders
            )
        except Exception:
            has_stop = False  # fail-open to REAL NAKED

        if has_stop:
            db_drift.append(r)
        else:
            real_naked.append(r)

    body["real_naked"] = real_naked
    body["db_drift"] = db_drift
    return body


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


# Recent-error window for the silent_audit_error_window invariant. Decoupled
# from the 30d baseline lookback that drives metric anomaly detection: a 30d
# window means a single bad day takes 30 days to clear, which is poor UX and
# trains the operator to dismiss the alert. 24h is a "are errors happening
# right now?" cadence — fix lands, alert clears the next audit run.
_RECENT_ERROR_WINDOW_HOURS = 24


async def check_audit_error_window(conn, *, since: datetime) -> tuple[bool, dict]:
    """Count `*_error` rows in the recent window. `since` kwarg accepted for
    signature compatibility with `all_invariants(...)` but the actual window
    is hardcoded to `_RECENT_ERROR_WINDOW_HOURS` so historical errors don't
    keep tripping the alert forever after a fix lands."""
    rows = await conn.fetch(
        """
        SELECT event_type, COUNT(*) AS n
        FROM mi_audit_log
        WHERE event_type LIKE '%_error'
          AND created_at >= NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY event_type
        ORDER BY n DESC
        """,
        str(_RECENT_ERROR_WINDOW_HOURS),
    )
    total = sum(int(r["n"]) for r in rows)
    return (total == 0, {
        "name": INV_AUDIT_ERROR_WINDOW,
        "count": total,
        "summary": (
            f"{total} '*_error' events in last {_RECENT_ERROR_WINDOW_HOURS}h"
            if total else "clean"
        ),
        "offending": [f"{r['event_type']}: {r['n']}" for r in rows[:10]],
        "drill_sql": (
            f"SELECT event_type, summary, detail, created_at FROM mi_audit_log\n"
            f"WHERE event_type LIKE '%_error'\n"
            f"  AND created_at >= NOW() - INTERVAL '{_RECENT_ERROR_WINDOW_HOURS} hours'\n"
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


async def check_zombie_theme(conn, *, stale_after_days: int = 10) -> tuple[bool, dict]:
    """Mainstream theme whose latest snapshot stopped appearing > N days ago.

    Recency-based retirement (`get_active_themes` 7-day window) means *any*
    stage can age out silently — that's the design, not a bug. So the only
    drop-out worth alerting on is **Mainstream**: by the time a theme reaches
    Mainstream it's load-bearing for the brief and trade surfaces, and a
    silent disappearance there means upstream RS/scoring stopped producing
    the expected signal.

    Second-iteration narrowing (2026-04-28): the 2026-04-27 fix excluded
    'Fading' but kept Nascent/Accelerating, which still fires every time a
    short-lived theme blips Accelerating for a day or two and rolls off.
    Today's breach was 18 Nascent + 11 Accelerating + 0 Mainstream — all
    by-design lifecycle drop-outs. Accelerating-drop-out churn is potentially
    interesting as L2 telemetry, but it's not an invariant violation.

    Threshold bumped 7 → 10d so a Mainstream theme that misses a holiday-
    shortened week doesn't false-fire on the next business day.
    """
    rows = await conn.fetch(
        """
        WITH latest AS (
            SELECT DISTINCT ON (name)
                name, theme_date AS last_seen, stage AS latest_stage
            FROM mi_themes
            ORDER BY name, theme_date DESC
        )
        SELECT name, last_seen, latest_stage,
               (CURRENT_DATE - last_seen) AS days_stale
        FROM latest
        WHERE latest_stage = 'Mainstream'
          AND (CURRENT_DATE - last_seen) > $1
        ORDER BY days_stale DESC
        """,
        stale_after_days,
    )
    return (len(rows) == 0, {
        "name": INV_ZOMBIE_THEME,
        "count": len(rows),
        "summary": f"{len(rows)} Mainstream themes stopped appearing > {stale_after_days}d ago",
        "offending": [
            f"{r['name']} stage={r['latest_stage']} last_seen={r['last_seen']} ({r['days_stale']}d stale)"
            for r in rows[:10]
        ],
        "drill_sql": (
            "WITH latest AS (\n"
            "  SELECT DISTINCT ON (name) name, theme_date AS last_seen, stage AS latest_stage\n"
            "  FROM mi_themes ORDER BY name, theme_date DESC\n"
            ")\n"
            "SELECT name, last_seen, latest_stage,\n"
            "       (CURRENT_DATE - last_seen) AS days_stale\n"
            "FROM latest\n"
            f"WHERE latest_stage = 'Mainstream'\n"
            f"  AND (CURRENT_DATE - last_seen) > {stale_after_days}\n"
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
# run weekend market jobs. nightly_data_pull starts at 17:00 ET; sector/desc
# enrichment + Claude calls can stretch the run past 17:30, so the deadline
# sits at 18:30 to avoid flagging mid-flight runs as missing.
# account_equity_snapshot (RED-3a, 2026-07-12): the 16:12 ET job that feeds the
# drawdown breaker + kill-scale bands. If it silently stops, the breaker runs
# fail-open on stale data with no alert — so it is watched here (deadline 16:45,
# generous for a 2-API-call job).
_EXPECTED_JOBS: dict[str, time] = {
    "morning_briefing": time(9, 30),
    "nightly_data_pull": time(18, 30),
    "evening_briefing": time(20, 30),
    "account_equity_snapshot": time(16, 45),
}

# Jobs whose completion evidence lives in `mi_job_runs` (status='success' via
# core.job_audit.audit_wrap) instead of `mi_job_log` (log_job_run — which only
# the three legacy jobs call). Success-only mirrors mi_job_log's semantics:
# a run that crashed still flags as missing here (belt-and-suspenders with
# notify_job_failure), exactly like a legacy job that died before log_job_run.
_MI_JOB_RUNS_SUCCESS_JOBS = frozenset({"account_equity_snapshot"})


async def check_job_no_show(conn, *, now_et: datetime | None = None) -> tuple[bool, dict]:
    """Jobs that should have run by `now_et` today show no completion evidence.

    Completion evidence is a `mi_job_log` row (the three legacy jobs, written
    via log_job_run) or — for `_MI_JOB_RUNS_SUCCESS_JOBS` — a status='success'
    `mi_job_runs` row today (audit_wrap telemetry; those jobs never write
    mi_job_log). Weekends are exempt (US equity market closed → jobs
    intentionally skip). A job with an in-progress `mi_job_runs` row
    (status='running') today is treated as "running" rather than missing —
    completion rows are only written at job end, so a slow run would
    otherwise look identical to a no-show.
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
    # RED-3a: jobs tracked via audit_wrap complete into mi_job_runs, not
    # mi_job_log — accept a clean (status='success') run today as evidence.
    runs_tracked_now = [n for n in expected_now if n in _MI_JOB_RUNS_SUCCESS_JOBS]
    if runs_tracked_now:
        success_rows = await conn.fetch(
            """
            SELECT DISTINCT job_id FROM mi_job_runs
            WHERE started_at >= $1::date AT TIME ZONE 'America/New_York'
              AND status = 'success'
              AND job_id = ANY($2::text[])
            """,
            today, runs_tracked_now,
        )
        ran |= {r["job_id"] for r in success_rows}
    # Also count jobs currently running per `mi_job_runs` — slow runs that
    # haven't yet logged completion shouldn't fire a "missing" alert.
    running_rows = await conn.fetch(
        """
        SELECT DISTINCT job_id FROM mi_job_runs
        WHERE started_at >= $1::date AT TIME ZONE 'America/New_York'
          AND status = 'running'
          AND job_id = ANY($2::text[])
        """,
        today, expected_now,
    )
    in_progress = {r["job_id"] for r in running_rows}
    missing = sorted(set(expected_now) - ran - in_progress)
    summary_parts = []
    if missing:
        summary_parts.append(f"{len(missing)} missing: {', '.join(missing)}")
    if in_progress:
        summary_parts.append(f"{len(in_progress)} still running: {', '.join(sorted(in_progress))}")
    summary = "; ".join(summary_parts) if summary_parts else "all expected jobs ran"
    return (not missing, {
        "name": INV_JOB_NO_SHOW,
        "count": len(missing),
        "summary": summary,
        "offending": missing,
        "drill_sql": (
            f"SELECT job_name, ran_at FROM mi_job_log\n"
            f"WHERE run_date = '{today}' ORDER BY ran_at;\n"
            f"-- in-progress check:\n"
            f"SELECT job_id, started_at, status FROM mi_job_runs\n"
            f"WHERE started_at >= '{today}'::date AT TIME ZONE 'America/New_York'\n"
            f"  AND status = 'running' ORDER BY started_at;"
        ),
        "code_pointers": [
            "agents/market_intelligence/scheduler.py",
        ],
    })


# ── #588 exit-share accounting (2026-08-24) ────────────────────────────────

# Rows that closed BEFORE the fix are known-bad and stay out of the alert: ETON
# 2026-08-14 plus 8 older paper rows. Backfilling them is the operator's call, so
# an unbounded check would L1-Telegram the same eight rows every sweep forever —
# a guard that always fires is not a guard.
EXIT_SHARE_SUM_SINCE = date(2026, 8, 24)


async def check_exit_share_sum(conn, *, since: date | None = None) -> tuple[bool, dict]:
    """A closed trade's exit legs must sum to the shares it entered (#588).

    ETON 2026-08-14: a 17-share position recorded a 17-share stop leg (the stop
    actually filled 12) plus the 5-share partial that was still resting when the
    stop fired — 22 shares booked against 17 entered, and the P&L $0.76 light.
    `mi_sell_discipline_records` reads straight off these legs, so the error lands
    in the evidence every exit-rule replay is tuned on.

    Deliberately narrow, so a breach means a real write-path defect:
      - closed rows only (an open trade legitimately has legs summing to less);
      - single-attempt only (a re-entered trade buys `entry_shares` again, so its
        legs legitimately sum to a MULTIPLE of it — 5 such paper rows exist);
      - every leg must carry `shares` (one 2026-04 legacy repair leg uses `qty`);
      - NO exit order still working at the broker. A +2R carve-out rests as a GTC
        limit, and the day-1 stop path closes the row at zero while it rests — so
        between the stop fill and the limit fill a CORRECTLY recorded trade reads
        12 of 17 and would alarm every sweep. ETON's limit rested six hours and
        filled at 15:58, seventeen minutes before the 16:15 sweep. The guard must
        tolerate that state gap (closing at zero with shares resting is an open
        operator question, not something this check can fix); the moment the order
        goes terminal the row is checked for real. Both Alpaca spellings of
        cancel are listed — the broker emits `canceled` AND `cancelled`.
      - float tolerance, never `!=` (legs are written as both 17 and 17.0).
    """
    cutoff = since or EXIT_SHARE_SUM_SINCE
    rows = await conn.fetch(
        """
        SELECT t.id, t.ticker, t.account_mode, t.alert_date, t.entry_shares,
               COALESCE((SELECT SUM((x->>'shares')::numeric)
                           FROM jsonb_array_elements(t.exits) x), 0) AS exit_shares
        FROM mi_live_trades t
        WHERE t.status = 'closed'
          AND COALESCE(t.entry_attempt, 1) = 1
          AND t.closed_at IS NOT NULL
          AND (t.closed_at AT TIME ZONE 'America/New_York')::date >= $1
          AND jsonb_array_length(COALESCE(t.exits, '[]'::jsonb)) > 0
          AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(t.exits) x WHERE NOT (x ? 'shares')
          )
          AND NOT EXISTS (
                SELECT 1 FROM mi_live_orders o
                WHERE o.trade_id = t.id
                  AND o.purpose IN ('partial_exit', 'full_exit')
                  AND o.status NOT IN ('filled', 'cancelled', 'canceled',
                                       'rejected', 'expired')
          )
          AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)
                              FROM jsonb_array_elements(t.exits) x), 0)
                  - t.entry_shares) > 0.001
        ORDER BY t.closed_at DESC
        """,
        cutoff,
    )
    return (len(rows) == 0, {
        "name": INV_EXIT_SHARE_SUM,
        "count": len(rows),
        "summary": (
            f"{len(rows)} closed trade(s) whose exit legs do not sum to the shares "
            f"entered — booked P&L is wrong on each"
        ),
        "offending": [
            f"{r['ticker']} {r['alert_date']} [{r['account_mode']}]: "
            f"entered {float(r['entry_shares']):g}, exits sum "
            f"{float(r['exit_shares']):g}"
            for r in rows[:10]
        ],
        "drill_sql": (
            "SELECT id, ticker, account_mode, entry_shares, exits\n"
            "FROM mi_live_trades\n"
            "WHERE status='closed' AND COALESCE(entry_attempt,1)=1\n"
            "  AND ABS(COALESCE((SELECT SUM((x->>'shares')::numeric)\n"
            "                      FROM jsonb_array_elements(exits) x),0)\n"
            "          - entry_shares) > 0.001;"
        ),
        "code_pointers": [
            "agents/market_intelligence/broker/order_manager.py::attempt_day1_reentry",
            "agents/market_intelligence/broker/trade_stream.py::_process_stop_fill",
            "agents/market_intelligence/broker/order_manager.py::_finalize_stop_fill_locked",
            "agents/market_intelligence/broker/order_manager.py::finalize_partial_exit",
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
        (INV_ZOMBIE_THEME, check_zombie_theme, {}),
        (INV_STALE_ORDER_PLACED, check_stale_order_placed, {}),
        (INV_COOLDOWN_SURGE, check_cooldown_surge, {}),
        (INV_HIGH_NO_TERMINAL, check_high_no_terminal, {}),
        (INV_JOB_NO_SHOW, check_job_no_show, {"now_et": now_et}),
        (INV_EXIT_SHARE_SUM, check_exit_share_sum, {}),
    ]
