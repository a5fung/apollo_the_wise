import csv, statistics as st, random, itertools
rows=list(csv.DictReader(open('q20_rows.csv')))
print('raw rows',len(rows))
seen={}; 
for r in rows:
    k=(r['alert_date'],r['ticker'],r['primary_model'],r['secondary_model'])
    seen.setdefault(k,[]).append(r)
dups={k:v for k,v in seen.items() if len(v)>1}
print('dup keys',len(dups), [ (k,[x['ep_score'] for x in v]) for k,v in dups.items()])
rows=[v[0] for v in seen.values()]   # dedupe join fan-out (mi_ep_alerts)
print('deduped',len(rows))
def f(x): return float(x) if x not in ('',None) else None
for r in rows:
    r['agree']=r['agree']=='t'; r['f5']=f(r['fwd_5d_pct']); r['f10']=f(r['fwd_10d_pct'])
def pair(r): return (r['primary_model'],r['secondary_model'])
def summ(label, sel):
    for ag in (False,True):
        xs=[r['f5'] for r in sel if r['agree']==ag and r['f5'] is not None]
        ys=[r['f10'] for r in sel if r['agree']==ag and r['f10'] is not None]
        if xs: print(f"{label:34s} agree={ag!s:5} n5={len(xs):3d} mean5={st.mean(xs):6.2f} med5={st.median(xs):6.2f} win5(>0)={sum(x>0 for x in xs)/len(xs):.2f} | n10={len(ys):3d} mean10={st.mean(ys):6.2f} med10={st.median(ys):6.2f}")
summ('POOLED all pairs', rows)
summ('opus-4-8/sonnet-4-6', [r for r in rows if pair(r)==('claude-opus-4-8','claude-sonnet-4-6')])
summ('opus-5/sonnet-5', [r for r in rows if pair(r)==('claude-opus-5','claude-sonnet-5')])
summ('opus-5-class + sonnet-5-class (any)', [r for r in rows if r['primary_model'].startswith('claude-opus-5') and r['secondary_model'].startswith('claude-sonnet-5')])
# Mann-Whitney & bootstrap on pooled 5d
def mwu(a,b):
    # exact-ish via normal approx with tie correction
    import math
    n1,n2=len(a),len(b); allv=sorted([(v,0) for v in a]+[(v,1) for v in b])
    ranks={}; i=0
    vals=[v for v,_ in allv]
    rk=[0]*len(allv)
    while i<len(allv):
        j=i
        while j+1<len(allv) and allv[j+1][0]==allv[i][0]: j+=1
        for k in range(i,j+1): rk[k]=(i+j)/2+1
        i=j+1
    R1=sum(rk[k] for k in range(len(allv)) if allv[k][1]==0)
    U1=R1-n1*(n1+1)/2; mu=n1*n2/2
    # tie-corrected variance
    from collections import Counter
    c=Counter(vals); N=n1+n2
    tie=sum(t**3-t for t in c.values())
    var=n1*n2/12*((N+1)-tie/(N*(N-1)))
    z=(U1-mu)/math.sqrt(var); p=math.erfc(abs(z)/math.sqrt(2))
    return U1,z,p
for label,sel in (('POOLED',rows),('opus-5/sonnet-5',[r for r in rows if pair(r)==('claude-opus-5','claude-sonnet-5')])):
    for k in ('f5','f10'):
        a=[r[k] for r in sel if not r['agree'] and r[k] is not None]; b=[r[k] for r in sel if r['agree'] and r[k] is not None]
        U,z,p=mwu(a,b)
        random.seed(1); diffs=[]
        for _ in range(5000):
            sa=[random.choice(a) for _ in a]; sb=[random.choice(b) for _ in b]
            diffs.append(st.mean(sa)-st.mean(sb))
        diffs.sort()
        print(f"{label} {k}: disagreed n={len(a)} vs agreed n={len(b)}  mean diff={st.mean(a)-st.mean(b):+.2f}  boot95=[{diffs[125]:+.2f},{diffs[4875]:+.2f}]  MWU p={p:.3f}")
# disagreed over time
print('disagreed HIGH dates:', sorted(r['alert_date'] for r in rows if not r['agree']))
# ep_score band: disagreed vs agreed
for ag in (False,True):
    es=[float(r['ep_score']) for r in rows if r['agree']==ag and r['ep_score']]
    print('ep_score agree=',ag,'n',len(es),'mean',round(st.mean(es),1))
