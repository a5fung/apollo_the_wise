"""Adversarial review checks of build/run.py. $0, local. Era-B rows after 2024-12-31 dropped at read + asserted."""
import importlib.util, sys, gzip
from pathlib import Path
import numpy as np, pandas as pd
REPO = Path("/Users/alvinfung/apollo_the_wise"); sys.path.insert(0, str(REPO))
def _load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
f3 = _load("f3_def", REPO/"scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO/"scripts/probes/_533_nbis_structure_encoder.py")
D = "/Users/alvinfung/apollo_data"; CUT = "2024-12-31"
DAILY = {"A": f"{D}/cb702_pre_v2/daily_closes_all.csv.gz", "B": f"{D}/cb702/daily_closes_all.csv.gz"}
CAL = {"A": f"{D}/cb702_pre_v2/sessions.txt", "B": f"{D}/cb702/qm_streams/track_a_1023/spy_sessions_eraB_le_2024-12-31.txt"}
X = pd.read_csv(REPO/"scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz", sep="\t", keep_default_na=False,
                na_values={"dmin": [""], "tercile": [""], "big_winner": [""], "ret60": [""], "fail5": [""]})
for c in ("is_his_buy", "in_prereg6"): X[c] = X[c].astype(str) == "True"
need = {e: set(X[X.era == e].ticker) for e in "AB"}
cal = {e: np.array(sorted(l.strip() for l in open(CAL[e]) if l.strip())) for e in "AB"}
bars = {}
for e in "AB":
    parts = []; drop = 0
    for ch in pd.read_csv(DAILY[e], header=None, names=list("tdohlcv"), dtype={"t": str, "d": str}, keep_default_na=False, chunksize=2_000_000):
        if e == "B":
            m = ch.d <= CUT; drop += int((~m).sum()); ch = ch[m]
        parts.append(ch[ch.t.isin(need[e])])
    df = pd.concat(parts); assert e == "A" or df.d.max() <= CUT
    print(f"era {e} kept {len(df)} dropped>{CUT} {drop} max {df.d.max()}")
    df = df.sort_values(["t", "d"], kind="mergesort")
    for t, g in df.groupby("t", sort=False):
        bars[(e, t)] = list(zip(g.d, g.o, g.h, g.l, g.c, g.v))
def five(d):
    from datetime import date
    y, m, dd = map(int, d.split("-"))
    try: return date(y-5, m, dd).isoformat()
    except ValueError: return date(y-5, m, 28).isoformat()
def feat(days, ia):
    cut = five(days[ia][0]); lo = 0
    while lo < ia and days[lo][0] < cut: lo += 1
    sl = days[lo:ia+1]; j = len(sl)-1
    return f3.f3_new(sl, j, nbis.adr20_pct(sl, j), f3.STATED)["dmin"]
# (a) independent dmin recompute + E-bar perturbation (and append fake future bars) on a sample
rng = np.random.default_rng(7); S = X[X.dmin.notna()]; idx = rng.choice(len(S), 600, replace=False)
mism = pert = fut = 0
for k in idx:
    r = S.iloc[k]; b = bars[(r.era, r.ticker)]; dts = [x[0] for x in b]; i = dts.index(r.E)
    d0 = feat(b[:i+1], i)
    if abs(d0 - r.dmin) > 1e-9: mism += 1
    days = b[:i] + [(r.E, 999.0, 9999.0, 0.01, 5.0, 1e12)]
    if abs(feat(days, i) - d0) > 1e-9: pert += 1
print(f"(a) dmin recompute mismatches {mism}/600; changed by garbage E bar {pert}/600")
# (b)(e) forward-window: build calendar reading vs recount ticker-row reading
rows = []
for r in X[X.in_prereg6].itertuples():
    b = bars[(r.era, r.ticker)]; dts = [x[0] for x in b]; i = dts.index(r.E)
    iE = int(np.searchsorted(cal[r.era], r.E)); last = cal[r.era][iE+60]
    if r.era == "B": assert last <= CUT
    win = [x for x in b[i:] if x[0] <= last]
    mx = max(x[4] for x in win); bw = float(mx >= 1.5*b[i][1])
    assert bw == r.big_winner, (r.ticker, r.E)
    rows.append(dict(era=r.era, ticker=r.ticker, E=r.E, nwin=len(win), short=len(win) < 61, has60rows=(i+60 < len(b)), bw=bw))
F = pd.DataFrame(rows)
print(f"(b) PRE-REG6 pop {len(F)}: big_winner recomputed = build in all; windows with <61 bars {int(F.short.sum())} "
      f"(big rate {F[F.short].bw.mean():.3f} vs full {F[~F.short].bw.mean():.3f}); without 60 ticker rows after E {int((~F.has60rows).sum())}")
print("    era-B max calendar E+60:", max(cal['B'][int(np.searchsorted(cal['B'], e))+60] for e in X[X.in_prereg6 & (X.era=='B')].E))
# (d) recompute terciles/ratio/perm from build rows, plus recount's forward reading on the same code
def p6(T, label):
    T = T[T.dmin.notna()].copy(); mc = T.groupby("month").size(); T = T[T.month.isin(mc[mc >= 6].index)]
    T = T.sort_values(["month", "dmin", "ticker"], kind="mergesort").reset_index(drop=True)
    terc = np.empty(len(T), int); groups = []
    for m in T.month.unique():
        g = np.flatnonzero((T.month == m).values); groups.append(g)
        for k, part in enumerate(np.array_split(g, 3)): terc[part] = k
    bw = T.big_winner.values
    def rat(tc): return bw[tc == 2].mean() / bw[tc == 0].mean()
    obs = rat(terc); rg = np.random.default_rng(1121); ge = 0
    for _ in range(2000):
        tc = np.empty(len(T), int)
        for g in groups: tc[g] = terc[g][rg.permutation(len(g))]
        ge += rat(tc) >= obs
    era = {e: rat(np.where(T.era.values == e, terc, -1)) for e in "AB"}
    print(f"(d) {label}: n {len(T)} rates b/m/t {[round(bw[terc==k].mean(),3) for k in range(3)]} ratio {obs:.3f} p {(1+ge)/2001:.4f} "
          f"eraA {era['A']:.3f} eraB {era['B']:.3f} tercile-match-build {int((T.tercile.values == terc).sum()) if 'tercile' in T else ''}/{len(T)}")
P6 = X[X.in_prereg6]
p6(P6, "build reading")
keep = set(zip(F[F.has60rows].era, F[F.has60rows].ticker, F[F.has60rows].E))
p6(P6[[k in keep for k in zip(P6.era, P6.ticker, P6.E)]], "recount's drop of names without 60 ticker rows")
# (e) PRE-REG 7 literal variant (his-vs-his pairs included) on build population
B7 = X[X.dmin.notna()]
days = [(g.dmin.values, g.is_his_buy.values) for (e, E), g in B7.groupby(["era", "E"]) if g.is_his_buy.any() and len(g) > 1]
def stat(L, lit):
    s = n = 0.0
    for (d, _), h in zip(days, L):
        for i in np.flatnonzero(h):
            o = np.ones(len(d), bool); o[i] = False
            if not lit: o &= ~h
            s += (d[i] > d[o]).sum() + 0.5*(d[i] == d[o]).sum(); n += o.sum()
    return s/n, n
for lit in (False, True):
    P, n = stat([h for _, h in days], lit); rg = np.random.default_rng(1121)
    ge = sum(stat([h[rg.permutation(len(h))] for _, h in days], lit)[0] >= P for _ in range(2000))
    print(f"(e) PRE-REG7 {'literal incl his-vs-his' if lit else 'build (excl his-vs-his)'}: days {len(days)} P {P:.3f} pairs {int(n)} p {(1+ge)/2001:.4f}")
