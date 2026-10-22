"""#314 stealth-dilution data check (2026-10-21, $0, read-only): does SEC XBRL company-facts carry the warrant / convertible terms we
need, point-in-time, for the SMALL caps that run parabolic? Picks the 60 most-run-up small caps of 2025-26 from mi_daily_closes
(close < $10 at the peak, peak >= 3x the 60-session low), maps them to CIKs via SEC's company_tickers.json, fetches company facts
with the app's own SEC User-Agent (collector._SEC_UA, as the nightly recorders already do), <= 5 requests a second, and counts which
tags exist with a filed date. Run inside apollo-market:  python3 /tmp/xbrl_probe_1021.py > /tmp/xbrl_probe_1021.out"""
import asyncio, json, time
import httpx
from agents.market_intelligence.collector import _SEC_UA
from agents.market_intelligence.db import get_pool

TAGS = {
    "warrants_outstanding": ["ClassOfWarrantOrRightOutstanding"],
    "warrant_exercise_price": ["ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1", "ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights"],
    "convertible_conversion_price": ["DebtInstrumentConvertibleConversionPrice1"],
    "convertible_shares": ["DebtInstrumentConvertibleNumberOfEquityInstruments"],
    "convertible_debt": ["ConvertibleNotesPayable", "ConvertibleDebt", "ConvertibleNotesPayableCurrent", "ConvertibleDebtNoncurrent"],
    "shares_outstanding": ["EntityCommonStockSharesOutstanding"],
}

async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("""
            WITH w AS (SELECT ticker, trade_date, close,
                       min(low_price) OVER (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 60 PRECEDING AND CURRENT ROW) lo60
                       FROM mi_daily_closes WHERE trade_date >= '2025-01-01')
            SELECT ticker, max(close/NULLIF(lo60,0)) runup, max(close) peak FROM w
            WHERE close < 10 AND lo60 > 0.3 GROUP BY ticker HAVING max(close/NULLIF(lo60,0)) >= 3 ORDER BY 2 DESC LIMIT 60""")
    tickers = [r["ticker"] for r in rows]
    async with httpx.AsyncClient(timeout=20, headers=_SEC_UA, follow_redirects=True) as cl:
        m = (await cl.get("https://www.sec.gov/files/company_tickers.json")).json()
        cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in m.values()}
        out = []
        for t in tickers:
            ck = cik.get(t.upper())
            rec = {"ticker": t, "cik": ck}
            if ck:
                time.sleep(0.25)
                r = await cl.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ck}.json")
                rec["http"] = r.status_code
                if r.status_code == 200:
                    facts = r.json().get("facts", {})
                    for k, names in TAGS.items():
                        hit = None
                        for ns in ("us-gaap", "dei"):
                            for n in names:
                                f = facts.get(ns, {}).get(n)
                                if f:
                                    vals = [v for u in f.get("units", {}).values() for v in u]
                                    hit = {"n": len(vals), "last_filed": max((v.get("filed", "") for v in vals), default="")}
                                    break
                            if hit: break
                        rec[k] = hit
            out.append(rec)
    n = len(out); mapped = [r for r in out if r.get("cik")]; ok = [r for r in mapped if r.get("http") == 200]
    print(json.dumps({"population": f"top {n} run-up small caps 2025-26 (peak close < $10, >= 3x the 60-session low)", "n": n,
                      "mapped_to_cik": len(mapped), "facts_200": len(ok),
                      "coverage": {k: sum(1 for r in ok if r.get(k)) for k in TAGS}}, indent=1))
    for r in out:
        print(r["ticker"], r.get("cik"), r.get("http"), {k: (r.get(k) or {}).get("last_filed") for k in TAGS})

asyncio.run(main())
