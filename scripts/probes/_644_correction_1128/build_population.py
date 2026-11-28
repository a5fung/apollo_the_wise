"""#644 correction test step 1. Run: cd /Users/alvinfung/portfolio-app2 && python3 <this>"""
import json, sys
from datetime import date
sys.path.insert(0, "/Users/alvinfung/portfolio-app2")
import theme_data
D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_correction_1128/"
WEEK = "2026-11-16"
def _t(c):
    if isinstance(c, (list, tuple, set, frozenset)): return sorted({str(t).strip().upper() for t in c if str(t).strip()})
    if isinstance(c, str): return sorted({t.strip().upper() for t in c.replace(";", ",").split(",") if t.strip()})
    return []
g = theme_data.get_canonical_weekly_grid(weeks=200)
g = g[g["week_start"].astype(str).str[:10] == WEEK]
rows = []
for _, r in g.iterrows():
    t = _t(r["tickers"])
    rows.append({"canonical_id": r["canonical_id"], "week_rank": None if r["week_rank"] != r["week_rank"] else int(r["week_rank"]),
                 "as_of_date": str(r["as_of_date"]), "tickers": t, "n_tickers": len(t)})
print("grid rows in week", len(rows))
pop = [r for r in rows if r["n_tickers"] >= 3]
print("themes with >=3 tickers:", len(pop))
json.dump(pop, open(D + "population.json", "w"), indent=1)
tk = sorted({t for r in pop for t in r["tickers"]} | {"SPY"})
print("tickers", len(tk))
with open(D + "closes.sql", "w") as f:
    f.write("SET default_transaction_read_only = on;\n")
    f.write("SELECT ticker, trade_date, close FROM mi_daily_closes\nWHERE ticker IN (" + ",".join("'%s'" % t.replace("'", "''") for t in tk) + ")\n  AND trade_date BETWEEN '2026-08-15' AND '2026-11-27'\nORDER BY ticker, trade_date;\n")
