"""Step 2 of the survivorship refetch, split out 2026-10-23: the first run's Polygon half finished in apollo-market (records sidecar
written: 3,739 gone CS/ADRC symbols, 395 renames skipped) but that container has no Alpaca keys. This reads the sidecar and fetches the
Alpaca bars in apollo-execution (which has them). Same rules as 01: split-adjusted daily bars 2016-01-04 .. min(latest delisting,
2022-06-30), 100 symbols per request, 3 retries with back-off, failed symbols listed, requested / with-bars counts at the end.
Optional argv[3] = split (default) | raw: the rebuild needs raw closes beside the adjusted ones (the $5 floor and the step check)."""
import os, sys, csv, time, datetime as dt
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
rec = list(csv.DictReader(open(sys.argv[1]), delimiter="\t"))
end_of = {}
for r in rec:
    end_of[r["ticker"]] = max(end_of.get(r["ticker"], ""), r["delisted"])
end_of = {s: min(d, "2022-06-30") for s, d in end_of.items()}
out = open(sys.argv[2], "w"); log = open(sys.argv[2] + ".log", "w")
adj = {"split": Adjustment.SPLIT, "raw": Adjustment.RAW}[sys.argv[3] if len(sys.argv) > 3 else "split"]
cl = StockHistoricalDataClient(os.environ["ALPACA_PAPER_API_KEY"], os.environ["ALPACA_PAPER_SECRET_KEY"])
syms = sorted(end_of); got, nbars, failed = 0, 0, []
for i in range(0, len(syms), 100):
    batch = syms[i:i + 100]; end = max(end_of[s] for s in batch); data = None
    for k in range(3):
        try:
            data = cl.get_stock_bars(StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day, start=dt.datetime(2016, 1, 4),
                                                      end=dt.datetime.fromisoformat(end) + dt.timedelta(days=1), adjustment=adj)).data
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
        if n: got += 1; nbars += n
    log.write(f"batch {i}: {len(batch)} symbols, {got} with bars so far, {nbars} bars\n"); log.flush(); time.sleep(0.4)
log.write(f"FAILED symbols after retries: {len(failed)} {' '.join(failed[:50])}\n")
log.write(f"DONE requested {len(syms)}; with bars {got}; bars {nbars}\n"); out.close(); log.close()
