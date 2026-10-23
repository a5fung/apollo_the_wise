"""Main-loop checks after the two verifiers (2026-10-22), from the builder's per-fill and control tables (no builder code):
(1) the stop-survivor view and the timing of the big moves; (2) the 5-session matched control (not in the generated tables)."""
import pandas as pd, numpy as np
CUTS = {"2017-21": [0.025, 0.0298, 0.0336, 0.0374, 0.0412, 0.0455, 0.0511, 0.0593, 0.0744],
        "2022-24": [0.0241, 0.0286, 0.0326, 0.0361, 0.0403, 0.0454, 0.0513, 0.0589, 0.0718]}
F = {"2017-21": ("/Users/alvinfung/apollo_data/cb702_pre/out/r_decomp_fills_2017-21.tsv.gz", "/Users/alvinfung/apollo_data/cb702_pre/out/r_decomp_control_2017-21.tsv.gz"),
     "2022-24": ("/Users/alvinfung/apollo_data/cb702/out/r_decomp_fills_2022-24.tsv.gz", "/Users/alvinfung/apollo_data/cb702/out/r_decomp_control_2022-24.tsv.gz")}
for era, (ff, cf) in F.items():
    d = pd.read_csv(ff, sep="\t", low_memory=False)
    d60 = d[d.complete_60 == 1]
    for T, col in ((5, "first_5adr"), (10, "first_10adr")):
        bm = d60[(d60[col] >= 1) & (d60[col] <= 60)]; s = bm[col]
        stopx = bm.exit_kind.isin(["stop", "day0_stop", "stop_gap", "day0_gap"]) & bm.partial_kind.isna()
        out = (bm.exit_session < s) | ((bm.exit_session == s) & bm.exit_kind.str.contains("stop", na=False))
        B = out & stopx; C = (out & ~stopx) | (~out & (bm.pnl_adr < T / 2)); D = ~out & (bm.pnl_adr >= T / 2); surv = ~B
        print(f"{era} +{T} ADR: big movers {len(bm):,}; B {B.sum()} C {C.sum()} D {D.sum()}; of the {surv.sum():,} the stop did not take, "
              f"the exit lost {C[surv].mean():.1%}; the move starts a median {s.median():.0f} sessions after the fill; stop survivors held a "
              f"median {bm.sessions_held[surv].median():.0f} sessions; all fills held a median {d60.sessions_held.median():.0f}")
    f = d[d.complete_5 == 1][["E", "adr20", "ret5_adr_close", "fill_month"]].copy()
    c = pd.read_csv(cf, sep="\t", usecols=["E", "adr20", "complete_5", "ret5_adr_close"]); c = c[c.complete_5 == 1]
    f["dec"] = np.searchsorted(CUTS[era], f.adr20, side="right"); c["dec"] = np.searchsorted(CUTS[era], c.adr20, side="right")
    m = f.join(c.groupby(["E", "dec"]).ret5_adr_close.mean().rename("ctl"), on=["E", "dec"]).dropna(subset=["ctl"])
    m["diff"] = m.ret5_adr_close - m.ctl
    rng = np.random.default_rng(702); months = m.fill_month.unique(); g = m.groupby("fill_month")["diff"].agg(["sum", "count"])
    bs = [(lambda s: s["sum"].sum() / s["count"].sum())(g.loc[rng.choice(months, len(months))]) for _ in range(2000)]
    print(f"{era}: 5-session close return from E close (ADR decile match), n = {len(m):,}: breakouts {m.ret5_adr_close.mean():+.3f} vs control "
          f"{m.ctl.mean():+.3f}, difference {m['diff'].mean():+.3f} [{np.percentile(bs, 2.5):+.3f}, {np.percentile(bs, 97.5):+.3f}]")
