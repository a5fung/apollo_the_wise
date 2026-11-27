import pandas as pd, numpy as np, json, sys
BIG="/Users/alvinfung/apollo_data/cb702/"
suffix = sys.argv[1] if len(sys.argv)>1 else ""
M=pd.read_parquet(BIG+f"r4_feature_table{suffix}.parquet")
T=pd.read_csv("/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1f/feature_table.tsv.gz",sep="\t",low_memory=False)
T=T[T.kept==True]
m=M.merge(T,on=["era","ticker","D"],suffixes=("","_t"))
print("mine",len(M),"theirs kept",len(T),"common",len(m), "mine-only", len(M)-len(m), "theirs-only", len(T)-len(m))
mp={f"f{i}":(f"f{i:02d}" if i<10 else f"f{i:02d}_t") for i in range(1,25)}
for b in ("B1","B2","B3","B4"): mp[b]=b+"_t"
out={}
for fm,ft in mp.items():
    a=m[fm].to_numpy(float); b=m[ft].to_numpy(float)
    nanmis=int((np.isnan(a)!=np.isnan(b)).sum())
    ok=~np.isnan(a)&~np.isnan(b)
    best=None
    for sc in (1.0,100.0,0.01):
        d=np.abs(a[ok]*sc-b[ok]); rel=d/(np.abs(b[ok])+1e-12)
        mx=float(np.max(np.minimum(d,rel))) if ok.sum() else 0.0
        if best is None or mx<best[1]: best=(sc,mx)
    out[fm]={"null_pattern_mismatch":nanmis,"scale_mine_to_theirs":best[0],"max_diff":best[1],"n":int(ok.sum())}
    print(f"{fm:4s} null-pattern mismatches {nanmis:4d}  scale {best[0]:>6} max |diff| {best[1]:.3g} (n {int(ok.sum())})")
# f24 above/below
print("f24 grp (their f24grp a/b) vs mine above:", int(((m.f24_above==1)!=(m.f24grp=='a')).sum()))
json.dump(out,open(f"out/feature_compare{suffix}.json","w"),indent=1)
