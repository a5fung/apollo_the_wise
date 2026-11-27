"""Stage 2 shared code: the outcome-free feature table (kept events, seed 1124), the thirds / two-group assignment of prereg 5.1,
count-to-ratio functions. READS ONLY: the stage-1f feature table + a random number generator. No bar, no outcome, nothing dated
after 2024-12-31 (asserted). Thirds helper copied from stage1f/lib1f.py (itself the EP study's stats.py) - proven by
reproducing stage 1f's printed layout (check_layout)."""
import hashlib, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
S1F = HERE.parent / "stage1f"
PREREG = REPO / "docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md"
PREREG_SHA = "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a"
A1 = REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md"
A1_SHA = "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10"
TABLE = S1F / "feature_table.tsv.gz"
TABLE_SHA = "d629ef0af85f0ed3404d0e9cffcc6545627fa3dec6230eb4da94cb3ed95bf53c"
SEED = 1124
CUT = "2024-12-31"
MIN_MONTH, MIN_STRATUM, MIN_TWO = 6, 9, 2

FEATS = ["f01", "f02", "f03", "f04", "f05", "f06", "f07", "f08", "f09", "f10", "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20",
         "f21", "f22", "f23", "f24a", "f24b"]
TWO_GROUP = ["f11", "f14", "f23"]
DESC_ONLY = ["f11", "f14", "f23"]          # stage 1f: smaller group under 100 events or under 15% on discovery (f14 empty)
CANDIDATES = [f for f in FEATS if f not in DESC_ONLY]
SEEN = ["f04", "f05", "f06", "f07", "f15", "f16", "f17"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def assert_docs():
    assert sha(PREREG) == PREREG_SHA, "prereg sha256 differs - STOP"
    assert sha(A1) == A1_SHA, "A1 sha256 differs - STOP"
    assert sha(TABLE) == TABLE_SHA, "feature table sha256 differs - STOP"


def load():
    """the whole table; callers filter. SEAL asserted: no E after 2024-12-31 (the table holds none by construction)."""
    T = pd.read_csv(TABLE, sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str}, low_memory=False)
    assert T.E.max() <= CUT and T.D.max() <= CUT, "a row dated after the cut - STOP"
    T["quarter"] = T.E.str[:4] + "Q" + ((T.E.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    return T


def kept_events(T):
    K = T[T.kept == True].reset_index(drop=True)             # noqa: E712  (seed 1124 events only; QM rows and seed-2411-only rows excluded)
    assert (K.set == "DISC").sum() == 5330 and (K.set == "CHECK").sum() == 6266 and len(K) == 11596
    D = K[K.set == "DISC"].reset_index(drop=True)
    assert D.E.max() <= "2020-12-31" and (D.era == "A").all()
    return K, D, K[K.set == "CHECK"].reset_index(drop=True)


def thirds_block(vals):
    """0 bottom / 1 middle / 2 top by np.array_split of the sorted order; a block of equal values is never split: it goes to the third
    holding its mid-rank position ((first+last)//2, the lower of two middle positions)."""
    n = len(vals)
    order = np.argsort(vals, kind="stable")
    pos_third = np.concatenate([np.full(len(p), k) for k, p in enumerate(np.array_split(np.arange(n), 3))])
    out = np.empty(n, dtype=np.int8)
    sv = vals[order]
    a = 0
    while a < n:
        b = a
        while b + 1 < n and sv[b + 1] == sv[a]:
            b += 1
        out[order[a:b + 1]] = pos_third[(a + b) // 2]
        a = b + 1
    return out


def assign_thirds(x, keys, min_n):
    """x: float array (NaN = not scored); keys: list of 1-D arrays defining the group. Returns thirds (0/1/2), -1 = not assigned."""
    out = np.full(len(x), -1, dtype=np.int8)
    ok = np.isfinite(x)
    kdf = pd.DataFrame({f"k{i}": np.asarray(k) for i, k in enumerate(keys)})
    sub = kdf[ok]
    pos_ok = np.flatnonzero(ok)
    for _, idx in sub.groupby(list(sub.columns), sort=False).indices.items():
        pos = pos_ok[idx]
        if len(pos) < min_n:
            continue
        out[pos] = thirds_block(x[pos])
    return out


def assign_two(g, keys, min_each=MIN_TWO):
    """two-group: g 1/0/-1(NULL). Returns 2 (yes) / 0 (no) within groups holding >= min_each of each; else -1."""
    out = np.full(len(g), -1, dtype=np.int8)
    ok = g >= 0
    kdf = pd.DataFrame({f"k{i}": np.asarray(k) for i, k in enumerate(keys)})
    sub = kdf[ok]
    pos_ok = np.flatnonzero(ok)
    for _, idx in sub.groupby(list(sub.columns), sort=False).indices.items():
        pos = pos_ok[idx]
        gy = g[pos]
        if (gy == 1).sum() < min_each or (gy == 0).sum() < min_each:
            continue
        out[pos] = np.where(gy == 1, 2, 0)
    return out


def pop_frame(K, name):
    """a feature's population: f24 splits on f24grp (never pooled); returns (frame, column)."""
    if name in ("f24a", "f24b"):
        return K[(K.f24grp == name[-1]) & K.f24.notna()].reset_index(drop=True), "f24"
    return K, name


def ratio_counts(wt, nt, wb, nb):
    """top / bottom pooled-rate ratio from counts (arrays over draws). Rates smoothed (w + .5)/(n + 1) ONLY when a third holds none
    (prereg 5.1): then BOTH rates are smoothed; else raw."""
    wt = np.asarray(wt, float); wb = np.asarray(wb, float)
    rt, rb = wt / nt, wb / nb
    st, sb = (wt + 0.5) / (nt + 1.0), (wb + 0.5) / (nb + 1.0)
    z = (wt == 0) | (wb == 0)
    return np.where(z, st / sb, rt / rb)


def mh_counts(Wy, ny, Wn, nn):
    """Mantel-Haenszel risk ratio yes/no stratified by block. Wy, Wn: (draws, blocks) winners; ny, nn: (blocks,) group sizes.
    sum_i(a_i n0_i / N_i) / sum_i(c_i n1_i / N_i); NaN when numerator or denominator is 0 (no smoothing invented)."""
    N = ny + nn
    num = (Wy * (nn / N)[None, :]).sum(1)
    den = (Wn * (ny / N)[None, :]).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    return np.where((num > 0) & (den > 0), r, np.nan)


def check_layout(D):
    """reproduce stage 1f's printed discovery layout (bottom / middle / top counts) - proves the copied thirds helper."""
    want = {"f01": (1793, 1775, 1762), "f20": (2058, 1745, 1527), "f24a": (488, 469, 458), "f12": (1811, 1763, 1756)}
    got = {}
    for nm in want:
        DD, col = pop_frame(D, nm)
        t = assign_thirds(DD[col].to_numpy(float), [DD.era.to_numpy(), DD.month.to_numpy()], MIN_MONTH)
        got[nm] = tuple(int((t == q).sum()) for q in (0, 1, 2))
        assert got[nm] == want[nm], (nm, got[nm], want[nm])
    return got
