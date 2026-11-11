#!/usr/bin/env python3
"""#717: rate each Qullamaggie buy — how confident it was a breakout, and where the buy point was.

The method is `docs/analysis/cb_qm_buy_confidence_2026-11-11.md` (committed before this ran). Pure functions + loaders;
reads only the two scorecard fixtures (no bar after `hi` exists in them)."""
import csv
import gzip
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

FX = Path("tests/fixtures/qm_breakout_scorecard")
FUNDS = frozenset("AGQ BOIL BRZU CWEB ERX FAS GUSH IWN JETS KWEB UVXY VXX XRT YINN".split())
LOOKBACK = 126          # how far back a taken-out level may sit
MIN_LEN = 10            # a range of 2 weeks
SHORT_LEN = 5           # the smallest pivot counted at all
RATIO = 0.5             # holds its gains: the range gives back no more than half the run
RUN_LOOKBACK = 60       # the run = level - lowest low of the 60 sessions before the range starts
VOL_N = 20
IPO_MIN = 60
EP_GAP = 0.09
TIERS = ("High", "Medium", "Low", "Not")


def load():
    """[dict(set, eid, sym, ticker, lo, hi, dates, o, h, l, c, v, win, row)] for the 757 buys."""
    out = []
    for name, buys, bars in (("dated", "buys.tsv", "bars.psv.gz"), ("widened", "buys_undated_widened.tsv", "bars_undated_widened.psv.gz")):
        by = defaultdict(list)
        with gzip.open(FX / bars, "rt") as f:
            for r in csv.DictReader(f, delimiter="|"):
                by[r["eid"]].append(r)
        for r in csv.DictReader(open(FX / buys), delimiter="\t"):
            rr = sorted(by[r["eid"]], key=lambda x: x["date"])
            ds = [date.fromisoformat(x["date"]) for x in rr]
            lo, hi = (r["E"], r["E"]) if name == "dated" else (r["lo"], r["hi"])
            win = [i for i, d in enumerate(ds) if date.fromisoformat(lo) <= d <= date.fromisoformat(hi)]
            assert win and win[-1] == len(ds) - 1, (name, r["eid"], "bars must end on hi")
            a = {k: np.array([float(x[k]) for x in rr]) for k in "ohlcv"}
            out.append(dict(set=name, eid=r["eid"], sym=r["sym"], ticker=r["ticker"], lo=lo, hi=hi, dates=ds, win=win, row=r, **a))
    return out


def _levels(x, top, t, tol):
    """Walk back from t-1: every bar of series x above all of x between it and t, and below `top` -> [(level, p, start)],
    lowest first. `start` (amendment 1) = the earliest session, among those the level stands above, within `tol` of it."""
    out, m = [], -np.inf
    j = t - 1
    stop = max(-1, t - 1 - LOOKBACK)
    while j > stop:
        if x[j] >= top:
            break
        if x[j] > m:
            m = x[j]
            out.append([float(x[j]), j, j])
        if x[j] >= m - tol:
            out[-1][2] = j
        j -= 1
    return [tuple(k) for k in out]


def _holds(b, level, s, t, ratio):
    if s < 1:
        return False
    run = level - b["l"][max(0, s - RUN_LOOKBACK):s].min()
    depth = level - b["l"][s:t].min()
    return bool(run > 0 and depth <= ratio * run)


def rate_session(b, t, min_len=MIN_LEN, ratio=RATIO, use_holds=True):
    """The session's tier and the level that earns it. -> dict(tier, level, p (range start), len, path, closed, vol, holds, reason)."""
    vol = bool(t >= VOL_N and b["v"][t] > b["v"][t - VOL_N:t].mean())
    tol = float((b["h"][max(0, t - VOL_N):t] - b["l"][max(0, t - VOL_N):t]).mean()) if t >= 1 else 0.0
    cands = []
    for level, _, s in _levels(b["h"], b["h"][t], t, tol):
        n = t - s
        if n < SHORT_LEN:
            continue
        cands.append(dict(level=level, p=s, len=n, path="high", closed=bool(b["c"][t] > level), vol=vol,
                          holds=(_holds(b, level, s, t, ratio) if use_holds else True)))
    for k in cands:                                              # High: the lowest level that earns it
        if k["len"] >= min_len and k["holds"] and k["closed"] and k["vol"]:
            return dict(k, tier="High", reason="range_break")
    for k in cands:
        if k["holds"] and ((k["len"] >= min_len and (k["closed"] or k["vol"])) or (k["len"] < min_len and k["closed"] and k["vol"])):
            return dict(k, tier="Medium", reason="range_break_partial" if k["len"] >= min_len else "short_pivot")
    if vol:
        for level, _, s in _levels(b["c"], b["c"][t], t, tol):  # the close path (ignore a spike / wicks)
            if t - s >= min_len and (_holds(b, level, s, t, ratio) if use_holds else True):
                return dict(level=level, p=s, len=t - s, path="close", closed=True, vol=True, holds=True, tier="Medium", reason="close_break")
    a = max(0, t - RUN_LOOKBACK)                                 # amendment 1: a short pivot inside a range that holds its gains
    if t - a >= min_len:
        top = a + int(np.argmax(b["h"][a:t]))
        if t - top >= min_len and (_holds(b, float(b["h"][top]), top, t, ratio) if use_holds else True):
            R = 0
            while t - 1 - R >= 0 and b["h"][t - 1 - R] < b["h"][t]:
                R += 1
            if R >= 3:
                piv = float(b["h"][t - R:t].max())
                if b["c"][t] > piv and piv < b["h"][top]:
                    return dict(level=piv, p=top, len=t - top, path="pivot", closed=True, vol=vol, holds=True, tier="Medium", reason="inside_range")
    if not cands:
        return dict(tier="Low", reason="no_level", level=None, p=None, len=None, path="", closed=None, vol=vol, holds=None)
    k = max(cands, key=lambda k: k["len"])
    return dict(k, tier="Low", reason="gives_back" if not any(c["holds"] for c in cands) else "weak_pivot")


def sma(c, n, k=50):
    return float(c[n - k + 1:n + 1].mean()) if n >= k - 1 else None


def overrides(b, n):
    """(category, tier) of the first override that fires at night n, else None. fund / ipo / ep_gap are checked by the caller's order."""
    c, h, l = b["c"], b["h"], b["l"]
    s_now, s_then = sma(c, n), sma(c, n - 20) if n >= 20 else None
    if s_now is not None and s_then is not None and c[n] < s_now and s_now < s_then:
        return "downtrend"
    a = max(0, n - 125)
    if n - a + 1 >= 60:
        lo_i = a + int(np.argmin(l[a:n + 1]))
        if n - lo_i < 20 and c[n] < (h[a:n + 1].max() + l[a:n + 1].min()) / 2:
            return "bounce"
    return None


def rate(b, min_len=MIN_LEN, ratio=RATIO, use_holds=True, use_trend=True):
    win = b["win"]
    per = [(t, rate_session(b, t, min_len, ratio, use_holds)) for t in win]
    t, s = min(per, key=lambda x: (TIERS.index(x[1]["tier"]), x[0]))
    out = dict(s, t=t, base_tier=s["tier"], base_reason=s["reason"])
    if s["tier"] == "Low":
        for tb in (win[0] - 1, win[0] - 2):
            if tb > SHORT_LEN and rate_session(b, tb, min_len, ratio, use_holds)["tier"] == "High":
                out["reason"] = out["base_reason"] = "broke_before"
                break
    if b["ticker"] in FUNDS:
        out.update(tier="Not", reason="fund")
    elif win[0] < IPO_MIN:
        out.update(tier="Not", reason="ipo")
    elif any(b["o"][i] >= (1 + EP_GAP) * b["c"][i - 1] for i in win if i >= 1):
        out.update(tier="Not", reason="ep_gap")
    elif use_trend:
        cat = overrides(b, t - 1)
        if cat:
            out.update(tier="Low", reason=cat)
    return out
