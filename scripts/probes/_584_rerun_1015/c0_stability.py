"""#584 rerun: stability of previously-pulled closes + splits (old 10-01 capture vs fresh pull). Reads only."""
import pandas as pd, numpy as np
old = pd.read_csv('../_584/q3_bars_out.csv', parse_dates=['trade_date'], keep_default_na=False, na_values=[''])
new = pd.read_csv('q3_closes.out', parse_dates=['trade_date'], keep_default_na=False, na_values=[''])
m = old.merge(new, on=['ticker','trade_date'], suffixes=('_o','')); print('old rows',len(old),'matched',len(m))
for c in ['open_price','high_price','low_price','close','volume']:
    x=m[c+'_o'].astype(float); y=m[c].astype(float)
    rel=((y-x).abs()/x.abs().replace(0,np.nan)); bad=rel>0.001
    print(c,'rows differing >0.1%:',int(bad.sum()),'tickers:',m[bad].ticker.nunique())
bad=m[((m.close-m.close_o).abs()/m.close_o.abs())>0.001]
print(bad.groupby('ticker').agg(n=('close','size'),first=('trade_date','min'),last=('trade_date','max'),ratio=('close',lambda s: np.nan)).head(40).to_string())
if len(bad):
    r=(bad.close/bad.close_o); bad=bad.assign(ratio=r)
    print(bad.groupby('ticker').ratio.agg(['median','min','max','size']).to_string())
S_old=pd.read_csv('../_584/q6_splits_out.csv'); S_new=pd.read_csv('q5_splits.out')
print('splits old',len(S_old),'new',len(S_new),'new execution_date>=2026-10-01:',(S_new.execution_date>='2026-10-01').sum())
print(S_new[S_new.execution_date>='2026-10-01'].to_string(index=False))
print('adjustment_applied counts new:',S_new.adjustment_applied.value_counts().to_dict())
