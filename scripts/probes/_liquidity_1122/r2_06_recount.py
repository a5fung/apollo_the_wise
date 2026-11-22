"""r2_06: second-route recount of the run-2 headline numbers (plain loops, math.fsum, csv module where practical), from the saved frames."""
import csv, math, itertools, statistics as stt, pandas as pd
O = "build_r2"
X = pd.read_csv("build/legs_X.csv", index_col=0); FR = pd.read_csv("build/legs_fresh.csv", index_col=0); V = pd.read_csv(f"{O}/legs_votes.csv", index_col=0)
dates = list(X.index); assert max(dates) <= "2024-12-31"
kept = "M1 F1 F2 R1 D1 K1 C3 R2 K5 M2".split(); votes = {}; diff = 0
for k in X.columns:
    x = list(X[k]); v = []
    for i in range(len(x)):
        if i < 49 or not bool(FR[k].iloc[i]): v.append(None); continue
        if k in ("C3", "F2", "F3", "R1", "R2"):
            xi = [int(round(z * 100)) for z in x[i-49:i+1]]; a, b = sum(xi[-20:]) * 50, sum(xi) * 20
        else:
            a, b = math.fsum(x[i-19:i+1]) / 20, math.fsum(x[i-49:i+1]) / 50
            if abs(a - b) <= 1e-9 * max(1, abs(a), abs(b)): a = b
        v.append(1 if a > b else (-1 if a < b else 0))
    votes[k] = v
    for i, d in enumerate(dates):
        s = V[k].iloc[i]; s = None if s != s else int(s)
        if s != v[i]: diff += 1
print(f"votes differing from build_r2/legs_votes.csv: {diff} of {len(dates)*len(X.columns)}")
H = (("H1", "2016-03-15", "2020-12-31"), ("H2", "2021-01-04", "2024-12-31"))
print("E2/E3 recount (kept legs + the three that failed): leg half tight% easy% median run")
for k in kept + ["C1", "C2", "D3"]:
    for h, a, b in H:
        seq = [v for d, v in zip(dates, votes[k]) if a <= d <= b]; nn = [v for v in seq if v is not None]
        rl = [len(list(g)) for key, g in itertools.groupby(seq) if key is not None]
        print(f"  {k} {h} n={len(seq)} tight {nn.count(1)/len(nn)*100:.1f} easy {nn.count(-1)/len(nn)*100:.1f} med_run {stt.median(rl)}")
CHN = {}
for k in kept: CHN.setdefault(k[0], []).append(k)
i0 = dates.index("2016-03-15"); S = []
for i in range(i0, len(dates)): S.append(sum(sum((votes[k][i] or 0) for k in ks) / len(ks) for ks in CHN.values()))
st = []; cur = "N"
for i in range(len(S)):
    if i >= 2:
        w = S[i-2:i+1]
        if cur == "D":
            if all(z <= -2 for z in w): cur = "E"
            elif all(z <= 1 for z in w): cur = "N"
        elif cur == "E":
            if all(z >= 2 for z in w): cur = "D"
            elif all(z >= -1 for z in w): cur = "N"
        else:
            if all(z >= 2 for z in w): cur = "D"
            elif all(z <= -2 for z in w): cur = "E"
    st.append(cur)
sd = dates[i0:]; comp = {r["date"]: r["state"] for r in csv.DictReader(open(f"{O}/composite.csv"))}
print("state days differing from composite.csv:", sum(1 for d, s in zip(sd, st) if comp[d] != s), "of", len(sd))
val = [(d, s) for d, s in zip(sd, st) if "2017-01-18" <= d <= "2024-09-27"]; n = len(val)
print(f"validation n={n}: Draining {sum(s=='D' for d,s in val)} ({sum(s=='D' for d,s in val)/n*100:.1f}%), Neutral {sum(s=='N' for d,s in val)}, Easing {sum(s=='E' for d,s in val)}")
chg = {}
for i in range(1, len(st)):
    if st[i] != st[i-1]: chg[sd[i][:4]] = chg.get(sd[i][:4], 0) + 1
print("word changes per year:", chg, "| median 2017-23:", stt.median([chg.get(str(y), 0) for y in range(2017, 2024)]))
rl = [len(list(g)) for key, g in itertools.groupby([s for d, s in val])]; print("spells", len(rl), "median dwell", stt.median(rl), "| without first and last", stt.median(rl[1:-1]))
for nm, a, b in (("Q1", "2017-01-18", "2017-12-29"), ("Q5", "2023-11-01", "2024-03-28"), ("S2", "2020-02-28", "2020-04-03")):
    w = [s for d, s in zip(sd, st) if a <= d <= b]; print(f"  {nm}: n={len(w)} Draining {w.count('D')} ({w.count('D')/len(w)*100:.1f}%) Easing {w.count('E')} ({w.count('E')/len(w)*100:.1f}%)")
# W2 statistic by loop
rows = list(csv.DictReader(open("build/etf_adj.csv"))); ed = [r["date"] for r in rows]; iwm = [float(r["IWM"]) for r in rows]; assert max(ed) <= "2024-12-31"
pos = {d: i for i, d in enumerate(ed)}; smap = dict(zip(sd, st)); cnt = {}
b3 = {r["date"]: r["B3"] for r in csv.DictReader(open(f"{O}/breadth.csv"))}
for d, s in val:
    i = pos[d]; e = min(iwm[i+1:i+64]) <= 0.9 * iwm[i]; assert len(iwm[i+1:i+64]) == 63
    half = "H1" if d <= "2020-12-31" else "H2"; neg = float(b3[d]) < 0
    for key in (("all", s), (half, "D" if s == "D" else "O"), ("neg" if neg else "pos", "D" if s == "D" else "O")) + ((("all", "O"),) if s != "D" else ()):
        c = cnt.setdefault(key, [0, 0]); c[0] += 1; c[1] += e
f = lambda k: f"{cnt[k][1]/cnt[k][0]*100:.1f}% (n={cnt[k][0]})"; r = lambda a, b: (cnt[a][1]/cnt[a][0]) / (cnt[b][1]/cnt[b][0])
print(f"W2 (a) Draining {f(('all','D'))} vs other {f(('all','O'))} ratio {r(('all','D'),('all','O')):.2f}")
print(f"W2 (c) H1 {f(('H1','D'))} vs {f(('H1','O'))} ratio {r(('H1','D'),('H1','O')):.2f} | H2 {f(('H2','D'))} vs {f(('H2','O'))} ratio {r(('H2','D'),('H2','O')):.2f}")
print(f"W2 (d) Easing {f(('all','E'))} vs Neutral {f(('all','N'))}")
print(f"W3 (c) breadth<0: Draining {f(('neg','D'))} vs rest {f(('neg','O'))} ratio {r(('neg','D'),('neg','O')):.4f}")
for nm, fn in (("EP", "p2_ep_frame.csv"), ("breakout", "p2_breakout_frame.csv")):
    c = {"D": [0, 0], "O": [0, 0]}
    for rr in csv.DictReader(open(f"{O}/{fn}")):
        k = "D" if rr["state"] == "D" else "O"; c[k][0] += 1; c[k][1] += int(rr["win"])
    print(f"P2 {nm}: Draining {c['D'][1]} of {c['D'][0]} ({c['D'][1]/c['D'][0]*100:.2f}%) vs rest {c['O'][1]} of {c['O'][0]} ({c['O'][1]/c['O'][0]*100:.2f}%)")
