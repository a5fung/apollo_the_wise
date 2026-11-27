import re,sys
src=open('rc_stats.py').read().split("rng=np.random.default_rng(1124)")[0]
exec(src)
def tryv(name,fn,restrict=False):
    D=C.copy()
    if restrict: D.loc[D[["f01","f09","f04","f02"]].isna().any(axis=1),["f01","f09","f04","f02"]]=np.nan
    for c in ["f01","f09","f04","f02"]:
        D["r_"+c]=D.groupby(["era","month"])[c].transform(fn)
    D["comb"]=(D.r_f01+D.r_f09+D.r_f04+(1-D.r_f02))/4
    D.loc[D[["f01","f09","f04","f02"]].isna().any(axis=1),"comb"]=np.nan
    global C_
    idx,st,grp=assign(D,"comb"); w=D.loc[idx,"win"].values
    print(f"{name:40s} n={len(idx)} sizes={[int((grp==k).sum()) for k in (0,1,2)]} win={[int(w[grp==k].sum()) for k in (0,1,2)]} ratio={ratio_thirds(w,grp,2,0):.3f}")
tryv("avg rank/n",lambda s:s.rank(method="average")/s.notna().sum())
tryv("(r-.5)/n",lambda s:(s.rank(method="average")-0.5)/s.notna().sum())
tryv("r/(n+1)",lambda s:s.rank(method="average")/(s.notna().sum()+1))
tryv("avg rank/n restrict all-four",lambda s:s.rank(method="average")/s.notna().sum(),True)
tryv("min rank/n",lambda s:s.rank(method="min")/s.notna().sum())
tryv("(r-1)/(n-1)",lambda s:(s.rank(method="average")-1)/(s.notna().sum()-1))
print("--- exact-tie variants (all-four-scored ranks)")
D=C.copy(); ok=D[["f01","f09","f04","f02"]].notna().all(axis=1); D.loc[~ok,["f01","f09","f04","f02"]]=np.nan
g=D.groupby(["era","month"])
R={c:g[c].rank(method="average") for c in ["f01","f09","f04","f02"]}
n=g["f01"].transform(lambda s:s.notna().sum())
S2=(R["f01"]*2+R["f09"]*2+R["f04"]*2+(2*n-2*R["f02"])).round().astype("Int64")   # exact integer, ties exact
for nm,val in (("exact integer sum of ranks (comb = S2/(8n))",S2/(n)),("float round 9dp",((R["f01"]+R["f09"]+R["f04"]+(n-R["f02"]))/n/4).round(9))):
    D["comb"]=val.astype(float); D.loc[~ok,"comb"]=np.nan
    idx,st,grp=assign(D,"comb"); w=D.loc[idx,"win"].values
    print(nm,[int((grp==k).sum()) for k in (0,1,2)],[int(w[grp==k].sum()) for k in (0,1,2)],f"{ratio_thirds(w,grp,2,0):.3f}", {e:round(ratio_thirds(w[D.loc[idx,'era'].values==e],grp[D.loc[idx,'era'].values==e],2,0),3) for e in 'AB'})
