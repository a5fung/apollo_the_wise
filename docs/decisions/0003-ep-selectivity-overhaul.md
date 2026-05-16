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

## 5. D1 fundamentals magnitude (Block 4) — STRETCH

Status: deferred to a follow-up session. Polygon `/v3/reference/financials`
fetcher not yet built. Block 4 was scoped as stretch and deprioritized
once Blocks 1-3 produced enough signal for the headline recommendations.
Filed as a separate work item; the catalyst-quality crosstabs in §3
already test the broad hypothesis (`routine` admits at 17% WR — already
clearly bad without a more granular grader).

## 6. EP detector latency (Block 5) — STRETCH

Status: deferred. CPA-class late-fire investigation needs a focused
query against `mi_ep_scan_log` to identify HIGH alerts where
`scan_time_et > 09:45 ET` and what gate held them. **Working
hypothesis** (to test in a focused session): pre-market RVOL gate
doesn't satisfy until later because of low pm-share floor for some
tickers; or catalyst grader latency from LLM round-trip. Quantify
how many HIGH alerts fire AFTER 9:31 ET that should have fired
pre-open. This is the path that converts CPA-class detected-late
losses into Class A entries.

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

### R3 — Drop Day-1 re-entry mechanic entirely
**Evidence**: 0.0% WR over 6 re-entries; methodology says first
breakout failure = setup invalidated.
**Action**: in `entry_pipeline`, after first stop-out, do not retry
same ticker same day.
**Reduction impact**: -6 / 58 = ~10% of traded alerts.

### R4 — In-theme scoring bonus (+10 pts for Accelerating/Mainstream)
**Evidence**: in-theme = 66.7% WR vs uncovered 39.6% WR (+27pp).
**Action**: add to `_score_ep` — `+10` if ticker is in an Accelerating
or Mainstream theme on alert_date.
**Selectivity impact**: alerts that score 50-60 (currently MODERATE
boundary) get nudged into HIGH if in-theme. Pairs with R1 — keeps the
genuinely high-context candidates.

### R5 — Loosen `session_rvol_low` rejection band
**Evidence**: 174 rejections, 48% would have been winners. The 1.0x
session RVOL floor is shedding alpha. The MIN_SESSION_RVOL floor
of 1.0 is too high during the first 15 minutes (volume curves are
still building).
**Action**: drop minimum session RVOL to 0.5x during 9:30-9:45 only;
keep 1.0x after. Or: shadow-track 0.5x for 30d and measure shadow-
admitted cohort WR.
**Reduction impact**: NEGATIVE (admits more) — but expected to ADMIT
WINNERS. Net effect is on cohort quality + opportunity-cost, not
volume.

### Cross-recommendation expected outcome
After R1-R5 ship: alert volume drops ~30% (MODERATE retired + gap
floor lifted); admitted cohort quality rises (themes + re-entry
removed); some session-RVOL alpha recovered. Hand-of-cards model:
fewer cards, better cards.

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
