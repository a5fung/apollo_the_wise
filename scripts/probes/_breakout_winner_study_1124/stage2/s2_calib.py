#!/usr/bin/env python3
"""STAGE 2 - calibration on SYNTHETIC labels only (prereg 6 step 2; 5.1, 5.2 cond 3, 5.2 "break-day selection" tag).
INPUTS: the outcome-free stage-1f feature table (kept events, seed 1124) + a random number generator. No bar, no outcome, nothing after
2024-12-31 (asserted in s2lib). Every "winner" below is a coin toss.

FROZEN BEFORE THE FIRST RUN (each is a reading the prereg text leaves open; all returned under "readings"):
 R1  base rate p = 5% outside 2020, 2020 at 3x (prereg 5.4's bolded row); 3% and 8% run as sensitivity. Era B at the same rate (1.0x).
     A block (era, E-month) rate is Beta around that rate, CV 0.6 (spread_sim_v2's model), so rates VARY between months and years.
 R2  planted effect k on feature f: label ~ Bernoulli(b, b(1+k)/2, b*k) by f's own (era, month) third, b = 2*pm/(1+k) (the EP rule);
     two-group: no = b, yes = b*k. Events NULL on f or in a month too small to hold thirds keep the month rate.
 R3  2,000 draws per (feature, case, rate); one generator per (feature, case, rate) seeded [1124, ...]. Condition 2's permutation p:
     within-month shuffle of labels among the scored events is EXACTLY a hypergeometric draw (EP precedent), 1,000 shuffles per
     draw (p = (1 + count) / 1,001), only for draws already passing condition 1 (10,000 x 2,000 draws x 22 features is not runnable).
 R4  smoothing: rates (w + .5)/(n + 1) ONLY when a third holds none (5.1 as written), then for BOTH rates; else raw.
 R5  B4 thirds (and B1 thirds) formed over ALL kept events of the era-quarter in the set (not only those scored on the feature);
     strata = (era, quarter, B4 third); feature thirds inside a stratum, strata holding >= 9 events scored on the feature (5.2 tag).
 R6  Floor rule (both floors, start 1.10, step 0.05, never under 1.05): the share of draws passing conditions 1-2 that also pass the
     floor in the planted direction, MEDIAN over the candidate features (the 22 not description-only); under 0.80 -> lower one step;
     1.05 still under 0.80 -> stays 1.05 (a stated weakness, not a failure). Decided on p = 5%; 3% / 8% printed.
 R7  CENTRING BAND (fixed now): the median over draws of a statistic's ratio on no-effect labels must lie in 0.95-1.05 (the EP A1
     precedent). BLOCKING: the carry-chain statistics (own, without-2020, B4-strata ratio on discovery; pooled / per-era / B4-strata
     on check; the Mantel-Haenszel ratio of the two-group features). NOT blocking, listed: B1-strata and the 5.5 population splits.
     The deterministic composition-expected ratio is printed beside every simulated median.
Run: python3 s2_calib.py > 2_calib.txt"""
import json, os, sys, time
from multiprocessing import Pool
import numpy as np
import pandas as pd
import s2lib as L

NDRAW, NSHUF, CV, X2020 = int(os.environ.get('NDRAW', 2000)), 1000, 0.6, 3.0
RATES = [0.05, 0.03, 0.08]
BAND = (0.95, 1.05)
L125, L110, L105 = np.log(1.25), np.log(1.10), np.log(1.05)

L.assert_docs()
T_ALL = L.load()
K, D, C = L.kept_events(T_ALL)
LAYOUT = L.check_layout(D)
D2411 = T_ALL[(T_ALL.kept2411 == True) & (T_ALL.set == "DISC")].reset_index(drop=True)   # noqa: E712

for fr in (D, C, D2411):                                  # B4 / B1 thirds over ALL events of the era-quarter in the set (R5)
    for col, nm in (("B4", "b4t"), ("B1", "b1t")):
        fr[nm] = L.assign_thirds(fr[col].to_numpy(float), [fr.era.to_numpy(), fr.quarter.to_numpy()], 1)
        assert (fr[nm] >= 0).all()


def blocks_of(df):
    key = (df.era + "|" + df.month).to_numpy()
    u, inv = np.unique(key, return_inverse=True)
    era = np.array([x.split("|")[0] for x in u])
    ey = np.array([int(x.split("|")[1][:4]) for x in u])
    return inv, era, ey


def pm_draw(rng, nd, era_b, ey, p, bmult=1.0):
    pb = p * np.where(ey == 2020, X2020, 1.0) * np.where(era_b, bmult, 1.0)
    a = np.maximum((1 - pb) / CV ** 2 - pb, 0.05)
    return rng.beta(a[None, :], (a * (1 - pb) / pb)[None, :], (nd, len(pb))), pb


def effect_rates(R, tm, k, two):
    b = 2 * R / (1 + k)
    if two:
        return np.where(tm == 2, b * k, np.where(tm == 0, b, R))
    return np.where(tm == 2, b * k, np.where(tm == 1, b * (1 + k) / 2, np.where(tm == 0, b, R)))


class Pop:
    """one population x one feature: the assignments (outcome-free) and the masks every statistic reads."""
    def __init__(self, df, col, two=False, strata=True):
        self.df, self.two, self.N = df, two, len(df)
        x = df[col].to_numpy(float)
        self.blk, self.blk_era, self.blk_ey = blocks_of(df)
        era, month, qtr = df.era.to_numpy(), df.month.to_numpy(), df.quarter.to_numpy()
        self.ey = df.Ey.to_numpy()
        if two:
            g = np.where(np.isnan(x), -1, np.nan_to_num(x)).astype(int)
            tm = L.assign_two(g, [era, month])
        else:
            tm = L.assign_thirds(x, [era, month], L.MIN_MONTH)
        self.tm, self.x = tm, x
        self.sets = {"all": (tm == 2, tm == 0)}
        self.sets["ex2020"] = (self.sets["all"][0] & (self.ey != 2020), self.sets["all"][1] & (self.ey != 2020))
        self.has2020 = bool((self.ey == 2020).any())
        for e in ("A", "B"):
            m = era == e
            if m.any():
                self.sets["era" + e] = (self.sets["all"][0] & m, self.sets["all"][1] & m)
        self.strata_blocks = {}
        if strata and "b4t" in df.columns:
            for nm, col_t in (("b4", "b4t"), ("b1", "b1t")):
                bt = df[col_t].to_numpy()
                if two:
                    t2 = L.assign_two(g, [era, qtr, bt])
                    _, inv = np.unique(pd.Series(era + qtr + bt.astype(str)), return_inverse=True)
                    ok = t2 >= 0
                    # strata must hold >= 9 events scored on the feature
                    cnt = pd.Series(np.where(ok, 1, 0)).groupby(inv).transform("sum").to_numpy()
                    t2 = np.where(cnt >= L.MIN_STRATUM, t2, -1).astype(np.int8)
                    self.strata_blocks[nm] = (t2, inv)
                    self.sets[nm] = (t2 == 2, t2 == 0)
                else:
                    t2 = L.assign_thirds(x, [era, qtr, bt], L.MIN_STRATUM)
                    self.sets[nm] = (t2 == 2, t2 == 0)
        # permutation layout (months holding thirds)
        key = (df.era + "|" + df.month).to_numpy()
        self.months = sorted(set(key[tm >= 0]))
        mi = np.array([self.months.index(k_) if t >= 0 else -1 for k_, t in zip(key, tm)])
        self.mi = mi
        M = len(self.months)
        self.n_m = np.array([(mi == q).sum() for q in range(M)])
        self.t_m = np.array([((mi == q) & (tm == 2)).sum() for q in range(M)])
        self.b_m = np.array([((mi == q) & (tm == 0)).sum() for q in range(M)])
        oh = np.zeros((self.N, M), dtype=np.float32)
        if M:
            oh[np.flatnonzero(mi >= 0), mi[mi >= 0]] = 1.0
        self.onehot = oh
        if two:                                   # MH blocks = months
            self.mh_blocks = {"all": (mi, M)}
            self.ny_m = np.array([((mi == q) & (tm == 2)).sum() for q in range(M)])
            self.nn_m = np.array([((mi == q) & (tm == 0)).sum() for q in range(M)])

    def expected_null(self, pb_events):
        """deterministic composition-expected ratio of every set under no effect: sum of event rates in the top group over the bottom."""
        out = {}
        for nm, (tp, bt) in self.sets.items():
            if two_set(self, nm):
                continue
            out[nm] = float(pb_events[tp].sum() / max(tp.sum(), 1)) / float(pb_events[bt].sum() / max(bt.sum(), 1)) if tp.any() and bt.any() else float("nan")
        return out


def two_set(pop, nm):
    return False


def event_pb(pop, p, bmult=1.0):
    return p * np.where(pop.ey == 2020, X2020, 1.0) * np.where(pop.df.era.to_numpy() == "B", bmult, 1.0)


def perm_p(pop, Lf, r, rng):
    """two-sided permutation p of the pooled thirds ratio for the draws in `r` (indices): exact hypergeometric within-month shuffle."""
    top, bot = pop.sets["all"]
    W = (Lf @ pop.onehot).astype(np.int64)                    # winners among assigned events per month
    nt, nb = int(top.sum()), int(bot.sum())
    pval = np.ones(Lf.shape[0])
    M = len(pop.months)
    return W, nt, nb


def run_case(pop, p, k, rng, nd=NDRAW, bmult=1.0, b4_only=False, need_p=True):
    """returns dict of arrays (draws,) of log ratios per set, c1, pval, plus winners matrix handles."""
    nblk = len(pop.blk_era)
    pm, pb = pm_draw(rng, nd, pop.blk_era == "B", pop.blk_ey, p, bmult)
    R = pm[:, pop.blk].astype(np.float32)
    if b4_only:
        bt = pop.df["b4t"].to_numpy()
        b = 2 * R / (1 + 2.0)
        rate = np.where(bt == 2, b * 2.0, np.where(bt == 1, b * 1.5, b))
    elif k == 1.0:
        rate = R
    else:
        rate = effect_rates(R, pop.tm, k, pop.two)
    Lf = (rng.random(R.shape, dtype=np.float32) < rate).astype(np.float32)
    res = {}
    if pop.two:
        mi = pop.mi
        W_y = np.zeros((nd, len(pop.months)), np.float64); W_n = np.zeros_like(W_y)
        yes, no = pop.sets["all"]
        for sname, (tp, bt_) in pop.sets.items():
            if sname in ("b4", "b1"):
                t2, inv = pop.strata_blocks[sname]
                nb_ = inv.max() + 1
                oh_y = np.zeros((pop.N, nb_), np.float32); oh_n = np.zeros((pop.N, nb_), np.float32)
                oh_y[np.flatnonzero(tp), inv[tp]] = 1; oh_n[np.flatnonzero(bt_), inv[bt_]] = 1
                ny_, nn_ = oh_y.sum(0), oh_n.sum(0)
                keep = (ny_ >= 2) & (nn_ >= 2)
                res["mh_" + sname] = L.mh_counts((Lf @ oh_y)[:, keep], ny_[keep], (Lf @ oh_n)[:, keep], nn_[keep]) if keep.any() else np.full(nd, np.nan)
                continue
            use = np.arange(len(pop.months))
            oh_y = pop.onehot * tp[:, None]; oh_n = pop.onehot * bt_[:, None]
            ny_, nn_ = oh_y.sum(0), oh_n.sum(0)
            keep = (ny_ >= 2) & (nn_ >= 2)
            if not keep.any():
                res["mh_" + sname] = np.full(nd, np.nan); res["pool_" + sname] = np.full(nd, np.nan); continue
            res["mh_" + sname] = L.mh_counts((Lf @ oh_y)[:, keep], ny_[keep], (Lf @ oh_n)[:, keep], nn_[keep])
            res["pool_" + sname] = L.ratio_counts(Lf @ tp.astype(np.float32), tp.sum(), Lf @ bt_.astype(np.float32), bt_.sum())
        return res, None, None
    for sname, (tp, bt_) in pop.sets.items():
        if tp.sum() == 0 or bt_.sum() == 0:
            res[sname] = np.full(nd, np.nan); continue
        res[sname] = np.log(L.ratio_counts(Lf @ tp.astype(np.float32), tp.sum(), Lf @ bt_.astype(np.float32), bt_.sum()))
    r = res["all"]
    c1 = np.abs(r) >= L125 - 1e-12
    pval = np.ones(nd)
    if need_p and len(pop.months):
        Wm = (Lf @ pop.onehot).astype(np.int64)
        top_n, bot_n = int(pop.t_m.sum()), int(pop.b_m.sum())
        idx = np.flatnonzero(c1)
        for a0 in range(0, len(idx), 100):
            ii = idx[a0:a0 + 100]
            W = Wm[ii][None, :, :]
            shp = (NSHUF,) + W.shape[1:]
            Tt = rng.hypergeometric(np.broadcast_to(W, shp), np.broadcast_to(pop.n_m[None, None, :] - W, shp), np.broadcast_to(pop.t_m[None, None, :], shp))
            rg = W - Tt
            rb = (pop.n_m - pop.t_m)[None, None, :] - rg
            Bb = rng.hypergeometric(rg, rb, np.broadcast_to(pop.b_m[None, None, :], rg.shape))
            pr = np.log(L.ratio_counts(Tt.sum(2), top_n, Bb.sum(2), bot_n))
            cnt = (np.abs(pr) >= np.abs(r[ii])[None, :] - 1e-12).sum(0)
            pval[ii] = (1 + cnt) / (NSHUF + 1)
    return res, c1, pval


# ---------------------------------------------------------------------------------------------------------------- tasks
CASES = [("k=1.0", 1.0), ("k=1.3", 1.3), ("k=1.5", 1.5), ("B4-only 2.0x", None)]


def disc_task(arg):
    fi, f = arg
    DD, col = L.pop_frame(D, f)
    two = f in L.TWO_GROUP
    if f == "f14":
        return dict(f=f, evaluable=False, n_yes=int((DD[col] == 1).sum()), n_no=int((DD[col] == 0).sum()))
    pop = Pop(DD, col, two=two)
    out = dict(f=f, evaluable=True, two=two, scored=int(np.isfinite(pop.x).sum()), assigned=int((pop.tm >= 0).sum()),
               expected={p_: pop.expected_null(event_pb(pop, p_)) for p_ in RATES} if not two else {}, rec={})
    for pi, p in enumerate(RATES):
        for ci_, (cn, k) in enumerate(CASES):
            if two and cn == "B4-only 2.0x":
                continue
            if two and cn == "k=1.3":
                continue
            if p != 0.05 and cn in ("k=1.3", "B4-only 2.0x"):
                continue
            rng = np.random.default_rng([L.SEED, fi, pi, ci_])
            res, c1, pval = run_case(pop, p, k if k else 1.0, rng, b4_only=(k is None), need_p=not two)
            if two:
                out["rec"][(p, cn)] = {kk: (float(np.nanmedian(v)), float(np.nanmean(np.log(v[np.isfinite(v) & (v > 0)]))), int(np.isnan(v).sum()))
                                        for kk, v in res.items()}
                continue
            r = res["all"]; c2 = pval <= 0.05; c12 = c1 & c2
            sgn = np.sign(r)
            rec = dict(c1=float(c1.mean()), c12=float(c12.mean()), n12=int(c12.sum()),
                       centre={s: (float(np.nanmedian(np.exp(v))), float(np.nanmean(v)), int(np.isnan(v).sum())) for s, v in res.items()},
                       planted_dir=float((c12 & (sgn > 0)).mean()))
            for s in ("ex2020", "b4", "b1"):
                if s in res:
                    for fl, lf in ((1.10, L110), (1.05, L105)):
                        ok = sgn * res[s] >= lf - 1e-12
                        rec[f"{s}@{fl:.2f}"] = float((ok & c12).sum() / max(1, c12.sum()))
                        rec[f"_ok_{s}@{fl:.2f}"] = ok
            rec["_c12"] = c12; rec["_sgn"] = sgn
            out["rec"][(p, cn)] = rec
    return out


def check_task(arg):
    fi, f = arg
    DD, col = L.pop_frame(C, f)
    two = f in L.TWO_GROUP
    if f == "f14":
        return dict(f=f, evaluable=False)
    pop = Pop(DD, col, two=two)
    out = dict(f=f, evaluable=True, two=two, scored=int(np.isfinite(pop.x).sum()), rec={},
               expected={p_: pop.expected_null(event_pb(pop, p_)) for p_ in RATES} if not two else {})
    for pi, p in enumerate(RATES):
        for ci_, (cn, k) in enumerate((("k=1.0", 1.0), ("k=1.5", 1.5))):
            rng = np.random.default_rng([L.SEED, 100 + fi, pi, ci_])
            res, c1, pval = run_case(pop, p, k, rng, need_p=False)
            if two:
                out["rec"][(p, cn)] = {kk: (float(np.nanmedian(v)), float(np.nanmean(np.log(v[np.isfinite(v) & (v > 0)]))), int(np.isnan(v).sum())) for kk, v in res.items()}
            else:
                out["rec"][(p, cn)] = {s: (float(np.nanmedian(np.exp(v))), float(np.nanmean(v)), int(np.isnan(v).sum())) for s, v in res.items()}
    return out


POPS = {   # 5.5 population splits, discovery (thirds re-formed INSIDE each population)
    "first break (after 10 quiet)": lambda d: d[d.first10 == True],            # noqa: E712
    "later breaks": lambda d: d[d.first10 == False],                           # noqa: E712
    "common stock only": lambda d: d[d.sectype == "CS"],
    "price >= $5": lambda d: d[d.f02 >= 5],
    "embargoed (E<=2020-10-06)": lambda d: d[d.E <= "2020-10-06"],
    "2019-20 alone": lambda d: d[d.Ey.isin([2019, 2020])],
    "second seed (2411)": None,
}
CHK_POPS = {
    "check: first break": lambda d: d[d.first10 == True],                      # noqa: E712
    "check: later breaks": lambda d: d[d.first10 == False],                    # noqa: E712
    "check: common stock only": lambda d: d[d.sectype == "CS"],
    "check: price >= $5": lambda d: d[d.f02 >= 5],
}


def pops_task(arg):
    fi, f = arg
    out = dict(f=f, rec={})
    for pi_, (pn, fn) in enumerate(list(POPS.items()) + list(CHK_POPS.items())):
        if pn == "second seed (2411)":
            base = D2411
        elif pn.startswith("check:"):
            base = C
        else:
            base = D
        fr = (fn(base) if fn else base).reset_index(drop=True)
        DD, col = L.pop_frame(fr, f)
        if len(DD) < 30:
            continue
        pop = Pop(DD, col, strata=False)
        if not len(pop.months):
            continue
        rng = np.random.default_rng([L.SEED, 200 + fi, pi_])
        res, _, _ = run_case(pop, 0.05, 1.0, rng, need_p=False)
        e = pop.expected_null(event_pb(pop, 0.05))
        out["rec"][pn] = dict(n=len(DD), scored=int(np.isfinite(pop.x).sum()), top=int(pop.sets["all"][0].sum()), bot=int(pop.sets["all"][1].sum()),
                              med=float(np.nanmedian(np.exp(res["all"]))), exp=e.get("all", float("nan")), nnan=int(np.isnan(res["all"]).sum()))
    return out


if __name__ == "__main__":
    t0 = time.time()
    P = print
    P("# STAGE 2 / calibration on SYNTHETIC labels (prereg 6 step 2). INPUT: the outcome-free feature table (kept events, seed 1124) + a random number generator.")
    P(f"prereg sha256 {L.PREREG_SHA[:8]} and A1 {L.A1_SHA[:8]} asserted | feature table sha256 {L.TABLE_SHA[:8]} asserted | max E on file {T_ALL.E.max()} (seal: nothing after {L.CUT})")
    P(f"populations: discovery {len(D)} (2017 {int((D.Ey == 2017).sum())} / 2018 {int((D.Ey == 2018).sum())} / 2019 {int((D.Ey == 2019).sum())} / 2020 {int((D.Ey == 2020).sum())}), check {len(C)} (era A {int((C.era == 'A').sum())}, era B {int((C.era == 'B').sum())}); second-seed discovery {len(D2411)}")
    P(f"copied thirds helper reproduces stage 1f's printed layout (bottom / middle / top): {LAYOUT}")
    P(f"draws {NDRAW} per (feature, case, rate); permutation shuffles {NSHUF} (exact hypergeometric); rates {RATES} (2020 x{X2020}, month CV {CV}); centring band {BAND}")
    ARGS = list(enumerate(L.FEATS))
    with Pool(9) as pool:
        DR = pool.map(disc_task, ARGS, chunksize=1)
        P(f"[discovery tasks done {time.time() - t0:.0f}s]", file=sys.stderr)
        CR = pool.map(check_task, ARGS, chunksize=1)
        P(f"[check tasks done {time.time() - t0:.0f}s]", file=sys.stderr)
        PR = pool.map(pops_task, [(i, f) for i, f in ARGS if f in L.CANDIDATES], chunksize=1)
        P(f"[population tasks done {time.time() - t0:.0f}s]", file=sys.stderr)
    DRd = {r["f"]: r for r in DR}
    CRd = {r["f"]: r for r in CR}
    miscentred, listed = [], []

    def judge(label, med, blocking, exp=None):
        ok = BAND[0] <= med <= BAND[1] or not np.isfinite(med)
        if not ok:
            (miscentred if blocking else listed).append((label, med, exp))
        return "" if ok else ("   <-- OUTSIDE BAND" + (" (BLOCKING)" if blocking else " (listed)"))

    # ------------------------------------------------------------------------------------------ A. no-effect centring, discovery
    P("\n## A. EVERY STATISTIC CENTRED ON 1.0 UNDER NO EFFECT - discovery (median of the draws' ratio; expected = the deterministic composition ratio; band 0.95-1.05)")
    P("##    columns: own (all discovery months) | without 2020 | B4-strata (the tag's form) | B1-strata (listed only)")
    for p in RATES:
        P(f"\n### base rate {p:.0%} outside 2020 (2020: {X2020 * p:.0%})")
        for f in L.FEATS:
            r = DRd[f]
            if not r["evaluable"]:
                P(f"  {f} NOT EVALUABLE: the group sizes are yes {r['n_yes']} / no {r['n_no']} (empty by the live code, stage 1f) - reported as not evaluable, not as a pass")
                continue
            if r["two"]:
                rec = r["rec"][(p, "k=1.0")]
                s = " | ".join(f"{k_[3:] if k_.startswith('mh_') else k_}: MH {v[0]:.3f}{judge(f + ' MH ' + k_ + f' @{p:.0%}', v[0], k_.startswith('mh_') and k_ != 'mh_b1')}" if k_.startswith("mh_")
                               else f"{k_[5:]}: pooled yes/no {v[0]:.3f} (the biased one)" for k_, v in rec.items())
                P(f"  {f} two-group (MH by month; NaN draws " + ",".join(f"{k_[3:]} {v[2]}" for k_, v in rec.items() if k_.startswith('mh_')) + f") {s}")
                continue
            rec = r["rec"][(p, "k=1.0")]["centre"]; ex = r["expected"][p]
            cells = []
            for s_, blocking in (("all", True), ("ex2020", True), ("b4", True), ("b1", False)):
                if s_ in rec:
                    cells.append(f"{s_} {rec[s_][0]:.3f} (exp {ex.get(s_, float('nan')):.3f}){judge(f + ' ' + s_ + f' @{p:.0%}', rec[s_][0], blocking, ex.get(s_))}")
            P(f"  {f:5s} scored {r['scored']:5d} assigned {r['assigned']:5d} | " + " | ".join(cells))
    # ------------------------------------------------------------------------------------------ B. check centring
    P("\n## B. NO-EFFECT CENTRING - check set (pooled | era A | era B | B4-strata | B1-strata listed)")
    for p in RATES:
        P(f"\n### base rate {p:.0%}")
        for f in L.FEATS:
            r = CRd[f]
            if not r["evaluable"]:
                P(f"  {f} NOT EVALUABLE (empty)"); continue
            rec = r["rec"][(p, "k=1.0")]
            if r["two"]:
                s = " | ".join((f"MH {k_[3:]} {v[0]:.3f}{judge(f + ' check MH ' + k_ + f' @{p:.0%}', v[0], k_ != 'mh_b1')}" if k_.startswith("mh_") else f"{k_[5:]} pooled {v[0]:.3f}") for k_, v in rec.items())
                P(f"  {f} two-group {s}")
                continue
            ex = r["expected"][p]
            cells = []
            for s_, blocking in (("all", True), ("eraA", True), ("eraB", True), ("b4", True), ("b1", False)):
                if s_ in rec:
                    cells.append(f"{s_} {rec[s_][0]:.3f} (exp {ex.get(s_, float('nan')):.3f}){judge(f + ' check ' + s_ + f' @{p:.0%}', rec[s_][0], blocking, ex.get(s_))}")
            P(f"  {f:5s} scored {r['scored']:5d} | " + " | ".join(cells))
    # ------------------------------------------------------------------------------------------ C. populations
    P("\n## C. 5.5 POPULATION SPLITS - own ratio under no effect (5%; thirds re-formed inside each population; listed only, not blocking)")
    allp = [pn for pn in list(POPS) + list(CHK_POPS)]
    for pn in allp:
        meds = [(r["f"], r["rec"][pn]) for r in PR if pn in r["rec"]]
        out_ = [(f, v) for f, v in meds if not BAND[0] <= v["med"] <= BAND[1]]
        P(f"  {pn:32s} features {len(meds):2d} | median-of-medians {np.median([v['med'] for _, v in meds]):.3f} | range {min(v['med'] for _, v in meds):.3f}-{max(v['med'] for _, v in meds):.3f}"
          f" | outside band: " + (", ".join(f"{f} {v['med']:.3f} (exp {v['exp']:.3f}, top {v['top']} / bot {v['bot']})" for f, v in out_) if out_ else "none"))
        for f, v in out_:
            listed.append((f"{pn} {f}", v["med"], v["exp"]))
    # ------------------------------------------------------------------------------------------ D. false carry
    P("\n## D. FALSE-CARRY AND DETECTION (conditions 1-2 on no-effect labels; the nominal is about 5%)")
    for p in RATES:
        v = [DRd[f]["rec"][(p, "k=1.0")]["c12"] for f in L.CANDIDATES]
        P(f"  rate {p:.0%}: conditions 1-2 on k=1.0, median over the {len(v)} candidates {np.median(v):.3f} (min {min(v):.3f}, max {max(v):.3f}); conditions 1 only {np.median([DRd[f]['rec'][(p, 'k=1.0')]['c1'] for f in L.CANDIDATES]):.3f}")
    for cn in ("k=1.3", "k=1.5"):
        v = [DRd[f]["rec"][(0.05, cn)]["c12"] for f in L.CANDIDATES]
        P(f"  rate 5% {cn}: conditions 1-2 median {np.median(v):.3f} (min {min(v):.3f}, max {max(v):.3f}) - detection")
    for f in L.TWO_GROUP:
        r = DRd[f]
        if r["evaluable"]:
            P(f"  {f} (MH): planted 1.5x MH median {r['rec'][(0.05, 'k=1.5')]['mh_all'][0]:.3f} vs no effect {r['rec'][(0.05, 'k=1.0')]['mh_all'][0]:.3f} (a dead statistic would read 1.0 on both)")
    # ------------------------------------------------------------------------------------------ E. floors
    P("\n## E. THE TWO FLOORS (planted 1.5x; share of draws passing conditions 1-2 that also pass the floor, MEDIAN over the candidates; under 0.80 -> lower 0.05, never under 1.05)")
    final = {}
    for p in RATES:
        P(f"\n### rate {p:.0%}")
        for nm, key, label in (("ex2020", "ex2020", "condition 3, without-2020 ratio"), ("b4", "b4", "break-day-selection (B4-strata) ratio")):
            chosen, lines = None, []
            for fl in (1.10, 1.05):
                vals = [DRd[f]["rec"][(p, "k=1.5")][f"{key}@{fl:.2f}"] for f in L.CANDIDATES]
                med = float(np.median(vals))
                lines.append(f"    {label} at {fl:.2f}: median pass {med:.3f} over {len(vals)} candidates (min {min(vals):.3f}, max {max(vals):.3f}) -> {'>= 0.80 OK' if med >= 0.80 else 'UNDER 0.80'}")
                if chosen is None and med >= 0.80:
                    chosen = fl
            weak = chosen is None
            if weak:
                chosen = 1.05
                lines.append(f"    {label}: 1.05 still under 0.80 -> stays 1.05 (STATED WEAKNESS)")
            P("\n".join(lines))
            final[(p, nm)] = (chosen, weak)
            P(f"    => {label} floor at {p:.0%}: {chosen:.2f}{' (weak)' if weak else ''}; lowering rule {'FIRED' if chosen != 1.10 else 'did not fire'}")
    fl3, w3 = final[(0.05, "ex2020")]; fl4, w4 = final[(0.05, "b4")]
    P("\n## CALIBRATED FLOORS (decided on the 5% row, the prereg's bolded one)")
    P(f"  condition 3 (without 2020): frozen start 1.10 -> FINAL {fl3:.2f} (or <= {1 / fl3:.3f} the other way) | lowering rule {'FIRED' if fl3 != 1.10 else 'did NOT fire'}{' | STATED WEAKNESS' if w3 else ''}")
    P(f"  break-day-selection tag (B4 strata): frozen start 1.10 -> FINAL {fl4:.2f} | lowering rule {'FIRED' if fl4 != 1.10 else 'did NOT fire'}{' | STATED WEAKNESS' if w4 else ''}")
    for nm in ("ex2020", "b4"):
        vs = {p: final[(p, nm)][0] for p in RATES}
        P(f"  sensitivity {nm}: " + ", ".join(f"{p:.0%} -> {v:.2f}" for p, v in vs.items()) + (" (differ across rates: the 5% row decides; stage 3 prints the 2017-19 rate)" if len(set(vs.values())) > 1 else " (same at every rate)"))
    # ------------------------------------------------------------------------------------------ F. carry chain + does the tag ever fire
    P("\n## F. CARRY CHAIN with the final floors (5%): share of draws passing 1-2 | 1-3 | and the tag (B4 ratio under its floor) among the 1-3 carriers")
    summ = {}
    for cn in ("k=1.0", "k=1.3", "k=1.5", "B4-only 2.0x"):
        c12s, c123s, tag_s = [], [], []
        for f in L.CANDIDATES:
            rec = DRd[f]["rec"][(0.05, cn)]
            c12 = rec["_c12"]; c123 = c12 & rec[f"_ok_ex2020@{fl3:.2f}"]
            tagged = c123 & ~rec[f"_ok_b4@{fl4:.2f}"]
            c12s.append(c12.mean()); c123s.append(c123.mean()); tag_s.append(tagged.sum() / max(c123.sum(), 1))
        summ[cn] = (np.median(c12s), np.median(c123s), np.median(tag_s))
        P(f"  {cn:13s}: median over candidates: 1-2 {np.median(c12s):.3f} | 1-3 {np.median(c123s):.3f} | tag fires on {np.median(tag_s):.3f} of the carriers (max over features {max(tag_s):.3f})")
    P("  (the B4-only case plants an effect on how big a day E had to be and none on the feature: a tag that never fires on it would be dead)")
    # ------------------------------------------------------------------------------------------ verdict
    P("\n## GATE: centring of every carry-chain and tag statistic")
    P(f"  BLOCKING statistics outside {BAND}: {len(miscentred)}")
    for lab, med, ex in miscentred:
        P(f"    {lab}: median {med:.3f} (composition-expected {ex})")
    P(f"  listed (not blocking) outside the band: {len(listed)}")
    for lab, med, ex in listed:
        P(f"    {lab}: median {med:.3f} (composition-expected {ex})")
    gate = len(miscentred) == 0
    P(f"  GATE (centring): {'PASS' if gate else 'FAIL'}")
    json.dump(dict(gate_centring=gate, miscentred=[(a, float(b)) for a, b, _ in miscentred], listed=[(a, float(b)) for a, b, _ in listed],
                   floor_ex2020=fl3, floor_b4=fl4, weak_ex2020=w3, weak_b4=w4, final={f"{k[0]}|{k[1]}": v[0] for k, v in final.items()},
                   n_candidates=len(L.CANDIDATES), secs=time.time() - t0, summ={k: [float(x) for x in v] for k, v in summ.items()}),
              open(L.HERE / "2_calib_result.json", "w"), indent=1)
    rows = []
    for f in L.FEATS:
        r = DRd[f]
        if not r["evaluable"] or r["two"]:
            continue
        for (p, cn), rec in r["rec"].items():
            rows.append(dict(feature=f, rate=p, case=cn, c1=rec["c1"], c12=rec["c12"], planted_dir=rec["planted_dir"],
                             **{k_: v for k_, v in rec.items() if k_ in ("ex2020@1.10", "ex2020@1.05", "b4@1.10", "b4@1.05", "b1@1.10", "b1@1.05")},
                             **{"med_" + s: v[0] for s, v in rec["centre"].items()}))
    pd.DataFrame(rows).to_csv(L.HERE / "calibration_rates.tsv", sep="\t", index=False, float_format="%.4f")
    (L.HERE / "floors_final.txt").write_text(
        f"condition 3 (without-2020) floor: {fl3:.2f} (lowering rule fired: {fl3 != 1.10}; stated weakness: {w3})\n"
        f"break-day-selection (B4 strata) floor: {fl4:.2f} (lowering rule fired: {fl4 != 1.10}; stated weakness: {w4})\n"
        f"decided on the 5% outside-2020 row; sensitivity 3% / 8%: " + ", ".join(f"{k[1]}@{k[0]:.0%}={v[0]:.2f}" for k, v in final.items()) + "\n"
        f"prereg sha256 {L.PREREG_SHA}\nA1 sha256 {L.A1_SHA}\nfeature_table sha256 {L.TABLE_SHA}\n"
        "NOTE: the frozen prereg document was NOT edited by stage 2; writing these floors into the run and recording them is left to the caller.\n")
    P(f"\ncalibration_rates.tsv sha256 {L.sha(L.HERE / 'calibration_rates.tsv')[:16]} | floors_final.txt sha256 {L.sha(L.HERE / 'floors_final.txt')[:16]} | this script {L.sha(__file__)[:16]} | {time.time() - t0:.0f}s")
