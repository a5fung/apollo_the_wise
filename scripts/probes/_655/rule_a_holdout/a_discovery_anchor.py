"""#655 rule A hold-out — step 1: DISCOVERY anchor (read-only, $0, local).

Re-runs the study's discovery replay EXACTLY (verify_b.py's board() + masked() + compute_g3, verify_c.py's
streak/retire logic) on the study's own 10-04 capture, for A3 and A5. Must reproduce verify_c:
  K=3 -> 26 retire events, 7 later-real (on 10-02 board AND passing 10-02); G3 nights 17/19
  K=5 -> 23 retire events, 4 later-real;                                    G3 nights 15/19
Saves per-night verdicts (incl. unjudgeable) + boards for the hold-out step.
"""
import collections
import pickle
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc

S = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_655/rule_a_holdout/"
d = pickle.load(open(S + "655_capture.pkl", "rb"))
scores, sector, excess, hist = d["scores"], d["sector"], d["excess"], d["history"]
sess = [date.fromisoformat(s) for s in d["sessions"]]
ret_dates = sess[1:]
assert len(ret_dates) == 60
by_name = collections.defaultdict(list)
for r in hist:
    by_name[r["name"]].append(r)
for n in by_name:
    by_name[n].sort(key=lambda r: r["theme_date"])
dates = sorted({r["theme_date"] for r in hist})


def board(D):  # verify_b.board(D, "active") verbatim
    out = []
    for n, rows in by_name.items():
        rr = [r for r in rows if r["theme_date"] <= D and r["theme_date"] >= D - timedelta(days=7)]
        if not rr:
            continue
        L = rr[-1]
        if L["stage"] == "Retired" or not L["tickers"]:
            continue
        out.append({"name": n, "stage": L["stage"], "tickers": list(L["tickers"]), "date": L["theme_date"]})
    return out


def masked(D):  # verify_b.masked verbatim
    keep = np.array([rd < D for rd in ret_dates])
    return {t: np.where(keep, v, np.nan) for t, v in excess.items()}, int(keep.sum())


nights = [D for D in dates if D >= date(2026, 9, 8)]
assert len(nights) == 19, nights
fails, boards, verdict = {}, {}, {}
for D in nights:
    b = board(D)
    boards[D] = b
    ex, _ = masked(D)
    us = tc.usable_set(ex)
    g3 = tc.compute_g3(b, ex, us, scores, sector)
    fails[D] = set(g3["fail_list"])
    verdict[D] = {r["name"]: r["pass_g3"] for r in g3["themes"]}
last = nights[-1]

out_lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out_lines.append(s)


P("DISCOVERY anchor — study capture, verify_b/verify_c method, nights", nights[0], "..", last, f"({len(nights)})")
for D in nights:
    v = verdict[D]
    nj = sum(1 for x in v.values() if x is not None)
    P(f"  {D} board {len(boards[D])} judgeable {nj} fails {len(fails[D])} G3 {100*(nj-len(fails[D]))/nj:.1f}%")

res = {}
for K in (3, 5):
    streak = collections.defaultdict(int)
    retired = {}
    g3_vc, g3_j = [], []
    for D in nights:
        names = {t["name"] for t in boards[D]}
        for n in names:
            streak[n] = streak[n] + 1 if n in fails[D] else 0
        for n in names:
            if streak[n] >= K and n not in retired:
                retired[n] = D
        live = [t for t in boards[D] if t["name"] not in retired]
        nf = sum(1 for t in live if t["name"] in fails[D])
        g3_vc.append(100 * (len(live) - nf) / len(live))  # verify_c's formula
        nj = sum(1 for t in live if verdict[D].get(t["name"]) is not None)
        g3_j.append(100 * (nj - nf) / nj)  # passing / judgeable survivors
    bl = {t["name"]: t for t in boards[last]}
    real = [n for n in retired if n in bl and n not in fails[last]]
    P(f"\nA{K}: retire events {len(retired)} | later-real (on 10-02 board AND pass 10-02) {len(real)}")
    P(f"   G3 nights >= 90%: verify_c formula {sum(x >= 90 for x in g3_vc)}/19 | passing/judgeable {sum(x >= 90 for x in g3_j)}/19")
    P("   per night (judgeable):", " ".join(f"{D.isoformat()[5:]}={x:.1f}" for D, x in zip(nights, g3_j)))
    for n, D in sorted(retired.items(), key=lambda x: (x[1], x[0])):
        sz = len(next(t for t in boards[D] if t["name"] == n)["tickers"])
        tag = "LATER-REAL" if n in real else ""
        P(f"   {D} retire {n[:62]:62s} size@retire {sz:2d} {tag}")
    res[K] = {"retired": retired, "real_1002": real, "g3_j": dict(zip(nights, g3_j)), "streak_end": dict(streak)}

pickle.dump({"nights": nights, "fails": fails, "verdict": verdict,
             "boards": {D: [{"name": t["name"], "stage": t["stage"], "size": len(t["tickers"])} for t in b]
                        for D, b in boards.items()},
             "res": res}, open(HERE + "a_discovery_anchor.pkl", "wb"))
open(HERE + "a_discovery_anchor.out", "w").write("\n".join(out_lines) + "\n")
