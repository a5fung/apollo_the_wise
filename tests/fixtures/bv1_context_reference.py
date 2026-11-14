"""The 2026-11-14 #717 RESEARCH code for the three context checks, copied VERBATIM (bodies unchanged; only the module
layout differs) so the production port in `breakout_v1.context_gates` is tested against the code the scorecard numbers
came from. Sources (era-A probes, 2026-11-14):
  pivots / legs / LOOK / K / CHART   scripts/probes/_717_contract_1114/swings/sw.py
  v3                                 scripts/probes/_717_contract_1114/swings/v3m.py
  lowslope                           scripts/probes/_717_contract_1114/swings/04_lowline.py == _717_lowline_1114/ll.py
  measure / flag (MIN_BARS 189)      scripts/probes/_717_lowline_1114/ll.py — the V3 line is a PARAMETER here: the
                                     research ran 0.212; the line used is MU 2021-12-21's exact V3, 0.2123 strict (the research's stated rule; he signed the check, not a number)
  ret126_of                          scripts/probes/_717_context_1114/ctx.py
  u50 / s50_chg10                    scripts/probes/_717_reasons_1114/01_measure.py::reason_measures
  ONE_D / A2(10)                     scripts/probes/_717_lowline_1114/02_score.py (= _717_context_1114/05_sheet.py)
W: (n, >=4, T) o/h/l/c[,v], NaN-padded on the left, index -1 = the list night D.
"""
import numpy as np

LOOK = 60
K = 3
CHART = 189
V3_LINE_RESEARCH, N_LOW, MIN_BARS = 0.212, 30, 189


def pivots(h, l, k=K):
    n = len(h); ev = []
    for i in range(k, n - k):
        hi = h[i] >= h[i - k:i + k + 1].max(); lo = l[i] <= l[i - k:i + k + 1].min()
        if hi and lo:
            last = ev[-1][2] if ev else 0
            ev += [(i, l[i], -1), (i, h[i], 1)] if last == 1 else [(i, h[i], 1), (i, l[i], -1)]
        elif hi:
            ev.append((i, h[i], 1))
        elif lo:
            ev.append((i, l[i], -1))
    out = []
    for p in ev:
        if out and out[-1][2] == p[2]:
            if (p[2] == 1 and p[1] > out[-1][1]) or (p[2] == -1 and p[1] < out[-1][1]):
                out[-1] = p
        else:
            out.append(p)
    return out


def legs(h, l, k=K):
    p = pivots(h, l, k)
    if not p:
        return np.zeros(0), p
    a = [abs(p[j + 1][1] - p[j][1]) for j in range(len(p) - 1)]
    i0, v0, t0 = p[-1]
    after = slice(i0 + 1, len(h))
    a.append(max(0.0, (v0 - l[after].min()) if t0 == 1 else (h[after].max() - v0)) if i0 + 1 < len(h) else 0.0)
    return np.asarray(a), p


def v3(W):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < LOOK: continue
        hh, ll = h[ok], l[ok]; chart = hh[-CHART:].max() - ll[-CHART:].min()
        a, p = legs(hh[-LOOK:], ll[-LOOK:])
        if len(a) < 2: out[r] = 0.0; continue
        b = int(np.argmax(a[:-1])); s = 0.0
        for j in range(b + 2, len(a) - 1):
            m = min(a[j], a[j + 1])
            if m > a[b + 1:j].min(): s = max(s, m)
        out[r] = s / chart
    return out


def lowslope(W, N):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < max(N, 60): continue
        hh, ll = h[ok], l[ok]; chart = hh[-CHART:].max() - ll[-CHART:].min()
        H, L = hh[-N:], ll[-N:]
        p = pivots(H, L)
        pts = [(i, v) for i, v, t in p if t == -1]
        last = p[-1][0] if p else -1
        if last + 1 < N:
            j = last + 1 + int(np.argmin(L[last + 1:])); pts.append((j, L[j]))
        if len(pts) < 2: out[r] = 0.0; continue
        x = np.array([q[0] for q in pts], float); y = np.array([q[1] for q in pts])
        out[r] = np.polyfit(x, y, 1)[0] * 10 / chart
    return out


def measure(W):
    W = np.asarray(W, np.float64)
    nb = (np.isfinite(np.log(W[:, 1])) & np.isfinite(np.log(W[:, 2]))).sum(1).astype(float)
    return v3(W), lowslope(W, N_LOW), nb


def flag(V3, LS, nb, line=V3_LINE_RESEARCH):
    V3, LS, nb = (np.asarray(x, float) for x in (V3, LS, nb))
    return (nb >= MIN_BARS) & (V3 > line) & (LS <= 0)


def ret126_of(W):
    c = np.asarray(W[:, 3], np.float64); out = np.full(len(c), np.nan)
    for r in range(len(c)):
        x = c[r][~np.isnan(c[r])]
        if len(x) >= 120:
            out[r] = x[-1] / (x[-127] if len(x) >= 127 else x[0]) - 1
    return out


def u50_s50chg10(c, D, adr):
    """reason_measures' "1 — the 50-day" block, on the closes c (bars <= D)."""
    def sma(i):
        return float(c[i - 49:i + 1].mean()) if i >= 49 else float("nan")
    s50 = sma(D)
    return c[D] / s50 - 1.0, (s50 / sma(D - 10) - 1.0) / adr


def one_d_keeps(u50, s50_chg10):
    return not ((u50 < -0.03) and (s50_chg10 < 0))


def a2_10_keeps(s50_chg10, ret126):
    return not ((s50_chg10 < 0) and (ret126 < 0))
