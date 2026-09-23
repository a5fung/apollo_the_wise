"""Composition check: did the ARRIVING candidates get junkier, or did the gates change?"""
import sys, os, collections, statistics as st
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from agents.market_intelligence.missed_outcomes import _categorize_skip_reason
SEP="|~|"; HERE=os.path.dirname(os.path.abspath(__file__))
def load(p):
    raw=open(p).read().splitlines(); sec=None; body=collections.defaultdict(list)
    for ln in raw:
        if ln.startswith("===") and ln.endswith("==="): sec=ln.strip("="); continue
        if sec is None or (ln.startswith("(") and ln.endswith("rows)")): continue
        body[sec].append(ln)
    out={}
    for k,v in body.items():
        hdr=v[0].split(SEP); out[k]=[dict(zip(hdr,l.split(SEP))) for l in v[1:] if len(l.split(SEP))==len(hdr)]
    return out
ticks=load(os.path.join(HERE,"_alertdrop_capture2_out.psv"))["R1_SCANLOG_TICKS"]
def f(x):
    try: return float(x)
    except (TypeError,ValueError): return None

# first-seen profile per (day, ticker)
prof={}
qual=collections.defaultdict(collections.Counter)
for r in ticks:
    k=(r["scan_date"],r["ticker"])
    p=prof.setdefault(k,{"gap":None,"prev_close":None,"adv":None,"advsrc":None,"pm_rvol":None,
                          "shortlist":False,"score":None})
    if p["gap"] is None: p["gap"]=f(r["gap_pct"])
    if p["prev_close"] is None: p["prev_close"]=f(r["prev_close"])
    a=f(r["adv"])
    if a and (p["adv"] is None or a>p["adv"]): p["adv"]=a
    if p["pm_rvol"] is None: p["pm_rvol"]=f(r["pm_rvol"])
    if "outside top-" not in r["filter_reason"]: p["shortlist"]=True
    s=f(r["ep_score"])
    if s is not None and (p["score"] is None or s>p["score"]): p["score"]=s
    if r["catalyst_quality"]: qual[r["scan_date"]][r["catalyst_quality"]]+=1
    if "routine catalyst" in r["filter_reason"]: qual[r["scan_date"]]["routine"]+=1

PER=[("A 07-27..08-07","2026-07-27","2026-08-07"),
     ("B 08-10..08-14","2026-08-10","2026-08-14"),
     ("C 08-17..08-21","2026-08-17","2026-08-21"),
     ("D 08-24 only  ","2026-08-24","2026-08-24")]
def med(xs): 
    xs=[x for x in xs if x is not None]
    return st.median(xs) if xs else float('nan')
print("### PROFILE of everything that ARRIVED (median), and of the SHORTLIST entrants")
print(f"{'period':16s}{'n_arr':>7s}{'gap%':>8s}{'prevC$':>9s}{'ADV$sh':>11s}{'|':>3s}{'n_short':>8s}{'gap%':>8s}{'prevC$':>9s}{'ADVsh':>11s}{'ADV<1M%':>9s}{'prevC<10%':>10s}")
for name,lo,hi in PER:
    ks=[k for k in prof if lo<=k[0]<=hi]
    sl=[k for k in ks if prof[k]["shortlist"]]
    a=[prof[k] for k in ks]; s=[prof[k] for k in sl]
    advs=[x["adv"] for x in s if x["adv"]]
    lowadv=sum(1 for x in advs if x<1_000_000)/len(advs)*100 if advs else float('nan')
    lowpc=sum(1 for x in s if x["prev_close"] and x["prev_close"]<10)/len(s)*100 if s else float('nan')
    print(f"{name:16s}{len(ks):7d}{med([x['gap'] for x in a]):8.1f}{med([x['prev_close'] for x in a]):9.2f}"
          f"{med([x['adv'] for x in a]):11.0f}{'|':>3s}{len(sl):8d}{med([x['gap'] for x in s]):8.1f}"
          f"{med([x['prev_close'] for x in s]):9.2f}{med(advs):11.0f}{lowadv:9.1f}{lowpc:10.1f}")

print()
print("### CATALYST GRADE MIX of every name that reached grading")
gs=["game_changing","strong","moderate","weak","routine"]
print(f"{'period':16s}{'graded':>8s}" + "".join(f"{g[:9]:>11s}" for g in gs) + f"{'strong+GC%':>12s}")
for name,lo,hi in PER:
    c=collections.Counter()
    for d,cc in qual.items():
        if lo<=d<=hi: c.update(cc)
    tot=sum(c[g] for g in gs)
    sgc=(c['strong']+c['game_changing'])/tot*100 if tot else float('nan')
    print(f"{name:16s}{tot:8d}" + "".join(f"{c[g]:11d}" for g in gs) + f"{sgc:11.1f}%")

print()
print("### CATALYST GRADE MIX per day (names reaching grading)")
print(f"{'date':12s}{'graded':>7s}" + "".join(f"{g[:9]:>11s}" for g in gs))
for d in sorted(qual):
    if d < "2026-07-27": continue
    c=qual[d]; tot=sum(c[g] for g in gs)
    print(f"{d:12s}{tot:7d}" + "".join(f"{c[g]:11d}" for g in gs))

print()
print("### EP SCORE distribution of SCORED names (bar was 65 in Bull, 70 Choppy, 75 Correcting)")
print(f"{'period':16s}{'n':>5s}{'p25':>7s}{'med':>7s}{'p75':>7s}{'max':>7s}")
for name,lo,hi in PER:
    xs=sorted(prof[k]["score"] for k in prof if lo<=k[0]<=hi and prof[k]["score"] is not None)
    if not xs: continue
    q=lambda p: xs[min(len(xs)-1,int(len(xs)*p))]
    print(f"{name:16s}{len(xs):5d}{q(.25):7.1f}{st.median(xs):7.1f}{q(.75):7.1f}{max(xs):7.1f}")

print()
print("### ARRIVALS vs the acting gap floor — min/p10 gap of arrivals per day")
byday=collections.defaultdict(list)
for (d,t),p in prof.items():
    if p["gap"] is not None: byday[d].append(p["gap"])
print(f"{'date':12s}{'n':>5s}{'min':>8s}{'p10':>8s}{'med':>8s}{'n<10%':>7s}{'n<9%':>6s}")
for d in sorted(byday):
    if d<"2026-08-03": continue
    xs=sorted(byday[d])
    p10=xs[max(0,int(len(xs)*.10))]
    print(f"{d:12s}{len(xs):5d}{xs[0]:8.2f}{p10:8.2f}{st.median(xs):8.2f}"
          f"{sum(1 for x in xs if x<10):7d}{sum(1 for x in xs if x<9):6d}")
