"""Amendment 3 (round 3): amendment 2's four gates + ONE trend-context variant, each scored once.
    python3 scripts/probes/_717_shape_gates_1111/08_score_amendment3.py > scripts/probes/_717_shape_gates_1111/08_score_amendment3.out
Per variant: his 17 `no` / 11 good-ok, Qullamaggie's 263 listed buys + 26 big winners (bars <= D only), the survivors
among the 190 names of list night 2026-11-10 (10_sheet_latest_list.out) and which of the 12 letters of the amendment-2
sheet (bought_sheet.png.key_do_not_show.txt) it removes — the letters are REPORTED, never used to pick."""
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
ALL = bv.SHAPE_GATES_V2 + bv.SHAPE_TREND_GATES


def passes(b, D, rs=99.0, raw=None):
    v = bv.v1_gates(b, D, rs_best=rs, raw_close=raw)
    if not v["ok"]:
        return None
    sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
    return {k: sg[k]["pass"] for k in ALL}


def mk(rows, keys="ohlcv", dkey="date"):
    return cb.daily_bars_from_arrays([date.fromisoformat(x[dkey]) for x in rows], *[[float(x[k]) for x in rows] for k in keys])


def load():
    gb = defaultdict(list)
    with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            gb[(r["ticker"], r["list_date"])].append(r)
    G = []
    for g in BREAKOUT_LIST_GRADES:
        b = mk(gb[(g.ticker, g.list_date)])
        G.append((g, b, len(b) - 1))
    FX = Path("tests/fixtures/qm_breakout_scorecard")
    by = defaultdict(list)
    with gzip.open(FX / "bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    Q = []
    for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"):
        rr = sorted(by[r["eid"]], key=lambda x: x["date"])
        D = [x["date"] for x in rr].index(r["D"])
        Q.append((r, mk(rr[:D + 1]), D))
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
    N = [(t, mk(bars[t]), len(bars[t]) - 1) for t in lst]
    letters = {}
    for line in open(HERE + "bought_sheet.png.key_do_not_show.txt"):
        p = line.strip().split("|")
        if len(p) == 5 and len(p[0]) == 1 and p[0].isalpha():
            letters[p[1]] = p[0]
    return G, Q, N, letters


G, Q, N, LET = load()


def run(label):
    pg = [(g, passes(b, D)) for g, b, D in G]
    pq = [(r, passes(b, D, float(r["rs_best"]), float(r["raw_close_D"]))) for r, b, D in Q]
    pn = [(t, passes(b, D)) for t, b, D in N]
    out = {}
    for name, gates in [("amendment 2 alone", bv.SHAPE_GATES_V2)] + [(f"+ {t}", bv.SHAPE_GATES_V2 + (t,)) for t in bv.SHAPE_TREND_GATES]:
        ok = lambda p: p is not None and all(p[k] for k in gates)
        no_pass = sorted(g.ticker for g, p in pg if g.grade == "no" and ok(p))
        gk = [g.ticker for g, p in pg if g.grade in ("good", "ok") and ok(p)]
        gd = sorted(g.ticker for g, p in pg if g.grade in ("good", "ok") and not ok(p))
        qk = [r for r, p in pq if ok(p)]
        base = {(r["sym"], r["E"]) for r, p in pq if p is not None and all(p[k] for k in bv.SHAPE_GATES_V2)}
        extra = sorted(f"{r['sym']} {r['E']}{' BIG' if r['big_winner'] == '1' else ''}[{r['his_label'] or '-'}]" for r, p in pq
                       if (r["sym"], r["E"]) in base and not ok(p))
        surv = [t for t, p in pn if ok(p)]
        gone = sorted(LET[t] for t, p in pn if t in LET and not ok(p))
        print(f"\n[{label}] {name}")
        print(f"  no rejected {17 - len(no_pass)}/17 (still pass: {no_pass}) | good/ok kept {len(gk)}/11 (dropped {gd})")
        print(f"  Qullamaggie buys kept {len(qk)}/263 | big winners {sum(r['big_winner'] == '1' for r in qk)}/26 | blocked on top of amendment 2: {len(extra)} {extra}")
        print(f"  list night 2026-11-10: {len(surv)} of {len(pn)} survive | sheet letters removed: {gone or 'none'} ({[t for t in LET if LET[t] in gone]})")
        n_na = sum(1 for r, b, D in Q if cb._sma_at(b, D, 200) is None)
        out[name] = (17 - len(no_pass), len(gk), len(qk))
    print(f"  (Qullamaggie buys with no 200-day at D: {n_na} of {len(Q)}; they do not fail the trend gate)")


run("pre-registered: SMA200 slope over 20 sessions")
for w in (10, 40):
    bv.SHAPE_SMA200_RISING_SESSIONS = w
    run(f"plateau check: slope over {w} sessions (T3 / T4 only move)")
bv.SHAPE_SMA200_RISING_SESSIONS = 20
