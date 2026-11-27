#!/usr/bin/env python3
"""STAGE 7b - CHECK, ONE RUN (prereg 5.3 / 5.5; amendments A1, A2, A3; stage-6 freeze: m = 6, gr1 = gallery read #1).

READS: the outcome-free stage-1f feature table (CHECK rows, seed 1124 only), stage 6's gr1 components (pinned sha), stage 3's PRINTED
result (carried list, directions, 2017-19 rate, discovery tags), stage 6e's printed power line for gr1, and - REAL MODE ONLY - the check
outcome file stage7/check_outcomes.tsv.gz written once by s7_outcomes.py. No bar is read here. Nothing dated after 2024-12-31 (asserted).

Modes: `python3 s7_check.py --synthetic` = the same path on planted coin-toss labels (the real outcome file is NOT opened; the synthetic
labels are written to stage7/_synthetic_outcomes.tsv.gz and read back through the SAME loader).  `python3 s7_check.py` = THE REAL RUN;
it refuses to run unless 7_check_SYNTHETIC.txt carries this script's own sha256 (same code for both runs) and refuses to overwrite.

THE FAMILY (frozen at stage 6, m = 6; Holm step-down, one-sided in the frozen direction):
  f01 HIGH | f09 HIGH | f04 HIGH | f02 LOW | combination (5.6: f01, f02 as 1 - rank, f04, f09; HIGH) | gr1 (not-V rate / V rate).

READINGS FIXED HERE, BEFORE THE REAL RUN (returned under "readings")
 K1  Population = feature-table rows set == CHECK and kept (seed 1124): 6,266 (era A 2,910 / era B 3,356). Seed 2411 and the +-50%
     windows are discovery-only in 5.5 - not read here. Strata = (era, calendar month); 2022-04 is in both eras and is two strata.
 K2  Thirds members: thirds inside (era, month) holding >= 6 scored events (s2lib.assign_thirds = the calibrated code). Ratio = pooled
     top / bottom rate (smoothed (w + .5)/(n + 1) for BOTH only when a third holds none). The CHECK RATIO is stated in the frozen
     direction: top/bottom for HIGH, bottom/top (= 1 / top/bottom, interval bounds inverted) for f02 LOW.
 K3  Combination: rebuilt on the CHECK rows - within-(era, month) percentile rank (average rank - 0.5) / n over events scored on all
     four, f02 as 1 - rank, equal-weight mean; thirds of that inside (era, month); HIGH wins. The discovery column is not carried over.
 K4  gr1: two groups inside (era, month) holding >= 2 V and >= 2 not-V (s2lib.assign_two); Mantel-Haenszel by (era, month); ratio =
     not-V / V (over 1.0 = his direction: V has FEWER big winners). Outcome-free asserts: 577 V, 0 NULL, 42 usable months, V 575 /
     not-V 5,105 (stage 6e).
 K5  Permutation: U = default_rng(1124).random((10000, 6266), float32) in table order, the SAME U for every member (stage 3's R3: an
     exact within-(era, month) shuffle among the events assigned on that member). One-sided p in the frozen direction =
     (1 + #(perm >= observed, frozen-direction log ratio)) / 10001; the opposite one-sided p = (1 + #(perm <= observed)) / 10001.
 K6  Holm (step-down) over the 6 one-sided p's -> adjusted p; PICKS family. The REVERSED family = Holm over the 6 OPPOSITE one-sided
     p's (its own family of the same m = 6).
 K7  90% interval: (era, month) blocks resampled with replacement, 2,000 draws, a fresh default_rng(1124) per member (stage 3's R4);
     gr1 by its MH form (stage 6d's boot, keyed on (era, month)).
 K8  'Same direction in every era present' = the frozen-direction ratio computed on that era's strata alone is > 1.0 in era A AND in
     era B. An era whose ratio is NaN (MH with an empty side) counts as NOT the same direction (conservative).
 K9  Verdict words (5.3 table): ratio >= 1.2 & Holm p <= 0.05 & K8 -> PICKS THE TAIL ('(check years partly seen)' on f04 - on the
     seen list); same without K8 -> PICKS THE TAIL (one era only); ratio >= 1.2 otherwise -> DIRECTIONAL, NOT PROVEN; ratio <= 0.83
     (read as 1 / 1.2, as stage 3 read '<= 0.80' as 1 / 1.25; a ratio in (0.83, 0.8333] is flagged) & REVERSED-family Holm p <= 0.05
     -> REVERSED; else NOT CONFIRMED. Bars judged on log ratio +-1e-12.
 K10 Smallest true ratio with an 80% chance of the PICKS line (any era form), computed in the outcome-free section BEFORE the outcome
     file is opened (prints identically in both modes): stage 6e's model (months as blocks, month rate Beta around the era rate, CV 0.6;
     base rate = stage 3's 2017-19 rate 9.18%; era B at 1.0x and 0.75x; first Holm step 0.05 / 6; 20,000 draws, rng 1124) on each
     thirds member's REAL check layout (rates b, b sqrt(k), b k for bottom / middle / top, the month's pooled rate unchanged). gr1's
     figure is quoted from 6e_m_and_power.txt (asserted present). The all-null sentence's P = the median of the thirds members'
     power at a true 1.5x (era B at the same rate).
 K11 Tags: 'gate-truncated' f01, f04 (prereg 4.1); 'seen on the check years (A+ read 10-22)' f04; 'against Qullamaggie's buys' and
     'break-day selection' carried from stage 3's result for the four features (f02: QM share 19.9% -> tag; no B4 tag fired);
     'era-B price partly derived' on every line (A1; stage 1e: fires); 'era-B population thinned by volume underflow' NOT fired
     (stage 1e: rung 3 reading, <= 1%; the rungs disagree - stated once).
 K12 Beside each verdict: monster / clean / ADR-scaled ratios (same layout), B4 = the member's ratio inside (era, quarter, B4 third)
     strata (thirds re-formed inside strata >= 9, stage 3's R8; gr1: MH with those strata as blocks).
 K13 5.5 readings on CHECK (description, no bar): per year; per era; first breaks (after 10 quiet sessions) vs later; first break after
     60 quiet sessions; common stock only; price >= $5; full 60-session windows only; QQQ above / below its 50-day at D; gapped over the
     level at the open vs not (f24grp a / b) - thirds RE-FORMED inside each population (stage 3's R9), gr1 by MH inside it; outcome:
     monster, clean, ADR-scaled, un-truncated, from max(level, high of E), E+1..E+60, ADR-neutral (thirds inside (era, quarter, ADR20
     third) strata >= 9; gr1: MH by (era, month, f01 third within (era, month)) = stage 6d's form); conditioning: within each B4 third
     and each B1 third (thirds inside (era, quarter, B-third) strata). gr1 also: FAILED (peak < 1.10x) as stage 6d printed it.
     Discovery-only 5.5 lines (embargo, 2019-20, second seed, window +-50%) are not printed on check.
 K14 B1-B3: ONE table (top/bottom ratio, two-sided p description, 90% interval, per era, within B4 strata, gapped / not). B4 own line.
"""
import hashlib, json, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[3]
SYN = "--synthetic" in sys.argv
CUT = "2024-12-31"
DOCS = {"docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md": "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a",
        "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md": "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10",
        "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md": "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b",
        "docs/analysis/breakout_winner_study_prereg_amendment_A3_2026-11-26.md": "a0c11a3685bc83369a9fba29766368e82734432ea9a3a464fd363787e6d34268",
        "docs/analysis/breakout_winner_study_stage6_freeze_2026-11-26.md": "28e40825e0729aaab48e96bcb677db697cb9527f895257b6c425368eb4e4bd18"}
PINS6 = {"gr1.py": "ff342a19c08ad7d707c32aff4e956e9087cb14271987d3e21e68082303c035a2", "common6.py": "c290946c49eeb8cba771d36ca2f8abc1c247471966434afcc1eff0b5b874b619",
         "gr1_components.tsv.gz": "9c4d25188c9e938ae1e453e58f0e5746b9612515e3dd9819fdc2b686d881a851", "s6a_build.py": "7a290dfe4a2c06b4ede71514bd462ac6fa814ef5bb39d212b17879dedd12ac9f"}
DISC_OUT_SHA = "89f590d6e64d13ac992dcd695111086ef3aea024077b617319f662b05e2cb201"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


for p, h in DOCS.items():
    assert sha(REPO / p) == h, f"{p} sha256 differs - STOP"
for p, h in PINS6.items():
    assert sha(ROOT / "stage6_draft" / p) == h, f"stage-6 pinned {p} sha256 differs - STOP"
sys.path.insert(0, str(ROOT / "stage2")); sys.path.insert(0, str(ROOT / "stage6_draft"))
import s2lib as L                                   # noqa: E402
import common6 as C6                                # noqa: E402  (imports gr1; reads gr1_components only through components())
L.assert_docs()
MYSHA = sha(__file__)
OUTC = HERE / "check_outcomes.tsv.gz"
SYNF = HERE / "_synthetic_outcomes.tsv.gz"
TXT = HERE / ("7_check_SYNTHETIC.txt" if SYN else "7_check.txt")
RES = HERE / "7_result.json"


def W(path):
    """every write lands under stage7/ (a star-import rebinding sent a stage-6 file astray once)."""
    path = Path(path).resolve()
    assert path.parent == HERE, f"write outside stage7: {path}"
    return path


if not SYN:
    assert not TXT.exists() and not RES.exists(), "the real check run is ONE run - 7_check.txt exists; read it"
    syn_txt = (HERE / "7_check_SYNTHETIC.txt").read_text()
    assert f"this script sha256 {MYSHA}" in syn_txt, "the synthetic dry run was not made at this script's sha - STOP"
NS, NBOOT, M = 10_000, 2_000, 6
TAIL, REV = 1.2, 1 / 1.2
LOG = []


def P(s=""):
    print(s, flush=True); LOG.append(s)


t0 = time.time()
P("# STAGE 7 - CHECK, ONE RUN" + ("   [SYNTHETIC MODE: planted labels, the check outcome file is NOT opened - NOT a result]" if SYN else ""))
P("prereg 3eb2b9b0 / A1 4a7beda1 / A2 0a6cc417 / A3 a0c11a36 / stage-6 freeze 28e40825 / feature table d629ef0a asserted; stage-6 pins gr1.py ff342a19, common6.py c290946c, gr1_components 9c4d2518, s6a_build.py 7a290dfe asserted")
P(f"this script sha256 {MYSHA}")
P(f"s2lib sha256 {sha(L.__file__)[:16]} | gr1 thresholds: trough_age <= {C6.gr1.T_MAX_AGE}, drop_adr >= {C6.gr1.DROP_ADR_MIN}, recover >= {C6.gr1.RECOVER_MIN}, at_level <= {C6.gr1.AT_LEVEL_MAX}")
assert (C6.gr1.T_MAX_AGE, C6.gr1.DROP_ADR_MIN, C6.gr1.RECOVER_MIN, C6.gr1.AT_LEVEL_MAX) == (59, 5.0, 0.5, 9)

# ════════════════════════════════════════ population (outcome-free) ════════════════════════════════════════
T = L.load()
C = T[(T.set == "CHECK") & (T.kept == True)].reset_index(drop=True)          # noqa: E712
del T
assert len(C) == 6266 and (C.era == "A").sum() == 2910 and (C.era == "B").sum() == 3356
assert C.E.min() >= "2021-01-01" and C.E.max() <= CUT and C.D.max() <= CUT
F6 = C6.components()
F6 = F6[(F6.set == "CHECK") & (F6.kept == True)][["era", "ci", "ticker", "E", "gr1", "gr1_null"]]   # noqa: E712
C = C.merge(F6, on=["era", "ci", "ticker", "E"], how="left", validate="1:1")
assert C.gr1.notna().all() and int((C.gr1 == 1).sum()) == 577 and (C.gr1_null == "").all()
N = len(C)
res3 = json.loads((ROOT / "stage3/3_result.json").read_text())
CARRIED = {c["f"]: c for c in res3["carried"]}
assert sorted(CARRIED) == ["f01", "f02", "f04", "f09"]
DIR = {f: (1 if CARRIED[f]["direction"] == "HIGH third wins" else -1) for f in CARRIED}
assert DIR == {"f01": 1, "f02": -1, "f04": 1, "f09": 1}
P0 = float(res3["rate_1719"]); assert abs(P0 - 0.09176) < 0.00005
e6 = (ROOT / "stage6_draft/6e_m_and_power.txt").read_text()
G6 = re.findall(r"-> smallest true ratio found 4 times in 5: ([\d.]+x)", e6)
assert len(G6) == 2 and "m = 4 carried + 1 combination + 1 read = 6" in e6
ERA, MON, QTR = C.era.to_numpy(), C.month.to_numpy(), C.quarter.to_numpy()
UM = pd.factorize(C.era + "|" + C.month)[0]
EY = C.Ey.to_numpy()

# combination (K3) - rebuilt on check rows
mask4 = np.ones(N, bool)
for f in ("f01", "f02", "f04", "f09"):
    mask4 &= C[f].notna().to_numpy()
acc = np.zeros(N)
sub = C[mask4]
for f in ("f01", "f02", "f04", "f09"):
    pr = np.full(N, np.nan)
    g = sub.groupby(["era", "month"], sort=False)[f]
    pr[np.flatnonzero(mask4)] = ((g.rank(method="average") - 0.5) / g.transform("size")).to_numpy()
    acc += pr if DIR[f] > 0 else 1.0 - pr
C["combo"] = np.where(mask4, acc / 4, np.nan)
for col, nm in (("B4", "b4t"), ("B1", "b1t"), ("f01", "adrt")):
    C[nm] = L.assign_thirds(C[col].to_numpy(float), [ERA, QTR], 1)
    assert (C[nm] >= 0).all()
C["adrm"] = L.assign_thirds(C.f01.to_numpy(float), [ERA, MON], L.MIN_MONTH)       # stage 6d's f01 third within (era, month)
gapA, gapB = (C.f24grp == "a").to_numpy(), (C.f24grp == "b").to_numpy()

MEMBERS = ["f01", "f09", "f04", "f02", "combo", "gr1"]
MDIR = {"f01": 1, "f09": 1, "f04": 1, "f02": -1, "combo": 1, "gr1": 1}
NAMES = {"f01": "Daily range (ADR20)", "f09": "6-month move", "f04": "Strength rank, best", "f02": "Price (raw close)",
         "combo": "Combination of f01, f02, f04, f09 (5.6)", "gr1": "Gallery read #1: V into the breakout",
         "B1": "Pick-model score", "B2": "Live order score", "B3": "Group strength", "B4": "Distance close(D) -> level (daily ranges)"}
DIRW = {"f01": "HIGH third wins", "f09": "HIGH third wins", "f04": "HIGH third wins", "f02": "LOW third wins", "combo": "HIGH third wins",
        "gr1": "V has FEWER big winners (ratio = not-V / V)"}


def thirds(col, mask=None, strata=None):
    x = C[col].to_numpy(float).copy()
    if mask is not None:
        x[~mask] = np.nan
    if strata is None:
        return L.assign_thirds(x, [ERA, MON], L.MIN_MONTH)
    return L.assign_thirds(x, [ERA, QTR, C[strata].to_numpy()], L.MIN_STRATUM)


def two(mask=None, keys=None):
    g = C.gr1.to_numpy(float).astype(np.int8)
    if mask is not None:
        g = np.where(mask, g, -1).astype(np.int8)
    return L.assign_two(g, keys if keys is not None else [ERA, MON])


LAY = {f: thirds(f) for f in ("f01", "f09", "f04", "f02", "combo", "B1", "B2", "B3", "B4")}
LAY["gr1"] = two()
LB4 = {f: thirds(f, strata="b4t") for f in ("f01", "f09", "f04", "f02", "combo", "B1", "B2", "B3")}
LADR = {f: thirds(f, strata="adrt") for f in ("f01", "f09", "f04", "f02", "combo")}
LB1 = {f: thirds(f, strata="b1t") for f in ("f01", "f09", "f04", "f02", "combo")}
KB4 = pd.factorize(C.era + "|" + C.quarter + "|" + C.b4t.astype(str))[0]
KADR = pd.factorize(C.era + "|" + C.month + "|" + C.adrm.astype(str))[0]
TG = LAY["gr1"]
usable = np.unique(UM[TG >= 0])
assert len(usable) == 42 and int((TG == 2).sum()) == 575 and int((TG == 0).sum()) == 5105, (len(usable), int((TG == 2).sum()), int((TG == 0).sum()))

P(f"\npopulation: CHECK seed-1124 events {N} (era A {int((ERA == 'A').sum())} 2021-01-04..2022-04-01 / era B {int((ERA == 'B').sum())} 2022-04-05..2024-10-04); E {C.E.min()}..{C.E.max()} (ASSERT <= {CUT})")
P("   per year of E: " + " | ".join(f"{y} {int((EY == y).sum())}" for y in sorted(set(EY))) + f" | (era, month) strata {len(np.unique(UM))}")
P("   thirds layout (bottom / middle / top assigned): " + " | ".join(f"{f} {int((LAY[f] == 0).sum())}/{int((LAY[f] == 1).sum())}/{int((LAY[f] == 2).sum())}" for f in ("f01", "f09", "f04", "f02", "combo")))
P(f"   combination scored on all four: {int(mask4.sum())} (f02 NULL {int(C.f02.isna().sum())})")
P(f"   gr1: V {int((C.gr1 == 1).sum())} of {N} ({100 * (C.gr1 == 1).mean():.1f}%), NULL 0; usable (era, month) strata {len(usable)}; V {int((TG == 2).sum())} / not-V {int((TG == 0).sum())} in them (= stage 6e)")


# ════════════════════════════════════════ statistics helpers ════════════════════════════════════════
def counts(y, t, mask=None):
    top, bot, mid = t == 2, t == 0, t == 1
    if mask is not None:
        top, bot, mid = top & mask, bot & mask, mid & mask
    return dict(wt=int(y[top].sum()), nt=int(top.sum()), wb=int(y[bot].sum()), nb=int(bot.sum()), wm=int(y[mid].sum()), nm=int(mid.sum()))


def ratio(c):
    if c["nt"] == 0 or c["nb"] == 0:
        return float("nan")
    return float(L.ratio_counts(np.array([c["wt"]]), c["nt"], np.array([c["wb"]]), c["nb"])[0])


def mh_nv(y, t, blocks, mask=None):
    """Mantel-Haenszel not-V / V over blocks (t: 2 = V, 0 = not-V, -1 unassigned); NaN when a side is empty."""
    ok = t >= 0 if mask is None else (t >= 0) & mask
    num = den = 0.0; a_ = n1_ = c_ = n0_ = 0
    for u in np.unique(blocks[ok]):
        s = ok & (blocks == u)
        v, nv = s & (t == 2), s & (t == 0)
        n1, n0 = int(v.sum()), int(nv.sum())
        if n1 == 0 or n0 == 0:
            continue
        a, c = float(y[v].sum()), float(y[nv].sum())
        num += c * n1 / (n1 + n0); den += a * n0 / (n1 + n0)
        a_ += int(a); n1_ += n1; c_ += int(c); n0_ += n0
    r = num / den if num > 0 and den > 0 else float("nan")
    return r, dict(wv=a_, nv=n1_, wn=c_, nn=n0_)


def judged(f, y, t=None, mask=None):
    """frozen-direction ratio of member f on labels y (layout t, default its main layout)."""
    if f == "gr1":
        return mh_nv(y, TG if t is None else t, UM, mask)[0]
    r = ratio(counts(y, LAY[f] if t is None else t, mask))
    return r if MDIR[f] > 0 else (1.0 / r if np.isfinite(r) and r > 0 else float("nan"))


UKEY = np.random.default_rng(L.SEED).random((NS, N), dtype=np.float32)


def perm_lr(y, t, two_=False):
    """stage 3's R3 on the check frame: 10,000 within-(era, month) permuted log ratios (top/bottom, or MH V/not-V when two_)."""
    asg = t >= 0
    WT = np.zeros(NS); WB = np.zeros(NS); NUM = np.zeros(NS); DEN = np.zeros(NS)
    for u in np.unique(UM[asg]):
        idx = np.flatnonzero(asg & (UM == u))
        wpos = np.flatnonzero(y[idx] == 1)
        if len(wpos) == 0:
            continue
        A = np.argsort(UKEY[:, idx], axis=1, kind="stable")[:, wpos]
        tt = t[idx][A]
        a = (tt == 2).sum(1); c = (tt == 0).sum(1)
        if two_:
            n1 = int((t[idx] == 2).sum()); n0 = int((t[idx] == 0).sum())
            NUM += a * n0 / (n1 + n0); DEN += c * n1 / (n1 + n0)
        else:
            WT += a; WB += c
    if two_:
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(NUM / DEN)
    return np.log(L.ratio_counts(WT, int((t == 2).sum()), WB, int((t == 0).sum())))


def boot(f, y, seed=L.SEED):
    t = LAY[f]
    asg = t >= 0
    us = np.unique(UM[asg])
    comp = np.array([[y[(UM == u) & (t == 2)].sum(), ((UM == u) & (t == 2)).sum(), y[(UM == u) & (t == 0)].sum(), ((UM == u) & (t == 0)).sum()] for u in us], float)
    draw = np.random.default_rng(seed).integers(0, len(us), size=(NBOOT, len(us)))
    s = comp[draw]
    if f == "gr1":                                                       # MH not-V / V
        Nn = s[:, :, 1] + s[:, :, 3]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = (s[:, :, 2] * s[:, :, 1] / Nn).sum(1) / (s[:, :, 0] * s[:, :, 3] / Nn).sum(1)
        r = r[np.isfinite(r) & (r > 0)]
        return float(np.percentile(r, 5)), float(np.percentile(r, 95))
    s = s.sum(1)
    ok = (s[:, 1] > 0) & (s[:, 3] > 0)
    rr = L.ratio_counts(s[ok, 0], s[ok, 1], s[ok, 2], s[ok, 3])
    lo, hi = float(np.percentile(rr, 5)), float(np.percentile(rr, 95))
    return (lo, hi) if MDIR[f] > 0 else (1.0 / hi, 1.0 / lo)


def holm(ps):
    o = np.argsort(ps, kind="stable"); adj = np.empty(len(ps)); run = 0.0
    for k, i in enumerate(o):
        run = max(run, min(1.0, (len(ps) - k) * ps[i])); adj[i] = run
    return adj


def fr_(x):
    return "nan" if x is None or not np.isfinite(x) else f"{x:.3f}"


# ════════════════════════════════════════ K10: smallest detectable ratio (OUTCOME-FREE, before any outcome) ════════════════════════════════════════
P("\n" + "=" * 110)
P(f"## SMALLEST DETECTABLE RATIO on the real check layout (outcome-free; synthetic labels; base rate {100 * P0:.2f}% = stage 3's 2017-19 rate; first Holm step 0.05/{M}; 20,000 draws)")
KS = (1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5, 3.0)
NSIM, CV = 20000, 0.6
srng = np.random.default_rng(1124)
SDR, POW15 = {}, {}


def sim_member(f, k, mult_b):
    t = LAY[f]
    WT = np.zeros(NSIM); WB = np.zeros(NSIM); NT = NB = 0
    for u in np.unique(UM[t >= 0]):
        s = UM == u
        nb_, nm_, nt_ = int((s & (t == 0)).sum()), int((s & (t == 1)).sum()), int((s & (t == 2)).sum())
        p = P0 * (mult_b if ERA[s][0] == "B" else 1.0)
        a_ = max((1 - p) / CV ** 2 - p, 0.05); pm = srng.beta(a_, a_ * (1 - p) / p, NSIM)
        b = pm * (nb_ + nm_ + nt_) / (nb_ + np.sqrt(k) * nm_ + k * nt_)
        WT += srng.binomial(nt_, np.minimum(b * k, 1)); WB += srng.binomial(nb_, np.minimum(b, 1)); NT += nt_; NB += nb_
    return L.ratio_counts(WT, NT, WB, NB)


for f in ("f01", "f09", "f04", "f02", "combo"):
    out = []
    for nm, mb in (("era B at the same rate", 1.0), ("era B at 0.75x", 0.75)):
        r0 = sim_member(f, 1.0, mb); crit = float(np.quantile(r0, 1 - 0.05 / M))
        need = None; pw = {}
        for k in KS:
            pw[k] = float(np.mean(sim_member(f, k, mb) >= max(crit, TAIL)))
            if need is None and pw[k] >= 0.80:
                need = k
        if mb == 1.0:
            POW15[f] = pw[1.5]
        SDR[(f, mb)] = need
        out.append(f"{nm}: no-effect median {np.median(r0):.3f}, ratio needed for p <= 0.05/{M} {crit:.2f}, power at 1.5x {100 * pw[1.5]:.0f}%, smallest found 4 in 5 "
                   + (f"{need:.1f}x" if need else "over 3.0x"))
    P(f"   {f:5} " + " | ".join(out))
SDR[("gr1", 1.0)], SDR[("gr1", 0.75)] = G6
P(f"   gr1   quoted from stage 6e (MH model, same base rate, m = 6): era B at the same rate {G6[0]} | era B at 0.75x {G6[1]}")
P("   read with care: a lower bound for a family member (first Holm step); day / theme clustering is not simulated and pushes the real figure down.")


def sdr_txt(f):
    a, b = SDR[(f, 1.0)], SDR[(f, 0.75)]
    s = lambda v: v if isinstance(v, str) else (f"{v:.1f}x" if v else "over 3.0x")   # noqa: E731
    return f"smallest true ratio it had an 80% chance to detect: {s(a)} (era B at 0.75x: {s(b)})"


# ════════════════════════════════════════ outcomes ════════════════════════════════════════
COLS = ["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month", "maxc", "big", "monster", "failed", "adr_tail", "clean", "first_hit",
        "big_untrunc", "maxc_untrunc", "big_fromhigh", "big_e1", "nbars", "nbars_untrunc", "truncated", "ends_inside", "full_window", "proxy", "qqq_above50"]
YCOLS = ["big", "monster", "failed", "adr_tail", "clean", "big_untrunc", "big_fromhigh", "big_e1"]


def load_outcomes(path):
    O = pd.read_csv(path, sep="\t", keep_default_na=False, na_values=["nan"], dtype={"ticker": str, "truncated": str})
    assert list(O.columns) == COLS, list(O.columns)
    assert len(O) == N and O.E.min() >= "2021-01-01" and O.E.max() <= CUT and (O.kept == True).all()    # noqa: E712
    X = C[["era", "ci", "ticker", "E"]].merge(O, on=["era", "ci", "ticker", "E"], how="left", validate="1:1")
    assert X.big.notna().all() and len(X) == N
    for c in YCOLS + ["full_window", "qqq_above50", "ends_inside", "nbars"]:
        assert set(np.unique(X[c])) <= ({0, 1} if c != "nbars" else set(range(0, 62))), c
    return X


if SYN:
    P("\n## SYNTHETIC LABELS (the check outcome file is NOT opened). Base 9%; planted: f01 HIGH 2.0x | f09 HIGH 2.5x era A, 0.8x era B | f04 HIGH 1.25x |"
      " f02 HIGH 2.0x (against its frozen LOW -> REVERSED expected) | gr1 V at 0.5x (not-V / V = 2.0) | B1 none.")
    rng = np.random.default_rng(7)
    rate = np.full(N, 0.09)
    for f, k, msk in (("f01", 2.0, None), ("f09", 2.5, ERA == "A"), ("f09", 0.8, ERA == "B"), ("f04", 1.25, None), ("f02", 2.0, None)):
        t = LAY[f]; m_ = np.ones(N, bool) if msk is None else msk
        rate = rate * np.where(m_ & (t == 2), np.sqrt(k), np.where(m_ & (t == 0), 1 / np.sqrt(k), 1.0))
    rate = rate * np.where(C.gr1.to_numpy() == 1, 0.5, 1.0)
    bigs = (rng.random(N) < np.minimum(rate, 1)).astype(int)
    S = C[["era", "ci", "D", "E", "ticker", "kept", "kept2411", "Ey", "month"]].copy()
    S["maxc"] = np.where(bigs == 1, 1.6, 1.05); S["big"] = bigs
    S["monster"] = (bigs * (rng.random(N) < 0.35)).astype(int); S["failed"] = ((1 - bigs) * (rng.random(N) < 0.5)).astype(int)
    S["adr_tail"] = (bigs * (rng.random(N) < 0.6)).astype(int); S["clean"] = (bigs * (rng.random(N) < 0.6)).astype(int)
    S["first_hit"] = np.where(bigs == 1, 10, -1); S["big_untrunc"] = bigs; S["maxc_untrunc"] = S.maxc
    S["big_fromhigh"] = (bigs * (rng.random(N) < 0.8)).astype(int); S["big_e1"] = (bigs * (rng.random(N) < 0.9)).astype(int)
    S["nbars"] = np.where(rng.random(N) < 0.98, 61, 40); S["nbars_untrunc"] = S.nbars
    S["truncated"] = np.where(rng.random(N) < 0.003, "guard", ""); S["ends_inside"] = (S.nbars < 61).astype(int)
    S["full_window"] = ((S.nbars == 61) & (S.truncated == "")).astype(int); S["proxy"] = 10.0; S["qqq_above50"] = (rng.random(N) < 0.6).astype(int)
    S = S[COLS]
    S.to_csv(W(SYNF), sep="\t", index=False, float_format="%.10g", compression={"method": "gzip", "mtime": 0})
    O1 = load_outcomes(SYNF)
else:
    O1 = load_outcomes(OUTC)
    P(f"\noutcomes: {OUTC.name} sha256 {sha(OUTC)}; {len(O1)} check rows, E {O1.E.min()}..{O1.E.max()} (ASSERT <= {CUT})")
Y = {c: O1[c].to_numpy(float) for c in YCOLS}
big = Y["big"]

# ════════════════════════════════════════ 1. base rates ════════════════════════════════════════
P("\n" + "=" * 110)
P("## 1. CHECK BASE RATES (big winner = +50% close within 60 sessions of max(level, open(E)); description)")
for lab, m in [(str(y), EY == y) for y in sorted(set(EY))] + [("era A", ERA == "A"), ("era B", ERA == "B"), ("ALL", np.ones(N, bool))]:
    P(f"   {lab:6s} n {int(m.sum()):5d} | big {int(big[m].sum()):4d} ({100 * big[m].mean():5.2f}%) | monster {int(Y['monster'][m].sum()):4d} | clean {int(Y['clean'][m].sum()):4d}"
      f" | ADR tail {int(Y['adr_tail'][m].sum()):4d} | failed {int(Y['failed'][m].sum()):5d} ({100 * Y['failed'][m].mean():5.2f}%)")
P(f"   discovery 2017-19 rate (stage 3) {100 * P0:.2f}%; check era B / that = {big[ERA == 'B'].mean() / P0:.2f}x; monsters on check {int(Y['monster'].sum())}" + ("  [THIN: under 60]" if Y['monster'].sum() < 60 else ""))
P(f"   window facts: truncated {int((O1.truncated != '').sum())} (by reason {O1[O1.truncated != ''].truncated.value_counts().to_dict()}); fewer than 61 bars {int((O1.nbars < 61).sum())}; full windows {int(O1.full_window.sum())};"
  f" big winners lost to truncation {int(((Y['big_untrunc'] == 1) & (big == 0)).sum())}")

# ════════════════════════════════════════ 2. the family ════════════════════════════════════════
R = {}
for f in MEMBERS:
    t = LAY[f]
    r = dict(f=f)
    if f == "gr1":
        jr, c = mh_nv(big, t, UM); r["c"] = c
        pl = -perm_lr(big, t, two_=True)                                    # log(not-V / V)
    else:
        c = counts(big, t); r["c"] = c
        jr = judged(f, big)
        pl = MDIR[f] * perm_lr(big, t)                                      # frozen-direction log ratio
    pl = pl[np.isfinite(pl)]
    lo_ = np.log(jr) if np.isfinite(jr) and jr > 0 else np.nan
    r["ratio"] = jr
    r["p1"] = (1 + int((pl >= lo_ - 1e-12).sum())) / (len(pl) + 1)
    r["p_opp"] = (1 + int((pl <= lo_ + 1e-12).sum())) / (len(pl) + 1)
    r["pmed"] = float(np.exp(np.median(pl))); r["nperm"] = len(pl)
    r["ci"] = boot(f, big)
    r["eraA"] = judged(f, big, mask=ERA == "A"); r["eraB"] = judged(f, big, mask=ERA == "B")
    r["same"] = bool(np.isfinite(r["eraA"]) and np.isfinite(r["eraB"]) and r["eraA"] > 1.0 and r["eraB"] > 1.0)
    if f == "gr1":
        r["b4"] = mh_nv(big, two(keys=[KB4]), KB4)[0]
        for k in ("monster", "clean", "adr_tail"):
            r[k] = mh_nv(Y[k], t, UM)[0]
    else:
        r["b4"] = judged(f, big, t=LB4[f])
        for k in ("monster", "clean", "adr_tail"):
            r[k] = judged(f, Y[k])
    R[f] = r
ADJ = holm(np.array([R[f]["p1"] for f in MEMBERS]))
ADJO = holm(np.array([R[f]["p_opp"] for f in MEMBERS]))
for f, a, b in zip(MEMBERS, ADJ, ADJO):
    R[f]["holm"], R[f]["holm_opp"] = float(a), float(b)


def verdict(f, r=None):
    r = R[f] if r is None else r
    lr = np.log(r["ratio"]) if np.isfinite(r["ratio"]) and r["ratio"] > 0 else np.nan
    if np.isfinite(lr) and lr >= np.log(TAIL) - 1e-12:
        if r["holm"] <= 0.05:
            w = "PICKS THE TAIL" if r["same"] else "PICKS THE TAIL (one era only)"
            if f in L.SEEN:
                w += " (check years partly seen)"
            return w
        return "DIRECTIONAL, NOT PROVEN"
    if np.isfinite(lr) and lr <= np.log(REV) + 1e-12 and r["holm_opp"] <= 0.05:
        return "REVERSED"
    return "NOT CONFIRMED"


# outcome-free unit test of the verdict table and Holm (runs in both modes, before any member's verdict is set)
_cases = [("f01", 1.5, 0.01, True, 1.0, "PICKS THE TAIL"), ("f04", 1.5, 0.01, True, 1.0, "PICKS THE TAIL (check years partly seen)"),
          ("f09", 1.5, 0.01, False, 1.0, "PICKS THE TAIL (one era only)"), ("f01", 1.2, 0.05, True, 1.0, "PICKS THE TAIL"),
          ("gr1", 1.5, 0.2, True, 1.0, "DIRECTIONAL, NOT PROVEN"), ("f02", 0.8, 1.0, False, 0.01, "REVERSED"), ("f02", 0.8, 1.0, False, 0.2, "NOT CONFIRMED"),
          ("f01", 1.1, 0.001, True, 1.0, "NOT CONFIRMED"), ("f01", 0.84, 1.0, False, 0.001, "NOT CONFIRMED"), ("combo", float("nan"), 1.0, False, 1.0, "NOT CONFIRMED")]
for f_, r_, h_, s_, ho_, want in _cases:
    got = verdict(f_, dict(ratio=r_, holm=h_, same=s_, holm_opp=ho_))
    assert got == want, (f_, r_, got, want)
assert np.allclose(holm(np.array([0.01, 0.04, 0.03, 0.005, 0.5, 0.2])), [0.05, 0.12, 0.12, 0.03, 0.5, 0.4])
P(f"\n   verdict-table and Holm unit test ({len(_cases)} cases, every word): PASS")
TRUNC = ["f01", "f03", "f04", "f07"]


def tags(f):
    t = []
    if f in TRUNC:
        t.append("gate-truncated")
    if f in L.SEEN:
        t.append("seen on the check years (A+ read 10-22)")
    if f in CARRIED:
        if CARRIED[f]["tag_b4"]:
            t.append("break-day selection")
        if CARRIED[f]["qm_share"] < 29.0:
            t.append("against Qullamaggie's buys")
    t.append("era-B price partly derived")
    return "[" + "; ".join(t) + "]"


for f in MEMBERS:
    R[f]["verdict"] = verdict(f)
    rr_ = R[f]["ratio"]
    R[f]["flag083"] = bool(np.isfinite(rr_) and 0.83 < rr_ <= REV + 1e-12)

P("\n" + "=" * 110)
P(f"## 2. THE CHECK - prereg 5.3, family of m = {M}, Holm step-down, one-sided in the frozen direction (permutation {NS:,}, rng {L.SEED}; bootstrap {NBOOT:,})")
P("   tag 'era-B population thinned by volume underflow': NOT fired (stage 1e, rung-3 reading <= 1%; its rungs disagree - flagged there)")
for f in MEMBERS:
    r = R[f]; c = r["c"]
    P(f"\n{f} - {NAMES[f]} | frozen direction: {DIRW[f]}  {tags(f)}")
    if f == "gr1":
        P(f"   big winner: V {c['wv']}/{c['nv']} = {100 * c['wv'] / max(c['nv'], 1):.2f}% | not-V {c['wn']}/{c['nn']} = {100 * c['wn'] / max(c['nn'], 1):.2f}% (usable strata)")
    else:
        P(f"   big winner: bottom {c['wb']}/{c['nb']} = {100 * c['wb'] / c['nb']:.2f}% | middle {c['wm']}/{c['nm']} = {100 * c['wm'] / max(c['nm'], 1):.2f}% | top {c['wt']}/{c['nt']} = {100 * c['wt'] / c['nt']:.2f}%")
    P(f"   CHECK RATIO (frozen direction) {fr_(r['ratio'])} (90% {r['ci'][0]:.2f}-{r['ci'][1]:.2f}) | one-sided p {r['p1']:.4f} -> Holm p {r['holm']:.4f} | opposite one-sided p {r['p_opp']:.4f} -> REVERSED-family Holm p {r['holm_opp']:.4f}"
      f" | permutation median {r['pmed']:.3f}")
    P(f"   per era (frozen direction): era A {fr_(r['eraA'])} | era B {fr_(r['eraB'])} -> same direction in every era: {'yes' if r['same'] else 'no'}")
    P(f"   beside it: monster {fr_(r['monster'])} | clean {fr_(r['clean'])} | ADR-scaled tail {fr_(r['adr_tail'])} | within B4 strata {fr_(r['b4'])}")
    P(f"   VERDICT: {r['verdict']}" + ("  ** ratio in (0.83, 0.8333]: the 1/1.2 reading decides **" if r["flag083"] else "")
      + (f" | {sdr_txt(f)}" if r["verdict"] in ("NOT CONFIRMED", "DIRECTIONAL, NOT PROVEN") else ""))

P("\n## VERDICT TABLE (prereg 5.3)")
P(f"   {'member':6} {'name':40} {'ratio':>6} {'90% interval':>13} {'p1':>7} {'Holm':>7} {'eraA':>6} {'eraB':>6} {'same':>4}  verdict")
for f in MEMBERS:
    r = R[f]
    P(f"   {f:6} {NAMES[f][:40]:40} {fr_(r['ratio']):>6} {r['ci'][0]:6.2f}-{r['ci'][1]:<6.2f} {r['p1']:7.4f} {r['holm']:7.4f} {fr_(r['eraA']):>6} {fr_(r['eraB']):>6} {('yes' if r['same'] else 'no'):>4}  {r['verdict']}")
PICKS = [f for f in MEMBERS if R[f]["verdict"].startswith("PICKS THE TAIL")]
if PICKS:
    pk = ", ".join(f + " (" + R[f]["verdict"] + ")" for f in PICKS)
    P(f"\n   REACHED PICKS THE TAIL: {pk} -> stage 8 blind sheets B follow (prereg 6.8).")
else:
    pmed15 = float(np.median([POW15[f] for f in POW15]))
    P(f"\n   No chart reading reached the bar. With {N} events and a base rate of {100 * P0:.1f}% this study finds a real 1.5x reading {100 * pmed15:.0f}% of the time;"
      " it says nothing about whether Qullamaggie's breakouts pay - they did, for years. The miss is in our measurement or our list.")

# ════════════════════════════════════════ benchmarks ════════════════════════════════════════
P("\n" + "=" * 110)
P("## BENCHMARKS B1-B3 - ONE table (not a test of the grade - the grade is judged on Qullamaggie's buys only, #717; description)")
for b in ("B1", "B2", "B3"):
    t = LAY[b]; c = counts(big, t); rb = ratio(c)
    pl = perm_lr(big, t); p2 = (1 + int((np.abs(pl) >= abs(np.log(rb)) - 1e-12).sum())) / (NS + 1)
    MDIR[b] = 1; lo, hi = boot(b, big)
    ga = ratio(counts(big, thirds(b, mask=gapA))); gb = ratio(counts(big, thirds(b, mask=gapB)))
    P(f"   {b} {NAMES[b]:18s}: bottom {c['wb']}/{c['nb']} | top {c['wt']}/{c['nt']} | ratio top/bottom {rb:.3f} (two-sided p {p2:.4f}, 90% {lo:.2f}-{hi:.2f}) | era A {fr_(ratio(counts(big, t, ERA == 'A')))} | era B {fr_(ratio(counts(big, t, ERA == 'B')))}"
      f" | within B4 strata {fr_(ratio(counts(big, LB4[b])))} | gapped over the level {fr_(ga)} / did not {fr_(gb)}")
c = counts(big, LAY["B4"])
P(f"   B4 (selection control, never a member): bottom {c['wb']}/{c['nb']} top {c['wt']}/{c['nt']} ratio top/bottom {ratio(c):.3f} | era A {fr_(ratio(counts(big, LAY['B4'], ERA == 'A')))} | era B {fr_(ratio(counts(big, LAY['B4'], ERA == 'B')))}")

# ════════════════════════════════════════ 5.5 extra readings ════════════════════════════════════════
P("\n" + "=" * 110)
P("## 5.5 EXTRA READINGS on check (description; NONE is a bar). 'dir' = the ratio in the frozen direction (gr1: not-V / V).")


def pop_line(lab, f, y, mask=None, t=None, blocks=None):
    if f == "gr1":
        tt = two(mask=mask) if t is None else t
        rr_, c = mh_nv(y, tt, UM if blocks is None else blocks, None if t is None else mask)
        return f"      {lab:46s} V winners {c['wv']}/{c['nv']} | not-V {c['wn']}/{c['nn']} | dir {fr_(rr_)}"
    tt = thirds(f, mask=mask) if t is None else t
    c = counts(y, tt, None if t is None else mask)
    rt = ratio(c); d = rt if MDIR[f] > 0 else (1 / rt if np.isfinite(rt) and rt > 0 else np.nan)
    return f"      {lab:46s} n(top+bottom) {c['nt'] + c['nb']:5d} | winners top:bottom {c['wt']}:{c['wb']} | ratio top/bottom {fr_(rt)} | dir {fr_(d)}"


for f in MEMBERS:
    P(f"\n   {f} {NAMES[f]} - {DIRW[f]} | verdict {R[f]['verdict']}")
    P("    population:")
    for y in sorted(set(EY)):
        P(pop_line(f"year {y}", f, big, EY == y, t=LAY[f]))
    for e in ("A", "B"):
        P(pop_line(f"era {e}", f, big, ERA == e, t=LAY[f]))
    for lab, m in (("first breaks (after 10 quiet sessions)", (C.first10 == True).to_numpy()), ("later breaks", (C.first10 == False).to_numpy()),   # noqa: E712
                   ("first break after 60 quiet sessions", (C.first60 == True).to_numpy()), ("common stock only", (C.sectype == "CS").to_numpy()),   # noqa: E712
                   ("price >= $5", (C.f02 >= 5).to_numpy()), ("full 60-session windows only", (O1.full_window == 1).to_numpy()),
                   ("QQQ above its 50-day at D", (O1.qqq_above50 == 1).to_numpy()), ("QQQ below its 50-day at D", (O1.qqq_above50 == 0).to_numpy()),
                   ("gapped over the level at the open", gapA), ("did not gap over the level", gapB)):
        P(pop_line(lab, f, big, m))
    P("    outcome:")
    for lab, k in (("monster tier (>= 2.0x)", "monster"), ("clean winners", "clean"), ("ADR-scaled tail", "adr_tail"), ("un-truncated window", "big_untrunc"),
                   ("from max(level, high of E)", "big_fromhigh"), ("E+1 .. E+60 (E's close excluded)", "big_e1")):
        P(pop_line(lab, f, Y[k], t=LAY[f]))
    if f == "gr1":
        P(pop_line("ADR-neutral (MH by era x month x f01 third, 6d form)", f, big, t=two(keys=[KADR]), blocks=KADR))
        P(pop_line("FAILED (peak < 1.10x; under 1.0 = V fails more)", f, Y["failed"], t=TG))
    else:
        P(pop_line("ADR-neutral (thirds inside ADR20 strata)", f, big, t=LADR[f]))
    P("    conditioning (the member's ratio only):")
    for nm, key in (("B4", "b4t"), ("B1 (pick-score)", "b1t")):
        for k_, lab in ((0, "bottom"), (1, "middle"), (2, "top")):
            m = (C[key] == k_).to_numpy()
            if f == "gr1":
                P(pop_line(f"within the {lab} {nm} third", f, big, m))
            else:
                P(pop_line(f"within the {lab} {nm} third", f, big, m, t=(LB4 if key == "b4t" else LB1)[f]))
P("\n   not printed on check (5.5 states them for discovery only): embargoed discovery, 2019-20 alone, the second seed (2411), window length +-50%.")

# ════════════════════════════════════════ synthetic gate ════════════════════════════════════════
if SYN:
    P("\n## SYNTHETIC GATE")
    words = {R[f]["verdict"] for f in MEMBERS}
    P(f"   verdict words fired: {sorted(words)}")
    meds = {f: R[f]["pmed"] for f in MEMBERS}
    P("   permutation medians (no-effect centre; must sit in 0.95-1.05): " + " | ".join(f"{f} {v:.3f}" for f, v in meds.items()))
    assert all(0.95 <= v <= 1.05 for v in meds.values()), meds
    assert R["f01"]["verdict"].startswith("PICKS THE TAIL") and R["gr1"]["verdict"].startswith("PICKS THE TAIL") and R["f02"]["verdict"] == "REVERSED", {f: R[f]["verdict"] for f in MEMBERS}
    P("   planted readings recovered (f01, gr1 PICKS; f02 REVERSED); medians centred: PASS")

P(f"\n## END OF CHECK{' [SYNTHETIC - not a result]' if SYN else ''} | {time.time() - t0:.0f}s")
W(TXT).write_text("\n".join(LOG) + "\n")
if not SYN:
    json.dump(dict(script_sha=MYSHA, outcomes_sha=sha(OUTC), m=M, n=N, winners=int(big.sum()),
                   members={f: dict(ratio=R[f]["ratio"], ci=R[f]["ci"], p1=R[f]["p1"], holm=R[f]["holm"], p_opp=R[f]["p_opp"], holm_opp=R[f]["holm_opp"],
                                    eraA=R[f]["eraA"], eraB=R[f]["eraB"], same=R[f]["same"], verdict=R[f]["verdict"]) for f in MEMBERS},
                   picks=PICKS), open(W(RES), "w"), indent=1)
