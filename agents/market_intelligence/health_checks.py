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

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import get_pool, log_audit_event
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
