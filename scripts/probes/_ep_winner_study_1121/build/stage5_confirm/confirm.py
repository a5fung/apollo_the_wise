#!/usr/bin/env python3
"""EP big-winner chart study — STAGE 5: THE ONE CONFIRM RUN (prereg docs/analysis/ep_winner_study_prereg_2026-11-21.md §6 step 8;
§5.1, §5.3, §5.5, §5.6, §10 amendments, §11 — where §11 conflicts with earlier text, §11 wins).

RUN ONCE. Every line of output is BUFFERED and written to confirm.txt only when the whole computation has finished, so a crash
anywhere is a crash before any outcome is printed. A real run refuses to start when confirm.txt already exists.

  python3 confirm.py                      THE REAL RUN (once)
  python3 confirm.py --synthetic --out=X  same code path on coin-toss labels for BOTH sets: NO forward bar is read, the stage-3
                                          outcome file is NOT opened, the B1 / discovery reproduction gates are skipped.
  python3 confirm.py --synthetic --real-disc --out=X   as above, but DISCOVERY labels are stage 3's already-seen outcomes file, so
                                          gate C13 (this script's statistics reproduce stage 3) can be tested without a forward read.

FORWARD READ (real mode): bars E..E+60 of every one of the 4,665 events, per era, never stitched; era-B rows after 2024-12-31 were
dropped at read by stage 1's loader and that is re-asserted here on every era-B series (#710). Discovery outcomes are recomputed
and must equal stage3/discovery_outcomes.tsv.gz before anything else is derived.
NOT opened: scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz, run.txt. NOT imported: stage3/discovery.py,
stage4_freeze/02_preconfirm_n.py (both run at module level) — their statistic / layout code is COPIED below.
"""
from __future__ import annotations

import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STAGE1 = HERE.parent / "stage1"
STAGE3 = HERE.parent / "stage3"
STAGE4 = HERE.parent / "stage4_freeze"
sys.path.insert(0, str(STAGE1))
import common as C      # noqa: E402  (outcome-free: paths, calendars, sha)
import features as F    # noqa: E402  (the stage-1 feature code; used for the §5.5 window +/-50% reading on DISCOVERY only)
import stats as S       # noqa: E402  (the SAME thirds / two-group assignment code as stages 1, 3, 4)

SYN = "--synthetic" in sys.argv
REALDISC = "--real-disc" in sys.argv          # synthetic variant: discovery labels = stage 3's SEEN outcomes (to test gate C13); confirm stays coin-toss
assert SYN or not REALDISC
SYN_RATE = 0.105
OUT_PATH = HERE / "confirm.txt"
for a in sys.argv[1:]:
    if a.startswith("--out="):
        OUT_PATH = Path(a[6:])
    if a.startswith("--rate="):
        SYN_RATE = float(a[7:])
if SYN:
    assert OUT_PATH != HERE / "confirm.txt", "synthetic mode must not write confirm.txt"
else:
    assert OUT_PATH == HERE / "confirm.txt"
    if OUT_PATH.exists():
        sys.exit("confirm.txt already exists — the confirm run is ONE run (prereg §5.3). Refusing to run again.")

NS, NBOOT, FWD = 10_000, 2_000, 60
BIG, MON, ADRK, FAILPOOL = 1.5, 2.0, 8.0, 1.10
PREREG_PREFIX = "6c581b6a"
FT_SHA = "ade1d7802eaf70aa60a9b5514d79b72084876d9601b0999328c9b1aad0cf0de7"
HR_SHA = "0b995389a41fc462e5ca81b3d7ce38247cd42f36dd754e1edd7c44d3110d79f7"
CN_SHA = "a7ebd5cd401c6ce3cd53dea5b3720e1e4c78b3d4133ca477c9789fcb43a95be4"
D3_SHA = "2bd0b0d315dbc7491945d0f0aa1727668cd0a618cea1d747bd39b9975b70fae1"
DO_SHA = "033b7facbcb085009b8fcc08e19fe92dec238223bd0018aa6548f5a3db115680"
CARRIED = {"f02": -1, "f03": +1, "f09": +1, "f18": -1}       # stage3/discovery.txt "CARRIED LIST (direction frozen)"
FAMILY = ["f02", "f03", "f09", "f18", "combo", "H1", "H2", "H3", "H4"]           # prereg §11.2: exactly 9
DIR = {"f02": -1, "f03": +1, "f09": +1, "f18": -1, "combo": +1, "H1": -1, "H2": -1, "H3": +1, "H4": +1}
TWO = {"H1", "H2", "H3"}
NAMES = {"f02": "gap size in daily ranges", "f03": "short run-up (20)", "f09": "base depth (40)", "f18": "price (raw)",
         "combo": "combination f02+f03+f09+f18", "H1": "below the 200-day at the open", "H2": "in a downtrend",
         "H3": "above all moving averages at open", "H4": "ADR20 (= B2)"}
DIRN = {"f02": "LOW third wins", "f03": "HIGH third wins", "f09": "HIGH third wins", "f18": "LOW third wins", "combo": "HIGH third wins",
        "H1": "NO wins", "H2": "NO wins", "H3": "YES wins", "H4": "HIGH third wins"}
# B1 pooled reproduction target — prereg §4.1 "B1" + RESULT 8 (docs/analysis/ep_rank_v2_prereg_2026-11-03.md): hardcoded BEFORE the run
B1_EXPECT = dict(n=3671, months=87, bottom="0.096", middle="0.113", top="0.129", ratio=1.355, era_A="1.48", era_B="1.08")

LINES: list[str] = []


def P(s=""):
    LINES.append(s)


def write_out():
    OUT_PATH.write_text("\n".join(LINES) + "\n")


def stop(msg):
    P(f"\n*** STOP: {msg}")
    write_out()
    print(f"STOP: {msg}  (see {OUT_PATH})")
    sys.exit(3)


# ════════════════════════════════════════ outcome-free header, asserts, layout ════════════════════════════════════════
pre_sha = C.sha(C.PREREG)
if not pre_sha.startswith(PREREG_PREFIX):
    sys.exit(f"STOP: prereg sha256 {pre_sha} does not begin {PREREG_PREFIX} — nothing run")
P("# STAGE 5 — THE ONE CONFIRM RUN (E >= 2021-01-01)" + ("   [SYNTHETIC MODE: coin-toss labels on BOTH sets, NO forward bar read — NOT a result]" if SYN else ""))
P(f"prereg sha256 {pre_sha} (ASSERT begins {PREREG_PREFIX}: OK — the frozen document of commit 3e6396c7)")
assert C.sha(STAGE1 / "feature_table.tsv.gz") == FT_SHA and C.sha(STAGE4 / "h_reads.tsv.gz") == HR_SHA and C.sha(STAGE4 / "confirm_n.tsv") == CN_SHA
assert C.sha(STAGE3 / "discovery.txt") == D3_SHA
P(f"inputs: feature_table.tsv.gz {FT_SHA[:8]}… · h_reads.tsv.gz {HR_SHA[:8]}… · confirm_n.tsv {CN_SHA[:8]}… · stage3/discovery.txt {D3_SHA[:8]}… (ASSERT OK)")
P(f"code sha256: this script {C.sha(__file__)} | stage1 stats.py {C.sha(STAGE1 / 'stats.py')} | common.py {C.sha(STAGE1 / 'common.py')} | features.py {C.sha(STAGE1 / 'features.py')}")
d3 = (STAGE3 / "discovery.txt").read_text()
for f, s in CARRIED.items():
    assert f"VERDICT: {f} " in d3 and f"CARRIED to confirm, direction frozen: {'HIGH' if s > 0 else 'LOW'} third wins" in d3.split(f"VERDICT: {f} ")[1].split("\n")[0], f
assert "-> the four: ['f09', 'f02', 'f18', 'f03']" in d3
assert "of f02 (1 - rank), f03 (as is), f09 (as is), f18 (1 - rank); direction fixed: HIGH third wins" in d3
P("carried list, directions and the combination definition equal stage3/discovery.txt (ASSERT OK)")

P("""
## APPLIED READINGS (fixed here, BEFORE any confirm outcome is computed)
 C1  Layout = stage1/stats.py (imported) used exactly as stage4_freeze/02_preconfirm_n.py (copied): thirds within (era, month) with
     >= 6 scored events, mid-rank ties; H1-H3 two-group = months with >= 6 scored and >= 2 of each. Asserted equal to every row of
     stage4_freeze/confirm_n.tsv before any bar is loaded.
 C2  THE RATIO, in the frozen direction (>= 1.2 = the frozen direction wins): thirds members = smoothed rates (winners + 0.5) /
     (n + 1) (§5.1, stage 3's R2), winning third / losing third (f02, f18: bottom / top; f03, f09, combo, H4: top / bottom); the raw
     ratio is printed beside it. H1-H3 = Mantel-Haenszel ratio by (era, month) (A1; §11.1): H1, H2 rate(no) / rate(yes), H3
     rate(yes) / rate(no). The §5.3 bars (1.2, 1.0) are judged on this ratio.
 C3  Permutation (§5.1): U = np.random.default_rng(1121).random((10000, 2251)); row = shuffle, column = confirm event in the fixed
     order (era, E, ticker). Within each (era, month) the events assigned on the member are sorted by key; the k-th event in key
     order receives the label of the k-th event in fixed order (stage 3's R4). One-sided p = (1 + #(d x permuted log ratio >=
     d x observed log ratio)) / 10001, d = the frozen direction.
 C4  Holm over the family of 9 (§11.2): p sorted ascending p(1..9); adjusted p(i) = max over j <= i of min(1, (9 - j + 1) x p(j)).
 C5  Per era: the same ratio restricted to era-A events / era-B events (MH over that era's months). "Same direction in both" =
     both ratios > 1.0; an undefined per-era ratio counts as NOT the same direction. A qualifier only (§5.3).
 C6  90% interval: (era, month) blocks resampled with replacement, 2,000 draws, a fresh default_rng(1121) per member (stage 3's
     R7); for a LOW / NO member the draws are inverted before the 5th-95th percentiles are taken.
 C7  ADR-neutral (§2): ADR20 third = thirds of the table's adr20_raw within (era, quarter) over ALL confirm events; the member's
     thirds within (era, quarter, ADR third), strata with >= 9 scored events; H1-H3: Mantel-Haenszel over those strata (>= 9 scored
     and >= 2 of each; stage 3's R3). H4: printed n/a (§11.3).
 C8  Tag "— a volatility proxy" (§2) = the confirm ADR-neutral ratio under 1.2 OR the confirm ADR-scaled-tail ratio under 1.10,
     both as C2 in the frozen direction. Not applied to H4. Per §11.3 it is a DESCRIPTION, NOT a negative verdict: it changes no
     verdict word.
 C9  §5.5 extra readings are description; NONE is a bar. Per year / common stock / untyped / one-per-identity / gap >= 10% are
     MASKS over the member's main (era, month) layout (thirds are not re-formed), the way stage 3 read ex-2020 and per-year.
     One event per identity per 60 sessions: identity = stage 1's identity_alt (A2); events of ALL 4,665 (discovery included, §3 b)
     are walked in (E, era, ticker) order and an event is kept when no KEPT event of the same identity lies within the 60 sessions
     before it (sessions counted on the union of the two era calendars); the reading uses the kept confirm events.
     Within shelf-distance thirds: dmin third = thirds of B1 within (era, quarter) over confirm events scored on B1; the member's
     thirds (or yes / no) within (era, quarter, dmin third), strata >= 9; pooled, and per dmin third.
     Feature 12 within vr20_mean halves: applies to no family member (f12 was not carried) -> n/a.
     Window length +/-50%, DISCOVERY only: every window scaled by 0.5 and 1.5 (n -> int(n x s + 0.5)). f03, f09 through
     stage1/features.py WINDOW_SCALE; f02 = gap % / ADR over the scaled 20-session window (10, 30); H4 = that scaled ADR; f18 has
     no window (n/a); combination = its members at the same scale; H1-H3 = a scaled copy of stage4_freeze/hreads.py (200 -> 100 /
     300, the 20-session lag -> 10 / 30, SMA50 -> 25 / 75, EMA10 / EMA21 -> 5 / 11 and 15 / 32), asserted to reproduce the frozen
     H1-H3 at scale 1.0. "fragile" = the discovery ratio in the frozen direction under 1.2 (a flip is under 1.0) at either scale.
 C10 B1 (shelf distance) pooled reproduction (§4.1, §6 step 8): thirds of B1 within (era, month) >= 6 scored, PRE-REG 6's ticker
     tie-break (midrank=False), over ALL 4,665 events (discovery + confirm = RESULT 8's set). HARD GATE, checked before any family
     number is derived or written: bottom 0.096, top 0.129, ratio within 0.005 of 1.355 ("12.9% vs 9.6% = 1.36x"). A miss stops
     the run with only the B1 lines written. Scored n 3,671, 87 months, middle 0.113, era A 1.48, era B 1.08 are printed MATCH /
     MISS beside it (RESULT 8's text; not the prereg's assert). RESULT 8's p is not recomputed (its shuffle convention differs).
 C11 Outcome window (stage 3's R8): bars with the event's OWN era calendar index in [ci(E), ci(E)+60]; big winner = max close >=
     1.5 x open(E); monster >= 2.0 x; ADR tail >= open(E) x (1 + 8 x ADR20 / 100), ADR20 = adr20_raw; no survivorship drop.
     GATE: the discovery outcomes recomputed here must equal stage3/discovery_outcomes.tsv.gz on all 2,414 events.
 C12 H1-H3 discovery ratios are printed last as description, labelled "seen" (§5.7, §11.1); H4's discovery reading is stage 3's B2
     block (5.78x), not recomputed.
 C13 GATE — this script's copies of stage 3's statistics must reproduce stage3/discovery.txt on the (seen) discovery outcomes before
     any family number is derived: f03 ratio 2.430, two-sided p 0.0001, interval 1.99-3.00; f02 ratio 0.355, interval 0.26-0.49 and
     its inverse under the LOW orientation; f01 ratio 1.321, p 0.0224; f09 ratio 5.443; f16 (two-group) MH 1.540, p 0.0080, interval
     1.14-2.02; the x1.0 rows of the window reading f03 2.430, f09 5.443. A miss stops the run with no confirm number written.
 C14 GUARD on C2: §5.1 read literally smooths only when a third holds zero winners. The verdict word is therefore ALSO computed
     on the raw ratio (thirds members; for H1-H3 the MH ratio is the only ratio). If the two words differ for any member, both
     are printed and flagged as a frozen-rule ambiguity for the caller — neither is picked silently.""")

T = pd.read_csv(STAGE1 / "feature_table.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "E": str, "year": str})
Hh = pd.read_csv(STAGE4 / "h_reads.tsv.gz", sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "E": str, "year": str})
POP = pd.read_csv(STAGE1 / "population.tsv", sep="\t", keep_default_na=False, dtype={"ticker": str, "E": str})
assert len(T) == len(Hh) == len(POP) == 4665
for X in (Hh, POP):
    assert (T.ticker.to_numpy() == X.ticker.to_numpy()).all() and (T.E.to_numpy() == X.E.to_numpy()).all() and (T.era.to_numpy() == X.era.to_numpy()).all()
assert list(zip(T.era, T.E, T.ticker)) == sorted(zip(T.era, T.E, T.ticker)), "fixed order (era, E, ticker)"
assert T[T.era == "B"].E.max() <= "2024-09-30" and T.E.max() <= C.CUT_B
for h in ("H1", "H2", "H3", "H4"):
    T[h] = Hh[h].to_numpy()
    T[h + "_null"] = Hh[h + "_null"].to_numpy()
assert np.allclose(T.H4.dropna(), T.B2.dropna()) and (T.H4.notna() == T.B2.notna()).all()
T["sectype"] = T.sectype.fillna("")
NALL = len(T)
IS_CONF = (T.set == "CONF").to_numpy()
IS_DISC = ~IS_CONF
assert int(IS_DISC.sum()) == 2414 and (T.E[IS_DISC] <= C.DISC_LAST).all() and (T.E[IS_CONF] >= "2021-01-01").all()


class Ctx:
    """one event set (confirm / discovery / all) with the layout helpers of stage 3 / stage 4."""

    def __init__(self, df):
        self.df = df.reset_index(drop=True)
        self.N = len(self.df)
        self.U_MONTH = pd.factorize(self.df.era + self.df.month)[0]
        self.eraA = (self.df.era == "A").to_numpy()
        self.year = self.df.year.to_numpy()

    def g2(self, col):
        return np.where(self.df[col].isna(), -1, self.df[col].fillna(0)).astype(int)

    def month_layout(self, col, two, midrank=True):
        if two:
            return S.assign_two(self.df, self.g2(col), ["era", "month"], min_n=S.MIN_MONTH)
        return S.assign_thirds(self.df, col, ["era", "month"], S.MIN_MONTH, midrank)

    def strata(self, base_col):
        """thirds of base_col within (era, quarter) over the events scored on it; unit ids of (era, quarter, third)."""
        third = S.assign_thirds(self.df, base_col, ["era", "quarter"], 1, midrank=True)
        self.df["_st_" + base_col] = third
        unit = pd.factorize(self.df.era + self.df.quarter + "|" + pd.Series(third).astype(str))[0]
        return third, unit

    def strata_layout(self, col, two, base_col, third):
        key = "_st_" + base_col
        if two:
            g = np.where(third >= 0, self.g2(col), -1)
            return S.assign_two(self.df, g, ["era", "quarter", key], min_n=S.MIN_STRATUM)
        Dd = self.df.copy()
        Dd.loc[third < 0, col] = np.nan
        return S.assign_thirds(Dd, col, ["era", "quarter", key], S.MIN_STRATUM, True)


def add_combo(df, cols=None):
    """§5.6 on this frame — the discovery definition (02_preconfirm_n.py, copied)."""
    cols = cols or {f: f for f in CARRIED}
    mask = np.ones(len(df), bool)
    for f in CARRIED:
        mask &= df[cols[f]].notna().to_numpy()
    acc = np.zeros(len(df))
    for f, s in CARRIED.items():
        pr = S.pct_rank_within(df, cols[f], ["era", "month"], mask)
        acc += pr if s > 0 else (1.0 - pr)
    return np.where(mask, acc / len(CARRIED), np.nan)


CF = Ctx(T[IS_CONF])
N = CF.N
assert N == 2251 and int(CF.eraA.sum()) == 867 and int((~CF.eraA).sum()) == 1384
CF.df["combo"] = add_combo(CF.df)
LAY = {r: CF.month_layout(r, r in TWO) for r in FAMILY}

# ---- population and n per row == stage4_freeze/confirm_n.tsv
CN = pd.read_csv(STAGE4 / "confirm_n.tsv", sep="\t")
P(f"\n## POPULATION (outcome-free): study population {NALL} events · DISCOVERY {int(IS_DISC.sum())} (E <= 2020-12-31, era A) · CONFIRM {N} (era A {int(CF.eraA.sum())}, E {CF.df.E[CF.eraA].min()}..{CF.df.E[CF.eraA].max()}"
  f" · era B {int((~CF.eraA).sum())}, E {CF.df.E[~CF.eraA].min()}..{CF.df.E[~CF.eraA].max()})")
P("## CONFIRM n per row — must equal stage4_freeze/confirm_n.tsv (low / high = bottom / top third, or yes / no for H1-H3)")
P(f"   {'':6}{'name':36} {'era':>6} {'events':>7} {'scored':>7} {'months':>7} {'in test':>8} {'bottom|yes':>11} {'middle':>7} {'top|no':>7}")
k = 0
for r in FAMILY:
    t = LAY[r]
    if r in TWO:
        lo, hi, mid = (t == 2), (t == 0), np.zeros(N, bool)
    else:
        lo, hi, mid = (t == 0), (t == 2), (t == 1)
    for era in ("A", "B", "A+B"):
        m = np.ones(N, bool) if era == "A+B" else (CF.df.era == era).to_numpy()
        it = m & (t >= 0)
        row = (r, era, int(m.sum()), int((m & CF.df[r].notna().to_numpy()).sum()), len(set(zip(CF.df.era[it], CF.df.month[it]))), int(it.sum()),
               int((m & lo).sum()), int((m & mid).sum()), int((m & hi).sum()))
        exp = tuple(CN.iloc[k])
        assert row[:2] == exp[:2] and tuple(int(x) for x in exp[2:]) == row[2:], (row, exp)
        k += 1
        P(f"   {r:6}{NAMES[r]:36} {era:>6} {row[2]:7d} {row[3]:7d} {row[4]:7d} {row[5]:8d} {row[6]:11d} {('-' if r in TWO else str(row[7])):>7} {row[8]:7d}")
assert k == len(CN) == 27
P("   ASSERT OK: all 27 rows (9 members x era A / B / A+B) equal stage4_freeze/confirm_n.tsv.")
P("   tags that could apply: 'shelf relative — confirm partly seen' applies to no family member (shelf relatives = f05, f07, neither carried);"
  " 'era-B population thinned of later reverse-splitters' is NOT triggered (stage 1 D2: 0 excluded days vs the trigger of 20).")

# ---- outcome-free strata, masks
ADR3, U_ADR = CF.strata("adr20_raw")
assert (ADR3 >= 0).all()
DM3, U_DMIN = CF.strata("B1")
LAY_ADR = {r: (None if r == "H4" else CF.strata_layout(r, r in TWO, "adr20_raw", ADR3)) for r in FAMILY}
LAY_DM = {r: CF.strata_layout(r, r in TWO, "B1", DM3) for r in FAMILY}

IDM = pd.read_csv(STAGE1 / "identity_map_event_tickers.tsv", sep="\t", dtype=str, keep_default_na=False)
idmap = {(e, t): i for e, t, i in zip(IDM.era, IDM.ticker, IDM.identity_alt)}
ident = np.array([idmap[(e, t)] for e, t in zip(T.era, T.ticker)])
cal = C.calendars()
union = np.array(sorted(set(cal["A"].tolist()) | set(cal["B"].tolist())), dtype="U10")
ui = np.searchsorted(union, T.E.to_numpy(dtype="U10"))
assert (union[ui] == T.E.to_numpy(dtype="U10")).all()
keep1 = np.zeros(NALL, bool)
last = {}
for kk in np.lexsort((T.ticker.to_numpy(), T.era.to_numpy(), T.E.to_numpy())):
    i = ident[kk]
    if i not in last or ui[kk] - last[i] > 60:
        keep1[kk] = True
        last[i] = ui[kk]
M_ONE = keep1[IS_CONF]
M_CS = (CF.df.sectype == "CS").to_numpy()
M_UNT = (CF.df.sectype == "").to_numpy()
M_GAP10 = (CF.df.f01 >= 0.10).to_numpy()
P(f"   §5.5 masks (outcome-free, confirm events): common stock {int(M_CS.sum())} · untyped {int(M_UNT.sum())} (ADR {int((CF.df.sectype == 'ADRC').sum())}) · one event per identity per 60 sessions {int(M_ONE.sum())}"
  f" (of all 4,665: {int(keep1.sum())} kept) · gap >= 10% {int(M_GAP10.sum())} · scored on shelf distance {int((DM3 >= 0).sum())}")

# ---- §5.5 window +/-50% on DISCOVERY: the scaled feature values (outcome-free; bars < E + open(E) only)
DC = Ctx(T[IS_DISC])
ND = DC.N
POPD = POP[IS_DISC].reset_index(drop=True)
bars_all = pickle.load(open(STAGE1 / "cache" / "bars_event_tickers.pkl", "rb"))
for (era_, t_), b in bars_all.items():
    if era_ == "B":
        assert b[0][-1] <= C.CUT_B, (t_, b[0][-1])               # SEALED (#710): no era-B bar after 2024-12-31 is in the store
flags = C.load_flags()
breaks = C.load_breaks()


def sc(n, s):
    return max(1, int(n * s + 0.5))


def _has_date_in(dates_sorted, lo, hi):
    import bisect
    if not dates_sorted:
        return False
    kx = bisect.bisect_left(dates_sorted, lo)
    return kx < len(dates_sorted) and dates_sorted[kx] <= hi


def ema_last(x, n):
    a = 2.0 / (n + 1.0)
    e = float(x[0])
    for kx in range(1, len(x)):
        e = a * float(x[kx]) + (1.0 - a) * e
    return e


def h_scaled(E, series, calx, flag_dates, break_dates, s):
    """stage4_freeze/hreads.py::h_features COPIED with every window scaled by s (+ the ADR over the scaled 20-session window)."""
    d_all, ci_all, o_all, h_all, l_all, c_all, v_all = series
    ciE = int(np.searchsorted(calx, E))
    assert calx[ciE] == E
    i = int(np.searchsorted(ci_all, ciE))
    assert ci_all[i] == ciE
    oE = float(o_all[i])
    d, ci, o, h, l, c = d_all[:i], ci_all[:i], o_all[:i], h_all[:i], l_all[:i], c_all[:i]          # THE CUT: nothing dated E or later
    assert len(ci) and ci[-1] == ciE - 1 and d[-1] < E
    first_ci = int(ci[0])
    N200, L, N50, n10, n21, nA = sc(200, s), sc(20, s), sc(50, s), sc(10, s), sc(21, s), sc(20, s)
    out = {}

    def idx(a_off, b_off):
        return int(np.searchsorted(ci, ciE - a_off)), int(np.searchsorted(ci, ciE - b_off, side="right"))

    def rules(n, subwindows):
        if ciE - n < 0 or first_ci > ciE - n:
            return "history"
        for a_off, b_off in subwindows:
            a, b = idx(a_off, b_off)
            if (b - a) / (a_off - b_off + 1) < 0.90:
                return "coverage"
        lo_date, hi_date = str(calx[ciE - n]), str(calx[ciE - 1])
        if _has_date_in(flag_dates, lo_date, hi_date):
            return "adjustment"
        if _has_date_in(break_dates, lo_date, hi_date):
            return "identity"
        a = int(np.searchsorted(ci, ciE - n))
        blk = np.concatenate([o[a:], h[a:], l[a:], c[a:]])
        if not (np.isfinite(blk).all() and (blk > 0).all()) or not (np.isfinite(oE) and oE > 0):
            return "bad_price"
        return None

    if rules(N200, [(N200, 1)]) is None:
        a, b = idx(N200, 1)
        w = c[a:b]
        sma200 = float(np.mean(w))
        a50, b50 = idx(N50, 1)
        sma50 = float(np.mean(c[a50:b50]))
        e10, e21 = ema_last(w, n10), ema_last(w, n21)
        out["H1"] = 1.0 if oE < sma200 else 0.0
        out["H3"] = 1.0 if oE > max(e10, e21, sma50, sma200) else 0.0
        if rules(N200 + L, [(N200, 1), (N200 + L, L + 1)]) is None:
            a, b = idx(N200 + L, L + 1)
            sma200_lag = float(np.mean(c[a:b]))
            out["H2"] = 1.0 if (oE < sma200 and sma200 < sma200_lag) else 0.0
    if rules(nA, [(nA, 1)]) is None:
        a, b = idx(nA, 1)
        out["ADR"] = float(np.mean((h[a:b] - l[a:b]) / c[a:b] * 100.0))
    return out


SCALED = {}
for s in (1.0, 0.5, 1.5):
    F.WINDOW_SCALE = s
    cols = {x: np.full(ND, np.nan) for x in ("f03", "f09", "H1", "H2", "H3", "ADR")}
    for kk in range(ND):
        r = POPD.iloc[kk]
        assert r.E <= C.DISC_LAST and r.era == "A"
        ser = bars_all[("A", r.ticker)]
        fl, br = flags["A"].get(r.ticker, []), breaks["A"].get(r.ticker, [])
        vals, _ = F.event_features("A", r.ticker, r.E, ser, bars_all[("A", "SPY")], cal["A"], fl, br, float(r.prev_close_raw), float(r.med_dv20))
        for x in ("f03", "f09"):
            if x in vals:
                cols[x][kk] = vals[x]
        for x, v in h_scaled(r.E, ser, cal["A"], fl, br, s).items():
            cols[x][kk] = v
    SCALED[s] = cols
F.WINDOW_SCALE = 1.0
b0 = SCALED[1.0]
for x in ("f03", "f09", "H1", "H2", "H3"):                         # scale 1.0 must reproduce the frozen tables
    ref = DC.df[x].to_numpy(dtype=float)
    assert (np.isnan(ref) == np.isnan(b0[x])).all() and np.allclose(ref[~np.isnan(ref)], b0[x][~np.isnan(ref)], rtol=1e-9, atol=1e-12), x
both = ~np.isnan(b0["ADR"]) & DC.df.B2.notna().to_numpy()
assert np.allclose(b0["ADR"][both], DC.df.B2.to_numpy()[both], rtol=1e-9)
adr_nullpattern_diff = int((np.isnan(b0["ADR"]) != DC.df.B2.isna().to_numpy()).sum())
P(f"   §5.5 window +/-50% (outcome-free build, DISCOVERY events only): at scale 1.0 the scaled code reproduces the frozen f03, f09, H1, H2, H3 on all {ND} discovery events"
  f" (values and NULL pattern) and ADR20 on the {int(both.sum())} events scored by both (ASSERT OK; NULL pattern differs on {adr_nullpattern_diff} events — the scaled ADR adds hreads' bad_price rule).")
DLAY_S = {}
for s in (1.0, 0.5, 1.5):
    cs = SCALED[s]
    df = DC.df
    df[f"f03@{s}"] = cs["f03"]; df[f"f09@{s}"] = cs["f09"]; df[f"H4@{s}"] = cs["ADR"]
    df[f"f02@{s}"] = np.where(cs["ADR"] > 0, df.f01 * 100.0 / cs["ADR"], np.nan)
    df[f"combo@{s}"] = add_combo(df, {"f02": f"f02@{s}", "f03": f"f03@{s}", "f09": f"f09@{s}", "f18": "f18"})
    for x in ("H1", "H2", "H3"):
        df[f"{x}@{s}"] = cs[x]
    DLAY_S[s] = {r: (None if r == "f18" else DC.month_layout(f"{r}@{s}", r in TWO)) for r in FAMILY}
DLAY = {r: DC.month_layout(r, r in TWO) for r in ("H1", "H2", "H3")}

AL = Ctx(T)
B1_T = AL.month_layout("B1", False, midrank=False)
B1C_T = AL.month_layout("B1clean", False, midrank=False)
P("   every layout above was formed before any outcome was computed.")

# ════════════════════════════════════════ OUTCOMES ════════════════════════════════════════
big = np.zeros(NALL); monster = np.zeros(NALL); adrt = np.full(NALL, np.nan); fail5 = np.full(NALL, np.nan); ret60 = np.full(NALL, np.nan)
failpool = np.zeros(NALL); maxc = np.zeros(NALL); nbars = np.zeros(NALL, int)
if SYN:
    rng = np.random.default_rng(7)
    rate = np.full(NALL, SYN_RATE)
    t3 = np.full(NALL, -1); t3[IS_CONF] = LAY["f03"]; rate = rate * np.where(t3 == 2, 4 / 3, np.where(t3 == 0, 2 / 3, 1.0))        # planted 2.0x on f03
    th = np.full(NALL, -1); th[IS_CONF] = LAY["H3"]; rate = rate * np.where(th == 2, 1.3, 1.0)
    big = (rng.random(NALL) < rate).astype(float)
    monster = big * (rng.random(NALL) < 0.3)
    adrt = (rng.random(NALL) < 0.2).astype(float)
    fail5 = (rng.random(NALL) < 0.5).astype(float); ret60 = rng.normal(0, 0.3, NALL); failpool = (rng.random(NALL) < 0.4).astype(float)
    maxc = 1 + rng.random(NALL); nbars = np.full(NALL, 61)
    if REALDISC:
        DO = pd.read_csv(STAGE3 / "discovery_outcomes.tsv.gz", sep="\t", dtype={"ticker": str, "E": str})
        assert (DO.ticker.to_numpy() == T.ticker[IS_DISC].to_numpy()).all() and (DO.E.to_numpy() == T.E[IS_DISC].to_numpy()).all()
        big[IS_DISC] = DO.big_winner.to_numpy(); monster[IS_DISC] = DO.monster.to_numpy(); adrt[IS_DISC] = DO.adr_tail.to_numpy(dtype=float)
else:
    adr_all = T.adr20_raw.to_numpy(dtype=float)
    for kk in range(NALL):
        era, t, E = T.era.iat[kk], T.ticker.iat[kk], T.E.iat[kk]
        d, ci, o, _h, _l, c, _v = bars_all[(era, t)]                    # the event's OWN era file only — never stitched
        calx = cal[era]
        iE = int(np.searchsorted(calx, E)); assert calx[iE] == E and iE == int(POP.iE.iat[kk])
        assert iE + FWD <= len(calx) - 1, (era, t, E)
        i = int(np.searchsorted(ci, iE)); assert ci[i] == iE and d[i] == E
        oE = float(o[i])
        assert abs(oE - float(POP.open.iat[kk])) <= 1e-5 * abs(oE) + 1e-6, (t, E)
        j = int(np.searchsorted(ci, iE + FWD, side="right"))
        assert j > i and ci[j - 1] <= iE + FWD
        if era == "B":
            assert d[j - 1] <= C.CUT_B
        w = c[i:j]; wci = ci[i:j]
        mx = float(w.max())
        maxc[kk] = mx / oE; nbars[kk] = j - i
        big[kk] = 1.0 if mx >= BIG * oE else 0.0
        monster[kk] = 1.0 if mx >= MON * oE else 0.0
        failpool[kk] = 1.0 if mx < FAILPOOL * oE else 0.0
        if np.isfinite(adr_all[kk]) and adr_all[kk] > 0:
            adrt[kk] = 1.0 if mx >= oE * (1 + ADRK * adr_all[kk] / 100.0) else 0.0
        p5 = np.flatnonzero(wci == iE + 5); p60 = np.flatnonzero(wci == iE + FWD)
        if len(p5):
            fail5[kk] = 1.0 if w[p5[0]] < oE else 0.0
        if len(p60):
            ret60[kk] = w[p60[0]] / oE - 1.0
    # GATE (C11): discovery outcomes equal stage 3's
    assert C.sha(STAGE3 / "discovery_outcomes.tsv.gz") == DO_SHA
    DO = pd.read_csv(STAGE3 / "discovery_outcomes.tsv.gz", sep="\t", dtype={"ticker": str, "E": str})
    assert len(DO) == 2414 and (DO.ticker.to_numpy() == T.ticker[IS_DISC].to_numpy()).all() and (DO.E.to_numpy() == T.E[IS_DISC].to_numpy()).all()
    okd = ((DO.big_winner.to_numpy() == big[IS_DISC]).all() and (DO.monster.to_numpy() == monster[IS_DISC]).all() and (DO.fwd_bars.to_numpy() == nbars[IS_DISC]).all()
           and np.allclose(DO.maxc_ratio.to_numpy(), maxc[IS_DISC], rtol=1e-6) and (DO.fail_pool.to_numpy() == failpool[IS_DISC]).all()
           and np.array_equal(np.nan_to_num(DO.adr_tail.to_numpy(dtype=float), nan=-1), np.nan_to_num(adrt[IS_DISC], nan=-1)))
    if not okd:
        stop("C11 gate: the discovery outcomes recomputed here do not equal stage3/discovery_outcomes.tsv.gz — no confirm number is written")
del bars_all
P("\n" + "=" * 118)
if SYN:
    P(f"## SYNTHETIC LABELS (rate {SYN_RATE}; planted 2.0x on f03, 1.3x on H3 yes). No forward bar read; gates C10 / C11 not enforced.")
else:
    P(f"## OUTCOMES computed for all {NALL} events from each event's own era file (E..E+60, calendar-indexed; no survivorship drop).")
    P(f"   C11 GATE PASSED: the {int(IS_DISC.sum())} discovery outcomes (big winner, monster, ADR tail, failure pool, forward bars, max-close ratio) equal stage3/discovery_outcomes.tsv.gz ({DO_SHA[:8]}…).")
    P(f"   sealed cut (#710): every era-B series in the bar store ends <= {C.CUT_B} (ASSERT OK); latest forward bar read for an era-B event <= {C.CUT_B} (ASSERT OK).")


# ════════════════════════════════════════ statistics (stage 3's, copied) ════════════════════════════════════════
def sm(w, n):
    return (w + 0.5) / (n + 1.0)


def stat(y, t, unit, two, mask=None):
    """top / yes vs bottom / no. thirds: pooled rates (raw) + smoothed log ratio; two-group: Mantel-Haenszel over `unit`."""
    ok = np.isfinite(y) & (t >= 0)
    if mask is not None:
        ok = ok & mask
    top, bot, mid = ok & (t == 2), ok & (t == 0), ok & (t == 1)
    nt, nb, nm = int(top.sum()), int(bot.sum()), int(mid.sum())
    wt, wb, wm = float(y[top].sum()), float(y[bot].sum()), float(y[mid].sum())
    r = dict(nt=nt, nb=nb, nm=nm, wt=wt, wb=wb, wm=wm, rt=wt / nt if nt else np.nan, rb=wb / nb if nb else np.nan, rm=wm / nm if nm else np.nan, two=two)
    if nt and nb:
        r["pooled"] = (r["rt"] / r["rb"]) if wb > 0 else (np.inf if wt > 0 else np.nan)
    else:
        r["pooled"] = np.nan
    if two:
        K = int(unit.max()) + 1
        n1 = np.bincount(unit[top], minlength=K).astype(float); n0 = np.bincount(unit[bot], minlength=K).astype(float)
        a = np.bincount(unit[top], weights=y[top], minlength=K); c = np.bincount(unit[bot], weights=y[bot], minlength=K)
        Nn = n1 + n0
        v = Nn > 0
        num = float((a[v] * n0[v] / Nn[v]).sum()); den = float((c[v] * n1[v] / Nn[v]).sum())
        if num > 0 and den > 0:
            r["raw"] = num / den; r["lr"] = float(np.log(num / den))
        else:
            r["raw"] = np.inf if den <= 0 < num else (0.0 if num <= 0 < den else np.nan); r["lr"] = np.nan
    else:
        r["raw"] = r["pooled"]
        r["lr"] = float(np.log(sm(wt, nt) / sm(wb, nb))) if nt and nb else np.nan
    return r


def perm_lr(ctx, y, t, two, UKEY):
    asg = t >= 0
    if two:
        NUM = np.zeros(NS); DEN = np.zeros(NS)
    else:
        WT = np.zeros(NS); WB = np.zeros(NS)
    for u in np.unique(ctx.U_MONTH[asg]):
        idx = np.flatnonzero(asg & (ctx.U_MONTH == u))            # ascending = fixed order
        wpos = np.flatnonzero(y[idx] == 1)
        if two:
            n1 = int((t[idx] == 2).sum()); n0 = int((t[idx] == 0).sum())
        if len(wpos) == 0:
            continue
        A = np.argsort(UKEY[:, idx], axis=1, kind="stable")[:, wpos]      # events receiving the winner labels
        tt = t[idx][A]
        a = (tt == 2).sum(1); c = (tt == 0).sum(1)
        if two:
            NUM += a * n0 / (n1 + n0); DEN += c * n1 / (n1 + n0)
        else:
            WT += a; WB += c
    with np.errstate(divide="ignore", invalid="ignore"):
        if two:
            return np.log(NUM / DEN)
        return np.log(sm(WT, int((t == 2).sum())) / sm(WB, int((t == 0).sum())))


def boot_ci(ctx, y, t, two, d, seed=C.SEED):
    asg = t >= 0
    us = np.unique(ctx.U_MONTH[asg])
    K = len(us)
    comp = np.zeros((K, 4))
    for kx, u in enumerate(us):
        m = asg & (ctx.U_MONTH == u)
        top, bot = m & (t == 2), m & (t == 0)
        if two:
            n1, n0 = top.sum(), bot.sum()
            comp[kx] = (y[top].sum() * n0 / (n1 + n0), 0, y[bot].sum() * n1 / (n1 + n0), 0)
        else:
            comp[kx] = (y[top].sum(), top.sum(), y[bot].sum(), bot.sum())
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, K, size=(NBOOT, K))
    s = comp[draw].sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = s[:, 0] / s[:, 2] if two else sm(s[:, 0], s[:, 1]) / sm(s[:, 2], s[:, 3])
        if d < 0:
            rr = 1.0 / rr
    rr = rr[np.isfinite(rr)]
    if len(rr) < NBOOT // 2:
        return float("nan"), float("nan"), NBOOT - len(rr)
    return float(np.percentile(rr, 5)), float(np.percentile(rr, 95)), NBOOT - len(rr)


def fmt(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nan"
    return "inf" if np.isinf(x) else f"{x:.2f}"


def J(s, d):
    """the judged ratio in the frozen direction (C2)."""
    return float(np.exp(d * s["lr"])) if np.isfinite(s["lr"]) else float("nan")


def RAW(s, d):
    x = s["raw"]
    if d > 0 or (isinstance(x, float) and np.isnan(x)):
        return x
    return np.inf if x == 0 else (0.0 if np.isinf(x) else 1.0 / x)


def desc(s, d):
    """ratio in the frozen direction + the counts behind it."""
    if s["two"]:
        if s["nt"] == 0 or s["nb"] == 0:
            return f"n/a (yes {int(s['wt'])}/{s['nt']}, no {int(s['wb'])}/{s['nb']})"
        return f"{fmt(J(s, d)) if np.isfinite(s['lr']) else fmt(RAW(s, d))} (yes {int(s['wt'])}/{s['nt']}, no {int(s['wb'])}/{s['nb']})"
    if s["nt"] == 0 or s["nb"] == 0:
        return f"n/a (bottom {int(s['wb'])}/{s['nb']}, top {int(s['wt'])}/{s['nt']})"
    return f"{fmt(J(s, d))} (raw {fmt(RAW(s, d))}; bottom {int(s['wb'])}/{s['nb']}, top {int(s['wt'])}/{s['nt']})"


# ════════════════════════════════════════ C10 GATE — B1 pooled reproduction (before any family number) ════════════════════════════════════════
B1L = []
b1 = stat(big, B1_T, AL.U_MONTH, False)
b1A = stat(big, B1_T, AL.U_MONTH, False, mask=AL.eraA)
b1B = stat(big, B1_T, AL.U_MONTH, False, mask=~AL.eraA)
b1_n = int((B1_T >= 0).sum()); b1_m = len(set(AL.U_MONTH[B1_T >= 0]))
gate_ok = (f"{b1['rb']:.3f}" == B1_EXPECT["bottom"] and f"{b1['rt']:.3f}" == B1_EXPECT["top"] and abs(b1["raw"] - B1_EXPECT["ratio"]) < 0.005)
mm = lambda ok: "MATCH" if ok else "MISS"
B1L.append("\n" + "=" * 118)
B1L.append("## POOLED B1 (shelf distance) REPRODUCTION — §4.1 / §6 step 8 (benchmark, already seen: RESULT 8). All 4,665 events, thirds within (era, month), ticker tie-break.")
B1L.append(f"   here     : scored in test {b1_n} in {b1_m} months | bottom {int(b1['wb'])}/{b1['nb']} = {b1['rb']:.3f} | middle {int(b1['wm'])}/{b1['nm']} = {b1['rm']:.3f} | top {int(b1['wt'])}/{b1['nt']} = {b1['rt']:.3f} | ratio top/bottom {b1['raw']:.3f}")
B1L.append(f"   RESULT 8 : 3,671 EPs in 87 months | bottom 9.6% | middle 11.3% | top 12.9% | ratio 1.36 (1.355)")
B1L.append(f"   HARD GATE (prereg: '12.9% vs 9.6% = 1.36x'): bottom {mm(f'{b1['rb']:.3f}' == B1_EXPECT['bottom'])} · top {mm(f'{b1['rt']:.3f}' == B1_EXPECT['top'])} · ratio {mm(abs(b1['raw'] - B1_EXPECT['ratio']) < 0.005)}"
           f"  -> {'PASSED' if gate_ok else 'MISSED'}" + ("  [synthetic: not enforced]" if SYN else ""))
B1L.append(f"   beside it (RESULT 8's text, not the prereg's assert): n {mm(b1_n == B1_EXPECT['n'])} · months {mm(b1_m == B1_EXPECT['months'])} · middle {mm(f'{b1['rm']:.3f}' == B1_EXPECT['middle'])}"
           f" · era A {fmt(b1A['raw'])} vs 1.48 {mm(fmt(b1A['raw']) == B1_EXPECT['era_A'])} · era B {fmt(b1B['raw'])} vs 1.08 {mm(fmt(b1B['raw']) == B1_EXPECT['era_B'])}")
B1L.append(f"   per era: A bottom {int(b1A['wb'])}/{b1A['nb']} top {int(b1A['wt'])}/{b1A['nt']} ratio {fmt(b1A['raw'])} | B bottom {int(b1B['wb'])}/{b1B['nb']} top {int(b1B['wt'])}/{b1B['nt']} ratio {fmt(b1B['raw'])}")
ey = sorted(set(zip(AL.df.era, AL.df.year)))
B1L.append("   per era-year (ratio, winners top:bottom): " + " · ".join(
    f"{e}{y} {fmt(s_['raw'])} ({int(s_['wt'])}:{int(s_['wb'])})" for (e, y) in ey
    for s_ in [stat(big, B1_T, AL.U_MONTH, False, mask=((AL.df.era == e) & (AL.df.year == y)).to_numpy())] if s_["nt"] and s_["nb"]))
sD = stat(big, B1_T, AL.U_MONTH, False, mask=IS_DISC); sC = stat(big, B1_T, AL.U_MONTH, False, mask=IS_CONF)
B1L.append(f"   by set: DISCOVERY bottom {int(sD['wb'])}/{sD['nb']} top {int(sD['wt'])}/{sD['nt']} ratio {fmt(sD['raw'])} (stage 3 printed 60/652, 90/616, 1.59) | CONFIRM bottom {int(sC['wb'])}/{sC['nb']} top {int(sC['wt'])}/{sC['nt']} ratio {fmt(sC['raw'])}")
c1 = stat(big, B1C_T, AL.U_MONTH, False); c1C = stat(big, B1C_T, AL.U_MONTH, False, mask=IS_CONF)
B1L.append(f"   B1-clean (dmin with the §4.0 NULL rules 3-4; description only): all years bottom {int(c1['wb'])}/{c1['nb']} = {c1['rb']:.3f} top {int(c1['wt'])}/{c1['nt']} = {c1['rt']:.3f} ratio {fmt(c1['raw'])}"
           f" | CONFIRM bottom {int(c1C['wb'])}/{c1C['nb']} top {int(c1C['wt'])}/{c1C['nt']} ratio {fmt(c1C['raw'])}")
if not SYN and not gate_ok:
    LINES.extend(B1L)
    stop("C10 gate: the pooled B1 reproduction missed RESULT 8 (12.9% vs 9.6% = 1.36x) — no family number is written (prereg §4.1: a mismatch stops the run)")
P(f"   C10 GATE (B1 pooled reproduction of RESULT 8) {'PASSED' if gate_ok else 'not enforced (synthetic)'} before any family number was derived — detail in the B1 block near the end.")

# ════════════════════════════════════════ C13 GATE — the copied statistics reproduce stage 3 on discovery ════════════════════════════════════════
yD = big[IS_DISC]
UKD = np.random.default_rng(C.SEED).random((NS, ND))
g13 = []


def chk(name, got, exp, nd=3):
    ok = f"{got:.{nd}f}" == exp
    g13.append((name, f"{got:.{nd}f}", exp, ok))


def disc_read(col, two):
    t = DC.month_layout(col, two)
    o = stat(yD, t, DC.U_MONTH, two)
    pl = perm_lr(DC, yD, t, two, UKD)
    p2 = (1 + int((np.abs(pl) >= abs(o["lr"]) - 1e-12).sum())) / (NS + 1)
    return t, o, p2


t_, o_, p_ = disc_read("f03", False)
chk("f03 ratio", np.exp(o_["lr"]), "2.430"); chk("f03 two-sided p", p_, "0.0001", 4)
ci_ = boot_ci(DC, yD, t_, False, +1); chk("f03 interval low", ci_[0], "1.99", 2); chk("f03 interval high", ci_[1], "3.00", 2)
t_, o_, p_ = disc_read("f02", False)
chk("f02 ratio", np.exp(o_["lr"]), "0.355"); chk("f02 two-sided p", p_, "0.0001", 4)
ci_ = boot_ci(DC, yD, t_, False, +1); chk("f02 interval low", ci_[0], "0.26", 2); chk("f02 interval high", ci_[1], "0.49", 2)
ci2 = boot_ci(DC, yD, t_, False, -1)
g13.append(("f02 interval inverted under LOW (low = 1/high, high = 1/low)", f"{ci2[0]:.3f}-{ci2[1]:.3f}", f"{1 / ci_[1]:.3f}-{1 / ci_[0]:.3f}",
            abs(ci2[0] * ci_[1] - 1) < 1e-6 and abs(ci2[1] * ci_[0] - 1) < 1e-6))
g13.append(("f02 oriented ratio J(d=-1) = 1 / ratio", f"{J(o_, -1):.4f}", f"{1 / np.exp(o_['lr']):.4f}", abs(J(o_, -1) * np.exp(o_["lr"]) - 1) < 1e-9))
t_, o_, p_ = disc_read("f01", False)
chk("f01 ratio", np.exp(o_["lr"]), "1.321"); chk("f01 two-sided p", p_, "0.0224", 4)
t_, o_, p_ = disc_read("f09", False)
chk("f09 ratio", np.exp(o_["lr"]), "5.443")
t_, o_, p_ = disc_read("f16", True)
chk("f16 MH ratio", o_["raw"], "1.540"); chk("f16 two-sided p", p_, "0.0080", 4)
ci_ = boot_ci(DC, yD, t_, True, +1); chk("f16 interval low", ci_[0], "1.14", 2); chk("f16 interval high", ci_[1], "2.02", 2)
chk("window x1.0 f03", J(stat(yD, DLAY_S[1.0]["f03"], DC.U_MONTH, False), +1), "2.430"); chk("window x1.0 f09", J(stat(yD, DLAY_S[1.0]["f09"], DC.U_MONTH, False), +1), "5.443")
del UKD
g13_ok = all(x[3] for x in g13)
G13L = ["   C13 GATE (copied statistics reproduce stage3/discovery.txt on discovery): " + " · ".join(f"{n} {g} vs {e} {'OK' if ok else 'MISS'}" for n, g, e, ok in g13)]
if (not SYN or REALDISC) and not g13_ok:
    LINES.extend(G13L)
    stop("C13 gate: this script's statistics do not reproduce stage 3 on the discovery outcomes — no confirm number is written")
LINES.extend(G13L)
P(f"   C13 GATE {'PASSED' if g13_ok else 'not enforced (synthetic labels)'}.")

# ════════════════════════════════════════ the family of 9 on CONFIRM ════════════════════════════════════════
yb = big[IS_CONF]; ymon = monster[IS_CONF]; yadr = adrt[IS_CONF]; yf5 = fail5[IS_CONF]; yr60 = ret60[IS_CONF]; yfp = failpool[IS_CONF]
UKEY = np.random.default_rng(C.SEED).random((NS, N))
RES = {}
for r in FAMILY:
    two, d, t = r in TWO, DIR[r], LAY[r]
    own = stat(yb, t, CF.U_MONTH, two)
    pl = perm_lr(CF, yb, t, two, UKEY)
    bad_perm = int((~np.isfinite(pl)).sum())
    p = (1 + int((d * pl >= d * own["lr"] - 1e-12).sum())) / (NS + 1) if np.isfinite(own["lr"]) else float("nan")
    plf = pl[np.isfinite(pl)]
    RES[r] = dict(own=own, p=p, bad_perm=bad_perm, ci=boot_ci(CF, yb, t, two, d),
                  null95=(float(np.exp(np.percentile(d * plf, 2.5))), float(np.exp(np.percentile(d * plf, 97.5)))),
                  A=stat(yb, t, CF.U_MONTH, two, mask=CF.eraA), B=stat(yb, t, CF.U_MONTH, two, mask=~CF.eraA),
                  mon=stat(ymon, t, CF.U_MONTH, two), n_mon=int(ymon[t >= 0].sum()), adrt=stat(yadr, t, CF.U_MONTH, two),
                  adrn=(stat(yb, LAY_ADR[r], U_ADR, two) if LAY_ADR[r] is not None else None),
                  dm=stat(yb, LAY_DM[r], U_DMIN, two), dmk=[stat(yb, LAY_DM[r], U_DMIN, two, mask=(DM3 == kx)) for kx in (0, 1, 2)])
del UKEY
# Holm (C4)
ps = np.array([RES[r]["p"] if np.isfinite(RES[r]["p"]) else 1.0 for r in FAMILY])
order = np.argsort(ps, kind="stable")
adj = np.zeros(len(FAMILY)); run = 0.0
for rank, ix in enumerate(order):
    run = max(run, min(1.0, (len(FAMILY) - rank) * ps[ix]))
    adj[ix] = run


def word_of(x, holm, both):
    if not np.isfinite(x):
        return "UNDEFINED (ratio not computable)"
    if x >= 1.2:
        return ("PICKS THE TAIL" if both else "PICKS THE TAIL (one era only)") if holm <= 0.05 else "DIRECTIONAL, NOT PROVEN"
    return "NOT CONFIRMED" if x >= 1.0 else "REVERSED"


for ix, r in enumerate(FAMILY):
    R = RES[r]; d = DIR[r]
    R["holm"] = float(adj[ix]); R["rank"] = int(np.flatnonzero(order == ix)[0]) + 1
    R["ratio"] = J(R["own"], d)
    R["jA"], R["jB"] = J(R["A"], d), J(R["B"], d)
    R["both"] = bool(np.isfinite(R["jA"]) and np.isfinite(R["jB"]) and R["jA"] > 1.0 and R["jB"] > 1.0)
    R["word"] = word_of(R["ratio"], R["holm"], R["both"])
    R["raw_ratio"] = RAW(R["own"], d)
    rA, rB = RAW(R["A"], d), RAW(R["B"], d)
    R["both_raw"] = bool(np.isfinite(rA) and np.isfinite(rB) and rA > 1.0 and rB > 1.0)
    R["word_raw"] = word_of(R["raw_ratio"], R["holm"], R["both_raw"])
    R["straddle"] = R["word_raw"] != R["word"]
    if r == "H4":
        R["tag"] = ""; R["tagwhy"] = "tag not applied to H4 (§11.3)"
    else:
        an, at = J(R["adrn"], d), J(R["adrt"], d)
        if not (np.isfinite(an) and np.isfinite(at)):
            R["tag"] = ""; R["tagwhy"] = "tag not computable (a ratio is undefined)"
        else:
            hit = [w for w, c_ in ((f"ADR-neutral {an:.2f} < 1.2", an < 1.2), (f"ADR-scaled tail {at:.2f} < 1.10", at < 1.10)) if c_]
            R["tag"] = " — a volatility proxy" if hit else ""
            R["tagwhy"] = ("tag fires: " + " and ".join(hit)) if hit else f"tag does not fire (ADR-neutral {an:.2f} >= 1.2 and ADR-scaled tail {at:.2f} >= 1.10)"

P("\n" + "=" * 118)
P("## CONFIRM base rates: events | big winners (>= 1.5x) | monsters (>= 2.0x) | ADR-scaled tail | failure pool (max close < 1.10x) | close(E+5) < open | mean 60-session return")
cells = [(f"{e} {y}", ((CF.df.era == e) & (CF.df.year == y)).to_numpy()) for (e, y) in sorted(set(zip(CF.df.era, CF.df.year)))]
cells += [("era A", CF.eraA), ("era B", ~CF.eraA), ("ALL", np.ones(N, bool))]
for nm, m in cells:
    P(f"   {nm:8s} n {int(m.sum()):4d} | big {int(yb[m].sum()):3d} ({yb[m].mean():.3f}) | monster {int(ymon[m].sum()):3d} ({ymon[m].mean():.3f}) | ADR tail {int(np.nansum(yadr[m])):3d} ({np.nanmean(yadr[m]):.3f})"
      f" | fail pool {int(yfp[m].sum()):4d} ({yfp[m].mean():.3f}) | fail5 {np.nanmean(yf5[m]):.3f} | ret60 mean {np.nanmean(yr60[m]):+.3f}")
nbc = nbars[IS_CONF]
P(f"   events with fewer than 61 bars in E..E+60 (kept, no survivorship drop): {int((nbc < 61).sum())}; no bar at E+5: {int(np.isnan(yf5).sum())}; no bar at E+60: {int(np.isnan(yr60).sum())}")

P("\n" + "=" * 118)
P("## §5.3 CONFIRM — the family of 9, one run, one-sided in the frozen direction, Holm over 9")
P(f"   permutation: {NS} shuffles, rng {C.SEED}; confirm events {N}; big winners {int(yb.sum())}; monsters {int(ymon.sum())}")
P("   NOTE (§11.3, his ruling): the suffix '— a volatility proxy' is a DESCRIPTION, not a negative verdict; it changes no verdict word.")
VERD = []
for r in FAMILY:
    R = RES[r]; d = DIR[r]; two = r in TWO; o = R["own"]; t = LAY[r]
    P(f"\n{r} — {NAMES[r]} | frozen direction: {DIRN[r]} | " + ("two-group, Mantel-Haenszel by (era, month)" if two else "thirds within (era, month)")
      + (" | COMBINATION (§5.6)" if r == "combo" else (" | his read (§11)" if r in ("H1", "H2", "H3") else (" | his ruling, = benchmark B2 (§11)" if r == "H4" else " | carried feature"))))
    if two:
        P(f"   big winner: YES {int(o['wt'])}/{o['nt']} = {o['rt']:.3f} | NO {int(o['wb'])}/{o['nb']} = {o['rb']:.3f} | MH ratio yes/no {fmt(o['raw'])} (pooled, biased: {fmt(o['pooled'])})"
          f" | RATIO in the frozen direction ({'no/yes' if d < 0 else 'yes/no'}) {R['ratio']:.3f}")
    else:
        P(f"   big winner: bottom {int(o['wb'])}/{o['nb']} = {o['rb']:.3f} | middle {int(o['wm'])}/{o['nm']} = {o['rm']:.3f} | top {int(o['wt'])}/{o['nt']} = {o['rt']:.3f}"
          f" | RATIO in the frozen direction ({'bottom/top' if d < 0 else 'top/bottom'}) {R['ratio']:.3f} (raw {R['raw_ratio']:.3f})")
    P(f"   90% bootstrap interval {fmt(R['ci'][0])}-{fmt(R['ci'][1])}" + (f" ({R['ci'][2]} undefined draws dropped)" if R["ci"][2] else "")
      + f" | one-sided permutation p {R['p']:.4f}" + (f" ({R['bad_perm']} shuffles with an undefined MH ratio)" if R["bad_perm"] else "")
      + f" | Holm-adjusted p (family of 9; rank {R['rank']} of 9) {R['holm']:.4f} | null 95% band of the ratio {R['null95'][0]:.2f}-{R['null95'][1]:.2f}")
    P(f"   per era (ratio in the frozen direction): era A {desc(R['A'], d)} | era B {desc(R['B'], d)} -> same direction in both: {'yes' if R['both'] else 'no'}")
    # §5.5 extras
    P("   §5.5 extras (description; none is a bar):")
    P("     per year: " + " · ".join(f"{nm} {desc(stat(yb, t, CF.U_MONTH, two, mask=m), d)}" for nm, m in cells[:-3]))
    P(f"     common stock only: {desc(stat(yb, t, CF.U_MONTH, two, mask=M_CS), d)} | untyped only: {desc(stat(yb, t, CF.U_MONTH, two, mask=M_UNT), d)}")
    P(f"     one event per identity per 60 sessions: {desc(stat(yb, t, CF.U_MONTH, two, mask=M_ONE), d)} | gap >= 10% only: {desc(stat(yb, t, CF.U_MONTH, two, mask=M_GAP10), d)}")
    P("     ADR-neutral (thirds within era-quarter-ADR third): " + ("n/a for H4 (thirds of ADR within ADR thirds, §11.3)" if R["adrn"] is None else desc(R["adrn"], d)))
    P(f"     ADR-SCALED TAIL (>= 8 daily ranges above the open): {desc(R['adrt'], d)}")
    P(f"     MONSTER tier (>= 2.0x; never a bar): {desc(R['mon'], d)}" + (f"  [thin: {R['n_mon']} monsters in the set under test, < 60]" if R["n_mon"] < 60 else f"  [{R['n_mon']} monsters]"))
    P(f"     within shelf-distance thirds (strata era-quarter-dmin third): pooled {desc(R['dm'], d)} | lowest dmin third {desc(R['dmk'][0], d)} | middle {desc(R['dmk'][1], d)} | highest {desc(R['dmk'][2], d)}")
    P("     feature 12 within vr20_mean halves: n/a (f12 is not in the family)")
    lo_g, hi_g = (t == 2, t == 0) if (two and d > 0) or (not two and d > 0) else (t == 0, t == 2)       # lo_g = the winning group
    P(f"     failed (description): close(E+5) < open — winning side {np.nanmean(yf5[lo_g]):.3f} vs losing side {np.nanmean(yf5[hi_g]):.3f} | mean 60-session return — winning side {np.nanmean(yr60[lo_g]):+.3f} vs losing side {np.nanmean(yr60[hi_g]):+.3f}")
    R["winlose"] = (lo_g, hi_g)
    if R["straddle"]:
        P(f"   *** C14 FROZEN-RULE AMBIGUITY: on the smoothed ratio {R['ratio']:.3f} the word is '{R['word']}'; on the raw ratio {R['raw_ratio']:.3f} it is '{R['word_raw']}'. Both are printed; neither is picked here.")
    rawtxt = "" if r in TWO else f" (raw {R['raw_ratio']:.3f})"
    line = (f"VERDICT {r} {NAMES[r]} [{DIRN[r]}]: {R['word']}{(' [raw-ratio reading: ' + R['word_raw'] + ' — C14 AMBIGUITY]') if R['straddle'] else ''}{R['tag']} | ratio {R['ratio']:.2f}{rawtxt} (90% {fmt(R['ci'][0])}-{fmt(R['ci'][1])}) | one-sided p {R['p']:.4f} | Holm p {R['holm']:.4f}"
            f" | era A {fmt(R['jA'])} · era B {fmt(R['jB'])} | monster {fmt(J(R['mon'], d)) if np.isfinite(R['mon']['lr']) else fmt(RAW(R['mon'], d))}{' (thin)' if R['n_mon'] < 60 else ''}"
            f" | ADR-scaled tail {fmt(J(R['adrt'], d))} | ADR-neutral {'n/a' if R['adrn'] is None else fmt(J(R['adrn'], d))} | {R['tagwhy']}")
    VERD.append(line)
    P("   " + line)

P("\n" + "=" * 118)
P("## VERDICT LINES (§5.3) — '— a volatility proxy' is printed as defined in §2 but per §11.3 is NOT a negative verdict")
for line in VERD:
    P("   " + line)
P("\n## HOLM TABLE (family of 9, sorted by one-sided p)")
for rank, ix in enumerate(order):
    r = FAMILY[ix]
    P(f"   {rank + 1}. {r:5s} p {ps[ix]:.4f} x {len(FAMILY) - rank} -> Holm {adj[ix]:.4f}  ratio {RES[r]['ratio']:.2f}  {RES[r]['word']}")
nstr = [r for r in FAMILY if RES[r]["straddle"]]
P("   C14 guard: " + ("the verdict word is the same on the smoothed and on the raw ratio for all 9 members." if not nstr else f"*** the word DIFFERS between the smoothed and the raw ratio for {nstr} — frozen-rule ambiguity, see those blocks."))
P("   H1-H3 are close to one read, not three (§11.2); Holm counts them as three. Power at a family of 9 was not simulated (§11.2).")

# ════════════════════════════════════════ §5.5 window +/-50% on DISCOVERY ════════════════════════════════════════
P("\n" + "=" * 118)
P("## §5.5 WINDOW LENGTH +/-50% — DISCOVERY ONLY (description; discovery outcomes are 'seen'). Ratio in the frozen direction; 'fragile' = under 1.2 at either scale.")
for r in FAMILY:
    d = DIR[r]; two = r in TWO
    if r == "f18":
        P(f"   {r:5s} {NAMES[r]:36s}: n/a (a price on E-1 has no window to scale)")
        continue
    js = {}
    parts = []
    for s in (1.0, 0.5, 1.5):
        st_ = stat(yD, DLAY_S[s][r], DC.U_MONTH, two)
        js[s] = J(st_, d)
        parts.append(f"x{s}: {fmt(js[s])} (n in test {int((DLAY_S[s][r] >= 0).sum())})")
    und = [s for s in (0.5, 1.5) if not np.isfinite(js[s])]
    frag = "n/a (a ratio is undefined)" if und else ("FRAGILE" if (js[0.5] < 1.2 or js[1.5] < 1.2) else "not fragile")
    P(f"   {r:5s} {NAMES[r]:36s}: " + " | ".join(parts) + f" -> {frag}")
P("   (x1.0 = the frozen definition recomputed on discovery; for f02 / H4 / the combination the x1.0 row uses the scaled-ADR code and can differ from stage 3 by the bad_price NULL rule only.)")

# ════════════════════════════════════════ B1 block ════════════════════════════════════════
LINES.extend(B1L)

# ════════════════════════════════════════ H1-H3 on DISCOVERY — 'seen' ════════════════════════════════════════
P("\n" + "=" * 118)
P("## H1-H3 ON DISCOVERY — DESCRIPTION, 'SEEN' (§5.7, §11.1: he named these reads after looking at the discovery winners; these numbers are not a test)")
ymD = monster[IS_DISC]; yaD = adrt[IS_DISC]
is2020 = (DC.year == "2020")
for r in ("H1", "H2", "H3"):
    d = DIR[r]; t = DLAY[r]
    o = stat(yD, t, DC.U_MONTH, True)
    P(f"   {r} {NAMES[r]} [{DIRN[r]}] seen: YES {int(o['wt'])}/{o['nt']} = {o['rt']:.3f} | NO {int(o['wb'])}/{o['nb']} = {o['rb']:.3f} | MH ratio in his direction ({'no/yes' if d < 0 else 'yes/no'}) {fmt(J(o, d))}"
      f" (pooled, biased: {fmt(RAW(dict(raw=o['pooled']), d))}) | months in test {len(set(DC.U_MONTH[t >= 0]))}, events {int((t >= 0).sum())}")
    P(f"        ex-2020 (2016-19): {desc(stat(yD, t, DC.U_MONTH, True, mask=~is2020), d)} | 2020 only: {desc(stat(yD, t, DC.U_MONTH, True, mask=is2020), d)}"
      f" | monster: {desc(stat(ymD, t, DC.U_MONTH, True), d)} | ADR-scaled tail: {desc(stat(yaD, t, DC.U_MONTH, True), d)}")
    P("        per year: " + " · ".join(f"{y} {desc(stat(yD, t, DC.U_MONTH, True, mask=(DC.year == y)), d)}" for y in sorted(set(DC.year))))
P("   H4 (ADR20) on discovery = stage 3's B2 block, 'seen' and disclosed in §11.2: top third 179/783 = 0.229 vs bottom 32/819 = 0.039, ratio 5.78; not recomputed here.")

P("\n## END OF CONFIRM" + (" [SYNTHETIC — not a result]" if SYN else " — this run is not repeated (prereg §5.3). Next per §6: the blind recount of this step; blind sheets B only for members that reached PICKS THE TAIL."))

# ════════════════════════════════════════ write ════════════════════════════════════════
if not SYN:
    out = T.loc[IS_CONF, ["era", "ticker", "E", "year", "month"]].copy()
    out["maxc_ratio"] = maxc[IS_CONF]; out["big_winner"] = yb.astype(int); out["monster"] = ymon.astype(int); out["adr_tail"] = yadr
    out["fail5"] = yf5; out["ret60"] = yr60; out["fail_pool"] = yfp.astype(int); out["fwd_bars"] = nbc
    for r in FAMILY:
        out["grp_" + r] = LAY[r]
    assert len(out) == 2251 and out.E.min() >= "2021-01-01" and out.E.max() <= "2024-09-30"
    OC = HERE / "confirm_outcomes.tsv.gz"
    out.to_csv(OC, sep="\t", index=False, float_format="%.8g", compression={"method": "gzip", "mtime": 0})
    P(f"wrote confirm_outcomes.tsv.gz ({len(out)} confirm rows; grp_* = the layout used: thirds 0/1/2, two-group 2 = yes / 0 = no, -1 = not in test), sha256 {C.sha(OC)}")
write_out()
if not SYN:
    h = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    (HERE / "confirm.txt.sha256").write_text(f"{h}  confirm.txt\n{C.sha(__file__)}  confirm.py\n{C.sha(HERE / 'confirm_outcomes.tsv.gz')}  confirm_outcomes.tsv.gz\n")
print(f"finished: wrote {OUT_PATH}" + (" [synthetic]" if SYN else ""))
