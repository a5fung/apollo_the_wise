import sys,gzip,csv,numpy as np
from collections import defaultdict
sys.path.insert(0,"../stage1ab")
from common import *
import v1_replay as R
pull=defaultdict(dict)
for ln in gzip.open(DATA/"cb702"/"raw_close_bwin_1124.csv.gz","rt"):
    t,d,c,v=ln.rstrip("\n").split(","); pull[t][d]=float(c)
poly=defaultdict(dict)
for f in ("raw_close_bv1_1101.csv.gz","raw_close_tgrid_1101.csv.gz"):
    for ln in gzip.open(R.CB/f,"rt"):
        t,d,c=ln.strip().split(","); poly[t][d]=float(c)
req={r["ticker"]:r for r in csv.DictReader((Path(".")/"bws1124_raw_request.tsv").open(),delimiter="\t")}
for t,r in req.items():
    if "ctlB_polygon" not in r["sets"].split("+"): continue
    kn=poly[t]; pr=pull.get(t,{})
    com=[(pr[d],kn[d]) for d in pr if d in kn and kn[d]>0]
    if not com: print(t,"NOCOMP"); continue
    rel=np.abs([p/k-1 for p,k in com]); m=float(np.median(rel))
    if m>0.10: print(t,len(com),f"med={m:.3f}",f"ratio_med={np.median([p/k for p,k in com]):.3f}")
