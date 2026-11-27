"""Stage 7 blind recount - the check statistics, own code from the frozen text. Family m=6, Holm one-sided."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
H = Path(__file__).parent; S = H.parent
T = pd.read_csv(S/"stage1f/feature_table.tsv.gz",sep="\t",keep_default_na=False,na_values=[""],dtype={"ticker":str},low_memory=False)
assert T.E.max()<="2024-12-31"
C = T[(T.kept==True)&(T.set=="CHECK")].copy()
O = pd.read_csv(H/"check_outcomes_rc.tsv",sep="\t",dtype={"ticker":str})
C = C.merge(O[["era","ci","ticker","E","win","monster"]],on=["era","ci","ticker","E"],how="left"); assert len(C)==6266 and C.win.notna().all()
C["win"]=C.win.astype(int)
G = pd.read_csv(S/"stage6_draft/gr1_components.tsv.gz",sep="\t",keep_default_na=False,na_values=[""],dtype={"ticker":str})
G["gr1_null"]=G.gr1_null.fillna("")
sc=G.gr1_null==""
base=sc&(G.trough_age<=59)&(G.drop_adr>=5.0)&(G.recover>=0.5)
G["gr1"]=np.where(sc,(base&(G.at_level<=9)).astype(float),np.nan)
C = C.merge(G[["era","ci","ticker","E","gr1"]],on=["era","ci","ticker","E"],how="left")
print("gr1 flagged",int((C.gr1==1).sum()),"of",len(C),"NULL",int(C.gr1.isna().sum()))
for c in ["f01","f02","f04","f09"]:
    C[c]=pd.to_numeric(C[c],errors="coerce")
    nul=C[c+"_null"].notna()  # non-blank null reason
    C.loc[nul,c]=np.nan
    print(c,"NULL",int(C[c].isna().sum()))
C["month"]=C.E.str[:7]
# combination: equal-weight mean of signed within-(era,month) percentile ranks of f01,f09,f04 (HIGH) and f02 (LOW)
def prank(s): return s.rank(method="average")/s.notna().sum()
for c in ["f01","f09","f04","f02"]:
    C["r_"+c]=C.groupby(["era","month"])[c].transform(lambda s: s.rank(method="average")/s.notna().sum())
C["comb"]=(C.r_f01+C.r_f09+C.r_f04+(1-C.r_f02))/4
C.loc[C[["f01","f09","f04","f02"]].isna().any(axis=1),"comb"]=np.nan
print("comb scored",int(C.comb.notna().sum()))
def thirds(v):
    n=len(v); order=np.argsort(v,kind="stable"); sv=v[order]
    sizes=[n//3+(1 if i<n%3 else 0) for i in range(3)]; b1=sizes[0]; b2=sizes[0]+sizes[1]
    g=np.zeros(n,int)
    i=0
    while i<n:
        j=i
        while j+1<n and sv[j+1]==sv[i]: j+=1
        pos=(i+j)//2
        gi=0 if pos<b1 else (1 if pos<b2 else 2)
        g[order[i:j+1]]=gi; i=j+1
    return g
def halves(v):
    n=len(v); order=np.argsort(v,kind="stable"); sv=v[order]; b=n//2 if False else (n+1)//2
    g=np.zeros(n,int); i=0
    while i<n:
        j=i
        while j+1<n and sv[j+1]==sv[i]: j+=1
        pos=(i+j)//2; g[order[i:j+1]]=0 if pos<b else 1; i=j+1
    return g
def assign(df,col,two_group=False):
    """returns arrays: idx(positions in df), stratum id, group (0 bottom/1 mid/2 top; two-group: 0/1->(0 bottom,2 top))"""
    df=df[df[col].notna()]
    idx=[];st=[];grp=[];k=0
    for (e,m),x in df.groupby(["era","month"]):
        if two_group:
            lab=x[col].values
            if (lab==0).sum()<2 or (lab==1).sum()<2: continue
            idx+=list(x.index);st+=[k]*len(x);grp+=list(np.where(lab==1,0,2)); k+=1   # group 0 = V(1), 2 = notV(0)? set later
            continue
        if len(x)<6: continue
        v=x[col].values.astype(float); g=thirds(v)
        if (g==0).sum()==0 or (g==2).sum()==0:
            g=halves(v); g=np.where(g==0,0,2)
        idx+=list(x.index);st+=[k]*len(x);grp+=list(g);k+=1
    return np.array(idx),np.array(st),np.array(grp)
def ratio_thirds(w,grp,top,bot):
    nt=(grp==top).sum(); nb=(grp==bot).sum(); wt=w[grp==top].sum(); wb=w[grp==bot].sum()
    rt=(wt+0.5)/(nt+1) if wt==0 else wt/nt; rb=(wb+0.5)/(nb+1) if wb==0 else wb/nb
    return rt/rb
def mh(w,st,grp,num,den):
    A=B=0.0
    for s in np.unique(st):
        m=st==s; g=grp[m]; ww=w[m]; N=m.sum(); n1=(g==num).sum(); n0=(g==den).sum()
        x1=ww[g==num].sum(); x0=ww[g==den].sum()
        A+=x1*n0/N; B+=x0*n1/N
    return A/B if B>0 else np.inf
rng=np.random.default_rng(1124); NP=10000
def run(name,col,direction,two_group=False):
    idx,st,grp=assign(C,col,two_group)
    w=C.loc[idx,"win"].values; eras=C.loc[idx,"era"].values
    # frozen direction: HIGH -> top/bottom ; LOW -> bottom/top ; gr1: notV rate / V rate  (grp 2 = notV, 0 = V)
    if two_group: top,bot=2,0
    else: top,bot=(2,0) if direction=="HIGH" else (0,2)
    f=(lambda ww,gg: mh(ww,st,gg,top,bot)) if two_group else (lambda ww,gg: ratio_thirds(ww,gg,top,bot))
    obs=f(w,grp)
    # permutation: shuffle labels within strata
    groups=[np.flatnonzero(st==s) for s in np.unique(st)]
    cnt_ge=0;cnt_le=0
    if two_group:
        pass
    # vectorised: for thirds, per perm compute winners sums in top/bot
    res=np.empty(NP)
    if not two_group:
        topm=(grp==top);botm=(grp==bot); nt=topm.sum(); nb=botm.sum()
        WT=np.zeros(NP);WB=np.zeros(NP)
        for gidx in groups:
            lab=w[gidx]; tm=topm[gidx]; bm=botm[gidx]
            keys=rng.random((NP,len(gidx))); perm=np.argsort(keys,axis=1); pl=lab[perm]
            WT+=pl[:,tm].sum(1); WB+=pl[:,bm].sum(1)
        rt=np.where(WT==0,(WT+0.5)/(nt+1),WT/nt); rb=np.where(WB==0,(WB+0.5)/(nb+1),WB/nb); res=rt/rb
    else:
        Aa=np.zeros(NP);Bb=np.zeros(NP)
        for gidx in groups:
            lab=w[gidx]; g=grp[gidx]; N=len(gidx); n1=(g==top).sum(); n0=(g==bot).sum()
            keys=rng.random((NP,N)); perm=np.argsort(keys,axis=1); pl=lab[perm]
            Aa+=pl[:,g==top].sum(1)*n0/N; Bb+=pl[:,g==bot].sum(1)*n1/N
        with np.errstate(divide="ignore",invalid="ignore"): res=np.where(Bb>0,Aa/Bb,np.inf)
    ge=(res>=obs-1e-12).sum(); le=(res<=obs+1e-12).sum()
    p_hi=(ge+1)/(NP+1); p_opp=(le+1)/(NP+1)
    # era-wise
    era_r={}
    for e in ("A","B"):
        mm=eras==e
        if mm.sum()==0: continue
        if two_group: era_r[e]=mh(w[mm],st[mm],grp[mm],top,bot)
        else: era_r[e]=ratio_thirds(w[mm],grp[mm],top,bot)
    # bootstrap-free: n per group
    ngrp={int(k):int((grp==k).sum()) for k in np.unique(grp)}
    wgrp={int(k):int(w[grp==k].sum()) for k in np.unique(grp)}
    return dict(name=name,n=int(len(idx)),ngroups=ngrp,winners=wgrp,ratio=float(obs),p_dir=float(p_hi),p_dir_noplus1=float(ge/NP),p_opp=float(p_opp),era=era_r,strata=int(len(groups)))
fam=[run("f01 daily range HIGH","f01","HIGH"),run("f09 6-month move HIGH","f09","HIGH"),run("f04 strength rank best HIGH","f04","HIGH"),run("f02 price LOW","f02","LOW"),run("combination (1-4)","comb","HIGH"),run("gr1 V into breakout (notV/V)","gr1",None,True)]
def holm(ps):
    m=len(ps); o=np.argsort(ps); adj=np.empty(m); run_max=0
    for r,i in enumerate(o):
        run_max=max(run_max,(m-r)*ps[i]); adj[i]=min(1,run_max)
    return adj
ph=holm([f["p_dir"] for f in fam]); po=holm([f["p_opp"] for f in fam])
for f,a,b in zip(fam,ph,po):
    f["holm_p"]=float(a); f["holm_opp"]=float(b)
    same_era = all(v>=1.0 for v in f["era"].values())
    if f["ratio"]>=1.2 and a<=0.05: v="PICKS THE TAIL" if same_era else "PICKS THE TAIL (one era only)"
    elif f["ratio"]>=1.2: v="DIRECTIONAL, NOT PROVEN"
    elif f["ratio"]<=0.83 and b<=0.05: v="REVERSED"
    else: v="NOT CONFIRMED"
    if f["name"].startswith("f04") and v.startswith("PICKS"): v+=" (check years partly seen)"
    f["verdict"]=v
    print(f"{f['name']:34s} n={f['n']} groups={f['ngroups']} win={f['winners']} ratio={f['ratio']:.3f} era={ {k:round(x,3) for k,x in f['era'].items()} } p={f['p_dir']:.4f} Holm={a:.4f} oppHolm={b:.4f} -> {v}")
(H/"rc_result.json").write_text(json.dumps(fam,indent=1))
