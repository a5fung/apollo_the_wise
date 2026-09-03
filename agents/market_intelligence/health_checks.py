"""
Systematic anti-silent-failure / completeness-health layer (PLAN #370, operator 6/24, EMPHATIC).

THE CLASS, NOT THE INSTANCE. A money-adjacent signal can silently stop computing and degrade
trading for weeks with ZERO alert: the regime's `spy_vs_200ma` was NULL for ~3 weeks (drives the
EP threshold + position sizing), the theme synthesis truncated to 0 cohorts for days, theme-shadow
wrote 0 rows (#173), the gdrive backup went stale. Every one "looked fine, wasn't." The directive
is to make silent failure impossible to miss, SYSTEMATICALLY — not to patch each instance.

PRIMARY LAYER = a GENERIC class-catcher (no hand-curated "failures we thought of" registry).

──────────────────────────────────────────────────────────────────────────────────────────────
THIS INCREMENT — the NULL-RATE DRIFT sweep (`run_null_rate_sweep`): the generic version of the
200MA catch. For each key output table, for each numeric value column, it compares the column's
recent per-date non-null rate against the latest date. If a column is NORMALLY populated but its
latest date went entirely NULL → a column silently stopped computing → FLAG + Telegram.

Granularity decision (advisor-refined): we evaluate **per-DATE non-null fractions**, NOT per-row.
The spec's "latest row" wording was written picturing `mi_market_regime` (one row per date); taken
literally on the multi-row tables (`mi_ep_alerts`, `mi_daily_closes` ~9,700 rows/day) a per-row
check is either noise or meaningless. The faithful generalization: group by the table's date
column, the series is `COUNT(col)::float / COUNT(*)` per date. For a one-row-per-date table this
collapses to 0.0 / 1.0 — i.e. EXACTLY the 200MA case, which is the proof this is the right
generalization, not a deviation.

Noise calibration (the make-or-break — a noisy guard gets muted and then misses the REAL failure):
  - BASELINE = the prior dates (excluding the latest). Require non-null rate ≥ 0.95 over ≥ 10
    prior dates → "normally populated". This is what separates STRUCTURALLY-BROKEN from
    legitimately-sparse: a column null half the time (`rel_volume`, `theme_score`) never clears
    the 0.95 gate, so it can never flag — it self-excludes.
  - TRIGGER = the latest date is ENTIRELY null (per-date non-null fraction == 0). Conservative:
    a single legit-null row among several on the latest date will NOT fire.
  - Flag only when BOTH hold. Latest-date driven (not a calendar 'today') → trading-day-aware.

Column selection is automatic, not a skip list: we take only NUMERIC columns from
`information_schema` (double precision / numeric / integer / bigint / real / smallint), which
auto-drops ids, timestamps, text blobs, booleans, and jsonb. A nice consequence: the legit-sparse
numeric columns self-exclude via the ≥95% gate, so the ACTIVE catches land on exactly the
high-value always-on signals — regime inputs, daily closes, rs scores.

──────────────────────────────────────────────────────────────────────────────────────────────
INCREMENT 3 — the JOB → OUTPUT-LIVENESS sweep (`run_job_liveness_sweep`, below): catches the OTHER
recurring silent-failure class — a scheduled JOB that ran clean ('success') but produced NOTHING (the
theme synthesis truncating to 0 cohorts 6/22-24, theme-shadow 0 rows #173). Where increment 1 reads a
column's null rate, this reads the OUTPUT TABLE's new-row count on the job's successful run-dates,
DECOUPLED from the job's own (lying) self-reported rows_written. See its section header for the full
noise-calibration (always-on K=1 vs legit-quiet K=3 cadence; ran-but-empty only; no-run = heartbeat).

──────────────────────────────────────────────────────────────────────────────────────────────
The BASELINE-SELF-POISON limitation of THIS sweep (the null sweep alerts day-1/2 of a silent null,
then quiets as the null walks into its own rolling baseline — DoD "alert day-1" is MET) is now
ADDRESSED by INCREMENT 2 (`reconcile_health_flags` + the direct re-check fns, bottom of file): a
flagged-AND-still-broken target keeps nagging daily, DECOUPLED from the rolling baseline. The
self-poison of the sweep ITSELF is still pinned by test_persistent_null_self_silences_known_limitation
(the sweep going quiet is BY DESIGN — increment 2's direct re-check is what keeps the alert alive).
DEFERRED next increment: (5) the specific hard-check registry (backups etc., CHANGE_PROCESS). See PLAN #370.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import (
    get_pool, log_audit_event, LIVE_SOURCE_SQL,
    get_latest_two_theme_dates, get_theme_retired_candidate_names,
    get_theme_history_window, get_theme_member_departures,
    get_theme_quality_alerted_targets, get_recent_rs_batch, get_rs_on_date,
    get_reactivation_sessions, get_high_ep_ticker_days,
    get_ticker_ecosystem_membership, get_mapped_theme_stages_before,
    get_reactivation_alerted_ecosystems, persist_reactivation_seed,
)
from shared.dates import et_today  # canonical ET-today (tz-bug-class centralization, /simplify 6/25)

_ET = ZoneInfo("America/New_York")  # codebase tz rule — never naive datetime.now()

logger = logging.getLogger(__name__)

# (table_name, date_column). The date column differs per table; everything else
# (the numeric value columns) is discovered automatically from information_schema.
# A simple list constant so it's trivial to extend — add a (table, date_col) tuple.
_NULL_SWEEP_TABLES: list[tuple[str, str]] = [
    ("mi_market_regime", "regime_date"),     # spy_vs_200ma etc. — the original 200MA catch
    ("mi_daily_closes", "trade_date"),       # close/volume/ohlc — the daily data spine
    ("mi_stock_scores", "score_date"),       # rs_1m/3m/6m/composite — RS engine output
    ("mi_ep_alerts", "alert_date"),          # ep_score/gap_pct — EP detector output
    ("mi_theme_axis_shadow", "alert_date"),  # theme attribution shadow
]

# Postgres numeric data_types we treat as "value columns" worth checking. Anything
# else (text, timestamptz, boolean, jsonb, ARRAY, …) is skipped automatically.
_NUMERIC_DATA_TYPES = frozenset({
    "double precision", "numeric", "real",
    "integer", "bigint", "smallint",
})

# Noise-calibration thresholds.
_MIN_BASELINE_DATES = 10   # need ≥10 prior dates to call a column "normally populated"
_POPULATED_RATE = 0.95     # ≥95% non-null over the baseline → normally populated
_RECENT_WINDOW = 30        # most-recent N dates pulled per table


def _evaluate_column(per_date_fractions: list[float]) -> dict[str, Any] | None:
    """Pure decision: given a column's per-DATE non-null fractions ordered MOST-RECENT FIRST,
    decide whether the column has silently broken.

    Returns a flag dict (baseline_rate, baseline_n) if the column is normally populated
    (≥95% over ≥10 prior dates) BUT the latest date is entirely null. Returns None otherwise.

    This is the whole noise calibration, isolated and mock-free so it can be tested directly:
      - latest entirely null + healthy baseline  → flag        (the 200MA / silently-broken case)
      - latest null + sparse baseline (<95%)      → None        (legit-often-null, self-excludes)
      - always-null                               → None        (never met the populated bar)
      - latest still populated                    → None        (nothing broke)
    """
    if len(per_date_fractions) < _MIN_BASELINE_DATES + 1:
        return None  # not enough history to judge

    latest = per_date_fractions[0]
    baseline = per_date_fractions[1:]  # prior dates only — exclude the latest from the baseline
    # (len(baseline) >= _MIN_BASELINE_DATES is guaranteed by the line-93 guard above.)

    # TRIGGER: the latest date is ENTIRELY null. Conservative — a partial-null latest date
    # (some rows null) does not fire (deferred refinement). >0 means at least one row populated.
    if latest > 0.0:
        return None

    # BASELINE GATE: was this column NORMALLY populated before it broke?
    baseline_rate = sum(baseline) / len(baseline)
    if baseline_rate < _POPULATED_RATE:
        return None  # legitimately-often-null column — NOT a silent failure, self-excludes

    return {
        "baseline_rate": round(baseline_rate, 4),
        "baseline_n": len(baseline),
    }


async def _numeric_columns(conn, table: str) -> list[str]:
    """Numeric value columns for `table`, discovered from information_schema (no skip list)."""
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1 AND data_type = ANY($2::text[])
        ORDER BY ordinal_position
        """,
        table,
        list(_NUMERIC_DATA_TYPES),
    )
    return [r["column_name"] for r in rows]


async def _per_date_fractions(conn, table: str, date_col: str, columns: list[str]) -> list[dict]:
    """One GROUP-BY query: per-date row count + per-column non-null count over the recent window.

    Aggregation happens in SQL (mi_daily_closes / mi_stock_scores are ~9,700 rows/day; pulling
    30 days into Python would be ~290k rows). Identifiers are double-quoted; the table/date_col
    come from our own constant and the column names from information_schema for the same table,
    so this is not attacker-controlled — but quoting keeps it correct for odd identifiers.
    """
    if not columns:
        return []
    counts = ",\n               ".join(
        f'COUNT("{c}")::float AS "nn_{c}"' for c in columns
    )
    # Bounded, NOT a full scan: every swept table has a DATE-LEADING index (PK or explicit), so the
    # planner does Index-Scan-Backward + GroupAggregate + LIMIT early-stop — reading ~_RECENT_WINDOW
    # dates, not the whole table. EXPLAIN-verified on mi_daily_closes (the largest): "Index Scan
    # Backward using mi_daily_closes_pkey" with the Limit early-stopping at 30 groups. (No WHERE date
    # bound needed; the LIMIT + index is the bound.)
    sql = f'''
        SELECT "{date_col}" AS d,
               COUNT(*)::float AS total,
               {counts}
        FROM "{table}"
        GROUP BY "{date_col}"
        ORDER BY "{date_col}" DESC
        LIMIT {_RECENT_WINDOW}
    '''
    rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


def _fractions_for_column(date_rows: list[dict], column: str) -> list[float]:
    """Extract the per-date non-null FRACTION series for one column, most-recent-first.

    Dates with total == 0 are impossible from a GROUP BY (an empty date produces no row at all,
    which is the deferred job-liveness concern), so total is always > 0 here.
    """
    out: list[float] = []
    for r in date_rows:
        total = r["total"]
        if not total:  # defensive — should never happen from GROUP BY
            continue
        out.append(r[f"nn_{column}"] / total)
    return out


async def _sweep_table(conn, table: str, date_col: str) -> dict[str, Any]:
    """Sweep one table. Wrapped by the caller in try/except so a bad table can't kill the sweep."""
    columns = await _numeric_columns(conn, table)
    date_rows = await _per_date_fractions(conn, table, date_col, columns)

    flags: list[dict[str, Any]] = []
    for col in columns:
        fractions = _fractions_for_column(date_rows, col)
        verdict = _evaluate_column(fractions)
        if verdict is not None:
            flags.append({"table": table, "column": col, **verdict})
    return {"columns_checked": len(columns), "flags": flags}


def _format_flag(f: dict[str, Any]) -> str:
    pct = round(f["baseline_rate"] * 100)
    return (
        f"• `{f['table']}.{f['column']}` null in latest date — "
        f"was {pct}% populated over {f['baseline_n']}d"
    )


async def run_null_rate_sweep(conn=None) -> dict[str, Any]:
    """Run the NULL-RATE DRIFT sweep across the key output tables.

    For each table, for each numeric value column: if the column was normally populated
    (≥95% non-null over ≥10 prior dates) but the LATEST date is entirely null, flag it — a
    column silently stopped computing. All flags are sent as ONE grouped Telegram; zero flags
    → audit-only (Telegram is reserved for real failures).

    Robust by design (a health guard that itself fails silently is the worst failure): per-table
    work is wrapped in try/except so one bad table doesn't kill the sweep; errors are logged and
    surfaced in the returned summary AND in the audit row.

    Args:
        conn: optional asyncpg connection. If None, acquires one from the shared pool.

    Returns:
        Summary dict: tables_scanned, columns_checked, flags (list), errors (list).
    """
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as acquired:
            return await run_null_rate_sweep(acquired)

    all_flags: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    tables_scanned = 0
    columns_checked = 0

    for table, date_col in _NULL_SWEEP_TABLES:
        try:
            result = await _sweep_table(conn, table, date_col)
            tables_scanned += 1
            columns_checked += result["columns_checked"]
            all_flags.extend(result["flags"])
        except Exception as e:  # one bad table must not kill the sweep
            logger.warning("null_rate_sweep: table %s failed: %s", table, e)
            errors.append({"table": table, "error": str(e)})

    summary = {
        "tables_scanned": tables_scanned,
        "columns_checked": columns_checked,
        "flags": all_flags,
        "errors": errors,
    }

    # ── Alert ────────────────────────────────────────────────────────────────────────────────
    if all_flags:
        header = f"🩺 SILENT-NULL DETECTED ({len(all_flags)})"
        lines = [header, ""]
        lines.extend(_format_flag(f) for f in all_flags)
        lines.append("")
        lines.append("A normally-populated column went null in its latest date — it may have "
                     "silently stopped computing (PLAN #370).")
        body = "\n".join(lines)
        try:
            # Imported lazily so a Telegram/env issue can't break module import or tests.
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(body)
        except Exception as e:
            logger.warning("null_rate_sweep: telegram send failed: %s", e)
            errors.append({"telegram": str(e)})

        detail_cols = ", ".join(f"{f['table']}.{f['column']}" for f in all_flags)
        await log_audit_event(
            "health_null_sweep_flagged",
            f"{len(all_flags)} silently-null column(s): {detail_cols}",
            detail=str(summary),
        )
    else:
        # Zero flags → audit-only (do NOT Telegram a clean run — Telegram is for real failures).
        note = (
            f"clean: {tables_scanned} tables, {columns_checked} numeric cols"
            + (f"; {len(errors)} table error(s)" if errors else "")
        )
        await log_audit_event("health_null_sweep_clean", note, detail=str(summary))

    if errors:
        logger.warning("null_rate_sweep completed with %d error(s): %s", len(errors), errors)

    # Persistence reconcile (#370 increment 2): record state + NAG flags the rolling baseline has
    # self-silenced but that are STILL broken (the self-poison fix — the direct re-check is decoupled
    # from the >=95% baseline gate). Internally robust; can't take down the sweep.
    recon = await reconcile_health_flags(
        conn, "null_sweep", all_flags, _recheck_null_flag, key_fn=_null_flag_target_key)
    summary["persistence"] = {k: recon[k] for k in ("nagged", "resolved", "still_open")}

    return summary


# ══════════════════════════════════════════════════════════════════════════════════════════════
# INCREMENT 3 — JOB → OUTPUT-LIVENESS sweep (PLAN #370). The OTHER recurring silent-failure class.
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# Increment 1 (above) catches a COLUMN silently going null. THIS catches a JOB that RAN but produced
# NOTHING — the theme synthesis truncating to 0 cohorts for days (6/22-24), theme-shadow writing 0
# rows (#173). "Ran today" stays GREEN through these: the job exits status='success', no exception,
# no empty_result — it just didn't write to its output table. We verify the OUTPUT TABLE directly.
#
# WHY CHECK THE TABLE, NOT `mi_job_runs.rows_written` (the decoupling IS the whole point): the job's
# OWN self-report lies. `nightly_data_pull` returns ~3,900 RS-scores and records status='success'
# even on a night the theme step inside it wrote 0 rows to `mi_themes` — its rows_written counts
# RS-scores, not themes. So we read the table's NEW-rows ground truth, decoupled from what the job
# claimed (memory feedback_scheduler_aggregators_db_sourced: never trust in-process/self-reported
# state; query the DB). audit_wrap's `expected_min_rows` (nightly=3500, crypto, minute_volume) is the
# complementary self-report band — we filter to status='success' so we never double-alert those jobs
# (an empty_result already Telegrams via audit_wrap; we only fire on the clean-but-empty case it misses).
#
# SCOPE — a job that did NOT run at all is a SEPARATE concern (heartbeat = increment 4). We flag ONLY
# ran-but-empty. No run-date in the window → SKIP, never flag (the no-false-fire rule for holidays /
# weekends / a genuinely-down job, which increment 4 owns).
#
# NOISE CALIBRATION (the make-or-break — a noisy guard gets muted, then misses the real one):
#   - Run-dates come from `mi_job_runs` as DISTINCT (started_at AT TIME ZONE 'America/New_York')::date
#     for status='success'. Dedup to DATES matters: ep_scan runs every 5 min → ~75 rows/day. Keying
#     off RUN-dates (not a calendar 'today') gives weekend-awareness for free (no weekend success-run).
#     HOLIDAYS are NOT free, though — a weekday holiday produces a success-run with ZERO output (the
#     nightly job early-returns past the theme step but still records 'success', PLAN #325), so we
#     explicitly DROP non-trading run-dates in `_successful_run_dates` (else the K=1 always-on entry
#     false-fires ~9-10×/yr → mutes the guard). This makes the sweep host-independent, not reliant on
#     the 17:30 caller being trading-day-gated (it is NOT — _post_nightly_audit_job runs mon-fri incl.
#     holidays). Same calendar increment 1 leans on implicitly via latest-date-WITH-DATA.
#   - Per output table we compare the table's NEW-row count on each of those run-dates against
#     `min_expected_rows`. A run-date "produced nothing" when its new-row count < min_expected_rows.
#   - CADENCE (the legit-quiet distinction): always-on tables (the nightly data spine — `mi_themes`,
#     RS/closes) MUST be non-empty every run → K=1 (a single empty run = broken). Legitimately-quiet
#     tables (EP alerts on a slow day, theme-synthesis proposing 0-3 cohorts) are empty some days by
#     DESIGN → K=3: flag only after K CONSECUTIVE empty run-dates (a structural break, not one quiet
#     day). This is the direct analog of increment 1's ≥95%-baseline gate: it's what separates
#     STRUCTURALLY-BROKEN from legitimately-quiet so the guard fires on the former only.
#   - Fewer than K successful run-dates in the window → SKIP (not enough history to judge), mirroring
#     increment 1's <10-baseline-dates guard.

# (job_id, label, output_table, date_col, min_expected_rows, k). The job_id is the audit_wrap id in
# scheduler.py (the run-ground-truth); the table/date_col is where that job's output lands. A simple
# list constant so it's trivially extensible — append a tuple. K encodes the cadence:
#   K=1  → always-on: every successful run MUST write ≥ min rows (a single empty run = structurally broken)
#   K=3  → legitimately-quiet: flag only after 3 CONSECUTIVE empty run-dates (avoids single-quiet-day noise)
_JOB_OUTPUT_CHECKS: list[tuple[str, str, str, str, int, int]] = [
    # ── Always-on (K=1): the nightly data spine. mi_themes is written INSIDE nightly_data_pull as a
    # fresh theme_date=today snapshot of the full active set EVERY run (theme_engine._save_themes) —
    # and audit_wrap's rows_written for this job counts RS-scores, NOT themes, so the theme step is
    # exactly the silently-truncatable output audit_wrap does NOT separately verify (the decoupling
    # value). During the #325 16-day discovery drought it still held ~15 rows/day → K=1/min≥1
    # correctly would NOT have fired (that was a births problem, not truncation-to-0 → out of scope).
    ("nightly_data_pull", "nightly theme snapshot", "mi_themes", "theme_date", 1, 1),

    # ── Legitimately-quiet (K=3): empty on a slow day is NORMAL, so require a 3-run consecutive zero.
    # theme_synthesis proposes 0-3 cohorts by design (the headline 6/22-24 truncation example) →
    # writes mi_theme_candidates_shadow; 0 for a single run is legit, 0 for 3 runs = structural break.
    ("theme_synthesis", "theme synthesis (RS-slope cohorts)",
     "mi_theme_candidates_shadow", "run_date", 1, 3),
    # ep_scan: "No alert for zero EPs (normal)" (ep_scan_watchdog) — EP HIGHs are a rare event, 0/day
    # is common; only a multi-day drought signals the detector silently dying (#173 shadow-death class).
    ("ep_scan", "EP detector alerts", "mi_ep_alerts", "alert_date", 1, 3),
    # 9m_ep_scan: virgin-9M is a ~1% rare event (target 2-5/day but many days 0) → quiet, K=3.
    ("9m_ep_scan", "9M EP alerts", "mi_9m_ep_alerts", "alert_date", 1, 3),
]

# NOTE on scope (judgment call, documented per advisor): mi_stock_scores / mi_daily_closes are
# DELIBERATELY EXCLUDED here. nightly_data_pull already declares expected_min_rows=3500 → audit_wrap
# band-checks + Telegrams an RS-score shortfall, AND increment 1's null-sweep covers their columns.
# Adding a degenerate-floor liveness check too would be redundant. mi_themes is the one nightly output
# NEITHER of those covers (rows_written counts RS-scores, not themes) → it's the high-value add here.


def _evaluate_job_liveness(
    per_date_counts: list[int], min_expected_rows: int, k: int
) -> dict[str, Any] | None:
    """Pure decision: given a job's output-row counts on its recent SUCCESSFUL run-dates, ordered
    MOST-RECENT FIRST, decide whether the job has been silently producing nothing.

    Returns a flag dict (empty_runs, window) if the job RAN but its output table got fewer than
    `min_expected_rows` new rows on ALL of the last `k` run-dates. Returns None otherwise.

    This is the whole noise calibration, isolated and mock-free so it can be tested directly:
      - last K run-dates all empty   → flag   (structurally broken: the truncation / #173 class)
      - K=1, latest run-date empty   → flag   (always-on table: one empty run = broken)
      - quiet table, single zero     → None    (legit quiet day; needs K consecutive zeros)
      - latest run-date has rows      → None    (job produced output — nothing broken)
      - fewer than K run-dates        → None    (not enough run history to judge — heartbeat's job)
    """
    if len(per_date_counts) < k:
        return None  # not enough successful run-dates to judge — a no/low-run case is heartbeat (incr 4)

    window = per_date_counts[:k]  # the most-recent k run-dates
    # TRIGGER: every one of the last k run-dates produced too few rows (all empty/degenerate).
    if all(c < min_expected_rows for c in window):
        return {"empty_runs": k, "window_counts": list(window)}
    return None


def _is_trading_day(d) -> bool:
    """True if `d` is an NYSE trading day. Isolated + lazy-imported so it's mockable and the import
    can't break module load. Defaults to True on any failure (fail-OPEN: better to risk one extra
    check than to silently drop a real run-date and miss a truncation)."""
    try:
        from agents.market_intelligence.trading_calendar import get_market_status
        return bool(get_market_status(d).is_trading_day)
    except Exception:  # calendar lookup failed — don't let it silence the sweep
        return True


async def _successful_run_dates(conn, job_id: str, limit: int) -> list[str]:
    """The most-recent DISTINCT TRADING-DAY ET dates on which `job_id` ran to status='success'.

    Deduped to DATES (ep_scan runs every 5 min → ~75 rows/day; we want run-DATES, not run-rows) and
    ET-localized (AT TIME ZONE) per the codebase tz rule. status='success' only: a 'failed' or
    'empty_result' run is NOT a clean run that silently produced nothing — those already alert via
    notify_job_failure / audit_wrap, so including them would double-count. Most-recent first.

    TRADING-DAY FILTER (the holiday false-fire fix): a weekday HOLIDAY is the trap for the K=1
    always-on entry — `nightly_data_pull` RUNS on a holiday, EARLY-RETURNS before the theme step,
    and STILL records status='success' in mi_job_runs (PLAN #325: "success = the clean holiday-skip"
    on Juneteenth). So the holiday's run-date has 0 theme rows → K=1 would false-fire ~9-10×/yr →
    the guard gets muted → it misses the real truncation. Increment 1 is holiday-safe by accident
    (a holiday produces NO regime row, so its latest-date-with-DATA skips the holiday); this sweep
    keys off run-happened+rows, where a holiday IS a success-run with zero output — NOT equivalent.
    We make it host-independent (not reliant on the caller gating non-trading days) by dropping
    non-trading run-dates here, exactly the calendar increment 1 leans on implicitly. We over-fetch
    (limit*2 + 5) so in-window holidays don't starve us below k real trading run-dates.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT (started_at AT TIME ZONE 'America/New_York')::date AS run_date
        FROM mi_job_runs
        WHERE job_id = $1 AND status = 'success'
        ORDER BY run_date DESC
        LIMIT $2
        """,
        job_id,
        limit * 2 + 5,  # over-fetch so dropped holidays don't starve us below `limit` trading days
    )
    trading = [r["run_date"] for r in rows if _is_trading_day(r["run_date"])]
    return trading[:limit]


async def _new_rows_on_date(conn, table: str, date_col: str, run_date) -> int:
    """COUNT of rows in `table` whose date column == `run_date`.

    The output's date column IS the "produced for this date" key (theme_date / alert_date / run_date),
    so a same-date count is the new-rows-on-that-run measure — no separate created_at window needed,
    and it's idempotent against the every-5-min upserts (ep_scan re-runs UPSERT the same date's rows).
    Identifiers are double-quoted; table/date_col come from our own constant (not attacker-controlled).
    """
    val = await conn.fetchval(
        f'SELECT COUNT(*) FROM "{table}" WHERE "{date_col}" = $1',
        run_date,
    )
    return int(val or 0)


async def _check_job(
    conn, job_id: str, table: str, date_col: str, min_expected_rows: int, k: int
) -> dict[str, Any] | None:
    """Check one job→table pairing. Wrapped by the caller in try/except so one bad job can't kill
    the sweep. Returns a flag dict (with job_id/table context) or None.

    Pulls a few more run-dates than k so the verdict is robust if a run-date has no rows at all to
    count against (we still want the k most-recent run-dates' output counts).
    """
    run_dates = await _successful_run_dates(conn, job_id, limit=k + 2)
    if len(run_dates) < k:
        return None  # not enough successful runs in history → skip (heartbeat territory, not ours)

    # One grouped COUNT keyed by date instead of a per-date round-trip each (/simplify 6/25 efficiency,
    # ~16 COUNT(*) -> 4 across the sweep, every nightly run). A run-date absent from the GROUP BY result
    # had 0 rows that day -> .get(d, 0) preserves the prior _new_rows_on_date `int(val or 0)` semantics.
    _rows = await conn.fetch(
        f'SELECT "{date_col}" AS d, COUNT(*) AS n FROM "{table}" '
        f'WHERE "{date_col}" = ANY($1::date[]) GROUP BY "{date_col}"',
        run_dates,
    )
    _by_date = {r["d"]: int(r["n"] or 0) for r in _rows}
    counts = [_by_date.get(d, 0) for d in run_dates]
    verdict = _evaluate_job_liveness(counts, min_expected_rows, k)
    if verdict is None:
        return None
    return {
        "job_id": job_id,
        "table": table,
        "min_expected_rows": min_expected_rows,
        **verdict,
    }


def _format_job_flag(label_by_job: dict[str, str], f: dict[str, Any]) -> str:
    label = label_by_job.get(f["job_id"], f["job_id"])
    runs = f["empty_runs"]
    run_word = "run" if runs == 1 else "runs"
    return (
        f"• `{label}` ({f['job_id']}) ran but `{f['table']}` got "
        f"< {f['min_expected_rows']} rows for {runs} {run_word}"
    )


async def run_job_liveness_sweep(conn=None) -> dict[str, Any]:
    """Run the JOB → OUTPUT-LIVENESS sweep (PLAN #370 increment 3).

    For each curated (job, output-table) pair: did the job RUN successfully recently (mi_job_runs)?
    If so, did its output table get ≥ min_expected_rows NEW rows on the expected run-date(s)? A job
    that RAN but whose table got 0/too-few rows for its cadence window (K=1 always-on, K=3 quiet) is
    FLAGGED. A job that did NOT run is NOT flagged here (that's the heartbeat, increment 4).

    All flags are sent as ONE grouped Telegram; zero flags → audit-only (Telegram reserved for real
    failures). Robust by design — per-job try/except so one bad job can't kill the sweep; a health
    guard that itself fails silently is the worst failure.

    Args:
        conn: optional asyncpg connection. If None, acquires one from the shared pool.

    Returns:
        Summary dict: jobs_checked, flags (list), errors (list).
    """
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as acquired:
            return await run_job_liveness_sweep(acquired)

    label_by_job = {job_id: label for (job_id, label, *_rest) in _JOB_OUTPUT_CHECKS}
    all_flags: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    jobs_checked = 0

    for job_id, _label, table, date_col, min_rows, k in _JOB_OUTPUT_CHECKS:
        try:
            flag = await _check_job(conn, job_id, table, date_col, min_rows, k)
            jobs_checked += 1
            if flag is not None:
                all_flags.append(flag)
        except Exception as e:  # one bad job/table must not kill the sweep
            logger.warning("job_liveness_sweep: job %s (%s) failed: %s", job_id, table, e)
            errors.append({"job_id": job_id, "table": table, "error": str(e)})

    summary = {
        "jobs_checked": jobs_checked,
        "flags": all_flags,
        "errors": errors,
    }

    # ── Alert ────────────────────────────────────────────────────────────────────────────────
    if all_flags:
        header = f"🩺 JOB PRODUCED NOTHING ({len(all_flags)})"
        lines = [header, ""]
        lines.extend(_format_job_flag(label_by_job, f) for f in all_flags)
        lines.append("")
        lines.append("A scheduled job ran successfully but its output table stayed empty — it may "
                     "have silently stopped producing rows (PLAN #370).")
        body = "\n".join(lines)
        try:
            # Imported lazily so a Telegram/env issue can't break module import or tests.
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(body)
        except Exception as e:
            logger.warning("job_liveness_sweep: telegram send failed: %s", e)
            errors.append({"telegram": str(e)})

        detail = ", ".join(f"{f['job_id']}→{f['table']}" for f in all_flags)
        await log_audit_event(
            "health_job_liveness_flagged",
            f"{len(all_flags)} job(s) ran but produced nothing: {detail}",
            detail=str(summary),
        )
    else:
        # Zero flags → audit-only (do NOT Telegram a clean run — Telegram is for real failures).
        note = (
            f"clean: {jobs_checked} jobs checked"
            + (f"; {len(errors)} job error(s)" if errors else "")
        )
        await log_audit_event("health_job_liveness_clean", note, detail=str(summary))

    if errors:
        logger.warning("job_liveness_sweep completed with %d error(s): %s", len(errors), errors)

    # Persistence reconcile (#370 increment 2): nag job-liveness flags the K-consecutive cadence has
    # self-silenced but whose latest successful run is STILL empty (direct re-check). Internally robust.
    recon = await reconcile_health_flags(
        conn, "job_liveness", all_flags, _recheck_job_liveness_flag, key_fn=_job_flag_target_key)
    summary["persistence"] = {k: recon[k] for k in ("nagged", "resolved", "still_open")}

    return summary


# ══════════════════════════════════════════════════════════════════════════════════════════════
# INCREMENT 4 — the guard's own HEARTBEAT (`run_health_heartbeat`, PLAN #370). THE most important gap.
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# Increments 1 + 3 catch OTHER silent failures (a column going null, a job producing nothing). But
# they are themselves a single point of failure: BOTH run inside `_post_nightly_audit_job` (17:30 ET).
# If THAT job dies — the cron misfires, the job errors before it reaches the sweep calls, a deploy
# breaks the import — then NOTHING runs, and NOTHING alerts. The guard fails SILENTLY: the worst
# possible case, and exactly the class #370 exists to kill. The heartbeat detects "the guard itself
# hasn't run."
#
# WHAT IT CHECKS: the most-recent timestamp across the FOUR sweep audit events (the sweeps' own
# proof-of-life — `health_null_sweep_clean/flagged` + `health_job_liveness_clean/flagged`). Every
# successful 17:30 run writes at least one of these (each sweep ALWAYS logs clean-or-flagged at its
# end). So a fresh sweep audit == "the 17:30 job ran AND reached the sweeps". A missing/stale one ==
# the job died before producing any — whole-job death, which is the target. (A single sweep of the
# two dying is already covered by its own notify_job_failure in the scheduler; the heartbeat owns the
# both-dead / job-never-ran case the per-sweep guards structurally cannot see.) We filter to exactly
# those four event types so the heartbeat's OWN `health_heartbeat_ok` rows can never self-satisfy a
# later check (a heartbeat that proves itself alive off its own pulse is no heartbeat).
#
# INDEPENDENCE — the load-bearing design constraint: the heartbeat MUST run in a DIFFERENT scheduled
# job than the sweeps, or it dies WITH them and proves nothing. The sweeps live in
# `_post_nightly_audit_job` (17:30). The intended host is the MORNING BRIEFING job (`_morning_briefing_job`,
# 09:00 ET) — an independent, reliably-firing job ~15.5h after the sweeps. This function is
# host-AGNOSTIC (takes only a conn); the wiring is the operator's. HARD RULE: do NOT call it from
# `_post_nightly_audit_job` — co-locating it there re-creates the single point of failure it exists to
# remove.
#
# THE THRESHOLD — trading-day-aware, NOT a flat 26h (the make-or-break, advisor-refined). The sweep
# host is a mon-fri cron (`day_of_week="mon-fri"`), so NO sweep runs Sat/Sun. A flat 26h threshold
# would false-fire EVERY Monday morning (the most-recent sweep would be Friday 17:30 ≈ 63h ago, on a
# perfectly healthy system) — the exact "noisy guard gets muted then misses the real failure" trap
# increments 1+3 obsessed over. There is no flat value that both catches a missed WEEKNIGHT (needs
# ≤ ~39h) and survives MONDAY (needs > 63h). So instead of wall-clock age we compute the cutoff =
# the most-recent expected sweep run, and ALERT iff no sweep audit landed at/after it.
#
# The cutoff is PLAIN WEEKDAY ARITHMETIC, deliberately NOT the trading calendar (advisor-corrected):
# the sweep host is a holiday-BLIND mon-fri cron ("runs mon-fri incl. holidays", per the increment-3
# comment) — the sweeps EXECUTE and write a clean audit every weekday, holiday or not. So we expect a
# sweep audit every weekday and must MATCH THE CRON, not the market. Using `get_market_status` would
# skip weekday holidays (a sweep dying Thanksgiving evening wouldn't be caught Friday morning — a blind
# spot on exactly #370's failure class). Weekday math catches it next morning, with no calendar import.

# The four sweep audit event types — the sweeps' proof-of-life. A fresh row of ANY of these means the
# 17:30 job ran and reached the sweep calls. NOT including health_heartbeat_* (those are THIS job's own
# pulse and must never self-satisfy the check).
_SWEEP_AUDIT_EVENTS: list[str] = [
    "health_null_sweep_clean",
    "health_null_sweep_flagged",
    "health_job_liveness_clean",
    "health_job_liveness_flagged",
]

_SWEEP_HOUR = 17    # the sweep host (_post_nightly_audit_job) fires at 17:30 ET
_SWEEP_MINUTE = 30


def _expected_sweep_cutoff(now_et: datetime) -> datetime:
    """The most-recent expected sweep run (a mon-fri 17:30 ET) STRICTLY before `now_et`.

    Pure date math (no calendar import) so it's trivially mock-free testable and matches the sweep
    host's holiday-BLIND mon-fri cron exactly. A sweep audit at/after this cutoff == the 17:30 job
    ran on schedule; nothing at/after == it died.

    Walk back from today@17:30: if that instant is not strictly in the past, step a day; then roll any
    Saturday/Sunday back to Friday (no sweep runs on the weekend). Examples (all ET):
      - Tue 09:00  → Mon 17:30   (last night's sweep; ~15.5h, normal)
      - Mon 09:00  → Fri 17:30   (weekend gap auto-widens; would be ~63h — NOT a false fire)
      - Wed 18:00  → Wed 17:30   (tonight's sweep already due+past)
    """
    cutoff = now_et.replace(hour=_SWEEP_HOUR, minute=_SWEEP_MINUTE, second=0, microsecond=0)
    if cutoff >= now_et:
        cutoff -= timedelta(days=1)        # today's 17:30 hasn't happened yet → expect yesterday's
    while cutoff.weekday() >= 5:           # 5=Sat, 6=Sun — no sweep ran; roll back to Friday
        cutoff -= timedelta(days=1)
    return cutoff


def _evaluate_heartbeat(latest_ts: datetime | None, cutoff: datetime) -> dict[str, Any] | None:
    """Pure decision: given the most-recent sweep-audit timestamp (or None) and the expected cutoff,
    decide whether the guard has gone dark.

    Returns a flag dict (reason) when the guard is dead, None when it's alive. Isolated + mock-free so
    cases 1-3 test directly:
      - latest_ts is None          → flag "never"   (the guard has NEVER run / its audit is broken)
      - latest_ts < cutoff         → flag "stale"   (no sweep audit since the last expected 17:30 run)
      - latest_ts >= cutoff        → None           (the guard ran on schedule — alive)
    """
    if latest_ts is None:
        return {"reason": "never", "latest_ts": None}
    if latest_ts < cutoff:
        return {"reason": "stale", "latest_ts": latest_ts}
    return None


def _now_et() -> datetime:
    """tz-aware now() in ET. Isolated so tests can monkeypatch it without touching the clock."""
    return datetime.now(_ET)


async def run_health_heartbeat(conn=None) -> dict[str, Any]:
    """Run the guard's own HEARTBEAT (PLAN #370 increment 4) — detect "the silent-failure guard
    itself hasn't run".

    Queries the most-recent timestamp across the four sweep audit events. If the latest is OLDER than
    the expected cutoff (the most-recent mon-fri 17:30 ET) — or there is NO sweep audit at all — the
    guard has gone dark → ONE grouped Telegram. If fresh → audit-only (`health_heartbeat_ok`).

    INDEPENDENCE: must be hosted in a DIFFERENT scheduled job than the sweeps (intended: the 09:00
    morning briefing). Do NOT call from `_post_nightly_audit_job` — that would re-create the single
    point of failure this exists to remove.

    LOUD ON FAILURE (deliberately the OPPOSITE of the sweeps' swallow-and-report-clean pattern): if the
    DB query / check itself throws, we send a DEGRADED Telegram, log at ERROR, and write a
    `health_heartbeat_error` audit — we NEVER fall through to `health_heartbeat_ok`. A heartbeat that
    cannot check must not pretend everything is fine; a silent heartbeat is the worst failure of all.

    Args:
        conn: optional asyncpg connection. If None, acquires one from the shared pool.

    Returns:
        Summary dict: status ("ok" | "alert" | "error"), latest_ts (iso str | None), cutoff (iso str).
    """
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as acquired:
            return await run_health_heartbeat(acquired)

    now_et = _now_et()
    cutoff = _expected_sweep_cutoff(now_et)

    # ── The check itself — LOUD on failure (never silently "ok") ──────────────────────────────────
    try:
        latest_ts = await conn.fetchval(
            """
            SELECT MAX(created_at)
            FROM mi_audit_log
            WHERE event_type = ANY($1::text[])
            """,
            _SWEEP_AUDIT_EVENTS,
        )
    except Exception as e:
        # A heartbeat that can't run its own check must FAIL LOUD, not pretend healthy.
        logger.error("health_heartbeat: check FAILED (cannot verify guard liveness): %s", e,
                     exc_info=True)
        body = (
            "🩺 SILENT-FAILURE GUARD HEARTBEAT BROKEN — the heartbeat itself could not query the "
            f"audit log ({type(e).__name__}). It cannot confirm the health sweeps are alive; treat "
            "the guard as UNVERIFIED (PLAN #370)."
        )
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(body)
        except Exception as te:  # even the degraded alert failed — log, but do NOT report ok
            logger.error("health_heartbeat: degraded telegram ALSO failed: %s", te)
        try:
            await log_audit_event(
                "health_heartbeat_error",
                f"heartbeat check failed: {type(e).__name__}: {e}",
                detail=str({"cutoff": cutoff.isoformat()}),
            )
        except Exception as ae:
            logger.error("health_heartbeat: error-audit write ALSO failed: %s", ae)
        return {"status": "error", "latest_ts": None, "cutoff": cutoff.isoformat(),
                "error": str(e)}

    # Normalize the timestamp to ET so the < comparison is tz-consistent (created_at is TIMESTAMPTZ;
    # asyncpg returns it tz-aware, but normalize defensively in case of a naive value).
    if latest_ts is not None and latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=_ET)

    verdict = _evaluate_heartbeat(latest_ts, cutoff)
    latest_iso = latest_ts.isoformat() if latest_ts is not None else None
    summary = {
        "status": "ok" if verdict is None else "alert",
        "latest_ts": latest_iso,
        "cutoff": cutoff.isoformat(),
    }

    # ── Alert ─────────────────────────────────────────────────────────────────────────────────────
    if verdict is not None:
        if verdict["reason"] == "never":
            headline = "🩺 SILENT-FAILURE GUARD HASN'T RUN — EVER"
            detail_line = ("there is NO health-sweep audit at all — the guard has never run, or its "
                          "audit log is broken.")
        else:
            age_hours = round((now_et - latest_ts).total_seconds() / 3600)
            headline = f"🩺 SILENT-FAILURE GUARD HASN'T RUN in {age_hours}h"
            detail_line = (
                f"the last health-sweep audit was {age_hours}h ago (before the expected "
                f"{cutoff.strftime('%a %H:%M')} ET run) — the 17:30 sweeps may be DEAD."
            )
        body = (
            f"{headline} — {detail_line} The health sweeps that catch silent failures appear to have "
            "stopped; the system is currently BLIND to the silent-failure class (PLAN #370). Check "
            "the 17:30 post-nightly audit job."
        )
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(body)
        except Exception as e:
            logger.error("health_heartbeat: telegram send failed on a REAL alert: %s", e)
            summary["telegram_error"] = str(e)

        await log_audit_event(
            "health_heartbeat_stale",
            f"guard liveness ALERT ({verdict['reason']}): latest sweep audit {latest_iso}, "
            f"expected ≥ {cutoff.isoformat()}",
            detail=str(summary),
        )
    else:
        # Fresh → audit-only (do NOT Telegram a healthy heartbeat — Telegram is for real failures).
        await log_audit_event(
            "health_heartbeat_ok",
            f"guard alive: latest sweep audit {latest_iso} ≥ cutoff {cutoff.isoformat()}",
            detail=str(summary),
        )

    return summary


# ══════════════════════════════════════════════════════════════════════════════════════════════
# INCREMENT 2 — PERSISTENCE-TRACKING (the SELF-POISON fix, PLAN #370). The operator's exact pain.
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# THE GAP (the KNOWN LIMITATION documented in increment 1's docstring + pinned by
# test_persistent_null_self_silences_known_limitation): the null-rate sweep alerts DAY-1/2 of a
# silent null, then SELF-SILENCES. As the persisting null walks into its own rolling 30-date
# baseline, the baseline non-null rate drops below 95% and the alert goes quiet. The 200MA was null
# for ~3 WEEKS; the sweep catches it day-1 then goes dark — the EXACT "looked fine for weeks" mode
# #370 exists to kill. (Identical shape for job-liveness: K consecutive empty run-dates flag, then
# as the broken run-dates age out of the K-window the sweep quiets while the job stays dead.)
#
# THE FIX: a STATE table (`mi_health_open_flags`) + a DIRECT re-check that is DECOUPLED from the
# rolling baseline. Each sweep, AFTER it computes its current flags, calls `reconcile_health_flags`:
#   (a) UPSERT each current flag → state ('open'; first_flagged set on insert, kept on update).
#   (b) For each OPEN state row of this check_kind whose target is NOT in current_flags, it either
#       RESOLVED (the column repopulated / the job produced rows) OR SELF-POISONED (the rolling
#       baseline went quiet but the underlying break PERSISTS). We DISTINGUISH by calling
#       `recheck_fn(target_key)` — the CRUX — which checks the UNDERLYING condition DIRECTLY (latest
#       row still null? latest successful run-date still empty?), NOT the baseline. Still-broken →
#       keep 'open' + re-alert on a once/day cadence (the persistence-nag); healthy → 'resolved'.
#
# WHY THE DIRECT RE-CHECK IS THE WHOLE POINT (and must NOT reuse the baseline-gated evaluators):
# `_evaluate_column` / `_evaluate_job_liveness` carry the ≥95%-over-30d / K-consecutive baseline
# gate that is EXACTLY what self-poisons. A recheck that reused them would self-silence in lockstep
# with the sweep → the persistence-nag would be a silent no-op. So the recheck fns below read ONLY
# the latest-date condition (fractions[0] == 0.0 for null; latest run-date count < min for job),
# reusing the sweep's data-pulling primitives but NONE of its baseline decision logic.
#
# CADENCE: a still-open flag re-alerts at most ONCE PER ET DAY (last_alerted < today → nag + bump).
# Not every run = no spam; not never = the whole point. The day a flag self-poisons out of
# current_flags, the sweep goes silent and reconcile becomes the SOLE alerter → ≤1 Telegram/target/day.

# Re-alert cadence: a persistent open flag re-nags at most once per ET day (compared on last_alerted).
_NAG_CADENCE_DAYS = 1


# ── The CRUX: the two CONCRETE direct re-check fns. ──────────────────────────────────────────────
# Each takes (conn, target_key) and returns True iff the UNDERLYING condition is STILL broken, by
# reading the LATEST-DATE condition DIRECTLY — never the rolling baseline (that is what self-poisons).
# The operator threads these into the sweeps as the recheck_fn for their check_kind.


def _parse_null_target(target_key: str) -> tuple[str, str]:
    """'mi_market_regime.spy_vs_200ma' → ('mi_market_regime', 'spy_vs_200ma'). rsplit on the LAST
    dot so a column containing no dot is safe (table names here never contain a dot)."""
    table, column = target_key.rsplit(".", 1)
    return table, column


def _parse_job_target(target_key: str) -> tuple[str, str]:
    """'theme_synthesis:mi_theme_candidates_shadow' → ('theme_synthesis', 'mi_theme_candidates_shadow')."""
    job_id, table = target_key.split(":", 1)
    return job_id, table


async def _recheck_null_flag(conn, target_key: str) -> bool:
    """DIRECT re-check for a null_sweep flag: is `table.column` STILL entirely null in its LATEST date?

    The crux of the self-poison fix. We pull the per-date non-null fractions (reusing the sweep's own
    `_per_date_fractions`) but apply ONLY the latest-date trigger (`fractions[0] == 0.0`) — we do NOT
    call `_evaluate_column`, whose ≥95%-baseline gate is the very thing that self-silences once the
    null has aged into the baseline. The date_col comes from `_NULL_SWEEP_TABLES` so the direct check
    can't drift from what the sweep checks. Returns True = still broken (keep nagging), False = healthy.
    """
    table, column = _parse_null_target(target_key)
    date_col = next((dc for (t, dc) in _NULL_SWEEP_TABLES if t == table), None)
    if date_col is None:
        # Target not in the swept-tables config — can't re-check directly. Conservative: treat as
        # still-broken (keep-open) so a config gap can't silently RESOLVE a real break.
        logger.warning("recheck_null_flag: %s not in _NULL_SWEEP_TABLES — keeping open", table)
        return True
    date_rows = await _per_date_fractions(conn, table, date_col, [column])
    fractions = _fractions_for_column(date_rows, column)
    if not fractions:
        # No rows at all for this table/date → the latest date produced nothing. That's a job-liveness
        # concern, not a null-fill; we can't confirm a fill, so keep-open (don't silently resolve).
        return True
    return fractions[0] == 0.0  # latest date STILL entirely null → still broken


async def _recheck_job_liveness_flag(conn, target_key: str) -> bool:
    """DIRECT re-check for a job_liveness flag: did the job's LATEST successful run-date STILL produce
    fewer than min_expected_rows?

    Decoupled from the sweep's K-consecutive cadence gate (which self-silences as broken run-dates age
    out of the K-window). We look ONLY at the most-recent successful trading-day run-date and ask "did
    that run produce rows?" — reusing `_successful_run_dates` + `_new_rows_on_date`, never
    `_evaluate_job_liveness`. min_expected_rows/date_col come from `_JOB_OUTPUT_CHECKS`. Returns True =
    still broken (latest run still empty), False = healthy (the job produced rows again).
    """
    job_id, table = _parse_job_target(target_key)
    cfg = next((c for c in _JOB_OUTPUT_CHECKS if c[0] == job_id and c[2] == table), None)
    if cfg is None:
        logger.warning("recheck_job_liveness_flag: %s not in _JOB_OUTPUT_CHECKS — keeping open",
                       target_key)
        return True  # config gap → conservative keep-open (never silently resolve a real break)
    _job_id, _label, _table, date_col, min_rows, _k = cfg
    run_dates = await _successful_run_dates(conn, job_id, limit=1)
    if not run_dates:
        # No recent successful run to judge against → can't confirm the job produced output. Keep-open
        # (a non-running job is heartbeat's concern, but we must not silently resolve a persisted break).
        return True
    count = await _new_rows_on_date(conn, table, date_col, run_dates[0])
    return count < min_rows  # latest successful run STILL produced too few rows → still broken


# ── The reconcile driver: UPSERT current flags + nag/resolve persisted ones. ─────────────────────


def _null_flag_target_key(f: dict[str, Any]) -> str:
    """Stable target_key for a null_sweep flag dict: 'table.column'."""
    return f"{f['table']}.{f['column']}"


def _job_flag_target_key(f: dict[str, Any]) -> str:
    """Stable target_key for a job_liveness flag dict: 'job_id:table'."""
    return f"{f['job_id']}:{f['table']}"


async def reconcile_health_flags(
    conn,
    check_kind: str,
    current_flags: list[dict[str, Any]],
    recheck_fn,
    *,
    key_fn,
    detail_fn=None,
) -> dict[str, Any]:
    """Persistence-tracking reconcile for ONE check_kind (PLAN #370 increment 2) — the self-poison fix.

    Called by a sweep AFTER it computes `current_flags`. Two passes, both scoped to `check_kind`:
      (a) UPSERT each current flag → `mi_health_open_flags` (status='open'; first_flagged set on
          INSERT, kept on open→open UPDATE, RESET on resolved→open re-break). No alert here — the
          sweep already day-1/2 alerts everything in current_flags; we just record state.
      (b) For each OPEN row of this check_kind whose target is NOT in current_flags: call
          `recheck_fn(conn, target_key)` — the DIRECT, baseline-decoupled re-check.
            still-broken → keep 'open'; re-alert at most once/ET-day (the persistence-nag).
            healthy      → mark 'resolved' (optional ✅ recovered note).
          recheck_fn raising → KEEP OPEN + log (never silently resolve on a broken re-check — that
          would re-introduce the exact silent failure this increment kills).

    Args:
        check_kind:    'null_sweep' | 'job_liveness' — scopes every query (a null reconcile must not
                       touch job rows).
        current_flags: the flag dicts the sweep just produced (may be empty — a clean sweep still must
                       nag persisted flags + resolve fixed ones).
        recheck_fn:    async (conn, target_key) -> bool. True = still broken. The CRUX.
        key_fn:        flag dict -> target_key (`_null_flag_target_key` / `_job_flag_target_key`).
        detail_fn:     optional flag dict -> detail str stored on the state row.

    Returns: summary dict {upserted, nagged, resolved, still_open, errors} for the caller's audit.

    Robust by design: the whole body is wrapped so a reconcile failure can NEVER take down the sweep
    that called it (a health guard whose own bookkeeping crashes the guard is the worst failure).
    """
    summary: dict[str, Any] = {
        "check_kind": check_kind,
        "upserted": 0, "nagged": 0, "resolved": 0, "still_open": 0,
        "nags": [], "resolutions": [], "errors": [],
    }
    try:
        today = et_today()
        current_keys: set[str] = set()

        # ── (a) UPSERT current flags ──────────────────────────────────────────────────────────────
        for f in current_flags:
            key = key_fn(f)
            current_keys.add(key)
            detail = detail_fn(f) if detail_fn else ""
            # first_flagged: today on INSERT; kept on open→open; RESET to today on resolved→open
            # (a re-break after a healthy gap shouldn't report an inflated "STILL BROKEN (Nd)").
            await conn.execute(
                """
                INSERT INTO mi_health_open_flags
                    (check_kind, target_key, first_flagged, last_alerted, status, detail, updated_at)
                VALUES ($1, $2, $3, NULL, 'open', $4, NOW())
                ON CONFLICT (check_kind, target_key) DO UPDATE SET
                    status = 'open',
                    detail = EXCLUDED.detail,
                    updated_at = NOW(),
                    first_flagged = CASE
                        WHEN mi_health_open_flags.status = 'resolved' THEN EXCLUDED.first_flagged
                        ELSE mi_health_open_flags.first_flagged
                    END
                """,
                check_kind, key, today, detail,
            )
            summary["upserted"] += 1

        # ── (b) Reconcile OPEN rows NOT in current_flags: nag (still-broken) or resolve (healthy) ──
        open_rows = await conn.fetch(
            """
            SELECT target_key, first_flagged, last_alerted, detail
            FROM mi_health_open_flags
            WHERE check_kind = $1 AND status = 'open'
            """,
            check_kind,
        )
        for row in open_rows:
            target_key = row["target_key"]
            if target_key in current_keys:
                continue  # still in current_flags → the sweep is alerting it; reconcile (a) handled it

            # The CRUX: DIRECT re-check, decoupled from the rolling baseline that self-poisoned.
            try:
                still_broken = await recheck_fn(conn, target_key)
            except Exception as e:  # a broken re-check must KEEP-OPEN, never silently resolve
                logger.warning("reconcile_health_flags: recheck %s/%s failed: %s — keeping open",
                               check_kind, target_key, e)
                summary["errors"].append({"target_key": target_key, "error": str(e)})
                summary["still_open"] += 1
                continue

            if still_broken:
                summary["still_open"] += 1
                last_alerted = row["last_alerted"]
                due = last_alerted is None or (today - last_alerted).days >= _NAG_CADENCE_DAYS
                if due:
                    days_open = (today - row["first_flagged"]).days + 1  # day-1 reads as "1d"
                    await _send_persistence_nag(check_kind, target_key, days_open, row["first_flagged"])
                    await conn.execute(
                        """
                        UPDATE mi_health_open_flags SET last_alerted = $3, updated_at = NOW()
                        WHERE check_kind = $1 AND target_key = $2
                        """,
                        check_kind, target_key, today,
                    )
                    summary["nagged"] += 1
                    summary["nags"].append({"target_key": target_key, "days_open": days_open})
            else:
                # The underlying condition healed → resolve + optional ✅ recovered note.
                await conn.execute(
                    """
                    UPDATE mi_health_open_flags SET status = 'resolved', updated_at = NOW()
                    WHERE check_kind = $1 AND target_key = $2
                    """,
                    check_kind, target_key,
                )
                summary["resolved"] += 1
                summary["resolutions"].append(target_key)
                await _send_recovery_note(check_kind, target_key)

    except Exception as e:  # reconcile must NEVER take down the sweep that called it
        logger.warning("reconcile_health_flags: %s reconcile failed: %s", check_kind, e)
        summary["errors"].append({"reconcile": str(e)})

    return summary


async def _send_persistence_nag(check_kind: str, target_key: str, days_open: int, first_flagged) -> None:
    """The persistence-nag Telegram — a STILL-BROKEN flag the rolling sweep has gone quiet on.
    Names the target + days-open + since-date. Lazy import so a Telegram issue can't break tests."""
    body = (
        f"🩺 STILL BROKEN ({days_open}d): `{target_key}` "
        f"{'null' if check_kind == 'null_sweep' else 'producing nothing'} since "
        f"{first_flagged.isoformat() if hasattr(first_flagged, 'isoformat') else first_flagged}. "
        "The rolling-baseline sweep self-silenced, but a direct re-check confirms it's STILL "
        "broken (PLAN #370). It will keep nagging daily until the underlying signal repopulates."
    )
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(body)
    except Exception as e:
        logger.warning("persistence_nag: telegram send failed for %s: %s", target_key, e)


async def _send_recovery_note(check_kind: str, target_key: str) -> None:
    """Optional ✅ recovered note when a persisted flag's underlying condition heals. Best-effort."""
    body = (
        f"✅ recovered: `{target_key}` "
        f"({'column repopulated' if check_kind == 'null_sweep' else 'job producing rows again'}) "
        "— a direct re-check confirms the silent break is fixed (PLAN #370)."
    )
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(body)
    except Exception as e:
        logger.warning("recovery_note: telegram send failed for %s: %s", target_key, e)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ROW-COUNT DRIFT sweep (#340) — the delta-check that replaces trusting a FROZEN floor
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# `audit_run(job_id, expected_min_rows=N)` compares each run against a HAND-PINNED N. That
# constant rots, and its rot is silent in the worst direction: when the real distribution steps
# DOWN for a legitimate reason, the job sits `empty_result` forever and the red light stops
# meaning anything. Twice now:
#   • #263 (2026-06-10) 5000 → 3500 after a universe change.
#   • #286 (2026-06-15) added a liquidity floor: nightly rows 3,888-4,008 → 2,467-2,530. The
#     stale 3500 pin left `nightly_data_pull` empty_result EVERY market day for 2+ WEEKS — a
#     permanently-red signal nobody read — until it was recalibrated 3500 → 2200 on 7/02.
#
# Operator's design (#340): alert on a >X% night-over-night DROP vs the TRAILING MEDIAN rather
# than vs a frozen baseline — catches a genuine collapse AND auto-adapts to an intended step
# without the deadlock, plus a one-time transition note so an intended step-down is NOTED once
# rather than silent.
#
# TWO signals, because they catch opposite failures:
#   A. DROP        — latest run is >DROP_PCT below the trailing median → the data broke.
#   B. STALE FLOOR — the job keeps tripping `empty_result` while its row counts are STABLE →
#                    the PIN is wrong, not the data. This is the #286 class specifically, and
#                    signal A alone would never catch it: after the step, the new level becomes
#                    the median and the drop check goes quiet — correctly — while the frozen pin
#                    stays red forever. B is what turns 2+ weeks of unread red into one alert.
#
# ADDITIVE, deliberately. `expected_min_rows` stays as the absolute-catastrophe floor (it catches
# a 0-row run on day one, before any median exists). Signal A is the sensitive relative check;
# together they cover sudden collapse, slow rot, and miscalibration. Removing the pin in favour
# of the median alone would lose the cold-start guarantee.
#
# Calibration against the real incident: the #286 step was −36.5% (3,888 → 2,467); ordinary
# wobble INSIDE the post-step band (2,467-2,530) is ~2.5%. DROP_PCT = 25% sits well clear of the
# noise and well under the real step. `_MIN_HISTORY` keeps a thin history from alerting at all.

_ROWCOUNT_DROP_PCT = 0.25      # >25% below the trailing median → flag
# ⚠ Added 2026-08-01 after the FIRST live run, which found exactly one "drop": `shadow_orb_entry`
# at 0 rows vs a median of 1 = a 100% collapse. It was a Saturday. On a job that normally writes
# a single row, any quiet day is a 100% drop — pure noise, and noise is how a guard gets muted
# and then misses the real failure (the calibration risk this file already warns about). A
# percentage is only meaningful once the median is big enough for a percentage to mean anything;
# below this, the ABSOLUTE `expected_min_rows` floor is the right instrument and already runs.
_ROWCOUNT_MIN_MEDIAN = 20      # medians under this are too small for a % drop to carry signal
_ROWCOUNT_MIN_HISTORY = 5      # need this many prior runs before the median means anything
_ROWCOUNT_WINDOW = 10          # trailing runs forming the median
_STALE_FLOOR_MIN_RUNS = 3      # consecutive empty_results before we suspect the PIN
_STALE_FLOOR_STABILITY = 0.10  # ...and only if those runs' spread is within 10% of their median


async def run_row_count_drift_sweep() -> dict[str, Any]:
    """#340 — flag row-count DROPS against a trailing median, and PINS that have gone stale.

    Returns `{"jobs_scanned": n, "drops": [...], "stale_floors": [...], "errors": [...]}`.
    Never raises: a health guard that dies silently is the failure it exists to prevent.
    """
    out: dict[str, Any] = {"jobs_scanned": 0, "drops": [], "stale_floors": [], "errors": []}
    try:
        pool = await get_pool()
        async with pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT job_id, started_at, status, rows_written, expected_min_rows
                FROM mi_job_runs
                WHERE rows_written IS NOT NULL
                  AND started_at >= NOW() - INTERVAL '45 days'
                ORDER BY job_id, started_at DESC
                """
            )
    except Exception as e:
        logger.error("row_count_drift: query failed: %s", e, exc_info=True)
        out["errors"].append(f"query: {e}")
        return out

    by_job: dict[str, list] = {}
    for r in rows:
        by_job.setdefault(r["job_id"], []).append(r)

    for job_id, runs in by_job.items():
        try:
            out["jobs_scanned"] += 1
            counts = [int(r["rows_written"]) for r in runs]      # newest first
            latest, history = counts[0], counts[1:1 + _ROWCOUNT_WINDOW]
            if len(history) < _ROWCOUNT_MIN_HISTORY:
                continue                                          # thin history → cannot judge

            median = statistics.median(history)
            if median >= _ROWCOUNT_MIN_MEDIAN and latest < median * (1 - _ROWCOUNT_DROP_PCT):
                out["drops"].append({
                    "job_id": job_id, "latest": latest, "median": median,
                    "drop_pct": round((1 - latest / median) * 100, 1),
                    "at": runs[0]["started_at"],
                })

            # Signal B — the pin, not the data. Consecutive empty_results whose row counts are
            # TIGHT means the job is producing a stable new normal that the pin no longer admits.
            leading = 0
            for r in runs:
                if r["status"] != "empty_result":
                    break
                leading += 1
            if leading >= _STALE_FLOOR_MIN_RUNS:
                s_counts = counts[:leading]
                s_med = statistics.median(s_counts)
                spread = (max(s_counts) - min(s_counts)) / s_med if s_med else 1.0
                if spread <= _STALE_FLOOR_STABILITY:
                    out["stale_floors"].append({
                        "job_id": job_id, "consecutive": leading,
                        "stable_at": int(s_med),
                        "expected_min_rows": runs[0]["expected_min_rows"],
                        "spread_pct": round(spread * 100, 1),
                    })
        except Exception as e:                       # one bad job must not kill the sweep
            logger.warning("row_count_drift: job %s failed: %s", job_id, e)
            out["errors"].append(f"{job_id}: {e}")

    await _emit_row_count_drift(out)
    return out


async def _emit_row_count_drift(out: dict[str, Any]) -> None:
    """Audit row always; ONE grouped Telegram only when there is something to act on."""
    try:
        await log_audit_event(
            "row_count_drift_sweep",
            f"{out['jobs_scanned']} jobs · {len(out['drops'])} drop(s) · "
            f"{len(out['stale_floors'])} stale floor(s) · {len(out['errors'])} error(s)",
            json.dumps(out, default=str),
        )
    except Exception as e:
        logger.warning("row_count_drift: audit log failed: %s", e)

    if not out["drops"] and not out["stale_floors"]:
        return                                    # Telegram is reserved for real failures
    lines = ["*Row-count drift*", "```"]
    for d in out["drops"]:
        lines.append(f"DROP  {d['job_id']}: {d['latest']} vs median {int(d['median'])} "
                     f"(-{d['drop_pct']}%)")
    for s in out["stale_floors"]:
        lines.append(f"PIN?  {s['job_id']}: {s['consecutive']} straight empty_result at a stable "
                     f"~{s['stable_at']} rows (pin {s['expected_min_rows']}) — recalibrate")
    lines.append("```")
    if out["stale_floors"]:
        lines.append("_PIN? = the floor looks stale, not the data — this is the #286 class._")
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.warning("row_count_drift: telegram send failed: %s", e)

# ── DB-GROWTH CHECK (2026-08-15 capture audit) ────────────────────────────────────────────────
#
# WHY. The capture audit relaxed retention (mi_ep_alerts kept forever, mi_intraday_bars 120d → 5y,
# minute bars now persisted for every alert ticker-day) on measured storage maths: whole DB 1.2 GB,
# planned growth ~1.3-1.7 GB/yr, 58 GB free. The operator's condition: unbounded retention must not
# be able to SURPRISE us. This check makes the maths a standing measurement instead of a one-off.
#
# HOW IT DECIDES TO SPEAK (a guard that always fires is not a guard): every night it records DB
# size + the largest tables as a `db_growth_check` audit row — the audit log IS the baseline store,
# no new table (the inert-sweep/theme-quality idiom). It compares against its own row from ~a week
# ago and Telegrams ONLY when the pro-rated weekly growth exceeds _DB_GROWTH_ALERT_BYTES (~10x the
# planned ~30 MB/wk — legit spikes like a heavy earnings week ≈ 30 MB or a one-off backfill ≈
# 100-200 MB stay under it) OR total size crosses _DB_SIZE_CEILING_BYTES (half the disk headroom —
# the "someone should look regardless of rate" line). First week (no baseline yet) → audit row
# only, silent. A firing that persists re-announces at most weekly (_DB_GROWTH_DEDUPE_DAYS).
_DB_GROWTH_MIN_BASELINE_AGE_DAYS = 6      # newest own row at least this old = the comparison point
_DB_GROWTH_MAX_BASELINE_AGE_DAYS = 45     # older than this (long downtime) → treat as no baseline
_DB_GROWTH_ALERT_BYTES = 300 * 1024**2    # pro-rated PER-WEEK growth above this speaks
_DB_SIZE_CEILING_BYTES = 30 * 1024**3     # absolute size above this speaks regardless of rate
_DB_GROWTH_DEDUPE_DAYS = 6                # a persisting condition re-announces at most weekly
_DB_GROWTH_TOP_TABLES = 8


def _evaluate_db_growth(
    current_bytes: int, baseline_bytes: int | None, baseline_age_days: float | None,
) -> dict[str, Any] | None:
    """Pure decision, isolated so it is testable mock-free (the file's idiom).

    Returns a flag dict or None. Growth is pro-rated to a 7-day rate because the
    baseline row's age floats (~6-45 days after downtime) — 300 MB over 6 weeks
    is on-plan, 300 MB over 6 days is 10x plan.
    """
    if current_bytes > _DB_SIZE_CEILING_BYTES:
        return {"kind": "ceiling", "current_bytes": current_bytes,
                "ceiling_bytes": _DB_SIZE_CEILING_BYTES}
    if (
        baseline_bytes is None or baseline_age_days is None
        or baseline_age_days < _DB_GROWTH_MIN_BASELINE_AGE_DAYS
        or baseline_age_days > _DB_GROWTH_MAX_BASELINE_AGE_DAYS
    ):
        return None                      # no usable baseline yet → measure, stay silent
    weekly_growth = (current_bytes - baseline_bytes) * 7.0 / baseline_age_days
    if weekly_growth > _DB_GROWTH_ALERT_BYTES:
        return {"kind": "growth", "current_bytes": current_bytes,
                "baseline_bytes": baseline_bytes,
                "baseline_age_days": round(baseline_age_days, 1),
                "weekly_growth_bytes": int(weekly_growth)}
    return None


def _fmt_bytes(n: int | float) -> str:
    """Plain-words sizes for the operator message (no raw byte counts)."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


async def run_db_growth_check() -> dict[str, Any]:
    """Nightly DB size + largest-tables recorder; speaks only when growth is out of line.

    Returns {"db_bytes": n, "tables": {...}, "flag": dict|None, "spoke": bool, "errors": [...]}.
    Never raises — a health guard that dies silently is the failure it exists to prevent.
    """
    out: dict[str, Any] = {"db_bytes": None, "tables": {}, "flag": None,
                           "spoke": False, "errors": []}
    try:
        pool = await get_pool()
        async with pool.acquire() as c:
            out["db_bytes"] = int(await c.fetchval(
                "SELECT pg_database_size(current_database())"))
            rows = await c.fetch(
                """
                SELECT c.relname AS t, pg_total_relation_size(c.oid) AS b
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                ORDER BY pg_total_relation_size(c.oid) DESC
                LIMIT $1
                """, _DB_GROWTH_TOP_TABLES)
            out["tables"] = {r["t"]: int(r["b"]) for r in rows}
            baseline = await c.fetchrow(
                """
                SELECT created_at, detail FROM mi_audit_log
                WHERE event_type = 'db_growth_check'
                  AND created_at <= NOW() - make_interval(days => $1)
                ORDER BY created_at DESC LIMIT 1
                """, _DB_GROWTH_MIN_BASELINE_AGE_DAYS)
    except Exception as e:
        logger.error("db_growth_check: measurement failed: %s", e, exc_info=True)
        out["errors"].append(f"measure: {e}")
        return out

    baseline_bytes: int | None = None
    baseline_age_days: float | None = None
    baseline_tables: dict[str, int] = {}
    if baseline is not None:
        try:
            detail = baseline["detail"]
            payload = json.loads(detail) if isinstance(detail, str) else (detail or {})
            baseline_bytes = int(payload["db_bytes"])
            baseline_tables = {k: int(v) for k, v in (payload.get("tables") or {}).items()}
            baseline_age_days = (
                datetime.now(_ET) - baseline["created_at"].astimezone(_ET)
            ).total_seconds() / 86400.0
        except (KeyError, TypeError, ValueError) as e:
            out["errors"].append(f"baseline parse: {e}")  # measure + record anyway

    out["flag"] = _evaluate_db_growth(out["db_bytes"], baseline_bytes, baseline_age_days)

    # Record tonight's measurement — this row IS next week's baseline, so it must
    # be written on every run, flagged or not, before any announce decision.
    try:
        await log_audit_event(
            "db_growth_check",
            f"db {_fmt_bytes(out['db_bytes'])}"
            + (f" · +{_fmt_bytes(out['db_bytes'] - baseline_bytes)}"
               f"/{baseline_age_days:.0f}d" if baseline_bytes is not None
               and baseline_age_days is not None else " · no baseline yet"),
            json.dumps({"db_bytes": out["db_bytes"], "tables": out["tables"]}),
        )
    except Exception as e:
        logger.warning("db_growth_check: audit log failed: %s", e)
        out["errors"].append(f"audit: {e}")

    if out["flag"] is None:
        return out

    # Dedupe: a condition that persists (especially the ceiling) must not become
    # nightly wallpaper — re-announce at most weekly. Fails OPEN (a dedupe-read
    # failure only risks a duplicate alert, never a missed one).
    try:
        pool = await get_pool()
        async with pool.acquire() as c:
            recent = await c.fetchval(
                """
                SELECT count(*) FROM mi_audit_log
                WHERE event_type = 'db_growth_alert'
                  AND created_at >= NOW() - make_interval(days => $1)
                """, _DB_GROWTH_DEDUPE_DAYS)
        if recent:
            return out
    except Exception as e:
        logger.warning("db_growth_check: dedupe read failed (will announce): %s", e)

    f = out["flag"]
    if f["kind"] == "ceiling":
        headline = (f"DB is {_fmt_bytes(f['current_bytes'])} — past the "
                    f"{_fmt_bytes(f['ceiling_bytes'])} line where retention needs a re-look")
    else:
        headline = (f"DB grew {_fmt_bytes(f['weekly_growth_bytes'])} in a week — "
                    f"~10x the planned rate ({_fmt_bytes(f['baseline_bytes'])} → "
                    f"{_fmt_bytes(f['current_bytes'])} in {f['baseline_age_days']:.0f}d)")
    grower_lines = []
    for t, b in out["tables"].items():
        delta = b - baseline_tables.get(t, 0)
        if baseline_tables and delta > 0:
            grower_lines.append((delta, f"{t}: {_fmt_bytes(b)} (+{_fmt_bytes(delta)})"))
        else:
            grower_lines.append((b, f"{t}: {_fmt_bytes(b)}"))
    grower_lines.sort(reverse=True)
    lines = ["\U0001F4BE *DB growth out of line*", headline, "```"]
    lines += [l for _, l in grower_lines[:5]]
    lines.append("```")
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        out["spoke"] = bool(await send_telegram_message("\n".join(lines)))
        await log_audit_event("db_growth_alert", headline, json.dumps(f))
    except Exception as e:
        logger.warning("db_growth_check: announce failed: %s", e)
        out["errors"].append(f"announce: {e}")
    return out


# ── #543 DETECTOR-LIVENESS check (2026-08-16) ───────────────────────────────────────────────────
#
# WHY. The 2026-08-15 review-registry sweep found detectors that produced nothing for months —
# `mi_anticipation_lifecycle` (last write 2026-06-16, the #270 pin rejects every candidate),
# `mi_flag_undercut_rally` (4 rows all-time, last 2026-06-18), the sugar-baby convergence alert
# (0 fires ever since 2026-05-22 ship) — and NOTHING TOLD ANYONE. The only thing "watching" them
# was a data-gated review predicate gated on the same dead counter, so it never fired either.
# Operator: "the biggest concern i have is lack of awareness when a critical part of the system
# fails, the silent failure i keep complaining about."
#
# THE RULE, stated so it can be checked, not just trusted: for each watched table, pull the
# distinct FIRE-DAYS (calendar days it wrote >=1 row) over the trailing LOOKBACK_DAYS. Bucketing
# to days, not raw rows, matters — several of these detectors write in same-day bursts (a hot tape
# can put a dozen mi_ep_alerts rows down in an hour), and a raw-row median gap would read as
# minutes, making the busiest tables hair-trigger.
#   - >= MIN_ACTIVE_DAYS distinct fire-days in the window -> the table's OWN median gap between
#     fire-days becomes its cadence. Alarm line = CADENCE_MULTIPLIER x that median, floored at
#     MIN_THRESHOLD_DAYS (a near-daily table can't be tripped by an ordinary quiet week) and
#     capped at ABSOLUTE_FALLBACK_DAYS (real cadence data can only TIGHTEN the alarm, never loosen
#     it past what a totally-unknown detector gets — see below).
#   - < MIN_ACTIVE_DAYS fire-days -> no reliable median to derive (mi_flag_undercut_rally: 4 rows
#     ALL-TIME). Falls back to the flat ABSOLUTE_FALLBACK_DAYS floor.
#   - Zero rows ever (MAX(date_col) IS NULL) -> its own case, flagged outright as "never fired" —
#     there is no cadence to be silent relative to.
#
# WHY THIS WON'T CRY WOLF: the threshold is DERIVED from each table's own history, not one shared
# constant. A detector that legitimately fires twice a month has a ~15-day median fire-gap, so even
# the flat sparse-path floor (45d, 3x that) comfortably clears a quiet fortnight (14d) — the task's
# own example case stays silent under EITHER path. MIN_THRESHOLD_DAYS=14 exists to protect the
# opposite end (a near-daily table with a 1-day median would otherwise get a 3-day trigger from the
# multiplier alone) — a bare-minimum "give it two weeks" floor before this guard speaks at all.
# That floor is deliberately generous for the CHATTIEST tables (mi_ep_alerts, mi_9m_ep_alerts)
# because they are NOT this guard's primary job — `run_job_liveness_sweep` already watches them at
# K=1/K=3 day-granularity via `_JOB_OUTPUT_CHECKS`, and the null-rate sweep covers their columns.
# This guard exists for the RARE detectors nothing else watches; a slower trigger on the tables
# that are already covered elsewhere is an acceptable trade, not a hole.
#
# COLD START: several watched tables are ALREADY dark by this rule on day one. All fresh flags from
# one run batch into ONE Telegram message — day one reads as a single "these are dark" line, not a
# stream. Re-announce is PER-TABLE (mirrors `run_inert_sweep_check`'s once-per-lane idiom, windowed
# instead of permanent — a table's condition can resolve, a permanent dedupe would silence it
# forever) and capped at once per DEDUPE_DAYS: these are structural defects, not daily conditions,
# so nightly repetition of an already-known dark table is wallpaper. A per-table (not one shared
# global) dedupe matters — a stale global count would let one already-announced table suppress a
# DIFFERENT table going dark days later, folding a fresh finding into an old one's silence window.
#
# COLUMN CHOICE, why it is NOT always the business date column: `mi_anticipation_lifecycle` rows are
# UPSERT-style (`PRIMARY KEY (ticker, gap_day)`) — a row's business dates (armed_date, coiled_date,
# ...) get REWRITTEN by state-advancing UPDATEs on the SAME row, so they would read "fresh" even
# when no NEW candidate has been seeded in months (exactly the #270-pin failure: nothing new is
# ever created, existing rows just sit). `created_at` is set once at INSERT and never touched again
# on that table, so it is the true "did a new candidate get seeded" signal — used ONLY for this one
# table, called out explicitly in the registry below.
#
# `mi_ep_alerts` NEEDS A LIVE-ROWS FILTER: it carries replay/backtest rows (`source='historical_scan'`,
# #268) sharing the table across a ~12-month span. An unfiltered read could see a REPLAY BATCH's
# rows (a fresh `created_at`, an old `alert_date`, or vice versa depending on the batch) and read a
# genuinely dead LIVE detector as active — the exact false-negative this guard exists to prevent.
# `LIVE_SOURCE_SQL` (db.py) is the canonical filter; applied here via the registry's extra-WHERE slot.
#
# THE LINE: telemetry only. This reads output tables and writes to mi_audit_log / Telegram — it does
# not touch any detector, gate, alert, entry, exit, or sizing path.
#
# KNOWN GAP, named not built: the sugar-baby convergence alert (0 fires ever, #543's own headline
# example) is an `mi_audit_log` event (`sugar_baby_convergence_alert`), not an output TABLE — this
# check is table-shaped and does not cover it. Left as a named follow-on, not silently dropped.
#
# 2026-08-16 cleanup review, finding 1 Fix B: the two shadow recorders that can fail
# 100% SILENTLY (exit_path_shadow.py / alert_rank_shadow.py — see their own headers)
# were the exact failure class this registry exists to catch, and were themselves
# excluded from it. Both DATE columns below are the modules' own business-date
# columns (`trading_day` / `alert_date`), NOT `computed_at` — `_detector_liveness_col_is_timestamp`
# is name-based (`== "created_at"`), so a timestamptz column here would silently mis-key
# as a plain DATE, crash the per-table try/except, and the table would just never get
# checked (the failure class this whole registry exists to prevent). ⚠ Both tables are
# EMPTY as of this commit — they read as `never_fired` until their first scheduled run
# (17:50 / 17:53 ET respectively).
#
# 2026-08-17 follow-up: the line above was aspirational, not implemented — this whole
# check runs inside post_nightly_audit at 17:30 ET, TWENTY MINUTES BEFORE either writer's
# own cron slot, so on deploy night both tables alarmed immediately ("Detectors gone
# quiet ... 0 rows ever") despite being perfectly healthy; a table simply cannot have
# written yet when the check that judges it runs first. A same-day clock comparison can't
# fix this: the checker precedes the writer EVERY evening, forever, so "hasn't fired yet
# today" is true on night 1 AND on night 1000 of a genuinely broken detector — it would
# suppress permanently, not just once. Fixed instead via `_evaluate_table_liveness`'s own
# run history (see `run_detector_liveness_check`): a `never_fired` table is only silenced
# the FIRST calendar day it is ever seen never_fired; if it is still never_fired on any
# later day, that means a full day-night cycle already passed with its writer given every
# chance, and it alarms for real. Self-resolving on first fire is genuinely true now.
_DETECTOR_LIVENESS_TABLES: tuple[tuple[str, str, str, str | None], ...] = (
    # (table, label, date/timestamp column, extra WHERE clause or None)
    # RETIRED 2026-08-31 — `mi_anticipation_lifecycle` is not a broken detector, it is a
    # SUPERSEDED one, and a watch on a deliberately-dead table cries wolf weekly forever
    # (the #604 class). Ground truth checked tonight, not assumed: the table holds 19 rows,
    # ALL written 2026-06-16 17:35:01-17:35:11 ET — one cycle, ten seconds, never again.
    # That matches the #327 Stage-0 teardown exactly (the #270 machine ran once; its entry
    # layer never ran because `replay()` re-gates +40% internally). Family A is literally
    # "reset of #270" and #327 IS the replacement — whose table `mi_delayed_entry_watch` is
    # registered below and FIRED ITS FIRST REAL RUN TONIGHT (4,414 rows / 871 tickers /
    # 1,269 lane members, 2026-08-31 17:57-18:46 ET). The old watch came off only AFTER the
    # replacement wrote, never before ([[a-rule-is-not-live-until-it-has-fired-once]]).
    # If the #270 anticipation machine is ever revived, re-add this line with it.
    ("mi_flag_undercut_rally", "flag undercut & rally", "ur_date", None),
    ("mi_flag_breaks", "flag breaks", "break_date", None),
    ("mi_htf_breakout_shadow", "HTF breakout shadow", "break_date", None),
    ("mi_consolidation_entry_shadow", "consolidation entry shadow", "entry_date", None),
    ("mi_9m_ep_alerts", "9M EP alerts", "alert_date", None),
    ("mi_ep_alerts", "EP alerts", "alert_date", LIVE_SOURCE_SQL),
    ("mi_exit_path_shadow", "exit-path shadow", "trading_day", None),
    ("mi_alert_rank_shadow", "alert-rank shadow", "alert_date", None),
    # Shortlist pre-score counterfactual (2026-08-22): written every scan tick with
    # >=1 candidate — a silent writer here means the gap-vs-prescore record has
    # stopped accruing (the 100%-silent recorder class this registry exists for).
    ("mi_ep_shortlist_shadow", "EP shortlist pre-score shadow", "scan_date", None),
    # #327 delayed-entry watch lane (2026-08-30): written every evening while ANY name
    # is inside its 20-session window — and the lane is SILENT by operator ruling (no
    # Telegram even on job failure), so this registry is its ONLY watchdog. Keyed on
    # the plain-DATE business column `session_date` (a timestamptz here would silently
    # never be checked — the name-based `created_at` rule below). The trigger table is
    # deliberately NOT registered: rungs legitimately go quiet for weeks in a quiet
    # tape, and a false liveness alarm on a genuinely quiet detector is exactly the
    # noise class this registry avoids — the watch table covers the writer, and both
    # tables are written by the same job.
    ("mi_delayed_entry_watch", "delayed-entry watch lane (#327)", "session_date", None),
    # #533 slot-ranking watch (2026-08-30): written on EVERY process_new_alerts_live
    # invocation with >=1 HIGH alert on the board, and SILENT by convention (no
    # Telegram on any path) — so this registry is its only watchdog. Keyed on the
    # plain-DATE business column `alert_date` (recorded_at/created_at are timestamptz
    # and would silently never be checked — the name-based `created_at` rule).
    ("mi_ep_slot_rank_shadow", "EP slot-rank watch (#533)", "alert_date", None),
    # #606 D-1 universe floor shadow (2026-08-31): written every scan tick with
    # >=1 real candidate on EITHER side of the D-1 floor — a fire-and-forget writer
    # read by nothing on the scan path, the same can-fail-100%-silently class as the
    # shortlist pre-score shadow above. Keyed on the plain-DATE business column
    # `scan_date` (created_at is timestamptz and would silently never be checked).
    ("mi_universe_floor_shadow", "D-1 universe floor dollar-volume shadow (#606)", "scan_date", None),
    # #333 analyst-estimates recorder (2026-08-31): written every weekday evening while
    # ANY live-source EP alert exists in the trailing 30 days — and the recorder is
    # SILENT by the data-capture contract (no Telegram even on job failure), so this
    # registry is its ONLY watchdog. A dead writer here silently stops the >=60-day
    # accrual clock that gates the #333 durability axis — exactly the
    # can-fail-100%-silently class this registry exists for. Keyed on the plain-DATE
    # business column `as_of_date` (created_at is timestamptz and would silently never
    # be checked — the name-based `created_at` rule).
    ("mi_analyst_estimates", "analyst estimates recorder (#333)", "as_of_date", None),
    # #482 (2026-09-03): the live-fill counterfactual recorder. Writes only when a MAGNA53
    # fill has arms left to settle (~a handful a month), so its cadence is sparse by nature —
    # the liveness rule derives that from the table's own history, as for mi_exit_path_shadow.
    # Keyed on `settled_session` (the last settled session the run had walked when it wrote —
    # a plain business DATE that advances with every writing run), NOT `recorded_at`: the
    # date-column rule below is name-based and only `created_at` routes to the timestamp branch.
    ("mi_live_fill_counterfactuals", "live-fill counterfactual recorder (#482)", "settled_session", None),
    ("mi_sustain_reject_replays", "sustain-reject bracket replay (#593)", "settled_session", None),
    # #617 Step 2 (2026-09-03): the gap-floor near-miss replay. Step 1 measured ~4-5 excluded
    # names/session in the 7-9% band across three months, so this writes on almost every
    # trading day — but the whole POINT of this task is "nothing was watching, so a dead
    # writer went unnoticed from April to September." Keyed on `settled_session` (same
    # name-based-timestamp rule as its two siblings above).
    ("mi_gap_near_miss_replays", "gap-floor near-miss replay (#617 Step 2)", "settled_session", None),
)
_DETECTOR_LIVENESS_LOOKBACK_DAYS = 90
_DETECTOR_LIVENESS_MIN_ACTIVE_DAYS = 6            # >=6 fire-days (>=5 gaps) before trusting a median
_DETECTOR_LIVENESS_CADENCE_MULTIPLIER = 3.0
_DETECTOR_LIVENESS_MIN_THRESHOLD_DAYS = 14        # floor — never alarm inside a plain quiet fortnight
_DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS = 45    # sparse-history floor AND the cadence-path ceiling
_DETECTOR_LIVENESS_DEDUPE_DAYS = 7


def _detector_liveness_col_is_timestamp(date_col: str) -> bool:
    """True for the one timestamptz column name the registry may use (`created_at`); every other
    entry is a plain DATE business column. NO entry uses it right now — the only one that did,
    `mi_anticipation_lifecycle`, was retired 2026-08-31 (see the registry). Kept, not deleted:
    it is the contract five registry comments cite when they explain why they key on a plain
    business date, and it is what a future UPSERT-style table would need. The rule is NAME-BASED,
    so a timestamptz column registered under any OTHER name (`recorded_at`, `fired_at`) is
    silently mis-keyed — pinned by test_detector_liveness_543."""
    return date_col == "created_at"


def _evaluate_table_liveness(
    active_days: list, last_write, today,
) -> dict[str, Any] | None:
    """Pure decision for ONE table's liveness, isolated + mock-free (the file's idiom).

    active_days: the table's fire-days within the trailing lookback window — may contain
      duplicates/be unordered (deduped + sorted here, so callers don't have to); may be empty.
    last_write: the table's true most-recent fire-day, UNBOUNDED by the lookback window (None if
      the table has never written a row at all).
    today: the caller's current ET date.

    Returns a flag dict or None (silent = healthy, or not enough signal against a "never fired"
    table — that case is unconditional, see below).
    """
    if last_write is None:
        return {"kind": "never_fired"}

    silence_days = (today - last_write).days
    days = sorted(set(active_days))

    if len(days) >= _DETECTOR_LIVENESS_MIN_ACTIVE_DAYS:
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        median_gap = statistics.median(gaps)
        threshold = min(
            max(_DETECTOR_LIVENESS_CADENCE_MULTIPLIER * median_gap,
                _DETECTOR_LIVENESS_MIN_THRESHOLD_DAYS),
            float(_DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS),
        )
        kind = "cadence"
    else:
        median_gap = None
        threshold = float(_DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS)
        kind = "sparse"

    if silence_days > threshold:
        return {
            "kind": kind,
            "silence_days": silence_days,
            "threshold_days": round(threshold, 1),
            "median_gap_days": median_gap,
            "last_write": last_write,
        }
    return None


def _format_liveness_flag(f: dict[str, Any]) -> str:
    label = f.get("label", f["table"])
    if f["kind"] == "never_fired":
        return f"{label} ({f['table']}): 0 rows ever"
    gap_note = f", normal gap ~{f['median_gap_days']:.0f}d" if f.get("median_gap_days") else ""
    return (f"{label} ({f['table']}): silent {f['silence_days']}d, "
            f"normally <= {f['threshold_days']:.0f}d{gap_note}")


async def run_detector_liveness_check() -> dict[str, Any]:
    """Nightly per-table cadence check (PLAN #543): did each watched detector output table write
    a row recently enough for ITS OWN historical cadence? Speaks only when a table's silence
    exceeds its own derived threshold (see the header above for the full rule + why it won't
    cry wolf).

    Returns {"tables_scanned": n, "flags": [...], "errors": [...], "spoke": bool}.
    Never raises — a health guard that dies silently is the failure it exists to prevent.
    """
    out: dict[str, Any] = {"tables_scanned": 0, "flags": [], "errors": [], "spoke": False}
    today = _now_et().date()
    cutoff_date = today - timedelta(days=_DETECTOR_LIVENESS_LOOKBACK_DAYS)

    try:
        pool = await get_pool()
        async with pool.acquire() as c:
            # #543 follow-up (2026-08-17): don't judge a table whose writer hasn't had its
            # FIRST chance to run yet as "gone quiet" — see the registry header above for why
            # this can't be a same-day clock/cron comparison (checker always runs before the
            # writer, every night, forever — that comparison would suppress a genuinely-dead
            # detector permanently, not just once). A single-night grace isn't enough either:
            # mi_exit_path_shadow writes one row per LIVE trade per day — with zero eligible
            # live trades on a given day it correctly writes NOTHING, and that is normal, not
            # broken (see record_exit_path_shadow's population/written counters). A quiet
            # 2-live-trade stretch would otherwise alarm on day 2 exactly like tonight, one
            # day later. So a never_fired table gets the SAME patience an established table
            # with too little history already gets in the cadence branch below
            # (_DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS, the sparse-path flat floor) — no new
            # policy, just applying the existing "not enough signal yet" tolerance to the
            # zero-signal case too. Anchor date = the EARLIEST calendar day this exact table
            # was ever flagged never_fired in this check's own run history (unconditional
            # every night it's dark — see _evaluate_table_liveness's never_fired branch — so
            # the earliest row is a reliable "since when have we been watching this table"
            # marker, immune to a cron-time reshuffle). mi_audit_log.detail is TEXT, parsed
            # Python-side, malformed rows skipped (mirrors get_judge_grade_decisions_for_date's
            # established pattern in db.py).
            first_never_fired_date: dict[str, date] = {}
            try:
                hist_rows = await c.fetch(
                    "SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, detail "
                    "FROM mi_audit_log "
                    "WHERE event_type = 'detector_liveness_check' "
                    "AND (created_at AT TIME ZONE 'America/New_York')::date < $1::date "
                    "ORDER BY (created_at AT TIME ZONE 'America/New_York')::date ASC",
                    today,
                )
                for r in hist_rows:
                    try:
                        row_date = r["d"]
                        for entry in json.loads(r["detail"] or "[]"):
                            table_name = entry.get("table")
                            if entry.get("kind") == "never_fired" and table_name:
                                # ASC order -> first write wins -> earliest sighting kept.
                                first_never_fired_date.setdefault(table_name, row_date)
                    # Narrow, matching db.py::get_judge_grade_decisions_for_date's established
                    # pattern for this exact table (mi_audit_log.detail is TEXT and can hold
                    # malformed rows) — one bad history row must not lose the rest.
                    except (ValueError, TypeError, AttributeError, KeyError):
                        continue
            except Exception as e:
                # Fail open toward SUPPRESSING, not alarming — mirrors the announce-dedupe
                # fail-open below. Worst case a genuinely-dead table stays silent one extra
                # night; a lost history read can never manufacture a false alarm from this.
                logger.warning(
                    "detector_liveness_check: history read failed "
                    "(treating all tables as first-seen this run): %s", e)

            for table, label, date_col, extra_where in _DETECTOR_LIVENESS_TABLES:
                try:
                    is_ts = _detector_liveness_col_is_timestamp(date_col)
                    where_sql = f" WHERE {extra_where}" if extra_where else ""
                    if is_ts:
                        day_expr = f'("{date_col}" AT TIME ZONE \'America/New_York\')::date'
                        cutoff_param = datetime(cutoff_date.year, cutoff_date.month,
                                                 cutoff_date.day, tzinfo=_ET)
                        last_write_raw = await c.fetchval(
                            f'SELECT MAX("{date_col}") FROM "{table}"{where_sql}')
                        last_write = last_write_raw.astimezone(_ET).date() if last_write_raw else None
                    else:
                        day_expr = f'"{date_col}"'
                        cutoff_param = cutoff_date
                        last_write = await c.fetchval(
                            f'SELECT MAX("{date_col}") FROM "{table}"{where_sql}')

                    cutoff_pred = f'"{date_col}" >= $1'
                    full_where = f'{cutoff_pred} AND {extra_where}' if extra_where else cutoff_pred
                    rows = await c.fetch(
                        f'SELECT DISTINCT {day_expr} AS d FROM "{table}" WHERE {full_where}',
                        cutoff_param,
                    )
                    active_days = [r["d"] for r in rows]
                    out["tables_scanned"] += 1
                    flag = _evaluate_table_liveness(active_days, last_write, today)
                    if flag is not None:
                        # never_fired within its grace window -> tag in_grace so it still gets
                        # PERSISTED (tomorrow's history read needs the earliest-sighting date)
                        # but does not speak tonight. Once the grace window elapses with the
                        # table STILL never_fired, it goes untagged and speaks normally —
                        # cadence/sparse flags (tables with SOME history) are untouched.
                        if flag["kind"] == "never_fired":
                            first_seen = first_never_fired_date.get(table, today)
                            days_in_grace = (today - first_seen).days
                            if days_in_grace < _DETECTOR_LIVENESS_ABSOLUTE_FALLBACK_DAYS:
                                flag = {
                                    **flag, "in_grace": True,
                                    "first_seen_date": first_seen.isoformat(),
                                }
                        out["flags"].append({**flag, "table": table, "label": label})
                except Exception as e:  # one bad table must not kill the sweep
                    logger.warning("detector_liveness_check: table %s failed: %s", table, e)
                    out["errors"].append({"table": table, "error": str(e)})
    except Exception as e:
        logger.error("detector_liveness_check: pool acquisition failed: %s", e, exc_info=True)
        out["errors"].append({"pool": str(e)})
        return out

    # Record tonight's run — always, flagged or not. Unlike db_growth_check this needs no
    # persisted baseline row: cadence is re-derived fresh each run straight from each table's own
    # row history, so this row is a plain audit trail, not next week's comparison point.
    try:
        await log_audit_event(
            "detector_liveness_check",
            f"{out['tables_scanned']} tables, {len(out['flags'])} dark",
            json.dumps([
                {**f, "last_write": f["last_write"].isoformat() if f.get("last_write") else None}
                for f in out["flags"]
            ]),
        )
    except Exception as e:
        logger.warning("detector_liveness_check: audit log failed: %s", e)
        out["errors"].append({"audit": str(e)})

    if not out["flags"]:
        return out

    # PER-TABLE dedupe (not one shared global count) — mirrors run_inert_sweep_check's
    # once-per-lane idiom, windowed instead of permanent (a table's condition CAN resolve, so a
    # permanent dedupe would silence it forever). mi_audit_log IS the dedupe state, no new table.
    # Fails OPEN: a dedupe-read failure only risks one duplicate alert, never a missed one.
    try:
        pool = await get_pool()
        async with pool.acquire() as c:
            recent_rows = await c.fetch(
                "SELECT DISTINCT split_part(summary, ':', 1) AS t FROM mi_audit_log "
                "WHERE event_type = 'detector_liveness_alert' "
                "AND created_at >= NOW() - make_interval(days => $1)",
                _DETECTOR_LIVENESS_DEDUPE_DAYS,
            )
        recently_announced = {r["t"] for r in recent_rows}
    except Exception as e:
        logger.warning("detector_liveness_check: dedupe read failed (will announce): %s", e)
        recently_announced = set()

    # in_grace (a never_fired table still inside its 45-day first-sighting window,
    # #543 follow-up above) never speaks — it exists in out["flags"] only so a later
    # night's history read can find the earliest-sighting date and keep counting from it.
    fresh = [
        f for f in out["flags"]
        if f["table"] not in recently_announced and not f.get("in_grace")
    ]
    if not fresh:
        return out

    lines = ["\U0001FA7A *Detectors gone quiet*", "```"]
    lines.extend(_format_liveness_flag(f) for f in fresh)
    lines.append("```")
    lines.append("Output table(s) above have stopped writing beyond their own normal cadence — "
                 "check the detector, not the tape (PLAN #543).")
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        out["spoke"] = bool(await send_telegram_message("\n".join(lines)))
        for f in fresh:
            await log_audit_event(
                "detector_liveness_alert",
                f"{f['table']}: " + ("never fired" if f["kind"] == "never_fired" else "silent"),
                json.dumps({**f, "last_write": f["last_write"].isoformat() if f.get("last_write") else None}),
            )
    except Exception as e:
        logger.warning("detector_liveness_check: announce failed: %s", e)
        out["errors"].append({"announce": str(e)})
    return out


# ── #521 INERT-SWEEP CHECK (2026-08-03) ───────────────────────────────────────────────────────
#
# WHY. `mi_orb_extension_shadow` swept six entry-cutoff times for three months and every one of
# them returned a BYTE-IDENTICAL result for every trade. The cause was a one-word bug — the
# simulator computed its fill threshold from the STOP instead of the LIMIT, so the threshold was
# crossed within minutes of the open, long before the earliest cutoff could matter. Nobody looked
# until the review's N>=20 threshold tripped on 2026-08-03, ninety-one days later, and the answer
# it would have given ("10:00 is already optimal") was manufactured by the bug.
#
# Operator, on being told: *"disappointing to have bad data for months, need to prevent this going
# forward."*
#
# THE CHECK, stated as narrowly as it can be: **a study that varies a parameter must produce
# variation.** If a sweep has >=2 variants and >=MIN_SUBJECTS subjects, and every subject scores
# IDENTICALLY across all of them, the sweep is inert — the parameter is not reaching the code, or
# the code is not reading it. That is decidable from the data alone; it needs no view on whether
# the numbers are *right*.
#
# WHAT IT DELIBERATELY DOES NOT DO: judge plausibility, ranges, or units. Those need a model of the
# domain and would cry wolf; a guard that always fires is not a guard (2026-08-01). This one fires
# only on a signature that is always a defect.
#
# ⚠ The registry below is HAND-MAINTAINED, and that is a real cost: a new sweep lane that is not
# added here is not checked. It is four entries, adding one is part of building a sweep, and the
# alternative — inferring "which column is the swept parameter" — was rejected as too magic to
# trust on money-adjacent telemetry.
_SWEEP_LANES: tuple[tuple[str, str, str, int], ...] = (
    # (table, swept-parameter column, outcome column, min subjects before judging)
    ("mi_orb_extension_shadow", "cutoff_minute", "total_pnl", 10),
    ("mi_giveback_shadow", "arm", "realized_r", 10),
    ("mi_htf_management_shadow", "trail_mode", "realized_r", 10),
    ("mi_consolidation_entry_shadow", "entry_mode", "realized_r", 10),
)
_SWEEP_SUBJECT_KEYS = ("trade_id", "ticker")

# Columns that LOOK like a swept study parameter but are NOT — each must say why, because the
# discovery gate (tests/test_inert_sweep_registry_complete.py) refuses to let anything be silently
# omitted. This is the same shape as the scheduler's role-partition guard: everything discovered
# must be CLASSIFIED, in one list or the other, or the check fails.
_NOT_SWEEP_PARAMS: dict[str, str] = {
    "account_mode": "paper vs live ROUTING, not a studied variable — the two arms are different "
                    "accounts, not variants of one experiment, so identical results are expected.",
    "score_tier":   "the alert's own HIGH/MODERATE grade — a classification of the subject, not a "
                    "parameter we vary over it.",
    "breakeven_armed": "mi_exit_path_shadow's observed state (was breakeven armed on the LIVE "
                    "position that day) — matched on the substring 'arm', not a swept parameter; "
                    "there is only one live rule, nothing is varied over it.",
    # #533 Change 6 (2026-08-22) — mi_catalyst_tier_shadow: OUTPUT columns, not swept settings.
    # There is exactly ONE lattice (catalyst_tier_shadow.shadow_retier); nothing varies per row.
    "shadow_tier_first": "mi_catalyst_tier_shadow's VERDICT at the first scan tick — the shadow "
                    "grader's output, a classification of the subject, not a parameter varied "
                    "over it (same shape as score_tier above).",
    "shadow_tier_last": "mi_catalyst_tier_shadow's VERDICT at the latest scan tick — output, not "
                    "a swept parameter; first/last exist to make intraday grade drift countable.",
    "rule_first":   "mi_catalyst_tier_shadow: WHICH single-lattice rule produced the first "
                    "verdict — provenance of an output, not an experimental arm; every row runs "
                    "the same one lattice.",
    "rule_last":    "mi_catalyst_tier_shadow: rule provenance of the latest verdict — same as "
                    "rule_first; recorded so tier changes are attributable, nothing is varied.",
    "live_tier":    "mi_catalyst_tier_shadow's copy of the LIVE alert tier (HIGH/MODERATE/NULL) "
                    "at the recording tick — the subject's own live classification, mirrored for "
                    "the counterfactual join; same not-a-parameter shape as score_tier above.",
    # #533 separation change (2026-08-22) — mi_ep_score_shadow: OUTPUT columns, not swept
    # settings. Both sides are computed on EVERY row by the same _score_ep (the whole point
    # is the per-row comparison); nothing is varied across rows.
    "sep_tier_first": "mi_ep_score_shadow: the separation side's tier at the first scan tick — "
                    "an output classification of the subject (same shape as score_tier above), "
                    "not a parameter varied over it.",
    "sep_tier_last": "mi_ep_score_shadow: the separation side's tier at the latest tick — "
                    "output, not a swept parameter; first/last make intraday drift countable.",
    "legacy_tier_first": "mi_ep_score_shadow: what the pre-2026-08-22 rubric would have tiered "
                    "this name at the first tick — the recorded counterfactual output, computed "
                    "on every row; not an experimental arm assignment.",
    "legacy_tier_last": "mi_ep_score_shadow: the counterfactual tier at the latest tick — same "
                    "as legacy_tier_first; a comparison record, nothing is varied per row.",
}


async def run_inert_sweep_check() -> dict[str, Any]:
    """Flag parameter sweeps whose variants all produce identical results.

    Returns {"lanes_scanned", "inert", "skipped", "errors"}. Never raises — a health check that
    dies silently is the failure it exists to prevent, so each lane is isolated."""
    from agents.market_intelligence.db import get_pool

    out: dict[str, Any] = {"lanes_scanned": 0, "inert": [], "skipped": [], "errors": []}
    pool = await get_pool()
    for table, sweep_col, outcome_col, min_subjects in _SWEEP_LANES:
        try:
            async with pool.acquire() as conn:
                cols = {r["column_name"] for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=$1", table)}
                if not cols:
                    out["skipped"].append({"table": table, "why": "table absent"})
                    continue
                subject = next((k for k in _SWEEP_SUBJECT_KEYS if k in cols), None)
                if subject is None or sweep_col not in cols or outcome_col not in cols:
                    out["skipped"].append({"table": table, "why": "expected columns absent"})
                    continue
                row = await conn.fetchrow(f"""
                    WITH per_subject AS (
                        SELECT {subject} AS s,
                               COUNT(DISTINCT {sweep_col}) AS n_variants,
                               COUNT(DISTINCT COALESCE({outcome_col}::text, '~null~')) AS n_outcomes
                        FROM {table} GROUP BY {subject}
                    )
                    SELECT COUNT(*) AS subjects,
                           COUNT(*) FILTER (WHERE n_variants > 1) AS multi_variant_subjects,
                           COUNT(*) FILTER (WHERE n_variants > 1 AND n_outcomes > 1) AS varied
                    FROM per_subject
                """)
            out["lanes_scanned"] += 1
            multi = int(row["multi_variant_subjects"] or 0)
            varied = int(row["varied"] or 0)
            if multi < min_subjects:
                out["skipped"].append({"table": table, "why": f"only {multi} multi-variant subjects "
                                                              f"(<{min_subjects}) — too early to judge"})
                continue
            if varied == 0:
                out["inert"].append({
                    "table": table, "swept": sweep_col, "outcome": outcome_col,
                    "multi_variant_subjects": multi,
                    "note": (f"{table}: {multi} subjects each scored across multiple {sweep_col} "
                             f"values and NOT ONE produced a different {outcome_col}. The swept "
                             f"parameter is not reaching the code, or the code is not reading it — "
                             f"this sweep is measuring nothing."),
                })
        except Exception as e:  # loud-ok: recorded in out["errors"] and surfaced by the caller — per-lane isolation so one bad table cannot blind the other three
            out["errors"].append({"table": table, "error": f"{type(e).__name__}: {e}"})
    return out


# ── #531 NIGHTLY THEME QUALITY CHECK (2026-08-04) ────────────────────────────────────────────────
#
# WHY. Operator, verbatim: "i'm really asking for quality checks regularly to make sure our themes
# are solid without me needing to check it and review manually" — he should learn a theme defect
# from a Telegram, not from an investigation (which is how #368's diagnosis happened: 5 of 9 theme-
# credit false positives traced to one mechanism nobody was watching for).
#
# FOUR candidate signatures were measured against 97 real trading days of prod mi_themes
# (2026-03-19..2026-08-04, captured once via ssh) before anything shipped. Two survived; two were
# DROPPED — dropping is the documented good outcome, not a shortfall (see each write-up below).
#
# SIGNATURE A — "a theme retired while healthy" (#368/F2's exact target). MEASURED: 165 distinct
# retirement incidents (`mi_audit_log.theme_retired`, clustered — the event re-fires nightly for up
# to ~7 days while the theme lingers in `existing`'s recency window, so incidents are keyed on
# theme NAME, first occurrence). Of those, 129 carry an EXPLICIT same-day `mi_themes` Retired row —
# a DIFFERENT, legitimate mechanism (ADR-0025 Arm-A 2-member dissolve on a validation-flagged
# member, or Pass1/1.5 engine-drop consolidation) that #368/F2 does not touch and this check
# deliberately does NOT fire on (hand-verified: Heavy Transportation Equipment Manufacturers,
# Casual Dining Restaurant Turnaround, Specialty Pharma — all exactly 2 members, explicit Retired
# row same day, score=0/rs_avg=None — the validator correctly dissolving a flagged pair, not a
# silent-death bug). Of the remaining SILENT vanishes (no row at all, any stage, on the retirement
# date), 6 had a healthy last-known state (Fading stage, rs_avg NOT NULL) immediately before
# vanishing — the exact #368/F2 signature (a "held"/score-delta Fading row that still cleared the
# strong-member floor, wrongly counted toward the 5-day retire streak): 'Single-Cell Genomics &
# Spatial Biology Instrumentation' (4/21, rs_avg 88.0), 'Lithium & Battery Critical Minerals Mining'
# (4/29, 93.8), 'Workforce Solutions & Technical Staffing Services' (5/06, 80.3), 'Precision
# Frequency & Timing Defense Electronics' (5/12, 80.2), 'Chip Architecture Licensing & CPU/GPU
# Compute Revival' (5/15, 82.8), and the verified prod case: 'Bitcoin Mining & Crypto Infrastructure
# Operators' (8/04, 84.9 on 8/03). 6/165 = a clean, low-noise signal — every firing hand-checked and
# real. NOTE, named deliberately (not left to only live in reasoning): a SEPARATE, DIFFERENT class
# — a healthy Fading theme dropped via the Pass1/1.5 ENGINE-DROP path (explicit same-day Retired
# row, e.g. 'AI Memory & Storage' 7/13 rs_avg 95.4 the day before) — was seen 4x in the same window
# and is NOT covered here: F2 does not fix it (it never reaches `_count_consecutive_fading`), so
# alerting it under this signature would point at the wrong remediation. Filed as a future
# candidate, not silently dropped.
#
# TWO measurement bugs found and fixed before trusting the number (both worth naming — a guard
# built on a buggy measurement is not a guard): (1) using `theme_date <= retirement_date` instead
# of `< ` double-counted a coincidental SAME-NAME rediscovery born in the identical nightly run as
# the old instance's retirement (e.g. 'Precious Metals Royalty & Streaming Companies' 8/03 — a 2-
# ticker Fading sub-theme retired AND a 4-ticker Nascent theme with the identical Haiku-generated
# name was born, same run) — fixed by requiring the lookup strictly BEFORE the retirement date.
# (2) the daily re-fire of `theme_retired` (discovered via this measurement) would have made an
# un-clustered incident count meaningless — fixed by clustering same-name events >7 days apart into
# one incident and keying dedupe on theme name alone (never name+date), so the persisting condition
# doesn't wallpaper the channel on night two.
#
# SIGNATURE B — "a member pruned while its RS was rising" (#368/F3's exact target — the
# `ticker_prune_held_rising` hold is supposed to catch and HOLD these, not let them prune).
# MEASURED: mirroring the ENGINE'S OWN exact prune gate (PRUNE_RS_HARD=25 candidate on any day;
# PRUNE_RS_SOFT=35 candidate only on the 3rd consecutive sub-floor day; >=35 never a candidate —
# an earlier pass that skipped this gate would have false-fired on tickers the engine was never
# going to prune at all) and excluding (a) #214 mass-evictions (>=3 leavers AND >=50% of the
# theme's membership gone at once — a validation strip, not a daily prune) and (b) tickers that
# MOVED to another live theme the same night (present somewhere in today's board — reassignment,
# not a prune): 164 prune-shaped exits over the window, 25 RISING (theme_engine._rs_rising: newest
# RS > oldest RS over the last 6 sessions, >=4 points of history). Of the 14 with a full 10-session
# forward window: 11 recovered to RS>=50, 2 stayed dead, 1 sat in limbo — 79% recovered, vs the
# FALLING control (the hold correctly still prunes these): 35/97 = 36% recovered. That 79-vs-36
# spread, not the raw firing count, is the evidence these are real defects, not noise — an ignited
# recovery pruned early, not routine decay. Verified case inside the window: IREN + APLD pruned
# from 'AI Compute & GPU Data Center Hosting Operators' 7/22 while both were igniting (the exact
# #368 miner-cohort mechanism F3 now holds instead of prunes).
#
# DROPPED — fragmentation (2+ live themes sharing >=50% of the smaller theme's members): 251
# day-level firings across 122 DISTINCT theme-name pairs in the same window — far too broad to ship
# (a guard that always fires is not a guard). More important than the noise count: the #368
# diagnosis already identified the real fragmentation signature as "zero crypto x AI pairs were
# EVER proposed for adjudication" (theme_merge_arm's Stage-A family gap), not "two themes overlap"
# — overlap is Arm-B's normal INPUT (the machinery that resolves it working as intended), so an
# overlap-percentage alarm would fire on healthy operation and need domain judgment ("same cohort,
# or two adjacent-but-distinct industries?") to tell real fragmentation from coincidence — exactly
# what this check's template (#521 inert-sweep) refuses to do. The real check (pairs never
# proposed) is F1's territory: withdrawn at its own gate 2026-08-04, filed #529, gated on #471
# (parent/child persistence not yet built). Building a parallel overlap alarm now would duplicate
# work already scoped correctly elsewhere and would not be trustworthy on its own terms.
#
# DROPPED — churn (a theme born-and-dead inside N days, repeatedly, in one ticker neighbourhood):
# 42 of 301 distinct names (14%) born-and-gone within 5 calendar days — mostly normal Nascent
# mortality (a cluster that just didn't have legs), not evidence of a defect on its own. The
# "repeatedly, in the same neighbourhood" qualifier the operator specified requires clustering
# short-lived themes by ticker-overlap across MULTIPLE deaths — the same neighbourhood-identity
# problem fragmentation has, and the same reason it isn't trustworthy to ship today.
#
# Measurement + hand-checks: docs/analysis/531_theme_quality_measurement_2026-08-04.md.
#
# WIRING: registered in `_post_nightly_audit_job` (scheduler.py) the same way `run_inert_sweep_check`
# is — own try/except so a failure here can't break the audit job; each signature isolated inside
# `run_theme_quality_check` (one bad query can't blind the other). Dedupe copies the inert-sweep
# idiom exactly (`mi_audit_log` IS the state; `SELECT DISTINCT split_part(summary, ':', 1)`) and
# fails OPEN — a broken dedupe read costs a duplicate alert, never a missed one. Both event types
# ('theme_retired_while_healthy', 'theme_member_pruned_while_rising') persist forever once
# announced — each finding is a discrete past event (a specific retirement, a specific prune), not
# an ongoing condition that can "heal" the way a null column can, so there is no resolve/re-open
# path here (unlike increment 2's reconcile above).

# Mirrors theme_engine.py's exact prune-gate constants + rising test — mirrored (not imported) so
# this file's lightweight-import discipline holds (see `_is_trading_day`'s docstring), with a pin
# test (tests/test_theme_quality_check.py) asserting byte-parity against the real engine values so
# a future threshold change can't silently drift this check out of sync with what it's guarding.
_PRUNE_RS_HARD_MIRROR = 25.0
_PRUNE_RS_SOFT_MIRROR = 35.0
_PRUNE_HOLD_MIN_POINTS_MIRROR = 4


def _rs_rising_mirror(hist: list[float]) -> bool:
    """Mirrors theme_engine._rs_rising exactly (byte-parity pinned by
    tests/test_theme_quality_check.py): newest-first `hist`, rising iff >=4 points
    AND hist[0] (newest) > hist[-1] (oldest, up to 6 sessions back) AND hist[0] is
    not below EVERY intermediate reading.

    The second clause was added 2026-08-26. The endpoint-only test compares two
    points and is blind to everything between, so a collapse whose oldest reading
    is a one-day trough scored as rising — this check's OWN 2026-08-25 flag on
    BLDR (`[10.0, 13.8, 25.7, 29.4, 29.2, 5.9]`, a 29 → 10 collapse) was a false
    alarm produced exactly that way. Full derivation + the four rejected broader
    shape tests: theme_engine._rs_rising's docstring."""
    if len(hist) < _PRUNE_HOLD_MIN_POINTS_MIRROR or hist[0] <= hist[-1]:
        return False
    interior = hist[1:-1]
    return not interior or hist[0] >= min(interior)


_RETIREMENT_LOOKBACK_DAYS = 7  # mirrors get_active_themes(stale_after_days=7) — the engine's
                               # own definition of "still the same lifecycle"


def _evaluate_theme_retirement(today, history: list[dict]) -> dict | None:
    """Pure decision for ONE candidate name (already known to have a fresh `theme_retired`
    audit event): given its mi_themes rows in [today-7, today] (most-recent-first, from
    `get_theme_history_window`), decide whether this was a SILENT vanish from a healthy
    Fading state — the #368/F2 signature — vs. one of the other legitimate retirement
    shapes this check must stay silent on.

    Returns a flag dict when: (a) NO row exists for `today` itself — an explicit same-day
    row means a DIFFERENT mechanism (ADR-0025 Arm-A 2-member dissolve, or Pass1/1.5
    engine-drop consolidation) that F2 doesn't touch, and firing on it would point at the
    wrong fix; AND (b) the most recent PRIOR row (theme_date < today, within
    `_RETIREMENT_LOOKBACK_DAYS` — `get_active_themes`'s own liveness horizon, enforced HERE
    too, not just by the caller's SQL bound, so this function stays correct even if a wider
    history list is ever passed in) has stage == 'Fading' AND rs_avg IS NOT NULL (the theme
    still cleared the strong-member floor the day it vanished). Returns None otherwise —
    including a weak Fading row (rs_avg IS NULL, the CORRECT, expected retirement shape), a
    stale reused-name row outside the lookback, and no prior history at all.
    """
    if history and history[0]["theme_date"] == today:
        return None  # explicit same-day row — a different, non-F2 mechanism
    prior = next((r for r in history if r["theme_date"] < today), None)
    if prior is None:
        return None  # no recent history to judge — can't confirm "healthy"
    if (today - prior["theme_date"]).days > _RETIREMENT_LOOKBACK_DAYS:
        return None  # a reused name's stale prior life — not "just retired while healthy"
    if prior["stage"] != "Fading" or prior["rs_avg"] is None:
        return None
    return {
        "prior_date": prior["theme_date"],
        "prior_rs_avg": prior["rs_avg"],
        "prior_score": prior.get("score"),
    }


def _is_mass_eviction(n_gone: int, prior_member_count: int) -> bool:
    """Mirrors theme_engine.py's #214 mass-eviction signature: >=3 leavers AND >=50% of
    prior membership gone at once — a validation strip / Arm-A dissolve, not a daily prune.
    The rising-hold only concerns individual PRUNE decisions; scoring a strip event here
    would be pure noise (unrelated to RS trajectory by construction)."""
    return n_gone >= 3 and n_gone * 2 >= prior_member_count


def _evaluate_pruned_while_rising(rs_now: float | None, hist3: list[float], hist6: list[float]) -> dict | None:
    """Pure decision for ONE ticker that left a still-alive theme overnight (already known
    to not be part of a mass-eviction and not present in any theme today — i.e. not moved):
    does this look like a #368/F3 hold regression?

    `hist3`/`hist6` are the ticker's most-recent-first rs_composite history (3 and 6
    sessions respectively, from ONE `get_recent_rs_batch(..., days=6)` call — hist3 is
    hist6[:3]). Mirrors the ENGINE'S OWN exact prune-candidacy gate before judging rising,
    so a ticker the engine was never going to prune in the first place (e.g. RS 40, never a
    candidate at all) can't false-fire here for leaving for some OTHER reason (validation,
    reassignment already excluded upstream):
      rs_now < HARD(25)          -> a prune candidate every day
      HARD <= rs_now < SOFT(35)  -> a candidate ONLY if the last 3 sessions were ALL < SOFT
      rs_now >= SOFT             -> never a prune candidate — not this check's concern
    Returns a flag dict only when it WAS a prune candidate AND `_rs_rising_mirror(hist6)` is
    True. Returns None otherwise (falling exits — the hold correctly still prunes those).
    """
    if rs_now is None:
        return None
    if rs_now < _PRUNE_RS_HARD_MIRROR:
        candidate = True
    elif rs_now < _PRUNE_RS_SOFT_MIRROR:
        candidate = len(hist3) >= 3 and all(v < _PRUNE_RS_SOFT_MIRROR for v in hist3)
    else:
        candidate = False
    if not candidate or not _rs_rising_mirror(hist6):
        return None
    return {"rs_now": rs_now, "hist": list(hist6)}


async def _check_theme_retirements(conn, today) -> dict[str, Any]:
    """Signature A. Isolated by the caller's try/except — a bad query here must not blind
    signature B. Returns {"flags": [...], "errors": [...]}."""
    out: dict[str, Any] = {"flags": [], "errors": []}
    start = today - timedelta(days=1)
    names = await get_theme_retired_candidate_names(conn, start, today)
    if not names:
        return out
    history_by_name = await get_theme_history_window(conn, names, today, lookback_days=7)
    for name in names:
        verdict = _evaluate_theme_retirement(today, history_by_name.get(name, []))
        if verdict is not None:
            out["flags"].append({"name": name, **verdict})
    return out


async def _check_pruned_while_rising(conn, today, prior_date) -> dict[str, Any]:
    """Signature B. Isolated by the caller's try/except — a bad query here must not blind
    signature A. Returns {"flags": [...], "errors": [...]}."""
    out: dict[str, Any] = {"flags": [], "errors": []}
    departures = await get_theme_member_departures(conn, today, prior_date)
    if not departures:
        return out

    by_theme: dict[str, list[dict]] = {}
    for d in departures:
        by_theme.setdefault(d["name"], []).append(d)

    candidates: list[dict] = []
    for name, rows in by_theme.items():
        # Mass-eviction is judged on ALL leavers (moved + not-moved) — a structural split
        # (e.g. one 18-member theme dividing into two child themes, 16 moved + 1 straggler)
        # must be excluded WHOLESALE, before the moved-filter would otherwise shrink it down
        # to "1 of 18", hiding the split and scoring the straggler as an ordinary prune day.
        prior_member_count = rows[0]["prior_member_count"]
        if _is_mass_eviction(len(rows), prior_member_count):
            continue
        gone = [r for r in rows if not r["moved_today"]]
        if not gone:
            continue
        candidates.extend({"name": name, "ticker": r["ticker"]} for r in gone)

    if not candidates:
        return out

    tickers = sorted({c["ticker"] for c in candidates})
    # rs_now must be the ticker's EXACT-today value, not "most recent available" —
    # get_recent_rs_batch silently falls back to a prior date for a ticker absent from
    # today's snapshot, which would misrepresent a stale value as current. A ticker with no
    # row for `today` at all is exactly the engine's SEPARATE missing-data prune branch
    # (theme_engine.py's `missing_rs_tickers`), which prunes on 5-day history and never
    # consults `_rs_rising` — scoring it here would be a false analogy to what the engine did.
    rs_today = await get_rs_on_date(conn, tickers, today)
    rs_hist = await get_recent_rs_batch(tickers, today, days=6)
    for c in candidates:
        rs_now = rs_today.get(c["ticker"])
        if rs_now is None:
            continue  # not in today's RS snapshot — the engine's other prune path, not ours
        hist6 = rs_hist.get(c["ticker"], [])
        verdict = _evaluate_pruned_while_rising(rs_now, hist6[:3], hist6)
        if verdict is not None:
            out["flags"].append({**c, **verdict})
    return out


def _format_retirement_flag(f: dict[str, Any]) -> str:
    # Plain text, no Markdown entities — this line lives INSIDE a ``` code block (below), where
    # Telegram Legacy Markdown does not parse further formatting. Theme names are free text from
    # Haiku (can contain &, -, digits, anything) — inline backticks/asterisks around a dynamic
    # value is exactly the class of bug #148/#121 exist to prevent (unbalanced entities -> 400).
    return (
        f"RETIRED  {f['name']}: was Fading, rs_avg {f['prior_rs_avg']:.1f} "
        f"on {f['prior_date'].isoformat()}, gone the next run"
    )


def _format_prune_flag(f: dict[str, Any]) -> str:
    hist = ", ".join(f"{v:.0f}" for v in f["hist"])
    return (
        f"PRUNED   {f['ticker']} left {f['name']}: RS {f['rs_now']:.1f} while rising — "
        f"last 6 sessions (newest→oldest): {hist}"
    )


async def run_theme_quality_check(conn=None) -> dict[str, Any]:
    """Nightly THEME QUALITY check (#531, operator 2026-08-04) — the two signatures measured
    and hand-verified above. Runs both signatures, each isolated so a bad query in one can't
    blind the other; dedupes each against its own permanent history (the inert-sweep idiom,
    failing OPEN); logs an audit row + sends ONE grouped Telegram only for NEW findings.

    Returns a summary dict: dates used, per-signature flag counts (fresh only), errors.
    """
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as acquired:
            return await run_theme_quality_check(acquired)

    today = et_today()
    summary: dict[str, Any] = {
        "today": today.isoformat(),
        "retired_while_healthy": [],
        "pruned_while_rising": [],
        "assignment_producing_nothing": [],
        "errors": [],
    }

    # ── Signature C — THE ASSIGNMENT STAGE PRODUCED NOTHING (#543, 2026-08-07) ────────────────
    # Added after a TOTAL, TEN-DAY, SILENT outage: every `theme_assignment` call from 07-28 to
    # 08-07 burned exactly its 4000-token ceiling and ended in either "proposed 0 assignment(s)"
    # (11x) or `assignment_silent_stop` (2x). Not one successful assignment in the window, while
    # the board showed 91 themes averaging 3.2 members and a whole gapping software cohort in
    # none. The operator found it by asking; nothing told anyone.
    #
    # It hid because "proposed 0 assignments" is a TELEMETRY line, not an error — a total outage
    # reads exactly like a quiet night. So the signature is deliberately about the STREAK, not a
    # single night: zero assignments on ONE night is normal (nothing needed re-homing); zero on
    # THREE CONSECUTIVE nights the engine ran is a dead stage.
    try:
        c_rows = await conn.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
                   count(*) FILTER (WHERE event_type = 'assignment_silent_stop')       AS stops,
                   count(*) FILTER (WHERE event_type = 'assignment_llm_proposed'
                                    AND summary LIKE '%proposed 0 assignment%')        AS zeros,
                   count(*) FILTER (WHERE event_type = 'assignment_llm_proposed'
                                    AND summary NOT LIKE '%proposed 0 assignment%')    AS produced
              FROM mi_audit_log
             WHERE event_type IN ('assignment_llm_proposed', 'assignment_silent_stop')
               AND created_at > now() - interval '10 days'
             GROUP BY 1 ORDER BY 1 DESC LIMIT 5
        """)
        # Only nights the stage actually RAN count — a weekend with no run is not a failure.
        ran = [r for r in c_rows if (r["stops"] + r["zeros"] + r["produced"]) > 0]
        barren = []
        for r in ran[:3]:
            if r["produced"] == 0:
                barren.append({"date": r["d"].isoformat(),
                               "silent_stops": int(r["stops"]), "zero_proposals": int(r["zeros"])})
            else:
                break          # streak broken by a night that produced something
        if len(barren) >= 3:
            summary["assignment_producing_nothing"] = barren
    except Exception as e:
        logger.warning("theme_quality_check: assignment-barren signature failed: %s", e)
        summary["errors"].append({"signature": "assignment_producing_nothing", "error": str(e)})

    # ── Signature A ──────────────────────────────────────────────────────────────────────────
    try:
        a_result = await _check_theme_retirements(conn, today)
        summary["retired_while_healthy"] = a_result["flags"]
    except Exception as e:
        logger.warning("theme_quality_check: retirement signature failed: %s", e)
        summary["errors"].append({"signature": "retired_while_healthy", "error": str(e)})

    # ── Signature B ──────────────────────────────────────────────────────────────────────────
    try:
        dates = await get_latest_two_theme_dates(conn)
        if dates is None:
            summary["errors"].append({"signature": "pruned_while_rising",
                                       "error": "fewer than 2 distinct theme_date snapshots — skip"})
        else:
            latest_date, prior_date = dates
            b_result = await _check_pruned_while_rising(conn, latest_date, prior_date)
            summary["pruned_while_rising"] = b_result["flags"]
    except Exception as e:
        logger.warning("theme_quality_check: prune signature failed: %s", e)
        summary["errors"].append({"signature": "pruned_while_rising", "error": str(e)})

    # ── Dedupe (fails OPEN — a broken read costs a duplicate alert, never a missed one) ───────
    async def _dedupe(flags: list[dict], event_type: str, key_fn) -> list[dict]:
        try:
            already = await get_theme_quality_alerted_targets(conn, event_type)
        except Exception as e:
            logger.warning("theme_quality_check: dedupe read failed for %s (will re-announce): %s",
                           event_type, e)
            already = set()
        return [f for f in flags if key_fn(f) not in already]

    fresh_retirements = await _dedupe(
        summary["retired_while_healthy"], "theme_retired_while_healthy", lambda f: f["name"])
    fresh_prunes = await _dedupe(
        summary["pruned_while_rising"], "theme_member_pruned_while_rising",
        lambda f: f"{f['ticker']}@{f['name']}")

    for f in fresh_retirements:
        await log_audit_event(
            "theme_retired_while_healthy",
            f"{f['name']}: retired while healthy (Fading rs_avg={f['prior_rs_avg']:.1f} "
            f"on {f['prior_date'].isoformat()})",
            detail=str(f),
        )
    for f in fresh_prunes:
        await log_audit_event(
            "theme_member_pruned_while_rising",
            f"{f['ticker']}@{f['name']}: pruned while RS rising (RS={f['rs_now']:.1f})",
            detail=str(f),
        )

    summary["retired_while_healthy"] = fresh_retirements
    summary["pruned_while_rising"] = fresh_prunes

    # ── Alert ────────────────────────────────────────────────────────────────────────────────
    barren = summary.get("assignment_producing_nothing") or []
    if barren:
        # Deliberately NOT deduped and NOT grouped with the two lifecycle signatures: this is a
        # STAGE OUTAGE, not a per-theme finding, and it must keep shouting every night until it
        # is fixed. The 07-28→08-07 outage was silent for ten days precisely because its only
        # trace was a routine-looking telemetry line.
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            n = len(barren)
            body = "\n".join([
                "🔴 THEME ASSIGNMENT IS PRODUCING NOTHING",
                "",
                f"{n} consecutive engine nights with ZERO successful assignments:",
                "```",
                *[f"{b['date']}  silent_stops={b['silent_stops']}  zero_proposals={b['zero_proposals']}"
                  for b in barren],
                "```",
                "This is the stage that puts stocks INTO themes. Zero for one night is normal;",
                "zero for three consecutive runs means it is dead — check max_tokens exhaustion",
                "and tool_choice on theme_engine's assignment loop (#543, the 2026-08-07 outage).",
            ])
            await send_telegram_message(body)
        except Exception as e:
            logger.warning("theme_quality_check: barren-assignment telegram failed: %s", e)
            summary["errors"].append({"telegram_barren": str(e)})
        await log_audit_event(
            "theme_assignment_barren",
            f"{len(barren)} consecutive engine nights with zero successful theme assignments",
            detail=str(barren),
        )

    if fresh_retirements or fresh_prunes:
        # Dynamic free-text (theme names, tickers) goes INSIDE a ``` code block — the same
        # discipline as run_inert_sweep_check / run_row_count_drift_sweep — so Legacy Markdown
        # never attempts to parse entities out of Haiku-generated names (verify-operator-facing-
        # surface: an unbalanced `_`/`*` in a name must not be able to lose the whole alert).
        lines = ["🩺 THEME QUALITY", ""]
        if fresh_retirements:
            lines.append("Retired while healthy (#368/F2 regression guard):")
            lines.append("```")
            lines.extend(_format_retirement_flag(f) for f in fresh_retirements)
            lines.append("```")
        if fresh_prunes:
            lines.append("Member pruned while rising (#368/F3 regression guard):")
            lines.append("```")
            lines.extend(_format_prune_flag(f) for f in fresh_prunes)
            lines.append("```")
        lines.append("")
        lines.append("These are the two theme-lifecycle bugs #368 fixed (F2/F3) — this is the "
                     "nightly guard that the fixes keep working (#531).")
        body = "\n".join(lines)
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(body)
        except Exception as e:
            logger.warning("theme_quality_check: telegram send failed: %s", e)
            summary["errors"].append({"telegram": str(e)})
    else:
        note = (
            f"clean: {len(summary.get('retired_while_healthy', []))} retirement flag(s), "
            f"{len(summary.get('pruned_while_rising', []))} prune flag(s)"
            + (f"; {len(summary['errors'])} error(s)" if summary["errors"] else "")
        )
        await log_audit_event("theme_quality_clean", note, detail=str(summary))

    if summary["errors"]:
        logger.warning("theme_quality_check completed with %d error(s): %s",
                       len(summary["errors"]), summary["errors"])

    return summary


# ══════════════════════════════════════════════════════════════════════════════════════════════
# #534 D3(b) — ECOSYSTEM REACTIVATION detector (2026-08-05, design doc
# docs/analysis/534_theme_universe_expansion_2026-08-05.md §5b). Deterministic, $0, no LLM.
#
# THE SIGNAL: a dormant ecosystem "coming back alive" (operator, 2026-08-04, on the duplicate
# defense themes: "multiple defense stocks moving and having EP around the same time… this group
# is coming back alive after a dormant period"). EP alerts are the only signal in the system that
# sees a wake-up on day one — RS is a 1/3/6-month lookback, so a dormant group has low RS by
# construction, and on 08-04 the signal EXISTED in prod only as five duplicate births nobody
# aggregated. This detector is that aggregation: nightly, map recent HIGH EP tickers to their
# ecosystems (mi_theme_ecosystems lineage memory), and fire when a DORMANT ecosystem collects a
# cluster against a quiet trailing baseline. Observability + a discovery seed — NEVER a theme
# birth (the source is allowlist-excluded from auto-promote; the birth gate owns promotion).
#
# THRESHOLDS — DERIVED, NOT PICKED (replayed over 66 real prod sessions 2026-05-06..2026-08-05,
# 324 HIGH ticker-day alerts; capture + scripts in the #534 build report):
#
#   WINDOW = 5 sessions, CLUSTER >= 3 distinct tickers. The (session, ecosystem) cluster-size
#   distribution over the window: size-1 = 104 pairs, size-2 = 35, size-3 = 11, size-4 = 4
#   (dormant-ecosystem subset: 48 / 15 / 3 / 2). K=3 sits at the elbow: pairs are ~10× more
#   common than triples and are ALREADY other machinery's territory (Lane-2's 2-member same-day
#   anchor; the birth gate's two-sighting arm). Hand-checked what K=2 would admit — 4 extra
#   incidents: DDOG+FTNT (unrelated May earnings gaps), QBTS+RGTI (a pair, not a group),
#   AEHR+TSEM (unconnected semi stories), HUT+IREN (the July miner wake-up — real, but the
#   Lane-2 v2 registry's own acceptance case, 2-member-shaped). K=3 keeps only group-scale.
#
#   BASELINE = 15 prior sessions, QUIET = <= 1 distinct mapped ticker. Across the whole replay
#   only TWO dormant-ecosystem clusters >= 3 exist, and the baseline separates them exactly:
#   E-DEF 08-04/08-05 (baseline 0 — fires, the real wake-up) vs E-AISEMI 07-31..08-05
#   (ARM+LRCX+SIMO, all reporting EARNINGS the same night 07-30, baseline 2 = AEHR+TSEM —
#   correctly suppressed). Q=2 would admit the semis earnings night; B=10 shortens the memory
#   below AEHR/TSEM and admits it too. THIS is the §5 confounder proof: the dormancy + quiet-
#   baseline preconditions are what separate a wake-up from a broad earnings week — the late-July
#   "Technology cluster of 14" fired NOTHING (its names map to LIVE ecosystems — E-AISEMI,
#   E-AIINFRA, E-SAAS, all with non-Fading themes — or map nowhere, having no theme lineage).
#
#   DORMANCY is judged at the WINDOW-START session S0 (board strictly before S0, 7-day liveness
#   horizon mirroring get_active_themes(stale_after_days=7)): dormant = no mapped live theme, or
#   every one Fading. Anchored at S0, not tonight, because births DURING the window are the
#   engine REACTING to the same burst (all five 08-04 defense births land inside it) — judged at
#   D they mask the exact signal this detector exists to surface. Measured: judging dormancy at
#   D never fires at all on the fixture.
#
#   MAPPING: ticker -> e_codes via ANY non-Retired mi_themes membership row (theme_date <= D)
#   whose name is in mi_theme_ecosystems — INCLUDING tonight's board (the reactive births are
#   how new wake-up names reach the dormant lineage's e_code; strictly-prior membership maps 0
#   of the 4 defense tickers — the dead themes never held them), else the taxonomy's exemplar
#   tickers. SECTOR fallback was measured and REJECTED: a conservative 1:1 sector map added
#   E-INDL@05-06 (9 unrelated industrials — CYRX cold-chain, GEO prisons, BLBD buses: a breadth
#   week, not a group) and E-COMM@05-14 (NBIS+STUB+VSNT — three unrelated stories sharing a
#   sector label). Sector grouping is exactly the "earnings surge is not a theme" trap.
#
# RESULT at the chosen shape: ONE incident in 66 sessions — E-DEF first-fire 2026-08-04,
# 4 tickers {AMRC, PLTR, TSAT, VOYG}, baseline 0, board-at-S0 all-Fading. (KTOS, the 5th design
# ticker, alerts 08-05 and joins via that night's board when the engine maps it.) An incident
# self-terminates in ~W sessions (its own alerts walk into the baseline; the reactive births end
# dormancy at S0 as the window advances) — measured 4 fire-days max, hence the RECENCY-bounded
# dedupe (10 days > the longest incident, < a genuine re-awakening months later).
#
# WIRING: _post_nightly_audit_job (scheduler.py), 17:30 ET — after the 17:00 theme engine, so
# tonight's board + ecosystem mappings exist when the detector reads them. Own try/except;
# dedupe fails OPEN; a missing table/column is SKIPPED with a distinct reason, never a finding.
# ══════════════════════════════════════════════════════════════════════════════════════════════

REACT_WINDOW_SESSIONS = 5    # burst window (sessions present in the data, never calendar days)
REACT_BASELINE_SESSIONS = 15  # trailing quiet-memory window (≈ the design's "prior three weeks")
REACT_MIN_CLUSTER = 3        # distinct mapped alert tickers in-window to call it a group
REACT_MAX_BASELINE = 1       # "quiet": at most 1 distinct mapped ticker in the baseline
REACT_DEDUPE_DAYS = 10       # one announcement per incident (longest measured incident: 4 fire-days)
_REACT_BOARD_LOOKBACK_DAYS = 7  # mirrors get_active_themes(stale_after_days=7) — pinned by test


def _is_missing_db_object(e: Exception) -> bool:
    """A missing table/column (asyncpg UndefinedTable/UndefinedColumn, or the textual
    'does not exist' a raw driver error carries) — the caller SKIPS with a distinct
    reason instead of reporting a finding or an error. Checked by NAME so this module
    never imports asyncpg (lightweight-import discipline, see _is_trading_day)."""
    return type(e).__name__ in ("UndefinedTableError", "UndefinedColumnError") \
        or "does not exist" in str(e)


def _evaluate_ecosystem_reactivation(
    window_by_eco: dict[str, set],
    baseline_by_eco: dict[str, set],
    live_stages_by_eco: dict[str, dict[str, str]],
    window_dates_by_eco: dict[str, set] | None = None,
) -> list[dict[str, Any]]:
    """Pure decision over pre-aggregated per-ecosystem sets: fire when a DORMANT
    ecosystem (no live theme at window-start, or every one Fading) collected
    >= REACT_MIN_CLUSTER distinct alert tickers in-window against a quiet trailing
    baseline (<= REACT_MAX_BASELINE distinct mapped tickers). Returns flag dicts,
    deterministically ordered by e_code. All three preconditions measured against
    real prod incidents — see the #534 section header for what each one excludes."""
    flags: list[dict[str, Any]] = []
    for e_code in sorted(window_by_eco):
        tickers = window_by_eco[e_code]
        if len(tickers) < REACT_MIN_CLUSTER:
            continue
        baseline = baseline_by_eco.get(e_code, set())
        if len(baseline) > REACT_MAX_BASELINE:
            continue  # not quiet — the E-AISEMI earnings-night shape stays silent
        stages = live_stages_by_eco.get(e_code, {})
        if stages and any(st != "Fading" for st in stages.values()):
            continue  # a live non-Fading theme at window start — not dormant
        dates = (window_dates_by_eco or {}).get(e_code, set())
        flags.append({
            "e_code": e_code,
            "tickers": sorted(tickers),
            "n_window": len(tickers),
            "n_days": len(dates),
            "n_baseline": len(baseline),
            "baseline_tickers": sorted(baseline),
            "fading_themes": sorted(stages),
        })
    return flags


def _format_reactivation_flag(f: dict[str, Any], display_name: str = "") -> list[str]:
    """The operator lines for one firing — plain text inside a ``` code block (the
    #148/#121 discipline: no Markdown entities around dynamic strings)."""
    disp = f" ({display_name})" if display_name else ""
    dorm = ("all themes Fading" if f.get("fading_themes") else "no live theme")
    days = f["n_days"] if f.get("n_days") else "?"
    return [
        f"{f['e_code']}{disp} reactivating: {f['n_window']} EPs/{days}d, {dorm}",
        f"  {' '.join(f['tickers'])} · baseline {f['n_baseline']} "
        f"in prior {REACT_BASELINE_SESSIONS} sessions",
    ]


async def run_ecosystem_reactivation_check(conn=None) -> dict[str, Any]:
    """Nightly ECOSYSTEM REACTIVATION detector (#534 D3(b)) — see the section header
    for the derived thresholds and the both-ways measurement. Fires an operator line
    + seeds a discovery candidate (source='ecosystem_reactivation', allowlist-excluded
    from auto-promote — the birth gate owns whether anything becomes a theme).

    Returns {today, sessions_used, flags (fresh only), skipped, errors}.
    """
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as acquired:
            return await run_ecosystem_reactivation_check(acquired)

    today = et_today()
    summary: dict[str, Any] = {
        "today": today.isoformat(), "sessions_used": 0,
        "flags": [], "skipped": [], "errors": [],
    }

    need = REACT_WINDOW_SESSIONS + REACT_BASELINE_SESSIONS
    try:
        sessions = await get_reactivation_sessions(conn, today, need)
        if len(sessions) < need:
            summary["skipped"].append(
                f"only {len(sessions)} sessions in the data (need {need}) — skip")
            return summary
        summary["sessions_used"] = len(sessions)
        window_days = sessions[-REACT_WINDOW_SESSIONS:]
        baseline_days = sessions[:-REACT_WINDOW_SESSIONS]
        s0 = window_days[0]

        alerts = await get_high_ep_ticker_days(conn, sessions[0], today)
        tickers = sorted({a["ticker"] for a in alerts})
        membership = await get_ticker_ecosystem_membership(conn, tickers, today)

        # Exemplar fallback from the taxonomy (fail-safe loader: a broken YAML
        # degrades to membership-only mapping, never raises).
        exemplars: dict[str, str] = {}
        display: dict[str, str] = {}
        try:
            from agents.market_intelligence.theme_ecosystems import get_ecosystems
            for eco in get_ecosystems():
                code = eco.get("e_code")
                if not code:
                    continue
                display[code] = eco.get("name") or ""
                for tk in (eco.get("exemplars") or []):
                    exemplars[str(tk).upper()] = code
        except Exception as e:
            logger.warning("ecosystem_reactivation: taxonomy load failed — "
                           "membership-only mapping: %s", e)

        def _map(tk: str) -> list[str]:
            ecos = membership.get(tk)
            if ecos:
                return ecos
            return [exemplars[tk]] if tk in exemplars else []

        window_set = set(window_days)
        win_by_eco: dict[str, set] = {}
        base_by_eco: dict[str, set] = {}
        win_dates_by_eco: dict[str, set] = {}
        for a in alerts:
            for ec in _map(a["ticker"]):
                if a["alert_date"] in window_set:
                    win_by_eco.setdefault(ec, set()).add(a["ticker"])
                    win_dates_by_eco.setdefault(ec, set()).add(a["alert_date"])
                else:
                    base_by_eco.setdefault(ec, set()).add(a["ticker"])

        board_rows = await get_mapped_theme_stages_before(
            conn, s0, lookback_days=_REACT_BOARD_LOOKBACK_DAYS)
        live_stages: dict[str, dict[str, str]] = {}
        for r in board_rows:
            live_stages.setdefault(r["e_code"], {})[r["name"]] = r["stage"]

        flags = _evaluate_ecosystem_reactivation(
            win_by_eco, base_by_eco, live_stages, win_dates_by_eco)
    except Exception as e:
        if _is_missing_db_object(e):
            summary["skipped"].append(f"missing table/column — skip: {e}")
            logger.warning("ecosystem_reactivation: missing DB object — skipped: %s", e)
        else:
            logger.warning("ecosystem_reactivation: detection failed: %s", e)
            summary["errors"].append({"stage": "detect", "error": str(e)})
        return summary

    # ── Dedupe (RECENCY-bounded, fails OPEN — a broken read costs a duplicate alert,
    #    never a missed one) ─────────────────────────────────────────────────────────
    try:
        already = await get_reactivation_alerted_ecosystems(conn, days=REACT_DEDUPE_DAYS)
    except Exception as e:
        logger.warning("ecosystem_reactivation: dedupe read failed (will re-announce): %s", e)
        already = set()
    fresh = [f for f in flags if f["e_code"] not in already]
    summary["flags"] = fresh

    if not fresh:
        await log_audit_event(
            "ecosystem_reactivation_clean",
            f"clean: {len(flags)} flag(s), {len(flags) - len(fresh)} deduped"
            + (f"; {len(summary['skipped'])} skipped" if summary["skipped"] else ""),
            detail=str(summary),
        )
        return summary

    # ── Audit + discovery seed per fresh firing ───────────────────────────────────
    for f in fresh:
        await log_audit_event(
            "ecosystem_reactivation",
            f"{f['e_code']}: reactivating — {f['n_window']} EP tickers in "
            f"{REACT_WINDOW_SESSIONS} sessions ({', '.join(f['tickers'])}), "
            f"baseline {f['n_baseline']}, "
            + ("all themes Fading" if f["fading_themes"] else "no live theme"),
            detail=str(f),
        )
        try:
            hist = f["fading_themes"]
            thesis = (
                f"Ecosystem reactivation signal ({today.isoformat()}): "
                f"{f['n_window']} HIGH EP alerts in {REACT_WINDOW_SESSIONS} sessions "
                f"({', '.join(f['tickers'])}) vs {f['n_baseline']} in the prior "
                f"{REACT_BASELINE_SESSIONS}; "
                + (f"dormant lineage at window start: {', '.join(hist)}."
                   if hist else "no live theme at window start.")
            )
            await persist_reactivation_seed(today, f["e_code"], f["tickers"], thesis)
        except Exception as e:
            # The seed is the secondary output — its failure must not cost the alert.
            logger.warning("ecosystem_reactivation: seed write failed for %s: %s",
                           f["e_code"], e)
            summary["errors"].append({"stage": "seed", "e_code": f["e_code"],
                                      "error": str(e)})

    # ── Alert (ONE grouped Telegram; dynamic text inside a code block) ────────────
    lines = ["🌱 ECOSYSTEM REACTIVATION", "", "```"]
    for f in fresh:
        lines.extend(_format_reactivation_flag(f, display.get(f["e_code"], "")))
    lines.append("```")
    lines.append("")
    lines.append("A dormant ecosystem is collecting fresh EP alerts — a discovery "
                 "candidate was seeded with the cohort. The birth gate decides "
                 "whether it becomes a theme; nothing is auto-promoted (#534).")
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message("\n".join(lines))
    except Exception as e:
        logger.warning("ecosystem_reactivation: telegram send failed: %s", e)
        summary["errors"].append({"telegram": str(e)})

    return summary



# ── DEAD-COLUMN SWEEP (#543, 2026-08-08) ──────────────────────────────────────────────────
#
# Operator, after finding `crypto_btc_dominance.slope_30d` NULL in all 97 rows: *"we need
# better dq checks for our tables and data, null checks at the very least, anomaly detection,
# row counts, etc."*
#
# Most of that already exists — `run_null_rate_sweep` (a populated column going null),
# `run_job_liveness_sweep` (a job producing no rows), the #340 row-count drift sweep, and the
# L1/L2/L3 anomaly system. `slope_30d` slipped through TWO specific holes:
#
#   1. `_evaluate_column` SKIPS always-null columns BY DESIGN — its docstring says so:
#      "always-null → None (never met the populated bar)". That is correct for its job (catching
#      a column that BROKE) and it is precisely why it cannot see one that was never wired.
#   2. `_NULL_SWEEP_TABLES` lists 5 tables. `crypto_btc_dominance` is not one of them, so
#      nothing was looking anyway.
#
# THIS SWEEP IS THE COMPLEMENT, not a replacement: a numeric column that is 100% NULL across
# its ENTIRE history, on a table with real rows, is either dead or never wired. That is binary,
# not a rate — which is what makes it cheap to check and near-impossible to false-positive on.
#
# ⚠ REPORTED ONCE PER COLUMN, EVER. This is a BUILD defect, not a daily condition: a column
# unwired today is unwired tomorrow, and re-announcing it every night is how a guard becomes
# noise and gets muted. The audit log IS the dedupe state (same pattern as `cost_new_lane`).
_DEAD_COL_MIN_ROWS = 30          # below this the table is too young to judge
_DEAD_COL_TABLE_PREFIXES = ("mi_", "crypto_")


async def run_dead_column_sweep(conn=None) -> dict[str, Any]:
    """Numeric columns that have NEVER been populated. Announced once per column, ever.

    Returns {"tables_scanned", "dead" [list], "errors" [list]}.
    """
    from agents.market_intelligence.db import get_pool, log_audit_event

    async def _run(c) -> dict[str, Any]:
        out: dict[str, Any] = {"tables_scanned": 0, "dead": [], "errors": []}
        tables = [r["table_name"] for r in await c.fetch(
            """
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
               AND (table_name LIKE 'mi\\_%' OR table_name LIKE 'crypto\\_%')
             ORDER BY table_name
            """)]
        already = {r["summary"] for r in await c.fetch(
            "SELECT summary FROM mi_audit_log WHERE event_type = 'dead_column_detected'")}

        for table in tables:
            try:
                n = await c.fetchval(f'SELECT count(*) FROM "{table}"')
                if not n or n < _DEAD_COL_MIN_ROWS:
                    continue
                out["tables_scanned"] += 1
                cols = [r["column_name"] for r in await c.fetch(
                    """
                    SELECT column_name FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = $1
                       AND data_type = ANY($2::text[])
                    """, table, sorted(_NUMERIC_DATA_TYPES))]
                for col in cols:
                    # count(col) counts NON-NULL. Zero over the whole table = never written.
                    if await c.fetchval(f'SELECT count("{col}") FROM "{table}"'):
                        continue
                    key = f"{table}.{col}"
                    out["dead"].append({"table": table, "column": col, "rows": n,
                                        "new": key not in already})
                    if key not in already:
                        await log_audit_event(
                            "dead_column_detected", key,
                            f'{{"table": "{table}", "column": "{col}", "rows": {n}}}')
            except Exception as e:  # loud-ok: one bad table must not kill the sweep
                out["errors"].append(f"{table}: {type(e).__name__}: {str(e)[:120]}")
                logger.warning(f"dead-column sweep: {table} failed: {e}")

        fresh = [d for d in out["dead"] if d["new"]]
        if fresh:
            from agents.market_intelligence.briefing import send_telegram_message
            lines = ["🟠 *DEAD COLUMNS* — declared but never once written:", "```"]
            for d in fresh[:10]:
                lines.append(f"{d['table']}.{d['column']}  ({d['rows']} rows, 0 populated)")
            lines += ["```", "Either wire the writer or drop the column — a column nothing "
                      "writes is a promise the schema keeps making and nothing honours."]
            await send_telegram_message("\n".join(lines))
        return out

    if conn is not None:
        return await _run(conn)
    pool = await get_pool()
    async with pool.acquire() as acquired:
        return await _run(acquired)

# ── ACCOUNT-MODE GRADUATION SWEEP (2026-08-11) ────────────────────────────────────────────
#
# Operator, after the get_flag_universe path-(c) rot (a query hardcoding
# `account_mode='paper'` that went silently dark for ~7 weeks when MAGNA53 graduated to
# live): *"1) find out if there's more cases like this ... 2) make sure when we graduate a
# setup from paper to live, everything graduates with it and nothing is left behind to
# become stale and dead."*
#
# The deploy gate (scripts/preflight_account_mode_literals.py, [5o/7]) forces every
# hardcoded account-mode/phase literal in production SQL to carry a reviewed
# `mode-ok:` annotation — that makes the INVENTORY complete, but a static check can
# never see the ROT moment: the literal is correct the day it ships and still
# annotated the day it stops matching. This sweep watches for the two data-side
# events that CREATE the rot, and replays the inventory exactly then:
#
#   1. PHASE TRANSITION — any change in `mi_strategies.phase` (the graduation
#      itself). The previous phase map is persisted in the audit log
#      (`strategy_phase_snapshot`); a diff announces ONCE (the snapshot advancing
#      IS the dedupe) with the pinned-literal inventory as the review checklist.
#      This is the day-one catch: the known case would have surfaced the night of
#      2026-06-22 instead of 7 weeks later.
#   2. DORMANT BOOK — an account_mode book in mi_live_trades with a real history
#      (≥30 rows) that has written NOTHING in 21+ days while another book is
#      active, AND code still pins queries to it. Announced once per (table,
#      mode) EVER (dead-column sweep pattern: the audit log is the dedupe state).
#      This is the backstop for a graduation done any way that skips the
#      registry, and it re-fires the review if an annotated pin outlives its era.
#
# ⚠ SILENT on a healthy day BY DESIGN: no phase change + no newly dormant pinned
# book → no Telegram, no audit rows beyond the rolling snapshot baseline. Both
# checks are binary and conjunctive — near-impossible to false-positive (a guard
# that always fires is not a guard, CLAUDE.md 08-03).
_GRAD_SNAPSHOT_EVENT = "strategy_phase_snapshot"
_GRAD_TRANSITION_EVENT = "strategy_phase_transition"
_DORMANT_BOOK_EVENT = "account_mode_book_dormant"
_DORMANT_BOOK_DAYS = 21          # ~a month of calendar; long enough that a thin week can't trip it
_DORMANT_BOOK_MIN_ROWS = 30      # below this the book never really lived — nothing to mourn


def _pinned_literal_inventory() -> tuple[list[dict], str | None]:
    """The gate's annotated-literal inventory (file:line + literal), fail-open.

    Imported from the deploy gate so the checklist the operator sees at a
    graduation is EXACTLY the set the gate enforces — one scanner, two moments.
    """
    try:
        from scripts.preflight_account_mode_literals import collect_pinned_sites
        return collect_pinned_sites(), None
    except Exception as e:  # loud-ok: inventory miss degrades the message, never kills the sweep
        return [], f"{type(e).__name__}: {str(e)[:120]}"


def _format_pinned_sites(sites: list[dict], cap: int = 20) -> list[str]:
    lines = [f"{s['file']}:{s['line']}  {s['text']}" for s in sites[:cap]]
    if len(sites) > cap:
        lines.append(f"… and {len(sites) - cap} more (run scripts/preflight_account_mode_literals.py)")
    return lines


async def run_account_mode_graduation_sweep(conn=None) -> dict[str, Any]:
    """Announce phase transitions + dormant-but-still-pinned books. Once each, ever.

    Returns {"transitions": [...], "dormant": [...], "baseline": bool, "errors": [...]}.
    """
    from agents.market_intelligence.db import get_pool, log_audit_event

    async def _run(c) -> dict[str, Any]:
        out: dict[str, Any] = {"transitions": [], "dormant": [], "baseline": False,
                               "errors": []}
        tg_blocks: list[str] = []

        # ── 1. Phase-transition watch (the graduation moment itself) ────────
        try:
            rows = await c.fetch(
                "SELECT strategy_id, phase FROM mi_strategies ORDER BY strategy_id")
            current = {r["strategy_id"]: r["phase"] for r in rows}
            fingerprint = ",".join(f"{k}:{v}" for k, v in sorted(current.items()))
            prev_row = await c.fetchrow(
                """
                SELECT summary FROM mi_audit_log
                 WHERE event_type = $1
                 ORDER BY created_at DESC LIMIT 1
                """, _GRAD_SNAPSHOT_EVENT)
            if prev_row is None:
                # First run on this DB: pin the baseline SILENTLY (announcing the
                # entire registry on day one is noise, not signal).
                await log_audit_event(_GRAD_SNAPSHOT_EVENT, fingerprint)
                out["baseline"] = True
            elif prev_row["summary"] != fingerprint:
                prev = {}
                for part in (prev_row["summary"] or "").split(","):
                    if ":" in part:
                        k, _, v = part.partition(":")
                        prev[k] = v
                changes = [
                    {"strategy_id": sid,
                     "old": prev.get(sid, "(new)"),
                     "new": current.get(sid, "(removed)")}
                    for sid in sorted(set(prev) | set(current))
                    if prev.get(sid) != current.get(sid)
                ]
                out["transitions"] = changes
                for ch in changes:
                    await log_audit_event(
                        _GRAD_TRANSITION_EVENT,
                        f"{ch['strategy_id']}: {ch['old']} → {ch['new']}",
                        json.dumps(ch))
                # Advance the snapshot — this IS the once-per-transition dedupe.
                await log_audit_event(_GRAD_SNAPSHOT_EVENT, fingerprint)
                sites, inv_err = _pinned_literal_inventory()
                lines = ["🎓 STRATEGY PHASE CHANGE — graduation checklist", "", "```"]
                lines += [f"{ch['strategy_id']}: {ch['old']} → {ch['new']}" for ch in changes]
                if sites:
                    lines.append("")
                    lines.append("Code still pinned to a mode/phase literal:")
                    lines += _format_pinned_sites(sites)
                lines.append("```")
                lines.append(
                    "A phase change moves the book a strategy writes to. Every pinned "
                    "literal above was correct when annotated — re-judge each against "
                    "the NEW phase map (the get_flag_universe rot class, 7 weeks dark).")
                if inv_err:
                    lines.append(f"(inventory scan failed: {inv_err})")
                tg_blocks.append("\n".join(lines))
        except Exception as e:  # loud-ok: one leg must not kill the other
            out["errors"].append(f"phase_watch: {type(e).__name__}: {str(e)[:120]}")
            logger.warning(f"graduation sweep phase-watch failed: {e}")

        # ── 2. Dormant-book watch (the rot moment, however the flip happened) ──
        try:
            today = _now_et().date()
            cutoff = today - timedelta(days=_DORMANT_BOOK_DAYS)
            book_rows = await c.fetch(
                "SELECT account_mode, COUNT(*) AS n, MAX(alert_date) AS last_row "
                "FROM mi_live_trades GROUP BY account_mode")
            books = [dict(r) for r in book_rows if r["account_mode"]]
            active = {b["account_mode"] for b in books if b["last_row"] and b["last_row"] >= cutoff}
            already = {r["summary"] for r in await c.fetch(
                "SELECT summary FROM mi_audit_log WHERE event_type = $1",
                _DORMANT_BOOK_EVENT)}
            for b in books:
                mode = b["account_mode"]
                if mode in active or b["n"] < _DORMANT_BOOK_MIN_ROWS:
                    continue
                if not active:
                    continue  # EVERYTHING quiet = market halt / outage, not a graduation
                sites, inv_err = _pinned_literal_inventory()
                # account_mode literals ONLY — a `phase='paper'` pin (boot-gate
                # prose, terminal-phase migration) does not READ this book and
                # must not resurrect a dormancy alarm for it.
                pinned = [s for s in sites
                          if s["text"].startswith("account_mode")
                          and s["text"].endswith(f"'{mode}'")]
                if not pinned:
                    continue  # dormant book nothing reads = the expected end state
                key = f"mi_live_trades.{mode}"
                out["dormant"].append({"table": "mi_live_trades", "mode": mode,
                                       "last_row": str(b["last_row"]), "rows": b["n"],
                                       "pinned": len(pinned), "new": key not in already})
                if key in already:
                    continue
                await log_audit_event(
                    _DORMANT_BOOK_EVENT, key,
                    json.dumps({"last_row": str(b["last_row"]), "rows": b["n"],
                                "pinned_sites": len(pinned)}))
                lines = [f"🪦 DORMANT BOOK STILL PINNED — mi_live_trades '{mode}'", "", "```",
                         f"last new row: {b['last_row']}  ({b['n']} lifetime rows)",
                         f"other book(s) active: {', '.join(sorted(active))}",
                         "",
                         f"{len(pinned)} quer{'y' if len(pinned) == 1 else 'ies'} still filter to it:"]
                lines += _format_pinned_sites(pinned)
                lines += ["```",
                          "This book stopped moving but code still reads only it — the "
                          "get_flag_universe class (dark 7 weeks). Re-judge each pin; fix or "
                          "re-annotate. Announced once, ever."]
                if inv_err:
                    lines.append(f"(inventory scan failed: {inv_err})")
                tg_blocks.append("\n".join(lines))
        except Exception as e:  # loud-ok: one leg must not kill the other
            out["errors"].append(f"dormant_book: {type(e).__name__}: {str(e)[:120]}")
            logger.warning(f"graduation sweep dormant-book failed: {e}")

        if tg_blocks:
            from agents.market_intelligence.briefing import send_telegram_message
            for block in tg_blocks:
                await send_telegram_message(block)
        return out

    if conn is not None:
        return await _run(conn)
    pool = await get_pool()
    async with pool.acquire() as acquired:
        return await _run(acquired)


# ── GRADING-HEALTH CHECK (#543 DoD (c), 2026-08-11) ──────────────────────────────────────
#
# The 08-06/08-07 extraction outage graded 14 earnings names/day down on an EXCEPTION and
# nothing watched the one number that separates "weak tape" from "dead component": the share
# of the day's catalyst-grading decisions driven by a system FAILURE rather than by the data.
# Measured on prod mi_audit_log, that share ran 0% (08-05: 0 of 23) → 53% (08-06: 9 of 17)
# → 88% (08-07: 46 of 52) across the incident, while every existing monitor stayed green —
# the failure logged as `catalyst_earnings_revenue_weak_downgrade`, a normal-sounding
# business outcome, so a total component outage read as a quiet day of weak catalysts.
#
# A downgrade because the numbers were weak is the system WORKING. A downgrade — or a grade
# held with no evidence — because the extractor/judge DIED is a component outage wearing a
# quiet tape's clothes. This check counts both sides for the ET day and alerts when the
# failure share dominates.
#
# TELEMETRY ONLY (THE LINE): reads mi_audit_log; changes no grade, rubric, or threshold.
# ⚠ SILENT on a healthy day BY DESIGN — replayed against every day since 2026-05-01 on prod:
# fires on exactly the two incident days (08-06, 08-07); every other day has ≤1 failure
# event and never trips the F≥2 floor (07-27 was a real 1-failure/1-data day — silent).
# NOT deduped: an outage that persists must keep shouting nightly (same reasoning as
# run_truncation_check — the original went quiet BECAUSE its only trace looked routine).
_GRADING_FAILURE_EVENTS = (
    "catalyst_extraction_failed_grade_kept",  # extraction died; grade deliberately kept (post-08-07 shape)
    "extraction_error",                       # extraction raised; rubric never got a chance
    "live_enriched_grade_failed",             # enriched grading path failed -> legacy fallback
    "judge_verdict_truncated",                # judge verdict cut by its ceiling -> discarded to floor
)
_GRADING_DATA_EVENTS = (
    "catalyst_earnings_revenue_weak_downgrade",  # failure-reason rows re-classed below
    "catalyst_prose_mismatch_downgrade",
    "catalyst_pplx_hedge_downgrade",
    "catalyst_downgrade_carveout_applied",       # grading RAN and the data said keep — health evidence
    "catalyst_yoy_recovered_live",               # same: the machinery worked, the data decided
)
# The 08-06/07 failure downgrades logged as weak_downgrade with detail reason
# 'extraction_failed_extraction_call_failed'. That downgrade-on-failure path is gone
# (operator 2026-08-07: "we shouldn't downgrade stocks due to call failure"), but the
# classifier keeps the reason split so a regression that reintroduces it is counted as
# FAILURE from day one — this is exactly what would have caught the original incident.
_GRADING_FAILURE_REASON_PREFIXES = ("extraction_failed", "extraction_error")
_GRADING_MIN_FAILURES = 2    # a single failure is never an outage signal
_GRADING_MIN_DECISIONS = 3   # denominator floor — a two-decision day cannot scream
_GRADING_FAIL_RATIO = 0.5    # incident day one read 53%; healthy days are 0-6%


def _classify_grading_event(event_type: str, detail: str | None) -> str | None:
    """'failure' | 'data' | None (not a grading event).

    A weak_downgrade row is DATA unless its detail reason carries the failure prefix —
    garbled/missing detail defaults to DATA, so bad JSON can never fake an outage."""
    if event_type in _GRADING_FAILURE_EVENTS:
        return "failure"
    if event_type not in _GRADING_DATA_EVENTS:
        return None
    if event_type == "catalyst_earnings_revenue_weak_downgrade":
        reason = ""
        try:
            payload = json.loads(detail or "{}")
            reason = (payload or {}).get("reason") or ""
        except (ValueError, TypeError):
            reason = ""
        if isinstance(reason, str) and reason.startswith(_GRADING_FAILURE_REASON_PREFIXES):
            return "failure"
    return "data"


def _grading_row_ticker(detail: str | None, summary: str | None) -> str:
    """Best-effort ticker for FAILURE-side dedup. Most grading events carry it in the
    detail JSON; the rest prefix the summary with 'TICKER: ...' (judge_verdict_truncated's
    summary IS the subject). Unparseable rows collapse onto '?' — conservative toward
    silence, never toward a louder alert."""
    try:
        t = (json.loads(detail or "{}") or {}).get("ticker")
        if t:
            return str(t)
    except (ValueError, TypeError):
        pass
    return (summary or "").split(":", 1)[0].strip() or "?"


def _evaluate_grading_health(failure_n: int, data_n: int) -> dict[str, Any] | None:
    """The alert predicate, pure. Fires only when failures DOMINATE a real day's
    decisions: ≥_GRADING_MIN_FAILURES failures AND ≥_GRADING_MIN_DECISIONS total
    AND failure share ≥ _GRADING_FAIL_RATIO. Returns the flag dict or None."""
    total = failure_n + data_n
    # The F-floor is redundant at the CURRENT thresholds (a 1-failure day always fails the
    # total or ratio floor too) — kept anyway as the explicit encoding of the rule "a single
    # failure never alerts", so it survives any future re-tuning of the other two numbers.
    if failure_n < _GRADING_MIN_FAILURES or total < _GRADING_MIN_DECISIONS:
        return None
    ratio = failure_n / total
    if ratio < _GRADING_FAIL_RATIO:
        return None
    return {"failure_n": failure_n, "data_n": data_n, "total": total,
            "ratio": round(ratio, 3)}


async def run_grading_health_check(conn=None, today=None) -> dict[str, Any]:
    """Failure-share of today's catalyst-grading decisions (#543 DoD (c)).

    Returns {"today", "failure_n", "data_n", "total", "ratio", "by_event", "flag",
    "errors"} — "flag" is None on a healthy day and nothing is written or sent."""
    from agents.market_intelligence.db import get_pool as _gp, log_audit_event as _log

    async def _run(c) -> dict[str, Any]:
        day = today or et_today()
        out: dict[str, Any] = {"today": day.isoformat(), "failure_n": 0, "data_n": 0,
                               "total": 0, "ratio": 0.0, "by_event": {}, "flag": None,
                               "errors": []}
        rows = await c.fetch(
            """
            SELECT event_type, summary, detail FROM mi_audit_log
             WHERE event_type = ANY($1::text[])
               AND (created_at AT TIME ZONE 'America/New_York')::date = $2::date
            """, list(_GRADING_FAILURE_EVENTS + _GRADING_DATA_EVENTS), day)
        by_event: dict[str, dict[str, int]] = {"failure": {}, "data": {}}
        # FAILURE side dedupes on (event, ticker): "two failures" must mean two NAMES
        # failed, not one name re-logged across scan ticks (prod 08-07: ACMR logged 4x by
        # a broken emission dedup; and a persistently-failing ticker re-extracts every
        # tick since the 08-10 cache fix). DATA-side events are already deduped per
        # ticker/day at emission, and any inflation there only makes this check QUIETER.
        seen_failures: set[tuple[str, str]] = set()
        for r in rows:
            side = _classify_grading_event(r["event_type"], r["detail"])
            if side is None:
                continue
            if side == "failure":
                key = (r["event_type"], _grading_row_ticker(r["detail"], r["summary"]))
                if key in seen_failures:
                    continue
                seen_failures.add(key)
            by_event[side][r["event_type"]] = by_event[side].get(r["event_type"], 0) + 1
        out["failure_n"] = sum(by_event["failure"].values())
        out["data_n"] = sum(by_event["data"].values())
        out["total"] = out["failure_n"] + out["data_n"]
        out["ratio"] = round(out["failure_n"] / out["total"], 3) if out["total"] else 0.0
        out["by_event"] = by_event
        flag = _evaluate_grading_health(out["failure_n"], out["data_n"])
        out["flag"] = flag
        if flag is None:
            return out
        pct = round(100.0 * flag["ratio"])
        await _log(
            "grading_health_alert",
            f"{flag['failure_n']} of {flag['total']} grading decisions today were "
            f"failure-driven ({pct}%)",
            json.dumps(out))
        from agents.market_intelligence.briefing import send_telegram_message
        # Event names are snake_case — #477 parity: they stay inside the code fence.
        lines = ["🔴 *GRADING HEALTH* — today's catalyst grades were decided by component "
                 "FAILURES, not by the data:", "```",
                 f"{flag['failure_n']} of {flag['total']} grading decisions ({pct}%) were "
                 f"a component failing"]
        for ev, n in sorted(by_event["failure"].items(), key=lambda kv: -kv[1]):
            lines.append(f"  {ev:<40} {n}")
        lines += ["```",
                  "A weak-looking day can be a dead grader. Check the extractor/judge "
                  "before trusting today's grades — this pattern is how the 08-06 "
                  "extraction outage hid."]
        await send_telegram_message("\n".join(lines))
        return out

    if conn is not None:
        return await _run(conn)
    pool = await _gp()
    async with pool.acquire() as acquired:
        return await _run(acquired)


# ── PLAN #216 JSONB DOUBLE-ENCODING regression guard (2026-08-17) ──────────────────────
#
# WHY. `db.py`'s jsonb codec auto-json.dumps()es every jsonb bind param; several write-path
# call sites ALSO json.dumps()ed the value themselves before binding `$N::jsonb`, so the
# already-serialised text got encoded a SECOND time — the column ends up holding a JSON
# STRING containing JSON text (`jsonb_typeof(col) = 'string'`) instead of a real object or
# array. Measured on prod 2026-08-17: ~4,300 rows across 9 tables (mi_signal_outcomes.detail
# alone 2440/2441). `scripts/_216_jsonb_repair.py` is the one-time cleanup for the rows
# already written wrong; THIS is the nightly tripwire that keeps the bug from silently
# coming back after a future write-path regression (a new call site re-adding a stray
# json.dumps() before an `::jsonb` bind).
#
# THE SIGNAL: per (table, jsonb column) discovered from information_schema — not the
# 9-table list, which is today's measurement, not a spec — COUNT(*) WHERE
# jsonb_typeof(col)='string'. Tonight's counts ARE the baseline for tomorrow's comparison
# (mirrors run_db_growth_check's audit-log-row-is-the-baseline idiom); no min-baseline-age
# gate is needed here, unlike db-growth, because there is no organic growth RATE to
# pro-rate against — the expected trajectory for a healthy column is flat. A column whose
# count is HIGHER than last night's recorded count is flagged.
#
# KNOWN LIMITATION, named not hidden: this counts ALL string-typed jsonb rows, not only the
# ones that would actually decode to a repairable object/array — a jsonb column that
# legitimately stores a plain string would also register here, and ordinary growth of THAT
# column would look identical to a regression. Accepted because (a) measured on prod
# 2026-08-17, every affected column's string-typed rows were ~100% the double-encoding bug —
# a genuinely string-typed jsonb column is the exception in this codebase, not the norm, and
# (b) discovery is column-wide, so a brand-new legitimately-stringy jsonb column gets one
# cold-start cycle to establish its own baseline, the same shape every other check in this
# file uses. The alternative — decoding every string-typed row nightly the way the repair
# script does, just to tell "did this regress" apart from "did this repair-eligible count
# specifically move" — was rejected as unnecessary weight for a guard whose only job is
# noticing regression, not classifying it; the repair script already owns that precision.
#
# THE LINE: telemetry only — reads jsonb_typeof() on existing columns and writes to
# mi_audit_log / Telegram. Never mutates a row (that is the separate, operator-run repair
# script) and never touches a detector, gate, alert, entry, exit, or sizing path.
_JSONB_ENCODING_DEDUPE_DAYS = 3


async def _jsonb_columns(conn) -> list[tuple[str, str]]:
    """All (table, column) pairs in the public schema whose type is jsonb — discovered, not
    hardcoded, so a new jsonb column is covered automatically (PLAN #216).

    Restricted to BASE TABLEs (excludes VIEWs — `information_schema.columns` returns view
    columns too, and a `jsonb_typeof` COUNT(*) over a view runs its whole underlying query
    for nothing). Mirrors `run_db_growth_check`'s `relkind = 'r'` filter.
    """
    rows = await conn.fetch(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public' AND c.data_type = 'jsonb'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.column_name
        """
    )
    return [(r["table_name"], r["column_name"]) for r in rows]


def _evaluate_jsonb_growth(
    current: dict[str, int], baseline: dict[str, int] | None,
) -> list[dict[str, Any]]:
    """Pure decision, isolated so it is testable mock-free (the file's idiom).

    Returns a list of per-column flags where the current count exceeds the baseline count.
    Empty list (not an error) when there is no prior baseline yet — measure and stay
    silent, same first-run behavior as run_db_growth_check / run_null_rate_sweep.
    """
    if baseline is None:
        return []
    flags = []
    for key, count in current.items():
        before = baseline.get(key, 0)
        if count > before:
            flags.append({"key": key, "before": before, "after": count, "delta": count - before})
    return flags


async def run_jsonb_encoding_check(conn=None) -> dict[str, Any]:
    """Nightly count of double/multi-encoded jsonb rows per column (PLAN #216); speaks only
    when a column's count of jsonb_typeof='string' rows GROWS beyond last night's recording.

    Returns {"counts": {"table.column": n}, "flags": [...], "errors": [...], "spoke": bool}.
    Never raises — a health guard that dies silently is the failure it exists to prevent.
    """
    from agents.market_intelligence.db import get_pool as _gp, log_audit_event as _log

    async def _run(c) -> dict[str, Any]:
        out: dict[str, Any] = {"counts": {}, "flags": [], "errors": [], "spoke": False}

        for table, column in await _jsonb_columns(c):
            key = f"{table}.{column}"
            try:
                n = await c.fetchval(
                    f'SELECT COUNT(*) FROM "{table}" WHERE jsonb_typeof("{column}") = \'string\''
                )
                out["counts"][key] = int(n)
            except Exception as e:  # one bad column must not kill the sweep
                logger.warning("jsonb_encoding_check: %s failed: %s", key, e)
                out["errors"].append({"column": key, "error": str(e)})

        # Baseline = the most recent PRIOR run's counts (no min-age gate — see header).
        baseline: dict[str, int] | None = None
        try:
            row = await c.fetchrow(
                "SELECT detail FROM mi_audit_log WHERE event_type = 'jsonb_encoding_check' "
                "ORDER BY created_at DESC LIMIT 1"
            )
            if row is not None:
                detail = row["detail"]
                payload = json.loads(detail) if isinstance(detail, str) else (detail or {})
                baseline = {k: int(v) for k, v in (payload.get("counts") or {}).items()}
        except Exception as e:
            logger.warning("jsonb_encoding_check: baseline read failed: %s", e)
            out["errors"].append({"baseline": str(e)})

        out["flags"] = _evaluate_jsonb_growth(out["counts"], baseline)

        # Record tonight's measurement — this row IS next run's baseline, so it must be
        # written on every run, flagged or not, before any announce decision.
        total = sum(out["counts"].values())
        try:
            await _log(
                "jsonb_encoding_check",
                f"{total} string-typed jsonb row(s) across {len(out['counts'])} column(s)",
                json.dumps({"counts": out["counts"]}),
            )
        except Exception as e:
            logger.warning("jsonb_encoding_check: audit log failed: %s", e)
            out["errors"].append({"audit": str(e)})

        if not out["flags"]:
            return out

        # PER-COLUMN dedupe (mirrors detector-liveness / inert-sweep idiom) — a persisting
        # regression must not become nightly wallpaper, and a per-column dedupe means one
        # already-announced column can't mask a DIFFERENT column regressing days later.
        # Fails OPEN: a dedupe-read failure only risks a duplicate alert, never a missed one.
        try:
            recent_rows = await c.fetch(
                "SELECT DISTINCT split_part(summary, ':', 1) AS k FROM mi_audit_log "
                "WHERE event_type = 'jsonb_encoding_alert' "
                "AND created_at >= NOW() - make_interval(days => $1)",
                _JSONB_ENCODING_DEDUPE_DAYS,
            )
            recently_announced = {r["k"] for r in recent_rows}
        except Exception as e:
            logger.warning("jsonb_encoding_check: dedupe read failed (will announce): %s", e)
            recently_announced = set()

        fresh = [f for f in out["flags"] if f["key"] not in recently_announced]
        if not fresh:
            return out

        lines = ["\U0001F9EA *JSONB double-encoding regression*",
                 "A column that should hold objects/arrays is holding JSON-as-a-string "
                 "again (PLAN #216) — check the write path for a stray json.dumps() before "
                 "an `::jsonb` bind:", "```"]
        for f in fresh[:5]:
            lines.append(f"{f['key']}: {f['before']} -> {f['after']} string-typed rows")
        lines.append("```")
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            out["spoke"] = bool(await send_telegram_message("\n".join(lines)))
            for f in fresh:
                await _log("jsonb_encoding_alert", f"{f['key']}: {f['before']} -> {f['after']}",
                           json.dumps(f))
        except Exception as e:
            logger.warning("jsonb_encoding_check: announce failed: %s", e)
            out["errors"].append({"announce": str(e)})
        return out

    if conn is not None:
        return await _run(conn)
    pool = await _gp()
    async with pool.acquire() as acquired:
        return await _run(acquired)


# ── #533 Change 6 — CATALYST TIER FLIP MONITOR (2026-08-22, operator-signed) ──────────────────
#
# WHY. The catalyst tier flipped live 2026-08-22: the corrected lattice
# (catalyst_tier_shadow.py) now re-tiers the LLM grade before _score_ep. The operator chose a
# NEGATIVE TEST over waiting for October labels: *"flip now and revert when wrong, observe/
# compare with existing, and have a condition to test if we're right or not and monitor."* The
# flip TIGHTENS (game_changer false positives 43% -> 18%), so the failure mode to watch is
# MISSED ALERTS — and 4 of the 7 graded labelled real EPs were undetermined offline (they died
# below score 50 with no stored catalyst text), so this monitor IS the test for that class.
#
# THE THREE REVERT TRIGGERS (any one -> Telegram naming the trigger + the numbers + the exact
# revert command, plus an audit row):
#   (a) P1 — a member of tests/fixtures/must_not_miss_eps.py is graded `routine` by the ACTING
#       side. A real EP must never be missed; announced once per member ever.
#   (b) HIGH alerts PER STOCK THAT GAPPED over the last 7 days fall MORE THAN 50% vs the prior
#       30 days (both pooled over TRADING days). Supply-normalised 2026-08-26 — see the block
#       above _LATTICE_SUPPLY_GAP_PCT.
#   (c) Two consecutive trading days with ZERO EP alerts (any tier).
#
# Wired into _post_nightly_audit_job (17:30 ET, scheduler.py) — the existing audit surface, no
# new cron. Stands down when the `catalyst_tier_lattice` toggle is OFF (reverted = nothing to
# guard). Read-only: SELECTs mi_catalyst_tier_shadow / mi_ep_alerts / mi_daily_closes, writes
# only audit rows and Telegram — never a grade, entry, sizing or safeguard path.

_LATTICE_TOGGLE = ("catalyst_tier_lattice", "CATALYST_TIER_LATTICE_ENABLED")
_LATTICE_REVERT_SQL = (
    "INSERT INTO mi_safeguard_state (safeguard, account_mode, state, last_transition_at, updated_at) "
    "VALUES ('catalyst_tier_lattice', 'global', 'off', NOW(), NOW()) "
    "ON CONFLICT (safeguard, account_mode) DO UPDATE "
    "SET state = EXCLUDED.state, updated_at = NOW();"
)
_LATTICE_HIGH_DROP_FRACTION = 0.5   # trigger (b): recent rate < 50% of prior rate. OPERATOR-
                                    # SIGNED 2026-08-22 and UNCHANGED by the 2026-08-26
                                    # supply-normalisation — only the denominator moved.
_LATTICE_RECENT_DAYS = 7            # trigger (b): recent window, calendar days
_LATTICE_PRIOR_DAYS = 30            # trigger (b): prior window, calendar days
_LATTICE_ZERO_ALERT_DAYS = 2        # trigger (c): consecutive zero-alert trading days
_LATTICE_FIXTURE_WARN_DEDUPE_DAYS = 3

# ── trigger (b) era-scope fix (2026-08-24) ────────────────────────────────────────────────
# Trigger (b) fired 2026-08-24 on a real collapse that started 2026-08-17 — five trading days
# BEFORE the flip (2026-08-22) — and named the flip as cause, printing revert SQL for a change
# measured to CUT bad grades 43% -> 18%. The blended before/after average cannot tell "the
# flip broke this" from "this was already broken and the flip happened to land nearby"; only
# an ERA-SCOPED comparison can, the same principle system_review.py applied to the exit-rule
# asks (commit f04173f0, 2026-08-23: era boundary constant + per-ask re-check against only
# trades under the current rule + "not enough to ask" floor instead of a blended finding).
# THE LINE: this changes which trading days trigger (b) COMPARES, never the 50% threshold,
# never the flip itself, never any grading rule.
_LATTICE_FLIP_DATE_FALLBACK = date(2026, 8, 22)   # operator-signed flip date (catalyst_tier_
    # shadow.py header + docs/setups/magna53_ep.md 2026-08-22 change log). HARDCODED FALLBACK
    # ONLY — see _lattice_flip_date docstring; used only when both DB-recorded signals below
    # are unavailable (fresh DB, migration gap, or a transient query error on both).
_LATTICE_MIN_POST_FLIP_TRADING_DAYS = 5   # trigger (b) floor: fewer post-flip trading days
    # than this cannot support a halving judgement. 5 is not arbitrary — it is exactly the
    # trading-day count a full _LATTICE_RECENT_DAYS(7 calendar)-day window normally yields
    # (Mon-Fri, no holiday) — i.e. the SAME sample size the pre-fix "recent" window always
    # compared on. Below it, trigger (b) is suppressed (silent, like a healthy day) rather
    # than firing on a partial week.

# ── trigger (b) SUPPLY NORMALISATION (2026-08-26) ─────────────────────────────────────────
# WHY. Trigger (b) counted OUR ALERTS against a trailing average of our alerts, i.e. it
# assumed a flat baseline of opportunity. Alert count is a function of SUPPLY, and supply is
# seasonal: the operator, on the second false fire in two days — *"we are at the tail end of
# earnings season, so gap-ups (and downs) shrink naturally"*. A flat-baseline trigger
# therefore false-fires at every earnings trough. Measured over 2026-07-30 -> 2026-08-25 the
# per-trading-day form fires 3x (08-21, 08-24, 08-25) and all three are the tape
# (docs/analysis/alert_volume_collapse_2026-08-24.md: every conversion stage inside the funnel
# was at or above its July level while the number of gapping stocks fell ~50/day -> ~20/day).
#
# THE OPERATOR'S CONSTRAINT, which is the whole design: *"i don't want to make the assumption
# that more real EPs happen during earnings season, just more gap ups (and downs) in general
# due to earnings, let's not conflate the two, I don't have any data to say if there's similar
# effect on real EPs."* So the denominator is GAP SUPPLY, which we measure, and NOTHING here
# encodes an expected EP rate, a seasonal scale factor or a per-month threshold. The trigger
# now asks "did our CONVERSION of available supply halve?" — a thin tape produces few alerts
# without tripping it, and a broken funnel still trips it on a thin tape.
#
# THE SUPPLY MEASURE: stocks whose OPEN gapped >= _LATTICE_SUPPLY_GAP_PCT above the prior
# close, restricted to the D-1 universe floors (prior close >= $5, prior-day volume >= 50k
# shares), counted per trading day from `mi_daily_closes`.
#
# WHY IT SURVIVES THE 2026-08-22 LOGGING BOUNDARY. The obvious denominator — candidates in
# `mi_ep_scan_log` — is NOT comparable across 2026-08-22: #570 made the two silent D-1
# universe floors log a row, so the scan log's distinct-ticker count jumps ~18/day to ~222/day
# (213 of the 222 rows on 2026-08-24 are `filter:universe_prev_close_too_low`, median prior
# close $1.78) purely from the logging change. `mi_daily_closes` is a different table written
# by a different job (nightly_data_pull 17:00 ET), untouched by #570, complete on both sides of
# the boundary (12.2-12.4k rows/day with an open price every day since 2026-07-06) — the
# boundary cannot reach it. It is also OUTSIDE our funnel entirely, which is the second reason
# to prefer it: a scan-log denominator moves with the #489/#490 real-time admission layer, so a
# break THERE would shrink numerator and denominator together and hide itself.
#
# THE FLOORS ARE A YARDSTICK, NOT A RULE — hardcoded here on purpose rather than imported from
# ep_detector, so a signed admission change (MIN_GAP_PCT 10.0 -> 9.0 on 2026-08-19) shows up as
# a CONVERSION MOVE instead of being silently absorbed by a denominator that moved with it. A
# yardstick that moves is not a yardstick. Nothing in this block admits, grades or sizes
# anything.
# THE LINE: this changes trigger (b)'s DENOMINATOR only. _LATTICE_HIGH_DROP_FRACTION (the
# operator-signed 50%), the flip, the revert flag and every grading/entry rule are untouched.
#
# ── #611: RECONCILED AGAINST `mi_ep_scan_log` (2026-09-01) — the two numbers measure
# DIFFERENT THINGS, neither is a bug. On 2026-09-01 the alert read "4 and 3 stocks gapping
# 10%+" for 09-01/08-31; counting DISTINCT TICKERS in `mi_ep_scan_log` with day-MAX
# `gap_pct >= 10` instead gives 42 and 52 — an apparent 10x miss. Traced end to end (prod
# SELECTs, not guessed):
#   1. The naive scan-log count never applies the $5/50k floors at all. Applying them (using
#      the scan log's OWN `prev_close`/`prev_day_volume` columns) drops 42 -> 6 and 52 -> 8 —
#      most of the "10x" is un-floored penny/micro names (e.g. GPRO prev_close $0.88, HKPD
#      $0.33) that were never in this trigger's universe to begin with.
#   2. The remaining gap is definitional, not a bug: `mi_ep_scan_log.gap_pct` is computed in
#      `ep_detector.py` as `(current_price - prev_close) / prev_close * 100` and the scanner
#      writes a fresh row EVERY SCAN TICK (dozens/ticker/day) — so a ticker's day-MAX gap_pct
#      is its PEAK live-price reading vs the prior close at any tick that ran, not the settled
#      opening print. `mi_daily_closes.open_price` IS the settled opening print. The two can
#      and do diverge: PRLD's day-max scan-tick reading was +12.3% (some tick before the bell)
#      but its actual open was BELOW the prior close (-0.9%, opening_gap_pct in
#      `mi_daily_closes`) — a live reading > 10% that resolved to a NEGATIVE opening gap.
#      CRK peaked at a +10.5% tick but opened at +9.6% — a real tick over the line the actual
#      open never reached. Of the 6 (09-01) / 8 (08-31) that pass the floors, only WETO/YEXT/
#      PXS/GDXD (4) and MOVE/WETO/SAIC (3) actually opened >= 10% — reproducing the alert
#      exactly. (GDXD never appears in the scan-log 42 at all — the two lists are not nested
#      either direction.)
#   VERDICT: `mi_daily_closes`'s settled-open measure is what this trigger is DESIGNED to use
# (see "THE SUPPLY MEASURE" above) and it reproduces correctly — nothing here changed. The fix
# is WORDING ONLY: the operator-facing message said "stocks gapping X%+ past the universe
# floors", which reads as "stocks that moved X%+ at some point" — exactly the (wrong) reading
# that produced the 42/52 comparison. It now says "opened X%+ above the prior close" and spells
# out the floor values inline, so a future reader cannot reach for the scan log's per-tick
# `gap_pct` as if it were the same measure. See tests/test_catalyst_lattice_monitor.py for the
# pinned 42->6->4 / 52->8->3 bridge with the real tickers.
_LATTICE_SUPPLY_GAP_PCT = 10.0            # open vs prior close, in percent

_LATTICE_SUPPLY_MIN_PREV_CLOSE = 5.0      # mirrors ep_detector.MIN_PREV_CLOSE as of 2026-08-26
_LATTICE_SUPPLY_MIN_PREV_VOLUME = 50_000  # mirrors ep_detector.MIN_PREV_DAY_VOLUME, same date
_LATTICE_SUPPLY_LAG_WARMUP_DAYS = 10      # extra calendar days read before the span so the
    # first day in the span has a prior-close/prior-volume row to LAG onto (covers a long
    # weekend plus a holiday). Warm-up rows are read, then filtered out of the result.


def _lattice_supply_floors(t: dict) -> str:
    """"prior close $5+, prior-day volume 50k+ shares" — rendered FROM the trigger's own values.

    Typed as literal text until 2026-09-02. The entire reason this alert was rewritten is that
    its words must not describe a different measure than the one it computed; a floor that moves
    (the comment above already flags these as mirroring ep_detector "as of 2026-08-26") would
    have left the message confidently stating the old number. Falls back to the module constants
    for a trigger dict written before they were carried.
    """
    close = t.get("supply_min_prev_close", _LATTICE_SUPPLY_MIN_PREV_CLOSE)
    vol = t.get("supply_min_prev_volume", _LATTICE_SUPPLY_MIN_PREV_VOLUME)
    vol_txt = f"{vol / 1000:.0f}k" if vol >= 1000 else f"{vol:.0f}"
    return f"prior close ${close:.0f}+, prior-day volume {vol_txt}+ shares"


_LATTICE_SUPPLY_MIN_UNIVERSE_ROWS = 2000  # a trading day counts as MEASURED only if it has at
    # least this many rows WITH an open price. Sits below the 2,200-row liveness floor
    # nightly_data_pull is already audited against (scheduler.py expected_min_rows), so a
    # partial or open-less ingest can never masquerade as a quiet tape. Guarding on rows WITH
    # AN OPEN specifically matters: closes-without-opens would score every day as zero supply,
    # which inflates the PRIOR rate and manufactures a false fire.


def _load_must_not_miss_members() -> "list[tuple[str, str]] | None":
    """(ticker, iso-date) pairs from the #577 fixture, excluded members skipped.

    The fixture ships in the market image (docker/Dockerfile.market COPY) precisely so
    trigger (a) is alive in prod. Returns None — never [] — on import failure so the
    caller can tell 'fixture unreachable' (alert-worthy: the P1 trigger is dark) from
    'no members'."""
    try:
        from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
        return [(m.ticker, m.alert_date) for m in MUST_NOT_MISS if not m.excluded]
    except Exception as e:
        logger.warning("catalyst_lattice_monitor: must_not_miss fixture unreachable: %s", e)
        return None


def _lattice_acting_tier(live_side: "str | None", live_quality_last: "str | None",
                         shadow_tier_last: "str | None") -> "str | None":
    """The tier the LIVE system ACTED on for a row — decided by the row's own live_side
    stamp, never by its date ('llm' rows predate the flip or ran with the flag off)."""
    if live_side == "lattice":
        return shadow_tier_last
    return live_quality_last


def _evaluate_lattice_high_drop(recent_avg: float, prior_avg: float) -> "dict[str, Any] | None":
    """Trigger (b), pure: fire when the recent per-trading-day HIGH average has fallen
    MORE than 50% vs the prior average. prior_avg == 0 never fires (nothing to fall from —
    a cold lane is trigger (c)'s job)."""
    if prior_avg > 0 and recent_avg < _LATTICE_HIGH_DROP_FRACTION * prior_avg:
        return {"recent_avg": round(recent_avg, 3), "prior_avg": round(prior_avg, 3),
                "drop_pct": round(100.0 * (1 - recent_avg / prior_avg), 1)}
    return None


def _lattice_trading_days(end_day: date, n_calendar: int) -> "list[date]":
    """The trading days inside the n_calendar-day window ENDING at end_day (inclusive)."""
    return [end_day - timedelta(days=i) for i in range(n_calendar)
            if _is_trading_day(end_day - timedelta(days=i))]


async def _lattice_flip_date(c) -> "tuple[date, str]":
    """The date the catalyst-tier lattice began ACTING — for era-scoping trigger (b), never a
    hardcoded constant when a DB-recorded signal is available. Returns (date, source); source
    is carried into the trigger payload / audit row so a misfire stays debuggable. Tried in
    order, each wrapped so a query failure falls through rather than raising:

    1. `mi_safeguard_state.last_transition_at` for ('catalyst_tier_lattice', 'global',
       state='on') — the administrative record of the toggle's own transition, when one was
       ever explicitly written (converted to an ET date, per the codebase AT TIME ZONE rule).
       In prod as shipped the flip went live via the `default=True` code default
       (ep_detector.py ~3196), not an explicit toggle write, so this row commonly does not
       exist — that is an EXPECTED miss, not an error, and falls through to source 2 rather
       than logging. ⚠ Caller-visible consequence: `set_safeguard_state` bumps
       `last_transition_at` on EVERY write, so a future revert-then-restore cycle (the exact
       mechanism this monitor's own alert offers) moves this date FORWARD to the restore, not
       the original flip — the era boundary becomes "the restore", the `_LATTICE_MIN_POST_
       FLIP_TRADING_DAYS` floor re-arms for a week, and trigger (b) goes quiet again for that
       week. Correct if the restore is treated as a fresh era (thin new data, same as after
       the original flip); worth a human glance if it lands during exactly that week.
    2. `MIN(scan_date)` from `mi_catalyst_tier_shadow` where `live_side = 'lattice'` — the
       earliest date the lattice is RECORDED as the acting side: the acting record itself,
       the same per-row stamp `_lattice_acting_tier` already trusts over any date guess
       ("never by its date" — this reuses that exact instinct for the era boundary too).
    3. `_LATTICE_FLIP_DATE_FALLBACK` — hardcoded, documented, last resort only (both DB
       signals unavailable)."""
    try:
        row = await c.fetchrow(
            "SELECT (last_transition_at AT TIME ZONE 'America/New_York')::date AS flip_date "
            "FROM mi_safeguard_state WHERE safeguard = 'catalyst_tier_lattice' "
            "AND account_mode = 'global' AND state = 'on'")
        if row is not None and row["flip_date"] is not None:
            return (row["flip_date"], "safeguard_state")
    except Exception as e:
        logger.warning("catalyst_lattice_monitor: flip-date safeguard_state read failed: %s", e)

    try:
        row = await c.fetchrow(
            "SELECT MIN(scan_date) AS flip_date FROM mi_catalyst_tier_shadow "
            "WHERE live_side = 'lattice'")
        if row is not None and row["flip_date"] is not None:
            return (row["flip_date"], "shadow_acting_record")
    except Exception as e:
        logger.warning("catalyst_lattice_monitor: flip-date shadow-table read failed: %s", e)

    return (_LATTICE_FLIP_DATE_FALLBACK, "hardcoded_fallback")


def _lattice_era_windows(day: date, flip_date: date) -> "tuple[list[date], list[date], bool]":
    """Trigger (b)'s two comparison windows, ERA-SCOPED to `flip_date` (2026-08-24 fix). Same
    two calendar-day buckets as before the fix (the last `_LATTICE_RECENT_DAYS` days = the
    'recent' bucket, the following `_LATTICE_PRIOR_DAYS` days back = the 'prior' bucket).
    Returns `(recent, prior, scoped)` — `scoped` tells the caller whether era-filtering
    actually applied, so it (and ONLY it) knows whether the post-flip minimum-days floor is
    relevant; the floor exists to stop a partial post-flip week from being judged and has no
    business constraining a steady-state rolling comparison (see below).

    SELF-HEALING, EXPLICIT: if `flip_date` is AT OR BEFORE the start of the whole
    `_LATTICE_RECENT_DAYS + _LATTICE_PRIOR_DAYS`-day lookback span, every day in both buckets
    is already post-flip and there is nothing to scope — return them UNFILTERED
    (`scoped=False`), byte-identical to the pre-fix windows. This is a real branch, not a
    filter that happens to degrade into one: a naive 'keep recent >= flip, keep prior < flip'
    filter looks like it self-heals but does NOT — once the flip ages past the whole span,
    EVERY prior-bucket day is >= flip_date (chronologically after a now-old flip), so a plain
    `< flip_date` filter empties the prior bucket and PERMANENTLY silences trigger (b) after
    that point. Caught by test_era_windows_self_heal_once_flip_is_outside_the_lookback_span
    before shipping. `scoped=False` ALSO matters for the floor: without it, a normal NYSE
    holiday week (`_lattice_trading_days(day, 7)` returns 4, not 5, ~9-10x/yr) would trip the
    post-flip floor forever, long after the flip stopped being relevant — the floor must only
    gate an ACTUAL partial post-flip window, never a routine short trading week.

    Otherwise (`scoped=True` — the flip is inside the lookback span, the only case that
    actually needs scoping) 'recent' keeps only trading days ON OR AFTER the flip and 'prior'
    keeps only trading days STRICTLY BEFORE it; a day on the wrong side of the flip for its
    ORIGINAL bucket is DROPPED, not moved to the other bucket. During the weeks the flip sits
    inside the window this can leave a handful of days counted in neither average — a narrow,
    temporary gap, never a full window. Whether dropping them makes trigger (b) MORE or LESS
    likely to fire depends on whether those specific days sat above or below the prior mean
    (in the incident this fixes they were collapsed/low, so excluding them from `prior` raises
    `prior_avg` and makes the drop easier to detect — but a dropped HIGH day would cut the
    other way); what it can never do, either direction, is compare a day against the wrong
    era, which is the actual bug this fixes."""
    recent_all = _lattice_trading_days(day, _LATTICE_RECENT_DAYS)
    prior_all = [d for d in _lattice_trading_days(day, _LATTICE_RECENT_DAYS + _LATTICE_PRIOR_DAYS)
                 if d not in set(recent_all)]
    window_start = day - timedelta(days=_LATTICE_RECENT_DAYS + _LATTICE_PRIOR_DAYS - 1)
    if flip_date <= window_start:
        return recent_all, prior_all, False
    recent = [d for d in recent_all if d >= flip_date]
    prior = [d for d in prior_all if d < flip_date]
    return recent, prior, True


async def _lattice_supply_by_date(c, span_start: date, span_end: date) -> "dict[date, int]":
    """Trigger (b)'s DENOMINATOR: per trading day, how many stocks actually gapped past the
    D-1 universe floors — the tape's offer, measured, never assumed (see the block above
    `_LATTICE_SUPPLY_GAP_PCT` for why this measure and why it survives the 2026-08-22 scan-log
    logging boundary).

    Returns {trade_date: supply}, containing ONLY days whose `mi_daily_closes` ingest is
    complete enough to trust (>= `_LATTICE_SUPPLY_MIN_UNIVERSE_ROWS` rows carrying an open
    price). A day that is ABSENT is 'not measured' — the caller MUST drop it from both the
    numerator and the denominator, never read it as zero supply. `{}` on any query failure:
    trigger (b) then has no denominator and stays silent, which is the correct failure
    direction for a monitor that would otherwise print revert SQL for a trading change.

    Read-only, one query, ~47 calendar days x ~12.3k rows; `mi_daily_closes` is keyed
    PRIMARY KEY (trade_date, ticker) so the span is an index range scan.

    Inline SQL on the caller's connection, not a `db.py` helper, deliberately: it matches the
    rest of this monitor (`_lattice_flip_date`, the alert-count query) and keeps the whole
    unit testable through one fake connection."""
    try:
        rows = await c.fetch(
            """
            WITH b AS (
                SELECT trade_date, open_price,
                       lag(close)  OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close,
                       lag(volume) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_volume
                FROM mi_daily_closes
                WHERE trade_date >= $1 AND trade_date <= $2
            )
            SELECT trade_date,
                   count(*) FILTER (WHERE open_price IS NOT NULL) AS rows_with_open,
                   count(*) FILTER (
                       WHERE open_price IS NOT NULL
                         AND prev_close >= $4
                         AND prev_volume >= $5
                         -- NULLIF, not a `prev_close > 0` companion clause: Postgres may
                         -- evaluate AND arms in any order, so a zero prior close (a bad
                         -- tick) could reach the division and raise. NULL simply fails the
                         -- comparison, which is the behaviour we want.
                         AND (open_price - prev_close) / NULLIF(prev_close, 0) * 100.0 >= $6
                   ) AS supply
            FROM b
            WHERE trade_date >= $3
            GROUP BY trade_date
            """,
            span_start - timedelta(days=_LATTICE_SUPPLY_LAG_WARMUP_DAYS), span_end, span_start,
            _LATTICE_SUPPLY_MIN_PREV_CLOSE, _LATTICE_SUPPLY_MIN_PREV_VOLUME,
            _LATTICE_SUPPLY_GAP_PCT)
    except Exception as e:
        logger.warning("catalyst_lattice_monitor: supply read failed: %s", e)
        return {}
    return {r["trade_date"]: int(r["supply"]) for r in rows
            if int(r["rows_with_open"] or 0) >= _LATTICE_SUPPLY_MIN_UNIVERSE_ROWS}


def _lattice_per_100(alerts: int, supply: int) -> float:
    """HIGH alerts per 100 gapping stocks — the rate in a unit a human can hold."""
    return round(100.0 * alerts / supply, 1) if supply else 0.0


async def run_catalyst_lattice_monitor(conn=None, today=None) -> "dict[str, Any]":
    """#533 flip monitor — see the block comment above. Returns {"enabled", "today",
    "triggers", "errors", "spoke"}; never raises (each trigger isolated). Silent when
    healthy; stands down entirely when the revert flag is OFF."""
    from agents.market_intelligence.db import get_pool as _gp, get_runtime_toggle, \
        log_audit_event as _log

    out: "dict[str, Any]" = {"enabled": True, "today": None, "triggers": [], "errors": [],
                             "spoke": False}
    try:
        out["enabled"] = bool(await get_runtime_toggle(*_LATTICE_TOGGLE, default=True))
    except Exception as e:  # toggle read is internally fail-open; belt and braces
        logger.warning("catalyst_lattice_monitor: toggle read failed: %s", e)
        out["errors"].append({"toggle": str(e)})
    if not out["enabled"]:
        return out

    async def _run(c) -> "dict[str, Any]":
        day = today or et_today()
        out["today"] = day.isoformat()

        # ── trigger (a): P1 — a must-not-miss member graded routine by the acting side ──
        members = _load_must_not_miss_members()
        if members is None:
            # The P1 trigger is DARK — itself alert-worthy, never silent. Deduped 3 days.
            out["errors"].append({"fixture": "unreachable"})
            try:
                already = await c.fetchrow(
                    "SELECT 1 FROM mi_audit_log WHERE event_type = 'catalyst_lattice_monitor_error' "
                    "AND created_at > NOW() - make_interval(days => $1) LIMIT 1",
                    _LATTICE_FIXTURE_WARN_DEDUPE_DAYS)
                await _log("catalyst_lattice_monitor_error",
                           "must_not_miss fixture unreachable — P1 trigger (a) is DARK",
                           json.dumps({"today": day.isoformat()}))
                if not already:
                    from agents.market_intelligence.briefing import send_telegram_message
                    await send_telegram_message(
                        "🟠 *CATALYST TIER MONITOR* — the must-not-miss fixture cannot be "
                        "loaded, so revert trigger (a) — a real EP graded routine — is "
                        "DARK. Check the market image ships "
                        "`tests/fixtures/must_not_miss_eps.py` (docker/Dockerfile.market).")
            except Exception as e:
                logger.warning("catalyst_lattice_monitor: fixture-dark warning failed: %s", e)
                out["errors"].append({"fixture_warn": str(e)})
        else:
            try:
                pairs = {(t, d) for t, d in members}
                rows = await c.fetch(
                    "SELECT scan_date, ticker, live_quality_last, shadow_tier_last, live_side "
                    "FROM mi_catalyst_tier_shadow WHERE ticker = ANY($1::text[])",
                    sorted({t for t, _ in pairs}))
                for r in rows:
                    key = (r["ticker"], r["scan_date"].isoformat())
                    if key not in pairs:
                        continue
                    acting = _lattice_acting_tier(
                        r["live_side"], r["live_quality_last"], r["shadow_tier_last"])
                    if acting != "routine":
                        continue
                    # announce once per member EVER (the dead-column idiom)
                    summary_key = f"{key[0]} {key[1]}"
                    already = await c.fetchrow(
                        "SELECT 1 FROM mi_audit_log WHERE event_type = 'catalyst_lattice_p1_miss' "
                        "AND summary LIKE $1 LIMIT 1", summary_key + "%")
                    if already:
                        continue
                    out["triggers"].append({
                        "kind": "p1_member_routine", "ticker": key[0], "date": key[1],
                        "live_side": r["live_side"],
                        "llm_grade": r["live_quality_last"],
                        "lattice_tier": r["shadow_tier_last"]})
            except Exception as e:
                logger.warning("catalyst_lattice_monitor: P1 member check failed: %s", e)
                out["errors"].append({"p1": str(e)})

        # ── per-date alert counts feed triggers (b) and (c) — one query ──────────────
        by_date: "dict[date, tuple[int, int]]" = {}
        try:
            span_start = day - timedelta(days=_LATTICE_RECENT_DAYS + _LATTICE_PRIOR_DAYS - 1)
            arows = await c.fetch(
                f"SELECT alert_date, COUNT(*) AS n, "
                f"COUNT(*) FILTER (WHERE score_tier = 'HIGH') AS high_n "
                f"FROM mi_ep_alerts WHERE alert_date >= $1 AND alert_date <= $2 "
                f"AND {LIVE_SOURCE_SQL} GROUP BY alert_date",
                span_start, day)
            by_date = {r["alert_date"]: (int(r["n"]), int(r["high_n"])) for r in arows}

            # the tape's offer per trading day — trigger (b)'s denominator, and the context
            # trigger (c) prints. Measured, never assumed; {} when unmeasurable.
            supply_by_date = await _lattice_supply_by_date(c, span_start, day)

            # trigger (b): HIGH alerts PER GAPPING STOCK over the last 7 days vs the prior 30,
            # trading days only, ERA-SCOPED to the flip (2026-08-24 fix — see
            # _lattice_era_windows docstring) and SUPPLY-NORMALISED (2026-08-26 fix — see the
            # block above _LATTICE_SUPPLY_GAP_PCT). A drop that falls entirely on the pre-flip
            # side of the boundary must never reach here as a "recent vs prior" comparison the
            # flip could plausibly explain; a drop that is just a thinner tape must not reach
            # the 50% test at all, because the 50% test is now about CONVERSION.
            flip_date, flip_source = await _lattice_flip_date(c)
            recent_td, prior_td, scoped = _lattice_era_windows(day, flip_date)
            if recent_td and prior_td:
                if scoped and len(recent_td) < _LATTICE_MIN_POST_FLIP_TRADING_DAYS:
                    # the floor gates only an ACTUAL partial post-flip window (scoped=True) —
                    # a routine short trading week (holiday) once the flip is old must never
                    # trip it; see _lattice_era_windows docstring.
                    logger.info(
                        "catalyst_lattice_monitor: trigger (b) suppressed — only %d trading "
                        "day(s) since the flip (%s, source=%s), need >= %d to judge a halving",
                        len(recent_td), flip_date, flip_source,
                        _LATTICE_MIN_POST_FLIP_TRADING_DAYS)
                else:
                    # a day whose supply is unmeasured leaves BOTH sides of the ratio — never
                    # counted as zero supply (that would inflate the other window's rate).
                    recent_m = [d for d in recent_td if d in supply_by_date]
                    prior_m = [d for d in prior_td if d in supply_by_date]
                    recent_supply = sum(supply_by_date[d] for d in recent_m)
                    prior_supply = sum(supply_by_date[d] for d in prior_m)
                    if not recent_m or not prior_m or not recent_supply or not prior_supply:
                        logger.info(
                            "catalyst_lattice_monitor: trigger (b) suppressed — gap supply "
                            "unmeasurable (recent %d/%d day(s)=%d stocks, prior %d/%d "
                            "day(s)=%d stocks); conversion cannot be judged without a "
                            "denominator", len(recent_m), len(recent_td), recent_supply,
                            len(prior_m), len(prior_td), prior_supply)
                        out["errors"].append({"supply": "unmeasurable"})
                    else:
                        recent_high = sum(by_date.get(d, (0, 0))[1] for d in recent_m)
                        prior_high = sum(by_date.get(d, (0, 0))[1] for d in prior_m)
                        # POOLED totals, not a mean of per-day ratios: a 5-name day would
                        # otherwise carry the same weight as a 130-name day.
                        recent_rate = recent_high / recent_supply
                        prior_rate = prior_high / prior_supply
                        drop = _evaluate_lattice_high_drop(recent_rate, prior_rate)
                        if drop:
                            out["triggers"].append({
                                "kind": "high_conversion_drop",
                                "recent_rate": round(recent_rate, 5),
                                "prior_rate": round(prior_rate, 5),
                                "drop_pct": drop["drop_pct"],
                                "recent_days": len(recent_m), "prior_days": len(prior_m),
                                "recent_high_n": recent_high, "prior_high_n": prior_high,
                                "recent_supply": recent_supply, "prior_supply": prior_supply,
                                "recent_per_100": _lattice_per_100(recent_high, recent_supply),
                                "prior_per_100": _lattice_per_100(prior_high, prior_supply),
                                "recent_avg": round(recent_high / len(recent_m), 3),
                                "prior_avg": round(prior_high / len(prior_m), 3),
                                "supply_gap_pct": _LATTICE_SUPPLY_GAP_PCT,
                                "supply_min_prev_close": _LATTICE_SUPPLY_MIN_PREV_CLOSE,
                                "supply_min_prev_volume": _LATTICE_SUPPLY_MIN_PREV_VOLUME,
                                "flip_date": flip_date.isoformat(),
                                "flip_date_source": flip_source})

            # trigger (c): the two most recent trading days both produced ZERO alerts.
            # DELIBERATELY NOT supply-normalised (2026-08-26): two silent days on a live money
            # path is worth a look even when the cause turns out to be the tape, and a monitor
            # that can never speak is worse than one that occasionally says something you
            # dismiss. What changed is the MESSAGE — it now carries each day's gap supply and
            # the trailing conversion rate, so the operator can dismiss it in one glance
            # instead of opening an investigation.
            last_tds: "list[date]" = []
            d = day
            while len(last_tds) < _LATTICE_ZERO_ALERT_DAYS and (day - d).days < 10:
                if _is_trading_day(d):
                    last_tds.append(d)
                d -= timedelta(days=1)
            if (len(last_tds) == _LATTICE_ZERO_ALERT_DAYS
                    and all(by_date.get(d, (0, 0))[0] == 0 for d in last_tds)):
                ctx_days = [d for d in prior_td if d in supply_by_date]
                ctx_supply = sum(supply_by_date[d] for d in ctx_days)
                # ALL tiers, matching this trigger's own "no EP alerts at all" definition —
                # not the HIGH-only count trigger (b) uses.
                ctx_alerts = sum(by_date.get(d, (0, 0))[0] for d in ctx_days)
                out["triggers"].append({
                    "kind": "zero_alert_days",
                    "days": [d.isoformat() for d in last_tds],
                    "supply": [supply_by_date.get(d) for d in last_tds],
                    "supply_gap_pct": _LATTICE_SUPPLY_GAP_PCT,
                    "supply_min_prev_close": _LATTICE_SUPPLY_MIN_PREV_CLOSE,
                    "supply_min_prev_volume": _LATTICE_SUPPLY_MIN_PREV_VOLUME,
                    "trailing_per_100": (_lattice_per_100(ctx_alerts, ctx_supply)
                                         if ctx_supply else None),
                    "trailing_days": len(ctx_days)})
        except Exception as e:
            logger.warning("catalyst_lattice_monitor: alert-volume triggers failed: %s", e)
            out["errors"].append({"volume": str(e)})

        if not out["triggers"]:
            return out

        # ── announce: WHICH trigger, the numbers, the exact revert command ───────────
        lines = ["🔴 *CATALYST TIER MONITOR — revert trigger hit* (#533 flip, 2026-08-22)"]
        for t in out["triggers"]:
            if t["kind"] == "p1_member_routine":
                lines.append(
                    f"• P1 MISS: `{t['ticker']}` {t['date']} — a labelled real EP was graded "
                    f"routine by the acting tier (LLM grade {t['llm_grade']}, lattice "
                    f"{t['lattice_tier']}, acting side {t['live_side']}). A real EP must "
                    f"never be missed — this is the trigger that matters most.")
            elif t["kind"] == "high_conversion_drop":
                lines.append(
                    f"• WE ARE CONVERTING LESS OF WHAT THE TAPE OFFERS: since the "
                    f"catalyst-tier flip ({t['flip_date']}), the {t['recent_days']} trading "
                    f"day(s) on/after it produced {t['recent_high_n']} HIGH alerts out of "
                    f"{t['recent_supply']} stocks that OPENED {t['supply_gap_pct']:.0f}%+ "
                    f"above the prior close ({_lattice_supply_floors(t)}) "
                    f"— {t['recent_per_100']} per 100 — against "
                    f"{t['prior_high_n']} out of {t['prior_supply']} "
                    f"({t['prior_per_100']} per 100) over the {t['prior_days']} trading days "
                    f"before it. That is a {t['drop_pct']}% fall in the share we convert "
                    f"(threshold 50%). Raw volume, for reference only: {t['recent_avg']} "
                    f"alerts/day vs {t['prior_avg']} — a thinner tape alone does NOT trip "
                    f"this trigger.")
            elif t["kind"] == "zero_alert_days":
                sup = ["?" if s is None else str(s) for s in t.get("supply", [])]
                ctx = (f" The tape offered {' and '.join(sup)} stocks that OPENED "
                       f"{t['supply_gap_pct']:.0f}%+ above the prior close "
                       f"({_lattice_supply_floors(t)}) on those days"
                       if sup else "")
                rate = t.get("trailing_per_100")
                ctx += (f", against {rate} alerts per 100 such stocks over the prior "
                        f"{t['trailing_days']} trading days." if rate is not None else ".")
                lines.append(
                    f"• ZERO-ALERT DAYS: no EP alerts at all on {' and '.join(t['days'])} "
                    f"— two consecutive trading days.{ctx} (Supply is CONTEXT, not a verdict "
                    f"— this trigger is deliberately not supply-normalised.)")
        lines.append("")
        lines.append("Revert the flip (ONE flag; takes effect within ~60s, no redeploy):")
        lines.append("```")
        lines.append(_LATTICE_REVERT_SQL)
        lines.append("```")
        lines.append("_Permanent form: set `CATALYST_TIER_LATTICE_ENABLED=false` in prod .env "
                     "and redeploy market-agent. Evidence + change log: "
                     "docs/setups/magna53_ep.md 2026-08-22._")

        headline = ("catalyst lattice revert trigger: "
                    + ", ".join(t["kind"] for t in out["triggers"]))
        try:
            await _log("catalyst_lattice_monitor_alert", headline,
                       json.dumps({"today": day.isoformat(), "triggers": out["triggers"]}))
            for t in out["triggers"]:
                if t["kind"] == "p1_member_routine":
                    await _log("catalyst_lattice_p1_miss",
                               f"{t['ticker']} {t['date']} graded routine by the acting tier",
                               json.dumps(t))
            from agents.market_intelligence.briefing import send_telegram_message
            out["spoke"] = bool(await send_telegram_message("\n".join(lines)))
        except Exception as e:
            logger.warning("catalyst_lattice_monitor: announce failed: %s", e)
            out["errors"].append({"announce": str(e)})
        return out

    if conn is not None:
        return await _run(conn)
    pool = await _gp()
    async with pool.acquire() as acquired:
        return await _run(acquired)


# ═══════════════════════════ DOCS-VS-REALITY DRIFT CHECK (2026-08-29) ═══════════════════════
#
# Nightly production twin of `python scripts/live_rules.py --drift-only`. Operator: *"how do we
# keep this check up to date and everything in sync?"* — until now the answer was "we don't": it
# only ran when someone typed it by hand, so `docs/architecture/entry_pipeline.md` called the
# #490 real-time gap re-check "BUILT OFF" for FOUR WEEKS after it went live globally, and
# `lane2_grouping_v2` ran ON and grade-affecting (feeds the judge's active_narratives, which sets
# alert tiers, which drives real trades) with NO owner document naming it at all. THE LINE: this
# is observability only — it changes no strategy/criterion/safeguard/trade state and never
# writes or flips a toggle, only reads.
#
# Reuses scripts/live_rules.py's detection functions DIRECTLY (collect_code_facts,
# discover_runtime_toggles, load_setup_docs, detect_drift, Resolver, ProdState) — never a second
# copy of the rules; that module's own docstring names the three failures a second copy would
# reintroduce ("a genuinely funny way to fail," per the operator brief for this job).
#
# SEVERITY IS NOT UNIFORM (CLAUDE.md audit L1/L2/L3 tiering, same principle):
#   DRIFT      — a doc provably contradicts code or prod. Actionable → Telegram EVERY run while
#                 it stands (this class rots for WEEKS unmentioned — see the #490 example above
#                 — so a once-ever announcement would let it rot again), but the message always
#                 says WHAT'S NEW since the previous run, not just the standing count: "a standing
#                 count of 2 that nobody has fixed is noise, while '1 NEW drift since yesterday'
#                 is a signal" (operator brief). The previous run's fingerprints are persisted in
#                 mi_audit_log (event_type=_DRIFT_CHECK_EVENT) so this diff is possible.
#   UNVERIFIED — a dated claim nothing can check. mi_audit_log only; read by
#                 _aggregate_drift_findings (system_review.py) for the Sunday weekly digest.
#                 Alerting nightly on something nobody can act on is how an alert gets muted —
#                 this repo has been bitten by exactly that shape before.
#
# PROD READ, done natively instead of over SSH: the interactive tool SSHes OUT to the server
# from a laptop; this job already runs INSIDE apollo-market, ON that server — SSH-ing to itself
# would need an ssh client + keys this slim image does not have, for data already reachable
# natively. So the "prod" snapshot here is read directly: mi_safeguard_state + mi_strategies via
# the existing DB pool (the SAME rows the SSH path reads through `docker exec apollo-postgres
# psql`), and rule env vars off THIS process's os.environ. `deployed_commit` /
# `deployed_constants` stay empty — from inside the deployed container the checkout on disk IS
# the deployed code, so there is nothing to cross-check it against; Resolver already degrades
# that gap honestly ("local; not re-checked on server"), never silently. apollo-execution shares
# the SAME env_file (docker-compose.prod.yml); its only per-container overrides
# (POSTGRES_HOST/REDIS_HOST/SERVICE_ROLE/EXECUTION_*/ALPACA_*) are infra plumbing or secrets
# live_rules._SECRET_TOKENS already excludes — none are rule constants this check tracks, so
# apollo-market's own env is a sound stand-in for "prod env." If the DB read itself fails, prod
# is reported UNREACHABLE — never guessed — and detect_drift skips every prod-dependent rule
# instead of manufacturing false drift (same contract as the SSH path's own failure mode).

_DRIFT_CHECK_EVENT = "drift_check_snapshot"


def _drift_fingerprint(row: Any) -> str:
    """A DriftRow identity that survives an unrelated doc edit shifting line numbers below it —
    `where` is `file:line`; keying on the line would fake 'N NEW drift' on every reflow, which is
    exactly the noise that trains an operator to stop reading the alert."""
    path = row.where.rsplit(":", 1)[0] if ":" in row.where else row.where
    return f"{row.rule}|{row.severity}|{path}|{row.claim.strip()}|{row.actual.strip()}"


async def run_drift_check(conn=None) -> dict[str, Any]:
    """Nightly docs-vs-code/prod drift check — see the module section header above for the full
    design (severity split, in-container prod read, THE LINE). Returns {"drift_n",
    "new_drift_n", "unverified_n", "prod_reachable", "error", "spoke"}."""
    out: dict[str, Any] = {"drift_n": 0, "new_drift_n": 0, "unverified_n": 0,
                           "prod_reachable": False, "error": None, "spoke": False}

    async def _run(c):
        repo = Path(__file__).resolve().parent.parent.parent
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        try:
            from scripts import live_rules
        except Exception as e:  # loud-ok: an import failure IS the finding here
            out["error"] = f"live_rules import failed: {type(e).__name__}: {str(e)[:200]}"
            logger.error(f"drift check: {out['error']}")
            await log_audit_event("drift_check_error", out["error"], "")
            return out

        code = live_rules.collect_code_facts(repo)
        toggles = live_rules.discover_runtime_toggles(repo)
        env_vars = [f.env_var for f in code.values() if f.kind == "env"] + \
                   [t.env_var for t in toggles.values() if t.env_var]

        # In-process prod snapshot (see header above for why this replaces the SSH path).
        prod = live_rules.ProdState(reachable=False)
        try:
            from agents.market_intelligence.db import (
                get_all_safeguard_states, get_all_strategy_summaries)
            toggle_rows = await get_all_safeguard_states(c)
            strat_rows = await get_all_strategy_summaries(c)
            prod = live_rules.ProdState(reachable=True)
            prod.env = {"apollo-market (in-process)": {v: os.environ.get(v) for v in env_vars}}
            prod.toggles = [
                {"safeguard": r["safeguard"], "account_mode": r["account_mode"],
                 "state": r["state"],
                 "last_transition_at": r["last_transition_at"].isoformat()
                                        if r["last_transition_at"] else ""}
                for r in toggle_rows]
            prod.strategies = [
                {"strategy_id": r["strategy_id"], "phase": r["phase"],
                 "enabled": r["enabled"], "live_real_enabled": r["live_real_enabled"],
                 "position_size_multiplier": str(r["position_size_multiplier"])}
                for r in strat_rows]
        except Exception as e:
            prod = live_rules.ProdState(error=f"{type(e).__name__}: {str(e)[:150]}")
            logger.warning(f"drift check: prod snapshot unavailable — {prod.error}")

        out["prod_reachable"] = prod.reachable
        res = live_rules.Resolver(code, toggles, prod)
        docs = live_rules.load_setup_docs(repo)
        if not docs:
            # Never let "no docs found" read as "no drift found" — a missing docs/ tree (a
            # dropped `COPY docs/ docs/`, a renamed docs/setups/, a bad `repo` resolution) would
            # otherwise silently report 0 DRIFT / 0 UNVERIFIED forever, which is exactly the
            # false-clean failure this whole check exists to prevent.
            out["error"] = f"load_setup_docs found ZERO doc files under {repo} — refusing to report a clean run"
            logger.error(f"drift check: {out['error']}")
            await log_audit_event("drift_check_error", out["error"], "")
            return out
        rows = live_rules.detect_drift(docs, res)

        drift_rows = [r for r in rows if r.severity == "DRIFT"]
        unverified_rows = [r for r in rows if r.severity == "UNVERIFIED"]
        out["drift_n"] = len(drift_rows)
        out["unverified_n"] = len(unverified_rows)

        current_fps = {_drift_fingerprint(r) for r in drift_rows}
        prev = await c.fetchrow(
            "SELECT detail FROM mi_audit_log WHERE event_type = $1 "
            "ORDER BY created_at DESC LIMIT 1", _DRIFT_CHECK_EVENT)
        prev_fps: set = set()
        if prev and prev["detail"]:
            try:
                prev_fps = set(json.loads(prev["detail"]).get("drift_fingerprints", []))
            except Exception:  # loud-ok: a garbled prior snapshot just reads as "all new"
                prev_fps = set()
        new_fps = current_fps - prev_fps
        new_rows = [r for r in drift_rows if _drift_fingerprint(r) in new_fps]
        out["new_drift_n"] = len(new_rows)

        if drift_rows:
            standing_rows = [r for r in drift_rows if _drift_fingerprint(r) not in new_fps]
            lines = [f"🔴 *DOCS-VS-REALITY DRIFT* — {out['drift_n']} finding(s), "
                     f"{out['new_drift_n']} NEW since last night:", "```"]
            for r in sorted(new_rows, key=lambda r: r.where)[:10]:
                lines.append(f"[NEW] {r.where}")
                lines.append(f"  {r.words}")
            if standing_rows:
                lines.append(f"+ {len(standing_rows)} standing (already known, not yet fixed)")
            lines.append("```")
            lines.append("Full report: `python scripts/live_rules.py --drift-only`")
            from agents.market_intelligence.briefing import send_telegram_message
            out["spoke"] = bool(await send_telegram_message("\n".join(lines)))
            if not out["spoke"]:
                # send_telegram_message never raises — it swallows a delivery failure (missing
                # config, network error, a 400 on a genuinely malformed payload) and returns
                # False. Without this line a failed send on the one severity that's supposed to
                # wake someone is invisible everywhere except a single log line nobody tails.
                logger.error(
                    f"drift check: DRIFT Telegram FAILED to send ({out['drift_n']} finding(s), "
                    f"{out['new_drift_n']} new) — check TELEGRAM_BOT_TOKEN / "
                    f"TELEGRAM_ALLOWED_USER_IDS; the finding is still in mi_audit_log")

        # Persist EVERY run, drift or not — this snapshot IS the "previous run" the next run
        # diffs against, and it is also what _aggregate_drift_findings (system_review.py) reads
        # for the Sunday weekly digest's UNVERIFIED line. Includes `spoke` so a silent send
        # failure is visible in the row itself, not just a log line.
        detail = json.dumps({
            "drift_n": out["drift_n"], "unverified_n": out["unverified_n"],
            "new_drift_n": out["new_drift_n"], "prod_reachable": prod.reachable,
            "spoke": out["spoke"],
            "drift_fingerprints": sorted(current_fps),
            "drift_claims": [{"where": r.where, "words": r.words} for r in drift_rows[:15]],
            "unverified_claims": [{"where": r.where, "words": r.words}
                                  for r in unverified_rows[:15]],
        })
        summary = (f"{out['drift_n']} DRIFT ({out['new_drift_n']} new), "
                  f"{out['unverified_n']} UNVERIFIED"
                  + ("" if prod.reachable else " — prod snapshot unavailable")
                  + ("" if out["spoke"] or not drift_rows else " — TELEGRAM SEND FAILED"))
        await log_audit_event(_DRIFT_CHECK_EVENT, summary, detail)
        return out

    if conn is not None:
        return await _run(conn)
    pool = await get_pool()
    async with pool.acquire() as acquired:
        return await _run(acquired)
