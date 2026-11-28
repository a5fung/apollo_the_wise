# #736 real-data dry run (read-only: Polygon + Alpaca reads, one SELECT). Run inside apollo-market.
import asyncio, json, time
from agents.market_intelligence import ep_detector as ep
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.trading_calendar import previous_trading_day

async def main():
    from agents.market_intelligence.ep_detector import get_snapshot_all
    snaps = await get_snapshot_all(caller="dryrun_736")
    pool = await get_pool()
    async with pool.acquire() as c:
        ns = {r["ticker"] for r in await c.fetch("SELECT ticker FROM mi_security_types WHERE security_type NOT IN ('CS','ADRC')")}
        ks = {r["ticker"] for r in await c.fetch("SELECT ticker FROM mi_security_types WHERE security_type IN ('CS','ADRC')")}
    today = et_today()
    fill_date = previous_trading_day(today)
    rows = ep._prev_close_fill_targets(snaps, ks, ns)
    t0 = time.monotonic()
    patched, counts = await ep._fill_missing_prev_closes(rows, today, fill_date)
    cold = time.monotonic() - t0
    t0 = time.monotonic()
    await ep._fill_missing_prev_closes(rows, today, fill_date)
    warm = time.monotonic() - t0
    clear = []
    for t, s in patched.items():
        pd = s["prevDay"]
        if pd["c"] >= ep.MIN_PREV_CLOSE and pd["v"] >= ep.MIN_PREV_DAY_VOLUME:
            clear.append((t, pd["c"], pd["v"], s[ep._PREV_CLOSE_FILL_MARK]))
    out = {"today": str(today), "fill_date": str(fill_date), "snapshot_rows": len(snaps),
           "targets": len(rows), "filled": counts, "not_filled": len(rows) - len(patched),
           "cold_s": round(cold, 2), "warm_s": round(warm, 3),
           "clear_floors_n": len(clear), "clear_floors": sorted(clear)[:200],
           "target_sample": sorted(rows)[:40]}
    print(json.dumps(out, default=str))
asyncio.run(main())
