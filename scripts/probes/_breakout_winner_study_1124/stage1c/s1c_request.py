"""Stage 1c steps 1-3a: sealed bar copy, request list (written ONCE, sha pinned). NO network. Reads only rows < 2025-01-01."""
import sys, json, gzip, hashlib, random
sys.path.insert(0, "../stage1ab")
from common import *
assert_prereg()
import numpy as np
import v1_replay as R
from datetime import date
OUT = HERE.parent / "stage1c"
REQ = OUT / "bws1124_raw_request.tsv"
assert not REQ.exists(), "request is written once, never rewritten"
S = R.load_store("B")
D = S.D
assert D.cal[-1] < date(2025, 1, 1), D.cal[-1]
cal = list(D.cal)
# era-B nights: D >= 2022-04-01 .. last D whose E+60 session is <= 2024-12-31
dates_idx = [i for i, d in enumerate(cal) if d >= date(2022, 4, 1)]
last_ci = len(cal) - 1
# E = ci+1 ; need ci(E)+60 <= last_ci  ->  ci_D + 61 <= last_ci
nights = [i for i in dates_idx if i + 61 <= last_ci]
n_lo, n_hi = min(nights), max(nights)
print("era-B nights", cal[n_lo], cal[n_hi], len(nights))
span = {}; src_cnt = {0: 0, 1: 0, 2: 0}
for k, t in enumerate(D.tickers):
    a, b = int(D.start[k]), int(D.stop[k])
    src_cnt[int(S.raw_src[a])] += 1
src2 = [k for k, t in enumerate(D.tickers) if int(S.raw_src[int(D.start[k])]) == 2]
src1 = [k for k, t in enumerate(D.tickers) if int(S.raw_src[int(D.start[k])]) == 1]
print("tickers by raw_src", src_cnt)
rows = []
for k in src2:
    a, b = int(D.start[k]), int(D.stop[k])
    c, v = D.c[a:b], D.v[a:b]; cidx = D.ci[a:b].astype(np.int64)
    dv = R._rolling_median(c * v, R.cb.DOLLAR_VOL_WINDOW)      # adjusted close x adjusted volume: does not touch the raw scale
    ok = (dv >= R.bv.MIN_DOLLAR_VOL) & (cidx >= n_lo) & (cidx <= n_hi)
    if ok.any():
        idx = np.nonzero(ok)[0]
        rows.append((D.tickers[k], cal[int(cidx[idx[0]])], cal[int(cidx[idx[-1]])], int(ok.sum())))
print("split-list-only tickers", len(src2), "-> passing the $5M floor on >=1 era-B night:", len(rows))
rows.sort()
req_set = {r[0] for r in rows}
# control set 1: seeded 300 of the bridged tickers (known raw = bridge factor x adjusted close) that have bars in era B
rng = random.Random(1124)
elig1 = []
for k in src1:
    a, b = int(D.start[k]), int(D.stop[k]); cidx = D.ci[a:b]
    m = (cidx >= n_lo) & (cidx <= n_hi)
    if m.any():
        idx = np.nonzero(m)[0]
        elig1.append((D.tickers[k], cal[int(cidx[idx[0]])], cal[int(cidx[idx[-1]])], int(m.sum())))
elig1.sort()
ctl1 = sorted(rng.sample(elig1, 300))
print("bridged tickers with era-B bars", len(elig1), "-> control A 300")
# control set 2: tickers of the 11-01 Polygon pulls (bv1 + tgrid), dates < 2025
poly = {}
for f in ("raw_close_bv1_1101.csv.gz", "raw_close_tgrid_1101.csv.gz"):
    for ln in gzip.open(DATA / "cb702" / f, "rt"):
        t, d, c = ln.strip().split(",")
        assert d < "2025-01-01"
        lo, hi = poly.get(t, (d, d)); poly[t] = (min(lo, d), max(hi, d))
print("polygon-pull tickers (union)", len(poly))
ctl2 = [(t, lo, hi, 0) for t, (lo, hi) in sorted(poly.items())]
allrows = {}
for tag, lst in (("main", rows), ("ctlA_bridged", ctl1), ("ctlB_polygon", ctl2)):
    for t, lo, hi, n in lst:
        lo, hi = str(lo), str(hi)
        if t in allrows:
            o = allrows[t]; allrows[t] = (min(o[0], lo), max(o[1], hi), o[2] + [tag])
        else:
            allrows[t] = (lo, hi, [tag])
assert all(h <= "2024-12-31" for _, h, _ in allrows.values()), "a request row carries a date after 2024-12-31"
with open(REQ, "w") as f:
    f.write("ticker\tfirst_date\tlast_date\tsets\n")
    for t in sorted(allrows):
        lo, hi, tags = allrows[t]
        f.write(f"{t}\t{lo}\t{hi}\t{'+'.join(sorted(set(tags)))}\n")
sha = hashlib.sha256(REQ.read_bytes()).hexdigest()
(OUT / "bws1124_raw_request.sha256").write_text(sha + "\n")
res = {"nights": [str(cal[n_lo]), str(cal[n_hi]), len(nights)], "src2_tickers": len(src2), "request_main": len(rows),
       "ctlA": len(ctl1), "ctlB": len(ctl2), "request_total": len(allrows), "request_sha256": sha,
       "max_request_date": max(h for _, h, _ in allrows.values()),
       "overlap_main_ctlB": len(req_set & set(poly)), "overlap_main_ctlA": len(req_set & {x[0] for x in ctl1})}
(OUT / "request_result.json").write_text(json.dumps(res, indent=1))
print(res)
