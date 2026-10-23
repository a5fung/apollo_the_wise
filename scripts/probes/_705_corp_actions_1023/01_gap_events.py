"""His 10-23 question after the OPLN spin-off: do other corporate-action artifacts sit inside our trades? Step 1 (local, $0): every
one-session OPEN gap of 25% or more (either direction) inside a published C0 tl ORH5 pp trade's holding window (E .. E + exit_session),
2017-21 and 2022-24 (bars cut at 2024-12-31). Writes the distinct (ticker, date) events for the server-side corporate-action check."""
import pandas as pd, numpy as np
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_corp_actions_1023"
ERAS = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz"),
        "2022-24": ("/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz")}
ev_all = []
for era, (tf, ef) in ERAS.items():
    t = pd.read_csv(tf, sep="\t", low_memory=False, usecols=["ticker", "E", "arm", "entry", "K", "C0", "mature", "exit_session", "realized_r"])
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)].copy()
    ex = pd.read_csv(ef, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], usecols=[0, 1, 2, 5])
    ex = ex[(ex.d <= "2024-12-31") & ex.ticker.isin(set(t.ticker))].sort_values(["ticker", "d"])
    ex["pc"] = ex.groupby("ticker").c.shift(1); ex["gap"] = ex.o / ex.pc - 1
    gaps = ex[ex.gap.abs() >= 0.25][["ticker", "d", "gap", "pc", "o"]]
    idx = {k: g.d.to_numpy() for k, g in ex.groupby("ticker")}
    hits = []
    for r in t.itertuples():
        g = gaps[gaps.ticker == r.ticker]
        if g.empty: continue
        dd = idx[r.ticker]; i = np.searchsorted(dd, r.E)
        if i >= len(dd): continue
        last = dd[min(i + int(r.exit_session), len(dd) - 1)]
        for x in g[(g.d >= r.E) & (g.d <= last)].itertuples():
            hits.append((era, r.ticker, r.E, x.d, x.gap, r.realized_r))
    h = pd.DataFrame(hits, columns=["era", "ticker", "E", "gap_date", "gap", "realized_r"])
    print(f"{era}: trades {len(t):,}; trades with a >=25% one-session open gap inside the hold {h[['ticker','E']].drop_duplicates().shape[0]:,} "
          f"(down {int((h.gap < 0).sum())}, up {int((h.gap > 0).sum())}); distinct events {h[['ticker','gap_date']].drop_duplicates().shape[0]}")
    ev_all.append(h)
H = pd.concat(ev_all); H.to_csv(f"{OUT}/01_trade_gaps.tsv", sep="\t", index=False)
H[["ticker", "gap_date"]].drop_duplicates().to_csv(f"{OUT}/01_events.tsv", sep="\t", index=False)
print("events file:", len(H[["ticker", "gap_date"]].drop_duplicates()))
