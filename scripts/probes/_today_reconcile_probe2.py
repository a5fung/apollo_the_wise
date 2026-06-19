"""6/16 CLOSE reconciliation — characterize the HIGH, the anomalies, RS cols (read-only)."""
import asyncio
from datetime import date
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        # anomaly_detected detail
        print("=== anomaly_detected — last 30h ===")
        for r in await c.fetch("""
            SELECT created_at, event_type, left(coalesce(detail,''), 240) AS detail
            FROM mi_audit_log
            WHERE created_at >= now() - INTERVAL '30 hours' AND event_type='anomaly_detected'
            ORDER BY created_at"""):
            print(f"  {r['created_at']}  {r['detail']}")

        # today's EP HIGH
        print("\n=== EP HIGH today (mi_ep_alerts) ===")
        cols = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position")]
        pick = [x for x in ("ticker", "alert_date", "created_at", "score_tier", "score",
                            "gap_pct", "orb_submitted", "order_id", "status", "account_mode") if x in cols]
        rows = await c.fetch(
            f"SELECT {', '.join(pick)} FROM mi_ep_alerts WHERE alert_date=$1 AND score_tier='HIGH'",
            date(2026, 6, 16))
        for r in rows:
            print("  " + "  ".join(f"{k}={r[k]}" for k in pick))

        # today's live trades (did anything route through the http ORB handoff?)
        print("\n=== mi_live_trades created today (ORB-handoff evidence) ===")
        lt_cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_live_trades'")}
        datecol = "created_at" if "created_at" in lt_cols else "entry_time"
        pick2 = [x for x in ("ticker", "strategy", "status", "account_mode", "entry_price",
                             "shares", "created_at", "entry_time") if x in lt_cols]
        rows2 = await c.fetch(
            f"SELECT {', '.join(pick2)} FROM mi_live_trades WHERE {datecol}::date = $1 ORDER BY {datecol}",
            date(2026, 6, 16))
        if not rows2:
            print("  (no live trades created today)")
        for r in rows2:
            print("  " + "  ".join(f"{k}={r[k]}" for k in pick2))

        # RS composite column + top-12 liquidity
        print("\n=== #286 RS top-12 (latest score_date) ===")
        cols2 = [r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='mi_stock_scores' ORDER BY ordinal_position")]
        print("  columns:", ", ".join(cols2))


if __name__ == "__main__":
    asyncio.run(main())
