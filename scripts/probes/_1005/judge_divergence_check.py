"""2026-10-05 read-only: the #301 grounding check — the week's judge 2nd-opinion rows, the disagreement in
full, and what the alert went on to do (daily bars)."""
import asyncio
from datetime import timedelta
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT * FROM mi_judge_divergence WHERE alert_date >= '2026-09-26' ORDER BY alert_date")
        for r in rows:
            print({k: (str(v)[:400] if v is not None else None) for k, v in dict(r).items()})
            if not r["agree"]:
                al = await c.fetchrow("SELECT ep_score, score_tier, catalyst_quality, gap_pct "
                                      "FROM mi_ep_alerts WHERE ticker=$1 AND alert_date=$2 ORDER BY ep_score DESC LIMIT 1",
                                      r["ticker"], r["alert_date"])
                print("  ALERT:", dict(al) if al else None)
                bars = await c.fetch("SELECT trade_date, open_price, high_price, low_price, close FROM mi_daily_closes "
                                     "WHERE ticker=$1 AND trade_date BETWEEN $2 AND $3 ORDER BY trade_date",
                                     r["ticker"], r["alert_date"] - timedelta(days=3), r["alert_date"] + timedelta(days=10))
                for b in bars:
                    print("   ", b["trade_date"], b["open_price"], b["high_price"], b["low_price"], b["close"])


asyncio.run(main())
