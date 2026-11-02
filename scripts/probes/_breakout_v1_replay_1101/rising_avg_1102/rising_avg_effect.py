"""G4 rising averages (DEFINITIONS.md, committed 512a5bef BEFORE this ran) on the frozen paper-baseline replay. Read-only.
Same pattern as shape_gates_1102/shape_gates_effect.py: a tighter gate only REMOVES list rows, so the walked outcomes
(out/trades.tsv.gz) are re-booked on the subset (5 slots, 2c), on top of the 4.26% floor. Writes rise_rows.tsv.gz and
rising_avg_effect.txt."""
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
REPO = HERE.parents[3]
for p in (REPO, PROBE, PROBE / "followup_tests_1101", PROBE / "shape_gates_1102"):
    sys.path.insert(0, str(p))
from agents.market_intelligence import breakout_v1 as bv            # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner                       # noqa: E402
from shape_gates_effect import STORES, SEAL                          # noqa: E402  (the same sealed stores)

ROWS = HERE / "rise_rows.tsv.gz"
XS = (0.03, 0.04, 0.05, 0.06, 0.07)
X0 = 0.05
QM12 = (("CELH-1", "CELH", "2020-06-22"), ("CELH-3", "CELH", "2020-08-04"), ("CODX-1", "CODX", "2020-04-15"),
        ("LVGO-4", "LVGO", "2020-07-02"), ("OPK-2", "OPK", "2020-07-16"), ("OSTK-2", "NXH", "2020-06-22"),
        ("SRNE-2", "SRNE", "2020-07-30"), ("PRTS", "PRTS", "2020-07-07"), ("ARCT", "ARCT", "2020-07-10"),
        ("HL", "HL", "2020-08-03"), ("IBIO-1", "IBIO", "2020-07-14"), ("PENN-2", "PENN", "2020-06-22"))
lines = []


def say(s=""):
    print(s, flush=True)
    lines.append(s)


def ema(x, n=21):
    a, out = 2 / (n + 1), np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rise_at(bars, D):
    """EMA21(D)/EMA21(P) - 1, bars <= D only (EMA is causal; computed on the cut series to make that literal)."""
    P = cb._pole_top(bars.h, bars.c, D - bv.BASE_MAX, D - bv.BASE_MIN)
    e = ema(np.asarray(bars.c[:D + 1], float))
    return float(e[D] / e[P] - 1), P


def stage_rows():
    out, parity = [], Counter()
    for era in ("A", "B"):
        lst = pd.read_csv(PROBE / "out" / f"list_era{era}.tsv.gz", sep="\t", keep_default_na=False)
        Dd = runner.load_daily(STORES[era])
        assert Dd.cal[-1] < SEAL, Dd.cal[-1]
        for t, grp in lst.groupby("ticker"):
            bars, _ = runner.bars_for(Dd, Dd.tid[t])
            pos = {d: i for i, d in enumerate(bars.dates)}
            full = ema(np.asarray(bars.c, float))
            for r in grp.itertuples(index=False):
                D = pos[date.fromisoformat(r.scan_date)]
                P = cb._pole_top(bars.h, bars.c, D - bv.BASE_MAX, D - bv.BASE_MIN)
                parity["pole_ok" if str(bars.dates[P]) == r.pole_date else "pole_MISMATCH"] += 1
                rise = float(full[D] / full[P] - 1)
                if len(out) % 997 == 0:           # look-ahead check: recomputed on bars cut at D
                    parity["cut_ok" if abs(rise_at(bars, D)[0] - rise) < 1e-12 else "cut_MISMATCH"] += 1
                out.append({"key": f"{r.E}|{t}", "scan_date": r.scan_date, "ticker": t, "rise21": rise})
        if era == "A":
            say("Qullamaggie's 12 graded setups v1 catches (catching watch night D), EMA21 rise across the base:")
            qm = []
            for name, t, d in QM12:
                bars, _ = runner.bars_for(Dd, Dd.tid[t])
                D = list(bars.dates).index(date.fromisoformat(d))
                rise, P = rise_at(bars, D)
                qm.append(rise)
                say(f"  {name:7s} D {d}  pole top {bars.dates[P]}  rise {rise:+.1%}  " + "  ".join(
                    f"{int(x * 100)}%:{'pass' if rise >= x else 'FAIL'}" for x in XS))
            for x in XS:
                say(f"  kept at {int(x * 100)}%: {sum(r >= x for r in qm)} of 12   (bar (b): >= 10)")
        del Dd
    rows = list(csv.DictReader(open(REPO / "scripts/probes/_mtw_1102/mtw_bars.csv")))
    c = np.array([float(r["close"]) for r in rows]); dts = [r["trade_date"] for r in rows]
    e = ema(c); D = dts.index("2026-10-30"); P = dts.index("2026-10-06")
    mtw = float(e[D] / e[P] - 1)
    say(f"MTW 10-30 (his NO; pole top 10-06 as the live list row): rise {mtw:+.1%}  " + "  ".join(
        f"{int(x * 100)}%:{'pass' if mtw >= x else 'FAIL'}" for x in XS) + "   (bar (a): FAIL wanted)")
    pd.DataFrame(out).to_csv(ROWS, sep="\t", index=False, compression="gzip")
    say(f"parity {dict(parity)}")
    assert not any("MISMATCH" in k for k in parity), parity


def stage_book():
    import v1_replay as V
    import followup as F
    g = pd.read_csv(ROWS, sep="\t").set_index("key")["rise21"]
    rows = F.load_placed()
    sessions = sorted({t["E"] for t in rows})
    for t in rows:
        t["rise21"] = float(g.loc[t["key"]])
    floor = [t for t in rows if t["adr20"] is not None and float(t["adr20"]) >= bv.ADR_MIN]
    dec = lambda ts: [t for t in ts if t["filled"] and t["decisive"] and t["r_2c"] is not None]

    def mean(ts):
        r = [t["r_2c"] for t in dec(ts)]
        return (len(r), float(np.mean(r)) if r else float("nan"), float(np.mean(np.array(r) >= 3)) if r else float("nan"))

    def book5(kept):
        b = V.apply_book([dict(t) for t in kept], slots=V.CAP_SLOTS, safeguards=False, sessions=sessions)
        return [t for t in kept if b["admitted"].get(t["key"])]

    say(f"\nplaced name-days {len(rows)}; floor-kept {len(floor)}; list rows passing 5%: {(g >= X0).mean():.0%}")
    base = book5(floor)
    say("BASELINE floor only, 5-slot: " + "; ".join(
        f"{e} n {mean([t for t in base if t['era'] == e])[0]} mean {mean([t for t in base if t['era'] == e])[1]:+.3f}"
        for e in ("2017-21", "2022-24")))
    rng = np.random.default_rng(1102)
    for x in XS:
        kept = [t for t in floor if t["rise21"] >= x]
        removed = [t for t in floor if t["rise21"] < x]
        adm = book5(kept)
        nk, mk, _ = mean(kept); nr, mr, _ = mean(removed)
        say(f"\n== G4 at {int(x * 100)}% ==  orders removed {len(removed)} of {len(floor)} ({len(removed) / len(floor):.0%})")
        say(f"  (c2) no slot limit, pooled: kept n {nk} mean {mk:+.3f} | removed n {nr} mean {mr:+.3f} -> "
            f"{'PASS' if mr < mk else 'FAIL'}")
        share = len(kept) / len(floor)
        draws = {"2017-21": [], "2022-24": []}
        for _ in range(200):
            keep = rng.random(len(floor)) < share
            radm = book5([t for t, k in zip(floor, keep) if k])
            for e in draws:
                draws[e].append(mean([t for t in radm if t["era"] == e])[1])
        for e, bar in (("2017-21", -0.139), ("2022-24", -0.340)):
            n, m, r3 = mean([t for t in adm if t["era"] == e])
            d = np.array(draws[e])
            say(f"  {e}: 5-slot n {n} mean {m:+.3f} 3R+ {r3:.1%}  (c1 >= {bar}: {'PASS' if m >= bar else 'FAIL'}; "
                f"c3 n>=100: {'PASS' if n >= 100 else 'FAIL'})  random median {np.median(d):+.3f}, random beats it in "
                f"{np.mean(d >= m):.0%} (c4 < 25%: {'PASS' if np.mean(d >= m) < 0.25 else 'FAIL'})")
    (HERE / "rising_avg_effect.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    stage_rows()
    stage_book()
