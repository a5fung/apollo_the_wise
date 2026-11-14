"""#717 lower-line check (2026-11-14) — the measures, shared by 01_capture.py / 02_score.py / 03_sheet.py.
lowslope is _717_contract_1114/swings/04_lowline.py's function VERBATIM (that file runs its study on import, so it is
copied, not imported); V3 = v3m.v3 (imported). THE CHECK: flag when V3 > 0.212 AND lowslope(W, 30) <= 0, and only when
the window holds >= 189 bars (finite high and low) up to the list night D; fewer bars = not scoreable = passes.
W: (n, >=3, T) o/h/l[/c...], NaN-padded on the left, index -1 = D."""
import os, sys
import numpy as np
SWD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_717_contract_1114", "swings")
sys.path.insert(0, SWD)
import sw, v3m  # noqa: E402

V3_LINE, N_LOW, MIN_BARS = 0.212, 30, 189


def lowslope(W, N):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < max(N, 60): continue
        hh, ll = h[ok], l[ok]; chart = hh[-sw.CHART:].max() - ll[-sw.CHART:].min()
        H, L = hh[-N:], ll[-N:]
        p = sw.pivots(H, L)
        pts = [(i, v) for i, v, t in p if t == -1]
        last = p[-1][0] if p else -1
        if last + 1 < N:
            j = last + 1 + int(np.argmin(L[last + 1:])); pts.append((j, L[j]))
        if len(pts) < 2: out[r] = 0.0; continue
        x = np.array([q[0] for q in pts], float); y = np.array([q[1] for q in pts])
        out[r] = np.polyfit(x, y, 1)[0] * 10 / chart
    return out


def measure(W):
    """-> (V3, LS, nbars) arrays (float64 math)."""
    W = np.asarray(W, np.float64)
    nb = (np.isfinite(np.log(W[:, 1])) & np.isfinite(np.log(W[:, 2]))).sum(1).astype(float)
    return v3m.v3(W), lowslope(W, N_LOW), nb


def flag(V3, LS, nb):
    V3, LS, nb = (np.asarray(x, float) for x in (V3, LS, nb))
    return (nb >= MIN_BARS) & (V3 > V3_LINE) & (LS <= 0)
