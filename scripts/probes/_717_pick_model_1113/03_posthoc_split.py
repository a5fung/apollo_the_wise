#!/usr/bin/env python3
"""#717 pick model — POST-HOC, descriptive (added AFTER the single test run; not in the registration; no refit, the
registered verdict is untouched). Reads coef.json and rebuilds the same test-day picks, then splits "his buys taken"
by how the buy is known: DATED (a stream-dated buy, `buys.tsv`, the only kind that can be a big winner) vs UNDATED
(a positions-panel sighting widened to a 1-5 session window, `buys_undated_widened.tsv`).

    python3 scripts/probes/_717_pick_model_1113/03_posthoc_split.py > scripts/probes/_717_pick_model_1113/03_posthoc_split.out
"""
import importlib.util, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("m", os.path.join(HERE, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
P2 = M.P2
df, cal, big = M.load()
co = json.load(open(M.COEF))["models"]["primary"]
df["score_primary"] = M.X_of(df, co["features"]) @ np.r_[co["intercept"], co["coef"]]
te = df[df.E >= M.TEST_FIRST]; f = te[te.fire]
split = lambda s: (sum(i[0] == "d" for i in s), sum(i[0] == "w" for i in s))
fd, fw = split(M.taken_set(f))
print("POST-HOC (not registered): his buys taken on the TEST days, by how the buy is known")
print(f"fired on the test days: {fd} dated + {fw} undated sightings = {fd + fw}; median dollar-volume rank inside the day's list (1 = most liquid): "
      f"dated {f[f.qm.map(lambda l: any(i[0] == 'd' for i in l))].f_dollar_vol20.median():.2f}, undated {f[f.qm.map(lambda l: any(i[0] == 'w' for i in l))].f_dollar_vol20.median():.2f}, all fires {f.f_dollar_vol20.median():.2f}")
print(f"  {'the day top 5 fires by':28s} {'dated':>6s} {'undated':>8s} {'total':>6s} {'big':>4s}")
sets = {}
for name, col in (("the model", "score_primary"), ("the order score", "score_order"), ("dollar volume", "dollar_vol20")):
    s = M.taken_set(P2.top_k(f, f[col])); sets[name] = s
    d, w = split(s)
    print(f"  {name:28s} {d:>6d} {w:>8d} {len(s):>6d} {len(s & big):>4d}")
a, b = sets["the model"], sets["dollar volume"]
print(f"model and dollar volume take the SAME buy {len(a & b)} times; model only {len(a - b)} (dated {split(a - b)[0]}), dollar volume only {len(b - a)} (dated {split(b - a)[0]})")
tr = df[df.fire & df.covered & (df.E <= M.FIT_LAST) & df.y]
print(f"fit label rows (410): landing on a dated buy's own day {int(tr.qm.map(lambda l: any(i[0] == 'd' for i in l)).sum())}, on an undated sighting's window {int(tr.qm.map(lambda l: any(i[0] == 'w' for i in l)).sum())}, in the +1/+2 tail only {int((~tr.is_qm).sum())}")
for lab, col in (("the model", "score_primary"), ("the order score", "score_order")):
    xa, seats = P2.live_like(te, te[col], "fire", 0)
    print(f"R as wired, {lab}: {seats} resting seats, {len(xa)} buys on {te.ci.nunique()} days")
