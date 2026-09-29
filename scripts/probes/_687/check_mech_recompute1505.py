"""ADVERSARIAL CHECK of #687 part 3, item 4 extended: the rebuilt-1,505 timing numbers with the SAME independent
walker as check_mech_recompute79.py. Inputs (population, day-1 states, daily + minute bars) are rebuilt with
backfill.py's own loaders exactly as mechanics.build_1505 does (copied here, NOT imported: importing
mechanics.py would truncate its mechanics_out.txt). $0, offline.
"""
from __future__ import annotations

import collections
import csv
import sys
from datetime import date, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "_685"))
import backfill as BF  # noqa: E402
import check_mech_recompute79 as W  # noqa: E402

OUT = open(HERE / "check_mech_recompute1505.txt", "w")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.write(s + "\n")


def build_1505():   # copy of mechanics.build_1505 (input construction only)
    pop = BF.load_population()
    daily = BF.load_daily()
    entry_min = BF.load_minutes(sorted(HERE.glob("minutes_entry*.tsv*")))
    held_min = BF.load_minutes(sorted(HERE.glob("minutes_held*.tsv*")))
    bad_join = set()
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k)
        if not bars0 or r["o"] is None:
            continue
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if orb and abs(orb["o"] - r["o"]) / r["o"] > 0.02:
            bad_join.add(k)
    states, day0_only = {}, {}
    for r in pop:
        k = (r["ticker"], r["d"])
        bars0 = entry_min.get(k, [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if k in bad_join or not bars0 or orb is None:
            continue
        Hh, Ll = orb["h"], orb["l"]
        ok, _ = BF.validate_orb_entry(Hh, Ll, BF.atr14_live(daily.get(r["ticker"], {}), r["d"]))
        if not ok or 2 * Ll - Hh <= 0:
            continue
        f = BF.live_entry(bars0, Hh, Ll)
        if f["status"] != "filled":
            continue
        st, why = BF.day0_from_fill(k[0], k[1], bars0, Hh, Ll, f, daily)
        if st is None:
            continue
        if st["settled_d0"]:
            day0_only[k] = st["h"]["realized_r"]
        else:
            states[k] = st
    return daily, held_min, states, day0_only


def main():
    daily, held, states, day0 = build_1505()
    stored = {}
    with open(HERE / "arms_per_trade.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            stored[(r["ticker"], date.fromisoformat(r["entry_day"]))] = r
    keys_all = sorted(set(states) | set(day0), key=lambda k: (k[1], k[0]))
    keys = [k for k in keys_all if k in stored and all(stored[k][f"{a}_status"] == "settled" for a in ("A0", "A1", "D10"))]
    P(f"# independent recompute, rebuilt: states {len(states)}, day0 {len(day0)}, stored-paired {len(keys)}")
    R, why = {}, {}
    ovn = {}
    for arm in ("A0", "D10"):
        for t in ("close", "open", "1545", "1545mkt"):
            dg = collections.Counter()
            dg["overnight"] = []
            res, rs = {}, collections.Counter()
            for k in keys:
                if k in day0:
                    res[k] = day0[k]
                    rs["day0"] += 1
                    continue
                dg.pop("mark", None)
                r, w = W.walk(arm, t, k, states[k], daily, held, BF.HORIZON, dg)
                if w == "open_at_horizon":
                    dbars = daily.get(k[0], {})
                    if dbars and max(dbars) < BF.HORIZON - __import__("datetime").timedelta(days=14) and dg.get("mark") is not None:
                        r, w = dg["mark"], "delisted_forced_close"
                res[k] = r
                rs[w] += 1
            R[(arm, t)] = res
            why[(arm, t)] = rs
            ovn[(arm, t)] = (dg["overnight"], dg["nobar_ambiguous"], dg.get("open_notional_r", []), dg.get("stop_notional_r", []))
    keys_p = [k for k in keys if all(R[v][k] is not None for v in R)]
    bad = [(arm, k, R[(arm, "close")][k], stored[k][f"{arm}_R"]) for arm in ("A0", "D10") for k in keys
           if R[(arm, "close")][k] is None or abs(R[(arm, "close")][k] - float(stored[k][f"{arm}_R"])) > 0.005]
    P(f"## FIDELITY close timing vs stored arms_per_trade.tsv: mismatches {len(bad)}; paired in all variants {len(keys_p)}")
    for b_ in bad[:10]:
        P("   ", b_)
    for (arm, t), rs in why.items():
        P(f"   {arm}-{t:8s} total {sum(R[(arm, t)][k] for k in keys_p):+8.2f}  exits {dict(rs)}")
    base = R[("A0", "open")]
    for a in (("D10", "close"), ("D10", "open"), ("D10", "1545"), ("D10", "1545mkt"), ("A0", "close")):
        diffs = [R[a][k] - base[k] for k in keys_p]
        srt = sorted(diffs)
        P(f"   {a[0]}-{a[1]} vs A0-open (today live): {sum(diffs):+.2f}R  without its top-2 {sum(diffs) - sum(srt[-2:]):+.2f}R")
    P(f"   D10-close vs A0-close: {sum(R[('D10', 'close')][k] - R[('A0', 'close')][k] for k in keys_p):+.2f}R")
    on = ovn[("D10", "open")][0]
    nD, nA = sum(ovn[("D10", "open")][2]), sum(ovn[("A0", "open")][2])
    for h in (0.0, 0.0044, 0.0072, 0.01, 0.0141):
        P(f"   haircut {h*100:.2f}%: totals " + " | ".join(
            f"{a}-{t} {sum(R[(a, t)][k] for k in keys_p) - h * sum(ovn[(a, t)][2]):+.2f}"
            for a in ("A0", "D10") for t in ("open", "1545")) +
          f" || D10-1545 minus D10-open {(sum(R[('D10','1545')][k] for k in keys_p) - h*sum(ovn[('D10','1545')][2])) - (sum(R[('D10','open')][k] for k in keys_p) - h*sum(ovn[('D10','open')][2])):+.2f}R")
    for (a, t) in (("A0", "open"), ("D10", "open"), ("D10", "1545")):
        P(f"   market-type fills {a}-{t}: next-open sales {len(ovn[(a, t)][2])} (notional {sum(ovn[(a, t)][2]):.1f} R-units), "
          f"stop fills {len(ovn[(a, t)][3])} (notional {sum(ovn[(a, t)][3]):.1f} R-units)")
    def tot(a, t, h, sym):
        n = sum(ovn[(a, t)][2]) + (sum(ovn[(a, t)][3]) if sym else 0.0)
        return sum(R[(a, t)][k] for k in keys_p) - h * n
    for h in (0.0, 0.0044, 0.0072, 0.01, 0.0141):
        P(f"   SYMMETRIC haircut {h*100:.2f}% (next-open sales AND stop fills, both arms): "
          f"D10-open − A0-open {tot('D10','open',h,1) - tot('A0','open',h,1):+.2f}R | "
          f"D10-1545 − A0-open {tot('D10','1545',h,1) - tot('A0','open',h,1):+.2f}R | "
          f"D10-1545 − D10-open {tot('D10','1545',h,1) - tot('D10','open',h,1):+.2f}R")
    for h in (0.0044, 0.005, 0.01, 0.0141):
        P(f"   open-fill haircut {h*100:.2f}% of price on every next-open sale: D10-open vs A0-open "
          f"{sum(R[('D10', 'open')][k] - base[k] for k in keys_p) - h * (nD - nA):+.2f}R "
          f"(D10 pays {h*nD:.2f}R over {len(ovn[('D10','open')][2])} sales, A0 pays {h*nA:.2f}R over {len(ovn[('A0','open')][2])})")
    P(f"   D10 next-open sales {len(on)}: next open minus close {sum(on):+.2f}R; better {sum(1 for x in on if x > 0.005)} worse {sum(1 for x in on if x < -0.005)}; "
      f"A0 next-open sales {len(ovn[('A0', 'open')][0])}")
    P(f"   no-bar ambiguous days D10-1545 (resolved as the close): {ovn[('D10', '1545')][1]}")
    for k in (("BE", date(2025, 7, 24)), ("HL", date(2025, 8, 7)), ("FCEL", date(2026, 4, 29))):
        if k in keys_p:
            P(f"   {k[0]} {k[1]}: " + " ".join(f"{a}-{t} {R[(a, t)][k]:+.2f}" for a in ("A0", "D10")
                                           for t in ("close", "open", "1545", "1545mkt")))
    OUT.close()


if __name__ == "__main__":
    main()
