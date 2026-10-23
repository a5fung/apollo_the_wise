"""Step 1b: the same >=25% one-session open-gap scan on the real-breakout (R1) trades of the trail read (cells A20_X1_P1 = pp and
A20_X3_P0, first entries and retries), entry_date .. exit session. Appends distinct events to 01_events.tsv."""
import pandas as pd, numpy as np
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_corp_actions_1023"
ERAS = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre/out/trail_r1_2017-21.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz"),
        "2022-24": ("/Users/alvinfung/apollo_data/cb702/out/trail_r1_2022-24.tsv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz")}
allh = []
for era, (tf, ef) in ERAS.items():
    t = pd.read_csv(tf, sep="\t", low_memory=False, usecols=["cell", "attempt", "ticker", "entry_date", "exit_j", "realized_r"])
    t = t[t.cell.isin(["A20_X1_P1", "A20_X3_P0"]) & t.exit_j.notna()]
    ex = pd.read_csv(ef, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], usecols=[0, 1, 2, 5])
    ex = ex[(ex.d <= "2024-12-31") & ex.ticker.isin(set(t.ticker))].sort_values(["ticker", "d"])
    ex["pc"] = ex.groupby("ticker").c.shift(1); ex["gap"] = ex.o / ex.pc - 1
    gaps = ex[ex.gap.abs() >= 0.25]
    gt = {k: g for k, g in gaps.groupby("ticker")}; idx = {k: g.d.to_numpy() for k, g in ex.groupby("ticker")}
    hits = []
    for r in t.itertuples():
        g = gt.get(r.ticker)
        if g is None: continue
        dd = idx[r.ticker]; i = np.searchsorted(dd, r.entry_date)
        last = dd[min(i + int(r.exit_j), len(dd) - 1)]
        for x in g[(g.d > r.entry_date) & (g.d <= last)].itertuples():
            hits.append((era, r.cell, r.attempt, r.ticker, r.entry_date, x.d, x.gap, r.realized_r))
    h = pd.DataFrame(hits, columns=["era", "cell", "attempt", "ticker", "entry", "gap_date", "gap", "realized_r"])
    print(f"{era}: R1 trades {len(t):,}; with a >=25% gap inside the hold {len(h):,} (down {int((h.gap<0).sum())}, up {int((h.gap>0).sum())}); "
          f"distinct events {h[['ticker','gap_date']].drop_duplicates().shape[0]}")
    allh.append(h)
H = pd.concat(allh); H.to_csv(f"{OUT}/02_r1_trade_gaps.tsv", sep="\t", index=False)
ev = pd.concat([pd.read_csv(f"{OUT}/01_events.tsv", sep="\t"), H[["ticker", "gap_date"]]]).drop_duplicates()
ev.to_csv(f"{OUT}/01_events.tsv", sep="\t", index=False); print("events total:", len(ev))
