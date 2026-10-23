#!/usr/bin/env python3
"""#702 R decomposition, step 1: REPRODUCE the published C0 / tl / ORH5 / pp row from the per-fill tables.
Published (exitpb_report_{pre,discovery}.tsv, row orh5 C0 tl pp all): 2017-21 n_filled 13,368 / n 13,363 / mean R +0.025 / >=10R 165;
2022-24 8,989 / 8,984 / -0.169 / 85. Reads NOTHING after 2024-12-31 (no holdout file opened)."""
import pandas as pd, numpy as np, sys
PRE = "/Users/alvinfung/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz"
DIS = "/Users/alvinfung/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz"
OUT = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_r_decomposition_1022/01_reproduce.txt"
lines = []
for era, path, pub in (("2017-21", PRE, (13368, 13363, 0.0254, 165)), ("2022-24", DIS, (8989, 8984, -0.1691, 85))):
    t = pd.read_csv(path, sep="\t", low_memory=False)
    lines.append(f"== {era}: {len(t)} rows; arms {sorted(t.arm.unique())}; entries {sorted(t.entry.unique())}; K {sorted(t.K.unique())}; status {sorted(t.status.unique())}")
    p = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1)]
    lines.append(f"  pp/orh5/tl/C0 rows {len(p)}; retrigger_chain values {p.retrigger_chain.value_counts().to_dict()}; row_no {p.row_no.value_counts().head(3).to_dict()}")
    filled = p[p.status.notna() & (p.status != "")]
    m = p[p.mature == 1]
    lines.append(f"  filled {len(filled)}  mature {len(m)}  open_mark {int((p.open_mark==1).sum())}  E range {p.E.min()}..{p.E.max()}")
    r = m.realized_r.astype(float)
    lines.append(f"  mean R {r.mean():.4f}  >=10R {int((r>=10).sum())}  >=5R {int((r>=5).sum())}  share>=10 {100*(r>=10).mean():.3f}/100  fill_day_stop share {m.fill_day_stop.mean():.4f}")
    lines.append(f"  PUBLISHED n_filled {pub[0]} n {pub[1]} meanR {pub[2]} ge10 {pub[3]} -> {'MATCH' if (len(p)==pub[0] and len(m)==pub[1] and abs(r.mean()-pub[2])<5e-4 and int((r>=10).sum())==pub[3]) else 'MISMATCH'}")
    lines.append(f"  status counts (mature): {m.status.value_counts().to_dict()}")
    lines.append(f"  exit_kind counts: {m.exit_kind.value_counts().to_dict()}")
    lines.append(f"  exit_session: min {m.exit_session.min()} max {m.exit_session.max()}; sessions_held min {m.sessions_held.min()} max {m.sessions_held.max()}; fwd_bars min {m.fwd_bars.min()}")
    lines.append(f"  width_adr quartiles {np.percentile(m.width_adr.astype(float),[25,50,75]).round(3).tolist()}; adr20 deciles {np.percentile(m.adr20.astype(float), range(10,100,10)).round(4).tolist()}")
    lines.append(f"  sample row: {m.iloc[0][['ticker','D','E','fill','stop','width_adr','adr20','status','realized_r','exit_kind','exit_px','exit_session','sessions_held','fill_day_stop','partial_kind','partial_session','fwd_bars']].to_dict()}")
    # the day-0 stop: relation between fill_day_stop and exit_session/sessions_held
    lines.append(f"  fill_day_stop==1: exit_session values {m[m.fill_day_stop==1].exit_session.value_counts().to_dict()} sessions_held {m[m.fill_day_stop==1].sessions_held.value_counts().head(3).to_dict()}")
    lines.append(f"  stopped (not day0): sessions_held - exit_session diff values {(m[m.status=='stopped'].sessions_held - m[m.status=='stopped'].exit_session).value_counts().head(3).to_dict()}")
    lines.append(f"  censored rows: {int((m.status=='censored').sum())} exit_session {m[m.status=='censored'].exit_session.value_counts().head(3).to_dict()} sessions_held {m[m.status=='censored'].sessions_held.value_counts().head(3).to_dict()}")
open(OUT, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
