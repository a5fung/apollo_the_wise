# Catalyst Rubric — Multi-axis fundamentals grader

**Phase**: LIVE — production gate. `CATALYST_RUBRIC_GATE_ENABLED` defaults
`true` (`constants.py`); the gate downgrades real grades
(`catalyst_quality → "routine"`, feeds `score_tier`) in `ep_detector.py`
(~line 2858). Shipped 2026-05-19 (Phase 5); operator-signed fixes
2026-06-28 (#320/#321, see change log).
**Origin**: ADR 0003 EP Selectivity Phase 1 (2026-05-16), user mandate
2026-05-14 for "rare EPs, not 100+/quarter."
**Design doc**: `analysis/2026-05-16/catalyst_rubric_design.md`
**Code**: `agents/market_intelligence/catalyst_rubric.py` + `scripts/fetch_ep_fundamentals.py`

## Definition

A multi-axis fundamentals scorer that grades each EP candidate's
**catalyst component** for the eventual meta-rubric. Output is a
**fundamentals_grade** (0-39 weighted composite), NOT the final EP
verdict — the final verdict composes catalyst + theme heat + technical
structure + gap alignment (Phase 4+).

**Methodology anchor**: Pradeep Bonde "neglect → acceleration → EP" —
the edge is when fundamentals **inflect**, not when absolute growth
is high. A name growing 50% accelerating to 100% is structurally
different from one growing 200% decelerating to 150%. Both have
triple-digit Y/Y; only the first is the EP setup.

## Architectural constraint (CRITICAL — read first)

This rubric grades the **fundamentals component only**. It MUST NOT be
the sole input to the final game_changer / strong / routine label.
NBIS at strong-not-game_changer per fundamentals is correct because
op_margin = -110% (no operating leverage yet) — composition with
theme heat + technical structure lifts it to game_changer.

**Do not over-tune the catalyst rubric to compensate for missing
upstream signals.** Add those signals as separate inputs, each with
their own SSoT + quarterly review.

## The 6 axes

### Axis 1 — Revenue trajectory (weight 2×, max 10 weighted)
Inputs: last 4-8 quarters from Polygon `/vX/reference/financials`.
Computed: `rev_yoy_q0`, `rev_yoy_q1` (Y/Y), `rev_qoq_q0`, `rev_accel`
(pp delta), `rev_accel_streak`.

Score bands (0-5):
| Score | Condition |
|---:|---|
| 5 | rev_yoy_q0 ≥ 50% AND rev_accel ≥ +10pp |
| 4 | rev_yoy_q0 ≥ 25% AND rev_accel ≥ +5pp |
| 3 | rev_yoy_q0 ≥ 15% AND rev_accel ≥ 0 |
| 2 | rev_yoy_q0 ≥ 10% AND rev_accel < 0 |
| 1 | rev_yoy_q0 > 0 |
| 0 | rev_yoy_q0 ≤ 0 (contracting) |

### Axis 2 — EPS trajectory (weight 1×, max 5 weighted)
Same shape as Axis 1 (Y/Y + acceleration). Weight 1× because EPS is
manipulable (buybacks, accounting). Score table parallels Axis 1.

**Small-base guardrail**: when `|EPS_q-4| < $0.10`, cap Axis 2 at
score 3 — Y/Y on tiny absolute bases is structurally unstable
(NBIS-class first-profitable cases get routed through Axis 6 bonus
instead).

### Axis 3 — Margin trajectory (weight 1×, max 5 weighted)
Inputs: gross / operating / net margin for q0, q1, q2.

**Threshold definitions**:
- "expanding" = `Δmargin ≥ +100bps` QoQ
- "contracting" = `Δmargin ≤ -100bps` QoQ
- "flat" = `|Δmargin| < 100bps`

Score (0-5):
- 5: all three tiers expanding for ≥2 consecutive quarters
- 4: op + net expanding q0 vs q1
- 3: at least one tier expanding, others flat
- 2: all flat
- 1: 1-2 tiers contracting
- 0: all 3 contracting

**De-correlator role**: Axis 3 catches "revenue growing but margins
shrinking" failure mode. Hard caps protect against extremes.

### Axis 4 — Beat vs consensus (weight 1×, max 5 weighted)
Inputs: revenue beat %, EPS beat % from yfinance estimates.

| Score | Condition |
|---:|---|
| 5 | rev ≥ +10% AND eps ≥ +30% |
| 4 | rev ≥ +5% AND eps ≥ +15% |
| 3 | rev ≥ +2% AND eps ≥ +5% |
| 2 | mixed (one beat, one in-line) |
| 1 | in-line ±2% |
| 0 | miss |

### Axis 5 — Guidance change (weight 2×, max 10 weighted)
Inputs: guidance text from earnings press release.

| Score | Condition |
|---:|---|
| 5 | Raised ≥ +20% above prior consensus |
| 4 | Raised 10-20% |
| 3 | Raised 5-10% |
| 2 | Reaffirmed (no change) |
| 1 | Reaffirmed with caveats |
| 0 | Lowered |

Weight 2× because guidance is the forward-looking signal institutional
algos react to. **NULL ≠ score 0** — missing guidance data triggers
missing-data scaling (see below), not the lowered-guidance hard cap.

### Axis 6 — Magnitude inflection bonus (weight 1×, max 4 bonus)
Boolean flags that boost score, layered on top of the 5 numeric axes:

- `first_profitable_quarter`: crossed from loss to profit AND remained
  profitable for ≥1 subsequent quarter (+1)
- `growth_milestone`: Y/Y revenue or EPS growth crossed a major
  threshold (25%, 50%, 100%) **by ≥+5pp AND beat the prior 7
  quarters' max by ≥+5pp** (+1) — persistence buffer prevents
  oscillation triggering/untriggering
- `sustained_acceleration`: `rev_accel_streak ≥ 3` consecutive
  quarters of positive Y/Y delta (+1)
- `structural_inflection`: headline-level cues like "first ever" /
  "new segment launch" (LLM-extracted; optional) (+1)

## Composite computation

```
composite = (
    2 × axis1 +        # max 10
        axis2 +        # max 5
        axis3 +        # max 5
        axis4 +        # max 5
    2 × axis5 +        # max 10
        axis6          # max 4
)
# Range: 0 – 39
```

**Label band cutoffs** (locked 2026-05-16):
| Composite | Label | Target frequency |
|---:|---|---|
| 30+ | `game_changer` | ~5-10 per quarter (NBIS-class) |
| 22-29 | `strong` | ~30-50 per quarter |
| 14-21 | `routine` | low-action; watchlist only |
| <14 | `weak` | filter out entirely |

## Missing-data scaling (Option A — LOCKED)

When some axes can't be scored (consensus data missing, etc.):

```
composite_scaled = sum_of_available × 39 / max_of_available_axes
```

Example (NBIS-class with strong Axes 1-3 but missing 4-5):
- Available: A1 (max 10), A2 (max 5), A3 (max 5), A6 (max 4) → max 24
- Scored: 10 + 5 + 4 + 4 = 23
- composite_scaled = 23 × 39 / 24 = 37.4 → `game_changer` ✓

This avoids structurally under-grading small-caps without consensus
data. Risk acknowledged: rewards data thinness slightly. Hard caps
still apply on raw axes.

## Hard caps (LOCKED)

Applied AFTER composite computation, regardless of score:

1. **Axis 6 `growth_milestone=False` AND `rev_yoy_q0 < 25%`** → cap
   at `strong` (no game_changer without crossing a magnitude threshold)
2. **Axis 1 = 0 (rev contracting)** → cap at `routine`
3. **Axis 3 = 0 (all margins contracting)** → cap at `routine`
4. **Axis 5 = 0 (guidance LOWERED, not missing)** → cap at
   `routine` (institutional algos sell lowered guidance
   unconditionally; setup will fail)

## Known limitations / open questions

1. **Polygon `/vX/reference/financials` coverage gaps**: ~12% of
   cohort tickers fall back to yfinance (recent IPOs, restated
   companies). yfinance lacks fiscal_year/fiscal_period attributes;
   fetcher falls back to index-based Y/Y lookup with
   `data_quality_flag='fiscal_attrs_missing_fallback_index'`.

2. **Axes 4-5 coverage**: only ~60-70% of cohort has consensus
   estimates + parsed guidance text. Missing-data scaling handles
   it, but partial-axis scoring is structurally noisier than
   full-6-axis scoring.

3. **Single-input limitation**: composite is the FUNDAMENTALS grade,
   not the final EP verdict. Phase 5 meta-rubric combines with theme
   heat (Phase 3 telemetry), technical structure (Phase 4.1), and
   gap alignment (Phase 4.2) for the actual production label.

4. **Operator-label divergence cases** (filed for quarterly review):
   VSNT, VIAV, ARX where rubric and operator labels diverge — useful
   calibration data for Phase 9 quarterly review.

5. **PROPOSED, AWAITING OPERATOR SIGN-OFF (2026-09-04): run the #321 live prior-year
   recovery BEFORE the 2026-05-28 beat+guidance carve-out.** Today the carve-out runs first
   and, when it fires, sets `_downgrade_reason=None` so the recovery never looks up the real
   number — 12 of the 19 missing-YoY cases in the 30d review were waved through on the
   heuristic with a computable real YoY sitting unchecked. Proposed order: recovery first;
   carve-out only when recovery returns None. This is a scoring-ORDER change on the money
   path (a name the carve-out keeps today can be downgraded on its real number), so per
   CHANGE_PROCESS it needs the operator's call, not the agent's. **$0 replay, 2026-09-04**
   (`compute_yoy_from_prior_year` offline against `mi_ep_catalyst_metrics` fiscal_period +
   q_revenue value, prior year from yfinance; the review's 12 = 8/06→9/04, plus the same
   cohort's three cases on 8/04-8/05). Forward returns from `mi_daily_closes`, close-to-close.

   ```
   ticker  date   kept grade    beat   guidance          recovery FIRST would…            fwd5d
   VOYG*   08-04  game_changer  +9.4%  raised/high       keep,  real +15.4%               +28.1%
   HGTY*   08-05  strong       +13.0%  raised/high       DOWNGRADE, real  -6.5%            -5.7%
   PRGO*   08-05  strong        +1.0%  reaffirmed/med    DOWNGRADE, real  -3.2%            -4.4%
   INSM    08-06  game_changer  +8.3%  raised/high       keep,  real +296.2%              -4.7%
   RPD     08-11  strong        +1.3%  raised/high       DOWNGRADE, real  -1.5%            -5.9%
   EROC    08-12  game_changer +46.0%  initiated/med     no prior-year row → carve-out     +3.9%
   GLBE    08-12  game_changer  +5.6%  raised/high       keep,  real +39.1%                +1.7%
   HRB     08-12  strong        +2.4%  raised/high       DOWNGRADE, real  +3.1% (<5 floor) -3.6%
   CRMD    08-13  strong        +6.6%  reaffirmed/high   keep,  real +156.8%               +1.1%
   SCSC    08-20  strong       +18.8%  initiated/med     keep,  real +17.2%                +3.0%
   CRWD    08-27  strong        +2.1%  raised/high       keep,  real +25.7%                -5.7%
   DG      08-27  strong        +0.8%  raised/high       no prior-year row → carve-out     +4.3%
   MBUU    08-27  strong       +12.0%  initiated/med     keep,  real +42.8%                -7.4%
   OKTA    08-27  game_changer  +1.2%  raised/high       keep,  real +10.6%                -1.4%
   VEEV    08-27  strong        +2.6%  raised/med        keep,  real +17.6%                +0.8%
   * outside the review's 12 (same cohort, one day earlier)
   ```

   Read: within the review's 12, only RPD and HRB flip; across the 15, four flip — and all
   four fell over the following week (mean -4.9%), none had a live entry (HGTY was
   `window:out_of_orb`; PRGO, RPD and HRB never reached the pipeline). Nine keep the same grade on a
   real number; two fall through to the carve-out unchanged. The four flips are verified real
   numbers: the extraction's current-quarter value equals yfinance's own current-quarter
   figure where present (HGTY 354.8 = 354.8, PRGO 1023.0 = 1022.8; RPD/HRB consistent with
   their series). Recommendation: approve — this is the 2026-06-05 "gate better in BOTH
   directions" case with N=15 replayed and zero cost to the eleven names that deserved to
   pass. Caveat: the replay used today's yfinance history; for the four flips the prior-year
   row was present on the alert day too (it is ≥4 quarters deep). On sign-off the code change
   is small — move the #321 block above the carve-out block; the carve-out's own condition is
   unchanged — and the carve-out entry below is then belt-and-suspenders, as its 2026-05-28
   architectural note anticipated.

## Quarterly Review Protocol

Per `user_quarterly_rule_review.md` discipline: rubric reviewed
quarterly, NOT for frequent tuning, but to **know deeply what we
filter and why**.

**First review fires**: Phase 6 ship date + 90 days (~late December
2026 / early January 2027).

**What the review produces**:
1. Rubric output × actual outcome cross-tab (21d max-favorable-excursion)
2. Per-axis Spearman correlation with forward returns
3. False-positives: composite ≥ 30 (game_changer) that didn't work
4. False-negatives: composite < 14 (weak) that WERE winners
5. Coverage report per axis (data-source improvement priorities)
6. Threshold drift candidates (require N≥30 evidence per
   `feedback_sample_size_discipline`)
7. Decisions: ship tweak / keep / file as long-term

**Output location**: `docs/decisions/0003-quarterly-review-YYYY-MM.md`
short doc. Logged in this file's change log.

**Anti-pattern explicitly avoided**: "we lost on KLAR therefore relax
X" single-case rule changes. Batch quarterly evidence, not single-
trade reactions.

**Data-gated review key**: `data_gated_reviews.yaml::catalyst_rubric_quarterly`
(to be filed when rubric ships to production gating in Phase 6).

## Change log (newest first)

### 2026-09-04 — #321 write-back: a recovered YoY now survives to every later tick (NSSC bug) + DG date guard

**Trigger**: the 30d data-gated review `yoy_missing_data_quality_investigation` (N=19). NSSC
2026-08-24 was recovered +10.1% at 07:25 ET (`catalyst_yoy_recovered_live`), then re-derived
from scratch at 09:30:07 — inside the 9:30-9:45 ORB window, where the fetch is off by design —
and DOWNGRADED `q_rev_yoy_missing_no_prior_year_comparable`. The 6/28 code comment claimed the
rescued grade "caches in `_catalyst_cache` for the in-window scans"; it did not on this path:
the gate block re-runs every 5-min tick from the DB-cached extraction (which never had the
YoY) and the recovered number was written nowhere a later tick could see.

**Evidence**: prod audit + `mi_ep_catalyst_metrics` rows for NSSC 8/24 (07:25 recovered, 09:30:07
downgraded, same extraction row `extracted_at` 07:25:27). Bug fix in an operator-approved
mechanism (6/28: "it's a BUG"), not a criteria change — no new evidence gate.

**What shipped**: `persist_yoy_recovery` writes the recovery result to a NEW column
`mi_ep_catalyst_metrics.yoy_recovered_json` (added at boot by `initialize_schema`; registered in
`scripts/preflight_db_updates.py`); `lookup_cached_metrics` carries it back as `_yoy_recovered`;
the #321 block reads it FIRST on every tick — a dict read, no latency, so it is honoured in the
ORB window — and fetches only when nothing is in hand and the window is closed. Written back
for BOTH outcomes (≥ floor and < floor) so a real below-floor number survives too. The carrier
is deliberately NOT `q_revenue_yoy_pct` / `raw_json.q_revenue_usd.yoy_pct`: if
`get_q_revenue_yoy_pct` returned the recovered number on later ticks the 6-axis rubric would
score and its composite gate could downgrade a name the recovery tick kept — a different gate
acting than the one that decided. Behaviour is identical except that the right number survives.

**Also (same commit, same bug class)**: `compute_yoy_from_prior_year` takes `alert_date` and
rejects a prior-year row whose period end is not roughly one year (+ reporting lag) before the
alert. DG 8/27 "Q2 FY2026" names the fiscal year by its STARTING calendar year; yfinance's
end-year labels put `prior_key (2, 2025)` on the quarter ending Jul-2024 — two years back. It
returned None on 8/27 only because yfinance carried five quarters; with eight it returns a
confidently-wrong number (the TAL 7/30 class). The band is deliberately loose
([−200d, +60d] around alert−1y): a $0 replay of all 102 prior-year matches in the 35-day cohort
changes NONE of them (a tighter 110-day band rejected three stale-but-correct fills —
BRUN/COHR/FN — and freshness is rubric semantics, not this guard's). Fail-closed: only ever
turns an answer into None.

**Anticipated effect**: zero change for every name recovered outside the window (18 in 30d);
a name recovered pre-market keeps its grade through the 9:30-9:45 ticks instead of being
re-downgraded (NSSC class: 1 in 30d). Verify-live: a populated `yoy_recovered_json` row, and
no same-day `catalyst_earnings_revenue_weak_downgrade` with reason `q_rev_yoy_missing…` for a
ticker that has an earlier `catalyst_yoy_recovered_live` row.

**Reversion-flag**: REFINEMENT of the 2026-06-28 #321 entry (same rule, the answer now persists).

**Status**: built + tested (`tests/test_yoy_writeback_and_window.py`), awaiting deploy
(`market-agent` scope) and next-market-day verify.

### 2026-09-04 — In-window #321 recovery, DETACHED, behind `live_yoy_recovery_inwindow` (default OFF — operator flip)

**Trigger**: same review. BE 2026-08-12 (game_changer, first seen 09:30:42 inside the ORB
window) and GPRK 8/31 (09:40:37) were downgraded `missing` because the fetch is off in-window;
both recovered on a later tick (+166.7%, +24.7%) once outside it. BE's HIGH alert fired at
09:50 — `window:out_of_orb`, the one confirmed pipeline consequence in the review (BE then fell
12.9% over the next five sessions, so the miss cost nothing — calibrates urgency, not the fix).

**Why not the calendar pre-fetch the review floated**: it cannot compute anything ahead of
time — `fiscal_period` and the current-quarter value only exist after the in-window Sonnet
extraction — so it could only warm the prior-year side; it needs a "who reports today" list
the code does not have (`is_earnings_day` is a per-ticker yfinance check; `get_fundamentals`
has no cache); and it would spend hundreds of speculative yfinance calls (~6 HTTP each)
pre-open with 429 risk to the 07:00-09:30 scan itself. Not built.

**What shipped instead**: when the block is in-window with no persisted answer, it starts the
SAME fetch as a detached task (`_spawn_yoy_recovery_background`: per-ticker-per-day dedup,
concurrency 2, 20s cap, loud on failure) and never awaits it — scan latency is untouched, which
is the 6/28 guard's whole reason — and the write-back lands for the next 5-min tick. BE would
have had its number by the 09:35 tick, inside the window. A name first seen at 09:40+ gets it
at the 09:45 tick and the existing ORB cutoff rule decides, as today.

**Bucket, plainly**: the signed #321 rule acting in the window it was excluded from purely for
latency, with the latency guarantee preserved — not a new criterion, no N≥10 needed. But it
changes in-window ACTING behaviour on the money path (a routine can become a HIGH → live ORB
entry), so it ships OFF. **Operator flip** = a `mi_safeguard_state` row
`('live_yoy_recovery_inwindow','global','on')` (or env `LIVE_YOY_RECOVERY_INWINDOW=true`);
nested inside the existing `live_yoy_recovery` toggle, so that kill switch still stops
everything. Recommendation: ON.

**Anticipated effect when ON**: ~2 names per 30d (BE/GPRK class) recovered one tick later
instead of 15-20 minutes later. Zero extra yfinance calls — the same fetch that runs at 09:50
today, started at 09:30.

**Reversion-flag**: NEW (toggle; default preserves today's in-window behaviour byte-for-byte).

**Status**: built + tested, default OFF, awaiting the operator's flip.

### 2026-07-24 — FL-5 reconcile: doc synced to code

Header was stale: read "PROVISIONAL — telemetry-only, not yet a production
filter" long after the Phase 5 ship (2026-05-19). `CATALYST_RUBRIC_GATE_ENABLED`
defaults `true` and the gate downgrades `catalyst_quality` to `routine` in
`ep_detector.py` (~line 2858), which feeds `score_tier` — this is a live
production filter, not telemetry-only. Also corrected the `Code:` pointer
(`scripts/score_catalyst_rubric.py` → `agents/market_intelligence/catalyst_rubric.py`,
which holds the live axis-scoring/`LABEL_BANDS`/composite logic that
`catalyst_rubric_runtime.py` calls at the gate call site). No code changed.

### 2026-07-13 — #416: M&A-filter binding-context guards A/B/C (operator-signed 7/12, rulings-pack R6)

**Trigger**: 7/4 Tier-2 sitting ratified 3 M&A-filter false-positives that suppressed real momentum
runners — FRMI +25%, ONDS +23%, MMED +23% (SUNE +216% correctly suppressed as the TP). #416 chartered
the amendment; signed 7/12 (all 3 §6 forks: IMAX confirmed FP · Guard-C = surgical port · priced FN tail).

**Evidence**: 896 historical `mna_filter_fired` rows. The 3 FPs root-caused to 3 DISTINCT fire-paths
(one guard each). Mechanism chosen by data — a "require-definitive" whitelist would flip ~890/896
(guts the filter; most real M&A suppress via buyout/tender-offer/going-private, binding but not
"definitive") → BLACKLIST of 3 narrow reject-guards instead. Full-text N-gate sim (prod): **7 flips /
5 distinct** — all 3 ratified FPs (MMED guard-A · ONDS guard-C · IMAX guard-A) + 2 proxy-missed finds
(WEN, IMVT) + FRMI (guard-B, proven separately — its audit row is truncated-at-write so the sim
couldn't parse it; guard-B REJECTS its reasoning, and the live guard runs pre-write). Blast radius
**≥~0.8% (a FLOOR** — the corpus replay under-counts on the 500-char-truncated rows; the live guard
runs pre-write on full text). ⚠ **PRE-DEPLOY GATE (advisor 7/13):** the N-gate sim used its OWN inline
regexes — before deploy, re-run the replay importing the SHIPPED `ma_filter` guard functions over the
896 rows, confirm the flip set still contains all 5 ratified FPs, and hand-classify every EXTRA flip:
if bare `could` / `talks` / `potential` drags in a REAL binding deal, that's a new false-negative
(entering a deal-pinned stock) → tighten `_MNA_SPECULATION` before shipping. Detail + tables:
`docs/analysis/416_mna_fp_amendment_2026-07-12.md`.

**Anticipated effect**: suppression rate falls ≤~1% of historical fires — negated/speculative
(guard A), exploration/agitation (guard B), acquirer-side/completed-deal (guard C) contexts stop
suppressing. Genuine binding target-side deals unchanged (SUNE + a plain "acquired by X" still fire).
Each guard is a per-path veto that falls through to the other independent paths.

**Reversion-flag**: REFINEMENT of the #410 pin-guard / polygon Path-B logic (tightening the fire
condition in the accuracy direction #410 intended). Guards A + C are NEW paths. Revert by removing the
3 guard predicates + their call sites in `ma_filter.py` (all tagged `#416 R6`).

**Status**: built + tested (15 guard tests + 29 ma_filter regression + suite 3089 green). **PRE-DEPLOY GATE PASSED 7/13** (shipped-code replay over 896: same 5-ticker flip set as the signed sim, SUNE preserved, the 2 extras are speculation not binding → no FN). PRE-DEPLOY
= the shipped-code corpus replay above (evidence must match code). NO same-day urgency — today's EP
scan window (7–10 ET) already ran, so this affects the NEXT day's scans; verify-live per path is
next-day regardless. Deploy market-agent on operator go after the replay confirms.

### 2026-06-28 — #321 + #320 LIVE: recovered YoY DRIVES the gate + stale-boost reset (operator: these are BUGS)

**The flip shipped (operator 6/28, `64e8ed4`).** The #149 shadow (below) accrued the cohort; the operator reframed both as BUGS, not strategy tuning: (a) #321 — the gate fired "no prior-year comparable" when the comparable IS available, just not in the news corpus; (b) #320 — the `confidence_multiplier` agreement-boost wasn't reset on the revenue-weak / prose-mismatch downgrades (only the pplx-hedge site reset it), so a routine name kept a 1.2× boost and phantom-alerted past the `score<50` skip.

**#321 — recovered YoY now DRIVES the gate.** In the downgrade block, when `_downgrade_reason == q_rev_yoy_missing_no_prior_year_comparable`, `fundamentals.compute_yoy_from_prior_year(ticker, fiscal_period, value)` matches the extractor's CURRENT quarter (new `fiscal_period` field, emitted by `catalyst_metrics_extractor`) to yfinance's PRIOR-YEAR same quarter (a year old → reliable; the staleness is in the MATCH not the value — validated prod 20/21 covered cases <3% vs the extraction truth), computes YoY, unit/scale-guarded. `>= EARNINGS_REVENUE_GATE_MIN_YOY` → clears the downgrade (real growth); `< floor` → keeps it with the real number; `None` → stays the conservative downgrade (NEVER fabricates). LATENCY GUARD: the fetch is SKIPPED in the 9:30–9:45 ORB-cutoff window (earnings classify pre-market; the rescued grade caches in `_catalyst_cache`). Toggle `live_yoy_recovery` / `LIVE_YOY_RECOVERY` (default on; revert = env + redeploy).

**#320 — `confidence_multiplier = 1.0` reset** added at the revenue-weak + prose-mismatch downgrade sites (mirrors the existing pplx-hedge reset). Shipped ATOMICALLY with #321 because the two MASK each other: of 16 phantom alerts since 5/14 (3 HIGH), 11 were #321-rescuable — the stale boost had been accidentally keeping the wrongly-downgraded winners alerting, so #320 alone would have dropped the rescues.

**Verify:** the 10:10 catalyst-downgrade digest surfaces a "🟢 N rescued" line (from `catalyst_yoy_recovered_live` audit). Follow-up #400: a DB toggle (instant revert) + retire the now-redundant #149 shadow block.

### 2026-06-05 — #149 SHADOW: deterministic yfinance YoY recovery (advisory; gate UNCHANGED)

**Root-cause framing.** The 5/28 carve-out (below) is LLM-corpus-dependent: it skips the downgrade only when the SAME news extraction that failed to produce `yoy_pct` *also* yields a beat + guidance signal. When the corpus is sparse, both fail → carve-out doesn't fire → downgrade stands. So the carve-out is a partial band-aid, not the root fix.

**The data isn't missing in the world.** Probe 2026-06-05 ran the 8 distinct affected names (HSAI, SNOW, BBWI, QFIN, ESLT, JOYY, LION, RL — all `q_rev_yoy_missing_no_prior_year_comparable`, all earnings catalysts) through `fundamentals.get_fundamentals` → `quarterly_revenue[-1].yoy_pct`: **8/8 (100%)** returned a usable prior-year-comparable YoY. The LLM extracts the current-quarter revenue from the press-release corpus but often can't compute the prior-year comparable; yfinance's `quarterly_income_stmt` carries 8 quarters incl. the same quarter 1yr prior — a deterministic, corpus-independent source for exactly the missing piece.

**What shipped (SHADOW only — `ep_detector.run_ep_scan`):** missing-prior-year-YoY earnings downgrades are captured in the gate block (cheap append, no I/O) and processed in a decoupled post-scan block (off the 9:45 ORB-cutoff path, bounded 30s, fail-open) that fetches the yfinance YoY and writes a `catalyst_q_rev_yoy_shadow_recovered` audit row with the recovered YoY + what the gate decision WOULD be (`_yoy_shadow_decision` helper, unit-tested). **The live gate is byte-identical — no name's grade changes.**

**Why the live flip was GATED (not shipped) as of 2026-06-05:** reversing the downgrade lets recovered-YoY names clear back to HIGH → auto-enter → real trades. That is a grade-gating change requiring CHANGE_PROCESS + operator sign-off + N≥10 backtest with forward-return evidence. Current cohort N=8 (< 10). Directional caution: 5 of 8 recovered YoYs are positive (would ADMIT more names to HIGH in a system currently over-trading non-EPs at realized −$10,124/24% WR), 3 are below threshold (BBWI −3.2 / QFIN −26.6 / LION −15.3 → correctly STAY DOWN on real data, not a missing-data proxy). The value is **gating better in BOTH directions**, not "un-downgrade more names." Shadow accrues the cohort; re-evaluate the flip at N≥10 with settled forward returns. **SUPERSEDED 2026-06-28** — the operator reframed this gate as a bug, not a strategy call needing the N≥10 methodology bar; see the entry above ("#321 + #320 LIVE"). The flip shipped, `live_yoy_recovery` / `LIVE_YOY_RECOVERY` acts live (default on, confirmed unset/no-override in both prod containers 2026-08-23), and is no longer gated.

### 2026-05-28 — Safety-net carve-out: guidance + beat overrides missing-YoY downgrade

**Trigger**: SNOW 2026-05-28 false negative. +37.5% gap on a Q1 beat (revenue $1.39B, +5.3% vs est) with raised guidance (4-source corroboration, high confidence) got downgraded to `routine` by the safety net in `ep_detector` purely because `q_revenue_usd.yoy_pct` was null (no prior-year SNOW Q1 in the structured fundamentals fetcher). Operator-identified blast radius: downgrade dropped `score_tier` from HIGH to MODERATE → Telegram alert suppressed → ORB entry pipeline never fired. Lost-alpha class, not cosmetic mislabeling.

**Evidence (data-gated review `rubric_safety_net_yoy_required` predicate fired N=10)**:
- Cohort: 10 cases since 2026-05-14 where extraction captured Q-rev value + beat-vs-est but `yoy_pct` was null
- Carve-out subset (beat>0 + guidance signal + conf ≥ medium): 6 — SNOW, BBWI, JOYY, RL, TATT, KLAR
- Mature subset of carve-out: 3 cases with ≥5d fwd returns settled — all positive (RL +4.59% / TATT +5.87% / KLAR +1.08%, +8.56% fwd_10d). Mean +3.85% fwd_5d.
- 4 cases still downgrade (no guidance signal): QFIN, ESLT, LION (+11.9% beat but no guidance → flat +0.37% fwd), ROIV (−34% miss → correctly suppressed). Confirms the safety net's intended catch zone.

**Spec** (in `ep_detector` downgrade block, applied AFTER `_downgrade_reason` is set):
```
SKIP downgrade IF:
  _downgrade_reason == "q_rev_yoy_missing_no_prior_year_comparable"
  AND q_revenue.beat_vs_est_pct > 0
  AND guidance.direction IN ("raised", "initiated", "reaffirmed")
  AND guidance.confidence IN ("high", "medium")
```

Scope deliberately narrow: only the `q_rev_yoy_missing_no_prior_year_comparable` reason is carved. Other downgrade reasons (`news_corpus_sparse_no_q_rev`, `extraction_failed_*`, `non_earnings_catalyst_no_q_rev_in_news`, `q_rev_yoy_X%_below_floor`) still fire as before — the safety net only loosens for the specific case where structured-extraction succeeded enough to capture a beat + guidance but couldn't compute YoY.

**Note on dropped clause**: original spec included `q_revenue.confidence == "high"` but verification showed 28/28 of beat-extracted alerts since 2026-04-15 have `confidence='high'` — the clause is decorative. Dropped to keep the spec honest. If future extraction calibration starts producing medium/low-confidence beat values, re-evaluate.

**Anticipated effect**:
- Today: SNOW would have stayed `game_changer` → HIGH score_tier → ORB-eligible (SNOW's existing 5/28 row is not retroactively updated, see ship discipline below)
- Forward: ~6 of every 10 missing-YoY-with-beat cases re-promote. The other 4 of 10 (no guidance signal) still downgrade per safety-net intent.
- Audit event `catalyst_downgrade_carveout_applied` emitted whenever carve-out fires, for telemetry/calibration.

**Reversion-flag**: NEW (loosens an existing filter; revert by removing the `if _downgrade_reason == "q_rev_yoy_missing_no_prior_year_comparable"` block in ep_detector.py).

**Status**: shipped 2026-05-28. Closes `data_gated_reviews.yaml::rubric_safety_net_yoy_required` with cohort evidence locked. Operator sign-off on the 4-case still-downgrade list confirmed 2026-05-28 in-session.

**Ship discipline note**: today's SNOW row in `mi_ep_alerts` stays `MODERATE`/`routine` by operator decision — the fix protects future cases only. Re-firing the rubric retroactively against today's row was offered but declined (operator: "leave SNOW as is for today").

**Per advisor 2026-05-28**: discipline rule (`feedback_sample_size_discipline.md`) for methodology changes (N≥10 backtest) IS met here via the data-gated review's `action_when_ready` clause; the review's predicate and forward-return criteria are the backtest. Honest count: full cohort N=10, carve-out subset N=6, mature carve-out N=3 (all positive). Conservative ship size; widening cohort over the next 30 days will validate.

**Architectural note (operator reframe 2026-05-28)**: this carve-out is a band-aid, not the principled fix. Missing data is its own state — `UNKNOWN`, not evidence of weakness. The right architecture treats:
- "Strong evidence of weak catalyst" (lowered guidance, miss, sparse news) → downgrade
- "Strong evidence of strong catalyst" (full rubric ≥ threshold) → keep grade
- "Missing data" → **fill the gap upstream**, then grade; only fall back to safety-net when the data is genuinely unrecoverable (recent IPO, restated, ticker change)

The carve-out is necessary today because the upstream data-fill isn't reliable. It should become belt-and-suspenders once `fetch_ep_fundamentals.py` is audited and the recoverable-but-missing cases are plumbed correctly. Filed as `data_gated_reviews.yaml::yoy_missing_data_quality_investigation` (earliest 2026-06-28). Until that investigation completes, the carve-out is load-bearing.

### 2026-05-17 — PROVISIONAL doc created

**Trigger**: Phase 2 SSoT discipline. ADR 0003 §5 produced Phase 1
diagnostic; rubric design locked yesterday (2026-05-16) with three
advisor refinements (EPS small-base guardrail, Axis 6 milestone
persistence buffer, Axis 3 +100bps margin threshold) and Gemini's
weighting revision (2× Axis 1 + 2× Axis 5, not 2× Axis 1+2).

**Status**: PROVISIONAL — running as one-shot analysis only. Production
wiring (Phase 3 telemetry) ships next week. Production gating (Phase 6)
gated on N≥20 settled advisory alerts in Phase 5.

**Anticipated effect at ship**: none — telemetry-only doc reflects the
analysis-only state today.

**Reversion-flag**: NEW.

---

### 2026-05-16 — Initial design locked (see `analysis/2026-05-16/catalyst_rubric_design.md`)

Design iteration covered:
- 6-axis structure (advisor + Gemini reviewed)
- Weighting (2× Axis 1 + 2× Axis 5 per Gemini)
- 4 hard caps including lowered-guidance cap (Gemini addition)
- Missing-data scaling Option A locked by user
- Quarterly review protocol per user discipline
- Architecture: rubric is ONE INPUT, not the final verdict
