#!/usr/bin/env python3
"""The scorecard fixture for the Saturday build (advisor review 11-02): Qullamaggie's 269 dated breakout buys, self-contained,
so the build's test never depends on the 4.2M-row table in apollo_data or the era-B sealed copy in a session scratchpad.
Writes tests/fixtures/qm_breakout_scorecard/: buys.tsv (eid, sym, ticker, D, E, era, big winner, rs_best and raw close at D —
the two inputs that need the universe or the raw store — his label, and the research result on the rebuilt rules) and
bars.psv.gz (each buy's split-adjusted daily bars from 300 sessions before D through E). Bars <= E only; nothing 2025+."""
import csv, gzip, json, os, runpy, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101"); sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R  # noqa
from scripts.probes._cb_backtest import runner  # noqa
OUT = "/Users/alvinfung/apollo_the_wise/tests/fixtures/qm_breakout_scorecard"
os.makedirs(OUT, exist_ok=True)
g = runpy.run_path(f"{HERE}/18_sma50_rule.py", run_name="lib")
F, Q, NEW = g["F"], g["Q"], g["NEW"]
# his labels on Qullamaggie's buys (latest label wins), from the label files of the day
lab = {}
for f, sc, lc in (("24_move70_labels.tsv", "sym", "his"), ("31_tight3_labels.tsv", "sym", "his")):
    for r in csv.DictReader(open(f"{HERE}/{f}"), delimiter="\t"):
        lab[(r[sc], r["E"])] = r[lc]
for (s, e), v in {("EW", "2019-08-16"): "good", ("LMT", "2022-04-05"): "good", ("LMT", "2022-04-06"): "good", ("LRN", "2020-08-05"): "good",
                  ("YPF", "2019-04-17"): "no", ("MRNA", "2021-11-29"): "no, maybe a different criteria", ("W", "2020-04-07"): "no, maybe EP",
                  ("DOCU", "2020-12-04"): "no", ("DOCU", "2020-12-15"): "no", ("SQM", "2021-09-10"): "no", ("HFC", "2018-07-31"): "a bit late buy",
                  ("CODX", "2020-04-06"): "good", ("AVLR", "2020-07-29"): "okish but likely no", ("AMC", "2021-02-22"): "ok",
                  ("DKNG", "2021-02-26"): "decent", ("BNTX", "2021-09-23"): "good", ("LAC", "2021-09-30"): "okish", ("MARA", "2021-11-30"): "good",
                  ("TSLA", "2022-04-21"): "ok", ("SE", "2020-09-14"): "ok (no on the EMA21 sheet)"}.items():
    lab.setdefault((s, e), v)
rows, bars = [], []
for era in ("A", "B"):
    S = R.load_store(era); D = S.D
    for r in Q[Q.era == era].itertuples():
        k = D.tid[r.ticker]; b, ci = runner.bars_for(D, k)
        dates = [x.isoformat() for x in b.dates]; i = dates.index(r.D)
        a0, a1 = max(0, i - 300), min(len(dates) - 1, i + 1)
        fac = S.raw_factor[int(D.start[k]):int(D.stop[k])]
        for j in range(a0, a1 + 1):
            bars.append((r.eid, r.ticker, dates[j], b.o[j], b.h[j], b.l[j], b.c[j], b.v[j]))
        row = F.loc[int(r.row)]
        rows.append({"eid": r.eid, "sym": r.sym, "ticker": r.ticker, "D": r.D, "E": r.E, "era": era, "big_winner": int(r.big),
                     "rs_best": float(row.rs_best), "raw_close_D": float(b.c[i] * fac[i]), "his_label": lab.get((r.sym, r.E), ""),
                     "on_rebuilt_list": int(bool(NEW[int(r.row)]))})
    del S, D
pd.DataFrame(rows).sort_values(["E", "sym"]).to_csv(f"{OUT}/buys.tsv", sep="\t", index=False)
with gzip.open(f"{OUT}/bars.psv.gz", "wt") as f:
    f.write("eid|ticker|date|o|h|l|c|v\n")
    for t in bars:
        f.write("|".join([str(t[0]), t[1], t[2]] + [repr(float(x)) for x in t[3:]]) + "\n")
B = pd.DataFrame(rows)
print(f"buys {len(B)} | on the rebuilt list {B.on_rebuilt_list.sum()} | big {B.big_winner.sum()} | labelled {int((B.his_label != '').sum())} | bars {len(bars)}")
