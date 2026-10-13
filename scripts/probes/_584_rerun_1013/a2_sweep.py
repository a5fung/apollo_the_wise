"""#584 RERUN 2026-10-13 step 2 (adapted from _584/a2_sweep.py; DEFINITIONS UNCHANGED).
Unchanged vs 10-01: in-window = minutes_since_open_at_open <= 15; fallback to _last only where no at_open read AND minutes_since_open_last <= 15;
bars $10M/$25M/$50M/$100M on today_dollar_volume_at_open; reach = peak HIGH over D0..D0+h vs D0 open >= 8 x ADR20 (mean (H-L)/C of the prior 20 sessions);
settled = close at D0+h vs D0 open (EXCURSION is not a return; no fills); guard = drop rows with a >4x single-day close jump up inside D0..D0+h;
admitted pool = admitted-side rows with an in-window at_open read; gap-matched admitted pool = same with gap_pct_at_open >= 10; Wilson 95% intervals.
Changes: horizon is a parameter (5 and 20); the ex-gap-day reach (peak over D1..Dh only, verifier correction #1) is reported next to every reach;
population composition + 20-session funnel come first; regression block re-derives the 10-01 table on D0 <= 09-23 as a drift check.
Local only. Reads $SCR/a1_rows.pkl + q3_closes.out + q4_calendar.out. Writes a2_sweep.out."""
import os, math
import pandas as pd, numpy as np
SCR = os.environ['SCR']
D = pd.read_pickle(SCR + '/a1_rows.pkl')
B = pd.read_csv('q3_closes.out', parse_dates=['trade_date'], keep_default_na=False, na_values=[''])   # 'NA' ticker fix, see a1_prep.py
CAL = pd.read_csv('q4_calendar.out', parse_dates=['trade_date']); cal = list(CAL.trade_date); cidx = {d: i for i, d in enumerate(cal)}
Bg = {t: g.set_index('trade_date').sort_index() for t, g in B.groupby('ticker')}
BARS = [10e6, 25e6, 50e6, 100e6]
W = 15
L = []
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); L.append(s)

def gH(r, h):
    g = Bg.get(r.ticker)
    if g is None or r.scan_date not in cidx: return np.nan, np.nan
    i = cidx[r.scan_date]; ds = [x for x in cal[i:i + h + 1] if x in g.index]
    cl = g.loc[ds].close.values
    if len(cl) < 2: return np.nan, np.nan
    q = cl[1:] / cl[:-1]; return float(np.nanmax(q)), float(np.nanmin(q))
t5 = D.apply(lambda r: gH(r, 5), axis=1, result_type='expand'); D['maxq5'] = t5[0]; D['minq5'] = t5[1]
t20 = D.apply(lambda r: gH(r, 20), axis=1, result_type='expand'); D['maxq20'] = t20[0]; D['minq20'] = t20[1]

D['ao'] = D.today_dollar_volume_at_open
D['inwin'] = D.minutes_since_open_at_open <= W
D['full_dv'] = D.d0_dv
for h, pk, pkx, ck in ((5, 'peak_hi_5', 'peak_hi_5_x0', 'c5'), (20, 'peak_hi_20', 'peak_hi_20_x0', 'c20')):
    D[f'exc{h}'] = D[pk] / D.d0_open - 1                 # incl. the gap day's own high
    D[f'exc{h}x'] = D[pkx] / D.d0_open - 1               # EXCLUDING the gap day's own high (D1..Dh highs only)
    D[f's{h}'] = D[ck] / D.d0_open - 1
    D[f'reach{h}'] = D[f'exc{h}'] >= 8 * D.adr20
    D[f'reach{h}x'] = D[f'exc{h}x'] >= 8 * D.adr20
    D[f'guard_up{h}'] = D[f'maxq{h}'] > 4
D['settled5'] = D.c5.notna() & (D.n_fwd5 == 5) & D.d0_open.gt(0)          # as in 10-01
D['settled20'] = D.c20.notna() & (D.n_fwd20 == 20) & D.peak_hi_20.notna() & D.d0_open.gt(0)

def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - a) / d, (c + a) / d)

ALLD = sorted(D.scan_date.unique()); nd = len(ALLD)
rej = D[D.rej]; adm = D[~D.rej]
ra = rej[rej.ao.notna()]
rw = ra[ra.inwin]; aw = adm[adm.ao.notna() & adm.inwin]
rw_g10 = rw[rw.gap_pct_at_open >= 10]; aw_g10 = aw[aw.gap_pct_at_open >= 10]

P('=== 1. POPULATION COMPOSITION (stated before any outcome number) ===')
P('captured 2026-10-13 ~09:52 ET; scan dates in analysis:', nd, ALLD[0].date(), '->', ALLD[-1].date(), '(10-13 session live => EXCLUDED); last close in mi_daily_closes:', cal[-1].date())
P('all shadow rows (both sides):', len(D), ' names:', D.ticker.nunique())
P('rejected-side rows:', len(rej), 'names:', rej.ticker.nunique(), '| admitted-side rows:', len(adm), 'names:', adm.ticker.nunique())
P('rejected by class:', rej.cls.value_counts().to_dict())
P('rejected with an at_open dollar-volume read:', len(ra), 'names:', ra.ticker.nunique(), 'dates:', ra.scan_date.nunique(), '| no post-open read at all (pre-market-only rows, excluded):', len(rej) - len(ra))
P('fallback to _last (minutes_since_open_last<=15) usable on rows with NO at_open read:', int(((rej.ao.isna()) & rej.today_dollar_volume_last.notna() & (rej.minutes_since_open_last <= 15)).sum()), '=> fallback NOT used')
P('at_open read minute mix (rejected):', ra.minutes_since_open_at_open.value_counts().sort_index().to_dict())
P('IN-WINDOW (minutes<=15) rejected rows:', len(rw), 'names:', rw.ticker.nunique(), '| out-of-window (20/25 min) excluded:', int((~ra.inwin).sum()))
P('  in-window by class:', rw.cls.value_counts().to_dict(), '| gap_at_open quantiles 5/25/50/75/95:', [round(x, 1) for x in rw.gap_pct_at_open.quantile([.05, .25, .5, .75, .95])], '| share gap>=10:', round((rw.gap_pct_at_open >= 10).mean(), 3))
P('  in-window rows/day:', {str(k.date())[5:]: int(v) for k, v in rw.groupby('scan_date').size().items()})
P('ADMITTED pool (cleared both floors, in-window at_open read): rows', len(aw), 'names', aw.ticker.nunique(), '| gap-matched (gap>=10):', len(aw_g10), 'rows /', aw_g10.ticker.nunique(), 'names')
d20 = sorted(D[D.settled20].scan_date.unique())
P('D0 dates with ANY 20-session settled close:', len(d20), [str(x.date())[5:] for x in d20], '| D0+20 close exists only for D0 <= ', d20[-1].date() if d20 else None)
d5 = sorted(D[D.settled5].scan_date.unique()); P('D0 dates with a 5-session settled close:', len(d5), d5[0].date(), '->', d5[-1].date())
P()

def nm(x): return x.ticker.nunique()
P('=== 2. 20-SESSION SETTLED NAMES PER BAR (the >=15 gate; rejected side, in-window at_open read >= bar) ===')
P('funnel columns = distinct NAMES (rows) at each stage:  clearing | +D0+20 close exists | +all 20 forward bars | +ADR20 defined | +no >4x jump-up (CLEAN = analysed sample)')
GATE = {}
for lab, pop in (('all gaps (review-literal)', rw), ('gap_at_open>=10', rw_g10)):
    P(' ', lab)
    for b in BARS:
        s0 = pop[pop.ao >= b]
        s1 = s0[s0.c20.notna()]
        s2 = s1[s1.settled20]
        s3 = s2[s2.adr20.notna()]
        s4 = s3[~s3.guard_up20]
        GATE[(lab, b)] = nm(s4)
        P(f'    >=${int(b/1e6)}M: {nm(s0)} ({len(s0)}) | {nm(s1)} ({len(s1)}) | {nm(s2)} ({len(s2)}) | {nm(s3)} ({len(s3)}) | {nm(s4)} ({len(s4)})   -> CLEAN names {nm(s4)} {"MEETS" if nm(s4) >= 15 else "BELOW"} the >=15 bar')
ext = list(cal); dd = cal[-1]
while len(ext) < len(cal) + 40:
    dd = dd + pd.Timedelta(days=1)
    if dd.weekday() < 5: ext.append(dd)          # Oct/Nov 2026: no NYSE holiday before 11-26
eidx = {x: i for i, x in enumerate(ext)}
P('PROJECTION: close date at which the 15th distinct in-window ADR-defined clearing name has a 20-session close (assumes no guard/missing-bar attrition):')
rwc = rw[rw.adr20.notna()].copy(); rwc['d20'] = rwc.scan_date.map(lambda x: ext[eidx[x] + 20])
for lab, pop in (('all gaps', rwc), ('gap>=10', rwc[rwc.gap_pct_at_open >= 10])):
    for b in BARS:
        sub = pop[pop.ao >= b].sort_values('d20'); seen = set(); when = None
        for r in sub.itertuples():
            seen.add(r.ticker)
            if len(seen) >= 15: when = r.d20; break
        P(f'  {lab} >=${int(b/1e6)}M: total clearing names through 10-12 = {sub.ticker.nunique()}; 15th settles at 20 once closes reach {when.date() if when is not None else "never within window"}')
P()

def stat(x, h):
    n = len(x)
    if n == 0: return dict(n=0)
    k8 = int(x[f'reach{h}'].sum()); k8x = int(x[f'reach{h}x'].sum()); lo, hi = wilson(k8, n); xlo, xhi = wilson(k8x, n)
    s = x[f's{h}']; ks = int((s <= -0.20).sum()); klo, khi = wilson(ks, n); kw = int((s >= 0.20).sum())
    d = dict(n=n, names=x.ticker.nunique(), reach_k=k8, reach=k8 / n, r_lo=lo, r_hi=hi, reachx_k=k8x, reachx=k8x / n, rx_lo=xlo, rx_hi=xhi,
             exc_med=x[f'exc{h}'].median(), exc_p90=x[f'exc{h}'].quantile(.9), s_med=s.median(), s_p10=s.quantile(.1),
             crash_k=ks, crash=ks / n, c_lo=klo, c_hi=khi, win_k=kw, win=kw / n)
    if h == 20:   # the 5-session read on the SAME rows
        d.update(s5_med=x.s5.median(), crash5_k=int((x.s5 <= -0.20).sum()), crash5=(x.s5 <= -0.20).mean(), reach5_k=int(x.reach5.sum()), reach5x_k=int(x.reach5x.sum()))
    return d

CHECK = []
def clean(x, h):
    return x[x[f'settled{h}'] & ~x[f'guard_up{h}'] & x.adr20.notna()]

def table(R, A, h, title, gapmin=None, ndays=None, tag=''):
    P('====', title)
    rs = R if gapmin is None else R[R.gap_pct_at_open >= gapmin]
    as_ = A if gapmin is None else A[A.gap_pct_at_open >= gapmin]
    rows = []
    for b in [0] + BARS:
        sub_all = rs[rs.ao >= b] if b else rs
        sub = clean(sub_all, h)
        s = stat(sub, h); s['label'] = 'REJ all in-window' if b == 0 else f'REJ >= ${int(b/1e6)}M'
        s['rows_all'] = len(sub_all); s['names_per_day'] = len(sub_all) / (ndays or nd)
        s['guard_dropped'] = int((sub_all[f'settled{h}'] & sub_all.adr20.notna() & sub_all[f'guard_up{h}']).sum())
        rows.append(s); CHECK.append(f'CHECK|{tag}h{h}|REJ|{"g10" if gapmin else "all"}|{int(b/1e6)}|{s["n"]}|{s.get("reach_k")}|{s.get("reachx_k")}|{s.get("crash_k")}|{s.get("win_k")}')
    for b in [0] + BARS:
        sub_all = as_[as_.ao >= b] if b else as_
        sub = clean(sub_all, h)
        s = stat(sub, h); s['label'] = 'ADM all in-window' if b == 0 else f'ADM >= ${int(b/1e6)}M'
        s['rows_all'] = len(sub_all); s['names_per_day'] = len(sub_all) / (ndays or nd); s['guard_dropped'] = int((sub_all[f'settled{h}'] & sub_all.adr20.notna() & sub_all[f'guard_up{h}']).sum())
        rows.append(s); CHECK.append(f'CHECK|{tag}h{h}|ADM|{"g10" if gapmin else "all"}|{int(b/1e6)}|{s["n"]}|{s.get("reach_k")}|{s.get("reachx_k")}|{s.get("crash_k")}|{s.get("win_k")}')
    T = pd.DataFrame(rows)
    pd.set_option('display.width', 330); pd.set_option('display.max_columns', 60)
    f = T.copy()
    for c in ['reach', 'r_lo', 'r_hi', 'reachx', 'rx_lo', 'rx_hi', 'crash', 'c_lo', 'c_hi', 'win', 'exc_med', 'exc_p90', 's_med', 's_p10'] + (['s5_med', 'crash5'] if h == 20 else []):
        f[c] = (f[c] * 100).round(1)
    f['names_per_day'] = f.names_per_day.round(1)
    cols = ['label', 'rows_all', 'names_per_day', 'n', 'names', 'guard_dropped', 'reach_k', 'reach', 'r_lo', 'r_hi', 'reachx_k', 'reachx', 'rx_lo', 'rx_hi', 'exc_med', 'exc_p90', 's_med', 's_p10', 'crash_k', 'crash', 'c_lo', 'c_hi', 'win_k']
    if h == 20: cols += ['s5_med', 'crash5_k', 'crash5', 'reach5_k', 'reach5x_k']
    P(f[cols].to_string(index=False)); P()
    return T

P('=== 3. TABLES (all excursions are EXCURSIONS vs the D0 open, never returns; settled = close at D0+h vs D0 open). reach = peak incl. gap-day high; reachx = EXCLUDING the gap day\'s own high ===')
P('refs from #570 (admitted pool baselines): reach>=8xADR 8.2% | median settled -11.7%.  10-01 interim (5-session, D0<=09-23): admitted gap-matched pool 9.8% reach / 20.7% settle<=-20%.')
nd_all = nd
T20a = table(rw, aw, 20, f'20-SESSION horizon, D0 in {d20[0].date()}..{d20[-1].date()} ({len(d20)} dates): rejected in-window, ALL gaps', ndays=nd_all, tag='')
T20b = table(rw, aw, 20, '20-SESSION horizon: rejected in-window, gap_at_open >= 10 (gap-matched; ADM rows also gap>=10)', gapmin=10.0, ndays=nd_all, tag='')
T5a = table(rw, aw, 5, f'5-SESSION horizon, EXTENDED to {len(d5)} D0 dates ({d5[0].date()}..{d5[-1].date()}): rejected in-window, ALL gaps', ndays=nd_all, tag='')
T5b = table(rw, aw, 5, '5-SESSION horizon, extended: gap_at_open >= 10', gapmin=10.0, ndays=nd_all, tag='')

P('=== 4. REGRESSION vs the 10-01 run (5-session, D0 <= 2026-09-23 only; counts must equal the 10-01 table) ===')
# the 10-01 analyst pipeline silently dropped ticker 'NA' (pandas default na_values); the 10-01 verifier (csv module) kept it and read n=1293 vs the analyst's 1291.
# The regression therefore excludes 'NA' to reproduce the 10-01 analyst table; every number in sections 1-3 INCLUDES it.
rw0 = rw[(rw.scan_date <= '2026-09-23') & (rw.ticker != 'NA')]; aw0 = aw[(aw.scan_date <= '2026-09-23') & (aw.ticker != 'NA')]
old_p = pd.read_csv('../_584/a2_table_primary.csv'); old_g = pd.read_csv('../_584/a2_table_gap10.csv')
sv = list(CHECK)
T_r1 = table(rw0, aw0, 5, 'REGRESSION all gaps (D0<=09-23)', ndays=20, tag='reg')
T_r2 = table(rw0, aw0, 5, 'REGRESSION gap>=10 (D0<=09-23)', gapmin=10.0, ndays=20, tag='reg')
ok = True
for nm_, old, new in (('primary', old_p, T_r1), ('gap10', old_g, T_r2)):
    for i in range(len(old)):
        o = old.iloc[i]; n_ = new.iloc[i]
        same = (int(o.n) == int(n_.n)) and (int(o.reach8_k) == int(n_.reach_k)) and (int(round(o.crash20 * o.n)) == int(n_.crash_k)) and (int(o.win20_k) == int(n_.win_k))
        ok &= same
        if not same: P(f'  REGRESSION MISMATCH {nm_} {o.label}: old n={o.n} reach_k={o.reach8_k} crash={round(o.crash20*o.n)} win={o.win20_k} | new n={n_.n} reach_k={n_.reach_k} crash={n_.crash_k} win={n_.win_k}')
P('REGRESSION RESULT:', 'ALL 20 table rows (n, reach count, crash count, win count) reproduce the 10-01 analyst run exactly (with ticker NA excluded as it was then)' if ok else 'MISMATCHES ABOVE')
P()
open('a2_sweep.out', 'w').write('\n'.join(L + [''] + CHECK) + '\n')
D.to_pickle(SCR + '/a2_rows.pkl')
