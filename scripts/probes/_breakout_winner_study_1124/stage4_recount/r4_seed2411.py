import numpy as np, pandas as pd, json
from datetime import date
import r4_common as C, r4_outcomes as OU
import v1_replay as R
from scripts.probes._cb_backtest import runner
W = pd.read_parquet(C.BIG / f"r4_events_postdrop{C.SUF}.parquet")
S = R.load_store("A"); Dd = S.D
guard, _ = C.load_guard(C.GUARD_A, "A")
def rate(sel, horizon):
    OU.HORIZON = horizon
    win = []
    for r in sel.itertuples():
        k = Dd.tid[r.ticker]; bars, cidx = runner.bars_for(Dd, k); a = int(Dd.start[k]); b = int(Dd.stop[k]); fac = S.raw_factor[a:b]
        lo, end, endf, reason = OU.forward_outcome(Dd, fac, cidx, bars, r.ci + 1, date.fromisoformat(r.E), "A", guard, r.ticker, r.level, r.oE, r.adr20)
        c = np.asarray(bars.c, float)[lo:end]; proxy = max(r.level, float(r.oE))
        win.append(bool(c.max() >= 1.5 * proxy))
    return np.array(win)
out = {}
for name, col in (("seed1124", "kept1124"), ("seed2411", "kept2411")):
    sel = W[(W[col]) & (W.era == "A") & (W.E <= "2020-12-31")]
    w = rate(sel, 60); yr = sel.E.str[:4].astype(int).to_numpy()
    out[name] = {"n": len(sel), "wins": int(w.sum()), "rate": float(w.mean()), "n_1719": int((yr <= 2019).sum()), "rate_1719": float(w[yr <= 2019].mean())}
    print(name, out[name])
sel = W[(W.kept1124) & (W.era == "A") & (W.E <= "2020-12-31")]
for h in (30, 90):
    w = rate(sel, h); out[f"h{h}"] = float(w.mean()); print("window", h, f"{w.mean():.4%}")
json.dump(out, open(C.OUTD / f"r4_seed2411{C.SUF}.json", "w"), indent=1)
