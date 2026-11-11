#!/usr/bin/env python3
"""#717 step 2b: (1) the circularity control — the High tier WITHOUT the two rating pieces that lean on gates under test;
(2) can a different measure of the run let the High buys the prior-move gate drops back in WITHOUT his 6 NOs?
Candidate: the 6-month run-up the list already computes for its order score (`breakout_v1.runup6m_at`).

    python3 scripts/probes/_717_qm_confidence_1111/04_run_measure.py > scripts/probes/_717_qm_confidence_1111/04_run_measure.out"""
import sys
from collections import Counter

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import importlib
m = importlib.import_module("03_high_vs_list")  # noqa: E402  (prints its own report first; ignore above the marker)
R, bv, cb, rows, BASE, night_ok, SIX, NEG, dated = m.R, m.bv, m.cb, m.rows, m.BASE, m.night_ok, m.SIX, m.NEG, m.dated
print("\n" + "#" * 30 + " 04_run_measure " + "#" * 30)

print("\n=== (1) CIRCULARITY CONTROL: High tier under looser ratings, widened set, vs the current list ===")
for name, kw in (("as rated", {}), ("holds-its-gains OFF", dict(use_holds=False)), ("trend overrides OFF", dict(use_trend=False)),
                 ("both OFF", dict(use_holds=False, use_trend=False))):
    g = [x for x in rows if x["b"]["set"] == "widened" and R.rate(x["b"], **kw)["tier"] == "High"]
    missed = [x for x in g if not any(n["ok"] for n in x["nights"])]
    blocks = Counter(gt for x in missed for gt in bv.GATES if all(gt in n["failed"] for n in x["nights"]))
    print(f"  {name:22s} High n = {len(g):3d}, on the list {len(g) - len(missed):3d} ({(len(g) - len(missed)) / len(g):.0%}); blocks: "
          + ", ".join(f"{k} {v}" for k, v in blocks.most_common()))

for x in rows:
    b = x["b"]
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    for n in x["nights"]:
        try:
            n["ru6"] = bv.runup6m_at(bars, n["D"])
        except Exception:
            n["ru6"] = None

T = lambda x: x["r"]["tier"]  # noqa: E731
print("\n=== (2) the run, two ways, on the best night: High buys the prior-move gate blocks, then his 6 NOs ===")
for x in rows:
    if x["b"]["set"] == "widened" and T(x) == "High" and all("prior_move" in n["failed"] for n in x["nights"]):
        n = x["nights"][-1]
        print(f"  HIGH  {x['b']['ticker']:5s} {x['b']['hi']} prior {n['val']['prior']:.0%}  6-month run-up {n['ru6']:.0%}  failed {','.join(n['failed'])}")
for x in dated:
    if (x["b"]["sym"], x["b"]["hi"]) in SIX:
        n = x["nights"][0]
        print(f"  NO    {x['b']['sym']:5s} {x['b']['hi']} prior {n['val']['prior']:.0%}  6-month run-up {n['ru6']:.0%}  failed {','.join(n['failed'])}  rated {T(x)}")


def held(x, P, ru_min):
    for n in x["nights"]:
        if night_ok(n, P):
            return True
        if ru_min is not None and n["val"] is not None and n.get("ru6") is not None and n["ru6"] >= ru_min and night_ok(n, dict(P, prior=None)):
            return True
    return False


def line(name, P, ru):
    o = {}
    for s in ("dated", "widened"):
        for tier in R.TIERS:
            g = [x for x in rows if x["b"]["set"] == s and T(x) == tier]
            o[(s, tier)] = f"{sum(held(x, P, ru) for x in g):3d}/{len(g):<3d}"
    bw = sum(held(x, P, ru) for x in dated if x["b"]["row"]["big_winner"] == "1")
    six = [x["b"]["sym"] for x in dated if (x["b"]["sym"], x["b"]["hi"]) in SIX and held(x, P, ru)]
    neg = sum(held(x, P, ru) for x in dated if (x["b"]["sym"], x["b"]["hi"]) in NEG)
    print(f"  {name:52s} H {o[('dated', 'High')]} {o[('widened', 'High')]} | M {o[('dated', 'Medium')]} {o[('widened', 'Medium')]} | Low {o[('dated', 'Low')]} "
          f"{o[('widened', 'Low')]} | Not {o[('dated', 'Not')]} {o[('widened', 'Not')]} | bigwin {bw}/26 | his NOs back {len(six)} {','.join(six)} | known neg {neg}/16")


print("\n=== (3) prior move >= 32% OR the 6-month run-up >= X (everything else as today) ===")
line("TODAY", BASE, None)
for ru in (1.0, 0.8, 0.6, 0.5, 0.4, 0.3):
    line(f"OR 6-month run-up >= {ru:.0%}", BASE, ru)
print("\n=== (4) with the 50-day rule loosened too: close no more than X under the 50-day ===")
for s50 in (-0.02, -0.03, -0.05):
    line(f"50-day {s50:+.0%} only", dict(BASE, s50=s50), None)
    for ru in (0.6, 0.5, 0.4):
        line(f"50-day {s50:+.0%} + OR 6-month run-up >= {ru:.0%}", dict(BASE, s50=s50), ru)
