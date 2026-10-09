"""re-verify #694: the main table's 'alone' survival column counts at the LAST pre-open check, while baseline A is now
counted over the whole morning. Recount three standalone keys over EVERY pre-open check (v9_ticks_positive_days.out):
A->Z, gap (the logged rank_by_gap at that check) and RS composite at P (q08_scores.out, P from build_checks.txt).
A real EP inside the top 20 at any check is graded then. Local only."""
import csv
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; B = HERE.parent
P = dict(x.split("->") for x in (B / "build_checks.txt").read_text().split() if "->" in x)
rs = {}
for r in csv.DictReader(open(B / "q08_scores.out"), delimiter="|"):
    if r.get("score_date") and r["rs_composite"]:
        rs[(r["ticker"], r["score_date"])] = float(r["rs_composite"])
ticks = defaultdict(list)
for r in csv.DictReader(open(HERE / "v9_ticks_positive_days.out"), delimiter="|"):
    if r.get("tick") and not r["scan_date"].startswith("("):
        ticks[(r["scan_date"], r["tick"])].append((r["ticker"], int(r["rank_by_gap"])))
POS = {"2026-05-06": ["UMC", "ARM"], "2026-05-07": ["SNOW"], "2026-08-04": ["PLTR"], "2026-08-07": ["TEAM"]}
tot = defaultdict(lambda: [0, 0])
for d, names in POS.items():
    for p in names:
        res = {}
        for kname in ("alpha", "gap", "rs_comp"):
            inside = n = 0; last = None
            for (dd, t), board in sorted(ticks.items()):
                if dd != d or p not in [x[0] for x in board]: continue
                n += 1
                if kname == "alpha":
                    order = sorted(x[0] for x in board)
                elif kname == "gap":
                    order = [x[0] for x in sorted(board, key=lambda x: x[1])]
                else:
                    order = sorted((x[0] for x in board), key=lambda t_: (rs.get((t_, P[d])) is None, -(rs.get((t_, P[d])) or 0), t_))
                rk = order.index(p) + 1; last = (rk, len(board))
                inside += rk <= 20
            res[kname] = (inside, n, last)
            tot[kname][0] += inside > 0; tot[kname][1] += last[0] <= 20
        print(d, p, " | ".join(f"{k}: inside top 20 at {v[0]} of {v[1]} checks, last check {v[2][0]} of {v[2][1]}" for k, v in res.items()))
for k, (whole, last) in tot.items():
    print(f"S:{k}: real EPs kept over the whole morning {whole} of 5; at the last check only {last} of 5")
