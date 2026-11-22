#!/usr/bin/env python3
"""The 20 candidate features + 2 benchmarks of prereg §4 (FROZEN v2). ONE entry point: `event_features`.

LOOK-AHEAD IS STRUCTURAL: `event_features` receives the ticker's full series but its first act is to cut every array to the
bars with calendar index < ci(E) (`pre`), keeping only open(E) from E's own bar. Nothing below that cut can see E's high / low /
close / volume or any later bar. The encoder and the shelf-distance code need a row for E to exist, so E's row is REBUILT as
(E, open, open, open, open, 0) — never E's real high / low / close / volume. 05_corrupt.py proves the same thing empirically.

NULL rules (§4.0), first match, one reason each:
  history | coverage | adjustment | identity | zero_volume (12, 13) | feature-specific (no_down_day, no_adr, no_base_bar,
  encode_error, bad_price, zero_denominator).
"""
from __future__ import annotations

import numpy as np

import common as C

FEATS = ["f01", "f02", "f03", "f04", "f05", "f06", "f07", "f08", "f09", "f10", "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20"]
NAMES = {"f01": "gap size %", "f02": "gap size in daily ranges", "f03": "short run-up (20)", "f04": "long run-up (120)",
         "f05": "below the 52-week high", "f06": "open vs the 6-month high", "f07": "sessions since the 6-month high",
         "f08": "flat-base length", "f09": "base depth (40)", "f10": "range tightening", "f11": "closing tightness",
         "f12": "volume dry-up", "f13": "up vs down volume", "f14": "strength vs SPY (60)", "f15": "earlier gap-ups (yes/no)",
         "f16": "unfilled gap-down overhead (yes/no)", "f17": "distance from the 50-day average (daily ranges)", "f18": "price (raw)",
         "f19": "liquidity (median $ volume)", "f20": "levels cleared by the open", "B1": "shelf distance (dmin)", "B1clean": "shelf distance, clean",
         "B2": "ADR20"}
WINDOW = {"f01": 1, "f02": 20, "f03": 20, "f04": 120, "f05": 252, "f06": 120, "f07": 120, "f08": 120, "f09": 40, "f10": 60, "f11": 20,
          "f12": 60, "f13": 21, "f14": 61, "f15": 120, "f16": 250, "f17": 50, "f18": 1, "f19": 20, "f20": 250, "B2": 20}
GROUPS = {"gap": ["f01", "f02"], "run-up / extension": ["f03", "f04", "f17"], "highs": ["f05", "f06", "f07"], "base": ["f08", "f09"],
          "tightness": ["f10", "f11"], "volume": ["f12", "f13"], "strength": ["f14"], "structure": ["f15", "f16", "f20"], "size": ["f18", "f19"]}
TWO_GROUP = ["f15", "f16"]
WINDOW_SCALE = 1.0          # §5.5 window-length ±50% reading (later stage); 1.0 here


def _has_date_in(dates_sorted, lo: str, hi: str) -> bool:
    """any date d in the sorted list with lo <= d <= hi"""
    if not dates_sorted:
        return False
    import bisect
    k = bisect.bisect_left(dates_sorted, lo)
    return k < len(dates_sorted) and dates_sorted[k] <= hi


def event_features(era: str, ticker: str, E: str, series, spy, cal, flag_dates, break_dates, prev_close_raw: float, med_dv20: float,
                   e_row_fill=None) -> tuple[dict, dict]:
    """series / spy = (d, ci, o, h, l, c, v) FULL arrays as loaded; everything at or after E is cut here except open(E).
    e_row_fill: None -> E's rebuilt row is (open, open, open, 0); a 4-tuple (h, l, c, v) -> used instead (the corrupt-E test only).
    Returns (values, null_reasons); a feature is in exactly one of the two."""
    d_all, ci_all, o_all, h_all, l_all, c_all, v_all = series
    ciE = int(np.searchsorted(cal, E))
    assert cal[ciE] == E
    i = int(np.searchsorted(ci_all, ciE))
    assert ci_all[i] == ciE, (ticker, E)
    oE = float(o_all[i])                                   # the ONLY value taken from E's bar
    # ------------------------------------------------ THE CUT: nothing dated E or later survives below this line
    d, ci, o, h, l, c, v = d_all[:i], ci_all[:i], o_all[:i], h_all[:i], l_all[:i], c_all[:i], v_all[:i]
    del d_all, ci_all, o_all, h_all, l_all, c_all, v_all, series
    assert len(ci) and ci[-1] < ciE and d[-1] < E
    sd, sci, so, sh, sl_, sc, sv = spy
    j = int(np.searchsorted(sci, ciE))
    sci, sc = sci[:j], sc[:j]
    del spy, sd, so, sh, sl_, sv
    assert sci[-1] < ciE
    # ------------------------------------------------
    n_pre = len(ci)
    first_ci = int(ci[0])
    assert ci[-1] == ciE - 1, "population guarantees a bar on E-1"
    vals, nulls = {}, {}

    def lo_of(n):                                          # first index of pre with ci >= ciE - n
        return int(np.searchsorted(ci, ciE - n))

    def null_rule(n, slice_lo_date=None, vol=False, rules12=True):
        """§4.0 rules 1-5 for the window E-n..E-1 (rules 3-4 on [slice_lo_date, E-1] when given)."""
        if rules12:
            if ciE - n < 0 or first_ci > ciE - n:
                return "history"
            if (n_pre - lo_of(n)) / n < 0.90:
                return "coverage"
        lo_date = slice_lo_date if slice_lo_date is not None else str(cal[ciE - n])
        hi_date = str(cal[ciE - 1])
        if _has_date_in(flag_dates, lo_date, hi_date):
            return "adjustment"
        if _has_date_in(break_dates, lo_date, hi_date):
            return "identity"
        if vol:
            a = lo_of(n)
            if (v[a:] <= 0).any() or not np.isfinite(v[a:]).all():
                return "zero_volume"
        return None

    def bad_price(n):
        a = lo_of(n)
        blk = np.concatenate([o[a:], h[a:], l[a:], c[a:]])
        return not (np.isfinite(blk).all() and (blk > 0).all())

    def W(k):                                              # scaled window length (1.0 in this stage)
        return max(1, int(round(k * WINDOW_SCALE)))

    # ADR20: the encoder's adr20_pct on the 20 bars before E (rows; the population guarantees they are the 20 sessions E-20..E-1)
    days = [(d[k], float(o[k]), float(h[k]), float(l[k]), float(c[k]), float(v[k])) for k in range(n_pre)]
    fill = e_row_fill if e_row_fill is not None else (oE, oE, oE, 0.0)
    days.append((E, oE, float(fill[0]), float(fill[1]), float(fill[2]), float(fill[3])))      # E's row REBUILT, see module docstring
    ia = n_pre
    adr = C.nbis.adr20_pct(days, ia)
    vals["adr20_raw"] = adr if adr is not None else float("nan")
    r = null_rule(20)
    if r:
        nulls["B2"] = r
    elif adr is None or not adr > 0:
        nulls["B2"] = "no_adr"
    else:
        vals["B2"] = adr
    adr_ok = adr is not None and adr > 0
    cm1 = float(c[-1])

    def put(name, n, fn, vol=False, need_adr=False):
        r = null_rule(n, vol=vol)
        if r is None and bad_price(n):
            r = "bad_price"
        if r is None and need_adr and not adr_ok:
            r = "no_adr"
        if r is not None:
            nulls[name] = r
            return
        out = fn()
        if isinstance(out, str):
            nulls[name] = out
        else:
            vals[name] = float(out)

    # 1 gap size %
    put("f01", 1, lambda: oE / cm1 - 1.0)
    # 2 gap in daily ranges
    put("f02", 20, lambda: (oE / cm1 - 1.0) * 100.0 / adr, need_adr=True)
    # 3 / 4 run-ups
    put("f03", W(20), lambda: cm1 / float(l[lo_of(W(20)):].min()) - 1.0)
    put("f04", W(120), lambda: cm1 / float(l[lo_of(W(120)):].min()) - 1.0)
    # 5 below the 52-week high
    put("f05", W(252), lambda: cm1 / float(h[lo_of(W(252)):].max()) - 1.0)
    # 6 open vs the 6-month high
    put("f06", W(120), lambda: oE / float(h[lo_of(W(120)):].max()) - 1.0)

    # 7 sessions since the 6-month high (latest on ties)
    def f07():
        a = lo_of(W(120)); hh = h[a:]
        k = len(hh) - 1 - int(np.argmax(hh[::-1]))          # latest index of the max
        return (ciE - 1) - int(ci[a + k])
    put("f07", W(120), f07)

    # 8 flat-base length: the largest n <= 120 with max close / min close - 1 <= 15% over the bars present in E-n..E-1
    def f08():
        nmax = W(120); a = lo_of(nmax)
        cc = c[a:]; cci = ci[a:]
        mx = np.maximum.accumulate(cc[::-1]); mn = np.minimum.accumulate(cc[::-1])
        ok = (mx / mn - 1.0) <= 0.15 + 1e-12                 # ok[k] = the last k+1 bars are within 15%
        if ok.all():
            return nmax
        kb = int(np.argmin(ok))                             # first backward step that breaks; bar index from the end
        ci_break = int(cci[len(cc) - 1 - kb])
        return (ciE - 1) - ci_break                         # sessions E-n..E-1 strictly after the breaking bar
    put("f08", W(120), f08)

    # 9 base depth
    put("f09", W(40), lambda: 1.0 - float(l[lo_of(W(40)):].min()) / float(h[lo_of(W(40)):].max()))

    # 10 range tightening / 12 volume dry-up: mean over E-10..E-1 divided by the mean over E-60..E-11
    def two_span(x, short=10, long=60):
        s_, L_ = W(short), W(long)
        a, b = lo_of(L_), lo_of(s_)
        if b - a <= 0 or n_pre - b <= 0:
            return "coverage"
        den = float(np.mean(x[a:b]))
        if not den > 0:
            return "zero_denominator"
        return float(np.mean(x[b:])) / den
    put("f10", W(60), lambda: two_span((h - l) / c))
    # 11 closing tightness
    def f11():
        a = lo_of(W(10)); cc = c[a:]
        return (float(cc.max()) - float(cc.min())) / float(cc.mean()) * 100.0 / adr
    put("f11", 20, f11, need_adr=True)
    put("f12", W(60), lambda: two_span(v), vol=True)

    # 13 up vs down volume over E-20..E-1 (vs the prior calendar session's close; g skipped when that bar is absent)
    def f13():
        a = lo_of(W(20))
        up = dn = 0.0; ndn = 0
        for k in range(a, n_pre):
            if k == 0 or ci[k - 1] != ci[k] - 1:
                continue
            if c[k] > c[k - 1]:
                up += v[k]
            elif c[k] < c[k - 1]:
                dn += v[k]; ndn += 1
        if ndn == 0:
            return "no_down_day"
        if not dn > 0:
            return "zero_denominator"
        return up / dn
    put("f13", W(20) + 1, f13, vol=True)

    # 14 strength vs SPY over 60 sessions
    def f14():
        n = W(60)
        base_ci = ciE - 1 - n
        k = int(np.searchsorted(ci, base_ci))
        if not (k < n_pre and ci[k] == base_ci):
            k2 = int(np.searchsorted(ci, base_ci)) - 1          # the latest bar before session E-61 ...
            if k2 < 0 or ci[k2] < base_ci - 5:                  # ... within the 5 sessions before it
                return "no_base_bar"
            k = k2
        used_ci = int(ci[k])
        s1 = int(np.searchsorted(sci, ciE - 1)); s0 = int(np.searchsorted(sci, used_ci))
        assert sci[s1] == ciE - 1 and sci[s0] == used_ci, "SPY bar missing"
        vals["f14_base_fallback"] = float(used_ci != base_ci)
        return (cm1 / float(c[k])) / (float(sc[s1]) / float(sc[s0])) - 1.0
    put("f14", W(60) + 1, f14)

    # 15 earlier gap-ups (yes / no)
    def f15():
        a = lo_of(W(120))
        for k in range(max(a, 1), n_pre):
            if ci[k - 1] == ci[k] - 1 and o[k] >= 1.05 * c[k - 1]:
                return 1.0
        return 0.0
    put("f15", W(120), f15)

    # 16 unfilled gap-down overhead (yes / no)
    def f16():
        a = lo_of(W(250))
        hmax_from = np.maximum.accumulate(h[::-1])[::-1]     # max high over bars k..E-1
        for k in range(max(a, 1), n_pre):
            if ci[k - 1] == ci[k] - 1 and o[k] <= 0.90 * c[k - 1] and hmax_from[k] < c[k - 1] and oE < c[k - 1]:
                return 1.0
        return 0.0
    put("f16", W(250), f16)

    # 17 distance from the 50-day average in daily ranges
    put("f17", W(50), lambda: (cm1 / float(np.mean(c[lo_of(W(50)):])) - 1.0) * 100.0 / adr, need_adr=True)
    # 18 price (raw, from the event list) / 19 liquidity (event list)
    put("f18", 1, lambda: prev_close_raw)
    put("f19", 20, lambda: med_dv20)

    # 20 + B1: score_one's 5-calendar-year row slice ending at E (copied logic: common.score_one)
    cut = C.five_years_before(E)
    lo = 0
    while lo < ia and days[lo][0] < cut:
        lo += 1
    slice5 = days[lo:ia + 1]
    slice_lo_date = cut                                      # rules 3-4 window for 20 and B1-clean = the whole slice
    r = null_rule(250, slice_lo_date=slice_lo_date)
    if r is None and bad_price(250):
        r = "bad_price"
    if r is not None:
        nulls["f20"] = r
    else:
        enc = C.nbis.encode(ticker, E, {ticker: slice5}, {}, preopen=True)       # n_cleared ONLY (never cls / ma_cleared)
        if "error" in enc or enc.get("n_cleared") is None:
            nulls["f20"] = "encode_error"
        else:
            vals["f20"] = float(enc["n_cleared"])
    res, adr_s = C.score_one(days, ia)
    assert (adr_s is None and adr is None) or abs(adr_s - adr) < 1e-12
    if res["dmin"] is None:
        nulls["B1"] = "f3:" + (res["null"] or "none").split("(")[0]
        nulls["B1clean"] = nulls["B1"]
    else:
        vals["B1"] = float(res["dmin"])
        r = null_rule(250, slice_lo_date=slice_lo_date, rules12=False)
        if r is not None:
            nulls["B1clean"] = r
        else:
            vals["B1clean"] = float(res["dmin"])
    return vals, nulls
