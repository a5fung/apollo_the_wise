"""2026-10-06 read-only: CEG traded at score 65 while the regime row says Choppy / bar 75 — which bar acted."""
import asyncio
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        print("regime:", dict(await c.fetchrow("SELECT * FROM mi_market_regime ORDER BY 1 DESC LIMIT 1") or {}))
        for r in await c.fetch("""SELECT scan_time_et, ep_score, score_tier, ep_bar, score_side, catalyst_quality, gap_pct
                                  FROM mi_ep_scan_log WHERE ticker='CEG' AND scan_date=(now() AT TIME ZONE 'America/New_York')::date
                                  ORDER BY scan_time_et LIMIT 6"""):
            print("scan:", dict(r))
        for r in await c.fetch("""SELECT id, ticker, status, account_mode, signal_type, risk_dollars, entry_shares, created_at
                                  FROM mi_live_trades WHERE ticker='CEG' AND created_at > now() - interval '1 day'"""):
            print("trade:", dict(r))
        n = await c.fetchval("""SELECT count(*) FROM mi_ep_scan_log WHERE scan_date > '2026-08-22' AND ep_bar <> 65 AND ep_bar IS NOT NULL""")
        print("scan rows since 08-22 with an acting bar other than 65:", n)


asyncio.run(main())
