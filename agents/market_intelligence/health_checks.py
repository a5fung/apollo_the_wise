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
DEFERRED next increments (job→output-liveness, hard-check registry, heartbeat, partial-break) + the
BASELINE-SELF-POISON limitation (this sweep alerts day-1/2 of a silent null, then quiets as the null
walks into its own rolling baseline — DoD "alert day-1" is MET; persistence re-nagging = increment 2):
see PLAN #370. The self-poison is pinned by test_persistent_null_self_silences_known_limitation.
"""
from __future__ import annotations

import logging
from typing import Any

from agents.market_intelligence.db import get_pool, log_audit_event

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

    return summary
