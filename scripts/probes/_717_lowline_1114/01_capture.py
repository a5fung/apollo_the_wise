#!/usr/bin/env python3
"""#717 lower-line check: the CAPTURE (2026-11-14; offline, $0, read-only, ERA A ONLY; research, no rule changed).
For every FIRE row of list_eraA_4pct.parquet (row order = df[df.fire].index): the last 200 daily bars (o/h/l/c, NaN-padded on
the left) ending on the list night D, from the era-A store (P.setup(), calendar asserted < 2025; `cb702/` is never opened),
matched exactly as _717_shape_1114/01_capture.py / _717_reasons_1114/03_sheet.py do (bars_for, ci + close). The measures
(ll.measure: V3, lower-line slope over 30 sessions, bar count) are computed in float64 inside the workers.
  -> /Users/alvinfung/apollo_data/bv1_lowline_1114/fires_lowline.parquet  (V3, LS30, nbars, matched; index = fire index)
  -> /Users/alvinfung/apollo_data/bv1_lowline_1114/fires_windows200.npy   (float32 o/h/l/c x 200, same row order)

    python3 scripts/probes/_717_lowline_1114/01_capture.py > scripts/probes/_717_lowline_1114/01_capture.out
"""
import importlib.util, os, sys, time
from datetime import date
from multiprocessing import get_context
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE); import ll  # noqa: E402
OUTD = "/Users/alvinfung/apollo_data/bv1_lowline_1114"
OUT_M, OUT_W = os.path.join(OUTD, "fires_lowline.parquet"), os.path.join(OUTD, "fires_windows200.npy")
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
W = 200
G = {}


def window(bars, D):
    out = np.full((4, W), np.nan, np.float64)
    a = max(0, D - W + 1)
    for j, x in enumerate((bars.o, bars.h, bars.l, bars.c)):
        seg = np.asarray(x[a:D + 1], float); out[j, W - len(seg):] = seg
    return out


def _work(tickers):
    P, D, tid = G["P"], G["D"], G["tid"]
    idx, wins, matched = [], [], []
    for t in tickers:
        g = G["groups"][t]
        cands = [P.runner.bars_for(D, k) for k in tid[t]]
        for i, ci, close in zip(g.index, g.ci, g.close):
            for bars, cidx in cands:
                hit = np.flatnonzero(np.asarray(cidx) == ci)
                if len(hit) and abs(float(bars.c[hit[0]]) - close) < 1e-6 * max(1.0, close):
                    wins.append(window(bars, int(hit[0]))); matched.append(1); break
            else:
                wins.append(np.full((4, W), np.nan)); matched.append(0)
            idx.append(i)
    WW = np.stack(wins) if wins else np.zeros((0, 4, W))
    V3, LS, nb = ll.measure(WW)
    return idx, WW.astype(np.float32), V3, LS, nb, matched


if __name__ == "__main__":
    assert not os.path.exists(OUT_M), "captured once — delete by hand to rebuild"
    spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py"))
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); P = M.P
    df = pd.read_parquet(CAP); f = df[df.fire]
    S, _ = P.setup(); D = S.D
    assert D.cal[-1] < date(2025, 1, 1), D.cal[-1]
    tid = {}
    for k, t in enumerate(D.tickers):
        tid.setdefault(t, []).append(k)
    G.update(P=P, D=D, tid=tid, groups={t: g for t, g in f.groupby("ticker")})
    ts = sorted(G["groups"]); t0 = time.time()
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(_work, [ts[i::64] for i in range(64)])
    idx = np.concatenate([np.asarray(p[0]) for p in parts])
    pos = pd.Series(np.arange(len(idx)), index=idx)
    assert len(pos) == len(f) and pos.index.is_unique
    order = pos.loc[f.index].to_numpy()
    WW = np.concatenate([p[1] for p in parts])[order]
    m = pd.DataFrame({k: np.concatenate([np.asarray(p[j], float) for p in parts])[order] for j, k in ((2, "V3"), (3, "LS30"), (4, "nbars"), (5, "matched"))},
                     index=f.index)
    assert (m.index == f.index).all()
    m.to_parquet(OUT_M); np.save(OUT_W, WW)
    print(f"era A fires: {len(m):,} windows in {time.time() - t0:.0f}s; unmatched {int((m.matched == 0).sum())}; "
          f"close(D) == capture close: {int((np.abs(WW[:, 3, -1] - f.close.to_numpy()) < 1e-4 * f.close.to_numpy()).sum()):,}; "
          f">= 189 bars: {int((m.nbars >= 189).sum()):,}; flagged (V3 > 0.212 and lower line flat/falling): {int(ll.flag(m.V3, m.LS30, m.nbars).sum()):,}; "
          f"calendar {D.cal[0]} .. {D.cal[-1]} -> {OUT_M}, {OUT_W}")
