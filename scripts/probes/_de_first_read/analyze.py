import csv, collections, datetime as dt
rows=[]
with open('q2_rows_out.txt') as f:
    lines=f.read().splitlines()
hdr=lines[0].split('|')
for l in lines[1:]:
    if l.startswith('('): break
    rows.append(dict(zip(hdr,l.split('|'))))
print('prospective rows',len(rows))
cut=dt.date(2026,10,9)-dt.timedelta(days=30)
def mature(r): return dt.date.fromisoformat(r['fire_date'])<=cut
def f(x): return float(x) if x not in ('',None) else None
C=collections.Counter
print('by maturity/settled:',C((mature(r), r['realized_r']!='', r['outcome'] or 'OPEN') for r in rows))
M=[r for r in rows if mature(r) and r['realized_r']!='']
print('MATURE settled',len(M))
print('mature all (incl unsettled):',C((r['outcome'] or 'OPEN') for r in rows if mature(r)))
print('fire_date range',min(r['fire_date'] for r in M),max(r['fire_date'] for r in M))
print('ep_date range',min(r['ep_date'] for r in M),max(r['ep_date'] for r in M))
print('campaigns (ticker,ep_date):',len({(r['ticker'],r['ep_date']) for r in M}))
for k in ['rung','pattern_version','screen_version','screen_member','reentry_shape','outcome','settle_version','resolution','catalyst_grade']:
    print(k,dict(C(r[k] for r in M)))
print()
print('rung x screen x outcome')
for rung in sorted({r['rung'] for r in M}):
    for lvl in ['raw','screen']:
        S=[r for r in M if r['rung']==rung and (lvl=='raw' or r['screen_member']=='t')]
        tails=[r for r in S if f(r['realized_r'])>=4]
        r4=[r for r in S if r['reached_4r']=='t']
        rs=[f(r['realized_r']) for r in S]
        print(f"{rung:22s} {lvl:6s} n={len(S):3d} tail(realized>=4)={len(tails)} reached_4r={len(r4)} stops={sum(r['outcome']=='stop' for r in S)} other={C(r['outcome'] for r in S if r['outcome']!='stop')} sumR={sum(rs) if rs else 0:.2f} maxR={max(rs) if rs else None}")
print()
print('ALL rungs raw/screen')
for lvl in ['raw','screen']:
    S=[r for r in M if (lvl=='raw' or r['screen_member']=='t')]
    print(lvl,len(S),'tails',sum(f(r['realized_r'])>=4 for r in S),'reached4',sum(r['reached_4r']=='t' for r in S),'first-only',sum(r['reentry_shape']=='first' for r in S))
print()
for r in sorted(M,key=lambda r:-f(r['realized_r'])):
    print(r['ticker'],r['ep_date'],r['rung'],r['fire_date'],r['reentry_shape'],r['screen_member'],r['outcome'],r['realized_r'],'trail',r['realized_r_trail'],'mfe',r['mfe_r'],'r4',r['reached_4r'],'075',r['realized_r_075'],r['reached_4r_075'],'100',r['realized_r_100'],r['reached_4r_100'])
print()
print('created lag days (created - fire):',C((dt.date.fromisoformat(r['created_et'][:10])-dt.date.fromisoformat(r['fire_date'])).days for r in M))
print('non-mature rows by fire_date month:',C((r['fire_date'][:7], r['outcome'] or 'OPEN') for r in rows if not mature(r)))
