#!/usr/bin/env python3
"""STARTING POINT (his 11-02 method): the loosest list that holds Qullamaggie's 269 dated breakout buys the night before,
and how many names a night it holds. Post hoc on the captured feature table (10_feature_table.py). Also the parity check:
v1's own rules (without today's two floors, which postdate the frozen files) must reproduce the frozen list files exactly."""
import gzip, csv, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = "/Users/alvinfung/apollo_data/qm_breakouts_1102"
LOG = []
def say(s=""): print(s, flush=True); LOG.append(str(s))

F = pd.concat([pd.read_parquet(f"{OUTDIR}/features_era{e}.parquet") for e in "AB"], ignore_index=True)
F = F[F.get("gate_error").isna()] if "gate_error" in F else F
nights = F.scan_date.nunique()
say(f"feature rows {len(F):,} over {nights} nights ({len(F) / nights:.0f} listable names a night with strength >= 30)")

# parity: v1 without the 11-02 floors == the frozen list files
shape = ["history", "universe", "rs", "prior_move", "higher_lows", "surf", "tightening", "breakdown"]
v1_nofloor = F[[f"pass_{g}" for g in shape]].all(axis=1)
mine = set(zip(F.ticker[v1_nofloor], F.scan_date[v1_nofloor]))
frozen = set()
for e in "AB":
    with gzip.open(f"/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/out/list_era{e}.tsv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            frozen.add((r["ticker"], r["scan_date"]))
say(f"PARITY v1 (no floors) vs frozen list files: mine {len(mine):,} frozen {len(frozen):,} both {len(mine & frozen):,} "
    f"only-mine {len(mine - frozen)} only-frozen {len(frozen - mine)}")

# his buys
Q = pd.read_csv(f"{HERE}/qm_breakouts_v1_gates.tsv.gz", sep="\t")
key = dict(zip(zip(F.ticker, F.scan_date), F.index))
Q["row"] = [key.get((t, d)) for t, d in zip(Q.ticker, Q.D)]
say(f"his 269 buys found in the table: {int(Q.row.notna().sum())}")
t = pd.read_csv("/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t")
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")]
Q["big"] = Q.eid.isin(set(w[w.realized_r >= 5].eid))
H = F.loc[Q.row.dropna().astype(int)]
say(f"his buys: strength rank lowest {H.rs_best.min():.1f}; daily range lowest {H.adr20.min():.2%}")


def report(name, mask):
    n = mask.groupby(F.scan_date).sum()
    hit = mask.loc[Q.row.dropna().astype(int)].values
    big = mask.loc[Q.row[Q.big].dropna().astype(int)].values
    say(f"  {name:62s} his buys {int(hit.sum()):3d}/269 | big winners {int(big.sum())}/{int(Q.big.sum())} | "
        f"names a night: median {n.median():.0f}, mean {n.mean():.0f}, 90th pct {n.quantile(.9):.0f}")
    return mask

base = F.pass_history.astype(bool) & F.pass_universe.astype(bool)
say("\nlists (each row = the rules kept on; everything else off):")
report("v1 today (strength 98 + floors + all shape rules)", F.ok_v1.astype(bool))
report("v1 rules without the two 11-02 floors", v1_nofloor)
S0 = report("STARTING POINT: strength >= 35, range >= 2.1%, prior move kept", base & (F.rs_best >= 35) & (F.adr20 >= 0.021) & F.pass_prior_move.astype(bool))
report("  + breakdown rule", S0 & F.pass_breakdown.astype(bool))
report("  strength >= 70 instead of 35", base & (F.rs_best >= 70) & (F.adr20 >= 0.021) & F.pass_prior_move.astype(bool))
report("  strength >= 90 instead of 35", base & (F.rs_best >= 90) & (F.adr20 >= 0.021) & F.pass_prior_move.astype(bool))
report("  range >= 4.26% (today's floor) instead of 2.1%", base & (F.rs_best >= 35) & (F.adr20 >= 0.0426) & F.pass_prior_move.astype(bool))
open(f"{HERE}/11_starting_point.txt", "w").write("\n".join(LOG) + "\n")
