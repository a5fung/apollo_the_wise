#!/usr/bin/env python3
"""#702 P4b step 6 - the CENTER-OF-MASS breakout line, scored against his 58 drawn lines ($0: local files only; no model,
API, network or outcome read of any kind).

His rule (operator 2026-10-18, `docs/methodology/operator_shared_notes.md`): "he finds where the center of mass is in the
consolidation and ignore the outliers if it's just a short period, meaning a 1-3 bars spike then drop back to the basing
area"; earlier that day: tight and flat -> the base high, wide then tightening -> the flag line. Every reading of the
sentence is implemented ONCE, in the frozen module's `cb.com_level` (variants `cb.COM_VARIANTS`); this script only calls
it over a grid and scores the result. Nothing here re-implements a level.

INPUT (used as given): labels_p4b.tsv from step 5 (`p4b_label_join.py`) - 58 bases with a top/level line, their comparison
night (`cmp_night` = the last C0 watch night <= the screen date whose base matches), his line's value at the comparison
session (`line_value_cmp`, bar scale), `pivot_full`, `adr20`, `pole_idx`. The bars are the same arrays step 5 ran on
(Alpaca split-adjusted 2016-2022 via `ext_c0`; the one Polygon base via `p4b_label_join.load_polygon`); the script asserts
`cb.explain_watch` reproduces step 5's pivot_full / pivot_tl / adr20 on every base before scoring.

SCORE (step 5's unit): err = (rule level - his line) / pivot_full / adr20 at the comparison session - ADR20 units, positive =
the rule sits ABOVE his line. A reading with no level that night (a filtered line under 3 sessions old) is a MISS.
Reported per source (bar_verified 48 / eyeball_confirmed 10 - carried separately, never pooled away) and per his line's
slope class (flat 35 / falling 23): n, median |err|, median err (the bias), share within 0.25 / 0.5 / 1.0 ADR, and the share
of nights the level sits BELOW the comparison night's close.

THE GRID: max_run L in {1, 2, 3}; spike_adr T in {0.5, 0.75, 1.0, 1.5, 2.0, inf (= no filter: the existing level)};
quantile q in {0.3 .. 0.95}; falling_slope s in {0.05, 0.1, 0.2, 0.3, 0.5} % of the anchor high per session.
Families: flat_high(L,T) flat_close(L,T) tl_filtered(L,T) switch_high(L,T,s) switch_close(L,T,s) quantile(q).
GRID EXTENSION, declared: the first run used q in {0.5 .. 0.95} (the brief's "a HIGH quantile of the base's highs") and its
best cell sat ON THE GRID EDGE (q = 0.5, the lowest value tried: M 0.741; q = 0.6: 0.655), so the plateau could not be read
there. The q grid was extended DOWN to {0.3, 0.4, 0.45, 0.5, 0.55, 0.6, ...} and the run repeated. The pick rule below was
not changed; the first run's numbers are in the commit message.

PICK RULE - written BEFORE the grid was run (ADR 0023: a plateau, never a single best point):
  M(cell)  = the share of the 58 bases with |err| <= 0.5 ADR (a miss counts as outside).
  SE       = the bootstrap standard deviation of M at the best cell (2,000 resamples of the 58 bases, seed 702).
  plateau  = every cell with M >= M_best - SE.
  EXCLUDED first: a cell whose level sits below close(i) on MORE THAN HALF of the 58 nights is not a breakout level
  (the "breakout day" would be any day price is already above it); his own line's share is reported beside.
  the choice, among plateau cells: (1) a family must hold >= 2 plateau cells adjacent in its own grid (an isolated cell is a
  peak, not a plateau); (2) the simplest such family - free parameters: quantile 1 < flat_high = flat_close 2 <
  tl_filtered 2 < switch 3, ties in that order; (3) the CENTRE of the family's plateau region (the median grid position
  per parameter, ties -> the smaller value); (4) ties -> the lower median |err|.
  FLAG (n = 10, never a veto): a pick whose eyeball_confirmed M is below the best existing level's eyeball M.
  The runner-up = every other plateau cell, listed with the pick.

    python p4b_com_rule.py [--out DIR] [--fixture-out DIR]
Outputs (OUT = QM/vision/p4b_labels): com_grid_p4b.tsv (one row per grid cell x stratum), com_per_base_p4b.tsv (per base:
his line, every family's best cell level, the pick), summary_p4b_com.txt. `--fixture-out` writes the test fixture:
cb_p4b_labelled_bars.psv (ticker|date|o|h|l|c|v for the bars each fixture base needs) + cb_p4b_labels.tsv (derived numbers).
"""
import argparse
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ext_c0  # noqa: E402  (adds the repo + _cb_backtest to sys.path; read-only on the module)
import p4b_label_join as lj  # noqa: E402

cb = ext_c0.cb
EXT = lj.EXT
OUT = lj.OUT
LABELS = os.path.join(OUT, "labels_p4b.tsv")

L_GRID = (1, 2, 3)
T_GRID = (0.5, 0.75, 1.0, 1.5, 2.0, math.inf)
Q_GRID = (0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)
S_GRID = (0.0005, 0.001, 0.002, 0.003, 0.005)         # fraction of the anchor high per session (0.05 .. 0.5 %/session)
FAMILY_ORDER = ("quantile", "flat_high", "flat_close", "tl_filtered", "switch_high", "switch_close")
FAMILY_PARAMS = {"quantile": 1, "flat_high": 2, "flat_close": 2, "tl_filtered": 2, "switch_high": 3, "switch_close": 3}
EXISTING = ("pivot_full", "pivot_k10", "pivot_k5", "pivot_tl", "high_close", "high_body", "high_2nd")
TOLS = (0.25, 0.5, 1.0)
BOOT_DRAWS, BOOT_SEED = 2000, 702
FIXTURE_BASES = ("RIOT|2021-02-17", "SPOT|2020-07-22", "NIO|2020-11-24", "AMD|2021-11-30", "NCLH|2020-09-03")
FIXTURE_BACK = 140                                    # bars before the comparison night kept in the fixture


# ───────────────────────────── grid ─────────────────────────────
def grid_cells():
    """[(family, L, T, q, s)] - every cell of the grid, T = inf once (L is irrelevant there)."""
    cells = []
    for q in Q_GRID:
        cells.append(("quantile", None, None, q, None))
    for fam in ("flat_high", "flat_close", "tl_filtered"):
        for T in T_GRID:
            for L in ((3,) if T == math.inf else L_GRID):
                cells.append((fam, L, T, None, None))
    for fam in ("switch_high", "switch_close"):
        for T in T_GRID:
            for L in ((3,) if T == math.inf else L_GRID):
                for s in S_GRID:
                    cells.append((fam, L, T, None, s))
    return cells


def cell_name(c):
    fam, L, T, q, s = c
    if fam == "quantile":
        return f"quantile(q={q})"
    t = "inf" if T == math.inf else f"{T:g}"
    return f"{fam}(L={L},T={t})" if s is None else f"{fam}(L={L},T={t},s={s * 100:g}%)"


def level_for(cell, bars, P, i, adr):
    fam, L, T, q, s = cell
    kw = dict(variant=fam)
    if fam == "quantile":
        kw["quantile"] = q
    else:
        kw.update(max_run=L, spike_adr=T)
        if s is not None:
            kw["falling_slope"] = s
    return cb.com_level(bars, P, i, adr, **kw)


# ───────────────────────────── bases ─────────────────────────────
def load_bases():
    lab = pd.read_csv(LABELS, sep="\t", keep_default_na=False)
    P = lab[lab.primary_role.isin(["top", "level"])].copy().reset_index(drop=True)
    assert len(P) == 58, len(P)
    ev = ext_c0.Evaluator(EXT)
    out = []
    for rw in P.itertuples():
        if rw.bars_source == "polygon":
            g = lj.load_polygon(rw.ticker)
            dates = [dt.date.fromisoformat(x) for x in g.d]
            bars = cb.daily_bars_from_arrays(dates, g.o, g.h, g.l, g.c, g.v)
        else:
            S = ev.series(rw.ticker)
            bars = S.bars
        d = [x.isoformat() for x in bars.dates]
        i = d.index(rw.cmp_night)
        Pi = int(rw.pole_idx)
        assert d[Pi] == rw.pole_date, (rw.base, d[Pi], rw.pole_date)
        feat, gate = cb.explain_watch(bars, i)
        assert feat is not None, (rw.base, gate)
        for k, col in (("pivot_full", rw.c_pivot_full), ("pivot_k5", rw.c_pivot_k5), ("pivot_k10", rw.c_pivot_k10)):
            assert abs(feat[k] - float(col)) <= 1e-6 * float(col), (rw.base, k, feat[k], col)
        tl = feat["pivot_tl"]
        assert (tl is None and rw.c_pivot_tl == "") or abs(tl - float(rw.c_pivot_tl)) <= 1e-6 * float(rw.c_pivot_tl), (rw.base, tl, rw.c_pivot_tl)
        assert abs(feat["adr20"] - float(rw.adr20)) <= 1e-5, (rw.base, feat["adr20"], rw.adr20)     # the TSV carries 5 dp
        assert feat["pole_idx"] == Pi
        ex = {k: (None if getattr(rw, "c_" + k) == "" else float(getattr(rw, "c_" + k))) for k in EXISTING}
        out.append(dict(base=rw.base, ticker=rw.ticker, screen=rw.screen, frame_id=rw.frame_id, source=rw.primary_source,
                        slope_class=rw.slope_class, cmp_night=rw.cmp_night, i=i, P=Pi, bars=bars, his=float(rw.line_value_cmp),
                        pf=float(rw.c_pivot_full), adr=float(rw.adr20), close_i=float(bars.c[i]), high_i=float(bars.h[i]),
                        existing=ex, base_len=int(rw.base_len), wick_adr=float(rw.wick_adr)))
    return out


# ───────────────────────────── scoring ─────────────────────────────
def err_of(level, b):
    return None if level is None else (level - b["his"]) / b["pf"] / b["adr"]


def stratum_stats(errs, below):
    """errs: list of err-or-None; below: list of bool-or-None (level < close(i)). -> dict."""
    n = len(errs)
    have = [e for e in errs if e is not None]
    ab = np.abs(np.asarray(have, dtype=float)) if have else np.zeros(0)
    st = {"n": n, "n_level": len(have), "median_abs": (float(np.median(ab)) if len(ab) else None),
          "median_err": (float(np.median(have)) if have else None)}
    for t in TOLS:
        st[f"within_{t}"] = (float((ab <= t).sum()) / n) if n else None
    bl = [x for x in below if x is not None]
    st["below_close"] = (float(sum(bl)) / n) if n else None
    return st


def score_rows(name, levels, bases):
    """One scored reading -> [row per stratum]. levels: list parallel to bases (float or None)."""
    errs = [err_of(lv, b) for lv, b in zip(levels, bases)]
    below = [(None if lv is None else bool(lv < b["close_i"])) for lv, b in zip(levels, bases)]
    rows = []
    strata = [("all", lambda b: True), ("bar_verified", lambda b: b["source"] == "bar_verified"),
              ("eyeball_confirmed", lambda b: b["source"] == "eyeball_confirmed"),
              ("flat", lambda b: b["slope_class"] == "flat"), ("falling", lambda b: b["slope_class"] == "falling"),
              ("all_but_spot", lambda b: b["frame_id"] != "p4b_018")]
    for sname, f in strata:
        idx = [k for k, b in enumerate(bases) if f(b)]
        st = stratum_stats([errs[k] for k in idx], [below[k] for k in idx])
        rows.append({"reading": name, "stratum": sname, **st})
    return rows, errs


def bootstrap_se(abs_errs_or_none, draws=BOOT_DRAWS, seed=BOOT_SEED, tol=0.5):
    """SD of the share-within-tol over resamples of the bases (a miss stays a miss)."""
    hit = np.asarray([0.0 if e is None else float(abs(e) <= tol) for e in abs_errs_or_none])
    rng = np.random.default_rng(seed)
    n = len(hit)
    idx = rng.integers(0, n, size=(draws, n))
    return float(hit[idx].mean(axis=1).std(ddof=1))


# ───────────────────────────── the pick ─────────────────────────────
def grid_position(cell):
    fam, L, T, q, s = cell
    if fam == "quantile":
        return (Q_GRID.index(q),)
    pos = (L_GRID.index(L) if T != math.inf else None, T_GRID.index(T))
    return pos + ((S_GRID.index(s),) if s is not None else ())


def adjacent(a, b):
    """Two cells of ONE family are adjacent when every grid coordinate differs by <= 1 (the inf column counts as L-free)."""
    pa, pb = grid_position(a), grid_position(b)
    for x, y in zip(pa, pb):
        if x is None or y is None:
            continue
        if abs(x - y) > 1:
            return False
    return True


def pick(cells, M, med_abs, excluded, se):
    """-> (chosen cell or None, plateau cells, plateau threshold, per-family regions)."""
    ok = [c for c in cells if c not in excluded]
    if not ok:
        return None, [], None, {}
    m_best = max(M[c] for c in ok)
    thr = m_best - se
    plateau = [c for c in ok if M[c] >= thr]
    regions = {}
    for c in plateau:
        fam = c[0]
        others = [d for d in plateau if d[0] == fam and d != c]
        if any(adjacent(c, d) for d in others):
            regions.setdefault(fam, []).append(c)
    if not regions:
        return None, plateau, thr, regions
    fam = min(regions, key=lambda f: (FAMILY_PARAMS[f], FAMILY_ORDER.index(f)))
    reg = regions[fam]
    # the centre: the median grid position per parameter (ties -> the smaller), then the lower median |err|
    poss = [grid_position(c) for c in reg]
    dims = len(poss[0])
    centre = []
    for k in range(dims):
        vals = sorted(p[k] for p in poss if p[k] is not None)
        centre.append(vals[(len(vals) - 1) // 2] if vals else None)

    def dist(c):
        p = grid_position(c)
        return sum(abs(p[k] - centre[k]) for k in range(dims) if p[k] is not None and centre[k] is not None)
    chosen = min(reg, key=lambda c: (dist(c), med_abs[c] if med_abs[c] is not None else 9e9, cell_name(c)))
    return chosen, plateau, thr, regions


# ───────────────────────────── main ─────────────────────────────
def fnum(x, nd=4):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


def write_fixture(bases, outdir):
    os.makedirs(outdir, exist_ok=True)
    rows, labs = [], []
    chosen = ("flat_high", cb.COM_MAX_RUN, cb.COM_SPIKE_ADR, None, None)
    for b in bases:
        if b["base"] not in FIXTURE_BASES:
            continue
        bars, i, P = b["bars"], b["i"], b["P"]
        lo = max(0, i - FIXTURE_BACK)
        for j in range(lo, i + 2):
            if j >= len(bars):
                break
            rows.append("|".join([b["ticker"], bars.dates[j].isoformat()] + [repr(float(x[j])) for x in (bars.o, bars.h, bars.l, bars.c, bars.v)]))
        com = cb.com_level(bars, P, i, b["adr"])                                   # the module's DEFAULT reading, pinned
        labs.append(dict(base=b["base"], ticker=b["ticker"], pole_date=bars.dates[P].isoformat(), cmp_night=b["cmp_night"],
                         source=b["source"], slope_class=b["slope_class"], his_line_cmp=b["his"], pivot_full=b["pf"],
                         pivot_k5=b["existing"]["pivot_k5"], pivot_tl=b["existing"]["pivot_tl"], adr20=b["adr"],
                         frame_id=b["frame_id"], com_variant=com["com_variant"], com_level=com["pivot_com"],
                         com_level_date=com["pivot_com_date"], com_err_adr=err_of(com["pivot_com"], b),
                         k5_err_adr=err_of(b["existing"]["pivot_k5"], b), tl_err_adr=err_of(b["existing"]["pivot_tl"], b)))
    with open(os.path.join(outdir, "cb_p4b_labelled_bars.psv"), "w") as fh:
        fh.write("\n".join(rows) + "\n")
    pd.DataFrame(labs).to_csv(os.path.join(outdir, "cb_p4b_labels.tsv"), sep="\t", index=False)
    return len(rows), len(labs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--fixture-out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    bases = load_bases()
    n = len(bases)
    srcs = {s: sum(1 for b in bases if b["source"] == s) for s in ("bar_verified", "eyeball_confirmed")}
    slopes = {s: sum(1 for b in bases if b["slope_class"] == s) for s in ("flat", "falling")}
    cells = grid_cells()
    grid_rows, M, med_abs, below_share, errs_of, levels_of, meta_of = [], {}, {}, {}, {}, {}, {}
    for c in cells:
        res = [level_for(c, b["bars"], b["P"], b["i"], b["adr"]) for b in bases]
        levels = [r["pivot_com"] for r in res]
        rows, errs = score_rows(cell_name(c), levels, bases)
        for r in rows:
            r.update(family=c[0], L=c[1], T=("inf" if c[2] == math.inf else c[2]), q=c[3], s=c[4])
        grid_rows += rows
        allrow = rows[0]
        M[c], med_abs[c], below_share[c] = allrow["within_0.5"], allrow["median_abs"], allrow["below_close"]
        errs_of[c], levels_of[c], meta_of[c] = errs, levels, res
    # the existing levels, same score
    ex_rows, ex_M = [], {}
    for k in EXISTING:
        rows, errs = score_rows("existing:" + k, [b["existing"][k] for b in bases], bases)
        for r in rows:
            r.update(family="existing", L="", T="", q="", s="")
        ex_rows += rows
        ex_M[k] = {r["stratum"]: r for r in rows}
    his_below = sum(1 for b in bases if b["his"] < b["close_i"]) / n
    # the pick
    best_cell = max(cells, key=lambda c: (M[c], -(med_abs[c] or 9e9)))
    se = bootstrap_se(errs_of[best_cell])
    excluded = [c for c in cells if below_share[c] is not None and below_share[c] > 0.5]
    chosen, plateau, thr, regions = pick(cells, M, med_abs, excluded, se)
    best_existing = max(EXISTING, key=lambda k: ex_M[k]["all"]["within_0.5"])
    flag = (chosen is not None and ex_M[best_existing]["eyeball_confirmed"]["within_0.5"] is not None
            and (next(r for r in grid_rows if r["reading"] == cell_name(chosen) and r["stratum"] == "eyeball_confirmed")["within_0.5"]
                 < ex_M[best_existing]["eyeball_confirmed"]["within_0.5"]))

    gdf = pd.DataFrame(grid_rows + ex_rows)
    gdf["plateau"] = gdf.reading.map(lambda nm: int(any(cell_name(c) == nm for c in plateau)))
    gdf["excluded_below_close"] = gdf.reading.map(lambda nm: int(any(cell_name(c) == nm for c in excluded)))
    gdf["chosen"] = gdf.reading.map(lambda nm: int(chosen is not None and cell_name(chosen) == nm))
    for col in ("median_abs", "median_err", "within_0.25", "within_0.5", "within_1.0", "below_close"):
        gdf[col] = gdf[col].map(fnum)
    gdf.to_csv(os.path.join(a.out, "com_grid_p4b.tsv"), sep="\t", index=False)

    # per base: his line, the pick, each family's best cell
    fam_best = {}
    for fam in FAMILY_ORDER:
        fc = [c for c in cells if c[0] == fam]
        fam_best[fam] = max(fc, key=lambda c: (M[c], -(med_abs[c] or 9e9)))
    pb = []
    for k, b in enumerate(bases):
        row = dict(base=b["base"], screen=b["screen"], frame_id=b["frame_id"], source=b["source"], slope_class=b["slope_class"],
                   cmp_night=b["cmp_night"], his_line=fnum(b["his"], 6), close_i=fnum(b["close_i"], 6), high_i=fnum(b["high_i"], 6),
                   pivot_full=fnum(b["pf"], 6), pivot_tl=fnum(b["existing"]["pivot_tl"], 6), adr20=fnum(b["adr"], 5),
                   wick_adr=b["wick_adr"], base_len=b["base_len"], his_below_close=int(b["his"] < b["close_i"]))
        if chosen is not None:
            m = meta_of[chosen][k]
            row.update(chosen=cell_name(chosen), chosen_level=fnum(m["pivot_com"], 6), chosen_err_adr=fnum(errs_of[chosen][k], 3),
                       chosen_character=m["com_character"], chosen_ignored_bars=m["com_ignored_bars"],
                       chosen_ignored_runs=m["com_ignored_runs"], chosen_typical_high=fnum(m["com_typical_high"], 6),
                       chosen_spike_thr=fnum(m["com_spike_thr"], 6), chosen_level_date=m["pivot_com_date"])
        for fam, c in fam_best.items():
            row[f"best_{fam}"] = cell_name(c)
            row[f"best_{fam}_level"] = fnum(levels_of[c][k], 6)
            row[f"best_{fam}_err_adr"] = fnum(errs_of[c][k], 3)
        for kx in EXISTING:
            row[f"err_{kx}"] = fnum(err_of(b["existing"][kx], b), 3)
        pb.append(row)
    pd.DataFrame(pb).to_csv(os.path.join(a.out, "com_per_base_p4b.tsv"), sep="\t", index=False)

    # summary
    L = []
    w = L.append
    w("P4B STEP 6 - THE CENTER-OF-MASS LINE vs HIS 58 DRAWN LINES   ($0; labels used as given; the pick rule is in the docstring, written first)")
    w("")
    w(f"POPULATION: {n} bases with a top/level line (bar_verified {srcs['bar_verified']}, eyeball_confirmed {srcs['eyeball_confirmed']}; "
      f"his line flat {slopes['flat']}, falling {slopes['falling']}); screens 2019-2023 (one bull era, mostly 2020-21); "
      f"none in the 2025-26 holdout. err = (rule - his) / pivot_full / adr20 (ADR20 units, + = above his line).")
    w(f"his line sits BELOW the comparison night's close on {his_below:.0%} of the nights (a line drawn after the break, or a level).")
    w("")
    w(f"PICK: metric M = share within 0.5 ADR on all {n}; best cell {cell_name(best_cell)} M = {M[best_cell]:.3f}; bootstrap SE {se:.3f}; "
      f"plateau = M >= {thr if thr is not None else float('nan'):.3f}: {len(plateau)} cells; excluded (level below close on > 50% of nights): {len(excluded)} cells.")
    if chosen is None:
        w("NO PLATEAU FAMILY (no two adjacent plateau cells in one family) - no choice is made; the grid is reported.")
    else:
        w(f"CHOSEN: {cell_name(chosen)}   (the simplest family with >= 2 adjacent plateau cells, at its centre; "
          f"plateau regions per family: " + ", ".join(f"{f} {len(r)}" for f, r in regions.items()) + ")")
        w(f"  eyeball flag (pick's eyeball M below the best existing level's): {'YES' if flag else 'no'}")
    w("")

    def tbl(title, names_rows):
        w(title)
        hdr = f"{'reading':<34}{'stratum':<18}{'n':>4}{'lvl':>5}{'med|err|':>9}{'bias':>7}{'<=.25':>7}{'<=.5':>7}{'<=1':>6}{'<close':>8}"
        w(hdr)
        for nm, strat in names_rows:
            r = next(x for x in grid_rows + ex_rows if x["reading"] == nm and x["stratum"] == strat)
            w(f"{nm:<34}{strat:<18}{r['n']:>4}{r['n_level']:>5}{(r['median_abs'] if r['median_abs'] is not None else float('nan')):>9.3f}"
              f"{(r['median_err'] if r['median_err'] is not None else float('nan')):>7.2f}{r['within_0.25']:>7.0%}{r['within_0.5']:>7.0%}"
              f"{r['within_1.0']:>6.0%}{(r['below_close'] if r['below_close'] is not None else float('nan')):>8.0%}")
        w("")

    strata = ("all", "bar_verified", "eyeball_confirmed", "flat", "falling", "all_but_spot")
    if chosen is not None:
        tbl("THE PICK, per stratum", [(cell_name(chosen), s) for s in strata])
    tbl("THE EXISTING LEVELS, per stratum (the best on M first)",
        [(f"existing:{k}", s) for k in sorted(EXISTING, key=lambda k: -ex_M[k]["all"]["within_0.5"]) for s in strata])
    tbl("EACH FAMILY'S BEST CELL (all 58, then per source)",
        [(cell_name(c), s) for fam, c in fam_best.items() for s in ("all", "bar_verified", "eyeball_confirmed", "flat", "falling")])
    w("PLATEAU CELLS (the runners-up), M then median |err|:")
    for c in sorted(plateau, key=lambda c: (-M[c], med_abs[c] or 9e9)):
        w(f"  {cell_name(c):<36} M {M[c]:.3f}  med|err| {med_abs[c]:.3f}  below-close {below_share[c]:.0%}" + ("   <- chosen" if c == chosen else ""))
    w("")
    w("EXCLUDED CELLS (level below close(i) on > 50% of the nights): " + (", ".join(cell_name(c) for c in excluded) if excluded else "none"))
    w("")
    w("THE WHOLE GRID on all 58 (M = share within 0.5 ADR; med = median |err| in ADR):")
    for fam in FAMILY_ORDER:
        fc = [c for c in cells if c[0] == fam]
        w(f"  {fam}: " + "  ".join(f"{cell_name(c).split('(', 1)[1][:-1]}:{M[c]:.2f}/{med_abs[c]:.2f}" for c in fc))
    text = "\n".join(L) + "\n"
    open(os.path.join(a.out, "summary_p4b_com.txt"), "w").write(text)
    print(text)
    if a.fixture_out:
        nb, nl = write_fixture(bases, a.fixture_out)
        print(f"fixture: {nb} bar rows, {nl} labelled bases -> {a.fixture_out}")


if __name__ == "__main__":
    sys.exit(main())
