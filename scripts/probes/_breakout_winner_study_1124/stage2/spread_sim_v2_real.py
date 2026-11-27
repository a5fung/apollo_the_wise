#!/usr/bin/env python3
"""STAGE 2 RE-RUN on the REAL counts (prereg 5.4 last bullet / 6 step 2): a copy of design/spread_sim_v2.py with ONLY the count inputs changed
(YEARS_A / MONTHS / ERA_B_YEAR replaced by the stage-1f table's real per-month thirds; keep = 1.0 only because the counts are already post-gate;
seed, N, CV, X2020, FAM, the model and every rule unchanged). Reads the feature table (counts only) and an RNG. Original docstring follows.
Spread simulation v2 for the BREAKOUT big-winner chart study draft v2 (§5.4), 2026-11-24. Supersedes spread_sim.py (kept
as v1 history; critique_power_rerun.py reads its source). OUTCOME-FREE: synthetic labels only; no bar, no forward price, no
outcome file is read. numpy only.     python3 spread_sim_v2.py > spread_sim_v2.txt

What changed from v1 (critique findings 1, 8, 9):
  * Event counts are the v2 keep rule's (rows <= D only, hash coin q = 0.2; `count_events_v2_forward_hash.txt`):
    2017 814 · 2018 1,232 · 2019 1,198 · 2020 3,439 · 2021 3,083 · 2022-Q1 748. Still INDICATIVE (era A, per ticker, the
    11-13 capture, BEFORE the context gates); `keep` 1.0 / 0.6 brackets the context gates' cut.
  * Era B = 30 months (E 2022-04 .. 2024-09; E+60 by 2024-12-31), ASSUMED 1,081 events a year (the v2 2017-19 mean) x 2.5 =
    2,703. No era-B count exists; no era-B list file was opened.
  * "p" is the big-winner rate OUTSIDE 2020 (2020 = 3 x p, a guess). The POOLED discovery rate is printed beside it — the
    row to read is chosen by the 2017-19 rate, never by the pooled one.
  * Era B's rate is run at 1.0 / 0.75 / 0.5 x p (0.75 = the #705 hint 7.9% vs 10.5%; 0.5 = a stress).
  * 25-month era B (features 10, 11, 21, 22, 23 are NULL in era B until about 2022-09) is run at 1.0x and 0.75x.
  * REVERSED: how often the v1 rule (check ratio < 1.0) and the v2 rule (ratio <= 0.83 AND opposite one-sided p <= 0.05/9)
    fire on a true 1.0x / 1.2x / 1.5x reading.
  * The smallest true ratio with an 80% chance of PICKS THE TAIL on check (family of 9, first Holm step), per setting.

Model (unchanged): months as blocks (thirds formed within month, §5.1). A month's rate is Beta around the year's rate (CV
0.6). Feature of true ratio k: third rates b, b(1+k)/2, bk with b = 2p/(1+k). p-values are empirical against the k = 1
draws (a stand-in for the within-month permutation). Family figures use the FIRST Holm step (0.05 / m): lower bounds for a
family member. The whole-chain figure is carried x check for independent draws; it is NOT a bound — the group / cap-of-four
rule, same-day theme clustering and gate truncation are not simulated and all push it DOWN."""
import numpy as np
rng = np.random.default_rng(1124); N = 20000; CV = 0.6; X2020 = 3.0; FAM = 9
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2lib as L
L.assert_docs()
_T = L.load(); _K, _D, _C = L.kept_events(_T)

def real_blocks(df, col):
    """per (era, month) holding >= 6 events scored on `col`: (events in top third, events in bottom third, year, era) from np.array_split sizes."""
    out = []
    d = df[df[col].notna()]
    for (era, mo), g in d.groupby(["era", "month"]):
        n = len(g)
        if n < 6:
            continue
        q, r = divmod(n, 3)
        out.append((q, q + (1 if r > 0 else 0), int(mo[:4]), era, mo))
    return out

REAL = {"f01": (real_blocks(_D, "f01"), real_blocks(_C, "f01")), "f10": (real_blocks(_D, "f10"), real_blocks(_C, "f10"))}

def nreal(which, era="all", feat="f01"):
    """real events in the blocks used (every event scored on the feature in a month holding thirds, middle third included)."""
    df = (_D, _C)[which]; df = df[df[feat].notna()]
    if era != "all": df = df[df.era == era]
    ok = df.groupby(["era", "month"]).month.transform("size") >= 6
    return int(ok.sum())

def blocks(which, p, era_b_mult=1.0, era="all", feat="f01"):
    """which = 0 discovery / 1 check; returns [(m_top, m_bot, rate, year)]."""
    out = []
    for mt, mb, y, e, mo in REAL[feat][which]:
        if era != "all" and e != era:
            continue
        out.append((mt, mb, p * (X2020 if y == 2020 else 1.0) * (era_b_mult if e == "B" else 1.0), y))
    return out

def draw(bl, k, k2020=None):
    T = np.zeros(N); B = np.zeros(N); M = 0; Tx = np.zeros(N); Bx = np.zeros(N); Mx = 0
    Mb = 0; Mbx = 0
    for mt, mb, p, y in bl:
        kk = k if k2020 is None else (k2020 if y == 2020 else 1.0)
        a = max((1 - p) / CV ** 2 - p, 0.05); pm = rng.beta(a, a * (1 - p) / p, N)
        b = 2 * pm / (1 + kk)
        t = rng.binomial(mt, np.minimum(b * kk, 1)); bb = rng.binomial(mb, np.minimum(b, 1))
        T += t; B += bb; M += mt; Mb += mb
        if y != 2020: Tx += t; Bx += bb; Mx += mt; Mbx += mb
    r = np.log(((T + 0.5) / (M + 1)) / ((B + 0.5) / (Mb + 1)))
    rx = np.log(((Tx + 0.5) / (Mx + 1)) / ((Bx + 0.5) / (Mbx + 1)))
    return r, rx, M + Mb

def pooled(bl):
    return sum((mt + mb) * p for mt, mb, p, _ in bl) / sum(mt + mb for mt, mb, _, _ in bl)

CHECKS = (("3a: era A only", dict(era="A")), ("3b: + era B (real months), rate x1.0", dict(bm=1.0)), ("3b: + era B, rate x0.75", dict(bm=0.75)),
          ("3b: + era B, rate x0.5", dict(bm=0.5)), ("3b, 25-month features (f10's scored counts), rate x1.0", dict(bm=1.0, feat="f10")),
          ("3b, 25-month features, rate x0.75", dict(bm=0.75, feat="f10")))
L125, L110, L12, L083 = np.log(1.25), np.log(1.10), np.log(1.2), np.log(0.83)
for keep in (1.0,):
    for p in (0.03, 0.05, 0.08):
        D = blocks(0, p)
        r0, r0x, nd = draw(D, 1.0); thr2 = np.quantile(np.abs(r0), 0.95)
        carried = {}
        print(f"\n==== REAL COUNTS (keep 1.0: counts are post-gate) · rate OUTSIDE 2020 {p:.0%} (2020: {X2020*p:.0%}; POOLED discovery rate {pooled(D):.1%}) · discovery {nreal(0)} events ({nd} in the compared top and bottom thirds) in {len(D)} months ====")
        print(f"  discovery null 95% band {np.exp(np.quantile(r0,.025)):.2f}-{np.exp(np.quantile(r0,.975)):.2f} | without 2020 "
              f"{np.exp(np.quantile(r0x,.025)):.2f}-{np.exp(np.quantile(r0x,.975)):.2f} | discovery ratio needed for p<=0.05: {np.exp(thr2):.2f}")
        for k in (1.0, 1.2, 1.3, 1.5, 2.0):
            r, rx, _ = draw(D, k)
            c12 = (r >= L125) & (np.abs(r) >= thr2); c123 = c12 & (rx >= L110); carried[k] = c123.mean()
            print(f"  true {k:.1f}x: carried on conditions 1-2 {c12.mean():.3f} | + without-2020 >= 1.10 {c123.mean():.3f}")
        r, rx, _ = draw(D, 1.0, k2020=1.5)
        c12 = (r >= L125) & (np.abs(r) >= thr2)
        print(f"  2020-only artefact (1.5x in 2020, none 2017-19): passes 1-2 {c12.mean():.3f}; of those, without-2020 >= 1.10 "
              f"{(c12 & (rx >= L110)).sum() / max(c12.sum(), 1):.2f}")
        for name, kw in CHECKS:
            C = blocks(1, p, era_b_mult=kw.get("bm", 1.0), era=kw.get("era", "all"), feat=kw.get("feat", "f01"))
            c0, _, nc = draw(C, 1.0)
            hi = np.quantile(c0, 1 - 0.05 / FAM); lo = np.quantile(c0, 0.05 / FAM)
            print(f"  -- check = {name} · {nreal(1, kw.get("era", "all"), kw.get("feat", "f01"))} events ({nc} in top+bottom) · pooled check rate {pooled(C):.1%} · null 95% band "
                  f"{np.exp(np.quantile(c0,.025)):.2f}-{np.exp(np.quantile(c0,.975)):.2f} · true-zero reads >= 1.2: {(c0 >= L12).mean():.3f}")
            for k in (1.0, 1.2, 1.3, 1.5, 2.0):
                rc, _, _ = draw(C, k)
                tail = ((rc >= hi) & (rc >= L12)).mean()
                print(f"     true {k:.1f}x: PICKS THE TAIL fam{FAM} {tail:.3f} | whole chain {carried[k] * tail:.3f} | "
                      f"REVERSED v1 rule (<1.0) {(rc < 0).mean():.3f} · v2 rule {((rc <= lo) & (rc <= L083)).mean():.3f} | "
                      f"reads >= 1.2 {(rc >= L12).mean():.3f} >= 1.5 {(rc >= np.log(1.5)).mean():.3f}")
            need = None
            for k in np.arange(1.2, 3.01, 0.1):
                rc, _, _ = draw(C, float(k))
                if ((rc >= hi) & (rc >= L12)).mean() >= 0.80: need = k; break
            print(f"     smallest true ratio with an 80% chance of PICKS THE TAIL on check (fam{FAM}): " + (f"{need:.1f}x" if need else "over 3.0x"))
