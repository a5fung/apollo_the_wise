"""Point-in-time security type for the 2017-21 export's UNTYPED admitted tickers (G6 refused at 7.3% of admitted nights, 2026-10-23).
Runs ON THE SERVER in apollo-market (Polygon key from the env, never printed; free reference calls). For each (ticker, as-of date =
its last universe night): the Polygon record for that ticker AS OF that date; if none, the delisted record whose delisting falls on or
after the as-of date (the holder at the time), else the latest delisted record. Output feeds `sectype|SYM|TYPE|` rows.
usage: 07_type_unknowns.py <ticker<TAB>asof file> <out.tsv>"""
import os, sys, json, time, urllib.request, urllib.parse
pk = os.environ["POLYGON_API_KEY"]
def get(params):
    url = "https://api.polygon.io/v3/reference/tickers?" + urllib.parse.urlencode(params); out = []
    while url:
        for k in range(4):
            try:
                r = json.load(urllib.request.urlopen(url + f"&apiKey={pk}", timeout=60)); break
            except Exception:
                time.sleep(5 * (k + 1))
        else:
            return out
        out += r.get("results") or []; url = r.get("next_url"); time.sleep(0.15)
    return out
with open(sys.argv[2], "w") as fh:
    fh.write("ticker\tasof\tsource\ttype\tname\tcik\tcomposite_figi\tdelisted\n")
    for ln in open(sys.argv[1]):
        s, asof = ln.rstrip("\n").split("\t")
        rs, src = get({"ticker": s, "date": asof, "limit": 10}), "asof"
        if not rs:
            gone = sorted(get({"ticker": s, "active": "false", "limit": 50}), key=lambda x: x.get("delisted_utc") or "")
            later = [x for x in gone if (x.get("delisted_utc") or "")[:10] >= asof]
            rs, src = (later[:1], "delisted_after_asof") if later else (gone[-1:], "latest_delisted") if gone else ([], "none")
        r = rs[0] if rs else {}
        fh.write("\t".join([s, asof, src, r.get("type") or "", (r.get("name") or "").replace("\t", " ")[:80], r.get("cik") or "",
                            r.get("composite_figi") or "", (r.get("delisted_utc") or "")[:10]]) + "\n"); fh.flush()
print("DONE")
