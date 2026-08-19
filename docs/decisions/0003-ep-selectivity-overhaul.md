# ADR 0003 — EP Selectivity Phase 1 (diagnostic baseline)

**Date**: 2026-05-16
**Status**: Phase 1 complete — recommendations not yet shipped
**Authors**: Apollo Assistant (with user mandate 2026-05-14)
**Supersedes**: none
**Phase**: 1 of 3 (diagnostic → shadow → ship)

## 1. Context

User mandate 2026-05-14: the EP detection system fires on essentially
every earnings gap-up during earnings season. Past 10 trading days at
the time of the mandate: **87 HIGH alerts (8.7/day average)**. Almost
all graded `catalyst_quality='strong'` — near-zero `game_changer`
discrimination. Linear extrapolation: ~180/month → ~550/quarter.

**Target**: EPs should be RARE — "a handful per quarter, not 100+."
Methodology (Pradeep Bonde / Qullamaggie / Stamatoudis) accepts low
win rates IF entries are exceptional setups. Current selectivity
admits every earnings gapper, then depends on stop-loss to manage
risk — trade-by-trade losses compound; win rate stays low because
entries lack edge.

**Specific examples driving the review**:
- **NBIS** (2026-05-13): 700%+ revenue growth — truly game-changing.
  Missed by M&A direction-blind bug (fix `446f700`), but ALSO would
  have been graded only "strong" not "game_changer". Grader doesn't
  see fundamentals magnitude.
- **5/14 cohort**: 11 HIGH alerts → 3 traded (CRMD/KLAR/CSCO) → 0
  winners. Methodology cohort **-$2,041** over 4 trades (excluding
  CRMD bug damage).

This Phase 1 ADR is **analysis only** — no filter changes ship from
this session. Recommendations go to Phase 2 (shadow telemetry over
30d) then Phase 3 (settled outcomes ≥ N20 with measurably better R).

## 2. Cohort summary

Pulled via `scripts/ep_selectivity_cohort.py` against the 60d window
ending 2026-05-15. Cartesian-explosion guard fired and was fixed on
first run — `mi_orb_shadow_trades` (multiple `signal_type` per
ticker-day) and `mi_ep_missed_outcomes` (multiple `source` values)
both required LATERAL collapse before joining forward returns.

| Metric | Count |
|---|---:|
| Raw `mi_ep_alerts` rows in 60d | 207 |
| Distinct (ticker, alert_date) after collapse | **165** |
| HIGH-tier alerts | **147** |
| MODERATE-tier alerts | 43 |
| Filter-rejected candidates (`mi_ep_missed_outcomes` 'scan_filter') | **1,147** |
| Filter-rejected with 5d forward return populated | 1,098 |
| HIGH alerts in last 30d (catalyst-label sheet) | 98 |

**Per-day rate**: 165 / 60 = 2.75 alerts/day across all tiers. 147 / 60
= **2.45 HIGH/day**. Already meaningfully below the 8.7/day cited at
the time of user mandate — but that figure was during peak earnings
season (5/05–5/14); 60d average regresses naturally as earnings
season tapers. The **selectivity problem is real but bursty** —
target of "a handful per quarter" requires structural filter changes,
not just calendar luck.

**Cohort partition (traded vs alerted-only)**:
- 58 alerts produced a paper trade (account_mode=paper, pnl_attribution
  IS NULL — methodology-only)
- 58 alerts were UNENTERED (HIGH or MODERATE that didn't fire entry)
- 49 alerts too recent for 5d forward (pending)
- **Traded win rate 56.9% / Alerted-only 29.3%** — system DOES preferentially
  trade the better alerts; the 87 unentered skew lower. The selectivity
  problem isn't "we trade everything"; it's "we ALERT on too much" —
  the alert volume itself sets up cognitive overload + dilutes operator
  attention to real setups.

## 3. Per-dimension findings (P1.2)

Full breakdowns at `analysis/2026-05-16/breakdowns.md`. Highlights:

### Catalyst quality (B2) — clearest signal

| Quality | N | Win rate | Avg ret |
|---|---:|---:|---:|
| game_changer | 7 | 42.9% | +4.8% |
| strong | 80 | 51.2% | +7.2% |
| routine | 18 | **16.7%** | +1.7% |
| unknown | 11 | 27.3% | -10.5% |

`routine` catalysts have a **17% win rate vs 51% for strong** — the
existing earnings-day pre-score boost (B11, shipped 2026-05-08) lifts
routine→strong on `is_earnings_day`, but the underlying admission
of routine catalysts as MODERATE/HIGH is the biggest single
selectivity leak. **Game_changer at 43% with N=7 is noisy** — the
grader is under-grading; only 7 cases in 60d crossed threshold.

### Score tier (B10)

| Tier | N | Win rate |
|---|---:|---:|
| HIGH | 73 | 52.1% |
| MODERATE | 43 | 27.9% |

Clean separator. MODERATE-as-trigger has a ~28% WR — supports
considering retiring MODERATE-tier auto-actions and keeping it as
watchlist-only.

### Gap size (A1)

| Bucket | N | Win rate | Avg ret |
|---|---:|---:|---:|
| 25%+ | 24 | 41.7% | +5.3% |
| 15–25% | 43 | 51.2% | +7.1% |
| 10–15% | 41 | 43.9% | +2.7% |
| 8–10% | 8 | **0.0%** | -2.4% |

8–10% gap bucket has **0% WR (n=8)** — the existing 8% floor is too
loose; the 10% floor on score promotion looks healthier. Lift floor
to 10% (or 12% in elevated regimes), 8-10% to watchlist only.

**⚠ SUPERSEDED 2026-08-19 on the floor value specifically** — see the dated addendum at the end of
this file (§ "2026-08-19 — R2's gap floor reversed"). The 12%-in-elevated-regimes half of this
recommendation was never built (confirmed by code search); only the flat 10% shipped. The win-rate
read above (N=8) is the reasoning that addendum documents as wrong, not merely incomplete.

### Pre-market RVOL@T (A2)

| Bucket | N | Win rate |
|---|---:|---:|
| 10x+ | 18 | **66.7%** |
| 5-10x | 11 | 27.3% |
| 2-5x | 5 | 60.0% |
| (no pm_rvol) | 82 | 39.0% |

10x+ pm_rvol is the cleanest single-variable separator. 5-10x at 27% is
counter-intuitive but n=11 is thin. Floor consideration: only admit
HIGH if pm_rvol≥5x OR session_rvol≥2x.

### Entry attempt (C2)

| Attempt | N | Win rate |
|---|---:|---:|
| 1 | 52 | 63.5% |
| 2 | 6 | **0.0%** |

**Re-entries lose 100% of the time (N=6).** Ship candidate: drop
Day-1 re-entry mechanic. Already partially gated by the 2026-05-11
gap-through rule (#73); 6 attempts post-gate is still 0/6. (The
sample is small but the pattern is structural — re-entering after
an ORB stop-out means the breakout already failed once.)

### Theme membership (E1)

| Bucket | N | Win rate |
|---|---:|---:|
| in-theme | 15 | **66.7%** |
| uncovered | 101 | 39.6% |

Strong tiebreaker dimension. In-theme alerts have 27pp higher win
rate. Cheap to ship — theme join already exists. Consider as
a SCORING bonus (e.g., +10 points if in Accelerating or Mainstream
theme on alert_date), not a hard gate.

### 5-min ORB shadow (C1)

| 5m shadow status | N | Win rate |
|---|---:|---:|
| no_entry | 16 | 56.2% |
| gate_blocked | 14 | **71.4%** |

Of the alerts where 5-min shadow was BLOCKED by a gate, **71% would
have been winners**. The 5-min mechanic is over-conservative — its
filters reject too aggressively. NOT a recommendation to promote
5-min to primary; rather a flag that the 5-min telemetry is finding
alerts the 1-min path catches better.

### Missed-EP (skipped) cohort by category

| Category | N | Win rate of rejected |
|---|---:|---:|
| outside_top20 | 477 | 40.5% |
| session_rvol_low | 174 | **47.7%** |
| pm_rvol_low | 87 | 28.7% |
| extension_gate | 49 | 24.5% |
| score_below_50 | 47 | 42.6% |
| mcap_low | 40 | 40.0% |
| catalyst_downgrade | 22 | 22.7% |
| atr_high | 6 | **0.0%** |
| cooldown | 15 | 40.0% |

**`session_rvol_low` is the biggest opportunity-cost gate** — it
rejected 174 candidates of which 48% would have been winners. The
1.0× session-RVOL floor is too tight on the rejection side.
Counter-evidence: `pm_rvol_low` (28%) and `extension_gate` (24%) and
`atr_high` (0%) are correctly rejecting losers. **The session-RVOL
gate is the single best candidate to LOOSEN.**

## 4. Class A/B/C/Chop/Dead split (P1.6)

Per `scripts/classify_ep_shape.py` — fetches 1-min bars from
Polygon for each HIGH alert, classifies intraday shape 9:30–11:00 ET.
N=117 HIGH alerts classified (30 alerts pending bar data or had no
bars).

| Class | N | Share | Win rate |
|---|---:|---:|---:|
| CLASS_A (clean ORB-high broken+held in window) | 58 | 49.6% | 58.3% |
| CLASS_B (late breakout: post-9:45 held OR post-10:00 exceed) | 5 | **4.3%** | 100% |
| CLASS_C (ORB-low broken, no same-day recovery) | 43 | 36.8% | 53.6% |
| AMBIGUOUS_CHOP (broken→failed→broke other side) | 11 | 9.4% | 12.5% |
| AMBIGUOUS_DEAD | 0 | 0.0% | — |

**Ambiguous-share = 9.4% — below 20% caveat threshold; structural
recommendations on this data are defensible.**

### Class B is NOT 30% — parallel-entry-path proposal not justified

The §G hypothesis from `data_gated_reviews.yaml` (lines 1958–1972)
predicted Class B might be 30%+ of HIGH alerts, which would justify
a separate entry mechanic. **The actual measurement is 4.3% (5 of
117)**. The parallel-entry-path proposal (§9) is **not data-supported**
at the MAGNA53 EP cohort level.

### Fixture mismatches surface a vocabulary distinction

User's qualitative labels for ONDS / KLAR / CPA / CSCO 5/14 + TRT
4/23 didn't match classifier output. Investigation:

- **TRT 4/23**: was a 9M EP (parallel methodology, `mi_9m_ep_alerts`
  table), NOT in MAGNA53 HIGH cohort. Classifier's
  `NOT_IN_COHORT` is correct.
- **ONDS 5/14**: never crossed MAGNA53 HIGH threshold.
  `NOT_IN_COHORT` is correct.
- **KLAR 5/14**: classifier → AMBIGUOUS_CHOP. Intraday shape WAS
  chop (broke ORB-high at 9:31, failed to hold, broke ORB-low at
  9:43). User's "Class B variant" framing was about the SECOND
  attempt at 10:10 ET, not the first attempt's shape.
- **CPA 5/14**: classifier → CLASS_A (broke high in window, held).
  User's "Class B" framing was about the EP DETECTOR firing late,
  not the shape. CPA's shape was actually clean Class A; we couldn't
  enter because we didn't have the signal in time.
- **CSCO 5/14**: classifier → CLASS_A (after priority fix; first
  draft incorrectly labeled CLASS_C). Matches user's read.

**Vocabulary note**: "Class B" in user discussion conflates three
distinct phenomena:
1. **Shape Class B** — intraday late-window breakout (what classifier
   captures): 4.3% of cohort.
2. **Detection-late** — EP fired AFTER 9:45 ET so we couldn't act.
   Separate from shape; captured in P1.7 (Block 5, not run in this
   session).
3. **Delayed EP (Pradeep)** — multi-day digest then breakout days/weeks
   later (TRT). This isn't an intraday shape issue at all; it's a
   "different setup needing different anchor" issue. Cohort question
   for parallel 9M / continuation-flag detectors, not MAGNA53.

Recommendation: keep §G's "Class B uncaptured" language only for
shape-level Class B (4.3%), and treat detection-late + Pradeep
delayed-EP as separate workstreams.

## 5. D1 fundamentals magnitude (Block C, ran 2026-05-16 PM)

Built and tested. Outputs:
- `scripts/fetch_ep_fundamentals.py` — Polygon `/vX/reference/financials`
  primary + yfinance fallback. 50-ticker sample fetched: 38 from Polygon
  with full 8 quarters, 12 from yfinance fallback (mostly recent IPOs).
- `scripts/score_catalyst_rubric.py` — applies 6-axis rubric with
  Gemini-locked weighting (2× Axes 1+5).
- `analysis/2026-05-16/catalyst_rubric_design.md` — full rubric spec
  with 4 hard caps and missing-data scaling.
- `analysis/2026-05-16/catalyst_rubric_scores.csv` + verification md.

### Fixture results (50 tickers, Axes 1-3 + 6 scored — Axes 4-5 require consensus + guidance data, deferred)

| Ticker | Expected | Got | Composite | Why |
|---|---|---|---:|---|
| CSCO | routine_correct | routine_correct ✓ | 16.25 | A1=2 decelerating, milestone cap fired |
| NBIS | game_changer | strong | 22.75 | A1=4 big rev growth, A3=1 op_margin -110% (still loss-making) |
| TRT | strong | routine_correct | 19.5 | A1=5 hot rev, A2=0 neg EPS, A3=1 margins contracting |
| ONDS | strong | routine_correct | 19.5 | Same pattern as TRT |
| KLAR | routine_correct | weak | 0.0 | Coverage gap (IPO, no quarterly history) |
| CPA | strong | weak | 6.5 | Low growth + milestone cap |

Label distribution across 50-ticker sample: 0 game_changer / 3 strong
/ 14 routine_correct / 33 weak. Conservative by design.

### Meta-rubric architecture (user lock 2026-05-16, Path 1)

The catalyst rubric grades the **fundamentals component** only. It is
**not the final EP verdict**. Fixture mismatches (NBIS→strong not
game_changer; TRT/ONDS→routine_correct not strong) are
**methodologically correct** — fundamentals alone don't capture:

- **Theme heat**: NBIS = neo-cloud in active AI theme (+27pp WR per
  Block 2 in-theme breakdown)
- **Technical structure**: gap through MAs, base shape, distance from
  52w high
- **Gap-vs-base alignment**: gap through resistance vs into congestion
- **Methodology fit**: explosive small-cap vs leader breakout vs
  delayed EP

The production architecture composes these inputs:

```
catalyst_rubric_score → fundamentals_grade ┐
theme_context boost                       ─┼→ meta_rubric → final EP label
technical_structure score                 ─┤
gap_alignment                            ─┘
```

Each input gets its own SSoT + quarterly review (per
`user_quarterly_rule_review.md` memory).

**Phase 2 implication**: ship `catalyst_rubric_shadow` audit event
recording the FUNDAMENTALS COMPONENT separately. Don't conflate it
with the overall EP label until the meta-rubric is built. Top-3
data-rich strong names from the 50-sample (RSI 29.25, TEAM 24.38,
NBIS 22.75) are good early-shadow validation targets.

### Top 5 scoring tickers in sample (Phase 1 sanity check)

| Ticker | Composite | A1 | A2 | A3 | A6 | Source |
|---|---:|---:|---:|---:|---:|---|
| RSI | 29.25 | 5 | 3 | 4 | 1 | Polygon |
| TEAM | 24.38 | 4 | 5 | 1 | 1 | Polygon |
| NBIS | 22.75 | 4 | 3 | 1 | 2 | yfinance |
| VG | 22.58 | 5 | None | 0 | 1 | Polygon |
| SITM | 21.12 | 4 | 0 | 5 | 0 | Polygon |

## 6. EP detector latency (Block B, ran 2026-05-16 PM)

Output: `analysis/2026-05-16/latency_audit.md`. N=64 HIGH alerts in
60d with `detected_at` populated.

### Emit-time distribution

| Bucket | N | Share |
|---|---:|---:|
| pre-market (best — fired before open) | 47 | **73.4%** |
| 9:30-9:44 (in ORB window) | 0 | **0.0%** |
| 9:45-9:59 (LATE — past cutoff) | 17 | **26.6%** |
| 10:00+ | 0 | 0.0% |

**Late-fire rate = 26.6%** — over a quarter of HIGH alerts emit after
the 9:45 ORB submission cutoff and CANNOT be acted on under current
mechanics. Each is a missed Class A entry.

The **zero alerts in 9:30-9:44** is structural — gates uniformly
release at 9:45+ scan tick, meaning ANY name not pre-market-qualified
gets pushed past the window.

### What blocks the late-fires (first filter_reason at earliest scan)

| Category | N | Notes |
|---|---:|---|
| score_below_50 | 4 | LLM catalyst grader was slow to promote — HUT/FROG/PGNY: 170 min latency from first scan to HIGH emit |
| pm_shares_floor | 3 | CPA-class — gapper with low pm float held by absolute 25K floor |
| outside_top20 | 2 | Gap rank didn't qualify until others dropped |
| rel_vol_low | 2 | session-RVOL gate during first 15 min |
| other | 2 | |
| (no reason recorded) | 4 | |

### CPA 5/14 fixture (user-flagged)

- Score 67.7, gap 13.12%, catalyst `strong`
- First scan at **09:31 ET** with reason `pre-mkt volume 7,058 < 25,000 shares`
- Detected (HIGH-promoted) at **09:55 ET**
- **Latency: 24 minutes** — clean Class A entry missed because of
  pm-shares absolute floor on a low-pm-float name that was already
  up 13% with a strong catalyst

### Implications (NEW R6)

### R6 — PM-shares absolute floor carve-out for high-score gappers
**Evidence**: pm_shares_floor blocks 3 of 17 late-fires, including
CPA. The 2026-05-08 carve-out lifts the floor when `pm_rvol ≥ 5x`
but doesn't help low-float names where pm volume hasn't built ratio
yet despite real catalyst.
**Action**: extend the carve-out to also bypass the absolute
`MIN_PREMARKET_SHARES=25000` floor when `gap_pct ≥ 10% AND
catalyst='strong'` — admit on relative anomaly via ATR-normalized
range or similar, not absolute share count.
**Caveat**: small N (3 cases); ship as shadow-only first to confirm
fewer false positives than current floor's intent (dead-zone
prevention).

**R7 — Catalyst-grader latency**: HUT/FROG/PGNY 170-min latencies
all root-cause to `score < 50` at early scans, promoted only after
LLM re-grading. Either (a) LLM call latency is high or (b) grader
is conservative on first read. Worth filing as a separate
infrastructure investigation — not a filter change, a pipeline
latency optimization. **Phase 1.5 followup.**

## 7. Score-weight regression (Block 6) — STRETCH

Status: deferred. Tables in §3 already surface the strongest
re-weight candidates without formal regression: under-weight
catalyst quality (separation routine vs strong is 35pp WR), gap
floor 8–10% admits zero winners, in-theme adds 27pp.

## 8. Recommendations — ship to Phase 2 shadow

Five recommendations, ordered by expected selectivity impact.
Phase 2 ships each as a shadow audit event (telemetry only, no
admit/reject change); Phase 3 promotes after N≥20 settled outcomes
show measurably better R-expectancy.

### R1 — Drop MODERATE auto-actions; treat as watchlist only
**Evidence**: MODERATE WR 27.9% vs HIGH 52.1% (n=43/73).
**Action**: MODERATE alerts emit to /pregame, no ORB entry attempt,
no order_placed. Operator can manually convert if conviction.
**Reduction impact**: -43 / 165 = -26% of cohort alerts immediately
gone from the auto-pipeline.

### R2 — Lift gap floor to 10% (was 8%)
**Evidence**: 8–10% bucket = 0.0% WR (n=8).
**Action**: `MIN_GAP_PCT` 8.0 → 10.0. Alternatively keep 8% as
watchlist and 10% as ORB entry trigger.
**Reduction impact**: -8 / 165 = -5% direct + tighter top-20 filtering
downstream.

### R3 — Drop Day-1 same-day re-entry from MAGNA53 ORB pipeline
**Evidence**: 0.0% WR over 6 re-entries; methodology says first
breakout failure = setup invalidated.

**Nuance (user feedback 2026-05-16)**: R3 is OK ONLY IF the cohort
we capture as "first attempt" is genuinely gap-and-go (Class A). For
Class B / delayed-EP shapes, re-entry is the RIGHT tactic — just
not on the same-day ORB. The proper home for re-entry-of-failed-EP
is the **9M Day-2 ORB** path (already exists) and the
**continuation-flag** detector (TRT 4/23 → 5/15 pattern). These
treat the breakout-day as a digest seed, not as the entry trigger.

**Block D audit empirically tested this hand-off** — for every
MAGNA53 HIGH alert in 60d that failed Day 1, walked forward 21 days
to check downstream pickup. **Results are sobering**:

- **Failed Day 1**: 112 of 115 HIGH alerts (97.4% failure rate)
- **69.1% of those failed names made +5% within 21d** = 76 alpha names
- **Capture rate of those alpha names by downstream detectors**:
  - Continuation flag (COILED/TRIGGERED/WATCH): 31.6% ✓ only meaningful
  - 9M EP: 5.3% (weak)
  - 9M sugar baby: **0.0%** (structurally broken — filter requires
    close>open + close in top 25% of range, which a stopped-out name
    almost never satisfies)
  - Next MAGNA53 EP within 21d: 0.0%
  - **ANY downstream pickup: 34.2%** — **65.8% of the alpha slips
    through entirely**.

Concrete alpha-slip names from the cohort: AMBQ (+38.7%), MRAM
(+42.7%), INOD (+57.4%), WEST (+30.7%), FLNC (+42.6%), VG (+14.5%),
VPG (+25.3%), AKAM (+13.8%) — all failed Day 1, made meaningful
21d moves, NOT captured downstream.

**Revised action**: R3 ships ONLY paired with the following downstream
gap closures (file as separate followups; shipping R3 in isolation
loses alpha):
1. **Sugar baby gate audit** — relax the close>open + top-25% close
   requirement so that MAGNA53-failed names with constructive late-day
   reversal can carry forward as Day-2 candidates. The 0% capture is
   structural, not data thinness.
2. **MAGNA53-failed → continuation-flag carryforward**: when a
   MAGNA53 EP fails Day 1, automatically register the ticker as a
   continuation-flag candidate (instead of waiting for the flag
   detector to independently discover it). The 31.6% capture rate
   shows the flag detector finds about 1-in-3 alpha names; this would
   lift coverage materially.
3. **Delayed-EP audit on 9M cohort**: this audit covered MAGNA53
   only. TRT was a 9M EP, not in this cohort. Repeat the audit on
   `mi_9m_ep_alerts` to size the 9M-side delayed-EP gap.

**Without these paired changes, shipping R3 alone trades a known
~10% loss-stream (0/6 re-entries) for a likely larger uncaptured-
alpha cost.** R3 still ships eventually; the order matters.

**Reduction impact**: -6 / 58 traded = ~10% of traded alerts.
Quality impact: those 6 attempts averaged -6.0% return. Paired
downstream capture work could recover the 30-60% of slipping alpha.

### R4 — In-theme scoring bonus (+10 pts for Accelerating/Mainstream)
**Evidence**: in-theme = 66.7% WR vs uncovered 39.6% WR (+27pp).
**Action**: add to `_score_ep` — `+10` if ticker is in an Accelerating
or Mainstream theme on alert_date.
**Selectivity impact**: alerts that score 50-60 (currently MODERATE
boundary) get nudged into HIGH if in-theme. Pairs with R1 — keeps the
genuinely high-context candidates.

### R5 — Loosen `session_rvol_low` rejection band — DOWNGRADED to shadow-only
**Original evidence (broad cohort)**: 174 session_rvol_low rejections,
48% would have been winners by 5d forward.
**Retrospective sim (block 2.5)**: when properly windowed to only the
9:30-9:45 ET first-15-min cohort (where the volume-curve building
argument applies), only **12 candidates** match, with avg ret -0.7%
and unclear win rate (most are pending or losers). The original
"48% WR" was an all-time-of-day aggregate; the time-windowed slice
that the rule would actually target is mediocre.
**Revised action**: do NOT ship R5 as a live filter change in Phase 2.
Instead, ADD a SHADOW audit event (`session_rvol_shadow_admit`) that
records candidates which would pass a 0.5× floor during 9:30-9:45,
along with their forward returns. Accumulate ≥30 settled outcomes
before reconsidering.
**Reduction impact**: zero (telemetry only).

### Cross-recommendation expected outcome
After **R1+R2+R3+R4 ship** (R5 deferred to shadow-only):
- Alert volume: 165 → 111 over 60d window (**-32.7%**)
- Cohort win rate: 43.1% → **58.2%** (+15.1pp)
- Cohort avg return: +4.5% → **+6.8%**
- Median return: +2.9% → **+6.7%**

These numbers come from the retrospective shadow simulation
(`scripts/ep_selectivity_shadow_sim.py`, output
`analysis/2026-05-16/shadow_sim.md`). They are DIRECTIONAL evidence,
not a guarantee — see Caveats below. Real Phase 2 shadow telemetry
in production is the actual test.

### Per-rule incremental contribution (data backing for §8.0)

| Rule | Alert delta | WR delta | Avg ret delta | Verdict |
|---|---:|---:|---:|---|
| R1 (drop MODERATE) | -48 | +9.0pp (43→52) | +0.9pp | **biggest lever** |
| R2 (gap floor 10%) | -1 | +0.7pp | flat | **fine cut** |
| R3 (drop re-entry) | -6 | +4.8pp | +1.0pp | clean structural cut |
| R4 (in-theme re-admit) | +1 | +0.6pp | +0.4pp | small but +ev |
| R5 (session_rvol 0.5×) | +12 | -5.5pp | -0.7pp | **don't ship; shadow only** |

### Caveats (read before believing the numbers)

1. **Retrospective**: filters applied to data they didn't shape.
   Real production Phase 2 shadow is the test.
2. **R3 sample size small (n=6)**: structural pattern is sound
   (failed breakout = invalidated setup), but the numerical lever
   is small in this cohort.
3. **R4 only n=1 admit** because few alerts in 60d were
   MODERATE + in Accelerating/Mainstream theme. The mechanism is
   right; the cohort just didn't have the data to validate.
4. **Sample 165 alerts** is below the N≥30-per-dimension feedback
   ship-gate. Treat each rule as directional, not definitive.
5. **Outcome metric mixing**: traded rows use entry-pnl R;
   unentered use 5d open-to-close return. WR direction is
   comparable; avg-ret only rough indicator.

## 9. Parallel entry path proposal — NOT recommended

§G hypothesized that "Class B uncaptured" required a separate entry
pipeline (620 method, basing detection, post-ORB-cutoff entries).
**Data does not support this for MAGNA53 EP cohort.**

- Shape Class B = 4.3% of HIGH cohort (5 alerts in 60d)
- Sample win rate 100% (n=5) — but n=5 is far below thresholds for
  any structural change
- User's "Class B" cases (TRT, ONDS) belong to OTHER setup types
  (9M, MODERATE) — different cohorts

**Recommendation**: do NOT build a parallel MAGNA53 entry path.
Instead, ensure the existing 9M Day-2 ORB system captures delayed-EP
shapes (TRT-class) and that the continuation flag detector captures
multi-day digests. Both already exist as parallel systems with their
own selectivity dynamics — better leverage than inventing a third
entry mechanic.

If user disagrees and wants Class B captured anyway, the right next
step is a separate cohort study with the trigger condition
"intraday late breakout" applied to a broader universe (not just
MAGNA53 alerts) — to see whether the setup has edge in general, not
just whether MAGNA53 misses it.

## 10. Open questions / scope deferred

- **P1.3 D1 fundamentals fetcher** (Polygon + yfinance) — operator-
  facing recognition test on NBIS/CSCO/KLAR pending.
- **P1.4 catalyst-prose operator labels** — sheet delivered (98 rows,
  `analysis/2026-05-16/catalyst_labels.csv`) but not labeled yet.
  Once labeled, retrain catalyst grader with magnitude rubric.
- **P1.5 score-weight regression** — formal model fit deferred; §3
  tables already surface the priorities.
- **P1.7 latency investigation** — CPA-class late fires need a
  separate `mi_ep_scan_log` walk to quantify how many HIGH alerts
  fired after 9:45 ET. Tightly couples to Class B vocabulary
  discussion.
- **R5 session_rvol shadow** — Phase 2 shadow telemetry needs an
  explicit audit event to record alerts the 0.5x floor would have
  admitted; build before any production change.
- **9M Day-2 cohort cross-tab** — TRT-class delayed EPs are
  the better testbed for "Class B" capture than MAGNA53; separate
  ADR.

## 10.1 Catalyst-labeling rubric (P1.4 operator instructions)

Sheet: `analysis/2026-05-16/catalyst_labels.csv` — 98 HIGH alerts in
last 30d. Columns: `ticker`, `alert_date`, `gap_pct`, `ep_score`,
`catalyst_quality` (current LLM grade), `catalyst` (1-line summary),
`claude_analysis` (LLM reasoning), `user_label` (BLANK — for you),
`user_notes` (BLANK — optional).

**For each row, set `user_label` to ONE of**:

| Label | Use when |
|---|---|
| `game_changer` | Genuinely transformative fundamentals: revenue growth ≥100% YoY (NBIS-class), guidance raise ≥30% over consensus, margin inflection from negative to positive, segment-changing news (FDA approval for primary product, contract worth >50% of mcap). The 1-in-50 case. |
| `strong` | Real beat-and-raise: revenue ≥20% growth + guidance raise + clear forward narrative. Not transformative, but materially better than expected. Most "strong" current grades will land here if accurate. |
| `routine_mislabeled` | Currently graded `strong` but actually pedestrian: single-digit beat, no guidance change, in-line revenue, generic management commentary. CSCO 5/14 type. Likely the biggest correction class. |
| `routine_correct` | Currently graded `routine`, you agree. Sanity check the grader is working when it does fire low. |
| `other` | Edge cases: M&A leak that should've been filtered, hedge phrase that should've downgraded, partial earnings (pre-announce only), data error in catalyst extraction. Put detail in `user_notes`. |

**`user_notes` (RECOMMENDED — capture context beyond catalyst prose)**.

Per user direction 2026-05-16: the catalyst rubric is one input of
many. Final EP conviction also depends on theme context, technical
structure, gap-vs-base alignment, sector heat. Capture these in
notes so the meta-rubric work later can use them:

- **Theme/sector context**: "neo-cloud in AI theme", "biotech FDA
  catalyst, EMA in oncology sub-theme", "energy independent E&P
  with crude rally tailwind". The Block 2 breakdowns showed
  in-theme +27pp WR — this is a separate input dimension.
- **Technical structure**: "gap up through 50d MA from base",
  "extended >50% in 30d", "VCP base 12 weeks, near 52w high",
  "no base, momentum-from-nothing"
- **Gap-vs-base alignment**: "gap-through prior consolidation",
  "gap into open air (no resistance)", "gap into prior failed
  breakout zone"
- **Methodology fit**: "small-cap explosive (Pradeep)", "leader
  breakout (Qullamaggie Stage 2)", "EP with neglect period (8-12
  months sideways)"
- **Standard catalyst notes**: "guidance raised but revenue only
  +8% YoY", "pre-announcement, full earnings 5/22", "partial Q
  earnings"

These notes will inform the meta-rubric design later. Don't worry
about completeness — capture what's salient. Empty `user_notes` is
fine for routine cases.

**Time estimate**: ~1.5-3 min per row × 98 rows = ~3-4 hours total.
Reading the catalyst column alone is usually enough; `claude_analysis`
adds context for marginal calls. Skip rows where the catalyst text is
empty / unreadable.

**Output use**: once 30+ rows are labeled (especially
`routine_mislabeled` cases), I can train a refined catalyst grader
with magnitude rubric. This feeds D1 (fundamentals-magnitude filter)
in a follow-up session. No urgency — labels can land over multiple
sittings.

## 11. Artifacts

- `scripts/ep_selectivity_cohort.py` — master cohort SQL + CSV
- `scripts/ep_selectivity_breakdowns.py` — per-dimension crosstabs
- `scripts/classify_ep_shape.py` — Class A/B/C/Chop/Dead classifier
- `analysis/2026-05-16/ep_cohort_alerts_60d.csv` — 165 alerts cohort
- `analysis/2026-05-16/ep_cohort_skipped_60d.csv` — 1,147 filter-rejected
- `analysis/2026-05-16/breakdowns.md` — §3 source tables
- `analysis/2026-05-16/classifier.csv` — per-alert shape labels
- `analysis/2026-05-16/classifier_summary.md` — §4 source
- `analysis/2026-05-16/catalyst_labels.csv` — operator labeling sheet
- `scripts/ep_selectivity_shadow_sim.py` — retrospective R1-R5 sim
- `analysis/2026-05-16/shadow_sim.md` — projected cohort delta

---

## 2026-07-21 — NBIS 2026-03-16 rubric calibration (review: nbis_rubric_calibration_gap)

Review premise (5/19) was "NBIS scored 27.0/39 strong vs operator game_changer (3pt gap)." **The premise
is now STALE** — re-running `scripts/probes/_nbis_rubric_diagnostic.py` today, the rubric scores NBIS
**13.76/39 (weak)** — a 16pt gap, not 3pt (rubric/extraction moved since 5/19). Per-axis: a1=3 (rev yoy
+684%, max) · a2=0 (eps yoy −109%) · a3=2 (margins flat) · a4=None (partial_consensus_data → `max_available`
capped 34) · a5=2 (reaffirmed) · a6=0 (no milestone). composite_raw=12 → scaled 13.76, no caps.

**Diagnosis:** the rubric is behaving as designed — it heavily penalizes negative EPS (a2=0) and
no-milestone (a6=0), which sinks a name whose only max axis is revenue growth. This is the
**hypergrowth-pre-profit tension**: a +684%-revenue neo-cloud in an active AI theme scores "weak" because
it isn't yet profitable and crossed no discrete milestone, while the operator's game_changer label weights
the revenue explosion far above those gates.

**Decision: NO code change** (single fixture = overfit, per the review's own DoD). Real calibration tension,
but a one-name weight tweak is the overfit the discipline forbids. **Watch for a 2nd fixture** of the same
shape (hypergrowth revenue + negative EPS + no milestone, operator game_changer, rubric weak) → at N≥2,
open a rubric-weight recalibration via CHANGE_PROCESS. Secondary note: a4=None (missing consensus) capped
max_available at 34/39 — a data-completeness gap that independently depresses the score.

---

## 2026-08-19 — R2's gap floor reversed: `MIN_GAP_PCT` 10.0% → 9.0% (full entry: `docs/setups/magna53_ep.md`)

**This section supersedes §3's gap-size recommendation and §8's R2 ("Lift gap floor to 10%") on the
FLOOR VALUE only.** Nothing else in this ADR is revised; R1/R3/R4/R5 and the rest of the Phase 1
diagnostic stand as originally written.

**What R2 got right**: the 8-10% bucket genuinely underperformed on a raw win-rate basis (0/8 in the
60d cohort available at the time) — that measurement was not wrong.

**What R2 got wrong**: treating a **0%-win-rate read on 8 trades** as sufficient grounds to raise a
selectivity floor, full stop. That is a pre-P3 standard (`docs/roadmap/ep_profitability_program.md`
§ THE PRINCIPLES, P3, added 2026-08-16: *"we need to remember EPs are rare and winrate is low… if we
hit a real EP we gain 10X, that's the distinction here"* — median/win-rate reads are banned as the
primary read for exactly this reason, they cannot see a 10x). Applied retroactively to the same
8-10% band with the tail-first lens P3 demands: **337R of R-available (`docs/analysis/
winner_r_available_2026-08-16.txt`) sits in that excluded band, against 174R in the entire pool
admitted today** — the band R2 called a loser by win rate holds two-thirds of the programme's own
≥10R tail. Zero wins on 8 small bets and the majority of the tail sitting in the same band are not in
tension; a win-rate statistic simply cannot distinguish them. That is the specific way the prior
reasoning was wrong, not merely thin on data — more N of the same statistic would not have fixed it.

**Resolution (operator-ruled 2026-08-19, priced in `docs/analysis/gap_floor_decision_table_2026-08-19.md`,
749 tier-A gap days)**: floor moves to 9.0%, recovering 8 of the 15 ≥10R winners this exact band was
found to exclude (`tests/fixtures/must_not_miss_eps.py` #577), for +6-8 candidates/day. 8.0% (full
recall) and 8.5% (priced, rejected — 56 extra gap-days buy 1 winner) were both on the table; 9.0% was
the operator's deliberate choice of the smaller option. Full reasoning + regime-floor disposition (the
"12% in elevated regimes" half of this section's own recommendation was never built) in
`docs/setups/magna53_ep.md`'s 2026-08-19 change-log entry, the live SSoT for this constant going
forward.
