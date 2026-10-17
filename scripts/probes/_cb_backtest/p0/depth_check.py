"""#702 P0 depth checks (read-only market data). Runs inside apollo-market.
1) Alpaca SIP 1-minute bars, SPLIT vs RAW adjustment, for days before later splits/reverse splits.
2) Polygon point-in-time ticker details (?date=) incl. a delisted name: SIC fields present?
Prints counts and day high/low only; never prints keys."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment

ET = ZoneInfo("America/New_York")
key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
sec = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
c = StockHistoricalDataClient(key, sec)
for tk, d in [("AAPL", "2022-06-15"), ("NVDA", "2022-06-15"), ("AMC", "2022-06-15"), ("TSLA", "2021-10-01")]:
    for adj in (Adjustment.SPLIT, Adjustment.RAW):
        s = datetime.fromisoformat(d).replace(hour=9, minute=30, tzinfo=ET)
        e = s.replace(hour=16, minute=0)
        try:
            df = c.get_stock_bars(StockBarsRequest(symbol_or_symbols=tk, timeframe=TimeFrame.Minute, start=s, end=e,
                                                   feed=DataFeed.SIP, adjustment=adj)).df
            n = len(df)
            print("alpaca", tk, d, adj.value, n, round(float(df["high"].max()), 4) if n else None,
                  round(float(df["low"].min()), 4) if n else None)
        except Exception as ex:
            print("alpaca", tk, d, adj.value, "ERROR", type(ex).__name__, str(ex)[:120])
pk = os.environ.get("POLYGON_API_KEY", "")
for tk, d in [("SIVB", "2022-06-15"), ("AAPL", "2022-06-15"), ("TWTR", "2022-06-15"), ("FRC", "2022-06-15")]:
    try:
        r = requests.get(f"https://api.polygon.io/v3/reference/tickers/{tk}", params={"date": d, "apiKey": pk}, timeout=20)
        j = r.json().get("results", {}) or {}
        print("polygon", tk, d, r.status_code, j.get("sic_code"), j.get("sic_description"), j.get("active"), j.get("type"))
    except Exception as ex:
        print("polygon", tk, d, "ERROR", type(ex).__name__, str(ex)[:120])
