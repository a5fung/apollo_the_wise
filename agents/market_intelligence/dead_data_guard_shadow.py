"""#488 SHADOW — nightly compare: RMV dead-data guard (inferred) vs authoritative halts.

Tracked as #488 (live-path project; #386, the original design-audit task, is closed). Merged
2026-09-12 from branch ba7533b, ~1,500 commits behind main at merge time — re-applied unchanged
after confirming `_compute_rmv`/`_ntr`/`_wilder_tr` are still byte-identical and every DB/import
call site below still resolves. One drift note: `flag_detector._HISTORY_DAYS` was recalibrated
2026-09-05 from 380 CALENDAR days to 262 TRADING days (`get_recent_daily_history` now counts
rows, not a date span) — this module imports the constant by name rather than hardcoding it, so
it picked up the new semantics for free; 262 trading rows still comfortably covers the 15-bar
RMV lookback this compare needs.

The RMV halt-floor (`flag_detector._RMV_DEAD_NTR_FLOOR`, commit 20c9c06) INFERS "halted /
frozen-feed / dead data" from a zero-range recent window of daily bars. This job logs that
inferred verdict BESIDE the authoritative per-security trading-status flag captured off
Alpaca's WS `statuses` channel (broker/halt_status_shadow.py → mi_halt_status_events), one
row per interesting (ticker, scan_date), into mi_dead_data_guard_shadow.

SHADOW-ONLY: pure read → recompute → telemetry-write. It never touches the live guard, any
detection table, or any entry path; `run_dead_data_guard_shadow` never raises (a shadow
failure must not fail the flag-scan job it piggybacks on). Flipping the live guard to read
the authoritative flag is a detection-criterion change — operator sign-off + CHANGE_PROCESS
on the measured agreement (docs/analysis/386_authoritative_halt_data_2026-07-18.md).

COHORT (the informative cells of the 2×2, exception-row design):
  · every scanned ticker whose persisted rmv_15d is NULL  → did the guard's None coincide
    with a real halt? (recomputed `rmv_none_reason` separates dead_floor from the benign
    insufficient-history/early-return NULLs);
  · every ticker with ≥1 authoritative status event in the trailing compare window →
    did a real halt trip the floor? (includes halted names OUTSIDE the flag universe —
    coverage telemetry via in_flag_universe=False).
The both-negative cell (scanned, rmv computed, no halt) is the uninformative bulk — its
count is derivable from mi_flag_candidates row counts, so no rows are written for it.

EXPECTED-DISAGREE CLASS (not a guard bug — bucket by status/reason codes in the analysis):
an intraday LULD pause (halt + resume same session) leaves the DAILY bar with a real range,
so the daily-bar floor SHOULD NOT trip on it; the guard's target is the multi-day T12-class
halt / frozen feed. The agreement analysis must therefore read `halt_codes`, not just the
boolean.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Trailing calendar-day window for "was there an authoritative status event" — covers the
# guard's current_window=3 TRADING bars (weekend-safe) without reaching back so far that a
# long-resolved halt pollutes the compare.
_COMPARE_WINDOW_DAYS = 5

# rmv_none_reason values that constitute the guard's DEAD verdict (the inference under
# test). insufficient_history / degenerate_close are benign Nones, not dead-data calls.
_DEAD_REASONS = frozenset({"dead_floor", "zero_base"})


async def run_dead_data_guard_shadow(scan_date: date) -> dict:
    """Write the compare rows for `scan_date`. Returns a summary counts dict; NEVER raises."""
    out = {"n_null_rmv": 0, "n_halted": 0, "n_rows": 0, "n_agree": 0}
    try:
        from agents.market_intelligence import db
        from agents.market_intelligence.flag_detector import (
            _HISTORY_DAYS, _compute_rmv, rmv_none_reason,
        )

        rmv_map = await db.get_flag_scan_rmv_map(scan_date)
        null_tickers = {t for t, v in rmv_map.items() if v is None}
        halt_map = await db.get_halt_events_between(
            scan_date - timedelta(days=_COMPARE_WINDOW_DAYS), scan_date,
        )
        out["n_null_rmv"] = len(null_tickers)
        out["n_halted"] = len(halt_map)

        for ticker in sorted(null_tickers | set(halt_map)):
            history = await db.get_recent_daily_history(
                ticker, _HISTORY_DAYS, end_date=scan_date,
            )
            # Mirror the structure-probe bar filter: _wilder_tr needs H+L (pre-backfill /
            # sparse rows carry NULLs that would TypeError inside the pure helpers).
            rows = [r for r in history
                    if r.get("high_price") is not None and r.get("low_price") is not None]
            if rows:
                idx = len(rows) - 1
                rmv = _compute_rmv(rows, idx, lookback=15)
                reason = rmv_none_reason(rows, idx, lookback=15)
            else:
                rmv, reason = None, "no_history"
            events = halt_map.get(ticker, [])
            inferred_dead = reason in _DEAD_REASONS
            halted = bool(events)
            row = {
                "scan_date": scan_date,
                "ticker": ticker,
                "rmv_15d": rmv,
                "none_reason": reason,
                "inferred_dead": inferred_dead,
                "halted_authoritative": halted,
                "halt_events_n": len(events),
                "halt_codes": sorted({
                    c for e in events
                    for c in (e.get("status_code"), e.get("reason_code")) if c
                }),
                "in_flag_universe": ticker in rmv_map,
                "agree": inferred_dead == halted,
            }
            await db.upsert_dead_data_guard_shadow(row)
            out["n_rows"] += 1
            out["n_agree"] += int(row["agree"])

        logger.info(
            f"dead-data guard shadow {scan_date}: {out['n_rows']} compare rows "
            f"({out['n_null_rmv']} null-rmv, {out['n_halted']} halted, "
            f"{out['n_agree']} agree)"
        )
    except Exception:
        # SHADOW-ONLY: swallow — the flag-scan job this piggybacks on must not fail.
        logger.exception("dead-data guard shadow failed (shadow-only, swallowed)")
    return out
