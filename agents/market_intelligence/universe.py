"""
Stock universe for RS calculations.

~150 liquid US stocks covering all major sectors and themes.
Polygon free tier supports individual ticker aggregates, so we use
a curated list rather than pulling all 8000+ US stocks.

Expand this list over time. Keep to ~200 max for the nightly run
to complete in <1 hour at Polygon free tier (5 calls/min).
"""

UNIVERSE: list[str] = [
    # Technology — large cap
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "QCOM", "INTC", "MU", "AMAT", "LRCX",
    "KLAC", "MRVL", "SMCI", "ARM", "CRWD", "PANW", "FTNT", "ZS", "OKTA", "CYBR",
    "NOW", "CRM", "SNOW", "DDOG", "MDB", "TEAM", "ASAN", "HUBS",
    # Technology — mid cap / high growth
    "PLTR", "AI", "PATH", "SOUN", "IONQ", "QUBT", "RGTI", "ARQQ",
    # Semiconductors / AI infrastructure
    "TSM", "ASML", "MCHP", "ADI", "TXN", "ON", "WOLF",
    # AI optical / networking
    "CIEN", "FNSR", "COHR", "LITE", "VIAVI", "IIVI",
    # Cloud / hyperscalers
    "META", "GOOGL", "AMZN", "MSFT",
    # Consumer discretionary
    "TSLA", "AMZN", "NKE", "LULU", "DECK", "ON", "CROX",
    "BKNG", "ABNB", "UBER", "LYFT", "DPZ", "CMG",
    # Financials
    "JPM", "GS", "MS", "BLK", "V", "MA", "PYPL", "SQ", "COIN",
    "BAC", "WFC", "C", "AXP", "SCHW",
    # Healthcare / biotech
    "LLY", "NVO", "ABBV", "MRK", "PFE", "AMGN", "GILD", "REGN",
    "VRTX", "MRNA", "BNTX", "SGEN", "INCY",
    "IRTC", "ISRG", "DXCM", "PODD", "GEHC",
    # Energy
    "XOM", "CVX", "COP", "EOG", "PXD", "SLB", "HAL",
    "FANG", "MPC", "VLO",
    # Industrials
    "CAT", "DE", "HON", "RTX", "LMT", "GD", "NOC",
    "GE", "ETN", "AXON", "TRMB",
    # Materials
    "FCX", "NEM", "AA", "X", "STLD", "RS",
    # Utilities
    "NEE", "VST", "NRG", "CEG",
    # Real estate
    "AMT", "EQIX", "PLD",
    # Consumer staples
    "COST", "WMT", "MNST", "KO", "PEP",
    # Communications
    "NFLX", "DIS", "SPOT", "TTD", "PINS", "SNAP",
    # ETFs for regime / benchmark
    "SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLI",
]

# Deduplicate while preserving order
_seen = set()
UNIVERSE = [t for t in UNIVERSE if not (t in _seen or _seen.add(t))]
