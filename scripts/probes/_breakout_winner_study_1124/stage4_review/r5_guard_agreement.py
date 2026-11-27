#!/usr/bin/env python3
"""Stage 4 review - is the era-B guard file as sensitive as era A's? DATES ONLY, both files, nothing after 2024-12-31 read.
Overlap 2022-04-01..2022-06-30 (both stores hold it): era-A guard break dates there, on symbols the era-B guard file lists, vs a guard-B
date within +-3 calendar days. Also the kinds of break each file records. Output -> r5_guard_agreement.txt"""
from pathlib import Path
from collections import Counter
from datetime import date
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[3]; DATA = Path("/Users/alvinfung/apollo_data")
CUT = "2024-12-31"; L = []
def P(s=""):
    print(s); L.append(str(s))
def load(path):
    out, kinds, syms = {}, Counter(), set()
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, ib = f.index("symbol"), f.index("breaks"); continue
        syms.add(f[ik])
        if len(f) <= ib or not f[ib]: continue
        for x in f[ib].split(";"):
            d, _, kind = x.partition(":")
            if d > CUT: continue
            out.setdefault(f[ik], []).append(d); kinds[kind.split(":")[0][:30]] += 1
    return out, kinds, syms
gA, kA, sA = load(DATA / "cb702_pre_v2/symbol_guard.tsv")
gB, kB, sB = load(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
P(f"era-A guard file: {len(sA)} symbols listed, {len(gA)} with a break; kinds {dict(kA.most_common(8))}")
P(f"era-B guard file: {len(sB)} symbols listed, {len(gB)} with a break; kinds {dict(kB.most_common(8))}")
lo, hi = "2022-04-01", "2022-06-30"
a_ov = [(t, d) for t, ds in gA.items() for d in ds if lo <= d <= hi]
b_ov = [(t, d) for t, ds in gB.items() for d in ds if lo <= d <= hi]
P(f"break dates inside the overlap {lo}..{hi}: era A {len(a_ov)} on {len({t for t, _ in a_ov})} symbols; era B {len(b_ov)} on {len({t for t, _ in b_ov})} symbols")
def near(t, d, g):
    x = date.fromisoformat(d).toordinal()
    return any(abs(date.fromisoformat(e).toordinal() - x) <= 3 for e in g.get(t, ()))
in_b = [(t, d) for t, d in a_ov if t in sB]
m = sum(near(t, d, gB) for t, d in in_b)
P(f"era-A overlap breaks on symbols the era-B file lists: {len(in_b)}; with an era-B break within 3 days: {m}")
in_a = [(t, d) for t, d in b_ov if t in sA]
m2 = sum(near(t, d, gA) for t, d in in_a)
P(f"era-B overlap breaks on symbols the era-A file lists: {len(in_a)}; with an era-A break within 3 days: {m2}")
P(f"era-B break dates per symbol: median {sorted(len(v) for v in gB.values())[len(gB) // 2]}, max {max(len(v) for v in gB.values())}; era A median {sorted(len(v) for v in gA.values())[len(gA) // 2]}, max {max(len(v) for v in gA.values())}")
(HERE / "r5_guard_agreement.txt").write_text("\n".join(L) + "\n")
