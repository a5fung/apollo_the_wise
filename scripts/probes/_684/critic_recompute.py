#!/usr/bin/env python3
"""#684 CRITIC recompute — reads critic_rows.txt (independent server-side outcome) + outcomes.tsv; writes nothing. Output captured in critic_recompute_out.txt."""
import csv, datetime as dt, random
from collections import defaultdict
H='/Users/alvinfung/apollo_the_wise/scripts/probes/_684/'
def load(p):
    L=[l.rstrip('\n') for l in open(p) if l.strip() and not l.startswith(('Output format','Field separator'))]
    hdr=L[0].split('|'); return [dict(zip(hdr,l.split('|'))) for l in L[1:]]
R=load(H+'critic_rows.txt')
f=lambda x: float(x) if x not in ('',None) else None
for r in R:
    for k in ('score','o0','c0','adr20','dv20','prev_close_adj','maxh15','range20_abs','min5_close'): r[k]=f(r[k])
    r['n_fwd']=int(r['n_fwd']); r['alerted']=r['alerted']=='t'
    r['run']=None
    if r['c0'] and r['adr20'] and r['n_fwd']==15 and r['maxh15'] is not None:
        r['run']=(r['maxh15']-r['c0'])/(r['adr20']*r['c0'])
    y,w,_=dt.date.fromisoformat(r['scan_date']).isocalendar(); r['wk']=f'{y}-W{w:02d}'
    r['block']='D' if r['scan_date']<='2026-08-14' else 'H'
S=[r for r in R if r['run'] is not None and r['ticker']+r['scan_date'] not in ('AVEX2026-05-12','CHRN2026-05-28','BRUN2026-05-29')]
print('rows',len(R),'with outcome',len(S),'censored',[ (r['ticker'],r['scan_date'],r['n_fwd']) for r in R if r['run'] is None])
run5=lambda r:int(r['run']>=5)
print('runners>=5',sum(map(run5,S)),'>=8',sum(r['run']>=8 for r in S))
al=[r for r in S if r['alerted']]; na=[r for r in S if not r['alerted']]
print('alerted',sum(map(run5,al)),len(al),' not',sum(map(run5,na)),len(na))
# compare to study outcomes
O={(o['ticker'],o['scan_date']):o for o in csv.DictReader(open(H+'outcomes.tsv'),delimiter='\t')}
diffs=[(r['ticker'],r['scan_date'],round(r['run'],3),O[(r['ticker'],r['scan_date'])]['run_xadr']) for r in S if abs(r['run']-float(O[(r['ticker'],r['scan_date'])]['run_xadr']))>0.01]
print('outcome mismatches >0.01 ADR vs study:',len(diffs),diffs[:10])
lab_mis=[(r['ticker'],r['scan_date']) for r in S if run5(r)!=int(O[(r['ticker'],r['scan_date'])]['runner5'])]
print('runner label mismatches',lab_mis)
# chosen tick times
from collections import Counter
print('chosen tick time buckets', Counter(('pre0930' if r['chosen_hhmm']<'09:30' else '0930-0944' if r['chosen_hhmm']<'09:45' else '0945+') for r in R))
print('chosen tick time buckets, alerted', Counter(('pre0930' if r['chosen_hhmm']<'09:30' else '0930-0944' if r['chosen_hhmm']<'09:45' else '0945+') for r in R if r['alerted']))
print('chosen tick time buckets, not alerted', Counter(('pre0930' if r['chosen_hhmm']<'09:30' else '0930-0944' if r['chosen_hhmm']<'09:45' else '0945+') for r in R if not r['alerted']))
import random, statistics as st
from collections import defaultdict, Counter
EX={('AVEX','2026-05-12'),('CHRN','2026-05-28'),('BRUN','2026-05-29')}
S=[r for r in R if (r['ticker'],r['scan_date']) not in EX]
for r in S:
    r['y']=int(r['run']>=5); r['pct']=(r['maxh15']/r['c0']-1)*100; r['y25']=int(r['pct']>=25)
    r['adrpct']=r['adr20']*100
    r['range20']=r['range20_abs']/r['prev_close_adj']*100
    r['ext5']=(r['prev_close_adj']/r['min5_close']-1)*100
D=[r for r in S if r['block']=='D']; Hh=[r for r in S if r['block']=='H']
print('first pass time buckets (alerted):',Counter(('pre0930' if r['first_pass_hhmm']<'09:30' else '0930-0944' if r['first_pass_hhmm']<'09:45' else '0945+') for r in R if r['alerted']))
def cuts(v):
    s=sorted(v); n=len(s); return s[max(0,n//3-1)], s[min(n-1,(2*n)//3)]
def perm(lab,fav,wk,obs,rng,N=5000):
    g=defaultdict(list)
    for i,w in enumerate(wk): g[w].append(i)
    hits=0; L=list(lab)
    for _ in range(N):
        for idx in g.values():
            v=[lab[i] for i in idx]; rng.shuffle(v)
            for i,x in zip(idx,v): L[i]=x
        a=[l for l,f in zip(L,fav) if f]; b=[l for l,f in zip(L,fav) if not f]
        if sum(a)/len(a)-sum(b)/len(b)>=obs-1e-12: hits+=1
    return hits/N
def test(name,key,lower,rows=D,held=Hh,y='y',seed=1):
    dr=[r for r in rows if r.get(key) is not None]; lo,hi=cuts([r[key] for r in dr])
    fm=[(r[key]<=lo) if lower else (r[key]>=hi) for r in dr]
    lab=[r[y] for r in dr]
    a=[l for l,f in zip(lab,fm) if f]; b=[l for l,f in zip(lab,fm) if not f]
    obs=sum(a)/len(a)-sum(b)/len(b)
    p=perm(lab,fm,[r['wk'] for r in dr],obs,random.Random(seed))
    hr=[r for r in held if r.get(key) is not None]; hm=[(r[key]<=lo) if lower else (r[key]>=hi) for r in hr]
    ha=[r[y] for r,f in zip(hr,hm) if f]; hb=[r[y] for r,f in zip(hr,hm) if not f]
    print(f"{name}: cut {'<=' if lower else '>='} {lo if lower else hi:.4g} | disc fav {sum(a)}/{len(a)}={100*sum(a)/len(a):.1f}% vs rest {sum(b)}/{len(b)}={100*sum(b)/len(b):.1f}% diff {100*obs:+.1f}pp perm p {p:.3f} | held fav {sum(ha)}/{len(ha)} vs rest {sum(hb)}/{len(hb)}")
    return lo,hi
print('--- recompute (own code, seed differs, 5000 perms) ---')
test('20d dollar volume LOWER','dv20',True)
test('EP score HIGHER','score',False)
test('ADR% HIGHER','adrpct',False)
print('--- the reversed "already moving" leads, stated as the doc states them (opposite third vs rest) ---')
test('20d close range/price WIDEST third','range20',False)
test('20d close range/price TIGHTEST third (the registered draw)','range20',True)
test('prev close above 5d low, FURTHEST third','ext5',False)
test('prev close above 5d low, LEAST third (the registered draw)','ext5',True)
# overlap with ADR%
lo,hi=cuts([r['adrpct'] for r in D]); lo2,hi2=cuts([r['range20'] for r in D])
top_adr={id(r) for r in D if r['adrpct']>=hi}; wide={id(r) for r in D if r['range20']>=hi2}
print(f'overlap: widest-range third {len(wide)}, top-ADR% third {len(top_adr)}, both {len(wide&top_adr)}; spearman-ish corr:')
def rk(v):
    s=sorted(range(len(v)),key=lambda i:v[i]); o=[0]*len(v)
    for k,i in enumerate(s): o[i]=k
    return o
def sp(x,y):
    a,b=rk(x),rk(y); ma,mb=st.mean(a),st.mean(b)
    return sum((p-ma)*(q-mb) for p,q in zip(a,b))/(sum((p-ma)**2 for p in a)*sum((q-mb)**2 for q in b))**0.5
print('  spearman range20 vs ADR%', round(sp([r['range20'] for r in D],[r['adrpct'] for r in D]),3), ' ext5 vs ADR%', round(sp([r['ext5'] for r in D],[r['adrpct'] for r in D]),3), ' dv20 vs ADR%', round(sp([r['dv20'] for r in D],[r['adrpct'] for r in D]),3))
# range in ADR units (strip volatility)
for r in S: r['range20_xadr']=r['range20']/r['adrpct']; r['ext5_xadr']=r['ext5']/r['adrpct']
test('20d range in ADR units, WIDEST third','range20_xadr',False)
test('20d range in ADR units, TIGHTEST third','range20_xadr',True)
test('ext off 5d low in ADR units, FURTHEST third','ext5_xadr',False)
# within ADR% terciles
print('--- widest-range-third vs rest WITHIN each ADR% tercile (discovery) ---')
for nm,cond in (('low ADR%',lambda r:r['adrpct']<=lo),('mid ADR%',lambda r:lo<r['adrpct']<hi),('high ADR%',lambda r:r['adrpct']>=hi)):
    g=[r for r in D if cond(r)]; a=[r['y'] for r in g if r['range20']>=hi2]; b=[r['y'] for r in g if r['range20']<hi2]
    print(f'  {nm}: n {len(g)} wide {sum(a)}/{len(a)} vs rest {sum(b)}/{len(b)}')
print('--- percent label (peak >= 25% from the close) ---')
test('ADR% HIGHER, %-label','adrpct',False,y='y25')
test('20d range WIDEST third, %-label','range20',False,y='y25')
test('dollar volume LOWER, %-label','dv20',True,y='y25')
print('runners >=5 ADR by ISO week and share in W19:',sum(r['y'] for r in D if r['wk']=='2026-W19'),'of',sum(r['y'] for r in D))
# overlapping same-ticker runner windows
byT=defaultdict(list)
for r in S:
    if r['y']: byT[r['ticker']].append(r['scan_date'])
print('tickers with >1 runner row:',{k:v for k,v in byT.items() if len(v)>1})
