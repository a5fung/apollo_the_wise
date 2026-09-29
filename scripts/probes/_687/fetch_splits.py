# #687 — pull every US stock split with execution_date >= 2024-01-02 from Polygon (reference endpoint, Starter plan),
# paginated, captured ONCE to /tmp/_687_splits.json inside the container. Needed to re-apply the live $5 prior-close
# and 50k prior-day-volume floors on RAW (unadjusted) values: mi_daily_closes is split-adjusted.
import asyncio, json, os, time
from agents.market_intelligence.collector import _polygon_get
async def main():
    out = []; url = "/v3/reference/splits"; params = {"execution_date.gte": "2024-01-02", "limit": 1000, "sort": "execution_date", "order": "asc"}
    n = 0
    while True:
        data = await _polygon_get(url, params)
        res = data.get("results", []) or []
        out.extend(res); n += 1
        nxt = data.get("next_url")
        if not nxt: break
        # next_url is absolute: strip the base
        url = nxt.split("api.polygon.io")[1].split("?")[0]
        q = nxt.split("?")[1] if "?" in nxt else ""
        params = dict(kv.split("=") for kv in q.split("&") if "=" in kv)
        params.pop("apiKey", None)
        await asyncio.sleep(0.3)
    json.dump(out, open("/tmp/_687_splits.json", "w"))
    print("calls", n, "splits", len(out))
asyncio.run(main())
