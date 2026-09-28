"""Critic check: were the 'late' births' founders ALREADY held by a live theme on the first-sighting night?"""
import re, statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
H = Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_655")
d_ = date.fromisoformat
spy = sorted(d_(l.split("|")[1]) for l in open(H/"funnel_closes.psv") if l.startswith("SPY|"))
sidx = {d:i for i,d in enumerate(spy)}
hist=[]
for ln in open(H/"funnel_themes_hist.psv"):
    p=ln.rstrip("\n").split("|")
    hist.append({"id":int(p[0]),"date":d_(p[1]),"name":p[2],"stage":p[3],"tickers":[t for t in p[4].split(",") if t]})
cl_by_date=defaultdict(lambda: defaultdict(set))
for ln in open(H/"funnel_clusters.psv"):
    p=ln.rstrip("\n").split("|"); cl_by_date[d_(p[0])][p[1]].add(p[2])
cdates=sorted(cl_by_date)
names=defaultdict(list)
for r in hist: names[r["name"]].append(r)
for n in names: names[n].sort(key=lambda r:r["date"])
parent={}
def find(x):
    while parent.get(x,x)!=x: x=parent[x]
    return x
for ln in open(H/"funnel_renames.psv"):
    o,nw,*_=ln.rstrip("\n").split("|")
    if o in names and nw in names: parent[find(nw)]=find(o)
for ln in open(H/"funnel_rename_events.psv"):
    txt=ln.rstrip("\n")
    for o,nw in re.findall(r"'([^']+)' → '([^']+)'",txt)+re.findall(r"'([^']+)' renamed to '([^']+)'",txt):
        if o in names and nw in names: parent[find(nw)]=find(o)
by_date=defaultdict(list)
for n,rs in names.items():
    for r in rs:
        if r["tickers"] and r["stage"]!="Retired": by_date[r["date"]].append((n,r["tickers"],r["stage"]))
first_row={}
for n,rs in names.items():
    live=[r for r in rs if r["stage"]!="Retired" and r["tickers"]]
    if live: first_row[n]=live[0]
for n,fr in first_row.items():
    d0,F=fr["date"],set(fr["tickers"]); recent={}
    for k in range(1,11):
        for nm,tk,_ in by_date.get(d0-timedelta(days=k),[]):
            if nm!=n and nm not in recent: recent[nm]=tk
    best,bj=None,0.0
    for nm,tk in recent.items():
        S=set(tk); j=len(F&S)/len(F|S)
        if j>bj: best,bj=nm,j
    if best and bj>=0.4: parent[find(n)]=find(best)
groups=defaultdict(list)
for n in first_row: groups[find(n)].append(n)
births=[]
for root,ns_ in groups.items():
    fr=min((first_row[n] for n in ns_),key=lambda r:(r["date"],r["id"]))
    if fr["date"]>=date(2026,6,1) and len(fr["tickers"])>=2 and fr["date"] in sidx: births.append(fr)
def board_at(d):
    latest={}
    for r in hist:
        if d-timedelta(days=7)<=r["date"]<=d and (r["name"] not in latest or r["date"]>latest[r["name"]]["date"]): latest[r["name"]]=r
    return [r for r in latest.values() if r["stage"]!="Retired" and r["tickers"]]
_bc={}
def board(d):
    if d not in _bc: _bc[d]=board_at(d)
    return _bc[d]
def leads(F,bd):
    i0=sidx[bd]; hits=[]
    for d in cdates:
        if d not in sidx or not (i0-40<=sidx[d]<i0): continue
        for tk in cl_by_date[d].values():
            if len(tk&F)/len(F)>=0.5: hits.append((i0-sidx[d],d)); break
    return hits
rows=[]
for b in births:
    if not (date(2026,8,26)<=b["date"]<=date(2026,9,25)): continue
    F=set(b["tickers"]); h=leads(F,b["date"])
    if not h: continue
    lf,dfirst=max(h)
    # was >= half the founders already in ONE live-board theme (any non-Retired stage) on the first-sighting night?
    held=[(len(F&set(r["tickers"]))/len(F),r["name"],r["stage"]) for r in board(dfirst)]
    held=max(held) if held else (0,None,None)
    # same, on ANY night between first sighting and the night before birth
    anyheld=False; nonfading_any=False
    for L,d in h:
        for r in board(d):
            if len(F&set(r["tickers"]))/len(F)>=0.5:
                anyheld=True
                if r["stage"]!="Fading": nonfading_any=True
    rows.append((b["date"],b["name"],lf,held,anyheld,nonfading_any))
print("births 08-26..09-25 with a pre-birth cluster:",len(rows),"median lead",statistics.median(r[2] for r in rows))
held_first=[r for r in rows if r[3][0]>=0.5]
print("founders already >=half in ONE live theme on the FIRST-sighting night:",len(held_first))
print("  of those, the holding theme was Fading:",sum(1 for r in held_first if r[3][2]=="Fading"))
print("founders >=half in one live theme on ANY pre-birth sighting night:",sum(r[4] for r in rows))
clean=[r for r in rows if r[3][0]<0.5]
print("median lead EXCLUDING births already held on first-sighting night:",statistics.median(r[2] for r in clean) if clean else None,"n=",len(clean))
clean2=[r for r in rows if not r[4]]
print("median lead EXCLUDING births held on ANY sighting night:",statistics.median(r[2] for r in clean2) if clean2 else None,"n=",len(clean2), " >10:",sum(r[2]>10 for r in clean2))
for r in sorted(rows,key=lambda r:-r[2])[:25]:
    print(f"  {r[0]} lead {r[2]:2d} held@first {r[3][0]:.2f} [{r[3][2]}] '{(r[3][1] or '')[:45]}' <- birth '{r[1][:50]}'")
print("\n--- #491 miner births since 06-01 (>=2 miners among founders) ---")
MINERS={"HUT","IREN","CLSK","RIOT","MARA","BTDR","CIFR","CORZ","WULF","APLD","ABTC","BITF"}
for b in sorted(births,key=lambda r:r["date"]):
    F=set(b["tickers"])
    if len(F&MINERS)<2: continue
    h=leads(F,b["date"])
    if not h: print(f"  {b['date']} no pre-birth cluster '{b['name'][:50]}'"); continue
    lf,dfirst=max(h)
    held=max(((len(F&set(r['tickers']))/len(F),r['name'],r['stage']) for r in board(dfirst)),default=(0,None,None))
    print(f"  {b['date']} lead {lf} first-sighting {dfirst}: held {held[0]:.2f} by [{held[2]}] '{(held[1] or '')[:55]}' <- '{b['name'][:55]}' {sorted(F)}")
print("\n--- all births 06-01..09-25 ---")
allrows=[]
for b in births:
    F=set(b["tickers"]); h=leads(F,b["date"])
    if not h: continue
    lf,dfirst=max(h)
    anyheld=any(len(F&set(r["tickers"]))/len(F)>=0.5 for L,d in h for r in board(d))
    allrows.append((lf,anyheld))
print("n",len(allrows),"median",statistics.median(r[0] for r in allrows),"held on some sighting night",sum(r[1] for r in allrows),
      "clean median",statistics.median([r[0] for r in allrows if not r[1]]),"clean n",sum(not r[1] for r in allrows))
print("births at the 40-session lookback cap (lead>=39), last-30d set:",sum(1 for r in rows if r[2]>=39),"of",len(rows))
print("\n--- held by ONE live theme (>= half the founders) on ANY board night from first sighting to the night before birth ---")
bdates=sorted({r["date"] for r in hist})
def held_between(F,d0,d1):
    for d in bdates:
        if d0<=d<d1:
            for r in board(d):
                if len(F&set(r["tickers"]))/len(F)>=0.5: return d,r["name"],r["stage"]
    return None
res=[]
for b in births:
    if not (date(2026,8,26)<=b["date"]<=date(2026,9,25)): continue
    F=set(b["tickers"]); h=leads(F,b["date"])
    if not h: continue
    lf,dfirst=max(h); hb=held_between(F,dfirst,b["date"])
    res.append((lf,hb,b))
print("last-30d births with pre-birth cluster:",len(res),"; group held by a live theme on some night in the lead window:",sum(1 for r in res if r[1]))
cl=[r[0] for r in res if not r[1]]
print("never held in the lead window: n",len(cl),"median lead",statistics.median(cl) if cl else None, ">10:",sum(x>10 for x in cl))
for lf,hb,b in sorted(res,key=lambda r:r[2]["date"]):
    F=set(b["tickers"])
    if len(F&MINERS)>=2: print("  miner birth",b["date"],b["name"][:50],"lead",lf,"held:",hb)
