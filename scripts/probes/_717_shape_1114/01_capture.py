#!/usr/bin/env python3
"""#717 shape checks: the CAPTURE (2026-11-14; offline, $0, read-only, ERA A ONLY; research, no rule changed).

Captures ONCE the last W=80 daily bars (open/high/low/close, float32, NaN-padded on the left) ending on the watch night D
— never the breakout day's bar — for the three populations of `_717_reasons_1114/01_measure.py`, through THAT module's
loaders (imported, not rebuilt; only `reason_measures` is swapped for a bar-window recorder and the output paths repointed
to this folder so the previous card's captures are not overwritten):
  fixtures : scorecard_rows.tsv / high_rows.tsv (this folder; column `wid` -> row of fixtures_windows.npy)
  eraA     : every FIRE row of list_eraA_4pct.parquet (cb702_pre_v2 via P.setup(), calendar asserted < 2025; `cb702/` is
             NOT opened) -> /Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy (row order = df[df.fire].index)
Every definition is post-processing (03_score.py).

    python3 scripts/probes/_717_shape_1114/01_capture.py fixtures > .../01_fixtures.out
    python3 scripts/probes/_717_shape_1114/01_capture.py eraA     > .../01_eraA.out
"""
import importlib.util, os, sys, time
from datetime import date
from multiprocessing import get_context
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
spec = importlib.util.spec_from_file_location("m01", os.path.join(REPO, "scripts/probes/_717_reasons_1114/01_measure.py"))
M1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(M1)
W = 80
OUT_FIRES = "/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy"     # outside git
STASH = []


def window(bars, D):
    out = np.full((4, W), np.nan, np.float32)
    a = max(0, D - W + 1)
    for j, x in enumerate((bars.o, bars.h, bars.l, bars.c)):
        seg = np.asarray(x[a:D + 1], float)
        out[j, W - len(seg):] = seg
    return out


def recorder(bars, D, P, adr, level):
    STASH.append(window(bars, D))
    return {"wid": len(STASH) - 1, "base_len": D - P}


def stage_fixtures():
    M1.reason_measures = recorder
    M1.HERE = HERE                                   # scorecard_rows.tsv / high_rows.tsv land in THIS folder
    M1.stage_fixtures()
    np.save(os.path.join(HERE, "fixtures_windows.npy"), np.stack(STASH))
    print(f"fixtures windows: {len(STASH)} x 4 x {W} -> fixtures_windows.npy")


G = M1.G


def _work(tickers):                                  # the bar-matching loop of 01_measure._work, verbatim
    P, D, tid = G["P"], G["D"], G["tid"]
    out = []
    for t in tickers:
        g = G["groups"][t]
        cands = [P.runner.bars_for(D, k) for k in tid[t]]
        for i, ci, close in zip(g.index, g.ci, g.close):
            for bars, cidx in cands:
                hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                    out.append((i, window(bars, int(hit[0]))))
                    break
            else:
                out.append((i, np.full((4, W), np.nan, np.float32)))
    return out


def stage_eraA():
    assert not os.path.exists(OUT_FIRES), "captured once — delete by hand to rebuild"
    sp = importlib.util.spec_from_file_location("b", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/01_build.py"))
    B = importlib.util.module_from_spec(sp); sp.loader.exec_module(B)
    P = B.P
    df = pd.read_parquet(B.CAPTURE)
    f = df[df.fire]
    S, _ = P.setup(); D = S.D
    assert D.cal[-1] < date(2025, 1, 1), D.cal[-1]
    tid = {}
    for k, t in enumerate(D.tickers):
        tid.setdefault(t, []).append(k)
    G.update(P=P, D=D, tid=tid, f=f, groups={t: g for t, g in f.groupby("ticker")})
    ts = sorted(G["groups"]); t0 = time.time()
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(_work, [ts[i::32] for i in range(32)])
    d = {i: w for p in parts for i, w in p}
    assert len(d) == len(f)
    arr = np.stack([d[i] for i in f.index])
    np.save(OUT_FIRES, arr)
    print(f"era A fires: {len(arr):,} windows in {time.time() - t0:.0f}s; unmatched {int(np.isnan(arr[:, 3, -1]).sum())}; "
          f"close(D) == capture close: {int((np.abs(arr[:, 3, -1] - f.close.to_numpy()) < 1e-4 * f.close.to_numpy()).sum()):,}; calendar {D.cal[0]} .. {D.cal[-1]} -> {OUT_FIRES}")


if __name__ == "__main__":
    {"fixtures": stage_fixtures, "eraA": stage_eraA}[sys.argv[1]]()
