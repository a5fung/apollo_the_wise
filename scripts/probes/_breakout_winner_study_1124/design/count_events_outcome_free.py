#!/usr/bin/env python3
"""OUTCOME-FREE event counts for the breakout big-winner study draft (2026-11-24). Reads ONLY the columns ci / ticker / fire
of the 11-13 capture (list rows of era A at the 4% ADR floor, BEFORE the 11-14 context gates) and the ticker / date columns
of Qullamaggie's buys fixture. No price after E, no `big_winner` column, no outcome file. Counts are INDICATIVE: the
study's stage 1 rebuilds the list from the live code at a pinned sha (context gates included).

    python3 scripts/probes/_breakout_winner_study_1124/design/count_events_outcome_free.py
"""
import numpy as np, pandas as pd
D = '/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet'
df = pd.read_parquet(D, columns=['ci', 'ticker', 'fire'])
cal = [l.strip() for l in open(D + '.cal.txt')]
f = df[df.fire == 1].sort_values(['ticker', 'ci']).copy()
f['E'] = f.ci + 1
yr = lambda i: int(cal[min(i, len(cal) - 1)][:4])
print(f"list rows {len(df):,} · nights {df.ci.nunique():,} · break rows (fire) {len(f):,} · tickers {f.ticker.nunique():,} · "
      f"median breaks per night {f.groupby('ci').size().median():.0f} · median breaks per ticker {f.groupby('ticker').size().median():.0f}")

def thin(rows, rule, seed=1124):
    rng = np.random.default_rng(seed); keep = []
    for t, x in rows.groupby('ticker', sort=True):
        ci = x.ci.values; ix = x.index.values
        order = rng.permutation(len(ci)) if rule == 'random' else np.arange(len(ci))
        acc = []
        for j in order:
            if all(abs(ci[j] - a) > 60 for a in acc): acc.append(ci[j]); keep.append(ix[j])
    return rows.loc[keep]

g = f.groupby('ticker').ci.diff()
SETS = {'A. random break per ticker per 60 sessions (PRIMARY)': thin(f, 'random'),
        'B. first break after 10 quiet sessions, one per ticker per 60': thin(f[g.isna() | (g > 10)], 'first'),
        'C. first break after 60 quiet sessions': f[g.isna() | (g > 60)]}
b = pd.read_csv('tests/fixtures/qm_breakout_scorecard/buys.tsv', sep='\t', usecols=['ticker', 'E'])
w = pd.read_csv('tests/fixtures/qm_breakout_scorecard/buys_undated_widened.tsv', sep='\t', usecols=['ticker', 'lo', 'hi'])
idx = {d: i for i, d in enumerate(cal)}
def hits(S, pad):
    n = 0
    for t, lo, hi in list(zip(b.ticker, b.E, b.E)) + list(zip(w.ticker, w.lo, w.hi)):
        a, z = idx.get(lo), idx.get(hi)
        n += a is not None and z is not None and any((t, i) in S for i in range(a - pad, z + 1))
    return n
fs = set(zip(f.ticker, f.E))
print(f"Qullamaggie's buys {len(b) + len(w)}: on a break row (his day or window) {hits(fs, 0)}")
for name, k in SETS.items():
    k = k.assign(y=[yr(i) for i in k.E], m=[cal[min(i, len(cal) - 1)][:7] for i in k.E])
    mm = k.groupby('m').size()
    print(f"\n{name}: {len(k):,} events · tickers {k.ticker.nunique():,} · per year {k.groupby('y').size().to_dict()}")
    print(f"   months {len(mm)}, smallest {mm.min()}, median {mm.median():.0f} · his buys on an event (day or window, 2 sessions earlier allowed): {hits(set(zip(k.ticker, k.E)), 2)}")

# --- un-thinned check (added after review): are Qullamaggie's buys under-represented on FIRST breaks? outcome-free ---
for name, mask in (('first break after 10 quiet sessions', g.isna() | (g > 10)), ('first break after 60 quiet sessions', g.isna() | (g > 60))):
    sub = f[mask]; S = set(zip(sub.ticker, sub.E))
    print(f"\nUN-THINNED {name}: {len(sub):,} of {len(f):,} break rows = {len(sub) / len(f):.1%} · his buys with such a row in "
          f"their day / window: {hits(S, 0)} of {hits(fs, 0)} = {hits(S, 0) / hits(fs, 0):.1%}")
