"""Stage 1c step 3: THE RAW-CLOSE PULL. Free Alpaca SIP daily bars, adjustment=RAW, dates <= 2024-12-31 only. Run ONCE.
Needs the Alpaca keys (env ALPACA_PAPER_API_KEY / ALPACA_API_KEY, as scripts/probes/_620_fetch_bars.py): they live only
in the apollo-market container. Usage (operator-approved host access only):
  python s1c_pull.py <bws1124_raw_request.tsv> <out_dir>      -> raw_close_bwin_1124.csv.gz (ticker,date,close,volume) + .meta.json
Refuses if any request row carries a date > 2024-12-31 or the request sha differs from the pinned one; refuses to write
if any returned bar is dated > 2024-12-31. Never prints a key."""
import csv, gzip, hashlib, json, os, sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
_ET = ZoneInfo("America/New_York"); CUT = date(2024, 12, 31)
PINNED = "164da7965c3b9c6ffa49c56cee073c37602eb6604d97c3a31302d750a5020f39"

def main(req_path, out_dir):
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    raw = open(req_path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest(); assert sha == PINNED, "request sha differs from the pinned one"
    rows = [r for r in csv.reader(raw.decode().splitlines(), delimiter="\t") if r and r[0] != "ticker"]
    for r in rows:
        assert date.fromisoformat(r[2]) <= CUT and date.fromisoformat(r[1]) <= CUT, f"REFUSED: request row after {CUT}: {r}"
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec: raise SystemExit("no Alpaca keys in env")
    client = StockHistoricalDataClient(key, sec)
    feed = DataFeed.SIP; assert feed == DataFeed.SIP
    out, empty, errors, maxd = [], [], [], date(1970, 1, 1)
    for t, first, last, *_ in rows:
        d0, d1 = date.fromisoformat(first), min(date.fromisoformat(last), CUT)
        req = StockBarsRequest(symbol_or_symbols=t, timeframe=TimeFrame.Day,
                               start=datetime(d0.year, d0.month, d0.day, tzinfo=_ET),
                               end=datetime(d1.year, d1.month, d1.day, tzinfo=_ET) + timedelta(days=1),
                               feed=feed, adjustment=Adjustment.RAW, limit=None)
        try:
            bars = client.get_stock_bars(req).data.get(t) or []
        except Exception as e:  # loud-ok: recorded per ticker
            errors.append(f"{t}: {type(e).__name__}: {str(e)[:120]}"); continue
        k = 0
        for b in bars:
            d = b.timestamp.astimezone(_ET).date()
            if d0 <= d <= d1:
                out.append((t, d.isoformat(), b.close, b.volume)); maxd = max(maxd, d); k += 1
        if not k: empty.append(t)
    assert maxd <= CUT, f"REFUSED to write: a returned bar is dated {maxd}"
    p = os.path.join(out_dir, "raw_close_bwin_1124.csv.gz")
    with gzip.open(p, "wt", newline="") as f:
        csv.writer(f).writerows(out)
    meta = {"adjustment": "raw", "feed": "sip", "request_sha256": sha, "tickers_requested": len(rows), "tickers_with_rows": len({o[0] for o in out}),
            "rows": len(out), "min_date": min(o[1] for o in out), "max_date": maxd.isoformat(), "empty": len(empty), "errors": len(errors),
            "pulled_at": datetime.now(timezone.utc).isoformat()}
    json.dump(meta, open(os.path.join(out_dir, "raw_close_bwin_1124.meta.json"), "w"), indent=1)
    open(os.path.join(out_dir, "raw_close_bwin_1124.log"), "w").write("EMPTY\n" + "\n".join(empty) + "\nERRORS\n" + "\n".join(errors) + "\n")
    print(json.dumps(meta)); return 0 if not errors else 3

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
