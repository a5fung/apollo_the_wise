"""#624 news step 1 — when did Benzinga stop appearing in Polygon's news feed? Market-wide per-day publisher counts, ~every 3rd weekday."""
import asyncio, os, httpx
from datetime import date, timedelta
KEY = os.environ["POLYGON_API_KEY"]; H = {"Authorization": f"Bearer {KEY}"}
async def main():
    async with httpx.AsyncClient(timeout=40) as c:
        d = date(2026, 6, 15); n = 0
        while d <= date(2026, 10, 5):
            if d.weekday() < 5 and n % 2 == 0:
                tot, pubs, url, params, pages = 0, {}, "https://api.polygon.io/v2/reference/news", {"published_utc.gte": d.isoformat(), "published_utc.lte": d.isoformat() + "T23:59:59Z", "limit": 1000}, 0
                while url and pages < 3:
                    r = await c.get(url, params=params if pages == 0 else None, headers=H)
                    if r.status_code != 200: break
                    js = r.json()
                    for a in js.get("results") or []:
                        k = (a.get("publisher") or {}).get("name"); pubs[k] = pubs.get(k, 0) + 1; tot += 1
                    url = js.get("next_url"); pages += 1
                    await asyncio.sleep(0.3)
                print(d, d.strftime("%a"), tot, {k: v for k, v in sorted(pubs.items(), key=lambda x: -x[1])[:5]})
            if d.weekday() < 5: n += 1
            d += timedelta(days=1)
asyncio.run(main())
