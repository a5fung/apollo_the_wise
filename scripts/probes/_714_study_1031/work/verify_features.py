# independent re-computation (plain python loops, own parser) of NP/NV/NA/ADV for 4 rows, compared with s2_read's numbers
import gzip, re, statistics, collections
want = {("ABNB","2026-08-07"),("CHPT","2026-09-03"),("MRNA","2026-08-19"),("TEAM","2026-08-07")}
bars = collections.defaultdict(dict)
cur=None; hdr=None
for line in gzip.open('out/30_daily_bars.out.gz','rt'):
    line=line.rstrip('\n')
    if line.startswith('==='): cur=line[4:]; hdr=None; continue
    if hdr is None: hdr=line.split('|'); continue
    if re.fullmatch(r'\(\d+ rows?\)',line) or not line: continue
    t,d,o,h,l,c,v=line.split('|')
    if t in {w[0] for w in want}:
        bars[t][d]=(float(h) if h else None,float(l) if l else None,float(c) if c else None,float(v) if v else None)
for tk,D in sorted(want):
    ds=sorted(d for d in bars[tk] if d<D)
    w=ds[-504:]
    c=[bars[tk][d][2] for d in w]; v=[bars[tk][d][3] for d in w]
    # NP
    runmin=1e18; mr=0
    for x in c:
        runmin=min(runmin,x); mr=max(mr,(x/runmin-1)*100)
    # NV
    mean504=sum(v)/len(v); v250=v[-250:]; nv=sum(1 for x in v250 if x<mean504)/250
    # NA (rolling 60-session prior median)
    allv=[bars[tk][d][3] for d in ds]; allc=[bars[tk][d][2] for d in ds]
    ev=[]
    for i in range(len(ds)-504,len(ds)):
        prev=allv[i-60:i]
        med=statistics.median(prev)
        r=abs(allc[i]/allc[i-1]-1)
        ev.append(allv[i]>=3*med and r>=0.05)
    na=sum(ev[-250:]); 
    adv=sum(allc[i]*allv[i] for i in range(len(ds)-20,len(ds)))/20
    print(tk,D,f"NP={mr:.2f} NV={nv:.3f} NA={na} ADV20={adv:,.0f}")
