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
import statistics
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import (
    get_pool, log_audit_event,
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
    """Mirrors theme_engine._rs_rising exactly: newest-first `hist`, rising iff
    >=4 points AND hist[0] (newest) > hist[-1] (oldest, up to 6 sessions back)."""
    return len(hist) >= _PRUNE_HOLD_MIN_POINTS_MIRROR and hist[0] > hist[-1]


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
