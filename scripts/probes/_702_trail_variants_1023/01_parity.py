"""#705 Track B — step 1: PARITY of walk_v / walk_chain_v at the pp cell (SMA20, X1, P1) BEFORE any new arm is read.
(a) SMA20 rebuilt from the close frame equals esr_lib's F.SMA bit for bit; (b) walk_chain (esr_lib, read-only) vs walk_chain_v on the S2
close T2 chain for P-win, R1 and a 300,000-row control subsample — every shared column equal (NaN = NaN); (d) the published `pp` rows re-walked
through walk_v reproduce 01_parity.txt of the 10-22 read (7,334 / 7,335 and 4,905 / 4,905). (c) — the whole S2_close cell to the digit — is
asserted inside 02_build.py before the other 15 cells run. Writes 01_parity.txt."""
import sys, time
import numpy as np, pandas as pd
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_702_trail_variants_1023"
sys.path.insert(0, HERE)
from trail_lib import Frame, ERAS, walk_v, walk_chain_v, add_sma, load_pops, log, STALL_R
from esr_lib import walk, walk_chain

sink = []
ok_all = True
for era in (sys.argv[1:] or list(ERAS)):
    cfg = ERAS[era]
    log(f"== {era}", sink)
    F = Frame(cfg["data"], cfg["cut"], sink)
    # (a)
    sma20 = pd.DataFrame(F.C).rolling(20, min_periods=20).mean().to_numpy().astype("float32")
    eq = np.array_equal(sma20, F.SMA, equal_nan=True)
    log(f"  (a) SMA20 rebuilt from the close frame == F.SMA bit for bit: {eq}; SMA10 built the same way: finite cells {int(np.isfinite(add_sma(F, 10)).sum()):,} (SMA20 {int(np.isfinite(F.SMA).sum()):,})", sink)
    ok_all &= eq
    # (b)
    win, r1, ctl, cells = load_pops(era, F, sink)
    sub = ctl.sample(300000, random_state=1).sort_values("ci").reset_index(drop=True)
    for name, b, t, hi, lo in (("P-win", win.b_p, win.tj, win.base_high_p, win.base_low_p), ("R1", r1.t, r1.tj, r1.pivot_full, r1.base_low),
                               ("control subsample", sub.ci, sub.tj, sub.proxy_hi, sub.proxy_lo)):
        t0 = time.time()
        A = walk_chain(F, b.to_numpy(), t.to_numpy(), hi.to_numpy("float32"), lo.to_numpy("float32"), "S2", "close", 2, with_race=True)
        B = walk_chain_v(F, b.to_numpy(), t.to_numpy(), hi.to_numpy("float32"), lo.to_numpy("float32"), "S2", "close", 20, "X1", "P1", 2, with_race=True)
        shared = [c for c in A.columns if c in B.columns]
        same = A[shared].equals(B[shared])
        diffcols = [c for c in shared if not A[c].equals(B[c])]
        log(f"  (b) {name}: S2 close T2 chain, esr_lib.walk_chain vs walk_chain_v(20, X1, P1): rows {len(A)} vs {len(B)}; {len(shared)} shared columns equal (NaN = NaN): {same}{'' if same else '; differing ' + str(diffcols)}; {time.time()-t0:.0f}s", sink)
        ok_all &= same and len(A) == len(B)
    # (d)
    tr = pd.read_csv(f"{cfg['data']}/{cfg['trades']}", sep="\t", low_memory=False)
    p = tr[(tr.arm == "pp") & (tr.K == "tl") & (tr.entry == "orh5") & (tr.C0 == 1) & (tr.mature == 1)].copy()
    p = p[(p.fill_day_stop == 0) & (p.partial_session.fillna(-1) != 0)].copy()
    p["ci"] = p.E.map(F.cidx); p["tj"] = p.ticker.map(F.tpos)
    p = p[p.ci.notna() & p.tj.notna()].copy(); p["ci"] = p.ci.astype(int); p["tj"] = p.tj.astype(int)
    p = p[(p.ci + p.exit_session + 1) <= F.last].copy()
    ci, tj = p.ci.to_numpy(), p.tj.to_numpy()
    fill, stop = p.fill.to_numpy("float64"), p.stop.to_numpy("float64")
    reached0 = F.H[ci, tj].astype("float64") >= fill + STALL_R * (fill - stop)
    w = walk_v(F, ci, tj, fill.astype("float32"), stop.astype("float32"), 1, 20, "X1", "P1", reached0=reached0)
    dr = np.abs(w["realized_r"] - p.realized_r.to_numpy()); ok_r = dr < 1e-3; ok_e = w["exit_j"] == p.exit_session.to_numpy()
    log(f"  (d) published pp rows re-walked through walk_v: n = {len(p)}; realized_r within 1e-3: {int(ok_r.sum())}; exit_session equal: {int(ok_e.sum())} (10-22 read: {'7334 / 7335' if era == '2017-21' else '4905 / 4905'})", sink)
    ok_all &= (int((ok_r & ok_e).sum()) == (7334 if era == "2017-21" else 4905)) and len(p) == (7335 if era == "2017-21" else 4905)
    del F
log(f"PARITY {'PASS' if ok_all else 'FAIL'}", sink)
open(f"{HERE}/01_parity.txt", "w").write("\n".join(sink) + "\n")
sys.exit(0 if ok_all else 1)
