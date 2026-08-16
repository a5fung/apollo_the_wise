#!/usr/bin/env python3
"""RS TRAJECTORY SHAPE (2026-08-16) — does a three-phase FALL -> STABILISE -> RISE (or its
calculus form, RS ACCELERATION/DECELERATION) beat the 2-point rs_1m-rs_6m sign already
tested, and does it survive his own floor objection?

SPEC: docs/methodology/operator_shared_notes.md §2026-08-16 "WHY THE TAIL, AND THE RS
TRAJECTORY SHAPE" (Claims 1-3) + docs/roadmap/ep_profitability_program.md §2026-08-16 "THE
TAIL RE-READ" (Finding 1: RS inflection sign has a TAIL effect that the median read missed;
FORK S-3 territory, nothing wired live) + §2026-08-15 "RS IMPROVEMENT, not RS level" (the
rs_1m-rs_6m primary that this probe re-tests with a richer feature, SAME population/method
otherwise). READ-ONLY. SHADOW MEASUREMENT ONLY. THE LINE: measures; wires nothing; a result
that points at a change is a FORK for the operator, no option pre-chosen.

HIS OWN OBJECTION IS THE PRIMARY TEST (verbatim, 2026-08-16): "or maybe this is moot because
the tail can't go lower?" RS composite is a 0-100 percentile, floored at 0 — variance
compresses mechanically near the floor, so "stabilisation" (or "deceleration") could be
GUARANTEED by the floor for any name already near rank-bottom, carrying no information.
PRE-REGISTERED PRIMARY: within NARROW RS-LEVEL BANDS (comp0 deciles across [0,50), holding
"how close to the floor" constant across the comparison), does the predicted trajectory
regime separate the TAIL (P90/P95, share>=+50%/+100%, max_high_20d primary / max_high_5d
secondary, permutation on the tail statistic itself via _tail_stats.py, whole ALERT-DATE
sessions shuffled)? If the effect only shows up POOLED (bands merged) and vanishes within
bands, the honest reading is "moot" per the task's own framing, and that is reported as a
complete, valuable answer, not softened.

THE SECOND-DERIVATIVE REFINEMENT (operator, sent mid-task, verbatim): "or another way to
think about it is the 2nd derivative, RS deceleration/acceleration down or up, I'd expect
deceleration associated with neglect and acceleration associated with attention in either
direction." This IS the three-phase shape restated as curvature: FALL then STABILISE is
"falling, decelerating" (velocity shrinking toward zero = sellers exhausting = neglect);
"the middle that already rose" is "rising, accelerating" (attention chasing it up); a name
about to fade after a run is "rising, decelerating." Adopted as the PRIMARY feature
encoding; the plain flat-vs-falling classification and the original 2-point sign are kept
as explicit comparators, not dropped — the task's own question is whether the richer
encodings add anything over the plain sign, and three encodings of one idea must be
COUNTED as related, not stacked as independent findings.

FEATURES, ALL POINT-IN-TIME (bisect on score_date STRICTLY < alert_date, identical
enforcement to _rs_inflection_read.py -- reused verbatim: structural bisect + runtime assert
+ 7-calendar-day staleness cutoff + lag histogram printed):
  comp0, rankpct0        rs_composite (0-100, higher=better) and rank-as-percentile-of-that-
                          day's stored universe (0-100, higher=WORSE -- near 100 = bottom
                          decile) at the feature row.
  slope_comp_W, slope_rankpct_W (W in 20, 60 SESSIONS, i.e. stored score-row counts, not
                          calendar days)  OLS slope of comp / rankpct on session-offset
                          across the W+1 points ending at the feature row. Requires i-W>=0
                          AND the window's own calendar span <= TRAJ_GUARD[W] (36d @ W=20,
                          the pre-existing house constant from _rs_inflection_read.py's
                          rchg20 guard; 100d @ W=60, a priori linear extrapolation of the
                          same 5->12/10->20/20->36 day-per-session ratio, disclosed, not
                          tuned on outcome) -- else the feature and everything downstream
                          for that W is undefined (None), NEVER silently substituted.
  accel_comp_W, accel_rankpct_W  slope(second half of window) - slope(first half), i.e. is
                          the trend itself speeding up or slowing down (curvature).
  regime4_comp_W         {falling_accel, falling_decel, rising_accel, rising_decel} per the
                          sign(slope) x sign(accel) table in the refinement above.
                          falling_decel is the PRE-REGISTERED PREDICTED bucket (neglect
                          settling -> EP precursor).
  flat_vs_falling_W      3-state classification reusing the EXACT a priori constants the
                          existing flatjump feature already uses (5 points cumulative change
                          ~ half a decile of the universe; 10 points intra-window range) --
                          FALLING: cumulative change <= -5. FLAT: |cumulative change| < 5 AND
                          window range <= 10. RISING: cumulative change >= +5. Anything else
                          (small negative change with wide range) is UNCLASSIFIED.
  duration_bottom_decile / _quintile   consecutive SESSIONS (and calendar DAYS) the name has
                          sat with rankpct >= 90 / >= 80, walking backward from the feature
                          row, bridging cadence gaps <= 10 calendar days (the weekly->daily
                          transition, 2026-03-24) but stopping (and flagging CENSORED) at any
                          larger gap or at the start of the ticker's own stored history --
                          "the feature that survives the floor" per the task.
  three_phase_composite  FALL over 60 sessions (cumulative change_60 <= -5) AND FLAT over the
                          last 20 (per flat_vs_falling_20 == FLAT). The richer shape as a
                          single yes/no, for head-to-head against the plain 2-point sign.
  infl16 = rs_1m - rs_6m the ALREADY-TESTED 2-point sign (rs_inflection_read.py's own
                          primary feature), carried over unchanged as the comparator.

CONFOUNDS: gap_pct and rs_composite LEVEL are on every row already (from
_rsinfl_outcomes.tsv / the point-in-time comp0). ADR20 is NOT stored in mi_stock_scores
(verified: no adr column in the table) or in the missed-outcomes table -- it is computed
LOCALLY from the cached daily OHLCV bars in _ladder_daily.tsv (463 of this probe's 1616
tickers overlap; the ADR confound check runs on that SUBSET only, coverage stated, no new
prod pull -- COST EFFICIENCY / "pull from prod only for daily RS history that is genuinely
not cached" scopes any new pull to RS history, which is fully cached here). Formula matches
_533_nbis_structure_encoder.py's adr20_pct() exactly: mean((high-low)/close*100) over the 20
trading days strictly before the feature date.

RIGOR: every test counted (TailLedger per section, house convention: each ledger is its OWN
Bonferroni denominator, never pooled across sections, matching _tail_reread_probe.py). A
GRAND total and an explicit statement of what survives a global correction across every tail
test this probe ran is printed at the end. N floors from _tail_stats.py (P90>=20, P95>=40,
share>=10, PER BUCKET) applied uniformly; thin cells print "N too thin", never a median
standing in for a tail read. Session-permutation, not per-row, on every p (whole alert-dates
share the tape).

Inputs (already cached, captured 2026-08-15/16, COST EFFICIENCY -- no re-pull):
  _rsinfl_outcomes.tsv, _rsinfl_scores.tsv, _rsinfl_totals.tsv  (identical to
  _rs_inflection_read.py's own inputs -- same population, same point-in-time machinery)
  _ladder_daily.tsv     daily OHLCV for the 463-ticker ladder-probe overlap (ADR confound only)
Output: capture once to docs/analysis/rs_trajectory_shape_2026-08-16.txt.
"""
from __future__ import annotations

import os
import statistics as st
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

if os.environ.get("APOLLO_PROBE_WRITE"):
    sys.exit("this probe is read-only by design")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _tail_stats as ts  # noqa: E402

SEED = 20260815
MATURITY_DAYS = {"ret_1d": 2, "ret_5d": 8, "ret_20d": 30, "max_high_5d": 8, "max_high_20d": 30}
STALE_MAX_DAYS = 7
MIN_UNIVERSE_ROWS = 500
TRAJ_GUARD = {20: 36, 60: 100}          # calendar-day span ceiling per window, a priori
FLAT_ABS_CHANGE = 5.0                    # points -- reused verbatim from flatjump
FLAT_RANGE_MAX = 10.0                    # points -- reused verbatim from flatjump
BOTTOM_DECILE_PCT = 90.0
BOTTOM_QUINTILE_PCT = 80.0
DURATION_GAP_GUARD_DAYS = 10
LOW_RS_PRIMARY = 50.0
BANDS = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, 40.0), (40.0, 50.0)]
ADR_LOOKBACK = 20


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def ols_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


# ================================================================================================
# LOAD (identical to _rs_inflection_read.py)
# ================================================================================================
UNIV: dict[str, int] = {}
for ln in (HERE / "_rsinfl_totals.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) == 2 and p[1].isdigit() and int(p[1]) >= MIN_UNIVERSE_ROWS:
        UNIV[p[0]] = int(p[1])

SCORES: dict[str, list[tuple]] = defaultdict(list)  # ticker -> [(date, rs1, rs3, rs6, comp, rank)]
for ln in (HERE / "_rsinfl_scores.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 7:
        continue
    t, d = p[0], p[1]
    if d not in UNIV:
        continue
    SCORES[t].append((d, fnum(p[2]), fnum(p[3]), fnum(p[4]), fnum(p[5]), fnum(p[6])))
for t in SCORES:
    SCORES[t].sort()

ROWS: list[dict] = []
for ln in (HERE / "_rsinfl_outcomes.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 11:
        continue
    ROWS.append(dict(
        ticker=p[0], d=p[1], skipcat=p[2], ep_score=fnum(p[3]), gap=fnum(p[4]),
        cq=p[5], ret_1d=fnum(p[6]), ret_5d=fnum(p[7]), ret_20d=fnum(p[8]),
        max_high_5d=fnum(p[9]), max_high_20d=fnum(p[10])))

DATA_MAX = max(pdate(r["d"]) for r in ROWS)

# ADR confound source: _ladder_daily.tsv (ticker|date|open|high|low|close|volume)
ADR_BARS: dict[str, list[tuple]] = defaultdict(list)
for ln in (HERE / "_ladder_daily.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 7:
        continue
    t, d = p[0], p[1]
    o, h, lo, c, v = (fnum(x) for x in p[2:7])
    if None in (h, lo, c) or c == 0:
        continue
    ADR_BARS[t].append((d, o, h, lo, c, v))
for t in ADR_BARS:
    ADR_BARS[t].sort()


def adr20_pct(ticker: str, before_date: str) -> float | None:
    """mean((high-low)/close*100) over the 20 trading days strictly before before_date.
    Matches _533_nbis_structure_encoder.py's adr20_pct() formula exactly."""
    bars = ADR_BARS.get(ticker)
    if not bars:
        return None
    dates = [b[0] for b in bars]
    ia = bisect_left(dates, before_date)
    lo_idx = max(0, ia - ADR_LOOKBACK)
    win = bars[lo_idx:ia]
    if len(win) < 10:
        return None
    return st.fmean((h - l) / c * 100.0 for _, _o, h, l, c, _v in win)


# ================================================================================================
# POINT-IN-TIME FEATURE BUILD
# ================================================================================================
excl = {"no_score_history": 0, "no_row_before_alert": 0, "stale_gt_7d": 0, "null_fields": 0}
lags: list[int] = []
for r in ROWS:
    r["feat"] = False
    ser = SCORES.get(r["ticker"])
    if not ser:
        excl["no_score_history"] += 1
        continue
    dates = [x[0] for x in ser]
    i = bisect_left(dates, r["d"]) - 1
    if i < 0:
        excl["no_row_before_alert"] += 1
        continue
    d0, rs1, rs3, rs6, comp, rank = ser[i]
    assert d0 < r["d"], f"LOOKAHEAD: {r['ticker']} feature {d0} !< alert {r['d']}"
    lag = (pdate(r["d"]) - pdate(d0)).days
    if lag > STALE_MAX_DAYS:
        excl["stale_gt_7d"] += 1
        continue
    if None in (rs1, rs6, comp, rank):
        excl["null_fields"] += 1
        continue
    lags.append(lag)
    r["feat"] = True
    r["i"] = i
    r["comp0"] = comp
    r["rankpct0"] = 100.0 * rank / UNIV[d0]
    r["infl16"] = rs1 - rs6
    r["adr20"] = adr20_pct(r["ticker"], d0)

    def rankpct_at(j):
        dj, _, _, _, _, rk = ser[j]
        return (100.0 * rk / UNIV[dj]) if (rk is not None and dj in UNIV) else None

    # ---- windowed slope / accel / regime, W in (20, 60) ----
    for W in (20, 60):
        r[f"slope_comp_{W}"] = None
        r[f"slope_rank_{W}"] = None
        r[f"accel_comp_{W}"] = None
        r[f"accel_rank_{W}"] = None
        r[f"disp_comp_{W}"] = None
        r[f"iqr_comp_{W}"] = None
        r[f"chg_comp_{W}"] = None
        r[f"range_comp_{W}"] = None
        r[f"regime4_comp_{W}"] = None
        r[f"regime4_rank_{W}"] = None
        r[f"flatfall_{W}"] = None
        j0 = i - W
        if j0 < 0:
            continue
        if (pdate(d0) - pdate(ser[j0][0])).days > TRAJ_GUARD[W]:
            continue
        pts = ser[j0:i + 1]                      # W+1 points, oldest..newest(=feature row)
        comps = [x[4] for x in pts]
        ranks_pct = [rankpct_at(j0 + k) for k in range(len(pts))]
        if any(c is None for c in comps) or any(rp is None for rp in ranks_pct):
            continue
        xs = list(range(len(pts)))
        slope_c = ols_slope(xs, comps)
        slope_r = ols_slope(xs, ranks_pct)
        H = len(pts) // 2
        s1_c = ols_slope(xs[:H + 1], comps[:H + 1])
        s2_c = ols_slope(xs[H:], comps[H:])
        s1_r = ols_slope(xs[:H + 1], ranks_pct[:H + 1])
        s2_r = ols_slope(xs[H:], ranks_pct[H:])
        if None in (slope_c, slope_r, s1_c, s2_c, s1_r, s2_r):
            continue
        accel_c = s2_c - s1_c
        accel_r = s2_r - s1_r
        chg_c = comps[-1] - comps[0]              # cumulative change, comp scale (+ = improved)
        rng_c = max(comps) - min(comps)
        disp_c = st.pstdev(comps)
        iqr_c = ts.pct(comps, 75) - ts.pct(comps, 25)

        r[f"slope_comp_{W}"] = slope_c
        r[f"slope_rank_{W}"] = slope_r
        r[f"accel_comp_{W}"] = accel_c
        r[f"accel_rank_{W}"] = accel_r
        r[f"disp_comp_{W}"] = disp_c
        r[f"iqr_comp_{W}"] = iqr_c
        r[f"chg_comp_{W}"] = chg_c
        r[f"range_comp_{W}"] = rng_c

        def regime4(slope, accel):
            if slope < 0:
                return "falling_decel" if accel >= 0 else "falling_accel"
            return "rising_accel" if accel >= 0 else "rising_decel"

        r[f"regime4_comp_{W}"] = regime4(slope_c, accel_c)
        # rank_pct is inverse of comp (higher = worse) -- flip sign so "improving" means the
        # same direction on both series before classifying, so the two regime labels are
        # directly comparable without the reader having to invert one of them.
        r[f"regime4_rank_{W}"] = regime4(-slope_r, -accel_r)

        if chg_c <= -FLAT_ABS_CHANGE:
            ff = "FALLING"
        elif chg_c >= FLAT_ABS_CHANGE:
            ff = "RISING"
        elif rng_c <= FLAT_RANGE_MAX:
            ff = "FLAT"
        else:
            ff = "UNCLASSIFIED"
        r[f"flatfall_{W}"] = ff

    # ---- three-phase composite: FALL(60) AND FLAT(20) ----
    r["three_phase"] = (r["chg_comp_60"] is not None and r["chg_comp_60"] <= -FLAT_ABS_CHANGE
                         and r["flatfall_20"] == "FLAT")

    # ---- duration at the bottom (walking backward from the feature row) ----
    for thresh, label in ((BOTTOM_DECILE_PCT, "decile"), (BOTTOM_QUINTILE_PCT, "quintile")):
        r[f"dur_{label}_days"] = None
        r[f"dur_{label}_sess"] = None
        r[f"dur_{label}_censored"] = None
        if r["rankpct0"] < thresh:
            continue                              # only defined for rows already in the bucket
        start_idx = i
        for idx in range(i - 1, -1, -1):
            rp = rankpct_at(idx)
            if rp is None or rp < thresh:
                break
            gap = (pdate(ser[start_idx][0]) - pdate(ser[idx][0])).days
            if gap > DURATION_GAP_GUARD_DAYS:
                break
            start_idx = idx
        censored = (start_idx == 0)
        r[f"dur_{label}_days"] = (pdate(ser[i][0]) - pdate(ser[start_idx][0])).days
        r[f"dur_{label}_sess"] = i - start_idx + 1
        r[f"dur_{label}_censored"] = censored

FEAT = [r for r in ROWS if r["feat"]]


def mature(rows, h):
    cutoff = DATA_MAX - timedelta(days=MATURITY_DAYS[h])
    return [r for r in rows if pdate(r["d"]) <= cutoff]


def band_of(r):
    c = r["comp0"]
    for lo, hi in BANDS:
        if lo <= c < hi:
            return f"[{lo:.0f},{hi:.0f})"
    return None


def spearman(xs, ys):
    n = len(xs)
    if n < 10:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda idx: v[idx])
        rk = [0.0] * n
        i2 = 0
        while i2 < n:
            j2 = i2
            while j2 + 1 < n and v[order[j2 + 1]] == v[order[i2]]:
                j2 += 1
            avg = (i2 + j2) / 2 + 1
            for k2 in range(i2, j2 + 1):
                rk[order[k2]] = avg
            i2 = j2 + 1
        return rk

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.fmean(rx), st.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


def run_within_bands(ledger: ts.TailLedger, label: str, pop: list[dict], split_fn, horizons):
    """The PRIMARY-shape test: same split_fn, run SEPARATELY inside each narrow comp0 band,
    so the floor (how close to 0 the band is) is held constant within every single test."""
    for lo, hi in BANDS:
        blabel = f"{label} | band comp0[{lo:.0f},{hi:.0f})"
        bandpop = [r for r in pop if lo <= r["comp0"] < hi]
        for h in horizons:
            m = mature(bandpop, h)
            pos = [r for r in m if split_fn(r) is True and r.get(h) is not None]
            neg = [r for r in m if split_fn(r) is False and r.get(h) is not None]
            print_tail_test(ledger, blabel, h, pos, neg)


def print_tail_test(ledger: ts.TailLedger, label: str, h: str, pos: list[dict], neg: list[dict]):
    pv = [r[h] * 100.0 for r in pos]
    nv = [r[h] * 100.0 for r in neg]
    ps = [r["d"] for r in pos]
    ns = [r["d"] for r in neg]
    dpos = ts.describe_tail(pv, set(ps))
    dneg = ts.describe_tail(nv, set(ns))
    print(f"\n  {label}  [{h}]")
    print(f"    POS {ts.fmt_bucket(dpos)}")
    print(f"    NEG {ts.fmt_bucket(dneg)}")
    for stat_name, statfn, dfield in [("P90", ts.p90, "p90"), ("P95", ts.p95, "p95"),
                                       ("share>=+50%", ts.share_stat(50.0), "share50"),
                                       ("share>=+100%", ts.share_stat(100.0), "share100")]:
        thin = (dpos[dfield] is None or dneg[dfield] is None)
        if thin:
            reason = ("n<20 for P90" if stat_name == "P90" else
                      "n<40 for P95" if stat_name == "P95" else "n<10 for a share")
            print(f"    {stat_name:<13} N TOO THIN ({reason}; pos n={dpos['n']}, neg n={dneg['n']})"
                  f" — no test attempted")
            ledger.add(label, stat_name, h, dpos, dneg, None, None, thin=True)
            N_THIN.append(f"{ledger.name} / {label} / {h} / {stat_name}: n={dpos['n']}/{dneg['n']}")
            continue
        p = ts.perm_p_stat(pv, nv, ps, ns, statfn)
        effect = statfn(pv) - statfn(nv)
        pstr = "N too coarse (perm resolution)" if p is None else f"raw p={p:.4f}"
        if p is None:
            N_THIN.append(f"{ledger.name} / {label} / {h} / {stat_name}: perm too coarse "
                           f"(n={dpos['n']}/{dneg['n']})")
        print(f"    {stat_name:<13} POS={dpos[dfield]:>7} NEG={dneg[dfield]:>7}  "
              f"diff={effect:+7.2f}pp  {pstr}")
        ledger.add(label, stat_name, h, dpos, dneg, p, effect, thin=False)


N_THIN: list[str] = []

# ================================================================================================
# HEADER + POINT-IN-TIME VERIFICATION
# ================================================================================================
print("=" * 100)
print("RS TRAJECTORY SHAPE — fall/stabilise/rise (and its 2nd-derivative form) vs the plain")
print("2-point sign, tested for a TAIL effect WITHIN narrow RS-level bands (his own floor")
print("objection as the primary test). 2026-08-16, read-only.")
print("=" * 100)
print(f"population: {len(ROWS)} distinct (ticker, alert_date) rows, "
      f"{len({r['d'] for r in ROWS})} sessions, {min(r['d'] for r in ROWS)} .. "
      f"{max(r['d'] for r in ROWS)}")
print(f"with point-in-time RS features: {len(FEAT)} ({len({r['d'] for r in FEAT})} sessions) — "
      "exclusions: " + ", ".join(f"{k}={v}" for k, v in excl.items()))
print("⚠ outcome values are FRACTIONS in the DB; printed x100 as real percents.")
print()
print("POINT-IN-TIME VERIFICATION (identical machinery to _rs_inflection_read.py):")
print("  - structural: features picked by bisect on score_date STRICTLY < alert_date.")
print(f"  - runtime: asserted score_date < alert_date on every one of the {len(FEAT)} feature rows.")
if lags:
    hist = defaultdict(int)
    for x in lags:
        hist[x] += 1
    print(f"  - feature-row lag before alert: min {min(lags)}d, max {max(lags)}d, distribution "
          + ", ".join(f"{k}d:{hist[k]}" for k in sorted(hist)))
print(f"  - staleness rule: rows lagging > {STALE_MAX_DAYS} calendar days excluded "
      f"({excl['stale_gt_7d']} rows).")

w20_ok = sum(1 for r in FEAT if r["slope_comp_20"] is not None)
w60_ok = sum(1 for r in FEAT if r["slope_comp_60"] is not None)
print(f"\nWINDOW FEASIBILITY (i-W>=0 AND calendar span <= TRAJ_GUARD[W]):")
print(f"  W=20 sessions (guard {TRAJ_GUARD[20]}d): {w20_ok} of {len(FEAT)} feature rows "
      f"({100*w20_ok/len(FEAT):.0f}%)")
print(f"  W=60 sessions (guard {TRAJ_GUARD[60]}d): {w60_ok} of {len(FEAT)} feature rows "
      f"({100*w60_ok/len(FEAT):.0f}%)")
print("  ⚠ mi_stock_scores was WEEKLY cadence before 2026-03-24 and near-daily after; a 20/60-")
print("    session window spanning the transition fails its own calendar guard and is excluded,")
print("    NOT silently included at the wrong cadence. This concentrates the richer-shape")
print("    population on alerts from roughly mid-2026-04 onward (60-session) / late-03 onward")
print("    (20-session) — stated once here, not re-derived per section.")

low = [r for r in FEAT if r["comp0"] < LOW_RS_PRIMARY]
print(f"\nlow-RS population (comp0 < {LOW_RS_PRIMARY:.0f}, same threshold as the 08-15/16 "
      f"probes): {len(low)} rows, {len({r['d'] for r in low})} sessions")
for lo, hi in BANDS:
    b = [r for r in low if lo <= r["comp0"] < hi]
    print(f"  band comp0[{lo:.0f},{hi:.0f}) : n={len(b)}  W20-feasible={sum(1 for r in b if r['slope_comp_20'] is not None)}  "
          f"W60-feasible={sum(1 for r in b if r['slope_comp_60'] is not None)}")

adr_n = sum(1 for r in FEAT if r["adr20"] is not None)
print(f"\nADR20 confound coverage: {adr_n} of {len(FEAT)} feature rows have a computable ADR20 "
      f"({len({r['ticker'] for r in FEAT if r['adr20'] is not None})} tickers) — the "
      "_ladder_daily.tsv 463-ticker overlap subset. Reported where it applies; not extrapolated.")

TOTAL_TESTS_START = 0

# ================================================================================================
# PART 1 — THE PRIMARY: predicted regime (falling_decel) vs REST, TAIL statistics, WITHIN
# narrow comp0 bands so "how close to the floor" is held constant across the comparison.
# ================================================================================================
print("\n" + "=" * 100)
print("PART 1 / PRIMARY — regime4_comp_20: falling_decel (predicted neglect precursor) vs the")
print("other 3 regimes pooled, TAIL statistics, WITHIN each narrow comp0 band. This is the test")
print("that settles Claim 3 (moot or real) — pre-registered before any cell below was read.")
print("=" * 100)
led_primary = ts.TailLedger("PART1-primary-regime-within-band")
w20pop = [r for r in low if r["regime4_comp_20"] is not None]
split_predicted = lambda r: (r["regime4_comp_20"] == "falling_decel")
run_within_bands(led_primary, "regime4_comp_20 falling_decel vs rest", w20pop, split_predicted,
                  ["max_high_20d", "max_high_5d"])
print(led_primary.bonferroni_summary())

print("\n--- [1b] SAME primary split, POOLED across bands (loses the floor-held-constant")
print("    property; reported ONLY as a companion read for dose-response, NOT the primary) ---")
led_pooled = ts.TailLedger("PART1b-primary-regime-pooled")
for h in ("max_high_20d", "max_high_5d"):
    m = mature(w20pop, h)
    pos = [r for r in m if split_predicted(r) is True and r.get(h) is not None]
    neg = [r for r in m if split_predicted(r) is False and r.get(h) is not None]
    print_tail_test(led_pooled, "falling_decel vs rest (POOLED, low-RS<50)", h, pos, neg)
print(led_pooled.bonferroni_summary())

print("\n--- [1c] NOT an independent robustness check (see agreement figure below) — same")
print("    within-band primary test on the RANK-based regime instead of comp-based ---")
led_rankcheck = ts.TailLedger("PART1c-primary-regime-rank-robustness")
w20pop_rank = [r for r in low if r["regime4_rank_20"] is not None]
agree = sum(1 for r in w20pop_rank if r.get("regime4_comp_20") == r["regime4_rank_20"])
print(f"  comp-based vs rank-based regime4 label AGREEMENT: {agree} of {len(w20pop_rank)} "
      f"({100*agree/len(w20pop_rank):.0f}%)" if w20pop_rank else "  (empty)")
if w20pop_rank and agree == len(w20pop_rank):
    print("  ⚠ 100% agreement means rs_rank is a MONOTONE TRANSFORM of rs_composite on each")
    print("    date (rank is very likely computed BY sorting composite) — the two regime labels")
    print("    are mechanically the same variable here, not independent evidence. This section")
    print("    is kept for completeness (it verifies the sign-flip wiring is correct) but is NOT")
    print("    counted as confirmation, and it inflates the global test count with zero new")
    print("    information — flagged explicitly at the grand ledger below.")
split_predicted_rank = lambda r: (r["regime4_rank_20"] == "falling_decel")
run_within_bands(led_rankcheck, "regime4_rank_20 falling_decel vs rest", w20pop_rank,
                  split_predicted_rank, ["max_high_20d"])
print(led_rankcheck.bonferroni_summary())

# ================================================================================================
# PART 2 — the SAME within-band design, using the FLAT-vs-FALLING classification (adds
# dispersion on top of slope) instead of the 2nd-derivative regime.
# ================================================================================================
print("\n" + "=" * 100)
print("PART 2 — flat_vs_falling_20: FLAT (stabilised) vs FALLING (still dropping), WITHIN")
print("narrow comp0 bands. This is his ORIGINAL wording (drop then stabilise) rather than the")
print("calculus form — do the two encodings say the same thing?")
print("=" * 100)
led2 = ts.TailLedger("PART2-flatfall-within-band")
ffpop = [r for r in low if r["flatfall_20"] in ("FLAT", "FALLING")]
split_ff = lambda r: (r["flatfall_20"] == "FLAT") if r["flatfall_20"] in ("FLAT", "FALLING") else None
run_within_bands(led2, "flatfall_20 FLAT vs FALLING", ffpop, split_ff, ["max_high_20d", "max_high_5d"])
print(led2.bonferroni_summary())

# ================================================================================================
# PART 3 — the SAME within-band design, using the plain 2-point sign already tested
# (rs_inflection_read.py's own primary feature) — the direct apples-to-apples comparator.
# ================================================================================================
print("\n" + "=" * 100)
print("PART 3 — infl16 (rs_1m - rs_6m) sign, WITHIN the SAME narrow comp0 bands, SAME")
print("population and horizons as Parts 1-2. Direct comparator: is the richer shape worth")
print("anything the plain sign didn't already carry?")
print("=" * 100)
led3 = ts.TailLedger("PART3-infl16-within-band")
inflpop = [r for r in low if r["infl16"] is not None]
split_infl = lambda r: (r["infl16"] > 0)
run_within_bands(led3, "infl16 sign > 0 vs <= 0", inflpop, split_infl, ["max_high_20d", "max_high_5d"])
print(led3.bonferroni_summary())

print("\n⚠ SINGLE-NAME CHECK on the largest raw hit above (band[30,40) P95 = +376.4%, n=61):")
_b3040 = [r for r in mature([r for r in inflpop if 30.0 <= r["comp0"] < 40.0 and r["infl16"] > 0],
                            "max_high_20d") if r.get("max_high_20d") is not None]
_b3040.sort(key=lambda r: r["max_high_20d"], reverse=True)
_top_tix = [r["ticker"] for r in _b3040[:5]]
print(f"  top-5 rows by max_high_20d in that cell: {[(r['ticker'], r['d']) for r in _b3040[:5]]}")
print(f"  {'SAME TICKER (SDOT) drives multiple of the top values — one episode logged as several'
      if len(set(_top_tix)) < len(_top_tix) else 'top-5 are distinct tickers'} "
      "candidate-days during its run, not independent winners; the P95/share hits in this cell"
      " overstate how many DISTINCT names produced the tail.")

print("\n--- [3b] APPLES-TO-APPLES: infl16 sign, restricted to the SAME W20-feasible rows Part 1")
print("    tests (slope_comp_20 is not None) — Part 1 vs Part 3 as originally run differ in N")
print("    because infl16 needs no 20-session window and survives the calendar guard that cuts")
print("    26% of Part 1's population. This equalizes N so the two features are compared on the")
print("    SAME rows, not just the same bands. ---")
led3b = ts.TailLedger("PART3b-infl16-within-band-w20matched")
inflpop_matched = [r for r in inflpop if r["slope_comp_20"] is not None]
print(f"  matched population: {len(inflpop_matched)} of {len(inflpop)} infl16-defined rows "
      f"(vs {len(w20pop)} for Part 1's regime population)")
run_within_bands(led3b, "infl16 sign > 0 vs <= 0 (W20-matched)", inflpop_matched, split_infl,
                  ["max_high_20d", "max_high_5d"])
print(led3b.bonferroni_summary())

# ================================================================================================
# PART 4 — DURATION AT THE BOTTOM: the feature that survives the floor BY CONSTRUCTION
# (population is already restricted to the bottom decile, so "how close to the floor" is held
# constant automatically — no banding needed for this one).
# ================================================================================================
print("\n" + "=" * 100)
print("PART 4 — DURATION in the bottom decile of rs_rank (rankpct0 >= 90), restricted to rows")
print("ALREADY there at the feature date — floor held constant by construction. Median split on")
print("duration (days), TAIL statistics. This is the feature the task says survives the floor.")
print("=" * 100)
bottom = [r for r in FEAT if r.get("dur_decile_days") is not None]
print(f"  bottom-decile population: {len(bottom)} rows, {len({r['d'] for r in bottom})} sessions "
      f"({sum(1 for r in bottom if r['dur_decile_censored'])} left-censored — the streak may "
      "predate our stored history, reported as a lower bound, not dropped)")
if bottom:
    durs = sorted(r["dur_decile_days"] for r in bottom)
    med_dur = st.median(durs)
    print(f"  duration (days) distribution: min={durs[0]} p25={ts.pct(durs,25):.0f} "
          f"median={med_dur:.0f} p75={ts.pct(durs,75):.0f} max={durs[-1]}")
    print(f"  ⚠ SPLIT CAVEAT: p25={ts.pct(durs,25):.0f}d means the median split below compares")
    print("    roughly '<=1 week at the bottom' vs '>1 week' — NOT the 'sat there three months")
    print("    vs fell there last week' contrast his hypothesis was actually about. A real test")
    print("    of that contrast needs a longer-tenure comparison group this data is too young")
    print("    (single ~6-month window) to populate at N; stated as a limitation, not a result.")
    led4 = ts.TailLedger("PART4-duration-bottom-decile")
    split_dur = lambda r: (r["dur_decile_days"] >= med_dur)
    for h in ("max_high_20d", "max_high_5d"):
        m = mature(bottom, h)
        pos = [r for r in m if split_dur(r) is True and r.get(h) is not None]
        neg = [r for r in m if split_dur(r) is False and r.get(h) is not None]
        print_tail_test(led4, f"duration >= median({med_dur:.0f}d) vs < median", h, pos, neg)
    print(led4.bonferroni_summary())

    print("\n--- [4b] IS DURATION JUST SLOPE WEARING A DIFFERENT NAME? Spearman vs slope_comp_20/60,")
    print("    plus a stratified check: within FALLING-only rows, does duration still separate ---")
    for W in (20, 60):
        pairs = [(r["dur_decile_days"], r[f"slope_comp_{W}"]) for r in bottom
                 if r[f"slope_comp_{W}"] is not None]
        rho = spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 10 else None
        print(f"  Spearman(duration_days, slope_comp_{W}) = "
              f"{f'{rho:+.3f}' if rho is not None else 'N too small'}  (n={len(pairs)})")
    falling_only = [r for r in bottom if r.get("flatfall_20") == "FALLING"]
    print(f"  STRATIFIED — rows classified FALLING at W=20 only (accel/slope held fixed-sign): "
          f"n={len(falling_only)}")
    if len(falling_only) >= 10:
        led4b = ts.TailLedger("PART4b-duration-within-falling-only")
        durs_f = sorted(r["dur_decile_days"] for r in falling_only)
        med_f = st.median(durs_f)
        split_dur_f = lambda r: (r["dur_decile_days"] >= med_f)
        for h in ("max_high_20d",):
            m = mature(falling_only, h)
            pos = [r for r in m if split_dur_f(r) is True and r.get(h) is not None]
            neg = [r for r in m if split_dur_f(r) is False and r.get(h) is not None]
            print_tail_test(led4b, f"[FALLING-only] duration >= median({med_f:.0f}d) vs <", h, pos, neg)
        print(led4b.bonferroni_summary())
    else:
        print("    N too thin to stratify (< 10 rows) — cannot test duration independent of slope"
              " within a fixed-slope-sign stratum.")

    print("\n--- [4c] duration in the bottom QUINTILE (rankpct0 >= 80), same design, wider population ---")
    bottom_q = [r for r in FEAT if r.get("dur_quintile_days") is not None]
    print(f"  bottom-quintile population: {len(bottom_q)} rows, "
          f"{sum(1 for r in bottom_q if r['dur_quintile_censored'])} left-censored")
    if bottom_q:
        durs_q = sorted(r["dur_quintile_days"] for r in bottom_q)
        med_q = st.median(durs_q)
        led4c = ts.TailLedger("PART4c-duration-bottom-quintile")
        split_dq = lambda r: (r["dur_quintile_days"] >= med_q)
        for h in ("max_high_20d",):
            m = mature(bottom_q, h)
            pos = [r for r in m if split_dq(r) is True and r.get(h) is not None]
            neg = [r for r in m if split_dq(r) is False and r.get(h) is not None]
            print_tail_test(led4c, f"duration >= median({med_q:.0f}d) vs < (quintile pop)", h, pos, neg)
        print(led4c.bonferroni_summary())
else:
    print("  EMPTY — no rows qualify (unexpected; check UNIV/rankpct0 wiring).")

# ================================================================================================
# PART 5 — THREE-PHASE COMPOSITE vs the plain 2-point sign, head-to-head, same population.
# ================================================================================================
print("\n" + "=" * 100)
print("PART 5 — three_phase (FALL 60 sessions AND FLAT last 20) vs infl16 sign, HEAD-TO-HEAD,")
print("same low-RS(<50) population, pooled AND within the deepest band. Is the richer shape")
print("worth anything over the simple sign already tested in 2026-08-15's probe?")
print("=" * 100)
tp_pop = [r for r in low if r["three_phase"] is not None and r["infl16"] is not None
          and r["chg_comp_60"] is not None]
print(f"  population with BOTH three_phase and infl16 defined: {len(tp_pop)} rows")
n_tp = sum(1 for r in tp_pop if r["three_phase"])
print(f"  three_phase fires on {n_tp} of {len(tp_pop)} ({100*n_tp/len(tp_pop):.1f}%)" if tp_pop else "")
led5 = ts.TailLedger("PART5-three-phase-vs-sign")
split_tp = lambda r: bool(r["three_phase"])
print("\n--- [5a] three_phase vs rest, POOLED (low-RS<50) ---")
for h in ("max_high_20d", "max_high_5d"):
    m = mature(tp_pop, h)
    pos = [r for r in m if split_tp(r) is True and r.get(h) is not None]
    neg = [r for r in m if split_tp(r) is False and r.get(h) is not None]
    print_tail_test(led5, "three_phase vs rest (POOLED)", h, pos, neg)
print("\n--- [5b] infl16 sign, SAME pooled population (apples-to-apples N) ---")
for h in ("max_high_20d", "max_high_5d"):
    m = mature(tp_pop, h)
    pos = [r for r in m if r["infl16"] > 0 and r.get(h) is not None]
    neg = [r for r in m if r["infl16"] <= 0 and r.get(h) is not None]
    print_tail_test(led5, "infl16 sign (SAME population, pooled)", h, pos, neg)
print("\n--- [5c] three_phase vs rest, WITHIN the deepest band [0,10) only (floor held constant) ---")
deepest = [r for r in tp_pop if 0.0 <= r["comp0"] < 10.0]
print(f"  deepest-band population: {len(deepest)}")
for h in ("max_high_20d",):
    m = mature(deepest, h)
    pos = [r for r in m if split_tp(r) is True and r.get(h) is not None]
    neg = [r for r in m if split_tp(r) is False and r.get(h) is not None]
    print_tail_test(led5, "three_phase vs rest (band [0,10) only)", h, pos, neg)
print(led5.bonferroni_summary())

# ================================================================================================
# PART 6 — REGIME REPORT: all 4 buckets, tail stats, POOLED low-RS<50 (the readable picture the
# operator asked for — is a wrong-direction prediction visible?). Also isolates the ACCEL effect
# by comparing same-slope-sign regimes against each other (falling_accel vs falling_decel; and
# rising_accel vs rising_decel) — does curvature add anything beyond slope alone?
# ================================================================================================
print("\n" + "=" * 100)
print("PART 6 — all 4 regimes (comp-based, W=20), tail statistics, POOLED low-RS<50. Then")
print("same-slope-sign head-to-heads to isolate what ACCELERATION adds over slope alone.")
print("=" * 100)
for reg in ("falling_accel", "falling_decel", "rising_accel", "rising_decel"):
    sub = mature([r for r in w20pop if r["regime4_comp_20"] == reg], "max_high_20d")
    vals = [r["max_high_20d"] * 100.0 for r in sub if r.get("max_high_20d") is not None]
    sess = {r["d"] for r in sub if r.get("max_high_20d") is not None}
    d = ts.describe_tail(vals, sess)
    print(f"  {reg:<15} {ts.fmt_bucket(d)}")

led6 = ts.TailLedger("PART6-accel-isolated-vs-slope")
print("\n--- [6a] WITHIN falling (slope<0): decel vs accel — does curvature add over slope sign? ---")
falling_pop = [r for r in w20pop if r["regime4_comp_20"] in ("falling_decel", "falling_accel")]
split_decel = lambda r: (r["regime4_comp_20"] == "falling_decel")
for h in ("max_high_20d", "max_high_5d"):
    m = mature(falling_pop, h)
    pos = [r for r in m if split_decel(r) is True and r.get(h) is not None]
    neg = [r for r in m if split_decel(r) is False and r.get(h) is not None]
    print_tail_test(led6, "[falling only] decel vs accel", h, pos, neg)
print("\n--- [6b] WITHIN rising (slope>=0): decel vs accel ---")
rising_pop = [r for r in w20pop if r["regime4_comp_20"] in ("rising_decel", "rising_accel")]
split_rdecel = lambda r: (r["regime4_comp_20"] == "rising_decel")
for h in ("max_high_20d", "max_high_5d"):
    m = mature(rising_pop, h)
    pos = [r for r in m if split_rdecel(r) is True and r.get(h) is not None]
    neg = [r for r in m if split_rdecel(r) is False and r.get(h) is not None]
    print_tail_test(led6, "[rising only] decel vs accel", h, pos, neg)
print(led6.bonferroni_summary())

# ================================================================================================
# PART 7 — CONFOUNDS: gap%, RS level (by construction via bands), ADR (subset), and the
# slope/duration/accel cross-correlations.
# ================================================================================================
print("\n" + "=" * 100)
print("PART 7 — CONFOUNDS")
print("=" * 100)
base = mature(low, "max_high_20d")
pos_pred = [r for r in base if r.get("regime4_comp_20") == "falling_decel"]
neg_pred = [r for r in base if r.get("regime4_comp_20") is not None and r["regime4_comp_20"] != "falling_decel"]
print("--- [7a] gap_pct: predicted bucket (falling_decel) vs rest, POOLED low-RS<50 ---")
gp = [r["gap"] for r in pos_pred if r.get("gap") is not None]
gn = [r["gap"] for r in neg_pred if r.get("gap") is not None]
if gp and gn:
    print(f"  median gap_pct: falling_decel {st.median(gp):.2f}%  (n={len(gp)})  vs rest "
          f"{st.median(gn):.2f}% (n={len(gn)})")
print("--- [7b] rs_composite LEVEL: median comp0 in each bucket, per band (should be ~equal WITHIN")
print("    a band by construction; printed as a sanity check the banding worked) ---")
for lo, hi in BANDS:
    bp = [r["comp0"] for r in pos_pred if lo <= r["comp0"] < hi]
    bn = [r["comp0"] for r in neg_pred if lo <= r["comp0"] < hi]
    if bp and bn:
        print(f"  band[{lo:.0f},{hi:.0f}) comp0 median: falling_decel {st.median(bp):.1f} "
              f"(n={len(bp)}) vs rest {st.median(bn):.1f} (n={len(bn)})")
print("--- [7c] ADR20 (subset with cached daily bars only) ---")
ap = [r["adr20"] for r in pos_pred if r.get("adr20") is not None]
an = [r["adr20"] for r in neg_pred if r.get("adr20") is not None]
if ap and an:
    print(f"  median ADR20%: falling_decel {st.median(ap):.2f}% (n={len(ap)}) vs rest "
          f"{st.median(an):.2f}% (n={len(an)})  [subset coverage only]")
else:
    print(f"  ADR20 subset too small on this split (falling_decel n={len(ap)}, rest n={len(an)})")
print("--- [7d] slope vs duration correlation already reported in [4b]; slope vs accel: ---")
pairs = [(r["slope_comp_20"], r["accel_comp_20"]) for r in FEAT
         if r["slope_comp_20"] is not None and r["accel_comp_20"] is not None]
rho = spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 10 else None
print(f"  Spearman(slope_comp_20, accel_comp_20) = "
      f"{f'{rho:+.3f}' if rho is not None else 'N too small'}  (n={len(pairs)}) — if strongly "
      "negative/positive, slope and curvature are not independent pieces of information.")

# ================================================================================================
# GRAND MULTIPLICITY LEDGER
# ================================================================================================
ALL_LEDGERS = [led_primary, led_pooled, led_rankcheck, led2, led3, led3b]
if bottom:
    ALL_LEDGERS.append(led4)
    if len(falling_only) >= 10:
        ALL_LEDGERS.append(led4b)
    if bottom_q:
        ALL_LEDGERS.append(led4c)
ALL_LEDGERS += [led5, led6]

print("\n" + "=" * 100)
print("GRAND MULTIPLICITY LEDGER — every tail-statistic test this probe ran, by section (each")
print("ledger is its OWN Bonferroni denominator, per house convention — never pooled across")
print("sections). A GLOBAL count and what survives a global correction follow.")
print("=" * 100)
total = 0
total_completed = 0
all_results = []
for led in ALL_LEDGERS:
    print(led.bonferroni_summary())
    total += led.attempted
    total_completed += led.completed
    all_results += [(led.name, r) for r in led.results]

sig_raw = [(n, r) for n, r in all_results if r["p"] is not None and r["p"] < 0.05]
sig_global = [(n, r) for n, r in all_results if r["p"] is not None and r["p"] * total < 0.05]
print(f"\nTOTAL TAIL TESTS ATTEMPTED THIS PROBE: {total} ({total_completed} produced a p, "
      f"{total - total_completed} were N-too-thin or too coarse)")
print(f"raw p<0.05 across ALL sections: {len(sig_raw)}"
      + (" — " + "; ".join(f"{n}/{r['label']}/{r['stat']} (p={r['p']:.3f})" for n, r in sig_raw)
         if sig_raw else ""))
print(f"surviving a GLOBAL Bonferroni x{total} across every test this probe ran: {len(sig_global)}"
      + (" — " + "; ".join(f"{n}/{r['label']}/{r['stat']}" for n, r in sig_global)
         if sig_global else " — NONE. Within-probe (per-section) survival, printed above per"
                             " ledger, is the defensible convention this program uses; the global"
                             " figure is reported for full disclosure, per house rigor rules."))
print(f"\nN-THIN / TOO-COARSE CELLS: {len(N_THIN)} of {total} ({100*len(N_THIN)/total:.0f}%)")
for line in N_THIN:
    print(f"  - {line}")

print("\n" + "=" * 100)
print("HOW TO READ THIS — the within-band tests (Parts 1, 3b) are the PRIMARY answer to 'is this")
print("moot because the tail can't go lower': if the predicted bucket separates the tail INSIDE")
print("a band (comp0 held to a 10-point range), the floor is not the whole explanation. Parts")
print("1b/6 report pooled/regime pictures for readability only — they do NOT hold the floor")
print("constant and are not the verdict on Claim 3. Part 1c is NOT independent evidence (100%")
print("mechanical agreement with Part 1's comp-based labels) — its 20 tests inflate the grand")
print("total with zero new information; read Part 1's verdict alone for the primary question.")
print("TWO DISTINCT 'moot' QUESTIONS, not one: (a) does his literal 'drop then stabilise' shape")
print("even OCCUR near the floor — answered by Part 2 (FLAT fires on ~1% of low-RS rows: it")
print("essentially never happens, which is a finding about the PREMISE, not about the floor);")
print("(b) WHERE trajectory shape IS measurable (the accel/decel regimes, well-populated, not")
print("mechanically collapsed — Spearman(slope,accel) ~ 0), does it separate the tail — answered")
print("NO by Part 1/3b within-band. THE LINE: measurement only; nothing here is wired into any")
print("grade, admission rule, sizing, or exit. A result that points at a change is a FORK for")
print("the operator, stated with no option pre-chosen.")
print("=" * 100)
