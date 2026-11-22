"""t_00_lib: shared helpers for the §13.1 turning-point run (no outcome is opened here)."""
import pandas as pd, numpy as np
O = "build_r2"; CUT = pd.Timestamp("2024-12-31"); VS, VE = pd.Timestamp("2017-01-18"), pd.Timestamp("2024-09-27")
H1END, H2START = pd.Timestamp("2020-12-31"), pd.Timestamp("2021-01-04")
KEPT = "M1 F1 F2 R1 D1 K1 C3 R2 K5 M2".split()
NAME = dict(M1="gold/silver", F1="net liquidity", F2="funds rate", R1="10y real yield", D1="dollar fund", K1="small vs large", C3="Baa spread", R2="2-year", K5="speculative growth", M2="copper/gold")
def ma(s, w): return s.rolling(w, min_periods=w).mean()
def sign_series(diff):
    """daily sign of a difference rounded to 9 decimals; 0 or missing -> NaN (to be carried)."""
    d = np.round(diff.values.astype(float), 9); s = np.where(np.isnan(d), np.nan, np.sign(d)); s[s == 0] = np.nan
    return pd.Series(s, diff.index)
def turns(s):
    """§13.1 (1) the one turn rule. s: +1/-1/NaN on the grid. Returns list of (position, new_sign) for confirmed turns,
    the carried sign series, and the position of the first raw sign. A tie/missing carries the previous session's sign
    (after its own carry); a turn = a sign different from the last CONFIRMED direction held 5 consecutive sessions, dated at the 5th;
    the first confirmed sign is a starting direction, not a turn."""
    v = s.values; n = len(v); c = np.full(n, np.nan); prev = np.nan
    for i in range(n):
        if not np.isnan(v[i]): prev = v[i]
        c[i] = prev
    out = []; conf = None; run = 0; rs = np.nan
    for i in range(n):
        if np.isnan(c[i]): continue
        if c[i] == rs: run += 1
        else: rs = c[i]; run = 1
        if run == 5:
            if conf is None: conf = rs
            elif rs != conf: conf = rs; out.append((i, int(rs)))
        # run > 5 in a new sign cannot happen unconfirmed: it was confirmed at 5
    first = int(np.flatnonzero(~np.isnan(c))[0]) if (~np.isnan(c)).any() else None
    return out, pd.Series(c, s.index), first
