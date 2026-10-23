#!/usr/bin/env python3
"""#705 breakout definition, step 1: REPRODUCE the population and the joins the read stands on. Reads NOTHING after 2024-12-31.
(a) the published C0 / tl / ORH5 / pp MATURE row (13,363 / 8,984) from the exitpb tables and yesterday's per-fill table;
(b) the watch row (pivot_full = the base high at D, adr20) joins 1:1 onto every fill;
(c) the entry tables' ORH5 filled / C0 / retrigger = 0 rows per K (the K-variant populations), and that K = tl equals the population."""
import pandas as pd, numpy as np
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_breakout_definition_1022/01_reproduce.txt"
ERAS = {
    "2017-21": dict(trades="/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz",
                    fills="/Users/alvinfung/apollo_data/cb702_pre/out/r_decomp_fills_2017-21.tsv.gz",
                    watch="/Users/alvinfung/apollo_data/cb702_pre/out/watch_tl_com.tsv.gz",
                    entries="/Users/alvinfung/apollo_data/cb702_pre/out/entries_pre_tl_com.tsv.gz", pub=(13368, 13363, 0.0254, 165)),
    "2022-24": dict(trades="/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz",
                    fills="/Users/alvinfung/apollo_data/cb702/out/r_decomp_fills_2022-24.tsv.gz",
                    watch="/Users/alvinfung/apollo_data/cb702/out/watch.tsv.gz",
                    entries="/Users/alvinfung/apollo_data/cb702/out/entries_discovery.tsv.gz", pub=(8989, 8984, -0.1691, 85)),
}
L = []
def p(s): print(s); L.append(s)
for era, c in ERAS.items():
    p(f"== {era}")
    t = pd.read_csv(c["trades"], sep="\t", low_memory=False)
    pop = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1)]
    m = pop[pop.mature == 1]
    r = m.realized_r.astype(float)
    ok = len(pop) == c["pub"][0] and len(m) == c["pub"][1] and abs(r.mean() - c["pub"][2]) < 5e-4 and int((r >= 10).sum()) == c["pub"][3]
    p(f"  population pp/orh5/tl/C0: {len(pop)} fills, {len(m)} mature, mean R {r.mean():.4f}, >=10R {int((r>=10).sum())} -> {'MATCH' if ok else 'MISMATCH'} vs published {c['pub']}")
    p(f"  duplicates in the population: (ticker, D) {int(m.duplicated(['ticker','D']).sum())}, (ticker, E) {int(m.duplicated(['ticker','E']).sum())}; retrigger_chain = 1 rows {int((m.retrigger_chain==1).sum())}")
    f = pd.read_csv(c["fills"], sep="\t", low_memory=False)
    j = f.merge(m[["ticker", "D", "E", "realized_r"]], on=["ticker", "D", "E"], how="inner")
    p(f"  yesterday's per-fill table: {len(f)} rows, all in the population: {len(j) == len(f)}; realized_r equal: {bool(np.allclose(j.realized_r_x, j.realized_r_y))}")
    w = pd.read_csv(c["watch"], sep="\t", usecols=["ticker", "watch_date", "pivot_full", "pivot_tl", "pivot_k5", "pivot_k10", "adr20", "close", "pole_high", "base_low", "base_len"])
    p(f"  watch rows {len(w):,}, duplicate (ticker, watch_date): {int(w.duplicated(['ticker','watch_date']).sum())}")
    jw = f.merge(w, left_on=["ticker", "D"], right_on=["ticker", "watch_date"], how="left", suffixes=("", "_w"))
    p(f"  fills without a watch row: {int(jw.pivot_full.isna().sum())}; watch adr20 == table adr20 within 1e-5 relative (yesterday's table is 6-digit text): {int((((jw.adr20 - jw.adr20_w).abs() / jw.adr20_w) < 1e-5).sum())} of {len(jw)}")
    p(f"  pivot_full >= pivot_tl on every fill: {bool((jw.pivot_full >= jw.pivot_tl).all())}; pivot_full >= pivot_k10 >= pivot_k5: {bool(((jw.pivot_full >= jw.pivot_k10) & (jw.pivot_k10 >= jw.pivot_k5)).all())}")
    p(f"  fill vs base high: fill >= pivot_full on {int((jw.fill >= jw.pivot_full).sum())} ({100*(jw.fill >= jw.pivot_full).mean():.1f}%); E's close > pivot_full on {int((jw.c_E > jw.pivot_full).sum())} ({100*(jw.c_E > jw.pivot_full).mean():.1f}%)")
    dist = (jw.pivot_full - jw.fill) / (jw.adr20 * jw.fill)
    p(f"  distance below base high (ADR20_D): quartiles {np.percentile(dist, [25,50,75]).round(3).tolist()}, mean {dist.mean():.3f}, p10/p90 {np.percentile(dist,[10,90]).round(3).tolist()}")
    e = pd.read_csv(c["entries"], sep="\t", low_memory=False)
    fe = e[(e.variant == "orh5") & (e.status == "filled") & (e.C0 == 1) & (e.retrigger == 0)]
    p(f"  entry table K values: {sorted(e.K.unique())}; ORH5 filled C0 retrigger=0 per K: {fe.groupby('K').size().to_dict()}")
    tl = fe[fe.K == "tl"]
    mm = m[["ticker", "D", "E"]].merge(tl[["ticker", "D", "E", "fill", "stop"]], on=["ticker", "D", "E"], how="outer", indicator=True)
    p(f"  K = tl rows vs the population: {mm._merge.value_counts().to_dict()}")
    p(f"  fill equal between entry table and trades table: {bool(np.allclose(m.merge(tl, on=['ticker','D','E']).fill_x, m.merge(tl, on=['ticker','D','E']).fill_y))}")
    for K in sorted(fe.K.unique()):
        g = fe[fe.K == K]
        p(f"    K = {K}: n {len(g)}, duplicate (ticker, E) {int(g.duplicated(['ticker','E']).sum())}, E range {g.E.min()}..{g.E.max()}, bases shared with tl (ticker, D): {int(g[['ticker','D']].merge(tl[['ticker','D']]).shape[0])}")
open(OUT, "w").write("\n".join(L) + "\n")
