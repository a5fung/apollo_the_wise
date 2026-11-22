"""02: §4.2 selection, outcome-blind. Reads ONLY build/legs_*.csv (leg-versus-leg facts). Writes the freeze file."""
import pandas as pd, numpy as np, itertools
B = "build"
P = pd.read_csv(f"{B}/legs_P.csv", index_col=0, parse_dates=True); V = pd.read_csv(f"{B}/legs_votes.csv", index_col=0, parse_dates=True)
SIGN = pd.read_csv(f"{B}/legs_sign.csv", index_col=0).iloc[:, 0]; FORM = pd.read_csv(f"{B}/legs_form.csv", index_col=0).iloc[:, 0]
assert P.index.max() <= pd.Timestamp("2024-12-31")
PRIO = "C1 M1 F1 F2 R1 D1 K1 C2 C3 R2 F3 K5 D3 M2 K2 K3 D2".split(); assert sorted(PRIO) == sorted(P.columns)
CH = {"C": "Credit", "F": "Fed and money", "R": "Rates", "D": "Dollar", "M": "Metals", "K": "Risk appetite"}
fs = V.dropna(how="all").index[0]
H = {"H1": (fs, pd.Timestamp("2020-12-31")), "H2": (pd.Timestamp("2021-01-04"), pd.Timestamp("2024-12-31"))}
print("first state session", fs.date(), "| H1 sessions", len(V.loc[H['H1'][0]:H['H1'][1]]), "| H2 sessions", len(V.loc[H['H2'][0]:H['H2'][1]]))
def runs(s):
    s = s.dropna(); return s.groupby((s != s.shift()).cumsum()).size()
print("\nELIGIBILITY (must pass in BOTH halves). E1 vote exists >=95% | E2 tight share and easy share each 10-70% | E3 median run >=5 sessions")
print("leg  half     n  E1_cov  tight%   easy%  flat%  med_run  E1 E2 E3")
elig = {}
for k in PRIO:
    ok = True
    for h, (a, b) in H.items():
        v = V.loc[a:b, k]; n = len(v); cov = v.notna().mean(); vv = v.dropna(); t, e = (vv == 1).mean(), (vv == -1).mean(); mr = runs(v.where(v.notna())).median()
        # runs: a missing vote breaks a run (only D2 has any)
        seg = v.copy(); grp = (seg.ne(seg.shift()) | seg.isna()).cumsum(); mr = seg.dropna().groupby(grp[seg.notna()]).size().median()
        e1, e2, e3 = cov >= 0.95, (0.10 <= t <= 0.70) and (0.10 <= e <= 0.70), mr >= 5; ok &= e1 and e2 and e3
        print(f"{k}   {h}  {n:5d}  {cov*100:5.1f}  {t*100:6.1f}  {e*100:6.1f}  {(vv==0).mean()*100:5.1f}  {mr:7.1f}   {'Y' if e1 else 'N'}  {'Y' if e2 else 'N'}  {'Y' if e3 else 'N'}")
    elig[k] = ok
E = [k for k in PRIO if elig[k]]
print("\neligible:", E, "\nfail -> display-only:", [k for k in PRIO if not elig[k]])
# trend gap on raw P, signed
g = {}
for k in PRIO:
    m20, m50 = P[k].rolling(20).mean(), P[k].rolling(50).mean()
    g[k] = SIGN[k] * ((m20 / m50 - 1) if FORM[k] == "ratio" else (m20 - m50))
G = pd.DataFrame(g)
def pair(a, b):
    out = {}
    for h, (s, e) in H.items():
        x = G.loc[s:e, [a, b]].dropna(); c = np.corrcoef(x[a], x[b])[0, 1]
        v = V.loc[s:e, [a, b]].dropna(); nz = v[(v[a] != 0) & (v[b] != 0)]; ag = (nz[a] == nz[b]).mean() if len(nz) else np.nan
        out[h] = (c, ag, len(nz))
    return out
for h in H:
    s, e = H[h]; print(f"\nCORRELATION of signed trend gap, {h} (n={len(G.loc[s:e].dropna())} sessions with all legs)"); print(G.loc[s:e, PRIO].corr().round(2).to_string())
print("\nVOTE AGREEMENT (share of sessions where both votes are non-zero on which they agree; n = both non-zero), eligible pairs")
PT = {}
for a, b in itertools.combinations(E, 2):
    r = pair(a, b); PT[(a, b)] = r; thr = 0.80 if a[0] == b[0] else 0.85
    t1 = all(r[h][0] >= thr for h in H); t2 = all((r[h][1] >= 0.85) for h in H)
    anyhalf = all((r[h][0] >= thr) or (r[h][1] >= 0.85) for h in H)
    PT[(a, b)] = (t1 or t2, anyhalf, r, thr)
    print(f"  {a}-{b}: corr H1 {r['H1'][0]:+.2f} H2 {r['H2'][0]:+.2f} (line {thr}) | agree H1 {r['H1'][1]*100:5.1f}% (n={r['H1'][2]}) H2 {r['H2'][1]*100:5.1f}% (n={r['H2'][2]})"
          + ("  <-- REDUNDANT" if (t1 or t2) else "") + ("  [redundant only under the alternative reading]" if anyhalf and not (t1 or t2) else ""))
def walk(idx, cap_during=True):
    kept, log = [], []
    for k in E:
        if cap_during and sum(1 for j in kept if j[0] == k[0]) >= 2: log.append(f"{k}: skipped, {CH[k[0]]} already holds 2 kept legs"); continue
        hit = [j for j in kept if PT[tuple(sorted((j, k), key=E.index))][idx]]
        if hit: log.append(f"{k}: pruned, redundant with {hit}")
        else: kept.append(k); log.append(f"{k}: KEPT")
    return kept, log
kept, log = walk(0)
print("\nPRUNING LOG (doc reading: a pair is redundant when ONE of the two tests holds in both halves; channel cap applied during the walk)"); print("\n".join("  " + l for l in log))
kept2, log2 = walk(1)
print("\nalternative reading (in each half at least one test holds):", kept2, "-> same kept list" if kept2 == kept else "-> DIFFERENT KEPT LIST")
chans = {c: [k for k in kept if k[0] == c] for c in CH}
K = sum(1 for c in chans if chans[c])
print("\nKEPT LIST:", kept); [print(f"  {CH[c]}: {chans[c] or 'UNCOVERED'}") for c in CH]
print(f"K = {K} live channels; enter line T = K/3 = {K/3:.3f}; exit line K/6 = {K/6:.3f}", "| composite built" if K >= 4 else "| FEWER THAN 4 CHANNELS: no composite")
print("seeds: C1 (junk bonds, on HYG)", "kept" if "C1" in kept else "PRUNED (tile stays)", "| M1 (gold/silver)", "kept" if "M1" in kept else "PRUNED (tile stays)")
print("\nSIGN AND LAG AUDIT (build check): share of sessions EASY in 2018-12-03..12-21 and 2020-03-09..03-20")
for k in PRIO:
    a = (V.loc["2018-12-03":"2018-12-21", k] == -1).mean(); b = (V.loc["2020-03-09":"2020-03-20", k] == -1).mean()
    print(f"  {k}: {a*100:5.1f}%  {b*100:5.1f}%" + ("  <-- AUDIT (easy on most of both)" if a > 0.5 and b > 0.5 else ""))
pd.Series(kept).to_csv(f"{B}/kept_legs.csv", index=False, header=False); G.to_csv(f"{B}/legs_trend_gap.csv")
