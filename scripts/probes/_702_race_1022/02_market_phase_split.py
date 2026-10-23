"""His 10-22 question: breakouts fail in bear phases — do our breakout trades split by the market's phase? Three phase readings at D
(the night before the trade): QQQ 10 > 20-day average (the setup's own phase_qqq_10_20 column), QQQ close above its 50-day, SPY close
above its 200-day. Per published C0 tl ORH5 pp mature trade: mean R, >= 10R per 100, win rate, n."""
import pandas as pd, numpy as np
for era, tf, ef in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz"),
                    ("2022-24", "/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz")):
    t = pd.read_csv(tf, sep="\t", usecols=["arm", "entry", "K", "C0", "mature", "phase_qqq_10_20", "realized_r", "D"], low_memory=False)
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)].copy()
    ex = pd.read_csv(ef, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], usecols=[0, 1, 5])
    ex = ex[ex.ticker.isin(["QQQ", "SPY"]) & (ex.date <= "2024-12-31")]
    px = ex.pivot(index="date", columns="ticker", values="c").sort_index()
    ph = pd.DataFrame({"qqq_gt_50": px.QQQ > px.QQQ.rolling(50).mean(), "spy_gt_200": px.SPY > px.SPY.rolling(200).mean()})
    t = t.join(ph, on="D")
    for col, lab in (("phase_qqq_10_20", "QQQ 10 > 20-day"), ("qqq_gt_50", "QQQ above 50-day"), ("spy_gt_200", "SPY above 200-day")):
        for v, g in t.groupby(t[col].astype(bool)):
            print(f"{era} {lab} = {'bull' if v else 'bear'}: n {len(g):,} ({len(g)/len(t):.0%}), mean R {g.realized_r.mean():+.3f}, "
                  f">=10R per 100 {100*(g.realized_r >= 10).mean():.2f}, win {(g.realized_r > 0).mean():.0%}")
