"""VERIFIER: Monte-Carlo spread of D1's discovery p under #684's own perm_p, across seeds (read-only)."""
import sys, random
sys.dont_write_bytecode = True
from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_rows
import study
rows = load_rows()
study.add_outcomes(rows, study.load_daily())
disc = [r for r in rows if r["block"] == "DISCOVERY" and r.get("runner5") is not None]
lab = [int(r["runner5"]) for r in disc]; wk = [r["iso_week"] for r in disc]
for col in ("SC_ge9m",):
    fm = study.fav_mask(disc, col, "bool", "1", None)
    d = study.diff_stat(lab, fm)
    ps = []
    for s in (9016, 684, 1, 2, 3, 4, 5, 6, 7, 8):
        ps.append(study.perm_p(lab, fm, wk, d, random.Random(s)))
    print(col, "diff", round(d, 4), "p by seed", ps, "mean", round(sum(ps)/len(ps), 4))
    # 20,000-shuffle estimate
    study.N_PERM = 20000
    print("20k shuffles seed 9016:", study.perm_p(lab, fm, wk, d, random.Random(9016)))
