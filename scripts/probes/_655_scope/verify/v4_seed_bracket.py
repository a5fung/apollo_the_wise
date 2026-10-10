"""verify #655: bracket the seed approximation for (iv) (09-25 seed only = clean scores, vs 09-24+09-25) and size the
(i-b) cold-start: how many of (i-b)'s taken themes passed G3 at 3 members on a seed night (kept under the rule). $0."""
import re, sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collections import defaultdict
from datetime import date
from board import B, NIGHTS, STORED, board_at, g3
V = {d: {t["name"]: t for t in STORED[d]["g3"]["themes"]} for d in NIGHTS}
def coll(s): return re.sub(r"[^0-9a-z]", "", s.lower())
seed = {}
for d in [date(2026, 9, 24), date(2026, 9, 25)]:
    bd = sorted([r for r in board_at(d) if r["tickers"]], key=lambda t: coll(t["name"]))
    if not [x for x in B["scores"] if x <= d]: B["scores"][d] = B["scores"][min(B["scores"])]
    sz = {t["name"]: len(t["tickers"]) for t in bd}
    seed[d] = {x["name"]: {**x, "size": sz[x["name"]]} for x in g3(bd, d)["themes"]}
hist = defaultdict(list)
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]: hist[r["name"]].append((r["d"], len(r["tickers"]), r["stage"], r["rs_avg"]))
def rates(names, d):
    j = [V[d][n] for n in names if V[d][n]["cohesion"] is not None]
    return 100 * sum(bool(t["pass_g3"]) for t in j) / len(j), 100 * sum(V[d][n]["size"] < 3 for n in names) / len(names)
def iv(seeds):
    st = defaultdict(int); ret = {}; out = []
    for d, verd in [(d, seed[d]) for d in seeds] + [(d, V[d]) for d in NIGHTS]:
        for n, t in verd.items():
            if n in ret: continue
            st[n] = st[n] + 1 if (t["size"] <= 3 and t["cohesion"] is not None and not t["pass_g3"]) else 0
            if st[n] >= 3: ret[n] = d
        if d in V: out.append(rates([n for n in V[d] if n not in ret], d))
    g = [x[0] for x in out]; f = [x[1] for x in out]
    strong = sum(1 for n, d in ret.items() if (lambda r: r and r[2] == "Nascent" and (r[3] or 0) >= 80)(max([x for x in hist[n] if x[0] <= d], default=None)))
    return f"G3 {sum(x>=90 for x in g)}/10 ({min(g):.1f}-{max(g):.1f}) G4 {sum(x<=10 for x in f)}/10 taken {len(ret)} strong-early {strong}"
print("(iv) cold start      :", iv([]))
print("(iv) seed 09-25 only :", iv([date(2026, 9, 25)]))
print("(iv) seed 09-24+09-25:", iv([date(2026, 9, 24), date(2026, 9, 25)]))
# (i-b): taken set as in a3/a6 (in-window reads only)
def r4(n, d): return any(k >= 4 for dd, k, *_ in hist[n] if dd <= d)
t_ib = {}
for d in NIGHTS:
    for n in V[d]:
        if not (r4(n, d) or any(V[x].get(n, {}).get("size") == 3 and V[x][n]["pass_g3"] for x in NIGHTS if x <= d)): t_ib.setdefault(n, d)
pre = [n for n in t_ib if any(seed[s].get(n, {}).get("size") == 3 and seed[s][n]["pass_g3"] for s in seed)]
strong_pre = [n for n in pre if (lambda r: r[2] == "Nascent" and (r[3] or 0) >= 80)(max(x for x in hist[n] if x[0] <= t_ib[n]))]
print(f"(i-b) taken {len(t_ib)}; of them passed G3 at 3 members on a seed night (kept under the rule): {len(pre)}; strong-early among them {len(strong_pre)}")
print("   ", [n[:50] for n in pre])
