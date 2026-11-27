#!/usr/bin/env python3
"""The era-A overlap guard breaks with no era-B guard match: is the symbol in the sealed era-B copy at all in 2022-04..06? Reads ticker and
date columns only of the SEALED copy (rows < 2025-01-01), restricted to 2022-04-01..2022-06-30. Appends to r5_guard_agreement.txt"""
import gzip
from pathlib import Path
from datetime import date
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[3]; DATA = Path("/Users/alvinfung/apollo_data")
SEALED = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/bws1124/pop/cb702_daily_lt2025.csv.gz")
def load(path):
    out = {}
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0: ik, ib = f.index("symbol"), f.index("breaks"); continue
        if len(f) > ib and f[ib]:
            out[f[ik]] = [(x.partition(":")[0], x.partition(":")[2]) for x in f[ib].split(";") if x.partition(":")[0] <= "2024-12-31"]
    return out
gA = load(DATA / "cb702_pre_v2/symbol_guard.tsv"); gB = load(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
lo, hi = "2022-04-01", "2022-06-30"
def near(t, d):
    x = date.fromisoformat(d).toordinal()
    return any(abs(date.fromisoformat(e).toordinal() - x) <= 3 for e, _ in gB.get(t, ()))
un = [(t, d, k) for t, v in gA.items() for d, k in v if lo <= d <= hi and not near(t, d)]
need = {t for t, _, _ in un}
days = {t: set() for t in need}
with gzip.open(SEALED, "rt") as fh:
    for ln in fh:
        t, d, _ = ln.split(",", 2)
        assert d < "2025-01-01"
        if t in need and lo <= d <= hi: days[t].add(d)
absent = [x for x in un if not days[x[0]]]
present = [x for x in un if days[x[0]]]
from collections import Counter
s = [f"era-A overlap breaks with no era-B guard date within 3 days: {len(un)} on {len(need)} symbols; symbol has NO bar in the sealed era-B copy in the overlap: {len(absent)}; symbol present there: {len(present)} (kinds {dict(Counter(k.split(':')[0] for _, _, k in present))}; sessions held in the overlap, median {sorted(len(days[t]) for t, _, _ in present)[len(present) // 2] if present else 0} of 62)",
     "present-but-unmatched (symbol date kind sessions-held-in-B): " + ", ".join(f"{t} {d} {k.split(':')[0]} {len(days[t])}" for t, d, k in sorted(present)[:45])]
print("\n".join(s))
open(HERE / "r5_guard_agreement.txt", "a").write("\n".join(s) + "\n")
