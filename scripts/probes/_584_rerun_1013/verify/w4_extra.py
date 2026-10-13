"""ADVERSARIAL VERIFY 2026-10-13 (local, reads w2_rows.out via w3's loader): (1) diff my CHECK rows vs the gatherer's a2_sweep.out;
(2) 5-session read on the SAME clean 20-session rows; (3) is the gap-day-high effect a HORIZON effect or a COHORT effect?
(4) 10-01 regression subset (D0<=09-23, ticker NA excluded) vs the numbers written into resolution_2026_10_01."""
import re, sys, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import w3_aggregate as W
OUT = []
def P(*a): s = ' '.join(str(x) for x in a); print(s); OUT.append(s)
mine = {l.split('|', 6)[1:6].__str__(): l.strip() for l in open('w3_aggregate.out') if l.startswith('CHECK|')}
theirs = [l.strip() for l in open('../a2_sweep.out') if l.startswith('CHECK|h')]
mine_set = {l.strip() for l in open('w3_aggregate.out') if l.startswith('CHECK|')}
miss = [l for l in theirs if l not in mine_set]
P('(1) gatherer CHECK rows (h5/h20):', len(theirs), '| reproduced exactly by SQL derivation:', len(theirs) - len(miss), '| mismatches:', miss)
rw, aw, clean, BARS = W.rw, W.aw, W.clean, W.BARS
def r5(sub):
    n = len(sub); k = sum(1 for d in sub if d['pk5'] / d['o'] - 1 >= 8 * d['adr']); kx = sum(1 for d in sub if d['pkx5'] is not None and d['pkx5'] / d['o'] - 1 >= 8 * d['adr'])
    s = [d['c5'] / d['o'] - 1 for d in sub]; kc = sum(1 for x in s if x <= -0.2)
    return n, k, kx, kc, W.med(s)
P('(2) 5-session read on the SAME clean 20-session rows: n | reach5 | reach5 ex-D0 | crash5 | settled5 median')
for lab, pop in (('REJ', rw), ('ADM', aw)):
    for b in [0] + BARS:
        sub = [d for d in pop if (b == 0 or d['ao'] >= b) and clean(d, 20) and clean(d, 5)]
        n, k, kx, kc, m = r5(sub)
        P(f'   {lab} >=${int(b/1e6)}M n={n} reach5={k} ex={kx} crash5={kc} ({100*kc/max(n,1):.1f}%) med5={100*m:.1f}%')
    sub = [d for d in pop if d['gap'] >= 10 and clean(d, 20) and clean(d, 5)]
    n, k, kx, kc, m = r5(sub); P(f'   {lab} gap>=10 all n={n} reach5={k} ex={kx} crash5={kc} ({100*kc/max(n,1):.1f}%) med5={100*m:.1f}%')
P('(3) 5-session reach incl vs ex-D0 split by COHORT: early (D0<=09-14, the 20-session cohort) vs late (D0 09-15..10-05)')
for b in BARS:
    for lab, cond in (('early', lambda d: d['date'] <= '2026-09-14'), ('late', lambda d: d['date'] > '2026-09-14')):
        sub = [d for d in rw if d['ao'] >= b and clean(d, 5) and cond(d)]
        n, k, kx, kc, m = r5(sub)
        P(f'   >=${int(b/1e6)}M {lab:5s} n={n:3d} reach5 {k:2d} ({100*k/max(n,1):4.1f}%) ex-D0 {kx:2d} ({100*kx/max(n,1):4.1f}%)')
P('(4) 10-01 regression subset (5-session, D0<=09-23, NA excluded): gap>=10 REJ clearers + gap-matched ADM')
for b in [0] + BARS:
    for lab, pop in (('REJ', rw), ('ADM', aw)):
        sub = [d for d in pop if d['date'] <= '2026-09-23' and d['t'] != 'NA' and d['gap'] >= 10 and (b == 0 or d['ao'] >= b) and clean(d, 5)]
        n, k, kx, kc, m = r5(sub)
        P(f'   {lab} g10 >=${int(b/1e6)}M n={n} reach={100*k/max(n,1):.1f}% ex-D0={100*kx/max(n,1):.1f}% crash={100*kc/max(n,1):.1f}%')
na = [(d['date'], d['m'], d['ao']) for d in W.rows if d['t'] == 'NA']
P('   ticker NA rows (date, minute, ao):', na)
open('w4_extra.out', 'w').write('\n'.join(OUT) + '\n')
