#!/usr/bin/env python3
"""Stage 0, capture once: (a) per list row (the rebuilt NEW list, both eras) the bar features the era-A scripts 23/32/36
computed — the 6-month move, the last-10-close spread, the daily buy test pieces — from the era's own daily store
(era A: cb702_pre_v2, the file _chartlib reads; era B: the sealed < 2025 copy via v1_replay.load_store("B")); (b) for each
of Qullamaggie's 269 buys the daily facts the intraday replay needs (5-day high to D, 10/50-session average volume to D,
the E bar). Writes stage0/s0_rowfeat.parquet and stage0/s0_buyfacts.tsv. No returns; nothing dated 2025+ is read."""
import os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import s0_lib as L  # noqa  (sets BV1_SCRATCH + sys.path before v1_replay)
import v1_replay as R  # noqa
from scripts.probes._cb_backtest import runner  # noqa

g = L.load()
F, Q, NEW, eraB = g["F"], g["Q"], g["NEW"], g["eraB"]
out_rows, out_buys = [], []
for era in "AB":
    t0 = time.time()
    if era == "A":
        D = runner.load_daily(R.PRE / "daily_closes_all.csv.gz")
    else:
        D = R.load_store("B").D
    assert D.cal[-1] < R.SEAL, D.cal[-1]
    m = NEW & (eraB if era == "B" else ~eraB)
    out_rows.append(L.bar_features(D, runner, F, m).assign(era=era))
    qq = Q[(Q.D >= L.ERA_B_D_FIRST) if era == "B" else (Q.D < L.ERA_B_D_FIRST)]
    for r in qq.itertuples():
        b, _ = runner.bars_for(D, D.tid[r.ticker])
        dates = [d.isoformat() for d in b.dates]
        Di = dates.index(r.D)
        h, l, v = np.asarray(b.h, float), np.asarray(b.l, float), np.asarray(b.v, float)
        e_ok = Di + 1 < len(dates) and dates[Di + 1] == r.E
        out_buys.append({"eid": r.eid, "sym": r.sym, "ticker": r.ticker, "D": r.D, "E": r.E, "era": era, "big": r.big,
                         "row": r.row, "on_list": bool(NEW[r.row]), "adr20": F.adr20[r.row], "level_v1": F.level[r.row],
                         "level5": float(h[Di - 4:Di + 1].max()), "vol10": float(v[Di - 9:Di + 1].mean()),
                         "vol50": float(v[Di - 49:Di + 1].mean()), "E_next_bar": e_ok,
                         "E_h": float(h[Di + 1]) if e_ok else np.nan, "E_l": float(l[Di + 1]) if e_ok else np.nan,
                         "E_v": float(v[Di + 1]) if e_ok else np.nan})
    print(f"era {era}: store loaded + features in {time.time() - t0:.0f}s; list rows {int(m.sum()):,}", flush=True)
    del D
rf = pd.concat(out_rows)
rf.to_parquet(f"{HERE}/s0_rowfeat.parquet")
pd.DataFrame(out_buys).to_csv(f"{HERE}/s0_buyfacts.tsv", sep="\t", index=False)
print(f"wrote s0_rowfeat.parquet ({len(rf):,} rows) and s0_buyfacts.tsv ({len(out_buys)} buys)")
