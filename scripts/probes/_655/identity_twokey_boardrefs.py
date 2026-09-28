"""EXPLORATORY (post-hoc reference choice), same maths/bars as identity_twokey.py: the reference for a
driver = members of every OTHER live theme mapped to that driver (the board's own definition), T's members
excluded. Run on the same dual-home themes, with the same random-alternative null (200 draws). The null is
the guard against fitting: the reference choice was made after seeing identity_test.py's results."""
import random, statistics
from collections import Counter, defaultdict
import numpy as np
import identity_test as it
BAR, SEP = it.IDENTITY_GAP_BAR, it.SEP_GUARD
eco = it.load_taxonomy(); themes = it.load_themes(); closes = it.load_closes()
ex, sess = it.excess_for(closes, it.RUN_DATE)
by_eco = defaultdict(list)
for t in themes:
    if t["e_code"] in eco: by_eco[t["e_code"]].append(t)
def ref(code, T):
    tick = sorted({m for t in by_eco[code] if t["name"] != T["name"] for m in t["tickers"]} - set(T["tickers"]))
    return it.ref_series(ex, tick)
def contrast(T, named, alt):
    (rn, nn), (ra, na) = ref(named, T), ref(alt, T)
    if rn is None or ra is None: return None
    sep = it.corr(rn, ra); rows = []
    for m in T["tickers"]:
        if m in ex:
            a1, a2 = it.corr(ex[m], rn), it.corr(ex[m], ra)
            if a1 is not None and a2 is not None: rows.append((m, a1, a2, a2 - a1))
    if len(rows) < it.MIN_JUDGEABLE_MEMBERS: return None
    g = sep is not None and sep >= SEP
    mis = [r for r in rows if r[3] >= BAR] if not g else []
    sh = len(mis) / len(rows)
    v = "UNJUDGEABLE_COLLINEAR" if g else "MISMATCH" if sh >= .5 else "SPLIT" if sh > 0 else "CONSISTENT"
    return dict(rows=rows, sep=sep, share=sh, verdict=v, misfits=[r[0] for r in mis], sizes=(nn, na))
home = defaultdict(list)
for t in themes:
    for m in t["tickers"]: home[m].append(t)
cand = defaultdict(set)
for t in themes:
    if t["e_code"] not in eco: continue
    for m in t["tickers"]:
        for o in home[m]:
            if o["name"] != t["name"] and o["e_code"] in eco and o["e_code"] != t["e_code"]: cand[t["name"]].add(o["e_code"])
out = [f"window {sess[1]}..{sess[-1]}; BAR {BAR} SEP {SEP}; themes with a dual-home alternative: {len(cand)}"]
vc = Counter()
for t in themes:
    if t["name"] not in cand: continue
    best = None
    for alt in sorted(cand[t["name"]]):
        r = contrast(t, t["e_code"], alt)
        if r and (best is None or r["share"] > best[1]["share"]): best = (alt, r)
    if not best: vc["UNJUDGEABLE"] += 1; continue
    alt, r = best; vc[r["verdict"]] += 1
    out.append(f"  {r['verdict']:<22} {t['name'][:58]:<58} {t['e_code']}->{alt} share {r['share']:.2f} sep {r['sep']:.2f} refs {r['sizes']} misfits {r['misfits']}")
out.append(f"verdicts: {dict(vc)}")
rng = random.Random(655); codes = sorted(by_eco); rates, anyr = [], []
for _ in range(it.NULL_DRAWS):
    f = j = a = 0
    for t in themes:
        if t["name"] not in cand: continue
        r = contrast(t, t["e_code"], rng.choice([c for c in codes if c != t["e_code"]]))
        if r is None or r["verdict"] == "UNJUDGEABLE_COLLINEAR": continue
        j += 1; f += r["verdict"] == "MISMATCH"; a += r["verdict"] in ("MISMATCH", "SPLIT")
    rates.append(f / max(j, 1)); anyr.append(a / max(j, 1))
jud = vc["MISMATCH"] + vc["SPLIT"] + vc["CONSISTENT"]
out.append(f"NULL random alternative: MISMATCH median {statistics.median(rates):.2f} p95 {np.percentile(rates,95):.2f}; "
           f"MISMATCH-or-SPLIT median {statistics.median(anyr):.2f} p95 {np.percentile(anyr,95):.2f} | REAL MISMATCH {vc['MISMATCH']}/{jud}, "
           f"MISMATCH-or-SPLIT {vc['MISMATCH']+vc['SPLIT']}/{jud}")
# searched form with board refs, whole board, for comparison with the rejected exemplar version
flag = judged = 0; bad = []
for t in themes:
    if t["e_code"] not in eco: continue
    meds = {}
    for c in by_eco:
        rs, n = ref(c, t)
        if rs is None: continue
        vals = [it.corr(ex[m], rs) for m in t["tickers"] if m in ex]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2: meds[c] = (statistics.median(vals), vals)
    if t["e_code"] not in meds or len(meds) < 2: continue
    judged += 1
    alts = {c: v for c, v in meds.items() if c != t["e_code"]}
    b = max(alts, key=lambda c: alts[c][0]); gap = alts[b][0] - meds[t["e_code"]][0]
    rb, _ = ref(b, t); rn, _ = ref(t["e_code"], t); sep = it.corr(rb, rn)
    mems = [m for m in t["tickers"] if m in ex]
    share = sum(1 for m in mems if (it.corr(ex[m], rb) or 0) > (it.corr(ex[m], rn) or 0)) / max(len(mems), 1)
    if gap >= BAR and share >= .5 and (sep is None or sep < SEP):
        flag += 1; bad.append((t["name"][:50], t["e_code"], b, round(gap, 2)))
out.append(f"SEARCHED form with board-theme references: {flag} of {judged} flagged")
for x in bad: out.append(f"    {x}")
open(it.HERE / "identity_twokey_boardrefs_out.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
