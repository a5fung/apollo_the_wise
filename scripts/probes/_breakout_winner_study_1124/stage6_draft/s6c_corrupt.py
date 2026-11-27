"""Stage 6 DRAFT step c: corrupt-E proof of gallery read #1, as stage 1f did (prereg 4.0). Sample = stage 1f's own seeded sample
(stage1f/corrupt_sample_events.tsv, 604 kept events on whole nights; read, never rewritten). OUTCOME-FREE.
 (1) WHOLE STORE (forked children, one per night x pattern): every bar of EVERY ticker at calendar index >= E gets garbage - open(E) included, this read
     takes nothing from E - then each sampled event is recomputed through the same gr1.cut_at_D + gr1.v_parts that built the table.
     (rs_best is the stored list value: stage 1f's pipeline proof showed the list columns do not move under this corruption; it only feeds gate
     pass / fail inside v1_gates, never level or ADR20.)
 (2) PER-NAME (parent): the ticker's own E-and-later bars corrupted, three patterns.
 LEAKY control: the same function handed bars cut at E instead of D (window D-83 .. E, level / ADR as of E) - it must move between patterns.
Compared: the five numeric components + level + ADR20 + NULL reason + the flag + ALT-1, exact equality."""
import hashlib, json, math, sys, time
from pathlib import Path
H6 = Path(__file__).resolve().parent
sys.path.insert(0, str(H6.parent / "stage1f")); sys.path.insert(0, str(H6))
from multiprocessing import get_context
from lib1f import *          # noqa
import gr1
import common6 as C6
t0 = time.time()
P = C6.Out("6c_corrupt.txt")
P("# STAGE 6 DRAFT (not a freeze) - c. CORRUPT-E PROOF of gallery read #1"); P(C6.assert_all())
SAMP = pd.read_csv(H6.parent / "stage1f/corrupt_sample_events.tsv", sep="\t", dtype={"ticker": str}, keep_default_na=False)
TBL = pd.read_csv(H6.parent / "stage1f/feature_table.tsv.gz", sep="\t", low_memory=False, keep_default_na=False, na_values=[""], dtype={"ticker": str})
RS = {(e, int(c), t): float(r) for e, c, t, r in zip(TBL.era, TBL.ci, TBL.ticker, TBL.rs_best)}
BUILT = C6.components().set_index(["era", "ci", "ticker"])
KEYS = gr1.COMPONENTS + ["level", "adr20"]
gB, fA, fB = load_dates()

def same(a, b):
    return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))

def garbage(o, h, l, c, v, m, pat, rng):
    n = int(m.sum())
    if pat == 1:
        for a in (o, h, l, c): a[m] = rng.uniform(0.5, 500.0, n)
        v[m] = rng.uniform(0.0, 1e9, n)
    elif pat == 2:
        for a in (o, h, l, c): a[m] = 1e7
        v[m] = 1e12
    else:
        for a in (o, h, l, c): a[m] = 1e-4
        v[m] = 0.0

def compute(ctx, S, era, ci, t, arrays=None, leak=False):
    k, a, d, cidx, o, h, l, c, v = ctx.series(t)
    Di = int(np.searchsorted(cidx, ci)); assert int(cidx[Di]) == ci
    raw_close = float(S.raw_factor[a + Di]) * float(c[Di] if arrays is None else arrays[3][Di]) if False else float(S.raw_factor[a + Di]) * float(S.D.c[a + Di])
    if arrays is not None: o, h, l, c, v = arrays
    cut = gr1.cut_at_D((d, cidx, o, h, l, c, v), Di + (1 if leak else 0))
    vals, nul = gr1.v_parts(bv=bv, cb=cb, cal=ctx.cal, cut=cut, ciD=ci + (1 if leak else 0), rs_best=RS[(era, ci, t)], raw_close=raw_close,
                            flag_dates=ctx.flags.get(t, []), guard_dates=ctx.guard.get(t, []))
    out = {k_: vals.get(k_, float("nan")) for k_ in KEYS}; out["null"] = nul or ""
    out["gr1"] = gr1.flag(vals) if not nul else -1
    out["alt1"] = gr1.flag(vals, at_max=None) if not nul else -1
    return out

CUR = {}
def task(a):
    era, ci, pat, seed, evs = a
    S, ctx = CUR["S"], CUR["ctx"]; D = S.D
    garbage(D.o, D.h, D.l, D.c, D.v, D.ci >= ci + 1, pat, np.random.default_rng(seed))
    ctx.cache.clear()
    return ci, pat, {t: compute(ctx, S, era, ci, t) for t in evs}

whole = {}; pern = {}; n_whole = n_pern = 0; leak_moved = leak_n = 0; leak_err = 0; flagged = alt_flagged = 0; nonnull = {}; vs_table = 0
for era in ("A", "B"):
    S = setup_store(era)
    cal = [d.isoformat() for d in S.D.cal]
    guard = {t: sorted(date.fromordinal(int(o)).isoformat() for o in v) for t, v in S.breaks.items()} if era == "A" else gB
    ctx = EraCtx(era, S, cal, guard, fA if era == "A" else fB)
    ev = SAMP[SAMP.era == era]
    clean = {}
    for r in ev.itertuples():
        c0 = compute(ctx, S, era, int(r.ci), r.ticker); clean[(int(r.ci), r.ticker)] = c0
        b = BUILT.loc[(era, int(r.ci), r.ticker)]
        for k_ in gr1.COMPONENTS:
            if not (np.isclose(c0[k_], b[k_], rtol=1e-8, atol=0, equal_nan=True)): vs_table += 1
        if c0["gr1"] != (int(b.gr1) if b.gr1 == b.gr1 else -1): vs_table += 1
        flagged += int(c0["gr1"] == 1); alt_flagged += int(c0["alt1"] == 1)
        for k_ in KEYS:
            if not math.isnan(c0[k_]): nonnull[(era, k_)] = nonnull.get((era, k_), 0) + 1
        # (2) per-name + leaky control
        k, a, d, cidx, o, h, l, c, v = ctx.series(r.ticker)
        Di = int(np.searchsorted(cidx, int(r.ci)))
        leaks = []
        for pat in (1, 2, 3):
            arr = [x.copy() for x in (o, h, l, c, v)]
            m = np.zeros(len(cidx), dtype=bool); m[Di + 1:] = True
            garbage(*arr, m, pat, np.random.default_rng(1124 + pat))
            c1 = compute(ctx, S, era, int(r.ci), r.ticker, arrays=tuple(arr))
            n_pern += 1
            for k_ in KEYS + ["null", "gr1", "alt1"]:
                if not same(c1[k_], c0[k_]): pern[k_] = pern.get(k_, 0) + 1
            try:
                lk = compute(ctx, S, era, int(r.ci), r.ticker, arrays=tuple(arr), leak=True)
                leaks.append(tuple(lk[k_] for k_ in KEYS + ["null"]))
            except Exception as e:                       # garbage bars can break the live gate code: that IS a change
                leaks.append(("error", type(e).__name__)); leak_err += 1
        leak_n += 1; leak_moved += int(len(set(map(repr, leaks))) == 3)
    # (1) whole store
    CUR.clear(); CUR.update(S=S, ctx=ctx)
    byn = ev.groupby("ci").ticker.apply(list).to_dict()
    tasks = [(era, int(c), pat, 1124 * 7 + pat, ts) for c, ts in sorted(byn.items()) for pat in (1, 2, 3)]
    with get_context("fork").Pool(5, maxtasksperchild=1) as pool:      # a FRESH fork per task
        outs = pool.map(task, tasks, chunksize=1)
    for ci, pat, res in outs:
        for t, c1 in res.items():
            n_whole += 1; c0 = clean[(ci, t)]
            for k_ in KEYS + ["null", "gr1", "alt1"]:
                if not same(c1[k_], c0[k_]): whole[k_] = whole.get(k_, 0) + 1
    P(f"era {era}: {len(ev)} sampled events on {len(byn)} whole nights; {len(tasks)} night x pattern whole-store runs")
    G.clear()
P(f"\n== CORRUPT-E PROOF ({len(SAMP)} sampled kept events; patterns 1 = random wide, 2 = 1e7 prices / 1e12 volume, 3 = 1e-4 prices / 0 volume; open(E) corrupted too) ==")
P(f"clean in-process recompute vs the built components table: cells differing {vs_table}")
P(f"(1) WHOLE STORE: {n_whole} event x pattern recomputes with every ticker's bars at index >= E corrupted: values / NULL reasons / flags changed {whole or 'NONE'}")
P(f"(2) PER-NAME: {n_pern} event x pattern recomputes on the ticker's own E-and-later bars: values / NULL reasons / flags changed {pern or 'NONE'}")
P(f"    LEAKY control (the same function cut at E, reads E on purpose): differs across all three garbage patterns on {leak_moved} of {leak_n} events (pattern runs that raised instead of returning a value: {leak_err} of {3 * leak_n}; a raise is NOT counted as a difference from another raise)")
P(f"a flat or all-NULL feature would prove nothing: sampled events flagged V {flagged} of {len(SAMP)} (ALT-1 {alt_flagged}); non-NULL per component (A / B): "
  + ", ".join(f"{k_} {nonnull.get(('A', k_), 0)}/{nonnull.get(('B', k_), 0)}" for k_ in KEYS))
gate = (vs_table == 0 and not whole and not pern and leak_moved == leak_n)
P(f"\nGATE (0 values change under corrupt-E; the leaky control changes): {'PASS' if gate else 'FAIL'}   [{time.time() - t0:.0f}s]")
P.save()
json.dump(dict(gate_pass=bool(gate), sample=len(SAMP), whole=n_whole, whole_changed=whole, per_name=n_pern, per_name_changed=pern, leak_moved=leak_moved, leak_n=leak_n,
               flagged_in_sample=flagged), open(H6 / "6c_corrupt_result.json", "w"), indent=1)
