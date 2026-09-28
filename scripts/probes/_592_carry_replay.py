import asyncio
from agents.market_intelligence import db, flag_detector as fd
from agents.market_intelligence.db import get_pool
async def m():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""
          WITH f AS (SELECT ticker, scan_date, pivot_high_date, pivot_high_price,
                     lag(scan_date) OVER w prev_scan, lag(pivot_high_date) OVER w prev_pd, lag(pivot_high_price) OVER w prev_pp
                     FROM mi_flag_candidates WHERE scan_date >= '2026-08-01' AND pivot_high_date IS NOT NULL
                     WINDOW w AS (PARTITION BY ticker ORDER BY scan_date))
          SELECT * FROM f WHERE scan_date >= '2026-09-05' AND scan_date - prev_scan BETWEEN 6 AND 40""")
    same = diff = wick = err = 0; ex = []
    for r in rows:
        try:
            h = await db.get_recent_daily_history(r["ticker"], fd._HISTORY_DAYS, end_date=r["scan_date"])
            idx = len(h) - 1
            fresh = fd._find_pivot_high(h, idx)
            carried = fd._find_pivot_high(h, idx, r["prev_pd"], float(r["prev_pp"]))
            if fresh == carried: same += 1
            else:
                diff += 1
                if carried[1] is not None and fresh[1] is not None and fresh[1] > carried[1]: wick += 1
                ex.append((r["ticker"], str(r["scan_date"]), fresh[1], carried[1]))
        except Exception as e:
            err += 1
    print(f"rows {len(rows)} same {same} differ {diff} (fresh top HIGHER than carried: {wick}) errors {err}")
    import json; open("/tmp/carry_replay_rows.json","w").write(json.dumps(ex, default=str)); print(json.dumps(ex, default=str))
asyncio.run(m())
