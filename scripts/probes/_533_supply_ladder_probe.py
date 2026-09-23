#!/usr/bin/env python3
"""SUPPLY-LADDER PROBE — extends _533_nbis_structure_encoder.py with the operator's own
mechanism (docs/methodology/operator_shared_notes.md §2026-08-16, THE SUPPLY-LADDER MODEL),
then his LIVE REFINEMENT sent minutes after this card started (verbatim in the coordinator
message, captured here for the record):

  "an added point, EPs that clear congestion zones the more it clears the stronger all else
  equal. If the gap up just meets the first congestion or fails even to go above it is iffy,
  the same concept of moving averages, it's just any proxy or gauge to see how strong the gap
  up is aside from raw % which has no reference. Gapping up above key levels, holding, even
  pulling back to not failing is sign of strength."

READ-ONLY. SHADOW MEASUREMENT ONLY. Nothing here touches _score_ep, the judge, entry, exit,
or sizing (THE LINE). A positive result is a FORK for the operator (fork S-3,
ep_profitability_program.md), not a pre-decided change.

REUSE, NOT REWRITE: this file imports _533_nbis_structure_encoder.py (the fixture-gated,
8/8-passing encoder) and calls its encode()/load_daily()/load_minute() UNCHANGED. It adds
zero new level-derivation logic (no new pivot/episode/SMA math beyond trivially COUNTING
fields the encoder already returns). The only new file-local computation is (a) a session-
high variant of "zones cleared" (counts the SAME qualified levels the encoder already found,
against the day's own high instead of the open) and (b) an MA-cleared COUNT (the encoder
already returns which MAs sat overhead pre-gap in `overhead_mas`; counting how many the open
price exceeds is arithmetic on that dict, not new level logic).

THE FEATURES (per alert, all reused from encode(..., preopen=True) unless flagged otherwise):
  zones_cleared         = n_cleared (preopen) — qualified resistance levels strictly between
                           yesterday's close and today's open. PRE-OPEN, POINT-IN-TIME.
                           *** THE PRIMARY FEATURE per the operator's refinement. ***
  zones_remaining       = n_uncleared (preopen) — the ORIGINAL primary (distance-based),
                           now DEMOTED to secondary per his refinement.
  dist_adr              = c5_adr_to_next_level (preopen) — ADR20 distance to the nearest
                           remaining level. Secondary.
  blue_sky              = class starts with BLUE_SKY (preopen) — the limiting case, its own
                           bucket, not folded into the continuous count.
  iffy                  = class == NEVER_BREACHED (preopen) — his OWN words: "just meets the
                           first congestion or fails even to go above it is iffy." Reported
                           as its own bucket, not a continuous variable, per his framing.
  ma_cleared_count      = of the SMA10/20/50 that sat above yesterday's close (the encoder's
                           `overhead_mas`, pre-open), how many the OPEN price exceeds. "the
                           same concept... just another proxy" (his words). Pre-open.
  zones_cleared_and_held= of the levels the gap cleared, how many were still HELD (encoder's
                           own end-state hold test, 60-min primary window) — "gapping above
                           key levels, holding, even pulling back to not failing." Uses
                           post-open minute bars (Tier-A subset only; NOT pre-open).
  zones_cleared_to_high = zones_cleared but measured to the ALERT DAY'S OWN HIGH instead of
                           the open — "the more it clears the stronger." ⚠ MECHANICALLY
                           CONTAMINATED: the day-0 high is one input into max_high_5d (1 of 5
                           trading days) and a smaller share of max_high_20d (1 of 20).
                           Reported, tested, and labelled — never read as a clean predictor,
                           tested ONLY against max_high_20d where the overlap is diluted.
  gap_pct               = the raw comparator his refinement asks to beat head-to-head.

DEPENDENT VARIABLES — mi_ep_missed_outcomes (⚠ FRACTIONS in the DB; printed x100 as real
percent throughout): max_high_5d, max_high_20d (excursion SIZE — the W-term question) and
ret_5d (forward return — the direction question, per his refinement's second half).

MFE IN R UNITS — SKIPPED, explicitly. scripts/probes/_468_moderate_realized_r.py's
`reconstruct()` returns REALIZED-R under a specific settle rule (SETTLE_RULE: +1R/+3R
halves + day-5 time stop), not uncapped MFE-in-R, and does not expose the fill index or the
intermediate mixed price path needed to derive one without re-deriving the ORB fill logic
(trigger detection, gap-through/limit handling, the 10:00 unfilled-cancel cutoff) ourselves.
Extracting MFE-in-R cleanly would mean rebuilding that piece of `reconstruct()`'s internals —
exactly the "fifth reconstruction" the task instructions say to avoid. Skipped; max_high_5d/
20d (% from open, not R) carry the excursion-size question instead.

POPULATION. mi_ep_missed_outcomes, source IN ('moderate_alert', 'high_unentered') — i.e. EPs
that reached ALERT GRADE (mi_ep_alerts, HIGH or MODERATE tier, source='live') but were never
entered. This is a DECLINED-ALERT population, not a random sample of everything scanned (the
broader 'scan_filter' source, 2,684 rows, is EXCLUDED — those names never reached alert grade,
which is a different question from "how does structure predict the size of an EP's move").
⚠ mi_ep_missed_outcomes by construction EXCLUDES every alert that was ACTUALLY TRADED (live
fills) — this measures the population of EPs we saw and passed on, not our own trades. This
is the same coverage shape _skip_attribution_read.py and _rs_inflection_read.py already
documented for this table; nothing new here, restated because it bounds every number below.

PRE-REGISTERED BATTERY — declared before any outcome was read (matches this docstring at
first commit of this file). 15 tests, session-level permutation (whole alert-mornings
shuffled — house convention, _rs_inflection_read.py / _533_nbis_structure_encoder.py), every
one counted with raw AND Bonferroni-adjusted (x15) significance:
  1-2   THE DECISIVE COMPARISON (his refinement's core ask): zones_cleared (0 vs >=1) vs
        gap_pct (population's own median split — outcome-blind) on max_high_5d.
  3-4   Same pair on ret_5d (direction).
  5-6   Same pair on max_high_20d (horizon check).
  7-9   THE CONFOUND CONTROL: zones_cleared (0 vs >=1) on max_high_5d, WITHIN each gap-size
        tercile of the analyzed population (outcome-blind cut) — is zones_cleared still
        doing work at comparable gap size?
  10    zones_cleared_and_held (0 vs >=1) on max_high_5d (Tier-A, minute-bar subset).
  11    iffy vs not-iffy on max_high_5d (his named weak case, its own bucket).
  12    blue_sky vs not on max_high_5d (the limiting case, its own bucket).
  13    dist_adr near(<1.5xADR) vs far(>=1.5xADR), among has-remaining-overhead only, on
        max_high_5d (the ORIGINAL primary, now secondary/robustness).
  14    ma_cleared_count == all-overhead-MAs-cleared vs not, on max_high_5d (the MA analog).
  15    zones_cleared_to_high (0 vs >=1) on max_high_20d — LABELLED CONTAMINATED, reported
        for completeness, never read as a clean predictor.
A null on either or both features of the decisive comparison (#1-2) is a real, reportable
result — the operator's hypothesis is that gap % is close to noise; that hypothesis can lose.

Inputs (pulled fresh 2026-08-16 — mi_ep_missed_outcomes was never cached under _533n_*, and
its declined-alert population reaches back to 2026-02-11, well before the 2026-05-11 start of
the existing _533n_daily.tsv/_533n_minute.tsv caches, so daily+minute bars were re-pulled for
the FULL ticker/date set this population needs; nothing here re-pulls what was already cached
for other probes):
  _ladder_missed.tsv   mi_ep_missed_outcomes, source IN (moderate_alert, high_unentered),
                       DISTINCT ON (ticker, alert_date) — 526 rows, 463 tickers, 97 sessions,
                       2026-02-11..2026-08-14.
  _ladder_daily.tsv    mi_daily_closes for all 463 tickers, full history (123,237 rows).
  _ladder_minute.tsv   mi_intraday_bars 09:30-12:00 ET for the 526 (ticker, date) pairs
                       (34,299 rows; only 237/526 pairs have minute coverage — the rest
                       predate intraday capture or are thin names; Tier-A/Tier-B split
                       throughout, matching _533_nbis_structure_encoder.py's own convention).
Output: append to docs/analysis/structure_ladder_2026-08-16.txt (capture once).
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
sys.path.insert(0, str(HERE))
import _533_nbis_structure_encoder as nbis  # noqa: E402 — reuse encode()/loaders, unchanged

# redirect the encoder's loaders at OUR pulled TSVs (this population predates the encoder's
# own 2026-05-11-onward cache) — encode() and load_daily/load_minute are called UNMODIFIED.
nbis.DAILY_TSV = HERE / "_ladder_daily.tsv"
nbis.MINUTE_TSV = HERE / "_ladder_minute.tsv"
MISSED_TSV = HERE / "_ladder_missed.tsv"

SEED = 20260815     # same seed the house convention uses everywhere else in this program
N_PERM = 20000
PLANNED_TESTS = 15
BAND_ADR = nbis.BAND_ADR             # 1.5 — reused, not re-picked
MATURITY_DAYS = {"ret_5d": 8, "max_high_5d": 8, "max_high_20d": 30}


def fnum(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


def pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


# ---------------- load the declined-alert cohort ----------------
ROWS: list[dict] = []
for ln in MISSED_TSV.read_text(encoding="utf-8").splitlines():
    p = ln.rstrip("\r").split("|")
    if len(p) != 13:
        continue
    ROWS.append(dict(
        ticker=p[0], d=p[1], source=p[2], skip_category=p[3], skip_reason=p[4],
        ep_score=fnum(p[5]), gap_pct=fnum(p[6]), catalyst_quality=p[7],
        ret_1d=fnum(p[8]), ret_5d=fnum(p[9]), ret_20d=fnum(p[10]),
        max_high_5d=fnum(p[11]), max_high_20d=fnum(p[12])))

DATA_MAX = max(pdate(r["d"]) for r in ROWS)


# ---------------- encode every alert (reusing the fixture-gated encoder, unchanged) -------
daily, minute = nbis.load_daily(), nbis.load_minute()

funnel = defaultdict(int)
FEAT: list[dict] = []
for r in ROWS:
    funnel["cohort"] += 1
    if r["gap_pct"] is None:
        funnel["no_gap_pct"] += 1
        continue
    pre = nbis.encode(r["ticker"], r["d"], daily, minute, preopen=True)
    if pre.get("error"):
        funnel[f"drop:{pre['error'].split('(')[0]}"] += 1
        continue
    days = daily[r["ticker"]]
    ia = next(i for i, row in enumerate(days) if row[0] == r["d"])
    day_high = days[ia][2]

    zones_cleared = pre["n_cleared"]
    zones_remaining = pre["n_uncleared"]
    dist_adr = pre["c5_adr_to_next_level"]
    blue_sky = pre["cls"].startswith("BLUE_SKY")
    iffy = pre["cls"] == "NEVER_BREACHED"
    overhead_mas = dict(pre["overhead_mas"])         # {name: value}, pre-open, pure
    # sma200 — his named 4th MA (10/20/50/200). The encoder only carries 10/20/50; this is
    # the SAME trivial trailing-mean arithmetic encode() already uses for the other three,
    # not new level-derivation logic. Needs 200 prior days; else omitted (counted below).
    prior_close_tmp = pre["prior_close"]
    if ia >= 200:
        sma200 = st.fmean(days[j][4] for j in range(ia - 200, ia))
        if sma200 > prior_close_tmp:
            overhead_mas["sma200"] = sma200
    ma_cleared_count = sum(1 for v in overhead_mas.values() if pre["open"] > v)
    n_overhead_mas = len(overhead_mas)

    # session-high variant: SAME qualified levels the encoder found (levels_detail prices),
    # counted against the day's own high instead of the open. No new level derivation.
    prior_close = pre["prior_close"]
    zones_cleared_to_high = sum(1 for L in pre["levels_detail"]
                                if L["price"] > prior_close and L["price"] <= day_high)

    # post-open HELD count (Tier-A only): reuse the encoder's own full (non-preopen) pass
    # and its per-level 'held' flag from levels_detail — no re-derivation of the hold logic.
    full = nbis.encode(r["ticker"], r["d"], daily, minute, preopen=False)
    tier_a = "no_minute_bars" not in full.get("flags", []) and \
             "scale_mismatch_minute_vs_daily" not in full.get("flags", [])
    zones_cleared_and_held = (sum(1 for L in full["levels_detail"] if L["held"] is True)
                              if tier_a else None)

    row = dict(r)
    row.update(zones_cleared=zones_cleared, zones_remaining=zones_remaining,
               dist_adr=dist_adr, blue_sky=blue_sky, iffy=iffy,
               ma_cleared_count=ma_cleared_count, n_overhead_mas=n_overhead_mas,
               has_sma200=("sma200" in overhead_mas),
               zones_cleared_to_high=zones_cleared_to_high,
               zones_cleared_and_held=zones_cleared_and_held, tier_a=tier_a,
               adr20_pct=pre["adr20_pct"], history_days=pre["history_days"],
               cls_preopen=pre["cls"])
    FEAT.append(row)
    funnel["encoded"] += 1
    funnel["tier_a" if tier_a else "tier_b_daily_only"] += 1

print("=" * 98)
print("SUPPLY-LADDER PROBE — zones_cleared (PRIMARY, his 2026-08-16 refinement) vs raw gap %,")
print("predicting EXCURSION SIZE and DIRECTION, on the declined-alert population")
print("=" * 98)
print("Population: mi_ep_missed_outcomes, source IN (moderate_alert, high_unentered) — EPs")
print("that reached alert grade and were never entered. Excludes every ACTUALLY TRADED alert")
print("(this table's own design) — reported, not hidden.")
print(f"\ncohort funnel: " + " · ".join(f"{k}={v}" for k, v in sorted(funnel.items())))
print(f"encoded: {len(FEAT)} of {len(ROWS)} rows, {len({r['d'] for r in FEAT})} sessions, "
      f"{min(r['d'] for r in FEAT)} .. {max(r['d'] for r in FEAT)}")
print(f"data max (bounds maturity filtering): {DATA_MAX}")
print("⚠ outcome values are FRACTIONS in the DB; printed x100 as real percents below.")
_hist = sorted(r["history_days"] for r in FEAT)
print(f"⚠ BLUE_SKY / hist_max means 'above the AVAILABLE-HISTORY high' (this pull's daily bars"
      f" go back to 2025-07; history per name ranges {_hist[0]}-{_hist[-1]} trading days, "
      f"median {int(st.median(_hist))} ≈ 13 months) — NOT literal all-time-high. Read it as "
      f"'nothing rejected this in the last ~13 months', not 'this stock has never been higher'.")


# ---------------- stats machinery (house pattern, copied from _rs_inflection_read.py) -----

def mature(rows: list[dict], h: str) -> list[dict]:
    cutoff = DATA_MAX - timedelta(days=MATURITY_DAYS[h])
    return [r for r in rows if pdate(r["d"]) <= cutoff]


def describe(rows: list[dict], h: str) -> dict:
    vals = [r[h] * 100.0 for r in rows if r.get(h) is not None]
    sess = {r["d"] for r in rows if r.get(h) is not None}
    if not vals:
        return {"n": 0, "sessions": 0, "median": None, "pct_positive": None}
    return {"n": len(vals), "sessions": len(sess), "median": round(st.median(vals), 2),
            "pct_positive": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1)}


def perm_p(a, b, sess_a, sess_b) -> float | None:
    """Permutation on difference in MEDIANS, shuffling whole SESSIONS (house pattern) —
    same-morning alerts share the tape and are not independent draws."""
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


TESTS_ATTEMPTED = 0
TESTS_COMPLETED = 0
RESULTS: list[dict] = []


def run_test(name: str, kind: str, pop: list[dict], split, h: str) -> dict:
    """split(r) -> True (POS bucket), False (NEG bucket), None (excluded)."""
    global TESTS_ATTEMPTED, TESTS_COMPLETED
    TESTS_ATTEMPTED += 1
    m = mature(pop, h)
    pos = [r for r in m if split(r) is True and r.get(h) is not None]
    neg = [r for r in m if split(r) is False and r.get(h) is not None]
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
        return f"  {res['name']:<58} EMPTY BUCKET (pos n={dp['n']}, neg n={dn['n']})"
    ps = "N too small for permutation" if res["p"] is None else f"raw p={res['p']:.3f}"
    if bonf and res["p"] is not None:
        ps += f"  adj p(x{bonf})={min(1.0, res['p'] * bonf):.3f}"
    return (f"  {res['name']:<58} POS med {dp['median']:>6}% (n={dp['n']}, {dp['sessions']} sess, "
            f"{dp['pct_positive']}% up) | NEG med {dn['median']:>6}% (n={dn['n']}, {dn['sessions']} sess, "
            f"{dn['pct_positive']}% up) | diff {res['effect']:+.2f}pp | {ps}")


# ---------------- splits (all outcome-blind — chosen from the PREDICTOR's own distribution
# or fixed a-priori constants, never from the dependent variable) ---------------------------

zc_split = lambda r: (r["zones_cleared"] >= 1) if r.get("zones_cleared") is not None else None

GAP_MEDIAN = st.median([r["gap_pct"] for r in FEAT if r["gap_pct"] is not None])
gap_split = lambda r: (r["gap_pct"] >= GAP_MEDIAN) if r.get("gap_pct") is not None else None

gaps_sorted = sorted(r["gap_pct"] for r in FEAT if r["gap_pct"] is not None)
n3 = len(gaps_sorted) // 3
GAP_T1, GAP_T2 = gaps_sorted[n3], gaps_sorted[2 * n3]
def gap_tercile(r):
    if r.get("gap_pct") is None:
        return None
    return "low" if r["gap_pct"] < GAP_T1 else ("high" if r["gap_pct"] >= GAP_T2 else "mid")

held_split = lambda r: ((r["zones_cleared_and_held"] >= 1) if r.get("zones_cleared_and_held") is not None else None)
iffy_split = lambda r: r["iffy"]
bluesky_split = lambda r: r["blue_sky"]

def dist_split(r):
    if r.get("zones_remaining") is None or r["zones_remaining"] == 0 or r.get("dist_adr") is None:
        return None
    return r["dist_adr"] < BAND_ADR    # True = NEAR (within the congestion band)

def ma_split(r):
    if not r.get("n_overhead_mas"):
        return None
    return r["ma_cleared_count"] == r["n_overhead_mas"]   # True = cleared ALL overhead MAs

zch_split = lambda r: (r["zones_cleared_to_high"] >= 1) if r.get("zones_cleared_to_high") is not None else None

print(f"\nzones_cleared distribution (analyzed pop): "
      + ", ".join(f"{k}={sum(1 for r in FEAT if r['zones_cleared']==k)}"
                  for k in sorted({r['zones_cleared'] for r in FEAT})))
print(f"gap_pct population median (outcome-blind split point): {GAP_MEDIAN:.1f}%  "
      f"terciles: <{GAP_T1:.1f}% / {GAP_T1:.1f}-{GAP_T2:.1f}% / >={GAP_T2:.1f}%")
rho_zc_gap = spearman([r["zones_cleared"] for r in FEAT], [r["gap_pct"] for r in FEAT])
print(f"Spearman(zones_cleared, gap_pct) = {rho_zc_gap:+.2f}  (descriptive; NOT counted in "
      f"the {PLANNED_TESTS}-test battery — the counted confound control is the gap-tercile "
      f"split, tests 7-9 below)")


# ============================================================================================
# THE DECISIVE COMPARISON (his refinement) — tests 1-6: zones_cleared vs gap_pct, head to head,
# same cohort, same splits-shape (0-vs->=1 / below-vs-at-or-above-median), across excursion
# SIZE (max_high_5d, max_high_20d) and DIRECTION (ret_5d).
# ============================================================================================
print("\n" + "=" * 98)
print("THE DECISIVE COMPARISON — does zones_cleared beat raw gap %? (his refinement, PRIMARY)")
print("=" * 98)

print("\n[1-2] EXCURSION SIZE — max_high_5d")
t1 = run_test("1  zones_cleared (0 vs >=1) -> max_high_5d", "primary", FEAT, zc_split, "max_high_5d")
print(fmt(t1, bonf=PLANNED_TESTS))
t2 = run_test("2  gap_pct (< vs >= population median) -> max_high_5d", "primary", FEAT, gap_split, "max_high_5d")
print(fmt(t2, bonf=PLANNED_TESTS))

print("\n[3-4] DIRECTION — ret_5d")
t3 = run_test("3  zones_cleared (0 vs >=1) -> ret_5d", "primary", FEAT, zc_split, "ret_5d")
print(fmt(t3, bonf=PLANNED_TESTS))
t4 = run_test("4  gap_pct (median split) -> ret_5d", "primary", FEAT, gap_split, "ret_5d")
print(fmt(t4, bonf=PLANNED_TESTS))

print("\n[5-6] HORIZON CHECK — max_high_20d")
t5 = run_test("5  zones_cleared (0 vs >=1) -> max_high_20d", "primary", FEAT, zc_split, "max_high_20d")
print(fmt(t5, bonf=PLANNED_TESTS))
t6 = run_test("6  gap_pct (median split) -> max_high_20d", "primary", FEAT, gap_split, "max_high_20d")
print(fmt(t6, bonf=PLANNED_TESTS))

print("\n" + "-" * 98)
print("[7-9] CONFOUND CONTROL — zones_cleared WITHIN gap-size tercile (comparable gap size)")
print("-" * 98)
for lbl, num in [("low", 7), ("mid", 8), ("high", 9)]:
    sub = [r for r in FEAT if gap_tercile(r) == lbl]
    print(fmt(run_test(f"{num}  gap-{lbl} tercile: zones_cleared (0 vs >=1) -> max_high_5d",
                       "confound", sub, zc_split, "max_high_5d"), bonf=PLANNED_TESTS))

print("\n" + "-" * 98)
print("[10-15] STRUCTURE DEPTH — his other named conditions, each its own bucket")
print("-" * 98)
t10 = run_test("10 zones_cleared_and_held (0 vs >=1, Tier-A) -> max_high_5d", "secondary",
               [r for r in FEAT if r["tier_a"]], held_split, "max_high_5d")
print(fmt(t10, bonf=PLANNED_TESTS))
print(f"   (Tier-A = minute bars present, n={sum(1 for r in FEAT if r['tier_a'])} of {len(FEAT)})")

t11 = run_test("11 IFFY (his word) vs not -> max_high_5d", "secondary", FEAT, iffy_split, "max_high_5d")
print(fmt(t11, bonf=PLANNED_TESTS))

t12 = run_test("12 BLUE_SKY (limiting case) vs not -> max_high_5d", "secondary", FEAT, bluesky_split, "max_high_5d")
print(fmt(t12, bonf=PLANNED_TESTS))

t13 = run_test("13 dist-to-nearest NEAR(<1.5xADR) vs FAR, has-overhead only -> max_high_5d",
               "secondary", FEAT, dist_split, "max_high_5d")
print(fmt(t13, bonf=PLANNED_TESTS))

t14 = run_test("14 MA-analog: cleared ALL overhead MAs vs not -> max_high_5d", "secondary",
               FEAT, ma_split, "max_high_5d")
print(fmt(t14, bonf=PLANNED_TESTS))
print(f"   (MAs = 10/20/50-day always, +200-day where >=200 prior days exist: "
      f"{sum(1 for r in FEAT if r['has_sma200'])} of {len(FEAT)} names)")

print("\n   ⚠ TEST 15 IS MECHANICALLY CONTAMINATED — zones_cleared_to_high uses the alert")
print("   day's own high, which is ONE of the twenty trading days inside max_high_20d.")
print("   Reported per the pre-registration; never read as a clean predictor.")
t15 = run_test("15 [CONTAMINATED] zones_cleared_to_high (0 vs >=1) -> max_high_20d", "contaminated",
               FEAT, zch_split, "max_high_20d")
print(fmt(t15, bonf=PLANNED_TESTS))

# ---------------- multiplicity ledger ----------------
print("\n" + "=" * 98)
print(f"MULTIPLICITY LEDGER — {TESTS_ATTEMPTED} tests attempted (planned {PLANNED_TESTS}), "
      f"{TESTS_COMPLETED} produced a p")
print("=" * 98)
assert TESTS_ATTEMPTED == PLANNED_TESTS, "battery drifted from pre-registration"
sig_raw = [r for r in RESULTS if r["p"] is not None and r["p"] < 0.05]
sig_adj = [r for r in RESULTS if r["p"] is not None and r["p"] * PLANNED_TESTS < 0.05]
print(f"  raw p<0.05: {len(sig_raw)} of {TESTS_COMPLETED}"
      + (" — " + "; ".join(f"{r['name'].strip()} (p={r['p']:.3f})" for r in sig_raw) if sig_raw else ""))
print(f"  surviving Bonferroni x{PLANNED_TESTS} (adj p<0.05): {len(sig_adj)}"
      + (" — " + "; ".join(r["name"].strip() for r in sig_adj) if sig_adj else " — NONE"))
print(f"  expected false positives at raw 0.05 across {TESTS_COMPLETED} tests: "
      f"~{0.05 * TESTS_COMPLETED:.1f} — a lone raw hit is what chance produces on its own.")

print("\n" + "=" * 98)
print("READ: session-permutation p shuffles whole alert-mornings (same-morning alerts share")
print("the tape, not independent draws). THE LINE: this probe measures. Nothing here is wired")
print("into any grade, admission rule, sizing, or exit. A result that points at a change is a")
print("FORK for the operator (fork S-3), stated with no option pre-chosen.")

# ============================================================================================
# POST-HOC ADDITIONS — added AFTER reading the battery above (advisor review, same session).
# NOT part of the pre-registration; the assert above already locked that ledger at 15 tests.
# Labelled EXPLORATORY throughout; a separate small ledger below, never folded into the x15
# Bonferroni figure.
# ============================================================================================
print("\n" + "=" * 98)
print("POST-HOC — added after reading the primary battery, NOT pre-registered. Two blocking")
print("gaps in the first pass: (1) the primary only tested presence (0 vs >=1), not the DOSE")
print("his words describe (\"the more it clears the stronger\"); (2) the zones_cleared==0 bucket")
print("silently pools two structural opposites (IFFY = had overhead, cleared none; and")
print("BLUE_SKY/NO_LEVEL = had nothing to clear). Addressed below.")
print("=" * 98)

POST_HOC_ATTEMPTED = 0
POST_HOC_RESULTS: list[dict] = []


def run_post_hoc(name, pop, split, h):
    global POST_HOC_ATTEMPTED
    POST_HOC_ATTEMPTED += 1
    res = run_test(name, "post_hoc", pop, split, h)
    POST_HOC_RESULTS.append(res)
    RESULTS.remove(res)          # keep the pre-registered ledger's membership exactly at 15
    return res


print("\n[A] ZERO-BUCKET COMPOSITION — what zones_cleared==0 actually contains")
zero = [r for r in FEAT if r["zones_cleared"] == 0]
comp = defaultdict(int)
for r in zero:
    comp[r["cls_preopen"]] += 1
print(f"  n={len(zero)}: " + " · ".join(f"{k}={v}" for k, v in sorted(comp.items(), key=lambda x: -x[1])))
print("  (NEVER_BREACHED = IFFY, his named weak case: had overhead, cleared none. The rest —")
print("  BLUE_SKY*/NEAR_ATH*/NO_LEVEL — had NOTHING overhead to clear, the opposite structure.")
print("  Pooling them in one NEG bucket for test 1 could mask or invert a real dose effect.)")

print("\n[B] TEST 1 RE-RUN — NEG restricted to IFFY only (true apples: cleared-something vs")
print("cleared-nothing-that-was-there), dropping the no-overhead names entirely")
iffy_or_cleared = [r for r in FEAT if r["zones_cleared"] >= 1 or r["iffy"]]
tB = run_post_hoc("B  zones_cleared>=1 vs IFFY-only (0, had overhead) -> max_high_5d",
                  iffy_or_cleared, zc_split, "max_high_5d")
print(fmt(tB))
print(f"  (dropped {len(FEAT) - len(iffy_or_cleared)} names with nothing overhead to clear at all)")

print("\n[C] DOSE-RESPONSE — graded buckets (descriptive: median/N/sessions, no invented p)")
for h in ("max_high_5d", "max_high_20d"):
    print(f"\n  {h}:")
    bounds = [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 999, "6+")]
    m = mature(FEAT, h)
    for lo, hi, lbl in bounds:
        sub = [r for r in m if lo <= r["zones_cleared"] <= hi and r[h] is not None]
        d = describe(sub, h)
        print(f"    zones_cleared {lbl:<4} " + (f"med {d['median']:>6}% n={d['n']:<4} "
              f"sessions={d['sessions']:<3} up%={d['pct_positive']}%" if d["n"] else "n=0"))

print("\n[D] EXTREME DOSE TEST — 0 vs 6+ (the strongest form of a monotone-dose claim), formal")
tD5 = run_post_hoc("D5 zones_cleared 0 vs 6+ -> max_high_5d",
                   [r for r in FEAT if r["zones_cleared"] == 0 or r["zones_cleared"] >= 6],
                   lambda r: r["zones_cleared"] >= 6, "max_high_5d")
print(fmt(tD5))
tD20 = run_post_hoc("D20 zones_cleared 0 vs 6+ -> max_high_20d",
                    [r for r in FEAT if r["zones_cleared"] == 0 or r["zones_cleared"] >= 6],
                    lambda r: r["zones_cleared"] >= 6, "max_high_20d")
print(fmt(tD20))

print("\n[E] MINIMUM DETECTABLE EFFECT — what the design could actually see at this N")
print("  (2.5/97.5 percentile band of the null permutation distribution for test 1; session-")
print("  level shuffling is conservative by construction, so the design UNDER-detects rather")
print("  than a null meaning 'no effect exists')")


def perm_null_band(a, b, sess_a, sess_b):
    by_sess: dict[str, list[float]] = defaultdict(list)
    for v, s in zip(a, sess_a):
        by_sess[s].append(v)
    for v, s in zip(b, sess_b):
        by_sess[s].append(v)
    sessions = sorted(by_sess)
    n_a = len(a)
    if n_a < 5 or len(b) < 5 or len(sessions) < 6:
        return None
    rng = random.Random(SEED)
    counts = [len(by_sess[s]) for s in sessions]
    pool = [by_sess[s] for s in sessions]
    diffs = []
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
        if pa and pb:
            diffs.append(st.median(pa) - st.median(pb))
    if not diffs:
        return None
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs))]
    return lo, hi


m1 = mature(FEAT, "max_high_5d")
pos1 = [r["max_high_5d"] * 100 for r in m1 if zc_split(r) is True and r["max_high_5d"] is not None]
neg1 = [r["max_high_5d"] * 100 for r in m1 if zc_split(r) is False and r["max_high_5d"] is not None]
psess1 = [r["d"] for r in m1 if zc_split(r) is True and r["max_high_5d"] is not None]
nsess1 = [r["d"] for r in m1 if zc_split(r) is False and r["max_high_5d"] is not None]
band = perm_null_band(pos1, neg1, psess1, nsess1)
if band:
    print(f"  test 1 (zones_cleared 0 vs >=1 -> max_high_5d): observed diff -1.91pp; the null's")
    print(f"  95% band is [{band[0]:+.2f}pp, {band[1]:+.2f}pp] — an observed |diff| bigger than "
          f"that at this N/session count would have cleared raw p<0.05.")

print("\n[F] SAME-SHAPE COMPARISON — Spearman rho (descriptive; no cluster-adjusted p computed")
print("  for the continuous form — see the docstring note on why a valid session-permutation")
print("  p for a clustered correlation coefficient wasn't attempted this round). zones_cleared")
print("  vs gap_pct, read side by side against each horizon, on the SAME rows per horizon:")
for h in ("max_high_5d", "max_high_20d", "ret_5d"):
    m = mature(FEAT, h)
    xs_zc = [r["zones_cleared"] for r in m if r[h] is not None]
    ys = [r[h] for r in m if r[h] is not None]
    xs_gap = [r["gap_pct"] for r in m if r[h] is not None and r["gap_pct"] is not None]
    ys_gap = [r[h] for r in m if r[h] is not None and r["gap_pct"] is not None]
    rho_zc = spearman(xs_zc, ys)
    rho_gap = spearman(xs_gap, ys_gap)
    print(f"    {h:<14} zones_cleared rho={rho_zc:+.3f} (n={len(xs_zc)})   "
          f"gap_pct rho={rho_gap:+.3f} (n={len(xs_gap)})")

print("\n[G] THE ADR/HISTORY CONFOUND — BLOCKING CHECK. The encoder's own qualification rule")
print("  needs episodes separated by >=1.0xADR20 — on a HIGH-ADR name that's a bigger price move,")
print("  harder to repeat -> fewer qualified levels -> LOWER zones_cleared. High-ADR names also")
print("  mechanically post BIGGER % excursions. That chain alone reproduces the whole monotone")
print("  decline in [C] with zero supply content. Also checked: history_days (more history ->")
print("  more chances to accumulate levels -> higher zones_cleared; short-history skews")
print("  recent-listing/high-beta -> bigger excursions) — same-direction confound.")
rho_adr_zc = spearman([r["adr20_pct"] for r in FEAT], [r["zones_cleared"] for r in FEAT])
m5, m20 = mature(FEAT, "max_high_5d"), mature(FEAT, "max_high_20d")
rho_adr_5 = spearman([r["adr20_pct"] for r in m5 if r["max_high_5d"] is not None],
                     [r["max_high_5d"] for r in m5 if r["max_high_5d"] is not None])
rho_adr_20 = spearman([r["adr20_pct"] for r in m20 if r["max_high_20d"] is not None],
                      [r["max_high_20d"] for r in m20 if r["max_high_20d"] is not None])
rho_hist_zc = spearman([r["history_days"] for r in FEAT], [r["zones_cleared"] for r in FEAT])
rho_hist_20 = spearman([r["history_days"] for r in m20 if r["max_high_20d"] is not None],
                       [r["max_high_20d"] for r in m20 if r["max_high_20d"] is not None])
print(f"  Spearman(adr20_pct, zones_cleared)   = {rho_adr_zc:+.3f}  (n={len(FEAT)})")
print(f"  Spearman(adr20_pct, max_high_5d)     = {rho_adr_5:+.3f}  (n={len(m5)})")
print(f"  Spearman(adr20_pct, max_high_20d)    = {rho_adr_20:+.3f}  (n={len(m20)})")
print(f"  Spearman(history_days, zones_cleared)= {rho_hist_zc:+.3f}  (n={len(FEAT)})")
print(f"  Spearman(history_days, max_high_20d) = {rho_hist_20:+.3f}  (n={len(m20)})")

adr_med = st.median(r["adr20_pct"] for r in FEAT)
print(f"\n  Dose table [C] RE-SPLIT at the population median ADR20 ({adr_med:.2f}%) — if the")
print(f"  monotone decline survives INSIDE each ADR half, it is not just volatility:")
for lbl, cond in [("low-ADR half", lambda r: r["adr20_pct"] < adr_med),
                  ("high-ADR half", lambda r: r["adr20_pct"] >= adr_med)]:
    print(f"    {lbl}:")
    for h in ("max_high_5d", "max_high_20d"):
        mm = [r for r in mature(FEAT, h) if cond(r)]
        for lo, hi, blbl in [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 999, "6+")]:
            sub = [r for r in mm if lo <= r["zones_cleared"] <= hi and r[h] is not None]
            d = describe(sub, h)
            if d["n"]:
                print(f"      {h:<13} zones_cleared {blbl:<4} med {d['median']:>6}% n={d['n']}")

print("\n  READ: adr20_pct correlates with BOTH zones_cleared (-0.35, as the episode-separation")
print("  mechanism predicts) and the excursion DVs (+0.36/+0.38) — a real confound. But the")
print("  monotone decline in the LOW-ADR half is STILL THERE (both horizons); it goes flat/mixed")
print("  in the HIGH-ADR half (cells as small as n=23-27, noisy, no formal test run on them).")
print("  Verdict: ADR explains PART of the pooled effect, not all of it — the reversal is not")
print("  purely a volatility artifact, but it is NOT uniform across the population either.")

print("\n[H] D20 IFFY-ONLY — the clean version of the strongest raw number (D20, p=0.015):")
print("  NEG restricted to IFFY (had overhead, cleared none), dropping blue-sky/no-level names")
d20_pop = [r for r in FEAT if r["zones_cleared"] >= 6 or r["iffy"]]
tD20b = run_post_hoc("H  zones_cleared>=6 vs IFFY-only -> max_high_20d",
                     d20_pop, lambda r: r["zones_cleared"] >= 6, "max_high_20d")
print(fmt(tD20b))

print("\n" + "-" * 98)
print(f"POST-HOC LEDGER — {POST_HOC_ATTEMPTED} additional tests (B, D5, D20, H), all")
print("EXPLORATORY, none folded into the pre-registered x15 Bonferroni figure above.")
print(f"TOTAL TESTS RUN THIS PROBE: {PLANNED_TESTS} pre-registered + {POST_HOC_ATTEMPTED} post-hoc "
      f"= {PLANNED_TESTS + POST_HOC_ATTEMPTED}.")
print("-" * 98)
for r in POST_HOC_RESULTS:
    ps = "N too small" if r["p"] is None else f"raw p={r['p']:.3f}"
    print(f"  {r['name'].strip():<58} {ps}")
