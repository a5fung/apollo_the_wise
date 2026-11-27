import numpy as np
from datetime import date
import r4_common as C
import v1_replay as R
S = R.load_store("B"); D = S.D; cal = D.cal
nights = [ci for ci, d in enumerate(cal) if date(2022, 4, 1) <= d and ci + 1 < len(cal) and cal[ci + 1] <= date(2024, 10, 4)]
nset = np.zeros(len(cal), bool); nset[nights] = True
nr = set(l.strip() for l in open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1c/notreturned_A1.txt") if l.strip())
v1 = {"tot": 0, "d757": 0, "dall": 0}; v2 = dict(v1); v3 = dict(v1)
for k, t in enumerate(D.tickers):
    a, b = int(D.start[k]), int(D.stop[k]); ci = D.ci[a:b].astype(np.int64); c = D.c[a:b]; v = D.v[a:b]
    on = nset[ci]
    if not on.any(): continue
    cv = c * v
    # (a) single-day
    sel = on & (cv >= 5e6)
    # (b) median of the available bars up to 20 (min_periods 1)
    med = np.array([np.median(cv[max(0, i - 19):i + 1]) for i in np.flatnonzero(on)]) if on.any() else np.array([])
    selb = np.zeros(len(c), bool); selb[np.flatnonzero(on)] = med >= 5e6
    d2 = S.raw_src[a:b] == 2
    for d, s in ((v1, sel), (v2, selb)):
        d["tot"] += int(s.sum()); d["dall"] += int((s & d2).sum()); d["d757"] += int((s & d2).sum()) if t in nr else 0
print("single-day c*v>=5M:", v1, f"{v1['d757'] / v1['tot']:.2%}", f"{v1['dall'] / v1['tot']:.2%}")
print("median of available (min_periods=1):", v2, f"{v2['d757'] / v2['tot']:.2%}", f"{v2['dall'] / v2['tot']:.2%}")
