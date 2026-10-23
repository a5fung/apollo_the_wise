#!/usr/bin/env python3
"""Main-loop adversarial checks (own code, no builder import), from the raw export and the bdef_* tables:
(1) pivot_full in the watch row == the max high over (P, D] in the export (the base high is what the doc says it is);
(2) s_c, the R2 flags and the >= 5 ADR share recomputed row by row from the raw bars on random samples (seed 702);
(3) the matched-control difference for R2 2017-21 at >= 5 ADR recomputed with a merge (not the builder's join path);
(4) the R1 table carries exactly one set of cl_* columns (the defect found on the first build)."""
import gzip, numpy as np, pandas as pd
rng = np.random.default_rng(702)
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_breakout_definition_1022/04_main_loop_checks.txt"
L = []
def p(s): print(s); L.append(s)
for era, data, watchf in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre", "watch_tl_com.tsv.gz"), ("2022-24", "/Users/alvinfung/apollo_data/cb702", "watch.tsv.gz")):
    ex = pd.read_csv(f"{data}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], keep_default_na=False)
    if era == "2022-24":
        ex = ex[ex.date <= "2024-12-31"]; assert ex.date.max() <= "2024-12-31"
    cal = sorted(ex[ex.ticker == "SPY"].date); cidx = {d: i for i, d in enumerate(cal)}
    f = pd.read_csv(f"{data}/out/bdef_fills_{era}.tsv.gz", sep="\t", low_memory=False)
    r = pd.read_csv(f"{data}/out/bdef_r1_{era}.tsv.gz", sep="\t", low_memory=False)
    w = pd.read_csv(f"{data}/out/{watchf}", sep="\t", usecols=["ticker", "watch_date", "pivot_full", "pole_date"])
    hdr = gzip.open(f"{data}/out/bdef_r1_{era}.tsv.gz", "rt").readline().rstrip("\n").split("\t")
    p(f"== {era}: R1 table cl_ columns {sum(c.startswith('cl_') for c in hdr)} (one set = 13), duplicates {len(hdr) - len(set(hdr))}")
    # (1) pivot_full == max high over (P, D]
    s = f.sample(300, random_state=702)
    bad = 0
    for _, row in s.iterrows():
        bars = ex[(ex.ticker == row.ticker)].set_index("date")
        wr = w[(w.ticker == row.ticker) & (w.watch_date == row.D)].iloc[0]
        seg = bars[(bars.index > wr.pole_date) & (bars.index <= row.D)].h
        if abs(seg.max() - row.pivot_full) > 1e-4 * row.pivot_full:
            bad += 1
    p(f"  (1) pivot_full == max high over (P, D] on 300 random fills: mismatches {bad}")
    # (2) s_c and the +5 ADR share from raw bars; the R2 flags from raw bars
    bad_sc = bad_ge5 = 0
    for _, row in s.iterrows():
        bars = ex[ex.ticker == row.ticker].set_index("date").reindex(cal)
        e = cidx[row.E]
        seg = bars.c.iloc[e: e + 61].to_numpy()
        hit = np.where(seg > row.pivot_full)[0]; sc = int(hit[0]) if hit.size else -1
        if sc != row.s_c: bad_sc += 1
        if e + 60 < len(cal):
            mfe = np.nanmax(bars.h.iloc[e + 1: e + 61].to_numpy()); ge5 = (mfe - row.c_E) / (row.adr20 * row.c_E) >= 5
            if int(ge5) != int(row.cl_mfe60 >= 5): bad_ge5 += 1
    p(f"  (2a) s_c recomputed from raw closes on 300 fills: mismatches {bad_sc}; >= 5 ADR from E close: mismatches {bad_ge5}")
    rs = r.sample(300, random_state=702); bad_r2 = bad_ge5 = 0
    for _, row in rs.iterrows():
        bars = ex[ex.ticker == row.ticker].set_index("date").reindex(cal)
        t = cidx[row.entry_date]; b = bars.iloc[t]; prev = bars.iloc[t - 20: t]
        adr = float(((prev.h - prev.l) / prev.c).mean()); vol50 = float(bars.v.iloc[t - 50: t].mean())
        rng_ok = (b.h - b.l) / b.c >= 1.0 * adr; loc_ok = b.h > b.l and (b.c - b.l) / (b.h - b.l) >= 0.70; vol_ok = b.v >= 1.5 * vol50
        exp = int(rng_ok and loc_ok and vol_ok)
        if abs(adr - row.adr_t1) > 1e-6 or exp != row.r2_exp: bad_r2 += 1
        if t + 60 < len(cal):
            mfe = np.nanmax(bars.h.iloc[t + 1: t + 61].to_numpy()); ge5 = (mfe - b.c) / (adr * b.c) >= 5
            if int(ge5) != int(row.cl_mfe60 >= 5): bad_ge5 += 1
    p(f"  (2b) ADR20 at t-1 and the R2 flag recomputed from raw bars on 300 R1 rows: mismatches {bad_r2}; >= 5 ADR from the R1 close: mismatches {bad_ge5}")
    # (3) R2 matched control at >= 5 ADR via a merge
    ctl = pd.read_csv(f"{data}/out/bdef_control_{era}.tsv.gz", sep="\t", usecols=["t", "adr20", "ret63", "cl_mfe60", "cl_c60", "cl_first5", "cl_c5"])
    r2 = r[(r.r2_exp == 1)].copy()
    dec = np.percentile(r2.adr_t1, range(10, 100, 10)); rq = np.percentile(r2.ret63_t1.dropna(), [20, 40, 60, 80])
    r2["dec"] = np.searchsorted(dec, r2.adr_t1); r2["q"] = np.searchsorted(rq, r2.ret63_t1.fillna(-9))
    ctl["dec"] = np.searchsorted(dec, ctl.adr20); ctl["q"] = np.searchsorted(rq, ctl.ret63.fillna(-9))
    c60 = ctl[ctl.cl_c60 == 1]; c60 = c60.assign(ge5=(c60.cl_mfe60 >= 5).astype(float))
    cell = c60.groupby(["t", "dec", "q"]).ge5.mean().rename("ctl").reset_index()
    cell2 = c60.groupby(["t", "dec"]).ge5.mean().rename("ctl2").reset_index()
    r2 = r2.drop(columns=["t"]).rename(columns={"entry_date": "t"})   # the table's `t` is the calendar index; the date is `entry_date`
    m = r2[r2.cl_c60 == 1].merge(cell, on=["t", "dec", "q"], how="left")
    m = m.merge(cell2, on=["t", "dec"], how="left"); m["ctl"] = m.ctl.fillna(m.ctl2)
    m["ge5"] = (m.cl_mfe60 >= 5).astype(float)
    p(f"  (3) R2 >= 5 ADR within 60, finer match via merge: n = {len(m)}, entries {100*m.ge5.mean():.2f}%, control {100*m.ctl.mean():.2f}%, difference {100*(m.ge5 - m.ctl).mean():+.2f} pts (report: 2017-21 +3.02 / 2022-24 +0.85)")
    c5 = ctl[ctl.cl_c5 == 1]; c5 = c5.assign(by5=((c5.cl_first5 >= 1) & (c5.cl_first5 <= 5)).astype(float))
    cell = c5.groupby(["t", "dec", "q"]).by5.mean().rename("ctl").reset_index()
    m = r2[r2.cl_c5 == 1].merge(cell, on=["t", "dec", "q"], how="left")
    m["by5"] = ((m.cl_first5 >= 1) & (m.cl_first5 <= 5)).astype(float)
    p(f"      R2 reaching +5 ADR by session 5: n = {int(m.ctl.notna().sum())}, entries {100*m.by5[m.ctl.notna()].mean():.2f}%, control {100*m.ctl.mean():.2f}% (report: 4.63 vs 2.28 / 3.83 vs 2.12)")
open(OUT, "w").write("\n".join(L) + "\n")
