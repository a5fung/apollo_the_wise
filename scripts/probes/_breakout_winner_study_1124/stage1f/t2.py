"""independent re-derivation (plain dict-by-calendar-index code) of f08 f11 f13 f17 f18 f21 f24 B4 on 60 random kept events"""
from lib1f import *
from collections import Counter
T=pd.read_csv("feature_table.tsv.gz",sep="\t",low_memory=False)
bad=Counter(); n=Counter()
for era in ("A","B"):
    S=setup_store(era); D=S.D
    LP=pd.read_parquet(OUT_DATA/f"bws1124_era{era}_list_ctx.parquet",columns=["ci","ticker","level","adr20"]).set_index(["ci","ticker"])
    x=T[(T.era==era)&T.kept].sample(30,random_state=7)
    for r in x.itertuples():
        k=D.tid[r.ticker]; a,b=int(D.start[k]),int(D.stop[k]); ci=D.ci[a:b]
        r_level,r_adr=LP.loc[(int(r.ci),r.ticker)]
        row={int(c):i+a for i,c in enumerate(ci)}   # calendar index -> flat row
        g=lambda arr,c: arr[row[c]] if c in row else None
        cD=int(r.ci); cl=D.c[row[cD]]
        def win(arr,lo,hi): return [arr[row[c]] for c in range(lo,hi+1) if c in row]
        def chk(name,val,got):
            n[name]+=1
            if (val is None and np.isnan(got)) : return
            if val is None or not np.isclose(val,got,rtol=1e-8): bad[name]+=1; print("BAD",name,r.ticker,r.D,val,got)
        if pd.isna(r.f08_null): chk("f08", cl/min(win(D.l,cD-19,cD))-1, r.f08)
        if pd.isna(r.f11_null): chk("f11", 1.0 if r_level>=max(win(D.h,cD-251,cD))*(1-1e-12) else 0.0, r.f11)
        if pd.isna(r.f17_null):
            sh=np.mean(win(D.v,cD-9,cD)); lg=np.mean(win(D.v,cD-59,cD-10)); chk("f17",sh/lg,r.f17)
        if pd.isna(r.f18_null):
            up=dn=0.0
            for c in range(cD-19,cD+1):
                if c in row and (c-1) in row:
                    if D.c[row[c]]>D.c[row[c-1]]: up+=D.v[row[c]]
                    elif D.c[row[c]]<D.c[row[c-1]]: dn+=D.v[row[c]]
            chk("f18",up/dn,r.f18)
        if pd.isna(r.f21_null):
            sma=np.mean(win(D.c,cD-199,cD)); chk("f21",(cl/sma-1)*100/(r_adr*100),r.f21)
        oE=D.o[row[cD+1]]
        chk("f24",(oE/cl-1)*100/(r_adr*100),r.f24)
        chk("B4",(r_level/cl-1)*100/(r_adr*100),r.B4)
        if pd.isna(r.f13_null):
            P=int(round(0)) 
            bl=int(r.f12); lows=win(D.l,cD-bl+1,cD); highs=win(D.h,cD-bl+1,cD)
            chk("f13",(1-min(lows)/max(highs))*100,r.f13)
        chk("f01",r_adr*100,r.f01)
        chk("f02",D.c[row[cD]]*S.raw_factor[row[cD]] if pd.isna(r.f02_null) else None, r.f02) if pd.isna(r.f02_null) else None
print("checked",dict(n)); print("BAD",dict(bad))
