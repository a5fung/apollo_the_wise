"""His 10-22 phrasing: "uptrend vs downtrend instead of bull/bear, under 200d but trending up can still be uptrend". The market's TREND
DIRECTION at D (the night before the trade), not its level: SPY's 50-day average higher than 10 sessions earlier (uptrend) or not; beside:
SPY's 20-day average higher than 5 sessions earlier; and the 2020 check — trades taken while SPY was under its 200-day but its 50-day was
rising. Per published C0 tl ORH5 pp mature trade: mean R, >= 10R per 100, win rate, n."""
import pandas as pd
for era, tf, ef in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz"),
                    ("2022-24", "/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz")):
    t = pd.read_csv(tf, sep="\t", usecols=["arm", "entry", "K", "C0", "mature", "realized_r", "D"], low_memory=False)
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)].copy()
    ex = pd.read_csv(ef, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], usecols=[0, 1, 5])
    s = ex[(ex.ticker == "SPY") & (ex.date <= "2024-12-31")].set_index("date").c.sort_index()
    m50, m20, m200 = s.rolling(50).mean(), s.rolling(20).mean(), s.rolling(200).mean()
    ph = pd.DataFrame({"up50": m50 > m50.shift(10), "up20": m20 > m20.shift(5), "under200_up50": (s < m200) & (m50 > m50.shift(10)),
                       "under200_down50": (s < m200) & ~(m50 > m50.shift(10))})
    t = t.join(ph, on="D")
    def line(lab, g): return (f"{era} {lab}: n {len(g):,} ({len(g)/len(t):.0%}), mean R {g.realized_r.mean():+.3f}, "
                              f">=10R per 100 {100*(g.realized_r >= 10).mean():.2f}, win {(g.realized_r > 0).mean():.0%}")
    for col, lab in (("up50", "SPY 50-day rising"), ("up20", "SPY 20-day rising")):
        for v, g in t.groupby(t[col].astype(bool)):
            print(line(f"{lab} = {'uptrend' if v else 'downtrend'}", g))
    for col, lab in (("under200_up50", "under the 200-day AND 50-day rising"), ("under200_down50", "under the 200-day AND 50-day falling")):
        print(line(lab, t[t[col].astype(bool)]))
