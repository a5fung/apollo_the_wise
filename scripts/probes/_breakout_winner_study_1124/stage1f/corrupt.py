"""Stage 1f corrupt-E proof (prereg 4.0): on a seeded 600-event sample (300 era A + 300 era B kept events, drawn by whole nights), E's high / low / close /
volume and EVERY later bar (all tickers) are replaced with garbage (three patterns); 0 values may change.
Two levels, both through the SAME functions that built the table:
  (1) PIPELINE (forked children): the store's arrays at calendar index >= E are corrupted for ALL tickers, the night's pool facts are rebuilt, the live list
      is re-run for the night (work() = night_members + cross-section + v1_gates) and every stored list column + every feature + B1 / B2 / B3 is recomputed.
  (2) PER-NAME (parent): the same sampled events through features_for with the ticker's own E-and-later bars corrupted, plus
      - the LEAKY control (close(E)/close(D) - 1, deliberately reads E): compared between garbage patterns only (no real E value is ever read for it),
      - the OPEN test: open(E) replaced by two garbage values - only f24 (and its 24a / 24b split) may move.
Clean values are recomputed in-process (never read back from the rounded table); they are also asserted equal to the table at rtol 1e-8."""
import json, random, time, hashlib, math
from collections import Counter
from multiprocessing import get_context
from lib1f import *

t0 = time.time()
assert_docs()
L = []
def P_(s=""):
    print(s, flush=True); L.append(s)
TBL = pd.read_csv(STAGE / "feature_table.tsv.gz", sep="\t", low_memory=False, keep_default_na=False, na_values=[""])
bres = json.load(open(STAGE / "1f_build_result.json"))
assert hashlib.sha256((STAGE / "feature_table.tsv.gz").read_bytes()).hexdigest() == bres["table_sha256"], "table changed since the build"
gB, fA, fB = load_dates()
ALLF = ff.FEATS + ff.BENCH

def same(a, b):
    if a is None and b is None: return True
    if a is None or b is None: return False
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    return a == b

def garbage(arr_o, arr_h, arr_l, arr_c, arr_v, m, mo, pat, rng):
    """in place: rows in mask m (E and later) get garbage h/l/c/v; rows in mo (after E) also garbage o. open(E) itself is kept."""
    n = int(m.sum()); n2 = int(mo.sum())
    if pat == 1:
        for a, mm, nn in ((arr_h, m, n), (arr_l, m, n), (arr_c, m, n)): a[mm] = rng.uniform(0.5, 500.0, nn)
        arr_v[m] = rng.uniform(0.0, 1e9, n); arr_o[mo] = rng.uniform(0.5, 500.0, n2)
    elif pat == 2:
        for a in (arr_h, arr_l, arr_c): a[m] = 1e7
        arr_v[m] = 1e12; arr_o[mo] = 1e7
    else:
        for a in (arr_h, arr_l, arr_c): a[m] = 1e-4
        arr_v[m] = 0.0; arr_o[mo] = 1e-4

CUR = {}
def task(a):
    era, ci, pat, seed, evs = a
    S, ctx, stored = CUR["S"], CUR["ctx"], CUR["stored"]
    D = S.D; rng = np.random.default_rng(seed)
    m = D.ci >= ci + 1; mo = D.ci > ci + 1
    garbage(D.o, D.h, D.l, D.c, D.v, m, mo, pat, rng)
    ctx.cache.clear()
    facts = G["facts"]
    for k, i in G["rows_at"].get(ci):
        facts[k] = R.ticker_facts(S, k)
    nr = pd.DataFrame(work(([ci], False)), columns=ALL_COLS).sort_values("ticker").reset_index(drop=True)
    st = stored[stored.ci == ci].sort_values("ticker").reset_index(drop=True)
    cols = [c for c in st.columns if c in nr.columns and c not in NONFEAT_COLS]
    out = dict(era=era, ci=ci, pat=pat, n_rows=len(st), n_new=len(nr), same_tickers=bool(list(nr.ticker) == list(st.ticker)), col_diff=Counter())
    if out["same_tickers"]:
        for c in cols:
            x, y = nr[c].to_numpy(), st[c].to_numpy()
            if x.dtype.kind == "f" or y.dtype.kind == "f":
                x, y = x.astype(float), y.astype(float)
                bad = ~((x == y) | (np.isnan(x) & np.isnan(y)))
            else:
                bad = x != y
            if bad.any(): out["col_diff"][c] = int(bad.sum())
    bm = night_benchmarks(nr)
    res = {}
    byt = nr.set_index("ticker")
    for t in evs:
        if t not in byt.index:
            res[t] = None; continue
        row = byt.loc[t].to_dict(); row["ticker"] = t; row["ci"] = ci
        vals, nulls, dg = ctx.feats(row)
        b1, b2 = bm.get(t, (None, None))
        if b1 is not None and math.isfinite(b1): vals["B1"] = float(b1)
        else: nulls["B1"] = "unscored"
        if b2 is not None and math.isfinite(b2): vals["B2"] = float(b2)
        else: nulls["B2"] = "unscored"
        res[t] = (vals, nulls, dg["f24grp"])
    out["res"] = res
    return out

report = dict(gate_parts={})
agg_pipe = Counter(); agg_pipe_nonnull = Counter(); n_pipe_events = 0; list_rows_cmp = 0; list_bad_cols = Counter(); list_missing = 0
per_name = Counter(); per_name_n = 0
leak_changed = leak_n = 0
open_changed = Counter(); open_n = 0; open_f24_nonnull = 0; open_f24_moved = 0
sample_rows = []
nonnull_sample = Counter()
clean_vs_table_bad = Counter()

for era, path in (("A", OUT_DATA / "bws1124_eraA_list_ctx.parquet"), ("B", OUT_DATA / "bws1124_eraB_list_ctx.parquet")):
    S = setup_store(era)
    cal = [d.isoformat() for d in S.D.cal]
    guard = {t: sorted(date.fromordinal(int(o)).isoformat() for o in v) for t, v in S.breaks.items()} if era == "A" else gB
    ctx = EraCtx(era, S, cal, guard, fA if era == "A" else fB)
    stored = pd.read_parquet(path)
    # ---- the seeded sample: whole nights, kept (1124) events, until 300 events
    K = TBL[(TBL.era == era) & (TBL.kept == True)]
    nights = sorted(set(K.ci)); random.Random(1124).shuffle(nights)
    chosen, cnt = [], 0
    for c in nights:
        if cnt >= 300: break
        chosen.append(c); cnt += int((K.ci == c).sum())
    chosen = sorted(chosen)
    S_ev = K[K.ci.isin(chosen)][["era", "ci", "D", "E", "ticker"]].reset_index(drop=True)
    sample_rows.append(S_ev)
    P_(f"era {era}: sample = {len(S_ev)} kept events on {len(chosen)} whole nights ({cal[chosen[0]]} .. {cal[chosen[-1]]})")
    ev_by_night = S_ev.groupby("ci").ticker.apply(list).to_dict()
    # ---- clean recompute (in-process) + equality with the table
    idx = stored.groupby("ci").indices
    clean = {}
    for c in chosen:
        nr = stored.iloc[idx[c]]
        bm = night_benchmarks(nr); byt = nr.set_index("ticker")
        for t in ev_by_night[c]:
            row = byt.loc[t].to_dict(); row["ticker"] = t; row["ci"] = c
            vals, nulls, dg = ctx.feats(row)
            b1, b2 = bm[t]
            if b1 is not None and math.isfinite(b1): vals["B1"] = float(b1)
            else: nulls["B1"] = "unscored"
            if b2 is not None and math.isfinite(b2): vals["B2"] = float(b2)
            else: nulls["B2"] = "unscored"
            clean[(c, t)] = (vals, nulls, dg["f24grp"], row)
            trow = TBL[(TBL.era == era) & (TBL.ci == c) & (TBL.ticker == t)].iloc[0]
            for f in ALLF:
                tv = trow[f]; tn = trow[f + "_null"]
                tn = "" if (isinstance(tn, float) and math.isnan(tn)) else tn
                if f in vals:
                    if tn != "" or not np.isclose(float(tv), vals[f], rtol=1e-8, atol=0): clean_vs_table_bad[f] += 1
                else:
                    if tn != nulls.get(f): clean_vs_table_bad[f] += 1
            for f in ALLF:
                if f in vals: nonnull_sample[(era, f)] += 1
    # ---- (2) per-name: corrupt this ticker's own E-and-later bars, leaky + open controls
    for (c, t), (vals0, nulls0, grp0, row) in clean.items():
        k, a, d, ci_, o, h, l, cl, v = ctx.series(t)
        Di = int(np.searchsorted(ci_, c))
        leaks = []
        for pat in (1, 2, 3):
            oo, hh, ll, cc, vv = (x.copy() for x in (o, h, l, cl, v))
            m = np.zeros(len(ci_), dtype=bool); m[Di + 1:] = True; mo = np.zeros(len(ci_), dtype=bool); mo[Di + 2:] = True
            garbage(oo, hh, ll, cc, vv, m, mo, pat, np.random.default_rng(1124 + pat))
            vals, nulls, dg = ctx.feats(row, arrays=(oo, hh, ll, cc, vv))
            b1b2 = {f: vals0[f] for f in ("B1", "B2") if f in vals0}; vals.update(b1b2)
            for f in ALLF:
                if f in ("B1", "B2"): continue
                if not (same(vals.get(f), vals0.get(f)) and nulls.get(f) == nulls0.get(f)): per_name[f] += 1
            if dg["f24grp"] != grp0: per_name["f24grp"] += 1
            leaks.append(float(cc[Di + 1]) / float(cl[Di]) - 1.0)                  # the leaky control: reads close(E)
        per_name_n += 1
        leak_n += 1; leak_changed += int(leaks[0] != leaks[1] and leaks[1] != leaks[2] and leaks[0] != leaks[2])
        # open test: two garbage open(E)
        base_o = float(o[Di + 1]); moved_any = set()
        for mult in (3.0, 0.2):
            vals, nulls, dg = ctx.feats(row, o_override=base_o * mult)
            for f in ff.FEATS:
                if not (same(vals.get(f), vals0.get(f)) and nulls.get(f) == nulls0.get(f)): moved_any.add(f)
        open_n += 1
        for f in moved_any: open_changed[f] += 1
        if "f24" in vals0: open_f24_nonnull += 1; open_f24_moved += int("f24" in moved_any)
    # ---- (1) pipeline children
    CUR.clear(); CUR.update(S=S, ctx=ctx, stored=stored)
    tasks = [(era, c, pat, 1124 * 7 + pat, ev_by_night[c]) for c in chosen for pat in (1, 2, 3)]
    t1 = time.time()
    with get_context("fork").Pool(5, maxtasksperchild=1) as pool:   # a FRESH fork per task: the corruption must never leak into the next night
        outs = pool.map(task, tasks, chunksize=1)
    P_(f"  pipeline: {len(tasks)} night x pattern runs in {time.time() - t1:.0f}s")
    for o_ in outs:
        list_rows_cmp += o_["n_rows"]
        if not o_["same_tickers"] or o_["n_rows"] != o_["n_new"]: list_missing += 1
        list_bad_cols.update(o_["col_diff"])
        for t, r in o_["res"].items():
            vals0, nulls0, grp0, _ = clean[(o_["ci"], t)]
            n_pipe_events += 1
            if r is None:
                agg_pipe["MISSING_EVENT"] += 1; continue
            vals, nulls, grp = r
            for f in ALLF:
                if not (same(vals.get(f), vals0.get(f)) and nulls.get(f) == nulls0.get(f)): agg_pipe[f] += 1
            if grp != grp0: agg_pipe["f24grp"] += 1
    del stored, clean
    G.clear()

pd.concat(sample_rows).to_csv(STAGE / "corrupt_sample_events.tsv", sep="\t", index=False)
nS = sum(len(x) for x in sample_rows)
P_(f"\n== CORRUPT-E PROOF ({nS} sampled kept events; garbage patterns 1 = random wide, 2 = 1e7 prices / 1e12 volume, 3 = 1e-4 prices / 0 volume) ==")
P_(f"clean in-process recompute vs the (rounded) table: values / NULL reasons differing: {dict(clean_vs_table_bad) or 'NONE'}")
P_(f"(1) PIPELINE: store bars at calendar index >= E corrupted for ALL tickers, pool facts rebuilt, live list re-run per night: {list_rows_cmp:,} stored list rows compared "
   f"(x3 patterns; E-dependent columns {NONFEAT_COLS} excluded); nights whose ticker set / row count differs {list_missing}; list-column cells changed {dict(list_bad_cols) or 'NONE'}")
P_(f"    {n_pipe_events} event x pattern feature recomputes (incl. rs ranks, B1 / B2 / B3 from the recomputed night): values or NULL reasons changed {dict(agg_pipe) or 'NONE'}")
P_(f"(2) PER-NAME: {per_name_n} events x 3 patterns on the ticker's own E-and-later bars: values / NULL reasons changed {dict(per_name) or 'NONE'}")
P_(f"    LEAKY control close(E) / close(D) - 1 (reads E on purpose): differs across all three garbage patterns on {leak_changed} of {leak_n} events")
P_(f"    OPEN test (open(E) x3.0 and x0.2): features that moved {dict(open_changed)}; f24 moved on {open_f24_moved} of {open_f24_nonnull} events with a f24 value; every other feature moved on 0")
P_("non-NULL events per feature in the sample (A / B) - an all-NULL or constant feature would prove nothing:")
for f in ALLF:
    P_(f"   {f:4} A {nonnull_sample[('A', f)]:3d} B {nonnull_sample[('B', f)]:3d}")
gate_pass = (not clean_vs_table_bad and list_missing == 0 and not list_bad_cols and not agg_pipe and not per_name and leak_changed == leak_n
             and set(open_changed) <= {"f24"} and open_f24_moved == open_f24_nonnull)
P_(f"\nGATE (0 values change under corrupt-E; the leaky control changes; open(E) moves only f24): {'PASS' if gate_pass else 'FAIL'}")
(STAGE / "1f_corrupt.txt").write_text("\n".join(L) + "\n")
json.dump(dict(gate_pass=bool(gate_pass), sample=nS, pipeline_events=n_pipe_events, list_rows=list_rows_cmp, list_bad=dict(list_bad_cols), pipe_changed=dict(agg_pipe),
               per_name_changed=dict(per_name), leak_changed=leak_changed, leak_n=leak_n, open_changed=dict(open_changed), secs=round(time.time() - t0)),
          open(STAGE / "1f_corrupt_result.json", "w"), indent=1)
