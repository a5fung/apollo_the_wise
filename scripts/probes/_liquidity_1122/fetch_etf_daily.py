"""Liquidity composite (docs/analysis/liquidity_composite_prereg_2026-11-22.md §6): daily ETF bars, SIP, both adjustments.
Read-only market data; writes /tmp/liq1122/etf_daily_{all,raw}.psv. Keys from env, never printed. Cut at 2024-12-31 (sealed #710)."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed
ET = ZoneInfo("America/New_York")
T = "JNK HYG IEI IEF LQD UUP FXY GLD SLV CPER IWM SPY QQQ SPHB SPLV KRE ARKK TLT".split()
k = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ["ALPACA_API_KEY"]
s = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ["ALPACA_SECRET_KEY"]
c = StockHistoricalDataClient(k, s)
os.makedirs("/tmp/liq1122", exist_ok=True)
for adj, name in ((Adjustment.ALL, "all"), (Adjustment.RAW, "raw")):
    r = c.get_stock_bars(StockBarsRequest(symbol_or_symbols=T, timeframe=TimeFrame.Day, feed=DataFeed.SIP, adjustment=adj,
                                          start=datetime(2015, 6, 1, tzinfo=ET), end=datetime(2024, 12, 31, 23, 59, tzinfo=ET)))
    n = 0
    with open(f"/tmp/liq1122/etf_daily_{name}.psv", "w") as f:
        f.write("ticker|date|o|h|l|c|v\n")
        for sym, bars in r.data.items():
            for b in bars:
                d = b.timestamp.astimezone(ET).date().isoformat()
                assert d <= "2024-12-31"
                f.write(f"{sym}|{d}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}\n"); n += 1
    print(name, n, "rows", sorted(r.data.keys()))
