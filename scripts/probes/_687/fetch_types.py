# #687 — Polygon reference lookup for the population tickers ABSENT from mi_security_types today (delisted since, mostly):
# what security type were they? Captured ONCE to /tmp/_687_types.json. ~225 calls, paced.
import asyncio, json
from agents.market_intelligence.collector import _polygon_get
async def main():
    ticks = [l.strip() for l in open("/tmp/unclassified_tickers.txt") if l.strip()]
    out = {}
    for t in ticks:
        rec = None
        for active in ("false", "true"):
            try:
                d = await _polygon_get("/v3/reference/tickers", {"ticker": t, "active": active, "limit": 5})
                res = d.get("results") or []
                if res:
                    rec = {k: res[0].get(k) for k in ("ticker", "type", "active", "delisted_utc", "name", "market", "primary_exchange")}
                    break
            except Exception as e:
                rec = {"ticker": t, "error": str(e)[:120]}
            await asyncio.sleep(0.3)
        out[t] = rec
        await asyncio.sleep(0.3)
    json.dump(out, open("/tmp/_687_types.json", "w"))
    print("looked up", len(out), "found", sum(1 for v in out.values() if v and "type" in v))
asyncio.run(main())
