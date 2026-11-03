"""Feature 3, re-defined — 'the pullbacks held the top of the base the stock broke out of before its run'.

The exact definition lives in F3_DEFINITION.md (same folder); this is its only implementation, shared by the
KOD check (kod_check.py) and the scorer (rank_v2_f3.py). Pure function of daily bars <= D; no I/O.

days = [(trade_date, o, h, l, c, v), ...] sorted, sliced to the 5 calendar years before D (rank_v2.py's slice5);
ia = index of D in days; adr = ADR20 % (the encoder's adr20_pct, shared with feature 1).
"""
from __future__ import annotations

PIVOT_WING = 2   # the encoder's PIVOT_WING, mirrored for lows exactly as rank_v2.py R3 does

STATED = dict(adr_mult=1.0, pb_win=40, base_end=250, run_win=60, shelf_win=45, run_min=0.30)


def swing_lows(days, ia, win):
    """rank_v2.py::swing_lows, copied verbatim (pivot in the last `win` sessions, both wings < D)."""
    w = PIVOT_WING
    lows = [x[3] for x in days[:ia]]
    out = []
    for i in range(max(w, ia - win), ia - w):
        if lows[i] <= min(lows[i - w:i]) and lows[i] < min(lows[i + 1:i + 1 + w]):
            out.append((lows[i], i))
    return out


def _argmax_latest(vals, lo, hi):
    """index of the max over vals[lo..hi] inclusive; the LATEST index on ties."""
    best = lo
    for i in range(lo, hi + 1):
        if vals[i] >= vals[best]:
            best = i
    return best


def _argmin_latest(vals, lo, hi):
    best = lo
    for i in range(lo, hi + 1):
        if vals[i] <= vals[best]:
            best = i
    return best


def f3_new(days, ia, adr, prm=STATED):
    """Returns dict: held (0/1/None), into (0/1/None), d1/d2 (ADR, None), and the structure, with reasons."""
    out = dict(held=None, into=None, d1=None, d2=None, dmin=None, structure=None, null=None,
               p_idx=None, p_date=None, p_high=None, s_idx=None, s_date=None, s_low=None,
               shelf_idx=None, shelf_date=None, shelf=None, run_pct=None, lows=None)
    pw, be, R, Wb = prm["pb_win"], prm["base_end"], prm["run_win"], prm["shelf_win"]
    if ia < be:
        out["null"] = f"history<{be}({ia})"
        return out
    if not adr:
        out["null"] = "no_adr"
        return out
    highs = [x[2] for x in days]
    lows_all = [x[3] for x in days]
    # step 1 — the high before the current base: highest high of sessions pw+1 .. be before D
    p = _argmax_latest(highs, ia - be, ia - pw - 1)
    out.update(p_idx=ia - p, p_date=days[p][0], p_high=highs[p])
    # step 2 — the run that set it: its start = the lowest low of the R sessions before P (P included)
    if p - R < 0:
        out["null"] = f"run_window_before_history(P-{R}<0)"
        return out
    s = _argmin_latest(lows_all, p - R, p)
    out.update(s_idx=ia - s, s_date=days[s][0], s_low=lows_all[s])
    # step 3 — the base before the run: the Wb sessions ending at the run's start; the shelf = its highest high
    if s - Wb < 0:
        out["null"] = f"shelf_window_before_history(S-{Wb}<0)"
        return out
    k = _argmax_latest(highs, s - Wb, s)
    shelf = highs[k]
    out.update(shelf_idx=ia - k, shelf_date=days[k][0], shelf=shelf)
    run_pct = highs[p] / lows_all[s] - 1 if lows_all[s] > 0 else None
    out["run_pct"] = run_pct
    # step 4 — pullbacks: the 2 lowest swing lows of the last pw sessions (rank_v2.py R3, unchanged)
    sls = sorted(swing_lows(days, ia, pw))
    out["lows"] = [(days[i][0], lo) for lo, i in sls[:2]]
    if len(sls) < 2:
        out["null"] = f"swing_lows={len(sls)}"
        return out
    d1, d2 = ((lo / shelf - 1) * 100 / adr for lo, _ in sls[:2])
    out.update(d1=d1, d2=d2, dmin=min(d1, d2))
    # structure guard — a base the stock broke out of, and a run worth the name
    if run_pct is None or run_pct < prm["run_min"] - 1e-12:
        out.update(structure="no_run(<%.0f%%)" % (prm["run_min"] * 100), held=0, into=0)
        return out
    if not highs[p] > shelf:
        out.update(structure="no_breakout(P<=shelf)", held=0, into=0)
        return out
    out["structure"] = "ok"
    m = prm["adr_mult"]
    out["held"] = 1 if (d1 >= -m and d2 >= -m) else 0
    out["into"] = 1 if (abs(d1) <= m and abs(d2) <= m) else 0
    return out
