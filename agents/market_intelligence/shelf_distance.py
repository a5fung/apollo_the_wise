"""SHELF DISTANCE — how far the last pullbacks sit from the top of the base the stock
broke out of before its run, in ADR units (`dmin`). PLAN #594.

THE ONE DEFINITION. These functions were written and tested in the analysis folders
(`scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py` and the ADR helper of
`scripts/probes/_533_nbis_structure_encoder.py`) and MOVED here unchanged on 2026-11-21 so
the live record and every analysis script read the same code — those two files now import
from this module (pinned by tests/test_594_shelf_rank_shadow.py, which also reproduces the
11 values of the 2026-11-21 labelled sample). The written rule:
`scripts/probes/_ep_rank_v2_1103/build_f3/F3_DEFINITION.md`. The evidence:
`docs/analysis/ep_rank_v2_prereg_2026-11-03.md` RESULT 6-9.

WHAT IT IS USED FOR. A RECORD ONLY — the seventh recorded ranking of the #533 within-day
slot watch (`ep_slot_rank_shadow.py`, `rank_shelf`). Operator ruling 2026-11-21: "Aligned,
but we should keep testing this idea". It changes no slot allocation, order, entry or size.

NO LOOK-AHEAD. `f3_new(days, ia, adr)` reads `days[:ia]` only — never the bar at `ia` or
later (swing lows from `days[:ia]`, ADR from `days[ia-20:ia]`, every high/low window ends
at `ia - 41` or earlier). So the gap day itself is not needed: production passes the bars
BEFORE the gap day and `ia = len(days)` (`shelf_distance_from_prior_days`), which gives
the same numbers as the analysis convention of the gap day as the last element (tested).

HISTORY DEPTH. The furthest bar read is `base_end + run_win + shelf_win` = 355 sessions
before the gap day; anything deeper cannot change the result (tested). Fewer than 250
prior sessions -> NULL with a reason, never a guess.

Standard library only, no I/O — the analysis scripts import this offline.
"""
from __future__ import annotations

import statistics as st

PIVOT_WING = 2      # a swing low is the lowest low of the 2 sessions either side
ADR_LOOKBACK = 20   # ADR20: mean daily (high - low) / close over the 20 sessions before D

STATED = dict(adr_mult=1.0, pb_win=40, base_end=250, run_win=60, shelf_win=45, run_min=0.30)

# The deepest session any step can read, counted back from the gap day.
MAX_SESSIONS_READ = STATED["base_end"] + STATED["run_win"] + STATED["shelf_win"]


def adr20_pct(days: list, ia: int) -> float | None:
    lo = max(0, ia - ADR_LOOKBACK)
    win = days[lo:ia]
    if len(win) < 10:
        return None
    return st.fmean((h - l) / c * 100.0 for _, _, h, l, c, _ in win)


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


def shelf_distance_from_prior_days(prior_days: list) -> dict:
    """The production entry point: `prior_days` = daily (date, o, h, l, c, v) sorted
    oldest-first, EVERY bar strictly BEFORE the gap day. Returns `f3_new`'s dict plus
    `adr` (ADR20 %) and `asof` (the last bar's date, None on an empty list).

    A bar with a missing or non-positive high / low / close in the part that is read
    (the last 355 sessions) gives NULL with the reason `bad_bar(<date>)` — a dropped row
    would shift every session count, and a zero close would divide by zero in the ADR."""
    ia = len(prior_days)
    read = prior_days[-MAX_SESSIONS_READ:]
    for d in read:
        if any(d[j] is None or not d[j] > 0 for j in (2, 3, 4)):
            out = f3_new([], 0, None)
            out.update(null=f"bad_bar({d[0]})", adr=None, asof=prior_days[-1][0])
            return out
    adr = adr20_pct(prior_days, ia)
    out = f3_new(prior_days, ia, adr)
    out.update(adr=adr, asof=prior_days[-1][0] if prior_days else None)
    return out
