#!/usr/bin/env python3
"""EP big-winner chart study — STAGE 4 (prereg §6 step 6): HIS GALLERY READS coded as H1-H3 (prereg §11).

LOOK-AHEAD IS STRUCTURAL (same rule as stage1/features.py): `h_features` cuts every array to calendar index < ci(E) and keeps
only open(E) from E's own bar. No outcome is computed anywhere in this folder.

Windows are CALENDAR sessions (§4.0). All averages are of ADJUSTED closes and are only ever COMPARED with open(E) or with each
other (ratios within one ticker — no adjusted level is a feature).
  SMA200(E-1)  = mean close of the bars present in sessions E-200..E-1      (the f17 precedent: mean of the bars present)
  SMA200(E-21) = mean close of the bars present in sessions E-220..E-21
  SMA50(E-1)   = mean close of the bars present in sessions E-50..E-1
  EMA10, EMA21 = recursive EMA (alpha = 2/(n+1)) over the closes of the bars present in sessions E-200..E-1, in date order,
                 SEEDED at the first bar of that window (so the NULL rules cover every bar the EMA reads; the gallery seeded at the
                 ticker's first bar ever — after 200 bars the seed's weight is (20/22)^199 ~ 6e-9 for EMA21, nil for EMA10).
NULL (first match, one reason; §4.0 rules 1-4 + bad_price):
  H1, H3: window n = 200 -> history | coverage (< 90% of 200) | adjustment | identity | bad_price
  H2    : window n = 220 -> history (first bar later than E-220) | coverage (EITHER 200-session sub-window E-200..E-1 or
          E-220..E-21 under 90%) | adjustment / identity anywhere in E-220..E-1 | bad_price
Values: 1.0 = yes, 0.0 = no.
  H1 "below the 200-day at the open"      : yes iff open(E) <  SMA200(E-1)                      his direction: NO wins
  H2 "in a downtrend"                     : yes iff open(E) <  SMA200(E-1) AND SMA200(E-1) < SMA200(E-21)      NO wins
  H3 "above all moving averages at open"  : yes iff open(E) >  max(EMA10, EMA21, SMA50, SMA200) through E-1    YES wins
"""
from __future__ import annotations

import bisect

import numpy as np

HS = ["H1", "H2", "H3"]
HNAMES = {"H1": "below the 200-day at the open (yes/no)", "H2": "in a downtrend (yes/no)", "H3": "above all moving averages at the open (yes/no)",
          "H4": "ADR20 (= benchmark B2)"}
HWIN = {"H1": 200, "H2": 220, "H3": 200}


def _has_date_in(dates_sorted, lo: str, hi: str) -> bool:
    if not dates_sorted:
        return False
    k = bisect.bisect_left(dates_sorted, lo)
    return k < len(dates_sorted) and dates_sorted[k] <= hi


def ema_last(x: np.ndarray, n: int) -> float:
    a = 2.0 / (n + 1.0)
    e = float(x[0])
    for k in range(1, len(x)):
        e = a * float(x[k]) + (1.0 - a) * e
    return e


def h_features(era: str, ticker: str, E: str, series, cal, flag_dates, break_dates) -> tuple[dict, dict, dict]:
    """series = (d, ci, o, h, l, c, v). Returns (values, null_reasons, parts) — parts = the averages, for printing only."""
    d_all, ci_all, o_all, h_all, l_all, c_all, v_all = series
    ciE = int(np.searchsorted(cal, E))
    assert cal[ciE] == E
    i = int(np.searchsorted(ci_all, ciE))
    assert ci_all[i] == ciE, (ticker, E)
    oE = float(o_all[i])                                   # the ONLY value taken from E's bar
    # ------------------------------------------------ THE CUT: nothing dated E or later survives below this line
    d, ci, o, h, l, c = d_all[:i], ci_all[:i], o_all[:i], h_all[:i], l_all[:i], c_all[:i]
    del d_all, ci_all, o_all, h_all, l_all, c_all, v_all, series
    assert len(ci) and ci[-1] == ciE - 1 and d[-1] < E
    # ------------------------------------------------
    n_pre = len(ci)
    first_ci = int(ci[0])
    vals, nulls, parts = {}, {}, {"open": oE}

    def idx(a_off, b_off):                                 # bars present in sessions E-a_off .. E-b_off (inclusive)
        return int(np.searchsorted(ci, ciE - a_off)), int(np.searchsorted(ci, ciE - b_off, side="right"))

    def rules(n, subwindows):
        if ciE - n < 0 or first_ci > ciE - n:
            return "history"
        for a_off, b_off in subwindows:
            a, b = idx(a_off, b_off)
            if (b - a) / (a_off - b_off + 1) < 0.90:
                return "coverage"
        lo_date, hi_date = str(cal[ciE - n]), str(cal[ciE - 1])
        if _has_date_in(flag_dates, lo_date, hi_date):
            return "adjustment"
        if _has_date_in(break_dates, lo_date, hi_date):
            return "identity"
        a = int(np.searchsorted(ci, ciE - n))
        blk = np.concatenate([o[a:], h[a:], l[a:], c[a:]])
        if not (np.isfinite(blk).all() and (blk > 0).all()) or not (np.isfinite(oE) and oE > 0):
            return "bad_price"
        return None

    r200 = rules(200, [(200, 1)])
    if r200 is None:
        a, b = idx(200, 1)
        w = c[a:b]
        sma200 = float(np.mean(w))
        a50, b50 = idx(50, 1)
        sma50 = float(np.mean(c[a50:b50]))
        e10, e21 = ema_last(w, 10), ema_last(w, 21)
        parts.update(sma200=sma200, sma50=sma50, ema10=e10, ema21=e21)
        vals["H1"] = 1.0 if oE < sma200 else 0.0
        vals["H3"] = 1.0 if oE > max(e10, e21, sma50, sma200) else 0.0
    else:
        nulls["H1"] = r200
        nulls["H3"] = r200
    r220 = rules(220, [(200, 1), (220, 21)])
    if r220 is None:
        assert r200 is None
        a, b = idx(220, 21)
        sma200_lag = float(np.mean(c[a:b]))
        parts["sma200_lag21"] = sma200_lag
        vals["H2"] = 1.0 if (oE < parts["sma200"] and parts["sma200"] < sma200_lag) else 0.0
    else:
        nulls["H2"] = r220
    return vals, nulls, parts
