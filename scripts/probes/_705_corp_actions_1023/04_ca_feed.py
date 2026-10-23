"""Step 3 (server, read-only): Alpaca's corporate-actions feed for every event ticker within the gap date -7 .. +3 (all action types).
Known coverage gap: nothing for 2019 KAR (the OPLN spin-off) — the feed starts around 2020; ZWS/RXN 2021 is found (the positive control)."""
import os, sys, csv, json, urllib.request, urllib.parse, datetime as dt, time
h = {"APCA-API-KEY-ID": os.environ["ALPACA_PAPER_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_PAPER_SECRET_KEY"]}
print("ticker\tgap_date\tactions")
for row in csv.DictReader(open(sys.argv[1]), delimiter="\t"):
    d = dt.date.fromisoformat(row["gap_date"])
    q = urllib.parse.urlencode({"symbols": row["ticker"], "start": str(d - dt.timedelta(days=7)), "end": str(d + dt.timedelta(days=3)), "limit": 50})
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(f"https://data.alpaca.markets/v1/corporate-actions?{q}", headers=h), timeout=30))
        ca = r.get("corporate_actions", {})
        acts = ";".join(f"{k}:{len(v)}" for k, v in ca.items() if v)
    except Exception as e:
        acts = f"error:{type(e).__name__}"
    print(f"{row['ticker']}\t{row['gap_date']}\t{acts}"); time.sleep(0.25)
