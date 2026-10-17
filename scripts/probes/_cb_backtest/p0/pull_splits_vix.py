"""#702 P0: Polygon split list since 2021-09-27 (all tickers, paginated) + VIX daily history (yfinance).
Read-only market data; runs inside apollo-market; writes /tmp/cb702_splits.psv and /tmp/cb702_vix.psv."""
import os, time
import requests

pk = os.environ.get("POLYGON_API_KEY", "")
url = "https://api.polygon.io/v3/reference/splits"
params = {"execution_date.gte": "2021-09-27", "limit": 1000, "order": "asc", "sort": "execution_date", "apiKey": pk}
rows, pages = [], 0
while url:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    for x in j.get("results", []):
        rows.append((x.get("ticker"), x.get("execution_date"), x.get("split_from"), x.get("split_to")))
    pages += 1
    nxt = j.get("next_url")
    url, params = (nxt, {"apiKey": pk}) if nxt else (None, None)
    time.sleep(0.2)
with open("/tmp/cb702_splits.psv", "w") as fh:
    for t in rows:
        fh.write("|".join("" if v is None else str(v) for v in t) + "\n")
print("splits", len(rows), "pages", pages)

import yfinance as yf
df = yf.download("^VIX", start="2021-06-01", end="2026-10-18", progress=False, auto_adjust=False)
with open("/tmp/cb702_vix.psv", "w") as fh:
    for d, row in df.iterrows():
        c = row["Close"]
        c = float(c.iloc[0]) if hasattr(c, "iloc") else float(c)
        fh.write(f"{d.date()}|{c}\n")
print("vix", len(df))
