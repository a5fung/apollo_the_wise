"""#545 — THE SELECTION TEST. Can anything knowable AT FIRE TIME separate the tail from the rest?

WHY THIS IS THE ONLY QUESTION LEFT. Across 267 caught EPs (May-Aug) the four delayed-entry buy
signals fire on 96% of names — recall is solved — and every group loses money, median fire a full
stop, in every month and both exit styles. Tonight's #482 re-read landed in the same place from the
other direction: the one real signal in the 5-minute bracket lane was that its REFUSALS dodged 21
losing days with zero winners. Selection, not geometry, not recall.

PRE-REGISTERED 2026-09-01 on the #545 PLAN line, BEFORE any of this was run:
  FEATURES (closed list, no feature invented after seeing results): catalyst grade · EP-day gap % ·
  EP-day dollar volume · prior-day RS composite · active-theme membership · stop width as % of
  entry · which buy signal fired · session index of the fire · how many signals fired together ·
  simulated day-1 group · extension at the EP.
  PASS BAR, all three: (a) lift the tail rate from its ~3% base to >=8%; (b) keep >=30 fires;
  (c) hold with MAY EXCLUDED and on BOTH exit arms.
  THE NULL IS A RESULT: if nothing clears the bar, delayed entry does not pay as a tactic.

Run: python scripts/probes/_545_selection_test.py
Offline — reads the captured TSVs plus _545_features.psv. No prod reads, no cost, re-runnable.
"""
from __future__ import annotations

import csv
import itertools
from collections import defaultdict

P = "scripts/probes/"
TAIL_R = 4.0          # THE GOAL: at ~17-20% win the average winner must clear ~4R to break even
BAR_RATE = 0.08       # the campaign study's P13 break-even band is 8-18%
BAR_N = 30


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(name, delim="|"):
    with open(P + name) as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def build():
    camp = {(r["ticker"], r["ep_date"]): r for r in load("_562bf_campaigns.tsv")}
    alert = {(r["ticker"], r["alert_date"]): r for r in load("_562bf_alerts.tsv")}
    grp = {(r["ticker"], r["ep_date"]): r["group"] for r in load("_562sp_classification.tsv")}
    feat = {}
    for line in open(P + "_545_features.psv"):
        p = line.rstrip("\n").split("|")
        if len(p) >= 5:
            feat[(p[0], p[1])] = {"rs": _f(p[2]), "dollar_vol": _f(p[3]), "extension": _f(p[4])}

    fires = load("_562bf_triggers.tsv")
    per_campaign = defaultdict(set)
    for r in fires:
        per_campaign[(r["ticker"], r["ep_date"])].add(r["rung"])

    rows = []
    for r in fires:
        R, Rt = _f(r["realized_r"]), _f(r["realized_r_trail"])
        if R is None:
            continue                      # unsettled / abstained — never counted either way
        k = (r["ticker"], r["ep_date"])
        c, a, ft = camp.get(k, {}), alert.get(k, {}), feat.get(k, {})
        entry, stop = _f(r["entry"]), _f(r["stop"])
        rows.append({
            "ticker": r["ticker"], "ep_date": r["ep_date"], "month": r["ep_date"][:7],
            "R": R, "Rt": Rt if Rt is not None else R,
            "tail": R >= TAIL_R, "tail_trail": (Rt if Rt is not None else R) >= TAIL_R,
            # ── the pre-registered features ──
            "catalyst_grade": a.get("catalyst_quality") or "(none)",
            "gap_pct": _f(c.get("gap_pct")),
            "dollar_vol": ft.get("dollar_vol"),
            "rs": ft.get("rs"),
            "in_theme": a.get("in_active_theme") or "(none)",
            "stop_width_pct": ((entry - stop) / entry * 100) if entry and stop and entry > stop else None,
            "rung": r["rung"],
            "session_idx": _f(r["session_idx"]),
            "n_rungs": len(per_campaign[k]),
            "day1_group": grp.get(k, "?"),
            "extension": ft.get("extension"),
        })
    return rows


def rate(sub, key="tail"):
    return (sum(1 for r in sub if r[key]) / len(sub)) if sub else 0.0


def evaluate(rows, label, sub, tried):
    """Score one cut against the pre-registered bar. Returns a verdict dict."""
    tried.append(label)
    n, k = len(sub), sum(1 for r in sub if r["tail"])
    if n == 0:
        return None
    no_may = [r for r in sub if r["month"] != "2026-05"]
    return {
        "cut": label, "n": n, "tail": k, "rate": k / n,
        "n_no_may": len(no_may), "rate_no_may": rate(no_may),
        "rate_trail": rate(sub, "tail_trail"),
        "mean_R": sum(r["R"] for r in sub) / n,
        "pass": (k / n >= BAR_RATE and n >= BAR_N
                 and len(no_may) >= BAR_N and rate(no_may) >= BAR_RATE
                 and rate(sub, "tail_trail") >= BAR_RATE),
    }


def main():
    rows = build()
    base_n, base_k = len(rows), sum(1 for r in rows if r["tail"])
    print(f"POPULATION: {base_n} settled fires · {base_k} reached >={TAIL_R:.0f}R "
          f"· base tail rate {base_k/base_n:.1%}")
    print(f"BAR: rate >= {BAR_RATE:.0%} AND n >= {BAR_N} AND holds ex-May AND holds on the trail arm\n")

    tried, results = [], []
    CONT = [("gap_pct", "EP-day gap %"), ("dollar_vol", "EP-day $ volume"),
            ("rs", "prior-day RS"), ("stop_width_pct", "stop width % of entry"),
            ("session_idx", "session index of fire"), ("extension", "extension at EP")]
    for key, name in CONT:
        vals = sorted(v for v in (r[key] for r in rows) if v is not None)
        if len(vals) < BAR_N * 2:
            print(f"  SKIP {name}: only {len(vals)} fires carry it — cannot support a cut")
            continue
        for q in (0.25, 0.5, 0.75):
            t = vals[int(len(vals) * q)]
            for op, sym in ((lambda v, t=t: v >= t, ">="), (lambda v, t=t: v < t, "<")):
                sub = [r for r in rows if r[key] is not None and op(r[key])]
                res = evaluate(rows, f"{name} {sym} {t:g}", sub, tried)
                if res:
                    results.append(res)
    for key, name in (("catalyst_grade", "catalyst grade"), ("in_theme", "in active theme"),
                      ("rung", "buy signal"), ("day1_group", "simulated day-1 group"),
                      ("n_rungs", "signals fired together")):
        for v in sorted({str(r[key]) for r in rows}):
            sub = [r for r in rows if str(r[key]) == v]
            res = evaluate(rows, f"{name} = {v}", sub, tried)
            if res:
                results.append(res)

    results.sort(key=lambda r: -r["rate"])
    print(f"{'cut':<40}{'n':>5}{'tail':>6}{'rate':>8}{'ex-May':>9}{'trail':>8}{'meanR':>8}  pass")
    for r in results[:22]:
        print(f"{r['cut']:<40}{r['n']:>5}{r['tail']:>6}{r['rate']:>7.1%}"
              f"{r['rate_no_may']:>9.1%}{r['rate_trail']:>8.1%}{r['mean_R']:>8.2f}"
              f"  {'PASS' if r['pass'] else ''}")

    passed = [r for r in results if r["pass"]]
    print(f"\nCUTS TRIED: {len(tried)}   CUTS PASSING: {len(passed)}")
    print(f"MULTIPLE COMPARISONS: at a 3.2% base rate, testing {len(tried)} cuts on {base_n} fires "
          f"with {base_k} positives,\n  some cut clearing 8% by chance alone is EXPECTED — a "
          f"single passing cut found after {len(tried)} tries is noise, not a finding.")
    if not passed:
        print("\n>>> NOTHING CLEARS THE PRE-REGISTERED BAR. This is the null, and it was written "
              "down in advance.")
    return results, tried


if __name__ == "__main__":
    main()
