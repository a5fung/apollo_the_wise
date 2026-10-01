import pandas as pd, numpy as np
pd.set_option('display.width',250); pd.set_option('display.max_columns',40); pd.set_option('display.max_rows',200)
D=pd.read_pickle('a2_rows.pkl')
S=pd.read_csv('q6_splits_out.csv',parse_dates=['execution_date'])
rw=D[D.rej & D.ao.notna() & D.inwin & D.settled5 & ~D.guard_up & D.adr20.notna()].copy()
aw=D[(~D.rej) & D.ao.notna() & D.inwin & D.settled5 & ~D.guard_up & D.adr20.notna()].copy()
print('splits in window for shadow names:',len(S))
# split within D0..D0+5 sessions flagged
def split_in(r):
    s=S[(S.ticker==r.ticker)&(S.execution_date>=r.scan_date)&(S.execution_date<=r.scan_date+pd.Timedelta(days=9))]
    return len(s)>0
rw['split5']=rw.apply(split_in,axis=1); aw['split5']=aw.apply(split_in,axis=1)
print('rows with a split in D0..D0+9d: REJ',int(rw.split5.sum()),'ADM',int(aw.split5.sum()))
print('gap_at_open median: REJ in-win',rw.gap_pct_at_open.median().round(1),'| REJ>=10M',rw[rw.ao>=10e6].gap_pct_at_open.median().round(1),'| REJ>=50M',rw[rw.ao>=50e6].gap_pct_at_open.median().round(1),'| ADM all',aw.gap_pct_at_open.median().round(1),'| ADM gap>=10',aw[aw.gap_pct_at_open>=10].gap_pct_at_open.median().round(1))
print('share gap>=10: REJ>=10M',(rw[rw.ao>=10e6].gap_pct_at_open>=10).mean().round(3),'REJ>=50M',(rw[rw.ao>=50e6].gap_pct_at_open>=10).mean().round(3),'ADM',(aw.gap_pct_at_open>=10).mean().round(3))
print('cls mix REJ>=10M',rw[rw.ao>=10e6].cls.value_counts().to_dict(),'REJ>=50M',rw[rw.ao>=50e6].cls.value_counts().to_dict())
print('prev_close median: REJ>=10M',rw[rw.ao>=10e6].prev_close.median(),'REJ>=50M',rw[rw.ao>=50e6].prev_close.median(),'ADM',aw.prev_close.median())
for lab,sub in [('REJ>=10M',rw[rw.ao>=10e6]),('REJ>=50M',rw[rw.ao>=50e6]),('ADM gap10',aw[aw.gap_pct_at_open>=10])]:
    print(lab,'s5 med vs open',round(sub.s5.median()*100,1),'| vs D0 close',round(sub.s5_vs_close.median()*100,1),'| D0 close/open med',round((sub.d0_close/sub.d0_open-1).median()*100,1),'| split5',int(sub.split5.sum()))
cols=['scan_date','ticker','cls','prev_close','gap_pct_at_open','minutes_since_open_at_open','ao','full_dv','d0_open','d0_close','c5','s5','exc5','adr20','reach8','split5']
x=rw[rw.ao>=50e6].sort_values('s5')[cols].copy(); x['ao']=(x.ao/1e6).round(1); x['full_dv']=(x.full_dv/1e6).round(1)
for c in ['s5','exc5','adr20']: x[c]=(x[c]*100).round(1)
print(x.to_string(index=False))
x.to_csv('a3_rej_ge50M_rows.csv',index=False)
print('ADM gap>=10 rows:'); y=aw[aw.gap_pct_at_open>=10].sort_values('s5')[cols].copy(); y['ao']=(y.ao/1e6).round(2); y['full_dv']=(y.full_dv/1e6).round(1)
for c in ['s5','exc5','adr20']: y[c]=(y[c]*100).round(1)
print(y.head(12).to_string(index=False)); print('...'); print(y.tail(6).to_string(index=False))
# per-day expected counts (names/day) x share, per bar, gap10 sample
nd=20
print('\nPER-DAY PRICE (gap>=10 sample, in-window, n/day over 20 dates):')
for b in [10e6,25e6,50e6,100e6]:
    sub_all=D[D.rej & D.ao.notna() & D.inwin & (D.ao>=b) & (D.gap_pct_at_open>=10)]
    sub=rw[(rw.ao>=b)&(rw.gap_pct_at_open>=10)]
    npd=len(sub_all)/nd
    print(f'  >=${int(b/1e6)}M: {npd:.1f} names/day admitted; of settled n={len(sub)}: reach8 {sub.reach8.mean()*100:.1f}% -> {npd*sub.reach8.mean():.2f}/day ; settled>=+20% {(sub.s5>=.2).mean()*100:.1f}% -> {npd*(sub.s5>=.2).mean():.2f}/day ; settled<=-20% {(sub.s5<=-.2).mean()*100:.1f}% -> {npd*(sub.s5<=-.2).mean():.2f}/day ; settled<=-50% {(sub.s5<=-.5).mean()*100:.1f}%')
sub=aw[aw.gap_pct_at_open>=10]; npd=len(D[(~D.rej)&D.ao.notna()&D.inwin&(D.gap_pct_at_open>=10)])/nd
print(f'  ADM gap>=10: {npd:.1f} names/day (already admitted); reach8 {sub.reach8.mean()*100:.1f}% ; settled>=+20% {(sub.s5>=.2).mean()*100:.1f}% ; <=-20% {(sub.s5<=-.2).mean()*100:.1f}% ; <=-50% {(sub.s5<=-.5).mean()*100:.1f}% ; median {sub.s5.median()*100:.1f}%')
