"""Critic: would #5 (named driver, v2) have flagged the miners when they were MOST bitcoin-linked? Fixed cohort, best-of-board competitor."""
import re, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import market_adjusted_correlation as mac
H = Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_655")
d_ = date.fromisoformat
closes = defaultdict(dict)
for ln in open(H/"funnel_closes.psv"):
    t,d,c = ln.rstrip("\n").split("|")
    if c: closes[t][d_(d)] = float(c)
hist=[]
for ln in open(H/"funnel_themes_hist.psv"):
    p=ln.rstrip("\n").split("|")
    hist.append({"date":d_(p[1]),"name":p[2],"stage":p[3],"tickers":[t for t in p[4].split(",") if t]})
def board_at(d):
    latest={}
    for r in hist:
        if d-timedelta(days=7)<=r["date"]<=d and (r["name"] not in latest or r["date"]>latest[r["name"]]["date"]): latest[r["name"]]=r
    return [r for r in latest.values() if r["stage"]!="Retired" and r["tickers"]]
DR=[(r"bitcoin|crypto|\bbtc\b|digital asset","IBIT"),(r"gold|silver|precious","GLD|SLV"),(r"uranium","URA"),(r"copper","COPX"),(r"crude|\boil\b|petroleum","USO")]
def drv(n):
    if re.search(r"pivot|conver|diversif|transition",n,re.I): return None
    for rx,px in DR:
        if re.search(rx,n,re.I): return px
def vc(a,b):
    m=np.isfinite(a)&np.isfinite(b)
    if m.sum()<30: return None
    return float(np.corrcoef(a[m],b[m])[0,1])
COH=["HUT","IREN","CIFR","CORZ","WULF","CLSK","BTDR","RIOT","MARA","ABTC"]
for bd in (date(2026,5,4),date(2026,5,15),date(2026,6,1),date(2026,7,1),date(2026,9,25)):
    sess=mac.session_index(closes["SPY"],bd+timedelta(days=1)); mk=mac.log_returns(closes["SPY"],sess); ex=mac.excess_returns(closes,sess,mk)
    rows=[ex[t] for t in COH if t in ex and mac.usable(ex[t],30)]
    mean=mac._basket_mean(np.vstack(rows),2)
    ib=vc(mean,ex["IBIT"])
    comp=[]
    for r in board_at(bd):
        if drv(r["name"])=="IBIT" or set(r["tickers"])&set(COH): continue
        bs=mac.build_baskets([{"name":r["name"],"stage":"X","tickers":r["tickers"]}],ex,("X",),min_members=3)
        if bs:
            c=vc(mean,bs[0].mean_all)
            if c is not None: comp.append((c,r["name"],len(bs[0].members)))
    comp.sort(reverse=True)
    top=comp[0]; n_over=sum(1 for c,_,_ in comp if c-ib>=0.15)
    # beta-equity control: best-of-board for the pure bitcoin-proxy equities (MSTR, COIN)
    pr=[ex[t] for t in ("MSTR","COIN") if t in ex]; pm=mac._basket_mean(np.vstack(pr),1)
    pib=vc(pm,ex["IBIT"])
    pc=max(((vc(pm,b.mean_all),b.name) for r in board_at(bd) if drv(r["name"])!="IBIT" and not set(r["tickers"])&{"MSTR","COIN"}
            for b in mac.build_baskets([{"name":r["name"],"stage":"X","tickers":r["tickers"]}],ex,("X",),min_members=3) if vc(pm,b.mean_all) is not None),default=(None,None))
    print(f"window before {bd+timedelta(days=1)} ({sess[1]}..{sess[-1]}): miners(10) ~IBIT {ib:.2f} | best other theme {top[0]:.2f} '{top[1][:45]}' [{top[2]}] | "
          f"FLAG={top[0]-ib>=0.15} | themes beating IBIT by >=0.15: {n_over} of {len(comp)} || MSTR+COIN ~IBIT {pib:.2f} vs best other {pc[0]:.2f} '{(pc[1] or '')[:30]}'")
print("\n--- the doc's proposed END STATE: the six converts leave, the bitcoin name stays on the 'true miners' — does #5 pass it? (window to 09-25, today's board) ---")
bd=date(2026,9,25); sess=mac.session_index(closes["SPY"],bd+timedelta(days=1)); mk=mac.log_returns(closes["SPY"],sess); ex=mac.excess_returns(closes,sess,mk)
for rem in (["ABTC","MARA","BTDR"],["ABTC","MARA","BTDR","CLSK","RIOT"],["ABTC","MARA","BTDR","CLSK","RIOT","IOND"]):
    mean=mac._basket_mean(np.vstack([ex[t] for t in rem if t in ex]),2); ib=vc(mean,ex["IBIT"])
    comp=[]
    for r in board_at(bd):
        if drv(r["name"])=="IBIT" or set(r["tickers"])&set(rem): continue
        for b in mac.build_baskets([{"name":r["name"],"stage":"X","tickers":r["tickers"]}],ex,("X",),min_members=3):
            c=vc(mean,b.mean_all)
            if c is not None: comp.append((c,r["name"]))
    comp.sort(reverse=True)
    print(f"  remainder {rem}: ~IBIT {ib:.2f} vs best other {comp[0][0]:.2f} '{comp[0][1][:45]}' -> FLAG={comp[0][0]-ib>=0.15}")
