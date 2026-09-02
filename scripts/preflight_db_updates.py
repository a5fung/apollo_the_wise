"""Boot-time DB UPDATE prepare validation (Gate 5 deliverable B, 2026-05-14).

Walks every parameterized UPDATE statement that runs on the trade lifecycle
hot path and calls `connection.prepare(sql)` against the production schema.
asyncpg's `AmbiguousParameterError` (and similar type-deduction failures)
fire at prepare-time, so this catches the CRMD-class bug at deploy rather
than at first entry fill.

Why this specifically: the 2026-05-14 CRMD incident silently broke every
entry-fill UPDATE for 4 days because the parameter was used for both
`double precision` (entry_price) and `numeric` (lowest_price_seen) columns.
asyncpg flagged it at prepare; nothing ran the prepare until a real fill.
A boot-time walk over the SQL would have caught it before deploy.

Designed to run as a final preflight step. Exits non-zero on any failure.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from agents.market_intelligence.db import (
    _ANALYST_EST_UPSERT_SQL, _DELAYED_DAY0_SQL, _DELAYED_SETTLE_SQL,
    _DELAYED_VARIANT_SETTLE_SQL, EP_ALERT_JUDGE_RESULT_UPDATE_SQL,
    UNIVERSE_FLOOR_SHADOW_INSERT_SQL, get_pool)

logger = logging.getLogger(__name__)


# Each entry is (label, sql) where sql is the EXACT parameterized SQL we
# execute in production code. Update this list when adding new UPDATEs to
# trade-lifecycle tables. The deploy fails if any prepare raises.
#
# The mi_live_trades statements below are DELIBERATE COPIES of the source
# (#265 reviewed 2026-06-10): hoisting them to module constants would break
# Gate 5 G ([5c/7] audit_column_writes.py), which attributes each inline
# `UPDATE mi_live_trades SET ...` block to its ENCLOSING FUNCTION to enforce
# the per-column writer allow-list. Keep each copy in sync with its source —
# the label names the exact module.function to diff against. Statements on
# OTHER tables (e.g. the judge result) are imported from their owner module
# instead, so those can't go stale.
TRADE_LIFECYCLE_UPDATES: list[tuple[str, str]] = [
    (
        "trade_stream._process_entry_fill: entry-fill UPDATE (post-T1.1 5-param)",
        # T1.1 refactor 2026-05-17: dropped stop_price + hard_stop from this
        # UPDATE (entry-fill is not the authorized writer; INSERT sets initial
        # value, update_stop owns trail). Param count 6 → 5.
        """
        UPDATE mi_live_trades SET
            status = 'filled',
            entry_price = $2, entry_shares = $3, remaining_shares = $3,
            filled_at = NOW(),
            stop_order_id = COALESCE($4, stop_order_id),
            lowest_price_seen = COALESCE(lowest_price_seen, $5),
            highest_price_seen = COALESCE(highest_price_seen, $5)
        WHERE id = $1
        """,
    ),
    (
        "trade_stream._process_entry_fill: orders UPDATE",
        """
        UPDATE mi_live_orders SET
            status = 'filled', filled_qty = $2, filled_avg_price = $3, filled_at = NOW()
        WHERE alpaca_order_id = $1
        """,
    ),
    (
        "order_manager.finalize_partial_exit",
        """
        UPDATE mi_live_trades SET
            exits = $2::jsonb,
            remaining_shares = $3,
            total_pnl = $4,
            partial_taken = TRUE,
            breakeven_active = TRUE
        WHERE id = $1
        """,
    ),
    (
        "order_manager._finalize_partial_exit_locked: close-at-zero branch (#566)",
        """
        UPDATE mi_live_trades SET
            exits = $2::jsonb,
            remaining_shares = $3,
            total_pnl = $4,
            partial_taken = TRUE,
            breakeven_active = TRUE,
            status = 'closed',
            stop_order_id = NULL,
            closed_at = NOW()
        WHERE id = $1
        """,
    ),
    (
        "order_manager._finalize_stop_fill_locked: partial-qty branch (#566)",
        """
        UPDATE mi_live_trades SET
            exits = $2::jsonb,
            remaining_shares = $3,
            total_pnl = $4,
            stop_order_id = CASE WHEN stop_order_id = $5
                                 THEN NULL ELSE stop_order_id END
        WHERE id = $1
        """,
    ),
    (
        "trade_stream._process_stop_fill: partial-qty branch (#566)",
        """
        UPDATE mi_live_trades SET
            status = 'filled', exits = $2::jsonb,
            remaining_shares = $3, total_pnl = $4,
            stop_order_id = NULL
        WHERE id = $1 AND status = 'stop_processing'
        """,
    ),
    (
        "order_manager.track_open_position_extremes",
        """
        UPDATE mi_live_trades SET
            lowest_price_seen = LEAST(COALESCE(lowest_price_seen, $2), $2),
            highest_price_seen = GREATEST(COALESCE(highest_price_seen, $3), $3)
        WHERE id = $1
        """,
    ),
    (
        "live_tracker.morning_stop_refresh: non-partial branch (post-T1.4 4-param)",
        # T1.4 refactor 2026-05-17: dropped stop_price + total_pnl +
        # partial_taken + remaining_shares. update_stop owns stop_price;
        # finalize_* own the others. Kept hold_days + breakeven_active +
        # running_closes (live_tracker domain).
        """
        UPDATE mi_live_trades SET
            hold_days = $2,
            breakeven_active = $3,
            running_closes = $4::jsonb
        WHERE id = $1
        """,
    ),
    (
        "live_tracker.morning_stop_refresh: partial_fired branch (post-T1.2 3-param)",
        # T1.2 refactor 2026-05-17: dropped stop_price from this UPDATE.
        # update_stop() at the same call site is the authorized writer.
        """
        UPDATE mi_live_trades SET
            hold_days = $2,
            running_closes = $3::jsonb
        WHERE id = $1
        """,
    ),
    (
        "live_tracker.sync_positions: remaining_shares overwrite",
        "UPDATE mi_live_trades SET remaining_shares = $2 WHERE id = $1",
    ),
    (
        "live_tracker._full_exit: close with exits",
        """
        UPDATE mi_live_trades SET
            status = 'closed', exits = $2::jsonb,
            remaining_shares = 0, stop_price = NULL,
            total_pnl = $3, hold_days = $4, closed_at = NOW(),
            stop_order_id = NULL
        WHERE id = $1
        """,
    ),
    (
        "db.update_ep_alert_judge_result: atomic judge verdict + grade override (#247)",
        # Not mi_live_trades, but LOAD-BEARING since the 2026-06-10 judge flip:
        # this one statement writes the judge columns AND the authoritative
        # score_tier that alert/entry read. A prepare failure here = every
        # judged alert silently falls back to the floor tier. Imported from
        # db.py (the executing module) — the gate prepares the REAL SQL (#265).
        EP_ALERT_JUDGE_RESULT_UPDATE_SQL,
    ),
]


# ── SHADOW / RECORDER WRITERS (added 2026-09-01) ──────────────────────────────────────
#
# WHY THIS SECOND LIST EXISTS. The gate above was scoped to "parameterized UPDATEs on the
# trade-lifecycle hot path" — the shape of the 2026-05-14 CRMD incident. But the BUG CLASS is
# type deduction on ANY parameterized statement, and on 2026-09-01 it recurred in a statement
# the narrow scope did not cover: `mi_universe_floor_shadow`'s INSERT re-used $4/$5/$13/$14/$15
# both as plain column values and inside bare `CASE WHEN ... THEN $n END` arms. Postgres typed
# the CASE arm as `text` against `double precision` elsewhere, asyncpg refused the whole
# executemany batch, and the table sat EMPTY through its first live morning while every tick
# logged a warning nobody was reading. Last night's deploy ran this gate and passed it — the
# statement simply was not in the list.
#
# The lesson is the SCOPE, not the statement: a silent recorder is exactly where this bug hides
# longest, because nothing downstream fails loudly when the write dies. Register a writer here
# when you add one. Statements are IMPORTED from their owner module, never copied — a copy can
# drift from what actually executes, which would make this gate green about the wrong SQL.
SHADOW_WRITER_STATEMENTS: list[tuple[str, str]] = [
    (
        "db.insert_universe_floor_shadow_rows: #606 D-1 universe-floor shadow (the 2026-09-01 case)",
        UNIVERSE_FLOOR_SHADOW_INSERT_SQL,
    ),
    (
        "db.upsert_analyst_estimates: #333 analyst-estimates recorder (executemany since 2026-08-31)",
        _ANALYST_EST_UPSERT_SQL,
    ),
    (
        "db.settle_delayed_entry_trigger: delayed-entry lane incumbent settlement",
        _DELAYED_SETTLE_SQL,
    ),
    *(
        (f"db.settle_delayed_entry_trigger_variant[{_sfx}]: #616 ADR-stop variant settlement",
         _sql)
        for _sfx, _sql in sorted(_DELAYED_VARIANT_SETTLE_SQL.items())
    ),
    (
        "db.record_delayed_entry_trigger_day0: #616 day-0 excursion cache",
        _DELAYED_DAY0_SQL,
    ),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== Preflight: DB UPDATE prepare validation ===\n")
    pool = await get_pool()
    failures: list[tuple[str, str]] = []
    async with pool.acquire() as conn:
        # Ensure lazily-created columns exist BEFORE preparing statements that
        # reference them (2026-06-11: rubric_version is added by
        # _ensure_ep_alert_columns on the first insert after boot, but this
        # gate runs at deploy time, before any insert — the prepare failed on
        # a column the code itself creates moments later. Idempotent.)
        from agents.market_intelligence.db import _ensure_ep_alert_columns
        await _ensure_ep_alert_columns(conn)
        for label, sql in (*TRADE_LIFECYCLE_UPDATES, *SHADOW_WRITER_STATEMENTS):
            try:
                stmt = await conn.prepare(sql)
                params = stmt.get_parameters()
                print(f"  ✓ {label}  ({len(params)} params)")
            except Exception as e:
                print(f"  ✗ {label}: {type(e).__name__}: {e}")
                failures.append((label, f"{type(e).__name__}: {e}"))

    if failures:
        print(f"\n=== PREFLIGHT-DB-UPDATES FAILED ({len(failures)}) ===")
        for label, err in failures:
            print(f"  {label}\n    {err}")
        sys.exit(1)

    print(f"\nPREFLIGHT-DB-UPDATES OK — "
          f"{len(TRADE_LIFECYCLE_UPDATES)} trade-lifecycle + "
          f"{len(SHADOW_WRITER_STATEMENTS)} shadow-writer statements prepared cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
