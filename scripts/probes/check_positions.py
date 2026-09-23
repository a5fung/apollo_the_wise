import os
from alpaca.trading.client import TradingClient
c = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
for p in c.get_all_positions():
    if p.symbol in ("GOOGL", "TEAM"):
        print(p.symbol, "qty=", p.qty, "avg_entry=", p.avg_entry_price, "mv=", p.market_value, "upnl=", p.unrealized_pl)
