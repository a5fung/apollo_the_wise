"""Classify the refetch's misses (2026-10-23) so recall is judged per COMPANY, not per symbol. Runs ON THE SERVER in apollo-market
(Polygon key from the env, never printed; read-only reference calls, free). For each missed symbol: its Polygon record AS OF
2022-03-31 (type, name, CIK, FIGIs) and any delisted records; then its CURRENT ticker via an active record with the same composite /
share-class FIGI or, failing that, the same CIK. The local step decides covered-under-the-new-name vs a real gap.
usage: 04_classify_misses.py <misses.txt> <out.tsv>"""
import os, sys, json, time, urllib.request, urllib.parse
pk = os.environ["POLYGON_API_KEY"]
def get(params):
    url = "https://api.polygon.io/v3/reference/tickers?" + urllib.parse.urlencode(params)
    out = []
    while url:
        for k in range(4):
            try:
                r = json.load(urllib.request.urlopen(url + f"&apiKey={pk}", timeout=60)); break
            except Exception:
                time.sleep(5 * (k + 1))
        else:
            return out + [{"_error": "failed"}]
        out += r.get("results") or []; url = r.get("next_url"); time.sleep(0.15)
    return out
act_figi, act_cik = {}, {}
for x in get({"market": "stocks", "active": "true", "limit": 1000}):
    for f in ("composite_figi", "share_class_figi"):
        if x.get(f): act_figi.setdefault(x[f], x["ticker"])
    if x.get("cik") and x.get("type") in ("CS", "ADRC"): act_cik.setdefault(x["cik"], x["ticker"])
syms = [s.strip() for s in open(sys.argv[1]) if s.strip()]
with open(sys.argv[2], "w") as fh:
    fh.write("symbol\ttype_2022\tname_2022\tcik\tcomposite_figi\tshare_class_figi\tcurrent_by_figi\tcurrent_by_cik\tdelisted\tdelisted_types\n")
    for s in syms:
        asof = [x for x in get({"ticker": s, "date": "2022-03-31", "limit": 10}) if "_error" not in x]
        gone = [x for x in get({"ticker": s, "active": "false", "limit": 50}) if "_error" not in x]
        r = asof[0] if asof else (sorted(gone, key=lambda x: x.get("delisted_utc") or "")[-1] if gone else {})
        figis = [r.get("composite_figi"), r.get("share_class_figi")]
        cur_f = next((act_figi[f] for f in figis if f and f in act_figi), "")
        cur_c = act_cik.get(r.get("cik") or "", "")
        fh.write("\t".join([s, r.get("type") or "", (r.get("name") or "").replace("\t", " ")[:80], r.get("cik") or "", r.get("composite_figi") or "",
                            r.get("share_class_figi") or "", cur_f, cur_c, "|".join(sorted((x.get("delisted_utc") or "")[:10] for x in gone)),
                            "|".join(sorted({x.get("type") or "" for x in gone}))]) + "\n")
        fh.flush()
print("DONE", len(syms))
