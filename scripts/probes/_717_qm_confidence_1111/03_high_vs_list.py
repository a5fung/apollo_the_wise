#!/usr/bin/env python3
"""#717 step 2: the High-confidence Qullamaggie buys against the CURRENT breakout list, gate by gate, and what each
loosening does (recall on High / Medium, cost on Low / Not, the pinned labels). Nothing is wired; proposals only.

Reads the two fixtures, ratings via rating.py, and (widened nights' strength rank + raw close only)
/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet (nights to 2022-03-31). features_eraB is NOT opened.

    python3 scripts/probes/_717_qm_confidence_1111/03_high_vs_list.py > scripts/probes/_717_qm_confidence_1111/03_high_vs_list.out"""
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
sys.path.insert(0, "tests")

F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
del F

B = R.load()
rows = []
for b in B:
    r = R.rate(b)
    bars = cb.daily_bars_from_arrays(b["dates"], b["o"], b["h"], b["l"], b["c"], b["v"])
    nights = []
    for D in [i - 1 for i in b["win"]]:
        if b["set"] == "dated":
            rs, raw = float(b["row"]["rs_best"]), float(b["row"]["raw_close_D"])
        else:
            rs, raw = RS.get((b["ticker"], b["dates"][D].isoformat()), (None, None))
        try:
            v = bv.v1_gates(bars, D, rs_best=rs, raw_close=raw)
        except Exception:
            nights.append(dict(D=D, failed=["history"], ok=False, val=None))
            continue
        g = v["gates"]
        val = None
        if g["universe"]["pass"] is not None:
            val = dict(universe=g["universe"]["pass"], pinned=g["pinned"]["pass"], adr=g["adr"]["pass"], rs=rs,
                       prior=g["prior_move"]["value"]["prior_move"], depth=g["base_depth"]["value"]["depth_adr"],
                       e21=g["ema21"]["value"]["vs_ema21_adr"],
                       s50=(v["close"] / g["sma50"]["value"]["sma50"] - 1) if isinstance(g["sma50"]["value"], dict) and g["sma50"]["value"].get("sma50") else None,
                       s50pass=g["sma50"]["pass"])
        nights.append(dict(D=D, failed=v["failed"], ok=v["ok"], val=val))
    rows.append(dict(b=b, r=r, nights=nights))

# ── reproduce the known numbers first ─────────────────────────────────────────────────────────────────────────
d_on = sum(x["nights"][0]["ok"] for x in rows if x["b"]["set"] == "dated")
w = [x for x in rows if x["b"]["set"] == "widened"]
w_on = sum(any(n["ok"] for n in x["nights"]) for x in w)
mism = [(x["b"]["ticker"], x["b"]["lo"]) for x in w if int(any(n["ok"] for n in x["nights"])) != int(x["b"]["row"]["on_current_list_any_night"])]
print(f"REPRODUCE: dated on the list at D {d_on} of 269 (known 263); widened on any night {w_on} of 488 (known 192); "
      f"row mismatches vs the fixture column: {len(mism)} {mism[:10]}")

BASE = dict(rs=bv.RS_MIN, prior=bv.PRIOR_MOVE_MIN, dmin=bv.BASE_DEPTH_ADR_MIN, dmax=bv.BASE_DEPTH_ADR_MAX, e21=bv.EMA21_ADR_MIN, s50=0.0)


def night_ok(n, P):
    v = n["val"]
    if v is None:
        return False
    if not (v["universe"] and v["pinned"] and v["adr"]):
        return False
    if P["rs"] is not None and not (v["rs"] is not None and v["rs"] >= P["rs"]):
        return False
    if P["prior"] is not None and not (v["prior"] is not None and v["prior"] >= P["prior"]):
        return False
    if v["depth"] is None or (P["dmin"] is not None and v["depth"] < P["dmin"]) or (P["dmax"] is not None and v["depth"] > P["dmax"]):
        return False
    if P["e21"] is not None and not (v["e21"] is not None and v["e21"] >= P["e21"]):
        return False
    if P["s50"] is not None and not (v["s50"] is not None and v["s50"] >= P["s50"]):
        return False
    return True


def held(x, P):
    return any(night_ok(n, P) for n in x["nights"])


chk = sum(held(x, BASE) != any(n["ok"] for n in x["nights"]) for x in rows)
print(f"the re-evaluator agrees with v1_gates on all buys: mismatches {chk}")

T = lambda x: x["r"]["tier"]  # noqa: E731
print("\n=== HIGH TIER: on the current list ===")
for s in ("dated", "widened"):
    for tier in R.TIERS:
        g = [x for x in rows if x["b"]["set"] == s and T(x) == tier]
        on = sum(held(x, BASE) for x in g)
        extra = ""
        if s == "widened" and tier in ("High", "Medium"):
            nb = sum(next((n["ok"] for n in x["nights"] if n["D"] == x["r"]["t"] - 1), False) for x in g)
            extra = f"   the night before the rated break day: {nb} of {len(g)}"
        print(f"  {s:8s} {tier:7s} on the list {on:3d} of {len(g):3d} ({on / max(1, len(g)):4.0%}){extra}")

print("\n=== PER-GATE MISS TABLE, High tier (blocks = fails on every night; alone = the only gate failing on the best night) ===")
for s in ("dated", "widened"):
    g = [x for x in rows if x["b"]["set"] == s and T(x) == "High"]
    missed = [x for x in g if not held(x, BASE)]
    print(f"{s}: High n = {len(g)}, missed {len(missed)}")
    blocks, alone, names = Counter(), Counter(), {}
    for x in missed:
        best = min(x["nights"], key=lambda n: len(n["failed"]))
        for gt in bv.GATES:
            if all(gt in n["failed"] for n in x["nights"]):
                blocks[gt] += 1
                names.setdefault(gt, []).append(f"{x['b']['ticker']} {x['b']['hi']}" + ("*" if best["failed"] == [gt] else ""))
        if len(best["failed"]) == 1:
            alone[best["failed"][0]] += 1
    for gt in sorted(blocks, key=lambda k: -blocks[k]):
        print(f"  {gt:11s} blocks {blocks[gt]:2d}  alone {alone[gt]:2d}   {', '.join(names[gt])}   (* = alone)")
    for x in missed:
        best = min(x["nights"], key=lambda n: len(n["failed"]))
        v = best["val"] or {}
        fmt = lambda k, f: "-" if v.get(k) is None else f.format(v[k])  # noqa: E731
        print(f"    {x['b']['ticker']:6s} {x['b']['lo']}..{x['b']['hi']} failed {','.join(best['failed']):28s} rs {fmt('rs', '{:.0f}')} prior {fmt('prior', '{:.0%}')} "
              f"depth {fmt('depth', '{:.1f}')} vs21 {fmt('e21', '{:+.2f}')} vs50 {fmt('s50', '{:+.1%}')}  level {x['r']['level']:.4g} len {x['r']['len']}")

# ── the pinned labels (dated set) ─────────────────────────────────────────────────────────────────────────────
SIX = {("YPF", "2019-04-17"), ("W", "2020-04-07"), ("DOCU", "2020-12-04"), ("DOCU", "2020-12-15"), ("SQM", "2021-09-10"), ("MRNA", "2021-11-29")}
NEG = {("ANET", "2018-03-12"), ("TDOC", "2019-10-31"), ("STNE", "2019-11-18"), ("ZS", "2020-03-24"), ("EXEL", "2020-04-20"), ("SHOP", "2020-04-20"),
       ("NVAX", "2020-05-12"), ("PLNT", "2020-05-26"), ("UAL", "2020-05-27"), ("JMIA", "2020-11-18"), ("FEAC", "2020-11-30"), ("UPST", "2021-08-12"),
       ("FCX", "2021-12-07"), ("MU", "2021-12-21"), ("FCX", "2021-12-27"), ("MDB", "2021-12-27")}
dated = [x for x in rows if x["b"]["set"] == "dated"]
print("\npinned labels' tiers: his 6 NOs " + ", ".join(f"{x['b']['sym']} {x['b']['hi']} {T(x)}" for x in dated if (x["b"]["sym"], x["b"]["hi"]) in SIX))
print("the 16 known negatives' tiers: " + str(dict(Counter(T(x) for x in dated if (x["b"]["sym"], x["b"]["hi"]) in NEG))))


def score(P):
    o = {}
    for s in ("dated", "widened"):
        for tier in R.TIERS:
            g = [x for x in rows if x["b"]["set"] == s and T(x) == tier]
            o[(s, tier)] = (sum(held(x, P) for x in g), len(g))
    o["bw"] = sum(held(x, P) for x in dated if x["b"]["row"]["big_winner"] == "1")
    o["six"] = sum(held(x, P) for x in dated if (x["b"]["sym"], x["b"]["hi"]) in SIX)
    o["neg"] = sum(held(x, P) for x in dated if (x["b"]["sym"], x["b"]["hi"]) in NEG)
    return o


def line(name, P):
    o = score(P)
    f = lambda k: f"{o[k][0]:3d}/{o[k][1]:<3d}"  # noqa: E731
    print(f"  {name:44s} H {f(('dated', 'High'))} {f(('widened', 'High'))} | M {f(('dated', 'Medium'))} {f(('widened', 'Medium'))} | "
          f"Low {f(('dated', 'Low'))} {f(('widened', 'Low'))} | Not {f(('dated', 'Not'))} {f(('widened', 'Not'))} | bigwin {o['bw']}/26 | his NOs {o['six']}/6 | known neg {o['neg']}/16")


print("\n=== ONE GATE MOVED AT A TIME (everything else as today). Columns: on the list / n, dated then widened ===")
line("TODAY", BASE)
for k, vals in (("prior", (0.30, 0.25, 0.20, 0.15, 0.10, None)), ("dmax", (10.0, 12.0, 15.0, 20.0, None)), ("dmin", (1.0, 0.5, None)),
                ("rs", (30.0, 20.0, None)), ("s50", (-0.02, -0.05, -0.10, None)), ("e21", (-1.0, -1.5, None))):
    for v in vals:
        line(f"{k} -> {'dropped' if v is None else v}", dict(BASE, **{k: v}))

print("\n=== COMBINATIONS ===")
for name, ch in (("prior 0.20 + dmax 12", dict(prior=0.20, dmax=12.0)), ("prior 0.15 + dmax 12", dict(prior=0.15, dmax=12.0)),
                 ("prior 0.15 + dmax 15", dict(prior=0.15, dmax=15.0)), ("prior 0.10 + dmax 15", dict(prior=0.10, dmax=15.0)),
                 ("prior 0.15 + dmax 12 + s50 -0.05", dict(prior=0.15, dmax=12.0, s50=-0.05)),
                 ("prior 0.15 + dmax 12 + rs dropped", dict(prior=0.15, dmax=12.0, rs=None)),
                 ("prior dropped + dmax dropped", dict(prior=None, dmax=None)),
                 ("prior, dmax, dmin, rs dropped", dict(prior=None, dmax=None, dmin=None, rs=None))):
    line(name, dict(BASE, **ch))
