"""6/16 CLOSE reconcile — ORB-handoff cleanliness (#1) + RS leaderboard liquidity (#286)."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        # ORB-handoff / entry-pipeline actions + any infra failures today
        print("=== entry-pipeline audit events today (RXT/NTLA ORB handoff) ===")
        rows = await c.fetch("""
            SELECT created_at, event_type, left(coalesce(detail,''),180) AS d
            FROM mi_audit_log
            WHERE created_at::date = $1
              AND (event_type ILIKE '%orb%' OR event_type ILIKE '%entry%'
                   OR event_type ILIKE '%auto_enter%' OR event_type ILIKE '%proposed%'
                   OR event_type ILIKE '%execution%' OR event_type ILIKE '%unreachable%'
                   OR detail ILIKE '%RXT%' OR detail ILIKE '%NTLA%'
                   OR detail ILIKE '%ExecutionUnreachable%' OR detail ILIKE '%infra:%')
            ORDER BY created_at LIMIT 40
        """, date(2026, 6, 16))
        if not rows:
            print("  (no orb/entry/execution audit events today)")
        for r in rows:
            print(f"  {r['created_at']:%H:%M:%S} {r['event_type']:<26} {r['d']}")

        # #286 RS top-12 liquidity (rs_composite is the real column)
        print("\n=== #286 RS top-12 by rs_composite (latest score_date) ===")
        sd = await c.fetchval("SELECT MAX(score_date) FROM mi_stock_scores")
        rows2 = await c.fetch("""
            SELECT ticker, rs_composite, rs_rank, close, adv_20, market_cap
            FROM mi_stock_scores WHERE score_date=$1
            ORDER BY rs_composite DESC NULLS LAST LIMIT 12""", sd)
        print(f"  score_date={sd}")
        for r in rows2:
            dvol = (r["close"] or 0) * (r["adv_20"] or 0) if r["adv_20"] else None
            dtag = f"${dvol/1e6:8.1f}M/d" if dvol else "  adv?=pass"
            flag = "  <-- THIN" if (dvol is not None and dvol < 20_000_000) else ""
            print(f"  {r['ticker']:<6} comp={float(r['rs_composite'] or 0):6.1f} px={r['close'] or 0:8.2f} {dtag}{flag}")


if __name__ == "__main__":
    asyncio.run(main())
