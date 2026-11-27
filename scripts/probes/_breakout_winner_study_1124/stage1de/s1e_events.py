"""Stage 1e: events. Identity map -> the 1.3 drops (per reason x era x year) -> q grid + rule -> keep walk (seeds 1124, 2411). Outcome-free prints.
Reads: the two list parquets (1b / 1d), bars <= D only (context_gates re-called on era-A live break rows), guard + audit-flag DATES (klass/ticker/date only, <= 2024-12-31),
the EP pair file (overlap closes only). The only post-E reads are DATES: guard / flag / split-list dates, era-A raw/adjusted factor steps, bar end dates, in the window print."""
import hashlib, json, time
from collections import Counter, defaultdict
from lib import *

OUT = HERE
SEEDS = (1124, 2411)
QS = [1, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10]
FLAG_KLASSES = {"known_adjustment_event", "discontinuous_across_known_adjustment"}
L = []
def P_(s=""):
    print(s, flush=True); L.append(s)

# ---------------------------------------------------------------- the walk (also run as a positive control on the 11-13 capture)
def u_of(seed, h, d):
    return int.from_bytes(hashlib.sha256(f"{seed}|{h}|{d}".encode()).digest()[:8], "big") / 2.0 ** 64

def walk(keys, uci, hstr, dstr, q, seed):
    """keys/uci/hstr/dstr aligned arrays sorted by (key, uci). Eligible when uci - last_kept > 60 (strict); kept when the hash coin < q."""
    keep = np.zeros(len(keys), dtype=bool); last_k, last = None, -10 ** 9
    for i in range(len(keys)):
        if keys[i] != last_k: last_k, last = keys[i], -10 ** 9
        if uci[i] - last > 60 and u_of(seed, hstr[i], dstr[i]) < q:
            keep[i] = True; last = uci[i]
    return keep

def first10(keys, uci):
    f = np.ones(len(keys), dtype=bool)
    same = keys[1:] == keys[:-1]
    f[1:] = ~same | ((uci[1:] - uci[:-1]) > 10)
    return f

# ---- positive control: the 11-13 capture, identity = ticker (advisor 14; expected from design/count_events_v2_forward_hash.txt)
CAP = DATA / "bv1_pick_model_1113" / "list_eraA_4pct.parquet"
cap = pd.read_parquet(CAP, columns=["ci", "ticker", "fire"]); capcal = [l.strip() for l in open(str(CAP) + ".cal.txt")]
cf = cap[cap.fire == 1].sort_values(["ticker", "ci"]).reset_index(drop=True)
ck, cu = cf.ticker.values, cf.ci.values; cd = np.array([capcal[c] for c in cu]); cf10 = first10(ck, cu)
exp = {(1.0, 1124): 15312, (0.2, 1124): 10514, (0.2, 2411): 10545}
ctl = {}
for (q, sd), n in exp.items():
    kp = walk(ck, cu, ck, cd, q, sd); ctl[(q, sd)] = kp
    assert int(kp.sum()) == n, ((q, sd), int(kp.sum()), n)
sh = int((ctl[(0.2, 1124)] & ctl[(0.2, 2411)]).sum()); f10 = cf10[ctl[(0.2, 1124)]].mean()
assert sh == 1108 and abs(f10 - 0.297) < 0.0006, (sh, f10)
P_(f"POSITIVE CONTROL (11-13 capture, identity = ticker): q=1 {exp[(1.0,1124)]:,} | q=1/5 {exp[(0.2,1124)]:,} events, first-break share {f10:.1%} | seed 2411 {exp[(0.2,2411)]:,}, shared {sh:,} -- all equal count_events_v2_forward_hash.txt: PASS")

# ---------------------------------------------------------------- stores, rows
t0 = time.time()
stores = {}
for era in ("A", "B"):
    S = setup_store(era); stores[era] = (S, dict(G))
SA, SB = stores["A"][0], stores["B"][0]
calA, calB = [d.isoformat() for d in SA.D.cal], [d.isoformat() for d in SB.D.cal]
ucal = sorted(set(calA) | set(calB)); uidx = {d: i for i, d in enumerate(ucal)}
assert all(a == b for a, b in zip(calA[calA.index(calB[0]):], calB)), "calendars disagree on the overlap"
P_(f"stores ready ({time.time() - t0:.0f}s); unified calendar {ucal[0]}..{ucal[-1]} ({len(ucal)} sessions)")

dfs = {}
for era, path in (("A", OUT_DATA / "bws1124_eraA_list_ctx.parquet"), ("B", OUT_DATA / "bws1124_eraB_list_ctx.parquet")):
    d = pd.read_parquet(path); cal = calA if era == "A" else calB
    live = d[d.failed == ""]
    brk = live[live.fire].copy()
    brk["era"] = era
    brk["D"] = [cal[c] for c in brk.ci]; brk["E"] = [cal[c + 1] for c in brk.ci]
    dfs[era] = (d, live, brk)
    P_(f"era {era}: bridge rows {len(d):,}, live-list rows {len(live):,}, live break rows {len(brk):,} on {live.ci.nunique()} nights {brk.D.min()}..{brk.D.max()}")
assert dfs["A"][2].D.max() < "2022-04-01" and dfs["B"][2].D.min() >= "2022-04-01"
assert len(dfs["A"][2]) == 114847, len(dfs["A"][2])           # 1b's live break-row count

# ---- era-A: first/last bar + the context checks re-called by the live code (advisor 12)
def ctxwork(rows):
    S, facts = G["S"], G["facts"]; D = S.D; out = []; cache = {}
    for ci, t, adr in rows:
        k = D.tid[t]
        if k not in cache: cache[k] = runner.bars_for(D, k)
        bars, cidx = cache[k]; Di = int(np.searchsorted(cidx, ci))
        cg = bv.context_gates(bars, Di, adr20=adr)
        llv, dtv = cg["lower_line"]["value"], cg["downtrend_6m"]["value"]
        out.append((llv["status"], dtv["ret126"] is None, dtv["s50_chg10_adr"] is None))
    return out
bA = dfs["A"][2]
G.clear(); G.update(stores["A"][1])
rows = list(zip(bA.ci.tolist(), bA.ticker.tolist(), bA.adr20.tolist()))
chunks = [rows[i::32] for i in range(32)]
with get_context("fork").Pool(8) as pool: parts = pool.map(ctxwork, chunks)
res = [None] * len(rows)
for i, p in enumerate(parts):
    for j, x in enumerate(p): res[i + 32 * j] = x
bA["ll_status"] = [x[0] for x in res]; bA["ret126_blank"] = [x[1] for x in res]; bA["chg10_blank"] = [x[2] for x in res]
bA["first_ci"] = [int(SA.D.ci[int(SA.D.start[SA.D.tid[t]])]) for t in bA.ticker]
bA["last_ci"] = [int(SA.D.ci[int(SA.D.stop[SA.D.tid[t]]) - 1]) for t in bA.ticker]
bA["raw_close"] = [np.nan] * len(bA); bA["raw_src"] = 0
bA["sectype"] = [SA.types.get(t, "") for t in bA.ticker]
# consistency: for era B the stored columns equal a fresh live call on a sample
bB = dfs["B"][2]
G.clear(); G.update(stores["B"][1])
smp = bB.sample(300, random_state=1124)
sres = ctxwork(list(zip(smp.ci.tolist(), smp.ticker.tolist(), smp.adr20.tolist())))
assert all(x[0] == s and x[1] == r and x[2] == c for x, s, r, c in zip(sres, smp.ll_status, smp.ret126_blank, smp.chg10_blank)), "era-B stored context columns differ from a fresh live call"
brk = pd.concat([bA, bB], ignore_index=True)
brk["Dy"] = brk.D.str[:4]; brk["Ey"] = brk.E.str[:4]
brk["unscored"] = (brk.ll_status == "insufficient_history") | brk.ret126_blank | brk.chg10_blank
brk["d_file_start"] = (brk.first_ci <= 5) & brk.unscored

# ---- guard / flag dates (<= 2024-12-31 at parse)
def parse_guard(path):
    out, dropped = {}, 0
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, ib = f.index("symbol"), f.index("breaks"); continue
        if len(f) <= ib or not f[ib]: continue
        ds = [x.split(":")[0] for x in f[ib].split(";")]
        keep = [x for x in ds if x <= CUT]; dropped += len(ds) - len(keep)
        if keep: out[f[ik]] = sorted(keep)
    return out, dropped
def parse_flags(path):
    out = defaultdict(list); n = 0; dropped = 0
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, it, id_ = f.index("klass"), f.index("ticker"), f.index("date"); continue
        if f[id_] > CUT: dropped += 1; continue
        if f[ik] in FLAG_KLASSES: out[f[it]].append(f[id_]); n += 1
    return {k: sorted(v) for k, v in out.items()}, n, dropped
gA = {t: sorted(date.fromordinal(int(o)).isoformat() for o in v) for t, v in SA.breaks.items()}
gB, dB = parse_guard(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
fA, nfA, dfA_ = parse_flags(DATA / "cb702_pre_v2/audit_1023/price/A_flags.tsv")
fB, nfB, dfB_ = parse_flags(DATA / "audit_runs_2026-10-23/B_flags.tsv")
assert max(max(v) for v in gB.values()) <= CUT and max(max(v) for v in fB.values()) <= CUT and max(max(v) for v in gA.values()) <= "2022-06-30"
P_(f"guard B: break dates after {CUT} dropped at parse: {dB}; audit flags (known_adjustment_event / discontinuous_across_known_adjustment) kept A {nfA}, B {nfB}; B flag rows dated after the cut dropped: {dfB_}")
G_ = {"A": gA, "B": gB}; F_ = {"A": fA, "B": fB}; CAL_ = {"A": calA, "B": calB}
def hit(dates, lo, hi):
    if not dates: return False
    import bisect
    i = bisect.bisect_left(dates, lo); return i < len(dates) and dates[i] <= hi
brk["d_guard"] = [hit(G_[e].get(t), CAL_[e][c - 85], CAL_[e][c + 1]) for e, t, c in zip(brk.era, brk.ticker, brk.ci)]
brk["d_flag"] = [hit(F_[e].get(t), CAL_[e][c - 85], CAL_[e][c + 1]) for e, t, c in zip(brk.era, brk.ticker, brk.ci)]
brk["d_window"] = [(c + 1 + 60 > (len(calA) - 1 if e == "A" else len(calB) - 1)) or (e == "B" and CAL_[e][min(c + 61, len(calB) - 1)] > CUT) for e, c in zip(brk.era, brk.ci)]
brk["drop_any"] = brk.d_guard | brk.d_flag | brk.d_file_start | brk.d_window
def first_reason(r):
    return "window_end" if r.d_window else ("file_start" if r.d_file_start else ("guard" if r.d_guard else ("flag" if r.d_flag else "")))
brk["reason"] = [first_reason(r) for r in brk.itertuples()]
P_("\n== DROPS (live break rows; exclusive reason = first of window_end > file_start > guard > flag; per era x year of E) ==")
for e in ("A", "B"):
    x = brk[brk.era == e]
    P_(f"era {e}: break rows {len(x):,}; dropped {int(x.drop_any.sum()):,} ({100 * x.drop_any.mean():.2f}%) | non-exclusive: window_end {int(x.d_window.sum())}, file_start {int(x.d_file_start.sum())}, guard {int(x.d_guard.sum())}, flag {int(x.d_flag.sum())}")
    tab = x[x.drop_any].groupby(["Ey", "reason"]).size().unstack(fill_value=0)
    tot = x.groupby("Ey").size()
    P_("  per year of E (rows / dropped by exclusive reason): " + "; ".join(f"{y}: {tot[y]:,} / " + (", ".join(f"{c} {int(tab.loc[y, c])}" for c in tab.columns if y in tab.index and tab.loc[y, c]) or "0") for y in tot.index))
xb = brk[(brk.era == "B")]
fsB = xb[xb.d_file_start]
P_(f"file-start drops in era B: {len(fsB):,}; latest D among them {fsB.D.max() if len(fsB) else None}; era-B break rows with D before 2022-06-24: {int((xb.D < '2022-06-24').sum()):,}, of which dropped (any reason) {int(xb[xb.D < '2022-06-24'].drop_any.sum()):,}")
surv = brk[~brk.drop_any].copy()
P_(f"break rows surviving all drops: {len(surv):,} (A {int((surv.era == 'A').sum()):,}, B {int((surv.era == 'B').sum()):,})")

# ---------------------------------------------------------------- identity (EP pair map; advisor 10/11: connected components)
pairs = pd.read_csv(REPO / "scripts/probes/_ep_winner_study_1121/build/stage1/identity_pairs_all.tsv", sep="\t", dtype={"a": str, "b": str}, keep_default_na=False)
OFF = pairs[pairs.first10_equal]; fullk = set(zip(pairs.a, pairs.b))
par = {}
def find(x):
    par.setdefault(x, x)
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
def union(x, y): par[find(x)] = find(y)
for a, b in zip(OFF.a, OFF.b): union(("A", a), ("B", b))
tkA, tkB = set(surv[surv.era == "A"].ticker), set(surv[surv.era == "B"].ticker)
allA, allB = set(brk[brk.era == "A"].ticker), set(brk[brk.era == "B"].ticker)
def ov_sessions(t):
    n = []
    for S in (SA, SB):
        k = S.D.tid.get(t)
        n.append(set() if k is None else {S.D.cal[i].isoformat() for i in S.D.ci[int(S.D.start[k]):int(S.D.stop[k])] if "2021-09-27" <= S.D.cal[i].isoformat() <= "2022-06-30"})
    return len(n[0] & n[1])
merged_by_name, kept_sep = 0, 0
for t in sorted(allA & allB):
    if find(("A", t)) == find(("B", t)): continue
    if (t, t) not in fullk and ov_sessions(t) < 40: union(("A", t), ("B", t)); merged_by_name += 1     # untestable: same symbol, under 40 shared sessions (EP: merges by name)
    else: kept_sep += 1
comp_members = defaultdict(set)
for t in allA: comp_members[find(("A", t))].add(("A", t))
for t in allB: comp_members[find(("B", t))].add(("B", t))
for n_ in list(par):
    if find(n_) in comp_members: comp_members[find(n_)].add(n_) if (n_[0] == "A" and n_[1] in allA) or (n_[0] == "B" and n_[1] in allB) else None
hs, cid = {}, {}
for r, mem in comp_members.items():
    As = sorted(t for e, t in mem if e == "A"); Bs = sorted(t for e, t in mem if e == "B")
    hs[r] = As[0] if As else Bs[0]
for i, r in enumerate(sorted(comp_members, key=lambda r: hs[r] + str(r))): cid[r] = i
sizes = Counter((sum(1 for e, _ in m if e == "A"), sum(1 for e, _ in m if e == "B")) for m in comp_members.values())
P_(f"\n== IDENTITY: map pairs {len(OFF):,} (EP pair file, overlap closes only); components over event tickers {len(comp_members):,}; same-symbol A/B tickers kept as TWO identities (fail the return test) {kept_sep}; merged by name (untestable, < 40 shared sessions) {merged_by_name}")
P_("  component shape (era-A tickers, era-B tickers): " + ", ".join(f"{k}: {v}" for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])[:10]) + f"; components with >1 ticker in an era: {sum(v for (a, b), v in sizes.items() if a > 1 or b > 1)}")
def key_of(e, t): return cid[find((e, t))]
def hstr_of(e, t): return hs[find((e, t))]
surv["key"] = [key_of(e, t) for e, t in zip(surv.era, surv.ticker)]; surv["hstr"] = [hstr_of(e, t) for e, t in zip(surv.era, surv.ticker)]
surv["uci"] = [uidx[d] for d in surv.D]
surv = surv.sort_values(["key", "uci", "era"]).reset_index(drop=True)
assert not surv.duplicated(["key", "uci"]).any(), "an (identity, D) appears twice (both eras)"
k_, u_, h_, d_ = surv.key.values, surv.uci.values, surv.hstr.values, surv.D.values
surv["first10"] = first10(k_, u_)
share_all = surv.first10.mean()
P_(f"first break after 10 quiet sessions (post-drop rows, both eras, identity-keyed): {share_all:.1%} of {len(surv):,} break rows")
P_("\n== q GRID (seed 1124): kept events and share that are a first break after 10 quiet sessions; rule: largest q with share <= 2 x the break rows' share")
grid = {}
for q in QS:
    kp = walk(k_, u_, h_, d_, q, 1124); grid[q] = kp
    ok = kp.mean() * 0 + surv.first10[kp].mean() <= 2 * share_all
    P_(f"  q {q:.4f}: {int(kp.sum()):6,} events, tickers-identities {surv.key[kp].nunique():,}, first-break share {surv.first10[kp].mean():.1%} {'<= 2x' if ok else '> 2x'} ({2 * share_all:.1%})")
qsel = max(q for q in QS if surv.first10[grid[q]].mean() <= 2 * share_all)
P_(f"q SELECTED by the frozen rule: {qsel:.4f}")
keep1 = grid[qsel]; keep2 = walk(k_, u_, h_, d_, qsel, 2411)
surv["kept"] = keep1; surv["kept2411"] = keep2
shared = int((keep1 & keep2).sum())
P_(f"keep walk at q={qsel:.4f}: seed 1124 {int(keep1.sum()):,} events; seed 2411 {int(keep2.sum()):,}; shared {shared:,}")
K = surv[surv.kept].copy()
for e in ("A", "B"):
    x = K[K.era == e]; P_(f"  era {e} kept {len(x):,}: per year of E {x.groupby('Ey').size().to_dict()}; smallest month {x.groupby(x.E.str[:7]).size().min()}")
surv.drop(columns=[c for c in surv.columns if c in ()]).to_parquet(OUT_DATA / "bws1124_events_postdrop.parquet", index=False)
K.to_csv(OUT / "events_kept_seed1124.tsv", sep="\t", index=False)
surv[surv.kept2411].to_csv(OUT / "events_kept_seed2411.tsv", sep="\t", index=False)
(OUT / "calendars_union.txt").write_text("\n".join(ucal))

# ---------------------------------------------------------------- outcome-free prints
P_("\n== PRINTS (outcome-free) ==")
seam = surv[(surv.D == "2022-04-01")]
P_(f"seam night D 2022-04-01 (era B's first night): post-drop break rows {len(seam)} (era {sorted(set(seam.era))}), kept {int(seam.kept.sum())}; era-A rows on D >= 2022-04-01: {int(((surv.era == 'A') & (surv.D >= '2022-04-01')).sum())}")
for e in ("A", "B"):
    for nm, x in ((f"kept events", K[K.era == e]), (f"all post-drop break rows", surv[surv.era == e])):
        unk = (x.sectype == "") | x.sectype.isna()
        P_(f"unknown security type, era {e}, {nm}: {int(unk.sum()):,} of {len(x):,} = {100 * unk.mean():.1f}%; per type {x.sectype.replace('', 'unknown').value_counts().to_dict()}")
# bars end inside window
def ends_in(row_df):
    out = []
    for e, t, c in zip(row_df.era, row_df.ticker, row_df.ci):
        S = SA if e == "A" else SB
        out.append(int(S.D.ci[int(S.D.stop[S.D.tid[t]]) - 1]) < c + 1 + 60)
    return np.array(out)
K["ends_in"] = ends_in(K)
for e in ("A", "B"):
    x = K[K.era == e]
    P_(f"kept events whose bars end inside E..E+60, era {e}: {int(x.ends_in.sum())} of {len(x):,}; per year of E {x[x.ends_in].groupby('Ey').size().to_dict()}; years tagged 'few delisted names on file': 2017-18 lines")
# guard / split / flag dates inside the window (dates only)
splitsB, _ = R.load_splits_sealed(CB_ := (DATA / "cb702" / "cb702_splits.psv"))
def win_dates(e, t, c):
    cal = CAL_[e]; lo, hi = cal[c + 1], cal[c + 1 + 60]
    g = hit(G_[e].get(t), lo, hi); fl = hit(F_[e].get(t), lo, hi)
    if e == "B":
        sp = hit(sorted(d.isoformat() for d, _ in [(x[0], x[1]) for x in splitsB.get(t, [])]), lo, hi)
    else:
        S = SA; k = S.D.tid[t]; a, b = int(S.D.start[k]), int(S.D.stop[k]); F = S.raw_factor[a:b]; cis = S.D.ci[a:b]
        st = np.flatnonzero(np.abs(F[1:] / F[:-1] - 1) > R.BRIDGE_TOL) + 1
        sp = any(lo <= cal[int(cis[j])] <= hi for j in st)
    return g, sp, fl
wd = [win_dates(e, t, c) for e, t, c in zip(K.era, K.ticker, K.ci)]
K["w_guard"], K["w_split"], K["w_flag"] = [x[0] for x in wd], [x[1] for x in wd], [x[2] for x in wd]
for e in ("A", "B"):
    x = K[K.era == e]
    P_(f"kept events with a date inside E..E+60, era {e} (n {len(x):,}): guard break {int(x.w_guard.sum())}, " + ("split-list date" if e == "B" else "raw/adjusted factor step (era A has no split list)") + f" {int(x.w_split.sum())}, audit adjustment flag {int(x.w_flag.sum())}, any {int((x.w_guard | x.w_split | x.w_flag).sum())} = {100 * (x.w_guard | x.w_split | x.w_flag).mean():.2f}%; per year {x[x.w_guard | x.w_split | x.w_flag].groupby('Ey').size().to_dict()}")
xb = K[K.era == "B"]
der = xb[xb.raw_src == 2]; near = der[(der.raw_close >= 0.2) & (der.raw_close <= 20)]
P_(f"era-B derived-only events (raw_src 2, no pulled close under A1): {len(der):,} of {len(xb):,} kept = {100 * len(der) / max(len(xb), 1):.2f}%; within a factor of 10 of the $2 floor (raw close 0.2..20): {len(near):,} = {100 * len(near) / max(len(xb), 1):.2f}%")
P_(f"  A1: era-B price partly derived TAG FIRES (A1 rule; both readings exceed 1% of era-B kept events: {len(der) > 0.01 * len(xb) and len(near) > 0.01 * len(xb)}). Share of era-B pool-candidate name-nights that are derived-only (stage 1c): 7.20% (A1 text says 0.80%, that was the 77-name figure).")
P_("era-B raw-volume sizing line (the pull's raw volume): UNAVAILABLE under A1 (the pull is discarded and never opened)")
K.to_csv(OUT / "events_kept_seed1124.tsv", sep="\t", index=False)
(OUT / "1e.txt").write_text("\n".join(L) + "\n")
json.dump(dict(q=qsel, n_kept=int(keep1.sum()), n_kept_2411=int(keep2.sum()), shared=shared, break_rows=len(brk), post_drop=len(surv), share_all=share_all), open(OUT / "1e_result.json", "w"), indent=1)
