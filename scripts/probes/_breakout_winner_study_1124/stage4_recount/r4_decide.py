"""Apply the stage-2 floors (read AFTER my raw stats were hashed) + A2 and decide carried sets under both group-and-cap readings; compare to stage 3's result JSON/text."""
import json, re, sys
import numpy as np, pandas as pd
import r4_common as C
suf = C.SUF
own = pd.read_csv(C.OUTD / f"r4_stats_own{suf}.tsv", sep="\t").set_index("feature")
z = pd.read_csv(C.OUTD / f"r4_stats_z{suf}.tsv", sep="\t").set_index("feature")
GROUPS = {"volatility": ["f1"], "size": ["f2", "f3"], "strength": ["f4", "f5", "f6"], "run-up": ["f7", "f8", "f9"], "highs": ["f10", "f11"], "base": ["f12", "f13", "f14"],
          "tightness": ["f15", "f16"], "volume": ["f17", "f18"], "averages": ["f19", "f20"], "trend": ["f21", "f22"], "stage": ["f23"], "open": ["f24a", "f24b"]}
FLOOR3, FLOORB4 = 1.10, 1.10          # stage-2 floors_final.txt
cand = [f for f in own.index if f.startswith("f") and not (isinstance(own.loc[f, "desc_only"], str) and own.loc[f, "desc_only"])]
def direction(r): return 1 if r > 1 else -1
def cond(f):
    r = own.loc[f, "ratio"]; p = own.loc[f, "p2"]; e = own.loc[f, "ratio_ex2020"]
    c1 = r >= 1.25 or r <= 0.80
    c2 = p <= 0.05
    c3 = (e >= FLOOR3) if r > 1 else (e <= 1 / FLOOR3 + 0.0)   # prereg: "<= 0.91" for 1.10
    return c1, c2, c3
c3_ok = {f: all(cond(f)) for f in cand}
pass13 = [f for f in cand if all(cond(f))]
print("candidates", cand)
print("pass 1-3:", pass13)
# R1: group winners among those passing 1-3 by z_grp; cap four by z_all ; R2: winners among all candidates by z_grp, then must pass 1-3
def winners(pool):
    gw = {}
    for g, mem in GROUPS.items():
        m = [f for f in mem if f in pool]
        if m:
            gw[g] = sorted(m, key=lambda f: (-z.loc[f, "z_grp"], own.loc[f, "p2"], int(re.sub(r"\D", "", f.split("a")[0].split("b")[0]) or 0)))[0]
    return gw
def cap(gw, k=4):
    return sorted(gw.values(), key=lambda f: (-z.loc[f, "z_all"], own.loc[f, "p2"]))[:k]
gw1 = winners(pass13); top1 = cap(gw1)
gw2 = winners(cand); top2 = cap(gw2); car2 = [f for f in top2 if f in pass13]
# single common-set variant (z_all everywhere)
def winners_all(pool):
    gw = {}
    for g, mem in GROUPS.items():
        m = [f for f in mem if f in pool]
        if m: gw[g] = sorted(m, key=lambda f: (-z.loc[f, "z_all"], own.loc[f, "p2"]))[0]
    return gw
gw3 = winners_all(pass13); top3 = cap(gw3)
print("R1 group winners (among pass1-3):", gw1, "-> carried", top1)
print("R2 group winners (among all candidates):", gw2, "-> top4", top2, "-> carried", car2)
print("R3 single-common-set z:", gw3, "->", top3)
json.dump({"pass13": pass13, "R1_group_winners": gw1, "R1_carried": top1, "R2_group_winners": gw2, "R2_top4": top2, "R2_carried": car2, "R3_carried": top3}, open(C.OUTD / f"r4_decision{suf}.json", "w"), indent=1)
# compare to stage 3
T = json.load(open("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage3/3_result.json"))
tf = T["features"]
print("\nstage 3 carried:", T["carried_alt"], "| top4", T["top4"], "| pass13", T["pass13"], "| group winners", T["group_winners"])
def tname(f): return "f" + f[1:].zfill(2) if f[1:].isdigit() else "f" + f[1:3].zfill(2) + f[3:] if False else ("f%02d" % int(re.sub(r"\D", "", f)) + (f[-1] if f[-1] in "ab" else ""))
rows = []
for f in own.index:
    k = tname(f) if f.startswith("f") else f
    if k in tf:
        t = tf[k]
        rows.append((f, own.loc[f, "ratio"], t["raw"] if "raw" in t else t["ratio"], own.loc[f, "p2"], t["p"], own.loc[f, "ratio_ex2020"], t["ex2020"], z.loc[f, "z_all"] if f in z.index else np.nan, t.get("z")))
D = pd.DataFrame(rows, columns=["f", "ratio", "ratio_t", "p", "p_t", "ex2020", "ex2020_t", "z_all", "z_t"])
D["d_ratio"] = (D.ratio - D.ratio_t).abs(); D["d_ex"] = (D.ex2020 - D.ex2020_t).abs(); D["d_p"] = (D.p - D.p_t).abs(); D["rel_z"] = ((D.z_all - D.z_t).abs() / D.z_t)
print(D.round(4).to_string())
print("max |d ratio|", D.d_ratio.max(), "max |d ex2020|", D.d_ex.max(), "max |d p|", D.d_p.max(), "max rel z", D.rel_z.max())
D.to_csv(C.OUTD / f"r4_vs_stage3{suf}.tsv", sep="\t", index=False)
