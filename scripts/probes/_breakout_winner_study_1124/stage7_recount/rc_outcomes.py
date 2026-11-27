"""Stage 7 blind recount - CHECK outcomes from bars (own code). Reads: kept seed-1124 CHECK events (stage1 events + feature table keys),
adjusted daily bars <=2024-12-31 (asserted), guard files, split list <=2024-12-31, era-A raw close. Writes check_outcomes_rc.tsv."""
import gzip, sys, bisect, hashlib
from pathlib import Path
import numpy as np, pandas as pd
CUT = "2024-12-31"
R = Path("/Users/alvinfung/apollo_the_wise"); S = R/"scripts/probes/_breakout_winner_study_1124"; DATA = Path("/Users/alvinfung/apollo_data")
SHA = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md":"3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
"docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md":"4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
"docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md":"0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b",
"docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md":"a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268",
"docs/analysis/breakout_winner_study_stage6_freeze_2026-11-26.md":"28e40825e0729aaab48e96bcb677db697cb9527f895257b6c425368eb4e4bd18",
"scripts/probes/_breakout_winner_study_1124/stage6_draft/gr1.py":"ff342a19c08ad7d707c32aff4e956e9087cb14271987d3e21e68082303c035a2",
"scripts/probes/_breakout_winner_study_1124/stage6_draft/common6.py":"c290946c49eeb8cba771d36ca2f8abc1c247471966434afcc1eff0b5b874b619",
"scripts/probes/_breakout_winner_study_1124/stage6_draft/gr1_components.tsv.gz":"9c4d25188c9e938ae1e453e58f0e5746b9612515e3dd9819fdc2b686d881a851",
"scripts/probes/_breakout_winner_study_1124/stage6_draft/s6a_build.py":"7a290dfe4a2c06b4ede71514bd462ac6fa814ef5bb39d212b17879dedd12ac9f",
"scripts/probes/_breakout_winner_study_1124/stage1f/feature_table.tsv.gz":"d629ef0af85f0ed3404d0e9cffcc6545627fa3dec6230eb4da94cb3ed95bf53c"}
for p,h in SHA.items(): assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h, p
print("all pins asserted")
def load_bars(path, rawpath=None, sealed=False):
    d = {}; dates=set()
    op = gzip.open
    with op(path,"rt") as f:
        for ln in f:
            t,dt,o,h,l,c,v = ln.rstrip("\n").split(",")[:7]
            if dt > CUT: continue
            d.setdefault(t,[]).append((dt,float(c))); dates.add(dt)
    raw = None
    if rawpath:
        raw = {}
        with op(rawpath,"rt") as f:
            for ln in f:
                t,dt,c = ln.rstrip("\n").split(",")[:3]
                if dt > CUT: continue
                raw.setdefault(t,{})[dt]=float(c)
    cal = sorted(dates); assert cal[-1] <= CUT
    return d, cal, raw
barsA, calA, rawA = load_bars(DATA/"cb702_pre_v2/daily_closes_all.csv.gz", DATA/"cb702_pre_v2/daily_raw_close.csv.gz")
barsB, calB, _ = load_bars(DATA/"cb702/daily_closes_all.csv.gz")
print("A", len(calA), calA[0], calA[-1], "B", len(calB), calB[0], calB[-1])
def parse_guard(path):
    out={}
    for i,ln in enumerate(open(path)):
        f=ln.rstrip("\n").split("\t")
        if i==0: ik,ib=f.index("symbol"),f.index("breaks"); continue
        if len(f)<=ib or not f[ib]: continue
        ds=[x.split(":")[0] for x in f[ib].split(";")]; ds=[x for x in ds if x<=CUT]
        if ds: out[f[ik]]=sorted(ds)
    return out
gA = parse_guard(DATA/"cb702_pre_v2/symbol_guard.tsv"); gB = parse_guard(R/"scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
spl={}
for ln in open(DATA/"cb702/cb702_splits.psv"):
    f=ln.strip().split("|")
    if len(f)<4 or f[1]>CUT: continue
    spl.setdefault(f[0],set()).add(f[1])
# events
T = pd.read_csv(S/"stage1f/feature_table.tsv.gz",sep="\t",keep_default_na=False,na_values=[""],dtype={"ticker":str},low_memory=False)
EV = pd.read_csv(S/"stage1de/events_kept_seed1124.tsv",sep="\t",keep_default_na=False,na_values=[""],dtype={"ticker":str},low_memory=False)
EV = EV[EV.kept==True][["era","ci","ticker","D","E","level","oE"]]
C = T[(T.kept==True)&(T.set=="CHECK")][["era","ci","ticker","D","E"]].merge(EV,on=["era","ci","ticker","D","E"],how="left")
assert len(C)==6266 and C.level.notna().all() and C.oE.notna().all()
assert C.E.min()>="2021-01-01" and C.E.max()<=CUT
rows=[]
nsplit_cut=nguard_cut=0
for r in C.itertuples():
    cal = calA if r.era=="A" else calB; bars = barsA if r.era=="A" else barsB
    assert cal[r.ci]==r.D and cal[r.ci+1]==r.E, (r.era,r.ci,r.D)
    ciE=r.ci+1; lo, hi = cal[ciE], cal[ciE+60]; assert hi<=CUT
    rb = [x for x in bars.get(r.ticker,[]) if lo<=x[0]<=hi]
    # previous row close (for the first move test we only test E+1.. rows, with predecessor inside window)
    g = (gA if r.era=="A" else gB).get(r.ticker,[])
    gdates=[d for d in g if cal[ciE+1]<=d<=hi]
    cut_date=None
    if gdates: cut_date=gdates[0]; nguard_cut+=1
    # split-move test
    if r.era=="B": sd = spl.get(r.ticker,set())
    else:
        sd=set()
        allr = bars.get(r.ticker,[]); rw = rawA.get(r.ticker,{})
        prevf=None
        for dt,c in allr:
            if dt in rw:
                f=rw[dt]/c
                if prevf is not None and abs(f/prevf-1)>0.005: sd.add(dt)
                prevf=f
    sc=None
    for i in range(1,len(rb)):
        if rb[i][0] in sd:
            m = rb[i][1]/rb[i-1][1]-1
            if m>=0.70 or m<=-0.50: sc=rb[i][0]; break
    if sc and (cut_date is None or sc<cut_date): cut_date=sc; nsplit_cut+=1
    rbt = [x for x in rb if cut_date is None or x[0]<cut_date]
    proxy=max(r.level,r.oE)
    mx = max(x[1] for x in rbt) if rbt else np.nan
    rows.append((r.era,r.ci,r.ticker,r.E,proxy,mx,len(rb),len(rbt),cut_date or "",mx/proxy if rbt else np.nan))
O=pd.DataFrame(rows,columns=["era","ci","ticker","E","proxy","maxclose","nbars","nbars_used","cut","ratio"])
O["win"]=O.ratio>=1.5; O["monster"]=O.ratio>=2.0
O.to_csv(Path(__file__).parent/"check_outcomes_rc.tsv",sep="\t",index=False)
print("events",len(O),"winners",int(O.win.sum()),f"rate {O.win.mean():.4f}","monsters",int(O.monster.sum()))
print(O.groupby("era").win.agg(["size","sum","mean"]))
print("truncated by guard",nguard_cut,"by split-move",nsplit_cut,"empty windows",int((O.nbars_used==0).sum()),"nan ratio",int(O.ratio.isna().sum()))
print("short windows (<61 bars used)",int((O.nbars_used<61).sum()))
