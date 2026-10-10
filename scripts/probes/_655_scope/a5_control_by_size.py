"""#655 scope: how hard is G3's bar by theme size? Median random-basket p95 and median cohesion, 10 nights pooled."""
import statistics as st
from collections import defaultdict
from board import NIGHTS, STORED
p95 = defaultdict(list); coh = defaultdict(list); cohf = defaultdict(list); n = defaultdict(int); f = defaultdict(int)
for d in NIGHTS:
    for t in STORED[d]["g3"]["themes"]:
        if t["cohesion"] is None: continue
        k = min(t["size"], 6)
        p95[k].append(t["c1_p95"]); coh[k].append(t["cohesion"]); n[k] += 1
        if not t["pass_g3"]: f[k] += 1; cohf[k].append(t["cohesion"])
print("size | theme-nights | fail | median random p95 (the bar) | median cohesion all | median cohesion of fails")
for k in sorted(n):
    print(f"{k}{'+' if k==6 else ''} | {n[k]} | {f[k]} | {st.median(p95[k]):.3f} | {st.median(coh[k]):.3f} | {st.median(cohf[k]) if cohf[k] else float('nan'):.3f}")
