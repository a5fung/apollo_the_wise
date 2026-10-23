"""Main-loop check after the verifiers (2026-10-22): is the expansion breakout's (R2) extra up-move matched by an extra DOWN-move?
Entries vs controls on the SAME entry day, matched on ADR20 decile x 63-session-return quintile (cuts on the R1 rows), from the entry
close: the share reaching +5 ADR up (cl_mfe60) and -3 / -5 ADR down (cl_mae60) within 60 sessions, and the mean 60-session return."""
import numpy as np, pandas as pd
D = {"2017-21": "/Users/alvinfung/apollo_data/cb702_pre/out/bdef_{}_2017-21.tsv.gz", "2022-24": "/Users/alvinfung/apollo_data/cb702/out/bdef_{}_2022-24.tsv.gz"}
for era, pat in D.items():
    r = pd.read_csv(pat.format("r1"), sep="\t", usecols=["ticker", "entry_date", "adr_t1", "ret63_t1", "r2_exp", "cl_c60", "cl_mfe60", "cl_mae60", "cl_ret60"], low_memory=False)
    r = r[(r.cl_c60 == 1) & r.entry_date.notna()].drop_duplicates(["ticker", "entry_date"]); r["t"] = r.entry_date.astype(str)
    c = pd.read_csv(pat.format("control"), sep="\t", usecols=["t", "adr20", "ret63", "cl_c60", "cl_mfe60", "cl_mae60", "cl_ret60"])
    c = c[c.cl_c60 == 1].copy(); c["t"] = c.t.astype(str)
    dq = np.quantile(r.adr_t1.dropna(), np.linspace(.1, .9, 9)); rq = np.quantile(r.ret63_t1.dropna(), [.2, .4, .6, .8])
    r["cell"] = list(zip(r.t, np.searchsorted(dq, r.adr_t1), np.searchsorted(rq, r.ret63_t1)))
    c["cell"] = list(zip(c.t, np.searchsorted(dq, c.adr20), np.searchsorted(rq, c.ret63)))
    for nm, f in (("up5", lambda x: x.cl_mfe60 >= 5), ("dn3", lambda x: x.cl_mae60 <= -3), ("dn5", lambda x: x.cl_mae60 <= -5), ("ret60", lambda x: x.cl_ret60)):
        c[nm] = f(c).astype(float); r[nm] = f(r).astype(float)
    cm = c.groupby("cell")[["up5", "dn3", "dn5", "ret60"]].mean()
    for lab, g in (("R2 expansion", r[r.r2_exp == 1]), ("R1 not R2", r[r.r2_exp != 1])):
        m = g.join(cm, on="cell", rsuffix="_c").dropna(subset=["up5_c"])
        print(f"{era} {lab} n = {len(m):,}: up +5 ADR {m.up5.mean():.1%} vs {m.up5_c.mean():.1%} | down -3 ADR {m.dn3.mean():.1%} vs {m.dn3_c.mean():.1%} "
              f"| down -5 ADR {m.dn5.mean():.1%} vs {m.dn5_c.mean():.1%} | mean 60-session return {m.ret60.mean():+.2f} vs {m.ret60_c.mean():+.2f} ADR")
