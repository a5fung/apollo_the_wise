"""#333 read-only: which free-tier restriction refuses FMP /analyst-estimates? 4 GETs, prints status + FMP's own message."""
import os, httpx
key = os.environ.get("FMP_API_KEY") or os.environ.get("FMP_KEY")
base = "https://financialmodelingprep.com/stable/analyst-estimates"
for sym, limit in (("AAPL", 10), ("AAPL", 20), ("WOLF", 10), ("QCOM", 10)):
    r = httpx.get(base, params={"apikey": key, "symbol": sym, "period": "annual", "page": 0, "limit": limit}, timeout=20)
    body = r.text[:220].replace(key or "", "***")
    print(f"{sym} limit={limit}: HTTP {r.status_code} | {body}")
