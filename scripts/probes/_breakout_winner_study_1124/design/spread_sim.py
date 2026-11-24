#!/usr/bin/env python3
"""Spread simulation for the BREAKOUT big-winner chart study draft (§5.4), 2026-11-24.
OUTCOME-FREE: synthetic labels only; no bar, no forward price, no outcome file is read. numpy only.

What it answers: on a CORRECT build, how often does a chart reading of true size k (top third's big-winner rate / bottom
third's) get carried on discovery and then reach PICKS THE TAIL on confirm — for each base rate we might meet (the real
base rate is NOT known: no outcome has been read for this population) and each population size the forks leave open.

Event counts (INDICATIVE): one random break per ticker per 60 sessions (set A of `count_events_outcome_free.py`), counted
outcome-free from the 11-13 capture `apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet` (fire flag only), which
PREDATES the 11-14 context gates: 2017 1,080 · 2018 1,608 · 2019 1,660 · 2020 3,977 · 2021 3,916 · 2022-Q1 1,220.
`keep` scales them for the context gates (1.0 and 0.6 — the real share is not known until stage 1).
Era B (2022-04..2024) has no capture: assumed 1,449 a year (the 2017-19 mean) x 2.75 years = 3,985 — an ASSUMPTION.

Model: months as blocks (thirds are formed within month, as §5.1). A month's base rate is Beta-distributed around the
year's rate (CV 0.6) so winners cluster in time as real ones do. Feature of true ratio k: third rates b, b(1+k)/2, bk
with b = 2p/(1+k). 2020's rate = 3 x the other years' (EP's was 5 x; unknown here, a guess). p-values are empirical
against the k = 1 draws (a stand-in for the within-month permutation). Holm figures use the FIRST step (0.05 / m): lower
bounds. NOT simulated: the ex-2020 floor's calibration, the gate-truncation of a feature's range, the group / cap rule,
same-day theme clustering (it widens every band a little)."""
import numpy as np
rng = np.random.default_rng(1124); N = 20000; CV = 0.6
YEARS_A = {2017: 1080, 2018: 1608, 2019: 1660, 2020: 3977, 2021: 3916, 2022: 1220}
MONTHS = {2017: 12, 2018: 12, 2019: 12, 2020: 12, 2021: 12, 2022: 3}
ERA_B = (3985, 33)                                             # events, months (2022-04 .. 2024-12)

def blocks(years, keep, p, x2020=3.0, with_b=False):
    out = []
    for y in years:
        m = MONTHS[y]; out += [(int(YEARS_A[y] * keep / m), p * (x2020 if y == 2020 else 1.0), y)] * m
    if with_b:
        out += [(int(ERA_B[0] * keep / ERA_B[1]), p, 2023)] * ERA_B[1]
    return out

def draw(bl, k, k2020=None):
    """returns (top winners, bottom winners, third size) summed over month blocks, plus the same without 2020."""
    T = np.zeros(N); B = np.zeros(N); M = 0; Tx = np.zeros(N); Bx = np.zeros(N); Mx = 0
    for ev, p, y in bl:
        kk = k if (k2020 is None or y == 2020) else 1.0
        if k2020 is not None and y == 2020: kk = k2020
        m = ev // 3
        a = (1 - p) / CV ** 2 - p; a = max(a, 0.05); pm = rng.beta(a, a * (1 - p) / p, N)   # month rate, mean p, CV 0.6
        b = 2 * pm / (1 + kk)
        t = rng.binomial(m, np.minimum(b * kk, 1)); bb = rng.binomial(m, np.minimum(b, 1))
        T += t; B += bb; M += m
        if y != 2020: Tx += t; Bx += bb; Mx += m
    r = np.log(((T + 0.5) / (M + 1)) / ((B + 0.5) / (M + 1)))
    rx = np.log(((Tx + 0.5) / (Mx + 1)) / ((Bx + 0.5) / (Mx + 1)))
    return r, rx, M * 3

DISC_Y = (2017, 2018, 2019, 2020); CONF_Y = (2021, 2022)
for keep in (1.0, 0.6):
    for p in (0.03, 0.05, 0.08):
        for with_b in (False, True):
            D = blocks(DISC_Y, keep, p); C = blocks(CONF_Y, keep, p, with_b=with_b)
            r0, r0x, nd = draw(D, 1.0); c0, _, nc = draw(C, 1.0)
            thr2 = np.quantile(np.abs(r0), 0.95)
            print(f"\n== keep {keep:.1f} of the capture · base rate {p:.0%} (2020: {3*p:.0%}) · confirm = "
                  f"{'era A + era B' if with_b else 'era A only'} · discovery {nd} events, confirm {nc} ==")
            print(f"  null 95% band: discovery {np.exp(np.quantile(r0,.025)):.2f}-{np.exp(np.quantile(r0,.975)):.2f} | ex-2020 "
                  f"{np.exp(np.quantile(r0x,.025)):.2f}-{np.exp(np.quantile(r0x,.975)):.2f} | confirm "
                  f"{np.exp(np.quantile(c0,.025)):.2f}-{np.exp(np.quantile(c0,.975)):.2f} | discovery ratio needed for p<=0.05: {np.exp(thr2):.2f}")
            for k in (1.0, 1.3, 1.5, 2.0):
                r, rx, _ = draw(D, k); rc, _, _ = draw(C, k)
                c12 = (r >= np.log(1.25)) & (np.abs(r) >= thr2); c123 = c12 & (rx >= np.log(1.10))
                line = f"  true {k:.1f}x: carried (1-2) {c12.mean():.3f} | + ex-2020>=1.10 {c123.mean():.3f} | confirm"
                for m in (1, 5, 9):
                    ok = (rc >= np.quantile(c0, 1 - 0.05 / m)) & (rc >= np.log(1.2))
                    line += f" fam{m} {ok.mean():.3f}"
                    if m == 9: chain = c123.mean() * ok.mean()
                line += f" | whole chain fam9 {chain:.3f} | P(confirm>=1.2) {(rc >= np.log(1.2)).mean():.3f} P(>=1.5) {(rc >= np.log(1.5)).mean():.3f}"
                print(line)
            if p == 0.05 and not with_b:
                r, rx, _ = draw(D, 1.0, k2020=1.5)
                c12 = (r >= np.log(1.25)) & (np.abs(r) >= thr2)
                print(f"  2020-only artefact (1.5x in 2020, none 2017-19): passes 1-2 {c12.mean():.3f}; of those ex-2020>=1.10 "
                      f"{(c12 & (rx >= np.log(1.10))).sum() / max(c12.sum(), 1):.2f}")
