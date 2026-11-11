"""#717 initial rules: the range-break buy trigger as PURE functions on bars <= D (the port of rating.py's High tier,
`docs/analysis/cb_initial_rules_2026-11-11.md` (b)). h / l / c / v are numpy arrays; D indexes the list night."""
import numpy as np

LOOKBACK = 126
MIN_LEN = 10
RATIO = 0.5
RUN_LOOKBACK = 60
VOL_N = 20
READY_X = 1.0


def avg_range(h, l, D):
    a = max(0, D - VOL_N + 1)
    return float((h[a:D + 1] - l[a:D + 1]).mean())


def range_levels(h, l, D, min_len=MIN_LEN, ratio=RATIO):
    """Every qualifying range at night D, lowest level first: [dict(level, start, len)] — len counts to E = D + 1."""
    tol = avg_range(h, l, D)
    out, m = [], -np.inf
    for j in range(D, max(-1, D - LOOKBACK), -1):
        if h[j] > m:
            m = float(h[j])
            out.append([m, j])
        if h[j] >= m - tol:
            out[-1][1] = j
    res = []
    for level, s in out:
        n = D + 1 - s
        if n < min_len or s < 1:
            continue
        run = level - float(l[max(0, s - RUN_LOOKBACK):s].min())
        depth = level - float(l[s:D + 1].min())
        if run > 0 and depth <= ratio * run:
            res.append(dict(level=level, start=s, len=n))
    return res


def vol_bar20(v, D):
    return float(v[D - VOL_N + 1:D + 1].mean()) if D >= VOL_N - 1 else None


def ready(levels, close_d, rng, x=READY_X):
    """The lowest qualifying level no more than x average daily ranges above the close of D, else None."""
    for k in levels:
        if k["level"] - close_d <= x * rng:
            return k
    return None


def triggered(levels, vbar, hi_e, close_e, vol_e):
    """The buy on E: the lowest qualifying level the high takes out with the close above it and volume above the bar."""
    if vbar is None or not vol_e > vbar:
        return None
    for k in levels:
        if hi_e > k["level"] and close_e > k["level"]:
            return k
    return None
