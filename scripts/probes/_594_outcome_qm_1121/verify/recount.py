"""Independent recount of PRE-REG 6 + 7 (ep_rank_v2_prereg_2026-11-03.md). $0, local, sealed-data dropped at read."""
import importlib.util, sys, bisect, gzip
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date
import numpy as np, pandas as pd
REPO = Path("/Users/alvinfung/apollo_the_wise"); sys.path.insert(0, str(REPO))
def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
f3 = _load("f3_def", REPO/"scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO/"scripts/probes/_533_nbis_structure_encoder.py")
from tests.fixtures.must_not_trade_charts import CHART_RULINGS, GOOD_CHART, OKISH_CHART
DATA = "/Users/alvinfung/apollo_data"; EV = f"{DATA}/cb702/qm_streams/ep_join_1023"
CUT = "2024-12-31"; SEED = 1121; NPERM = 2000

def five_years_before(d):
    try: return d.replace(year=d.year-5).isoformat()
    except ValueError: return d.replace(year=d.year-5, day=28).isoformat()
def slice5(rows, dates, d):
    ia_full = bisect.bisect_left(dates, d)
    assert ia_full < len(dates) and dates[ia_full] == d
    lo = bisect.bisect_left(dates, five_years_before(date.fromisoformat(d)))
    return rows[lo:ia_full+1], ia_full
def feat(rows, dates, d):
    sl, ia_full = slice5(rows, dates, d); ia = len(sl)-1
    adr = nbis.adr20_pct(sl, ia); return f3.f3_new(sl, ia, adr)["dmin"]

# ---- loader check on sample 10
def read_bars(path):
    into = {}; cur = None
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("== "):
            t, d = line[3:].split(); cur = (t, d); into[cur] = []
        elif cur and line and line[0].isdigit() and "|" in line:
            td, o, h, l, c, v = line.split("|"); into[cur].append((td, float(o), float(h), float(l), float(c), float(v)))
    return into
b10 = read_bars(REPO/"scripts/probes/_594_sample10_1121/q2_bars.out")
rows10 = [r for r in CHART_RULINGS if r.ruling_date == "2026-11-21"]
sc = []
for r in rows10:
    days = b10[(r.ticker, r.alert_date)]; dates = [x[0] for x in days]
    sc.append((r.verdict in (GOOD_CHART, OKISH_CHART), feat(days, dates, r.alert_date)))
Y = [d for y, d in sc if y and d is not None]; N = [d for y, d in sc if not y and d is not None]
pairs = [(y, n) for y in Y for n in N]
P10 = sum(1.0 if y > n else 0.5 if y == n else 0.0 for y, n in pairs)/len(pairs)
print(f"LOADER CHECK sample 10: yes={len(Y)} no={len(N)} pairs={len(pairs)} P={P10:.3f}")
assert abs(P10-0.750) < 5e-4 and len(pairs) == 28, "loader check failed"

# ---- events
ev = []
for era in "AB":
    e = pd.read_csv(f"{EV}/ep_events_{era}.tsv.gz", sep="\t", keep_default_na=False, dtype=str)
    n0 = len(e); e = e[e.primary == "True"].copy(); e["era"] = era
    print(f"era {era}: rows {n0}, primary {len(e)}")
    if era == "B":
        late = (e.E > CUT).sum(); print(f"  era-B primary rows dated after {CUT} dropped at read: {late}")
        e = e[e.E <= CUT]
        late2 = (e.E > "2024-09-30").sum(); print(f"  era-B primary E in (2024-09-30, {CUT}] dropped (60-session window): {late2}")
        e = e[e.E <= "2024-09-30"]
    ev.append(e)
ev = pd.concat(ev, ignore_index=True)
assert ev.E.max() <= "2024-09-30"
nflag = ((ev.flag_adj == "True") | (ev.flag_adj_Dm1 == "True"))
print(f"primary events (pre-drop): {len(ev)}; flag_adj/flag_adj_Dm1 dropped: {int(nflag.sum())}")
ev = ev[~nflag].reset_index(drop=True)
print(f"AMBIGUITY: {int(ev.duplicated(['ticker','E'],keep=False).sum())} rows share (ticker,E) across eras A/B (overlap 2021-10..2022-06); kept literally (both eras); era-B copies have <250 sessions of history so are NULL-dmin and drop from scoring")

# ---- bars
bars = {}
for era in "AB":
    tick = set(ev[ev.era == era].ticker) | set(pd.read_csv(f"{DATA}/cb702/qm_streams/holdings_1024/entries.tsv", sep="\t", keep_default_na=False, dtype=str).sym)
    path = f"{DATA}/cb702_pre_v2/daily_closes_all.csv.gz" if era == "A" else f"{DATA}/cb702/daily_closes_all.csv.gz"
    parts = []; dropped = 0
    for ch in pd.read_csv(path, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str}, keep_default_na=False, chunksize=2_000_000):
        m = ch.d <= CUT; dropped += int((~m).sum()); ch = ch[m & ch.t.isin(tick)]; parts.append(ch)
    df = pd.concat(parts); assert df.d.max() <= CUT
    print(f"bars era {era}: rows kept {len(df)}, rows after {CUT} dropped at read {dropped}, max date {df.d.max()}")
    df = df.sort_values(["t", "d"], kind="mergesort"); bars[era] = {}
    for t, g in df.groupby("t", sort=False):
        bars[era][t] = ([tuple(x) for x in zip(g.d, g.o, g.h, g.l, g.c, g.v)], list(g.d))

# ---- feature + outcome
recs = []; nobars = 0; nofwd = 0
for r in ev.itertuples():
    b = bars[r.era].get(r.ticker)
    if b is None or r.E not in set(b[1]) and bisect.bisect_left(b[1], r.E) >= len(b[1]) or (b is not None and b[1][bisect.bisect_left(b[1], r.E)] != r.E):
        nobars += 1; continue
    rows, dates = b; dm = feat(rows, dates, r.E); i = bisect.bisect_left(dates, r.E)
    out = dict(ticker=r.ticker, E=r.E, era=r.era, sectype=r.sectype or "UNKNOWN", dmin=dm, month=r.E[:7], year=r.E[:4])
    if i+60 < len(rows):
        o = rows[i][1]; mx = max(x[4] for x in rows[i:i+61]); out.update(big=int(mx >= 1.5*o), ret60=rows[i+60][4]/o-1, early=int(rows[i+5][4] < o))
        out['span_gap'] = int((date.fromisoformat(rows[i+60][0])-date.fromisoformat(r.E)).days > 110)
    else: nofwd += 1; out.update(big=None, ret60=None, early=None)
    recs.append(out)
D = pd.DataFrame(recs)
print(f"events with no bar on E: {nobars}; events without 60 forward sessions (dropped from outcome): {nofwd}")
D = D[D.big.notna()].copy(); D["big"] = D.big.astype(int)
print(f"forward windows spanning >110 calendar days (bar gaps; kept): {int(D.get('span_gap', pd.Series(dtype=float)).sum())}")
print(f"event population after drops (flag, no-bar, no-forward): {len(D)}")
print("events per year:", dict(sorted(Counter(D.year).items())))
print("per sectype:", dict(Counter(D.sectype)))
nul = D[D.dmin.isna()]; sc_ = D[D.dmin.notna()]
print(f"NULL-dmin: {len(nul)} (big-winner rate {nul.big.mean():.3f}); scored: {len(sc_)} (big-winner rate {sc_.big.mean():.3f})")
print("NULL by year:", dict(sorted(Counter(nul.year).items())), " by era:", dict(Counter(nul.era)))
S = sc_.copy()
mc = S.groupby("month").size(); keep = mc[mc >= 6].index
print(f"months with >=6 scored: {len(keep)} of {len(mc)}; events in dropped months: {int(mc[mc < 6].sum())}")
S = S[S.month.isin(keep)].sort_values(["month", "dmin", "ticker"], kind="mergesort").reset_index(drop=True)
S["pos"] = S.groupby("month").cumcount(); S["n"] = S.groupby("month").month.transform("size")
S["terc"] = (3*S.pos//S.n).astype(int)   # 0 bottom (lowest dmin) .. 2 top (highest = closest to/above shelf)
def ratio(big, terc):
    t = big[terc == 2].mean(); b = big[terc == 0].mean(); return t, b, (t/b if b > 0 else float("inf"))
def tab(df, label):
    t, b, r = ratio(df.big.values, df.terc.values); m = df[df.terc == 1].big.mean()
    print(f"{label}: n={len(df)} bottom {b:.3f} (n={int((df.terc==0).sum())}) mid {m:.3f} top {t:.3f} (n={int((df.terc==2).sum())}) ratio top/bottom {r:.3f}")
    return r
r_all = tab(S, "ALL")
rA = tab(S[S.era == "A"], "era A"); rB = tab(S[S.era == "B"], "era B")
for y, g in S.groupby("year"): tab(g, f"year {y}")
rng = np.random.default_rng(SEED)
groups = [np.flatnonzero((S.month == m).values) for m in keep]
big = S.big.values.copy(); terc = S.terc.values; cnt = 0; infs = 0
for _ in range(NPERM):
    pb = big.copy()
    for ix in groups: pb[ix] = big[rng.permutation(ix)]
    t, b, r = ratio(pb, terc); cnt += (r >= r_all - 1e-12)
print(f"permutation (within-month, {NPERM} shuffles, seed {SEED}; shuffle outcomes across fixed dmin ranks = shuffle dmin): p = {cnt/NPERM:.4f}  [(k+1)/(N+1) = {(cnt+1)/(NPERM+1):.4f}]")
print(f"SECONDARY: mean ret60 by tercile {[round(S[S.terc==k].ret60.mean(),3) for k in range(3)]}; early-loss rate {[round(S[S.terc==k].early.mean(),3) for k in range(3)]}")
print("BAR1 ratio>=1.5:", r_all >= 1.5, "| era A ratio>1:", rA > 1, "| era B ratio>1:", rB > 1)

# ---- PRE-REG 7
E7 = pd.read_csv(f"{DATA}/cb702/qm_streams/holdings_1024/entries.tsv", sep="\t", keep_default_na=False, dtype=str)
H = E7[E7.setup.isin(["EP", "both"]) & (E7.flicker == "False") & (E7.has_bars == "True")]
print(f"\nPRE-REG 7: his EP/both, non-flicker, has_bars: {len(H)}")
assert H.E.max() <= "2024-09-30"
allp = pd.concat([ev]).set_index(["ticker", "E"]).index   # primary events incl. flagged
matched = [(r.sym, r.E) for r in H.itertuples() if (r.sym, r.E) in allp]
print(f"matched to a primary event (ticker,E): {len(matched)} of {len(H)}; unmatched: {[(r.sym, r.E) for r in H.itertuples() if (r.sym, r.E) not in allp]}")
print("(note: the primary list used here already excludes flag_adj events; matching vs the unfiltered list:)")
raw_ev = pd.concat([pd.read_csv(f"{EV}/ep_events_{e}.tsv.gz", sep="\t", keep_default_na=False, dtype=str).query("primary=='True'") for e in "AB"])
rawidx = set(zip(raw_ev.ticker, raw_ev.E)); print(f"  matched vs unfiltered primary list: {sum((r.sym, r.E) in rawidx for r in H.itertuples())}")
his = set(matched)
Dd = D.copy(); Dd["his"] = [(t, e) in his for t, e in zip(Dd.ticker, Dd.E)]
hs = Dd[Dd.his & Dd.dmin.notna() | (Dd.his & ~Dd.duplicated(["ticker","E"],keep=False))]; print(f"his buys in outcome population: {len(hs)}; with non-NULL dmin: {int(hs.dmin.notna().sum())}; NULL dmin: {[(a,b) for a,b in zip(hs[hs.dmin.isna()].ticker, hs[hs.dmin.isna()].E)]}")
Sc = Dd[Dd.dmin.notna()]
byday = {e: g for e, g in Sc.groupby("E")}
def stat(label_sets, literal=True):
    num = 0.0; n = 0; days_used = 0
    for e, g in byday.items():
        h = [i for i, x in enumerate(g.index) if label_sets(e, g, i)]
        if not h: continue
        d = g.dmin.values; hmask = np.zeros(len(g), bool); hmask[h] = True
        tot = 0.0; k = 0
        for i in h:
            for j in range(len(g)):
                if j == i or (not literal and hmask[j]): continue
                tot += 1.0 if d[i] > d[j] else 0.5 if d[i] == d[j] else 0.0; k += 1
        if k: num += tot; n += k; days_used += 1
    return num/n if n else float("nan"), n, days_used
for literal in (True, False):
    P7, npairs, ndays = stat(lambda e, g, i: (g.ticker.values[i], e) in his, literal)
    # permutation: within day, shuffle which events carry the "his" label
    rng = np.random.default_rng(SEED); cnt = 0
    days = [(e, g) for e, g in byday.items() if g.his.any()]
    for _ in range(NPERM):
        lab = {e: rng.permutation(g.his.values) for e, g in days}
        num = 0.0; n = 0
        for e, g in days:
            L = lab[e]; d = g.dmin.values; h = np.flatnonzero(L)
            for i in h:
                for j in range(len(g)):
                    if j == i or (not literal and L[j]): continue
                    num += 1.0 if d[i] > d[j] else 0.5 if d[i] == d[j] else 0.0; n += 1
        cnt += (num/n if n else 0) >= P7 - 1e-12
    tag = "LITERAL (others = every other primary event incl. his other buys)" if literal else "VARIANT (others exclude his other buys)"
    print(f"{tag}: within-day P={P7:.3f} over {npairs} pairs on {ndays} days; permutation p={cnt/NPERM:.4f} [(k+1)/(N+1)={(cnt+1)/(NPERM+1):.4f}]; bar P>=0.60 & p<=0.05")
alone = [e for e, g in Dd[Dd.his].groupby("E") if len(byday.get(e, [])) <= 1]
print(f"his-buy days with no scored other event (dropped): {len(alone)}")
# percentile within own month (among all scored events that month, same month set as PRE-REG6 incl. <6 months)
mon = {m: g.dmin.values for m, g in Sc.groupby("month")}
pc = []
for r in Sc[Sc.his].itertuples():
    a = mon[r.month]; pc.append((np.sum(a < r.dmin)+0.5*np.sum(a == r.dmin))/len(a))
print(f"his buys' dmin percentile within month: n={len(pc)} mean {np.mean(pc):.3f} median {np.median(pc):.3f}")
print(f"his buys big winners (PRE-REG 6 def): {int(hs.big.sum())} of {len(hs)} ({hs.big.mean():.3f}); all-scored-event base rate {Sc.big.mean():.3f}")
