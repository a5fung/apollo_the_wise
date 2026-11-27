import numpy as np, pandas as pd, time
import r4_common as C
import r4_stats as S
D = pd.read_parquet(C.OUTD / "r4_disc_frame_fix.parquet")
n = len(D); y = D.win.to_numpy().astype(float)
sc = pd.factorize(D.era + "|" + D.month)[0]
targets = {"f20": 0.2498, "f24a": 0.3613, "f16": 0.3926, "f18": 0.0453, "f15": 0.1436, "f10": 0.0041}
ratio_obs = {}
cols = {f: D[f].to_numpy() for f in ["f20", "f16", "f18", "f15", "f10"]}
f24 = D.f24.to_numpy(); ab = D.f24_above.to_numpy() == 1
cols["f24a"] = np.where(ab, f24, np.nan)
def thirds_count_perm(U, v, alt):
    a = S.thirds_assign(v, sc); S_ = U.shape[0]
    wt = np.zeros(S_); wb = np.zeros(S_); nt = nb = 0
    for s in np.unique(sc[a >= 0]):
        idx = np.flatnonzero((sc == s) & (a >= 0)); perm = np.argsort(U[:, idx], axis=1)
        L = y[idx]; aa = a[idx]; top, bot = aa == 2, aa == 0
        if alt == 0:
            wt += (top[perm] * L[None, :]).sum(1); wb += (bot[perm] * L[None, :]).sum(1)
        else:
            wt += (L[perm] * top[None, :]).sum(1); wb += (L[perm] * bot[None, :]).sum(1)
        nt += int(top.sum()); nb += int(bot.sum())
    lr = np.log((wt / nt) / (wb / nb))
    wt0 = sum(y[(sc == s) & (a == 2)].sum() for s in np.unique(sc[a >= 0])); wb0 = sum(y[(sc == s) & (a == 0)].sum() for s in np.unique(sc[a >= 0]))
    lo = np.log((wt0 / nt) / (wb0 / nb))
    return (1 + int((np.abs(lr) >= abs(lo) - 1e-12).sum())) / (S_ + 1)
rng = np.random.default_rng(1124)
U1 = rng.random((10000, n))
U2 = np.random.default_rng(1124).random((n, 10000)).T
for name, U in (("row-major (s,e)", U1), ("col-major (e,s)", U2)):
    for alt in (0, 1):
        res = {f: thirds_count_perm(U, cols[f], alt) for f in cols}
        print(name, "deal", alt, {f: round(p, 4) for f, p in res.items()}, flush=True)
print("target", targets)
