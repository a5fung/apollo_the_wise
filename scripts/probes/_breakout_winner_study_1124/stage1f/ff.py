"""Stage 1f: the 24 candidate features (+ B3, B4) of prereg section 4.1 for ONE event. B1 / B2 are night-level (build.night_benchmarks).

LOOK-AHEAD IS STRUCTURAL: `features_for` receives the ticker's full arrays but its first act is to cut every array to the bars with
index <= Di (D) and keep ONLY open(E) from E's own bar. Nothing below the cut can see E's high / low / close / volume or any later bar.
The corrupt-E proof (corrupt.py) shows it empirically through the same function.

NULL rules (one reason per NULL, first match):
  calendar-window features (2 raw price aside: 8, 13, 17, 18, 21 + 10, 11, 22, 23): history | coverage (< 90% of the window's sessions present)
     | adjustment (audit flag in window; NOT applied to 10, 11, 21, 22, 23 per the prereg's own text) | identity (guard break in window)
     | zero_volume (3, 17, 18) | bad_price | feature-specific.
  live-code values (1, 3-7, 9, 12, 14-16, 19, 20, B3): exempt from the calendar rules (prereg 4.0); NULL only when the live code returns nothing.
"""
import bisect
import math
import numpy as np

SEG = {"f01": "volatility", "f02": "size", "f03": "size", "f04": "strength", "f05": "strength", "f06": "strength", "f07": "run-up", "f08": "run-up",
       "f09": "run-up", "f10": "highs", "f11": "highs", "f12": "base", "f13": "base", "f14": "base", "f15": "tightness", "f16": "tightness",
       "f17": "volume", "f18": "volume", "f19": "averages", "f20": "averages", "f21": "trend", "f22": "trend", "f23": "stage", "f24": "open"}
NAMES = {"f01": "Daily range (ADR20, %)", "f02": "Price (raw close)", "f03": "Dollar volume (20-session median)", "f04": "Strength rank, best",
         "f05": "Strength rank, 1 month", "f06": "Strength rank, 6 months", "f07": "Prior move", "f08": "20-session run-up",
         "f09": "6-month move", "f10": "Close / 52-week high", "f11": "Level IS a 52-week high (2 groups)", "f12": "Base length (sessions)",
         "f13": "Base depth, %", "f14": "Level from a range (2 groups)", "f15": "Last-10-close spread (ADR)", "f16": "Range contraction (5 / prior 5)",
         "f17": "Volume dry-up (10 / prior 50)", "f18": "Up vs down volume (20)", "f19": "Extension above the 10-day (ADR)", "f20": "Shape count (0-5)",
         "f21": "Close vs 200-day (ADR)", "f22": "Sessions since 52-week low", "f23": "First base since the major low (2 groups)",
         "f24": "Gap at the open (ADR)", "B1": "Pick-model score", "B2": "Live order score", "B3": "Group strength", "B4": "Distance close(D) to level (ADR)"}
FEATS = [f"f{i:02d}" for i in range(1, 25)]
BENCH = ["B1", "B2", "B3", "B4"]
TWO_GROUP = ["f11", "f14", "f23"]
WIN252 = {"f10", "f11", "f22", "f23"}


def _has(dates_sorted, lo, hi):
    if not dates_sorted:
        return False
    k = bisect.bisect_left(dates_sorted, lo)
    return k < len(dates_sorted) and dates_sorted[k] <= hi


def features_for(*, bv, cb, B, cal, d, ci, o, h, l, c, v, Di, row, raw_close, raw_src, era, flag_dates, guard_dates, o_override=None):
    """cal = the era's calendar as ISO strings; d/ci/o/h/l/c/v = the ticker's FULL series; Di = index of D; row = the stored cross-section values
    (rs_best, rs_1m, rs_6m, group_strength, level, adr20 are re-derived here from bars where possible). Returns (vals, nulls, diag)."""
    ciD = int(ci[Di])
    assert Di + 1 < len(ci) and int(ci[Di + 1]) == ciD + 1, "E must be the next session"
    oE = float(o[Di + 1]) if o_override is None else float(o_override)      # the ONLY value taken from E's bar
    # ------------------------------------------------ THE CUT: nothing at or after E survives below this line
    dd, cci, oo, hh, ll, cc, vv = d[:Di + 1], ci[:Di + 1], o[:Di + 1], h[:Di + 1], l[:Di + 1], c[:Di + 1], v[:Di + 1]
    del d, ci, o, h, l, c, v
    assert cci[-1] == ciD and len(cci) == Di + 1
    # ------------------------------------------------
    n_pre = len(cci)
    first_ci = int(cci[0])
    vals, nulls, diag = {}, {}, {}
    tb = cb.daily_bars_from_arrays(dd, oo, hh, ll, cc, vv)
    g = bv.v1_gates(tb, Di, rs_best=float(row["rs_best"]), raw_close=float(raw_close), cidx=cci)
    assert g["failed"] == [] or set(g["failed"]) <= set(bv.CONTEXT_GATES)
    adr = g["adr20"]
    level = g["level"]
    close = float(cc[Di])
    adr_ok = adr is not None and adr > 0
    adr_pct = adr * 100.0 if adr_ok else None
    oi = bv.order_inputs(tb, Di, adr)
    d52, since_low, nb = B.base_facts(tb.h, tb.l, tb.c, Di)
    sg = bv.shape_gates(tb, Di, P=int(g["pole_idx"]), adr20=adr)
    diag.update(level=level, adr20=adr, close=close, failed=",".join(g["failed"]), oE=oE, raw_close=float(raw_close), raw_src=int(raw_src),
                dist_52w_live=d52, level_source=g["level_source"], range_len=(g["range"]["value"]["len"] if g["level_source"] == "range" else None),
                range_exists=bool(g['range']['pass']), since_low_live=since_low, bases_before_live=nb, pole_idx=int(g["pole_idx"]), runup6m_adr=oi["runup6m_adr"],
                spread10_adr=oi["spread10_adr"], vs_ema21_adr=g["gates"]["ema21"]["value"]["vs_ema21_adr"], base_len=int(g["gates"]["prior_move"]["value"]["base_len"]),
                depth_adr=g["gates"]["base_depth"]["value"]["depth_adr"], dollar_vol20=g["gates"]["universe"]["value"]["dollar_vol20"],
                bars_to_d=n_pre)

    def lo_of(n):                                    # first index with ci >= ciD - n + 1 (window D-n+1 .. D)
        return int(np.searchsorted(cci, ciD - n + 1))

    def rule(n, *, adj=True, ident=True, vol=False, price=True):
        if ciD - n + 1 < 0 or first_ci > ciD - n + 1:
            return "history"
        a = lo_of(n)
        if (n_pre - a) / n < 0.90:
            return "coverage"
        lo_date, hi_date = cal[ciD - n + 1], cal[ciD]
        if adj and _has(flag_dates, lo_date, hi_date):
            return "adjustment"
        if ident and _has(guard_dates, lo_date, hi_date):
            return "identity"
        if vol and ((vv[a:] <= 0).any() or not np.isfinite(vv[a:]).all()):
            return "zero_volume"
        if price:
            blk = np.concatenate([oo[a:], hh[a:], ll[a:], cc[a:]])
            if not (np.isfinite(blk).all() and (blk > 0).all()):
                return "bad_price"
        return None

    def put(name, r, fn):
        if r is not None:
            nulls[name] = r
            return
        out = fn()
        if isinstance(out, str):
            nulls[name] = out
        elif out is None or not math.isfinite(out):
            nulls[name] = "not_computable"
        else:
            vals[name] = float(out)

    fin = lambda x: None if (x is None or (isinstance(x, float) and not math.isfinite(x))) else float(x)
    # ---- live-code values (exempt from the calendar rules)
    put("f01", None, lambda: adr_pct)
    put("f02", "derived_only" if (era == "B" and int(raw_src) == 2) else None, lambda: float(raw_close))
    # 3: dollar volume (live value) NULL on a zero-volume 20-session window
    a20 = lo_of(20)
    zero20 = bool((vv[a20:] <= 0).any() or not np.isfinite(vv[a20:]).all())
    put("f03", "zero_volume" if zero20 else None, lambda: fin(g["gates"]["universe"]["value"]["dollar_vol20"]))
    put("f04", None if row.get("rs_best") is not None and math.isfinite(float(row["rs_best"])) else "no_rank", lambda: float(row["rs_best"]))
    put("f05", None if math.isfinite(float(row["rs_1m"])) else "no_rank", lambda: float(row["rs_1m"]))
    put("f06", None if math.isfinite(float(row["rs_6m"])) else "no_rank", lambda: float(row["rs_6m"]))
    put("f07", None, lambda: fin(g["prior_move"]))
    # 8: 20-session run-up, calendar window D-19..D: close(D) / lowest low - 1
    put("f08", rule(20), lambda: close / float(ll[lo_of(20):].min()) - 1.0)
    put("f09", None, lambda: fin(oi["runup6m"]))
    # 10 / 11 / 22 / 23: the 252-session window rules (history, coverage, identity - no adjustment test, per the prereg text)
    r252 = rule(252, adj=False)
    put("f10", r252, lambda: fin(d52))
    a252 = lo_of(252)
    hmax_cal = float(hh[a252:].max()) if a252 < n_pre else float("nan")
    diag["dist_52w_cal"] = close / hmax_cal if hmax_cal > 0 else float("nan")
    put("f11", r252, lambda: 1.0 if level >= hmax_cal * (1 - 1e-12) else 0.0)
    put("f12", None, lambda: float(diag["base_len"]))
    P = int(g["pole_idx"])
    # 13: base depth %, the base's own highest high (pole top + 1 .. D) - NOT the pole high
    put("f13", rule(max(diag["base_len"], 2)), lambda: (1.0 - float(ll[P + 1:Di + 1].min()) / float(hh[P + 1:Di + 1].max())) * 100.0)
    put("f14", None, lambda: 1.0 if g["level_source"] == "range" else 0.0)      # settled_after_wick and five_day = "no"
    put("f15", None, lambda: fin(oi["spread10_adr"]))
    put("f16", None, lambda: fin(sg["range_contract"]["value"]["range5_over_prev5"]))

    def two_span():
        a, b = lo_of(60), lo_of(10)
        if b - a <= 0 or n_pre - b <= 0:
            return "coverage"
        den = float(np.mean(vv[a:b]))
        if not den > 0:
            return "zero_denominator"
        return float(np.mean(vv[b:])) / den
    put("f17", rule(60, vol=True), two_span)

    def updown():
        a = lo_of(20)
        up = dn = 0.0
        ndn = 0
        for k in range(max(a, 1), n_pre):
            if cci[k - 1] != cci[k] - 1:
                continue
            if cc[k] > cc[k - 1]:
                up += vv[k]
            elif cc[k] < cc[k - 1]:
                dn += vv[k]
                ndn += 1
        if ndn == 0:
            return "no_down_day"
        if not dn > 0:
            return "zero_denominator"
        return up / dn
    put("f18", rule(21, vol=True), updown)
    put("f19", None, lambda: fin(sg["not_extended"]["value"]["close_vs_ema10_adr"]))
    put("f20", None, lambda: float(sum(1 for k in bv.SHAPE_GATES if sg[k]["pass"])))
    # 21: close vs the 200-day SMA in daily ranges; 200 calendar sessions, >= 90% present, mean of the present closes
    r200 = rule(200, adj=False)
    put("f21", r200 if r200 is not None else (None if adr_ok else "no_adr"),
        lambda: (close / float(np.mean(cc[lo_of(200):])) - 1.0) * 100.0 / adr_pct)
    put("f22", r252, lambda: float(since_low))
    put("f23", r252, lambda: 1.0 if nb == 0 else 0.0)
    # 24: gap at the open in daily ranges - open(E) ONLY; 24a opened above the level, 24b at or below
    put("f24", None if adr_ok else "no_adr", lambda: (oE / close - 1.0) * 100.0 / adr_pct if (math.isfinite(oE) and oE > 0) else "no_open")
    diag["f24grp"] = ("a" if oE > level else "b") if (math.isfinite(oE) and "f24" in vals) else ""
    # benchmark parts knowable here
    put("B3", None if math.isfinite(float(row["group_strength"])) else "no_group", lambda: float(row["group_strength"]))
    put("B4", None if adr_ok else "no_adr", lambda: (level / close - 1.0) * 100.0 / adr_pct)
    diag["short_year"] = bool(era == "B" and ciD < 251)        # B1: three of its inputs sit on < 252 sessions of file
    return vals, nulls, diag
