"""Stage 6 DRAFT (not a freeze) - the operator's gallery read #1, 'V into the breakout', as components for ONE event.

LOOK-AHEAD IS STRUCTURAL: `v_parts` receives arrays ALREADY CUT at D by the caller (`cut_at_D`), asserts the last bar is D, and never
receives open(E). Level and ADR20 are recomputed here from the cut bars through the live `bv.v1_gates` (as stage 1f's features_for does).

Windows are CALENDAR sessions (ci), stage 1f's NULL rules: history | coverage (< 100% of the 85-session window: the list's own data
guard is 86 consecutive bars ending D, so a hole is a defect, not a thin window) | adjustment | identity | bad_price | no_adr.
"""
import bisect
import math
import numpy as np

WIN = 85          # D-84 .. D : the list's guaranteed history (DEEP = 85) and the 1.3 drop window
T_MAX_AGE = 59    # the trough lies in D-59 .. D
PRE = 25          # the drop leg: the highest high of the 25 sessions before the trough
NEAR_ADR = 1.0    # 'at the level' = a high within one daily range under the level (or above it)
# thresholds of the DRAFT definition (chosen before any outcome was joined; see definition_DRAFT.md)
DROP_ADR_MIN = 5.0
RECOVER_MIN = 0.5    # first written as 2/3; moved to 1/2 at the face check on shape (definition_DRAFT.md), BEFORE any outcome was joined
AT_LEVEL_MAX = 9  # fewer than 10 sessions at the level = no base by the list's own minimum (BASE_MIN = 10)
COMPONENTS = ["trough_age", "drop_adr", "drop_len", "recover", "at_level", "rally_adr"]


def _has(dates_sorted, lo, hi):
    if not dates_sorted:
        return False
    k = bisect.bisect_left(dates_sorted, lo)
    return k < len(dates_sorted) and dates_sorted[k] <= hi


def cut_at_D(series, Di):
    """the ONLY place the full series is touched: returns arrays with index <= Di. open(E) is NOT taken."""
    d, ci, o, h, l, c, v = series
    return d[:Di + 1], ci[:Di + 1], o[:Di + 1], h[:Di + 1], l[:Di + 1], c[:Di + 1], v[:Di + 1]


def v_parts(*, bv, cb, cal, cut, ciD, rs_best, raw_close, flag_dates, guard_dates):
    """cut = (d, ci, o, h, l, c, v) with last bar == D. Returns (vals, null_reason)."""
    dd, cci, oo, hh, ll, cc, vv = cut
    n = len(cci)
    assert int(cci[-1]) == int(ciD), "the last bar handed in must be D"
    Di = n - 1
    lo_ci = ciD - WIN + 1
    if lo_ci < 0 or int(cci[0]) > lo_ci:
        return {}, "history"
    a = int(np.searchsorted(cci, lo_ci))
    if n - a != WIN:
        return {}, "coverage"
    if _has(flag_dates, cal[lo_ci], cal[ciD]):
        return {}, "adjustment"
    if _has(guard_dates, cal[lo_ci], cal[ciD]):
        return {}, "identity"
    blk = np.concatenate([oo[a:], hh[a:], ll[a:], cc[a:]])
    if not (np.isfinite(blk).all() and (blk > 0).all()):
        return {}, "bad_price"
    tb = cb.daily_bars_from_arrays(dd, oo, hh, ll, cc, vv)
    g = bv.v1_gates(tb, Di, rs_best=float(rs_best), raw_close=float(raw_close), cidx=cci)
    adr, level = g["adr20"], g["level"]
    if adr is None or not adr > 0 or level is None or not math.isfinite(level):
        return {}, "no_adr"
    H, L = np.asarray(hh[a:], float), np.asarray(ll[a:], float)      # positions 0 .. 84 ; D = 84
    lowv = float(L.min())
    T = int(np.flatnonzero(L == lowv)[-1])                           # the LATEST session making the window's lowest low
    age = (WIN - 1) - T
    vals = {"trough_age": float(age), "level": float(level), "adr20": float(adr)}
    if age > T_MAX_AGE:                                              # the low of the 85 sessions is older than 60 sessions: no V in view
        vals.update(drop_adr=float("nan"), drop_len=float("nan"), recover=float("nan"), at_level=float("nan"), rally_adr=float("nan"))
        return vals, None
    pre = H[T - PRE:T]                                               # T >= 25 by construction (age <= 59, window 85)
    assert len(pre) == PRE
    H1 = float(pre.max())
    kH = int(np.flatnonzero(pre == H1)[-1])                          # latest session at that high
    drop = (H1 - lowv) / H1
    vals["drop_adr"] = drop / adr
    vals["drop_len"] = float(PRE - kH)                               # sessions from the high to the trough
    vals["recover"] = (level - lowv) / (H1 - lowv) if H1 > lowv else float("nan")
    vals["rally_adr"] = (level / lowv - 1.0) / adr
    near = np.flatnonzero(H[T + 1:] >= level * (1.0 - NEAR_ADR * adr))
    vals["at_level"] = float((WIN - 1) - (T + 1 + int(near[0]))) if len(near) else 0.0   # sessions since price first got back to the level
    return vals, None


def flag(vals, *, drop_min=DROP_ADR_MIN, rec_min=RECOVER_MIN, at_max=AT_LEVEL_MAX):
    """the DRAFT binary: 1 = V into the breakout. vals from v_parts (scored)."""
    if not (vals["trough_age"] <= T_MAX_AGE):
        return 0
    return int(vals["drop_adr"] >= drop_min and vals["recover"] >= rec_min and (at_max is None or vals["at_level"] <= at_max))
