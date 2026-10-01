"""#584 probe step 1: load captured CSVs, compute outcomes per shadow row. Read-only, local."""
import pandas as pd, numpy as np
R = pd.read_csv('q2_rows_out.csv', parse_dates=['scan_date'])
B = pd.read_csv('q3_bars_out.csv', parse_dates=['trade_date'])
CAL = pd.read_csv('q4_calendar_out.csv', parse_dates=['trade_date'])
cal = list(CAL.trade_date)
cidx = {d:i for i,d in enumerate(cal)}
last_day = cal[-1]
R['failed_price_floor']=R.failed_price_floor.astype(str).eq('t'); R['failed_volume_floor']=R.failed_volume_floor.astype(str).eq('t')
R = R[R.scan_date < '2026-10-01'].copy()      # 10-01 session is live/in-progress at capture
R['rej'] = R.failed_price_floor | R.failed_volume_floor
R['cls'] = np.where(R.failed_price_floor & R.failed_volume_floor,'PV',np.where(R.failed_price_floor,'P',np.where(R.failed_volume_floor,'V','ADM')))
Bg = {t:g.set_index('trade_date').sort_index() for t,g in B.groupby('ticker')}
out=[]
for r in R.itertuples():
    g = Bg.get(r.ticker)
    d0 = r.scan_date
    rec = dict(has_bars=False)
    if g is not None and d0 in g.index:
        i = cidx[d0]
        o0 = g.at[d0,'open_price']; c0 = g.at[d0,'close']
        pre = g[g.index < d0].tail(20)
        adr = ((pre.high_price-pre.low_price)/pre.close).mean() if len(pre)>=20 else np.nan
        rec.update(has_bars=True, d0_open=o0, d0_close=c0, d0_vol=g.at[d0,'volume'], d0_dv=g.at[d0,'volume']*c0, adr20=adr, n_pre=len(pre))
        # forward window by calendar index
        for k in (5,20):
            j = i+k
            if j < len(cal) and cal[j] in g.index:
                rec[f'c{k}'] = g.at[cal[j],'close']
        fw_dates = [x for x in cal[i:min(i+21,len(cal))] if x in g.index]   # D0..D0+20 (as available)
        fw = g.loc[fw_dates]
        rec['n_fwd'] = len(fw_dates)-1
        rec['peak_hi_avail'] = fw.high_price.max()
        # peak within first 5 sessions D0..D0+5
        fw5 = g.loc[[x for x in cal[i:min(i+6,len(cal))] if x in g.index]]
        rec['n_fwd5'] = len(fw5)-1
        rec['peak_hi_5'] = fw5.high_price.max()
        cl = fw.close.values
        rec['disc_up'] = bool(len(cl)>1 and np.nanmax(cl[1:]/cl[:-1])>4)
        rec['disc_dn'] = bool(len(cl)>1 and np.nanmin(cl[1:]/cl[:-1])<0.25)
    out.append(rec)
O = pd.DataFrame(out, index=R.index)
D = pd.concat([R,O],axis=1)
D.to_pickle('a1_rows.pkl')
D.to_csv('a1_rows_with_outcomes.csv', index=False)
print('rows',len(D),'with bars',D.has_bars.sum())
rj = D[D.rej]
print('rejected rows',len(rj),'with bars',rj.has_bars.sum(), 'names', rj.ticker.nunique())
ao = rj[rj.today_dollar_volume_at_open.notna()]
print('rej with at_open dv',len(ao), 'min<=15:',(ao.minutes_since_open_at_open<=15).sum())
for k in (5,20):
    print(f'settled c{k}: rej_atopen', ao[f'c{k}'].notna().sum() if f'c{k}' in ao else 0, 'names', ao[ao[f'c{k}'].notna()].ticker.nunique() if f'c{k}' in ao else 0)
print(ao.groupby('scan_date').apply(lambda x: pd.Series(dict(n=len(x), c5=x.c5.notna().sum() if 'c5' in x else 0, c20=x.c20.notna().sum() if 'c20' in x else 0))).to_string())
print('n_fwd dist (rej at_open):'); print(ao.n_fwd.describe())
print('disc_up',ao.disc_up.sum(),'disc_dn',ao.disc_dn.sum())
print('adr nan', ao.adr20.isna().sum())
