"""#584 RERUN: (1) reverse/forward splits inside the outcome windows of the CLEAN samples (bars are split-adjusted; the >4x guard only fires on an UN-applied split);
(2) per-bar pipeline of rejected clearers still waiting on a 20th session: cumulative distinct names by D0 date -> the close date each bar reaches 15. Read-only, local."""
import os
import pandas as pd, numpy as np
SCR = os.environ['SCR']
D = pd.read_pickle(SCR + '/a2_rows.pkl')
S = pd.read_csv('q5_splits.out', parse_dates=['execution_date'], keep_default_na=False, na_values=[''])
CAL = pd.read_csv('q4_calendar.out', parse_dates=['trade_date']); cal = list(CAL.trade_date); cidx = {d: i for i, d in enumerate(cal)}
ext = list(cal); dd = cal[-1]
while len(ext) < len(cal) + 40:
    dd += pd.Timedelta(days=1)
    if dd.weekday() < 5: ext.append(dd)
eidx = {x: i for i, x in enumerate(ext)}
out = []
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); out.append(s)
rw = D[D.rej & D.ao.notna() & D.inwin]
BARS = [10e6, 25e6, 50e6, 100e6]
P('=== (1) SPLITS INSIDE THE OUTCOME WINDOW (D0..D0+h) of the clean rejected samples ===')
def split_in(r, h):
    end = ext[eidx[r.scan_date] + h]
    s = S[(S.ticker == r.ticker) & (S.execution_date >= r.scan_date) & (S.execution_date <= end)]
    return ';'.join(f'{x.split_from:g}:{x.split_to:g}@{str(x.execution_date.date())[5:]}({x.adjustment_applied})' for x in s.itertuples())
for h, lab in ((20, '20-session'), (5, '5-session')):
    c = rw[rw[f'settled{h}'] & ~rw[f'guard_up{h}'] & rw.adr20.notna()].copy()
    c['sp'] = [split_in(r, h) for r in c.itertuples()]
    P(f'{lab}: clean rejected in-window rows {len(c)}; rows with a split in window: {int((c.sp != "").sum())}')
    for b in BARS:
        x = c[(c.ao >= b) & (c.sp != '')]
        P(f'  >=${int(b/1e6)}M: {len(x)} of {int((c.ao>=b).sum())} rows with a split in window ' + (str([(r.ticker, str(r.scan_date.date())[5:], r.sp, round(r.exc20 if h == 20 else r.exc5, 2), round(r.s20 if h == 20 else r.s5, 2)) for r in x.itertuples()]) if len(x) else ''))
    P(f'  unapplied (f) splits inside any clean window: {int(c.sp.str.contains("(f)", regex=False).sum())}')
P()
P('=== (2) PIPELINE TO 15 CLEAN 20-SESSION NAMES, per bar (rejected, in-window; cumulative DISTINCT names by D0 date; ADR-defined; attrition from guard/missing bars not knowable ahead) ===')
rwc = rw[rw.adr20.notna()].copy(); rwc['d20'] = rwc.scan_date.map(lambda x: ext[eidx[x] + 20])
for lab, pop in (('all gaps', rwc), ('gap>=10', rwc[rwc.gap_pct_at_open >= 10])):
    for b in BARS:
        sub = pop[pop.ao >= b].sort_values('scan_date'); seen = set(); line = []
        for d, g in sub.groupby('scan_date'):
            seen |= set(g.ticker); line.append(f'{str(d.date())[5:]}:{len(seen)}')
        clean_now = sub[sub.settled20 & ~sub.guard_up20].ticker.nunique()
        P(f'{lab} >=${int(b/1e6)}M clean-now {clean_now}; cumulative distinct names by D0 -> ' + ' '.join(line))
        s2 = sub.assign(d20=sub.scan_date.map(lambda x: ext[eidx[x] + 20])).sort_values('d20'); seen = set(); when = None
        for r in s2.itertuples():
            seen.add(r.ticker)
            if len(seen) >= 15: when = (r.d20, r.scan_date); break
        P(f'    -> 15th name: D0 {when[1].date() if when else None}, has its 20th-session close on {when[0].date() if when else None}')
open('r6_splits_pending.out', 'w').write('\n'.join(out) + '\n')
