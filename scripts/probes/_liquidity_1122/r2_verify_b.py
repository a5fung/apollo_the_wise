"""r2_verify_b: INDEPENDENT recount of W2 and W3 for run 2. Inputs: my own composite + adjusted ETF closes (r2_verify_a outputs),
FRED VIXCLS, and breadth REBUILT from the raw cb702 / cb702_pre_v2 daily closes (awk cut <= 2024-12-31 in the stream).
Never runs any r2_*.py; reads build_r2 frames only to compare. Writes only to the scratchpad dir given as argv[1]."""
import pandas as pd, numpy as np, os, sys, subprocess
CUT = pd.Timestamp("2024-12-31"); HERE = os.path.dirname(os.path.abspath(__file__)); OUT = sys.argv[1]; D = os.path.expanduser("~/apollo_data")
P = print
ST = pd.read_csv(f"{OUT}/my_composite.csv", index_col=0, parse_dates=True)["state"]
A = pd.read_csv(f"{OUT}/my_adj.csv", index_col=0, parse_dates=True); assert A.index.max() <= CUT
grid = A.index; ng = len(grid); ST = ST.reindex(grid)
VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27"); vi = grid[(grid >= VS) & (grid <= VE)]; n = len(vi); assert n == 1937
assert grid.get_loc(VE) + 63 <= ng - 1

# ---------------- forward statistic, own loop ----------------
def fwd_min(px, h):
    a = px.values; o = np.full(ng, np.nan)
    for i in range(ng - h): o[i] = a[i + 1:i + 1 + h].min() / a[i] - 1
    return pd.Series(o, grid)
dd = fwd_min(A["IWM"], 63); ev = (dd.loc[vi] <= -0.10).values.astype(float); assert not np.isnan(dd.loc[vi]).any()
st = ST.loc[vi].values; Dm, Em, Nm = st == "D", st == "E", st == "N"
def rat(flag, x=ev):
    a, b = x[flag].mean(), x[~flag].mean(); return a / b, a, b, int(flag.sum()), int((~flag).sum())
r_a = rat(Dm); P(f"W2 base rate {ev.mean()*100:.1f}% (n={n}); (a) ratio {r_a[0]:.3f} = {r_a[1]*100:.1f}% (n={r_a[3]}) vs {r_a[2]*100:.1f}% (n={r_a[4]})")
# (b) quarter-block bootstrap, own draw (blocks drawn via Generator.choice, seed 1)
q = pd.Series(pd.PeriodIndex(vi, freq="Q").astype(str), index=vi); blocks = q.unique()
agg = pd.DataFrame({"q": q.values, "dn": Dm.astype(int), "de": Dm * ev, "on": (~Dm).astype(int), "oe": (~Dm) * ev}).groupby("q").sum().loc[blocks].values
rng = np.random.default_rng(1); difs = []; drop = 0
for _ in range(10000):
    s = agg[rng.choice(len(blocks), len(blocks), replace=True)].sum(axis=0)
    if s[0] == 0 or s[2] == 0: drop += 1; continue
    difs.append(s[1] / s[0] - s[3] / s[2])
lo, hi = np.percentile(difs, [2.5, 97.5]); P(f"(b) {len(blocks)} quarters, dropped {drop}: 95% interval {lo*100:+.1f} to {hi*100:+.1f} points")
# (b2) circular shift
sh = []
for off in range(126, n - 126 + 1):
    d2 = np.concatenate([Dm[-off:], Dm[:-off]]); b = ev[~d2].mean(); sh.append(ev[d2].mean() / b if b > 0 else np.inf)
sh = np.array(sh); P(f"(b2) {len(sh)} offsets; 95th pct {np.percentile(sh,95):.3f}; median {np.median(sh):.3f}; observed {r_a[0]:.3f}")
h1 = vi <= pd.Timestamp("2020-12-31"); h2 = ~h1
for lab, m in (("H1", h1), ("H2", h2)):
    r = rat(Dm[m], ev[m]); P(f"(c) {lab}: ratio {r[0]:.3f} = {r[1]*100:.1f}% (n={r[3]}) vs {r[2]*100:.1f}% (n={r[4]})")
P(f"(d) Easing {ev[Em].mean()*100:.1f}% (n={Em.sum()}) vs Neutral {ev[Nm].mean()*100:.1f}% (n={Nm.sum()})")
# Easing drop days by spell
s = pd.Series(st, vi); e_ = pd.Series(ev, vi); g = (s != s.shift()).cumsum()
P("   Easing spells with a following 10% IWM drop (spell: drop days / spell days):")
for _, x in s.groupby(g):
    if x.iloc[0] == "E" and e_.loc[x.index].sum() > 0: P(f"     {x.index[0].date()} -> {x.index[-1].date()}: {int(e_.loc[x.index].sum())} / {len(x)}")
tot = int(e_[s == "E"].sum()); covid = int(e_[(s == "E") & (s.index >= "2019-12-01") & (s.index <= "2020-02-28")].sum())
P(f"   Easing drop days total {tot}; of which Dec-2019..Feb-2020 (pre-Covid) {covid}; Easing share without them {(tot-covid)/(Em.sum()-int(((s=='E')&(s.index>='2019-12-01')&(s.index<='2020-02-28')).sum()))*100:.1f}%")
# floor
def eps(flag):
    rr = []; i = 0
    while i < n:
        if flag[i]:
            j = i
            while j + 1 < n and flag[j + 1]: j += 1
            if j - i + 1 >= 5: rr.append([i, j, j - i + 1])
            i = j + 1
        else: i += 1
    m = []
    for r in rr:
        if m and r[0] - m[-1][1] - 1 < 63: m[-1][1] = r[1]; m[-1][2] += r[2]
        else: m.append(r)
    return m
for nm, fl in (("Draining", Dm), ("Easing", Em)):
    m = eps(fl); hh = ["H1" if h1[a] else "H2" for a, b, c in m]
    P(f"floor {nm}: episodes H1 {hh.count('H1')} H2 {hh.count('H2')} pooled {len(m)}; sessions H1 {int(fl[h1].sum())} H2 {int(fl[h2].sum())}")
# reported
for t, h in (("SPY", 63), ("QQQ", 63), ("IWM", 21)):
    x = (fwd_min(A[t], h).loc[vi] <= -0.10).values.astype(float); r = rat(Dm, x); P(f"reported {t} {h}: ratio {r[0]:.2f}")

# ---------------- breadth from raw ----------------
cs = sorted(set(l.split("|")[0] for l in open(f"{D}/cb702/cb702_sic.psv") if l.rstrip("\n").split("|")[-1] == "CS"))
P(f"\nCS tickers {len(cs)}")
cache = f"{OUT}/raw_cs.csv.gz"
if not os.path.exists(cache):
    tl = f"{OUT}/cs_list.txt"; open(tl, "w").write("\n".join(cs) + "\n")
    with open(f"{OUT}/raw_cs.csv", "w") as fh:
        for src in ("cb702_pre_v2", "cb702"):
            cmd = f"gzcat {D}/{src}/daily_closes_all.csv.gz | awk -F, -v s={src} 'NR==FNR{{k[$1]=1;next}} ($2<=\"2024-12-31\") && ($1 in k) {{print s\",\"$1\",\"$2\",\"$6\",\"$7}}' {tl} -"
            r = subprocess.run(cmd, shell=True, stdout=fh, text=True); assert r.returncode == 0
    subprocess.run(f"gzip -f {OUT}/raw_cs.csv", shell=True, check=True)
U = pd.read_csv(cache, names=["src", "t", "d", "c", "v"], parse_dates=["d"], dtype={"t": str}); assert U.d.max() <= CUT
P(f"raw universe rows {len(U)}, tickers {U.t.nunique()}")
bu = pd.read_csv(f"{HERE}/build_r2/universe_cs_closes.csv.gz", names=["src", "t", "d", "c", "v"], parse_dates=["d"], dtype={"t": str})
P(f"builder extract rows {len(bu)}, tickers {bu.t.nunique()}; row-for-row identical to mine: {len(bu)==len(U) and bool((bu.sort_values(['src','t','d']).reset_index(drop=True)[['src','t','c']].astype(str).values == U.sort_values(['src','t','d']).reset_index(drop=True)[['src','t','c']].astype(str).values).all()) if len(bu)==len(U) else False}")
del bu
def piv(src, col): return U[U.src == src].drop_duplicates(["t", "d"], keep="last").pivot(index="d", columns="t", values=col)
c1, v1, c2, v2 = piv("cb702_pre_v2", "c"), piv("cb702_pre_v2", "v"), piv("cb702", "c"), piv("cb702", "v")
SPL = pd.Timestamp("2022-06-30"); cols = c1.columns.union(c2.columns)
ov = c1.index.intersection(c2.index); both = c1.columns.intersection(c2.columns)
ratio = (c2.loc[ov, both] / c1.loc[ov, both])
def build(variant):
    med = ratio.median(); spread = ratio.max() / ratio.min() - 1
    unst = spread > 0.02; resc = (abs(med - 1) > 0.005) & ~unst
    fac = pd.Series(1.0, cols)
    if variant in ("spec", "no_drop"): fac[med[resc].index] = 1 / med[resc]
    post = c2.loc[c2.index > SPL].reindex(columns=cols).mul(fac, axis=1)
    if variant in ("spec", "no_rescale"): post.loc[:, unst[unst].index] = np.nan
    C = pd.concat([c1.reindex(columns=cols), post]).reindex(grid)
    DV = pd.concat([(c1 * v1).reindex(columns=cols), (c2 * v2).loc[c2.index > SPL].reindex(columns=cols)]).reindex(grid)
    a = C.values; dv = DV.values; N_ = np.zeros(ng); Hh = np.zeros(ng); Ll = np.zeros(ng)
    dv20 = pd.DataFrame(dv).rolling(20, min_periods=20).mean().values
    for i in range(252, ng):
        w = a[i-252:i]; full = ~np.isnan(w).any(axis=0); mx = np.nanmax(np.where(np.isnan(w), -np.inf, w), axis=0); mn = np.nanmin(np.where(np.isnan(w), np.inf, w), axis=0)
        el = full & (a[i] >= 5) & (dv20[i] >= 5e6)
        N_[i] = el.sum(); Hh[i] = (el & (a[i] > mx)).sum(); Ll[i] = (el & (a[i] < mn)).sum()
    b = pd.Series(np.where(N_ > 0, (Hh - Ll) / np.maximum(N_, 1), np.nan), grid)
    return b.rolling(10, min_periods=10).mean(), int(unst.sum()), int(resc.sum())
BRb = pd.read_csv(f"{HERE}/build_r2/breadth.csv", index_col=0, parse_dates=True)["B3"].reindex(grid)
B3s = {}
for var in ("spec", "no_rescale", "no_drop"):
    B3s[var], nu, nr = build(var); d = (B3s[var].loc[vi] - BRb.loc[vi]).abs()
    P(f"breadth variant {var}: unstable {nu} rescaled {nr}; vs builder B3 max abs diff {d.max():.2e}, days differing > 1e-9: {int((d > 1e-9).sum())}")

# ---------------- W3 ----------------
vx = pd.read_csv(f"{HERE}/fred/VIXCLS.csv"); vx.columns = ["d", "v"]; vx["d"] = pd.to_datetime(vx.d); vx["v"] = pd.to_numeric(vx.v, errors="coerce"); vx = vx[vx.d <= CUT].dropna()
VIX = vx.set_index("d")["v"].reindex(grid, method=None).ffill()
k = int(Dm.sum()); cr = r_a[0]
def kf(s, low=True):
    x = s.loc[vi]; order = sorted(range(n), key=lambda i: ((x.iloc[i] if low else -x.iloc[i]), i)); f = np.zeros(n, bool); f[order[:k]] = True; return f
sg = A["SPY"] / A["SPY"].rolling(50).mean() - 1; ig = A["IWM"] / A["IWM"].rolling(50).mean() - 1
def same(X):
    m20, m50 = X.rolling(20).mean(), X.rolling(50).mean(); return {"combined": ((X > m20) & (m20 > m50)).loc[vi].values, "trend": (m20 > m50).loc[vi].values}
for var, B3 in B3s.items():
    out = [f"\nW3 with breadth variant '{var}' (composite ratio {cr:.3f}):"]
    base = {"B1 SPY k": kf(sg), "B4 IWM k": kf(ig), "B2 VIX k": kf(VIX, False), "B3 breadth k": kf(B3)}
    for nm, X in (("B1 SPY", -A["SPY"]), ("B4 IWM", -A["IWM"]), ("B2 VIX", VIX), ("B3 breadth", -B3)):
        for f, fl in same(X).items(): base[f"{nm} same-{f}"] = fl
    for nm, fl in base.items():
        r = rat(fl); out.append(f"   {nm}: ratio {r[0]:.3f} (flagged n={r[3]}) -> composite {'>=' if cr >= r[0] else '<'}")
    vmed = VIX.rolling(252, min_periods=252).median(); quiet = (VIX < vmed).loc[vi].values
    r = rat(Dm[quiet], ev[quiet]); out.append(f"   quiet-VIX: ratio {r[0]:.3f} (D n={r[3]}, rest n={r[4]})")
    neg = (B3.loc[vi] < 0).values; r = rat(Dm[neg], ev[neg]); out.append(f"   W3(c) breadth<0: {int(neg.sum())} sessions, ratio {r[0]:.4f} = {r[1]*100:.1f}% (n={r[3]}) vs {r[2]*100:.1f}% (n={r[4]}) -> {'PASS' if r[0] >= 1.25 else 'FAIL'} at 1.25")
    pos = ~neg; r = rat(Dm[pos], ev[pos]); out.append(f"   breadth>=0 (not judged): ratio {r[0]:.2f} (D n={r[3]})")
    out.append(f"   overlap Draining with k-matched breadth flag: {(Dm & base['B3 breadth k']).sum()/k*100:.1f}%")
    P("\n".join(out))
Dfull = (ST == "D")
for L in (5, 10):
    fl = Dfull.shift(L, fill_value=False).loc[vi].values.astype(bool); r = rat(fl); P(f"lag {L}: ratio {r[0]:.2f} (n={r[3]})")
# compare builder frame
fr = pd.read_csv(f"{HERE}/build_r2/w2_w3_frame.csv", index_col=0, parse_dates=True)
P(f"\nbuilder frame event column vs mine: {int((fr['event_iwm63'].astype(bool).values != ev.astype(bool)).sum())} days differ; state column differs {int((fr['state'].values != st).sum())}")
for c, mine in (("k_B1", kf(sg)), ("k_B4", kf(ig)), ("k_B2", kf(VIX, False)), ("k_B3", kf(B3s['spec']))):
    P(f"  {c}: flags differ on {int((fr[c].astype(bool).values != mine).sum())} days")
