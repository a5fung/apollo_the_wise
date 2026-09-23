"""#644 — weekly SHADOW capture of theme down-day resilience.

PURPOSE (RECORDS ONLY — drives NOTHING). PLAN.md #644 froze a decision rule for a
November forward test: does a theme cohort with ABOVE-median down-day resilience hold its
top-30 board slot more often than one below it? That test must read a resilience value that
was CAPTURED WEEKLY AS-OF THE TIME it was measured, never one reconstructed later from
`mi_daily_closes` — a reconstruction that silently differs from a live capture is the #629
defect class this codebase has been bitten by before. This module is that capture, nothing
else.

The measure itself — `db.get_down_day_resilience` — already exists, is already tested
(tests/test_644_down_day_resilience.py, 8 tests incl. a proved-RED as-of leak guard), and is
frozen: this module calls it, once per active theme per week, and never reimplements or
tunes it.

    cohort resilience = median(get_down_day_resilience(d, tickers=cohort)['resilience'])

— median across covered member tickers, matching the aggregation
docs/analysis/644_down_day_resilience_2026-09-11.md used for the (separately, already-run)
pre-registered test, so a later reader comparing this table's numbers against that
document's is comparing like for like.

NEVER SKIPS A THEME. If the measure can't be computed for a theme (no tickers on the
snapshot, or `get_down_day_resilience` returns no coverage — insufficient session history,
zero SPY down days in the window, or no member ticker had a valid down-day observation), the
row is still written: `resilience` NULL, `resilience_computable` FALSE, and
`not_computable_reason` stating why. A missing row and a computed-null are different facts
and must never render identically to a later reader — the single most repeated lesson in
this codebase, and the whole reason `write_theme_resilience_weekly_row` never has a guard
clause that would let a theme fall through unwritten.

⚖ THE LINE: this module writes ONLY `mi_theme_resilience_weekly` (+ `mi_audit_log`). It
never touches a grade/entry/exit/size/admission column or table, and nothing here ranks,
scores, admits, sizes, or alerts on the resilience value. Any future use of it to do any of
those things is a detection-criterion change and stays the operator's call, behind
CHANGE_PROCESS — not something this module proposes or performs.

Idempotent: `write_theme_resilience_weekly_row`'s ON CONFLICT (theme_name, week_start) DO
UPDATE means re-running the job for a week that already has rows recomputes and REPLACES
them rather than accumulating duplicates.

⚠ JOIN RULE FOR THE NOVEMBER READER. `week_start` (week_start_for(as_of_date)) is the ISO
week the CAPTURE ran in, not the board week a cohort's entry belongs to — this job fires
Sunday morning, before the board's own Monday week begins, so a row's `week_start` reads
ONE CALENDAR WEEK EARLIER than the board week it is the correct as-of value for. A cohort
entering the board's top 30 on Monday W needs the row whose `as_of_date == W - 1 day` (the
Sunday walking into W) — join on `as_of_date`, never on `week_start` alone, or the read
silently lags the board by a week (and, going the other way, would leak the entry week's own
price action into what's supposed to describe what was known walking in).

NEVER raises past the caller (SHADOW contract, same discipline as theme_axis_shadow.py):
a per-theme failure swallows to `logger.warning` + an audit event and the loop continues: a
telemetry failure must never cost the rest of the week's rows, and must never propagate into
the job that hosts it.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta

from agents.market_intelligence.db import (
    get_active_themes,
    get_down_day_resilience,
    get_pool,
    log_audit_event,
    write_theme_resilience_weekly_row,
)

logger = logging.getLogger(__name__)

# Frozen with the measure (#644 task line: "Do not change ... the measure. They are frozen
# in the task line.") — matches get_down_day_resilience's own default, spelled out here
# (not left implicit) so a captured row's `lookback_days` column is self-documenting even
# if the function's default is ever revisited later.
DOWN_DAY_RESILIENCE_LOOKBACK = 20

_NO_TICKERS_REASON = "theme snapshot carries no tickers"
_NO_COVERAGE_REASON = (
    "get_down_day_resilience returned no coverage for this theme's tickers — "
    "insufficient session history, zero SPY down days in the window, or no member "
    "ticker had a valid down-day observation"
)


def week_start_for(d: "date") -> "date":
    """Monday of the ISO week containing `d`. The one place a run date maps to a
    `week_start` — pure, so re-running the same week (any day inside it) always resolves
    to the same row identity for the idempotent upsert."""
    return d - timedelta(days=d.weekday())


async def compute_theme_resilience_fields(theme: dict, as_of_date: "date") -> dict:
    """Compute (WITHOUT writing) one active theme's weekly resilience fields. Split out
    from record_theme_resilience_weekly so a dry-run/sample check can call this directly —
    same shape as theme_axis_shadow.compute_unscored_theme_axis_row's split from its writer
    loop, same reason. `theme` is one row from db.get_active_themes() (a dict with at least
    name/stage/theme_date/tickers). Returns every field write_theme_resilience_weekly_row
    needs beyond (week_start, theme_name)."""
    stage = theme.get("stage")
    snapshot_date = theme.get("theme_date")
    tickers = list(theme.get("tickers") or [])

    if not tickers:
        return {
            "theme_stage": stage, "theme_snapshot_date": snapshot_date,
            "tickers": tickers, "n_tickers_covered": 0, "resilience": None,
            "as_of_date": as_of_date, "lookback_days": DOWN_DAY_RESILIENCE_LOOKBACK,
            "resilience_computable": False, "not_computable_reason": _NO_TICKERS_REASON,
        }

    results = await get_down_day_resilience(
        as_of_date, tickers=tickers, lookback=DOWN_DAY_RESILIENCE_LOOKBACK)

    if not results:
        return {
            "theme_stage": stage, "theme_snapshot_date": snapshot_date,
            "tickers": tickers, "n_tickers_covered": 0, "resilience": None,
            "as_of_date": as_of_date, "lookback_days": DOWN_DAY_RESILIENCE_LOOKBACK,
            "resilience_computable": False, "not_computable_reason": _NO_COVERAGE_REASON,
        }

    cohort_resilience = statistics.median(r["resilience"] for r in results)
    return {
        "theme_stage": stage, "theme_snapshot_date": snapshot_date,
        "tickers": tickers, "n_tickers_covered": len(results), "resilience": cohort_resilience,
        "as_of_date": as_of_date, "lookback_days": DOWN_DAY_RESILIENCE_LOOKBACK,
        "resilience_computable": True, "not_computable_reason": None,
    }


async def record_theme_resilience_weekly(as_of_date: "date") -> dict:
    """The weekly job entry point (#644). One row per currently-active theme
    (db.get_active_themes — same 7-day-stale de-facto-retirement population every other
    theme reader uses), written via write_theme_resilience_weekly_row keyed on
    (theme_name, week_start_for(as_of_date)).

    NEVER raises: get_active_themes failing degrades to a zero-themes no-op (logged +
    audited); a single theme's compute/write failing degrades to skipping THAT theme only
    (logged + audited) — every OTHER theme in the week's run still gets its row. Returns
    {"themes": n, "written": n, "computable": n, "not_computable": n}.
    """
    week_start = week_start_for(as_of_date)

    try:
        themes = await get_active_themes()
    except Exception as e:
        logger.warning(f"theme resilience weekly: get_active_themes failed — {e}")
        try:
            await log_audit_event(
                "theme_resilience_weekly_failed",
                f"{week_start}: get_active_themes failed: {type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — logger.warning above already surfaced it
            pass
        return {"themes": 0, "written": 0, "computable": 0, "not_computable": 0}

    written = computable = not_computable = 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        for theme in themes:
            name = theme.get("name")
            try:
                fields = await compute_theme_resilience_fields(theme, as_of_date)
                n = await write_theme_resilience_weekly_row(
                    conn, week_start=week_start, theme_name=name, **fields)
                written += n
                if fields["resilience_computable"]:
                    computable += 1
                else:
                    not_computable += 1
            except Exception as e:
                logger.warning(f"theme resilience weekly: row failed for {name}: {e}")
                try:
                    await log_audit_event(
                        "theme_resilience_weekly_row_failed",
                        f"{name} {week_start}: {type(e).__name__}: {e}",
                    )
                except Exception:  # loud-ok: fallback-of-the-fallback — logger.warning above already surfaced it
                    pass

    try:
        await log_audit_event(
            "theme_resilience_weekly_logged",
            f"{week_start}: {written}/{len(themes)} written "
            f"({computable} computable / {not_computable} not computable)",
        )
    except Exception:  # loud-ok: fallback-of-the-fallback, matches theme_axis_shadow's job-level audit calls
        pass

    return {
        "themes": len(themes), "written": written,
        "computable": computable, "not_computable": not_computable,
    }
