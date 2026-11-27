"""Stage 6 DRAFT step d: discovery numbers of gallery read #1, labelled SEEN (prereg 5.7: he saw the discovery winners; the read skips the 5.2 gates).
Opens ONE outcome file: stage3/discovery_outcomes.tsv.gz (sha asserted; max E <= 2020-12-31 asserted; zero CHECK rows in the join asserted).
The thresholds in gr1.py were fixed BEFORE this script first ran and were not touched after it."""
from common6 import *
P = Out("6d_seen_discovery.txt")
P("# STAGE 6 DRAFT (not a freeze) - d. DISCOVERY numbers of gallery read #1 - 'SEEN' (description; never a bar)"); P(assert_all())
OP = ROOT / "stage3/discovery_outcomes.tsv.gz"
assert hashlib.sha256(OP.read_bytes()).hexdigest() == "89f590d6e64d13ac992dcd695111086ef3aea024077b617319f662b05e2cb201"
O = pd.read_csv(OP, sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str})
assert O.E.max() <= "2020-12-31" and (O.era == "A").all(), "an outcome row after 2020-12-31 - STOP"
F = components()
X = O[["era", "ci", "ticker", "E", "big", "monster", "failed", "clean", "adr_tail"]].merge(F, on=["era", "ci", "ticker", "E"], how="left", validate="1:1")
assert X.gr1.notna().all() and (X.set == "DISC").all() and X.E.max() <= "2020-12-31", "a CHECK row in the join - STOP"
P(f"outcomes: discovery_outcomes.tsv.gz sha 89f590d6 asserted; {len(O)} discovery rows, max E {O.E.max()} (ASSERT <= 2020-12-31); CHECK rows joined: 0 (asserted)")
P("direction HE states: V into the breakout -> FEWER big winners. Ratio printed = rate of NOT-V / rate of V (over 1.0 = his direction).")
NS = 10000

def mh_notv_over_v(y, g, um):
    t = L.assign_two(g.astype(np.int8), [um])
    us = np.unique(um[t >= 0])
    a = np.array([y[(um == u) & (t == 2)].sum() for u in us], float); n1 = np.array([((um == u) & (t == 2)).sum() for u in us], float)
    c = np.array([y[(um == u) & (t == 0)].sum() for u in us], float); n0 = np.array([((um == u) & (t == 0)).sum() for u in us], float)
    N = n1 + n0
    num, den = (c * n1 / N).sum(), (a * n0 / N).sum()            # not-V / V
    return (num / den if num > 0 and den > 0 else float("nan")), t, (int(a.sum()), int(n1.sum()), int(c.sum()), int(n0.sum()), len(us))

def perm_p(y, t, um, obs, seed=L.SEED):
    rng = np.random.default_rng(seed); NUM = np.zeros(NS); DEN = np.zeros(NS)
    for u in np.unique(um[t >= 0]):
        idx = np.flatnonzero((t >= 0) & (um == u)); yy = y[idx]; isv = t[idx] == 2
        n1, n0 = int(isv.sum()), int((~isv).sum()); w = int(yy.sum())
        if w == 0: continue
        a = rng.hypergeometric(n1, n0, w, NS)                    # winners landing in V under a within-month shuffle
        NUM += (w - a) * n1 / (n1 + n0); DEN += a * n0 / (n1 + n0)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(NUM / DEN)
    lo = np.log(obs)
    one = (1 + np.sum(lr >= lo - 1e-12)) / (NS + 1)                   # one-sided, his direction
    two = (1 + np.sum(np.abs(lr - np.nanmedian(lr)) >= abs(lo - np.nanmedian(lr)) - 1e-12)) / (NS + 1)
    return one, two

def boot(y, t, um, seed=L.SEED):
    us = np.unique(um[t >= 0])
    comp = np.array([[y[(um == u) & (t == 2)].sum(), ((um == u) & (t == 2)).sum(), y[(um == u) & (t == 0)].sum(), ((um == u) & (t == 0)).sum()] for u in us], float)
    d = np.random.default_rng(seed).integers(0, len(us), size=(2000, len(us)))
    s = comp[d]; N = s[:, :, 1] + s[:, :, 3]
    r = (s[:, :, 2] * s[:, :, 1] / N).sum(1) / (s[:, :, 0] * s[:, :, 3] / N).sum(1)
    r = r[np.isfinite(r)]
    return float(np.percentile(r, 5)), float(np.percentile(r, 95))

def line(nm, d, ycol="big", full=False):
    y = d[ycol].to_numpy(int); g = d.gr1.to_numpy(float); um = d.month.to_numpy()
    r, t, (a, n1, c, n0, nb) = mh_notv_over_v(y, g, um)
    s = f"   {nm:44} V {a:4d}/{n1:4d} = {100 * a / max(n1, 1):5.2f}% | not-V {c:4d}/{n0:4d} = {100 * c / max(n0, 1):5.2f}% | ratio not-V / V {r:5.3f}"
    if full:
        one, two = perm_p(y, t, um, r); lo, hi = boot(y, t, um)
        s += f" (90% {lo:.2f}-{hi:.2f}) | permutation p one-sided (his direction) {one:.4f}, two-sided {two:.4f} | months used {nb}"
    P(s)

K = X[X.kept == True].reset_index(drop=True); assert len(K) == 5330
P(f"\n== SEED 1124 discovery, {len(K)} events, {int(K.big.sum())} big winners (Mantel-Haenszel by month; months holding >= 2 of each group) ==")
line("ALL 2017-2020  [SEEN]", K, full=True)
line("without 2020 (2017-19)  [SEEN]", K[K.Ey < 2020] if K.Ey.dtype != object else K[K.Ey < "2020"], full=True)
for y_ in sorted(K.Ey.unique()):
    line(f"year {y_}", K[K.Ey == y_])
line("embargoed (E <= 2020-10-06)", K[K.E <= "2020-10-06"])
line("monster tier (>= 2.0x)", K, "monster")
line("clean winners", K, "clean")
line("ADR-scaled tail", K, "adr_tail")
P("   the other side of his sentence ('prone to failure'): FAILED = peak under 1.10x (here the ratio is still not-V / V, so UNDER 1.0 = V fails more)")
line("failed (peak < 1.10x)", K, "failed")
T_ = L.load()[["era", "ci", "ticker", "f01"]]
Kf = K.merge(T_, on=["era", "ci", "ticker"], how="left", validate="1:1")
th = L.assign_thirds(Kf.f01.to_numpy(float), [Kf.era.values, Kf.month.values], 6)
Kf = Kf[th >= 0].copy(); Kf["month"] = Kf.month.astype(str) + "/" + th[th >= 0].astype(str)
P("   the flag leans to LOW daily-range names (6b: 12.4% / 10.7% / 7.7% flagged by f01 third) and f01's high third wins 3.2x - so part of the ratio is f01's echo:")
line("ALL, stratified by month x daily-range third", Kf, full=True)
K2 = X[X.kept2411 == True].reset_index(drop=True)
P(f"\n== SECOND SEED (2411) discovery, {len(K2)} events ==")
line("ALL 2017-2020  [SEEN]", K2, full=True)
P("\n'SEEN': he named the read after looking at discovery winners and failures, and the definition's author saw 48 of those charts with their sheet. These numbers are description; the test is the check years, once.")
P.save()
