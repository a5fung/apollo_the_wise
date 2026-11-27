"""Stage 1c under amendment A1: pull discarded (never opened). Writes notreturned_A1.txt (757 main-set names) + A1.txt."""
import sys, csv, hashlib
sys.path.insert(0, "../stage1ab")
from common import *
assert_prereg()
assert hashlib.sha256(open("/Users/alvinfung/apollo_the_wise/docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md","rb").read()).hexdigest()=="4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10"
import numpy as np
import v1_replay as R
from datetime import date
OUT = HERE.parent / "stage1c"
REQ = OUT / "bws1124_raw_request.tsv"
assert hashlib.sha256(REQ.read_bytes()).hexdigest() == (OUT / "bws1124_raw_request.sha256").read_text().strip()
req = {r["ticker"]: r for r in csv.DictReader(REQ.open(), delimiter="\t")}
main = sorted(t for t, r in req.items() if "main" in r["sets"].split("+"))
(OUT / "notreturned_A1.txt").write_text("\n".join(main) + "\n")
S = R.load_store("B"); D = S.D; assert D.cal[-1] < date(2025, 1, 1)
cal = [d.isoformat() for d in D.cal]; mset = set(main)
tot = der = der_all = 0; src2_main = 0; seen = set()
for k, t in enumerate(D.tickers):
    a, b = int(D.start[k]), int(D.stop[k]); c, v = D.c[a:b], D.v[a:b]; ci = D.ci[a:b]
    dv = R._rolling_median(c * v, R.cb.DOLLAR_VOL_WINDOW)
    m = (dv >= R.bv.MIN_DOLLAR_VOL) & (np.array([cal[int(x)] for x in ci]) >= "2022-04-01")
    n = int(m.sum()); tot += n
    s2 = int(S.raw_src[a]) == 2
    if n and s2: der_all += n
    if t in mset:
        seen.add(t)
        if s2: src2_main += 1
        der += n
lines = [f"A1 not-returned list: {len(main)} main-set names -> stage1c/notreturned_A1.txt",
 f"main names found in era-B store: {len(seen)}/{len(main)}; of those raw_src==2: {src2_main}",
 f"derived-only share of era-B pool-candidate name-nights (adjusted $5M floor), A1 list (757 main): {der:,}/{tot:,} = {der/max(tot,1):.2%}",
 f"(cross-check, all raw_src-2 names with floor nights, none pulled: {der_all:,}/{tot:,} = {der_all/max(tot,1):.2%}; pre-A1 print was 17,796 = 0.80%)",
 f"'era-B price partly derived' tag fires: {len(main)>0 and der>0}"]
(OUT / "A1.txt").write_text("\n".join(lines)+"\n"); print("\n".join(lines))
