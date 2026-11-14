"""#717 wide-and-loose measures. Every measure reads bars <= the night before the buy (index -1), is scale-free (log
prices) and uses NO list-rule output (no pole, no base length, no v1 level), so an unlisted Qullamaggie buy scores too.
W: (n, >=4, T) o/h/l/c, NaN-padded on the left."""
import numpy as np, pandas as pd


def zz_legs(c, thr):
    """Zigzag on log closes: the sizes of the completed + running legs with reversal threshold thr (log units)."""
    piv, d, ext = [c[0]], 0, c[0]
    for x in c[1:]:
        if d >= 0 and x > ext or d <= 0 and x < ext:
            if d == 0 and abs(x - piv[0]) >= thr:
                d = 1 if x > piv[0] else -1
            if d != 0 or True:
                ext = x if d != 0 else (x if abs(x - piv[0]) > abs(ext - piv[0]) else ext)
        elif d != 0 and abs(x - ext) >= thr:
            piv.append(ext); d = -d; ext = x
    piv.append(ext)
    return np.abs(np.diff(piv))


def measures(W, Ns=(15, 20, 30), chart=189):
    W = np.asarray(W, np.float64)
    h, l, c = np.log(W[:, 1]), np.log(W[:, 2]), np.log(W[:, 3])
    dc = np.diff(c, axis=1)                                   # dc[:, -1] = the last night's close-to-close move
    tr = np.fmax(h[:, 1:], c[:, :-1]) - np.fmin(l[:, 1:], c[:, :-1])
    m = {}
    m["adr20"] = np.nanmean(h[:, -20:] - l[:, -20:], 1)
    ch = np.nanmax(h[:, -chart:], 1) - np.nanmin(l[:, -chart:], 1)          # the height of the chart he looks at
    m["chart_h"] = ch
    for N in Ns:
        box = np.nanmax(h[:, -N:], 1) - np.nanmin(l[:, -N:], 1)             # WIDE RANGE: the high-low box of the last N sessions
        d = dc[:, -N:]
        up, dn = np.nansum(np.clip(d, 0, None), 1), np.nansum(np.clip(-d, 0, None), 1)
        churn = np.fmin(up, dn)                                              # UP AND DOWN: the smaller of (sum of up closes, sum of down closes)
        path = up + dn
        big = np.abs(d) > 0.5 * box[:, None] / np.sqrt(N)                    # (unused scale guard)
        sgn = np.sign(d)
        flips = (sgn[:, 1:] * sgn[:, :-1] < 0)
        m[f"box{N}"] = box
        m[f"box{N}_adr"] = box / m["adr20"]
        m[f"box{N}_chart"] = box / ch
        m[f"churn{N}"] = churn
        m[f"churn{N}_adr"] = churn / m["adr20"]
        m[f"churn{N}_chart"] = churn / ch
        m[f"path{N}"] = path
        m[f"path{N}_box"] = path / box
        m[f"atr{N}"] = np.nanmean(tr[:, -N:], 1)
        m[f"atr{N}_chart"] = m[f"atr{N}"] / ch
        m[f"absc{N}"] = np.nanmean(np.abs(d), 1)                             # mean absolute close-to-close move
        # large reversals: a day that closes the other way from the day before, both moves counted at the smaller size
        rv = np.where(flips[:, -(N - 1):], np.fmin(np.abs(d[:, 1:]), np.abs(d[:, :-1])), 0.0)
        m[f"rev{N}"] = np.nansum(rv, 1)
        m[f"rev{N}_chart"] = m[f"rev{N}"] / ch
        # not tightening: the last 10 sessions' box against the box of the N sessions before them
        b10 = np.nanmax(h[:, -10:], 1) - np.nanmin(l[:, -10:], 1)
        bp = np.nanmax(h[:, -10 - N:-10], 1) - np.nanmin(l[:, -10 - N:-10], 1)
        m[f"b10_prev{N}"] = b10 / bp
        m[f"box10_x_churn{N}"] = np.sqrt(b10 * churn)
        m[f"box{N}_x_churn{N}"] = np.sqrt(box * churn)                       # WIDE x UP-AND-DOWN (geometric mean, a % of price)
        m[f"box{N}_x_churn{N}_chart"] = np.sqrt(box * churn) / ch
        for k in (0.05, 0.08):
            sw = np.array([zz_legs(c[r, -N:][~np.isnan(c[r, -N:])], k) if np.isfinite(c[r, -N:]).sum() > 2 else np.zeros(1) for r in range(len(c))], dtype=object)
            m[f"zzn{N}_{k}"] = np.array([max(0, len(s) - 1) for s in sw], float)          # reversals of >= k
            m[f"zzsum{N}_{k}"] = np.array([float(np.sort(s)[:-1].sum()) if len(s) > 1 else 0.0 for s in sw])   # swing travel without the largest leg
    for N in (20, 30, 40):                                                   # swings sized against the CHART: legs of >= f x the chart's height
        for f in (0.12, 0.15, 0.2, 0.25):
            cnt, trav = np.zeros(len(c)), np.zeros(len(c))
            for r in range(len(c)):
                x = c[r, -N:]; x = x[~np.isnan(x)]
                if len(x) > 2 and ch[r] > 0:
                    s = zz_legs(x, f * ch[r]); s = s[s >= f * ch[r]]
                    cnt[r] = len(s); trav[r] = s.sum() / ch[r]
            m[f"swn{N}_{f}"] = cnt; m[f"swtrav{N}_{f}"] = trav
    m["atr5_atr20"] = np.nanmean(tr[:, -5:], 1) / np.nanmean(tr[:, -20:], 1)
    m["nbars"] = np.isfinite(c).sum(1).astype(float)
    return pd.DataFrame(m)


# ── FROZEN 2026-11-14 on the graded charts only (02_study.out), BEFORE any Qullamaggie buy was scored ──
# wide  = box20_chart   : the high-low box of the last 20 sessions as a share of the height of the 189-session chart (log prices)
# chop  = churn20_chart : over the same 20 sessions, the smaller of (sum of the up closes, sum of the down closes) as a share
#                         of the chart's height — how far price travelled BOTH ways (a one-way run scores ~0, a tight base ~0)
# The line = the least extreme of TDOC / MELI / RRC on each (both are TDOC's): a chart is "as wide and loose as his def-no
# charts" when wide >= WIDE_MIN AND chop >= CHOP_MIN; score = min(wide / WIDE_MIN, chop / CHOP_MIN) >= 1.
MIN_BARS = 60          # fewer bars than this to the night before -> not scored (the chart has no height to compare against)


def score(m, wide_min, chop_min):
    s = np.minimum(m["box20_chart"] / wide_min, m["churn20_chart"] / chop_min)
    return s.where(m["nbars"] >= MIN_BARS)


def core(W):
    """The two frozen components only (fast path for the era-A fires); must equal measures() — asserted in 03_score.py."""
    W = np.asarray(W, np.float64)
    h, l, c = np.log(W[:, 1]), np.log(W[:, 2]), np.log(W[:, 3])
    ch = np.nanmax(h[:, -189:], 1) - np.nanmin(l[:, -189:], 1)
    box = np.nanmax(h[:, -20:], 1) - np.nanmin(l[:, -20:], 1)
    d = np.diff(c, axis=1)[:, -20:]
    churn = np.fmin(np.nansum(np.clip(d, 0, None), 1), np.nansum(np.clip(-d, 0, None), 1))
    return pd.DataFrame({"box20_chart": box / ch, "churn20_chart": churn / ch, "nbars": np.isfinite(c).sum(1).astype(float)})
