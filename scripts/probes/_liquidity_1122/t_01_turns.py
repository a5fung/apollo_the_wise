"""t_01: OUTCOME-BLIND. Rebuild every turn list of §13.1 (1) from build_r2/composite.csv and legs_votes.csv only, and check the counts frozen in the doc.
No price, VIX, breadth, EP or breakout file is opened. Writes build_t/turns_*.csv."""
import pandas as pd, numpy as np, os, hashlib, re
from t_00_lib import *
os.makedirs("build_t", exist_ok=True)
# sha check of the frozen section
L = open("../../../docs/analysis/liquidity_composite_prereg_2026-11-22.md", encoding="utf-8").read().split("\n")
a = [i for i, l in enumerate(L) if l.startswith("### 13.1")][0]; b = [i for i, l in enumerate(L) if l.startswith("FROZEN 2026-11-22 before any outcome")][0]
h = hashlib.sha256(("\n".join(L[a:b]) + "\n").encode()).hexdigest(); want = L[b].split("sha256 of §13.1 text: ")[1].strip()
print(f"§13.1 sha256 (heading line through the last bullet, trailing newline): {h}\n  doc line: {want} -> {'MATCH' if h == want else 'MISMATCH'}"); assert h == want
comp = pd.read_csv(f"{O}/composite.csv", index_col=0, parse_dates=True); V = pd.read_csv(f"{O}/legs_votes.csv", index_col=0, parse_dates=True)
assert comp.index.max() <= CUT and V.index.max() <= CUT
grid = V.index; assert len(grid) == 2264; S = comp["S"].reindex(grid)
vs, ve = grid.get_loc(VS), grid.get_loc(VE); n = ve - vs + 1; assert n == 1937
print(f"grid {grid[0].date()} -> {grid[-1].date()} n={len(grid)}; S first {S.first_valid_index().date()}; window n={n}")
def report(nm, s, exp=None):
    t, c, first = turns(s); w = [(i, d) for i, d in t if vs <= i <= ve]
    e = [i for i, d in w if d < 0]; g = [i for i, d in w if d > 0]
    h = lambda x: (sum(grid[i] <= H1END for i in x), sum(grid[i] >= H2START for i in x))
    allg = np.diff([i for i, d in w]); msg = f"{nm}: easing {len(e)} {h(e)}, tightening {len(g)} {h(g)}"
    if len(allg): msg += f"; gaps n={len(allg)} min {allg.min()} median {np.median(allg):g}, <=20: {(allg<=20).sum()}, <=60: {(allg<=60).sum()}"
    for lab, x in (("easing", e), ("tightening", g)):
        d = np.diff(x)
        if len(d): msg += f"; {lab}-to-{lab} gaps n={len(d)} <43: {(d<43).sum()} <21: {(d<21).sum()} min {d.min()}"
    if exp is not None: msg += f"  | doc {exp} -> {'MATCH' if (len(e), len(g)) == exp else 'MISMATCH'}"
    print(msg); pd.DataFrame({"date": [grid[i] for i, d in t], "pos": [i for i, d in t], "dir": ["tightening" if d > 0 else "easing" for i, d in t], "in_window": [vs <= i <= ve for i, d in t]}).to_csv(f"build_t/turns_{re.sub('[^A-Za-z0-9]+', '_', nm)}.csv", index=False)
    return w
prim = report("PRIMARY", sign_series(ma(S, 20) - ma(S, 50)), (24, 24))
alt = report("ALTERNATE", sign_series(S - ma(S, 20)), (38, 37))
print("primary turn dates:", ", ".join(f"{grid[i].date()}{'E' if d < 0 else 'T'}" for i, d in prim))
DOC = dict(M1=(20, 21), F1=(24, 24), F2=(14, 13), R1=(21, 20), D1=(19, 18), K1=(20, 21), C3=(17, 18), R2=(15, 14), K5=(19, 18), M2=(20, 21))
for k in KEPT: report(f"leg {k}", sign_series(V[k]), DOC[k])
F = comp["Fed and money"].reindex(grid)
report("FedChannel sign of score", sign_series(F), (25, 24))
report("FedChannel MA20 vs MA50 of score", sign_series(ma(F, 20) - ma(F, 50)), (25, 24))
