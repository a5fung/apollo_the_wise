"""
Backfill skip rows for HIGH EP alerts that never produced an mi_live_trades row.

Typical trigger: the 2026-04-22 incident where the event loop hung mid-morning,
4 HIGH EPs were detected, 0 orders placed, and no terminal state was written.
After hardening (bar-stream subscribe timeouts, post-9:59 window writes, etc.),
this script patches any historical day's orphans so the reason-coverage invariant
(zero rows with status IS NULL AND skip_reason IS NULL) holds retrospectively.

Usage:
    python scripts/backfill_orphan_ep_alerts.py YYYY-MM-DD               # dry run
    python scripts/backfill_orphan_ep_alerts.py YYYY-MM-DD --apply       # write
    python scripts/backfill_orphan_ep_alerts.py YYYY-MM-DD --reason "infra:subscribe_timeout: container hang"
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

from agents.market_intelligence.broker.skip_reasons import INFRA_SUBSCRIBE_TIMEOUT
from agents.market_intelligence.db import get_pool


async def _main(target_date: date, apply: bool, reason: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.ticker, a.ep_score, a.catalyst_quality, a.gap_pct,
                   r.regime
            FROM mi_ep_alerts a
            LEFT JOIN mi_live_trades lt
              ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
            LEFT JOIN mi_market_regime r
              ON r.regime_date = a.alert_date
            WHERE a.alert_date = $1
              AND a.score_tier = 'HIGH'
              AND lt.ticker IS NULL
            ORDER BY a.ep_score DESC
        """, target_date)

        if not rows:
            print(f"[{target_date}] no orphaned HIGH alerts — nothing to backfill")
            return

        print(f"[{target_date}] {len(rows)} orphan HIGH alert(s):")
        for r in rows:
            print(f"  {r['ticker']:<6} score={r['ep_score']} catalyst={r['catalyst_quality']} gap={r['gap_pct']}")

        if not apply:
            print(f"\n(dry run) — re-run with --apply to insert skipped rows with reason: {reason!r}")
            return

        inserted = 0
        for r in rows:
            try:
                await conn.execute("""
                    INSERT INTO mi_live_trades
                        (ticker, alert_date, ep_score, catalyst_quality, gap_pct,
                         regime, status, skip_reason)
                    VALUES ($1, $2, $3, $4, $5, $6, 'skipped', $7)
                    ON CONFLICT (ticker, alert_date) DO NOTHING
                """, r["ticker"], target_date, r["ep_score"], r["catalyst_quality"],
                    r["gap_pct"], r["regime"], reason)
                inserted += 1
            except Exception as e:
                print(f"  ! {r['ticker']} insert failed: {e}")
        print(f"\ninserted {inserted}/{len(rows)} skip rows with reason={reason!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        target = date.fromisoformat(sys.argv[1])
    except ValueError:
        print(f"bad date: {sys.argv[1]} — use YYYY-MM-DD")
        sys.exit(1)
    apply_flag = "--apply" in sys.argv
    reason_val = f"{INFRA_SUBSCRIBE_TIMEOUT}: event-loop hang — retro-fit"
    if "--reason" in sys.argv:
        i = sys.argv.index("--reason")
        if i + 1 < len(sys.argv):
            reason_val = sys.argv[i + 1]
    asyncio.run(_main(target, apply_flag, reason_val))
