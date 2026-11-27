src=open('rc_stats.py').read().split("rng=np.random.default_rng(1124)")[0]
exec(src)
idx,st,grp=assign(C,"gr1",True); w=C.loc[idx,"win"].values
obs=mh(w,st,grp,2,0); print("obs",obs)
groups=[np.flatnonzero(st==s) for s in np.unique(st)]
for seed in (1124,7,99):
  rng=np.random.default_rng(seed); tot=0; ge=0; NPc=5000
  for rep in range(40):
    Aa=np.zeros(NPc);Bb=np.zeros(NPc)
    for gi in groups:
        lab=w[gi]; g=grp[gi]; N=len(gi); n1=(g==2).sum(); n0=(g==0).sum()
        perm=np.argsort(rng.random((NPc,N)),axis=1); pl=lab[perm]
        Aa+=pl[:,g==2].sum(1)*n0/N; Bb+=pl[:,g==0].sum(1)*n1/N
    with np.errstate(divide="ignore",invalid="ignore"): res=np.where(Bb>0,Aa/Bb,np.inf)
    ge+=(res>=obs-1e-12).sum(); tot+=NPc
  print("seed",seed,"perms",tot,"p",ge/tot)
