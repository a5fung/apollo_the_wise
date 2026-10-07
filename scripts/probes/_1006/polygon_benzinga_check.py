"""2026-10-06 read-only: independent check of the claim 'Polygon news stopped carrying Benzinga from 2026-06-19'
(the #692 M&A headline scan reads Polygon news). Counts articles by publisher on sample days."""
import asyncio, os, collections
import httpx

KEY = os.environ.get("POLYGON_API_KEY", "")
DAYS = ["2026-05-14", "2026-06-10", "2026-06-17", "2026-06-23", "2026-07-15", "2026-09-10", "2026-10-02"]


async def day(session, d):
    url = "https://api.polygon.io/v2/reference/news"
    params = {"published_utc.gte": f"{d}T00:00:00Z", "published_utc.lte": f"{d}T23:59:59Z", "limit": "1000", "order": "asc"}
    pubs = collections.Counter()
    n = 0
    while url and n < 5:
        r = await session.get(url, params=params, headers={"Authorization": f"Bearer {KEY}"})
        j = r.json()
        for a in j.get("results", []):
            pubs[(a.get("publisher") or {}).get("name", "?")] += 1
        url = j.get("next_url"); params = None; n += 1
    return d, sum(pubs.values()), pubs.most_common(6)


async def main():
    async with httpx.AsyncClient(timeout=30) as s:
        for d in DAYS:
            dd, tot, top = await day(s, d)
            print(dd, tot, top)


asyncio.run(main())
