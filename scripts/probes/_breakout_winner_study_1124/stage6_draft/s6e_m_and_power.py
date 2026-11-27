"""Stage 6 DRAFT step e: m, check n per era, and the smallest detectable ratio for gallery read #1. OUTCOME-FREE: reads the components table (group
sizes per month) and stage 3's PRINTED discovery text (the carried list, the combination, the 2017-19 rate). Synthetic labels only; no check outcome.
Model = stage 2's (design/spread_sim_v2): months as blocks; a month's rate is Beta around the era's rate (CV 0.6); p-values empirical against the
no-effect draws (a stand-in for the within-month permutation); FIRST Holm step 0.05 / m (a lower bound for a family member). Two groups, Mantel-Haenszel
by (era, month), ratio = not-V / V; a true ratio k means: V rate b, not-V rate b x k, the month's pooled rate unchanged."""
import json, re
from common6 import *
P = Out("6e_m_and_power.txt")
P("# STAGE 6 DRAFT (not a freeze) - e. m, check n and the smallest detectable ratio - outcome-free"); P(assert_all())
txt = (ROOT / "stage3/3_discovery.txt").read_text()
res = json.load(open(ROOT / "stage3/3_result.json"))
carried = [c["f"] for c in res["carried"]]
comb = [ln for ln in txt.splitlines() if "equal-weight mean of the within-(era, month) percentile ranks" in ln]
assert carried == ["f01", "f02", "f04", "f09"] and len(comb) == 1
P(f"\n== m (prereg 5.3: counted, to be pinned at step 6 - NOT pinned here) ==")
P(f"   carried on discovery: {len(carried)} ({', '.join(carried)})")
P(f"   combination (5.6: exists because >= 2 features are carried; one, pre-stated): 1  -> '{comb[0].strip()[:150]}...'")
P("   the operator's gallery reads so far: 1 (this one). Ruling slot: unused so far.")
m = len(carried) + 1 + 1
P(f"   m = {len(carried)} carried + 1 combination + 1 read = {m}   (it grows by one for each further read or a ruling he gives before step 6; cap 9)")
p0 = float(res["rate_1719"]); assert abs(p0 - 0.0918) < 0.0005
F = components(); K = F[F.kept].reset_index(drop=True); C = K[K.set == "CHECK"].reset_index(drop=True)
assert len(C) == 6266
t = L.assign_two(np.where(C.gr1.isna(), -1, C.gr1).astype(np.int8), [C.era.values, C.month.values])
C["t"] = t
P("\n== CHECK n for this read (seed 1124; a month enters when it holds >= 2 V and >= 2 not-V) ==")
blocks = {}
for era in ("A", "B"):
    d = C[C.era == era]; u = d[d.t >= 0]
    bl = [(int((g.t == 2).sum()), int((g.t == 0).sum())) for _, g in u.groupby("month")]
    blocks[era] = bl
    P(f"   era {era} ({'2021 to 2022-Q1' if era == 'A' else '2022-04 to 2024'}): events {len(d)} | V {int((d.gr1 == 1).sum())} = {100 * (d.gr1 == 1).mean():.1f}% | NULL {int(d.gr1.isna().sum())} | "
      f"months {d.month.nunique()}, usable {len(bl)} | in usable months: V {sum(b[0] for b in bl)}, not-V {sum(b[1] for b in bl)}")
u = C[C.t >= 0]
P(f"   ALL check: events {len(C)} | V {int((C.gr1 == 1).sum())} | usable months {len(blocks['A']) + len(blocks['B'])} | in usable months: V {int((u.t == 2).sum())}, not-V {int((u.t == 0).sum())}")
for nm, pm in (("at the 2017-19 rate", 1.0), ("era B at 0.75x", 0.75)):
    ev = sum(b[0] for b in blocks["A"]) * p0 + sum(b[0] for b in blocks["B"]) * p0 * pm
    P(f"   big winners expected among the V events if V made no difference, {nm}: about {ev:.0f}")
N = 20000; CV = 0.6; rng = np.random.default_rng(1124)

def draw(k, mult_b, eras=("A", "B")):
    NUM = np.zeros(N); DEN = np.zeros(N); NA = {e: [np.zeros(N), np.zeros(N)] for e in eras}
    for e in eras:
        p = p0 * (mult_b if e == "B" else 1.0)
        for n1, n0 in blocks[e]:
            a_ = max((1 - p) / CV ** 2 - p, 0.05); pm = rng.beta(a_, a_ * (1 - p) / p, N)
            b = pm * (n1 + n0) / (n1 + k * n0)
            a = rng.binomial(n1, np.minimum(b, 1)); c = rng.binomial(n0, np.minimum(b * k, 1))
            nu, de = c * n1 / (n1 + n0), a * n0 / (n1 + n0)
            NUM += nu; DEN += de; NA[e][0] += nu; NA[e][1] += de
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where((NUM > 0) & (DEN > 0), NUM / DEN, np.nan)
        re_ = {e: np.where((v[0] > 0) & (v[1] > 0), v[0] / v[1], np.nan) for e, v in NA.items()}
    return r, re_

P(f"\n== SMALLEST DETECTABLE RATIO (synthetic labels; base rate {100 * p0:.2f}% = stage 3's 2017-19 rate; one-sided in his direction; first Holm step 0.05 / {m} = {0.05 / m:.4f}; {N:,} draws) ==")
P("   'reaches the bar' = check ratio not-V / V >= 1.2 AND one-sided p <= 0.05 / m (the PICKS THE TAIL line of 5.3, either era form)")
out = {}
for nm, mb in (("era B at the same rate", 1.0), ("era B at 0.75x", 0.75)):
    r0, _ = draw(1.0, mb)
    crit = np.nanquantile(r0, 1 - 0.05 / m)
    P(f"\n   {nm}: under no effect the ratio's median is {np.nanmedian(r0):.3f}, 95% band {np.nanquantile(r0, .025):.2f}-{np.nanquantile(r0, .975):.2f}; ratio needed for p <= 0.05/{m}: {crit:.2f}; "
      f"a true-zero read shows >= 1.2 in {100 * np.nanmean(r0 >= 1.2):.0f}% of runs")
    need = None; row = []
    for k in (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5, 3.0):
        r, re_ = draw(k, mb)
        hit = (r >= max(crit, 1.2)); pw = float(np.nanmean(hit))
        both = float(np.nanmean(hit & (re_["A"] > 1) & (re_["B"] > 1)))
        row.append(f"{k:.1f}x {100 * pw:.0f}% (same direction in both eras {100 * both:.0f}%)")
        if need is None and pw >= 0.80: need = k
    P("   chance of reaching the bar by TRUE ratio: " + " | ".join(row))
    P(f"   -> smallest true ratio found 4 times in 5: " + (f"{need:.1f}x" if need else "over 3.0x"))
    out[nm] = need
P("\n   read with care: a lower bound for a family member (first Holm step); day / theme clustering is not simulated and pushes the real figure down;")
P("   the V group is about 1 event in 11 on check (a thirds feature compares 1 in 3 with 1 in 3).")
# the same, for ALT-1 (pause allowed) - group sizes only
t2 = L.assign_two(np.where(C.alt1.isna(), -1, C.alt1).astype(np.int8), [C.era.values, C.month.values])
save = blocks; blocks = {e: [(int(((C.era == e) & (C.month == mo) & (t2 == 2)).sum()), int(((C.era == e) & (C.month == mo) & (t2 == 0)).sum()))
                             for mo in sorted(C.month[(C.era == e) & (t2 >= 0)].unique())] for e in ("A", "B")}
P(f"\n== the same for ALT-1 'V, pause allowed' (group sizes only; its outcomes were never joined): check V {int((C.alt1 == 1).sum())} of {len(C)} = {100 * (C.alt1 == 1).mean():.1f}% ==")
for nm, mb in (("era B at the same rate", 1.0), ("era B at 0.75x", 0.75)):
    r0, _ = draw(1.0, mb); crit = np.nanquantile(r0, 1 - 0.05 / m); need = None
    for k in (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5, 3.0):
        r, _ = draw(k, mb)
        if float(np.nanmean(r >= max(crit, 1.2))) >= 0.80: need = k; break
    P(f"   {nm}: ratio needed for p <= 0.05/{m}: {crit:.2f}; smallest true ratio found 4 times in 5: " + (f"{need:.1f}x" if need else "over 3.0x"))
P.save()
