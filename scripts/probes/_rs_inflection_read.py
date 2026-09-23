#!/usr/bin/env python3
"""RS INFLECTION within the LOW-RS alert population — does IMPROVEMENT (not level)
predict forward outcome?  (READ-ONLY; STUDY ONLY; no writes, no trading, no LLM spend)

THE HYPOTHESIS (operator 2026-08-15, verbatim): "on RS, RS improvement may be a
factor for ones that don't have high RS, that can be similar to neglect that's
coming back up."  The scope restriction is PART of the claim: the test population
is alerts on names that do NOT already have high relative strength.  Context:
ep_profitability_program.md §2026-08-15 "RS IMPROVEMENT, not RS level" — the 08-04
board (n=11, one winner) illustrated that rs_1m − rs_6m orders the board opposite
to RS level; this probe is the $0 distribution-level test that section calls for.

PRE-REGISTERED PRIMARY TEST — written before any outcome was looked at:
  POPULATION  every DISTINCT (ticker, alert_date) row of mi_ep_missed_outcomes
              (the full logged candidate stream, ~2.9k ticker-days since 2026-02-11)
              whose point-in-time RS features exist (see POINT-IN-TIME below),
              restricted to LOW-RS = rs_composite < 50 at the feature row.
              50 is the percentile scale's own midpoint = "not already high RS";
              chosen on principle, NOT tuned; a sensitivity strip at 30/40/60/70
              is printed so a knife-edge would be visible.
  FEATURE     infl_1m6m = rs_1m − rs_6m (both are 0-100 percentile ranks; positive
              = the shortest lookback is the strongest = "coming back up").
  BUCKETS     positive (infl_1m6m > 0) vs non-positive (<= 0).  Sign split per the
              plan doc's own framing; zero goes to non-positive.
  OUTCOME     ret_5d (DB stores FRACTIONS; printed x100), maturity-filtered.
  STATISTIC   difference in bucket MEDIANS; significance by SESSION-level
              permutation (whole alert-days shuffled, 20,000 perms, seed 20260815)
              because alerts on one morning share the tape and are not
              independent draws.  N and distinct sessions printed per bucket.

MULTIPLE COMPARISONS — the make-or-break rigor point.  This probe runs a FIXED,
pre-declared battery of 17 permutation tests (1 primary + 16 exploratory):
    1  PRIMARY   low-RS(<50) · infl_1m6m sign · ret_5d
    4  sensitivity: thresholds 30/40/60/70 · same feature · ret_5d
    4  horizons at the primary threshold: ret_1d, ret_20d, max_high_5d, max_high_20d
    2  scope check: same test in HIGH-RS (>=50) and in ALL alerts (does the
       restriction matter — the operator's claim implies low-RS-specific signal)
    5  secondary features in low-RS · ret_5d: infl_1m3m = rs_1m − rs_3m;
       rank-percentile improvement over the prior 5 / 10 / 20 sessions;
       flat-then-jumped flag
    1  alert-grade subset (rows that passed the scan-stage filters) · primary test
Every test is counted; the primary is reported with its RAW permutation p AND a
Bonferroni adjustment across all 17 attempted tests (conservative — strictly the
pre-registration shields the primary, but the operator's bar is separation from
chance, so both are printed and the ADJUSTED one governs the verdict).  A result
that only survives unadjusted is reported as NOT surviving.  Everything beyond
the primary is labelled EXPLORATORY in the output.

POINT-IN-TIME, STRICTLY — how lookahead is excluded and how that is verified:
  Features come from the ticker's most recent mi_stock_scores row with
  score_date STRICTLY BEFORE alert_date (scores are written nightly post-close,
  so the alert-day row already contains the gap-day move and is never used).
  Enforcement is structural (bisect on score_date < alert_date) AND asserted at
  runtime for every feature row used, with the lag distribution printed.
  Staleness rule (pre-registered): the feature row must be within 7 calendar
  days before the alert, else the alert is EXCLUDED (scores were weekly-cadence
  before 2026-03-24; a 7-day-stale feature is stale but never lookahead).

TRAJECTORY FEATURES (exploratory) — defined point-in-time on the ticker's own
stored score-date series (dates with a near-empty snapshot, <500 rows, dropped):
  rank_pct(d)   = rs_rank / (that date's stored-universe row count) x 100 —
                  normalized because the stored universe size changed
                  (~9.7k weekly -> ~3.9k daily -> ~2.45k daily); raw rank changes
                  are not comparable across those boundaries.
  rank_chg_k    = rank_pct(k sessions back) − rank_pct(feature row); positive =
                  improved.  Calendar guard: the k-back row must be within
                  {5: 12, 10: 20, 20: 36} calendar days of the feature row
                  (~1.6x trading-to-calendar plus holiday slack) else undefined.
  flat_jump     = (rank_chg_5 >= 5 points of universe) AND (rank_pct range over
                  sessions t-20..t-5 <= 10 points).  Constants chosen a priori
                  (5 pts ~ half a decile of the universe), not tuned.

CONFOUND CHECK (descriptive, not counted as tests): Spearman correlation of
infl_1m6m with gap_pct, ep_score, catalyst_quality (ordinal: game_changer 3,
strong/mna 2, routine 1), and with rs_composite itself, within the analyzed
low-RS population.  If |rho| is high the test cannot separate inflection from
that variable on this data, and the output says so.

KNOWN LIMITS, stated up front:
  - The stored score universe is FILTERED (~2.4-3.9k of ~9.7k names recently);
    an alert ticker absent from the prior night's stored set has no feature and
    drops out.  Exclusion counts are printed; the surviving "low-RS" population
    is low-RS WITHIN the stored (liquidity-filtered) universe, not the bottom of
    the whole market.
  - rs_rank is a rank WITHIN the stored set (max rank == row count per date) —
    hence the rank_pct normalization above.  NOTE: this contradicts the plan
    doc's "rank 2230/9,700" framing for PLTR (denominator that night was ~2,415).
  - ep_score is populated on only ~26% of outcome rows and catalyst_quality on
    ~26% — the confound read against those two runs on that subset, N stated.
  - Outcomes exist only for the tickers the scan logged; nothing here says how
    the feature behaves on names the scan never surfaced.
  - mi_ep_missed_outcomes holds NON-ENTERED names only — the ~20 entered live
    positions (incl. PLTR, the motivating case) are absent (verified post-run:
    PLTR/LIFE have no rows; AMRC does).  ~20 of ~2,960 candidate-days, so the
    distribution read stands, but the one labelled winner is not in this data.

WHAT WOULD MAKE THIS CONCLUSIVE (operator 2026-08-15: "i won't say it's
conclusive yet until we can truly separate noise and chance with real alpha,
though the data can still be informative"): (a) the PRIMARY surviving the
session-level permutation AFTER the x17 Bonferroni adjustment; (b) the same sign
across the sensitivity strip (no knife-edge); (c) an effect not explained by the
confound correlations.  A null is a real deliverable — it saves building a
feature that does not work.  THE LINE: this probe measures; it changes no grade,
admission rule, sizing, or exit.  If the result suggests one, that is a FORK for
the operator, stated with no option pre-chosen.

Inputs (captured ONCE from prod 2026-08-15, COST EFFICIENCY rule — never re-pull):
  _rsinfl_outcomes.tsv  DISTINCT ON (ticker, alert_date) mi_ep_missed_outcomes
  _rsinfl_scores.tsv    mi_stock_scores history for every outcome ticker
  _rsinfl_totals.tsv    per-score_date stored-universe row counts
Output captured once to docs/analysis/rs_inflection_read_2026-08-15.txt.
"""
from __future__ import annotations

import os
import random
import statistics as st
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

if os.environ.get("APOLLO_PROBE_WRITE"):
    sys.exit("this probe is read-only by design")

HERE = Path(__file__).resolve().parent
SEED = 20260815
N_PERM = 20000
PLANNED_TESTS = 17
LOW_RS_PRIMARY = 50.0
SENSITIVITY = [30.0, 40.0, 60.0, 70.0]
MATURITY_DAYS = {"ret_1d": 2, "ret_5d": 8, "ret_20d": 30, "max_high_5d": 8, "max_high_20d": 30}
STALE_MAX_DAYS = 7
TRAJ_GUARD = {5: 12, 10: 20, 20: 36}
MIN_UNIVERSE_ROWS = 500
# scan-stage rejects (never reached alert grade) vs everything that did
SCAN_STAGE = {"outside_top20", "session_rvol_low", "score_below_50", "adv_low",
              "mcap_low", "pm_rvol_low", ""}
CAT_ORD = {"game_changer": 3.0, "strong": 2.0, "mna": 2.0, "routine": 1.0}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


# ---------------- load ----------------
UNIV: dict[str, int] = {}
for ln in (HERE / "_rsinfl_totals.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) == 2 and p[1].isdigit() and int(p[1]) >= MIN_UNIVERSE_ROWS:
        UNIV[p[0]] = int(p[1])

SCORES: dict[str, list[tuple]] = defaultdict(list)  # ticker -> [(date_str, rs1, rs3, rs6, comp, rank)]
for ln in (HERE / "_rsinfl_scores.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 7:
        continue
    t, d = p[0], p[1]
    if d not in UNIV:                     # near-empty snapshot dates carry no usable rank
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

# ---------------- point-in-time features ----------------
excl = {"no_score_history": 0, "no_row_before_alert": 0, "stale_gt_7d": 0, "null_fields": 0}
lags: list[int] = []
for r in ROWS:
    r["feat"] = False
    ser = SCORES.get(r["ticker"])
    if not ser:
        excl["no_score_history"] += 1
        continue
    dates = [x[0] for x in ser]
    i = bisect_left(dates, r["d"]) - 1    # last index with score_date STRICTLY < alert_date
    if i < 0:
        excl["no_row_before_alert"] += 1
        continue
    d0, rs1, rs3, rs6, comp, rank = ser[i]
    assert d0 < r["d"], f"LOOKAHEAD: {r['ticker']} feature {d0} !< alert {r['d']}"
    lag = (pdate(r["d"]) - pdate(d0)).days
    if lag > STALE_MAX_DAYS:
        excl["stale_gt_7d"] += 1
        continue
    if None in (rs1, rs6, comp):
        excl["null_fields"] += 1
        continue
    lags.append(lag)
    r["feat"] = True
    r["comp"] = comp
    r["infl16"] = rs1 - rs6
    r["infl13"] = (rs1 - rs3) if rs3 is not None else None
    r["rankpct"] = 100.0 * rank / UNIV[d0] if rank is not None else None
    # trajectory features (exploratory)
    for k in (5, 10, 20):
        r[f"rchg{k}"] = None
        j = i - k
        if j >= 0 and r["rankpct"] is not None:
            dk, *_rest, rank_k = ser[j]
            if rank_k is not None and (pdate(d0) - pdate(dk)).days <= TRAJ_GUARD[k]:
                r[f"rchg{k}"] = (100.0 * rank_k / UNIV[dk]) - r["rankpct"]
    r["flatjump"] = None
    if r["rchg5"] is not None and i - 20 >= 0:
        d20 = ser[i - 20][0]
        if (pdate(d0) - pdate(d20)).days <= TRAJ_GUARD[20]:
            win = [100.0 * ser[j][5] / UNIV[ser[j][0]]
                   for j in range(i - 20, i - 4) if ser[j][5] is not None]
            if len(win) >= 12:
                r["flatjump"] = 1 if (r["rchg5"] >= 5.0 and max(win) - min(win) <= 10.0) else 0

FEAT = [r for r in ROWS if r["feat"]]


# ---------------- stats machinery (house pattern) ----------------
TESTS_ATTEMPTED = 0
TESTS_COMPLETED = 0
RESULTS: list[dict] = []


def mature(rows: list[dict], h: str) -> list[dict]:
    cutoff = DATA_MAX - timedelta(days=MATURITY_DAYS[h])
    return [r for r in rows if pdate(r["d"]) <= cutoff]


def describe(rows: list[dict], h: str) -> dict:
    vals = [r[h] * 100.0 for r in rows if r[h] is not None]
    sess = {r["d"] for r in rows if r[h] is not None}
    if not vals:
        return {"n": 0, "sessions": 0, "median": None, "pct_positive": None}
    return {"n": len(vals), "sessions": len(sess), "median": round(st.median(vals), 2),
            "pct_positive": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1)}


def perm_p(a, b, sess_a, sess_b) -> float | None:
    """Permutation on difference in MEDIANS, shuffling whole SESSIONS (house pattern)."""
    by_sess: dict[str, list[float]] = defaultdict(list)
    for v, s in zip(a, sess_a):
        by_sess[s].append(v)
    for v, s in zip(b, sess_b):
        by_sess[s].append(v)
    sessions = sorted(by_sess)
    n_a = len(a)
    if n_a < 5 or len(b) < 5 or len(sessions) < 6:
        return None
    obs = st.median(a) - st.median(b)
    rng = random.Random(SEED)
    counts = [len(by_sess[s]) for s in sessions]
    pool = [by_sess[s] for s in sessions]
    hits = 0
    for _ in range(N_PERM):
        idx = list(range(len(sessions)))
        rng.shuffle(idx)
        take, got = set(), 0
        for i in idx:
            if got >= n_a:
                break
            take.add(i)
            got += counts[i]
        pa = [v for i in take for v in pool[i]]
        pb = [v for i in range(len(sessions)) if i not in take for v in pool[i]]
        if not pa or not pb:
            continue
        if abs(st.median(pa) - st.median(pb)) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def run_test(name: str, kind: str, pop: list[dict], split, h: str) -> dict:
    """split(r) -> True (bucket POS), False (bucket NEG), None (excluded)."""
    global TESTS_ATTEMPTED, TESTS_COMPLETED
    TESTS_ATTEMPTED += 1
    m = mature(pop, h)
    pos = [r for r in m if split(r) is True and r[h] is not None]
    neg = [r for r in m if split(r) is False and r[h] is not None]
    dp, dn = describe(pos, h), describe(neg, h)
    p = perm_p([r[h] * 100 for r in pos], [r[h] * 100 for r in neg],
               [r["d"] for r in pos], [r["d"] for r in neg])
    if p is not None:
        TESTS_COMPLETED += 1
    eff = (dp["median"] - dn["median"]) if (dp["median"] is not None and dn["median"] is not None) else None
    res = dict(name=name, kind=kind, h=h, pos=dp, neg=dn, effect=eff, p=p)
    RESULTS.append(res)
    return res


def fmt(res: dict, bonf: int | None = None) -> str:
    dp, dn = res["pos"], res["neg"]
    if not dp["n"] or not dn["n"]:
        return f"  {res['name']:<46} EMPTY BUCKET (pos n={dp['n']}, neg n={dn['n']})"
    ps = "N too small for permutation" if res["p"] is None else f"raw p={res['p']:.3f}"
    if bonf and res["p"] is not None:
        ps += f"  adj p(x{bonf})={min(1.0, res['p'] * bonf):.3f}"
    return (f"  {res['name']:<46} POS med {dp['median']:>6}% (n={dp['n']}, {dp['sessions']} sess, "
            f"{dp['pct_positive']}% up) | NEG med {dn['median']:>6}% (n={dn['n']}, {dn['sessions']} sess, "
            f"{dn['pct_positive']}% up) | diff {res['effect']:+.2f}pp | {ps}")


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 10:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k2 in range(i, j + 1):
                rk[order[k2]] = avg
            i = j + 1
        return rk

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.fmean(rx), st.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


# ---------------- header + verification ----------------
print("=" * 98)
print("RS INFLECTION IN THE LOW-RS ALERT POPULATION — improvement, not level  "
      "(capture 2026-08-15, read-only)")
print("=" * 98)
print(f"population: {len(ROWS)} distinct (ticker, alert_date) outcome rows, "
      f"{len({r['d'] for r in ROWS})} sessions, "
      f"{min(r['d'] for r in ROWS)} .. {max(r['d'] for r in ROWS)}")
print(f"with point-in-time RS features: {len(FEAT)} "
      f"({len({r['d'] for r in FEAT})} sessions) — exclusions: "
      + ", ".join(f"{k}={v}" for k, v in excl.items()))
print("⚠ outcome values are FRACTIONS in the DB; printed x100 as real percents.")
print("⚠ each horizon drops alerts too recent for the horizon to have elapsed "
      "(maturity filter vs data max " + str(DATA_MAX) + ").")
print()
print("POINT-IN-TIME VERIFICATION (lookahead would invalidate the whole read):")
print("  - structural: features picked by bisect on score_date STRICTLY < alert_date;")
print("    nightly scores mean the alert-day row holds the gap-day move — never used.")
print("  - runtime: asserted score_date < alert_date on every one of the "
      f"{len(FEAT)} feature rows (a violation raises).")
if lags:
    hist = defaultdict(int)
    for x in lags:
        hist[x] += 1
    print(f"  - feature-row lag before alert: min {min(lags)}d, max {max(lags)}d, "
          "distribution " + ", ".join(f"{k}d:{hist[k]}" for k in sorted(hist)))
print(f"  - staleness rule: rows lagging > {STALE_MAX_DAYS} calendar days excluded "
      f"({excl['stale_gt_7d']} rows; scores were weekly before 2026-03-24).")

low = [r for r in FEAT if r["comp"] < LOW_RS_PRIMARY]
high = [r for r in FEAT if r["comp"] >= LOW_RS_PRIMARY]
print(f"\nlow-RS population (rs_composite < {LOW_RS_PRIMARY:.0f}, the pre-registered threshold): "
      f"{len(low)} rows over {len({r['d'] for r in low})} sessions; "
      f"high-RS complement: {len(high)}")

sgn = lambda r: (r["infl16"] > 0) if r["infl16"] is not None else None

# ---------------- PRIMARY ----------------
print("\n" + "=" * 98)
print("PRIMARY (pre-registered): low-RS · rs_1m − rs_6m positive vs non-positive · 5-day forward return")
print("=" * 98)
pri = run_test(f"PRIMARY low-RS(<{LOW_RS_PRIMARY:.0f}) infl_1m6m ret_5d", "primary", low, sgn, "ret_5d")
print(fmt(pri, bonf=PLANNED_TESTS))
print(f"  (POS = RS improving into the alert; NEG = not. adj p = Bonferroni across all "
      f"{PLANNED_TESTS} attempted tests — the adjusted p governs the verdict.)")

# ---------------- EXPLORATORY ----------------
print("\n" + "-" * 98)
print("EXPLORATORY 1 — sensitivity strip: same test at other low-RS thresholds (is the primary a knife-edge?)")
print("-" * 98)
for th in SENSITIVITY:
    sub = [r for r in FEAT if r["comp"] < th]
    print(fmt(run_test(f"low-RS(<{th:.0f}) infl_1m6m ret_5d", "sens", sub, sgn, "ret_5d")))

print("\n" + "-" * 98)
print("EXPLORATORY 2 — other horizons at the primary threshold")
print("-" * 98)
for h in ("ret_1d", "ret_20d", "max_high_5d", "max_high_20d"):
    print(fmt(run_test(f"low-RS(<50) infl_1m6m {h}", "horizon", low, sgn, h)))

print("\n" + "-" * 98)
print("EXPLORATORY 3 — scope check: does the restriction matter? (claim implies signal lives in LOW-RS)")
print("-" * 98)
print(fmt(run_test("HIGH-RS(>=50) infl_1m6m ret_5d", "scope", high, sgn, "ret_5d")))
print(fmt(run_test("ALL alerts infl_1m6m ret_5d", "scope", FEAT, sgn, "ret_5d")))

print("\n" + "-" * 98)
print("EXPLORATORY 4 — secondary features within low-RS, ret_5d")
print("-" * 98)
print(fmt(run_test("low-RS infl_1m3m (rs_1m − rs_3m)", "secondary", low,
                   lambda r: (r["infl13"] > 0) if r["infl13"] is not None else None, "ret_5d")))
for k in (5, 10, 20):
    print(fmt(run_test(f"low-RS rank-pct improved over prior {k} sessions", "secondary", low,
                       lambda r, k=k: (r[f"rchg{k}"] > 0) if r[f"rchg{k}"] is not None else None,
                       "ret_5d")))
n_fj = sum(1 for r in low if r["flatjump"] == 1)
print(fmt(run_test("low-RS flat-then-jumped flag", "secondary", low,
                   lambda r: bool(r["flatjump"]) if r["flatjump"] is not None else None, "ret_5d")))
print(f"  (flat-then-jumped fired on {n_fj} low-RS rows; definition and a-priori constants in docstring)")

print("\n" + "-" * 98)
print("EXPLORATORY 5 — alert-grade subset (rows that passed scan-stage filters; decision-surface population)")
print("-" * 98)
ag = [r for r in low if r["skipcat"] not in SCAN_STAGE]
print(f"  alert-grade low-RS rows: {len(ag)} of {len(low)}")
print(fmt(run_test("alert-grade low-RS infl_1m6m ret_5d", "subset", ag, sgn, "ret_5d")))

# ---------------- multiplicity ledger ----------------
print("\n" + "=" * 98)
print(f"MULTIPLICITY LEDGER — {TESTS_ATTEMPTED} tests attempted (planned {PLANNED_TESTS}), "
      f"{TESTS_COMPLETED} produced a p")
print("=" * 98)
assert TESTS_ATTEMPTED == PLANNED_TESTS, "battery drifted from pre-registration"
sig_raw = [r for r in RESULTS if r["p"] is not None and r["p"] < 0.05]
sig_adj = [r for r in RESULTS if r["p"] is not None and r["p"] * PLANNED_TESTS < 0.05]
print(f"  raw p<0.05: {len(sig_raw)} of {TESTS_COMPLETED}"
      + (" — " + "; ".join(f"{r['name']} (p={r['p']:.3f})" for r in sig_raw) if sig_raw else ""))
print(f"  surviving Bonferroni x{PLANNED_TESTS} (adj p<0.05): {len(sig_adj)}"
      + (" — " + "; ".join(r["name"] for r in sig_adj) if sig_adj else ""))
print(f"  expected false positives at raw 0.05 across {TESTS_COMPLETED} tests: "
      f"~{0.05 * TESTS_COMPLETED:.1f} — a lone raw hit is what chance produces.")

# ---------------- confound check ----------------
print("\n" + "-" * 98)
print("CONFOUND CHECK (descriptive) — is infl_1m6m just a proxy for gap size, ep_score, catalyst, or level?")
print("-" * 98)
base = mature(low, "ret_5d")
for label, get in [("gap_pct", lambda r: r["gap"]),
                   ("ep_score", lambda r: r["ep_score"]),
                   ("catalyst_quality (ordinal)", lambda r: CAT_ORD.get(r["cq"])),
                   ("rs_composite (level)", lambda r: r["comp"])]:
    pairs = [(r["infl16"], get(r)) for r in base if get(r) is not None and r["infl16"] is not None]
    rho = spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 10 else None
    rs = f"rho={rho:+.2f}" if rho is not None else "N too small"
    print(f"  infl_1m6m vs {label:<28} n={len(pairs):>4}  Spearman {rs}")
pos_g = [r["gap"] for r in base if sgn(r) is True and r["gap"] is not None]
neg_g = [r["gap"] for r in base if sgn(r) is False and r["gap"] is not None]
if pos_g and neg_g:
    print(f"  median gap_pct: POS bucket {st.median(pos_g):.1f} vs NEG bucket {st.median(neg_g):.1f}"
          " — if far apart, the buckets differ in gap, not just RS trajectory.")
print("  reading: |rho| >= ~0.4 would mean this data cannot separate inflection from that variable.")

print("\n" + "=" * 98)
print("HOW TO READ THIS — the permutation shuffles whole SESSIONS (alerts on one morning share")
print("the tape). The verdict rests on the PRIMARY's ADJUSTED p; exploratory lines generate")
print("hypotheses only. The population is low-RS WITHIN the stored, liquidity-filtered universe")
print("(~2.4-3.9k names), not the whole market. Nothing here licenses a change to grading,")
print("admission, sizing, or exits — THE LINE; any suggested change is a FORK for the operator.")
print("=" * 98)
