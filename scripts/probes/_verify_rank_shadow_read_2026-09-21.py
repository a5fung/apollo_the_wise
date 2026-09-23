import csv, statistics as st, collections
bars = collections.defaultdict(list)
for r in csv.reader(open('/tmp/rev4/bars.psv'), delimiter='|'):
    if len(r) < 6: continue
    bars[r[0]].append((r[1], float(r[2]), float(r[3]), float(r[4]), float(r[5])))
for t in bars: bars[t].sort()

rows=[]
for r in csv.reader(open('/tmp/rev4/shadow.psv'), delimiter='|'):
    if len(r)<9: continue
    tk, d, adr = r[0], r[1], float(r[2])
    filled = r[3]=='t'
    ce, pe, c9, p9 = float(r[5]), int(r[6]), float(r[7]), int(r[8])
    b = bars[tk]
    i = next(k for k,x in enumerate(b) if x[0]==d)
    fwd = b[i:]                      # d0 onward
    sess = len(fwd)
    open0, low0 = fwd[0][1], fwd[0][3]
    w5, w20 = fwd[:6], fwd[:21]      # module: trade_date >= alert_date LIMIT 6 / 21
    mh5 = (max(x[2] for x in w5)-open0)/open0
    mh20 = (max(x[2] for x in w20)-open0)/open0
    post5 = fwd[1:6]
    minlow = min(x[3] for x in post5) if post5 else None
    rows.append(dict(tk=tk,d=d,adr=adr,filled=filled,ce=ce,pe=pe,c9=c9,p9=p9,
                     sess=sess,open0=open0,low0=low0,mh5=mh5,mh20=mh20,
                     x5=mh5/adr, x20=mh20/adr,
                     loser=(minlow is not None and minlow < low0)))

print("POPULATION (re-derived): rows=%d sessions=%d filled=%d" % (
    len(rows), len({r['d'] for r in rows}), sum(r['filled'] for r in rows)))
print("5d-matured (sess>=6): %d   20d-matured (sess>=21): %d" % (
    sum(1 for r in rows if r['sess']>=6), sum(1 for r in rows if r['sess']>=21)))
BAR=8.0; TOL=1e-9
def rep(tag,key,mat,xk):
    pop=[r for r in rows if r['sess']>=mat]
    top=[r for r in pop if r[key]<=0.25+TOL]; rest=[r for r in pop if r[key]>0.25+TOL]
    print("\n== %s == scored n=%d" % (tag,len(pop)))
    for nm,c in (("TOP<=0.25",top),("REST",rest)):
        if not c: print("  %s: n=0"); continue
        w=sum(1 for r in c if r[xk]>=BAR); l=sum(1 for r in c if r['loser'])
        xs=sorted(r[xk] for r in c)
        print("  %-9s n=%2d  tail>=8x %d/%d  brokeLow %d/%d  median %.2fx  best %.2fx (%s)" % (
            nm,len(c),w,len(c),l,len(c),st.median(xs),max(xs),
            max(c,key=lambda r:r[xk])['tk']))
rep("EOD 5d","ce",6,"x5"); rep("EOD 20d","ce",21,"x20")
rep("0945 5d","c9",6,"x5"); rep("0945 20d","c9",21,"x20")
print("\nTOP x5 (matured):")
for r in sorted([r for r in rows if r['sess']>=6], key=lambda r:-r['x5'])[:6]:
    print("  %-5s %s x5=%.2f x20=%.2f filled=%s ce=%.4f pool=%d" % (r['tk'],r['d'],r['x5'],r['x20'],r['filled'],r['ce'],r['pe']))
print("\nTOP x5 EXCLUDING filled (what the old missed-outcomes population saw):")
for r in sorted([r for r in rows if r['sess']>=6 and not r['filled']], key=lambda r:-r['x5'])[:4]:
    print("  %-5s %s x5=%.2f x20=%.2f" % (r['tk'],r['d'],r['x5'],r['x20']))
print("\nTOP x20 EXCLUDING filled, 20d-matured-or-not (old run's read):")
for r in sorted([r for r in rows if not r['filled']], key=lambda r:-r['x20'])[:4]:
    print("  %-5s %s x20=%.2f sess=%d" % (r['tk'],r['d'],r['x20'],r['sess']))
print("\nMRNA detail:")
m=[r for r in rows if r['tk']=='MRNA'][0]
print("  open0=%.2f low0=%.2f mh5=%.16f mh20=%.16f adr=%.16f x5=%.4f" % (m['open0'],m['low0'],m['mh5'],m['mh20'],m['adr'],m['x5']))
print("\nrecomputed mh5/mh20 for all rows (for stored-vs-recompute compare):")
for r in sorted(rows,key=lambda r:(r['d'],r['tk'])):
    print("  CMP|%s|%s|%.17g|%.17g|%d" % (r['tk'],r['d'],r['mh5'],r['mh20'],r['sess']))

print("\n=== ALTERNATIVE CUT: in-sample style top-25% BY RANK ORDER (int(round(0.25*n))) ===")
for tag,key,mat,xk in (("EOD 5d","ce",6,"x5"),("0945 5d","c9",6,"x5"),("EOD 20d","ce",21,"x20")):
    pop=sorted([r for r in rows if r['sess']>=mat], key=lambda r:r[key])
    k=int(round(0.25*len(pop))); top=pop[:k]; rest=pop[k:]
    def s(c,xk):
        return "n=%d tail>=8x %d brokeLow %d median %.2fx" % (len(c),sum(1 for r in c if r[xk]>=8.0),sum(1 for r in c if r['loser']),st.median([r[xk] for r in c]))
    print("  %-8s TOP-25%%  %s | REST %s | members: %s" % (tag, s(top,xk), s(rest,xk), ",".join(r['tk'] for r in top)))
