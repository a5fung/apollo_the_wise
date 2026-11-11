"""Amendment 4 (round 4): amendment 2's four gates + ONE right-edge tightness variant, each scored once.
    python3 scripts/probes/_717_shape_gates_1111/09_score_amendment4.py > scripts/probes/_717_shape_gates_1111/09_score_amendment4.out
Labels: his 41 graded name-nights (23 no + 5 conditional = 28 must-REJECT; 13 good/ok), keyed on ticker + night.
Qullamaggie's 263 listed buys + 26 big winners (bars <= D only). The 190 names of list night 2026-11-10 and the 12
letters of the amendment-2 sheet. Also prints every measure per label row (for the scope finding)."""
import csv
import gzip
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES  # noqa: E402

HERE = "scripts/probes/_717_shape_gates_1111/"
ALL = bv.SHAPE_GATES + bv.SHAPE_GATES_V2 + bv.SHAPE_TIGHT_GATES


def shape(b, D, rs=99.0, raw=None):
    v = bv.v1_gates(b, D, rs_best=rs, raw_close=raw)
    if not v["ok"]:
        return None
    return bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])


def mk(rows):
    return cb.daily_bars_from_arrays([date.fromisoformat(x["date"]) for x in rows], *[[float(x[k]) for x in rows] for k in "ohlcv"])


gb = defaultdict(list)
with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        gb[(r["ticker"], r["list_date"])].append(r)
G = [(g, mk(gb[(g.ticker, g.list_date)])) for g in BREAKOUT_LIST_GRADES]
FX = Path("tests/fixtures/qm_breakout_scorecard")
by = defaultdict(list)
with gzip.open(FX / "bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        by[r["eid"]].append(r)
Q = []
for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
    rr = sorted(by[r["eid"]], key=lambda x: x["date"])
    D = [x["date"] for x in rr].index(r["D"])
    Q.append((r, mk(rr[:D + 1])))
lst, bars, sec = [], defaultdict(list), None
for line in open(HERE + "10_sheet_latest_list.out"):
    line = line.strip()
    if line.startswith("== "):
        sec = line[3:]
    elif sec == "LIST" and line[:2] == "20":
        lst.append(line.split("|")[1])
    elif sec == "BARS" and line.count("|") == 6 and line.split("|")[1][:2] == "20":
        t, d, o, h, l, c, v = line.split("|")
        bars[t].append({"date": d, "o": o, "h": h, "l": l, "c": c, "v": v})
N = [(t, mk(bars[t])) for t in lst]
LET = {}
for line in open(HERE + "bought_sheet.png.key_do_not_show.txt"):
    p = line.strip().split("|")
    if len(p) == 5 and len(p[0]) == 1 and p[0].isalpha():
        LET[p[1]] = p[0]
REJ = ("no", "conditional")


def run(label, variants):
    sg_g = [(g, shape(b, len(b) - 1)) for g, b in G]
    sg_q = [(r, shape(b, len(b) - 1, float(r["rs_best"]), float(r["raw_close_D"]))) for r, b in Q]
    sg_n = [(t, shape(b, len(b) - 1)) for t, b in N]
    base_q = {(r["sym"], r["E"]) for r, p in sg_q if p is not None and all(p[k]["pass"] for k in bv.SHAPE_GATES_V2)}
    for name, gates in variants:
        ok = lambda p: p is not None and all(p[k]["pass"] for k in gates)
        rej_pass = sorted(f"{g.ticker} {g.list_date[5:]}({g.grade[:4]})" for g, p in sg_g if g.grade in REJ and ok(p))
        gd = sorted(f"{g.ticker} {g.list_date[5:]}({g.grade})" for g, p in sg_g if g.grade in ("good", "ok") and not ok(p))
        n_rej = sum(g.grade in REJ for g, _ in sg_g)
        n_ok = sum(g.grade in ("good", "ok") for g, _ in sg_g)
        qk = [r for r, p in sg_q if ok(p)]
        extra = sorted(f"{r['sym']} {r['E']}{' BIG' if r['big_winner'] == '1' else ''}[{r['his_label'] or '-'}]" for r, p in sg_q
                       if (r["sym"], r["E"]) in base_q and not ok(p))
        surv = [t for t, p in sg_n if ok(p)]
        gone = sorted(LET[t] for t, p in sg_n if t in LET and not ok(p))
        print(f"\n[{label}] {name}")
        print(f"  no+conditional rejected {n_rej - len(rej_pass)}/{n_rej} | still pass: {rej_pass}")
        print(f"  good/ok kept {n_ok - len(gd)}/{n_ok} | dropped: {gd}")
        print(f"  Qullamaggie buys kept {len(qk)}/263 | big winners {sum(r['big_winner'] == '1' for r in qk)}/26 | blocked on top of amendment 2: {len(extra)} {extra}")
        print(f"  list night 2026-11-10: {len(surv)} of {len(sg_n)} survive | sheet letters removed: {gone or 'none'}")
    return sg_g


V2 = bv.SHAPE_GATES_V2
sg_g = run("pre-registered", [("amendment 2 alone", V2)] + [(f"+ {t}", V2 + (t,)) for t in bv.SHAPE_TIGHT_GATES])
for const, gate, vals in (("SHAPE_RC_MAX", "range_contract", (1.0, 1.25)), ("SHAPE_C5_ADR_MAX", "tight_closes5", (1.0, 2.0)),
                          ("SHAPE_TIGHT_RUN", "tight_run3", (2, 4))):
    keep = getattr(bv, const)
    for val in vals:
        setattr(bv, const, val)
        run(f"sweep {const}={val}", [(f"+ {gate}", V2 + (gate,))])
    setattr(bv, const, keep)

print("\n=== every measure on his 41 labels (pre-registered constants) — for the scope finding ===")
print(f"{'name night':14s}{'grade':12s}{'A2':5s}{'rc5v5':>7s}{'c5':>6s}{'run':>5s}{'spread10':>9s}{'ext10':>7s}{'since_bot':>10s}{'de10':>7s}{'de21':>7s}  words")
sg_g = [(g, shape(b, len(b) - 1)) for g, b in G]
for g, p in sorted(sg_g, key=lambda x: (x[0].grade not in ("good", "ok"), x[0].grade, x[0].list_date)):
    a2 = "pass" if all(p[k]["pass"] for k in V2) else "rej"
    ra = p["rising_avg"]["value"]
    print(f"{g.ticker + ' ' + g.list_date[5:]:14s}{g.grade:12s}{a2:5s}{p['range_contract']['value']['range5_over_prev5']:7.2f}"
          f"{p['tight_closes5']['value']['spread5_adr']:6.2f}{p['tight_run3']['value']['tight_days_in_a_row']:5d}"
          f"{p['tight10']['value']['spread10_adr']:9.2f}{p['not_extended']['value']['close_vs_ema10_adr']:7.2f}"
          f"{p['higher_lows']['value']['sessions_since_bottom']:10d}{ra['ema10'] / ra['ema10_prev'] - 1:7.1%}{ra['ema21'] / ra['ema21_prev'] - 1:7.1%}  {g.operator_words[:40]}")
