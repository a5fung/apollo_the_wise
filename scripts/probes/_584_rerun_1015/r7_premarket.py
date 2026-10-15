"""#584 RERUN verifier correction #2 (adapted from _584_verify/v7_price_consistency.py): how many 09:31 reads carry a PRE-MARKET price?
Definition (unchanged): the shadow's today_price_at_open lies OUTSIDE the D0 daily bar's [low*0.995, high*1.005] => it cannot be a regular-session print.
NEW: mi_daily_closes is split-adjusted but the shadow price is the raw print, so for D0 before an applied split's execution date the bar is un-adjusted
(bar / (split_from/split_to)) before comparing. The raw (uncorrected) count is printed too so the 10-01 figure (564/1382) is comparable.
Read-only, local. Writes r7_premarket.out."""
import csv, os
import pandas as pd, numpy as np
SCR = os.environ['SCR']
D = pd.read_pickle(SCR + '/a2_rows.pkl')
B = pd.read_csv('q3_closes.out', parse_dates=['trade_date'], keep_default_na=False, na_values=[''])
S = pd.read_csv('q5_splits.out', parse_dates=['execution_date'], keep_default_na=False, na_values=[''])
S = S[S.adjustment_applied.astype(str) == 't']
bar = {(r.ticker, r.trade_date): (r.low_price, r.high_price) for r in B.itertuples()}
fac = {}
for r in S.itertuples():
    fac.setdefault(r.ticker, []).append((r.execution_date, r.split_from / r.split_to))
def factor(t, d0):
    f = 1.0
    for ed, x in fac.get(t, []):
        if ed > d0: f *= x
    return f
def flag(r, corrected=True):
    b = bar.get((r.ticker, r.scan_date))
    if b is None or not np.isfinite(r.today_price_at_open): return np.nan
    f = factor(r.ticker, r.scan_date) if corrected else 1.0
    lo, hi = b[0] / f, b[1] / f
    return float(not (lo * 0.995 <= r.today_price_at_open <= hi * 1.005))
D['pm_raw'] = [flag(r, False) for r in D.itertuples()]
D['pm'] = [flag(r, True) for r in D.itertuples()]
out = []
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); out.append(s)
def frac(x, col='pm'):
    x = x[x[col].notna()]
    return f'{int(x[col].sum())}/{len(x)} ({100*x[col].mean():.0f}%)' if len(x) else '0/0'
rw = D[D.rej & D.ao.notna() & D.inwin]; aw = D[(~D.rej) & D.ao.notna() & D.inwin]
P('=== PRE-MARKET PRICE FLAG on the 09:31-09:45 reads (price outside the session low-high +-0.5%) ===')
P('rows whose D0 precedes an applied split of that ticker (bar un-adjusted before the comparison):', sum(factor(t, d) != 1.0 for t, d in zip(D.ticker, D.scan_date)), 'of', len(D))
for lab, pop in (('REJECTED in-window', rw), ('ADMITTED in-window', aw)):
    for m in (1, 5, 10, 15):
        x = pop[pop.minutes_since_open_at_open == m]
        if len(x): P(f'  {lab} minute {m}: split-corrected {frac(x)} | raw/uncorrected (10-01 method) {frac(x, "pm_raw")}')
    P(f'  {lab} ALL in-window: split-corrected {frac(pop)} | raw {frac(pop, "pm_raw")}')
P('--- the 09:31 (minute-1) reads among BAR-CLEARERS (rejected, in-window, ao >= bar) ---')
for b in (10e6, 25e6, 50e6, 100e6):
    x = rw[rw.ao >= b]; x1 = x[x.minutes_since_open_at_open == 1]
    P(f'  >=${int(b/1e6)}M: all in-window reads {frac(x)} | minute-1 reads {frac(x1)} (minute-1 share of clearers {len(x1)}/{len(x)})')
P('--- the 20-session CLEAN cohort per bar (D0 <= 09-14) ---')
c20 = rw[rw.settled20 & ~rw.guard_up20 & rw.adr20.notna()]
for b in (10e6, 25e6, 50e6, 100e6):
    x = c20[c20.ao >= b]; P(f'  >=${int(b/1e6)}M clean-20s rows {len(x)}: flagged pre-market {frac(x)}')
P('--- the 5-session CLEAN cohort per bar (D0 <= 10-05) ---')
c5 = rw[rw.settled5 & ~rw.guard_up5 & rw.adr20.notna()]
for b in (10e6, 25e6, 50e6, 100e6):
    x = c5[c5.ao >= b]; P(f'  >=${int(b/1e6)}M clean-5s rows {len(x)}: flagged pre-market {frac(x)}')
# strict (no tolerance) for minute 1
def strict(r):
    b = bar.get((r.ticker, r.scan_date))
    if b is None: return np.nan
    f = factor(r.ticker, r.scan_date); return float(not (b[0] / f <= r.today_price_at_open <= b[1] / f))
x1 = rw[rw.minutes_since_open_at_open == 1].copy(); x1['st'] = [strict(r) for r in x1.itertuples()]
P('strict (no +-0.5% tolerance) rejected minute-1:', frac(x1, 'st'))
open('r7_premarket.out', 'w').write('\n'.join(out) + '\n')
