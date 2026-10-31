"""#714 POST-HOC descriptive (labelled): the F1 gap by ADV$ stratum, pooled vs stored-float era, so the +11 pp (stored era) vs -2.4 pp (pooled)
difference can be read. No verdict word; nothing here changes a registered result."""
import sys, os, io, contextlib, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location("s2", os.path.join(HERE, "s2_read.py"))
s2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s2)
with contextlib.redirect_stdout(io.StringIO()):
    S, B, popB, labun = s2.step0_1()
    popB, ba = s2.step1(S, B, popB)
    S["popB"] = popB
    frames = s2.build_frames(popB, S)
popB = s2.attach_outcomes(B, popB)
rung_names = {0: "<$50M", 1: "$50-100M", 2: "$100-250M", 3: "$250-500M", 4: ">=$500M"}
for key in ("F1", "F1_stored"):
    fr = frames[key]
    d = popB.loc[fr.idx]
    keep = d.runner.notna().to_numpy()
    y = d.runner.to_numpy()[keep].astype(int); g = fr.g[keep]; s = fr.strata[keep]
    print(f"\n{fr.name}: low float (<50M) vs not, runner rate by ADV$ stratum (merged rung index -> name)")
    for k in sorted(set(s.tolist())):
        m = s == k
        n1, n0 = int((g[m] == 1).sum()), int((g[m] == 0).sum())
        r1 = int(y[m & (g == 1)].sum()); r0 = int(y[m & (g == 0)].sum())
        rd = (r1 / n1 - r0 / n0) if n1 and n0 else np.nan
        print(f"  {rung_names[k]:>10s}: low-float {r1}/{n1} = {100*r1/max(n1,1):.1f}%  vs rest {r0}/{n0} = {100*r0/max(n0,1):.1f}%  gap {rd*100 if np.isfinite(rd) else float('nan'):+.1f} pp  weight {n1*n0/(n1+n0) if n1 and n0 else 0:.1f}")
# the same rows in B3: pooled-source split
d = popB.loc[frames["F1"].idx]
b3 = d[d.block == "B3"]
print("\nB3 rows in the pooled frame by float source:", dict(b3.float_src.value_counts()))
print("runner rate in B3 rows by source (runners/rows):", {k: (int(v.runner.sum()), int(v.runner.notna().sum())) for k, v in b3.groupby("float_src")})
for blk in ("B1", "B2", "B3"):
    dd = d[d.block == blk]
    low = ((dd.float_val > 0) & (dd.float_val < 50e6))
    print(f"{blk}: low-float rows {int(low.sum())} of {len(dd)} ({100*low.mean():.0f}%); runner rate overall {100*dd.runner.mean():.1f}%")
