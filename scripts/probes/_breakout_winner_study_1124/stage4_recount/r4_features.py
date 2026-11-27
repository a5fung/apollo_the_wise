"""R4 stage 1f recount (blind): the 24 features + 4 benchmarks for every kept (seed 1124) event, from bars <= D, the level at D, and open(E) only.
Night-level cross-section inputs (rs_1m, rs_6m, group strength, pick/order scores) come from the R4 list pass capture (bars <= D by construction).
Corrupt-E proof + positive control run through the SAME function on altered bars. NULL rules = EP 4.0 (history, coverage<90%, adjustment, identity, zero volume)."""
import json, sys
from collections import Counter, defaultdict
from datetime import date
import numpy as np, pandas as pd
import r4_common as C
import v1_replay as R
from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_pick_model as pm
from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import runner

FEATS = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20", "f21", "f22",
         "f23", "f24", "B1", "B2", "B3", "B4"]


def window_rows(cidx, ci0, ci1):
    return int(np.searchsorted(cidx, ci0, "left")), int(np.searchsorted(cidx, ci1, "right"))


class Ctx:
    def __init__(self, era, cal, first_ci, guard, flags):
        self.era, self.cal, self.first, self.guard, self.flags = era, cal, first_ci, guard, flags


def null_reason(cx, ticker, cidx, ci, n, vol=None, use_adj=True, use_guard=True, zero_vol=False):
    """the EP NULL rules for the calendar window ci-n+1..ci: history -> coverage -> adjustment -> identity -> zero_volume."""
    ci0 = ci - n + 1
    if ci0 < 0 or cx.first > ci0:
        return "history"
    lo, hi = window_rows(cidx, ci0, ci)
    if (hi - lo) / n < 0.90:
        return "coverage"
    d0, d1 = cx.cal[ci0], cx.cal[ci]
    if use_adj and any(d0 <= x <= d1 for x in cx.flags.get(ticker, ())):
        return "adjustment"
    if use_guard and any(d0 <= dk[0] <= d1 for dk in cx.guard.get(ticker, ())):
        return "identity"
    if zero_vol and (vol is not None) and (vol[lo:hi] == 0).any():
        return "zero_volume"
    return None


def compute(cx, bars, cidx, Di, ci, ticker, rb, raw_close, raw_src, xs, leak=False):
    """-> ({feature: value or nan}, {feature: null reason})"""
    h, l, c, o, v = (np.asarray(x, float) for x in (bars.h, bars.l, bars.c, bars.o, bars.v))
    g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=raw_close, cidx=cidx)
    assert g["ok"], "event row is not a list row at D"
    oi = bv.order_inputs(bars, Di, g["adr20"])
    P = g["pole_idx"]
    sg = bv.shape_gates(bars, Di, P=P, adr20=g["adr20"])
    pmf = pm.base_facts(bars.h, bars.l, bars.c, Di)
    adr = g["adr20"]; gg = g["gates"]
    out, why = {}, {}

    def put(k, val, reason=None):
        if reason is not None or val is None or (isinstance(val, float) and not np.isfinite(val)):
            out[k] = np.nan; why[k] = reason or "blank"
        else:
            out[k] = float(val)

    put("f1", adr)
    if cx.era == "B" and raw_src == 2:
        put("f2", None, "derived_only")
    else:
        put("f2", raw_close)
    r3 = null_reason(cx, ticker, cidx, ci, 20, v, use_adj=False, use_guard=False, zero_vol=True)
    put("f3", gg["universe"]["value"]["dollar_vol20"], "zero_volume" if r3 == "zero_volume" else None)
    put("f4", rb)
    put("f5", xs["rs_1m"]); put("f6", xs["rs_6m"])
    put("f7", g["prior_move"])
    # f8: close(D) / lowest low of D-19..D - 1
    r = null_reason(cx, ticker, cidx, ci, 20)
    if r: put("f8", None, r)
    else:
        lo, hi = window_rows(cidx, ci - 19, ci)
        put("f8", c[Di] / l[lo:hi].min() - 1.0)
    put("f9", oi["runup6m"])
    # 52-week group (10, 11, 22, 23): history / coverage / identity only
    r52 = null_reason(cx, ticker, cidx, ci, 252, use_adj=False)
    put("f10", pmf[0] if pmf else None, r52)
    if r52: put("f11", None, r52)
    else:
        lo, hi = window_rows(cidx, ci - 251, ci)
        put("f11", 1.0 if g["level"] >= h[lo:hi].max() else 0.0)
    put("f12", gg["prior_move"]["value"]["base_len"])
    # f13: 1 - lowest low / highest high over P+1..D ; window = the base
    nb = Di - P
    r = null_reason(cx, ticker, cidx, ci, nb)
    if r: put("f13", None, r)
    else: put("f13", 1.0 - l[P + 1:Di + 1].min() / h[P + 1:Di + 1].max())
    put("f14", 1.0 if g["level_source"] == "range" else 0.0)
    put("f15", oi["spread10_adr"])
    put("f16", sg["range_contract"]["value"]["range5_over_prev5"])
    # f17 volume dry-up, n=60
    r = null_reason(cx, ticker, cidx, ci, 60, v, zero_vol=True)
    if r: put("f17", None, r)
    else:
        lo, hi = window_rows(cidx, ci - 9, ci); lo2, hi2 = window_rows(cidx, ci - 59, ci - 10)
        den = v[lo2:hi2].mean()
        put("f17", v[lo:hi].mean() / den if den > 0 else None)
    # f18 up vs down volume D-19..D, vs prior session's close (bar at the previous calendar session)
    r = null_reason(cx, ticker, cidx, ci, 21, v, zero_vol=True)
    if r: put("f18", None, r)
    else:
        up = dn = 0.0
        pos = {int(cidx[i]): i for i in range(*window_rows(cidx, ci - 20, ci))}
        for gi in range(ci - 19, ci + 1):
            if gi in pos and (gi - 1) in pos:
                a, b = pos[gi], pos[gi - 1]
                if c[a] > c[b]: up += v[a]
                elif c[a] < c[b]: dn += v[a]
        put("f18", (up / dn) if dn > 0 else None, None if dn > 0 else "no_down_day")
    put("f19", sg["not_extended"]["value"]["close_vs_ema10_adr"])
    put("f20", float(sum(bool(sg[k]["pass"]) for k in bv.SHAPE_GATES)))
    r = null_reason(cx, ticker, cidx, ci, 200, use_adj=not C.FIX)
    if r: put("f21", None, r)
    else:
        lo, hi = window_rows(cidx, ci - 199, ci)
        put("f21", (c[Di] / c[lo:hi].mean() - 1.0) * 100.0 / adr)
    put("f22", pmf[1] if pmf else None, r52)
    put("f23", (1.0 if pmf[2] == 0 else 0.0) if pmf else None, r52)
    put("f24", (o[Di + 1] / c[Di] - 1.0) * 100.0 / adr)
    out["f24_above"] = 1.0 if o[Di + 1] > g["level"] else 0.0
    out["B1"] = xs["pick_score"]; out["B2"] = xs["order_score"]; out["B3"] = xs["group_strength"]
    out["B4"] = (g["level"] / c[Di] - 1.0) * 100.0 / adr
    out["level"] = g["level"]; out["c_D"] = c[Di]
    if leak:
        out["LEAK"] = h[Di + 1] / c[Di] - 1.0
    return out, why


def corrupt(bars, Di, pat, rng):
    n = len(bars)
    arr = {k: np.array(getattr(bars, k), float) for k in "ohlcv"}
    for k in "hlcv":
        idx = slice(Di + 1, n)
        m = n - Di - 1
        if pat == 0: arr[k][idx] = arr[k][idx] * 7.3 + 100.0
        elif pat == 1: arr[k][idx] = 0.01 if k != "v" else 0.0
        else: arr[k][idx] = rng.uniform(1, 1e5, m)
    arr["o"][Di + 2:n] = 5e4 + rng.uniform(0, 1, max(0, n - Di - 2))      # bars after E fully garbage; open(E) itself kept
    return cb.daily_bars_from_arrays(list(bars.dates), arr["o"], arr["h"], arr["l"], arr["c"], arr["v"])


def main():
    C.assert_pins()
    K = pd.read_parquet(C.BIG / f"r4_events_kept{C.SUF}.parquet")
    logf = open(C.OUTD / f"stage1f_features{C.SUF}.log", "w")

    def P_(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); logf.write(s + "\n"); logf.flush()
    rows, nulls = [], []
    rng_s = np.random.default_rng(1124)
    sample_ids = set(rng_s.choice(len(K), 600, replace=False).tolist())
    changed = Counter(); leak_changed = 0; n_tested = 0
    gA, _ = C.load_guard(C.GUARD_A, "A"); gB, _ = C.load_guard(C.GUARD_B, "B")
    fA, _ = C.load_flags(C.FLAGS_A); fB, _ = C.load_flags(C.FLAGS_B)
    for era, guard, flags in (("A", gA, fA), ("B", gB, fB)):
        S = R.load_store(era)
        Dd = S.D
        cx_cal = Dd.cal
        pool = pd.read_parquet(C.BIG / f"r4_pool_era{era}.parquet").set_index(["ci", "ticker"])
        Ke = K[K.era == era]
        cache = {}
        for r in Ke.itertuples():
            k = Dd.tid[r.ticker]
            if k not in cache:
                cache[k] = runner.bars_for(Dd, k)
            bars, cidx = cache[k]
            Di = int(np.searchsorted(cidx, r.ci))
            assert int(cidx[Di]) == r.ci and Di == r.Di
            pr = pool.loc[(r.ci, r.ticker)]
            xs = {"rs_1m": pr.rs_1m, "rs_6m": pr.rs_6m, "group_strength": pr.group_strength, "pick_score": pr.pick_score, "order_score": pr.order_score}
            cx = Ctx(era, cx_cal, int(Dd.ci[Dd.start[k]]), guard, flags)
            vals, why = compute(cx, bars, cidx, Di, r.ci, r.ticker, r.rs_best, r.raw_close, r.raw_src, xs, leak=(r.Index in sample_ids))
            # the capture's gate values must equal the recomputation
            assert abs(vals["level"] - r.level) < 1e-9, (r.ticker, r.D)
            if r.Index in sample_ids:
                n_tested += 1
                rngc = np.random.default_rng(r.Index)
                for pat in range(3):
                    cb_ = corrupt(bars, Di, pat, rngc)
                    v2, _ = compute(cx, cb_, cidx, Di, r.ci, r.ticker, r.rs_best, r.raw_close, r.raw_src, xs, leak=True)
                    for f in FEATS + ["f24_above", "level"]:
                        a, b = vals.get(f, np.nan), v2.get(f, np.nan)
                        if not ((np.isnan(a) and np.isnan(b)) or a == b):
                            changed[f] += 1
                    if not (vals["LEAK"] == v2["LEAK"]):
                        leak_changed += 1
                # open(E) moves f24 only
                bo = {k_: np.array(getattr(bars, k_), float) for k_ in "ohlcv"}
                bo["o"][Di + 1] *= 1.37
                b2 = cb.daily_bars_from_arrays(list(bars.dates), bo["o"], bo["h"], bo["l"], bo["c"], bo["v"])
                v3, _ = compute(cx, b2, cidx, Di, r.ci, r.ticker, r.rs_best, r.raw_close, r.raw_src, xs)
                for f in FEATS:
                    a, b = vals.get(f, np.nan), v3.get(f, np.nan)
                    if not ((np.isnan(a) and np.isnan(b)) or a == b):
                        changed["open_move:" + f] += 1
            row = {"era": era, "ticker": r.ticker, "D": r.D, "E": r.E, "ci": r.ci, "set": r.set, "month": r.month, **{f: vals.get(f, np.nan) for f in FEATS},
                   "f24_above": vals["f24_above"], "level": vals["level"], "ikey": r.ikey, "istr": r.istr, "first_break": r.first_break,
                   "raw_src": r.raw_src, "adr20": r.adr20}
            rows.append(row)
            for f, w in why.items():
                nulls.append((era, r.E[:4], f, w))
        P_(f"era {era}: features computed for {len(Ke)} events")
    FT = pd.DataFrame(rows)
    FT.to_parquet(C.BIG / f"r4_feature_table{C.SUF}.parquet", index=False)
    N = pd.DataFrame(nulls, columns=["era", "year", "feature", "reason"]).groupby(["feature", "era", "year", "reason"]).size().rename("n").reset_index()
    N.to_csv(C.OUTD / f"r4_null_counts{C.SUF}.tsv", sep="\t", index=False)
    P_("events", len(FT), "NULL totals by feature (all reasons):", {f: int(FT[f].isna().sum()) for f in FEATS})
    P_(f"CORRUPT-E proof: {n_tested} events x 3 garbage patterns; values changed per feature: {dict(changed)} (must be empty except open_move:f24 / leak); "
       f"positive control (leaky feature high(E)/close(D)) changed in {leak_changed} of {n_tested * 3} runs")
    ok = all(v == 0 or k.startswith("open_move:f24") for k, v in changed.items()) and not any(k.startswith("open_move") and k != "open_move:f24" for k in changed)
    P_("corrupt-E gate:", "PASS" if (not [k for k in changed if not k.startswith("open_move:")]) and leak_changed > 0 else "FAIL",
       "| open(E) moved ->", {k: v for k, v in changed.items() if k.startswith("open_move:")})
    json.dump({"changed": dict(changed), "leak_changed": leak_changed, "n_tested": n_tested,
               "null_totals": {f: int(FT[f].isna().sum()) for f in FEATS}}, open(C.OUTD / f"stage1f_results_r4{C.SUF}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
