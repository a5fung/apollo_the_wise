"""ADVERSARIAL VERIFY 2026-10-13: aggregate w2_rows.out (per-row fields derived in SQL) with the csv module only.
Independent of a1_prep/a2_sweep (pandas) and v5_verify. Definitions per the review: in-window = minutes_since_open_at_open <= 15;
bars on today_dollar_volume_at_open; reach = peak HIGH over D0..D0+h vs D0 open >= 8 x ADR20; reach_x = same over D1..Dh only;
settled = close(D0+h)/D0 open - 1; crash <= -20%, win >= +20%; clean = D0+h close + all h forward bars + ADR20 (20 bars) + no >4x close jump-up."""
import csv, math, sys
from collections import defaultdict
rows = []
with open('w2_rows.out') as f:
    lines = [l for l in f if not l.startswith(('BEGIN', 'ROLLBACK'))]
for r in csv.DictReader(lines):
    def F(k):
        v = r[k]; return float(v) if v not in ('', None) else None
    d = dict(date=r['scan_date'], t=r['ticker'], rej=r['rej'] == 't', ao=F('ao'), m=F('m_ao'), gap=F('gap'), p=F('p_ao'),
             o=F('d0_open'), hi=F('d0_high'), lo=F('d0_low'), adr=F('adr20'), npre=int(r['n_pre'] or 0), npre0720=int(r['n_pre_0720'] or 0),
             fac=F('fac'), nsp20=int(r['n_split_in_20'] or 0), nspa=int(r['n_split_after_d0'] or 0))
    for h in (5, 20):
        d[f'n{h}'] = int(r[f'n_fwd{h}'] or 0); d[f'pk{h}'] = F(f'pk{h}'); d[f'pkx{h}'] = F(f'pk{h}x'); d[f'c{h}'] = F(f'c{h}')
        d[f'maxq{h}'] = F(f'maxq{h}'); d[f'minq{h}'] = F(f'minq{h}')
    rows.append(d)
OUT = []
def P(*a): s = ' '.join(str(x) for x in a); print(s); OUT.append(s)
def wilson(k, n, z=1.96):
    if n == 0: return (float('nan'),) * 2
    p = k / n; dd = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return ((c - a) / dd, (c + a) / dd)
def fisher_greater(k1, n1, k2, n2):  # one-sided P(X>=k1) hypergeometric, group1 rate > group2 rate
    K = k1 + k2; N = n1 + n2
    def lc(a, b): return math.lgamma(a + 1) - math.lgamma(b + 1) - math.lgamma(a - b + 1)
    tot = 0.0
    for x in range(k1, min(K, n1) + 1):
        tot += math.exp(lc(n1, x) + lc(n2, K - x) - lc(N, K))
    return tot
def adr_ok(d, rule): return d['adr'] is not None and (d['npre0720'] >= 20 if rule == 'pipe' else d['npre'] >= 20)
def clean(d, h, rule='pipe'):
    return (d[f'c{h}'] is not None and d[f'n{h}'] == h and d['o'] and d['o'] > 0 and d[f'pk{h}'] is not None and adr_ok(d, rule)
            and not (d[f'maxq{h}'] is not None and d[f'maxq{h}'] > 4))
def med(xs):
    xs = sorted(xs); n = len(xs)
    return float('nan') if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)
def stat(sub, h):
    n = len(sub)
    k = sum(1 for d in sub if d[f'pk{h}'] / d['o'] - 1 >= 8 * d['adr'])
    kx = sum(1 for d in sub if d[f'pkx{h}'] is not None and d[f'pkx{h}'] / d['o'] - 1 >= 8 * d['adr'])
    s = [d[f'c{h}'] / d['o'] - 1 for d in sub]
    kc = sum(1 for x in s if x <= -0.2); kw = sum(1 for x in s if x >= 0.2)
    return dict(n=n, names=len({d['t'] for d in sub}), k=k, kx=kx, kc=kc, kw=kw, smed=med(s))
def fmt(st):
    n = st['n']
    if n == 0: return 'n=0'
    lo, hi = wilson(st['k'], n); xlo, xhi = wilson(st['kx'], n); clo, chi = wilson(st['kc'], n)
    return (f"n={n:4d} names={st['names']:4d} | reach {st['k']:3d} {100*st['k']/n:5.1f}% [{100*lo:4.1f}-{100*hi:4.1f}] | ex-D0 {st['kx']:3d} {100*st['kx']/n:5.1f}% [{100*xlo:4.1f}-{100*xhi:4.1f}]"
            f" | crash {st['kc']:3d} {100*st['kc']/n:5.1f}% [{100*clo:4.1f}-{100*chi:4.1f}] | win {st['kw']:3d} {100*st['kw']/n:4.1f}% | settled med {100*st['smed']:6.1f}%")

dates = sorted({d['date'] for d in rows})
rej = [d for d in rows if d['rej']]; adm = [d for d in rows if not d['rej']]
ra = [d for d in rej if d['ao'] is not None]
rw = [d for d in ra if d['m'] is not None and d['m'] <= 15]
aw = [d for d in adm if d['ao'] is not None and d['m'] is not None and d['m'] <= 15]
P('=== V1 POPULATION ===')
P('rows', len(rows), 'names', len({d['t'] for d in rows}), 'dates', len(dates), dates[0], '->', dates[-1])
P('rejected rows', len(rej), 'names', len({d['t'] for d in rej}), '| admitted rows', len(adm), 'names', len({d['t'] for d in adm}))
P('rej with at_open read', len(ra), 'names', len({d['t'] for d in ra}), '| pre-market-only (no at_open) rows', len(rej) - len(ra))
P('rej in-window rows', len(rw), 'names', len({d['t'] for d in rw}), '| minute-1 in-window', sum(1 for d in rw if d['m'] == 1),
  '| share gap>=10', round(sum(1 for d in rw if d['gap'] >= 10) / len(rw), 3))
P('adm in-window rows', len(aw), 'names', len({d['t'] for d in aw}), '| gap>=10 rows', sum(1 for d in aw if d['gap'] >= 10), 'names', len({d['t'] for d in aw if d['gap'] >= 10}))
s20dates = sorted({d['date'] for d in rows if d['c20'] is not None and d['n20'] == 20})
s5dates = sorted({d['date'] for d in rows if d['c5'] is not None and d['n5'] == 5})
P('D0 dates with a 20-session settled close:', len(s20dates), s20dates[0], '->', s20dates[-1], '| 5-session:', len(s5dates), s5dates[0], '->', s5dates[-1])
for h in (20, 5):
    P(f'clean h{h} (pipeline ADR rule): rej in-window rows', sum(1 for d in rw if clean(d, h)), 'names', len({d['t'] for d in rw if clean(d, h)}),
      '| adm', sum(1 for d in aw if clean(d, h)), '/', len({d['t'] for d in aw if clean(d, h)}),
      '| adm gap>=10', sum(1 for d in aw if clean(d, h) and d['gap'] >= 10), '/', len({d['t'] for d in aw if clean(d, h) and d['gap'] >= 10}))
P()
BARS = [10e6, 25e6, 50e6, 100e6]
P('=== V2 the >=15 gate: rejected in-window clearers -> names (rows) clearing | with a D0+20 close | CLEAN h20 ===')
for lab, g in (('all gaps', None), ('gap>=10', 10)):
    for b in BARS:
        s0 = [d for d in rw if d['ao'] >= b and (g is None or d['gap'] >= g)]
        s1 = [d for d in s0 if d['c20'] is not None]
        s2 = [d for d in s0 if clean(d, 20)]
        s2b = [d for d in s0 if clean(d, 20, 'any20')]
        nm = lambda x: len({d['t'] for d in x})
        P(f'  {lab:8s} >=${int(b/1e6):3d}M: clearing {nm(s0)} ({len(s0)}) | D0+20 close {nm(s1)} ({len(s1)}) | CLEAN {nm(s2)} ({len(s2)}) {"MEETS" if nm(s2) >= 15 else "BELOW"} | clean w/ ADR from any 20 prior bars {nm(s2b)} ({len(s2b)}) | names/day {len(s0)/len(dates):.1f}')
P()
for h in (20, 5):
    for lab, g in (('ALL GAPS', None), ('GAP>=10', 10)):
        P(f'=== V3 h={h} {lab} ===')
        R = [d for d in rw if (g is None or d['gap'] >= g)]; A = [d for d in aw if (g is None or d['gap'] >= g)]
        for side, pop in (('REJ', R), ('ADM', A)):
            for b in [0] + BARS:
                sub = [d for d in pop if (b == 0 or d['ao'] >= b) and clean(d, h)]
                st = stat(sub, h)
                P(f'  {side} >=${int(b/1e6):3d}M  {fmt(st)}')
                P(f'CHECK|h{h}|{side}|{"g10" if g else "all"}|{int(b/1e6)}|{st["n"]}|{st["k"]}|{st["kx"]}|{st["kc"]}|{st["kw"]}')
        P()
P('=== V4 one-sided Fisher (rejected clearers vs comparator) on 20-session reach, reach ex-D0, crash ===')
def grab(pop, b, h, g=None): return [d for d in pop if (b == 0 or d['ao'] >= b) and (g is None or d['gap'] >= g) and clean(d, h)]
A0 = stat(grab(aw, 0, 20), 20); Ag = stat(grab(aw, 0, 20, 10), 20)
for b in BARS[:2]:
    S = stat(grab(rw, b, 20), 20); Sg = stat(grab(rw, b, 20, 10), 20)
    P(f'  ${int(b/1e6)}M all-gap REJ {S["k"]}/{S["n"]} vs ADM-all {A0["k"]}/{A0["n"]}: p={fisher_greater(S["k"],S["n"],A0["k"],A0["n"]):.3f} | ex-D0 {S["kx"]}/{S["n"]} vs {A0["kx"]}/{A0["n"]}: p={fisher_greater(S["kx"],S["n"],A0["kx"],A0["n"]):.3f}'
      f' | vs ADM gap>=10 {Ag["k"]}/{Ag["n"]}: p={fisher_greater(S["k"],S["n"],Ag["k"],Ag["n"]):.3f} | gap-matched REJ {Sg["k"]}/{Sg["n"]} vs {Ag["k"]}/{Ag["n"]}: p={fisher_greater(Sg["k"],Sg["n"],Ag["k"],Ag["n"]):.3f}')
    P(f'      crash REJ {S["kc"]}/{S["n"]} vs ADM gap>=10 {Ag["kc"]}/{Ag["n"]}: p(REJ crashes more)={fisher_greater(S["kc"],S["n"],Ag["kc"],Ag["n"]):.4f}')
    k82 = round(0.082 * S['n'])
    P(f'      vs #570 8.2%: binomial P(X>={S["k"]} | n={S["n"]}, p=.082) = {sum(math.comb(S["n"],x)*0.082**x*0.918**(S["n"]-x) for x in range(S["k"], S["n"]+1)):.3f}')
P()
P('=== V5 projection: per D0 date, NEW distinct in-window clearing names with ADR (cumulative) at $50M / $100M ===')
for b in (50e6, 100e6):
    seen = set(); cum = []
    for dt in dates:
        new = {d['t'] for d in rw if d['date'] == dt and d['ao'] >= b and adr_ok(d, 'pipe')} - seen
        seen |= new; cum.append(f'{dt[5:]}:{len(seen)}')
    P(f'  ${int(b/1e6)}M', ' '.join(cum))
P()
P('=== V6 pre-market-price flag: minute-1 in-window rejected reads with price outside D0 [low,high] +-0.5% (bars un-adjusted by applied splits after D0) ===')
def flag(d):
    if d['hi'] is None or d['lo'] is None or d['p'] is None: return None
    f = d['fac'] or 1.0
    return d['p'] < d['lo'] * f * 0.995 or d['p'] > d['hi'] * f * 1.005
m1 = [d for d in rw if d['m'] == 1]
fl = [flag(d) for d in m1]
P('  all rej minute-1 in-window:', sum(1 for x in fl if x), '/', sum(1 for x in fl if x is not None), f'({100*sum(1 for x in fl if x)/max(1,sum(1 for x in fl if x is not None)):.0f}%)')
fl_raw = [ (d['p'] < d['lo']*0.995 or d['p'] > d['hi']*1.005) for d in m1 if d['hi'] is not None and d['p'] is not None]
P('  same, WITHOUT split un-adjustment:', sum(fl_raw), '/', len(fl_raw))
for b in BARS:
    c = [d for d in rw if d['m'] == 1 and d['ao'] >= b]; cf = [flag(d) for d in c]
    cc = [d for d in rw if d['ao'] >= b and clean(d, 20)]; ccf = [flag(d) for d in cc if d['m'] == 1]
    P(f'  >=${int(b/1e6)}M: flagged {sum(1 for x in cf if x)}/{len([d for d in rw if d["ao"] >= b])} clearers ({len(c)} are minute-1) | clean-20 cohort flagged {sum(1 for x in ccf if x)}/{len(cc)}')
P()
P('=== V7 split exposure inside clean 20-session rows; >4x single-day DROP (unapplied forward split would read as a crash) ===')
cr = [d for d in rw if clean(d, 20)]
P('  clean rej in-window h20 rows with an applied split inside D0..D0+20:', sum(1 for d in cr if d['nsp20'] > 0), '/', len(cr),
  '| rows with a >4x down day (minq20<0.25):', sum(1 for d in cr if d['minq20'] is not None and d['minq20'] < 0.25),
  [ (d['date'], d['t']) for d in cr if d['minq20'] is not None and d['minq20'] < 0.25])
for b in BARS:
    sub = [d for d in cr if d['ao'] >= b]
    P(f'   >=${int(b/1e6)}M clean rows with split in window: {[(d["date"][5:], d["t"]) for d in sub if d["nsp20"] > 0]} | >4x drop: {[(d["date"][5:], d["t"]) for d in sub if d["minq20"] is not None and d["minq20"] < 0.25]}')
P()
P('=== V8 clean 20-session $50M and $100M cohort listing (date ticker ao gap reach reach_x settled) ===')
for b in (50e6, 25e6):
    for d in sorted([d for d in cr if d['ao'] >= b], key=lambda x: (x['date'], x['t'])):
        P(f'  >=${int(b/1e6)}M {d["date"]} {d["t"]:6s} ao=${d["ao"]/1e6:7.1f}M m={int(d["m"])} gap={d["gap"]:6.1f} adr={d["adr"]:.3f} exc={d["pk20"]/d["o"]-1:+.2f} excx={d["pkx20"]/d["o"]-1:+.2f} 8adr={8*d["adr"]:.2f} s20={d["c20"]/d["o"]-1:+.2f}')
open('w3_aggregate.out', 'w').write('\n'.join(OUT) + '\n')
