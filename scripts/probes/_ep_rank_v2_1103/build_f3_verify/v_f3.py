#!/usr/bin/env python3
"""BLIND VERIFIER — re-defined feature 3 ("pullbacks held the top of the base it broke out of").

Written from build_f3/F3_DEFINITION.md + the encoder's adr20_pct + rank_v2.py's R3 text only.
The builder's f3_def.py / rank_v2_f3.py / kod_check.py were NOT read before this ran.
Research only, $0, offline: ../bars.csv.gz, ../pairs.tsv, ../shadow_rows.csv,
../../_rank_shadow_running_read_1103/rows.psv (cross-check only), the ruling fixture, the EP doc.
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import random
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
REPO = Path("/Users/alvinfung/apollo_the_wise")
OUT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.append(s)


# ---------------------------------------------------------------- load (own loader)
bars = defaultdict(list)
with gzip.open(DATA / "bars.csv.gz", "rt") as f:
    for r in csv.DictReader(f):
        try:
            o, h, l, c = (float(r[k]) for k in ("open_price", "high_price", "low_price", "close"))
        except (TypeError, ValueError):
            continue
        if c <= 0 or h <= 0:
            continue
        bars[r["ticker"]].append((r["trade_date"], o, h, l, c, float(r["volume"] or 0)))
for t in bars:
    bars[t].sort()
    ds = [x[0] for x in bars[t]]
    assert len(ds) == len(set(ds)), f"duplicate dates {t}"

pairs = list(csv.DictReader(open(DATA / "pairs.tsv"), delimiter="\t"))


def five_y(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    try:
        return date(y - 5, m, dd).isoformat()
    except ValueError:
        return date(y - 5, m, 28).isoformat()


def slice_to(t, d):
    rows = bars.get(t)
    if not rows:
        return None, None
    sl = [x for x in rows if five_y(d) <= x[0] <= d]
    if not sl or sl[-1][0] != d:
        return None, None
    return sl, len(sl) - 1


def adr20(sl, ia):
    win = sl[max(0, ia - 20):ia]
    if len(win) < 10:
        return None
    return sum((h - l) / c * 100.0 for _, _, h, l, c, _ in win) / len(win)


STATED = dict(run_win=60, shelf_win=45, p_end=250, pb_win=40, band=1.0, run_min=0.30,
              p_start=41, couple=False, run_incl=True, shelf_incl=True)


def f3(t, d, prm=STATED):
    prm = {**STATED, **prm}
    o = dict(held=None, into=None, d1=None, d2=None, null=None, structure=None, shelf=None,
             shelf_date=None, S=None, S_date=None, P=None, P_date=None, run=None, adr=None,
             lows=None, touched_max=None, ia=None)
    sl, ia = slice_to(t, d)
    if sl is None:
        o["null"] = "no_bar_on_D"
        return o
    o["ia"] = ia
    touched = []
    pe = prm["p_end"]
    ps = (prm["pb_win"] + 1) if prm["couple"] else prm["p_start"]
    if ia < pe:
        o["null"] = f"history<{pe}({ia})"
        return o
    adr = adr20(sl, ia)
    touched += list(range(max(0, ia - 20), ia))
    o["adr"] = adr
    # (1) P = highest high of sessions ps..pe before D, latest on ties
    pidx = list(range(ia - pe, ia - ps + 1))
    touched += pidx
    ph = max(sl[i][2] for i in pidx)
    pi = max(i for i in pidx if sl[i][2] == ph)
    o["P"], o["P_date"] = ph, sl[pi][0]
    # (2) S = lowest low of the run_win sessions ending at P (P included), latest on ties
    rw = prm["run_win"]
    s0 = pi - (rw - 1) if prm["run_incl"] else pi - rw
    if s0 < 0:
        o["null"] = f"run_window_before_history(start {s0})"
        return o
    sidx = list(range(s0, pi + 1))
    touched += sidx
    sv = min(sl[i][3] for i in sidx)
    si = max(i for i in sidx if sl[i][3] == sv)
    o["S"], o["S_date"] = sv, sl[si][0]
    # (3) shelf = highest high of the shelf_win sessions ending at S (S included), latest on ties
    sw = prm["shelf_win"]
    b0 = si - (sw - 1) if prm["shelf_incl"] else si - sw
    if b0 < 0:
        o["null"] = f"shelf_window_before_history(start {b0})"
        return o
    bidx = list(range(b0, si + 1))
    touched += bidx
    shv = max(sl[i][2] for i in bidx)
    shi = max(i for i in bidx if sl[i][2] == shv)
    o["shelf"], o["shelf_date"] = shv, sl[shi][0]
    o["run"] = ph / sv - 1
    if adr is None or adr <= 0:
        o["null"] = "no_adr"
        return o
    # (5) swing lows: pivot in the pb_win sessions before D, wings +-2, all wings < D
    pw = prm["pb_win"]
    sw_l = []
    for i in range(ia - pw, ia):
        if i - 2 < 0 or i + 2 >= ia:
            continue
        L = sl[i][3]
        if L <= sl[i - 1][3] and L <= sl[i - 2][3] and L < sl[i + 1][3] and L < sl[i + 2][3]:
            sw_l.append((L, i))
            touched += [i - 2, i - 1, i, i + 1, i + 2]
    sw_l.sort()
    if len(sw_l) < 2:
        o["null"] = f"swing_lows={len(sw_l)}"
        return o
    (l1, i1), (l2, i2) = sw_l[0], sw_l[1]
    o["lows"] = f"{sl[i1][0]} {l1:.2f}, {sl[i2][0]} {l2:.2f}"
    d1 = (l1 / shv - 1) * 100 / adr
    d2 = (l2 / shv - 1) * 100 / adr
    o["d1"], o["d2"] = d1, d2
    ok_run = o["run"] >= prm["run_min"]
    ok_brk = ph > shv
    o["structure"] = "ok" if (ok_run and ok_brk) else ("no_run" if not ok_run else "no_breakout")
    band = prm["band"]
    if o["structure"] == "ok":
        o["held"] = 1 if (d1 >= -band and d2 >= -band) else 0
        o["into"] = 1 if (abs(d1) <= band and abs(d2) <= band) else 0
    else:
        o["held"] = 0
        o["into"] = 0
    o["into_ungated"] = 1 if (abs(d1) <= band and abs(d2) <= band) else 0
    o["touched_max"] = max(touched)
    assert o["touched_max"] < ia, f"LOOK-AHEAD {t} {d}"
    return o


def auc(y, n):
    if not y or not n:
        return None
    s = 0.0
    for a in y:
        for b in n:
            s += 1.0 if a > b else (0.5 if a == b else 0.0)
    return s / (len(y) * len(n))


def boot(y, n, B=2000, seed=20261103):
    rng = random.Random(seed)
    xs = []
    for _ in range(B):
        yy = [rng.choice(y) for _ in y]
        nn = [rng.choice(n) for _ in n]
        xs.append(auc(yy, nn))
    xs.sort()
    return xs[int(0.05 * B)], xs[int(0.95 * B)]


YES = {"GOOD_CHART", "OKISH_CHART"}
NO = {"BAD_CHART"}

# ---------------------------------------------------------------- population checks
P("=" * 100)
P("BLIND VERIFY — re-defined F3 (build_f3/F3_DEFINITION.md)")
P("=" * 100)
spec = importlib.util.spec_from_file_location("fx", REPO / "tests/fixtures/must_not_trade_charts.py")
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)
fix = {(r.ticker, r.alert_date): r.verdict for r in fx.CHART_RULINGS}
pa = {(p["ticker"], p["date"]): p["label"] for p in pairs if p["source"] == "A"}
P(f"[pop] fixture rulings {len(fix)} · pairs.tsv A {len(pa)} · identical (keys+verdicts): {fix == pa}")
if fix != pa:
    P("   diff:", set(fix.items()) ^ set(pa.items()))
yesA = [k for k, v in pa.items() if v in YES]
noA = [k for k, v in pa.items() if v in NO]
P(f"[pop] A yes {len(yesA)} / no {len(noA)} / excluded {len(pa) - len(yesA) - len(noA)}")
doc = (REPO / "docs/methodology/operator_labelled_eps.md").read_text()
docB = set(re.findall(r"^\| \*\*([A-Z]+)\*\* \| (\d{4}-\d{2}-\d{2}) \|", doc, re.M))
pB = {(p["ticker"], p["date"]) for p in pairs if p["source"] == "B" and p["label"] == "operator"}
P(f"[pop] labelled-EP doc rows {len(docB)} · pairs.tsv B(operator) {len(pB)} · identical: {docB == pB}")
sh = list(csv.DictReader(open(DATA / "shadow_rows.csv")))
shC = {(r["ticker"], r["alert_date"]) for r in sh if r["alert_date"] > "2026-08-16"}
pC = {(p["ticker"], p["date"]) for p in pairs if p["source"] == "C"}
P(f"[pop] shadow rows > 2026-08-16 {len(shC)} · pairs.tsv C {len(pC)} · identical: {shC == pC}")
P(f"[pop] bar data max date: {max(x[-1][0] for x in bars.values())}")

# ---------------------------------------------------------------- KOD
P("\n[KOD] 2026-09-28 stated + 12 variants")
VARS = [("stated", {}), ("adr_mult=0.5", dict(band=0.5)), ("adr_mult=1.5", dict(band=1.5)),
        ("pb_win=20", dict(pb_win=20)), ("pb_win=60", dict(pb_win=60)),
        ("base_end=125", dict(p_end=125)), ("base_end=375", dict(p_end=375)),
        ("run_win=30", dict(run_win=30)), ("run_win=90", dict(run_win=90)),
        ("shelf_win=22", dict(shelf_win=22)), ("shelf_win=68", dict(shelf_win=68)),
        ("run_min=0.15", dict(run_min=0.15)), ("run_min=0.45", dict(run_min=0.45))]
for nm, v in VARS:
    o = f3("KOD", "2026-09-28", v)
    ia = o["ia"]
    sl, _ = slice_to("KOD", "2026-09-28")
    di = {x[0]: i for i, x in enumerate(sl)}
    off = lambda dt: f"D-{ia - di[dt]}" if dt else "-"
    P(f"  {nm:<13} P {o['P_date']} {o['P']:.2f} ({off(o['P_date'])})  S {o['S_date']} {o['S']:.2f} "
      f"({off(o['S_date'])})  shelf {o['shelf_date']} {o['shelf']:.2f} ({off(o['shelf_date'])})  run "
      f"{o['run']*100:.0f}%  lows {o['lows']}  d {o['d1']:+.3f}/{o['d2']:+.3f}  {o['structure']} "
      f"held {o['held']} into {o['into']}  ADR {o['adr']:.4f} hist {ia}")

# ---------------------------------------------------------------- all pairs, stated
res = {}
for p in pairs:
    res[(p["ticker"], p["date"], p["source"])] = f3(p["ticker"], p["date"])

with open(HERE / "f3_verify.tsv", "w") as fo:
    cols = ["ticker", "date", "source", "label", "held", "into", "into_ungated", "d1", "d2", "shelf",
            "shelf_date", "S", "S_date", "P", "P_date", "run", "structure", "null", "lows", "adr", "ia",
            "touched_max"]
    fo.write("\t".join(cols) + "\n")
    for p in pairs:
        o = res[(p["ticker"], p["date"], p["source"])]
        row = [p["ticker"], p["date"], p["source"], p["label"]] + [
            "" if o.get(k) is None else (f"{o[k]:.6f}" if isinstance(o[k], float) else str(o[k]))
            for k in cols[4:]]
        fo.write("\t".join(row) + "\n")

# ---------------------------------------------------------------- diff vs builder's tsv (claims)
bt = list(csv.DictReader(open(DATA / "build_f3/f3_features.tsv"), delimiter="\t"))
bmap = {(r["ticker"], r["date"], r["source"]): r for r in bt}
P(f"\n[diff] builder f3_features.tsv rows {len(bt)} · mine {len(res)} · same keys: {set(bmap) == set(res)}")


def diff(R, tag, verbose=True):
    nd = 0
    lines = []
    for k, o in R.items():
        b = bmap.get(k)
        if b is None:
            lines.append(f"  missing in builder: {k}")
            nd += 1
            continue
        issues = []
        bh = None if b["held_new"] == "" else int(b["held_new"])
        if bh != o["held"]:
            issues.append(f"held {bh} vs mine {o['held']}")
        bi = None if b["into"] == "" else int(b["into"])
        if bi != o["into"]:
            issues.append(f"into {bi} vs mine {o['into']}")
        for bk, mk, tol in (("d1_adr", "d1", 6e-5), ("d2_adr", "d2", 6e-5), ("shelf", "shelf", 6e-5),
                            ("s_low", "S", 6e-5), ("p_high", "P", 6e-5)):
            bv = None if b[bk] == "" else float(b[bk])
            mv = o[mk]
            if (bv is None) != (mv is None) or (bv is not None and abs(bv - mv) > tol * max(1, abs(mv))):
                issues.append(f"{bk} {bv} vs mine {None if mv is None else round(mv, 4)}")
        for bk, mk in (("shelf_date", "shelf_date"), ("s_date", "S_date"), ("p_date", "P_date")):
            if (b[bk] or None) != o[mk]:
                issues.append(f"{bk} {b[bk]} vs mine {o[mk]}")
        bs = (b["structure"] or "").split("(")[0] or None
        if bs != o["structure"]:
            issues.append(f"structure {b['structure']} vs mine {o['structure']}")
        if bool(b["null"]) != bool(o["null"]):
            issues.append(f"null '{b['null']}' vs mine '{o['null']}'")
        if issues:
            nd += 1
            lines.append(f"  {k}: " + "; ".join(issues))
    P(f"[diff:{tag}] pairs with any mismatch vs builder tsv: {nd} of {len(R)}")
    if verbose:
        for ln in lines:
            P(ln)
    return nd


diff(res, "stated as I read it: run P-59..P (60 incl), shelf S-44..S (45 incl)")
for rin, sin, tg in ((False, True, "run P-60..P (61), shelf S-44..S (45)"),
                     (True, False, "run P-59..P (60), shelf S-45..S (46)"),
                     (False, False, "run P-60..P (61), shelf S-45..S (46)")):
    RR_ = {(p["ticker"], p["date"], p["source"]): f3(p["ticker"], p["date"], {"run_incl": rin, "shelf_incl": sin}) for p in pairs}
    diff(RR_, tg, verbose=(not rin and not sin))

# ---------------------------------------------------------------- score A
def score(R):
    y = [R[(t, d, "A")] for (t, d) in yesA]
    n = [R[(t, d, "A")] for (t, d) in noA]
    yv = [o["held"] for o in y if o["held"] is not None]
    nv = [o["held"] for o in n if o["held"] is not None]
    return y, n, yv, nv


y, n, yv, nv = score(res)
a = auc(yv, nv)
ci = boot(yv, nv)
ci2 = boot(yv, nv, seed=7)
P(f"\n[A] held: P(yes>no) {a:.4f} n {len(yv)}/{len(nv)}  held=1 yes {sum(yv)}/{len(yv)} no {sum(nv)}/{len(nv)}"
  f"  90% CI (seed 20261103) [{ci[0]:.3f}, {ci[1]:.3f}]  (seed 7) [{ci2[0]:.3f}, {ci2[1]:.3f}]  qualifies>=0.65: {max(a,1-a) >= 0.65}")
iy = [o["into"] for o in y if o["into"] is not None]
inn = [o["into"] for o in n if o["into"] is not None]
P(f"[A] into (structure-gated): P(yes>no) {auc(iy, inn):.4f}  yes {sum(iy)}/{len(iy)} no {sum(inn)}/{len(inn)}")
iyu = [o["into_ungated"] for o in y if o["held"] is not None]
inu = [o["into_ungated"] for o in n if o["held"] is not None]
P(f"[A] into (UNgated by structure): P(yes>no) {auc(iyu, inu):.4f}  yes {sum(iyu)}/{len(iyu)} no {sum(inu)}/{len(inu)}")
dy = [min(o["d1"], o["d2"]) for o in y if o["held"] is not None]
dn = [min(o["d1"], o["d2"]) for o in n if o["held"] is not None]
P(f"[A] dmin descriptive: P(yes>no) {auc(dy, dn):.4f}  yes median {st.median(dy):.3f} (n {len(dy)})  no median {st.median(dn):.3f} (n {len(dn)})")
P("[A] NULLs:", "; ".join(f"{t} {d} {pa[(t,d)]} {res[(t,d,'A')]['null']}" for (t, d) in yesA + noA if res[(t, d, 'A')]['held'] is None))

P("\n[A] boundary pairs (|d| near 1 ADR), full precision:")
for (t, d) in yesA + noA:
    o = res[(t, d, "A")]
    if o["d1"] is None:
        continue
    if min(abs(o["d1"] + 1), abs(o["d2"] + 1), abs(abs(o["d1"]) - 1), abs(abs(o["d2"]) - 1)) < 0.25 or \
            (o["d1"] < 0 and o["d1"] > -1.5):
        adr_r = round(o["adr"], 2)
        d1r = (o["d1"] * o["adr"]) / adr_r
        d2r = (o["d2"] * o["adr"]) / adr_r
        hr = 1 if (o["structure"] == "ok" and d1r >= -1 and d2r >= -1) else 0
        P(f"   {t:<5} {d} {pa[(t,d)]:<11} d1 {o['d1']:+.5f} d2 {o['d2']:+.5f} ADR {o['adr']:.5f} held {o['held']} "
          f"into {o['into']} | with ADR rounded to {adr_r}: d1 {d1r:+.5f} d2 {d2r:+.5f} held {hr} | {o['structure']} lows {o['lows']}")

# ---------------------------------------------------------------- per-pair A table
P("\n[A] per pair (mine): ticker date label held into d1 d2 shelf S P run structure/null")
for (t, d) in yesA + noA:
    o = res[(t, d, "A")]
    fmt = lambda v: "NULL" if v is None else (f"{v:+.2f}" if isinstance(v, float) else str(v))
    P(f"   {t:<5} {d} {pa[(t,d)]:<11} {fmt(o['held']):>4} {fmt(o['into']):>4} {fmt(o['d1']):>7} {fmt(o['d2']):>7} "
      f"{o['shelf_date'] or '-'} {o['shelf'] or '-'} | {o['S_date'] or '-'} {o['S'] or '-'} | {o['P_date'] or '-'} {o['P'] or '-'} | "
      f"{'' if o['run'] is None else f'{o[chr(114)+chr(117)+chr(110)]*100:.0f}%'} {o['structure'] or o['null']}")

# ---------------------------------------------------------------- B
P("\n[B] his 8 labelled EPs")
bh = []
for p in pairs:
    if p["source"] == "B" and p["label"] == "operator":
        o = res[(p["ticker"], p["date"], "B")]
        bh.append(o["held"])
        P(f"   {p['ticker']:<5} {p['date']} held {o['held']} into {o['into']} d "
          f"{'NULL' if o['d1'] is None else f'{o[chr(100)+chr(49)]:+.2f}/{o[chr(100)+chr(50)]:+.2f}'} shelf {o['shelf_date']} {o['shelf']} "
          f"run {'' if o['run'] is None else f'{o[chr(114)+chr(117)+chr(110)]*100:.0f}%'} {o['structure'] or o['null']}")
P(f"[B] held=1 on {sum(x for x in bh if x is not None)} of {sum(1 for x in bh if x is not None)} non-NULL ({sum(1 for x in bh if x is None)} NULL)")

# coverage
cov = defaultdict(lambda: defaultdict(int))
nulls = defaultdict(list)
for p in pairs:
    src = p["source"] if not (p["source"] == "B" and p["label"] != "operator") else "B2"
    o = res[(p["ticker"], p["date"], p["source"])]
    if o["held"] is None:
        nulls[src].append(f"{p['ticker']} {p['date']} ({o['null']})")
    else:
        cov[src][o["structure"]] += 1
P(f"\n[coverage] NULL total {sum(len(v) for v in nulls.values())}: " + " | ".join(f"{k} {len(v)}" for k, v in nulls.items()))
for k, v in nulls.items():
    P(f"   {k}: " + "; ".join(v))
P("   structure among non-NULL: " + " | ".join(f"{k}: " + ", ".join(f"{s}={c}" for s, c in sorted(v.items())) for k, v in cov.items()))

# ---------------------------------------------------------------- C outcomes from bars
shd = {(r["ticker"], r["alert_date"]): r for r in sh}
crow = {}
for (t, d) in sorted(pC):
    rows = bars.get(t, [])
    di = [i for i, x in enumerate(rows) if x[0] == d]
    adrf = float(shd[(t, d)]["adr20_frac"]) if shd[(t, d)]["adr20_frac"] else None
    if not di:
        crow[(t, d)] = None
        continue
    i0 = di[0]
    fw = rows[i0:]
    o0, l0 = fw[0][1], fw[0][3]
    sess = len(fw)
    mh5 = (max(x[2] for x in fw[:6]) - o0) / o0
    mh20 = (max(x[2] for x in fw[:21]) - o0) / o0
    mlow = min(x[3] for x in fw[1:6]) if len(fw) > 1 else None
    crow[(t, d)] = dict(sess=sess, x5=mh5 / adrf if adrf else None, x20=mh20 / adrf if adrf else None,
                        loser=(mlow is not None and mlow < l0))
# cross-check vs the running read's rows.psv (only rows present there)
rr = {}
for r in csv.reader(open(REPO / "scripts/probes/_rank_shadow_running_read_1103/rows.psv"), delimiter="|"):
    rr[(r[0], r[1])] = r
cmp_n = cmp_bad = 0
for k, r in rr.items():
    if k not in crow or crow[k] is None:
        continue
    cmp_n += 1
    adr = float(r[2]) if r[2] else None
    mh5 = float(r[13]) / adr if r[13] and adr else None
    loser = r[17] != "" and r[11] != "" and float(r[17]) < float(r[11])
    c = crow[k]
    if int(r[12]) >= 6 and (abs((mh5 or 0) - (c["x5"] or 0)) > 1e-6 or loser != c["loser"]):
        cmp_bad += 1
        P("   C outcome mismatch vs rows.psv", k, mh5, c["x5"], loser, c["loser"])
P(f"\n[C] outcomes from bars vs running-read rows.psv: {cmp_n} rows compared, {cmp_bad} mismatches (rows.psv holds {len(rr)})")

sys.path.insert(0, str(REPO))
from scripts.alert_rank_shadow_running_read import CohortRead, score_both_directions  # noqa: E402


def c_read(R, verbose=True):
    outl = []
    for h, mm, xk in (("5d", 6, "x5"), ("20d", 21, "x20")):
        mat = [(k, crow[k]) for k in sorted(pC) if crow[k] and crow[k]["sess"] >= mm and crow[k][xk] is not None]
        g1 = [(k, c) for k, c in mat if R[(k[0], k[1], "C")]["held"] == 1]
        g0 = [(k, c) for k, c in mat if R[(k[0], k[1], "C")]["held"] == 0]
        gn = [k for k, c in mat if R[(k[0], k[1], "C")]["held"] is None]
        w1 = sum(1 for _, c in g1 if c[xk] >= 8.0); l1 = sum(1 for _, c in g1 if c["loser"])
        w0 = sum(1 for _, c in g0 if c[xk] >= 8.0); l0 = sum(1 for _, c in g0 if c["loser"])
        v = score_both_directions(CohortRead(len(g1), w1, l1), CohortRead(len(g0), w0, l0))
        tails = [f"{k[0]} {k[1]} {c[xk]:.2f}x held={R[(k[0], k[1], 'C')]['held']}" for k, c in mat if c[xk] >= 8.0]
        line = (f"[{h}] matured n={len(mat)} (NULL {len(gn)}) | held=1 n={len(g1)} w {w1} L {l1} | "
                f"held=0 n={len(g0)} w {w0} L {l0} -> {v.split(' --')[0]} | tails: {', '.join(tails)}")
        outl.append((len(g1), w1, l1, len(g0), w0, l0, v.split(" --")[0]))
        if verbose:
            P("  " + line)
    return outl


P("[C] held=1 vs held=0 (stated):")
c_read(res)

# ---------------------------------------------------------------- plateau (both P-window readings)
for couple, wins, wtag in ((False, {}, "literal windows run 60 / shelf 45"), (True, {}, "literal windows run 60 / shelf 45"),
                          (True, {"run_incl": False, "shelf_incl": False}, "BUILDER windows run 61 / shelf 46")):
    P(f"\n[plateau] P window end {'COUPLED to pb_win (D-base_end .. D-(pb_win+1))' if couple else 'FIXED at 41 (D-base_end .. D-41), as the definition states'} · {wtag}")
    for nm, v in VARS:
        R = {}
        for p in pairs:
            R[(p["ticker"], p["date"], p["source"])] = f3(p["ticker"], p["date"], {**v, "couple": couple, **wins})
        _, _, yv2, nv2 = score(R)
        a2 = auc(yv2, nv2)
        ci_ = boot(yv2, nv2)
        bb = [R[(p["ticker"], p["date"], "B")]["held"] for p in pairs if p["source"] == "B" and p["label"] == "operator"]
        k = R[("KOD", "2026-09-28", "A")]["held"]
        cc = c_read(R, verbose=False)
        P(f"   {nm:<13} {a2:.3f} [{ci_[0]:.2f}, {ci_[1]:.2f}] n {len(yv2)}/{len(nv2)} =1 {sum(yv2)}/{len(yv2)}·{sum(nv2)}/{len(nv2)}"
          f"  B=1 {sum(x for x in bb if x)}/8  KOD {k}  C5 {cc[0][1]}w{cc[0][2]}L/{cc[0][0]} vs {cc[0][4]}w{cc[0][5]}L/{cc[0][3]}"
          f" · C20 {cc[1][1]}w{cc[1][2]}L/{cc[1][0]} vs {cc[1][4]}w{cc[1][5]}L/{cc[1][3]}  qual {max(a2,1-a2) >= 0.65}")

# run-window convention check (61-session window P-60..P)
R = {}
for p in pairs:
    R[(p["ticker"], p["date"], p["source"])] = f3(p["ticker"], p["date"], {"run_incl": False})
_, _, yv3, nv3 = score(R)
RB = {(p["ticker"], p["date"], p["source"]): f3(p["ticker"], p["date"], {"run_incl": False, "shelf_incl": False}) for p in pairs}
yb, nb, _, _ = score(RB)
dyb = [min(o["d1"], o["d2"]) for o in yb if o["held"] is not None]
dnb = [min(o["d1"], o["d2"]) for o in nb if o["held"] is not None]
P(f"[conv] dmin descriptive under the builder windows: P(yes>no) {auc(dyb, dnb):.4f} yes median {st.median(dyb):.3f} no median {st.median(dnb):.3f}")
P(f"\n[conv] run window as P-60..P (61 sessions): A {auc(yv3, nv3):.4f} n {len(yv3)}/{len(nv3)}; "
  f"WYFI {R[('WYFI','2026-08-12','A')]['null']} held {R[('WYFI','2026-08-12','A')]['held']}; "
  f"HTFL {R[('HTFL','2026-08-14','B')]['null']} held {R[('HTFL','2026-08-14','B')]['held']}")
for key in (("WYFI", "2026-08-12", "A"), ("HTFL", "2026-08-14", "B")):
    o = res[key]
    sl, ia = slice_to(key[0], key[1])
    di = {x[0]: i for i, x in enumerate(sl)}
    P(f"   {key[0]} stated: P {o['P_date']} at slice index {di[o['P_date']]} (ia {ia}) -> 60-incl window start {di[o['P_date']]-59}; null {o['null']}")

(HERE / "v_f3.txt").write_text("\n".join(OUT) + "\n")
