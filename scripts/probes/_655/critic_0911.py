"""Critic: the brief's known-broken 09-11 board — what do the reads (and the guard) say about it?"""
import sys
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import market_adjusted_correlation as mac
H=Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_655"); d_=date.fromisoformat
hist=[]
for ln in open(H/"funnel_themes_hist.psv"):
    p=ln.rstrip("\n").split("|"); hist.append({"id":int(p[0]),"date":d_(p[1]),"name":p[2],"stage":p[3],"tickers":[t for t in p[4].split(",") if t]})
D=date(2026,9,11)
latest={}
for r in hist:
    if D-timedelta(days=7)<=r["date"]<=D and (r["name"] not in latest or r["date"]>latest[r["name"]]["date"]): latest[r["name"]]=r
board=[r for r in latest.values() if r["stage"]!="Retired"]
sz=Counter(len(r["tickers"]) for r in board)
print(f"09-11 board: {len(board)} themes; empty {sz.get(0,0)}; at 2 {sz.get(2,0)}; <=5 {sum(v for k,v in sz.items() if k<=5)} ({100*sum(v for k,v in sz.items() if k<=5)/len(board):.0f}%)")
closes=defaultdict(dict)
for ln in open(H/"funnel_closes.psv"):
    t,d,c=ln.rstrip("\n").split("|")
    if c: closes[t][d_(d)]=float(c)
sess=mac.session_index(closes["SPY"],D+timedelta(days=1)); ex=mac.excess_returns(closes,sess,mac.log_returns(closes["SPY"],sess))
slots=judg=ok=0; nojudge=0; empty_in_denominator=0
for th in board:
    slots+=len(th["tickers"]); any_=False
    bs=mac.build_baskets([{"name":th["name"],"stage":"X","tickers":th["tickers"]}],ex,("X",))
    if bs:
        for m in bs[0].members:
            c,_,_=mac.correlate(ex[m],bs[0],exclude=m)
            if c is not None: judg+=1; ok+=c>=0.35; any_=True
    nojudge+= not any_
print(f"#1 all judgeable {ok}/{judg} = {100*ok/judg:.1f}% (bar 90%) | GUARD {judg}/{slots} = {100*judg/slots:.1f}% (bar 80%) | themes with no judgeable member {nojudge}/{len(board)}")
print(f"empty themes contribute 0 slots to the guard and 0 members to #1/#2, and have no basket for #3/#4 -> invisible to every grouping read: {sz.get(0,0)}")
bk={}
for th in board:
    b=mac.build_baskets([{"name":th["name"],"stage":"X","tickers":th["tickers"]}],ex,("X",),min_members=2)
    if b: bk[th["name"]]=(b[0].mean_all,set(th["tickers"]))
def vc(a,b):
    m=np.isfinite(a)&np.isfinite(b); return float(np.corrcoef(a[m],b[m])[0,1]) if m.sum()>=30 else None
nm=sorted(bk); dup=0
for i,a in enumerate(nm):
    for b in nm[i+1:]:
        c=vc(bk[a][0],bk[b][0])
        if c is not None and c>=0.70 and len(bk[a][1]&bk[b][1])/min(len(bk[a][1]),len(bk[b][1]))>=0.5: dup+=1
print(f"#4 duplicate pairs on 09-11: {dup}")
