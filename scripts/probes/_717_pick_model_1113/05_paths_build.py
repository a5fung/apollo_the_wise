#!/usr/bin/env python3
"""#717 template — the candidate PATHS capture (2026-11-13; offline, $0, read-only, ERA A ONLY; registration: Part 2 of
docs/analysis/cb_pick_model_2026-11-13.md §T2). For every FIRE row of the 01 capture: the 90 closes ending the list
night D (bars <= D only; NaN where the name has fewer), raw — the normalising is done by the reader. Bars:
cb702_pre_v2 (`P.setup()` asserts the calendar ends before 2025). No Qullamaggie label is read.

    python3 scripts/probes/_717_pick_model_1113/05_paths_build.py
"""
import importlib.util, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b", os.path.join(HERE, "01_build.py"))
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
P = B.P
OUT = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/fire_paths90.npz"       # captured ONCE, outside git
WMAX = 90
assert not os.path.exists(OUT), "captured once — delete by hand to rebuild"
df = pd.read_parquet(B.CAPTURE)
f = df[df.fire]
S, _ = P.setup(); D = S.D
tid = {}
for k, t in enumerate(D.tickers):
    tid.setdefault(t, []).append(k)
paths = np.full((len(f), WMAX), np.nan, dtype=np.float32)
pos = {i: n for n, i in enumerate(f.index)}
miss = 0
for t, g in f.groupby("ticker"):
    cands = [(P.runner.bars_for(D, k)) for k in tid[t]]
    for i, ci, close in zip(g.index, g.ci, g.close):
        for bars, cidx in cands:
            hit = np.flatnonzero(np.asarray(cidx) == ci)
            if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                Di = int(hit[0]); c = np.asarray(bars.c[max(0, Di - WMAX + 1):Di + 1], float)
                paths[pos[i], WMAX - len(c):] = c
                break
        else:
            miss += 1
np.savez_compressed(OUT, idx=f.index.to_numpy(), paths=paths)
print(f"paths: {len(f):,} fire rows, {miss} unmatched, rows with fewer than 90 closes {int(np.isnan(paths[:, 0]).sum()):,} -> {OUT}")
