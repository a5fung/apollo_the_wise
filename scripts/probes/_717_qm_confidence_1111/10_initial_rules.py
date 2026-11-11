#!/usr/bin/env python3


RECORD: run at 16c12402 or earlier — it reads `breakout_v1`'s list constants as they were BEFORE the 2026-11-11 initial
rule set was wired, and does not reproduce on a later commit."""#717: SCORE the pre-registered initial rule set (docs/analysis/cb_initial_rules_2026-11-11.md), once.

    python3 scripts/probes/_717_qm_confidence_1111/10_initial_rules.py > scripts/probes/_717_qm_confidence_1111/10_initial_rules.out"""
import contextlib
import csv
import gzip
import importlib
import io
import sys
from collections import Counter, defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
with contextlib.redirect_stdout(io.StringIO()):
    m = importlib.import_module("03_high_vs_list")
import range_break as rb  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES  # noqa: E402

NEW = dict(m.BASE, prior=0.20, s50=None, e21=-0.9, dmax=11.0)
ALT = dict(NEW, s50=-0.03)
T = lambda x: x["r"]["tier"]  # noqa: E731


def night(x):
    """The night D before the rated break day."""
    D = x["r"]["t"] - 1
    return next(n for n in x["nights"] if n["D"] == D)


def unmeasured(x, n):
    return x["b"]["set"] == "widened" and (n["val"] is None or n["val"]["rs"] is None)


def listed(x, P):
    """(kept by every measurable gate, note). An unranked widened night is scored without rs (and the $2 floor ran on the adjusted close)."""
    n = night(x)
    if n["val"] is None:
        return False, "history"
    if unmeasured(x, n):
        return m.night_ok(n, dict(P, rs=None)), "rs/$2 not measurable"
    return m.night_ok(n, P), ""


def port(x):
    b = x["b"]
    D = x["r"]["t"] - 1
    lv = rb.range_levels(b["h"], b["l"], D)
    k = rb.triggered(lv, rb.vol_bar20(b["v"], D), b["h"][D + 1], b["c"][D + 1], b["v"][D + 1])
    rng = rb.avg_range(b["h"], b["l"], D)
    dist = None if k is None else (k["level"] - b["c"][D]) / rng
    return k, dist


print("=== (i) THE 84 HIGH-TIER BUYS ===")
high = [x for x in m.rows if T(x) == "High"]
bought, dists, notlisted, notes = 0, [], [], Counter()
for x in high:
    k, dist = port(x)
    same = k is not None and abs(k["level"] - x["r"]["level"]) < 1e-9
    bought += bool(same)
    if not same:
        print(f"  PORT MISMATCH {x['b']['ticker']} {x['b']['hi']}: rating level {x['r']['level']}, port {k}")
    dists.append((dist, x))
    ok, note = listed(x, NEW)
    notes[note] += 1
    if not ok:
        notlisted.append((x, note, night(x)["failed"]))
print(f"bought on E by the port (same buy point as the rating): {bought} of {len(high)}")
print(f"listed at D by the initial list rules: {len(high) - len(notlisted)} of {len(high)}   (scored without rs / $2: {notes['rs/$2 not measurable']})")
for x, note, failed in notlisted:
    v = night(x)["val"]
    print(f"  NOT LISTED {x['b']['ticker']} {x['b']['hi']} [{note}] today's failed gates {failed}  val {v}")
print("  unranked High nights (rs and the $2 floor not measurable): " + ", ".join(f"{x['b']['ticker']} {x['b']['hi']}" for x in high if unmeasured(x, night(x))))
alt = [x for x in high if not listed(x, ALT)[0]]
print(f"alternative (3% under the 50-day instead of dropped): listed {len(high) - len(alt)} of {len(high)}; drops " + ", ".join(f"{x['b']['ticker']} {x['b']['hi']}" for x in alt))
print("distance from the close of D up to the buy point, in average daily ranges:")
ds = sorted(d for d, _ in dists if d is not None)
print(f"  median {np.median(ds):.2f}, 90th pct {np.percentile(ds, 90):.2f}, max {ds[-1]:.2f}")
for X in (1.0, 1.5, 2.0, 3.0):
    out = [x for d, x in dists if d is None or d > X]
    print(f"  ready at X = {X}: {len(high) - len(out)} of {len(high)}" + ("" if not out else "   not ready: " + ", ".join(f"{x['b']['ticker']} {x['b']['hi']}" for x in out[:12])))
X = next((X for X in (1.0, 1.5, 2.0, 3.0) if all(d is not None and d <= X for d, _ in dists)), 3.0)
print(f"X chosen on the 84 only: {X}")

print("\n=== (ii) MEDIUM TIER (the port is the High-tier trigger, so a Medium buy is bought only if the daily bar also meets it) ===")
for s in ("dated", "widened"):
    g = [x for x in m.rows if T(x) == "Medium" and x["b"]["set"] == s]
    li = sum(listed(x, NEW)[0] for x in g)
    li0 = sum(listed(x, m.BASE)[0] for x in g)
    bo = sum(port(x)[0] is not None for x in g)
    rd = sum(rb.ready(rb.range_levels(x["b"]["h"], x["b"]["l"], x["r"]["t"] - 1), x["b"]["c"][x["r"]["t"] - 1], rb.avg_range(x["b"]["h"], x["b"]["l"], x["r"]["t"] - 1), X) is not None for x in g)
    print(f"  {s:8s} n = {len(g)}: listed {li} (today's gates {li0}); ready the night before {rd}; bought by the High trigger {bo}")

# ── his graded list charts ────────────────────────────────────────────────────────────────────────────────────
gb = defaultdict(list)
with gzip.open("tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
    for r in csv.DictReader(f, delimiter="|"):
        gb[(r["ticker"], r["list_date"])].append(r)


def gate_val(b, D):
    v = bv.v1_gates(b, D, rs_best=99.0)                      # it was on the list that night: rank passes
    g = v["gates"]
    return dict(D=D, failed=v["failed"], ok=v["ok"], val=dict(
        universe=g["universe"]["pass"], pinned=g["pinned"]["pass"], adr=g["adr"]["pass"], rs=99.0,
        prior=g["prior_move"]["value"]["prior_move"], depth=g["base_depth"]["value"]["depth_adr"], e21=g["ema21"]["value"]["vs_ema21_adr"],
        s50=(v["close"] / g["sma50"]["value"]["sma50"] - 1) if isinstance(g["sma50"]["value"], dict) and g["sma50"]["value"].get("sma50") else None))


def chart_state(b, D):
    h, l, c = np.asarray(b.h, float), np.asarray(b.l, float), np.asarray(b.c, float)
    n = gate_val(b, D)
    lv = rb.range_levels(h, l, D)
    rng = rb.avg_range(h, l, D)
    out = dict(listed=m.night_ok(n, NEW), listed_today=n["ok"], n_ranges=len(lv))
    for x in (1.0, 1.5, 2.0, 3.0):
        k = rb.ready(lv, c[D], rng, x)
        out[x] = k
    out["nearest"] = None if not lv else (lv[0]["level"] - c[D]) / rng
    return out


print("\n=== (iii) / (iv) HIS 41 GRADED LIST CHARTS at their list night ===")
rej, keep = [], []
for g in BREAKOUT_LIST_GRADES:
    rr = gb[(g.ticker, g.list_date)]
    ds = [date.fromisoformat(x["date"]) for x in rr]
    b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
    st = chart_state(b, len(ds) - 1)
    (rej if g.grade in ("no", "conditional") else keep).append((g, st))
    k = st[X]
    print(f"  {g.grade:11s} {g.ticker:5s} {g.list_date} listed {int(st['listed'])} ranges {st['n_ranges']} nearest {'-' if st['nearest'] is None else format(st['nearest'], '.2f'):>5s} "
          f"READY {'-' if k is None else format(k['level'], '.4g') + ' len ' + str(k['len'])}")
for name, grp in (("his 28 no / not-yet", rej), ("his 13 good / ok", keep)):
    print(f"{name} (n = {len(grp)}): listed {sum(s['listed'] for _, s in grp)}; ready to trigger at X = "
          + ", ".join(f"{x}: {sum(s[x] is not None for _, s in grp)}" for x in (1.0, 1.5, 2.0, 3.0)) + f"   (X in force: {X})")
print("  READY among the 28: " + (", ".join(f"{g.ticker} {g.list_date} ({g.grade}: {g.operator_words[:40]})" for g, s in rej if s[X] is not None) or "none"))
print("  READY among the 13: " + (", ".join(f"{g.ticker} {g.list_date}" for g, s in keep if s[X] is not None) or "none"))

# ── list night 2026-11-10 ─────────────────────────────────────────────────────────────────────────────────────
lst, bars, sec = [], defaultdict(list), None
for line in open("scripts/probes/_717_shape_gates_1111/10_sheet_latest_list.out"):
    line = line.strip()
    if line.startswith("== "):
        sec = line[3:]
    elif sec == "LIST" and line[:2] == "20":
        lst.append(line.split("|"))
    elif sec == "BARS" and line.count("|") == 6 and line.split("|")[1][:2] == "20":
        t, d, o, h, l, c, v = line.split("|")
        bars[t].append((date.fromisoformat(d), float(o), float(h), float(l), float(c), float(v)))
print(f"\n=== (v) LIST NIGHT {lst[0][0]}: {len(lst)} names on today's list ===")
rd = []
for d, t, rk, lvl, *_ in lst:
    rows_ = bars[t]
    b = cb.daily_bars_from_arrays([x[0] for x in rows_], *[[x[i] for x in rows_] for i in range(1, 6)])
    st = chart_state(b, len(b) - 1)
    if st[X] is not None:
        rd.append((int(rk), t, st[X]["level"], st[X]["len"], float(lvl), st["listed"]))
print(f"ready to trigger at X = {X}: {len(rd)} of {len(lst)}  (at 1.0 / 1.5 / 2.0 / 3.0 the loop above is re-run below)")
for rk, t, level, n, lvl5, li in sorted(rd):
    print(f"  rank {rk:3d} {t:6s} range high {level:.4g} (range {n} sessions)   today's 5-day level {lvl5:.4g}   kept by the loosened gates {int(li)}")
