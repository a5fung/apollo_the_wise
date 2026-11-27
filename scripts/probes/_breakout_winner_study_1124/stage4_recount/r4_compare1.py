import pandas as pd, numpy as np
BIG="/Users/alvinfung/apollo_data/cb702/"
W=pd.read_parquet(BIG+"r4_events_postdrop.parquet"); T=pd.read_parquet(BIG+"bws1124_events_postdrop.parquet")
kW=set(zip(W.era,W.ticker,W.D)); kT=set(zip(T.era,T.ticker,T.D))
print("post-drop rows mine",len(W),"theirs",len(T),"equal sets",kW==kT,"mine-only",len(kW-kT),"theirs-only",len(kT-kW))
m=W.merge(T[["era","ticker","D","kept","kept2411","hstr","key","uci","first10","d_file_start","d_guard","d_flag","d_window","reason"]],on=["era","ticker","D"],suffixes=("","_t"))
print("merged",len(m))
print("uD==uci all:",bool((m.uD==m.uci).all()), "first_break==first10 all:",bool((m.first_break==m.first10).all()))
for s,c in ((1124,"kept"),(2411,"kept2411")):
    a=m[f"kept{s}"]; b=m[c]
    print(f"seed {s}: mine {int(a.sum())} theirs {int(b.sum())} mine-only {int((a&~b).sum())} theirs-only {int((~a&b).sum())}")
d=m[(m.kept1124!=m.kept)|(m.kept2411!=m.kept2411_t)]
print(d[["era","ticker","D","istr","hstr","kept1124","kept","kept2411","kept2411_t"]].to_string())
print("identity string differs rows:",int((m.istr!=m.hstr).sum()), "distinct (era,ticker) with differing strings:", m[m.istr!=m.hstr][["era","ticker","istr","hstr"]].drop_duplicates().shape[0])
print(m[m.istr!=m.hstr][["era","ticker","istr","hstr"]].drop_duplicates().head(30).to_string())
# drop-reason diffs on the original break rows is not available (post-drop only); compare non-exclusive flags among kept rows
