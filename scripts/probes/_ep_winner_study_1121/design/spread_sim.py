#!/usr/bin/env python3
"""Spread simulation for prereg_draft.md §5.4 (2026-11-21). OUTCOME-FREE: synthetic binomial labels only, no bar or outcome read.
Thirds pooled per year-block; a feature of true ratio k has third rates b, b(1+k)/2, bk with b = 2p/(1+k) (mean rate p kept).
Per-year base rates: 2016-19 4.9% (about 80 winners / 1,643 events, critique §S), 2020 25%, confirm 10.5% — all already-seen
aggregates from RESULT 8, used for spread only. p-values are empirical against the k=1 draws (stand-in for the permutation).
NOT simulated: the ADR-neutral floor and the shelf-relative condition (need the real feature table -> build step 0)."""
import numpy as np
rng = np.random.default_rng(1121); N = 40000
def draw(blocks, k, n=N):
    """blocks = [(events, base rate)]; returns top winners, bottom winners, third size (pooled), per block arrays."""
    out = []
    for ev, p in blocks:
        m = ev // 3; b = 2 * p / (1 + k)
        out.append((rng.binomial(m, min(b * k, 1), n), rng.binomial(m, b, n), m))
    return out
def ratio(parts):
    t = sum(x[0] for x in parts) + 0.5; b = sum(x[1] for x in parts) + 0.5; m = sum(x[2] for x in parts) + 1
    return (t / m) / (b / m)
DISC = [(1643, 0.049), (771, 0.25)]; DISC_LONG = [(1317, 0.049), (771, 0.25)]   # long = 250-bar features: 2016 all NULL
CONF = [(2178, 0.105)]; CONF_LONG = [(1850, 0.105)]
for name, D, C in (("short-history feature", DISC, CONF), ("250-bar feature", DISC_LONG, CONF_LONG)):
    print(f"\n== {name}: discovery {sum(e for e,_ in D)} events, confirm {C[0][0]} ==")
    nd = draw(D, 1.0); r0 = np.log(ratio(nd)); r0x = np.log(ratio(nd[:1]))
    thr2 = np.quantile(np.abs(r0), 0.95)                       # two-sided p <= 0.05 on |log ratio|
    nc = np.log(ratio(draw(C, 1.0)))
    print(f"  null 95% band: discovery {np.exp(np.quantile(r0,.025)):.2f}-{np.exp(np.quantile(r0,.975)):.2f} | ex-2020 "
          f"{np.exp(np.quantile(r0x,.025)):.2f}-{np.exp(np.quantile(r0x,.975)):.2f} | confirm {np.exp(np.quantile(nc,.025)):.2f}-{np.exp(np.quantile(nc,.975)):.2f}"
          f" | discovery ratio needed for p<=0.05: {np.exp(thr2):.2f}")
    for k in (1.0, 1.3, 1.5, 2.0):
        d = draw(D, k); r = np.log(ratio(d)); rx = np.log(ratio(d[:1]))
        c12 = (r >= np.log(1.25)) & (np.abs(r) >= thr2)
        c123 = c12 & (rx >= np.log(1.10))
        rc = np.log(ratio(draw(C, k)))
        line = f"  true {k:.1f}x: carry cond 1-2 {c12.mean():.3f} | + ex-2020 >=1.10 {c123.mean():.3f} | ex-2020 pass given 1-2 {c123.sum()/max(c12.sum(),1):.2f} | confirm"
        for m in (1, 5, 8):
            thr = np.quantile(nc, 1 - 0.05 / m)
            line += f" fam{m}: {((rc >= thr) & (rc >= np.log(1.2))).mean():.3f}"
        line += f" | P(confirm ratio>=1.2) {(rc >= np.log(1.2)).mean():.3f} P(>=1.5) {(rc >= np.log(1.5)).mean():.3f}"
        print(line)
# a 2020-only artefact: true 1.5x in 2020, 1.0x in 2016-19
d = [draw([DISC[0]], 1.0)[0], draw([DISC[1]], 1.5)[0]]; r = np.log(ratio(d)); rx = np.log(ratio(d[:1]))
r0 = np.log(ratio(draw(DISC, 1.0))); thr2 = np.quantile(np.abs(r0), 0.95)
c12 = (r >= np.log(1.25)) & (np.abs(r) >= thr2)
print(f"\n2020-only artefact (1.5x in 2020, none 2016-19): passes cond 1-2 {c12.mean():.3f}; of those, ex-2020 'same direction' "
      f"{(c12 & (rx > 0)).sum()/c12.sum():.2f}, ex-2020 >=1.10 {(c12 & (rx >= np.log(1.10))).sum()/c12.sum():.2f}")
