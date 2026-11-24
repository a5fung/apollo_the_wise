"""Synthetic only. Does the draft's either-side random thinning create a feature-outcome link under a TRUE NULL?
Each ticker: one stream of break rows over 1300 sessions built from episodes. An episode at a random start has
 - a PAST-density flag z (feature: 'already running' = many break rows in the 60 sessions BEFORE the focal row)
 - a FUTURE-density flag w (outcome: 'big winner' = keeps breaking out for 60 sessions AFTER the focal row)
z and w are drawn INDEPENDENTLY (null). Every row gets feature = # break rows in the prior 60 sessions (>= cut -> high),
outcome = # break rows in the next 60 sessions >= cut2 (a stand-in for 'ran'), so truth is measured on ALL rows and on
focal rows; then three thinnings are compared on the FOCAL rows' design flags z,w (independent by construction)."""
import numpy as np
rng = np.random.default_rng(7)
def run(ntick=40000, lam=3.0, mult=4.0, pw=0.10):
    res = {k: np.zeros((2, 2)) for k in ('all', 'either_random', 'forward_first', 'forward_coin')}  # forward_first is thin at high density: read its n
    for _ in range(ntick):
        z = rng.random() < 0.5; w = rng.random() < pw
        A = rng.poisson(lam * (mult if z else 1)); B = rng.poisson(lam * (mult if w else 1))
        t = np.r_[-rng.integers(1, 61, A), 0, rng.integers(1, 61, B)]
        t = np.unique(t); foc = int(np.flatnonzero(t == 0)[0])
        res['all'][int(z), int(w)] += 1
        # either-side random greedy (the draft)
        acc = []
        for j in rng.permutation(len(t)):
            if all(abs(t[j] - a) > 60 for a in acc): acc.append(t[j])
        if 0 in acc: res['either_random'][int(z), int(w)] += 1
        # forward walk, first eligible
        last = -10**9; kept = []
        for x in t:
            if x - last > 60: kept.append(x); last = x
        if 0 in kept: res['forward_first'][int(z), int(w)] += 1
        # forward walk with a coin (q = 0.25): decision uses rows <= x only
        last = -10**9; kept = []
        for x in t:
            if x - last > 60 and rng.random() < 0.25: kept.append(x); last = x
        if 0 in kept: res['forward_coin'][int(z), int(w)] += 1
    for k, m in res.items():
        r1 = m[1, 1] / m[1].sum(); r0 = m[0, 1] / m[0].sum()
        print(f"  {k:14s} kept {int(m.sum()):6d}  winner rate z=high {r1:.3f}  z=low {r0:.3f}  ratio {r1 / r0:.2f}")
for lam, mult in ((3, 4), (1, 4), (1, 2)):
    print(f"lam {lam} mult {mult} (true ratio 1.00 by construction)"); run(ntick=250000, lam=lam, mult=mult)
