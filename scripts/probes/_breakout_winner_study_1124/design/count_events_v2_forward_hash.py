#!/usr/bin/env python3
"""OUTCOME-FREE event recount for draft v2 (critique finding 1), 2026-11-24. Reads ONLY ci / ticker / fire of the 11-13
capture (era-A list rows at the 4% ADR floor, BEFORE the 11-14 context gates) and ticker / E / lo / hi of Qullamaggie's buys
fixtures. No price, no bar after E, no outcome file. INDICATIVE: era A only, identity = ticker, no guard / file-start drops
(stage 1 applies those BEFORE this walk, on the pinned live code).

The v2 keep rule — decided on rows dated <= D only: walk a name's break rows forward in time; a row is ELIGIBLE when no KEPT
row of that name lies in the 60 sessions before it; an eligible row is KEPT when sha256("<seed>|<identity>|<D yyyy-mm-dd>")
read as a fraction of 2^64 (first 8 bytes) is under q. (v1 kept a row by what lay 60 sessions EITHER side — future-dependent.)

    python3 scripts/probes/_breakout_winner_study_1124/design/count_events_v2_forward_hash.py > .../count_events_v2_forward_hash.txt
"""
import hashlib
import numpy as np, pandas as pd
P = '/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet'
df = pd.read_parquet(P, columns=['ci', 'ticker', 'fire'])
cal = [l.strip() for l in open(P + '.cal.txt')]
f = df[df.fire == 1].sort_values(['ticker', 'ci']).reset_index(drop=True)
f['E'] = f.ci + 1
assert f.E.max() + 60 <= len(cal) - 1 or True
n_no60 = int((f.E + 60 > len(cal) - 1).sum())
gap = f.groupby('ticker').ci.diff()
f['first10'] = (gap.isna() | (gap > 10)).values
f['first60'] = (gap.isna() | (gap > 60)).values

def u(seed, t, d):
    return int.from_bytes(hashlib.sha256(f"{seed}|{t}|{d}".encode()).digest()[:8], 'big') / 2.0 ** 64

def thin(q, seed=1124):
    keep = np.zeros(len(f), dtype=bool)
    tk = f.ticker.values; ci = f.ci.values
    last_t, last_kept = None, -10 ** 9
    for i in range(len(f)):
        if tk[i] != last_t: last_t, last_kept = tk[i], -10 ** 9
        if ci[i] - last_kept > 60 and u(seed, tk[i], cal[ci[i]]) < q:
            keep[i] = True; last_kept = ci[i]
    return f[keep]

b = pd.read_csv('tests/fixtures/qm_breakout_scorecard/buys.tsv', sep='\t', usecols=['ticker', 'E'])
w = pd.read_csv('tests/fixtures/qm_breakout_scorecard/buys_undated_widened.tsv', sep='\t', usecols=['ticker', 'lo', 'hi'])
idx = {d: i for i, d in enumerate(cal)}
def hits(S, pad):
    n = 0
    for t, lo, hi in list(zip(b.ticker, b.E, b.E)) + list(zip(w.ticker, w.lo, w.hi)):
        a, z = idx.get(lo), idx.get(hi)
        n += a is not None and z is not None and any((t, i) in S for i in range(a - pad, z + 1))
    return n

print(f"break rows {len(f):,} · tickers {f.ticker.nunique():,} · of them 'first break after 10 quiet sessions' {f.first10.mean():.1%} · "
      f"'after 60 quiet' {f.first60.mean():.1%} · break rows whose E+60 is past the file end {n_no60}")
print("q grid (seed 1124). 'first10' / 'first60' = share of KEPT events that are a first break after 10 / 60 quiet sessions "
      "(break rows: see the line above).")
for q in (1.0, 0.5, 1 / 3, 0.25, 0.2, 1 / 6, 0.125, 0.1, 0.05):
    k = thin(q)
    yr = k.E.map(lambda i: int(cal[i][:4])); mm = k.E.map(lambda i: cal[i][:7]).value_counts()
    print(f"  q {q:.3f}: {len(k):6,} events · tickers {k.ticker.nunique():,} · first10 {k.first10.mean():.1%} · first60 {k.first60.mean():.1%} · "
          f"months {len(mm)}, smallest {mm.min()}, median {mm.median():.0f} · per year {yr.value_counts().sort_index().to_dict()} · "
          f"Qullamaggie's buys on an event {hits(set(zip(k.ticker, k.E)), 2)}")
print("\nsecond seed (2411), same grid points 0.25 / 0.2 / 0.125:")
for q in (0.25, 0.2, 0.125):
    k = thin(q, seed=2411); yr = k.E.map(lambda i: int(cal[i][:4]))
    k1 = thin(q)
    both = len(set(zip(k.ticker, k.ci)) & set(zip(k1.ticker, k1.ci)))
    print(f"  q {q:.3f}: {len(k):6,} events · first10 {k.first10.mean():.1%} · first60 {k.first60.mean():.1%} · per year "
          f"{yr.value_counts().sort_index().to_dict()} · events shared with seed 1124: {both}")
