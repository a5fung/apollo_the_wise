"""Stage 1f build: feature table (kept 1124 U kept 2411 U every Qullamaggie live break-row buy), NULL counts, tie shares, Qullamaggie coverage and
position tables, table hash. Outcome-free: bars <= D plus open(E) only. Writes ONCE (refuses to overwrite)."""
import hashlib, json, math, time, sys
from collections import Counter
from lib1f import *

OUTDIR = STAGE
OUT_TABLE = OUTDIR / "feature_table.tsv.gz"
L = []
def P_(s=""):
    print(s, flush=True); L.append(s)

t0 = time.time()
assert_docs()
assert not OUT_TABLE.exists(), "captured once - the feature table is written once"
FX = REPO / "tests/fixtures/qm_breakout_scorecard"
gB, fA, fB = load_dates()

# ------------------------------------------------------------------ stores + list parquets (sealed)
ctx, dfs, cals = {}, {}, {}
for era, path in (("A", OUT_DATA / "bws1124_eraA_list_ctx.parquet"), ("B", OUT_DATA / "bws1124_eraB_list_ctx.parquet")):
    S = setup_store(era)
    cal = [d.isoformat() for d in S.D.cal]
    assert cal == [l.strip() for l in open(str(path).replace(".parquet", ".cal.txt"))], "calendar file differs"
    assert S.D.cal[-1] < CUT_D
    guard = {t: sorted(date.fromordinal(int(o)).isoformat() for o in v) for t, v in S.breaks.items()} if era == "A" else gB
    ctx[era] = EraCtx(era, S, cal, guard, fA if era == "A" else fB)
    d = pd.read_parquet(path); d["era"] = era
    dfs[era] = d; cals[era] = cal
P_(f"stores + list parquets ready ({time.time() - t0:.0f}s): bridge rows A {len(dfs['A']):,} B {len(dfs['B']):,}; sealed: era B last bar {ctx['B'].S.D.cal[-1]}")

surv = pd.read_parquet(OUT_DATA / "bws1124_events_postdrop.parquet")
surv = surv.sort_values(["key", "uci", "era"]).reset_index(drop=True)
k_, u_ = surv.key.values, surv.uci.values
f60 = np.ones(len(surv), dtype=bool); same = k_[1:] == k_[:-1]; f60[1:] = ~same | ((u_[1:] - u_[:-1]) > 60)
surv["first60"] = f60
assert int(surv.kept.sum()) == 11596 and int(surv.kept2411.sum()) == 11607, (int(surv.kept.sum()), int(surv.kept2411.sum()))
surv["first10"] = surv.first10.astype(bool)

# ------------------------------------------------------------------ Qullamaggie buys: ticker / E / lo / hi ONLY
bd = pd.read_csv(FX / "buys.tsv", sep="\t", usecols=["ticker", "E"], dtype=str, keep_default_na=False)
bw = pd.read_csv(FX / "buys_undated_widened.tsv", sep="\t", usecols=["ticker", "lo", "hi"], dtype=str, keep_default_na=False)
buys = [("d%d" % i, r.ticker, r.E, r.E, "dated") for i, r in enumerate(bd.itertuples())] + [("w%d" % i, r.ticker, r.lo, r.hi, "undated") for i, r in enumerate(bw.itertuples())]
assert len(buys) == 757, len(buys)

def break_index(df, era, live_only):
    x = df[df.fire & ((df.failed == "") if live_only else True)]
    return {(era, int(c), t): cals[era][int(c) + 1] for c, t in zip(x.ci, x.ticker)}
brk_live = {}; brk_bridge = {}
for era in ("A", "B"):
    brk_live.update(break_index(dfs[era], era, True)); brk_bridge.update(break_index(dfs[era], era, False))
def by_ticker(idx):
    o = defaultdict(list)
    for (era, ci, t), E in idx.items(): o[t].append((E, era, ci))
    return {t: sorted(v) for t, v in o.items()}
bt_live, bt_bridge = by_ticker(brk_live), by_ticker(brk_bridge)
last_E = max(brk_live.values())
def place(bt, buy):
    _, t, lo, hi, kind = buy
    for E, era, ci in bt.get(t, ()):
        if lo <= E <= hi:
            return (era, ci, t, E)                          # first break row inside the window (dated: lo == hi)
    return None
placed_live = {b[0]: place(bt_live, b) for b in buys}
placed_bridge = {b[0]: place(bt_bridge, b) for b in buys}
qm_keys = {v[:3] for v in placed_live.values() if v}
P_(f"Qullamaggie buys read (ticker / E / lo / hi only): {len(buys)} (dated {len(bd)}, undated {len(bw)}); placed on a bridge-set break row {sum(1 for v in placed_bridge.values() if v)}, "
   f"on a live break row {len(qm_keys) and sum(1 for v in placed_live.values() if v)}; last break-row E on file {last_E}; distinct live rows holding a buy {len(qm_keys)}")

# ------------------------------------------------------------------ target rows
live = []
for era in ("A", "B"):
    d = dfs[era]; x = d[(d.failed == "") & d.fire].copy()
    x["D"] = [cals[era][c] for c in x.ci]; x["E"] = [cals[era][c + 1] for c in x.ci]
    live.append(x)
live = pd.concat(live, ignore_index=True)
sv = surv[["era", "ci", "ticker", "kept", "kept2411", "first10", "first60", "key", "hstr", "uci", "sectype", "ll_status", "ret126_blank", "chg10_blank", "first_ci"]].copy()
live = live.drop(columns=[c for c in ("sectype", "ll_status", "ret126_blank", "chg10_blank", "first_ci") if c in live.columns])
live = live.merge(sv, on=["era", "ci", "ticker"], how="left", indicator="srv")
live["in_surv"] = live.srv == "both"; live = live.drop(columns="srv")
for c_ in ("kept", "kept2411", "first10", "first60"): live[c_] = live[c_].fillna(False).astype(bool)
live["qm"] = [(e, int(c), t) in qm_keys for e, c, t in zip(live.era, live.ci, live.ticker)]
T = live[live.kept | live.kept2411 | live.qm].copy().sort_values(["era", "ci", "ticker"]).reset_index(drop=True)
T["sectype"] = [s if isinstance(s, str) else ctx[e].S.types.get(t, "") for s, e, t in zip(T.sectype, T.era, T.ticker)]
assert (T.kept.sum() == 11596) and (T.kept2411.sum() == 11607)
P_(f"target rows: kept(1124) {int(T.kept.sum()):,} U kept(2411) {int(T.kept2411.sum()):,} U Qullamaggie live break-row buys {int(T.qm.sum())} = {len(T):,} rows "
   f"(kept in both seeds {int((T.kept & T.kept2411).sum()):,}; QM rows that are not kept events {int((T.qm & ~T.kept).sum())}, of which dropped by 1.3 {int((T.qm & ~T.in_surv).sum())})")
assert T.E.max() <= CUT

# ------------------------------------------------------------------ night benchmarks B1 / B2
t1 = time.time()
bm = {}
for era in ("A", "B"):
    d = dfs[era]
    need = sorted(set(T.ci[T.era == era].tolist()))
    idx = d.groupby("ci").indices
    for c in need:
        for t, v in night_benchmarks(d.iloc[idx[c]]).items():
            bm[(era, c, t)] = v
P_(f"B1 / B2 built for {len(bm):,} listed names on the {len({k[:2] for k in bm}):,} nights holding a target row ({time.time() - t1:.0f}s)")

# ------------------------------------------------------------------ features
t1 = time.time()
recs, nul_cols = [], []
mism = Counter()
chk = [("level", "level"), ("adr20", "adr20"), ("close", "close"), ("dist_52w_live", "dist_52w"), ("runup6m_adr", "runup6m_adr"), ("spread10_adr", "spread10_adr"),
       ("vs_ema21_adr", "vs_ema21_adr"), ("depth_adr", "depth_adr"), ("dollar_vol20", "dollar_vol20")]
for r in T.itertuples(index=False):
    row = r._asdict()
    vals, nulls, dg = ctx[r.era].feats(row)
    for a_, b_ in chk:
        x, y = dg[a_], row[b_]
        if not ((x is None and (y is None or (isinstance(y, float) and math.isnan(y)))) or (x is not None and np.isclose(float(x), float(y), rtol=1e-9, atol=0, equal_nan=True))):
            mism[a_] += 1
    if dg["failed"] != r.failed: mism["failed"] += 1
    if dg["since_low_live"] != r.since_low: mism["since_low"] += 1
    if dg["bases_before_live"] != r.bases_before: mism["bases_before"] += 1
    if dg["base_len"] != r.base_len: mism["base_len"] += 1
    if r.era == "B" and (not np.isclose(dg["raw_close"], r.raw_close, rtol=1e-9) or dg["raw_src"] != r.raw_src): mism["raw_close_B"] += 1
    if r.era == "A" and dg["raw_src"] != 0: mism["raw_src_A"] += 1
    b1, b2 = bm[(r.era, int(r.ci), r.ticker)]
    if b1 is None or not math.isfinite(b1): nulls["B1"] = "unscored"
    else: vals["B1"] = float(b1)
    if b2 is None or not math.isfinite(b2): nulls["B2"] = "unscored"
    else: vals["B2"] = float(b2)
    rec = dict(vals); rec.update({k + "_null": v for k, v in nulls.items()})
    rec.update(raw_close_s=dg["raw_close"], raw_src_s=dg["raw_src"], level_source=dg["level_source"], range_len=dg["range_len"] if dg["range_len"] is not None else np.nan,
               f24grp=dg["f24grp"], range_exists=dg["range_exists"], short_year=dg["short_year"], dist_52w_cal=dg["dist_52w_cal"], bars_to_d=dg["bars_to_d"])
    recs.append(rec)
F = pd.DataFrame(recs)
ALL = ff.FEATS + ff.BENCH
for f in ALL:
    if f not in F: F[f] = np.nan
    if f + "_null" not in F: F[f + "_null"] = ""
    F[f + "_null"] = F[f + "_null"].fillna("")
P_(f"features computed for {len(T):,} rows in {time.time() - t1:.0f}s; consistency of the live re-call with the stored list columns: mismatches {dict(mism) or 'NONE'}")
assert not mism, mism
keep_cols = ["era", "ci", "D", "E", "ticker", "key", "hstr", "kept", "kept2411", "first10", "first60", "qm", "in_surv", "sectype", "ll_status", "ret126_blank", "chg10_blank",
             "first_ci", "rs_best", "failed"]
TT = pd.concat([T[keep_cols].reset_index(drop=True), F[[c for c in F.columns if c not in keep_cols]]], axis=1)
TT["Ey"] = TT.E.str[:4]; TT["month"] = TT.E.str[:7]
TT["set"] = np.where(TT.E <= "2020-12-31", "DISC", "CHECK")
assert (TT[TT.era == "B"].set == "CHECK").all()
TT["key"] = TT.key.fillna(-1).astype(np.int64)
P_(f"table: {len(TT):,} rows x {TT.shape[1]} columns")

# ------------------------------------------------------------------ prints: NULLs
K = TT[TT.kept].reset_index(drop=True)
P_("\n== NULL COUNTS (kept events, seed 1124; scored / NULL; reasons first-match) ==")
P_(f"{'feat':5} {'name':40} | {'scored':>6} {'NULL':>5} | {'A sc':>5} {'A nl':>5} | {'B sc':>5} {'B nl':>5} | DISC sc / CHECK sc | reasons")
nc_rows = []
for f in ALL:
    nul = K[f + "_null"] != ""; a = K.era == "A"
    rs = Counter(K.loc[nul, f + "_null"])
    P_(f"{f:5} {ff.NAMES[f][:40]:40} | {int((~nul).sum()):6d} {int(nul.sum()):5d} | {int((~nul & a).sum()):5d} {int((nul & a).sum()):5d} | {int((~nul & ~a).sum()):5d} {int((nul & ~a).sum()):5d} | "
       f"{int((~nul & (K.set == 'DISC')).sum())} / {int((~nul & (K.set == 'CHECK')).sum())} | " + ", ".join(f"{k}: {v}" for k, v in sorted(rs.items(), key=lambda x: -x[1])))
    for (e, y, why), n in K[nul].groupby(["era", "Ey", f + "_null"]).size().items():
        nc_rows.append((f, e, y, why, int(n)))
pd.DataFrame(nc_rows, columns=["feature", "era", "year", "reason", "n"]).to_csv(OUTDIR / "null_counts.tsv", sep="\t", index=False)
P_("\n== NULL reasons per feature x era x year (non-zero cells, kept events) ==")
for f in ALL:
    g = [r for r in nc_rows if r[0] == f]
    if g: P_(f"{f}: " + " | ".join(f"{e}{y} {w} {n}" for _, e, y, w, n in g))
yrs = sorted(set(zip(K.era, K.Ey)))
P_("\nkept events per era x year: " + ", ".join(f"{e}{y} {int(((K.era == e) & (K.Ey == y)).sum())}" for e, y in yrs))
P_("\n== FIRST E SCORED (era B) on the 252-session features and 200-session f21 (expected near 2022-09 for 252, 2022-07 for 200) ==")
for f in ("f10", "f11", "f21", "f22", "f23"):
    g = K[(K.era == "B") & (K[f + "_null"] == "")]
    P_(f"  {f}: first era-B E scored {g.E.min() if len(g) else 'none'}; era-B events NULL on history {int(((K.era == 'B') & (K[f + '_null'] == 'history')).sum())} of {int((K.era == 'B').sum())}; era-A NULL history {int(((K.era == 'A') & (K[f + '_null'] == 'history')).sum())}")
P_("\n== SHORT HISTORY / PASSED UNSCORED (kept events; by era x year) ==")
for nm, m in (("lower_line passed unscored (fewer than 189 bars)", K.ll_status == "insufficient_history"), ("downtrend_6m ret126 blank (passes)", K.ret126_blank.astype(bool)),
              ("downtrend_6m 50-day change blank (passes)", K.chg10_blank.astype(bool)), ("bars to D under 252 (the 252-session features NULL)", K.bars_to_d < 252),
              ("rs_6m blank (under 126 consecutive sessions; 0.5 in B1)", K.f06_null != ""), ("B1 tag 'short year' (era B, under 252 sessions of file)", K.short_year.astype(bool))):
    P_(f"  {nm}: {int(m.sum())} of {len(K)}; " + ", ".join(f"{e}{y} {int((m & (K.era == e) & (K.Ey == y)).sum())}" for e, y in yrs if int((m & (K.era == e) & (K.Ey == y)).sum())))
P_(f"  B1 pick score inputs: group strength blank (no industry code or group < 10) on {int((K.B3_null != '').sum())} of {len(K)} kept events; B3 tag 'group codes are a 2026-10-16 snapshot' applies to all")
d_cal = K[(K.f10_null == "") & K.dist_52w_cal.notna()]
diff = np.abs(d_cal.f10 - d_cal.dist_52w_cal) > 1e-9
P_(f"  f10 live by-row 52-week window vs the calendar-window value: differ on {int(diff.sum())} of {len(d_cal)} scored kept events (a hole in the window); live value used (prereg 4.0: gate/pick values as live)")
P_(f"  f02 price NULL 'derived_only' (era-B raw_src 2, A1): {int((K.f02_null == 'derived_only').sum())} of {int((K.era == 'B').sum())} era-B kept events = {100 * (K.f02_null == 'derived_only').sum() / max((K.era == 'B').sum(), 1):.1f}%")

# ------------------------------------------------------------------ tie shares / thirds / two-group minimums (DISCOVERY kept events, outcome-free)
D = K[K.set == "DISC"].reset_index(drop=True)
P_("\n== TIE SHARES + THIRDS (DISCOVERY kept events: E <= 2020-12-31; thirds by np.array_split within (era, month) holding >= 6 scored, mid-rank; two-group fallback when a third is under 20%) ==")
P_(f"{'feat':5} {'scored':>6} {'distinct':>8} {'top block':>9} {'in mo>=6':>8} {'moved':>6} {'bottom':>6} {'middle':>6} {'top':>6} {'top%':>5} {'bot%':>5}  decision")
decis = {}
def thirds_ticker(vals, tick):
    n = len(vals); order = np.lexsort((tick, vals)); out = np.empty(n, dtype=np.int8)
    for kk, p in enumerate(np.array_split(np.arange(n), 3)): out[order[p]] = kk
    return out
for f in ff.FEATS:
    if f in ff.TWO_GROUP: continue
    if f == "f24":
        parts = [("f24a", D[D.f24grp == "a"].reset_index(drop=True)), ("f24b", D[D.f24grp == "b"].reset_index(drop=True))]
    else:
        parts = [(f, D)]
    for nm, DD in parts:
        x = DD[f].to_numpy(dtype=float); ok = np.isfinite(x); sc = int(ok.sum())
        t_mid = assign_thirds(DD, f, ["era", "month"])
        t_tic = np.full(len(DD), -1, dtype=np.int8)
        for _, ix in DD[ok].groupby(["era", "month"], sort=False).indices.items():
            pos = np.flatnonzero(ok)[ix]
            if len(pos) >= 6: t_tic[pos] = thirds_ticker(x[pos], DD.ticker.to_numpy()[pos])
        inm = int((t_mid >= 0).sum()); moved = int(((t_mid != t_tic) & (t_mid >= 0)).sum())
        nb_, nm_, nt_ = (int((t_mid == q).sum()) for q in (0, 1, 2))
        vc = pd.Series(x[ok]).value_counts()
        ts, bs = nt_ / max(sc, 1), nb_ / max(sc, 1)
        fb = ts < 0.20 or bs < 0.20
        decis[nm] = "TWO-GROUP (tie-heavy fallback)" if fb else "thirds"
        extra = ""
        if nm in ("f24a", "f24b"):
            decis[nm] += (" - description only (< 300 scored)" if sc < 300 else " - candidate (>= 300 scored)")
        P_(f"{nm:5} {sc:6d} {len(vc):8d} {100 * vc.iloc[0] / max(sc, 1):8.1f}% {inm:8d} {moved:6d} {nb_:6d} {nm_:6d} {nt_:6d} {100 * ts:4.1f}% {100 * bs:4.1f}%  {decis[nm]}")
P_("  'top block' = share of scored events in the largest tied value; 'moved' = events whose third differs from a ticker-order split of the same sorted values.")
P_("\n== TWO-GROUP FEATURES (11, 14, 23): group sizes on scored DISCOVERY kept events; minimum = smaller group >= 100 events AND >= 15% ==")
for f in ff.TWO_GROUP:
    g = D[f].dropna(); ny, nn_ = int((g == 1).sum()), int((g == 0).sum()); small = min(ny, nn_); tot = ny + nn_
    ok = small >= 100 and small / tot >= 0.15
    gc = K[(K.set == "CHECK")][f].dropna()
    P_(f"  {f} {ff.NAMES[f]}: yes / no = {ny} / {nn_} of {tot}; smaller {small} = {100 * small / tot:.1f}% -> {'candidate' if ok else 'DESCRIPTION ONLY (cannot be carried)'}; check (outcome-free) yes / no = {int((gc == 1).sum())} / {int((gc == 0).sum())}")
for nm in ("a", "b"):
    g = D[(D.f24grp == nm) & (D.f24_null == "")]
    P_(f"  f24{nm} ({'opened above the level' if nm == 'a' else 'opened at or below the level'}): scored discovery events {len(g)} -> {'candidate' if len(g) >= 300 else 'DESCRIPTION ONLY (< 300)'}; all kept scored {int(((K.f24grp == nm) & (K.f24_null == '')).sum())}")
P_(f"  range length inside the 'level from a range = yes' group (description only): median {K[K.f14 == 1].range_len.median():.0f} sessions, n {int((K.f14 == 1).sum())}")
P_(f"  level source mix (kept): " + str(K.level_source.value_counts().to_dict()) + "  ('settled_after_wick' and 'five_day' both read NO on feature 14)")
P_(f"  f14 is EMPTY by the live code, not by data: a qualifying range exists at D on {int(K.range_exists.sum())} of {len(K)} kept events ({100 * K.range_exists.mean():.0f}%), but the live level is the lower of the range level and the (settled) 5-day high, and every range level is >= the 5-day high (the walk back from D only steps UP; a step inside the last 5 sessions is under 10 sessions long) -> level_source 'range' never occurs (30,000 era-A listed rows re-called: 0). Literal reading kept; 'a range exists' is description only (column range_exists).")

# ------------------------------------------------------------------ Qullamaggie coverage tables
P_("\n== QULLAMAGGIE COVERAGE (757 buys; ticker / E / lo / hi only; undated buy placed on the FIRST break row inside its window) ==")
brk_kept = set(zip(TT.era[TT.kept], TT.ci[TT.kept], TT.ticker[TT.kept])); brk_k2 = set(zip(TT.era[TT.kept2411], TT.ci[TT.kept2411], TT.ticker[TT.kept2411]))
brk_surv = set(zip(surv.era, surv.ci, surv.ticker))
rows_cov = []
for b in buys:
    pl, pb = placed_live[b[0]], placed_bridge[b[0]]
    yr = (pl[3] if pl else (pb[3] if pb else b[2]))[:4]
    rows_cov.append(dict(id=b[0], kind=b[4], year=yr, bridge=bool(pb), live=bool(pl), surv=bool(pl and pl[:3] in brk_surv), kept=bool(pl and pl[:3] in brk_kept),
                         kept2=bool(pl and pl[:3] in brk_k2), era=(pl[0] if pl else (pb[0] if pb else ""))))
CV = pd.DataFrame(rows_cov)
P_(f"{'year':6} {'buys':>5} {'bridge':>7} {'live':>5} {'post-drop':>9} {'kept 1124':>9} {'kept 2411':>9}")
for y, g in CV.groupby("year"):
    P_(f"{y:6} {len(g):5d} {int(g.bridge.sum()):7d} {int(g.live.sum()):5d} {int(g.surv.sum()):9d} {int(g.kept.sum()):9d} {int(g.kept2.sum()):9d}")
P_(f"{'ALL':6} {len(CV):5d} {int(CV.bridge.sum()):7d} {int(CV.live.sum()):5d} {int(CV.surv.sum()):9d} {int(CV.kept.sum()):9d} {int(CV.kept2.sum()):9d}   (by year = the placed row's E year, else the buy's own)")
P_("  by era of the placed row: " + ", ".join(f"{e} live {int(g.live.sum())} kept {int(g.kept.sum())}" for e, g in CV[CV.live].groupby("era")))
P_("  by kind: " + ", ".join(f"{k} {len(g)} buys, bridge {int(g.bridge.sum())}, live {int(g.live.sum())}, kept {int(g.kept.sum())}" for k, g in CV.groupby("kind")))
# two buys placed on the same row (distinct buys, one row)
P_(f"  distinct live rows holding a buy {len(qm_keys)} for {int(CV.live.sum())} placed buys (two buys can sit on one row); buys with E after the last break row on file ({last_E}): {sum(1 for b in buys if b[3] > last_E)}")

# ------------------------------------------------------------------ Qullamaggie position tables
def wilson(k, n, z=1.645):
    if n == 0: return (float("nan"),) * 2
    p = k / n; den = 1 + z * z / n; ctr = (p + z * z / (2 * n)) / den; hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return ctr - hw, ctr + hw
KK = TT[TT.kept].reset_index(drop=True)
QM = TT[TT.qm].reset_index(drop=True)
P_(f"\n== QULLAMAGGIE POSITION (his {len(QM)} live break-row buys placed against the kept-event (era, E-month) group on each feature; BEFORE any outcome) ==")
P_("   placement: a buy that IS a kept event takes its own third; else it is inserted as one more member of its (era, month) group (>= 6 kept events scored) and read at its mid-rank third.")
P_("   shares with 90% Wilson interval; the 'against Qullamaggie's buys' tag (winning third < 29%) waits for the discovery direction.")
P_(f"{'feat':5} {'placed':>6} {'bottom':>16} {'middle':>16} {'top':>16}   (share, [90% interval]); two-group: yes-share vs kept-event yes-share")
POS = []
def place_buy(feature, qrow, K_pop):
    """third of a buy within its (era, month) kept group on `feature`; None if unplaced (NULL value or fewer than 6 kept events scored)."""
    x = qrow[feature]
    if not np.isfinite(x): return None
    g = K_pop[(K_pop.era == qrow["era"]) & (K_pop.month == qrow["month"]) & K_pop[feature].notna()]
    vals = g[feature].to_numpy(dtype=float)
    if qrow["kept"]:                                       # own third among the kept group (it is one of them)
        if len(vals) < 6: return None
        me = np.flatnonzero(((g.ci == qrow["ci"]) & (g.ticker == qrow["ticker"])).to_numpy())
        return int(thirds_block(vals)[me[0]]) if len(me) else None
    if len(vals) < 6: return None
    return int(thirds_block(np.append(vals, x))[-1])      # inserted as one more member; tied blocks read at the mid-rank third
for f in ff.FEATS + ff.BENCH:
    if f in ff.TWO_GROUP:
        q = QM[QM[f].notna()]; ny = int((q[f] == 1).sum()); n = len(q); lo, hi = wilson(ny, n)
        ky = KK[f].dropna(); ref = (ky == 1).mean()
        P_(f"{f:5} {n:6d}   yes {100 * ny / max(n, 1):5.1f}% [{100 * lo:4.1f}, {100 * hi:4.1f}]   (kept events: yes {100 * ref:.1f}%)")
        POS.append((f, n, ny / max(n, 1), ref)); continue
    pops = [("f24a", "f24", KK[KK.f24grp == "a"], QM[QM.f24grp == "a"]), ("f24b", "f24", KK[KK.f24grp == "b"], QM[QM.f24grp == "b"])] if f == "f24" else [(f, f, KK, QM)]
    for nm, col, Kp, Qp in pops:
        cnt = Counter();
        Kp = Kp.reset_index(drop=True)
        for q in Qp.to_dict("records"):
            th = place_buy(col, q, Kp)
            if th is not None: cnt[th] += 1
        n = sum(cnt.values()); cells = []
        for t in (0, 1, 2):
            lo, hi = wilson(cnt[t], n); cells.append(f"{100 * cnt[t] / max(n, 1):5.1f}% [{100 * lo:4.1f},{100 * hi:4.1f}]")
        P_(f"{nm:5} {n:6d} " + " ".join(f"{c:>16}" for c in cells))
        POS.append((nm, n, [cnt[t] / max(n, 1) for t in (0, 1, 2)]))
P_("  B1-B3 above print in this one block under the fixed line: not a test of the grade - the grade is judged on Qullamaggie's buys only (#717); B1 is in-sample for 2017-20 (fitted on his picks); B3 codes are a 2026-10-16 snapshot.")

# ------------------------------------------------------------------ hash the table
out = TT.sort_values(["era", "ci", "ticker"]).reset_index(drop=True)
out.to_csv(OUT_TABLE, sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
sha = hashlib.sha256(OUT_TABLE.read_bytes()).hexdigest()
nsha = hashlib.sha256((OUTDIR / "null_counts.tsv").read_bytes()).hexdigest()
P_(f"\nfeature_table.tsv.gz written: {len(out):,} rows x {out.shape[1]} columns; sha256 {sha}")
P_(f"null_counts.tsv sha256 {nsha}")
P_("code sha256: " + " | ".join(f"{n} {hashlib.sha256((OUTDIR / n).read_bytes()).hexdigest()[:16]}" for n in ("ff.py", "lib1f.py", "build.py")))
(OUTDIR / "1f_build.txt").write_text("\n".join(L) + "\n")
json.dump(dict(table_sha256=sha, rows=len(out), cols=int(out.shape[1]), kept=int(out.kept.sum()), kept2411=int(out.kept2411.sum()), qm_rows=int(out.qm.sum()), secs=round(time.time() - t0)),
          open(OUTDIR / "1f_build_result.json", "w"), indent=1)
