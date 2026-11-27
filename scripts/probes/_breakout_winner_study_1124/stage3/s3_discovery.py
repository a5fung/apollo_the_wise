#!/usr/bin/env python3
"""STAGE 3b - DISCOVERY: base rates first, then prereg 5.2 (conditions 1-4, the break-day-selection tag), the benchmark table and
the 5.5 extra readings of the carried features. Amendments A1 and A2 in force.

READS: the outcome-free stage-1f feature table (DISC rows only) + stage3/discovery_outcomes.tsv.gz (discovery rows only, written
once by s3_outcomes.py). No bar. No check row (dropped at load; every E asserted <= 2020-12-31). Qullamaggie's buys are never
grouped, tabulated or read against an outcome.

Modes: `python3 s3_discovery.py --synthetic` = the same statistics path on coin-toss labels (the outcomes file is NOT opened) -
used to debug before the single real run.   `python3 s3_discovery.py` = THE REAL RUN.

READINGS FIXED BEFORE THE REAL RUN (each is a reading the text leaves open; returned under "readings")
 R1  Assignment / ratio code = stage2/s2lib.py (imported: thirds_block, assign_thirds, assign_two, ratio_counts, mh_counts) - the
     code the two floors were calibrated on. Layout asserted against stage 1f's print (check_layout).
 R2  Ratio = pooled top-third rate / bottom-third rate; smoothed (w + .5)/(n + 1) for BOTH rates ONLY when a third holds no winner
     (5.1 as stage 2 read it); else raw. Every bar is judged on sign x log(ratio) >= log(floor), as the calibration did
     (so "<= 0.80" is 1/1.25 and "<= 0.91" is 1/1.10).
 R3  Permutation (5.1): U = default_rng(1124).random((10000, N), float32), N = the 5,330 discovery events in table order; the SAME
     U for every feature. Within each (era, month) the events ASSIGNED on the feature (scored, month >= 6 scored) are ordered by
     their U key and the winner labels go to the first positions - an exact within-month shuffle among scored events (scored events
     in months too small to hold thirds cannot change the ratio). Two-sided p = (1 + #(|log perm| >= |log observed|)) / 10001.
 R4  90% interval: (era, month) blocks resampled with replacement, 2,000 draws, a fresh default_rng(1124) per feature.
 R5  Condition 3: the feature's own-month thirds, events of 2020 removed (stage 2's 'ex2020'); floor 1.10 (stage 2, lowering rule
     did not fire).
 R6  Condition 4: ALL 22 candidates compete (the EP study's literal reading). THE common set = discovery events scored on every
     candidate other than 24a / 24b; thirds re-formed within month on it; z = |log judged ratio| / SD of the 10,000 permuted log
     ratios there; 24a / 24b on (common set AND own population). Largest z wins its group; the four largest group winners (by
     the same z) take the cap; ties -> smaller own p -> lower number. CARRIED = passes 1-3 AND is its group's winner AND is in
     the four. The alternative reading (only the 1-3 passers compete) is printed and a difference is flagged.
 R7  A2 (f20): the pooled own-month discovery ratio is divided by the FROZEN 0.9441473 (stage 2's composition-expected value, 2020
     at 3x); the quotient meets conditions 1 and the z. Any other f20 ratio is divided by its own stage-2-model composition-expected
     value (mean event rate of the top third / of the bottom third, 2020 at 3x, computed outcome-free here by stage 2's formula)
     ONLY when that value is outside 0.95-1.05; else read raw. Condition 2 (the p) is NOT a floor or a verdict word: it runs on
     the RAW ratio as 5.1 writes it; the p centred on the frozen expected value is printed beside it and a straddle of 0.05 is
     flagged. The permutation median of f20's ratio (the real-rates centre) is printed; a verdict flip under it is a discrepancy
     to report, never a substitution.
 R8  Break-day-selection tag: B4 thirds over ALL kept discovery events of the (era, quarter); feature thirds inside strata
     (era, quarter, B4 third) holding >= 9 scored events; pooled ratio in the frozen direction; under 1.10 -> tag (stage 2 floor).
 R9  5.5 population readings re-form the thirds INSIDE the population (stage 2 section C); per-year lines use the own thirds.
     ADR-neutral = thirds inside (era, quarter, ADR20 third) strata >= 9 (the EP form). 'Fragile' (window +-50%) = direction
     flips or the ratio in the frozen direction is under 1.2.
 R10 Two-group features 11, 14, 23 are DESCRIPTION ONLY (stage 1f): Mantel-Haenszel by month printed, never a candidate.
 R11 'against Qullamaggie's buys' = the winning third's share in stage 1f's position table (printed before any outcome) < 29%.
 GATE (the prereg names none for stage 3; fixed here): every assert holds, s3_outcomes.py's cross-checks vs stage 1e hold, the
     independent recount (s3_verify.py) equals the captured outcomes, and the synthetic run recovers the planted readings with
     every no-effect permutation median inside 0.95-1.05 (f20 as a quotient).
"""
import re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stage2"))
import s2lib as L

SYN = "--synthetic" in sys.argv
A2 = L.REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md"
A2_SHA = "0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b"
OUTC = HERE / "discovery_outcomes.tsv.gz"
NS, NBOOT = 10_000, 2_000
C1, FL3, FL4 = 1.25, 1.10, 1.10
F20_EXP = 0.9441473
BAND = (0.95, 1.05)
DISC_LAST, EMBARGO = "2020-12-31", "2020-10-06"
X2020 = 3.0
NAMES = {"f01": "Daily range (ADR20)", "f02": "Price (raw close)", "f03": "Dollar volume", "f04": "Strength rank, best", "f05": "Strength rank, 1 month",
         "f06": "Strength rank, 6 months", "f07": "Prior move", "f08": "20-session run-up", "f09": "6-month move", "f10": "Close / 52-week high",
         "f11": "Level is a 52-week high", "f12": "Base length", "f13": "Base depth, %", "f14": "Level comes from a range", "f15": "Last-10-close spread",
         "f16": "Range contraction", "f17": "Volume dry-up", "f18": "Up vs down volume", "f19": "Extension above the 10-day", "f20": "Shape count",
         "f21": "Close vs the 200-day (daily ranges)", "f22": "Sessions since the 52-week low", "f23": "First base since the major low",
         "f24a": "Gap at the open, opened ABOVE the level", "f24b": "Gap at the open, opened at / below the level",
         "B1": "Pick-model score", "B2": "Live order score", "B3": "Group strength", "B4": "Distance close(D) -> level (daily ranges)"}
GROUPS = {"volatility": ["f01"], "size": ["f02", "f03"], "strength": ["f04", "f05", "f06"], "run-up": ["f07", "f08", "f09"], "highs": ["f10", "f11"],
          "base": ["f12", "f13", "f14"], "tightness": ["f15", "f16"], "volume": ["f17", "f18"], "averages": ["f19", "f20"], "trend": ["f21", "f22"],
          "stage": ["f23"], "open": ["f24a", "f24b"]}
GROUP_OF = {f: g for g, fs in GROUPS.items() for f in fs}
TRUNC = ["f01", "f03", "f04", "f07"]            # gate-truncated (prereg 4.1)
CAND = L.CANDIDATES
LOG = []


def P(s=""):
    print(s, flush=True); LOG.append(s)


t0 = time.time()
L.assert_docs()
assert L.sha(A2) == A2_SHA, "A2 sha256 differs - STOP"
fl = (HERE.parent / "stage2/floors_final.txt").read_text()
assert "condition 3 (without-2020) floor: 1.10" in fl and "break-day-selection (B4 strata) floor: 1.10" in fl
P("# STAGE 3 - DISCOVERY" + ("   [SYNTHETIC MODE: coin-toss labels, the outcomes file is NOT opened - NOT a result]" if SYN else ""))
P(f"prereg {L.PREREG_SHA[:8]} / A1 {L.A1_SHA[:8]} / A2 {A2_SHA[:8]} / feature table {L.TABLE_SHA[:8]} asserted; floors 1.10 / 1.10 asserted vs stage2/floors_final.txt")
P(f"code sha256: this script {L.sha(__file__)[:16]} | s2lib {L.sha(L.__file__)[:16]}")

# ════════════════════════════════════════ table (outcome-free) ════════════════════════════════════════
T = L.load()
T = T[T.set == "DISC"].reset_index(drop=True)                     # CHECK rows dropped at load
assert T.E.max() <= DISC_LAST and (T.era == "A").all()
D = T[T.kept == True].reset_index(drop=True)                      # noqa: E712
D2 = T[T.kept2411 == True].reset_index(drop=True)                 # noqa: E712  (second seed, 5.5)
del T                                                             # the Qullamaggie-only rows are gone with it; `qm` is never read
N = len(D)
assert N == 5330 and len(D2) == 5314
LAYOUT = L.check_layout(D)
for fr in (D, D2):
    fr["f24a"] = np.where((fr.f24grp == "a"), fr.f24, np.nan)
    fr["f24b"] = np.where((fr.f24grp == "b"), fr.f24, np.nan)
    for col, nm in (("B4", "b4t"), ("B1", "b1t"), ("f01", "adrt")):
        fr[nm] = L.assign_thirds(fr[col].to_numpy(float), [fr.era.to_numpy(), fr.quarter.to_numpy()], 1)
        assert (fr[nm] >= 0).all()
assert (D.f11.isna() == D.f10.isna()).all() and (D.f23.isna() == D.f22.isna()).all() and D.f14.notna().all()
EY = D.Ey.to_numpy()
is2020 = EY == 2020
COMMON = np.ones(N, bool)
for f in CAND:
    if f not in ("f24a", "f24b"):
        COMMON &= D[f].notna().to_numpy()


class Lay:
    """a population (frame) + the month / strata keys; thirds of any column inside any sub-mask."""
    def __init__(self, fr):
        self.fr, self.n = fr, len(fr)
        self.era, self.month, self.qtr = fr.era.to_numpy(), fr.month.to_numpy(), fr.quarter.to_numpy()
        self.um = pd.factorize(fr.era + fr.month)[0]
        self.ey = fr.Ey.to_numpy()
        self.pb = 0.05 * np.where(self.ey == 2020, X2020, 1.0)     # stage 2's no-effect event rate (the centre is rate-free up to scale)

    def thirds(self, col, mask=None, strata=None):
        x = self.fr[col].to_numpy(float).copy()
        if mask is not None:
            x[~mask] = np.nan
        if strata is None:
            return L.assign_thirds(x, [self.era, self.month], L.MIN_MONTH)
        return L.assign_thirds(x, [self.era, self.qtr, self.fr[strata].to_numpy()], L.MIN_STRATUM)

    def two(self, col, mask=None):
        x = self.fr[col].to_numpy(float)
        g = np.where(np.isnan(x), -1, np.nan_to_num(x)).astype(int)
        if mask is not None:
            g = np.where(mask, g, -1)
        return L.assign_two(g, [self.era, self.month])

    def expected(self, t, mask=None):
        top, bot = t == 2, t == 0
        if mask is not None:
            top, bot = top & mask, bot & mask
        return float(self.pb[top].mean() / self.pb[bot].mean()) if top.any() and bot.any() else float("nan")


LD, LD2 = Lay(D), Lay(D2)


def counts(y, t, mask=None):
    top, bot, mid = t == 2, t == 0, t == 1
    if mask is not None:
        top, bot, mid = top & mask, bot & mask, mid & mask
    return dict(wt=int(y[top].sum()), nt=int(top.sum()), wb=int(y[bot].sum()), nb=int(bot.sum()), wm=int(y[mid].sum()), nm=int(mid.sum()))


def ratio(c):
    if c["nt"] == 0 or c["nb"] == 0:
        return float("nan")
    return float(L.ratio_counts(np.array([c["wt"]]), c["nt"], np.array([c["wb"]]), c["nb"])[0])


def mh(y, t, um):
    """Mantel-Haenszel yes/no by month (months already hold >= 2 of each through assign_two)."""
    ok = t >= 0
    us = np.unique(um[ok])
    Wy = np.array([[y[(um == u) & (t == 2)].sum() for u in us]], float); Wn = np.array([[y[(um == u) & (t == 0)].sum() for u in us]], float)
    ny = np.array([((um == u) & (t == 2)).sum() for u in us], float); nn = np.array([((um == u) & (t == 0)).sum() for u in us], float)
    return float(L.mh_counts(Wy, ny, Wn, nn)[0]) if len(us) else float("nan")


UKEY = np.random.default_rng(L.SEED).random((NS, N), dtype=np.float32)


def perm_lr(y, t, lay=None, two=False):
    """R3: the 10,000 permuted log ratios of layout t (discovery seed-1124 frame only)."""
    assert len(t) == N
    asg = t >= 0
    um = LD.um
    WT = np.zeros(NS); WB = np.zeros(NS); NUM = np.zeros(NS); DEN = np.zeros(NS)
    for u in np.unique(um[asg]):
        idx = np.flatnonzero(asg & (um == u))
        wpos = np.flatnonzero(y[idx] == 1)
        if len(wpos) == 0:
            continue
        A = np.argsort(UKEY[:, idx], axis=1, kind="stable")[:, wpos]
        tt = t[idx][A]
        a = (tt == 2).sum(1); c = (tt == 0).sum(1)
        if two:
            n1 = int((t[idx] == 2).sum()); n0 = int((t[idx] == 0).sum())
            NUM += a * n0 / (n1 + n0); DEN += c * n1 / (n1 + n0)
        else:
            WT += a; WB += c
    if two:
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(NUM / DEN)
    return np.log(L.ratio_counts(WT, int((t == 2).sum()), WB, int((t == 0).sum())))


def boot(y, t, um, seed=L.SEED):
    asg = t >= 0
    us = np.unique(um[asg])
    comp = np.array([[y[(um == u) & (t == 2)].sum(), ((um == u) & (t == 2)).sum(), y[(um == u) & (t == 0)].sum(), ((um == u) & (t == 0)).sum()] for u in us], float)
    draw = np.random.default_rng(seed).integers(0, len(us), size=(NBOOT, len(us)))
    s = comp[draw].sum(1)
    ok = (s[:, 1] > 0) & (s[:, 3] > 0)
    rr = L.ratio_counts(s[ok, 0], s[ok, 1], s[ok, 2], s[ok, 3])
    return float(np.percentile(rr, 5)), float(np.percentile(rr, 95))


def fr_(x):
    return "nan" if not np.isfinite(x) else f"{x:.3f}"


# ════════════════════════════════════════ outcome-free prints (identical in both modes) ════════════════════════════════════════
TM = {f: LD.thirds(f) for f in CAND + ["B1", "B2", "B3", "B4"]}
TB4 = {f: LD.thirds(f, strata="b4t") for f in CAND + ["B1", "B2", "B3"]}
TADR = {f: LD.thirds(f, strata="adrt") for f in CAND}
TC = {f: LD.thirds(f, mask=COMMON) for f in CAND}
TWO = {f: LD.two(f) for f in ("f11", "f23")}
e_all = LD.expected(TM["f20"])
assert abs(e_all - F20_EXP) < 1e-6, e_all
F20E = {"all": F20_EXP, "ex2020": LD.expected(TM["f20"], ~is2020), "b4": LD.expected(TB4["f20"]), "common": LD.expected(TC["f20"]), "adr": LD.expected(TADR["f20"])}
P(f"\nlayout (bottom / middle / top) equals stage 1f's print: {LAYOUT}")
P(f"discovery events {N} (2017 {int((EY == 2017).sum())} / 2018 {int((EY == 2018).sum())} / 2019 {int((EY == 2019).sum())} / 2020 {int(is2020.sum())}); second seed {len(D2)}; common set (scored on the 20 candidates other than 24a / 24b) {int(COMMON.sum())}"
  f" [24a {int((COMMON & D.f24a.notna()).sum())}, 24b {int((COMMON & D.f24b.notna()).sum())}]")
P("A2 / R7 - f20 composition-expected ratio under no effect (stage-2 model, 2020 at 3x; outcome-free): "
  + " | ".join(f"{k} {v:.4f}{' -> QUOTIENT' if not BAND[0] <= v <= BAND[1] else ' -> raw'}" for k, v in F20E.items())
  + f"   (the 'all' value reproduces stage 2's frozen {F20_EXP})")


def f20_div(key):
    v = F20E[key]
    return F20_EXP if key == "all" else (v if not BAND[0] <= v <= BAND[1] else 1.0)


# Qullamaggie position table (stage 1f, printed before any outcome): share of his break-row buys in bottom / top third
QMPOS = {}
for ln in (HERE.parent / "stage1f/1f_build.txt").read_text().splitlines():
    m = re.match(r"^(f\d\d[ab]?|B\d)\s+(\d+)\s+([\d.]+)% \[[^\]]*\]\s+([\d.]+)% \[[^\]]*\]\s+([\d.]+)% \[", ln)
    if m:
        QMPOS[m.group(1)] = (float(m.group(3)), float(m.group(5)))
assert all(f in QMPOS for f in CAND), sorted(set(CAND) - set(QMPOS))

# ════════════════════════════════════════ outcomes ════════════════════════════════════════
YCOLS = ["big", "monster", "failed", "adr_tail", "clean", "big_untrunc", "big_fromhigh", "big_e1", "big_w30", "big_w90"]
if SYN:
    P("\n## SYNTHETIC LABELS (no outcome file opened). 4% outside 2020, 12% in 2020; planted 2.0x on f08 (high), f13 (high), f02 (LOW).")
    rng = np.random.default_rng(7)

    def synth(fr, lay):
        rate = np.where(fr.Ey.to_numpy() == 2020, 0.12, 0.04).astype(float)
        for f, hi in (("f08", True), ("f13", True), ("f02", False)):
            t = lay.thirds(f)
            rate = rate * np.where(t == (2 if hi else 0), 4 / 3, np.where(t == (0 if hi else 2), 2 / 3, 1.0))
        o = pd.DataFrame({"big": (rng.random(len(fr)) < rate).astype(int)})
        for c in YCOLS[1:]:
            o[c] = (o.big * (rng.random(len(fr)) < 0.6)).astype(int) if c != "failed" else ((1 - o.big) * (rng.random(len(fr)) < 0.5)).astype(int)
        o["full_window"] = (rng.random(len(fr)) < 0.97).astype(int); o["truncated"] = ""; o["ends_inside"] = 0; o["nbars"] = 61
        o["qqq_above50"] = (rng.random(len(fr)) < 0.7).astype(int)
        return o
    O1, O2 = synth(D, LD), synth(D2, LD2)
else:
    O = pd.read_csv(OUTC, sep="\t", keep_default_na=False, na_values=["nan"], dtype={"ticker": str, "truncated": str})
    assert len(O) == 9968 and O.E.max() <= DISC_LAST and (O.era == "A").all()
    P(f"\noutcomes: {OUTC.name} sha256 {L.sha(OUTC)} ; {len(O)} discovery rows, max E {O.E.max()} (ASSERT <= {DISC_LAST})")
    O1 = D[["ci", "ticker"]].merge(O, on=["ci", "ticker"], how="left", validate="1:1")
    O2 = D2[["ci", "ticker"]].merge(O, on=["ci", "ticker"], how="left", validate="1:1")
    assert O1.big.notna().all() and O2.big.notna().all() and (O1.kept == True).all() and (O2.kept2411 == True).all()   # noqa: E712
Y = {c: O1[c].to_numpy(float) for c in YCOLS}
Y2 = {c: O2[c].to_numpy(float) for c in YCOLS}
big = Y["big"]

# ════════════════════════════════════════ 1. BASE RATES FIRST ════════════════════════════════════════
P("\n" + "=" * 110)
P("## 1. BASE RATES (prereg 2: the 2017-19 rate on its own line - it picks the row of 5.4)")
m1719 = ~is2020
r1719, rall, r2020 = big[m1719].mean(), big.mean(), big[is2020].mean()
P(f"   2017-19 big-winner rate (+50% close within 60 sessions of the buy-point proxy): {int(big[m1719].sum())} of {int(m1719.sum())} = {100 * r1719:.2f}%")
P(f"   pooled discovery rate 2017-2020: {int(big.sum())} of {N} = {100 * rall:.2f}%   | 2020 alone {int(big[is2020].sum())} of {int(is2020.sum())} = {100 * r2020:.2f}% = {r2020 / r1719:.2f}x the 2017-19 rate (the simulation guessed 3x)")
grid = [0.03, 0.05, 0.08]
near = min(grid, key=lambda g: abs(np.log(r1719 / g)))
P(f"   5.4 row picked by the 2017-19 rate: nearest grid rate {near:.0%} (grid 3% / 5% / 8%; nearest on the log scale)"
  + ("  ** the rate is OUTSIDE the grid's range - 5.4's figures do not bracket it **" if not 0.03 <= r1719 <= 0.08 else ""))
P("   per year: events | big winners | monsters (>= 2.0x) | clean winners | ADR-scaled tail | failed (max close < 1.10x)")
for lab, m in [(str(y), EY == y) for y in (2017, 2018, 2019, 2020)] + [("2017-19", m1719), ("2019-20", (EY >= 2019)), ("ALL", np.ones(N, bool)), (f"E<={EMBARGO}", (D.E <= EMBARGO).to_numpy())]:
    tag = "  [few delisted names on file]" if lab in ("2017", "2018") else ""
    P(f"   {lab:13s} n {int(m.sum()):5d} | big {int(big[m].sum()):4d} ({100 * big[m].mean():5.2f}%) | monster {int(Y['monster'][m].sum()):4d} ({100 * Y['monster'][m].mean():5.2f}%) | clean {int(Y['clean'][m].sum()):4d}"
      f" | ADR tail {int(Y['adr_tail'][m].sum()):4d} ({100 * Y['adr_tail'][m].mean():5.2f}%) | failed {int(Y['failed'][m].sum()):5d} ({100 * Y['failed'][m].mean():5.2f}%){tag}")
nmon = int(Y["monster"].sum())
P(f"   monsters in discovery: {nmon}" + ("  [THIN: under 60]" if nmon < 60 else ""))
P(f"   window facts: truncated by the frozen rule {int((O1.truncated.fillna('') != '').sum())} events; big winners lost to truncation (un-truncated winner, truncated not) {int(((Y['big_untrunc'] == 1) & (big == 0)).sum())};"
  f" un-truncated rate {100 * Y['big_untrunc'].mean():.2f}% | from max(level, high of E) {100 * Y['big_fromhigh'].mean():.2f}% | E+1..E+60 {100 * Y['big_e1'].mean():.2f}% | 30 sessions {100 * Y['big_w30'].mean():.2f}% | 90 sessions {100 * Y['big_w90'].mean():.2f}%")
P(f"   second seed (2411): {int(Y2['big'].sum())} of {len(D2)} = {100 * Y2['big'].mean():.2f}% ; 2017-19 {100 * Y2['big'][D2.Ey.to_numpy() != 2020].mean():.2f}%")


# ════════════════════════════════════════ 2. 5.2 ════════════════════════════════════════
def read_feature(f, cand=True):
    tm = TM[f]
    r = dict(f=f)
    c = counts(big, tm); r["c"] = c
    raw = ratio(c)
    div = f20_div("all") if f == "f20" else 1.0
    pl = perm_lr(big, tm)
    r.update(raw=raw, div=div, judged=raw / div, lr=float(np.log(raw / div)), pmed=float(np.exp(np.median(pl))), sd=float(pl.std()),
             p=(1 + int((np.abs(pl) >= abs(np.log(raw)) - 1e-12).sum())) / (NS + 1),
             null95=(float(np.exp(np.percentile(pl, 2.5))), float(np.exp(np.percentile(pl, 97.5)))))
    if f == "f20":
        r["p_centred"] = (1 + int((np.abs(pl - np.log(div)) >= abs(np.log(raw / div)) - 1e-12).sum())) / (NS + 1)
        r["judged_permcentre"] = raw / r["pmed"]
    r["dir"] = 1 if r["lr"] > 0 else -1
    lo, hi = boot(big, tm, LD.um); r["ci"] = (lo / div, hi / div)
    cx = counts(big, tm, ~is2020); dx = f20_div("ex2020") if f == "f20" else 1.0
    r["ex"] = cx; r["ex_r"] = ratio(cx) / dx
    r["only20"] = counts(big, tm, is2020)
    if f in TB4:
        cb = counts(big, TB4[f]); db = f20_div("b4") if f == "f20" else 1.0
        r["b4"] = cb; r["b4_r"] = ratio(cb) / db
    for k in ("monster", "clean", "adr_tail"):
        r[k] = counts(Y[k], tm)
    r["years"] = {y: counts(big, tm, EY == y) for y in (2017, 2018, 2019, 2020)}
    if cand:
        tc = TC[f]; cc = counts(big, tc); dc = f20_div("common") if f == "f20" else 1.0
        plc = perm_lr(big, tc)
        rc = ratio(cc) / dc
        r["zc"] = dict(n=int((tc >= 0).sum()), r=rc, sd=float(plc.std()), z=abs(np.log(rc)) / float(plc.std()) if np.isfinite(rc) and rc > 0 else float("nan"))
        d = r["dir"]
        r["c1"] = bool(d * r["lr"] >= np.log(C1) - 1e-12)
        r["c2"] = bool(r["p"] <= 0.05)
        r["c3"] = bool(np.isfinite(r["ex_r"]) and r["ex_r"] > 0 and d * np.log(r["ex_r"]) >= np.log(FL3) - 1e-12)
        r["c13"] = r["c1"] and r["c2"] and r["c3"]
        r["tag_b4"] = not bool(np.isfinite(r["b4_r"]) and r["b4_r"] > 0 and d * np.log(r["b4_r"]) >= np.log(FL4) - 1e-12)
        qb, qt = QMPOS[f]
        r["qm_share"] = qt if d > 0 else qb
    return r


P("\n" + "=" * 110)
R = {f: read_feature(f) for f in CAND}
BEN = {b: read_feature(b, cand=False) for b in ("B1", "B2", "B3", "B4")}


def rank_key(f):
    return (-R[f]["zc"]["z"], R[f]["p"], int(re.sub(r"\D", "", f)), f)


def winners(pool):
    win = {}
    for g, fs in GROUPS.items():
        fs = [f for f in fs if f in pool]
        if fs:
            win[g] = sorted(fs, key=rank_key)[0]
    order = sorted(win.values(), key=rank_key)
    return win, order, order[:4]


WIN, ORDER, TOP4 = winners(set(CAND))
for f in CAND:
    r = R[f]
    r["gw"] = WIN[GROUP_OF[f]] == f; r["in4"] = f in TOP4
    r["carried"] = r["c13"] and r["gw"] and r["in4"]
PASS13 = [f for f in CAND if R[f]["c13"]]
WIN_alt, ORDER_alt, TOP4_alt = winners(set(PASS13))
CAR = [f for f in CAND if R[f]["carried"]]
CAR_alt = [f for f in PASS13 if f in TOP4_alt]


def dirword(r):
    return "HIGH third wins" if r["dir"] > 0 else "LOW third wins"


def tags(f, r=None):
    t = []
    if f in TRUNC:
        t.append("gate-truncated")
    if f in L.SEEN:
        t.append("seen on the check years (A+ read 10-22)")
    if r is not None and r.get("carried"):
        if r["tag_b4"]:
            t.append("break-day selection")
        if r["qm_share"] < 29.0:
            t.append("against Qullamaggie's buys")
    return ("  [" + "; ".join(t) + "]") if t else ""


def rr(c, div=1.0):
    return fr_(ratio(c) / div)


def block(r, cand=True):
    f = r["f"]; c = r["c"]; d = r["dir"]
    P(f"\n{f} - {NAMES[f]}" + (f" | group: {GROUP_OF[f]}" if f in GROUP_OF else " | not a candidate") + tags(f, r))
    P(f"   big winner: bottom {c['wb']}/{c['nb']} = {100 * c['wb'] / c['nb']:.2f}% | middle {c['wm']}/{c['nm']} = {100 * c['wm'] / max(c['nm'], 1):.2f}% | top {c['wt']}/{c['nt']} = {100 * c['wt'] / c['nt']:.2f}%"
      f" | ratio top/bottom {r['raw']:.3f}" + (f" / composition-expected {r['div']:.4f} = QUOTIENT {r['judged']:.3f} (A2)" if f == "f20" else "") + f" -> {dirword(r)}")
    P(f"   permutation p (two-sided, 10,000) {r['p']:.4f}" + ("  <-- NEAR THE BAR (0.04-0.06)" if 0.04 <= r["p"] <= 0.06 else "")
      + (f" | p centred on the expected value {r['p_centred']:.4f}" + ("  ** STRADDLES 0.05 **" if (r['p'] <= 0.05) != (r['p_centred'] <= 0.05) else "") if f == "f20" else "")
      + f" | permutation median {r['pmed']:.3f} | null 95% band {r['null95'][0]:.2f}-{r['null95'][1]:.2f} | 90% interval {r['ci'][0]:.2f}-{r['ci'][1]:.2f}")
    x, o = r["ex"], r["only20"]
    P(f"   without 2020 (2017-19): bottom {x['wb']}/{x['nb']} top {x['wt']}/{x['nt']} ratio {fr_(r['ex_r'])} | 2020 only: bottom {o['wb']}/{o['nb']} top {o['wt']}/{o['nt']} ratio {rr(o)}")
    if "b4" in r:
        b = r["b4"]
        P(f"   within B4 strata (how big a day E had to be): bottom {b['wb']}/{b['nb']} top {b['wt']}/{b['nt']} ratio {fr_(r['b4_r'])}")
    mo, cl, at = r["monster"], r["clean"], r["adr_tail"]
    nm = mo["wt"] + mo["wb"] + mo["wm"]
    P(f"   monster (>= 2.0x; never a bar): bottom {mo['wb']} top {mo['wt']} ratio {rr(mo)}{'  [thin: ' + str(nm) + ' monsters, under 60]' if nm < 60 else ''} | clean winners: bottom {cl['wb']} top {cl['wt']} ratio {rr(cl)}"
      f" | ADR-scaled tail: bottom {at['wb']} top {at['wt']} ratio {rr(at)}")
    P("   per year (ratio, winners top:bottom): " + " · ".join(f"{y}{'*' if y in (2017, 2018) else ''} {rr(s)} ({s['wt']}:{s['wb']})" for y, s in r["years"].items()) + "   (* few delisted names on file)")
    if not cand:
        return
    yn = lambda b: "PASS" if b else "FAIL"     # noqa: E731
    z = r["zc"]
    P(f"   CONDITIONS: 1 ratio >= 1.25 or <= 0.80: {r['judged']:.3f} {yn(r['c1'])} | 2 p <= 0.05: {r['p']:.4f} {yn(r['c2'])} | 3 without 2020 >= 1.10 same direction: {fr_(r['ex_r'] ** d)} {yn(r['c3'])}"
      f" | 4 common set n {z['n']}: ratio {fr_(z['r'])} z {z['z']:.2f}; group '{GROUP_OF[f]}' winner {WIN[GROUP_OF[f]]}" + (f"; rank {ORDER.index(f) + 1} of {len(ORDER)} group winners" if r["gw"] else "") + f" {yn(r['gw'] and r['in4'])}")
    fails = [str(k) for k, key in ((1, "c1"), (2, "c2"), (3, "c3")) if not r[key]] + ([] if (r["gw"] and r["in4"]) else ["4"])
    P(f"   VERDICT: {f} {NAMES[f]} - " + (f"CARRIED, direction frozen: {dirword(r)}{tags(f, r)}" if r["carried"] else f"NOT CARRIED in this study (fails condition{'s' if len(fails) > 1 else ''} {', '.join(fails)})"))


P(f"## 2. PREREG 5.2 - per feature (permutation {NS} shuffles, rng {L.SEED}; discovery events {N}; big winners {int(big.sum())})")
b4 = BEN["B4"]
B4LINE = (f"   B4 (selection control - distance from close(D) to the level, in daily ranges; NOT a grade, never carried): bottom {b4['c']['wb']}/{b4['c']['nb']} top {b4['c']['wt']}/{b4['c']['nt']}"
          f" ratio {b4['raw']:.3f} (p {b4['p']:.4f}; without 2020 {fr_(b4['ex_r'])})")
P(B4LINE)
for f in CAND:
    block(R[f])

P("\n" + "=" * 110)
P("## DESCRIPTION-ONLY two-group features (stage 1f: smaller group under 15% / empty) - Mantel-Haenszel yes/no by month; never a candidate")
for f in ("f11", "f23"):
    t = TWO[f]
    c = counts(big, t)
    m_ = mh(big, t, LD.um)
    pl = perm_lr(big, t, two=True); pl = pl[np.isfinite(pl)]
    p_ = (1 + int((np.abs(pl) >= abs(np.log(m_)) - 1e-12).sum())) / (len(pl) + 1) if np.isfinite(m_) and m_ > 0 else float("nan")
    P(f"   {f} {NAMES[f]}: NO {c['wb']}/{c['nb']} = {100 * c['wb'] / max(c['nb'], 1):.2f}% | YES {c['wt']}/{c['nt']} = {100 * c['wt'] / max(c['nt'], 1):.2f}% | MH ratio yes/no {fr_(m_)} (permutation p {p_:.4f}, description) | permutation median {np.exp(np.median(pl)):.3f}")
P("   f14 Level comes from a range: NOT EVALUABLE (the yes group is empty by the live code, stage 1f) - no reading")
P(B4LINE)

P("\n" + "=" * 110)
P("## CONDITION 4 - group winners and the cap of four (z on the common set; ALL candidates compete, R6)")
for g, fs in GROUPS.items():
    fs = [f for f in fs if f in CAND]
    if not fs:
        P(f"   group {g:10s}: no candidate (description-only)"); continue
    P(f"   group {g:10s}: " + " | ".join(f"{f} z {R[f]['zc']['z']:.2f} (ratio {fr_(R[f]['zc']['r'])}, own p {R[f]['p']:.4f}, 1-3 {'pass' if R[f]['c13'] else 'fail'})" for f in fs) + f"  -> winner {WIN[g]}")
P("   cap: " + " > ".join(f"{f} z {R[f]['zc']['z']:.2f}" for f in ORDER) + f"  -> the four: {TOP4}")
P(f"   passing conditions 1-3: {PASS13 if PASS13 else 'none'}")
P(f"   ALTERNATIVE reading (only the 1-3 passers compete): group winners {WIN_alt}; the four {TOP4_alt}; carried {CAR_alt}"
  + ("   ** DIFFERS from the frozen reading - reported as a discrepancy, not substituted **" if sorted(CAR_alt) != sorted(CAR) else "   (same carried list)"))

P("\n## SUMMARY (judged ratio; ex20 / B4s in the feature's own direction; z on the common set)")
P(f"   {'feat':5} {'name':42} {'ratio':>6} {'p':>7} {'ex20':>6} {'B4s':>6} {'z':>5} {'grpWin':>6} {'cap4':>5} {'1-3':>5}  verdict")
for f in CAND:
    r = R[f]; d = r["dir"]
    P(f"   {f:5} {NAMES[f][:42]:42} {r['judged']:6.3f} {r['p']:7.4f} {fr_(r['ex_r'] ** d):>6} {fr_(r['b4_r'] ** d):>6} {r['zc']['z']:5.2f} {('yes' if r['gw'] else 'no'):>6} {('yes' if r['in4'] else 'no'):>5} {('pass' if r['c13'] else 'fail'):>5}  {'CARRIED' if r['carried'] else 'NOT CARRIED'}{tags(f, r)}")
P(f"   {'B4':5} {NAMES['B4'][:42]:42} {b4['raw']:6.3f} {b4['p']:7.4f} {fr_(b4['ex_r'] ** b4['dir']):>6} {'-':>6} {'-':>5} {'-':>6} {'-':>5} {'-':>5}  selection control (never carried)")
P("\n## CARRIED LIST (direction frozen)")
if CAR:
    for f in CAR:
        r = R[f]; d = r["dir"]
        P(f"   {f} {NAMES[f]}: {dirword(r)} | ratio {r['judged']:.3f} (90% {r['ci'][0]:.2f}-{r['ci'][1]:.2f}) p {r['p']:.4f} | without 2020 {fr_(r['ex_r'] ** d)} | within B4 strata {fr_(r['b4_r'] ** d)}"
          f" (floor 1.10 -> {'TAG break-day selection' if r['tag_b4'] else 'no tag'}) | monster {rr(r['monster'])} | clean {rr(r['clean'])} | ADR tail {rr(r['adr_tail'])}"
          f" | Qullamaggie's buys in the winning third {r['qm_share']:.1f}%{' -> TAG against Qullamaggie' + chr(39) + 's buys' if r['qm_share'] < 29 else ''}{tags(f, r)}")
else:
    P("   NONE - no feature met all four conditions. Every candidate is NOT CARRIED in this study (final for this study's family, not for the reading).")
P(f"   passing 1-3 but losing on condition 4 (group / cap): {[f for f in PASS13 if not R[f]['carried']] or 'none'}")
P(f"   passing 1-2 only: {[f for f in CAND if R[f]['c1'] and R[f]['c2'] and not R[f]['c3']] or 'none'}")
P(f"   p within 0.04-0.06 (recount-sensitive): {[f for f in CAND if 0.04 <= R[f]['p'] <= 0.06] or 'none'}")
r20 = R["f20"]
flip = (abs(np.log(r20["judged_permcentre"])) >= np.log(C1) - 1e-12) != r20["c1"]
P(f"   f20 (A2): raw {r20['raw']:.3f} / frozen expected {F20_EXP} = {r20['judged']:.3f}; permutation median (real-rates centre) {r20['pmed']:.3f} -> raw / that = {r20['judged_permcentre']:.3f};"
  f" condition 1 under the frozen centre {'PASS' if r20['c1'] else 'FAIL'}" + ("  ** WOULD FLIP under the permutation centre - discrepancy, not substituted **" if flip else " (same under the permutation centre)"))

# ════════════════════════════════════════ benchmarks, one table ════════════════════════════════════════
P("\n" + "=" * 110)
P("## BENCHMARKS B1-B3 - ONE table per stage")
P("   not a test of the grade - the grade is judged on Qullamaggie's buys only (#717)")
P("   B1 is in-sample for 2017-20 (fitted on Qullamaggie's picks, never on returns). B3 codes are a 2026-10-16 snapshot (names gone by 2026 have none).")
gapA, gapB = (D.f24grp == "a").to_numpy(), (D.f24grp == "b").to_numpy()
for b in ("B1", "B2", "B3"):
    r = BEN[b]; c = r["c"]
    ga = counts(big, LD.thirds(b, mask=gapA)); gb = counts(big, LD.thirds(b, mask=gapB))
    P(f"   {b} {NAMES[b]:18s}: bottom {c['wb']}/{c['nb']} = {100 * c['wb'] / c['nb']:.2f}% | middle {c['wm']}/{c['nm']} | top {c['wt']}/{c['nt']} = {100 * c['wt'] / c['nt']:.2f}% | ratio {r['raw']:.3f} (p {r['p']:.4f}, 90% {r['ci'][0]:.2f}-{r['ci'][1]:.2f})"
      f" | without 2020 {fr_(r['ex_r'])} | within B4 strata {fr_(r['b4_r'])} | gapped over the level {rr(ga)} / did not {rr(gb)} | per year " + " · ".join(f"{y} {rr(s)}" for y, s in r["years"].items()))
P(B4LINE)

# ════════════════════════════════════════ combination ════════════════════════════════════════
P("\n## 5.6 COMBINATION")
if len(CAR) >= 2:
    mask = np.ones(N, bool)
    for f in CAR:
        mask &= D[f].notna().to_numpy()
    acc = np.zeros(N)
    for f in CAR:
        sub = D[mask]
        pr = np.full(N, np.nan)
        pr[np.flatnonzero(mask)] = ((sub.groupby(["era", "month"], sort=False)[f].rank(method="average") - 0.5) / sub.groupby(["era", "month"], sort=False)[f].transform("size")).to_numpy()
        acc += pr if R[f]["dir"] > 0 else 1.0 - pr
    D["combo"] = np.where(mask, acc / len(CAR), np.nan)
    tcb = LD.thirds("combo"); cc = counts(big, tcb)
    P("   definition (fixed; tested ONCE on check as one family member): equal-weight mean of the within-(era, month) percentile ranks ((average rank - 0.5) / n, over events scored on all members) of "
      + ", ".join(f"{f} ({'as is' if R[f]['dir'] > 0 else '1 - rank'})" for f in CAR) + "; HIGH third wins.")
    P(f"   discovery numbers are DESCRIPTION ('seen' - the members were chosen on these outcomes): scored {int(mask.sum())}; bottom {cc['wb']}/{cc['nb']} top {cc['wt']}/{cc['nt']} ratio {rr(cc)}")
else:
    P(f"   {len(CAR)} feature(s) carried -> fewer than 2: no combination (5.6).")

# ════════════════════════════════════════ 5.5 extra readings (carried only; NONE is a bar) ════════════════════════════════════════
P("\n" + "=" * 110)
P("## 5.5 EXTRA READINGS of the carried features (description; NONE is a bar). Ratios are top/bottom; 'dir' = in the frozen direction.")


def pop_ratio(lay, y, col, mask, f):
    t = lay.thirds(col, mask=mask)
    c = counts(y, t)
    e = lay.expected(t) if f == "f20" else 1.0
    div = e if (f == "f20" and np.isfinite(e) and not BAND[0] <= e <= BAND[1]) else 1.0
    return c, ratio(c) / div, (e if f == "f20" else None)


def line(lab, c, rt, d, e=None):
    return (f"      {lab:44s} n(top+bottom) {c['nt'] + c['nb']:5d} | winners top:bottom {c['wt']}:{c['wb']} | ratio {fr_(rt)} | dir {fr_(rt ** d) if np.isfinite(rt) and rt > 0 else 'nan'}"
            + (f" | f20 expected {e:.3f}{' (quotient shown)' if not BAND[0] <= e <= BAND[1] else ''}" if e is not None and np.isfinite(e) else ""))


for f in CAR:
    r = R[f]; d = r["dir"]
    P(f"\n   {f} {NAMES[f]} - frozen direction: {dirword(r)}{tags(f, r)}")
    P("    population:")
    for y in (2017, 2018, 2019, 2020):
        P(line(f"year {y} (own thirds)" + (" [few delisted names on file]" if y < 2019 else ""), r["years"][y], ratio(r["years"][y]), d))
    sub = [("first breaks (after 10 quiet sessions)", (D.first10 == True).to_numpy()), ("later breaks", (D.first10 == False).to_numpy()),      # noqa: E712
           ("first break after 60 quiet sessions", (D.first60 == True).to_numpy()), ("common stock only", (D.sectype == "CS").to_numpy()),      # noqa: E712
           ("price >= $5", (D.f02 >= 5).to_numpy()), (f"embargoed discovery (E <= {EMBARGO})", (D.E <= EMBARGO).to_numpy()),
           ("2019-20 alone", EY >= 2019), ("full 60-session windows only", (O1.full_window == 1).to_numpy()),
           ("QQQ above its 50-day at D", (O1.qqq_above50 == 1).to_numpy()), ("QQQ below its 50-day at D", (O1.qqq_above50 == 0).to_numpy())]
    if f not in ("f24a", "f24b"):
        sub += [("gapped over the level at the open", gapA), ("did not gap over the level", gapB)]
    for lab, m in sub:
        c, rt, e = pop_ratio(LD, big, f, m, f)
        P(line(lab, c, rt, d, e))
    c, rt, e = pop_ratio(LD2, Y2["big"], f, None, f)
    P(line("second seed (2411) of the keep rule", c, rt, d, e))
    P("    outcome:")
    for lab, k in (("monster tier (>= 2.0x)", "monster"), ("clean winners", "clean"), ("ADR-scaled tail", "adr_tail"), ("un-truncated window", "big_untrunc"),
                   ("from max(level, high of E)", "big_fromhigh"), ("E+1 .. E+60 (E's close excluded)", "big_e1")):
        c = counts(Y[k], TM[f]); P(line(lab, c, ratio(c) / r["div"], d))
    ca = counts(big, TADR[f]); da = f20_div("adr") if f == "f20" else 1.0
    P(line("ADR-neutral (thirds inside ADR20 strata)", ca, ratio(ca) / da, d))
    for lab, k in (("window 30 sessions (-50%)", "big_w30"), ("window 90 sessions (+50%)", "big_w90")):
        c = counts(Y[k], TM[f]); rt = ratio(c) / r["div"]
        frag = (not np.isfinite(rt)) or rt <= 0 or (rt ** d) < 1.2
        P(line(lab, c, rt, d) + ("  -> FRAGILE" if frag else ""))
    P("    conditioning (the FEATURE's ratio only):")
    for nm, key, tt in (("B4", "b4t", TB4[f]), ("B1 (pick-score)", "b1t", LD.thirds(f, strata="b1t"))):
        for k_, lab in ((0, "bottom"), (1, "middle"), (2, "top")):
            m = (D[key] == k_).to_numpy()
            c = counts(big, tt, m)
            P(line(f"within the {lab} {nm} third", c, ratio(c), d, (LD.expected(tt, m) if f == "f20" else None)))
if not CAR:
    P("   none carried - no extra reading to print.")

P(f"\n## END OF DISCOVERY{' [SYNTHETIC - not a result]' if SYN else ''} | {time.time() - t0:.0f}s")
(HERE / ("3_discovery_SYNTHETIC.txt" if SYN else "3_discovery.txt")).write_text("\n".join(LOG) + "\n")
if not SYN:
    import json
    json.dump(dict(rate_1719=float(r1719), rate_pooled=float(rall), rate_2020=float(r2020), row_54=near, n=N, winners=int(big.sum()), monsters=nmon,
                   carried=[dict(f=f, direction=dirword(R[f]), ratio=R[f]["judged"], p=R[f]["p"], ex2020=R[f]["ex_r"], b4=R[f]["b4_r"], tag_b4=R[f]["tag_b4"], qm_share=R[f]["qm_share"]) for f in CAR],
                   carried_alt=CAR_alt, pass13=PASS13, top4=TOP4, group_winners=WIN,
                   features={f: dict(ratio=R[f]["judged"], raw=R[f]["raw"], p=R[f]["p"], ex2020=R[f]["ex_r"], b4=R[f]["b4_r"], z=R[f]["zc"]["z"], c1=R[f]["c1"], c2=R[f]["c2"], c3=R[f]["c3"],
                                     gw=R[f]["gw"], in4=R[f]["in4"], carried=R[f]["carried"]) for f in CAND}),
              open(HERE / "3_result.json", "w"), indent=1)
