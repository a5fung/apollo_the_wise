"""Step 5: how the suspected artifacts move the headline numbers. Suspects (by hand, step 4 + verifier notes): spin-off / distribution gaps
OPLN 2019-06-28 (KAR -> IAA), ZWS 2021-10-05 (Rexnord -> Regal), BEP 2020-07-30 (BEPC distribution); a non-stock in the population DWT
(a 3x inverse crude ETN); up-gaps that fully reverted the next session (bad-print suspects, 7). Recomputes (a) the published C0 row
(mean R, >= 10R per 100) and (b) the trail read's R1 pp and 20.X3.P0 cells (mean R per first trade, worst trade) without trades whose
hold contains a suspect event."""
import pandas as pd
D = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_corp_actions_1023"
lc = pd.read_csv(f"{D}/05_local_checks.tsv", sep="\t")
sus = {("OPLN", "2019-06-28"), ("ZWS", "2021-10-05"), ("BEP", "2020-07-30")}
sus |= {(r.ticker, r.gap_date) for r in lc[lc.up_gap_reverted_next_day == True].itertuples()}
etn = {"DWT"}
pub = pd.read_csv(f"{D}/01_trade_gaps.tsv", sep="\t"); r1 = pd.read_csv(f"{D}/02_r1_trade_gaps.tsv", sep="\t")
for era, tf in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz"), ("2022-24", "/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz")):
    t = pd.read_csv(tf, sep="\t", low_memory=False, usecols=["ticker", "E", "arm", "entry", "K", "C0", "mature", "realized_r"])
    t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)]
    bad = {(r.ticker, r.E) for r in pub[(pub.era == era)].itertuples() if (r.ticker, r.gap_date) in sus} | {(tk, e) for tk, e in zip(t.ticker, t.E) if tk in etn}
    keep = t[[(tk, e) not in bad for tk, e in zip(t.ticker, t.E)]]
    print(f"{era} published C0 (n {len(t):,}): suspect trades {len(t) - len(keep)}; mean R {t.realized_r.mean():+.4f} -> {keep.realized_r.mean():+.4f}; "
          f">=10R per 100 {100*(t.realized_r >= 10).mean():.3f} -> {100*(keep.realized_r >= 10).mean():.3f}")
for era, tf in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre/out/trail_r1_2017-21.tsv.gz"), ("2022-24", "/Users/alvinfung/apollo_data/cb702/out/trail_r1_2022-24.tsv.gz")):
    t = pd.read_csv(tf, sep="\t", low_memory=False, usecols=["cell", "attempt", "ticker", "entry_date", "realized_r", "complete120"])
    t = t[t.cell.isin(["A20_X1_P1", "A20_X3_P0"]) & (t.attempt == 0)]
    rr = r1[r1.era == era]
    bad = {(r.cell, r.ticker, r.entry) for r in rr.itertuples() if (r.ticker, r.gap_date) in sus} | {(c, tk, e) for c, tk, e in zip(t.cell, t.ticker, t.entry_date) if tk in etn}
    for cell, g in t.groupby("cell"):
        keep = g[[(cell, tk, e) not in bad for tk, e in zip(g.ticker, g.entry_date)]]
        print(f"{era} R1 {cell} first trades (n {len(g):,}): suspect {len(g) - len(keep)}; mean R {g.realized_r.mean():+.4f} -> {keep.realized_r.mean():+.4f}; "
              f"worst {g.realized_r.min():+.1f} -> {keep.realized_r.min():+.1f} R; >=10R per 100 {100*(g.realized_r >= 10).mean():.2f} -> {100*(keep.realized_r >= 10).mean():.2f}")
