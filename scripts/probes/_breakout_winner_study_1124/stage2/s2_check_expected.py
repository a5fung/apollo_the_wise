"""ADDED AFTER RUN 1 (advisor): the composition-expected check ratio under no effect with era B at 0.75x and 0.5x (the prereg's own grid), because
the check null of s2_calib.py has equal rates in both eras so every expected ratio there is 1.000 by construction. Table + arithmetic only; no draws."""
import sys, numpy as np
import s2_calib as S, s2lib as L
P = print
P("composition-expected ratio under no effect, CHECK set: pooled (all) | B4-strata; era B rate x1.0 / x0.75 / x0.5 of era A's 5%; band 0.95-1.05")
bad = []
for f in L.FEATS:
    if f in L.TWO_GROUP: continue
    DD, col = L.pop_frame(S.C, f); pop = S.Pop(DD, col)
    cells = []
    for bm in (1.0, 0.75, 0.5):
        e = pop.expected_null(S.event_pb(pop, 0.05, bm))
        cells.append(f"x{bm}: all {e['all']:.3f} b4 {e.get('b4', float('nan')):.3f}")
        for k in ('all', 'b4'):
            if k in e and not 0.95 <= e[k] <= 1.05: bad.append((f, bm, k, e[k]))
    P(f"  {f:5s} " + " | ".join(cells))
P(f"\noutside the band: {bad if bad else 'none'}")
