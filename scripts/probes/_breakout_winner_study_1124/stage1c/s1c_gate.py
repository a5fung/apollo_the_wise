"""Stage 1c step 4: the four gates on the captured pull (read many, never re-pulled). usage: s1c_gate.py [pull.csv.gz] [meta.json]
Reads sealed local files (rows < 2025-01-01) + the pull. Writes stage1c/gate_result.json, notreturned.txt, gate.txt."""
import sys, json, gzip, csv, hashlib
sys.path.insert(0, "../stage1ab")
from common import *
assert_prereg()
import numpy as np
import v1_replay as R
from datetime import date
from collections import defaultdict
OUT = HERE.parent / "stage1c"
PULL = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "cb702" / "raw_close_bwin_1124.csv.gz"
META = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA / "cb702" / "raw_close_bwin_1124.meta.json"
meta = json.loads(META.read_text())
REQ = OUT / "bws1124_raw_request.tsv"
assert meta["request_sha256"] == hashlib.sha256(REQ.read_bytes()).hexdigest() == (OUT / "bws1124_raw_request.sha256").read_text().strip()
req = {r["ticker"]: r for r in csv.DictReader(REQ.open(), delimiter="\t")}
pull = defaultdict(dict); maxd = ""
for ln in gzip.open(PULL, "rt"):
    t, d, c, v = ln.rstrip("\n").split(",")
    pull[t][d] = (float(c), float(v)); maxd = max(maxd, d)
lines = []
def P(s): print(s, flush=True); lines.append(s)
S = R.load_store("B"); D = S.D; assert D.cal[-1] < date(2025, 1, 1)
splits, _ = R.load_splits_sealed(R.CB / "cb702_splits.psv")
cal = [d.isoformat() for d in D.cal]
tid = {t: k for k, t in enumerate(D.tickers)}
# (a)
ga = maxd <= "2024-12-31"; P(f"(a) max returned date {maxd} <= 2024-12-31: {ga}")
# (b) coverage per year: requested ticker-nights = store sessions of the ticker inside its request span
tick_ret = sum(1 for t in req if t in pull)
P(f"(b) tickers returned {tick_ret}/{len(req)} = {tick_ret/len(req):.1%}")
for tag in ("main", "ctlA_bridged", "ctlB_polygon"):
    ts = [t for t, r in req.items() if tag in r["sets"].split("+")]
    P(f"    set {tag}: tickers returned {sum(1 for t in ts if t in pull)}/{len(ts)}")
yr_req, yr_got = defaultdict(int), defaultdict(int)
for t, r in req.items():
    k = tid.get(t)
    if k is None: continue
    a, b = int(D.start[k]), int(D.stop[k])
    for i in range(a, b):
        d = cal[int(D.ci[i])]
        if r["first_date"] <= d <= r["last_date"]:
            yr_req[d[:4]] += 1; yr_got[d[:4]] += d in pull.get(t, {})
for y in sorted(yr_req): P(f"    {y}: ticker-nights returned {yr_got[y]:,}/{yr_req[y]:,} = {yr_got[y]/yr_req[y]:.1%}")
# (c) scale agreement on the control sets
def known_bridge(t):
    k = tid[t]; a, b = int(D.start[k]), int(D.stop[k])
    return {cal[int(D.ci[i])]: float(S.raw_factor[i] * D.c[i]) for i in range(a, b)}
poly = defaultdict(dict)
for f in ("raw_close_bv1_1101.csv.gz", "raw_close_tgrid_1101.csv.gz"):
    for ln in gzip.open(R.CB / f, "rt"):
        t, d, c = ln.strip().split(","); poly[t][d] = float(c)
gc = True
for tag, getk in (("ctlA_bridged", known_bridge), ("ctlB_polygon", lambda t: poly[t])):
    ts = [t for t, r in req.items() if tag in r["sets"].split("+")]
    agree = comp = 0; w05 = nrows = 0
    for t in ts:
        kn = getk(t); pr = pull.get(t, {})
        com = [(pr[d][0], kn[d]) for d in pr if d in kn and kn[d] > 0]
        if not com: continue
        comp += 1
        rel = np.abs(np.array([p / k_ - 1 for p, k_ in com]))
        agree += float(np.median(rel)) <= 0.10; w05 += int((rel <= 0.005).sum()); nrows += len(rel)
    share = agree / comp if comp else 0.0
    ok = comp > 0 and share >= 0.99; gc &= ok
    P(f"(c) {tag}: control tickers with comparable rows {comp}/{len(ts)}; agree (median |pulled/known-1| <= 10%) {agree} = {share:.2%} (pass >= 99%): {ok}; rows within 0.5%: {w05/max(nrows,1):.1%} of {nrows:,} (description)")
# (d) per pulled ticker: raw/adjusted stable between split dates, on rows with adjusted close >= $1
notret, nd_fail = [], 0
for t in sorted(pull):
    k = tid.get(t)
    if k is None: notret.append(t); continue
    a, b = int(D.start[k]), int(D.stop[k])
    adj = {cal[int(D.ci[i])]: float(D.c[i]) for i in range(a, b)}
    sp = sorted(e.isoformat() for e, _ in splits.get(t, []))
    segs = defaultdict(list)
    for d, (c, _) in pull[t].items():
        if d in adj and adj[d] >= 1.0:
            segs[sum(1 for e in sp if d >= e)].append(c / adj[d])
    bad = any(max(v) / min(v) - 1 > R.BRIDGE_TOL for v in segs.values() if min(v) > 0)
    if bad: nd_fail += 1; notret.append(t)
P(f"(d) pulled tickers {len(pull)}; failed raw/adjusted stability (BRIDGE_TOL {R.BRIDGE_TOL}) -> treated as NOT returned: {nd_fail}")
req_main = [t for t, r in req.items() if "main" in r["sets"].split("+")]
nr = sorted(set(req_main) - (set(pull) - set(notret)))
(OUT / "notreturned.txt").write_text("\n".join(nr) + "\n")
P(f"    main request names not returned or failed: {len(nr)}/{len(req_main)} -> derived-only handling (prereg 1.3), not a stop")
# derived-only share of pool candidates: era-B name-nights at the $5M floor (adjusted) for raw_src-2 names, with / without a good pulled close
good = set(pull) - set(notret); tot = der = 0
for k, t in enumerate(D.tickers):
    a, b = int(D.start[k]), int(D.stop[k]); c, v = D.c[a:b], D.v[a:b]
    ci = D.ci[a:b]; dv = R._rolling_median(c * v, R.cb.DOLLAR_VOL_WINDOW)
    m = (dv >= R.bv.MIN_DOLLAR_VOL) & (np.array([cal[int(x)] for x in ci]) >= "2022-04-01")
    n = int(m.sum()); tot += n
    if n and int(S.raw_src[a]) == 2 and t not in good: der += n
P(f"    derived-only share of era-B pool-candidate name-nights (adjusted $5M floor): {der:,}/{tot:,} = {der/max(tot,1):.2%}")
res = {"a": bool(ga), "c": bool(gc), "pull_rows": meta["rows"], "gate_pass": bool(ga and gc)}
(OUT / "gate_result.json").write_text(json.dumps(res, indent=1)); (OUT / "gate.txt").write_text("\n".join(lines) + "\n")
P(f"GATE {'PASS' if res['gate_pass'] else 'FAIL'}: {res}")
