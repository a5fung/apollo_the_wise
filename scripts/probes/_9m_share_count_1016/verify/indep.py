#!/usr/bin/env python3
"""VERIFIER — independent re-derivation of the 9M-share-count read (2026-10-16).

Does NOT import common.py, read.py or #684's study.py. Reads #684's features.tsv (row identity, block,
alerted, iso_week only) and daily.tsv.gz (bars) directly; recomputes gap-day shares, ADR20, the outcome,
RVOL50, terciles, the week-blocked permutation p (own implementation, several seeds), drop-best-week,
drop-two, AUCs and the tail tables. Read-only; writes only to stdout.
"""
import gzip, math, random, statistics, csv
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "_684"

rows = []
with (SRC / "features.tsv").open() as fh:
    rd = csv.DictReader(fh, delimiter="\t")
    for r in rd:
        rows.append({k: r[k] for k in ("ticker", "scan_date", "block", "alerted", "iso_week", "era",
                                       "CLOSE_vol_vs_avg50", "adr_dollar_ep", "O945_covered")})

bars = defaultdict(list)
with gzip.open(SRC / "daily.tsv.gz", "rt") as fh:
    hdr = None
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.startswith("("):
            continue
        p = line.split("|")
        if hdr is None:
            hdr = p; continue
        t, d, o, h, l, c, v = p
        if not (o and h and l and c):
            continue
        bars[t].append((d, float(o), float(h), float(l), float(c), float(v) if v else 0.0))
for t in bars:
    bars[t].sort()

orb = {}
with (SRC / "orb.tsv").open() as fh:
    hdr = None
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field sep"):
            continue
        p = line.split("|")
        if hdr is None:
            hdr = p; continue
        if len(p) != len(hdr):
            continue
        dd = dict(zip(hdr, p))
        orb[(dd["ticker"], dd["scan_date"])] = dd

pub_out = {}
with (SRC / "outcomes.tsv").open() as fh:
    for r in csv.DictReader(fh, delimiter="\t"):
        pub_out[(r["ticker"], r["scan_date"])] = r

mism_adr = mism_out = mism_rv = 0
for r in rows:
    b = bars.get(r["ticker"], [])
    ds = [x[0] for x in b]
    r["shares"] = r["run"] = r["rv50"] = None
    if r["scan_date"] not in ds:
        continue
    i = ds.index(r["scan_date"])
    g = b[i]
    r["shares"] = g[5]
    r["close"] = g[4]
    pre = b[:i]
    if len(pre) >= 21:
        adr = statistics.mean((x[2] - x[3]) / x[4] for x in pre[-20:] if x[4] > 0)
        adr_d = adr * g[4]
        r["adr_pct"] = adr * 100
        if r["adr_dollar_ep"] and abs(adr_d / float(r["adr_dollar_ep"]) - 1) > 1e-6:
            mism_adr += 1
        v50 = statistics.mean(x[5] for x in pre[-50:])
        r["rv50"] = g[5] / v50 if v50 > 0 else None
        if r["CLOSE_vol_vs_avg50"] and r["rv50"] and abs(r["rv50"] / float(r["CLOSE_vol_vs_avg50"]) - 1) > 1e-6:
            mism_rv += 1
        fwd = b[i + 1:i + 16]
        if len(fwd) == 15:
            r["run"] = (max(x[2] for x in fwd) - g[4]) / adr_d
    po = pub_out.get((r["ticker"], r["scan_date"]))
    if po and po["run_xadr"] and r["run"] is not None and abs(float(po["run_xadr"]) - r["run"]) > 0.002:
        mism_out += 1
    ob = orb.get((r["ticker"], r["scan_date"]))
    r["e_orb"] = float(ob["orb_vol"]) if (ob and r["O945_covered"] in ("1", "1.0") and ob.get("orb_vol")) else None

print("rows", len(rows), " shares present", sum(r["shares"] is not None and r["shares"] > 0 for r in rows))
print("ADR mismatches vs features.tsv:", mism_adr, " RVOL50 mismatches vs CLOSE_vol_vs_avg50:", mism_rv,
      " run_xadr mismatches vs #684 outcomes.tsv:", mism_out)
oc = [r for r in rows if r["run"] is not None]
print("outcome rows", len(oc), " >=5ADR", sum(r["run"] >= 5 for r in oc), " >=8ADR", sum(r["run"] >= 8 for r in oc))
cens = [r for r in rows if r["run"] is None]
print("censored:", [(r["ticker"], r["scan_date"], r["shares"]) for r in cens])
print(">=9M all:", sum(r["shares"] >= 9e6 for r in rows), "of", len(rows))

def grp(rs, f):
    a = [r for r in rs if f(r)]
    return a

def rate(rs, k):
    return sum(r["run"] >= k for r in rs), len(rs)

def show(name, rs, k=5):
    h, n = rate(rs, k)
    return f"{name}: {h}/{n} = {100*h/n:.1f}%"

disc = [r for r in oc if r["block"] == "DISCOVERY"]
held = [r for r in oc if r["block"] != "DISCOVERY"]
print("disc", len(disc), "runners", sum(r["run"] >= 5 for r in disc), " held", len(held),
      "runners", sum(r["run"] >= 5 for r in held), ">=8", sum(r["run"] >= 8 for r in held))

def terc(vals):
    s = sorted(vals); n = len(s)
    return s[max(0, n // 3 - 1)], s[min(n - 1, (2 * n) // 3)]

# discovery cuts computed on ALL discovery rows with the value (incl. censored), as #684 does? check both
disc_all = [r for r in rows if r["block"] == "DISCOVERY"]
lo_s_all, hi_s_all = terc([math.log10(r["shares"]) for r in disc_all])
lo_s, hi_s = terc([math.log10(r["shares"]) for r in disc])
print(f"shares tercile cut (disc, outcome rows) hi={10**hi_s:,.0f} lo={10**lo_s:,.0f};  (all disc rows) hi={10**hi_s_all:,.0f}")
rvd = [r for r in disc if r["rv50"] is not None]
lo_r, hi_r = terc([r["rv50"] for r in rvd])
print(f"rv50 tercile cut (disc) hi={hi_r:.3f} lo={lo_r:.3f}")

D = {
    "D1 >=9M": lambda r: r["shares"] >= 9e6,
    "D2 shares top3": lambda r: math.log10(r["shares"]) >= hi_s,
    "D3 rv50 top3": lambda r: r["rv50"] is not None and r["rv50"] >= hi_r,
}

def diff(rs, lab, fav):
    a = [l for l, f in zip(lab, fav) if f]; b = [l for l, f in zip(lab, fav) if not f]
    return sum(a) / len(a) - sum(b) / len(b)

def permp(rs, favf, seed, n=2000):
    rs = [r for r in rs if (r["rv50"] is not None or favf is not D["D3 rv50 top3"])]
    lab = [int(r["run"] >= 5) for r in rs]
    fav = [favf(r) for r in rs]
    obs = diff(rs, lab, fav)
    wk = defaultdict(list)
    for i, r in enumerate(rs):
        wk[r["iso_week"]].append(i)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n):
        L = lab[:]
        for g in wk.values():
            v = [lab[i] for i in g]; rng.shuffle(v)
            for i, x in zip(g, v): L[i] = x
        if diff(rs, L, fav) >= obs - 1e-12:
            hits += 1
    return obs, hits / n

def auc(vals, lab):
    pos = [v for v, l in zip(vals, lab) if l]; neg = [v for v, l in zip(vals, lab) if not l]
    w = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return w / (len(pos) * len(neg))

wk_runners = defaultdict(int)
for r in disc:
    wk_runners[r["iso_week"]] += r["run"] >= 5
best_wk = max(wk_runners, key=wk_runners.get)
top2 = sorted([r for r in disc], key=lambda r: -r["run"])[:2]
print("best week", best_wk, wk_runners[best_wk], " two biggest disc:", [(r["ticker"], r["scan_date"], round(r["run"], 2)) for r in top2])

for name, f in D.items():
    dr = [r for r in disc if (r["rv50"] is not None or name[:2] != "D3")]
    fa = [r for r in dr if f(r)]; re_ = [r for r in dr if not f(r)]
    hf = [r for r in held if (r["rv50"] is not None or name[:2] != "D3") and f(r)]
    hr = [r for r in held if (r["rv50"] is not None or name[:2] != "D3") and not f(r)]
    ps = [permp(disc, f, s)[1] for s in (9016, 684, 1, 2, 3)]
    obs = permp(disc, f, 9016, 1)[0]
    wkd = [r for r in disc if r["iso_week"] != best_wk]
    o_w, p_w = permp(wkd, f, 9016)
    t2 = [r for r in disc if r not in top2]
    o_t, p_t = permp(t2, f, 9016)
    print(f"{name}: {show('fav', fa)} | {show('rest', re_)} | diff {100*obs:+.1f}pp | perm p seeds 9016/684/1/2/3 = {ps}"
          f" | held {sum(r['run']>=5 for r in hf)}/{len(hf)} vs {sum(r['run']>=5 for r in hr)}/{len(hr)}"
          f" | drop week {100*o_w:+.1f}pp p {p_w:.3f} | drop two {100*o_t:+.1f}pp p {p_t:.3f}")

# head-to-head AUC on discovery rows with both
both = [r for r in disc if r["rv50"] is not None]
lab = [int(r["run"] >= 5) for r in both]
a_s = auc([r["shares"] for r in both], lab); a_r = auc([r["rv50"] for r in both], lab)
print(f"AUC disc n {len(both)} runners {sum(lab)}: shares {a_s:.3f} rv50 {a_r:.3f} diff {a_s-a_r:+.3f}")
# paired permutation: swap per-row percentile ranks with p 1/2
def pct_rank(v):
    s = sorted(v); n = len(s)
    import bisect
    return [(bisect.bisect_left(s, x) + bisect.bisect_right(s, x)) / (2 * n) for x in v]
ps_ = pct_rank([r["shares"] for r in both]); pr_ = pct_rank([r["rv50"] for r in both])
obs = auc(ps_, lab) - auc(pr_, lab)
rng = random.Random(9016); hits = 0
for _ in range(2000):
    A, B = [], []
    for x, y in zip(ps_, pr_):
        if rng.random() < 0.5: A.append(y); B.append(x)
        else: A.append(x); B.append(y)
    if auc(A, lab) - auc(B, lab) >= obs - 1e-12: hits += 1
print(f"paired perm (own impl, seed 9016): obs {obs:+.3f} p {hits/2000:.3f}")

# tail, all outcome rows
print("\nTAIL all outcome rows:")
for name, f in [(">=9M", lambda r: r["shares"] >= 9e6), ("<9M", lambda r: r["shares"] < 9e6)]:
    g = [r for r in oc if f(r)]
    runs = sorted(r["run"] for r in g)
    print(f"  {name}: n {len(g)} >=5 {sum(x>=5 for x in runs)} ({100*sum(x>=5 for x in runs)/len(g):.1f}%) >=8 {sum(x>=8 for x in runs)} ({100*sum(x>=8 for x in runs)/len(g):.1f}%)"
          f" median {statistics.median(runs):.2f} mean {statistics.mean(runs):.2f}")
top15 = sorted(oc, key=lambda r: -r["run"])[:15]
print("  top 15 runs:", [(r["ticker"], r["scan_date"], round(r["run"], 1), round(r["shares"] / 1e6, 1)) for r in top15])
print("  top 15 under 9M:", sum(r["shares"] < 9e6 for r in top15))
# where are the 26 >=8 runners by ADR
al = [r for r in oc if r["alerted"] in ("1", "1.0", "True")]
print("\nALERTED outcome rows", len(al))
for name, f in [(">=9M", lambda r: r["shares"] >= 9e6), ("<9M", lambda r: r["shares"] < 9e6)]:
    g = [r for r in al if f(r)]
    print(f"  {name}: n {len(g)} >=5 {sum(r['run']>=5 for r in g)} ({100*sum(r['run']>=5 for r in g)/len(g):.1f}%) >=8 {sum(r['run']>=8 for r in g)} ({100*sum(r['run']>=8 for r in g)/len(g):.1f}%)")

# post-hoc W19
print("\nPOSTHOC by week (disc):")
w19 = [r for r in disc if r["iso_week"] == best_wk]; oth = [r for r in disc if r["iso_week"] != best_wk]
for nm, g in (("best wk", w19), ("others", oth)):
    a = [r for r in g if r["shares"] >= 9e6]; b = [r for r in g if r["shares"] < 9e6]
    print(f"  {nm}: >=9M {sum(r['run']>=5 for r in a)}/{len(a)}  <9M {sum(r['run']>=5 for r in b)}/{len(b)}")
# high-ADR band
adrs = sorted(r["adr_pct"] for r in oc)
c1, c2 = adrs[len(adrs) // 3], adrs[2 * len(adrs) // 3]
print(f"  ADR tercile cuts (all oc) {c1:.2f} {c2:.2f}")
for nm, f in (("low", lambda r: r["adr_pct"] < c1), ("mid", lambda r: c1 <= r["adr_pct"] < c2), ("high", lambda r: r["adr_pct"] >= c2)):
    g = [r for r in oc if f(r)]
    a = [r for r in g if r["shares"] >= 9e6]; b = [r for r in g if r["shares"] < 9e6]
    print(f"  ADR {nm}: >=9M {sum(r['run']>=5 for r in a)}/{len(a)} (>=8 {sum(r['run']>=8 for r in a)})  <9M {sum(r['run']>=5 for r in b)}/{len(b)} (>=8 {sum(r['run']>=8 for r in b)})")

# early proxy
e = [r for r in rows if r["e_orb"] and r["shares"]]
fr = sorted(r["e_orb"] / r["shares"] for r in e)
print(f"\nfirst-15-min / day: n {len(fr)} median {statistics.median(fr):.3f}")
ed = [r for r in disc if r["e_orb"]]
lo_e, hi_e = terc([r["e_orb"] for r in ed])
fa = [r for r in ed if r["e_orb"] >= hi_e]; re_ = [r for r in ed if r["e_orb"] < hi_e]
print(f"early top third (>= {hi_e:,.0f}): {show('fav', fa)} | {show('rest', re_)}")
# rank corr shares vs e_orb
def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); rk = [0] * len(v)
    for j, i in enumerate(o): rk[i] = j
    return rk
ee = [r for r in rows if r["e_orb"] and r["shares"]]
a, b = ranks([r["shares"] for r in ee]), ranks([r["e_orb"] for r in ee])
ma, mb = statistics.mean(a), statistics.mean(b)
rho = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
print(f"rank corr shares vs 09:30-09:44 shares: {rho:.3f} (n {len(ee)})")

# RVOL terciles (discovery cuts) on all outcome rows and on alerted rows
print("\nRVOL50 terciles (disc cuts", round(lo_r, 3), round(hi_r, 3), ")")
for nm, pool in (("all", oc), ("alerted", al)):
    for tn, f in (("bottom", lambda r: r["rv50"] <= lo_r), ("mid", lambda r: lo_r < r["rv50"] < hi_r), ("top", lambda r: r["rv50"] >= hi_r)):
        g = [r for r in pool if r["rv50"] is not None and f(r)]
        print(f"  {nm} {tn}: n {len(g)} >=5 {sum(r['run']>=5 for r in g)} ({100*sum(r['run']>=5 for r in g)/len(g):.1f}%) >=8 {sum(r['run']>=8 for r in g)} mean {statistics.mean(r['run'] for r in g):.2f}")
print("share of all outcome rows under 9M:", f"{sum(r['shares']<9e6 for r in oc)}/{len(oc)}", " share of >=8 ADR under 9M:",
      f"{sum(r['shares']<9e6 for r in oc if r['run']>=8)}/{sum(r['run']>=8 for r in oc)}")
