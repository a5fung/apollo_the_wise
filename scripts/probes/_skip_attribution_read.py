#!/usr/bin/env python3
"""SKIP-REASON ATTRIBUTION — does each decline reason drop names that RAN, or
names that died?  (READ-ONLY; STUDY ONLY; no writes, no trading, no LLM spend)

Step 4 of The Real EP Plan (docs/roadmap/ep_profitability_program.md, "§1b step
4" / "Skip-reason attribution" line, the week's declared lead target 2026-08-15).

THE QUESTION (operator, standing scope rule 2026-08-12, verbatim): "don't just
look at what we traded, also look at all the EPs we detected but didn't trade
for whatever reason, that's the whole group to review." Every `skip_reason` is
a decision the system made. This probe pairs each reason with what the name
went on to DO. A reason that consistently drops names that ran is a candidate
defect; a reason that consistently drops names that died is working. The
canonical motivating case: SE (2026-08-11), skipped on the gap floor at 9.2% vs
a 10% floor, reclaimed to +10.5% four minutes later.

POPULATION = every row of mi_ep_missed_outcomes (non-entered names only, this
is the whole "detected but not traded" population by construction) since
2026-02-11, N=3,224. BENCHMARK = the names we actually took: mi_live_trades,
account_mode='live', status IN ('closed', 'filled') — actually filled
positions, N=22, spanning 2026-07-06 .. 2026-08-14. ('skipped' mi_live_trades
rows are already inside mi_ep_missed_outcomes' high_unentered source;
'cancelled' rows were submitted but never filled — not "taken" — excluded from
the benchmark and NOT separately analyzed here, noted as a limit below.)

CALENDAR MATCH — load-bearing, added after first-draft review caught it before
any number was reported to the operator. The skip population runs 2026-02-11
.. 2026-08-14 (116 sessions); the taken benchmark only exists 2026-07-06 ..
2026-08-14 (15 sessions). A skip-vs-taken diff computed against the FULL skip
window is not a reason effect — it is part reason, part "is Jul-Aug a
different tape than Feb-Jun." It also breaks the permutation test's own
assumption: perm_p assigns whole SESSIONS to a pseudo-"taken" group to build
the null, which requires the two cohorts' sessions to be exchangeable: a
February session can never actually be a "taken" session (no fills exist that
day), so pooling Feb-Jun skip sessions into the permutation pool is not just
underpowered, it is answering a different question than "did this reason
differ from what we did instead."
  FIX: MATCH_START = the taken cohort's own earliest date (2026-07-06,
  computed from data, not hardcoded). ALL 54 tests in the battery below run on
  skip rows with alert_date >= MATCH_START only (781 of 3,224 rows, 24%). The
  full Feb-Aug window is reported ALONGSIDE, per reason, labelled CONFOUNDED —
  CONTEXT ONLY, exactly the pooled-vs-banded shape _grade_override_outcome_read.py
  uses for its own confound (gap-band vs override). It is never fed to a
  permutation test and never governs a verdict.

PRE-REGISTERED PRIMARY TEST (declared before any outcome/return was looked at
— the reason taxonomy below was built from skip_reason TEXT only, never from
ret_1d/5d/20d/max_high_5d/20d, which were not queried until after this section
was written):
  Does `setup:gap_below_floor` (the SELECTION-kind reason the operator named as
  the motivating case) drop names whose 5-day forward return is BETTER than the
  names we took?
  POPULATION  skip_reason ILIKE 'setup:gap_below_floor%' (nested inside the DB's
              'setup_other' skip_category — see REASON TAXONOMY below), date-
              matched (>= MATCH_START — moot here: all 7 rows on record already
              fall 2026-08-06..08-14, i.e. this reason has only existed inside
              the matched window; it never appears earlier), vs the taken-names
              benchmark.
  OUTCOME     ret_5d (DB stores FRACTIONS; printed x100), maturity-filtered.
  STATISTIC   difference in MEDIANS; significance by SESSION-level permutation
              (whole alert-days shuffled, 20,000 perms, seed 20260815) — same
              house pattern as _grade_override_outcome_read.py and
              _rs_inflection_read.py, because alerts on one morning share the
              tape and are not independent draws.
  ⚠ KNOWN GOING IN: this reason has N=7 rows total, ALL within the last 9
  calendar days of the capture window — it is a NEW reason, not a mature one.
  The operator's own evidence rule says a single skipped name that ran proves
  nothing; N=7 spanning 6 sessions is barely above that floor before maturity
  filtering even starts cutting it. Disclosed BEFORE running it, not after
  seeing a null. The honest read of a result this thin is "too new to tell,"
  not "no effect" — reported that way below, gated on N>=10 mature rather than
  a date (same convention the rest of the house uses).

REASON TAXONOMY — built from the code's own classifier
(agents/market_intelligence/missed_outcomes.py::_categorize_skip_reason and its
SQL-side mirror), NOT invented for this probe. The DB's 21 skip_category values
collapse 'setup_other' (a catch-all, N=14) into its 4 distinct setup: prefixes
by parsing skip_reason text (still done BEFORE any outcome was queried) —
giving 24 distinct "reasons" total. Kind assignment follows the task's own
examples where a category matches one; ambiguous ones are assigned by what the
reason actually gates (read from a sample of its real skip_reason text, listed
inline):
  MECHANICS      window_missed, infra_skip, duplicate_scan, faded_from_orb,
                 zero_range (setup:zero_range — degenerate ORB bar, not a
                 judgement call)
  SELECTION      outside_top20, session_rvol_low, score_below_50, adv_low,
                 mcap_low, pm_rvol_low, extension_gate ("already up N% in
                 prior 5 days"), catalyst_downgrade, ma_filter, moderate_tier
                 (the grade engine's own tier judgement), gap_below_floor
  RISK GEOMETRY  stop_too_wide, atr_high ("filter:atr_too_high: N% > 15.0%" —
                 same stop-distance domain as stop_too_wide, pre-scan instead
                 of post-ORB), size_too_small (<1 share after sizing),
                 price_exceeds_cap (price > 20% of position cap — the closest
                 analog on record to "chase_cap_exceeded"; that literal string
                 does not appear in the data, noted as a limit)
  PORTFOLIO      cooldown, breaker_blocked, cap_blocked
  OTHER          high_unentered (N=289 wide, but only 2 of those fall inside
                 the date-matched window — see caveat below; a HIGH alert with
                 NO logged skip_reason at all; the code only falls through to
                 this bucket when none of the block:/window:/setup:/infra:
                 prefixes matched, so this is genuinely unattributed, not a
                 mechanics guess dressed up)
  `setup:chase_cap_exceeded` from the task's own example list has zero rows in
  the data under that literal name; price_exceeds_cap is reported in its place
  and flagged as such everywhere it appears.

NAMED CAVEATS ON SPECIFIC REASONS (found while building the date-matched read;
each restated inline where the reason is printed, not just here):
  - window_missed: 55 rows wide, only 3 of them AFTER 2026-08-13 (the ORB
    submission-window bug fix the plan doc records as "fixed 08-13, verified
    clean 08-14"). The 23 date-matched rows are mostly PRE-fix. Any signal on
    this reason is describing a bug that has already been fixed, not the
    go-forward mechanics leak — reported explicitly, not left to be misread as
    current.
  - moderate_tier: this exact question (does MODERATE≈HIGH on raw forward
    return) was already answered by scripts/probes/_468_moderate_realized_r.py
    — MODERATE ≈ HIGH on raw 5-day return there too. A hit here re-derives a
    known result, not a new one.
  - outside_top20: 156 date-matched rows fall on only 7 sessions (~22/session)
    — it only exists on days with more than 20 alerts, i.e. big-breadth
    earnings-cluster days. Its diff is substantially a market-condition effect
    (what kind of day produces >20 alerts) riding along with the filter
    effect, not cleanly separable in this data.
  - high_unentered: 289 rows wide collapses to 2 in the date-matched window —
    this attribution gap was overwhelmingly a Feb-Jun phenomenon and is
    already nearly gone in the last six weeks. Reported as a wide-window-only
    finding; the date-matched number is too thin to say anything.

MULTIPLE COMPARISONS — 54 permutation tests, fixed and counted, ALL run on the
date-matched population (>= MATCH_START):
    1   PRIMARY: gap_below_floor · ret_5d
    4   sensitivity: PRIMARY reason at the other 4 horizons
   23   per-reason battery: the other 23 reasons (all but gap_below_floor,
        already the primary) · ret_5d only
   25   per-kind battery: 5 kinds x 5 horizons
    1   scope check: ALL date-matched skips pooled (every non-entered row,
        any reason) · ret_5d — does skipping in general differ from what we
        took
Every test is counted whether or not it produces a p (small-N reasons return
"N too small" and are NOT counted toward the significance denominator's hit
list, but ARE counted in the 54). Raw p<0.05 AND Bonferroni-adjusted-by-54 are
both reported; a result surviving only unadjusted is reported as NOT surviving.

MATURITY FILTER (house pattern, identical constants to the other two probes):
  ret_1d>=2cd, ret_5d>=8cd, ret_20d>=30cd, max_high_5d>=8cd, max_high_20d>=30cd
  calendar days elapsed since alert_date, vs DATA_MAX = 2026-08-14 (both
  mi_ep_missed_outcomes and mi_daily_closes are current through that date,
  verified before writing this probe).

READING HIT RATES SAFELY — a second thing first-draft review caught. A "share
of the cohort that touched +5%/+10%" printed next to a DEEPLY NEGATIVE 5-day
close median (extension_gate: 87.1% touch +5% high, but ret_5d MEDIAN is
-23.8%) reads as "this reason drops runners" when it actually describes a
spike-then-collapse pattern — most gappers touch +5% intraday at some point in
5 days almost by construction. Every per-reason block below prints a single
combined SPIKE-VS-HOLD line pairing the ret_5d close median against the
max_high_5d hit rate so the two numbers cannot be read apart, and the ALL-
DATE-MATCHED-SKIPS-POOLED hit rate is printed once as the base rate every
individual reason's hit rate should be read against (most reasons cluster near
it — the base rate itself, not any one reason, is why hit rates run high).

THE BASELINE PROBLEM (rigor rule 6) — QUANTIFIED, not just stated. Skipped
names' ret_1d/5d/20d/max_high_5d/20d are priced from open_d0 (the gap-day
open — missed_outcomes.py's own documented basis: "what a day-2 chaser would
have paid"). The benchmark built here for taken names uses the IDENTICAL
open_d0-basis formula (same LATERAL-join SQL pattern copied from
missed_outcomes.py, re-run read-only against mi_live_trades — see
_skipattr_taken.tsv) so the PERMUTATION TESTS above compare like for like on
FORMULA. But that formula is not what a live trade actually captures: the real
entry is the ORB-high stop-buy, which fires only after the stock has already
moved off the open. For the 22 taken names this probe computes
basis_gap_pct = (entry_price − open_d0) / open_d0 directly from data already
pulled (entry_price and orb_high are in mi_live_trades; open_d0 is the same
daily-bar join). Its median, printed in the header, is the number of
percentage points the open_d0-basis figure overstates what entering at the
real price actually would have captured — apply it as a downward adjustment to
every "taken" figure in this report when comparing to what was economically
achievable, and understand every skip-cohort figure carries the same
un-quantifiable optimism (a skipped name never got a real entry price to
measure against).

KNOWN LIMITS, stated up front:
  - 'cancelled' mi_live_trades rows (order submitted, never filled, N=18) are
    NEITHER in the skip population NOR in the taken benchmark here — they are
    a real gap in the "whole group to review" and are called out, not silently
    dropped, in the closing section.
  - ep_score/gap_pct are populated on effectively all missed_outcomes rows;
    catalyst_quality is sometimes literally 'unknown' (a real value, not
    NULL) — coverage is printed, not assumed.
  - This does not attempt R-multiple parity with realized live P&L at fixed
    day checkpoints (would need daily mark-to-market of open positions, not
    stored) — total_pnl/risk_dollars is reported as descriptive context only,
    never compared statistically to the skip cohort.
  - The date-matched window (6 weeks) is itself one stretch of tape — the
    fix above removes the Feb-Aug confound but cannot rule out that Jul-Aug
    is atypical in its own right; a future window will either confirm or
    move these numbers, and that is expected, not a flaw.

THE LINE: this probe measures. Skips are entry discipline — the operator's
sole authority. Nothing here proposes or pre-selects a threshold, filter, or
rule change; a reason that looks defective is stated as a FORK for the
operator with no option chosen.

Inputs (captured ONCE from prod 2026-08-15, COST EFFICIENCY rule — never
re-pull; re-run this script freely, it is pure local computation over the
TSVs):
  _skipattr_missed.tsv  full mi_ep_missed_outcomes dump (3,224 rows)
  _skipattr_taken.tsv   mi_live_trades (account_mode='live', status IN
                        (closed,filled)) LEFT JOINed to mi_daily_closes with
                        the exact missed_outcomes.py open_d0-basis formula
Output captured once to docs/analysis/skip_attribution_2026-08-15.txt.
"""
from __future__ import annotations

import os
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

if os.environ.get("APOLLO_PROBE_WRITE"):
    sys.exit("this probe is read-only by design")

HERE = Path(__file__).resolve().parent
SEED = 20260815
N_PERM = 20000
PLANNED_TESTS = 54
HORIZONS = ["ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"]
MATURITY_DAYS = {"ret_1d": 2, "ret_5d": 8, "ret_20d": 30, "max_high_5d": 8, "max_high_20d": 30}
KINDS = ["mechanics", "selection", "risk_geometry", "portfolio", "other"]

REASON_KIND: dict[str, str] = {
    # mechanics
    "window_missed": "mechanics", "infra_skip": "mechanics", "duplicate_scan": "mechanics",
    "faded_from_orb": "mechanics", "zero_range": "mechanics",
    # selection
    "outside_top20": "selection", "session_rvol_low": "selection", "score_below_50": "selection",
    "adv_low": "selection", "mcap_low": "selection", "pm_rvol_low": "selection",
    "extension_gate": "selection", "catalyst_downgrade": "selection", "ma_filter": "selection",
    "moderate_tier": "selection", "gap_below_floor": "selection",
    # risk geometry
    "stop_too_wide": "risk_geometry", "atr_high": "risk_geometry",
    "size_too_small": "risk_geometry", "price_exceeds_cap": "risk_geometry",
    # portfolio
    "cooldown": "portfolio", "breaker_blocked": "portfolio", "cap_blocked": "portfolio",
    # other — genuinely unattributed
    "high_unentered": "other",
}
PRIMARY_REASON = "gap_below_floor"
LABEL = {
    "price_exceeds_cap": "price_exceeds_cap (chase-cap analog; "
                          "'setup:chase_cap_exceeded' has 0 rows on record)",
    "window_missed": "window_missed (mostly PRE the 08-13 ORB-window fix — see caveat)",
    "moderate_tier": "moderate_tier (re-derives _468_moderate_realized_r.py — see caveat)",
    "outside_top20": "outside_top20 (concentrated on high-breadth days — see caveat)",
    "high_unentered": "high_unentered (wide-window only — collapses to n=2 date-matched)",
}


def fnum(x):
    try:
        return float(x) if x not in ("", None) else None
    except (TypeError, ValueError):
        return None


def pdate(s: str) -> date:
    y, m, d = (int(v) for v in s.split("-"))
    return date(y, m, d)


# ---------------- load ----------------

def reason_key(skip_category: str, skip_reason: str) -> str:
    if skip_category != "setup_other":
        return skip_category
    s = (skip_reason or "").lower()
    if s.startswith("setup:gap_below_floor"):
        return "gap_below_floor"
    if s.startswith("setup:size_too_small"):
        return "size_too_small"
    if s.startswith("setup:price_exceeds_cap"):
        return "price_exceeds_cap"
    if s.startswith("setup:zero_range"):
        return "zero_range"
    return "setup_other_unclassified"  # safety net — expected to be empty


SKIPS: list[dict] = []
unclassified = 0
for ln in (HERE / "_skipattr_missed.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 12:
        continue
    ticker, d, skip_reason, skip_category = p[0], p[1], p[2], p[3]
    r = dict(ticker=ticker, d=d, skip_reason=skip_reason, skip_category=skip_category,
              ep_score=fnum(p[4]), gap_pct=fnum(p[5]), cq=p[6],
              ret_1d=fnum(p[7]), ret_5d=fnum(p[8]), ret_20d=fnum(p[9]),
              max_high_5d=fnum(p[10]), max_high_20d=fnum(p[11]))
    rk = reason_key(skip_category, skip_reason)
    if rk == "setup_other_unclassified":
        unclassified += 1
        rk = "other"
    r["reason"] = rk
    r["kind"] = REASON_KIND.get(rk, "other")
    SKIPS.append(r)

TAKEN: list[dict] = []
for ln in (HERE / "_skipattr_taken.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 17:
        continue
    TAKEN.append(dict(
        ticker=p[0], d=p[1], ep_score=fnum(p[2]), gap_pct=fnum(p[3]), cq=p[4],
        status=p[5], entry_price=fnum(p[6]), orb_high=fnum(p[7]),
        total_pnl=fnum(p[8]), risk_dollars=fnum(p[9]),
        open_d0=fnum(p[10]), close_d0=fnum(p[11]),
        ret_1d=fnum(p[12]), ret_5d=fnum(p[13]), ret_20d=fnum(p[14]),
        max_high_5d=fnum(p[15]), max_high_20d=fnum(p[16])))

DATA_MAX = max([pdate(r["d"]) for r in SKIPS] + [pdate(r["d"]) for r in TAKEN])
assert str(DATA_MAX) == "2026-08-14", f"DATA_MAX drifted: {DATA_MAX} (docstring assumes 2026-08-14)"

# ---------------- calendar match (the load-bearing fix) ----------------
MATCH_START = min(r["d"] for r in TAKEN)
SKIPS_MATCHED = [r for r in SKIPS if r["d"] >= MATCH_START]


# ---------------- stats machinery (house pattern, identical to the other two probes) ----------------

def mature(rows: list[dict], h: str) -> list[dict]:
    cutoff = DATA_MAX - timedelta(days=MATURITY_DAYS[h])
    return [r for r in rows if pdate(r["d"]) <= cutoff]


def describe(rows: list[dict], h: str) -> dict:
    vals = [r[h] * 100.0 for r in rows if r[h] is not None]
    sess = {r["d"] for r in rows if r[h] is not None}
    if not vals:
        return {"n": 0, "sessions": 0, "median": None, "p25": None, "p75": None, "pct_positive": None}
    s = sorted(vals)
    return {"n": len(vals), "sessions": len(sess), "median": round(st.median(vals), 2),
            "p25": round(s[len(s) // 4], 2), "p75": round(s[3 * len(s) // 4], 2),
            "pct_positive": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1)}


def hit_rate(rows: list[dict], h: str, thresh: float) -> tuple[int, float | None]:
    vals = [r[h] * 100.0 for r in rows if r[h] is not None]
    if not vals:
        return 0, None
    return len(vals), round(100.0 * sum(1 for v in vals if v >= thresh) / len(vals), 1)


MIN_DISTINCT_PERM_STATS = 50  # below this the permutation null is too discrete to trust a p from


def perm_p(a: list[float], b: list[float], sess_a: list[str], sess_b: list[str]) -> float | None:
    """Permutation on difference in MEDIANS, shuffling whole SESSIONS (house pattern,
    identical to _grade_override_outcome_read.py / _rs_inflection_read.py).

    GUARD (added after second-draft review): when one side's row count is a large
    share of the pooled total, perm_p's session-quota assignment can only ever
    route a HANDFUL of distinct session-subsets into the smaller pseudo-group — the
    20,000 draws sample the same few dozen configurations over and over, so a
    p near 1/20001 means "this is the single most extreme achievable split," not
    "this is in the tail of a continuous null." Caught in this probe: two kind-
    level 20-day tests (taken n=5 across 4 sessions vs skip n=83/7 — an extreme
    size imbalance) printed p=0.000 and nominally survived Bonferroni; neither
    permutation actually explored enough distinct splits to support that. Fix:
    count DISTINCT values of the permuted statistic actually produced across the
    20,000 draws; below MIN_DISTINCT_PERM_STATS, the null is too coarse to trust
    and this returns None (same "N too small" bucket as the n<5 gate below) rather
    than a p that looks precise but isn't."""
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
    distinct_stats: set[float] = set()
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
        stat = st.median(pa) - st.median(pb)
        distinct_stats.add(round(stat, 6))
        if abs(stat) >= abs(obs):
            hits += 1
    if len(distinct_stats) < MIN_DISTINCT_PERM_STATS:
        return None
    return (hits + 1) / (N_PERM + 1)


TESTS_ATTEMPTED = 0
TESTS_COMPLETED = 0
RESULTS: list[dict] = []


def run_test(name: str, group: list[dict], taken: list[dict], h: str, level: str = "other") -> dict:
    """level tags the granularity for downstream filtering: 'primary', 'reason',
    'kind', or 'scope' — NOT parsed from the name string. `group` is ALWAYS drawn
    from the date-matched population (SKIPS_MATCHED) by every call site below."""
    global TESTS_ATTEMPTED, TESTS_COMPLETED
    TESTS_ATTEMPTED += 1
    g, t = mature(group, h), mature(taken, h)
    dg, dt = describe(g, h), describe(t, h)
    vg = [r[h] * 100 for r in g if r[h] is not None]
    vt = [r[h] * 100 for r in t if r[h] is not None]
    sg = [r["d"] for r in g if r[h] is not None]
    st_ = [r["d"] for r in t if r[h] is not None]
    p = perm_p(vg, vt, sg, st_)
    if p is not None:
        TESTS_COMPLETED += 1
    eff = (dg["median"] - dt["median"]) if (dg["median"] is not None and dt["median"] is not None) else None
    res = dict(name=name, h=h, level=level, group=dg, taken=dt, effect=eff, p=p)
    RESULTS.append(res)
    return res


def fmt(res: dict, bonf: int | None = None) -> str:
    dg, dt = res["group"], res["taken"]
    if not dg["n"] or not dt["n"]:
        return f"  {res['name']:<52} EMPTY (group n={dg['n']}, taken n={dt['n']})"
    ps = "N too small for permutation" if res["p"] is None else f"raw p={res['p']:.3f}"
    if bonf and res["p"] is not None:
        ps += f"  adj p(x{bonf})={min(1.0, res['p'] * bonf):.3f}"
    return (f"  {res['name']:<52} group med {dg['median']:>6}% (n={dg['n']:>4}, {dg['sessions']:>3} sess) | "
            f"taken med {dt['median']:>6}% (n={dt['n']:>2}, {dt['sessions']:>2} sess) | "
            f"diff {res['effect']:+.2f}pp | {ps}")


# ==================================================================================
print("=" * 100)
print("SKIP-REASON ATTRIBUTION — does each decline reason drop names that RAN, or names that died?")
print("(capture 2026-08-15, read-only; step 4 of The Real EP Plan)")
print("=" * 100)
print(f"skip population (WIDE, context only): {len(SKIPS)} rows, {len({r['d'] for r in SKIPS})} "
      f"sessions, {min(r['d'] for r in SKIPS)} .. {max(r['d'] for r in SKIPS)}")
print(f"skip population (DATE-MATCHED, governs every test below): {len(SKIPS_MATCHED)} rows "
      f"({100*len(SKIPS_MATCHED)/len(SKIPS):.0f}% of wide), "
      f"{len({r['d'] for r in SKIPS_MATCHED})} sessions, >= {MATCH_START}")
print(f"taken benchmark : {len(TAKEN)} rows (mi_live_trades account_mode=live, status IN "
      f"closed/filled), {len({r['d'] for r in TAKEN})} sessions, "
      f"{min(r['d'] for r in TAKEN)} .. {max(r['d'] for r in TAKEN)}")
print("⚠ MATCH_START = the taken cohort's own earliest date, computed from data. Every permutation")
print("  test below runs on the DATE-MATCHED skip population only — a Feb-2026 skip session can never")
print("  actually be a 'taken' session (no fills exist that day), so pooling it in would answer a")
print("  different question ('is Jul-Aug different from Feb-Jun') than the one asked.")
print(f"setup_other rows that did not match a known setup: prefix: {unclassified} "
      "(0 expected; folded into OTHER if nonzero)")
cq_unknown = sum(1 for r in SKIPS_MATCHED if r["cq"] == "unknown")
cq_empty = sum(1 for r in SKIPS_MATCHED if r["cq"] == "")
cq_populated = len(SKIPS_MATCHED) - cq_unknown - cq_empty
print(f"catalyst_quality coverage (date-matched): {cq_populated}/{len(SKIPS_MATCHED)} populated "
      f"({100*cq_populated/len(SKIPS_MATCHED):.0f}%), {cq_unknown} literally 'unknown', "
      f"{cq_empty} NULL/empty — any catalyst_quality-flavored reason (catalyst_downgrade, ma_filter)")
print("  reads on skip_reason TEXT, not this column, so the gap does not block those reasons.")
print("⚠ outcome values are FRACTIONS in the DB; printed x100 as real percents.")
print("⚠ each horizon drops alerts too recent to have elapsed (maturity filter vs data max "
      f"{DATA_MAX}); N falls as the horizon lengthens.\n")

# ---------------- baseline-problem quantification ----------------
gaps = [100.0 * (r["entry_price"] - r["open_d0"]) / r["open_d0"]
        for r in TAKEN if r["entry_price"] and r["open_d0"] and r["open_d0"] > 0]
print("-" * 100)
print("BASELINE PROBLEM — quantified (rigor rule 6)")
print("-" * 100)
if gaps:
    print(f"  basis_gap_pct = (ORB-high entry − gap-day open) / gap-day open, the 22 taken names:")
    print(f"    median {st.median(gaps):+.2f}%  mean {st.fmean(gaps):+.2f}%  (n={len(gaps)})")
    print("  READ: every open_d0-basis figure below (both cohorts, by construction, since the")
    print("  taken-name benchmark is computed on the SAME formula as the skip cohort for formula")
    print("  comparability) overstates what a real entry actually captures by roughly this much —")
    print("  the skip cohort NEVER got a real entry price, so this haircut cannot be applied to it,")
    print("  only disclosed as the direction and rough size of the flattering bias on 'taken'.")
else:
    print("  could not compute — missing entry_price/open_d0 on the taken cohort")
print()

# ---------------- taken-cohort benchmark + base-rate hit rate, printed first as the reference ----------------
print("-" * 100)
print("TAKEN-NAMES BENCHMARK — what we actually did instead (the standard every reason is judged against)")
print("-" * 100)
for h in HORIZONS:
    t = mature(TAKEN, h)
    dt = describe(t, h)
    _, hr5 = hit_rate(t, h, 5.0)
    _, hr10 = hit_rate(t, h, 10.0)
    if dt["n"]:
        print(f"  {h:<13} n={dt['n']:>3} ({dt['sessions']:>2} sess)  median {dt['median']:>7}%  "
              f"IQR [{dt['p25']:>7}%, {dt['p75']:>7}%]  {dt['pct_positive']:>5}% up  "
              f"share>=+5% {hr5}%  share>=+10% {hr10}%")
realized_r = [r["total_pnl"] / r["risk_dollars"] for r in TAKEN
              if r["total_pnl"] is not None and r["risk_dollars"] not in (None, 0)]
if realized_r:
    print(f"  (context only, not compared statistically to skips: ACTUAL realized R "
          f"[total_pnl/risk_dollars] median {st.median(realized_r):+.2f}R, n={len(realized_r)})")
print()
print("-" * 100)
print("BASE RATE — ALL date-matched skips pooled, max_high hit-rates (read every individual")
print("reason's hit rate against THIS, not against zero — most reasons cluster near it)")
print("-" * 100)
for h in ("ret_5d", "max_high_5d", "max_high_20d"):
    m = mature(SKIPS_MATCHED, h)
    dm = describe(m, h)
    _, hr5 = hit_rate(m, h, 5.0)
    _, hr10 = hit_rate(m, h, 10.0)
    if dm["n"]:
        print(f"  {h:<13} n={dm['n']:>4} ({dm['sessions']:>3} sess)  median {dm['median']:>7}%  "
              f"share>=+5% {hr5}%  share>=+10% {hr10}%")
print()

# ---------------- PRIMARY ----------------
print("=" * 100)
print(f"PRIMARY (pre-registered): {PRIMARY_REASON} (SELECTION kind) vs taken-names benchmark · ret_5d")
print("=" * 100)
primary_group = [r for r in SKIPS_MATCHED if r["reason"] == PRIMARY_REASON]
print(f"  pre-maturity-filter N for {PRIMARY_REASON}: {len(primary_group)} "
      "(all 7 rows on record fall inside the date-matched window already — this reason has never")
print("  fired before 2026-08-06; it is NEW, not merely small — see docstring)")
pri = run_test(f"PRIMARY {PRIMARY_REASON} ret_5d", primary_group, TAKEN, "ret_5d", level="primary")
print(fmt(pri, bonf=PLANNED_TESTS))
print(f"  (adj p = Bonferroni across all {PLANNED_TESTS} attempted tests; the adjusted p governs "
      "the verdict, per the pre-registration.)")
print("  VERDICT LANGUAGE: 'too new to tell', not 'no effect' — gate the re-ask on N>=10 mature")
print("  rows (house convention: data-gated, not calendar-gated), not on a fixed future date.")

# ---------------- EXPLORATORY 1: primary at other horizons ----------------
print("\n" + "-" * 100)
print("EXPLORATORY 1 — sensitivity: PRIMARY reason at the other 4 horizons")
print("-" * 100)
for h in ("ret_1d", "ret_20d", "max_high_5d", "max_high_20d"):
    print(fmt(run_test(f"{PRIMARY_REASON} {h}", primary_group, TAKEN, h, level="primary_sens")))

# ---------------- EXPLORATORY 2: per-reason battery at ret_5d ----------------
print("\n" + "-" * 100)
print("EXPLORATORY 2 — every OTHER reason vs taken-names benchmark · ret_5d (date-matched population)")
print("-" * 100)
REASON_ORDER = sorted(REASON_KIND, key=lambda rk: (REASON_KIND[rk], rk))
for rk in REASON_ORDER:
    if rk == PRIMARY_REASON:
        continue
    group = [r for r in SKIPS_MATCHED if r["reason"] == rk]
    label = LABEL.get(rk, rk)
    print(fmt(run_test(f"[{REASON_KIND[rk]}] {label} ret_5d", group, TAKEN, "ret_5d", level="reason")))

# ---------------- EXPLORATORY 3: per-kind battery across all 5 horizons ----------------
print("\n" + "-" * 100)
print("EXPLORATORY 3 — per taxonomy KIND vs taken-names benchmark, all 5 horizons (date-matched)")
print("-" * 100)
KIND_RESULTS: dict[str, list[dict]] = defaultdict(list)
for kind in KINDS:
    kgroup = [r for r in SKIPS_MATCHED if r["kind"] == kind]
    print(f" -- {kind.upper()} (n_raw={len(kgroup)} date-matched rows across all reasons in this kind) --")
    for h in HORIZONS:
        res = run_test(f"[{kind}] {h}", kgroup, TAKEN, h, level="kind")
        KIND_RESULTS[kind].append(res)
        print(fmt(res))

# ---------------- EXPLORATORY 4: scope check — all skips pooled ----------------
print("\n" + "-" * 100)
print("EXPLORATORY 4 — scope check: ALL date-matched skips pooled (any reason) vs taken benchmark · ret_5d")
print("-" * 100)
scope_res = run_test("ALL date-matched skips pooled ret_5d", SKIPS_MATCHED, TAKEN, "ret_5d", level="scope")
print(fmt(scope_res))
print("  READ THIS ONE FIRST: nearly every individual reason above shows a SIMILARLY SIZED positive")
print("  diff vs taken, regardless of kind (mechanics, selection, portfolio alike) — that pattern is")
print("  a LEVEL SHIFT in the benchmark (taken names' 5d median is -7.49%, the documented losing")
print("  stretch), not a per-reason effect. This pooled line is that shift with reason stripped out;")
print("  it is the number that shows the shift is population-wide, not particular to any one filter.")

# ---------------- multiplicity ledger ----------------
print("\n" + "=" * 100)
print(f"MULTIPLICITY LEDGER — {TESTS_ATTEMPTED} tests attempted (planned {PLANNED_TESTS}), "
      f"{TESTS_COMPLETED} produced a p")
print("=" * 100)
assert TESTS_ATTEMPTED == PLANNED_TESTS, "battery drifted from pre-registration"
sig_raw = [r for r in RESULTS if r["p"] is not None and r["p"] < 0.05]
sig_adj = [r for r in RESULTS if r["p"] is not None and r["p"] * PLANNED_TESTS < 0.05]
print(f"  raw p<0.05: {len(sig_raw)} of {TESTS_COMPLETED}"
      + (" — " + "; ".join(f"{r['name']} (p={r['p']:.3f}, diff={r['effect']:+.2f}pp)"
                            for r in sig_raw) if sig_raw else ""))
print(f"  surviving Bonferroni x{PLANNED_TESTS} (adj p<0.05): {len(sig_adj)}"
      + (" — " + "; ".join(r["name"] for r in sig_adj) if sig_adj else ""))
print(f"  expected false positives at raw 0.05 across {TESTS_COMPLETED} tests: "
      f"~{0.05 * TESTS_COMPLETED:.1f} — this many raw hits is what chance alone produces.")
n20 = [r for r in sig_adj if r["h"] in ("ret_20d", "max_high_20d")]
if n20:
    print("  ⚠ CAVEAT ON THE BONFERRONI SURVIVORS: both are at a 20-day horizon where the taken")
    print("    benchmark has only n=5 rows across 4 sessions — barely above this probe's own floor")
    print("    for running a permutation at all (n>=5, sessions>=6 combined). With the skip side an")
    print("    order of magnitude larger, the permutation's resolution is thin at that imbalance; a")
    print("    p this extreme is plausible as a small-sample artifact, not necessarily a robust")
    print("    finding. Read as 'worth re-checking once the taken cohort matures past 20 days on")
    print("    more names,' not as settled evidence.")

# ---------------- full descriptive appendix: every reason, every horizon, honest N ----------------
print("\n" + "=" * 100)
print("APPENDIX — full descriptive table, every reason x every horizon. DATE-MATCHED numbers govern")
print("(N and sessions on every line; reasons with single-digit N get NO p, marked as such). WIDE")
print("(Feb-Aug) numbers follow each reason as CONTEXT ONLY, labelled confounded, never tested.")
print("=" * 100)
for rk in REASON_ORDER:
    group_matched = [r for r in SKIPS_MATCHED if r["reason"] == rk]
    group_wide = [r for r in SKIPS if r["reason"] == rk]
    label = LABEL.get(rk, rk)
    print(f"\n[{REASON_KIND[rk]}] {label}")
    print(f"  date-matched: n_raw={len(group_matched)} rows, "
          f"{len({r['d'] for r in group_matched})} sessions, >= {MATCH_START}")
    if len(group_matched) < 10:
        print("  ⚠ N<10 date-matched — the operator's evidence rule: a single skipped name that ran")
        print("    proves nothing. Descriptive numbers below are shown for completeness, NOT evidence.")
    ret5d_med = hi5d_5 = hi5d_10 = None
    for h in HORIZONS:
        g = mature(group_matched, h)
        dg = describe(g, h)
        if not dg["n"]:
            continue
        _, hr5 = hit_rate(g, h, 5.0)
        _, hr10 = hit_rate(g, h, 10.0)
        print(f"    {h:<13} n={dg['n']:>4} ({dg['sessions']:>3} sess)  median {dg['median']:>7}%  "
              f"IQR [{dg['p25']:>7}%, {dg['p75']:>7}%]  {dg['pct_positive']:>5}% up  "
              f"share>=+5% {hr5}%  share>=+10% {hr10}%")
        if h == "ret_5d":
            ret5d_med = dg["median"]
        if h == "max_high_5d":
            hi5d_5, hi5d_10 = hr5, hr10
    if ret5d_med is not None and hi5d_5 is not None:
        print(f"    SPIKE-VS-HOLD  5d close median {ret5d_med:+.1f}%  vs  5d-high touch rate "
              f">=5% {hi5d_5}% / >=10% {hi5d_10}% — read together: a high touch-rate with a")
        print(f"                   negative close median means names spiked then gave it back, not")
        print(f"                   that this reason 'drops runners'.")
    dw5 = describe(mature(group_wide, "ret_5d"), "ret_5d")
    if dw5["n"]:
        print(f"    WIDE (Feb-Aug, CONFOUNDED, context only, not tested): ret_5d n={dw5['n']} "
              f"({dw5['sessions']} sess) median {dw5['median']:+.1f}%")

# ---------------- ranked summary table (for the operator-facing report) ----------------
print("\n" + "=" * 100)
print("RANKED SUMMARY — reasons at ret_5d (date-matched), sorted by how much the skipped cohort")
print("OUT-RAN taken names (only reasons with n>=10 after maturity filtering are ranked; smaller-N")
print("reasons listed below, unranked, exactly per the operator's evidence rule)")
print("=" * 100)
ranked = [r for r in RESULTS if r["h"] == "ret_5d" and r["level"] == "reason"
          and r["group"]["n"] and r["group"]["n"] >= 10]
ranked.sort(key=lambda r: (r["effect"] if r["effect"] is not None else -999), reverse=True)
for r in ranked:
    print(fmt(r, bonf=PLANNED_TESTS))
small_n = [(rk, len(mature([x for x in SKIPS_MATCHED if x["reason"] == rk], "ret_5d")))
           for rk in REASON_ORDER]
small_n = [(rk, n) for rk, n in small_n if n < 10]
print(f"\n  reasons with n<10 at ret_5d date-matched (unranked, per evidence rule): "
      + ", ".join(f"{LABEL.get(rk, rk)}(n={n})" for rk, n in small_n))

# ---------------- what could not be measured ----------------
print("\n" + "=" * 100)
print("WHAT COULD NOT BE MEASURED, AND WHY")
print("=" * 100)
print("  - mi_live_trades 'cancelled' rows (submitted, never filled, N=18 on record) are in neither")
print("    cohort here — not a skip decision (passed every gate, got submitted) and not a taken name")
print("    (never filled). The 'whole group to review' is incomplete by this many rows; a follow-up")
print("    would need to decide which side they belong on before including them.")
print("  - high_unentered (n=289 wide) collapses to n=2 in the date-matched window — cannot say")
print("    anything about it in the window that matters for comparison to what we're doing now;")
print("    the wide-window number is reported as historical context only.")
print("  - No R-multiple / realized-P&L comparison at fixed day checkpoints: mi_live_trades does not")
print("    store daily mark-to-market of open positions, only entry/exit and final total_pnl — the")
print("    ACTUAL realized R printed above is context only, never tested against the skip cohort.")
print("  - The baseline problem (open_d0 vs ORB-high entry) is quantified in direction and rough")
print("    magnitude (basis_gap_pct above) but cannot be applied AS a correction to the skip cohort,")
print("    which never received a real entry price to measure the same gap against.")
print("  - 'setup:chase_cap_exceeded' (named in the task) has 0 rows under that literal string;")
print("    price_exceeds_cap is reported as the closest analog on record and flagged everywhere.")
print("  - The date-matched window is itself one 6-week stretch of tape; it cannot rule out that")
print("    Jul-Aug is atypical in its own right — a future window will move these numbers, expected.")

print("\n" + "=" * 100)
print("HOW TO READ THIS — permutation shuffles whole SESSIONS (alerts on one morning share the tape),")
print("and only within the date-matched window (a Feb session can never be a 'taken' session). The")
print("PRIMARY's verdict rests on its ADJUSTED p; everything else is exploratory / hypothesis-")
print("generating. Nothing here licenses a change to any skip rule, filter, or threshold — skips are")
print("entry discipline (THE LINE); any reason that looks defective is a FORK for the operator, with")
print("no option pre-chosen.")
print("=" * 100)
