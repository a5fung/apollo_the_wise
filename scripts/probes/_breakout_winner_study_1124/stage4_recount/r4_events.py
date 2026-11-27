"""R4 stage 1b/1d/1e recount (blind): bridge, drops, identity, q rule, keep walk, coverage, outcome-free prints. Dates only after E (no price after E)."""
import bisect, json, sys
from collections import Counter, defaultdict
from datetime import date
import numpy as np, pandas as pd
import r4_common as C, r4_keep as K
import v1_replay as R

LOGF = open(C.OUTD / f"stage1_events{C.SUF}.log", "w")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True); LOGF.write(s + "\n"); LOGF.flush()


C.assert_pins()
RES = {}
cal = {}
pool = {}
for e in "AB":
    cal[e] = [date.fromisoformat(x) for x in (C.BIG / f"r4_pool_era{e}.cal.txt").read_text().split()]
    pool[e] = pd.read_parquet(C.BIG / f"r4_pool_era{e}.parquet")
    assert pool[e].D.max() < C.SEAL.isoformat()
    P(f"era {e}: pool rows {len(pool[e]):,} (ok {int(pool[e].ok.sum()):,}) nights {pool[e].ci.nunique()}")

# ---------------------------------------------------------------- 1b bridge, era A (context off) -- vs the 11-13 capture (ci/ticker/fire only)
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
cap = pd.read_parquet(CAP, columns=["ci", "ticker", "fire"])
A = pool["A"]
A["fire_ctxoff"] = A.has_e & (A.hE > A.level)
ka = set(zip(A.ci, A.ticker)); kc = set(zip(cap.ci, cap.ticker))
fa = set(zip(A.ci[A.fire_ctxoff], A.ticker[A.fire_ctxoff])); fc = set(zip(cap.ci[cap.fire], cap.ticker[cap.fire]))
P(f"BRIDGE era A (context-off set = failed subset of CONTEXT_GATES): mine {len(A):,} rows / {int(A.fire_ctxoff.sum()):,} break rows / {A.ci.nunique()} nights / "
  f"median {A.groupby('ci').size().median():.0f} a night | 11-13 capture {len(cap):,} / {int(cap.fire.sum()):,} / {cap.ci.nunique()}")
P(f"  row set equal: {ka == kc} (mine-only {len(ka - kc)}, capture-only {len(kc - ka)}); break set equal: {fa == fc} (mine-only {len(fa - fc)}, capture-only {len(fc - fa)})")
nb = A.groupby("ci").fire_ctxoff.sum()
P(f"  break rows per night median {nb.median():.0f}")
RES["bridge_A"] = {"rows": len(A), "break_rows": int(A.fire_ctxoff.sum()), "nights": int(A.ci.nunique()), "row_sets_equal": ka == kc,
                   "break_sets_equal": fa == fc, "median_breaks_per_night": float(nb.median())}
# context cut: how many context-off break rows the live context gates take off
P(f"  context gates' cut, era A: list rows (ok) {int(A.ok.sum()):,}; context-only {int((~A.ok).sum()):,}; ok break rows {int((A.ok & A.fire_ctxoff).sum()):,} of {int(A.fire_ctxoff.sum()):,}")

# ---------------------------------------------------------------- Qullamaggie buys (ticker / E / lo / hi only)
bd = pd.read_csv(C.BUYS, sep="\t", usecols=["ticker", "E"], dtype=str, keep_default_na=False)
bu = pd.read_csv(C.BUYS_W, sep="\t", usecols=["ticker", "lo", "hi"], dtype=str, keep_default_na=False)
P(f"Qullamaggie buys: dated {len(bd)}, undated-widened {len(bu)} = {len(bd) + len(bu)}")


def buys_on(rows_df, calE):
    """rows_df has ticker, E (iso). returns (#dated buys on a row, #undated placed on the FIRST break row inside window, ids)"""
    byt = defaultdict(list)
    for t, e in zip(rows_df.ticker, rows_df.E):
        byt[t].append(e)
    for t in byt: byt[t].sort()
    nd = 0
    placed = []
    for t, e in zip(bd.ticker, bd.E):
        if e in set(byt.get(t, ())):
            nd += 1; placed.append((t, e))
    nu = 0
    for t, lo, hi in zip(bu.ticker, bu.lo, bu.hi):
        es = byt.get(t, [])
        i = bisect.bisect_left(es, lo)
        if i < len(es) and es[i] <= hi:
            nu += 1; placed.append((t, es[i]))
    return nd, nu, placed


brk_off = A[A.fire_ctxoff][["ticker", "E"]]
nd, nu, _ = buys_on(brk_off, None)
P(f"  buys on a context-off break row (era A): dated {nd} + undated {nu} = {nd + nu} of {len(bd) + len(bu)}  (prereg: 375)")
RES["buys_on_break_row_ctxoff"] = nd + nu

# ---------------------------------------------------------------- stores: first bar / last bar / types / splits
stores = {}
for e in "AB":
    S = R.load_store(e)
    D = S.D
    first = {t: int(D.ci[D.start[k]]) for k, t in enumerate(D.tickers)}
    last = {t: int(D.ci[D.stop[k] - 1]) for k, t in enumerate(D.tickers)}
    stores[e] = {"first": first, "last": last, "types": S.types, "cal": D.cal}
    assert D.cal == cal[e], "calendar mismatch with pool cal"
splits_B, nskip = R.load_splits_sealed(C.SPLITS_B)
P(f"era B split list rows read < 2025: tickers {len(splits_B)} (2025-26 rows skipped on date: {nskip})")
gA, dA = C.load_guard(C.GUARD_A, "A"); gB, dB = C.load_guard(C.GUARD_B, "B")
fA, fdA = C.load_flags(C.FLAGS_A); fB, fdB = C.load_flags(C.FLAGS_B)
P(f"guards: A symbols {len(gA)} (dated>=2025 dropped {dA}); B symbols {len(gB)} (dropped at read {dB}); adjustment flags: A tickers {len(fA)} (dropped {fdA}), B tickers {len(fB)} (dropped {fdB})")
RES["guard_B_dropped_at_read"] = dB

# ---------------------------------------------------------------- union calendar + identity
U = sorted(set(cal["A"]) | set(cal["B"]))
uidx = {d: i for i, d in enumerate(U)}
for d in set(cal["A"]) & set(cal["B"]):
    pass
pairs = pd.read_csv(C.OUTD / "identity_pairs_r4.tsv", sep="\t", dtype={"a": str, "b": str}, keep_default_na=False)
edges = pairs[(pairs.a == pairs.b) | pairs.first10.astype(bool)]
par = {}


def find(x):
    while par.setdefault(x, x) != x:
        par[x] = par[par[x]]; x = par[x]
    return x


for a, b in zip(edges.a, edges.b):
    ra, rb = find(("A", a)), find(("B", b))
    if ra != rb: par[ra] = rb
members = defaultdict(list)
for x in list(par):
    members[find(x)].append(x)


def ident(era, t):
    r = find((era, t))
    ms = members.get(r, [(era, t)])
    aa = sorted(x[1] for x in ms if x[0] == "A")
    bb = sorted(x[1] for x in ms if x[0] == "B")
    return r, (aa[0] if aa else bb[0])


# ---------------------------------------------------------------- break rows + drops
def window_ci_end(e):
    return len(cal[e]) - 1       # era A: file end 2022-06-30; era B: sealed copy end (< 2025-01-01) asserted


rows = []
for e, g, fl in (("A", gA, fA), ("B", gB, fB)):
    df = pool[e]
    br = df[df.ok & df.has_e & (df.hE > df.level)].copy()
    br["era"] = e
    cl = cal[e]
    first, last = stores[e]["first"], stores[e]["last"]
    lastci = window_ci_end(e)
    gd, fd, sp, fs, we, gk = [], [], [], [], [], []
    for r in br.itertuples():
        lo, hi = cl[r.ci - 85], cl[r.ci + 1]
        hit = [dk for dk in g.get(r.ticker, ()) if lo <= dk[0] <= hi]
        gd.append(bool(hit)); gk.append(hit[0][1] if hit else "")
        fd.append(any(lo <= x <= hi for x in fl.get(r.ticker, ())))
        sp.append(any(lo <= x[0] <= hi for x in splits_B.get(r.ticker, ())) if e == "B" else False)
        fs.append(bool(first[r.ticker] <= 5 and ((not r.ll_scored and r.Di + 1 < 189) or (r.ret126_none and r.Di + 1 < 120))))
        we.append(bool(r.ci + 1 + 60 > lastci))
    br["d_guard"], br["d_flag"], br["d_split"], br["d_filestart"], br["d_winend"], br["guard_kind"] = gd, fd, sp, fs, we, gk
    rows.append(br)
BR = pd.concat(rows, ignore_index=True)
BR["Ey"] = [int(x[:4]) for x in BR.E]
BR["reason"] = np.select([BR.d_guard | BR.d_flag, BR.d_filestart, BR.d_winend], ["guard_or_flag", "file_start", "window_end"], "")
P(f"\nBREAK ROWS (live list rows whose level is taken out on E): era A {int((BR.era == 'A').sum()):,}, era B {int((BR.era == 'B').sum()):,}")
for e in "AB":
    s = BR[BR.era == e]
    P(f"  era {e}: drops first-match guard/flag {int((s.reason == 'guard_or_flag').sum())} (guard {int(s.d_guard.sum())}, flag {int(s.d_flag.sum())}, "
      f"guard-or-flag overlap-free count {int((s.d_guard | s.d_flag).sum())}), file_start {int((s.reason == 'file_start').sum())}, window_end {int((s.reason == 'window_end').sum())}; "
      f"kept for walk {int((s.reason == '').sum())}")
    P("    by year (first-match):", s[s.reason != ""].groupby(["Ey", "reason"]).size().to_dict())
    P(f"    (variant, not applied) era-B split-list date in D-85..E: {int(s.d_split.sum())} rows, of which not already dropped {int((s.d_split & (s.reason == '')).sum())}")
RES["breakrows"] = {e: int((BR.era == e).sum()) for e in "AB"}
RES["drops"] = {e: {k: int((BR[(BR.era == e)].reason == k).sum()) for k in ("guard_or_flag", "file_start", "window_end")} for e in "AB"}
RES["drops"]["split_variant_B_not_dropped"] = int((BR.d_split & (BR.reason == "")).sum())
RES["guard_flag_detail"] = {e: {"guard": int(BR[BR.era == e].d_guard.sum()), "flag": int(BR[BR.era == e].d_flag.sum())} for e in "AB"}
RES["guard_kinds"] = BR[BR.d_guard].groupby(["era", "guard_kind"]).size().rename(lambda x: x).to_dict().__repr__()

BR.to_parquet(C.BIG / f"r4_events_breakrows{C.SUF}.parquet", index=False)
W = BR[BR.reason == ""].copy().reset_index(drop=True)
W["uD"] = [uidx[cal[e][c]] for e, c in zip(W.era, W.ci)]
ids = [ident(e, t) for e, t in zip(W.era, W.ticker)]
W["ikey"] = pd.factorize(np.array([str(i[0]) for i in ids]))[0]
W["istr"] = [i[1] for i in ids]
if C.FIX:   # traced reading: "its era-A ticker when it has one" = an era-A EVENT ticker; a component with no era-A break row keys its era-B rows by the era-B ticker
    _aev = set(W[W.era == "A"].ikey)
    W["istr"] = [s if (k in _aev or e == "A") else t for s, k, e, t in zip(W.istr, W.ikey, W.era, W.ticker)]
dup = W.groupby(["istr", "D"]).era.nunique()
P(f"  (identity, D) in both eras: {int((dup > 1).sum())}; seam night 2022-04-01 post-drop break rows: {int((W.D == '2022-04-01').sum())}")
# same-(ident, D) across eras by key
dupk = W.groupby(["ikey", "D"]).era.nunique()
assert int((dupk > 1).sum()) == 0, "an (identity, D) appears in both eras"

idents = W.ikey.to_numpy(); uD = W.uD.to_numpy(); dstr = W.D.to_numpy()
fq = K.first_after_quiet(idents, uD, 10, False)
W["first_break"] = fq
base = fq.mean()
P(f"\nPOST-DROP BREAK ROWS {len(W):,}; first-break-after-10-quiet share of all break rows {base:.4%}")
grid_out = []
chosen = None
coins = {s: np.array([K.coin(s, W.istr.iloc[i], dstr[i], "big") for i in range(len(W))]) for s in (1124, 2411)}
for q in K.GRID:
    k = K.walk(idents, uD, dstr, q, 1124, 60, True, "big", coins[1124])
    sh = fq[k].mean()
    grid_out.append((q, int(k.sum()), float(sh)))
    P(f"  q={q:.4f}: kept {int(k.sum()):,} first-share {sh:.4%} ratio {sh / base:.3f}")
    if chosen is None and sh <= 2 * base:
        chosen = q
P(f"  q (largest on grid with ratio <= 2) = {chosen}")
RES["q_grid"] = grid_out; RES["q"] = chosen
for s in (1124, 2411):
    W[f"kept{s}"] = K.walk(idents, uD, dstr, chosen, s, 60, True, "big", coins[s])
P(f"KEPT seed 1124: {int(W.kept1124.sum()):,}; seed 2411: {int(W.kept2411.sum()):,}; common {int((W.kept1124 & W.kept2411).sum()):,}")
Kp = W[W.kept1124].copy()
Kp["set"] = np.where(Kp.E <= "2020-12-31", "DISC", "CHECK")
Kp["month"] = [r.E[:7] for r in Kp.itertuples()]
Kp["Ey"] = [int(x[:4]) for x in Kp.E]
P("kept 1124 by set:", Kp.groupby("set").size().to_dict(), "| by era+set:", Kp.groupby(["era", "set"]).size().to_dict())
P("kept 1124 by era+year:", Kp.groupby(["era", "Ey"]).size().to_dict())
P(f"  distinct identities {Kp.ikey.nunique():,}; months {Kp.month.nunique()}; smallest month {Kp.month.value_counts().min()}")
P(f"  kept first-break-share {Kp.first_break.mean():.4%}")
RES["kept1124"] = int(len(Kp)); RES["kept2411"] = int(W.kept2411.sum()); RES["kept_common"] = int((W.kept1124 & W.kept2411).sum())
RES["kept_by_set"] = {k: int(v) for k, v in Kp.groupby("set").size().items()}
RES["kept_by_era_set"] = {f"{a}_{b}": int(v) for (a, b), v in Kp.groupby(["era", "set"]).size().items()}
RES["kept_by_era_year"] = {f"{a}_{b}": int(v) for (a, b), v in Kp.groupby(["era", "Ey"]).size().items()}
RES["kept_by_year_all"] = {int(k): int(v) for k, v in Kp.groupby("Ey").size().items()}
RES["kept_distinct_ident"] = int(Kp.ikey.nunique())
# gate: no identity kept twice within 60 sessions
kk = Kp.sort_values(["ikey", "uD"])
gaps = kk.groupby("ikey").uD.diff().dropna()
P(f"  GATE: min session gap between two kept events of one identity = {int(gaps.min()) if len(gaps) else 'n/a'} (must be > 60)")
RES["min_gap_kept"] = int(gaps.min()) if len(gaps) else None
assert (gaps > 60).all()

# ---------------------------------------------------------------- outcome-free prints (dates only)
def stype(e, t):
    return stores[e]["types"].get(t)


Kp["stype"] = [stype(e, t) for e, t in zip(Kp.era, Kp.ticker)]
for e in "AB":
    s = Kp[Kp.era == e]
    P(f"  era {e} unknown security type share of kept events: {s.stype.isna().mean():.3%} ({int(s.stype.isna().sum())} of {len(s)}); types {s.stype.fillna('UNKNOWN').value_counts().to_dict()}")
RES["unknown_type_share"] = {e: float(Kp[Kp.era == e].stype.isna().mean()) for e in "AB"}
# bars end inside window / guard or split date inside window (dates only)
endin, guardin, splitin = [], [], []
for r in Kp.itertuples():
    lastc = stores[r.era]["last"][r.ticker]
    endin.append(lastc < r.ci + 1 + 60)
    cl = cal[r.era]
    lo, hi = cl[r.ci + 2], cl[min(r.ci + 1 + 60, len(cl) - 1)]
    g = gA if r.era == "A" else gB
    guardin.append(any(lo <= dk[0] <= hi for dk in g.get(r.ticker, ())))
    splitin.append(any(lo <= x[0] <= hi for x in splits_B.get(r.ticker, ())) if r.era == "B" else False)
Kp["bars_end_in_window"], Kp["guard_in_window"], Kp["split_in_window"] = endin, guardin, splitin
P("  kept events whose bars end inside E..E+60, by year:", Kp[Kp.bars_end_in_window].groupby("Ey").size().to_dict())
P(f"  kept events with a guard break dated E+1..E+60: {int(Kp.guard_in_window.sum())} (by era {Kp[Kp.guard_in_window].groupby('era').size().to_dict()}); "
  f"era-B split-list date inside window: {int(Kp.split_in_window.sum())}")
RES["bars_end_in_window"] = int(Kp.bars_end_in_window.sum()); RES["guard_in_window"] = int(Kp.guard_in_window.sum()); RES["split_in_window"] = int(Kp.split_in_window.sum())
RES["bars_end_by_year"] = {int(k): int(v) for k, v in Kp[Kp.bars_end_in_window].groupby("Ey").size().items()}
RES["guard_in_window_by_era"] = {k: int(v) for k, v in Kp[Kp.guard_in_window].groupby("era").size().items()}
dB_ = Kp[(Kp.era == "B") & (Kp.raw_src == 2)]
P(f"  era B derived-only (raw_src 2) kept events: {len(dB_)} of {int((Kp.era == 'B').sum())} = {len(dB_) / max(1, int((Kp.era == 'B').sum())):.2%}; "
  f"of those within a factor of 10 of the $2 floor (raw close <= 20): {int((dB_.raw_close <= 20).sum())}")
RES["derived_only_B"] = {"n": len(dB_), "of": int((Kp.era == 'B').sum()), "near_floor": int((dB_.raw_close <= 20).sum()),
                         "share_of_kept_B": len(dB_) / max(1, int((Kp.era == 'B').sum()))}
P("  era-B raw_src of kept events:", Kp[Kp.era == "B"].raw_src.value_counts().to_dict())

# Qullamaggie coverage
for name, df_ in (("context-on break rows (pre-drop)", BR[BR.era == "A"]), ("post-drop break rows", W[W.era == "A"]), ("kept events", Kp[Kp.era == "A"])):
    nd, nu, pl = buys_on(df_[["ticker", "E"]], None)
    P(f"  Qullamaggie buys on {name}: dated {nd} + undated {nu} = {nd + nu}")
    RES[f"buys_on_{name.split(' (')[0].replace(' ', '_').replace('-', '_')}"] = nd + nu

# per-year Q coverage on kept
Kp.to_parquet(C.BIG / f"r4_events_kept{C.SUF}.parquet", index=False)
W.to_parquet(C.BIG / f"r4_events_postdrop{C.SUF}.parquet", index=False)
json.dump(RES, open(C.OUTD / f"stage1_results_r4{C.SUF}.json", "w"), indent=1, default=str)
P("written")
