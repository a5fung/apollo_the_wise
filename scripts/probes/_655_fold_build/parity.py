"""#655 fold build — parity: the engine's PURE planner (theme_engine.plan_small_theme_folds) vs the
scope's replay (scripts/probes/_655_scope/a4_fold.py --min505 -> a4_fold_fail_majority_min505.log) on
the same 10 captured nights, same inputs (stored G3 verdicts as the fail set, the capture's closes /
ecosystem map / industries). No guards (exclusions, cooldowns, protected, renames: none in the
replay). $0, offline. PRE-STATED: parity = the same (night, theme, home, passing members) set.
Run from the repo root: PYTHONPATH=. python scripts/probes/_655_fold_build/parity.py"""
import ast
import os
import re
import sys
from pathlib import Path

SCOPE = Path(__file__).resolve().parents[1] / "_655_scope"
sys.path.insert(0, str(SCOPE))
os.chdir(SCOPE)
from board import B, NIGHTS, STORED, ordered_board, g3_inputs  # noqa: E402
from agents.market_intelligence import theme_engine as te  # noqa: E402

eco = B["eco"]
ind = {t: (v.get("industry") or None) for t, v in B["industry"].items()}

mine = set()
for d in NIGHTS:
    board, _, _ = ordered_board(d)
    excess, usable, *_ = g3_inputs(d)
    fail = {t["name"] for t in STORED[d]["g3"]["themes"] if t["pass_g3"] is False}
    bd = [{"name": t["name"], "stage": t["stage"], "tickers": list(t["tickers"]),
           "description": t.get("desc")} for t in board]
    ctx = te.ComoveContext(before_date=d, excess=excess, n_sessions=0, n_rows=0)
    folds, counts = te.plan_small_theme_folds(bd, fail, ctx, usable, eco, ind)
    for f in folds:
        mine.add((str(d), f.theme, f.home, tuple(sorted(f.moved + f.already_in_home))))
    print(d, counts)

theirs = set()
pat = re.compile(r"^(\S+) \| (.+) \((\d), [^)]*\) -> (.+) \| moved (\[.*\])$")
for ln in open(SCOPE / "a4_fold_fail_majority_min505.log"):
    m = pat.match(ln.strip())
    if m:
        theirs.add((m[1], m[2], m[4], tuple(sorted(ast.literal_eval(m[5])))))
print(f"replay folds {len(theirs)} | planner folds {len(mine)} | identical {len(mine & theirs)}")
print("only replay:", sorted(theirs - mine))
print("only planner:", sorted(mine - theirs))
