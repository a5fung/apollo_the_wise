import sys, json, csv, statistics, asyncio, importlib.util
from unittest.mock import AsyncMock, MagicMock
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
spec = importlib.util.spec_from_file_location("old", "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_resilience_test.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
db = old.db
D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_forward_1128/"
rows = []
for r in csv.reader(open(D + "closes.out")):
    if len(r) != 3 or r[0] == "ticker": continue
    rows.append({"ticker": r[0], "trade_date": old._parse_date(r[1]), "close": float(r[2])})
print("closes", len(rows))
conn = old._RealPullConn(rows)
cm = MagicMock(); cm.__aenter__ = AsyncMock(return_value=conn); cm.__aexit__ = AsyncMock(return_value=None)
pool = MagicMock(); pool.acquire = MagicMock(return_value=cm)
db.get_pool = AsyncMock(return_value=pool)
ents = json.load(open(D + "entrants_fwd.json"))
res, nocov = [], []
for e in ents:
    pt = asyncio.run(db.get_down_day_resilience(old._parse_date(e["as_of_date"]), tickers=e["tickers"], lookback=20))
    if not pt: nocov.append(e["canonical_id"] + " " + e["week_start"]); continue
    res.append({**e, "cohort_resilience": statistics.median(r["resilience"] for r in pt)})
print("scored", len(res), "nocov", len(nocov), nocov)
json.dump(res, open(D + "scored_fwd.json", "w"), indent=1, default=str)
CUT = 0.005
def split(sub):
    sc = [r for r in sub if r["holds_next"] is not None]
    hi = [r for r in sc if r["cohort_resilience"] > CUT]; lo = [r for r in sc if r["cohort_resilience"] <= CUT]
    f = lambda a: (len(a), sum(r["holds_next"] for r in a))
    return f(hi), f(lo)
out = {}
out["all"] = split(res)
for e in ("pre_10-05", "10-05..10-12", "post_10-12"):
    out[e] = split([r for r in res if r["era"] == e])
sc = [r for r in res if r["holds_next"] is not None]
out["median_fwd"] = statistics.median(r["cohort_resilience"] for r in sc)
out["scorable"] = len(sc); out["hold"] = sum(r["holds_next"] for r in sc)
# weekly scorable rate
from collections import Counter
out["wk_scorable"] = sorted(Counter(r["week_start"] for r in sc).items())
json.dump(out, open(D + "summary.json", "w"), indent=1)
for k, v in out.items(): print(k, v)
