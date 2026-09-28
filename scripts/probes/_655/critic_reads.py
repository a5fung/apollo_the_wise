"""Critic: re-run #1 (member fit), #4 (duplicates), #6 (names settled) + the guard on today's board, independently."""
import sys, statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import market_adjusted_correlation as mac
H = Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_655"); d_=date.fromisoformat
closes=defaultdict(dict)
for ln in open(H/"funnel_closes.psv"):
    t,d,c=ln.rstrip("\n").split("|")
    if c: closes[t][d_(d)]=float(c)
board=[]
for ln in open(H/"funnel_live_board.psv"):
    p=ln.rstrip("\n").split("|"); board.append({"date":d_(p[0]),"name":p[1],"stage":p[2],"tickers":[t for t in p[4].split(",") if t]})
sess=mac.session_index(closes["SPY"],date(2026,9,26)); ex=mac.excess_returns(closes,sess,mac.log_returns(closes["SPY"],sess))
# #1 + guard
slots=judg=ok=0; nojudge=0
for th in board:
    bs=mac.build_baskets([{"name":th["name"],"stage":"X","tickers":th["tickers"]}],ex,("X",))
    slots+=len(th["tickers"]); any_=False
    if bs:
        for m in bs[0].members:
            c,_,_=mac.correlate(ex[m],bs[0],exclude=m)
            if c is not None: judg+=1; ok+=c>=0.35; any_=True
    nojudge+= not any_
print(f"#1 all judgeable: {ok}/{judg} = {100*ok/judg:.1f}% | guard {judg}/{slots} = {100*judg/slots:.1f}% | themes with no judgeable member {nojudge}/{len(board)}")
# #4 duplicates: overlap >= half (of the smaller) AND basket tie >= 0.70
bk={}
for th in board:
    b=mac.build_baskets([{"name":th["name"],"stage":"X","tickers":th["tickers"]}],ex,("X",),min_members=2)
    if b: bk[th["name"]]=(b[0].mean_all,set(th["tickers"]),th["date"])
def vc(a,b):
    m=np.isfinite(a)&np.isfinite(b); return float(np.corrcoef(a[m],b[m])[0,1]) if m.sum()>=30 else None
names=sorted(bk); dup=[]; shard=0; shard_disjoint=[]
for i,a in enumerate(names):
    for b in names[i+1:]:
        c=vc(bk[a][0],bk[b][0]);
        if c is None or c<0.70: continue
        shard+=1; A,B=bk[a][1],bk[b][1]; ov=len(A&B)/min(len(A),len(B))
        if ov>=0.5: dup.append((round(c,2),round(ov,2),a[:40],str(bk[a][2]),b[:40],str(bk[b][2])))
        elif c>=0.90: shard_disjoint.append((round(c,2),round(ov,2),a[:45],b[:45]))
print(f"#4 pairs overlap>=half & tie>=0.70: {len(dup)}"); [print("   ",x) for x in sorted(dup,reverse=True)]
print(f"   shard pairs tie>=0.70: {shard}; of which tie>=0.90 and overlap<half (NOT counted by #4): {len(shard_disjoint)}")
for x in sorted(shard_disjoint,reverse=True): print("     ",x)
# #6 size bias
hist=[]
for ln in open(H/"funnel_themes_hist.psv"):
    p=ln.rstrip("\n").split("|"); hist.append({"date":d_(p[1]),"name":p[2],"stage":p[3],"tickers":[t for t in p[4].split(",") if t]})
shadow=[]
for ln in open(H/"funnel_shadow_candidates.psv"):
    p=ln.rstrip("\n").split("|"); shadow.append({"date":d_(p[0]),"name":p[1],"tickers":[t for t in p[2].split(",") if t]})
def cn(T,until=date(2026,9,25)):
    T=set(T); s=set()
    for r in hist:
        if until-timedelta(days=30)<=r["date"]<=until and r["stage"]!="Retired" and r["tickers"]:
            S=set(r["tickers"]); sh=len(S&T)
            if sh>=2 and sh/min(len(S),len(T))>=0.5: s.add(r["name"])
    for r in shadow:
        if until-timedelta(days=30)<=r["date"]<=until and r["tickers"]:
            S=set(r["tickers"]); sh=len(S&T)
            if sh>=2 and sh/min(len(S),len(T))>=0.5: s.add(r["name"])
    return s
res=[(len(cn(th["tickers"])),len(th["tickers"]),th["name"]) for th in board]
print(f"#6 >=4 names: {sum(r[0]>=4 for r in res)}/{len(res)}")
for lo,hi in ((2,3),(4,5),(6,9),(10,99)):
    sub=[r for r in res if lo<=r[1]<=hi]
    print(f"   size {lo}-{hi}: n={len(sub)} flagged(>=4 names) {sum(r[0]>=4 for r in sub)} ({100*sum(r[0]>=4 for r in sub)/max(1,len(sub)):.0f}%) median names {statistics.median(r[0] for r in sub)}")
