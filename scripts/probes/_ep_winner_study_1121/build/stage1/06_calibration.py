#!/usr/bin/env python3
"""STAGE 1 / step 2 — floor calibration on SYNTHETIC labels (prereg §6 step 2, §5.2). NO FORWARD READ: the only inputs are the
outcome-free feature table (discovery rows) and a random number generator. Every "winner" below is a coin toss.

Frozen: 2,000 draws per feature per case; a planted effect k on feature f: label ~ Bernoulli(b, b(1+k)/2, bk) by f's own
within-month third (two-group: no = b, yes = bk), b = 2p/(1+k), p = 4.9% for 2016-19 and 25% for 2020; events NULL on f (or in a
month too small to hold thirds) get rate p. Cases k = 1.0, 1.3, 1.5, and one ADR-only case (rate by ADR20 third within
era-quarter, 2.0x, independent of f).

IMPLEMENTATION CHOICES THE FROZEN TEXT DOES NOT FIX (each printed and returned as an ambiguity):
 (i)  Condition 2's permutation p inside each synthetic draw: 10,000 label shuffles x 160,000 draws is not runnable. The within-
      month shuffle of labels among the scored events is EXACTLY a hypergeometric draw of the winners landing in the top and the
      bottom third of each month, so the p is sampled from that exact distribution with 1,000 shuffles per draw
      (p = (1 + count) / 1,001), only for draws that already pass condition 1. BESIDE: the design-stage stand-in
      (spread_sim.py: |log ratio| >= the 95th percentile of the k = 1.0 draws).
 (ii) RNG: one generator per (feature, case), default_rng([1121, feature index, case index]) — a single default_rng(1121) stream
      cannot be shared across parallel workers reproducibly.
 (iii) ADR20 thirds of an era-quarter are formed over ALL discovery events of that era-quarter (encoder ADR20), not only those
      scored on f; dmin thirds over all discovery events with a dmin.
 (iv) All ratios use the smoothed rates (winners + 0.5) / (n + 1) (§5.1 "every test uses rates smoothed").
Run: python3 06_calibration.py > 06_calibration.txt"""
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

import common as C
import features as F
import stats as S

NDRAW, NSHUF = 2000, 1000
P_BASE = {False: 0.049, True: 0.25}                       # 2016-19 / 2020
CASES = [("k=1.0", 1.0), ("k=1.3", 1.3), ("k=1.5", 1.5), ("ADR-only 2.0x", None)]
FLOORS = {3: [1.10, 1.05], 4: [1.15, 1.10, 1.05], 5: [1.10, 1.05]}
T = pd.read_csv(C.HERE / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "year": str})
D = T[T.set == "DISC"].reset_index(drop=True)
assert len(D) == 2414 and (D.era == "A").all() and D.E.max() <= C.DISC_LAST
N = len(D)
is2020 = (D.year == "2020").to_numpy()
p_event = np.where(is2020, P_BASE[True], P_BASE[False])
DEC = pd.read_csv(C.HERE / "feature_decisions.tsv", sep="\t").set_index("feature").decision.to_dict()
REL = [x for x in (C.HERE / "shelf_relatives.txt").read_text().split() if x]
# strata labels
D["adr_third"] = S.assign_thirds(D, "adr20_raw", ["era", "quarter"], 1, midrank=True)
assert (D.adr_third >= 0).all()
D["dmin_third"] = S.assign_thirds(D, "B1", ["era", "quarter"], 1, midrank=True)        # -1 where dmin is NULL


def layout(f):
    """per-event assignments for feature f: month thirds, ADR-stratum thirds, dmin-stratum thirds (2 top/yes, 0 bottom/no, 1 middle, -1 none)."""
    if DEC[f].startswith("two-group"):
        g = np.where(D[f].isna(), -1, D[f].fillna(0)).astype(int)
        tm = S.assign_two(D, g, ["era", "month"], min_n=S.MIN_MONTH)
        ta = S.assign_two(D, g, ["era", "quarter", "adr_third"], min_n=S.MIN_STRATUM)
        Dd = D.copy(); g2 = np.where(D.dmin_third >= 0, g, -1)
        td = S.assign_two(Dd, g2, ["era", "quarter", "dmin_third"], min_n=S.MIN_STRATUM)
    else:
        tm = S.assign_thirds(D, f, ["era", "month"], S.MIN_MONTH)
        ta = S.assign_thirds(D, f, ["era", "quarter", "adr_third"], S.MIN_STRATUM)
        Dd = D.copy(); Dd.loc[Dd.dmin_third < 0, f] = np.nan
        td = S.assign_thirds(Dd, f, ["era", "quarter", "dmin_third"], S.MIN_STRATUM)
    return tm, ta, td


def sm_ratio(wt, nt, wb, nb):
    return ((wt + 0.5) / (nt + 1.0)) / ((wb + 0.5) / (nb + 1.0))


def work(arg):
    fi, f = arg
    two = DEC[f].startswith("two-group")
    tm, ta, td = layout(f)
    mkey = (D.era + D.month).to_numpy()
    months = sorted(set(mkey[tm >= 0]))
    mi = np.array([months.index(x) if t >= 0 else -1 for x, t in zip(mkey, tm)])
    M = len(months)
    n_m = np.array([(mi == q).sum() for q in range(M)])
    t_m = np.array([((mi == q) & (tm == 2)).sum() for q in range(M)])
    b_m = np.array([((mi == q) & (tm == 0)).sum() for q in range(M)])
    onehot = np.zeros((N, M), dtype=np.float32)
    onehot[np.flatnonzero(mi >= 0), mi[mi >= 0]] = 1.0
    top, bot = (tm == 2), (tm == 0)
    x20 = ~is2020
    sets = {"all": (top, bot), "ex2020": (top & x20, bot & x20), "adr": (ta == 2, ta == 0), "dmin": (td == 2, td == 0)}
    info = dict(feature=f, two_group=two, scored=int(D[f].notna().sum()), in_months=int((tm >= 0).sum()), months=M,
                n_top=int(top.sum()), n_bot=int(bot.sum()), n_top_ex2020=int((top & x20).sum()), n_bot_ex2020=int((bot & x20).sum()),
                adr_strata_events=int((ta >= 0).sum()), dmin_strata_events=int((td >= 0).sum()))
    for nm, (tp, bt) in sets.items():                         # ADDED after run 1: the ratio a feature with NO effect is expected to show
        info["null_" + nm] = float(p_event[tp].mean() / p_event[bt].mean()) if tp.sum() and bt.sum() else float("nan")
    out = []
    null_abs = None
    for ci_, (cname, k) in enumerate(CASES):
        rng = np.random.default_rng([C.SEED, fi, ci_])
        if k is None:                                           # ADR-only: rate by ADR20 third within era-quarter, 2.0x, independent of f
            kk = 2.0; b = 2 * p_event / (1 + kk)
            rate = np.where(D.adr_third.to_numpy() == 2, b * kk, np.where(D.adr_third.to_numpy() == 1, b * (1 + kk) / 2, b))
        else:
            b = 2 * p_event / (1 + k)
            if two:
                rate = np.where(tm == 2, b * k, np.where(tm == 0, b, p_event))
            else:
                rate = np.where(tm == 2, b * k, np.where(tm == 1, b * (1 + k) / 2, np.where(tm == 0, b, p_event)))
        L = (rng.random((NDRAW, N)) < rate[None, :])
        Lf = L.astype(np.float32)
        lr = {}
        for nm, (tp, bt) in sets.items():
            lr[nm] = np.log(sm_ratio(Lf[:, tp].sum(1), tp.sum(), Lf[:, bt].sum(1), bt.sum()))
        r = lr["all"]
        c1 = np.abs(r) >= np.log(1.25) - 1e-12
        # condition 2: exact within-month permutation distribution by hypergeometric sampling, for the draws that pass condition 1
        Wm = (Lf @ onehot).astype(np.int64)                      # winners among the scored-and-assigned events of each month
        pval = np.ones(NDRAW)
        idx = np.flatnonzero(c1)
        for a0 in range(0, len(idx), 100):
            ii = idx[a0:a0 + 100]
            W = Wm[ii][None, :, :]
            Tt = rng.hypergeometric(np.broadcast_to(W, (NSHUF,) + W.shape[1:]), np.broadcast_to(n_m[None, None, :] - W, (NSHUF,) + W.shape[1:]),
                                    np.broadcast_to(t_m[None, None, :], (NSHUF,) + W.shape[1:]))
            if two:
                Bb = W - Tt
            else:
                rem_good = W - Tt
                rem_bad = (n_m - t_m)[None, None, :] - rem_good
                Bb = rng.hypergeometric(rem_good, rem_bad, np.broadcast_to(b_m[None, None, :], rem_good.shape))
            pr = np.log(sm_ratio(Tt.sum(2), t_m.sum(), Bb.sum(2), b_m.sum()))        # (NSHUF, len(ii))
            cnt = (np.abs(pr) >= np.abs(r[ii])[None, :] - 1e-12).sum(0)
            pval[ii] = (1 + cnt) / (NSHUF + 1)
        c2 = pval <= 0.05
        c12 = c1 & c2
        if k == 1.0:
            null_abs = np.quantile(np.abs(r), 0.95)
        c12_standin = c1 & (np.abs(r) >= null_abs)
        sgn = np.sign(r)
        rec = dict(feature=f, case=cname, c1=c1.mean(), c12=c12.mean(), c12_standin=c12_standin.mean(), n12=int(c12.sum()),
                   c12_planted_dir=(c12 & (sgn > 0)).mean())
        for cond, key in ((3, "ex2020"), (4, "adr"), (5, "dmin")):
            for fl in FLOORS[cond]:
                ok = sgn * lr[key] >= np.log(fl) - 1e-12
                rec[f"c{cond}@{fl:.2f}|12"] = (ok & c12).sum() / max(1, c12.sum())
                rec[f"c{cond}@{fl:.2f}|12standin"] = (ok & c12_standin).sum() / max(1, c12_standin.sum())
                rec[f"_ok{cond}@{fl:.2f}"] = ok
        rec["_c12"] = c12
        rec["_sgn"] = sgn
        out.append(rec)
    return info, out


if __name__ == "__main__":
    print("# STAGE 1 / 06 floor calibration on SYNTHETIC labels (prereg §6 step 2). No forward read; discovery rows of the feature table only.")
    print(f"prereg sha256 {C.sha(C.PREREG)} | feature_table.tsv.gz sha256 {C.sha(C.HERE / 'feature_table.tsv.gz')}")
    print(f"discovery events {N} (2016-19: {int((~is2020).sum())}, 2020: {int(is2020.sum())}); draws per feature per case {NDRAW}; permutation shuffles per draw {NSHUF} (exact hypergeometric form)")
    print(f"shelf relatives (condition 5 applies): {REL}; description-only features (cannot be carried): {[f for f in F.FEATS if 'DESCRIPTION' in DEC[f]]}")
    with Pool(8) as pool:
        res = pool.map(work, list(enumerate(F.FEATS)), chunksize=1)
    print("\n## layout per feature (discovery): events scored / in months with >= 6 (two-group: and >= 2 of each) / top / bottom / ex-2020 top / bottom / in ADR strata >= 9 / in dmin strata >= 9")
    for info, _ in res:
        print(f"  {info['feature']} {'two-group' if info['two_group'] else 'thirds   '} scored {info['scored']:5d} | months {info['months']:3d} events {info['in_months']:5d} | top {info['n_top']:4d} bottom {info['n_bot']:4d}"
              f" | ex-2020 top {info['n_top_ex2020']:4d} bottom {info['n_bot_ex2020']:4d} | ADR strata {info['adr_strata_events']:5d} | dmin strata {info['dmin_strata_events']:5d}")
    print("\n## ADDED after run 1 (no rule changed; the draws are seeded, so every number above and below is identical to run 1): the ratio a feature with NO effect")
    print("## is EXPECTED to show under the synthetic base rates (4.9% in 2016-19, 25% in 2020), from the composition of its groups alone. Thirds are balanced inside")
    print("## each month, so they sit near 1.00; a yes/no feature is NOT balanced inside a month, so its POOLED ratio moves with the 2020 share of each group.")
    for info, _ in res:
        print(f"  {info['feature']} {'two-group' if info['two_group'] else 'thirds   '} expected null ratio: all {info['null_all']:.3f} | ex-2020 {info['null_ex2020']:.3f} | ADR-neutral strata {info['null_adr']:.3f} | dmin strata {info['null_dmin']:.3f}"
              + ("   <-- outside 0.95-1.05" if not (0.95 <= info['null_all'] <= 1.05 and 0.95 <= info['null_adr'] <= 1.05) else ""))
    R = {(rec["feature"], rec["case"]): rec for _, out in res for rec in out}
    for cname, _ in CASES:
        print(f"\n## case {cname} — per feature: share of draws passing cond 1 | cond 1-2 (exact permutation) | cond 1-2 (stand-in) || given 1-2: cond 3 at 1.10 / 1.05 | cond 4 at 1.15 / 1.10 / 1.05 | cond 5 at 1.10 / 1.05")
        for f in F.FEATS:
            r = R[(f, cname)]
            print(f"  {f}{'*' if f in REL else ' '} c1 {r['c1']:.3f} | c1-2 {r['c12']:.3f} (n {r['n12']:4d}) | stand-in {r['c12_standin']:.3f} || c3 {r['c3@1.10|12']:.3f} / {r['c3@1.05|12']:.3f}"
                  f" | c4 {r['c4@1.15|12']:.3f} / {r['c4@1.10|12']:.3f} / {r['c4@1.05|12']:.3f} | c5 {r['c5@1.10|12']:.3f} / {r['c5@1.05|12']:.3f}")
    # ---- the floor rule (§5.2): planted TRUE 1.5x, pass rate given cond 1-2, MEDIAN over the features the floor applies to
    cand = [f for f in F.FEATS if "DESCRIPTION" not in DEC[f]]
    applies = {3: cand, 4: cand, 5: [f for f in REL if f in cand]}
    print("\n## THE FLOOR RULE (§5.2): planted true 1.5x; pass rate of a floor = share of draws passing conditions 1-2 that also pass it; MEDIAN over the features it applies to; under 80% -> lower by 0.05, never below 1.05")
    final = {}
    fired = {}
    for cond in (3, 4, 5):
        fs = applies[cond]
        if not fs:
            final[cond] = FLOORS[cond][0]; fired[cond] = False
            print(f"  condition {cond}: applies to no feature -> stays {FLOORS[cond][0]:.2f}")
            continue
        chosen = None
        for fl in FLOORS[cond]:
            med = float(np.median([R[(f, "k=1.5")][f"c{cond}@{fl:.2f}|12"] for f in fs]))
            med_s = float(np.median([R[(f, "k=1.5")][f"c{cond}@{fl:.2f}|12standin"] for f in fs]))
            lo = min(R[(f, "k=1.5")][f"c{cond}@{fl:.2f}|12"] for f in fs); hi = max(R[(f, "k=1.5")][f"c{cond}@{fl:.2f}|12"] for f in fs)
            print(f"  condition {cond} at {fl:.2f}: median pass rate {med:.3f} over {len(fs)} features (min {lo:.3f}, max {hi:.3f}); with the stand-in condition 2: {med_s:.3f}"
                  f" -> {'>= 0.80 OK' if med >= 0.80 else 'UNDER 0.80'}")
            if chosen is None and med >= 0.80:
                chosen = fl
        if chosen is None:
            chosen = FLOORS[cond][-1]
            print(f"  condition {cond}: 1.05 still under 80% -> stays 1.05 (STATED WEAKNESS)")
        final[cond] = chosen; fired[cond] = chosen != FLOORS[cond][0]
    print("\n## CALIBRATED FLOORS")
    names = {3: "ex-2020 ratio (2016-19 pooled)", 4: "ADR-neutral ratio", 5: "within-dmin-third ratio (shelf relatives only)"}
    for cond in (3, 4, 5):
        print(f"  condition {cond} {names[cond]}: frozen start {FLOORS[cond][0]:.2f} -> FINAL {final[cond]:.2f} (or <= {1 / final[cond]:.3f} the other way)"
              f" | mechanical lowering rule {'FIRED' if fired[cond] else 'did NOT fire'}")
    # ---- carry chain with the final floors, per case
    print("\n## carry chain per feature with the FINAL floors (share of the 2,000 draws): cond 1-2 | 1-3 | 1-4 | 1-5 (shelf relatives only; others = 1-4)")
    summ = []
    for cname, _ in CASES:
        print(f"  case {cname}")
        for f in F.FEATS:
            r = R[(f, cname)]
            c12 = r["_c12"]; c123 = c12 & r[f"_ok3@{final[3]:.2f}"]; c1234 = c123 & r[f"_ok4@{final[4]:.2f}"]
            c12345 = c1234 & r[f"_ok5@{final[5]:.2f}"] if f in REL else c1234
            c1234_init = c12 & r["_ok3@1.10"] & r["_ok4@1.15"]
            planted = (r["_sgn"] > 0)
            summ.append((cname, f, c12.mean(), c123.mean(), c1234.mean(), c12345.mean(), c1234_init.mean(), (c12345 & planted).mean()))
            print(f"    {f}{'*' if f in REL else ' '} {c12.mean():.3f} | {c123.mean():.3f} | {c1234.mean():.3f} | {c12345.mean():.3f}   (1-4 at the frozen starting floors {c1234_init.mean():.3f}; all conditions AND the planted direction {(c12345 & planted).mean():.3f})")
        g = [x for x in summ if x[0] == cname and x[1] in cand]
        print(f"    MEDIAN over the {len(g)} candidate features: 1-2 {np.median([x[2] for x in g]):.3f} | 1-3 {np.median([x[3] for x in g]):.3f} | 1-4 {np.median([x[4] for x in g]):.3f} | all {np.median([x[5] for x in g]):.3f}")
    print("\n## ADR-only label (a pure volatility effect, 2.0x by ADR20 third, independent of the feature): how often it gets a feature through conditions 1-4")
    for f in F.FEATS:
        x = [s for s in summ if s[0] == "ADR-only 2.0x" and s[1] == f][0]
        print(f"  {f} conditions 1-2 {x[2]:.3f} | 1-4 at the final floors {x[4]:.3f} | 1-4 at the frozen starting floors {x[6]:.3f}")
    pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in R.values()]).to_csv(C.HERE / "calibration_rates.tsv", sep="\t", index=False, float_format="%.4f")
    (C.HERE / "floors_final.txt").write_text(
        f"condition 3 (ex-2020) floor: {final[3]:.2f} (lowering rule fired: {fired[3]})\ncondition 4 (ADR-neutral) floor: {final[4]:.2f} (lowering rule fired: {fired[4]})\n"
        f"condition 5 (shelf relatives, within dmin thirds) floor: {final[5]:.2f} (lowering rule fired: {fired[5]})\nshelf relatives: {REL}\n"
        f"prereg sha256 at calibration: {C.sha(C.PREREG)}\nfeature_table sha256: {C.sha(C.HERE / 'feature_table.tsv.gz')}\n"
        "NOTE: the frozen prereg document was NOT edited by stage 1 (task scope); writing these floors into it and re-recording its sha256 is left to the caller.\n")
    print(f"\ncalibration_rates.tsv sha256 {C.sha(C.HERE / 'calibration_rates.tsv')} | floors_final.txt sha256 {C.sha(C.HERE / 'floors_final.txt')} | this script {C.sha(__file__)}")
