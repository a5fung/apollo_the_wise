import numpy as np
from datetime import date
import r4_common as C
import v1_replay as R
S = R.load_store("B"); D = S.D
cal = D.cal
nights = [ci for ci, d in enumerate(cal) if date(2022, 4, 1) <= d and ci + 1 < len(cal) and cal[ci + 1] <= date(2024, 10, 4)]
nset = np.zeros(len(cal), bool); nset[nights] = True
nr = [l.strip() for l in open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1c/notreturned_A1.txt") if l.strip()]   # cross-check only
nrset = set(nr)
tot = d2 = d757 = 0
for k, t in enumerate(D.tickers):
    f = R.ticker_facts(S, k); a, b = f["a"], f["b"]
    if b - a < 20: continue
    sel = nset[f["cidx"]] & np.isfinite(f["dv"]) & (f["dv"] >= 5e6)
    n = int(sel.sum()); tot += n
    if n and (S.raw_src[a:b] == 2).any():
        n2 = int((sel & (S.raw_src[a:b] == 2)).sum()); d2 += n2
        if t in nrset: d757 += n2
print(f"era-B pool-candidate name-nights (adjusted $5M floor, nights 2022-04-01..2024-10-03): {tot:,}; raw_src 2 any {d2:,} = {d2 / tot:.2%}; the 757 not-returned names {d757:,} = {d757 / tot:.2%}")
print("notreturned list size", len(nr), "all in store B:", all(t in D.tid for t in nr), "all raw_src 2:", all((S.raw_src[D.start[D.tid[t]]:D.stop[D.tid[t]]] == 2).all() for t in nr if t in D.tid))
