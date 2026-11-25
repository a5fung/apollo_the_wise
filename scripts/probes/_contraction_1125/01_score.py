#!/usr/bin/env python3
"""#717 contraction-into-the-buy: the FROZEN pre-registration, scored ONCE (2026-11-25; offline, $0, research only).

WHAT  docs/analysis/cb_contraction_into_buy_prereg_2026-11-25.md (sha256 20b36c4a...b410) — 4 candidate readings of
      "the chart tightens into the buy" (C1 box_narrows, C2 lines_converge, C3 swings_shrink, C4 daily_range_shrinks),
      a closed grid of 51 cells, scored against bars (a) keep Qullamaggie's buys, (b) VOR fails, (c) his chart grades,
      (d) cut rate on the prod list (reported only). Implemented literally; ambiguities are logged as DEVIATIONS below.
WHY   he marked VOR "a wide flat range" vs SKLZ / QS / (maybe) OSTK "tightness going into it"; a found-base
      requirement loses buys (190 of 269). No production code, list rule or deploy changes with this file.
HOW   python3 scripts/probes/_contraction_1125/01_score.py --selfcheck   # bridge + synthetic + label counts only, no scoring
      python3 scripts/probes/_contraction_1125/01_score.py > scripts/probes/_contraction_1125/01_score.out 2>&1   # ONCE
      (for (d) add --prod to fetch the prod list/bars read-only over ssh once, cached in prod_*.psv beside this file; without it (d) is skipped)
Sealed cb702/ is never opened. 2025+ bars read: the 41 fixture live-list charts, VOR, prod list names for (d).
"""
import csv, gzip, math, os, re, subprocess, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tests/fixtures"))
HERE = Path(__file__).resolve().parent
from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
from breakout_list_grades import BREAKOUT_LIST_GRADES, MODEL_PICK_GRADES

FX = REPO / "tests/fixtures/qm_breakout_scorecard"
SELFCHECK = "--selfcheck" in sys.argv
DEV = []          # deviations / ambiguities, printed at the end

# ───────────────────────────── the grid (closed, 51 cells) ─────────────────────────────
GRID = {("C1", 10): (0.6, 0.7, 0.8, 0.9, 1.0), ("C1", 15): (0.6, 0.7, 0.8, 0.9, 1.0), ("C1", 20): (0.6, 0.7, 0.8, 0.9, 1.0),
        ("C2", 30): (0.5, 0.65, 0.8, 0.95), ("C2", 40): (0.5, 0.65, 0.8, 0.95), ("C2", 60): (0.5, 0.65, 0.8, 0.95),
        ("C3", 30): (0.4, 0.5, 0.6, 0.7), ("C3", 40): (0.4, 0.5, 0.6, 0.7), ("C3", 60): (0.4, 0.5, 0.6, 0.7),
        ("C4", 20): (0.7, 0.8, 0.9, 1.0), ("C4", 30): (0.7, 0.8, 0.9, 1.0), ("C4", 40): (0.7, 0.8, 0.9, 1.0)}
CELLS = [(c, w, T) for (c, w), Ts in GRID.items() for T in Ts]
assert len(CELLS) == 51
NAMES = {"C1": "box_narrows", "C2": "lines_converge", "C3": "swings_shrink", "C4": "daily_range_shrinks"}


def _fin(x):
    return bool(np.isfinite(x).all())


def _log(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(np.asarray(x, dtype=float))


def r_c1(h, l, D, n):
    if D - 2 * n + 1 < 0:
        return None
    H, L = _log(h[D - 2 * n + 1:D + 1]), _log(l[D - 2 * n + 1:D + 1])
    if not (_fin(H) and _fin(L)):
        return None
    new = H[n:].max() - L[n:].min(); old = H[:n].max() - L[:n].min()
    return None if old <= 0 else float(new / old)


def _line(pts, fallback):
    if len(pts) == 0:
        return lambda x: fallback
    if len(pts) == 1:
        return lambda x, v=pts[0][1]: v
    xs = np.array([q[0] for q in pts], float); ys = np.array([q[1] for q in pts], float)
    m, b = np.polyfit(xs, ys, 1)
    return lambda x: m * x + b


def c2_lines(h, l, D, N):
    """(lower_fn, upper_fn, pivots) on log highs/lows of the last N sessions, or None when unscorable."""
    if D - N + 1 < 0:
        return None
    H, L = _log(h[D - N + 1:D + 1]), _log(l[D - N + 1:D + 1])
    if not (_fin(H) and _fin(L)):
        return None
    p = bv.swing_pivots(H, L)
    lows = [(i, v) for i, v, t in p if t == -1]; highs = [(i, v) for i, v, t in p if t == 1]
    last = p[-1][0] if p else -1
    if last + 1 < N:
        j = last + 1 + int(np.argmin(L[last + 1:])); lows.append((j, L[j]))
        j = last + 1 + int(np.argmax(H[last + 1:])); highs.append((j, H[j]))
    return _line(lows, L.min()), _line(highs, H.max()), p


def r_c2(h, l, D, N):
    z = c2_lines(h, l, D, N)
    if z is None:
        return None
    lo, up, _ = z
    g0 = up(0) - lo(0); g1 = up(N - 1) - lo(N - 1)
    if not g0 > 0:
        return None
    return float(max(g1, 0.0) / g0)          # gap(N-1) <= 0 with gap(0) > 0 = lines met = ratio 0 = pass


def r_c3(h, l, D, N):
    if D - N + 1 < 0:
        return None
    H, L = _log(h[D - N + 1:D + 1]), _log(l[D - N + 1:D + 1])
    if not (_fin(H) and _fin(L)):
        return None
    legs, _ = bv.swing_legs(H, L)
    if len(legs) < 3 or legs.max() <= 0:
        return None
    return float(legs[-2:].mean() / legs.max())


def r_c4(h, l, c, D, m):
    if D - 9 - m < 0:
        return None
    hh, ll, cc = (np.asarray(x, float)[D - 9 - m:D + 1] for x in (h, l, c))
    if not (_fin(hh) and _fin(ll) and _fin(cc)) or (cc <= 0).any():
        return None
    r = (hh - ll) / cc
    den = r[:m].mean()
    return None if den <= 0 else float(r[m:].mean() / den)


def ratios(h, l, c, D):
    out = {}
    for n in (10, 15, 20): out[("C1", n)] = r_c1(h, l, D, n)
    for N in (30, 40, 60): out[("C2", N)] = r_c2(h, l, D, N)
    for N in (30, 40, 60): out[("C3", N)] = r_c3(h, l, D, N)
    for m in (20, 30, 40): out[("C4", m)] = r_c4(h, l, c, D, m)
    return out


def passes(rat, key, T):
    x = rat[key]
    return x is None or x <= T


# ───────────────────────────── loaders ─────────────────────────────
def load_bars(name):
    by = defaultdict(list)
    with gzip.open(FX / name, "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["eid"]].append(r)
    out = {}
    for eid, rr in by.items():
        rr.sort(key=lambda x: x["date"]); ds = [date.fromisoformat(x["date"]) for x in rr]
        out[eid] = (ds, cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"]))
    return out


def arrs(b):
    return np.asarray(b.h, float), np.asarray(b.l, float), np.asarray(b.c, float)


MARK = {("SKLZ", "2021-01-05"): "SKLZ", ("QS", "2021-10-29"): "QS", ("OSTK", "2021-01-22"): "OSTK",
        ("APT", "2020-06-17"): "APT", ("MDB", "2020-09-21"): "MDB", ("JMIA", "2020-11-18"): "JMIA"}
Q = {}                                            # the 269
B = load_bars("bars.psv.gz"); buys = list(csv.DictReader(open(FX / "buys.tsv"), delimiter="\t"))
rows269 = []
for r in buys:
    ds, b = B[r["eid"]]; D = ds.index(date.fromisoformat(r["D"]))
    assert ds[D + 1] == date.fromisoformat(r["E"])
    g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
    h, l, c = arrs(b)
    found = bool(bv.range_levels(h, l, D))
    rows269.append(dict(r=r, b=b, D=D, g=g, h=h, l=l, c=c, found=found, listed=bool(g["ok"]), big=r["big_winner"] == "1",
                        tag=MARK.get((r["sym"], r["E"])), name=f'{r["sym"]} {r["E"]}'))
assert len(rows269) == 269
print("=" * 100); print("BRIDGE (correct-build check; reproduces scripts/probes/_vor_1125/01_range_on_qm_buys.out)"); print("=" * 100)
nfound = sum(x["found"] for x in rows269); L_ = sum(x["listed"] for x in rows269); BL = sum(x["listed"] and x["big"] for x in rows269)
nbig = sum(x["big"] for x in rows269); bigfound = sum(x["big"] and x["found"] for x in rows269)
lostbig = [x["name"] for x in rows269 if x["big"] and not x["found"]]
lfound = sum(x["listed"] and x["found"] for x in rows269)
print(f"DATED buys: base found the night before on {nfound} of 269; on today's list {L_}, of them base found {lfound}; listed big winners BL={BL}")
print(f"  big winners: base found {bigfound} of {nbig}; lost: {', '.join(lostbig)}")
bridge_ok = (nfound, nbig, bigfound, L_, lfound) == (190, 26, 20, 218, 156) and lostbig == ["APT 2020-06-17", "MDB 2020-09-21", "JMIA 2020-11-18", "SKLZ 2021-01-05", "OSTK 2021-01-22", "QS 2021-10-29"]
print(f"  BRIDGE {'OK' if bridge_ok else 'MISMATCH'} (expected 190 / 26 / 20 / 218 / 156 and the six named)")
need = -(-95 * L_ // 100)     # ceil(0.95 L)
print(f"  bar (a) lines: lose zero of BL={BL}; >= 256 of 269; >= ceil(0.95 x {L_}) = {need} of the listed")

# VOR
vrows = [ln.split("|") for ln in open(REPO / "scripts/probes/_vor_1125/vor_bars.psv") if re.match(r"\d{4}-\d\d-\d\d\|", ln)]
VD = [r[0] for r in vrows]; VO, VH, VL, VC = (np.array([float(r[k]) for r in vrows]) for k in (1, 2, 3, 4))
def vor_at(night):
    D = VD.index(night); return VH[:D + 1], VL[:D + 1], VC[:D + 1], D     # bars through the night ONLY
vh, vl, vc, vD = vor_at("2026-11-20")
print(f"VOR: D=2026-11-20 -> {vD + 1} bars through D (expected 185): {'OK' if vD + 1 == 185 else 'MISMATCH'}")
bridge_ok = bridge_ok and vD + 1 == 185

# labels
def read_psv_grades():
    by = defaultdict(list)
    with gzip.open(REPO / "tests/fixtures/breakout_list_grades_bars.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[(r["ticker"], r["list_date"])].append(r)
    return by
LB = read_psv_grades(); LIVE = []
for g in BREAKOUT_LIST_GRADES:
    rr = sorted(LB[(g.ticker, g.list_date)], key=lambda x: x["date"])
    assert rr[-1]["date"] == g.list_date, g
    h, l, c = (np.array([float(x[k]) for x in rr]) for k in "hlc")
    LIVE.append(dict(t=g.ticker, d=g.list_date, grade=g.grade, words=g.operator_words, h=h, l=l, c=c, D=len(rr) - 1, o=np.array([float(x["o"]) for x in rr])))
import pandas as pd
GR = pd.read_csv(HERE.parent / "_717_wideloose_1114/graded_rows.tsv", sep="\t")
WG = np.load(HERE.parent / "_717_wideloose_1114/graded_windows200.npy")
fx = {(g.ticker, g.list_date): g.grade for g in MODEL_PICK_GRADES}
HIST = []
for _, r in GR.iterrows():
    w = WG[int(r.wid)]
    if fx.get((r.ticker, r.D)) != r.grade: DEV.append(f"hist label mismatch fixture vs graded_rows: {r.ticker} {r.D}")
    HIST.append(dict(t=r.ticker, d=r.D, grade=r.grade, words=r.words, o=w[0], h=w[1], l=w[2], c=w[3], D=199))
RX = re.compile(r"wide|range|chop|loose|lose\b|tight|higher low|lower low|random", re.I)
for s in LIVE + HIST:
    s["side"] = "good" if s["grade"] in ("good", "ok") else ("no" if s["grade"] == "no" else "cond")
    s["reason"] = bool(s["side"] == "no" and RX.search(s["words"]))
for s in HIST:
    if s["t"] == "OCGN" and s["reason"]: s["reason"] = False
FRZ_LIVE = {"IAG", "FNKO", "RSKD", "CVLT", "MANE", "ABCL", "OUST"}
FRZ_HIST = {"LCID", "SWAV", "FLGT", "MVIS", "DVAX", "DOCN", "THC", "CDE", "TWTR", "TDOC", "MELI", "RRC", "WPX"}
def cnt(S, f): return sum(1 for s in S if f(s))
print(f"LIVE 41: {cnt(LIVE, lambda s: s['grade']=='no')} no / {cnt(LIVE, lambda s: s['side']=='good')} good-ok (frozen 23 / 13) / {cnt(LIVE, lambda s: s['side']=='cond')} cond (5); reason-matched no {cnt(LIVE, lambda s: s['reason'])} (frozen 7)")
print(f"HIST 48: {cnt(HIST, lambda s: s['grade']=='no')} no (25) / {cnt(HIST, lambda s: s['side']=='good')} good-ok (14) / {cnt(HIST, lambda s: s['side']=='cond')} cond (9); reason-matched no {cnt(HIST, lambda s: s['reason'])} (13)")
rl = {s["t"] for s in LIVE if s["reason"]}; rh = {s["t"] for s in HIST if s["reason"]}
print(f"  reason-matched live names {sorted(rl)} == frozen: {rl == FRZ_LIVE}; hist {sorted(rh)} == frozen: {rh == FRZ_HIST}")
labels_ok = (rl == FRZ_LIVE and rh == FRZ_HIST and cnt(LIVE, lambda s: s['side'] == 'good') == 13 and cnt(HIST, lambda s: s['side'] == 'good') == 14
             and cnt(HIST, lambda s: s['grade'] == 'no') == 25)
print(f"  LABEL COUNTS {'OK' if labels_ok else 'MISMATCH'}")

# ───────────────────────────── synthetic checks (ratios, before any label is read) ─────────────────────────────
def synth(kind, n=184):
    t = np.arange(n); ph = np.sin(2 * np.pi * t / 12)
    if kind == "flat":
        A = np.full(n, 0.05); hr = np.full(n, 0.01)
    else:
        A = np.where(t < 100, 0.10, 0.10 - 0.09 * (t - 100) / (n - 1 - 100)); hr = np.where(t < 100, 0.02, 0.02 - 0.017 * (t - 100) / (n - 1 - 100))
    mid = np.log(100.0) + A * ph
    return np.exp(mid + hr), np.exp(mid - hr), np.exp(mid), n - 1       # D = 183 = a peak (3 + 12k)
fr = ratios(*synth("flat")); wr = ratios(*synth("wedge"))
print("\nSYNTHETIC ratio check (flat box ~1.0 on C1/C2/C4, >= 0.75 on C3; wedge clearly lower on all four)")
syn_ok = True
for k in fr:
    f, w = fr[k], wr[k]
    cond = (f is not None and w is not None and w < f - 0.15)
    if k[0] in ("C1", "C2", "C4"): cond = cond and abs(f - 1.0) <= 0.15
    if k[0] == "C3": cond = cond and f >= 0.75
    syn_ok &= bool(cond)
    print(f"  {k[0]} {k[1]:>3}: flat {f if f is None else round(f,3)}  wedge {w if w is None else round(w,3)}  {'ok' if cond else 'FAIL'}")
print(f"  SYNTHETIC {'OK' if syn_ok else 'MISMATCH'}")
if SELFCHECK or not (bridge_ok and syn_ok and labels_ok):
    if not (bridge_ok and syn_ok and labels_ok): print("\nCORRECT-BUILD CHECK FAILED -> no scoring (a runner defect is fixed before scoring)")
    sys.exit(0 if (bridge_ok and syn_ok and labels_ok) else 2)

# ───────────────────────────── per-chart ratios ─────────────────────────────
for x in rows269: x["rat"] = ratios(x["h"], x["l"], x["c"], x["D"])
for s in LIVE + HIST: s["rat"] = ratios(s["h"], s["l"], s["c"], s["D"])
VORN = {n: ratios(*vor_at(n)[:3], vor_at(n)[3]) for n in ("2026-11-13", "2026-11-20", "2026-11-23", "2026-11-24")}
VRAT = VORN["2026-11-20"]
TAG = {x["tag"]: x for x in rows269 if x["tag"]}
assert len(TAG) == 6, TAG.keys()

print("\n" + "=" * 100); print("BRIDGE 2: per-candidate RATIOS (cell-independent; pass iff ratio <= T, unscored = pass) on VOR / SKLZ / QS / OSTK (+ APT MDB JMIA)"); print("=" * 100)
keys = list(GRID.keys())
def f3(x): return "unsc" if x is None else f"{x:.3f}"
print(f'{"chart":<22}' + "".join(f'{k[0]}:{k[1]:<3} ' for k in keys))
for nm, rat in [("VOR D=11-20", VRAT), ("VOR D=11-13", VORN["2026-11-13"]), ("VOR D=11-23", VORN["2026-11-23"]), ("VOR D=11-24", VORN["2026-11-24"])] + [(t + " (D=" + TAG[t]["r"]["D"] + ")", TAG[t]["rat"]) for t in ("SKLZ", "QS", "OSTK", "APT", "MDB", "JMIA")]:
    print(f"{nm:<22}" + "".join(f"{f3(rat[k]):<6} " for k in keys))

# undated 488
W = load_bars("bars_undated_widened.psv.gz"); wr_ = list(csv.DictReader(open(FX / "buys_undated_widened.tsv"), delimiter="\t"))
UND = []
for r in wr_:
    if r["eid"] not in W: continue
    ds, b = W[r["eid"]]; lo, hi_ = date.fromisoformat(r["lo"]), date.fromisoformat(r["hi"])
    idx = [i - 1 for i, d in enumerate(ds) if lo <= d <= hi_ and i >= 1]
    if not idx: continue
    h, l, c = arrs(b); UND.append([ratios(h, l, c, D) for D in idx])

# ───────────────────────────── reference rows ─────────────────────────────
print("\n" + "=" * 100); print("REFERENCE rows (standing alone, same populations; NOT eligible; will not match the 11-11 figures stacked on amendment 2)"); print("=" * 100)
REF = {"range_contract": lambda sg, x: sg["range_contract"]["pass"], "tight_closes5": lambda sg, x: sg["tight_closes5"]["pass"],
       "tight_run3": lambda sg, x: sg["tight_run3"]["pass"], "tight10": lambda sg, x: sg["tight10"]["pass"],
       "higher_lows": lambda sg, x: sg["higher_lows"]["pass"], "found_base": None}
print(f'{"reference":<16}{"of 269":>8}{"of L":>7}{"big/26":>8}{"bigL":>6}   big winners failed')
for nm, fn in REF.items():
    p = pl = pb = pbl = 0; fb = []
    for x in rows269:
        if nm == "found_base": ok = x["found"]
        else:
            try: ok = bool(fn(bv.shape_gates(x["b"], x["D"], P=x["g"]["pole_idx"], adr20=x["g"]["adr20"]), x)) if x["g"]["pole_idx"] is not None else False
            except Exception: ok = False
        p += ok; pl += ok and x["listed"]; pb += ok and x["big"]; pbl += ok and x["big"] and x["listed"]
        if x["big"] and not ok: fb.append(x["name"])
    print(f"{nm:<16}{p:>8}{pl:>7}{pb:>8}{pbl:>6}   {', '.join(fb)}")

# ───────────────────────────── the score table ─────────────────────────────
LOWLINE7 = {"COUP", "DVAX", "MELI", "RRC", "TDOC", "TWTR", "WPX"}
def cell_eval(cand, win, T):
    key = (cand, win)
    P = lambda rat: passes(rat, key, T)
    ps = [P(x["rat"]) for x in rows269]
    unsc = sum(x["rat"][key] is None for x in rows269)
    k269 = sum(ps); kL = sum(p and x["listed"] for p, x in zip(ps, rows269))
    big = sum(p and x["big"] for p, x in zip(ps, rows269)); bigL = sum(p and x["big"] and x["listed"] for p, x in zip(ps, rows269))
    lostbigL = [x["name"] for p, x in zip(ps, rows269) if not p and x["big"] and x["listed"]]
    lostbig = [x["name"] for p, x in zip(ps, rows269) if not p and x["big"]]
    void = unsc > 0.10 * 269
    a = (not void) and len(lostbigL) == 0 and k269 >= 256 and kL >= need
    vor = P(VRAT); b = not vor
    mk = {t: P(TAG[t]["rat"]) for t in TAG}
    gl = sum(P(s["rat"]) for s in LIVE if s["side"] == "good"); gh = sum(P(s["rat"]) for s in HIST if s["side"] == "good")
    rl_ = sum((not P(s["rat"])) for s in LIVE if s["reason"]); rh_ = sum((not P(s["rat"])) for s in HIST if s["reason"])
    c = mk["SKLZ"] and mk["QS"] and gl >= 11 and gh >= 12 and rl_ >= 4 and rh_ >= 7
    allno_l = sum((not P(s["rat"])) for s in LIVE if s["side"] == "no"); allno_h = sum((not P(s["rat"])) for s in HIST if s["side"] == "no")
    cond_l = sum((not P(s["rat"])) for s in LIVE if s["side"] == "cond"); cond_h = sum((not P(s["rat"])) for s in HIST if s["side"] == "cond")
    gfail_l = sum((not P(s["rat"])) for s in LIVE if s["side"] == "good"); gfail_h = sum((not P(s["rat"])) for s in HIST if s["side"] == "good")
    rl7 = sum((not P(s["rat"])) for s in HIST if s["reason"] and s["t"] not in LOWLINE7)
    rl7n = sum(1 for s in HIST if s["reason"] and s["t"] not in LOWLINE7)
    gh7 = sum(P(s["rat"]) for s in HIST if s["side"] == "good")      # none of the 7 is good/ok in the 48? printed anyway
    und = sum(any(passes(r_, key, T) for r_ in nights) for nights in UND)
    return dict(cell=(cand, win, T), k269=k269, kL=kL, big=big, bigL=bigL, lostbigL=lostbigL, lostbig=lostbig, unsc=unsc, void=void, a=a, b=b,
                c=c, vor=VRAT[key], mk=mk, gl=gl, gh=gh, rl=rl_, rh=rh_, allno_l=allno_l, allno_h=allno_h, cond_l=cond_l, cond_h=cond_h,
                gfail_l=gfail_l, gfail_h=gfail_h, rl7=rl7, rl7n=rl7n, und=und, vor_nights={n: (not passes(VORN[n], key, T)) for n in VORN})
RES = {cell: cell_eval(*cell) for cell in CELLS}

print("\n" + "=" * 100); print(f"SCORE TABLE — 51 cells. a = zero of BL={BL} listed big winners lost AND >=256/269 AND >={need}/{L_} listed; b = VOR(11-20) FAILS; c = markup + good/ok kept (>=11/13 live, >=12/14 hist) + reason-no failed (>=4/7, >=7/13)"); print("=" * 100)
hdr = f'{"cell":<16}{"/269":>5}{"/L":>5}{"big/26":>7}{"bigL":>5}{"unsc":>5}{"VORfail":>8}{"SKLZ":>5}{"QS":>4}{"OSTK":>5}{"APT":>4}{"MDB":>4}{"JMIA":>5}{"gl/13":>6}{"gh/14":>6}{"rl/7":>5}{"rh/13":>6}  a b c   big winners lost (of 26)'
print(hdr)
tf = lambda v: "P" if v else "-"
for cell in CELLS:
    e = RES[cell]; nm = f"{cell[0]} w{cell[1]} T{cell[2]}"
    print(f'{nm:<16}{e["k269"]:>5}{e["kL"]:>5}{e["big"]:>7}{e["bigL"]:>5}{e["unsc"]:>5}{"yes" if e["b"] else "no":>8}'
          f'{tf(e["mk"]["SKLZ"]):>5}{tf(e["mk"]["QS"]):>4}{tf(e["mk"]["OSTK"]):>5}{tf(e["mk"]["APT"]):>4}{tf(e["mk"]["MDB"]):>4}{tf(e["mk"]["JMIA"]):>5}'
          f'{e["gl"]:>6}{e["gh"]:>6}{e["rl"]:>5}{e["rh"]:>6}  {tf(e["a"])} {tf(e["b"])} {tf(e["c"])}   {", ".join(e["lostbig"])}' + ("  VOID" if e["void"] else ""))

print("\nLEAN (reported, never a verdict): fail rate on reason-matched no / fail rate on good-ok, per set; then all-no, conditional, undated 488")
print(f'{"cell":<16}{"liveRNO":>8}{"liveGOK":>8}{"histRNO":>8}{"histGOK":>8}{"hist-RNO-w/o-7":>16}{"liveALLno":>10}{"histALLno":>10}{"condL/5":>8}{"condH/9":>8}{"undated pass/488":>18}')
for cell in CELLS:
    e = RES[cell]; nm = f"{cell[0]} w{cell[1]} T{cell[2]}"
    print(f'{nm:<16}{e["rl"]}/7={e["rl"]/7:.2f}'.ljust(16 + 8) + f'{e["gfail_l"]}/13={e["gfail_l"]/13:.2f}'.rjust(9) + f'{e["rh"]}/13={e["rh"]/13:.2f}'.rjust(10)
          + f'{e["gfail_h"]}/14={e["gfail_h"]/14:.2f}'.rjust(11) + f'{e["rl7"]}/{e["rl7n"]}'.rjust(14) + f'{e["allno_l"]}/23'.rjust(10) + f'{e["allno_h"]}/25'.rjust(10)
          + f'{e["cond_l"]}/5'.rjust(8) + f'{e["cond_h"]}/9'.rjust(8) + f'{e["und"]}/{len(UND)}'.rjust(18))
print("\nVOR at the other list nights (reported): fail = the cell would have removed VOR that night")
for cell in CELLS:
    e = RES[cell]; print(f'  {cell[0]} w{cell[1]} T{cell[2]}: ' + "  ".join(f"{n[5:]}:{'fail' if v else 'pass'}" for n, v in e["vor_nights"].items()))

# ───────────────────────────── plateaus ─────────────────────────────
def runs(flags):
    out, cur = [], []
    for i, f in enumerate(flags):
        if f: cur.append(i)
        else:
            if cur: out.append(cur)
            cur = []
    if cur: out.append(cur)
    return out
def best_plateau(setname):
    """per (cand, win): longest run >= 3 of consecutive thresholds each passing the set; chosen = middle (even: higher T)."""
    res = {}
    for key, Ts in GRID.items():
        fl = [all(RES[(key[0], key[1], T)][s] for s in setname) for T in Ts]
        rr = [r for r in runs(fl) if len(r) >= 3]
        if not rr: continue
        r = max(rr, key=len); mid = r[len(r) // 2] if len(r) % 2 == 1 else r[len(r) // 2]   # even run: the higher of the two middle = index len//2
        res[key] = (Ts[mid], [Ts[i] for i in r])
    return res
SETS = {"(a)(b)(c)": ("a", "b", "c"), "(a)(b)": ("a", "b"), "(b)(c)": ("b", "c")}
PL = {k: best_plateau(v) for k, v in SETS.items()}
print("\n" + "=" * 100); print("PLATEAUS (run of >= 3 consecutive thresholds each passing every bar in the set; chosen = middle, even run -> looser/higher T)"); print("=" * 100)
winners = {}
for sname, pl in PL.items():
    print(f"{sname}: " + ("none" if not pl else ""))
    for key, (T, run) in pl.items():
        keys_ = list(GRID.keys()); i = keys_.index(key)
        sup = [k for k in (keys_[i - 1] if i > 0 and keys_[i - 1][0] == key[0] else None, keys_[i + 1] if i + 1 < len(keys_) and keys_[i + 1][0] == key[0] else None) if k and k in pl]
        e = RES[(key[0], key[1], T)]
        print(f"  {key[0]} {NAMES[key[0]]} window {key[1]}: run {run} -> chosen T={T}; kept {e['k269']}/269, {e['kL']}/{L_} listed, big {e['big']}/26 (listed {e['bigL']}/{BL}); adjacent window(s) also with a run: {sup or 'none'}")
    if pl:
        pick = max(pl.items(), key=lambda kv: (RES[(kv[0][0], kv[0][1], kv[1][0])]["k269"], RES[(kv[0][0], kv[0][1], kv[1][0])]["rl"] + RES[(kv[0][0], kv[0][1], kv[1][0])]["rh"]))
        winners[sname] = (pick[0], pick[1][0])
        print(f"  -> the study's choice among plateaus (most of 269, tie -> most reason-matched no failed): {pick[0][0]} window {pick[0][1]} T={pick[1][0]}")
a_cells = [c for c in CELLS if RES[c]["a"]]
a_fail_somewhere = len(a_cells) < len(CELLS)
a_all_keep_vor = all(not RES[c]["b"] for c in a_cells)
print(f"\ncells passing (a): {len(a_cells)} of 51; of those, VOR also fails (b) in {sum(RES[c]['b'] for c in a_cells)}; every (a)-passing cell keeps VOR: {a_all_keep_vor}")

print("\n" + "=" * 100); print("RESULT (pre-worded table read top-down, first match wins)"); print("=" * 100)
if "(a)(b)(c)" in winners:
    (cand, win), T = winners["(a)(b)(c)"]; e = RES[(cand, win, T)]; res = "PROPOSE"
    print(f"PROPOSE: {cand} {NAMES[cand]} at window {win}, T {T} keeps {e['k269']} of Qullamaggie's 269 buys and every big winner the list keeps ({e['bigL']} of {BL}), fails VOR, keeps {e['gl']} of 13 (live) and {e['gh']} of 14 (hist) good/ok charts and rejects {e['rl']} of 7 / {e['rh']} of 13 reason-matched no charts. Cut rate: see (d).")
elif "(a)(b)" in winners:
    (cand, win), T = winners["(a)(b)"]; e = RES[(cand, win, T)]; res = "PARTIAL"
    print(f"PARTIAL: {cand} {NAMES[cand]} window {win} T {T} keeps Qullamaggie's buys ({e['k269']}/269, listed big {e['bigL']}/{BL}) and fails VOR but does not match the grades: markup SKLZ {e['mk']['SKLZ']} QS {e['mk']['QS']}; good/ok kept live {e['gl']}/13 hist {e['gh']}/14; reason-no failed live {e['rl']}/7 hist {e['rh']}/13.")
elif "(b)(c)" in winners:
    (cand, win), T = winners["(b)(c)"]; e = RES[(cand, win, T)]; res = "NULL-expected"
    print(f"NULL (expected): a reading that matches the eye on VOR / SKLZ / QS loses Qullamaggie buys — {', '.join(e['lostbig']) or 'none'} ({cand} window {win} T {T}; listed big winners lost: {', '.join(e['lostbigL']) or 'none'}). No contraction GATE is proposed. Next: contraction as a ranking input (separate pre-registration).")
elif a_fail_somewhere:
    res = "NULL"; print("NULL: no stable reading of tightening-into-the-buy separates VOR and your no charts while keeping Qullamaggie's buys. Nothing proposed. VOR stays a labelled example.")
else:
    res = "NULL-all-keep-VOR"; print("NULL: every reading that keeps his buys also keeps VOR.")
print(f"[RESULT_CODE {res}]")

# ───────────────────────────── (d) prod list cut rate ─────────────────────────────
print("\n" + "=" * 100); print("(d) prod list cut rate, scan dates 2026-11-16 .. 11-24 (reported, not a bar). Bars from mi_daily_closes up to each scan date only."); print("=" * 100)
PL_F, PB_F = HERE / "prod_list.psv", HERE / "prod_bars.psv"
SQL_L = "SET default_transaction_read_only = on;\nSELECT scan_date, ticker FROM mi_breakout_v1_list WHERE scan_date BETWEEN '2026-11-16' AND '2026-11-24' ORDER BY 1,2;\n"
SQL_B = ("SET default_transaction_read_only = on;\nSELECT ticker, trade_date, open_price, high_price, low_price, close FROM mi_daily_closes WHERE trade_date BETWEEN '2025-09-01' AND '2026-11-24' "
         "AND ticker IN (SELECT DISTINCT ticker FROM mi_breakout_v1_list WHERE scan_date BETWEEN '2026-11-16' AND '2026-11-24') ORDER BY ticker, trade_date;\n")
def fetch(sql, path):
    if path.exists() and path.stat().st_size > 0: return True
    if "--prod" not in sys.argv: print("  prod cache absent and --prod not given (read-only ssh not attempted)"); return False
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=20", "apollo@87.99.134.162", 'docker exec -i apollo-postgres psql -U apollo -d apollo -q -t -A -F "|"'], input=sql, capture_output=True, text=True, timeout=300)
    if p.returncode != 0 or not p.stdout.strip(): print(f"  prod fetch failed rc={p.returncode}: {p.stderr[:200]}"); return False
    path.write_text("\n".join(ln for ln in p.stdout.splitlines() if "|" in ln) + "\n"); return True
CUT = None
try:
    if fetch(SQL_L, PL_F) and fetch(SQL_B, PB_F):
        PB = defaultdict(list)
        for ln in PB_F.read_text().splitlines():
            t, d, o, h, l, c = ln.split("|")
            if h and l and c: PB[t].append((d, float(h), float(l), float(c)))
        nights = defaultdict(list)
        for ln in PL_F.read_text().splitlines():
            d, t = ln.split("|"); nights[d].append(t)
        PR = {}
        skipped = 0
        for d, ts in nights.items():
            lst = []
            for t in ts:
                bb = [x for x in PB.get(t, []) if x[0] <= d]
                if not bb or bb[-1][0] != d: skipped += 1; continue
                h, l, c = (np.array([x[k] for x in bb]) for k in (1, 2, 3)); lst.append(ratios(h, l, c, len(bb) - 1))
            PR[d] = lst
        print("names on the list per night (scored / on list): " + ", ".join(f"{d[5:]}: {len(PR[d])}/{len(nights[d])}" for d in sorted(nights)) + f"; {skipped} without a bar on their scan date")
        CUT = PR
        show = [c for c in CELLS if RES[c]["a"]] or []
        chosen = {c for pl in winners.values() for c in [(winners[[k for k in winners if winners[k] == c or True][0]][0][0], 0, 0)]} if False else set()
        for sname, (key, T) in winners.items(): chosen.add((key[0], key[1], T))
        cells_d = sorted(set(show) | chosen, key=CELLS.index)
        print(f"cells shown: all {len(show)} that pass (a)" + (f" plus the plateau-chosen {sorted(chosen)}" if chosen else " (no plateau -> no chosen cell)"))
        print(f'{"cell":<16}' + "".join(f"{d[5:]:>8}" for d in sorted(nights)) + f'{"all nights":>12}')
        for c in cells_d:
            key = (c[0], c[1]); row = []; tot = [0, 0]
            for d in sorted(nights):
                rr = PR[d]; cutn = sum(not passes(r_, key, c[2]) for r_ in rr); row.append(cutn / len(rr) if rr else float("nan")); tot[0] += cutn; tot[1] += len(rr)
            print(f'{c[0]+" w"+str(c[1])+" T"+str(c[2]):<16}' + "".join(f"{v:>8.1%}" for v in row) + f'{tot[0]/max(tot[1],1):>12.1%}')
    else:
        print("prod not reachable: (d) SKIPPED")
except Exception as ex:
    print(f"(d) SKIPPED: {type(ex).__name__}: {ex}")

# ───────────────────────────── the chart sheet ─────────────────────────────
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    def score_of(c): e = RES[c]; return (e["a"] + e["b"] + e["c"], e["k269"])
    for pref in ("(a)(b)(c)", "(a)(b)", "(b)(c)"):
        if pref in winners:
            (cd, wn), Tn = winners[pref]; best = (cd, wn, Tn); why = f"plateau {pref}"; break
    else:
        best = max(CELLS, key=score_of); why = "no plateau: the cell satisfying most of (a)(b)(c), then most buys kept"
    cd, wn, Tn = best; key = (cd, wn); e = RES[best]
    print(f"\nSHEET cell = {cd} {NAMES[cd]} window {wn} T {Tn} ({why})")
    charts = [("VOR 2026-11-20", vh, vl, vc, vD)] + [(t + " " + TAG[t]["r"]["E"], TAG[t]["h"], TAG[t]["l"], TAG[t]["c"], TAG[t]["D"]) for t in ("SKLZ", "QS", "OSTK")]
    goods = [s for s in LIVE if s["side"] == "good"][:4]; rnos = [s for s in LIVE if s["reason"]][:4]
    charts += [(f'{s["t"]} {s["grade"]} {s["d"]}', s["h"], s["l"], s["c"], s["D"]) for s in goods + rnos]
    fig, axs = plt.subplots(3, 4, figsize=(22, 14))
    for ax, (ttl, h, l, c, D) in zip(axs.flat, charts):
        a0 = max(0, D - 119); xs = np.arange(a0, D + 1)
        ax.vlines(xs, l[a0:D + 1], h[a0:D + 1], color="0.55", lw=0.8); ax.plot(xs, c[a0:D + 1], color="k", lw=0.8)
        rat = ratios(h, l, c, D)[key]; ok = passes({key: rat}, key, Tn)
        if cd == "C1":
            n = wn
            for (s0, e0, col) in ((D - 2 * n + 1, D - n, "tab:orange"), (D - n + 1, D, "tab:blue")):
                if s0 >= 0:
                    sl = slice(s0, e0 + 1); ax.add_patch(plt.Rectangle((s0, l[sl].min()), e0 - s0, h[sl].max() - l[sl].min(), fill=False, ec=col, lw=2))
        elif cd == "C2":
            z = c2_lines(h, l, D, wn)
            if z:
                lo, up, p = z; X = np.arange(wn); ax.plot(D - wn + 1 + X, np.exp([lo(x) for x in X]), color="tab:green", lw=2); ax.plot(D - wn + 1 + X, np.exp([up(x) for x in X]), color="tab:red", lw=2)
        elif cd == "C3":
            if D - wn + 1 >= 0:
                H, L = _log(h[D - wn + 1:D + 1]), _log(l[D - wn + 1:D + 1]); p = bv.swing_pivots(H, L)
                ax.plot([D - wn + 1 + i for i, v, t in p], [np.exp(v) for i, v, t in p], "o-", color="tab:purple", lw=1.5)
        else:
            for (s0, e0, col) in ((D - 9 - wn, D - 10, "tab:orange"), (D - 9, D, "tab:blue")):
                if s0 >= 0: ax.axvspan(s0, e0, color=col, alpha=0.18)
        ax.set_title(f'{ttl}\n{cd} w{wn} ratio {f3(rat)} T {Tn} -> {"PASS" if ok else "FAIL"}', fontsize=10, color=("tab:green" if ok else "tab:red")); ax.set_xticks([])
    fig.suptitle(f"{cd} {NAMES[cd]} window {wn} T {Tn}  ({why}).  Row 1: VOR, SKLZ, QS, OSTK; rows 2-3: his live-list charts, 4 good/ok then 4 reason-matched no", fontsize=12)
    fig.tight_layout(); fig.savefig(HERE / "sheet.png", dpi=80); print(f"wrote {HERE/'sheet.png'}")
except Exception as ex:
    print(f"SHEET FAILED: {type(ex).__name__}: {ex}")

print("\n" + "=" * 100); print("DEVIATIONS / READINGS"); print("=" * 100)
DEV += [
 "lower-line sheet (12 charts) NOT reported: its bars need the external era-A store via P.setup() (heavy loader, outside any fixture); it is outside bar (c) per the pre-registration, so no bar is affected.",
 "plateau, even-length run: 'the looser of the two middle values' implemented as the HIGHER T of the two middle thresholds (run index len//2).",
 "the (d) 'plateau cells' shown = every cell passing (a) plus the plateau-chosen cells (so the cut is visible even if no plateau exists).",
 "result table row 4 ('(a) fails somewhere and nothing above matched') literally matches whenever any cell fails (a), so row 5 is unreachable when read top-down; row 5's condition is printed ('every (a)-passing cell keeps VOR') as a diagnostic.",
 "historical charts: the 48 windows are the 200-bar NaN-left-padded windows of graded_windows200.npy; a window slice touching padding = unscored = pass.",
 "C2 ratio when gap(N-1) <= 0 with gap(0) > 0 is recorded as 0 (lines met = pass); C1/C4 non-positive denominators = unscored.",
 "C2 upper-line 'after last pivot' point uses the same last-confirmed-pivot (of either type) as the lower line, as in lower_line_slope.",
 "synthetic series: first selfcheck used a 20-bar sine period and printed C2 w30 flat 0.574 / C3 w30 unscored (a 30-bar window then holds one confirmed trough / <3 legs: a property of the test series, not a runner defect); the period was changed to 12 bars (ends on a peak, D=183) before any label-based scoring.",
 "synthetic check tolerances (prereg says 'about 1.0' / 'clearly below'): flat within 0.85-1.15, wedge at least 0.15 below flat; flat C3 >= 0.75.",
]
for d in DEV: print(" - " + d)
