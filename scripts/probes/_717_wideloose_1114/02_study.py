#!/usr/bin/env python3
"""#717 wide-and-loose: which measure puts his wide-loose rejects at the extreme (2026-11-14; graded charts ONLY — no
Qullamaggie buy is scored here). IN-SAMPLE: 8 wide-loose rejects vs 14 ok/good.
AUC = chance a wide-loose reject scores higher than an ok/good chart (1.00 = perfect). `ok>=min3` = how many of the 14
ok/good charts score at or above the LEAST extreme of TDOC / MELI / RRC (0 = a line there keeps every ok/good chart).
    python3 scripts/probes/_717_wideloose_1114/02_study.py > scripts/probes/_717_wideloose_1114/02_study.out
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import wl
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
WL = ["TDOC", "MELI", "RRC", "TWTR", "SWAV", "CDE", "DVAX", "THC"]; DEF = ["TDOC", "MELI", "RRC"]
gr = pd.read_csv(os.path.join(HERE, "graded_rows.tsv"), sep="\t")
m = wl.measures(np.load(os.path.join(HERE, "graded_windows200.npy"))[gr.wid.to_numpy()])
gr["grp"] = np.where(gr.ticker.isin(WL), "wide-loose", np.where(gr.grade.isin(["ok", "good"]), "ok/good", np.where(gr.grade == "conditional", "maybe", "other no")))
assert (gr.grp == "wide-loose").sum() == 8 and (gr.grp == "ok/good").sum() == 14 and (gr[gr.ticker.isin(WL)].grade == "no").all()
a, b = (gr.grp == "wide-loose").to_numpy(), (gr.grp == "ok/good").to_numpy()
rows = []
for k in m.columns:
    x = m[k].to_numpy()
    auc = np.mean([(i > j) + 0.5 * (i == j) for i in x[a] for j in x[b]])
    lo3 = x[gr.ticker.isin(DEF).to_numpy()].min()
    rows.append(dict(measure=k, auc=auc, wl_med=np.median(x[a]), ok_med=np.median(x[b]), min3=lo3, ok_ge_min3=int((x[b] >= lo3).sum()),
                     maybe_ge=int((x[(gr.grp == "maybe").to_numpy()] >= lo3).sum()), otherno_ge=int((x[(gr.grp == "other no").to_numpy()] >= lo3).sum()),
                     wl_ge=int((x[a] >= lo3).sum())))
res = pd.DataFrame(rows).sort_values(["ok_ge_min3", "auc"], ascending=[True, False])
print(res.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
d3 = gr.ticker.isin(DEF).to_numpy()
WIDE_MIN, CHOP_MIN = float(m.box20_chart[d3].min()), float(m.churn20_chart[d3].min())
m["wl_score"] = wl.score(m, WIDE_MIN, CHOP_MIN)
print(f"\nCHOSEN: wide = box20_chart, chop = churn20_chart; the line = the least of TDOC/MELI/RRC on each: WIDE_MIN {WIDE_MIN:.4f} ({gr.ticker[d3].iloc[int(np.argmin(m.box20_chart[d3]))]}), CHOP_MIN {CHOP_MIN:.4f} ({gr.ticker[d3].iloc[int(np.argmin(m.churn20_chart[d3]))]})")
x = m.wl_score.to_numpy()
print(f"wl_score: AUC wide-loose vs ok/good {np.mean([(i > j) + 0.5 * (i == j) for i in x[a] for j in x[b]]):.3f}; at or beyond the line (>= 1): " + ", ".join(f"{g} {int((x[(gr.grp == g).to_numpy()] >= 1).sum())} of {int((gr.grp == g).sum())}" for g in ("wide-loose", "ok/good", "maybe", "other no")))
show = [c for c in sys.argv[1:]] or ["chart_h", "adr20", "box20_chart", "churn20_chart", "atr15_chart", "b10_prev30", "wl_score"]
print("\n== per chart ==")
print(pd.concat([gr[["ticker", "D", "grade", "grp"]], m[show], gr.words.str[:60]], axis=1).sort_values(show[-1], ascending=False).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
