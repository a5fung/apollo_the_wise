"""#584 RERUN 2026-10-15 x1: supplementary reads on the $50M / $100M levels (local, read-only, $0). Reads $SCR/a2_rows.pkl (a2_sweep.py output) + q5_splits.out + q4_calendar.out.
Definitions UNCHANGED from a2_sweep.py (reach = peak HIGH D0..D0+h vs D0 open >= 8 x ADR20; reachx = same excluding the gap day's own high; crash = settled <= -20%).
Adds: (1) the guard-dropped $50M/$100M rows listed; (2) one-sided tests incl. reach-ex-gap-day vs gap-matched admitted and vs #570's 8.2%;
(3) the $50M cohort row-by-row; (4) date-cluster / split-in-window / BENF sensitivities; (5) settled-return pricing (mean/median/p10/p90, no fills);
(6) projection of when $50M reaches 30 and 40 clean 20-session names. Writes x1_extra.out."""
import os, math
import pandas as pd, numpy as np
SCR = os.environ['SCR']
D = pd.read_pickle(SCR + '/a2_rows.pkl')
S = pd.read_csv('q5_splits.out', parse_dates=['execution_date'], keep_default_na=False, na_values=[''])
CAL = pd.read_csv('q4_calendar.out', parse_dates=['trade_date']); cal = list(CAL.trade_date)
ext = list(cal); dd = cal[-1]
while len(ext) < len(cal) + 60:
    dd += pd.Timedelta(days=1)
    if dd.weekday() < 5: ext.append(dd)
eidx = {x: i for i, x in enumerate(ext)}
OUT = []
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); OUT.append(s)
def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return ((c - a) / d, (c + a) / d)
def lc(a, b): return math.lgamma(a + 1) - math.lgamma(b + 1) - math.lgamma(a - b + 1)
def fisher_greater(k1, n1, k2, n2):
    K = k1 + k2; N = n1 + n2; tot = 0.0
    for x in range(k1, min(K, n1) + 1): tot += math.exp(lc(n1, x) + lc(n2, K - x) - lc(N, K))
    return tot
def binom_ge(k, n, p=0.082): return sum(math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(k, n + 1))

rw = D[D.rej & D.ao.notna() & D.inwin]; aw = D[(~D.rej) & D.ao.notna() & D.inwin]
def clean(x, h=20): return x[x[f'settled{h}'] & ~x[f'guard_up{h}'] & x.adr20.notna()]
Ag = clean(aw[aw.gap_pct_at_open >= 10]); Aa = clean(aw)
ag_k, ag_n = int(Ag.reach20.sum()), len(Ag); agx_k = int(Ag.reach20x.sum()); agc_k = int((Ag.s20 <= -0.2).sum())
aa_k, aa_n = int(Aa.reach20.sum()), len(Aa)
P('=== X1 comparators (20-session, clean, in-window admitted): gap-matched (gap>=10) n=%d reach %d (%.1f%%) ex-gap-day %d crash %d (%.1f%%) | all admitted n=%d reach %d (%.1f%%) | #570 baseline reach 8.2%%' % (
    ag_n, ag_k, 100 * ag_k / ag_n, agx_k, agc_k, 100 * agc_k / ag_n, aa_n, aa_k, 100 * aa_k / aa_n))

def block(x, lab):
    n = len(x); k = int(x.reach20.sum()); kx = int(x.reach20x.sum()); kc = int((x.s20 <= -0.2).sum()); kw = int((x.s20 >= 0.2).sum())
    lo, hi = wilson(k, n); xlo, xhi = wilson(kx, n); clo, chi = wilson(kc, n)
    P(f'--- {lab}: n={n} names={x.ticker.nunique()} dates={x.scan_date.nunique()}')
    P(f'  reach (pre-registered, incl gap-day high) {k}/{n} = {100*k/n:.1f}% [{100*lo:.1f}-{100*hi:.1f}] | vs gap-matched admitted {ag_k}/{ag_n} Fisher p={fisher_greater(k, n, ag_k, ag_n):.3f} | vs #570 8.2% binomial p={binom_ge(k, n):.3f}')
    P(f'  reach ex-gap-day-high {kx}/{n} = {100*kx/n:.1f}% [{100*xlo:.1f}-{100*xhi:.1f}] | vs gap-matched admitted {agx_k}/{ag_n} Fisher p={fisher_greater(kx, n, agx_k, ag_n):.3f} | vs #570 8.2% binomial p={binom_ge(kx, n):.3f}')
    P(f'  crash (settled<=-20%) {kc}/{n} = {100*kc/n:.1f}% [{100*clo:.1f}-{100*chi:.1f}] | vs gap-matched admitted {agc_k}/{ag_n} ({100*agc_k/ag_n:.1f}%) Fisher p={fisher_greater(kc, n, agc_k, ag_n):.4f} | settled>=+20% {kw}/{n}')
    s = x.s20
    P(f'  settled-vs-D0-open (excursion-free, no fills): mean {100*s.mean():.1f}% median {100*s.median():.1f}% p10 {100*s.quantile(.1):.1f}% p90 {100*s.quantile(.9):.1f}% | gap-matched admitted: mean {100*Ag.s20.mean():.1f}% median {100*Ag.s20.median():.1f}% | all admitted median {100*Aa.s20.median():.1f}% | #570 admitted median -11.7%')
    hits = x[x.reach20]
    P(f'  of the {len(hits)} reach hits: also settled <=-20%: {int((hits.s20 <= -0.2).sum())}; hit only on the gap day itself: {int((~hits.reach20x).sum())}; hit dates: {dict(hits.scan_date.dt.strftime("%m-%d").value_counts().sort_index())}')

c50 = clean(rw[rw.ao >= 50e6]); c100 = clean(rw[rw.ao >= 100e6])
block(c50, '$50M AS-RUN (pre-registered guard)')
block(c100, '$100M AS-RUN')
# guard-dropped rows
for b in (50e6, 100e6):
    g = rw[(rw.ao >= b) & rw.settled20 & rw.adr20.notna() & rw.guard_up20]
    P(f'=== GUARD-DROPPED at >=${int(b/1e6)}M (settled, ADR defined, >4x close jump-up in D0..D0+20): {len(g)}')
    for r in g.itertuples():
        sp = S[(S.ticker == r.ticker) & (S.execution_date >= r.scan_date - pd.Timedelta(days=5))]
        P(f'  {r.scan_date.date()} {r.ticker} ao=${r.ao/1e6:.1f}M gap={r.gap_pct_at_open:.1f} max 1-day close ratio {r.maxq20:.2f} exc20 {100*r.exc20:.0f}% exc20x {100*r.exc20x:.0f}% 8xADR {100*8*r.adr20:.0f}% reach {bool(r.reach20)} reachx {bool(r.reach20x)} settled20 {100*r.s20:+.1f}% | splits near: {sp[["execution_date","split_from","split_to","adjustment_applied"]].values.tolist()}')
# BENF-restored sensitivity
rest = rw[(rw.ao >= 50e6) & rw.settled20 & rw.adr20.notna()]
block(rest, '$50M with guard-dropped rows RESTORED (sensitivity, NOT the pre-registered definition)')
# cluster / split sensitivities
P('=== $50M AS-RUN cohort, row by row (sorted by D0)')
for r in c50.sort_values(['scan_date', 'ticker']).itertuples():
    P(f'  {r.scan_date.date()} {r.ticker:5s} min={int(r.minutes_since_open_at_open)} ao=${r.ao/1e6:6.1f}M gap={r.gap_pct_at_open:6.1f} adr={r.adr20:.3f} exc={100*r.exc20:+6.0f}% excx={100*r.exc20x:+6.0f}% 8adr={100*8*r.adr20:4.0f}% reach={int(r.reach20)} reachx={int(r.reach20x)} s20={100*r.s20:+6.1f}%')
sp_names = set(S[S.adjustment_applied.astype(str) == 't'].ticker)
def has_split_in_window(r):
    end = ext[eidx[r.scan_date] + 20]
    s = S[(S.ticker == r.ticker) & (S.execution_date >= r.scan_date) & (S.execution_date <= end) & (S.adjustment_applied.astype(str) == 't')]
    return len(s) > 0
c50 = c50.assign(sp=[has_split_in_window(r) for r in c50.itertuples()])
block(c50[~c50.sp], '$50M AS-RUN minus rows with an applied split inside the 20-session window (NCT, SUGP, DLXY, RETO)')
block(c50[c50.scan_date != pd.Timestamp('2026-09-16')], '$50M AS-RUN minus the 09-16 cohort day (DLXY, MEDS, RETO, ZTG)')
P('=== per-D0-date cohort in the $50M as-run sample: n names, reach hits')
for d, g in c50.groupby('scan_date'):
    P(f'  {d.date()} n={len(g)} reach={int(g.reach20.sum())} reachx={int(g.reach20x.sum())} crash={int((g.s20 <= -0.2).sum())}')
# $10M/$25M drift vs 10-13 resolution (same definitions)
for b, old in ((10e6, '10-13: n=56 reach 14.3% crash 62.5%'), (25e6, '10-13: n=29 reach 10.3% crash 72.4%')):
    x = clean(rw[rw.ao >= b]); k = int(x.reach20.sum()); n = len(x)
    P(f'=== DRIFT ${int(b/1e6)}M now n={n} reach {k} ({100*k/n:.1f}%) binomial-vs-8.2% p={binom_ge(k, n):.3f} Fisher-vs-gap-matched-admitted p={fisher_greater(k, n, ag_k, ag_n):.3f} crash {int((x.s20<=-0.2).sum())} ({100*(x.s20<=-0.2).mean():.1f}%) | was {old}; without 09-15/09-16 D0: reach {int(x[x.scan_date<="2026-09-14"].reach20.sum())}/{len(x[x.scan_date<="2026-09-14"])}')
# projection of N clean names at $50M
P('=== PROJECTION $50M: date by which the Nth distinct in-window ADR-defined clearing name has a 20-session close (before guard attrition ~5%)')
rwc = rw[rw.adr20.notna() & (rw.ao >= 50e6)].copy(); rwc['d20'] = rwc.scan_date.map(lambda x: ext[eidx[x] + 20])
for N in (20, 25, 30, 40):
    seen = set(); when = None
    for r in rwc.sort_values('d20').itertuples():
        seen.add(r.ticker)
        if len(seen) >= N: when = r.d20; break
    P(f'  {N} names: closes through {when.date() if when is not None else "not yet"} (ingested that night, readable next morning)')
# 5-session larger sample
def clean5(x): return x[x.settled5 & ~x.guard_up5 & x.adr20.notna()]
A5 = clean5(aw[aw.gap_pct_at_open >= 10]); a5k, a5n, a5kx, a5c = int(A5.reach5.sum()), len(A5), int(A5.reach5x.sum()), int((A5.s5 <= -0.2).sum())
for b in (50e6, 100e6):
    x = clean5(rw[rw.ao >= b]); n = len(x); k = int(x.reach5.sum()); kx = int(x.reach5x.sum()); kc = int((x.s5 <= -0.2).sum())
    P(f'=== 5-SESSION larger sample >=${int(b/1e6)}M: n={n} names={x.ticker.nunique()} dates={x.scan_date.nunique()} reach {k} ({100*k/n:.1f}%) Fisher-vs-gap-matched-admitted {a5k}/{a5n} p={fisher_greater(k, n, a5k, a5n):.3f} | ex-gap-day {kx} ({100*kx/n:.1f}%) vs {a5kx}/{a5n} p={fisher_greater(kx, n, a5kx, a5n):.3f} binomial-vs-8.2% p={binom_ge(kx, n):.3f} | crash {kc} ({100*kc/n:.1f}%) vs {a5c}/{a5n} ({100*a5c/a5n:.1f}%) p={fisher_greater(kc, n, a5c, a5n):.5f}')
open('x1_extra.out', 'w').write('\n'.join(OUT) + '\n')
