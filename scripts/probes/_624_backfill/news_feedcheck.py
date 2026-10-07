"""#624 news step 1 — is Polygon's news feed itself thinner in 2026, or is my window wrong? Market-wide + big-name density by month.
READ-ONLY, ~60 calls, key header-only."""
import asyncio, os, httpx, json
KEY = os.environ["POLYGON_API_KEY"]; H = {"Authorization": f"Bearer {KEY}"}
async def q(c, **p):
    p.setdefault("limit", 1000)
    r = await c.get("https://api.polygon.io/v2/reference/news", params=p, headers=H)
    js = r.json() if r.status_code == 200 else {}
    return r.status_code, js.get("results") or [], js.get("next_url")
async def main():
    async with httpx.AsyncClient(timeout=40) as c:
        print("== latest article per name (desc, limit 3)")
        for t in ["PLTR", "AAPL", "JAGX", "AEIS", "FTK", "BLZE"]:
            st, res, _ = await q(c, ticker=t, order="desc", limit=3)
            print(t, st, [(a["published_utc"][:10], (a.get("publisher") or {}).get("name"), a["title"][:50]) for a in res])
        print("== PLTR articles per month (cap 1000)")
        for lo, hi in [("2024-03-01","2024-04-01"),("2025-03-01","2025-04-01"),("2025-09-01","2025-10-01"),("2026-03-01","2026-04-01"),("2026-06-01","2026-07-01"),("2026-08-01","2026-09-01")]:
            st, res, nxt = await q(c, ticker="PLTR", **{"published_utc.gte": lo, "published_utc.lte": hi})
            pubs = {}
            for a in res: pubs[(a.get("publisher") or {}).get("name")] = pubs.get((a.get("publisher") or {}).get("name"), 0) + 1
            print("PLTR", lo, len(res), "more" if nxt else "", sorted(pubs.items(), key=lambda x: -x[1])[:5])
        print("== market-wide articles on one weekday per period (no ticker filter; cap 1000)")
        for day in ["2024-03-12","2024-09-17","2025-03-11","2025-09-16","2026-03-10","2026-06-16","2026-08-18","2026-09-15"]:
            st, res, nxt = await q(c, **{"published_utc.gte": day, "published_utc.lt": day + "T23:59:59Z" if False else day+"T23:59:59Z"})
            pubs = {}
            for a in res: pubs[(a.get("publisher") or {}).get("name")] = pubs.get((a.get("publisher") or {}).get("name"), 0) + 1
            print(day, len(res), "more" if nxt else "", sorted(pubs.items(), key=lambda x: -x[1])[:5])
asyncio.run(main())
