"""r2_04: W2 (forward risk) and W3 (baselines), run ONCE after the freeze, W0/W1 and the readings file (build_r2/READINGS_before_outcomes.txt).
Computes everything, saves frames to build_r2/, prints last."""
import pandas as pd, numpy as np, json
from numpy.lib.stride_tricks import sliding_window_view as swv
O = "build_r2"; CUT = pd.Timestamp("2024-12-31"); SEED = 20261122
comp = pd.read_csv(f"{O}/composite.csv", index_col=0, parse_dates=True); A = pd.read_csv("build/etf_adj.csv", index_col=0, parse_dates=True)
BR = pd.read_csv(f"{O}/breadth.csv", index_col=0, parse_dates=True)
vx = pd.read_csv("fred/VIXCLS.csv"); vx.columns = ["d", "v"]; vx["d"] = pd.to_datetime(vx.d); vx["v"] = pd.to_numeric(vx.v, errors="coerce"); vx = vx[vx.d <= CUT]
for f in (comp, A, BR): assert f.index.max() <= CUT
assert vx.d.max() <= CUT
grid = A.index; assert len(grid) == 2264
VIX = vx.dropna().set_index("d")["v"].reindex(grid).ffill()
ST = comp["state"].reindex(grid)
VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27"); vi = grid[(grid >= VS) & (grid <= VE)]; n = len(vi); assert n == 1937
assert grid.get_loc(VE) + 63 <= len(grid) - 1
def fwd(px, h):
    a = px.values.astype(float); mn = np.full(len(a), np.nan); mx = mn.copy(); rt = mn.copy()
    w = swv(a[1:], h); m = len(w); mn[:m] = w.min(axis=1); mx[:m] = w.max(axis=1); rt[:len(a)-h] = a[h:]
    return pd.DataFrame({"dd": mn / a - 1, "up": mx / a - 1, "ret": rt / a - 1}, index=px.index)
F = {(t, h): fwd(A[t], h) for t in ("IWM", "SPY", "QQQ") for h in (63, 21)}
ev = (F[("IWM", 63)]["dd"] <= -0.10).loc[vi]; assert F[("IWM", 63)]["dd"].loc[vi].notna().all()
st = ST.loc[vi]; D = (st == "D").values; E = (st == "E").values; Nn = (st == "N").values; e = ev.values.astype(float)
def ratio(flag, x=e, mask=None):
    if mask is not None: flag, x = flag[mask], x[mask]
    a, b = x[flag], x[~flag]
    if len(a) == 0 or len(b) == 0: return np.nan, np.nan, np.nan, len(a), len(b)
    pa, pb = a.mean(), b.mean(); return (pa / pb if pb > 0 else (np.inf if pa > 0 else np.nan)), pa, pb, len(a), len(b)
R = {}; R["a"] = ratio(D)
# (b) quarter-block bootstrap
q = pd.PeriodIndex(vi, freq="Q"); qc = pd.DataFrame({"q": q, "dn": D.astype(int), "de": D * e, "on": (~D).astype(int), "oe": (~D) * e}).groupby("q").sum().values
rng = np.random.default_rng(SEED); idx = rng.integers(0, len(qc), (10000, len(qc))); sm = qc[idx].sum(axis=1)
ok = (sm[:, 0] > 0) & (sm[:, 2] > 0); dif = sm[ok, 1] / sm[ok, 0] - sm[ok, 3] / sm[ok, 2]
R["b"] = dict(lo=float(np.percentile(dif, 2.5)), hi=float(np.percentile(dif, 97.5)), dropped=int((~ok).sum()), blocks=len(qc))
# (b2) circular shift
sh = []
for off in range(126, n - 126 + 1):
    d2 = np.roll(D, off); pa, pb = e[d2].mean(), e[~d2].mean(); sh.append(pa / pb if pb > 0 else np.inf)
sh = np.array(sh); R["b2"] = dict(p95=float(np.percentile(sh, 95)), n=len(sh), share_ge=float((sh >= R["a"][0]).mean()), median=float(np.median(sh)))
h1 = (vi <= pd.Timestamp("2020-12-31")); h2 = (vi >= pd.Timestamp("2021-01-04")); R["c"] = (ratio(D, mask=h1), ratio(D, mask=h2))
R["d"] = (e[E].mean() if E.sum() else np.nan, int(E.sum()), e[Nn].mean() if Nn.sum() else np.nan, int(Nn.sum()))
def episodes(flag):
    runs = []; i = 0
    while i < n:
        if flag[i]:
            j = i
            while j + 1 < n and flag[j + 1]: j += 1
            if j - i + 1 >= 5: runs.append([i, j, j - i + 1])
            i = j + 1
        else: i += 1
    ep = []
    for r in runs:
        if ep and r[0] - ep[-1][1] - 1 < 63: ep[-1][1] = r[1]; ep[-1][2] += r[2]
        else: ep.append(list(r))
    return ep
FL = {}
for nm, fl in (("Draining", D), ("Easing", E)):
    ep = episodes(fl); half = ["H1" if h1[a] else "H2" for a, b, c in ep]
    FL[nm] = dict(episodes=[(str(vi[a].date()), str(vi[b].date()), c, h) for (a, b, c), h in zip(ep, half)],
                  ep_h1=half.count("H1"), ep_h2=half.count("H2"), sess_cal=(int(fl[h1].sum()), int(fl[h2].sum())),
                  sess_ep=(sum(c for (a, b, c), h in zip(ep, half) if h == "H1"), sum(c for (a, b, c), h in zip(ep, half) if h == "H2")))
    x = FL[nm]; x["ok"] = x["ep_h1"] >= 2 and x["ep_h2"] >= 2 and len(ep) >= 4 and min(x["sess_cal"] + x["sess_ep"]) >= 60
# reported
REP = {}
for (t, h), f in F.items():
    g = f.loc[vi]; dd = (g["dd"] <= -0.10).values.astype(float); up = (g["up"] >= 0.10).values.astype(float)
    REP[(t, h)] = dict(dd=ratio(D, dd), up=ratio(D, up), mean=(g["ret"][D].mean(), g["ret"][~D].mean()), med=(g["ret"][D].median(), g["ret"][~D].median()),
                       by={k: (dd[m].mean(), up[m].mean(), g["ret"].values[m].mean(), np.median(g["ret"].values[m]), int(m.sum())) for k, m in (("D", D), ("N", Nn), ("E", E))})
# W3 baselines
k = int(D.sum())
def ma(s, w): return s.rolling(w, min_periods=w).mean()
spy_g, iwm_g = A["SPY"] / ma(A["SPY"], 50) - 1, A["IWM"] / ma(A["IWM"], 50) - 1; B3 = BR["B3"].reindex(grid)
def kflag(s, lowest=True):
    x = s.loc[vi]; assert x.notna().all(), x.isna().sum(); o = x.sort_values(ascending=lowest, kind="mergesort").index[:k]; return pd.Series(vi.isin(o), vi).values
BK = {"B1 SPY trend": kflag(spy_g), "B4 IWM trend": kflag(iwm_g), "B2 VIX": kflag(VIX, False)}
b3v = B3.loc[vi]; b3ok = b3v.notna().values
BK["B3 breadth"] = kflag(B3.fillna(np.inf)) if not b3ok.all() else kflag(B3)
def rule(X):
    m20, m50 = ma(X, 20), ma(X, 50); return ((X > m20) & (m20 > m50)).loc[vi].values, (m20 > m50).loc[vi].values, int(m50.loc[vi].isna().sum())
SR = {"B1 SPY falling": rule(-A["SPY"]), "B4 IWM falling": rule(-A["IWM"]), "B2 VIX rising": rule(VIX), "B3 breadth falling": rule(-B3)}
W3 = {"k": k, "kmatched": {nm: ratio(f) for nm, f in BK.items()}, "same": {nm: (ratio(c), ratio(t), miss) for nm, (c, t, miss) in SR.items()}}
vmed = VIX.rolling(252, min_periods=252).median(); quiet = (VIX < vmed).loc[vi].values; assert vmed.loc[vi].notna().all()
W3["quiet"] = (ratio(D, mask=quiet), int(quiet.sum()), int((D & quiet).sum()))
neg = (b3v < 0).values; pos = (b3v >= 0).values
W3["bneg"] = (ratio(D, mask=neg), int(neg.sum()), int((D & neg).sum())); W3["bpos"] = (ratio(D, mask=pos), int(pos.sum()), int((D & pos).sum()))
W3["overlap"] = float((D & BK["B3 breadth"]).sum() / k)
Dfull = (ST == "D")
W3["lag"] = {L: ratio(Dfull.shift(L).fillna(False).loc[vi].values.astype(bool)) for L in (5, 10)}
# lead and recovery (mechanical SPY episodes)
spy = A["SPY"]; hi = spy.rolling(252, min_periods=252).max(); under = spy <= 0.93 * hi; b1full = pd.Series(False, grid); b1full.loc[vi] = BK["B1 SPY trend"]
LR = []; i = grid.get_loc(VS); gl = len(grid)
while i < gl:
    if under.iloc[i] and grid[i] <= VE:
        on = i; j = on
        while j < gl and not (spy.iloc[j] >= 0.97 * hi.iloc[on]): j += 1
        low = on + int(np.argmin(spy.iloc[on:j].values)) if j > on else on
        def lead(fl):
            w = fl.iloc[max(0, on - 63):on + 1].values; z = np.flatnonzero(w); return int(len(w) - 1 - z[0]) if len(z) else None
        t = low
        while t < gl and Dfull.iloc[t]: t += 1
        LR.append(dict(onset=str(grid[on].date()), low=str(grid[low].date()), recovered=str(grid[j].date()) if j < gl else "not by 2024-12-31", lead_draining=lead(Dfull), lead_B1=lead(b1full),
                       draining_at_low=bool(Dfull.iloc[low]), low_to_leaving_draining=int(t - low)))
        i = j + 1
    else: i += 1
fr = pd.DataFrame({"state": st, "event_iwm63": ev, "iwm_dd63": F[("IWM", 63)]["dd"].loc[vi], "vix": VIX.loc[vi], "quiet": quiet, "B3": b3v, "spy_gap": spy_g.loc[vi], "iwm_gap": iwm_g.loc[vi]})
for nm, f in BK.items(): fr["k_" + nm.split()[0]] = f
for nm, (c, t, m) in SR.items(): fr["sc_" + nm.split()[0]] = c; fr["st_" + nm.split()[0]] = t
fr.to_csv(f"{O}/w2_w3_frame.csv")
# ---------------- print ----------------
P = print; pc = lambda x: f"{x*100:.1f}%"
def rr(r): return f"ratio {r[0]:.2f} = {pc(r[1])} (n={r[3]}) vs {pc(r[2])} (n={r[4]})"
P(f"validation window {VS.date()} -> {VE.date()} n={n}; Draining {int(D.sum())}, Neutral {int(Nn.sum())}, Easing {int(E.sum())}; base rate of a 10% IWM drop within 63 sessions: {pc(e.mean())} (n={n})")
P("\nW2 FORWARD RISK (IWM lowest adjusted close over the next 63 sessions at least 10% below the day's close)")
a_ok = R["a"][0] >= 1.5; P(f"  (a) Draining vs other: {rr(R['a'])}; bar >= 1.5 -> {'PASS' if a_ok else 'FAIL'}")
b = R["b"]; b_ct = b["dropped"] > 500; b_ok = (b["lo"] > 0 or b["hi"] < 0) and b["lo"] > 0 and not b_ct
P(f"  (b) quarter-block bootstrap ({b['blocks']} quarters, 10,000 resamples, {b['dropped']} dropped): 95% interval of the difference {b['lo']*100:+.1f} to {b['hi']*100:+.1f} points; bar excludes 0 -> {'CANNOT TELL' if b_ct else ('PASS' if b_ok else 'FAIL')}")
b2 = R["b2"]; b2_ok = R["a"][0] > b2["p95"]; P(f"  (b2) circular shift ({b2['n']} offsets): shifted ratios median {b2['median']:.2f}, 95th percentile {b2['p95']:.2f}; observed {R['a'][0]:.2f}; {pc(b2['share_ge'])} of shifts reach the observed ratio -> {'PASS' if b2_ok else 'FAIL'}")
c_ok = all(x[0] >= 1.2 for x in R["c"]); P(f"  (c) H1 (to 2020-12-31): {rr(R['c'][0])} | H2 (from 2021-01-04): {rr(R['c'][1])}; bar >= 1.2 in each -> {'PASS' if c_ok else 'FAIL'}")
d = R["d"]; d_ct = d[1] < 60 or d[3] < 60; d_ok = (d[0] <= d[2]) and not d_ct; P(f"  (d) press: Easing {pc(d[0])} (n={d[1]}) vs Neutral {pc(d[2])} (n={d[3]}); bar Easing <= Neutral -> {'CANNOT TELL' if d_ct else ('PASS' if d_ok else 'FAIL')}")
for nm in ("Draining", "Easing"):
    x = FL[nm]; P(f"  floor {nm}: merged episodes H1 {x['ep_h1']}, H2 {x['ep_h2']} (bar 2 each, 4 pooled); sessions by calendar date H1/H2 {x['sess_cal']}, inside episodes by assigned half {x['sess_ep']} (bar 60) -> {'met' if x['ok'] else 'NOT MET = cannot tell'}")
    for ep in x["episodes"]: P(f"      {ep[0]} -> {ep[1]} ({ep[2]} sessions in state) {ep[3]}")
fl_ok = FL["Draining"]["ok"] and FL["Easing"]["ok"]
w2 = "CANNOT TELL" if (not fl_ok or b_ct or d_ct) else ("PASS" if (a_ok and b_ok and b2_ok and c_ok and d_ok) else "FAIL")
if not (a_ok and b_ok and b2_ok and c_ok and (d_ok or d_ct)) : w2 = "FAIL" if fl_ok else "CANNOT TELL (floor) and bar parts failed"
P(f"  W2: {w2}")
P("\n  reported, not judged (10% drop share / 10% gain share / mean / median forward return; n):")
for (t, h), x in REP.items():
    P(f"   {t} {h} sessions: drop D vs other {rr(x['dd'])}; gain D vs other {rr(x['up'])}")
    for kk in "DNE": y = x["by"][kk]; P(f"       {kk}: drop {pc(y[0])} gain {pc(y[1])} mean {y[2]*100:+.1f}% median {y[3]*100:+.1f}% (n={y[4]})")
P(f"\nW3 BASELINES (same window; k = {k} flagged sessions for the k-matched forms)")
cr = R["a"][0]
for nm, r in W3["kmatched"].items(): P(f"  k-matched {nm}: {rr(r)} -> composite {cr:.2f} {'>=' if cr >= r[0] else '<'} baseline")
for nm, (c, t, miss) in W3["same"].items():
    for lab, r in (("combined rule", c), ("trend rule", t)):
        P(f"  same-rule {nm} [{lab}]: {rr(r)}" + (" (fewer than 60 flagged: not judged)" if r[3] < 60 else f" -> composite {cr:.2f} {'>=' if cr >= r[0] else '<'} baseline") + (f" [{miss} window sessions before the baseline's 50-day exists count as not flagged]" if miss else ""))
def ge(r): return r[3] < 60 or cr >= r[0]
a3 = cr >= W3["kmatched"]["B1 SPY trend"][0] and cr >= W3["kmatched"]["B4 IWM trend"][0] and all(ge(W3["same"][x][i]) for x in ("B1 SPY falling", "B3 breadth falling", "B4 IWM falling") for i in (0, 1))
qr, qn, qd = W3["quiet"]; esc = (qd >= 60) and qr[0] >= 1.3
b3_direct = cr >= W3["kmatched"]["B2 VIX"][0] and all(ge(W3["same"]["B2 VIX rising"][i]) for i in (0, 1)); b3ok_ = b3_direct or esc
P(f"  (a) vs SPY trend, IWM trend and the same-rule SPY / IWM / breadth forms -> {'PASS' if a3 else 'FAIL'}")
P(f"  (b) vs VIX: direct {'yes' if b3_direct else 'no'}; escape 'warns while VIX is quiet' (VIX below its trailing 252-session median, {qn} sessions, {qd} Draining): {rr(qr)}; bar >= 1.3 -> escape {'met' if esc else 'not met'} -> {'PASS' if b3ok_ else 'FAIL'}")
nr, nn_, nd = W3["bneg"]; pr, pn, pd_ = W3["bpos"]; c_ct = nd < 60; c3 = cr >= W3["kmatched"]["B3 breadth"][0] and nr[0] >= 1.25 and not c_ct
P(f"  (c) vs breadth: k-matched above; within breadth < 0 ({nn_} sessions, {nd} Draining): {rr(nr)}; bar >= 1.25 -> {'CANNOT TELL' if c_ct else ('PASS' if c3 else 'FAIL')}")
P(f"      breadth >= 0 stratum, not judged ({pn} sessions, {pd_} Draining): {rr(pr)}")
P(f"  W3: {'PASS' if (a3 and b3ok_ and c3) else ('CANNOT TELL' if (a3 and b3ok_ and c_ct and cr >= W3['kmatched']['B3 breadth'][0]) else 'FAIL')}")
P(f"\n  reported: Draining days also in the k-matched breadth flag: {pc(W3['overlap'])} (n={k}){'  <-- close to breadth by another name' if W3['overlap'] > .85 else ''}")
for L, r in W3["lag"].items(): P(f"  reported: state lagged {L} sessions: {rr(r)}" + ("  <-- below 1.2: 'coincident'" if (L == 10 and r[0] < 1.2) else ""))
P("  reported: lead and recovery (SPY 7% below its 252-session closing high = onset; sessions)")
for x in LR: P("     ", json.dumps(x))
json.dump(dict(a=R["a"], b=R["b"], b2=R["b2"], floor=FL, lead=LR), open(f"{O}/w2_w3_numbers.json", "w"), default=float, indent=1)
