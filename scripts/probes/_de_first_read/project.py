import collections,datetime as dt
L=open('q2_rows_out.txt').read().splitlines(); h=L[0].split('|')
R=[dict(zip(h,l.split('|'))) for l in L[1:] if not l.startswith('(')][:131]
print('all prospective by rung x screen:',collections.Counter((r['rung'],r['screen_member']=='t') for r in R))
print('first-attempt only:',collections.Counter((r['rung'],r['reentry_shape']) for r in R))
d0,d1=dt.date(2026,8,31),dt.date(2026,10,8)
wk=((d1-d0).days+1)/7
for rung in sorted({r['rung'] for r in R}):
    for lvl in ['raw','screen']:
        S=[r for r in R if r['rung']==rung and (lvl=='raw' or r['screen_member']=='t')]
        rate=len(S)/wk
        mat=sum(1 for r in S if dt.date.fromisoformat(r['fire_date'])<=dt.date(2026,9,9))
        need=max(0,30-mat)
        # fires already recorded but not yet mature count toward future maturity
        recorded=len(S)
        if recorded>=30:
            # date when 30th fire (by fire_date) matures
            fd=sorted(dt.date.fromisoformat(r['fire_date']) for r in S)[29]
            when=fd+dt.timedelta(days=30); src='already fired'
        else:
            more=30-recorded; when=d1+dt.timedelta(days=7*more/rate if rate else 9999)+dt.timedelta(days=30); src='projected'
        print(f"{rung:20s} {lvl:6s} recorded={recorded:3d} mature_now={mat:2d} rate/wk={rate:4.1f} 30th mature ~{when} ({src})")
print('weeks',round(wk,2),'total rate/wk',round(len(R)/wk,1))
print('fires per week:',sorted(collections.Counter(dt.date.fromisoformat(r['fire_date']).isocalendar()[1] for r in R).items()))
