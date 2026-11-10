"""#723 step 5 — an INDEPENDENT recount of one live refresh at the same minute. Read-only. Shares only the INPUT
(the nightly reference); the fetch is raw HTTPS to Alpaca (not collector.get_alpaca_snapshots_batch) and the count is
written here from the contract (docs/architecture/market_breadth_snapshot.md §Live breadth), not breadth_live.py."""
import json, os, time, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
ref = json.load(open("/app/logs/apollo_breadth_reference.json"))
st = ref["stocks"]
uni = [t for t, v in st.items() if v[4]]
key = next(os.environ[k] for k in ("ALPACA_PAPER_API_KEY", "ALPACA_API_KEY", "APCA_API_KEY_ID") if os.environ.get(k))
sec = next(os.environ[k] for k in ("ALPACA_PAPER_SECRET_KEY", "ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY") if os.environ.get(k))
t0 = datetime.now(ET); snaps = {}
for i in range(0, len(uni), 100):
    chunk = uni[i:i + 100]
    req = urllib.request.Request("https://data.alpaca.markets/v2/stocks/snapshots?feed=sip&symbols=" + ",".join(chunk),
                                 headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    for attempt in range(3):
        try:
            snaps.update(json.loads(urllib.request.urlopen(req, timeout=20).read())); break
        except Exception as e:
            time.sleep(1)
t1 = datetime.now(ET); today = t0.date()
adv = dec = unch = nop = miss = 0; hi = lo = elig = 0
for t in uni:
    prev, h252, l252, hl_ok = st[t][0], st[t][1], st[t][2], st[t][3]
    db = (snaps.get(t) or {}).get("dailyBar") or {}
    ts = db.get("t")
    d = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET).date() if ts else None
    c = db.get("c") if d == today else None
    if c is None:
        miss += 1; continue
    if not prev:
        nop += 1
    elif c > prev: adv += 1
    elif c < prev: dec += 1
    else: unch += 1
    h, l = db.get("h"), db.get("l")
    if hl_ok and h and l and h > 0 and l > 0:
        elig += 1; hi += h >= h252; lo += l <= l252
print(json.dumps({"fetch_start_et": t0.strftime("%H:%M:%S"), "fetch_end_et": t1.strftime("%H:%M:%S"),
                  "universe_n": len(uni), "read_n": len(uni) - miss, "missing": miss,
                  "adv_dec": {"advances": adv, "declines": dec, "unchanged": unch, "no_prior": nop},
                  "highs_lows": {"eligible_n": elig, "new_highs": hi, "new_lows": lo}}))
