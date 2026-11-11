"""THE SCORE of the pre-registered shape gates (docs/analysis/cb_shape_gates_2026-11-11.md), run once per gate set.

    python3 scripts/probes/_717_shape_gates_1111/02_score.py [--drop gate,gate] [--set NAME=value,...] > <out file>

(1)/(1b) the 29 name-nights he graded (tests/fixtures/breakout_list_grades.py + _bars.psv.gz);
(2)/(2b) Qullamaggie's 269 dated breakout buys (tests/fixtures/qm_breakout_scorecard/), the existing seven rules AND the
shape gates at the night D before his buy. Prints every row, the per-gate miss tables and the declared sweeps.
No return, outcome or bar after D is read (the scorecard's E bar is never touched). --drop / --set exist ONLY for the one
dated amendment the pre-registration allows; the default run is the pre-registered set."""
import argparse
import csv
import gzip
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--drop", default="")
ap.add_argument("--set", default="")
ap.add_argument("--only", default="")
a = ap.parse_args()
DROP = {x for x in a.drop.split(",") if x}
for kv in [x for x in a.set.split(",") if x]:
    k, v = kv.split("=")
    assert hasattr(bv, k), k
    setattr(bv, k, type(getattr(bv, k))(float(v)))
ACTIVE = [x for x in a.only.split(",") if x] or [g for g in bv.SHAPE_GATES if g not in DROP]
print(f"gate set: {ACTIVE}  (dropped: {sorted(DROP) or 'none'})")
print("constants:", {k: getattr(bv, k) for k in ("SHAPE_HL_RECENT", "SHAPE_SWING_HALF", "SHAPE_LOWER_LOW_ADR",
                                                  "SHAPE_RISING_SESSIONS", "SHAPE_EXTENDED_ADR_MAX", "SHAPE_TIGHT_ADR_MAX")})

# ── load ────────────────────────────────────────────────────────────────────────────────────────────────────
gb = defaultdict(list)
with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        gb[(r["ticker"], r["list_date"])].append(r)
GRADES = []
for g in BREAKOUT_LIST_GRADES:
    rr = gb[(g.ticker, g.list_date)]
    ds = [date.fromisoformat(x["date"]) for x in rr]
    b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
    GRADES.append((g, b, len(ds) - 1))

FX = Path("tests/fixtures/qm_breakout_scorecard")
buys = list(csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"))
by_eid = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        by_eid[r["eid"]].append(r)
QM = []
for r in buys:
    rr = sorted(by_eid[r["eid"]], key=lambda x: x["date"])
    ds = [date.fromisoformat(x["date"]) for x in rr]
    D = ds.index(date.fromisoformat(r["D"]))
    rr, ds = rr[:D + 1], ds[:D + 1]                        # bars <= D ONLY: the buy day E is cut off before any use
    b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
    QM.append((r, b, D))

NEG = {"no", "EP", "looks like EP", "no, maybe EP", "no, maybe a different criteria", "no, buy point maybe a few days earlier",
       "EP look, day before maybe breakout", "ok but EP look"}       # the spec's no / EP-like (its 16 + 6)
TIMING = {"a bit late buy", "buy few days earlier", "maybe a few days ealier", "okish but likely no"}


def label_class(lab):
    if not lab:
        return "unlabelled"
    if lab in NEG:
        return "no_or_ep"
    if lab in TIMING:
        return "timing_or_unsure"
    return "ok_or_better"


def evaluate():
    """-> (grade rows, qm rows): each (meta, existing_ok, {gate: pass}, {gate: value})."""
    grows, qrows = [], []
    for g, b, D in GRADES:
        v = bv.v1_gates(b, D, rs_best=99.0)                 # it WAS on the list; rs is not in the bars
        sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
        grows.append((g, v, {k: sg[k]["pass"] for k in ACTIVE}, sg))
    for r, b, D in QM:
        v = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
        if v["pole_idx"] is None:
            qrows.append((r, v, {k: False for k in ACTIVE}, None))
            continue
        sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
        qrows.append((r, v, {k: sg[k]["pass"] for k in ACTIVE}, sg))
    return grows, qrows


def summary(grows, qrows):
    no = [x for x in grows if x[0].grade == "no"]
    ok = [x for x in grows if x[0].grade in ("good", "ok")]
    no_rej = sum(not all(x[2].values()) for x in no)
    ok_kept = sum(all(x[2].values()) for x in ok)
    listed = [x for x in qrows if x[1]["ok"]]
    kept = [x for x in listed if all(x[2].values())]
    big = sum(x[0]["big_winner"] == "1" for x in kept)
    cls = Counter(label_class(x[0]["his_label"]) for x in listed)
    clk = Counter(label_class(x[0]["his_label"]) for x in kept)
    return dict(no_rej=no_rej, no_n=len(no), ok_kept=ok_kept, ok_n=len(ok), listed=len(listed), kept=len(kept), big=big,
                okb_kept=clk["ok_or_better"], okb_n=cls["ok_or_better"], neg_kept=clk["no_or_ep"], neg_n=cls["no_or_ep"],
                tim_kept=clk["timing_or_unsure"], tim_n=cls["timing_or_unsure"], unl_kept=clk["unlabelled"], unl_n=cls["unlabelled"])


def line(s):
    return (f"no rejected {s['no_rej']}/{s['no_n']} | good/ok kept {s['ok_kept']}/{s['ok_n']} | QM buys kept {s['kept']}/269 "
            f"(of {s['listed']} on today's list) | big winners {s['big']}/26 | his ok-or-better QM {s['okb_kept']}/{s['okb_n']} | "
            f"his no/EP QM still kept {s['neg_kept']}/{s['neg_n']} | timing/unsure {s['tim_kept']}/{s['tim_n']} | unlabelled {s['unl_kept']}/{s['unl_n']}")


grows, qrows = evaluate()
S = summary(grows, qrows)
print("\n=== HEADLINE ===")
print(line(S))
print(f"bars: (1) {S['no_n']}/{S['no_n']} {'PASS' if S['no_rej'] == S['no_n'] else 'FAIL'} | (1b) >=80% of {S['ok_n']} {'PASS' if S['ok_kept'] >= 0.8 * S['ok_n'] else 'FAIL'} | "
      f"(2) 263/269 + 26/26 {'PASS' if S['kept'] >= 263 and S['big'] == 26 else 'FAIL'} | "
      f"(2b) >=80% ok-or-better {'PASS' if S['okb_kept'] >= 0.8 * S['okb_n'] else 'FAIL'} ({S['okb_kept'] / max(1, S['okb_n']):.0%})")

print("\n=== (1) HIS LIST GRADES, row by row (n = 29) ===")
hdr = "night       ticker grade        rank  " + " ".join(f"{k[:12]:12s}" for k in ACTIVE) + "  verdict   values"
print(hdr)
for g, v, p, sg in grows:
    val = (f"since_bottom {sg['higher_lows']['value']['sessions_since_bottom']} | undercut {len(sg['no_lower_low']['value']['undercut_swing_lows'])} | "
           f"e10 {sg['rising_avg']['value']['ema10'] / sg['rising_avg']['value']['ema10_prev'] - 1:+.1%} e21 {sg['rising_avg']['value']['ema21'] / sg['rising_avg']['value']['ema21_prev'] - 1:+.1%} | "
           f"ext {sg['not_extended']['value']['close_vs_ema10_adr']:+.2f} | spread10 {sg['tight10']['value']['spread10_adr']:.2f} | existing failed (rs aside) {v['failed']}")
    print(f"{g.list_date}  {g.ticker:6s} {g.grade:12s} {g.list_rank:4d}  " + " ".join(f"{'pass' if p[k] else 'FAIL':12s}" for k in ACTIVE)
          + f"  {'KEPT' if all(p.values()) else 'rejected':9s} {val}")

print("\n=== per-gate on his grades: which gate rejects which `no`, which drops which good/ok ===")
for k in ACTIVE:
    rej = [x[0].ticker for x in grows if x[0].grade == "no" and not x[2][k]]
    alone = [x[0].ticker for x in grows if x[0].grade == "no" and not x[2][k] and sum(not q for q in x[2].values()) == 1]
    drop = [f"{x[0].ticker}({x[0].grade})" for x in grows if x[0].grade in ("good", "ok") and not x[2][k]]
    print(f"  {k:13s} rejects {len(rej):2d}/{sum(x[0].grade == 'no' for x in grows)} no {rej} (alone: {alone}) | drops {len(drop)}/{sum(x[0].grade in ('good', 'ok') for x in grows)} good/ok {drop}")
print("  `no` rows that pass EVERY gate:", [x[0].ticker for x in grows if x[0].grade == "no" and all(x[2].values())])
print("  conditional row:", [(x[0].ticker, 'kept' if all(x[2].values()) else 'rejected by ' + str([k for k in ACTIVE if not x[2][k]])) for x in grows if x[0].grade == "conditional"])

print("\n=== (2) QULLAMAGGIE'S BUYS: per-gate miss table (n = 269; 263 on today's list) ===")
listed = [x for x in qrows if x[1]["ok"]]
print("gate          | buys it blocks (any) | blocks ALONE | big winners blocked (any) | ok-or-better blocked | no/EP blocked")
for k in ACTIVE:
    blk = [x for x in listed if not x[2][k]]
    alone = [x for x in blk if sum(not q for q in x[2].values()) == 1]
    print(f"  {k:13s} {len(blk):4d} ({len(blk) / len(listed):.0%})        {len(alone):4d}         {sum(x[0]['big_winner'] == '1' for x in blk):3d}                    "
          f"{sum(label_class(x[0]['his_label']) == 'ok_or_better' for x in blk):3d}                  {sum(label_class(x[0]['his_label']) == 'no_or_ep' for x in blk):3d}")
print("number of shape gates failing per listed buy:", dict(sorted(Counter(sum(not q for q in x[2].values()) for x in listed).items())))
by_year = Counter(x[0]["E"][:4] for x in listed)
kept_year = Counter(x[0]["E"][:4] for x in listed if all(x[2].values()))
print("kept by year:", {y: f"{kept_year[y]}/{by_year[y]}" for y in sorted(by_year)})

print("\n=== Qullamaggie buys DROPPED by the shape gates (on today's list, off the gated one) ===")
for r, v, p, sg in listed:
    if not all(p.values()):
        print(f"  {r['sym']:6s} buy {r['E']}  big={r['big_winner']}  label[{r['his_label'] or '-'}]  fails {[k for k in ACTIVE if not p[k]]}")

print("\n=== his LABELLED Qullamaggie buys, kept or dropped ===")
for cls in ("ok_or_better", "no_or_ep", "timing_or_unsure"):
    rows = [x for x in listed if label_class(x[0]["his_label"]) == cls]
    print(f"  {cls}: kept {sum(all(x[2].values()) for x in rows)}/{len(rows)}")
    for r, v, p, sg in rows:
        print(f"     {r['sym']:6s} {r['E']} [{r['his_label']}] {'KEPT' if all(p.values()) else 'dropped by ' + str([k for k in ACTIVE if not p[k]])}")

print("\n=== SWEEPS (reported, not used to choose; each row = the full set with ONE number moved) ===")
base = {k: getattr(bv, k) for k in ("SHAPE_HL_RECENT", "SHAPE_LOWER_LOW_ADR", "SHAPE_RISING_SESSIONS", "SHAPE_EXTENDED_ADR_MAX", "SHAPE_TIGHT_ADR_MAX")}
if a.only:
    base = {k: getattr(bv, k) for k in ("SHAPE_BASE_ABOVE_ADR_MAX", "SHAPE_E21_S50_ADR_MIN")}
SWEEPS = (("SHAPE_BASE_ABOVE_ADR_MAX", (0.0, 0.25, 0.5, 1.0)), ("SHAPE_E21_S50_ADR_MIN", (-1.5, -1.25, -1.0, -0.75, -0.5, 0.0))) if a.only else (("SHAPE_HL_RECENT", (3, 5, 10)), ("SHAPE_LOWER_LOW_ADR", (0.5, 1.0, 1.5, 1e9)), ("SHAPE_RISING_SESSIONS", (3, 5, 10)),
          ("SHAPE_EXTENDED_ADR_MAX", (0.5, 1.0, 1.5, 2.0)), ("SHAPE_TIGHT_ADR_MAX", (3.0, 4.0, 5.0, 6.0)))
for name, vals in SWEEPS:
    for val in vals:
        setattr(bv, name, val)
        print(f"  {name}={'none' if val == 1e9 else val}: {line(summary(*evaluate()))}")
    setattr(bv, name, base[name])

print("\n=== each gate ALONE (the existing rules + that one gate) and LEAVE-ONE-OUT ===")
full = ACTIVE[:]
for k in full:
    ACTIVE[:] = [k]
    print(f"  only {k:13s}: {line(summary(*evaluate()))}")
for k in full:
    ACTIVE[:] = [g for g in full if g != k]
    print(f"  without {k:13s}: {line(summary(*evaluate()))}")
ACTIVE[:] = full
