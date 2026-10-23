"""Survivorship fix for the 2017-21 export (found 2026-10-23): cb702_pre was built from the symbols Alpaca LISTS today, so every stock
acquired or delisted since is missing (TWTR, ATVI, EA, MRO, X, WBA...). Alpaca still serves their bars by name. Runs ON THE SERVER
(read-only, free market data; secrets from the env, never printed):
  1. Polygon /v3/reference/tickers active=false, market=stocks, types CS / ADRC, delisted on or after 2016-01-04 (paginated);
  2. drop the symbols already in the export (argv[1]: one symbol per line);
  3. Alpaca daily bars, split-adjusted, 2016-01-04 .. min(delist date, 2022-06-30), 100 symbols per request;
  writes argv[2] in the export's column order: ticker,date,open,high,low,close,volume (+ a .log of counts).
Known limit: a ticker REUSED by a later company keeps Alpaca's history under that symbol; the export's identity guard handles it later."""
import os, sys, json, time, urllib.request, urllib.parse, datetime as dt
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
have = {ln.strip() for ln in open(sys.argv[1]) if ln.strip()}
out = open(sys.argv[2], "w"); log = open(sys.argv[2] + ".log", "w")
pk = os.environ["POLYGON_API_KEY"]
url = "https://api.polygon.io/v3/reference/tickers?" + urllib.parse.urlencode({"market": "stocks", "active": "false", "limit": 1000})
dl = {}
while url:
    r = json.load(urllib.request.urlopen(url + f"&apiKey={pk}", timeout=60))
    for x in r.get("results") or []:
        d = (x.get("delisted_utc") or "")[:10]
        if x.get("type") in ("CS", "ADRC") and d >= "2016-01-04" and x["ticker"] not in have:
            dl[x["ticker"]] = min(d, dl.get(x["ticker"], "9999"))
    url = r.get("next_url"); time.sleep(0.2)
log.write(f"polygon delisted CS/ADRC since 2016 not in export: {len(dl)}\n"); log.flush()
cl = StockHistoricalDataClient(os.environ["ALPACA_PAPER_API_KEY"], os.environ["ALPACA_PAPER_SECRET_KEY"])
syms = sorted(dl); got = 0; nbars = 0
for i in range(0, len(syms), 100):
    batch = syms[i:i + 100]
    end = min(max(dl[s] for s in batch), "2022-06-30")
    try:
        data = cl.get_stock_bars(StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day, start=dt.datetime(2016, 1, 4),
                                                  end=dt.datetime.fromisoformat(end) + dt.timedelta(days=1), adjustment=Adjustment.SPLIT)).data
    except Exception as e:
        log.write(f"batch {i} error {type(e).__name__}: {str(e)[:120]}\n"); log.flush(); time.sleep(5); continue
    for s, bars in data.items():
        lim = min(dl[s], "2022-06-30"); n = 0
        for b in bars:
            d = b.timestamp.date().isoformat()
            if d <= lim:
                out.write(f"{s},{d},{b.open},{b.high},{b.low},{b.close},{float(b.volume)}\n"); n += 1
        if n: got += 1; nbars += n
    log.write(f"batch {i}: {len(batch)} symbols, {got} with bars so far, {nbars} bars\n"); log.flush(); time.sleep(0.4)
log.write(f"DONE symbols with bars {got} of {len(syms)}; bars {nbars}\n"); out.close(); log.close()
