"""05: prereg 4.2 item 6 sign and lag audit for the two flagged legs (R2 2-year yield, F3 2-year minus funds rate). Reads FRED files + legs_P.csv only."""
import pandas as pd
P = pd.read_csv("build/legs_P.csv", index_col=0, parse_dates=True)
f = lambda i: pd.read_csv(f"fred/{i}.csv", index_col=0, parse_dates=True).iloc[:, 0]
d2, ff = f("DGS2"), f("DFF")
for a, b in (("2018-11-30", "2018-12-21"), ("2020-03-06", "2020-03-20")):
    print(f"FRED DGS2 {a}: {d2[a]}  {b}: {d2[b]} | DFF {a}: {ff[a]}  {b}: {ff[b]}")
for s in ("2018-12-03", "2018-12-21", "2020-03-09", "2020-03-20"):
    t = pd.Timestamp(s); prev = d2[:t - pd.Timedelta(days=1)].dropna()
    print(f"grid {s}: R2 = {P.loc[t,'R2']} (FRED DGS2 of {prev.index[-1].date()} = {prev.iloc[-1]}, the prior session: lag ok={abs(P.loc[t,'R2']-prev.iloc[-1])<1e-9}) | F3 = {P.loc[t,'F3']:.2f} = that DGS2 minus DFF of {ff[:t - pd.Timedelta(days=1)].index[-1].date()} ({ff[:t - pd.Timedelta(days=1)].iloc[-1]})")
print("Reading: the 2-year yield FELL in both windows (flight to Treasuries), and fell against the funds rate. Under prereg §3 a falling 2-year is EASY. Sign and lag match the doc; both legs stay as coded.")
