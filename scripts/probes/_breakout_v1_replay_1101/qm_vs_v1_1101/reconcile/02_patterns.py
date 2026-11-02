#!/usr/bin/env python3
"""Reconcile step 2: count each candidate pattern in his 28 winners (R >= 5), his losers (R <= 0), his middle, and in
v1's own fills (guard book, his window) winners (R >= 5 under today's exit A, or under exit C) vs losers (R <= 0).
Reads his205_nights.tsv and v1_fills_window.tsv (step 1). Writes patterns.txt."""
import numpy as np, pandas as pd
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101/reconcile"
h = pd.read_csv(f"{HERE}/his205_nights.tsv", sep="\t")
v = pd.read_csv(f"{HERE}/v1_fills_window.tsv", sep="\t")
L = []
def p(s=""): print(s); L.append(str(s))
h["grp"] = np.where(h.R >= 5, "win5", np.where(h.R <= 0, "loss", "mid"))
G = {"win5": h[h.grp == "win5"], "loss": h[h.grp == "loss"], "mid": h[h.grp == "mid"], "all": h}
p(f"his 205: win5 {len(G['win5'])}, loss {len(G['loss'])}, mid {len(G['mid'])}; EP/both setups {int((h.setup!='breakout').sum())}")
def row(name, mask_fn):
    out = []
    for k in ("win5", "loss", "mid", "all"):
        d = G[k]; m = mask_fn(d)
        out.append(f"{k} {int(m.sum())}/{len(d)} ({100*m.mean():.0f}%)")
    p(f"{name:58s} " + " | ".join(out))
fl = lambda d, g: d.failed.fillna("").str.split(",").apply(lambda x: g in x)
row("on the 98 list the night before", lambda d: d.in98 == 1)
row("on the 90 list the night before", lambda d: d.in90 == 1)
row("strength >= 98", lambda d: d.rs_best >= 98)
row("strength 90-98", lambda d: (d.rs_best >= 90) & (d.rs_best < 98))
row("strength 90-98 and strength the ONLY failure", lambda d: (d.rs_best >= 90) & (d.rs_best < 98) & (d.failed == "rs"))
row("strength < 90 (or not ranked)", lambda d: ~(d.rs_best >= 90))
row("strength < 90 AND within 10% of 6-month high", lambda d: ~(d.rs_best >= 90) & (d.hi126_gap >= -0.10))
for g in ("universe", "prior_move", "higher_lows", "surf", "tightening", "breakdown"):
    row(f"fails {g}", lambda d, g=g: fl(d, g))
shape = ("higher_lows", "surf", "tightening", "breakdown")
row("fails any shape gate", lambda d: sum(fl(d, g) for g in shape) > 0)
row("strength >= 98 but a shape gate fails", lambda d: (d.rs_best >= 98) & (sum(fl(d, g) for g in shape) > 0))
row("fails ONLY surf (strength fine)", lambda d: d.failed == "surf")
row("fails ONLY higher_lows (strength fine)", lambda d: d.failed == "higher_lows")
row("fails ONLY tightening (strength fine)", lambda d: d.failed == "tightening")
row("would list without surf (all else passes, rs>=98)", lambda d: d.failed.fillna("").isin(["surf"]))
row("would list without surf at rs>=90", lambda d: (d.rs_best >= 90) & d.failed.fillna("").apply(lambda s: set(s.split(",")) <= {"rs", "surf"}))
row("his day volume < 1.2x 50-day average", lambda d: d.vol_x_E < 1.2)
row("his day volume < 1.0x", lambda d: d.vol_x_E < 1.0)
row("v1 5-day-high level > 3% above his pivot", lambda d: d.level_vs_pivot > 0.03)
row("his fill below v1's 5-day-high level", lambda d: d.fill_vs_level < 0)
row("night before was a wide up day (range > 1 ADR)", lambda d: d.wide_up_D == 1)
for k in ("win5", "loss"):
    d = G[k]
    p(f"  {k}: median strength {d.rs_best.median():.1f}, median vol x {d.vol_x_E.median():.2f}, median level vs pivot {100*d.level_vs_pivot.median():.1f}%, median stop {100*d.stop_pct.median():.1f}%")
p()
# ---- v1 fills
v = v[v.note.isna()] if "note" in v else v
v["grp"] = np.where(v.R_A >= 5, "win5", np.where(v.R_A <= 0, "loss", "mid"))
p(f"v1 fills in his window (guard book, every listed day, mature): {len(v)}; R_A>=5 {int((v.R_A>=5).sum())}, R_A<=0 {int((v.R_A<=0).sum())}; R_C>=5 {int((v.R_C>=5).sum())}, R_C<=0 {int((v.R_C<=0).sum())}")
VG = {"win5A": v[v.R_A >= 5], "win5C": v[v.R_C >= 5], "lossA": v[v.R_A <= 0], "all": v}
def vrow(name, fn):
    out = []
    for k, d in VG.items():
        m = fn(d); out.append(f"{k} {int(m.sum())}/{len(d)} ({100*m.mean():.0f}%)")
    p(f"{name:58s} " + " | ".join(out))
vrow("buy-day volume < 1.2x (full day)", lambda d: d.vol_x_E < 1.2)
vrow("buy-day volume >= 2x", lambda d: d.vol_x_E >= 2)
vrow("5-day-high level > 3% above prior day's high", lambda d: d.level_vs_hiD > 0.03)
vrow("level = prior day's high (within 0.1%)", lambda d: d.level_vs_hiD.abs() < 0.001)
vrow("fill > 3% above prior day's high", lambda d: d.fill_vs_hiD > 0.03)
vrow("night before was a wide up day (range > 1 ADR)", lambda d: d.wide_up_D == 1)
vrow("night before up > 1 ADR close-to-close", lambda d: d.upD > d.adr20)
vrow("strength >= 99.5", lambda d: d.rs_best >= 99.5)
vrow("sold a third at +2R then stopped at cost on day 0", lambda d: d.third_then_cost_day0 == 1)
vrow("exit A stopped on day 0", lambda d: d.exit_kind == "day0_stop")
for fn, name in [(lambda d: d.wide_up_D == 1, "after a wide up day"), (lambda d: d.wide_up_D == 0, "NOT after a wide up day"),
                 (lambda d: d.level_vs_hiD > 0.03, "level > 3% above prior high"), (lambda d: d.level_vs_hiD <= 0.03, "level <= 3% above prior high"),
                 (lambda d: d.vol_x_E < 1.5, "buy-day vol < 1.5x"), (lambda d: d.vol_x_E >= 1.5, "buy-day vol >= 1.5x")]:
    d = v[fn(v)]
    p(f"  v1 fills {name:32s}: n {len(d)}, mean R_A {d.R_A.mean():+.2f}, losers {100*(d.R_A<=0).mean():.0f}%, 5R+ A {int((d.R_A>=5).sum())} C {int((d.R_C>=5).sum())}, mean R_C {d.R_C.mean():+.2f}")
t3 = v[v.third_then_cost_day0 == 1]
p(f"  third-then-cost on day 0: n {len(t3)}; their exit C: mean {t3.R_C.mean():+.2f}, 5R+ {int((t3.R_C>=5).sum())}, lost under C {int((t3.R_C<=0).sum())}")
nt = v[v.third_then_cost_day0 == 0]
p(f"  all other fills:          n {len(nt)}; A mean {nt.R_A.mean():+.2f}, C mean {nt.R_C.mean():+.2f}")
open(f"{HERE}/patterns.txt", "w").write("\n".join(L) + "\n")
