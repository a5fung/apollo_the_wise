"""V3 swing measure (see 03_v3_abs.py)."""
import numpy as np
import sw

def v3(W):
    W = np.asarray(W, np.float64); out = np.full(len(W), np.nan)
    for r in range(len(W)):
        h, l = np.log(W[r, 1]), np.log(W[r, 2]); ok = np.isfinite(h) & np.isfinite(l)
        if ok.sum() < sw.LOOK: continue
        hh, ll = h[ok], l[ok]; chart = hh[-sw.CHART:].max() - ll[-sw.CHART:].min()
        a, p = sw.legs(hh[-sw.LOOK:], ll[-sw.LOOK:])
        if len(a) < 2: out[r] = 0.0; continue
        b = int(np.argmax(a[:-1])); s = 0.0
        for j in range(b + 2, len(a) - 1):
            m = min(a[j], a[j + 1])
            if m > a[b + 1:j].min(): s = max(s, m)
        out[r] = s / chart
    return out

