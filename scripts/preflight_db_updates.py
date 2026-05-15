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

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)


# Each entry is (label, sql) where sql is the EXACT parameterized SQL we
# execute in production code. Update this list when adding new UPDATEs to
# trade-lifecycle tables. The deploy fails if any prepare raises.
TRADE_LIFECYCLE_UPDATES: list[tuple[str, str]] = [
    (
        "trade_stream._process_entry_fill: entry-fill UPDATE",
        """
        UPDATE mi_live_trades SET
            status = 'filled',
            entry_price = $2, entry_shares = $3, remaining_shares = $3,
            hard_stop = $4, stop_price = $4, filled_at = NOW(),
            stop_order_id = COALESCE($5, stop_order_id),
            lowest_price_seen = COALESCE(lowest_price_seen, $6),
            highest_price_seen = COALESCE(highest_price_seen, $6)
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
        "order_manager.track_open_position_extremes",
        """
        UPDATE mi_live_trades SET
            lowest_price_seen = LEAST(COALESCE(lowest_price_seen, $2), $2),
            highest_price_seen = GREATEST(COALESCE(highest_price_seen, $3), $3)
        WHERE id = $1
        """,
    ),
    (
        "live_tracker.morning_stop_refresh: non-partial branch",
        """
        UPDATE mi_live_trades SET
            stop_price = $2, hold_days = $3, total_pnl = $4,
            partial_taken = $5, breakeven_active = $6,
            running_closes = $7::jsonb,
            remaining_shares = $8
        WHERE id = $1
        """,
    ),
    (
        "live_tracker.morning_stop_refresh: partial_fired branch (post-2026-05-14 fix)",
        """
        UPDATE mi_live_trades SET
            stop_price = $2, hold_days = $3,
            running_closes = $4::jsonb
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
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== Preflight: DB UPDATE prepare validation ===\n")
    pool = await get_pool()
    failures: list[tuple[str, str]] = []
    async with pool.acquire() as conn:
        for label, sql in TRADE_LIFECYCLE_UPDATES:
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

    print(f"\nPREFLIGHT-DB-UPDATES OK — {len(TRADE_LIFECYCLE_UPDATES)} statements prepared cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
