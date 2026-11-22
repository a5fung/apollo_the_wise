"""r2_03: §4.3 composite on the frozen run-2 legs, then W0 (flicker) and W1 (episodes). OUTCOME-BLIND: reads only build_r2/legs_votes.csv + kept_legs.csv.
No ETF price, forward return, breadth, EP or breakout file is opened. Validation window fixed from the grid: 2017-01-18 -> 2024-09-27 (doc: 1,937 sessions)."""
import pandas as pd, numpy as np
O = "build_r2"; CUT = pd.Timestamp("2024-12-31")
V = pd.read_csv(f"{O}/legs_votes.csv", index_col=0, parse_dates=True); assert V.index.max() <= CUT
kept = [l.strip() for l in open(f"{O}/kept_legs.csv") if l.strip()]; assert kept == "M1 F1 F2 R1 D1 K1 C3 R2 K5 M2".split()
CH = {"C": "Credit", "F": "Fed and money", "R": "Rates", "D": "Dollar", "M": "Metals", "K": "Risk appetite"}
fs = V.dropna(how="all").index[0]; Vk = V.loc[fs:, kept].fillna(0.0)   # a kept leg with no vote votes 0 and stays in the channel mean
C = pd.DataFrame({CH[c]: Vk[[k for k in kept if k[0] == c]].mean(axis=1) for c in CH if any(k[0] == c for k in kept)})
K = C.shape[1]; assert K == 6; T, X_ = K / 3, K / 6
S = C.sum(axis=1); ntight = (C > 0).sum(axis=1); neasy = (C < 0).sum(axis=1)
s = S.values; st = []; cur = "N"
for i in range(len(s)):
    if i >= 2:
        w = s[i-2:i+1]; dr, ea, xd, xe = (w >= T).all(), (w <= -T).all(), (w <= X_).all(), (w >= -X_).all()
        if cur == "D": cur = "E" if ea else ("N" if xd else "D")
        elif cur == "E": cur = "D" if dr else ("N" if xe else "E")
        else: cur = "D" if dr else ("E" if ea else "N")
    st.append(cur)
ST = pd.Series(st, S.index, name="state")
out = C.copy(); out["S"] = S; out["n_tight"] = ntight; out["n_easy"] = neasy; out["state"] = ST; out.to_csv(f"{O}/composite.csv")
NAME = {"D": "Draining", "N": "Neutral", "E": "Easing"}
VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27"); val = ST.loc[VS:VE]; assert len(val) == 1937, len(val)
def spells(x):
    g = (x != x.shift()).cumsum(); return x.groupby(g).agg(["first", "size"])
print(f"K = {K}; enter {T:g}, exit {X_:g}; state series {ST.index[0].date()} -> {ST.index[-1].date()} n={len(ST)}; validation window {VS.date()} -> {VE.date()} n={len(val)}")
print("\nCOMPOSITE HISTORY")
for nm, x in (("all state sessions", ST), ("validation window", val)):
    print(f"  {nm} (n={len(x)}): " + " | ".join(f"{NAME[k]} {(x==k).mean()*100:.1f}% ({int((x==k).sum())})" for k in "DNE"))
print("  S distribution, validation window (value: sessions):", S.loc[VS:VE].round(2).value_counts().sort_index().to_dict())
print("  groups tight count, validation window (count: sessions):", ntight.loc[VS:VE].value_counts().sort_index().to_dict())
chg = (ST != ST.shift()) & ST.shift().notna(); cy = chg.groupby(chg.index.year).sum()
print("  word changes per calendar year:", {int(y): int(v) for y, v in cy.items()})
sp = spells(val); sp_in = sp.iloc[1:-1]
print(f"  spells in validation window: n={len(sp)}; median dwell all spells {sp['size'].median():.1f} sessions; excluding the first and last (cut-off) spells {sp_in['size'].median():.1f} (n={len(sp_in)})")
for k in "DNE": print(f"    {NAME[k]}: spells {int((sp['first']==k).sum())}, median dwell {sp.loc[sp['first']==k,'size'].median()}, longest {sp.loc[sp['first']==k,'size'].max()}")
print("  each group's tight share on Draining days (validation, n=%d):" % (val == "D").sum(), {c: f"{(C.loc[val.index][val=='D'][c] > 0).mean()*100:.0f}%" for c in C.columns})
print("  each group's easy share on Easing days (validation, n=%d):" % (val == "E").sum(), {c: f"{(C.loc[val.index][val=='E'][c] < 0).mean()*100:.0f}%" for c in C.columns})
print("\nW0 FLICKER (outcome-blind)")
med_chg = cy.loc[2017:2023].median(); dshare = (val == "D").mean(); d1, d2 = sp["size"].median(), sp_in["size"].median()
a = med_chg <= 8; b = (d1 >= 10) and (d2 >= 10); c = 0.10 <= dshare <= 0.35
print(f"  (a) word changes per calendar year, median over 2017-2023: {med_chg:g} (bar <= 8) -> {'PASS' if a else 'FAIL'}")
print(f"  (b) median dwell: {d1:g} sessions all spells / {d2:g} excluding cut-off spells (bar >= 10 under both) -> {'PASS' if b else 'FAIL'}")
print(f"  (c) Draining share of validation sessions: {dshare*100:.1f}% (n={len(val)}; bar 10% to 35%) -> {'PASS' if c else 'FAIL'}")
print("  W0:", "PASS" if (a and b and c) else "FAIL")
print("\nW1 EPISODES (expected in advance; share = share of sessions in the window)")
def sh(a_, b_, k): x = ST.loc[a_:b_]; return (x == k).mean(), int((x == k).sum()), len(x)
rows = []
def ctx(a_, b_): return " ".join(f"{c[:6]}:{(C.loc[a_:b_, c] > 0).mean()*100:.0f}/{(C.loc[a_:b_, c] < 0).mean()*100:.0f}" for c in C.columns)
for r, a_, b_, bar in (("S1", "2018-10-10", "2018-12-24", .5), ("S2", "2020-02-28", "2020-04-03", .5), ("S3", "2022-01-18", "2022-10-14", .5), ("S4", "2023-08-15", "2023-10-27", .4)):
    p, n1, n = sh(a_, b_, "D"); ok = p >= bar; rows.append(("S", ok)); print(f"  {r} must drain {a_}..{b_} n={n}: Draining {p*100:.1f}% ({n1}) vs >= {bar*100:.0f}% -> {'HIT' if ok else 'MISS'} | Easing {sh(a_,b_,'E')[0]*100:.0f}% | groups tight/easy %: {ctx(a_,b_)}")
for r, a_, b_, leg, lb, dmax in (("L1", "2023-03-10", "2023-03-24", "K3", .8, 10), ("L2", "2024-08-01", "2024-08-09", "D3", .8, 5), ("L3", "2018-02-05", "2018-02-16", "R1", .6, 5), ("L4", "2021-02-16", "2021-03-19", "R1", .7, 10)):
    v = V.loc[a_:b_, leg]; lt = (v == 1).mean(); p, n1, n = sh(a_, b_, "D"); ok = (lt >= lb) and (n1 <= dmax); rows.append(("L", ok))
    print(f"  {r} leg only {a_}..{b_} n={n}: {leg} TIGHT (trend vote) {lt*100:.1f}% ({int((v==1).sum())}) vs >= {lb*100:.0f}% AND Draining sessions {n1} vs <= {dmax} -> {'HIT' if ok else 'MISS'}")
for r, a_, b_, emin, dmax in (("Q1", "2017-01-18", "2017-12-29", None, .10), ("Q2", "2019-01-07", "2019-04-30", None, .15), ("Q3", "2019-07-01", "2020-01-31", None, .15), ("Q4", "2020-06-01", "2021-01-29", .5, .10), ("Q5", "2023-11-01", "2024-03-28", .4, .10)):
    p, n1, n = sh(a_, b_, "D"); e, e1, _ = sh(a_, b_, "E"); ok = (p <= dmax) and (emin is None or e >= emin); rows.append(("Q", ok))
    print(f"  {r} calm {a_}..{b_} n={n}: Draining {p*100:.1f}% ({n1}) vs <= {dmax*100:.0f}%" + (f" AND Easing {e*100:.1f}% ({e1}) vs >= {emin*100:.0f}%" if emin else f" | Easing {e*100:.1f}% ({e1})") + f" -> {'HIT' if ok else 'MISS'}")
cnt = {t: sum(ok for tt, ok in rows if tt == t) for t in "SLQ"}; w1 = cnt["S"] >= 3 and cnt["L"] >= 3 and cnt["Q"] >= 4
print(f"  must drain {cnt['S']} of 4 (bar 3) | leg only {cnt['L']} of 4 (bar 3) | calm {cnt['Q']} of 5 (bar 4) -> W1 {'PASS' if w1 else 'FAIL'}")
print("\nDraining spells (>= 5 sessions), validation window:")
g = (val != val.shift()).cumsum()
for _, x in val.groupby(g):
    if x.iloc[0] == "D" and len(x) >= 5: print(f"   {x.index[0].date()} -> {x.index[-1].date()} ({len(x)})")
print("Easing spells (>= 5 sessions), validation window:")
for _, x in val.groupby(g):
    if x.iloc[0] == "E" and len(x) >= 5: print(f"   {x.index[0].date()} -> {x.index[-1].date()} ({len(x)})")
