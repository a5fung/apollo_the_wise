"""One-shot backfill of lowest_price_seen / highest_price_seen on
historical closed trades.

For each closed paper trade with NULL extremes, queries Polygon minute
bars between filled_at and closed_at (inclusive of the entire holding
window), computes MIN(low) and MAX(high), and UPDATEs the row.

Idempotent: only operates on rows where BOTH extreme columns are NULL.
Re-running after a successful backfill is a no-op.

Run on Hetzner:
  docker exec apollo-market python -m scripts.backfill_position_extremes

Or locally:
  python -m scripts.backfill_position_extremes

Origin: 2026-05-10. Lights up Apollo Trades dashboard Phase 3 panel
(#51) against paper trade history without waiting for live cutover.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, timedelta

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_position_extremes")


async def _backfill_one(trade: dict) -> tuple[bool, str]:
    """Compute extremes for one trade. Returns (success, message)."""
    ticker = trade["ticker"]
    filled_at = trade["filled_at"]
    closed_at = trade["closed_at"]
    if not filled_at or not closed_at:
        return False, "missing filled_at or closed_at"

    from_d = filled_at.date()
    to_d = closed_at.date()
    # Cap range to ~30d to keep Polygon response under the 50k-bar limit.
    if (to_d - from_d).days > 30:
        return False, f"hold span {(to_d - from_d).days}d > 30d cap"

    bars = await get_minute_bars(ticker, from_d.isoformat(), to_d.isoformat())
    if not bars:
        return False, "no minute bars returned"

    # Filter to the actual hold window (Polygon returns full days; trim
    # bars outside [filled_at, closed_at] timestamps). t = epoch ms.
    filled_ms = int(filled_at.timestamp() * 1000)
    closed_ms = int(closed_at.timestamp() * 1000)
    in_window = [
        b for b in bars
        if b.get("t") and filled_ms <= int(b["t"]) <= closed_ms
        and b.get("l") and b.get("h")
    ]
    if not in_window:
        return False, "no bars in hold window after timestamp filter"

    lo = min(float(b["l"]) for b in in_window)
    hi = max(float(b["h"]) for b in in_window)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_live_trades
            SET lowest_price_seen = $2, highest_price_seen = $3
            WHERE id = $1
              AND lowest_price_seen IS NULL
              AND highest_price_seen IS NULL
            """,
            trade["id"], lo, hi,
        )
    return True, f"lo=${lo:.2f} hi=${hi:.2f} ({len(in_window)} bars)"


async def main() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ticker, filled_at, closed_at
            FROM mi_live_trades
            WHERE status IN ('closed', 'stopped')
              AND filled_at IS NOT NULL
              AND closed_at IS NOT NULL
              AND lowest_price_seen IS NULL
              AND highest_price_seen IS NULL
            ORDER BY closed_at DESC
            """,
        )
    logger.info(f"Backfill candidates: {len(rows)} closed trades with NULL extremes")
    if not rows:
        return 0

    ok = 0
    skipped = 0
    for r in rows:
        trade = dict(r)
        success, msg = await _backfill_one(trade)
        if success:
            ok += 1
            logger.info(
                f"  ✓ {trade['ticker']:6} id={trade['id']} {msg}"
            )
        else:
            skipped += 1
            logger.warning(
                f"  ✗ {trade['ticker']:6} id={trade['id']} skipped — {msg}"
            )

    logger.info(f"Backfill complete: {ok} updated, {skipped} skipped")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
