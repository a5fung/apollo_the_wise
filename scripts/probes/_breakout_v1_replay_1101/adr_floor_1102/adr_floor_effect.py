"""His 2026-11-02 ruling ("yes to both"): breakout v1's list gains a daily-range floor, ADR20 >= 4.26% (his own
reverse-engineered stock pool, docs/analysis/cb_reverse_engineer_his_rules_prereg_2026-10-24.md L814), so a pinned
deal target (BWMN, ARX, PCRX on 11-02) never lists. CHANGE_PROCESS backtest: the effect on the frozen paper-baseline
replay (out/trades.tsv.gz), both books, both eras, at 2c — computed BEFORE the code ships. Read-only."""
import sys, json
from pathlib import Path
import numpy as np
P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P)); sys.path.insert(0, str(P / "followup_tests_1101"))
import v1_replay as V
import followup as F

FLOOR = 0.0426
rows = F.load_placed()
sessions = sorted({t["E"] for t in rows})
def book(rs, slots):
    return V.apply_book(rs, slots=slots, safeguards=False, sessions=sessions)
def summary(name, admitted):
    for era in ("2017-21", "2022-24", None):
        tt = [t for t in admitted if t["filled"] and t["decisive"] and (era is None or t["era"] == era) and t["r_2c"] is not None]
        r = np.array([t["r_2c"] for t in tt]); n = len(r)
        if not n: print(f"  {name:28s} {era or 'all':8s} n 0"); continue
        print(f"  {name:28s} {era or 'all':8s} n {n:5d} mean {r.mean():+.3f} win {np.mean(r>0):.1%} 3R+ {np.mean(r>=3):.1%} 10R+/100 {100*np.mean(r>=10):.1f} sum {r.sum():+.0f}")
kept = [t for t in rows if t["adr20"] is not None and float(t["adr20"]) >= FLOOR]
print(f"placed name-days: {len(rows)}; with ADR20 >= 4.26%: {len(kept)} ({len(kept)/len(rows):.0%}); removed {len(rows)-len(kept)}")
lo = [t for t in rows if t["adr20"] is not None and float(t["adr20"]) < FLOOR and t["filled"] and t["decisive"] and t["r_2c"] is not None]
r = np.array([t["r_2c"] for t in lo]); print(f"the REMOVED filled decisive trades (no slot limit): n {len(r)} mean {r.mean():+.3f} 3R+ {np.mean(r>=3):.1%} 10R+ {int(np.sum(r>=10))}")
for label, rs in (("today (no floor)", rows), ("ADR20 >= 4.26%", kept)):
    for slots, bname in ((None, "no slot limit"), (V.CAP_SLOTS, "5 slots (paper)")):
        res = book([dict(t) for t in rs], slots)
        summary(f"{label} | {bname}", [t for t in rs if res["admitted"].get(t["key"])])
