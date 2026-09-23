"""Market-vs-mechanism decomposition + name-level grade mix + small-N check."""
import sys, os, collections, math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from agents.market_intelligence.missed_outcomes import _categorize_skip_reason
SEP="|~|"; HERE=os.path.dirname(os.path.abspath(__file__))
def load(p):
    raw=open(p).read().splitlines(); sec=None; body=collections.defaultdict(list)
    for ln in raw:
        if ln.startswith("===") and ln.endswith("==="): sec=ln.strip("="); continue
        if sec is None or (ln.startswith("(") and ln.endswith("rows)")): continue
        body[sec].append(ln)
    return {k:[dict(zip(v[0].split(SEP), l.split(SEP))) for l in v[1:]
               if len(l.split(SEP))==len(v[0].split(SEP))] for k,v in body.items()}
c1=load(os.path.join(HERE,"_alertdrop_capture_out.psv"))
ticks=load(os.path.join(HERE,"_alertdrop_capture2_out.psv"))["R1_SCANLOG_TICKS"]
tape={r["trade_date"]:r for r in c1["Q5_TAPE_BREADTH"]}
alerted=collections.defaultdict(dict)
for r in c1["Q3_ALERTS"]:
    if r["src"]=="live": alerted[r["alert_date"]][r["ticker"]]=r["score_tier"]

POS={"d1_universe_floor":10,"adv_low":20,"mcap_low":20,"atr_high":20,"extension_gate":20,
     "pm_rvol_low":20,"session_rvol_low":20,"cooldown":20,"ma_filter":20,"filter_other":20,
     "infra_skip":20,"setup_other":20,"block_other":20,"outside_top20":30,
     "catalyst_downgrade":80,"score_below_50":90,"ALERTED":100,"duplicate_scan":0}
st=collections.defaultdict(lambda:{"pos":-1,"cat":None,"grade":None,"scored":False})
for r in ticks:
    k=(r["scan_date"],r["ticker"]); s=st[k]
    if r["catalyst_quality"]: s["grade"]=r["catalyst_quality"]
    if r["ep_score"]: s["scored"]=True
    cat="ALERTED" if r["filter_reason"]=="<none>" else _categorize_skip_reason("scan_filter",r["filter_reason"])
    if cat=="catalyst_downgrade": s["grade"]=s["grade"] or "routine"
    p=POS.get(cat,20)
    if p>s["pos"]: s["pos"],s["cat"]=p,cat

PER=[("A 07-27..08-07","2026-07-27","2026-08-07"),
     ("B 08-10..08-14","2026-08-10","2026-08-14"),
     ("C 08-17..08-21","2026-08-17","2026-08-21")]
MECH={"d1_universe_floor","adv_low","mcap_low","atr_high","extension_gate","pm_rvol_low",
      "session_rvol_low","cooldown","ma_filter","filter_other","infra_skip"}
print("### CAP-NEUTRAL LADDER — base = names that ENTERED the graded shortlist")
print(f"{'period':16s}{'days':>5s}{'tape10':>8s}{'arrived':>8s}{'cap-cut':>8s}{'entered':>8s}"
      f"{'mech-cut':>9s}{'routine':>8s}{'scored':>7s}{'below':>7s}{'HIGH':>6s}{'HIGH/ent':>9s}")
res={}
for name,lo,hi in PER:
    ks=[k for k in st if lo<=k[0]<=hi]
    ds=sorted({k[0] for k in ks}); n=len(ds)
    arrived=len(ks)
    cap=sum(1 for k in ks if st[k]["cat"]=="outside_top20")
    mech=sum(1 for k in ks if st[k]["cat"] in MECH)
    routine=sum(1 for k in ks if st[k]["cat"]=="catalyst_downgrade")
    scored=sum(1 for k in ks if st[k]["scored"])
    below=sum(1 for k in ks if st[k]["cat"]=="score_below_50")
    high=sum(1 for d in ds for t,tier in alerted.get(d,{}).items() if tier=="HIGH")
    ent=arrived-cap
    tp=sum(int(tape[d]["gap10"]) for d in ds)
    res[name]=dict(n=n,arrived=arrived,cap=cap,ent=ent,mech=mech,routine=routine,
                   scored=scored,below=below,high=high,tape=tp)
    print(f"{name:16s}{n:5d}{tp/n:8.1f}{arrived/n:8.1f}{cap/n:8.1f}{ent/n:8.1f}"
          f"{mech/n:9.1f}{routine/n:8.1f}{scored/n:7.1f}{below/n:7.1f}{high/n:6.1f}{high/ent*100:8.1f}%")

print()
print("### DECOMPOSITION — HIGH alerts per day = (names entering the shortlist) x (HIGH per entrant)")
def dec(x,y):
    a,b=res[x],res[y]
    ea,eb=a["ent"]/a["n"],b["ent"]/b["n"]; ra,rb=a["high"]/a["ent"],b["high"]/b["ent"]
    ha,hb=a["high"]/a["n"],b["high"]/b["n"]
    only_vol=eb*ra
    print(f"\n{x} -> {y}:  {ha:.2f} -> {hb:.2f} HIGH alerts/day  ({(hb-ha)/ha*100:+.0f}%)")
    print(f"   names entering the shortlist   {ea:6.1f} -> {eb:6.1f}   ({(eb-ea)/ea*100:+.0f}%)")
    print(f"   HIGH per entrant               {ra*100:5.1f}% -> {rb*100:5.1f}%   ({(rb-ra)/ra*100:+.0f}%)")
    print(f"   fewer names alone would give   {only_vol:6.2f}/day  -> explains {(ha-only_vol)/(ha-hb)*100 if ha!=hb else 0:5.0f}% of the fall")
    print(f"   lower conversion explains the remaining {(only_vol-hb)/(ha-hb)*100 if ha!=hb else 0:5.0f}%")
dec("A 07-27..08-07","B 08-10..08-14")
dec("B 08-10..08-14","C 08-17..08-21")
dec("A 07-27..08-07","C 08-17..08-21")

print()
print("### SMALL-N CHECK on the step-2 conversion drop (B vs C, both uncapped)")
b,c=res["B 08-10..08-14"],res["C 08-17..08-21"]
print(f"   B: {b['high']} HIGH out of {b['ent']} shortlist entrants = {b['high']/b['ent']*100:.1f}%")
print(f"   C: {c['high']} HIGH out of {c['ent']} shortlist entrants = {c['high']/c['ent']*100:.1f}%")
# two-sided Fisher exact
from math import comb
a1,b1=b["high"],b["ent"]-b["high"]; c1_,d1=c["high"],c["ent"]-c["high"]
N=a1+b1+c1_+d1
def pr(a):
    return comb(a1+b1,a)*comb(c1_+d1,(a1+c1_)-a)/comb(N,a1+c1_)
obs=pr(a1); tot=0.0
for a in range(max(0,(a1+c1_)-(c1_+d1)), min(a1+b1,a1+c1_)+1):
    p=pr(a)
    if p<=obs+1e-12: tot+=p
print(f"   Fisher exact two-sided p = {tot:.3f}  ({'significant' if tot<0.05 else 'NOT significant at 0.05 — the conversion half of step 2 is small-N'})")

print()
print("### GRADE MIX at NAME level (one grade per day-ticker that reached grading)")
gs=["game_changing","strong","moderate","weak","routine"]
print(f"{'period':16s}{'reached':>9s}" + "".join(f"{g[:9]:>11s}" for g in gs))
for name,lo,hi in PER:
    cc=collections.Counter(st[k]["grade"] for k in st if lo<=k[0]<=hi and st[k]["grade"])
    tot=sum(cc[g] for g in gs)
    print(f"{name:16s}{tot:9d}" + "".join(f"{cc[g]:11d}" for g in gs))

print()
print("### WHICH MECHANICAL GATE — per trading day, B vs C")
gates=["mcap_low","adv_low","extension_gate","atr_high","pm_rvol_low","session_rvol_low",
       "cooldown","ma_filter","d1_universe_floor","filter_other"]
print(f"{'gate':22s}" + "".join(f"{p.split()[0]:>9s}" for p,_,_ in PER))
for g in gates:
    vals=[]
    for name,lo,hi in PER:
        ks=[k for k in st if lo<=k[0]<=hi]
        ds=len({k[0] for k in ks})
        vals.append(sum(1 for k in ks if st[k]["cat"]==g)/ds)
    print(f"{g:22s}" + "".join(f"{v:9.1f}" for v in vals))

print()
print("### THE OPERATOR'S OWN STEP: the four days before step 1 vs the five after")
PER2=[("A' 08-04..08-07","2026-08-04","2026-08-07"),
      ("B  08-10..08-14","2026-08-10","2026-08-14"),
      ("C  08-17..08-21","2026-08-17","2026-08-21"),
      ("D  08-24 only  ","2026-08-24","2026-08-24")]
for name,lo,hi in PER2:
    ks=[k for k in st if lo<=k[0]<=hi]
    ds=sorted({k[0] for k in ks}); n=len(ds)
    # 08-24: strip the newly-logged D-1 universe floor rows (#570 shipped 08-22)
    real=[k for k in ks if st[k]["cat"]!="d1_universe_floor"]
    cap=sum(1 for k in real if st[k]["cat"]=="outside_top20")
    ent=len(real)-cap
    high=sum(1 for d in ds for t,tier in alerted.get(d,{}).items() if tier=="HIGH")
    tp=sum(int(tape[d]["gap10"]) for d in ds)
    print(f"{name:16s} days={n}  tape_gap10/day={tp/n:5.1f}  arrived/day={len(real)/n:5.1f}  "
          f"entered/day={ent/n:5.1f}  HIGH/day={high/n:4.2f}  HIGH/entrant={high/ent*100 if ent else 0:5.1f}%")

print()
print("### WHAT THE 9% GAP FLOOR ADDED (live from 2026-08-20)")
for d in ["2026-08-19","2026-08-20","2026-08-21","2026-08-24"]:
    sub=[k for k in st if k[0]==d and st[k]["cat"]!="d1_universe_floor"]
    g={}
    for r in ticks:
        if r["scan_date"]==d and r["filter_reason"]!="<none>" or r["scan_date"]==d:
            try: g.setdefault((r["scan_date"],r["ticker"]), float(r["gap_pct"]))
            except (TypeError,ValueError): pass
    sub9=[k for k in sub if g.get(k) is not None and g[k]<10.0]
    hi9=[k for k in sub9 if alerted.get(d,{}).get(k[1])=="HIGH"]
    print(f"   {d}: {len(sub)} real candidates, {len(sub9)} of them below the old 10% floor "
          f"(admitted only because of the 9% floor); {len(hi9)} of those became HIGH")

print()
print("### THE EXTENSION-GATE NAMES IN PERIOD C (cap was still 50% until 2026-08-22)")
for k in sorted(k for k in st if "2026-08-17"<=k[0]<="2026-08-21" and st[k]["cat"]=="extension_gate"):
    rs=[r for r in ticks if (r["scan_date"],r["ticker"])==k and "extended" in r["filter_reason"]]
    if rs: print(f"   {k[0]}  {k[1]:6s}  {rs[-1]['filter_reason']}")

print()
print("### THE JULY BASELINE — is today's funnel cutting harder than it did all summer?")
PER3=[("P0 07-06..07-24 (July baseline)","2026-07-06","2026-07-24"),
      ("P1 07-27..07-31","2026-07-27","2026-07-31"),
      ("P2 08-03..08-07 (the burst)","2026-08-03","2026-08-07"),
      ("P3 08-10..08-14","2026-08-10","2026-08-14"),
      ("P4 08-17..08-21","2026-08-17","2026-08-21"),
      ("P5 08-24","2026-08-24","2026-08-24")]
print(f"{'period':34s}{'days':>5s}{'tape10/d':>10s}{'arrived/d':>10s}{'scored/d':>9s}{'HIGH/d':>8s}"
      f"{'scored/arr':>12s}{'HIGH/arrival':>14s}{'HIGH/scored':>13s}")
for name,lo,hi in PER3:
    ks=[k for k in st if lo<=k[0]<=hi and st[k]["cat"]!="d1_universe_floor"]
    ds=sorted({k[0] for k in ks}); n=len(ds)
    arr=len(ks); sc=sum(1 for k in ks if st[k]["scored"])
    high=sum(1 for d in ds for t,tier in alerted.get(d,{}).items() if tier=="HIGH")
    tp=sum(int(tape[d]["gap10"]) for d in ds)
    print(f"{name:34s}{n:5d}{tp/n:10.1f}{arr/n:10.1f}{sc/n:9.1f}{high/n:8.2f}"
          f"{sc/arr*100:11.1f}%{high/arr*100:13.1f}%{(high/sc*100 if sc else 0):12.1f}%")
