"""Find the rows pipeline B includes in the 5-session REJ in-window sample but A does not (reconciliation: n 2010 vs 2008, identical reach/crash/win counts)."""
import sys, os, runpy
import pandas as pd
sys.argv = ['v5_verify.py', '5']
g = runpy.run_path('v5_verify.py')
cl = g['cl']
SCR = os.environ['SCR']
D = pd.read_pickle(SCR + '/a2_rows.pkl')
A = D[D.rej & D.ao.notna() & D.inwin & D.settled5 & ~D.guard_up5 & D.adr20.notna()]
ka = set(zip(A.scan_date.dt.date, A.ticker)); kb = set((r['scan_date'], r['ticker']) for r in cl)
print('A', len(ka), 'B', len(kb), 'B-A', sorted(kb - ka), 'A-B', sorted(ka - kb))
for (d, t) in sorted(kb - ka):
    x = D[(D.scan_date == pd.Timestamp(d)) & (D.ticker == t)].iloc[0]
    print(t, d, dict(c5=x.c5, n_fwd5=x.n_fwd5, d0_open=x.d0_open, adr20=x.adr20, maxq5=x.maxq5, guard_up5=x.guard_up5, settled5=x.settled5, exc5=x.exc5, s5=x.s5, peak5=x.peak_hi_5))
    b = g['bars'][t]
    print('  bars around:', {str(k): v for k, v in b.items() if pd.Timestamp(d) - pd.Timedelta(days=3) <= pd.Timestamp(k) <= pd.Timestamp(d) + pd.Timedelta(days=10)})
