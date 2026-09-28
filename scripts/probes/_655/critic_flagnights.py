"""Critic: with the #491 cohort excluded (i.e. a system where #491 is FIXED), on how many nights would #5 (v2, bar 0) still fail?"""
import re, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import market_adjusted_correlation as mac
H=Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_655"); d_=date.fromisoformat
closes=defaultdict(dict)
for ln in open(H/"funnel_closes.psv"):
    t,d,c=ln.rstrip("\n").split("|")
    if c: closes[t][d_(d)]=float(c)
hist=[]
for ln in open(H/"funnel_themes_hist.psv"):
    p=ln.rstrip("\n").split("|"); hist.append({"date":d_(p[1]),"name":p[2],"stage":p[3],"tickers":[t for t in p[4].split(",") if t]})
def board_at(d):
    latest={}
    for r in hist:
        if d-timedelta(days=7)<=r["date"]<=d and (r["name"] not in latest or r["date"]>latest[r["name"]]["date"]): latest[r["name"]]=r
    return [r for r in latest.values() if r["stage"]!="Retired" and r["tickers"]]
V1=[(r"bitcoin|crypto|\bbtc\b|digital asset","IBIT"),(r"gold|precious","GLD"),(r"silver","SLV"),(r"uranium","URA"),(r"copper","COPX"),(r"crude|\boil\b|tanker|petroleum","USO")]
V2=[(r"bitcoin|crypto|\bbtc\b|digital asset","IBIT"),(r"gold|silver|precious","GLD|SLV"),(r"uranium","URA"),(r"copper","COPX"),(r"crude|\boil\b|petroleum","USO")]
def dv1(n):
    for rx,px in V1:
        if re.search(rx,n,re.I): return px
def dv2(n):
    if re.search(r"pivot|conver|diversif|transition",n,re.I): return None
    for rx,px in V2:
        if re.search(rx,n,re.I): return px
def vc(a,b):
    m=np.isfinite(a)&np.isfinite(b)
    if m.sum()<30 or a[m].std()<1e-12 or b[m].std()<1e-12: return None
    return float(np.corrcoef(a[m],b[m])[0,1])
MINERS={"HUT","IREN","CIFR","CORZ","WULF","CLSK","BTDR","APLD","RIOT","MARA","IOND","ABTC"}
dates=sorted({r["date"] for r in hist if r["date"]>=date(2026,5,4)})
nights=0; bad_nights=0; flags=0; tn=0; per=[]
for d in dates:
    b_=board_at(d); sess=mac.session_index(closes["SPY"],d+timedelta(days=1)); ex=mac.excess_returns(closes,sess,mac.log_returns(closes["SPY"],sess))
    lb={}
    for r in b_:
        bs=mac.build_baskets([{"name":r["name"],"stage":"X","tickers":r["tickers"]}],ex,("X",))
        if bs: lb[r["name"]]=bs[0]
    nf=0
    for th in b_:
        px=dv2(th["name"])
        if not px or len(set(th["tickers"])&MINERS)>=2: continue
        bs=mac.build_baskets([{"name":th["name"],"stage":"X","tickers":th["tickers"]}],ex,("X",),min_members=2)
        if not bs: continue
        mean=bs[0].mean_all; vals=[vc(mean,ex[p]) for p in px.split("|") if p in ex]; vals=[v for v in vals if v is not None]
        if not vals: continue
        dfit=max(vals); best=None
        for n2,b2 in lb.items():
            if n2==th["name"] or dv2(n2)==px or dv1(n2)==(px if "|" not in px else "GLD") or (px=="GLD|SLV" and dv1(n2)=="SLV") or set(b2.members)&set(th["tickers"]): continue
            c=vc(mean,b2.mean_all)
            if c is not None and (best is None or c>best): best=c
        tn+=1
        if best is not None and best-dfit>=0.15: nf+=1
    nights+=1; flags+=nf; bad_nights+= nf>0; per.append((d,nf))
print(f"board nights since 05-04: {nights}; non-#491 priced-driver theme-nights {tn}, flagged {flags} ({100*flags/max(tn,1):.0f}%)")
print(f"nights on which #5 (bar 0) FAILS with the #491 cohort removed: {bad_nights} of {nights} ({100*bad_nights/nights:.0f}%)")
print("last 20 nights:", " ".join(f"{d.strftime('%m-%d')}:{n}" for d,n in per[-20:]))
