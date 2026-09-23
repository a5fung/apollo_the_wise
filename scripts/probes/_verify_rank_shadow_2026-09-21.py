import csv, statistics as st
F=lambda s: None if s=="" else float(s)
rows=[]
for r in csv.reader(open("/tmp/rev4_calc.psv"),delimiter="|"):
    rows.append(dict(tk=r[0],date=r[1],adr=F(r[2]),filled=r[3]=="t",tier=r[4],
        ce=F(r[5]),pe=int(r[6]),c9=F(r[7]),p9=int(r[8]),open0=F(r[9]),low0=F(r[10]),
        sess=int(r[11]),h5=F(r[12]),h20=F(r[13]),minlow=F(r[14])))
for r in rows:
    r["mh5"]=(r["h5"]-r["open0"])/r["open0"] if r["h5"] and r["open0"] else None
    r["mh20"]=(r["h20"]-r["open0"])/r["open0"] if r["h20"] and r["open0"] else None
    r["x5"]=r["mh5"]/r["adr"] if r["mh5"] is not None and r["adr"] else None
    r["x20"]=r["mh20"]/r["adr"] if r["mh20"] is not None and r["adr"] else None
    r["loser"]= r["minlow"] is not None and r["low0"] is not None and r["minlow"]<r["low0"]
print("rows",len(rows),"sessions",len({r['date'] for r in rows}),"filled",sum(r['filled'] for r in rows))
print("5d-matured(sess>=6)",sum(1 for r in rows if r['sess']>=6),"20d-matured(sess>=21)",sum(1 for r in rows if r['sess']>=21))
BAR=8.0; TOL=1e-9
def rep(tag,key,pk,mm,xk):
    pop=[r for r in rows if r['sess']>=mm and r[xk] is not None]
    top=[r for r in pop if r[key]<=0.25+TOL]; rest=[r for r in pop if r[key]>0.25+TOL]
    print(f"\n== {tag} == pop n={len(pop)}")
    for nm,c in (("TOP",top),("REST",rest)):
        if not c: print(f"  {nm}: n=0"); continue
        w=sum(1 for r in c if r[xk]>=BAR); l=sum(1 for r in c if r['loser'])
        xs=sorted(r[xk] for r in c)
        print(f"  {nm}: n={len(c)} tail>={BAR}x: {w}/{len(c)} brokeLow: {l}/{len(c)} median {st.median(xs):.4f}x best {max(xs):.4f}x")
rep("EOD 5d","ce","pe",6,"x5"); rep("EOD 20d","ce","pe",21,"x20")
rep("0945 5d","c9","p9",6,"x5"); rep("0945 20d","c9","p9",21,"x20")
m=[r for r in rows if r['tk']=='MRNA'][0]
print(f"\nMRNA x5={m['x5']:.6f} x20={m['x20']:.6f} mh5={m['mh5']!r} mh20={m['mh20']!r} rank_eod={m['ce']} pool={m['pe']}")
t=[r for r in rows if r['tk']=='TEM'][0]; print("TEM mh5 recomputed:",repr(t['mh5']),"mh20:",repr(t['mh20']))
q=[r for r in rows if r['tk']=='QCOM'][0]; print("QCOM mh5:",repr(q['mh5']),"mh20:",repr(q['mh20']))
# single-alert days
from collections import Counter
c=Counter(r['date'] for r in rows); print("\nsessions with exactly 1 alert:",sum(1 for d,n in c.items() if n==1), sorted(d for d,n in c.items() if n==1))
print("rows with pool_eod==1 among 5d-matured:",sum(1 for r in rows if r['sess']>=6 and r['pe']==1))
