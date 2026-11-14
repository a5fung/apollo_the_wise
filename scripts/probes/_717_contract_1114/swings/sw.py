"""#717 swing-structure contraction measure (shared by 01_score.py). Bars <= the night before the buy / the list night.
W: (n, >=4, T) o/h/l/c[,v], NaN-padded on the left, index -1 = the last night. Log prices throughout (scale-free)."""
import numpy as np

LOOK = 60        # the base the eye reads: the last 60 sessions (fits the 80-bar fire windows)
K = 3            # a swing high / low = the highest high / lowest low of the 3 bars either side (a "few-bar" pivot)
CHART = 189      # chart height = highest high - lowest low over the last 189 sessions (what the sheets show)
GATE = 0.10      # the late swings must be visible: their mean size >= 10% of the chart's height


def pivots(h, l, k=K):
    """Alternating fractal swing points [(i, price, +1 high / -1 low)], confirmed only (k bars after each)."""
    n = len(h); ev = []
    for i in range(k, n - k):
        hi = h[i] >= h[i - k:i + k + 1].max(); lo = l[i] <= l[i - k:i + k + 1].min()
        if hi and lo:                                       # outside bar: order the two so they alternate with the last point
            last = ev[-1][2] if ev else 0
            ev += [(i, l[i], -1), (i, h[i], 1)] if last == 1 else [(i, h[i], 1), (i, l[i], -1)]
        elif hi:
            ev.append((i, h[i], 1))
        elif lo:
            ev.append((i, l[i], -1))
    out = []
    for p in ev:                                            # two highs in a row -> keep the higher; two lows -> the lower
        if out and out[-1][2] == p[2]:
            if (p[2] == 1 and p[1] > out[-1][1]) or (p[2] == -1 and p[1] < out[-1][1]):
                out[-1] = p
        else:
            out.append(p)
    return out


def legs(h, l, k=K):
    """Swing sizes oldest -> newest. The LAST leg = the move from the last confirmed pivot to the extreme of the bars
    since it (so a tight right side still counts as a small final swing, never vanishes)."""
    p = pivots(h, l, k)
    if not p:
        return np.zeros(0), p
    a = [abs(p[j + 1][1] - p[j][1]) for j in range(len(p) - 1)]
    i0, v0, t0 = p[-1]
    after = slice(i0 + 1, len(h))
    a.append(max(0.0, (v0 - l[after].min()) if t0 == 1 else (h[after].max() - v0)) if i0 + 1 < len(h) else 0.0)
    return np.asarray(a), p


def score_rows(W, chart=None):
    """-> dict of arrays: S (amplitude ratio late / early, NaN = not scoreable), late, early, late_chart, nlegs, lowchg, nbars.
    late = mean of the last 2 legs; early = mean of the 2 legs before them; S = late / early when late >= GATE x chart
    else 0 (swings too small to be wide chop); fewer than 4 legs in the base -> S = 0 (no alternating swings)."""
    W = np.asarray(W, np.float64)
    n = len(W)
    o = {k: np.full(n, np.nan) for k in ("S", "late", "early", "late_chart", "nlegs", "lowchg", "chart", "nbars")}
    for r in range(n):
        h, l = np.log(W[r, 1]), np.log(W[r, 2])
        ok = np.isfinite(h) & np.isfinite(l)
        nb = int(ok.sum()); o["nbars"][r] = nb
        if nb < LOOK:
            continue
        hc, lc = h[ok][-CHART:], l[ok][-CHART:]
        ch = hc.max() - lc.min() if chart is None else float(chart[r]); o["chart"][r] = ch
        hb, lb = h[ok][-LOOK:], l[ok][-LOOK:]
        a, p = legs(hb, lb)
        o["nlegs"][r] = len(a)
        L = [x[1] for x in p if x[2] == -1]
        if len(L) >= 2:
            o["lowchg"][r] = (L[-1] - L[-2]) / ch
        if len(a) < 4:
            o["S"][r] = 0.0; continue
        late, early = a[-2:].mean(), a[-4:-2].mean()
        o["late"][r], o["early"][r], o["late_chart"][r] = late, early, late / ch
        o["S"][r] = (late / early if early > 0 else np.inf) if late >= GATE * ch else 0.0
    return o


# ── V2 (the one revision; written AFTER V1's results and 02_legs_diag.out, i.e. fitted on those printed charts) ──
def score_rows_v2(W, chart=None):
    """RE-EXPANSION after the base's biggest swing. Legs as in V1 (same pivots, last 60 sessions, running final leg kept).
    B = the biggest CONFIRMED leg (the running final leg can never be B). After B, every pair of consecutive legs (j, j+1)
    — the running leg may be the second member — whose SMALLER leg is bigger than some leg already seen since B (a leg
    strictly between B and j) = the swings shrank and then widened again, both ways. S = the largest such smaller-of-pair
    / B; 0 when there is none (swings only decay after the big move = contracting). No size gate."""
    W = np.asarray(W, np.float64)
    n = len(W)
    o = {k: np.full(n, np.nan) for k in ("S", "B", "nlegs", "nbars")}
    for r in range(n):
        h, l = np.log(W[r, 1]), np.log(W[r, 2])
        ok = np.isfinite(h) & np.isfinite(l)
        nb = int(ok.sum()); o["nbars"][r] = nb
        if nb < LOOK:
            continue
        a, p = legs(h[ok][-LOOK:], l[ok][-LOOK:])
        o["nlegs"][r] = len(a)
        if len(a) < 2:
            o["S"][r] = 0.0; continue
        b = int(np.argmax(a[:-1])); B = a[b]; o["B"][r] = B
        s = 0.0
        for j in range(b + 2, len(a) - 1):
            m = min(a[j], a[j + 1])
            if m > a[b + 1:j].min():
                s = max(s, m / B)
        o["S"][r] = s
    return o
