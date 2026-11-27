"""Cross-era identity map, blind, from the EP prereg text (+ its amendment A2 'identity_alt'): era-A ticker a and era-B ticker b are the SAME identity when
they share >= 40 sessions on the 2021-09-27..2022-06-30 overlap and their close-to-close returns agree within 0.002 on >= 90% of the shared consecutive
pairs; a cross-symbol candidate additionally needs the first 10 shared returns equal at 4 decimals; a same-symbol pair that passes the full test is ONE
identity (A2), one that fails is two. Reads closes dated <= 2022-06-30 only (date compared before the close is used)."""
import numpy as np, pandas as pd, json
import r4_common as C

LO, HI = "2021-09-27", "2022-06-30"
MIN_SHARED, TOL, MIN_AGREE, NFIRST = 40, 0.002, 0.90, 10
FB = C.SCR / "pop" / "cb702_daily_lt2025.csv.gz"
assert FB.exists(), "run the era-B pool pass first (it builds the sealed copy)"


def read(path):
    parts = []
    for ch in pd.read_csv(path, header=None, usecols=[0, 1, 5], dtype=str,
                          keep_default_na=False, chunksize=2_000_000):
        ch.columns = ["t", "d", "c"]
        ch = ch[(ch.d >= LO) & (ch.d <= HI)]
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    df["c"] = df.c.astype(float)
    assert df.d.max() <= HI
    return df


dA, dB = read(C.PRE / "daily_closes_all.csv.gz"), read(FB)
calA = np.array(sorted(dA[dA.t == "SPY"].d)); calB = np.array(sorted(dB[dB.t == "SPY"].d))
assert len(calA) == len(calB) and (calA == calB).all()
S = len(calA)
print("overlap sessions", S)


def mat(df):
    si = np.searchsorted(calA, df.d.to_numpy(dtype="U10"))
    ok = (si < S) & (calA[np.minimum(si, S - 1)] == df.d.to_numpy(dtype="U10"))
    df = df[ok].copy(); df["si"] = si[ok]
    tk = np.array(sorted(df.t.unique()))
    ti = np.searchsorted(tk, df.t.to_numpy())
    M = np.full((len(tk), S), np.nan)
    c = df.c.to_numpy()
    M[ti, df.si.to_numpy()] = np.where(c > 0, c, np.nan)
    return tk, M


tkA, MA = mat(dA); tkB, MB = mat(dB)
kA = np.isfinite(MA).sum(1) >= MIN_SHARED; kB = np.isfinite(MB).sum(1) >= MIN_SHARED
tkA, MA, tkB, MB = tkA[kA], MA[kA], tkB[kB], MB[kB]
PA, PB = np.isfinite(MA), np.isfinite(MB)
with np.errstate(invalid="ignore", divide="ignore"):
    RA = MA[:, 1:] / MA[:, :-1] - 1.0
    RB = MB[:, 1:] / MB[:, :-1] - 1.0
VA, VB = np.isfinite(RA), np.isfinite(RB)
RA0, RB0 = np.nan_to_num(RA), np.nan_to_num(RB)
QA, QB = np.round(RA0, 4), np.round(RB0, 4)
PBf = PB.astype(np.float32)
rows = []
CH = 16
for a0 in range(0, len(tkA), CH):
    sl = slice(a0, a0 + CH)
    shared = PA[sl].astype(np.float32) @ PBf.T
    mask = VA[sl][:, None, :] & VB[None, :, :]
    npair = mask.sum(2)
    nag = ((np.abs(RA0[sl][:, None, :] - RB0[None, :, :]) <= TOL) & mask).sum(2)
    full = (shared >= MIN_SHARED) & (npair > 0) & (nag >= MIN_AGREE * npair - 1e-12)
    for i, j in zip(*np.nonzero(full)):
        first = np.flatnonzero(mask[i, j])[:NFIRST]
        cand = bool(len(first) == NFIRST and (QA[a0 + i, first] == QB[j, first]).all())
        rows.append((tkA[a0 + i], tkB[j], int(shared[i, j]), int(npair[i, j]), int(nag[i, j]), cand))
P = pd.DataFrame(rows, columns=["a", "b", "shared", "pairs", "agree", "first10"])
P.to_csv(C.OUTD / "identity_pairs_r4.tsv", sep="\t", index=False)
same = P[P.a == P.b]
print("full-test pairs", len(P), "same-symbol", len(same), "cross-symbol", int((P.a != P.b).sum()),
      "cross-symbol passing first-10", int(((P.a != P.b) & P.first10).sum()))
# map edges (A2): same-symbol full pass (one identity); cross-symbol needs first10
E = P[(P.a == P.b) | P.first10]
json.dump({"edges": len(E), "same": int((E.a == E.b).sum()), "rename": int((E.a != E.b).sum())}, open(C.OUTD / "identity_r4.json", "w"))
print("map edges", len(E))
