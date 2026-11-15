#!/usr/bin/env python3
"""#717 grades — POST HOC (not registered; run after 01_grades.out was read; era A only). Two questions on whether the
grade is 'absolute': (a) A+ share of the WHOLE list per night and how the A+ count tracks list size; (b) the fit
by-year buy rate per grade on `covered` rows only (days his positions panel covers).
    python3 scripts/probes/_717_grades_1115/03_posthoc.py > scripts/probes/_717_grades_1115/03_posthoc.out
"""
import importlib.util, json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "01_grades.py")); G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
spec = importlib.util.spec_from_file_location("m", os.path.join(REPO, "scripts/probes/_717_pick_model_1113/02_fit_test.py")); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
pd.set_option("display.width", 250)
cuts = list(json.load(open(os.path.join(HERE, "cutoffs.json")))["cutoffs_log_odds"].items()); names = [n for n, _ in cuts] + ["C"]
df, cal, big = M.load(); df = df[df.E <= G.ERA_LAST]
co = json.load(open(M.COEF))["models"]["primary"]
df["PM"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]; df["grade"] = G.grade_of(df.PM, cuts)
for era, x in (("FIT 2017-2020", df[df.E <= G.FIT_LAST]), ("TEST 2021-01..2022-03", df[df.E >= G.TEST_FIRST])):
    n = x.groupby("ci").size(); a = x[x.grade == "A+"].groupby("ci").size().reindex(n.index).fillna(0); sh = a / n
    print(f"== {era}, whole list: nights {len(n)}; list size 10th/median/90th {n.quantile(.1):.0f}/{n.median():.0f}/{n.quantile(.9):.0f}; "
          f"A+ count 10th/median/90th {a.quantile(.1):.0f}/{a.median():.0f}/{a.quantile(.9):.0f}; A+ SHARE of the list 10th/median/90th "
          f"{100*sh.quantile(.1):.1f}%/{100*sh.median():.1f}%/{100*sh.quantile(.9):.1f}%; nights with no A+ {int((a == 0).sum())}; corr(A+ count, list size) {np.corrcoef(a, n)[0, 1]:.2f}")
pool = G.load_pool(); pool["grade"] = G.grade_of(pool.PM, cuts)
f = pool[(pool.E <= G.FIT_LAST) & pool.covered]; y = f.assign(year=f.E.str[:4])
print("\n== FIT, COVERED rows only: buy rate percent per grade by year, then rows, then buy rows ==")
for fn in ("mean", "size", "sum"):
    t = y.pivot_table(index="year", columns="grade", values="is_qm", aggfunc=fn)[names]
    print((t * 100).round(2).to_string() if fn == "mean" else t.to_string()); print()
t = pool[(pool.E >= G.TEST_FIRST)]
print("== TEST covered share of rows:", round(t.covered.mean(), 3), "| buy rate per grade on covered rows (percent):",
      ", ".join(f"{g} {100*t[t.covered & (t.grade == g)].is_qm.mean():.2f}" for g in names))
