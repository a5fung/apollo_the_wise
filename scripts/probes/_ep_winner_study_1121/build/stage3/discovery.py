#!/usr/bin/env python3
"""EP big-winner chart study — STAGE 3: DISCOVERY OUTCOMES (prereg docs/analysis/ep_winner_study_prereg_2026-11-21.md §6 step 3,
§5.1-5.2, §5.6, §10 amendments A1-A3 which override earlier text).

FORWARD READ IS LIMITED TO DISCOVERY: forward bars are read ONLY for events with E <= 2020-12-31 (asserted per event), from the
era-A file only, and the bar store is cut at calendar index ci(2020-12-31)+60 before any outcome is computed (asserted). No era-B
bar, no confirm event (E >= 2021-01-01) outcome, no row after 2024-12-31 is touched. NOT opened: scripts/probes/_594_outcome_qm_1121/
build/events_scored.tsv.gz and run.txt (the four A3 lines are hardcoded below, copied from run.txt "per year" 2017-2020).

ORDER (frozen): header + applied readings -> layout asserts vs stage 1 -> A1 synthetic no-effect check (stop on a miss) ->
discovery outcomes -> A3 B1 reproduction (stop on a miss) -> §5.2 table -> carried list -> combination -> descriptions.

Modes: `python3 discovery.py` = THE REAL RUN (once).  `python3 discovery.py --synthetic` = same statistics path on coin-toss
labels, NO forward bar read, A3 skipped — used to debug the code before the single real run.
"""
from __future__ import annotations

import pickle
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STAGE1 = HERE.parent / "stage1"
sys.path.insert(0, str(STAGE1))
import common as C      # noqa: E402  (outcome-free: paths, calendars, sha; imports f3_def / encoder which are import-safe)
import features as F    # noqa: E402  (names, groups only)
import stats as S       # noqa: E402  (the SAME thirds / two-group assignment code the floors were calibrated on)

SYN = "--synthetic" in sys.argv
NS = 10_000                  # §5.1 permutation shuffles
NBOOT = 2_000                # §5.1 bootstrap draws
FWD = 60
BIG, MON, ADRK, FAILPOOL = 1.5, 2.0, 8.0, 1.10
FLOOR = {1: 1.25, 3: 1.10, 4: 1.15, 5: 1.10}
A3_EXPECT = {  # scripts/probes/_594_outcome_qm_1121/build/run.txt, block "per year:", rows 2017-2020 (RESULT 8), verbatim
    "2017": "    2017 era A: n  337  bottom 0.043  top 0.056  ratio 1.30",
    "2018": "    2018 era A: n  419  bottom 0.021  top 0.037  ratio 1.78",
    "2019": "    2019 era A: n  442  bottom 0.039  top 0.063  ratio 1.61",
    "2020": "    2020 era A: n  706  bottom 0.192  top 0.303  ratio 1.57",
}
FT_SHA = "ade1d7802eaf70aa60a9b5514d79b72084876d9601b0999328c9b1aad0cf0de7"


def stop(msg):
    print(f"\n*** STOP: {msg}")
    sys.stdout.flush()
    sys.exit(3)


# ════════════════════════════════════════ header (outcome-free) ════════════════════════════════════════
print("# STAGE 3 — DISCOVERY OUTCOMES" + ("   [SYNTHETIC MODE: coin-toss labels, NO forward bar read — NOT a result]" if SYN else ""))
print(f"prereg sha256 (current, with §10) {C.sha(C.PREREG)}")
ft_sha = C.sha(STAGE1 / "feature_table.tsv.gz")
print(f"feature_table.tsv.gz sha256 {ft_sha}")
assert ft_sha == FT_SHA, "feature table is not the stage-1 table"
fl = (STAGE1 / "floors_final.txt").read_text()
assert "condition 3 (ex-2020) floor: 1.10" in fl and "condition 4 (ADR-neutral) floor: 1.15" in fl and "within dmin thirds) floor: 1.10" in fl
print(f"floors (§10): condition 3 {FLOOR[3]:.2f} · condition 4 {FLOOR[4]:.2f} · condition 5 {FLOOR[5]:.2f} (ASSERT OK vs floors_final.txt)")
print(f"code sha256: this script {C.sha(__file__)} | stage1 stats.py {C.sha(STAGE1 / 'stats.py')} | common.py {C.sha(STAGE1 / 'common.py')}")
print("""
## APPLIED READINGS (fixed here, BEFORE any outcome is computed)
 R1  Assignment code = stage1/stats.py (imported); thirds / strata layouts copied from stage1/06_calibration.py::layout and
     asserted equal to its printed "layout per feature" counts.
 R2  Every bar (conditions 1, 3, 4, 5) is judged as the calibration did: sign x log(ratio) >= log(floor), where the ratio of a
     thirds feature uses smoothed rates (winners + 0.5) / (n + 1) (§5.1); the raw ratio is printed beside it.
 R3  Two-group features (f15, f16): Mantel-Haenszel risk ratio (A1) = sum_i(a_i * n0_i / N_i) / sum_i(c_i * n1_i / N_i), i = the
     unit the yes/no groups were formed in: (era, month) for the main / ex-2020 / common-set readings; (era, quarter, ADR third)
     for condition 4; (era, quarter, dmin third) for condition 5. A zero numerator or denominator on a bar reading stops the run.
     (A1's text names months only; MH over the ADR / dmin strata for conditions 4-5 is this script's reading.)
 R4  Permutation (§5.1): U = np.random.default_rng(1121).random((10000, 2414)); row = shuffle, column = discovery event in the
     fixed order (era, E, ticker). Within each (era, month) the events assigned on the feature are sorted by key; the k-th event in
     key order receives the label of the k-th event in fixed order. Own p two-sided on |log ratio|: (1 + #(|perm| >= |obs|)) / 10001.
 R5  Condition 6, literal: candidates = all 20 features (none is description-only). Group winner = largest z among ALL members of
     the group, on the discovery events scored on every member (thirds re-formed within month on that common set, months >= 6
     events; z = |log ratio| / SD of the 10,000 permuted log ratios there). Cap = the four largest z among the nine group winners,
     each recomputed the same way on the events scored on ALL 20 features. Ties -> smaller own p -> lower feature number.
     A feature is CARRIED only if it passes 1-5 AND is its group's winner AND is in the four.
 R6  Family-wide p (description): on the all-20 common set, share of shuffles whose largest |log ratio| over the 20 features
     is >= this feature's |log ratio| there, (1 + count) / 10001.
 R7  90% interval: (era, month) blocks resampled with replacement, 2,000 draws, a fresh default_rng(1121) per feature.
 R8  Outcome window: bars with era-A calendar index in [ci(E), ci(E)+60]; big winner = max close >= 1.5 x open(E); monster
     >= 2.0 x; ADR tail >= open(E) x (1 + 8 x ADR20 / 100), ADR20 = the table's adr20_raw; no survivorship drop.
 R9  B1 keeps PRE-REG 6's ticker tie-break (midrank=False); B2 and the 20 features use mid-rank ties.
 R10 §5.5 window-length +/-50% and the other extra readings are left to the confirm step (step 8); per-year, monster, ADR-tail
     and failure descriptions are printed here.""")

# ════════════════════════════════════════ feature table, layouts (outcome-free) ════════════════════════════════════════
T = pd.read_csv(STAGE1 / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "year": str})
D = T[T.set == "DISC"].reset_index(drop=True)
del T                                                     # confirm rows of the (outcome-free) table are not used here
assert len(D) == 2414 and (D.era == "A").all() and D.E.max() <= C.DISC_LAST
assert list(zip(D.E, D.ticker)) == sorted(zip(D.E, D.ticker)), "fixed order (era, E, ticker)"
N = len(D)
POP = pd.read_csv(STAGE1 / "population.tsv", sep="\t", keep_default_na=False, dtype={"ticker": str, "E": str})
POP = POP[POP.set == "DISC"].reset_index(drop=True)
assert (POP.ticker.to_numpy() == D.ticker.to_numpy()).all() and (POP.E.to_numpy() == D.E.to_numpy()).all()
is2020 = (D.year == "2020").to_numpy()
YEAR = D.year.to_numpy()
DEC = pd.read_csv(STAGE1 / "feature_decisions.tsv", sep="\t").set_index("feature").decision.to_dict()
REL = [x for x in (STAGE1 / "shelf_relatives.txt").read_text().split() if x]
assert REL == ["f05", "f07"]
FEATS = list(F.FEATS)
TWO = {f: DEC[f].startswith("two-group") for f in FEATS}
assert [f for f in FEATS if TWO[f]] == ["f15", "f16"] and not any("DESCRIPTION" in DEC[f] for f in FEATS)
GROUP_OF = {f: g for g, fs in F.GROUPS.items() for f in fs}
assert sorted(GROUP_OF) == sorted(FEATS)
D["adr_third"] = S.assign_thirds(D, "adr20_raw", ["era", "quarter"], 1, midrank=True)        # 06_calibration.py line "strata labels"
assert (D.adr_third >= 0).all()
D["dmin_third"] = S.assign_thirds(D, "B1", ["era", "quarter"], 1, midrank=True)
G2 = {f: np.where(D[f].isna(), -1, D[f].fillna(0)).astype(int) for f in FEATS if TWO[f]}
U_MONTH = pd.factorize(D.era + D.month)[0]
U_ADR = pd.factorize(D.era + D.quarter + "|" + D.adr_third.astype(str))[0]
U_DMIN = pd.factorize(D.era + D.quarter + "|" + D.dmin_third.astype(str))[0]
ALLTRUE = np.ones(N, bool)


def month_assign(col, mask, two=False, midrank=True):
    """thirds (or yes/no) within (era, month) formed on the events in `mask` only; -1 elsewhere."""
    sub = D[mask].reset_index(drop=True)
    if two:
        ts = S.assign_two(sub, G2[col][mask], ["era", "month"], min_n=S.MIN_MONTH)
    else:
        ts = S.assign_thirds(sub, col, ["era", "month"], S.MIN_MONTH, midrank)
    out = np.full(N, -1, dtype=np.int8)
    out[np.flatnonzero(mask)] = ts
    return out


def strata_assign(col, kind, two=False, midrank=True):
    """06_calibration.py::layout — thirds of the feature within (era, quarter, ADR20 third) / (era, quarter, dmin third), strata >= 9."""
    key = "adr_third" if kind == "adr" else "dmin_third"
    if two:
        g = G2[col] if kind == "adr" else np.where(D.dmin_third >= 0, G2[col], -1)
        return S.assign_two(D, g, ["era", "quarter", key], min_n=S.MIN_STRATUM)
    Dd = D
    if kind == "dmin":
        Dd = D.copy()
        Dd.loc[Dd.dmin_third < 0, col] = np.nan
    return S.assign_thirds(Dd, col, ["era", "quarter", key], S.MIN_STRATUM, midrank)


LAY = {}
for f in FEATS:
    LAY[f] = dict(tm=month_assign(f, ALLTRUE, TWO[f]), ta=strata_assign(f, "adr", TWO[f]), td=strata_assign(f, "dmin", TWO[f]))
LAY["B1"] = dict(tm=month_assign("B1", ALLTRUE, midrank=False), ta=strata_assign("B1", "adr", midrank=False), td=None)
LAY["B1clean"] = dict(tm=month_assign("B1clean", ALLTRUE, midrank=False), ta=strata_assign("B1clean", "adr", midrank=False), td=None)
LAY["B2"] = dict(tm=month_assign("B2", ALLTRUE), ta=None, td=None)

# assert vs stage 1's printed layout
cal_txt = (STAGE1 / "06_calibration.txt").read_text()
pat = re.compile(r"^\s+(f\d\d) (thirds|two-group)\s+scored\s+(\d+) \| months\s+(\d+) events\s+(\d+) \| top\s+(\d+) bottom\s+(\d+) \| ex-2020 top\s+(\d+) bottom\s+(\d+) \| ADR strata\s+(\d+) \| dmin strata\s+(\d+)", re.M)
seen = {}
for m in pat.finditer(cal_txt):
    seen[m.group(1)] = tuple(int(x) for x in m.groups()[2:])
assert sorted(seen) == sorted(FEATS), sorted(seen)
for f in FEATS:
    tm, ta, td = LAY[f]["tm"], LAY[f]["ta"], LAY[f]["td"]
    mine = (int(D[f].notna().sum()), len(set(U_MONTH[tm >= 0])), int((tm >= 0).sum()), int((tm == 2).sum()), int((tm == 0).sum()),
            int(((tm == 2) & ~is2020).sum()), int(((tm == 0) & ~is2020).sum()), int((ta >= 0).sum()), int((td >= 0).sum()))
    assert mine == seen[f], (f, mine, seen[f])
print("\nlayout per feature (months, top, bottom, ex-2020 top / bottom, ADR strata, dmin strata) equals stage 1's 06_calibration.txt on all 20 features (ASSERT OK)")
COMMON_ALL = np.ones(N, bool)
for f in FEATS:
    COMMON_ALL &= D[f].notna().to_numpy()
GROUP_SET = {}
for g, fs in F.GROUPS.items():
    m = np.ones(N, bool)
    for f in fs:
        m &= D[f].notna().to_numpy()
    GROUP_SET[g] = m
print(f"common sets (outcome-free): scored on ALL 20 features: {int(COMMON_ALL.sum())} events; per group: "
      + " · ".join(f"{g} {int(m.sum())}" for g, m in GROUP_SET.items()))


# ════════════════════════════════════════ statistics ════════════════════════════════════════
def sm(w, n):
    return (w + 0.5) / (n + 1.0)


def stat(y, t, unit, two, mask=None, strict=False):
    """ratio of the top / yes group vs the bottom / no group. thirds: pooled rates (raw + smoothed log); two-group: MH over `unit`."""
    ok = np.isfinite(y) & (t >= 0)
    if mask is not None:
        ok &= mask
    top, bot, mid = ok & (t == 2), ok & (t == 0), ok & (t == 1)
    nt, nb, nm = int(top.sum()), int(bot.sum()), int(mid.sum())
    wt, wb, wm = float(y[top].sum()), float(y[bot].sum()), float(y[mid].sum())
    r = dict(nt=nt, nb=nb, nm=nm, wt=wt, wb=wb, wm=wm, rt=wt / nt if nt else np.nan, rb=wb / nb if nb else np.nan, rm=wm / nm if nm else np.nan)
    r["pooled"] = (r["rt"] / r["rb"]) if (nb and wb > 0) else (np.inf if wt > 0 else np.nan)
    if two:
        K = int(unit.max()) + 1
        n1 = np.bincount(unit[top], minlength=K).astype(float); n0 = np.bincount(unit[bot], minlength=K).astype(float)
        a = np.bincount(unit[top], weights=y[top], minlength=K); c = np.bincount(unit[bot], weights=y[bot], minlength=K)
        Nn = n1 + n0
        v = Nn > 0
        num = float((a[v] * n0[v] / Nn[v]).sum()); den = float((c[v] * n1[v] / Nn[v]).sum())
        if num <= 0 or den <= 0:
            if strict:
                stop(f"Mantel-Haenszel numerator / denominator is zero on a bar reading (num {num}, den {den}) — no smoothing is invented")
            r["raw"] = np.inf if den <= 0 < num else (0.0 if num <= 0 < den else np.nan); r["lr"] = np.nan
        else:
            r["raw"] = num / den; r["lr"] = float(np.log(num / den))
        r["comp"] = (a * n0 / np.where(v, Nn, 1), c * n1 / np.where(v, Nn, 1))
    else:
        r["raw"] = r["pooled"]
        r["lr"] = float(np.log(sm(wt, nt) / sm(wb, nb))) if nt and nb else np.nan
    return r


def perm_lr(y, t, two):
    """§5.1 / R4: the 10,000 permuted log ratios (labels permuted within (era, month) among the assigned events)."""
    asg = t >= 0
    if two:
        NUM = np.zeros(NS); DEN = np.zeros(NS)
    else:
        WT = np.zeros(NS); WB = np.zeros(NS)
    for u in np.unique(U_MONTH[asg]):
        idx = np.flatnonzero(asg & (U_MONTH == u))            # ascending = fixed order
        wpos = np.flatnonzero(y[idx] == 1)
        if two:
            n1 = int((t[idx] == 2).sum()); n0 = int((t[idx] == 0).sum())
        if len(wpos) == 0:
            continue
        A = np.argsort(UKEY[:, idx], axis=1, kind="stable")[:, wpos]      # events receiving the winner labels
        tt = t[idx][A]
        a = (tt == 2).sum(1); c = (tt == 0).sum(1)
        if two:
            NUM += a * n0 / (n1 + n0); DEN += c * n1 / (n1 + n0)
        else:
            WT += a; WB += c
    if two:
        if (NUM <= 0).any() or (DEN <= 0).any():
            stop("a permuted Mantel-Haenszel numerator / denominator is zero — no smoothing is invented")
        return np.log(NUM / DEN)
    return np.log(sm(WT, int((t == 2).sum())) / sm(WB, int((t == 0).sum())))


def boot_ci(y, t, two, seed=C.SEED):
    asg = t >= 0
    us = np.unique(U_MONTH[asg])
    K = len(us)
    comp = np.zeros((K, 4))
    for k, u in enumerate(us):
        m = asg & (U_MONTH == u)
        top, bot = m & (t == 2), m & (t == 0)
        if two:
            n1, n0 = top.sum(), bot.sum()
            comp[k] = (y[top].sum() * n0 / (n1 + n0), 0, y[bot].sum() * n1 / (n1 + n0), 0)
        else:
            comp[k] = (y[top].sum(), top.sum(), y[bot].sum(), bot.sum())
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, K, size=(NBOOT, K))
    s = comp[draw].sum(1)                                     # (NBOOT, 4)
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = s[:, 0] / s[:, 2] if two else sm(s[:, 0], s[:, 1]) / sm(s[:, 2], s[:, 3])
    rr = rr[np.isfinite(rr)]
    return float(np.percentile(rr, 5)), float(np.percentile(rr, 95))


def fmt_r(x):
    return "inf" if np.isinf(x) else ("nan" if np.isnan(x) else f"{x:.2f}")


# ════════════════════════════════════════ A1: synthetic no-effect check for every MH reading used ════════════════════════════════════════
print("\n## A1 — synthetic NO-EFFECT labels (4.9% in 2016-19, 25% in 2020; 2,000 draws; no forward read): the Mantel-Haenszel ratio must centre near 1.0")
print("   pass band fixed before running: median MH ratio within 0.95-1.05 on every reading; a miss stops the run. The pooled yes/no ratio is printed beside it (it is the biased one).")
p_event = np.where(is2020, 0.25, 0.049)
A1_SETS = {}
for fi, f in enumerate(["f15", "f16"]):
    rng = np.random.default_rng([C.SEED, 3, fi])
    L = (rng.random((2000, N)) < p_event[None, :]).astype(float)
    readings = [("months (main)", LAY[f]["tm"], U_MONTH, None), ("months, ex-2020", LAY[f]["tm"], U_MONTH, ~is2020),
                ("ADR strata (cond 4)", LAY[f]["ta"], U_ADR, None), ("dmin strata", LAY[f]["td"], U_DMIN, None),
                ("group common set (structure)", month_assign(f, GROUP_SET["structure"], True), U_MONTH, None),
                ("all-20 common set", month_assign(f, COMMON_ALL, True), U_MONTH, None)]
    for nm, t, unit, mask in readings:
        ok = (t >= 0) if mask is None else ((t >= 0) & mask)
        top, bot = ok & (t == 2), ok & (t == 0)
        NUM = np.zeros(2000); DEN = np.zeros(2000)
        for u in np.unique(unit[ok]):
            mt, mb = top & (unit == u), bot & (unit == u)
            n1, n0 = mt.sum(), mb.sum()
            if n1 + n0 == 0:
                continue
            NUM += L[:, mt].sum(1) * n0 / (n1 + n0); DEN += L[:, mb].sum(1) * n1 / (n1 + n0)
        mh = NUM / DEN
        pooled = (L[:, top].sum(1) / top.sum()) / (L[:, bot].sum(1) / bot.sum())
        med = float(np.median(mh))
        okb = 0.95 <= med <= 1.05
        print(f"   {f} {nm:30s} yes {int(top.sum()):4d} / no {int(bot.sum()):4d} | MH ratio median {med:.3f} mean {mh.mean():.3f} (5th-95th {np.percentile(mh, 5):.2f}-{np.percentile(mh, 95):.2f})"
              f" | pooled ratio median {np.median(pooled):.3f} -> {'OK' if okb else 'MISS'}")
        if not okb:
            stop(f"A1: MH ratio of {f} on '{nm}' does not centre near 1.0 on no-effect labels (median {med:.3f})")
    del L
print("   A1 PASSED: every Mantel-Haenszel reading of f15 and f16 centres within 0.95-1.05 on no-effect labels.")

# ════════════════════════════════════════ OUTCOMES — discovery only ════════════════════════════════════════
print("\n" + "=" * 118)
cal = C.calendars()["A"]
if SYN:
    print("## SYNTHETIC LABELS (no forward bar read). Planted 2.0x on f04, f10, f14, f15 to exercise the carry path.")
    rng = np.random.default_rng(7)
    rate = p_event.copy()
    for f in ("f04", "f10", "f14", "f15"):
        tmf = LAY[f]["tm"]
        rate = rate * np.where(tmf == 2, 4 / 3, np.where(tmf == 0, 2 / 3, 1.0))
    big = (rng.random(N) < rate).astype(float)
    monster = big * (rng.random(N) < 0.35)
    adrt = (rng.random(N) < 0.08).astype(float)
    fail5 = (rng.random(N) < 0.5).astype(float); ret60 = rng.normal(0, 0.3, N); failpool = (rng.random(N) < 0.4).astype(float); maxc = 1 + rng.random(N)
    nbars = np.full(N, 61)
else:
    print("## DISCOVERY OUTCOMES — forward bars read ONLY for E <= 2020-12-31 (era A file)")
    ci_disc_last = int(np.searchsorted(cal, C.DISC_LAST))
    assert cal[ci_disc_last] == C.DISC_LAST
    CI_MAX = ci_disc_last + FWD
    assert CI_MAX < len(cal)
    bars_all = pickle.load(open(STAGE1 / "cache" / "bars_event_tickers.pkl", "rb"))
    need = set(D.ticker)
    bars = {}
    for (era, t), b in bars_all.items():
        if era != "A" or t not in need:
            continue                                           # every era-B series and every non-discovery ticker is dropped unread
        d, ci, o, h, l, c, v = b
        k = int(np.searchsorted(ci, CI_MAX, side="right"))
        bars[t] = (d[:k], ci[:k], o[:k], c[:k])                # only date, calendar index, open, close; cut at ci(2020-12-31)+60
    n_all = len(bars_all)
    del bars_all
    mxd = max(b[0][-1] for b in bars.values())
    assert mxd <= cal[CI_MAX], (mxd, cal[CI_MAX])
    print(f"   bar store: {n_all} cached series -> kept {len(bars)} era-A discovery tickers, cut at calendar index {CI_MAX} = {cal[CI_MAX]}"
          f" (= ci({C.DISC_LAST}) + {FWD}); latest bar retained {mxd} (ASSERT <= {cal[CI_MAX]}); no era-B series retained")
    big = np.zeros(N); monster = np.zeros(N); adrt = np.full(N, np.nan); fail5 = np.full(N, np.nan); ret60 = np.full(N, np.nan)
    failpool = np.zeros(N); maxc = np.zeros(N); nbars = np.zeros(N, int)
    adr = D.adr20_raw.to_numpy(dtype=float)
    for k in range(N):
        t, E = D.ticker.iat[k], D.E.iat[k]
        assert E <= C.DISC_LAST and D.era.iat[k] == "A", (t, E)          # CONFIRM OUTCOMES ARE NEVER READ
        d, ci, o, c = bars[t]
        iE = int(np.searchsorted(cal, E)); assert cal[iE] == E and iE == int(POP.iE.iat[k])
        i = int(np.searchsorted(ci, iE)); assert ci[i] == iE and d[i] == E
        oE = float(o[i])
        assert abs(oE - float(POP.open.iat[k])) <= 1e-5 * abs(oE) + 1e-6, (t, E, oE, POP.open.iat[k])
        j = int(np.searchsorted(ci, iE + FWD, side="right"))
        assert j > i and ci[j - 1] <= iE + FWD and iE + FWD <= CI_MAX
        w = c[i:j]; wci = ci[i:j]
        mx = float(w.max())
        maxc[k] = mx / oE; nbars[k] = j - i
        big[k] = 1.0 if mx >= BIG * oE else 0.0
        monster[k] = 1.0 if mx >= MON * oE else 0.0
        failpool[k] = 1.0 if mx < FAILPOOL * oE else 0.0
        if np.isfinite(adr[k]) and adr[k] > 0:
            adrt[k] = 1.0 if mx >= oE * (1 + ADRK * adr[k] / 100.0) else 0.0
        p5 = np.flatnonzero(wci == iE + 5); p60 = np.flatnonzero(wci == iE + FWD)
        if len(p5):
            fail5[k] = 1.0 if w[p5[0]] < oE else 0.0
        if len(p60):
            ret60[k] = w[p60[0]] / oE - 1.0
    out = D[["era", "ticker", "E", "year", "month"]].copy()
    out["maxc_ratio"] = maxc; out["big_winner"] = big.astype(int); out["monster"] = monster.astype(int); out["adr_tail"] = adrt
    out["fail5"] = fail5; out["ret60"] = ret60; out["fail_pool"] = failpool.astype(int); out["fwd_bars"] = nbars
    assert (out.E <= C.DISC_LAST).all() and len(out) == 2414
    OUT = HERE / "discovery_outcomes.tsv.gz"
    out.to_csv(OUT, sep="\t", index=False, float_format="%.8g", compression={"method": "gzip", "mtime": 0})
    print(f"   outcomes computed for {N} events, max E {D.E.max()} (ASSERT every E <= {C.DISC_LAST}); wrote {OUT.name} (discovery rows only), sha256 {C.sha(OUT)}")
    print(f"   events with fewer than 61 bars in E..E+60 (kept, no survivorship drop): {int((nbars < 61).sum())}; no bar at E+5: {int(np.isnan(fail5).sum())}; no bar at E+60: {int(np.isnan(ret60).sum())}")

print("\n## base rates (discovery): events | big winners (>= 1.5x) | monsters (>= 2.0x) | ADR-scaled tail | failure pool (max close < 1.10x) | close(E+5) < open | mean 60-session return")
for y in sorted(set(YEAR)) + ["ALL", "2016-19"]:
    m = ALLTRUE if y == "ALL" else (~is2020 if y == "2016-19" else YEAR == y)
    print(f"   {y:8s} n {int(m.sum()):4d} | big {int(big[m].sum()):3d} ({big[m].mean():.3f}) | monster {int(monster[m].sum()):3d} ({monster[m].mean():.3f}) | ADR tail {int(np.nansum(adrt[m])):3d} ({np.nanmean(adrt[m]):.3f})"
          f" | fail pool {int(failpool[m].sum()):4d} ({failpool[m].mean():.3f}) | fail5 {np.nanmean(fail5[m]):.3f} | ret60 mean {np.nanmean(ret60[m]):+.3f}")

# ════════════════════════════════════════ A3: B1 reproduction (stop on a miss) ════════════════════════════════════════
print("\n## A3 — B1 (shelf distance) reproduces RESULT 8's discovery-year rows (run.txt 'per year' 2017-2020) BEFORE any new-feature statistic")
tb = LAY["B1"]["tm"]
miss = 0
for y in ("2017", "2018", "2019", "2020"):
    g = (YEAR == y) & (tb >= 0)
    t_, b_ = big[g & (tb == 2)].mean(), big[g & (tb == 0)].mean()
    line = f"    {y} era A: n {int(g.sum()):4d}  bottom {b_:.3f}  top {t_:.3f}  ratio {(t_ / b_ if b_ > 0 else float('inf')):.2f}"
    same = line == A3_EXPECT[y]
    miss += not same
    print(f"   here     {line}\n   RESULT 8 {A3_EXPECT[y]}   -> {'MATCH' if same else 'MISS'}")
if SYN:
    print("   (synthetic mode: A3 cannot match and is not enforced)")
elif miss:
    stop(f"A3: B1 reproduction missed on {miss} of 4 discovery-year rows — no new-feature verdict is printed")
else:
    print("   A3 PASSED: all four rows reproduce exactly (n, bottom rate, top rate, ratio).")

# ════════════════════════════════════════ §5.2 — the six conditions ════════════════════════════════════════
UKEY = np.random.default_rng(C.SEED).random((NS, N))


def full_read(col, two, lay, name, group=None):
    tm, ta, td = lay["tm"], lay["ta"], lay["td"]
    r = dict(col=col, two=two, name=name)
    own = stat(big, tm, U_MONTH, two, strict=True)
    pl = perm_lr(big, tm, two)
    r.update(own=own, lr=own["lr"], p=(1 + int((np.abs(pl) >= abs(own["lr"]) - 1e-12).sum())) / (NS + 1), sd=float(pl.std()),
             null95=(float(np.exp(np.percentile(pl, 2.5))), float(np.exp(np.percentile(pl, 97.5)))))
    r["dir"] = 1 if own["lr"] > 0 else -1
    r["ci"] = boot_ci(big, tm, two)
    r["ex"] = stat(big, tm, U_MONTH, two, mask=~is2020, strict=True)
    r["only2020"] = stat(big, tm, U_MONTH, two, mask=is2020)
    r["adr"] = stat(big, ta, U_ADR, two, strict=True) if ta is not None else None
    r["dmin"] = stat(big, td, U_DMIN, two, strict=(col in REL)) if td is not None else None
    r["mon"] = stat(monster, tm, U_MONTH, two)
    r["n_mon"] = int(monster[tm >= 0].sum())
    r["adrt"] = stat(adrt, tm, U_MONTH, two)
    r["fail5"] = (np.nanmean(fail5[tm == 0]), np.nanmean(fail5[tm == 2])); r["ret60"] = (np.nanmean(ret60[tm == 0]), np.nanmean(ret60[tm == 2]))
    r["years"] = {y: stat(big, tm, U_MONTH, two, mask=(YEAR == y)) for y in sorted(set(YEAR))}
    return r


R = {f: full_read(f, TWO[f], LAY[f], F.NAMES[f]) for f in FEATS}
BEN = {b: full_read(b, False, LAY[b], F.NAMES[b]) for b in ("B1", "B1clean", "B2")}

# common-set strength z
def z_on(f, mask):
    t = month_assign(f, mask, TWO[f])
    s = stat(big, t, U_MONTH, TWO[f], strict=True)
    pl = perm_lr(big, t, TWO[f])
    return dict(lr=s["lr"], raw=s["raw"], sd=float(pl.std()), z=abs(s["lr"]) / float(pl.std()), n=int((t >= 0).sum()), pl=pl)


ZG = {f: z_on(f, GROUP_SET[GROUP_OF[f]]) for f in FEATS}
ZA = {f: z_on(f, COMMON_ALL) for f in FEATS}
mx = np.max(np.abs(np.vstack([ZA[f]["pl"] for f in FEATS])), axis=0)
for f in FEATS:
    R[f]["pfam"] = (1 + int((mx >= abs(ZA[f]["lr"]) - 1e-12).sum())) / (NS + 1)
    ZG[f].pop("pl"); ZA[f].pop("pl")


def rank_key(f, Z):
    return (-Z[f]["z"], R[f]["p"], int(f[1:]))


WIN = {g: sorted(fs, key=lambda f: rank_key(f, ZG))[0] for g, fs in F.GROUPS.items()}
winners = list(WIN.values())
order4 = sorted(winners, key=lambda f: rank_key(f, ZA))
TOP4 = order4[:4]


def passes(lrx, d, floor):
    return bool(np.isfinite(lrx) and d * lrx >= np.log(floor) - 1e-12)


for f in FEATS:
    r = R[f]
    d = r["dir"]
    r["c1"] = passes(r["lr"], d, FLOOR[1])
    r["c2"] = r["p"] <= 0.05
    r["c3"] = passes(r["ex"]["lr"], d, FLOOR[3])
    r["c4"] = passes(r["adr"]["lr"], d, FLOOR[4])
    r["c5"] = passes(r["dmin"]["lr"], d, FLOOR[5]) if f in REL else None
    r["gw"] = WIN[GROUP_OF[f]] == f
    r["in4"] = f in TOP4
    r["c6"] = r["gw"] and r["in4"]
    r["c15"] = r["c1"] and r["c2"] and r["c3"] and r["c4"] and (r["c5"] is not False)
    r["carried"] = r["c15"] and r["c6"]


def dirword(r):
    if r["two"]:
        return "YES group wins" if r["dir"] > 0 else "NO group wins"
    return "HIGH third wins" if r["dir"] > 0 else "LOW third wins"


def e(lr):
    return "nan" if not np.isfinite(lr) else f"{np.exp(lr):.3f}"


def block(r, cond=True):
    f = r["col"]; o = r["own"]; two = r["two"]
    tag = "  [shelf relative — confirm partly seen]" if f in REL else ""
    print(f"\n{f} — {r['name']}" + (f" | group: {GROUP_OF[f]}" if f in GROUP_OF else (" | COMBINATION" if f == "combo" else " | BENCHMARK (not a candidate)")) + (" | two-group, Mantel-Haenszel by month (A1)" if two else " | thirds") + tag)
    if two:
        print(f"   big winner: NO {int(o['wb'])}/{o['nb']} = {o['rb']:.3f} | YES {int(o['wt'])}/{o['nt']} = {o['rt']:.3f} | MH ratio yes/no {r['own']['raw']:.3f} (pooled, biased: {fmt_r(o['pooled'])}) -> {dirword(r)}")
    else:
        print(f"   big winner: bottom {int(o['wb'])}/{o['nb']} = {o['rb']:.3f} | middle {int(o['wm'])}/{o['nm']} = {o['rm']:.3f} | top {int(o['wt'])}/{o['nt']} = {o['rt']:.3f} | ratio top/bottom raw {o['raw']:.3f}, smoothed {e(r['lr'])} -> {dirword(r)}")
    near = "  <-- NEAR THE BAR (0.04-0.06): a recount's shuffle convention can move it ~0.005" if 0.04 <= r["p"] <= 0.06 else ""
    print(f"   permutation p (two-sided, 10,000) {r['p']:.4f}{near} | null 95% band of the ratio {r['null95'][0]:.2f}-{r['null95'][1]:.2f} | 90% bootstrap interval {r['ci'][0]:.2f}-{r['ci'][1]:.2f}"
          + (f" | family-wide p (all-20 set, description) {r['pfam']:.4f}" if "pfam" in r else ""))
    x = r["ex"]; y20 = r["only2020"]
    print(f"   ex-2020 (2016-19): bottom {int(x['wb'])}/{x['nb']} top {int(x['wt'])}/{x['nt']} ratio raw {fmt_r(x['raw'])}, judged {e(x['lr'])} | 2020 only: bottom {int(y20['wb'])}/{y20['nb']} top {int(y20['wt'])}/{y20['nt']} ratio {fmt_r(y20['raw'])}")
    if r["adr"] is not None:
        a = r["adr"]
        print(f"   ADR-neutral (thirds within era-quarter-ADR third): bottom {int(a['wb'])}/{a['nb']} top {int(a['wt'])}/{a['nt']} ratio raw {fmt_r(a['raw'])}, judged {e(a['lr'])}")
    if r["dmin"] is not None:
        dm = r["dmin"]
        print(f"   within shelf-distance thirds{' (CONDITION 5 applies)' if f in REL else ' (description; not a shelf relative)'}: bottom {int(dm['wb'])}/{dm['nb']} top {int(dm['wt'])}/{dm['nt']} ratio raw {fmt_r(dm['raw'])}, judged {e(dm['lr'])}")
    mo = r["mon"]; at = r["adrt"]
    print(f"   MONSTER tier (>= 2.0x; never a bar): bottom {int(mo['wb'])}/{mo['nb']} top {int(mo['wt'])}/{mo['nt']} ratio {fmt_r(mo['raw'])}{'  [thin: ' + str(r['n_mon']) + ' monsters in the set under test, < 60]' if r['n_mon'] < 60 else '  [' + str(r['n_mon']) + ' monsters]'}"
          f" | ADR-SCALED TAIL (never a carry bar): bottom {int(at['wb'])}/{at['nb']} top {int(at['wt'])}/{at['nt']} ratio {fmt_r(at['raw'])}")
    print(f"   failed (description): close(E+5) < open — bottom {r['fail5'][0]:.3f} top {r['fail5'][1]:.3f} | mean 60-session return — bottom {r['ret60'][0]:+.3f} top {r['ret60'][1]:+.3f}")
    print("   per year (top/bottom ratio, winners top:bottom): " + " · ".join(f"{y} {fmt_r(s['raw'])} ({int(s['wt'])}:{int(s['wb'])})" for y, s in r["years"].items() if s["nt"] and s["nb"]))
    if not cond:
        return
    d = r["dir"]
    yn = lambda b: "PASS" if b else "FAIL"
    g = GROUP_OF[f]
    print(f"   CONDITIONS: 1 ratio >= 1.25 or <= 0.80: {e(r['lr'])} {yn(r['c1'])} | 2 p <= 0.05: {r['p']:.4f} {yn(r['c2'])} | 3 ex-2020 >= 1.10 same direction: {e(d * r['ex']['lr'])} {yn(r['c3'])}"
          f" | 4 ADR-neutral >= 1.15 same direction: {e(d * r['adr']['lr'])} {yn(r['c4'])} | 5 " + ("n/a (not a shelf relative)" if r["c5"] is None else f"within shelf thirds >= 1.10 same direction: {e(d * r['dmin']['lr'])} {yn(r['c5'])}"))
    print(f"               6 group '{g}' common set n {ZG[f]['n']}: ratio {fmt_r(ZG[f]['raw'])} z {ZG[f]['z']:.2f} -> group winner {WIN[g]} ({'this feature' if r['gw'] else 'not this feature'})"
          f" | all-20 set n {ZA[f]['n']}: ratio {fmt_r(ZA[f]['raw'])} z {ZA[f]['z']:.2f}" + (f" -> rank {order4.index(f) + 1} of {len(order4)} group winners ({'in' if r['in4'] else 'outside'} the cap of four)" if r["gw"] else "") + f" : {yn(r['c6'])}")
    fails = [str(k) for k, key in ((1, "c1"), (2, "c2"), (3, "c3"), (4, "c4"), (5, "c5"), (6, "c6")) if r[key] is False]
    print(f"   VERDICT: {f} {r['name']} — " + (f"CARRIED to confirm, direction frozen: {dirword(r)}{tag}" if r["carried"] else f"NOT CARRIED (fails condition{'s' if len(fails) > 1 else ''} {', '.join(fails)})"))


print("\n" + "=" * 118)
print("## §5.2 DISCOVERY — the six conditions, per feature (judged values are sign x smoothed / MH ratio in the feature's own direction)")
print(f"   permutation: {NS} shuffles, rng {C.SEED}; discovery events {N}; big winners {int(big.sum())}")
for f in FEATS:
    block(R[f])
print("\n" + "=" * 118)
print("## BENCHMARKS (not candidates; printed for reference)")
for b in ("B1", "B1clean", "B2"):
    block(BEN[b], cond=False)

print("\n" + "=" * 118)
print("## CONDITION 6 — group winners and the cap of four")
print(f"   common-set sizes: all-20 {int(COMMON_ALL.sum())} events; " + " · ".join(f"{g} {int(m.sum())}" for g, m in GROUP_SET.items()))
for g, fs in F.GROUPS.items():
    print(f"   group {g:20s}: " + " | ".join(f"{f} z {ZG[f]['z']:.2f} (ratio {fmt_r(ZG[f]['raw'])}, own p {R[f]['p']:.4f})" for f in fs) + f"  -> winner {WIN[g]}")
print("   cap (group winners ranked by z on the all-20 set): " + " > ".join(f"{f} z {ZA[f]['z']:.2f}" for f in order4) + f"  -> the four: {TOP4}")

print("\n## SUMMARY TABLE (ratio = judged top/bottom or MH yes/no; ex20 / ADRn / shelf = in the feature's own direction)")
print(f"   {'feat':4} {'name':44} {'ratio':>6} {'p':>7} {'ex20':>6} {'ADRn':>6} {'shelf':>6} {'grpWin':>6} {'cap4':>5} {'1-5':>5}  verdict")
for f in FEATS:
    r = R[f]; d = r["dir"]
    print(f"   {f:4} {r['name'][:44]:44} {e(r['lr']):>6} {r['p']:7.4f} {e(d * r['ex']['lr']):>6} {e(d * r['adr']['lr']):>6} {(e(d * r['dmin']['lr']) if f in REL else '-'):>6} {('yes' if r['gw'] else 'no'):>6} {('yes' if r['in4'] else 'no'):>5} {('pass' if r['c15'] else 'fail'):>5}  {'CARRIED' if r['carried'] else 'NOT CARRIED'}")
CAR = [f for f in FEATS if R[f]["carried"]]
lost6 = [f for f in FEATS if R[f]["c15"] and not R[f]["c6"]]
nearp = [f for f in FEATS if 0.04 <= R[f]["p"] <= 0.06]
print("\n## CARRIED LIST (direction frozen)")
if CAR:
    for f in CAR:
        r = R[f]
        print(f"   {f} {r['name']}: {dirword(r)} | ratio {e(r['lr'])} (90% {r['ci'][0]:.2f}-{r['ci'][1]:.2f}) p {r['p']:.4f} | ex-2020 {e(r['dir'] * r['ex']['lr'])} | ADR-neutral {e(r['dir'] * r['adr']['lr'])}"
              f" | monster {fmt_r(r['mon']['raw'])} | ADR tail {fmt_r(r['adrt']['raw'])}" + ("  [shelf relative — confirm partly seen]" if f in REL else ""))
else:
    print("   NONE — no feature met all six conditions. Every feature is NOT CARRIED, final (§5.2).")
print(f"   features passing conditions 1-5 but losing on condition 6 (group / cap): {lost6 if lost6 else 'none'}")
print(f"   features whose p sits within 0.04-0.06 (recount-sensitive): {nearp if nearp else 'none'}")
print(f"   features passing conditions 1-2 only: {[f for f in FEATS if R[f]['c1'] and R[f]['c2']]}")

# ════════════════════════════════════════ §5.6 combination ════════════════════════════════════════
print("\n## §5.6 COMBINATION (fixed on discovery; tested once on confirm)")
if len(CAR) >= 2:
    mask = np.ones(N, bool)
    for f in CAR:
        mask &= D[f].notna().to_numpy()
    acc = np.zeros(N)
    for f in CAR:
        pr = S.pct_rank_within(D, f, ["era", "month"], mask)
        acc += pr if R[f]["dir"] > 0 else (1.0 - pr)
    D["combo"] = np.where(mask, acc / len(CAR), np.nan)
    print("   definition: equal-weight mean of the within-(era, month) percentile ranks ((average rank - 0.5) / n, over the events scored on all members) of "
          + ", ".join(f"{f} ({'as is' if R[f]['dir'] > 0 else '1 - rank'})" for f in CAR) + "; direction fixed: HIGH third wins; then thirds within month as §5.1.")
    rc = full_read("combo", False, dict(tm=month_assign("combo", ALLTRUE), ta=strata_assign("combo", "adr"), td=None), "combination of " + "+".join(CAR))
    print(f"   events scored on all members: {int(mask.sum())}")
    print("   discovery numbers below are DESCRIPTION (the members were chosen on these outcomes — 'seen'):")
    block(rc, cond=False)
else:
    print(f"   {len(CAR)} feature(s) carried -> fewer than 2: NO combination step (§5.6).")
print("\n## END OF DISCOVERY" + (" [SYNTHETIC — not a result]" if SYN else ""))
