#!/usr/bin/env python3
"""Stage 4 review - the 20 era-A 'file start' drops (prereg 1.3): which unscored flag fired and does the look-back reach before the file's
first date? Outcome-free: bars <= D only (the live context_gates re-called exactly as stage 1e did). Output -> r2_file_start.txt"""
import sys
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1de")
from lib import *
A2 = REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md"
assert sha256(A2) == "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b"
L = []
def P_(s=""):
    print(s, flush=True); L.append(str(s))
S = setup_store("A"); D = S.D
cal = [d.isoformat() for d in D.cal]
d = pd.read_parquet(OUT_DATA / "bws1124_eraA_list_ctx.parquet")
brk = d[(d.failed == "") & d.fire]
EV = pd.read_parquet(OUT_DATA / "bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker"])
sv = set(zip(EV.ci[EV.era == "A"], EV.ticker[EV.era == "A"]))
dropped = brk[[(c, t) not in sv for c, t in zip(brk.ci, brk.ticker)]]
P_(f"era-A live break rows {len(brk)}; not in the post-drop set {len(dropped)}")
rows = []
for r in dropped.itertuples():
    k = D.tid[r.ticker]; a, b = int(D.start[k]), int(D.stop[k])
    first_ci = int(D.ci[a])
    if first_ci > 5: continue
    bars, cidx = runner.bars_for(D, k); Di = int(np.searchsorted(cidx, r.ci))
    assert int(cidx[Di]) == r.ci
    cg = bv.context_gates(bars, Di, adr20=r.adr20)                      # reads bars <= D
    ll, dt = cg["lower_line"]["value"], cg["downtrend_6m"]["value"]
    uns = (ll["status"] == "insufficient_history", dt["ret126"] is None, dt["s50_chg10_adr"] is None)
    if not any(uns): continue
    sess = r.ci - first_ci + 1                                           # calendar sessions from the name's first bar to D
    nb = Di + 1                                                          # bars the name holds to D
    last_gap = int(np.max(np.diff(cidx[:Di + 1]))) if Di > 0 else 0
    run = 1
    j = Di
    while j > 0 and cidx[j] - cidx[j - 1] == 1: run += 1; j -= 1
    rows.append((r.ticker, cal[r.ci], first_ci, sess, nb, run, last_gap, ll["status"], int(ll["bars"]), *uns))
P_(f"rows with first bar within 5 sessions of the file start AND a check passed unscored: {len(rows)} (stage 1e printed 20)")
P_("ticker D first_ci sessions_first_bar_to_D bars_to_D consecutive_run_ending_D largest_hole ll_status ll_bars | unscored: lower_line ret126 chg10")
for x in sorted(rows, key=lambda x: (x[1], x[0])):
    P_("  " + " ".join(str(v) for v in x))
n_reach = sum(1 for x in rows if x[3] < 189)
P_(f"rows where the file start is inside the longest look-back (fewer than 189 calendar sessions from the file's first date to D): {n_reach} of {len(rows)}")
P_("reading: every one of these has its first bar in the file's first week YEARS before D; the check went unscored because of a HOLE in the name's bars (or a restart of the symbol), not because the file starts.")
(HERE.parent / "stage4_review/r2_file_start.txt").write_text("\n".join(L) + "\n")
