#!/usr/bin/env python3
"""#717 slot ranking: capture two raw per-fire measures from bars <= D (era A only, cb702_pre_v2 via P.setup; cb702/ never opened):
sma200_ratio = close(D) / SMA of the last 200 closes (all that exist if >= 120, else NaN); ret126 = close(D)/close(D-126)-1 (the earliest bar if 120..126 exist, else NaN).
Row order = df[df.fire].index of list_eraA_4pct.parquet. Output outside git."""
import importlib.util, os, time
from datetime import date
from multiprocessing import get_context
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = "/Users/alvinfung/apollo_data/bv1_rank_1114/fires_trend.parquet"
sp = importlib.util.spec_from_file_location("b", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/01_build.py"))
B = importlib.util.module_from_spec(sp); sp.loader.exec_module(B)
G = {}
def meas(c):
    n = len(c)
    if n < 120: return np.nan, np.nan
    s = c[-200:].mean(); r = c[-1] / (c[-127] if n >= 127 else c[0]) - 1
    return float(c[-1] / s), float(r)
def work(tickers):
    P, D, tid = G["P"], G["D"], G["tid"]; out = []
    for t in tickers:
        g = G["groups"][t]; cands = [P.runner.bars_for(D, k) for k in tid[t]]
        for i, ci, close in zip(g.index, g.ci, g.close):
            for bars, cidx in cands:
                hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                    out.append((i, *meas(np.asarray(bars.c[:int(hit[0]) + 1], float)))); break
            else: out.append((i, np.nan, np.nan))
    return out
if __name__ == "__main__":
    P = B.P; df = pd.read_parquet(B.CAPTURE); f = df[df.fire]
    S, _ = P.setup(); D = S.D; assert D.cal[-1] < date(2025, 1, 1)
    tid = {}
    for k, t in enumerate(D.tickers): tid.setdefault(t, []).append(k)
    G.update(P=P, D=D, tid=tid, groups={t: g for t, g in f.groupby("ticker")})
    ts = sorted(G["groups"]); t0 = time.time()
    with get_context("fork").Pool(8) as pool: parts = pool.map(work, [ts[i::32] for i in range(32)])
    d = {i: (a, b) for p in parts for i, a, b in p}; assert len(d) == len(f)
    out = pd.DataFrame([d[i] for i in f.index], index=f.index, columns=["sma200_ratio", "ret126"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True); out.to_parquet(OUT)
    print(f"{len(out):,} fires in {time.time()-t0:.0f}s; NaN sma200 {out.sma200_ratio.isna().sum()}, ret126 {out.ret126.isna().sum()}; calendar {D.cal[0]}..{D.cal[-1]}")
