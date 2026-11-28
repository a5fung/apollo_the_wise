"""#644 forward step 1 — forward entrant population. Adapted from
portfolio-app2/_644_entrants.py (same definition: entrant = board[w]-board[prev],
board = week_rank<=30, holds_next = cid in board[next]). Forward = week_start >= 2026-09-14
(frozen rule: entrants on/after 09-14). Run from portfolio-app2 dir:
  cd /Users/alvinfung/portfolio-app2 && python3 <this file>"""
import json, sys
from datetime import date
sys.path.insert(0, "/Users/alvinfung/portfolio-app2")
import theme_data
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_644_forward_1128/entrants_fwd.json"
BOARD = 30
FWD_START = date(2026, 9, 14)

def _tickers(cell):
    if isinstance(cell, (list, tuple, set, frozenset)):
        return sorted(str(t).strip().upper() for t in cell if str(t).strip())
    if isinstance(cell, str):
        return sorted(t.strip().upper() for t in cell.replace(";", ",").split(",") if t.strip())
    return []

def era(ws):
    s = str(ws)
    if s < "2026-10-05": return "pre_10-05"
    if s <= "2026-10-12": return "10-05..10-12"
    return "post_10-12"

g = theme_data.get_canonical_weekly_grid(weeks=200)
g = g[g["week_rank"].notna()]
weeks = sorted(g["week_start"].unique())
board, baskets, as_of = {}, {}, {}
for w in weeks:
    wk = g[g["week_start"] == w]
    board[w] = set(wk[wk["week_rank"] <= BOARD]["canonical_id"])
    baskets[w] = {r["canonical_id"]: _tickers(r["tickers"]) for _, r in wk.iterrows()}
    as_of[w] = {r["canonical_id"]: r["as_of_date"] for _, r in wk.iterrows()}
print("weeks:", [str(w) for w in weeks][-14:])
rows = []
for i, w in enumerate(weeks):
    if w < FWD_START: continue
    prev = weeks[i-1]; nxt = weeks[i+1] if i+1 < len(weeks) else None
    for cid in sorted(board[w] - board[prev]):
        t = baskets[w].get(cid, [])
        rows.append({"canonical_id": cid, "week_start": str(w), "as_of_date": str(as_of[w].get(cid)),
                     "tickers": t, "n_tickers": len(t),
                     "holds_next": (cid in board[nxt]) if nxt is not None else None,
                     "era": era(w)})
json.dump(rows, open(OUT, "w"), indent=1, default=str)
sc = [r for r in rows if r["holds_next"] is not None]
print("forward entrants", len(rows), "scorable", len(sc), "hold", sum(r["holds_next"] for r in sc))
for e in ("pre_10-05", "10-05..10-12", "post_10-12"):
    a = [r for r in rows if r["era"] == e]; b = [r for r in a if r["holds_next"] is not None]
    print(e, "entrants", len(a), "scorable", len(b))
from collections import Counter
print(sorted(Counter(r["week_start"] for r in rows).items()))
print("as_of min/max", min(r["as_of_date"] for r in rows), max(r["as_of_date"] for r in rows))
print("empty baskets", sum(1 for r in rows if not r["tickers"]))
print("tickers", len({t for r in rows for t in r["tickers"]}))
