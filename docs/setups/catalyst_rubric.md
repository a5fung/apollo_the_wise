# Catalyst Rubric — Multi-axis fundamentals grader

**Phase**: PROVISIONAL — telemetry-only, not yet a production filter.
**Origin**: ADR 0003 EP Selectivity Phase 1 (2026-05-16), user mandate
2026-05-14 for "rare EPs, not 100+/quarter."
**Design doc**: `analysis/2026-05-16/catalyst_rubric_design.md`
**Code**: `scripts/score_catalyst_rubric.py` + `scripts/fetch_ep_fundamentals.py`
**Future production wiring**: Phase 3 telemetry → Phase 5 calibration →
Phase 6 gating ship per `~/.claude/plans/i-want-to-plan-groovy-horizon.md`.

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
| 14-21 | `routine_correct` | low-action; watchlist only |
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
2. **Axis 1 = 0 (rev contracting)** → cap at `routine_correct`
3. **Axis 3 = 0 (all margins contracting)** → cap at `routine_correct`
4. **Axis 5 = 0 (guidance LOWERED, not missing)** → cap at
   `routine_correct` (institutional algos sell lowered guidance
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
