"""His 10-22 challenge: "if 40% of breakouts make big gains ... if R is 2R then it'll be profitable". The number that decides it is how
often a trade reaches +kR BEFORE its own stop. Per published C0 tl ORH5 fill (2017-21, 2022-24; bars cut at 2024-12-31): R = fill - stop
(the trade's own low-of-day stop). Day 0: the published fill_day_stop -> stop first; else day 0's high >= fill + kR counts as a hit
(ORH5 fills early in the day; flagged). Sessions 1..60: first session whose low <= stop vs first whose high >= fill + kR; a session
with both is counted as STOP first (conservative) and counted. Neither within 60 = marked at the day-60 close, in R.
A fixed target-or-stop exit's expected R = P(hit) * k - P(stop) * 1 + the marked rest."""
import numpy as np, pandas as pd
ERAS = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre/out/r_decomp_fills_2017-21.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz"),
        "2022-24": ("/Users/alvinfung/apollo_data/cb702/out/r_decomp_fills_2022-24.tsv.gz", "/Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz")}
KS = (1, 2, 3, 5, 10)
for era, (ff, ef) in ERAS.items():
    f = pd.read_csv(ff, sep="\t", usecols=["ticker", "E", "fill", "stop", "fill_day_stop", "complete_60", "realized_r"], low_memory=False)
    f = f[f.complete_60 == 1].copy()
    ex = pd.read_csv(ef, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], usecols=[0, 1, 3, 4, 5])
    ex = ex[ex.date <= "2024-12-31"]; ex = ex[ex.ticker.isin(set(f.ticker))].sort_values(["ticker", "date"])
    g = {t: (d.date.to_numpy(), d.h.to_numpy(), d.l.to_numpy(), d.c.to_numpy()) for t, d in ex.groupby("ticker")}
    res = {k: {"hit": 0, "stop": 0, "both": 0, "open_r": [], "d0hit": 0} for k in KS}; n = 0
    for r in f.itertuples():
        if r.ticker not in g: continue
        dts, h, l, c = g[r.ticker]; i = np.searchsorted(dts, r.E)
        if i >= len(dts) or dts[i] != r.E or i + 60 >= len(dts): continue
        R = r.fill - r.stop
        if R <= 0: continue
        n += 1
        for k in KS:
            tgt = r.fill + k * R; o = res[k]
            if r.fill_day_stop == 1: o["stop"] += 1; continue
            if h[i] >= tgt: o["hit"] += 1; o["d0hit"] += 1; continue
            hh = h[i+1:i+61] >= tgt; ll = l[i+1:i+61] <= r.stop
            fh = np.argmax(hh) if hh.any() else 99; fl = np.argmax(ll) if ll.any() else 99
            if fh == 99 and fl == 99: o["open_r"].append((c[i+60] - r.fill) / R)
            elif fl <= fh:
                o["stop"] += 1; o["both"] += int(fl == fh)
            else: o["hit"] += 1
    print(f"{era}: n = {n:,} fills (complete 60-session windows); published mean R of these {f.realized_r.mean():+.3f}")
    for k in KS:
        o = res[k]; ph, ps = o["hit"] / n, o["stop"] / n; po = len(o["open_r"]) / n; mo = np.mean(o["open_r"]) if o["open_r"] else 0
        ev = ph * k - ps + po * mo
        print(f"  +{k}R before the stop: {ph:.1%} (break-even needs {1/(k+1):.1%}); stop first {ps:.1%} (same-session ties {o['both']}); "
              f"neither in 60 {po:.1%} (marked {mo:+.2f}R); day-0 hits {o['d0hit']} -> target-or-stop expected R {ev:+.3f}")
