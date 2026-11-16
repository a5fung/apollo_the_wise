import csv, collections, datetime as dt
rows=[]
with open('q2_out.txt') as f:
    lines=f.read().splitlines()
hdr=lines[1].split('|')
for l in lines[2:]:
    if l.startswith('('): break
    rows.append(dict(zip(hdr,l.split('|'))))
print('prospective rows',len(rows))
cut=dt.date(2026,11,16)-dt.timedelta(days=30)
def mature(r): return dt.date.fromisoformat(r['fire_date'])<=cut
def f(x): return float(x) if x not in ('',None) else None
C=collections.Counter
print('by maturity/settled:',C((mature(r), r['realized_r']!='', r['outcome'] or 'OPEN') for r in rows))
M=[r for r in rows if mature(r) and r['realized_r']!='']
print('MATURE settled',len(M))
print('mature all (incl unsettled):',C((r['outcome'] or 'OPEN') for r in rows if mature(r)))
print('fire_date range',min(r['fire_date'] for r in M),max(r['fire_date'] for r in M))
print('ep_date range',min(r['ep_date'] for r in M),max(r['ep_date'] for r in M))
print('campaigns (ticker,ep_date):',len({(r['ticker'],r['ep_date']) for r in M}))
for k in ['rung','pattern_version','screen_version','screen_member','reentry_shape','outcome','settle_version','resolution','catalyst_grade']:
    print(k,dict(C(r[k] for r in M)))
print()
print('rung x screen x outcome')
for rung in sorted({r['rung'] for r in M}):
    for lvl in ['raw','screen']:
        S=[r for r in M if r['rung']==rung and (lvl=='raw' or r['screen_member']=='t')]
        tails=[r for r in S if f(r['realized_r'])>=4]
        r4=[r for r in S if r['reached_4r']=='t']
        rs=[f(r['realized_r']) for r in S]
        print(f"{rung:22s} {lvl:6s} n={len(S):3d} tail(realized>=4)={len(tails)} reached_4r={len(r4)} stops={sum(r['outcome']=='stop' for r in S)} other={C(r['outcome'] for r in S if r['outcome']!='stop')} sumR={sum(rs) if rs else 0:.2f} maxR={max(rs) if rs else None}")
print()
print('ALL rungs raw/screen')
for lvl in ['raw','screen']:
    S=[r for r in M if (lvl=='raw' or r['screen_member']=='t')]
    print(lvl,len(S),'tails',sum(f(r['realized_r'])>=4 for r in S),'reached4',sum(r['reached_4r']=='t' for r in S),'first-only',sum(r['reentry_shape']=='first' for r in S))
print()
for r in sorted(M,key=lambda r:-f(r['realized_r'])):
    print(r['ticker'],r['ep_date'],r['rung'],r['fire_date'],r['reentry_shape'],r['screen_member'],r['outcome'],r['realized_r'],'trail',r['realized_r_trail'],'mfe',r['mfe_r'],'r4',r['reached_4r'],'075',r['realized_r_075'],r['reached_4r_075'],'100',r['realized_r_100'],r['reached_4r_100'])
print()
print('created lag days (created - fire):',C((dt.date.fromisoformat(r['created_et'][:10])-dt.date.fromisoformat(r['fire_date'])).days for r in M))
print('non-mature rows by fire_date month:',C((r['fire_date'][:7], r['outcome'] or 'OPEN') for r in rows if not mature(r)))
print()
print('=== ERA SPLITS by ep_date (08-29, 09-14) and extras ===')
def era(r):
    e=r['ep_date']
    return 'a:<08-29' if e<'2026-08-29' else ('b:08-29..09-13' if e<'2026-09-14' else 'c:>=09-14')
for lvl in ['raw','screen','first','screen_false','screen_null']:
  for rung in sorted({r['rung'] for r in M})+['ALL']:
    for e in ['a:<08-29','b:08-29..09-13','c:>=09-14','pooled']:
        S=[r for r in M if (rung=='ALL' or r['rung']==rung) and (e=='pooled' or era(r)==e)]
        if lvl=='screen': S=[r for r in S if r['screen_member']=='t']
        if lvl=='screen_false': S=[r for r in S if r['screen_member']=='f']
        if lvl=='screen_null': S=[r for r in S if r['screen_member']=='']
        if lvl=='first': S=[r for r in S if r['reentry_shape']=='first']
        t=sum(f(r['realized_r'])>=4 for r in S)
        rs=[f(r['realized_r']) for r in S]
        camp=len({(r['ticker'],r['ep_date']) for r in S})
        tc=len({(r['ticker'],r['ep_date']) for r in S if f(r['realized_r'])>=4})
        print(f"{lvl:12s} {rung:20s} {e:16s} n={len(S):3d} tails={t} rate={(100*t/len(S) if S else 0):5.1f}% camps={camp} tailcamps={tc} sumR={sum(rs):+.1f} meanR={(sum(rs)/len(rs) if rs else 0):+.3f}")
# mature but unsettled
U=[r for r in rows if mature(r) and r['realized_r']=='']
print('mature unsettled:',len(U),[(r['ticker'],r['fire_date'],r['rung'],r['outcome']) for r in U])
print('versions among mature:',C((r['pattern_version'],r['screen_version'],r['settle_version']) for r in M))
# wilson/exact upper bounds
from math import comb
def cp(k,n,a=0.05):
    # clopper-pearson via bisection
    def cdf(p,k): return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
    lo=0.0
    if k>0:
        l,h=0,1
        for _ in range(60):
            m=(l+h)/2
            if 1-cdf(m,k-1)<a/2: l=m
            else: h=m
        lo=l
    l,h=0,1
    for _ in range(60):
        m=(l+h)/2
        if cdf(m,k)>a/2: l=m
        else: h=m
    return lo,l
for lab,k,n in [(lab,sum(f(r['realized_r'])>=4 for r in S),len(S)) for lab,S in
    [(f"{lvl}/{rung}",[r for r in M if (rung=='ALL' or r['rung']==rung) and (lvl=='raw' or r['screen_member']=='t')]) for lvl in ['raw','screen'] for rung in sorted({r['rung'] for r in M})+['ALL']]]:
    if n: print(lab,k,n,'95%% CI %.1f%%..%.1f%%'%tuple(100*x for x in cp(k,n)))
