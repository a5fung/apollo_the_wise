"""Survivorship fix for the 2017-21 export (found 2026-10-23): cb702_pre was built from the symbols Alpaca LISTS today, so every stock
acquired or delisted since is missing (TWTR, ATVI, EA, MRO, X, WBA...). Alpaca still serves their bars by name. Runs ON THE SERVER
(read-only, free market data; secrets from the env, never printed).

Revised 2026-10-23 before its first run, on the #314 recheck's findings:
  - a RENAMED company that still trades (FB -> META) is NOT re-fetched: a delisted record whose composite or share-class FIGI matches an
    ACTIVE record is a rename, not a gone company (the export already double-carries some of those — the dedupe is the rebuild's job);
  - a symbol reused by two delisted companies keeps the LATEST delisting date (the old min() cut the later company's bars off);
  - every batch is retried 3 times with back-off; failed symbols are listed; the log ends with requested / with-bars counts;
  - a sidecar <out>.records.tsv carries ticker, name, type, cik, composite_figi, share_class_figi, delisted for every fetched record, so the
    rebuild can key companies by FIGI / CIK.
Steps: 1. Polygon /v3/reference/tickers active=true (FIGIs) and active=false (CS / ADRC, delisted >= 2016-01-04), paginated;
2. drop renames (FIGI matches an active record) and symbols already in the export (argv[1]); 3. Alpaca daily bars, split-adjusted,
2016-01-04 .. min(latest delisting, 2022-06-30), 100 symbols per request -> argv[2] (ticker,date,open,high,low,close,volume)."""
import os, sys, json, time, urllib.request, urllib.parse, datetime as dt
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

have = {ln.strip() for ln in open(sys.argv[1]) if ln.strip()}
out = open(sys.argv[2], "w"); log = open(sys.argv[2] + ".log", "w")
pk = os.environ["POLYGON_API_KEY"]


def pages(active: str):
    url = "https://api.polygon.io/v3/reference/tickers?" + urllib.parse.urlencode({"market": "stocks", "active": active, "limit": 1000})
    while url:
        for k in range(4):
            try:
                r = json.load(urllib.request.urlopen(url + f"&apiKey={pk}", timeout=60)); break
            except Exception as e:
                log.write(f"polygon page retry {k} ({type(e).__name__})\n"); log.flush(); time.sleep(5 * (k + 1))
        else:
            raise SystemExit("polygon reference pull failed after 4 tries")
        yield from (r.get("results") or [])
        url = r.get("next_url"); time.sleep(0.2)


active_figi = set()
for x in pages("true"):
    for f in ("composite_figi", "share_class_figi"):
        if x.get(f): active_figi.add(x[f])
recs, renamed = {}, 0
for x in pages("false"):
    d = (x.get("delisted_utc") or "")[:10]
    if x.get("type") not in ("CS", "ADRC") or d < "2016-01-04":
        continue
    if (x.get("composite_figi") and x["composite_figi"] in active_figi) or (x.get("share_class_figi") and x["share_class_figi"] in active_figi):
        renamed += 1; continue
    if x["ticker"] in have:
        continue
    recs.setdefault(x["ticker"], []).append(x)
log.write(f"active FIGIs {len(active_figi)}; renames skipped {renamed}; gone CS/ADRC symbols not in export {len(recs)}\n"); log.flush()
with open(sys.argv[2] + ".records.tsv", "w") as fh:
    fh.write("ticker\tname\ttype\tcik\tcomposite_figi\tshare_class_figi\tdelisted\n")
    for s, rs in sorted(recs.items()):
        for x in rs:
            fh.write("\t".join([s, (x.get("name") or "").replace("\t", " "), x.get("type") or "", x.get("cik") or "", x.get("composite_figi") or "",
                                x.get("share_class_figi") or "", (x.get("delisted_utc") or "")[:10]]) + "\n")
end_of = {s: min(max((x.get("delisted_utc") or "")[:10] for x in rs), "2022-06-30") for s, rs in recs.items()}
cl = StockHistoricalDataClient(os.environ["ALPACA_PAPER_API_KEY"], os.environ["ALPACA_PAPER_SECRET_KEY"])
syms = sorted(recs); got, nbars, failed = 0, 0, []
for i in range(0, len(syms), 100):
    batch = syms[i:i + 100]
    end = max(end_of[s] for s in batch)
    data = None
    for k in range(3):
        try:
            data = cl.get_stock_bars(StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day, start=dt.datetime(2016, 1, 4),
                                                      end=dt.datetime.fromisoformat(end) + dt.timedelta(days=1), adjustment=Adjustment.SPLIT)).data
            break
        except Exception as e:
            log.write(f"batch {i} try {k} error {type(e).__name__}: {str(e)[:120]}\n"); log.flush(); time.sleep(10 * (k + 1))
    if data is None:
        failed += batch; continue
    for s, bars in data.items():
        n = 0
        for b in bars:
            d = b.timestamp.date().isoformat()
            if d <= end_of.get(s, "2022-06-30"):
                out.write(f"{s},{d},{b.open},{b.high},{b.low},{b.close},{float(b.volume)}\n"); n += 1
        if n:
            got += 1; nbars += n
    log.write(f"batch {i}: {len(batch)} symbols, {got} with bars so far, {nbars} bars\n"); log.flush(); time.sleep(0.4)
log.write(f"FAILED symbols after retries: {len(failed)} {' '.join(failed[:50])}\n")
log.write(f"DONE requested {len(syms)}; with bars {got}; bars {nbars}\n"); out.close(); log.close()
