"""#584 probe step 2: population block + per-bar sweep. Local only (reads a1_rows.pkl + captured CSVs).
Horizon = 5 sessions (the only settled horizon that exists; 20-session = 0 rows). Excursion = peak HIGH over
D0..D0+5 vs D0 open (an EXCURSION, not a return). Settled = close at D0+5 vs D0 open. No fills fabricated."""
import pandas as pd, numpy as np, math
D = pd.read_pickle('a1_rows.pkl')
B = pd.read_csv('q3_bars_out.csv', parse_dates=['trade_date'])
CAL = pd.read_csv('q4_calendar_out.csv', parse_dates=['trade_date']); cal=list(CAL.trade_date); cidx={d:i for i,d in enumerate(cal)}
Bg = {t:g.set_index('trade_date').sort_index() for t,g in B.groupby('ticker')}
BARS=[10e6,25e6,50e6,100e6]
W=15  # 09:31-09:45 => minutes_since_open_at_open <= 15

# 5-session discontinuity guard (>4x single-day close jump up, per #570) on D0..D0+5 only
def g5(r):
    g=Bg.get(r.ticker)
    if g is None or r.scan_date not in cidx: return np.nan, np.nan
    i=cidx[r.scan_date]; ds=[x for x in cal[i:i+6] if x in g.index]
    cl=g.loc[ds].close.values
    if len(cl)<2: return np.nan,np.nan
    q=cl[1:]/cl[:-1]; return float(np.nanmax(q)), float(np.nanmin(q))
tmp=D.apply(g5,axis=1,result_type='expand'); D['maxq5']=tmp[0]; D['minq5']=tmp[1]

D['ao']=D.today_dollar_volume_at_open
D['inwin']=D.minutes_since_open_at_open<=W
D['exc5']=D.peak_hi_5/D.d0_open-1
D['s5']=D.c5/D.d0_open-1
D['s5_vs_close']=D.c5/D.d0_close-1
D['reach8']=D.exc5>=8*D.adr20
D['full_dv']=D.d0_dv
D['settled5']=D.c5.notna() & (D.n_fwd5==5) & D.d0_open.gt(0)
D['guard_up']=D.maxq5>4
D['guard_dn']=D.minq5<0.25

def wilson(k,n,z=1.96):
    if n==0: return (np.nan,np.nan)
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); a=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return ((c-a)/d,(c+a)/d)

L=[]
def P(*a):
    s=' '.join(str(x) for x in a); print(s); L.append(s)

ALLD=sorted(D.scan_date.unique()); nd=len(ALLD)
P('=== POPULATION (captured 2026-10-01 ~13:46Z; 10-01 session in progress => EXCLUDED)')
P('scan dates in analysis:',nd,ALLD[0].date(),'->',ALLD[-1].date())
P('all shadow rows (both sides):',len(D),' names:',D.ticker.nunique())
rej=D[D.rej]; adm=D[~D.rej]
P('rejected-side rows:',len(rej),'names:',rej.ticker.nunique(),'| admitted-side rows:',len(adm),'names:',adm.ticker.nunique())
P('rejected by class: ',rej.cls.value_counts().to_dict())
ra=rej[rej.ao.notna()]
P('rejected with at_open dollar-volume read:',len(ra),'names:',ra.ticker.nunique(),'dates:',ra.scan_date.nunique())
P('  of which no post-open read at all (pre-market-only rows, excluded):',len(rej)-len(ra))
P('  fallback to _last (minutes_since_open_last<=15) used on rows with NO at_open read:',int(((rej.ao.isna())&rej.today_dollar_volume_last.notna()&(rej.minutes_since_open_last<=15)).sum()),'=> fallback NOT used')
P('  at_open read minute mix (rejected):',ra.minutes_since_open_at_open.value_counts().sort_index().to_dict())
rw=ra[ra.inwin]
P('  IN-WINDOW (minutes<=15) rejected rows:',len(rw),'names:',rw.ticker.nunique(),'| out-of-window (20/25 min) rows excluded from sweep:',int((~ra.inwin).sum()))
P('  in-window by class:',rw.cls.value_counts().to_dict())
P('  in-window gap_pct_at_open quantiles (5/25/50/75/95):',[round(x,1) for x in rw.gap_pct_at_open.quantile([.05,.25,.5,.75,.95])], '| share gap>=9:',round((rw.gap_pct_at_open>=9).mean(),3),'| >=10:',round((rw.gap_pct_at_open>=10).mean(),3))
P('  in-window rows/day: by date', {str(k.date())[5:]:int(v) for k,v in rw.groupby('scan_date').size().items()})
P('  in-window rows with bars:',int(rw.has_bars.sum()),'| ADR20 NaN (<20 prior sessions):',int(rw.adr20.isna().sum()))
sw=rw[rw.settled5]
P('SETTLED  20-session closes (rejected, at_open, any window):',int(ra.c20.notna().sum()) if 'c20' in ra else 0,'rows / 0 names  (earliest cohort 09-02 reaches D0+20 on 10-01, not yet in mi_daily_closes max trade_date',cal[-1].date(),')')
P('SETTLED  5-session closes (rejected, at_open, any window):',int(ra.c5.notna().sum()),'rows /',ra[ra.c5.notna()].ticker.nunique(),'names, dates',ra[ra.c5.notna()].scan_date.min().date(),'->',ra[ra.c5.notna()].scan_date.max().date())
P('SETTLED  5-session closes IN-WINDOW rejected:',len(sw),'rows /',sw.ticker.nunique(),'names; excl guard(up>4x):',int(sw.guard_up.sum()),'rows, guard(down<0.25):',int(sw.guard_dn.sum()),'rows (down NOT excluded; sensitivity below)')
swc=sw[~sw.guard_up & sw.adr20.notna()]
P('  analysis sample after dropping guard_up and NaN-ADR:',len(swc),'rows /',swc.ticker.nunique(),'names')
aw=adm[adm.ao.notna()&adm.inwin]
awc=aw[aw.settled5 & ~aw.guard_up & aw.adr20.notna()]
P('ADMITTED pool same window (cleared both floors, at_open read in-window): rows',len(aw),'names',aw.ticker.nunique(),'| settled5 clean:',len(awc),'rows /',awc.ticker.nunique(),'names')
P()

def stat(x, label, ndays_rows=None):
    n=len(x); k8=int(x.reach8.sum()); lo,hi=wilson(k8,n)
    ks=int((x.s5<=-0.20).sum()); klo,khi=wilson(ks,n)
    kw=int((x.s5>=0.20).sum())
    return dict(label=label, n=n, names=x.ticker.nunique(), reach8_k=k8, reach8=k8/n if n else np.nan, r8_lo=lo, r8_hi=hi,
        exc_med=x.exc5.median(), exc_p90=x.exc5.quantile(.9), s5_med=x.s5.median(), s5_p10=x.s5.quantile(.1), s5_mean=x.s5.mean(),
        crash20=ks/n if n else np.nan, c_lo=klo, c_hi=khi, win20=kw/n if n else np.nan, win20_k=kw)

def table(R, A, title, gapmin=None):
    P('====',title)
    rs=R.copy(); as_=A.copy()
    if gapmin is not None:
        rs=rs[rs.gap_pct_at_open>=gapmin]; as_=as_[as_.gap_pct_at_open>=gapmin]
    rows=[]
    # names/day admitted per bar: all in-window rejected rows with at_open read (not only settled) / nd
    for b in [0]+BARS:
        sub_all = rs[rs.ao>=b] if b else rs
        sub = sub_all[sub_all.settled5 & ~sub_all.guard_up & sub_all.adr20.notna()]
        s=stat(sub, ('REJ all in-window' if b==0 else f'REJ >= ${int(b/1e6)}M'))
        s['names_per_day']=len(sub_all)/nd; s['rows_all']=len(sub_all)
        # minute mix in cleared (all in-window, not just settled)
        m=sub_all.minutes_since_open_at_open
        s['mix']=f"min1:{int((m==1).sum())} min5-10:{int(((m>=5)&(m<=10)).sum())} min15:{int((m==15).sum())}"
        # identifiability vs full-day tier-A ($50M D0 dollar volume)
        z=sub_all[sub_all.full_dv.notna()]
        s['prec_fullA']=(z.full_dv>=50e6).mean() if len(z) else np.nan
        rows.append(s)
    for b in [0]+BARS:
        sub_all = as_[as_.ao>=b] if b else as_
        sub = sub_all[sub_all.settled5 & ~sub_all.guard_up & sub_all.adr20.notna()]
        s=stat(sub, ('ADM all in-window' if b==0 else f'ADM >= ${int(b/1e6)}M'))
        s['names_per_day']=len(sub_all)/nd; s['rows_all']=len(sub_all); s['mix']=''; s['prec_fullA']=np.nan
        rows.append(s)
    T=pd.DataFrame(rows)
    pd.set_option('display.width',250); pd.set_option('display.max_columns',40)
    f=T.copy()
    for c in ['reach8','r8_lo','r8_hi','crash20','c_lo','c_hi','win20','exc_med','exc_p90','s5_med','s5_p10','s5_mean','prec_fullA']:
        f[c]=(f[c]*100).round(1)
    f['names_per_day']=f.names_per_day.round(1)
    P(f[['label','rows_all','names_per_day','n','names','reach8_k','reach8','r8_lo','r8_hi','exc_med','exc_p90','s5_med','s5_p10','crash20','c_lo','c_hi','win20_k','win20','prec_fullA','mix']].to_string(index=False))
    P()
    return T

T1=table(rw, aw, 'PRIMARY: in-window (<=15 min at_open read), all gaps, horizon 5 sessions')
T1.to_csv('a2_table_primary.csv',index=False)
T2=table(rw, aw, 'SENSITIVITY: same, gap_pct_at_open >= 10%', gapmin=10.0)
T2.to_csv('a2_table_gap10.csv',index=False)

# Recall of full-day tier-A among in-window rejected rows (what share of the names that DID reach $50M all-day were visible at the open at each bar)
P('==== IDENTIFIABILITY: in-window rejected rows, full-day D0 dollar volume (mi_daily_closes volume*close) >= $50M')
fa=rw[rw.full_dv>=50e6]
P('rows with full-day >= $50M:',len(fa),'names:',fa.ticker.nunique(),'| per day:',round(len(fa)/nd,1))
for b in BARS:
    P(f'  at_open >= ${int(b/1e6)}M catches',int((fa.ao>=b).sum()),'of',len(fa),f'({(fa.ao>=b).mean()*100:.0f}% recall of the full-day tier-A)')
P('  median at_open dv of full-day>=$50M rows: $%.1fM ; of full-day<$50M rows: $%.2fM'%(fa.ao.median()/1e6, rw[rw.full_dv<50e6].ao.median()/1e6))
P()
# By read minute: median at_open dv (shows the mix problem)
P('==== at_open dollar-volume by read minute (in-window rejected): median, share>=$10M, >=$50M')
for m,g in rw.groupby('minutes_since_open_at_open'):
    P(f'  min {m}: n={len(g)} med=${g.ao.median()/1e6:.2f}M >=10M {((g.ao>=10e6).mean()*100):.1f}% >=50M {((g.ao>=50e6).mean()*100):.1f}%')
P()
# guard-down sensitivity at each bar (rows with <0.25 single-day drop kept in primary; show effect)
P('==== SENSITIVITY: also exclude guard_dn rows (single-day close <0.25x) in the REJ settled sample')
for b in [0]+BARS:
    sub=(rw[rw.ao>=b] if b else rw); sub=sub[sub.settled5 & ~sub.guard_up & sub.adr20.notna()]
    s2=sub[~sub.guard_dn]
    P(f'  bar {int(b/1e6)}M: n {len(sub)}->{len(s2)}, reach8 {sub.reach8.mean()*100:.1f}%->{s2.reach8.mean()*100:.1f}%, s5 med {sub.s5.median()*100:.1f}%->{s2.s5.median()*100:.1f}%')
P()
# Projection: when does a >=15-name 20-session settled sample exist per bar? (20 sessions after D0, calendar extended with weekdays; NYSE open all Oct)
ext=list(cal)
d=cal[-1]
while len(ext)<len(cal)+40:
    d=d+pd.Timedelta(days=1)
    if d.weekday()<5: ext.append(d)
eidx={x:i for i,x in enumerate(ext)}
P('==== PROJECTION: earliest mi_daily_closes max trade_date at which >=15 in-window rejected NAMES (distinct, ADR ok) clearing each bar have a 20-session close')
rwc=rw[rw.adr20.notna()].copy()
rwc['d20']=rwc.scan_date.map(lambda x: ext[eidx[x]+20])
for b in [0]+BARS:
    sub=rwc[rwc.ao>=b] if b else rwc
    sub=sub.sort_values('d20'); seen=set(); when=None
    for r in sub.itertuples():
        seen.add(r.ticker)
        if len(seen)>=15: when=r.d20; break
    tot=sub.ticker.nunique()
    P(f'  bar {int(b/1e6)}M: in-window clearing names total through 09-30 = {tot}; 15th distinct name settles-at-20 once closes reach {when.date() if when is not None else "never within window"}')
open('a2_sweep_out.txt','w').write('\n'.join(L)+'\n')
D.to_pickle('a2_rows.pkl')
