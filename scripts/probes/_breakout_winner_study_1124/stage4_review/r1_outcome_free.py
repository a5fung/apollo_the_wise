#!/usr/bin/env python3
"""Stage 4 review, part 1 - OUTCOME-FREE checks. Reads: stage-1f feature table, stage-1e post-drop events parquet, guard / flag
files (DATES only, never printing a date after 2024-12-31), union calendar. No bar is opened. Output -> r1_outcome_free.txt"""
import hashlib, sys, re
from pathlib import Path
from collections import Counter
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; ST = HERE.parent; REPO = ST.parents[2]; DATA = Path("/Users/alvinfung/apollo_data")
CUT = "2024-12-31"
SH = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md": "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
      "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md": "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
      "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md": "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b"}
for p, h in SH.items():
    assert hashlib.sha256((REPO / p).read_bytes()).hexdigest() == h, p
L = []
def P(s=""):
    print(s); L.append(str(s))
T = pd.read_csv(ST / "stage1f/feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str}, low_memory=False)
assert hashlib.sha256((ST / "stage1f/feature_table.tsv.gz").read_bytes()).hexdigest().startswith("d629ef0a")
assert T.E.max() <= CUT and T.D.max() <= CUT
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet")
assert EV.E.max() <= CUT and EV.D.max() <= CUT
P(f"SEAL: feature table max E {T.E.max()}, max D {T.D.max()}; post-drop events max E {EV.E.max()} (all <= {CUT})")
K = T[T.kept == True].copy()
P("\n== 1. POPULATION (kept events, seed 1124; outcome-free) ==")
K["set_era"] = K.set + "/" + K.era
P(f"kept {len(K)}: " + ", ".join(f"{k} {v}" for k, v in K.set_era.value_counts().sort_index().items()))
P("per E-year: " + ", ".join(f"{e}{y} {n}" for (e, y), n in K.groupby(["era", "Ey"]).size().items()))
D = K[K.set == "DISC"]; C = K[K.set == "CHECK"]
def comp(X, nm):
    P(f"-- {nm} (n {len(X)})")
    P(f"   identities {X.key.nunique()}, tickers {X.ticker.nunique()}; events per identity: median {X.groupby('key').size().median():.0f}, max {X.groupby('key').size().max()}, identities with >=5 events {int((X.groupby('key').size() >= 5).sum())}")
    nn = X.groupby("E").size()
    P(f"   break days {len(nn)}; events per day median {nn.median():.0f}, p95 {nn.quantile(.95):.0f}, max {nn.max()} (on {nn.idxmax()}); share of events on days holding >= 10 events {100 * nn[nn >= 10].sum() / len(X):.1f}%")
    st = X.sectype.fillna("unknown").value_counts()
    P("   security type: " + ", ".join(f"{k} {v} ({100 * v / len(X):.1f}%)" for k, v in st.items()))
    px = X.raw_close_s.astype(float)
    P("   raw price at D: " + ", ".join(f"{lab} {100 * ((px >= a) & (px < b)).mean():.1f}%" for lab, a, b in (("<$5", 0, 5), ("$5-10", 5, 10), ("$10-20", 10, 20), ("$20-50", 20, 50), ("$50-100", 50, 100), (">=$100", 100, 1e12))) + f"; median ${px.median():.2f}")
    P(f"   daily range ADR20 %: p10 {X.f01.quantile(.1):.2f} median {X.f01.median():.2f} p90 {X.f01.quantile(.9):.2f} max {X.f01.max():.1f}")
    P(f"   first break after 10 quiet sessions {100 * X.first10.mean():.1f}%; after 60 quiet {100 * X.first60.mean():.1f}%")
    P(f"   opened above the level (24a) {100 * (X.f24grp == 'a').mean():.1f}%; at/below (24b) {100 * (X.f24grp == 'b').mean():.1f}%")
    P(f"   B4 distance close(D)->level in daily ranges: p10 {X.B4.quantile(.1):.2f} median {X.B4.median():.2f} p90 {X.B4.quantile(.9):.2f}; level source {X.level_source.value_counts().to_dict()}")
    P(f"   bars to D under 252: {int((X.bars_to_d < 252).sum())} ({100 * (X.bars_to_d < 252).mean():.1f}%); 5-letter symbols ending Q: {int(X.ticker.str.fullmatch(r'[A-Z]{4}Q').sum())}; symbols with a dot/W/U suffix pattern: {int(X.ticker.str.contains(r'[.]').sum())}")
for nm, X in (("DISCOVERY (E <= 2020-12-31, era A)", D), ("CHECK era A (2021 .. 2022-04-01)", C[C.era == "A"]), ("CHECK era B (2022-04 .. 2024-10-04)", C[C.era == "B"])):
    comp(X, nm)
P(f"2020 share of discovery events: {100 * (D.Ey == 2020).mean():.1f}% ({int((D.Ey == 2020).sum())} of {len(D)})")
ms = K.groupby(["set", "era", "month"]).size()
for (s, e), g in ms.groupby(level=[0, 1]):
    small = g[g < 6]
    P(f"months {s}/{e}: {len(g)}; smallest {g.min()}; months under 6 events (no thirds can form) {len(small)} holding {int(small.sum())} events: {', '.join(m for _, _, m in small.index)}")
cb = C[C.era == "B"].groupby("month").size()
P("era-B check events per month: " + ", ".join(f"{m} {n}" for m, n in cb.items()))
P("unknown-type discovery tickers (top 25 by events): " + ", ".join(f"{t} {n}" for t, n in D[D.sectype.isna()].ticker.value_counts().head(25).items()))
P("most frequent discovery tickers: " + ", ".join(f"{t} {n}" for t, n in D.ticker.value_counts().head(15).items()))

P("\n== 2. KEEP RULE: independent re-walk from the post-drop rows (own code; sha256('seed|identity|D') first 8 bytes / 2^64 < 1/5; eligible when no kept row in the prior 60 union sessions) ==")
ucal = (ST / "stage1de/calendars_union.txt").read_text().split("\n"); uidx = {d: i for i, d in enumerate(ucal)}
assert (EV.uci == EV.D.map(uidx)).all(), "uci is not the union-calendar index of D"
assert all(ucal[i + 1] == e for i, e in zip(EV.uci, EV.E)) , "E is not the next union session"
def rewalk(seed):
    keep = {}
    for ident, g in EV.groupby("key", sort=False):
        g = g.sort_values("uci"); lastk = None
        hs = g.hstr.iloc[0]; assert (g.hstr == hs).all()
        for idx, u, d in zip(g.index, g.uci, g.D):
            if lastk is not None and u - lastk <= 60:
                keep[idx] = False; continue
            x = int.from_bytes(hashlib.sha256(f"{seed}|{hs}|{d}".encode()).digest()[:8], "big") / 2 ** 64
            keep[idx] = x < 0.2
            if keep[idx]: lastk = u
    return pd.Series(keep).reindex(EV.index)
for seed, col in ((1124, "kept"), (2411, "kept2411")):
    k = rewalk(seed)
    P(f"seed {seed}: re-walk kept {int(k.sum())}; stored {int(EV[col].sum())}; rows differing {int((k != EV[col]).sum())}")
    assert (k == EV[col]).all()
# identity string rule
g = EV.groupby("key")
a_tk = EV[EV.era == "A"].groupby("key").ticker.agg(lambda s: sorted(set(s)))
bad = 0
for key, hs in g.hstr.first().items():
    if key in a_tk.index and hs not in a_tk[key]: bad += 1
P(f"identity string: identities with an era-A event ticker whose string is not one of their era-A tickers: {bad} (a string may be an era-A ticker with no surviving event row - allowed)")
P(f"(identity, D) duplicated: {int(EV.duplicated(['key', 'uci']).sum())}; an (identity) spanning both eras: {int((EV.groupby('key').era.nunique() == 2).sum())}")
Kp = EV[EV.kept].sort_values(["key", "uci"]); gap = Kp.groupby("key").uci.diff().dropna()
P(f"smallest gap between two kept events of one identity: {int(gap.min())} sessions (must be >= 61)")
# drops precede the walk and read nothing after E: every reason is a date <= E or the calendar
P(f"post-drop rows carrying a drop flag: {int(EV.drop_any.sum())} (must be 0)")
# truncation-invariance of the keep decision: walk on rows with D <= X reproduces the stored decision for those rows
for X in ("2019-06-28", "2020-12-30", "2022-03-31"):
    sub = EV[EV.D <= X]; lastk = {}; ok = True
    for key, u, d, hs, st in sorted(zip(sub.key, sub.uci, sub.D, sub.hstr, sub.kept)):
        lk = lastk.get(key)
        kp = (lk is None or u - lk > 60) and int.from_bytes(hashlib.sha256(f"1124|{hs}|{d}".encode()).digest()[:8], "big") / 2 ** 64 < 0.2
        if kp: lastk[key] = u
        ok &= (kp == st)
    P(f"   walk run only on rows with D <= {X}: decisions equal the full-run decisions on those rows: {ok}")
f10_all = EV.first10.mean(); f10_k = EV[EV.kept].first10.mean()
P(f"first-break share: all post-drop rows {100 * f10_all:.2f}%, kept {100 * f10_k:.2f}% (line 2x = {200 * f10_all:.2f}%)")

P("\n== 3. GUARD / FLAG ARMS (dates only; nothing after 2024-12-31 printed) ==")
def guard_years(path):
    c = Counter(); n_sym = 0; fmt_bad = 0
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, ib = f.index("symbol"), f.index("breaks"); hdr = f; continue
        if len(f) <= ib or not f[ib]: continue
        n_sym += 1
        for x in f[ib].split(";"):
            d = x.split(":")[0]
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", d): fmt_bad += 1; continue
            c[d[:4] if d <= CUT else "after-cut"] += 1
    return hdr, n_sym, fmt_bad, c
for nm, p in (("era A pre_v2/symbol_guard.tsv", DATA / "cb702_pre_v2/symbol_guard.tsv"), ("era B symbol_guard_B.tsv", REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")):
    hdr, n_sym, fb, c = guard_years(p)
    P(f"{nm}: columns {hdr}; symbols with a break {n_sym}; break tokens not parsing as a date {fb}; break dates per year {dict(sorted(c.items()))}")
B = EV[EV.era == "B"]; A = EV[EV.era == "A"]
P(f"era-B post-drop break rows {len(B)} on {B.ticker.nunique()} tickers; era A {len(A)} on {A.ticker.nunique()} tickers")
def guard_map(path):
    out = {}
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, ib = f.index("symbol"), f.index("breaks"); continue
        if len(f) > ib and f[ib]:
            ds = sorted(d for d in (x.split(":")[0] for x in f[ib].split(";")) if d <= CUT)
            if ds: out[f[ik]] = ds
    return out
gB = guard_map(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
gA = guard_map(DATA / "cb702_pre_v2/symbol_guard.tsv")
for nm, gm, X in (("B", gB, B), ("A", gA, A)):
    tk = set(X.ticker); inter = tk & set(gm)
    kept = X[X.kept]
    lo_hi = [(t, ucal[u + 2], ucal[min(u + 61, len(ucal) - 1)]) for t, u in zip(kept.ticker, kept.uci)]
    w = sum(1 for t, lo, hi in lo_hi if any(lo <= d <= hi for d in gm.get(t, ())))
    span = (X.D.min(), X.E.max())
    in_span = sum(1 for t in inter for d in gm[t] if span[0] <= d <= span[1])
    P(f"era {nm}: event tickers with any guard break date <= cut: {len(inter)} of {len(tk)}; their break dates inside the era's event span {span}: {in_span}; kept events with a guard date in E+1..E+60: {w}")
