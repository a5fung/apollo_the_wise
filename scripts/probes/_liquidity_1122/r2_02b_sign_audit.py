"""r2_02b: §4.2 item 6 sign and lag audit of the legs flagged under the trend vote (R2, F3, K5). Reads build/legs_P.csv (raw un-negated leg series) only."""
import pandas as pd
P = pd.read_csv("build/legs_P.csv", index_col=0, parse_dates=True); assert P.index.max() <= pd.Timestamp("2024-12-31")
for k, name, tight_when in (("R2", "2-year yield (DGS2, next-session lag checked in run-1 05)", "P rises"), ("F3", "2-year minus funds rate", "P rises"), ("K5", "ARKK / QQQ (same-day ETF ratio, no lag)", "P falls")):
    m20, m50 = P[k].rolling(20).mean(), P[k].rolling(50).mean()
    print(f"\n{k} {name}; tight when {tight_when}")
    for d in ("2018-10-01", "2018-12-03", "2018-12-21", "2020-02-19", "2020-03-09", "2020-03-20"):
        t = pd.Timestamp(d); print(f"  {d}: P={P.loc[t,k]:.4f}  MA20={m20[t]:.4f}  MA50={m50[t]:.4f}  -> 20-day {'ABOVE' if m20[t]>m50[t] else 'BELOW'} 50-day")
print("""
Reading (code vs doc §3):
- R2, F3: the 2-year yield's 20-day sat below its 50-day in both windows (flight to Treasuries); doc: a falling 2-year is EASY. Sign and lag as the doc; stay.
- K5: doc X = -(ARKK/QQQ), tight when speculative growth LAGS. In both windows the ARKK/QQQ 20-day sat above its 50-day on most sessions (ARKK held up vs QQQ on the 20/50 trend), so the leg reads EASY. The code matches the doc's sign; same-day ETF closes, no lag. Stays as coded.""")
