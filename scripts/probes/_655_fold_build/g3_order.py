"""#655 fold build — how much the engine's own G3 draw (board sorted by name in Python, the order the
fold uses) differs from the stored 17:31 verdicts (board in the DB's collation order) on the same 10
captured nights, same inputs. Only the RNG stream position per theme differs. $0, offline.
PRE-STATED: report verdicts identical / flipped over all judged theme-nights, and over the 2-3-member
ones, and how many fold decisions change when the fold reads the re-drawn verdicts.
Run from the repo root: PYTHONPATH=. python scripts/probes/_655_fold_build/g3_order.py"""
import os
import sys
from pathlib import Path

SCOPE = Path(__file__).resolve().parents[1] / "_655_scope"
sys.path.insert(0, str(SCOPE))
os.chdir(SCOPE)
from board import B, NIGHTS, STORED, ordered_board, g3, g3_inputs  # noqa: E402
from agents.market_intelligence import theme_engine as te  # noqa: E402

eco = B["eco"]
ind = {t: (v.get("industry") or None) for t, v in B["industry"].items()}
tot = same = small_tot = small_same = 0
fold_stored = fold_redrawn = 0
diff_folds = []
for d in NIGHTS:
    board, _, _ = ordered_board(d)
    st = {t["name"]: t["pass_g3"] for t in STORED[d]["g3"]["themes"]}
    by_name = sorted(board, key=lambda t: t["name"])
    r = {x["name"]: x["pass_g3"] for x in g3(by_name, d)["themes"]}
    for t in board:
        if st[t["name"]] is None:
            continue
        tot += 1
        same += r[t["name"]] == st[t["name"]]
        if 2 <= len(t["tickers"]) <= 3:
            small_tot += 1
            small_same += r[t["name"]] == st[t["name"]]
    excess, usable, *_ = g3_inputs(d)
    bd = [{"name": t["name"], "stage": t["stage"], "tickers": list(t["tickers"]),
           "description": t.get("desc")} for t in by_name]
    ctx = te.ComoveContext(before_date=d, excess=excess, n_sessions=0, n_rows=0)
    fa, _ = te.plan_small_theme_folds(bd, {n for n, v in st.items() if v is False}, ctx, usable, eco, ind)
    fb, _ = te.plan_small_theme_folds(bd, {n for n, v in r.items() if v is False}, ctx, usable, eco, ind)
    fold_stored += len(fa)
    fold_redrawn += len(fb)
    sa = {(f.theme, f.home) for f in fa}
    sb = {(f.theme, f.home) for f in fb}
    diff_folds += [(str(d), "stored only", x) for x in sorted(sa - sb)]
    diff_folds += [(str(d), "re-drawn only", x) for x in sorted(sb - sa)]
print(f"judged theme-nights {tot}: same verdict {same}, flipped {tot - same}")
print(f"2-3-member judged theme-nights {small_tot}: same {small_same}, flipped {small_tot - small_same}")
print(f"folds with stored verdicts {fold_stored} | with the name-order re-draw {fold_redrawn}")
for x in diff_folds:
    print(" ", x)
