"""#687 INDEPENDENT CHECK (5) — headline paired totals and p per block, recomputed from (a) arms_per_trade.tsv and (b) MY walker's
per-trade R (check_mine_per_trade.tsv), with my own week-block sign-flip permutation (numpy, seed 20260929, 20,000 draws).
Writes check_recompute.txt."""
import csv, collections
from datetime import date
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
O = open(HERE / "check_recompute.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); O.write(s + "\n")
T = {}
for r in csv.DictReader(open(HERE / "arms_per_trade.tsv"), delimiter="|"):
    T[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
M = {}
for r in csv.DictReader(open(HERE / "check_mine_per_trade.tsv"), delimiter="|"):
    M[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
ARMS = ("A0", "A1", "D10", "T20_hs", "S20_hs", "T20_be", "S20_be")
def tsvR(k, a):
    r = T[k]
    return float(r[f"{a}_R"]) if r[f"{a}_status"] == "settled" and r[f"{a}_R"] else None
def mineR(k, a):
    r = M[k]
    return float(r[f"{a}_R"]) if r[f"{a}_R"] and not r[f"{a}_final"].startswith(("abstain", "open")) else None
rng = np.random.default_rng(20260929)
def perm_p(diffs, weeks, n=20000):
    groups = collections.defaultdict(float)
    for d, w in zip(diffs, weeks):
        groups[w] += d
    g = np.array(list(groups.values()))
    obs = abs(g.sum())
    if obs == 0:
        return 1.0
    signs = rng.choice([-1.0, 1.0], size=(n, len(g)))
    return float((np.abs(signs @ g) >= obs - 1e-12).mean())
def table(getR, label, keys_filter=None):
    P(f"## {label}")
    for blk in ("ALL", "DISC", "HELD"):
        ks = [k for k in T if (blk == "ALL" or T[k]["block"] == blk)]
        paired = [k for k in ks if all(getR(k, a) is not None for a in ARMS)]
        if keys_filter:
            paired = [k for k in paired if keys_filter(k)]
        base = np.array([getR(k, "A0") for k in paired])
        weeks = [f"{k[1].isocalendar()[0]}-{k[1].isocalendar()[1]}" for k in paired]
        for a in ARMS:
            v = np.array([getR(k, a) for k in paired]); d = v - base
            mpo = np.array([(float(T[k]["entry"]) - float(T[k]["hard"])) / (float(T[k]["entry"]) - float(T[k]["orb_low"])) for k in paired])
            orb = v * mpo
            srt = np.sort(v)
            top2 = np.sort(d)[-2:].sum() if a != "A0" else 0.0
            line = (f"   {blk:4s} {a:7s} n={len(paired):4d} total {v.sum():+8.2f} mean {v.mean():+.3f} drop-best-2 {srt[:-2].sum():+8.2f}")
            if a != "A0":
                line += (f" | vs A0 {d.sum():+7.2f} p={perm_p(list(d), weeks):.3f} better/worse {(d > 0.005).sum()}/{(d < -0.005).sum()}"
                         f" diff w/o its top 2 {d.sum() - top2:+7.2f}")
            line += f" | >=3R {(orb >= 3).sum()} >=8R {(orb >= 8).sum()} worst {v.min():+.2f} <-1.5R {(v < -1.5).sum()}"
            P(line)
table(tsvR, "FROM arms_per_trade.tsv (the study's per-trade R), all paired trades")
eng = {k for k in T if (T[k]["T20_be_final"] in ("time_close",) or T[k]["T20_be_exit_day"] != T[k]["A0_exit_day"] or T[k]["T20_be_R"] != T[k]["A0_R"])}
table(mineR, "FROM MY WALKER's per-trade R (independent code), all paired trades")
# depth vs close-only (post-hoc in the doc)
for blk in ("ALL", "DISC", "HELD"):
    ks = [k for k in T if (blk == "ALL" or T[k]["block"] == blk) and all(tsvR(k, a) is not None for a in ARMS)]
    d = np.array([tsvR(k, "D10") - tsvR(k, "A1") for k in ks])
    P(f"   depth - close-only {blk}: {d.sum():+.2f} (better {(d > 0.005).sum()} / worse {(d < -0.005).sum()} of {(np.abs(d) > 0.005).sum()} that differ)")
# drop BE / HL
ks = [k for k in T if all(tsvR(k, a) is not None for a in ARMS)]
x = [k for k in ks if not (k in {("BE", date(2025, 7, 24)), ("HL", date(2025, 8, 7))})]
P(f"   without BE 2025-07-24 and HL 2025-08-07 (n {len(x)}): A1-A0 {sum(tsvR(k, 'A1') - tsvR(k, 'A0') for k in x):+.2f}  D10-A0 {sum(tsvR(k, 'D10') - tsvR(k, 'A0') for k in x):+.2f}")
hx = [k for k in ks if T[k]["block"] == "HELD" and k not in {("BE", date(2025, 7, 24)), ("HL", date(2025, 8, 7)), ("FCEL", date(2026, 4, 29))}]
P(f"   held-out without BE, HL, FCEL (n {len(hx)}): D10-A0 {sum(tsvR(k, 'D10') - tsvR(k, 'A0') for k in hx):+.2f}")
# runner engaged counts + the DWAC mark artefact
import json
J = json.load(open(HERE / "arms_results.json"))
engaged = [k for k, v in J["T20_be"].items() if v.get("runner_engaged")]
P(f"   runner engaged {len(engaged)}; T20_be-A0 on engaged {sum(tsvR((k.split('|')[0], date.fromisoformat(k.split('|')[1])), 'T20_be') - tsvR((k.split('|')[0], date.fromisoformat(k.split('|')[1])), 'A0') for k in engaged):+.2f}")
k = ("DWAC", date(2024, 3, 25))
P(f"   DWAC 2024-03-25 (bars end on the entry day): A0 {tsvR(k, 'A0'):+.4f} vs every runner arm {tsvR(k, 'T20_be'):+.4f} -> +{tsvR(k, 'T20_be') - tsvR(k, 'A0'):.2f}R of each runner's 'vs today' is a MARK convention "
  f"(walk_hybrid_arm marks at the entry price when no later bar exists; walk_runner marks at day P's close), not a rule effect")
top = sorted(ks, key=lambda k: -(tsvR(k, "T20_be") - tsvR(k, "A0")))[:5]
P(f"   T20_be top-5 contributors: {[(k[0], str(k[1]), round(tsvR(k, 'T20_be') - tsvR(k, 'A0'), 2)) for k in top]}")
d = sorted([tsvR(k, "T20_be") - tsvR(k, "A0") for k in ks])
P(f"   T20_be-A0 without top 2 {sum(d[:-2]):+.2f}, without top 3 {sum(d[:-3]):+.2f}; median diff among engaged {np.median([tsvR((k.split('|')[0], date.fromisoformat(k.split('|')[1])), 'T20_be') - tsvR((k.split('|')[0], date.fromisoformat(k.split('|')[1])), 'A0') for k in engaged]):+.3f}")
O.close()
