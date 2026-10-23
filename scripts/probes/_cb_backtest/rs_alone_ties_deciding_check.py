"""Independent count (no runner code): for the RS-alone rule on the two DECIDING eras (already read), how many fills sit exactly at
their cutoff member's rs_best value, and how many A+ the rule produces — to compare with the sealed era's dry run (172 A+, 47 ties).
Calendar = the distinct fill dates of the era's table (an approximation to the SPY calendar; validated by reproducing the A+ count)."""
import numpy as np, pandas as pd, datetime as dt
for era, f, want in (("2017-21", "/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_aplus.tsv.gz", 510),
                     ("2022-24", "/Users/alvinfung/apollo_data/cb702/out/trades_discovery_aplus.tsv.gz", 289)):
    d = pd.read_csv(f, sep="\t", usecols=["ticker", "E", "fill_minute", "eligible", "rs_best", "week"], low_memory=False)
    d = d[d.eligible == 1].copy() if d.eligible.dtype != bool else d[d.eligible].copy()
    cal = sorted(d.E.unique()); si = {e: k for k, e in enumerate(cal)}
    d["s"] = d.E.map(si); d = d.sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    by_s = {s: g.rs_best.dropna().to_numpy() for s, g in d.groupby("s")}
    aplus_cand = np.zeros(len(d), bool); tie = np.zeros(len(d), bool); rated = np.zeros(len(d), bool)
    for i, r in enumerate(d.itertuples()):
        S = np.concatenate([by_s.get(k, np.empty(0)) for k in range(r.s - 20, r.s)])
        if len(S) < 31 or np.isnan(r.rs_best): continue          # pool floor 30 on the member's pool-minus-itself, 12 members
        n = len(S); Sd = np.sort(S)[::-1]; u = Sd[11]
        ref = (np.sum(S < u) + 0.5 * (np.sum(S == u) - 1)) / (n - 1)
        sc = (np.sum(S < r.rs_best) + 0.5 * np.sum(S == r.rs_best)) / n
        rated[i] = True; aplus_cand[i] = sc >= ref; tie[i] = r.rs_best == u
    taken = {}; aplus = np.zeros(len(d), bool)
    for i in np.where(aplus_cand)[0]:
        w = d.week.iat[i]
        if taken.get(w, 0) < 3: aplus[i] = True; taken[w] = taken.get(w, 0) + 1
    print(f"{era}: rated {rated.sum():,}; A+ {aplus.sum()} (the read's filled {want}); ties at the cutoff {tie.sum()} "
          f"({(tie & ~aplus_cand).sum()} below the cutoff, {(tie & aplus).sum()} A+); ties per 1,000 rated {1000*tie.sum()/rated.sum():.1f}")
