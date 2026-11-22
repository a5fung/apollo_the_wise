#!/usr/bin/env python3
"""#594 PRE-REGISTRATIONS 6 + 7 (docs/analysis/ep_rank_v2_prereg_2026-11-03.md, written 2026-11-21 before any outcome was read).

PRE-REG 6: does the shelf distance (dmin) pick EPs that work (big winner = max close E..E+60 >= 1.5 x open(E))?
PRE-REG 7: do Qullamaggie's EP buys sit nearer the shelf than the other EPs of the same morning?

$0, local files only. No network / DB / subagent. Feature code IMPORTED (never copied):
  f3_def.py::f3_new with STATED, _533_nbis_structure_encoder.adr20_pct.

APPLIED READINGS (fixed in this header BEFORE the first run; each is a reading of a prereg sentence, not a new rule):
 R1 eras are never stitched: an era-A event reads only cb702_pre_v2/daily_closes_all.csv.gz, an era-B event only
    cb702/daily_closes_all.csv.gz ("Bars from the same adjusted daily files and loaders 01_ep_join.py uses"). Every era-B row
    dated after 2024-12-31 is dropped at read and asserted. The era-A file ends 2022-06-30.
 R2 forward window = CALENDAR sessions of the event's era calendar: ci in [iE, iE+60]. Big winner = max close over the
    ticker's bars inside that window >= 1.5 x open(E). ret60 needs a bar at exactly iE+60, fail5 a bar at exactly iE+5; else
    NaN, counted. The 60-session window must exist on the era file: era B E <= 2024-09-30 (the prereg's own rule, asserted
    cal_B[iE+60] <= 2024-12-31); era A events whose iE+60 lies past the A file's last session are dropped and counted, as the
    mirror of "E <= 2024-09-30 so the 60-session forward window never crosses that date". Applies to PRE-REG 6 only.
 R3 terciles: within each (era, calendar month) with >= 6 scored events, sort by dmin (ties: by ticker, stable) and split the
    sorted order into 3 near-equal groups with np.array_split (bottom = most below the shelf, top = closest to / above it).
    Asserted: no month holds scored events of both eras; no duplicate (ticker, E) among scored events.
 R4 ratio = pooled top-tercile big-winner rate / pooled bottom-tercile rate (inf if bottom = 0 and top > 0).
    Permutation: within each month, dmin is shuffled across that month's events (= tercile labels shuffled within month),
    2,000 shuffles, np.random.default_rng(1121); one-sided p = (1 + #(ratio_perm >= ratio_obs)) / 2001.
    "direction the same in era A and era B" = top rate > bottom rate in EACH era.
    Verdicts: all three pass -> "the lead predicts the tail"; ratio >= 1.5 with p > 0.05 -> "directional, not proven"
    (read as the prereg's "the ratio alone"); ratio < 1.0 -> "does not pick winners"; any other combination -> no word is
    invented: "NO PRE-REGISTERED VERDICT COVERS THIS" with the three components printed.
 R5 PRE-REG 7: his buy matches a primary row of the same (ticker, E) in the event list of his entry's own `era` column.
    "Others" = same-day, same-era events of the PRE-REG 6 population before the forward-window drop (primary, not flag_adj /
    flag_adj_Dm1, non-NULL dmin), not his own buys (his-vs-his pairs on a two-buy day are excluded). Statistic pooled over all
    his-vs-other pairs (ties 0.5). Permutation: within each kept day, the "his" labels are shuffled among that day's scored
    events (count per day kept), 2,000 shuffles, rng 1121, one-sided p as R4. Month percentile = share of the same
    (era, month) scored events with a dmin strictly below his + half the ties.
 FIXES AFTER THE FIRST RUN (no rule changed): (a) run 1 crashed at the open(E) cross-check — the event list stores open to 6
    significant digits, so the tolerance became relative 1e-5; (b) run 2's events_scored.tsv.gz joined terciles / in_prereg6 on
    (ticker, E) without era, mislabelling era-overlap twins — now joined on (era, ticker, E) and asserted; one printout label
    corrected ("all scored events (both eras)"). Run 3's printout is diffed against run 2's.
 R6 the sample-10 loader check reads scripts/probes/_594_sample10_1121/q2_bars.out (2026 bars already scored in RESULT 7; not the
    sealed #710 export) through the same score_one() the historical path uses; the 2024-12-31 cut applies to the export files.
"""
from __future__ import annotations

import gzip
import importlib.util
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


f3 = _load("f3_def", REPO / "scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")

DATA = "/Users/alvinfung/apollo_data"
EVDIR = f"{DATA}/cb702/qm_streams/ep_join_1023"
ENTRIES = f"{DATA}/cb702/qm_streams/holdings_1024/entries.tsv"
DAILY = {"A": f"{DATA}/cb702_pre_v2/daily_closes_all.csv.gz", "B": f"{DATA}/cb702/daily_closes_all.csv.gz"}
CAL = {"A": f"{DATA}/cb702_pre_v2/sessions.txt", "B": f"{DATA}/cb702/qm_streams/track_a_1023/spy_sessions_eraB_le_2024-12-31.txt"}
CUT_B = "2024-12-31"
E_MAX_B = "2024-09-30"
FWD = 60
BIG = 1.5
MIN_MONTH = 6
NPERM = 2000
SEED = 1121
OUT_TSV = HERE / "events_scored.tsv.gz"


def five_years_before(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    try:
        return date(y - 5, m, dd).isoformat()
    except ValueError:
        return date(y - 5, m, 28).isoformat()


def score_one(days, ia):
    """THE feature path, shared by the loader check and the history: days sliced to 5 calendar years before E, E = last bar."""
    lo = 0
    cut = five_years_before(days[ia][0])
    while lo < ia and days[lo][0] < cut:
        lo += 1
    sl = days[lo:ia + 1]
    j = len(sl) - 1
    adr = nbis.adr20_pct(sl, j)
    res = f3.f3_new(sl, j, adr, f3.STATED)
    return res, adr


# ══════════════════════════════════ (0) LOADER CHECK — sample 10 must reproduce P = 0.750 ══════════════════════════════════
def read_q2(path):
    into, cur = {}, None
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("== "):
            t, d = line[3:].split(); cur = (t, d); into[cur] = []
        elif cur and line and line[0].isdigit() and "|" in line:
            td, o, h, l, c, v = line.split("|"); into[cur].append((td, float(o), float(h), float(l), float(c), float(v)))
    return into


print("=" * 110)
print("(0) LOADER CHECK — sample 10 (RESULT 7) through score_one()")
from tests.fixtures.must_not_trade_charts import CHART_RULINGS, GOOD_CHART, OKISH_CHART  # noqa: E402

q2 = read_q2(REPO / "scripts/probes/_594_sample10_1121/q2_bars.out")
rows10 = [r for r in CHART_RULINGS if r.ruling_date == "2026-11-21"]
assert len(rows10) == 11, len(rows10)
Y, N = [], []
for r in rows10:
    days = q2[(r.ticker, r.alert_date)]
    assert days[-1][0] == r.alert_date
    res, _ = score_one(days, len(days) - 1)
    (Y if r.verdict in (GOOD_CHART, OKISH_CHART) else N).append(res["dmin"])
    print(f"  {r.ticker:6s} {r.alert_date} {r.verdict:12s} dmin={res['dmin']:.3f}")
assert all(x is not None for x in Y + N)
P10 = sum(1.0 if y > n else 0.5 if y == n else 0.0 for y in Y for n in N) / (len(Y) * len(N))
print(f"  yes {len(Y)} / no {len(N)}, pairs {len(Y) * len(N)}, P = {P10:.3f}")
if round(P10, 3) != 0.750:
    print("LOADER CHECK FAILED — stop."); sys.exit(2)
print("  LOADER CHECK PASSED: P = 0.750 reproduced exactly")

# ══════════════════════════════════ events + his buys ══════════════════════════════════
cal = {}
for era in "AB":
    c = [ln.strip() for ln in open(CAL[era]) if ln.strip()]
    if era == "B":
        assert max(c) <= CUT_B
    cal[era] = np.array(sorted(c), dtype="U10")
ev = []
for era in "AB":
    e = pd.read_csv(f"{EVDIR}/ep_events_{era}.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
    assert (e.era == era).all()
    if era == "B":
        assert e.E.max() <= CUT_B
    ev.append(e)
ev = pd.concat(ev, ignore_index=True)
n_rows_all = len(ev)
ev = ev[ev.primary == "True"].copy()
n_primary = len(ev)

ent = pd.read_csv(ENTRIES, sep="\t", dtype=str, keep_default_na=False)
his = ent[ent.setup.isin(["EP", "both"]) & (ent.flicker == "False") & (ent.has_bars == "True")].copy()
assert len(his) == 62, len(his)
assert (his.sym == his.sym_a).all()
assert not his.duplicated(["sym", "E"]).any()
his_keys = set(zip(his.era, his.sym, his.E))

# ══════════════════════════════════ daily bars (o h l c v), era B cut at read ══════════════════════════════════
need = {era: set(ev.loc[ev.era == era, "ticker"]) | set(his.loc[his.era == era, "sym"]) for era in "AB"}
bars = {}
readcnt = {}
for era in "AB":
    cnt = Counter()
    parts = []
    for ch in pd.read_csv(DAILY[era], header=None, names=["t", "d", "o", "h", "l", "c", "v"],
                          dtype={"t": str, "d": str, "o": "float64", "h": "float64", "l": "float64", "c": "float64", "v": "float64"},
                          keep_default_na=False, chunksize=2_000_000):
        cnt["rows_read"] += len(ch)
        if era == "B":
            m = ch.d <= CUT_B
            cnt["rows_dropped_after_2024-12-31"] += int((~m).sum())
            ch = ch[m]
        ch = ch[ch.t.isin(need[era])]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    del parts
    if era == "B":
        assert df.d.max() <= CUT_B, df.d.max()          # SEALED (#710): nothing after 2024-12-31 survives the read
    dv = df.d.to_numpy(dtype="U10")
    ci = np.searchsorted(cal[era], dv)
    on = (ci < len(cal[era])) & (cal[era][np.minimum(ci, len(cal[era]) - 1)] == dv)
    cnt["rows_off_calendar_dropped"] = int((~on).sum())
    df = df[on].copy()
    df["ci"] = ci[on]
    df.sort_values(["t", "ci"], inplace=True, kind="mergesort")
    assert not df.duplicated(["t", "ci"]).any()
    for t, g in df.groupby("t", sort=False):
        bars[(era, t)] = (g.d.tolist(), g.ci.to_numpy(), g.o.to_numpy(), g.h.to_numpy(), g.l.to_numpy(), g.c.to_numpy(), g.v.to_numpy())
    cnt["rows_kept(event tickers)"] = len(df)
    readcnt[era] = cnt
    del df
print("\n" + "=" * 110)
print("(1) POPULATION")
for era in "AB":
    print(f"  daily file era {era}: " + ", ".join(f"{k}={v:,}" for k, v in readcnt[era].items()))
assert max(d for (era, _), b in bars.items() if era == "B" for d in b[0][-1:]) <= CUT_B


def feature_and_outcome(era, t, E, open_list):
    b = bars.get((era, t))
    if b is None:
        return None
    d, ci, o, h, l, c, v = b
    try:
        i = d.index(E)
    except ValueError:
        return None
    assert abs(o[i] - float(open_list)) <= 1e-5 * abs(o[i]) + 1e-6, (era, t, E, o[i], open_list)
    days = [(d[k], o[k], h[k], l[k], c[k], v[k]) for k in range(i + 1)]
    res, adr = score_one(days, i)
    iE = int(ci[i])
    last_ci = len(cal[era]) - 1
    fwd_ok = iE + FWD <= last_ci
    out = dict(iE=iE, dmin=res["dmin"], structure=res["structure"], null=res["null"], adr20=adr, fwd_ok=fwd_ok,
               big_winner=np.nan, ret60=np.nan, fail5=np.nan, maxc_ratio=np.nan)
    if fwd_ok:
        if era == "B":
            assert cal["B"][iE + FWD] <= CUT_B
        j = i
        mx = -np.inf
        r60 = np.nan
        r5 = np.nan
        while j < len(d) and ci[j] <= iE + FWD:
            mx = max(mx, c[j])
            if ci[j] == iE + FWD:
                r60 = c[j] / o[i] - 1.0
            if ci[j] == iE + 5:
                r5 = 1.0 if c[j] < o[i] else 0.0
            j += 1
        out.update(maxc_ratio=mx / o[i], big_winner=1.0 if mx >= BIG * o[i] else 0.0, ret60=r60, fail5=r5)
    return out


recs = []
miss_bar = 0
for r in ev.itertuples(index=False):
    fo = feature_and_outcome(r.era, r.ticker, r.E, r.open)
    if fo is None:
        miss_bar += 1
        continue
    assert fo["iE"] == int(r.iE), (r.ticker, r.E, fo["iE"], r.iE)
    recs.append(dict(ticker=r.ticker, E=r.E, era=r.era, month=r.E[:7], year=r.E[:4], sectype=r.sectype or "UNKNOWN",
                     flag=(r.flag_adj == "True") or (r.flag_adj_Dm1 == "True"), is_his_buy=(r.era, r.ticker, r.E) in his_keys, **fo))
X = pd.DataFrame(recs)
assert miss_bar == 0, miss_bar

print(f"  event-list rows {n_rows_all:,}; primary {n_primary:,}; no bar found for E: {miss_bar}")
print("  events per era:", X.era.value_counts().sort_index().to_dict())
print("  events per year (era):")
print("   " + X.groupby(["year", "era"]).size().unstack(fill_value=0).to_string().replace("\n", "\n   "))
print("  events per security type (era):")
print("   " + X.groupby(["sectype", "era"]).size().unstack(fill_value=0).to_string().replace("\n", "\n   "))
print(f"  dropped flag_adj / flag_adj_Dm1: {int(X.flag.sum())} (per era {X[X.flag].era.value_counts().to_dict()})")
X = X[~X.flag].copy()

# forward-window gate (PRE-REG 6 only)
dropB = X[(X.era == "B") & (X.E > E_MAX_B)]
dropA = X[(X.era == "A") & (~X.fwd_ok)]
print(f"  forward window: era B E > {E_MAX_B} dropped {len(dropB)}; era A E with no E+60 in the A file (after "
      f"{cal['A'][len(cal['A']) - 1 - FWD]}) dropped {len(dropA)}")
assert X[(X.era == "B") & (X.E <= E_MAX_B)].fwd_ok.all()
base7 = X.copy()                                     # PRE-REG 7 population (no forward requirement)
P6 = X[~X.index.isin(dropB.index) & ~X.index.isin(dropA.index)].copy()
assert P6.fwd_ok.all() and P6.big_winner.notna().all()

nul = P6[P6.dmin.isna()]
print(f"  NULL dmin (PRE-REG 6 population {len(P6)}): {len(nul)}  big-winner rate NULL {nul.big_winner.mean():.3f} "
      f"vs non-NULL {P6[P6.dmin.notna()].big_winner.mean():.3f}")
reason = nul.null.fillna("").str.replace(r"\(.*", "", regex=True)
print("   NULL by reason (era):")
print("   " + pd.crosstab(reason, nul.era).to_string().replace("\n", "\n   "))
print("   NULL by year (era):")
print("   " + pd.crosstab(nul.year, nul.era).to_string().replace("\n", "\n   "))
print("   NULL big-winner rate per era: " + ", ".join(f"{e} {g.big_winner.mean():.3f} (n {len(g)}) vs non-NULL "
      f"{P6[(P6.era == e) & P6.dmin.notna()].big_winner.mean():.3f}" for e, g in nul.groupby("era")))

S = P6[P6.dmin.notna()].copy()
assert not S.duplicated(["ticker", "E"]).any(), "duplicate (ticker, E) across eras among scored events"
mer = S.groupby("month").era.nunique()
assert (mer == 1).all(), f"months with both eras: {list(mer[mer > 1].index)}"
mc = S.groupby("month").size()
small = mc[mc < MIN_MONTH]
print(f"  months with scored events: {len(mc)}; dropped (< {MIN_MONTH} events): {len(small)} months, {int(small.sum())} events")
S = S[S.month.isin(mc[mc >= MIN_MONTH].index)].copy()
S.sort_values(["month", "dmin", "ticker"], inplace=True, kind="mergesort")
ties = int(S.duplicated(["month", "dmin"]).sum())
print(f"  scored events ranked: {len(S)} in {S.month.nunique()} months; tied dmin within a month: {ties}")
print("  ranked events per era:", S.era.value_counts().sort_index().to_dict(),
      " big-winner base rate per era:", {e: round(g.big_winner.mean(), 3) for e, g in S.groupby("era")})

month_groups = [np.flatnonzero((S.month == m).to_numpy()) for m in S.month.unique()]   # S is sorted by month, dmin
terc = np.empty(len(S), dtype=int)
for g in month_groups:
    for k, part in enumerate(np.array_split(g, 3)):
        terc[part] = k
S["tercile"] = terc                                   # 0 bottom (furthest below shelf) .. 2 top
BW = S.big_winner.to_numpy()
ERA = S.era.to_numpy()


def ratio_of(tc, mask=None):
    m = np.ones(len(tc), bool) if mask is None else mask
    top = BW[m & (tc == 2)]
    bot = BW[m & (tc == 0)]
    rt, rb = top.mean(), bot.mean()
    return (rt / rb if rb > 0 else (np.inf if rt > 0 else np.nan)), rt, rb, len(top), len(bot)


obs, rt, rb, nt, nb = ratio_of(terc)
rng = np.random.default_rng(SEED)
ge = 0
perm_r = np.empty(NPERM)
for s in range(NPERM):
    tc = np.empty(len(S), dtype=int)
    for g in month_groups:
        tc[g] = terc[g][rng.permutation(len(g))]
    pr = ratio_of(tc)[0]
    perm_r[s] = pr
    if pr >= obs:
        ge += 1
p6 = (1 + ge) / (NPERM + 1)

print("\n" + "=" * 110)
print("(2) PRE-REGISTRATION 6 — does the shelf distance pick EPs that WORK?")
print("  per-tercile big-winner rate (max close E..E+60 >= 1.5 x open(E)), all ranked events:")
for k, nm in ((0, "bottom (furthest below shelf)"), (1, "middle"), (2, "top (closest to / above shelf)")):
    g = S[S.tercile == k]
    print(f"    {nm:32s} n {len(g):5d}  big winners {int(g.big_winner.sum()):4d}  rate {g.big_winner.mean():.3f}  "
          f"median dmin {g.dmin.median():+.2f}")
print(f"  RATIO top/bottom = {obs:.3f}  (bar >= 1.5)")
print(f"  within-month permutation ({NPERM}, seed {SEED}): p = {p6:.4f}  (bar <= 0.05); perm ratio median {np.nanmedian(perm_r):.3f}, "
      f"95th pct {np.nanpercentile(perm_r, 95):.3f}")
era_dir = {}
print("  per era:")
for e in "AB":
    r_, t_, b_, nt_, nb_ = ratio_of(terc, ERA == e)
    mid = S[(S.era == e) & (S.tercile == 1)].big_winner.mean()
    era_dir[e] = t_ > b_
    print(f"    era {e}: n {int((ERA == e).sum())}  bottom {b_:.3f} (n {nb_})  middle {mid:.3f}  top {t_:.3f} (n {nt_})  ratio {r_:.3f}  "
          f"top > bottom: {t_ > b_}")
print("  per year:")
for (y, e), g in S.groupby(["year", "era"]):
    t_, b_ = g[g.tercile == 2].big_winner.mean(), g[g.tercile == 0].big_winner.mean()
    print(f"    {y} era {e}: n {len(g):4d}  bottom {b_:.3f}  top {t_:.3f}  ratio {(t_ / b_ if b_ > 0 else float('inf')):.2f}")
print("  secondary (description only): median / mean close(E+60)/open(E)-1, and share with close(E+5) < open(E):")
for k in (0, 1, 2):
    g = S[S.tercile == k]
    print(f"    tercile {k}: ret60 median {g.ret60.median():+.3f}  mean {g.ret60.mean():+.3f} (n {g.ret60.notna().sum()})  "
          f"fail5 {g.fail5.mean():.3f} (n {g.fail5.notna().sum()})")
for e in "AB":
    for k in (0, 2):
        g = S[(S.era == e) & (S.tercile == k)]
        print(f"    era {e} tercile {k}: ret60 median {g.ret60.median():+.3f}  fail5 {g.fail5.mean():.3f}")
print(f"  ret60 NaN (no bar at E+60): {int(S.ret60.isna().sum())}; fail5 NaN (no bar at E+5): {int(S.fail5.isna().sum())}")
c1, c2, c3 = obs >= 1.5, p6 <= 0.05, era_dir["A"] and era_dir["B"]
print(f"  components: ratio >= 1.5: {c1}; p <= 0.05: {c2}; top > bottom in era A AND era B: {c3}")
if c1 and c2 and c3:
    v6 = "the lead predicts the tail"
elif c1 and not c2:
    v6 = "directional, not proven"
elif obs < 1.0:
    v6 = "does not pick winners"
else:
    v6 = "NO PRE-REGISTERED VERDICT COVERS THIS"
print(f"  VERDICT (PRE-REG 6): {v6}")

# ══════════════════════════════════ (3) PRE-REG 7 ══════════════════════════════════
print("\n" + "=" * 110)
print("(3) PRE-REGISTRATION 7 — do Qullamaggie's EP buys sit near the shelf?")
allp = X.copy()   # after the flag drop, before forward drop; X already excludes flagged
keyset = {(r.era, r.ticker, r.E) for r in ev.itertuples(index=False)}
flagged_his = [k for k in his_keys if k in keyset and k not in set(zip(allp.era, allp.ticker, allp.E))]
matched = [k for k in his_keys if k in keyset]
print(f"  his EP buys (setup EP/both, not flicker, has bars): {len(his)}; matched to a primary event (same era, ticker, E): "
      f"{len(matched)}  -> {'description only (< 20)' if len(matched) < 20 else 'test eligible (>= 20)'}")
print(f"  unmatched: {sorted(k for k in his_keys if k not in keyset)}")
print(f"  matched but flag_adj-dropped: {flagged_his}")
H = base7[base7.is_his_buy]
Hs = H[H.dmin.notna()]
print(f"  matched with non-NULL dmin: {len(Hs)}; NULL: {sorted(zip(H[H.dmin.isna()].ticker, H[H.dmin.isna()].E, H[H.dmin.isna()].null))}")
B7 = base7[base7.dmin.notna()]
days7, dropped_days = [], []
for (e, E), g in B7.groupby(["era", "E"]):
    if not g.is_his_buy.any():
        continue
    if (~g.is_his_buy).sum() == 0:
        dropped_days.append((e, E, list(g.ticker)))
        continue
    days7.append((g.dmin.to_numpy(), g.is_his_buy.to_numpy()))
n_his_kept = sum(int(h.sum()) for _, h in days7)
print(f"  days with his buy and >= 1 other scored event: {len(days7)} (his buys on them {n_his_kept}); days dropped (no other): "
      f"{len(dropped_days)} {dropped_days}")
if n_his_kept < 20:
    print(f"  NOTE: effective n (his buys in kept days) = {n_his_kept} < 20")


def p7_of(lbls):
    s = 0.0
    n = 0
    for (dm, _), h in zip(days7, lbls):
        a, b = dm[h], dm[~h]
        s += ((a[:, None] > b[None, :]).sum() + 0.5 * (a[:, None] == b[None, :]).sum())
        n += len(a) * len(b)
    return s / n, n


P7, npairs = p7_of([h for _, h in days7])
rng7 = np.random.default_rng(SEED)
ge7 = 0
for s in range(NPERM):
    if p7_of([h[rng7.permutation(len(h))] for _, h in days7])[0] >= P7:
        ge7 += 1
pp7 = (1 + ge7) / (NPERM + 1)
print(f"  within-day P(his dmin > same-day other's) = {P7:.3f} over {npairs} pairs  (bar >= 0.60)")
print(f"  within-day label permutation ({NPERM}, seed {SEED}): p = {pp7:.4f}  (bar <= 0.05)")
# month percentile
pcts = []
for r in Hs.itertuples():
    g = B7[(B7.era == r.era) & (B7.month == r.month)].dmin.to_numpy()
    pcts.append(((g < r.dmin).sum() + 0.5 * ((g == r.dmin).sum() - 1)) / (len(g) - 1) if len(g) > 1 else np.nan)
pcts = np.array(pcts)
print(f"  his buys' dmin percentile within their (era) month: median {np.nanmedian(pcts):.3f}, mean {np.nanmean(pcts):.3f}, "
      f"share above 0.5 {np.nanmean(pcts > 0.5):.3f} (n {np.isfinite(pcts).sum()})")
print(f"  his buys' median dmin {Hs.dmin.median():+.2f} ADR vs all scored events (both eras) {B7.dmin.median():+.2f}")
Hb = H[H.big_winner.notna()]
print(f"  his buys that are big winners (PRE-REG 6 definition, description): {int(Hb.big_winner.sum())} of {len(Hb)} with a "
      f"full 60-session window ({Hb.big_winner.mean():.3f}); base rate of the PRE-REG 6 population {P6.big_winner.mean():.3f}")
print("  his buys:")
for r in H.sort_values("E").itertuples():
    print(f"    {r.era} {r.ticker:5s} {r.E}  dmin {'' if pd.isna(r.dmin) else f'{r.dmin:+.2f}':>7s}  {r.structure or r.null}  "
          f"big_winner {'' if pd.isna(r.big_winner) else int(r.big_winner)}  maxc/open {r.maxc_ratio:.2f}")
if len(matched) < 20:
    v7 = "description only (matched n < 20)"
elif P7 >= 0.60 and pp7 <= 0.05:
    v7 = "PASS: his EP buys sit nearer the shelf than the same-day others"
else:
    v7 = "FAIL: bar not met (P >= 0.60 and p <= 0.05 both required)"
print(f"  VERDICT (PRE-REG 7): {v7}")

# ══════════════════════════════════ per-event rows ══════════════════════════════════
outr = base7.merge(S[["era", "ticker", "E", "tercile"]], on=["era", "ticker", "E"], how="left")
assert len(outr) == len(base7)
outr["null"] = outr.null.fillna("")
outr["in_prereg6"] = outr.set_index(["era", "ticker", "E"]).index.isin(P6.set_index(["era", "ticker", "E"]).index)
assert int((outr.dmin.isna() & outr.tercile.notna()).sum()) == 0
assert int(((outr.era == "A") & (outr.E > cal["A"][len(cal["A"]) - 1 - FWD]) & outr.in_prereg6).sum()) == 0
assert int(outr.in_prereg6.sum()) == len(P6) and int(outr.tercile.notna().sum()) == len(S)
cols = ["ticker", "E", "era", "month", "dmin", "structure", "null", "tercile", "big_winner", "ret60", "fail5", "is_his_buy", "in_prereg6"]
with gzip.open(OUT_TSV, "wt") as fh:
    outr[cols].to_csv(fh, sep="\t", index=False)
print(f"\nwrote {OUT_TSV} ({len(outr)} rows)")
