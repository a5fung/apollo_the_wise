import sys, statistics as st
rows=[]
lines=open('q1.out').read().splitlines()
i=lines.index('ticker|alert_date|era|reason|has_alert|o|c5|c20')
for l in lines[i+1:]:
    if l.startswith('('): break
    t,d,era,reason,ha,o,c5,c20=l.split('|')
    v='PASS' if not reason else ('DOWNGRADE' if all(r.startswith('rubric_composite_') for r in reason.split(';')) else 'OTHER:'+reason)
    rows.append(dict(t=t,d=d,era=era,v=v,ha=ha=='t',o=float(o) if o else None,c5=float(c5) if c5 else None,c20=float(c20) if c20 else None))
def p90(x): s=sorted(x); return s[round(0.9*(len(s)-1))]
def line(lbl,xs):
    if not xs: return f'{lbl:22s} n=0'
    n=len(xs); t20=sum(x>=20 for x in xs); t40=sum(x>=40 for x in xs)
    return f'{lbl:22s} n={n:3d}  >=+20%: {t20} ({100*t20/n:.0f}%)  >=+40%: {t40} ({100*t40/n:.0f}%)  p90 {p90(xs):+.1f}%  median {st.median(xs):+.1f}%  win {100*sum(x>0 for x in xs)/n:.0f}%'
other=[r for r in rows if r['v'].startswith('OTHER')]
print('OTHER-reason rows:',len(other),sorted(set(r['v'] for r in other))[:5])
for H in ('c5','c20'):
    print(f'\n== {H[1:]}-session return from alert-day open ==')
    for era in ('pre','post'):
        for v in ('PASS','DOWNGRADE'):
            xs=[100*(r[H]-r['o'])/r['o'] for r in rows if r['era']==era and r['v']==v and r['o'] and r[H]]
            print(line(f'{era} {v}',xs))
post_pass=[r for r in rows if r['era']=='post' and r['v']=='PASS']
print('\npost PASS rows with no live alert record:', [ (r['t'],r['d']) for r in post_pass if not r['ha']])
print('post PASS settled 5d, each:')
for r in post_pass:
    if r['o'] and r['c5']: print(f"  {r['t']:6s} {r['d']}  5d {100*(r['c5']-r['o'])/r['o']:+.1f}%" + (f"  20d {100*(r['c20']-r['o'])/r['o']:+.1f}%" if r['c20'] else '') + ('' if r['ha'] else '  [no alert row]'))
xs=[100*(r['c5']-r['o'])/r['o'] for r in rows if r['era']=='post' and r['v']=='PASS' and r['o'] and r['c5'] and r['ha']]
print(line('post PASS, alerted only',xs))
print('\n== alerted rows only (a live alert record exists) ==')
for H in ('c5','c20'):
    for era in ('pre','post'):
        for v in ('PASS','DOWNGRADE'):
            xs=[100*(r[H]-r['o'])/r['o'] for r in rows if r['era']==era and r['v']==v and r['o'] and r[H] and r['ha']]
            print(H, line(f'{era} {v}',xs))
for era in ('pre','post'):
    for v in ('PASS','DOWNGRADE'):
        g=[r for r in rows if r['era']==era and r['v']==v]
        print(f'{era} {v}: {len(g)} rows, {sum(r["ha"] for r in g)} with an alert record')
# chance of 0 tail hits in PASS if PASS were as good as DOWNGRADE (post, 5d)
p=7/84; print('\nchance of 0 of 24 at the DOWNGRADE tail rate:', round((1-p)**24,3))
print('\npost DOWNGRADE rows that rose >= +20% in 5 sessions:')
for r in rows:
    if r['era']=='post' and r['v']=='DOWNGRADE' and r['o'] and r['c5'] and 100*(r['c5']-r['o'])/r['o']>=20:
        print(f"  {r['t']:6s} {r['d']}  5d {100*(r['c5']-r['o'])/r['o']:+.1f}%" + (f"  20d {100*(r['c20']-r['o'])/r['o']:+.1f}%" if r['c20'] else '') + ('  [alerted]' if r['ha'] else ''))
