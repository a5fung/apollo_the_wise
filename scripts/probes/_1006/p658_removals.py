"""2026-10-06 read-only: #658 — the 'label-matched but tape-rejected' assignment refusals since 09-15
(sector test said admit, co-movement said no). Dump every one with the stock's own description and the
theme's description, then draw a FIXED sample of 20 (every 6th row by time — no cherry-picking)."""
import asyncio, json
from agents.market_intelligence.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""SELECT created_at AT TIME ZONE 'America/New_York' t, detail FROM mi_audit_log
                                WHERE event_type='assignment_skipped_comove_below_bar' AND created_at >= '2026-09-15'
                                ORDER BY created_at""")
        pairs = []
        for r in rows:
            try:
                d = json.loads(r["detail"] or "{}")
            except Exception:
                continue
            if d.get("sector_verdict") == "admit":
                pairs.append((r["t"], d))
        print("label-matched tape-rejected pairs since 09-15:", len(pairs))
        uniq = {}
        for _t, d in pairs:
            uniq[(d.get("ticker"), d.get("theme"))] = uniq.get((d.get("ticker"), d.get("theme")), 0) + 1
        print("unique (ticker, theme) pairs:", len(uniq), "| re-judged 3+ nights:", sum(1 for v in uniq.values() if v >= 3))
        sample = pairs[::max(1, len(pairs) // 20)][:20]
        out = []
        for t, d in sample:
            tk, th = d.get("ticker"), d.get("theme")
            o = await c.fetchrow("SELECT company_name, description, industry FROM mi_ticker_overrides WHERE ticker=$1", tk)
            thr = await c.fetchrow("""SELECT description, tickers FROM mi_themes WHERE name=$1 ORDER BY theme_date DESC LIMIT 1""", th)
            out.append({"t": str(t)[:16], "ticker": tk, "theme": th, "corr": d.get("corr"), "bar": d.get("bar"),
                        "overlap": d.get("overlap_sessions"), "stock_sector": d.get("stock_sector"),
                        "company": o["company_name"] if o else None, "industry": o["industry"] if o else None,
                        "stock_desc": (o["description"] or "")[:220] if o else None,
                        "theme_desc": (thr["description"] or "")[:260] if thr else None,
                        "theme_members": list(thr["tickers"] or [])[:12] if thr else None})
        for x in out:
            print(json.dumps(x))


asyncio.run(main())
