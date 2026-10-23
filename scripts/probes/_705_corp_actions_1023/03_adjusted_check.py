"""Step 2 (server, read-only, free Alpaca market data): for each (ticker, gap_date) event, the one-session open gap under the SPLIT-adjusted
daily bars (what our export holds) vs the ALL-adjusted bars (splits + dividends + spin-offs). A gap that shrinks by more than half under
'all' is a distribution / spin-off artifact, not a price move. Prints one TSV line per event; secrets are read from the env, never printed."""
import csv, os, sys, datetime as dt
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
cl = StockHistoricalDataClient(os.environ["ALPACA_PAPER_API_KEY"], os.environ["ALPACA_PAPER_SECRET_KEY"])
def gap(tk, d, adj):
    day = dt.date.fromisoformat(d)
    r = StockBarsRequest(symbol_or_symbols=tk, timeframe=TimeFrame.Day, start=day - dt.timedelta(days=10), end=day + dt.timedelta(days=1), adjustment=adj)
    bars = cl.get_stock_bars(r).data.get(tk, [])
    b = [x for x in bars if x.timestamp.date() <= day]
    if len(b) < 2 or b[-1].timestamp.date() != day: return None, None
    return b[-1].open / b[-2].close - 1, b[-2].close
print("ticker\tgap_date\tgap_split\tgap_all\tprev_close_split\tverdict")
for row in csv.DictReader(open(sys.argv[1]), delimiter="\t"):
    try:
        gs, pcs = gap(row["ticker"], row["gap_date"], Adjustment.SPLIT); ga, _ = gap(row["ticker"], row["gap_date"], Adjustment.ALL)
    except Exception as e:
        print(f"{row['ticker']}\t{row['gap_date']}\t\t\t\terror:{type(e).__name__}"); continue
    if gs is None or ga is None: v = "no_bar"
    elif abs(ga) < abs(gs) / 2: v = "ARTIFACT_distribution"
    else: v = "real_move"
    print(f"{row['ticker']}\t{row['gap_date']}\t{'' if gs is None else round(gs,4)}\t{'' if ga is None else round(ga,4)}\t{'' if pcs is None else round(pcs,2)}\t{v}")
