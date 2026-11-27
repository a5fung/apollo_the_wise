"""Stage 1d (part 2): the era-B overlap bridge. Nights D 2022-04-01 .. 2022-06-29 are built from BOTH stores (era A bars end 2022-06-30; E <= 2022-06-30).
CAUSE TAXONOMY (written before any difference was looked at; every difference gets the FIRST cause whose mechanical test it passes, else UNTRACED):
  twin      : ticker in both stores with >= 40 shared overlap sessions whose (t,t) pair does not even pass the EP pair file's FULL test (returns disagree) = a reused symbol
              (REFINED after run 1: run 1 used 'not in the first-10 map', which also caught same-company pairs whose closes differ in the 4th decimal)
  adj_step  : B/A adjusted-close ratio over the shared sessions to D steps (max/min-1 > BRIDGE_TOL 0.005), or B's raw scale fell back to the split list
              (raw_src 2 for a name in both stores), or an era-A guard break / audit flag lies in D-85..D
  pool      : (rs gate) both stores' strength ranks recomputed on the INTERSECTION pool agree; (membership) the other store's own floors/guard/type/history
              test excludes the name (diagnostic mirrors R.night_members test for test and is asserted equal to it)
  rank_inputs/session_set: (ADDED after run 2: B lacks sessions A has) rs: the name's r21/r63/r126 differ between the stores; others: recompute on A cut to B's first date AND to B's session set equals B
  file_start: the item recomputed on era-A bars CUT to >= 2021-09-27 (era B's first date) equals era B's value (proof by recomputation, not by date)
  type_snap : the two stores' 2026 security-type snapshots differ for the ticker (the fund / ETV rule's input)
  bar_values: (ADDED after run 1, which showed the two files carry different high / low / volume feeds on some sessions and 1e-4 close rounding) the item's own input fields
              (closes for rs / ema21 / sma50 / downtrend; high, low, close for the rest; plus E's high for the break) differ between the stores, scaled, on an overlap
              session inside the look-back. Identical inputs with a different output would be UNTRACED.
Gate: every difference traced; untraced -> stop. Prints agreement per gate; the < 130-bar gates are flagged."""
import json, pickle, time
from collections import Counter, defaultdict
from lib import *

OV_LO, OV_HI = date(2022, 4, 1), date(2022, 6, 29)
FIRST_B = date(2021, 9, 27)
BRIDGE_TOL = R.BRIDGE_TOL
L = []
def P_(s=""):
    print(s, flush=True); L.append(s)

def setup_and_eval(era):
    S = setup_store(era)
    g = dict(G)
    nights = [ci for ci, d in enumerate(S.D.cal) if OV_LO <= d <= OV_HI]
    df = run_nights(nights, keep_all=True)
    df["D"] = [S.D.cal[c].isoformat() for c in df.ci]
    pools = {}
    for ci in nights:
        members, _ = R.night_members(S, g["facts"], ci, g["rows_at"])
        pools[S.D.cal[ci].isoformat()] = (ci, {m["ticker"]: m for m in members})
    return S, g, nights, df, pools

t0 = time.time()
SA, GA, nA, dfA, poolA = setup_and_eval("A")
SB, GB, nB, dfB, poolB = setup_and_eval("B")
assert [SA.D.cal[c] for c in nA] == [SB.D.cal[c] for c in nB], "overlap calendars differ"
dates = [SA.D.cal[c].isoformat() for c in nA]
P_(f"1d overlap bridge: {len(dates)} nights {dates[0]}..{dates[-1]}; evaluated name-nights A {len(dfA):,} B {len(dfB):,} ({time.time() - t0:.0f}s)")

# ---- identity sets (twin) from the EP pair file (overlap closes only) -------------------------------------------------
pairs = pd.read_csv(REPO / "scripts/probes/_ep_winner_study_1121/build/stage1/identity_pairs_all.tsv", sep="\t", dtype={"a": str, "b": str}, keep_default_na=False)
okk = set(zip(pairs.a[pairs.first10_equal], pairs.b[pairs.first10_equal]))
def span_dates(S, t):
    k = S.D.tid.get(t)
    if k is None: return {}
    a, b = int(S.D.start[k]), int(S.D.stop[k])
    return {S.D.cal[i].isoformat(): float(S.D.c[a + j]) for j, i in enumerate(S.D.ci[a:b]) if date(2021, 9, 27) <= S.D.cal[i] <= date(2022, 6, 30)}
span_cache = {}
def spans(t):
    if t not in span_cache: span_cache[t] = (span_dates(SA, t), span_dates(SB, t))
    return span_cache[t]
fullk = set(zip(pairs.a, pairs.b))
def is_twin(t):
    a, b = spans(t)
    shared = set(a) & set(b)
    return len(shared) >= 40 and (t, t) not in fullk
_al = {}
def aligned(t):
    if t not in _al:
        out = {}
        for key, S in (("A", SA), ("B", SB)):
            k = S.D.tid.get(t)
            if k is None: out[key] = {}; continue
            a, b = int(S.D.start[k]), int(S.D.stop[k])
            out[key] = {S.D.cal[i].isoformat(): (S.D.o[a + j], S.D.h[a + j], S.D.l[a + j], S.D.c[a + j], S.D.v[a + j]) for j, i in enumerate(S.D.ci[a:b]) if FIRST_B <= S.D.cal[i] <= date(2022, 6, 30)}
        sh = sorted(set(out["A"]) & set(out["B"]))
        _al[t] = (sh, np.array([out["A"][x] for x in sh]), np.array([out["B"][x] for x in sh]))
    return _al[t]
C_ONLY = ("rs", "sma50_falling_under", "downtrend_6m")   # ema21 divides by ADR20 (high, low, close) so it is NOT close-only
def bar_values_differ(t, d, gname):
    sh, A_, B_ = aligned(t)
    if not len(sh): return False
    last = [i for i, x in enumerate(sh) if x <= d]
    if not last: return False
    n = last[-1] + 1
    if gname.startswith("break"):
        e = SA.D.cal[SA.D.cal.index(date.fromisoformat(d)) + 1].isoformat()
        n = max(n, (sh.index(e) + 1) if e in sh else n)
    f = np.median(B_[:n, 3] / A_[:n, 3])
    cols = [3] if gname in C_ONLY else [1, 2, 3]
    return bool((np.abs(B_[:n][:, cols] / (A_[:n][:, cols] * f) - 1) > 1e-9).any())
def ratio_step(t, d):
    a, b = spans(t)
    sh = [x for x in sorted(set(a) & set(b)) if x <= d]
    if len(sh) < 2: return False
    r = np.array([b[x] / a[x] for x in sh])
    return bool(r.max() / r.min() - 1 > BRIDGE_TOL)
def guard_near(t, d):
    dd = date.fromisoformat(d).toordinal()
    br = SA.breaks.get(t)
    return bool(br is not None and len(br) and ((br > dd - 120) & (br <= dd)).any())

# ---- pool-level: membership, ranks on the intersection pool -----------------------------------------------------------
def why_not(S, g, ci, t):
    facts = g["facts"]; k = S.D.tid.get(t)
    if k is None: return "absent_in_file"
    f = facts[k]; pos = int(np.searchsorted(f["cidx"], ci))
    if pos >= len(f["cidx"]) or f["cidx"][pos] != ci: return "no_bar_that_night"
    ok, why = bv.security_admitted(t, S.types.get(t), S.etv_names.get(t))
    if why == "ticker": return "excluded_ticker"
    if f["brk"][pos]: return "identity_break_guard"
    if pos + 1 < cb.DOLLAR_VOL_WINDOW: return "short_history"
    if not (f["raw"][pos] >= bv.MIN_PRICE and f["dv"][pos] >= bv.MIN_DOLLAR_VOL):
        return "below_floors:" + ("price" if f["raw"][pos] < bv.MIN_PRICE else "") + ("dollar_volume" if f["dv"][pos] < bv.MIN_DOLLAR_VOL else "")
    if np.isnan(f["r63"][pos]): return "no_r63"
    return "UNEXPLAINED_member"
pool_rows, pool_cause, rs_rows = [], Counter(), {}
for d, ca, cb_ in zip(dates, nA, nB):
    _, mA = poolA[d]; _, mB = poolB[d]
    inter = sorted(set(mA) & set(mB))
    for side, S, g, c, mine, other in (("A", SA, GA, ca, mA, mB), ("B", SB, GB, cb_, mB, mA)):
        for t in set(mine) - set(other):
            pool_cause[(side, why_not(SB if side == "A" else SA, GB if side == "A" else GA, cb_ if side == "A" else ca, t))] += 1
    def ranks(m):
        mm = [m[t] for t in inter]
        return dict(zip(inter, cb.cross_section_one_date([x["r21"] for x in mm], [x["r63"] for x in mm], [x["r126"] for x in mm], [None] * len(mm))[0]))
    rA_i, rB_i = ranks(mA), ranks(mB)
    full = {}
    for side, m in (("A", mA), ("B", mB)):
        mm = list(m.values())
        full[side] = dict(zip(m.keys(), cb.cross_section_one_date([x["r21"] for x in mm], [x["r63"] for x in mm], [x["r126"] for x in mm], [None] * len(mm))[0]))
    for t in inter:
        rs_rows[(d, t)] = (full["A"][t], full["B"][t], rA_i[t], rB_i[t])
pool_n = sum(len(poolA[d][1]) for d in dates), sum(len(poolB[d][1]) for d in dates)
P_(f"pool members over the {len(dates)} nights: A {pool_n[0]:,} B {pool_n[1]:,}; in both {len(rs_rows):,}")
P_("pool membership, names in ONE store's pool only: " + "; ".join(f"{s}-only {c}: {n}" for (s, c), n in sorted(pool_cause.items())))
unex = {k: v for k, v in pool_cause.items() if k[1].startswith("UNEXPLAINED")}
P_(f"  unexplained pool differences: {sum(unex.values())}")

# sanity: the full-pool recompute equals the rank used by the list build
chk = dfA.head(2000)
bad = sum(1 for r in chk.itertuples() if (r.D, r.ticker) in rs_rows and not np.isclose(rs_rows[(r.D, r.ticker)][0], r.rs_best))
assert bad == 0, bad

_cl = {}
def clean_rank_agree(d, t):
    """rs flag on the intersection pool restricted to names whose r21/r63/r126 are identical in both stores (ADDED after run 3: 4 names sit at rank 35.0/34.9
    and flip because OTHER names' rank inputs differ)."""
    if d not in _cl:
        mA, mB = poolA[d][1], poolB[d][1]
        cl = [x for x in sorted(set(mA) & set(mB)) if not rin(d, x)]
        out = []
        for m in (mA, mB):
            mm = [m[x] for x in cl]
            out.append(dict(zip(cl, cb.cross_section_one_date([y["r21"] for y in mm], [y["r63"] for y in mm], [y["r126"] for y in mm], [None] * len(mm))[0])))
        _cl[d] = out
    o = _cl[d]
    if t not in o[0]: return False
    return (o[0][t] >= bv.RS_MIN) == (o[1][t] >= bv.RS_MIN)
def rin(d, t):
    a, b = poolA[d][1][t], poolB[d][1][t]
    return any((a[k] is None) != (b[k] is None) or (a[k] is not None and not np.isclose(a[k], b[k], rtol=1e-9)) for k in ("r21", "r63", "r126"))
# ---- rs gate on names in both pools ------------------------------------------------------------------------------------
rs_diff = []
n_rs = len(rs_rows)
for (d, t), (a, b, ai, bi) in rs_rows.items():
    fa = a is not None and a >= bv.RS_MIN; fb = b is not None and b >= bv.RS_MIN
    if fa != fb:
        fai = ai is not None and ai >= bv.RS_MIN; fbi = bi is not None and bi >= bv.RS_MIN
        rs_diff.append((d, t, "pool" if fai == fbi else ("twin" if is_twin(t) else ("adj_step" if ratio_step(t, d) or guard_near(t, d) else ("rank_inputs" if rin(d, t) else ("pool_clean" if clean_rank_agree(d, t) else ("bar_values" if bar_values_differ(t, d, "rs") else "UNTRACED")))))))
c_rs = Counter(x[2] for x in rs_diff)
for x in rs_diff:
    if x[2] == "UNTRACED":
        P_("  rs UNTRACED " + str((x[0], x[1], rs_rows[(x[0], x[1])], {k: (poolA[x[0]][1][x[1]][k], poolB[x[0]][1][x[1]][k]) for k in ("r21", "r63", "r126")}, spans(x[1])[0].__len__(), spans(x[1])[1].__len__())))
P_(f"\nGATE rs (strength rank >= 35) on names in both pools: {n_rs:,} compared, {n_rs - len(rs_diff):,} agree = {100 * (n_rs - len(rs_diff)) / n_rs:.3f}%; differences by cause {dict(c_rs)}")

# ---- per-gate on names evaluated (rank >= 35, listable, history) in BOTH stores -----------------------------------------
m = dfA.merge(dfB, on=["D", "ticker"], suffixes=("_A", "_B"))
only_A = len(dfA) - len(m); only_B = len(dfB) - len(m)
P_(f"\nevaluated in both stores: {len(m):,} name-nights; only A {only_A:,}; only B {only_B:,}")
# why evaluated in one store only (both in pools): rs flag, listable (type snapshot), history
ev_keyA = set(zip(dfA.D, dfA.ticker)); ev_keyB = set(zip(dfB.D, dfB.ticker))
one_cause = Counter()
for side, ev_me, ev_other, mine, other in (("A", ev_keyA, ev_keyB, poolA, poolB), ("B", ev_keyB, ev_keyA, poolB, poolA)):
    for (d, t) in ev_me - ev_other:
        ci_o, mo = other[d]
        if t not in mo:
            one_cause[(side, "not in the other pool")] += 1; continue
        mm = mo[t]; a, b, ai, bi = rs_rows[(d, t)]
        r_other = (rs_rows[(d, t)][1] if side == "A" else rs_rows[(d, t)][0])
        if r_other is None or r_other < bv.RS_MIN: one_cause[(side, "rank < 35 in the other (the rs item)")] += 1
        elif not mm["listable"]:
            one_cause[(side, "type_snap" if SA.types.get(t) != SB.types.get(t) else "UNTRACED_not_listable")] += 1
        elif not mm["history"]: one_cause[(side, "history in the other")] += 1
        else: one_cause[(side, "UNTRACED_other")] += 1
P_("  evaluated in one store only, by cause: " + "; ".join(f"{s}: {c}: {n}" for (s, c), n in sorted(one_cause.items())))
untr_one = sum(n for (s, c), n in one_cause.items() if c.startswith("UNTRACED"))

def trunc_gates(d, t, restrict=False):
    k = SA.D.tid[t]; bars, cidx = runner.bars_for(SA.D, k)
    keep = [i for i, x in enumerate(bars.dates) if x >= FIRST_B]
    if restrict:
        kb = SB.D.tid[t]; bset = set(SB.D.cal[i] for i in SB.D.ci[int(SB.D.start[kb]):int(SB.D.stop[kb])])
        keep = [i for i in keep if bars.dates[i] in bset]
    keep = np.array(keep)
    tb = cb.daily_bars_from_arrays([bars.dates[i] for i in keep], bars.o[keep], bars.h[keep], bars.l[keep], bars.c[keep], bars.v[keep])
    ci_ = cidx[keep]
    Di = int(np.searchsorted(ci_, SA.D.cal.index(date.fromisoformat(d))))
    r = m_idx[(d, t)]
    g = bv.v1_gates(tb, Di, rs_best=r.rs_best_A, raw_close=r.raw_close_A, cidx=ci_)
    return g
def _same(gname, tg, r):
    if gname in GATE_NAMES: return bool(tg["gates"][gname]["pass"]) == bool(getattr(r, "gp_" + gname + "_B"))
    if gname.startswith("break"): return bool(np.isclose(tg["level"], r.level_B / (r.close_B / r.close_A), rtol=1e-6))
    if gname.startswith("level"): return bool(np.isclose(tg["level"] * (r.close_B / r.close_A), r.level_B, rtol=1e-6))
    if gname.startswith("bridge"): return (set(tg["failed"]) <= CTX) == (set(filter(None, r.failed_B.split(","))) <= CTX)
    return (tg["failed"] == []) == (r.failed_B == "")
m_idx = {(r.D, r.ticker): r for r in m.itertuples()}

res = {}
summary_rows = []
for gname in GATE_NAMES + ["break (level_pass)", "level (scaled)", "bridge-set member", "LIVE-list member"]:
    diffs = []
    for r in m.itertuples():
        if gname in GATE_NAMES:
            a, b = getattr(r, "gp_" + gname + "_A"), getattr(r, "gp_" + gname + "_B")
        elif gname.startswith("break"):
            a, b = r.fire_A, r.fire_B
        elif gname.startswith("level"):
            sc = r.close_B / r.close_A
            a, b = True, bool(np.isclose(r.level_B, r.level_A * sc, rtol=1e-6))
        elif gname.startswith("bridge"):
            a = set(filter(None, r.failed_A.split(","))) <= CTX; b = set(filter(None, r.failed_B.split(","))) <= CTX
        else:
            a, b = r.failed_A == "", r.failed_B == ""
        if bool(a) != bool(b): diffs.append(r)
    causes = Counter(); det = []
    for r in diffs:
        t, d = r.ticker, r.D
        if gname == "rs":
            a_, b_, ai, bi = rs_rows[(d, t)]
            fai = ai is not None and ai >= bv.RS_MIN; fbi = bi is not None and bi >= bv.RS_MIN
            cause = "pool" if fai == fbi else ("twin" if is_twin(t) else ("adj_step" if ratio_step(t, d) or guard_near(t, d) or r.raw_src_B == 2 else ("rank_inputs" if rin(d, t) else ("bar_values" if bar_values_differ(t, d, gname) else "UNTRACED"))))
        elif is_twin(t): cause = "twin"
        elif ratio_step(t, d) or guard_near(t, d) or r.raw_src_B == 2:
            cause = "adj_step"
        else:
            if _same(gname, trunc_gates(d, t), r): cause = "file_start"
            elif _same(gname, trunc_gates(d, t, True), r): cause = "session_set"
            else: cause = "bar_values" if bar_values_differ(t, d, gname) else "UNTRACED"
        causes[cause] += 1
        if cause == "UNTRACED" and len(det) < 12: det.append(f"{t} {d}")
    n = len(m); ag = n - len(diffs)
    lt130 = gname in ("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21", "sma50_falling_under", "downtrend_6m")
    P_(f"GATE {gname:22s} {'(<130 bars)' if lt130 else '(>=130 bars)' if gname == 'lower_line' else '            '}: {n:,} compared, agree {ag:,} = {100 * ag / n:.3f}%; differences {len(diffs):,} by cause {dict(causes)}" + (f"  UNTRACED sample: {det}" if det else ""))
    res[gname] = dict(n=n, agree=ag, pct=100 * ag / n, diffs=len(diffs), causes=dict(causes), lt130=lt130)

untraced = sum(v["causes"].get("UNTRACED", 0) for v in res.values()) + len([x for x in rs_diff if x[2] == "UNTRACED"]) + untr_one + sum(v for k, v in pool_cause.items() if k[1].startswith("UNEXPLAINED"))
low = [g for g, v in res.items() if v["pct"] < 99.0]
P_(f"\nGATES under 99% agreement: {low}")
P_(f"UNTRACED differences in total: {untraced}")
P_(f"1d OVERLAP GATE: {'PASS (every difference traced)' if untraced == 0 else 'FAIL (untraced differences)'}")
(HERE / "1d_overlap.txt").write_text("\n".join(L) + "\n")
(HERE / "1d_overlap_result.json").write_text(json.dumps(dict(gates=res, rs=dict(n=n_rs, diffs=len(rs_diff), causes=dict(c_rs)), untraced=untraced, low=low,
    pool_cause={f"{s}:{c}": n for (s, c), n in pool_cause.items()}, one_cause={f"{s}:{c}": n for (s, c), n in one_cause.items()}), indent=1) + "\n")
