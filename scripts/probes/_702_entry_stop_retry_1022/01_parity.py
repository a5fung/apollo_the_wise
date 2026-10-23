"""#705 entry/stop/retry — step 1: PARITY of the lockstep `pp` walker against the PUBLISHED pp rows (trades_*_exitpb, arm pp, tl, orh5,
C0, mature), before any grid number is read. Rows with a day-0 stop or a day-0 third are excluded (the published day 0 ran on minutes);
the rest are re-walked from session 1 off the published fill and stop, the day-0 reach read from E's daily high (a proxy for the minute
high after the fill — the one known source of residual mismatch). Compares realized_r (1e-6) and exit_session. Writes 01_parity.txt."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022")
from esr_lib import Frame, ERAS, walk, log, STALL_R

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_entry_stop_retry_1022"
sink = []
for era in (sys.argv[1:] or list(ERAS)):
    cfg = ERAS[era]
    log(f"== {era}", sink)
    F = Frame(cfg["data"], cfg["cut"], sink)
    tr = pd.read_csv(f"{cfg['data']}/{cfg['trades']}", sep="\t", low_memory=False)
    p = tr[(tr.arm == "pp") & (tr.K == "tl") & (tr.entry == "orh5") & (tr.C0 == 1) & (tr.mature == 1)].copy()
    log(f"  published pp rows: {len(p)}; fill_day_stop {int(p.fill_day_stop.sum())}; day-0 third {int((p.partial_session == 0).sum())}", sink)
    p = p[(p.fill_day_stop == 0) & (p.partial_session.fillna(-1) != 0)].copy()
    p["ci"] = p.E.map(F.cidx); p["tj"] = p.ticker.map(F.tpos)
    p = p[p.ci.notna() & p.tj.notna()].copy(); p["ci"] = p.ci.astype(int); p["tj"] = p.tj.astype(int)
    # the published exit must sit inside the readable bars (2022-24 published walks ran past the cut)
    p = p[(p.ci + p.exit_session + 1) <= F.last].copy()
    log(f"  parity set (no day-0 stop / third, exit inside the readable bars): n = {len(p)}", sink)
    ci, tj = p.ci.to_numpy(), p.tj.to_numpy()
    fill, stop = p.fill.to_numpy("float64"), p.stop.to_numpy("float64")
    hE = F.H[ci, tj].astype("float64")
    reached0 = hE >= fill + STALL_R * (fill - stop)
    w = walk(F, ci, tj, fill.astype("float32"), stop.astype("float32"), 1, reached0=reached0)
    p["my_r"] = w["realized_r"]; p["my_exit"] = w["exit_j"]; p["my_status"] = w["status"]; p["my_pkind"] = w["pkind"]
    dr = (p.my_r - p.realized_r).abs()
    ok_r = dr < 1e-3; ok_e = p.my_exit == p.exit_session
    log(f"  realized_r within 1e-3 (the published fill is 6-digit text on float32 bars; max abs diff {dr.max():.2e}, p99 {dr.quantile(0.99):.1e}): {int(ok_r.sum())} of {len(p)} ({100*ok_r.mean():.2f}%); exit_session equal: {int(ok_e.sum())} ({100*ok_e.mean():.2f}%)", sink)
    bad = p[~(ok_r & ok_e)]
    if len(bad):
        # classify: the day-0 reach proxy (a cut I take that the minutes did not, or vice versa)
        cut_mine = (bad.my_status == 2) & (bad.exit_kind != "cut")
        cut_pub = (bad.exit_kind == "cut") & (bad.my_status != 2)
        log(f"  mismatches {len(bad)}: I cut / published did not {int(cut_mine.sum())}; published cut / I did not {int(cut_pub.sum())}; other {int((~cut_mine & ~cut_pub).sum())}", sink)
        oth = bad[~cut_mine & ~cut_pub]
        if len(oth):
            log("  other mismatches (first 12):", sink)
            log(oth[["ticker", "E", "fill", "stop", "status", "exit_kind", "exit_session", "realized_r", "partial_kind", "partial_session", "my_status", "my_exit", "my_r", "my_pkind", "fwd_hole"]].head(12).to_string(), sink)
            log(f"  other mismatches by published exit_kind: {oth.exit_kind.value_counts().to_dict()}; by my status: {oth.my_status.value_counts().to_dict()}; fwd_hole among them {int(oth.fwd_hole.sum())}", sink)
    # by status / partial kind, the agreement
    for st, g in p.groupby("status"):
        log(f"    status {st}: n = {len(g)}, R match {100*((g.my_r-g.realized_r).abs()<1e-3).mean():.2f}%", sink)
    for pk, g in p.groupby(p.partial_kind.fillna("none")):
        log(f"    partial {pk}: n = {len(g)}, R match {100*((g.my_r-g.realized_r).abs()<1e-3).mean():.2f}%", sink)
    del F
open(f"{HERE}/01_parity.txt", "w").write("\n".join(sink) + "\n")
