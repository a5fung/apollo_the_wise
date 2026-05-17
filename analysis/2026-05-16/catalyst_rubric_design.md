# Multi-dimensional catalyst rubric — design (LOCKED 2026-05-16)

**Design decisions locked** (final):
1. **Axes 1 (Revenue) + 5 (Guidance) get 2× weight; Axis 2 (EPS) stays
   1×.** Per Gemini's refinement (2026-05-16): EPS is manipulable
   (buybacks, accounting one-offs); revenue + guidance are what
   institutions react to. Supersedes the earlier 2x-on-1-and-2 lock.
2. Acceleration thresholds (+10pp / +5pp Y/Y) static for Phase 1;
   recalibrate against hand labels in Phase 2.
3. Margin direction (Axis 3), not net income trajectory.
4. Hard caps: 4 total (revenue contracting / all margins contracting /
   no game_changer without milestone / **lowered guidance caps at
   routine_correct** — Gemini addition).
5. Fixture expectations: NBIS=game_changer, CSCO/KLAR=routine_correct.
6. Quarterly review cadence — see §11.
7. **Missing-data: scale composite by axes available** (Option A).
   `composite_scaled = sum_available × max_total / max_available`.
   Best for small-caps without consensus estimates.



**Purpose**: replace the single-axis "rev_yoy ≥100% = game_changer"
threshold with a multi-axis rubric that captures quality, sustainability,
and acceleration per user feedback 2026-05-16.

**Methodology anchor**: Pradeep Bonde "neglect → acceleration → EP" — the
edge is when fundamentals **inflect**, not when absolute growth is high.
A name growing 50% accelerating to 100% is structurally different from
one growing 200% decelerating to 150%. Both have triple-digit Y/Y; only
the first is the EP setup.

**Architecture note (user lock 2026-05-16, Path 1)**: this rubric grades
the **fundamentals component** of EP conviction — it is **not the final
verdict**. The eventual production architecture combines:

```
catalyst_rubric_score → fundamentals_grade ┐
theme_context (heat / stage)              ─┼→ meta_rubric → final EP label
technical_structure (MA distance, base)   ─┤
gap_alignment with prior structure       ─┘
```

The Phase 1 verification will produce conservative labels (NBIS=strong
not game_changer; TRT=routine_correct not strong) **because**
fundamentals alone don't capture the theme + technical multipliers.
This is the right design — composition lifts NBIS-class names to
game_changer when paired with hot-theme membership and clean technical
setup; pairs TRT-class with delayed-EP detection rather than calling
the catalyst day's fundamentals strong on revenue alone.

**Do not over-tune the catalyst rubric to compensate for missing
upstream signals** — the right answer is to add those signals as
separate inputs, each with its own SSoT + quarterly review (per user
discipline preference, memory: `user_quarterly_rule_review.md`).

## The 6 axes

### Axis 1 — Revenue trajectory
Inputs (last 4-8 quarters from Polygon `/vX/reference/financials`):
- `rev_yoy_q0` — most recent quarter YoY growth (the catalyst day's quarter)
- `rev_yoy_q1`, `rev_yoy_q2`, `rev_yoy_q3` — prior 3 quarters YoY
- `rev_qoq_q0` — most recent sequential growth

Computed:
- **`rev_accel`** = `rev_yoy_q0 - rev_yoy_q1` (pp delta — positive =
  accelerating; negative = decelerating)
- **`rev_accel_streak`** = consecutive quarters of positive `rev_yoy` deltas

Score bands (0-5):
| Score | Condition |
|---:|---|
| 5 | rev_yoy_q0 ≥ 50% AND rev_accel ≥ +10pp (high growth + accelerating) |
| 4 | rev_yoy_q0 ≥ 25% AND rev_accel ≥ +5pp |
| 3 | rev_yoy_q0 ≥ 15% AND rev_accel ≥ 0 (growing, not slowing) |
| 2 | rev_yoy_q0 ≥ 10% but rev_accel < 0 (decelerating) |
| 1 | rev_yoy_q0 < 10% but positive |
| 0 | rev_yoy_q0 ≤ 0 (contracting) |

### Axis 2 — EPS trajectory
Same shape as Axis 1 (Y/Y + acceleration). Different scoring weights
because EPS swings more on margin / one-offs / buybacks.

| Score | Condition |
|---:|---|
| 5 | eps_yoy_q0 ≥ 100% AND eps_accel ≥ +20pp |
| 4 | eps_yoy_q0 ≥ 50% AND eps_accel ≥ +10pp |
| 3 | eps_yoy_q0 ≥ 25% AND eps_accel ≥ 0 |
| 2 | eps_yoy_q0 ≥ 15% but eps_accel < 0 |
| 1 | eps_yoy_q0 ≥ 0 |
| 0 | eps_yoy_q0 < 0 |

**Small-base guardrail** (advisor 2026-05-16): when `|EPS_q-4| < $0.10`,
Y/Y growth is unstable (a swing from $0.01 → $0.05 = +400% but isn't
methodologically meaningful). Apply rule:

- If `|EPS_q-4| < $0.10`, **cap Axis 2 score at 3**. Flag axis as
  `small_base_capped=True` in output for visibility.
- This protects against the "first profitable quarter" edge case
  inflating Axis 2 to 5 from a base-effect rather than real leverage.
- The genuinely-game-changing first-profitable case still earns the
  Axis 6 `first_profitable_quarter` bonus (+1), so cap-at-3 doesn't
  erase the signal — it just routes it through the right axis.

### Axis 3 — Margin trajectory (quality of earnings)
Inputs: gross / operating / net margin for q0, q1, q2.

**Threshold definitions** (advisor 2026-05-16 — bps required to count
as direction, not noise):
- "expanding" = `Δmargin ≥ +100bps` QoQ
- "contracting" = `Δmargin ≤ -100bps` QoQ
- "flat" = `|Δmargin| < 100bps`

Score (0-5):
- 5: all three margin tiers expanding (≥+100bps) for ≥2 consecutive quarters
- 4: operating + net expanding (≥+100bps) q0 vs q1
- 3: at least one tier expanding, others flat
- 2: flat across all tiers
- 1: 1-2 tiers contracting
- 0: all 3 tiers contracting

This separates "real" growth (margin-expanding) from "revenue with
shrinking margins" (low-quality, often acquisitions / sub-par pricing).

**De-correlator caveat**: Axes 1 + 2 (revenue + EPS YoY) are
mechanically correlated ~0.8 when margins are stable. Doubling weight
on both doesn't strictly double-count (you want both to drive score)
but makes the composite revenue-sensitive. **Axis 3 is the
de-correlator** — under-weighting it lets the rubric miss the
"growing but margins shrinking" failure mode that Axis 3 is precisely
designed to catch. Hard caps (revenue contracting → routine, all 3
margins contracting → routine) protect against the worst case;
flagged in SSoT for awareness.

### Axis 4 — Beat vs consensus
Inputs: revenue beat %, EPS beat %, from estimates table or earnings
calendar API.

| Score | Condition |
|---:|---|
| 5 | rev beat ≥ +10% AND eps beat ≥ +30% |
| 4 | rev beat ≥ +5% AND eps beat ≥ +15% |
| 3 | rev beat ≥ +2% AND eps beat ≥ +5% |
| 2 | mixed (one beat, one in-line) |
| 1 | in-line ±2% |
| 0 | miss |

### Axis 5 — Guidance change
Inputs: guidance text from press release; consensus deltas where
available. May require LLM extraction from prose since structured
guidance data is rare in free APIs.

| Score | Condition |
|---:|---|
| 5 | Guidance raised ≥ 20% above prior consensus |
| 4 | Guidance raised 10-20% |
| 3 | Guidance raised 5-10% |
| 2 | Guidance reaffirmed (no change) |
| 1 | Guidance reaffirmed but with caveats |
| 0 | Guidance lowered |

### Axis 6 — Magnitude inflection (the Pradeep core)
Boolean flags that boost score, layered on top of the 5 numeric axes.

**Persistence buffer required** (advisor 2026-05-16): a name
oscillating 23% → 26% → 24% would trigger and untrigger the 25%
milestone every quarter — meaningless noise. Apply buffer:

- **first_profitable_quarter** — crossed from loss to profit AND
  remained profitable for ≥1 subsequent quarter (so we don't credit
  a one-off accounting tailwind that reverts) (+1 bonus point)
- **growth_milestone** — Y/Y revenue or EPS growth crossed a
  major threshold (25%, 50%, 100%) **by ≥+5pp AND beat the prior 7
  quarters' max by ≥+5pp**. E.g., growth went from prior-7q-max=20%
  to q0=27% qualifies (crossed 25% by ≥5pp). Growth oscillating
  23-26% does not (prior-max was already 26%, no real breakout
  through the threshold). (+1)
- **sustained_acceleration** — `rev_accel_streak ≥ 3` consecutive
  quarters of positive Y/Y delta (+1)
- **structural_inflection** — name appears in headlines like "first
  ever..." / "new segment launch" / "guidance raised twice this
  year" (requires LLM/Perplexity, optional) (+1)

## Composite mapping (LOCKED — Gemini-refined weighting)

Weighted composite — Axes 1 (Revenue) + 5 (Guidance) carry double
weight per Gemini 2026-05-16:

```
composite = 2 × Axis1 + Axis2 + Axis3 + Axis4 + 2 × Axis5 + Axis6_bonus
          (max 10)   (max 5) (max 5) (max 5) (max 10)   (max 4)
          = max 39
```

**Why Revenue (1) + Guidance (5), not EPS (2)**: EPS is mechanically
manipulable — buybacks reduce share count → "automatic" EPS growth
without operational improvement; one-time items inflate; accounting
choices distort. Revenue is hard to fake. Guidance is the forward-
looking signal institutional algos react to. Axis 2 stays in the
composite at 1× weight to flag operating leverage when present, but
doesn't dominate.

**Missing-data scaling** (Option A locked):
```
composite_scaled = sum_of_available_axes × 39 / max_possible_for_available_axes
```

Example: NBIS-class with strong Axes 1, 2, 3 but missing Axes 4 + 5
(common for small-caps without consensus estimates):
- Available axes: 1 (max 10), 2 (max 5), 3 (max 5), 6 (max 4) → max=24
- If scored: 10 + 5 + 4 + 4 = 23
- `composite_scaled = 23 × 39 / 24 = 37.4` → grades `game_changer` ✓

This avoids structurally under-grading small-caps without consensus
data. Risk acknowledged: rewards data thinness slightly (4 perfect
axes can outscore 6 mixed axes). Mitigation: hard caps still apply
on the raw-axis side (lowered guidance, revenue contraction).

| Composite | Label | Approx target frequency |
|---:|---|---|
| 30+ | `game_changer` | ~5-10 per quarter (NBIS-class — true rare event) |
| 22-29 | `strong` | ~30-50 per quarter (real beat-and-raise; methodology candidates) |
| 14-21 | `routine_correct` | low-action; watchlist only |
| <14 | `weak` | filter out entirely |

**Fixture sanity check** (verify before shipping):
- NBIS Q4 2025 (700% rev YoY + 7× accel): expected score ~32-36
  → `game_changer` ✓
- CSCO 2026 Q3 (~10% rev, flat accel, margin steady, in-line beat):
  expected score ~13-17 → `routine_correct` ✓
- KLAR (no game-changing growth or guidance): expected score ~10-15
  → `routine_correct` or `weak` ✓

**Hard constraints regardless of composite** (LOCKED):
1. Axis 6 `growth_milestone` = false AND rev_yoy_q0 < 25% → cap at
   `strong` (no game_changer without crossing a magnitude threshold)
2. Axis 1 score = 0 (rev contracting) → cap at `routine_correct` (no
   matter how high other axes; revenue contraction is structural)
3. Axis 3 score = 0 (all margins contracting) → cap at `routine_correct`
4. **Axis 5 score = 0 (guidance LOWERED) → cap at `routine_correct`**
   (Gemini 2026-05-16: institutional algos sell lowered guidance
   unconditionally; the EP setup will fail regardless of backward-
   looking revenue/EPS strength). When Axis 5 is MISSING (not
   reported), this cap does NOT apply — see missing-data scaling
   above. The cap is on actual lowered-guidance signal, not absence.

## Data sources

| Field | Primary | Fallback | Coverage notes |
|---|---|---|---|
| Quarterly revenue / EPS | Polygon `/vX/reference/financials` | yfinance `quarterly_financials` | Polygon coverage spotty for sub-$5B mcap; yfinance fills gaps |
| Margins (GP, OP, net) | Polygon | yfinance income stmt | derived from revenue + cost lines |
| Consensus revenue / EPS | yfinance `analyst_estimate` | FMP (paid) | weak signal for small caps; expect ~60% coverage |
| Guidance text | Press release (catalyst column already captured) | Perplexity prose | LLM extraction required |
| Magnitude inflection flags | Computed from 8-quarter time series | n/a | derived locally |

**Coverage realism**: expect Axes 1-3 to fill cleanly for ~85% of
cohort. Axis 4 (beat vs consensus) fills ~60-70%. Axis 5 (guidance)
needs LLM and may be sparse. Axis 6 bonuses are derived locally, no
external dependency.

For names with Axis 4/5 missing, fall back to composite of available
axes scaled to the same 22+ / 16+ / 10+ thresholds — i.e., grade on
fewer axes when data is thin.

## Why this shape vs alternatives

### Alternative A: single-axis (rev_yoy ≥ 100%)
Rejected — misses CSCO 5/14 case ("11% earnings growth, 10% revenue
growth — hardly transformative" per user) and misses acceleration
quality. Also overrates flat-100% names that have been at 100% for 4
quarters.

### Alternative B: LLM full-prose grader
Rejected — already what we have. Current grader doesn't see structured
financial data, just headline prose. Plus LLM grader gave routine vs
strong vs game_changer with near-zero discrimination per §1 of the ADR.

### Alternative C: Multi-axis structured (this proposal)
- Captures sustainability (Q/Q + 4-Q trajectory, not just one
  quarter)
- Captures acceleration (Pradeep core) explicitly via Axis 1.2/2.2
- Captures quality of earnings (margins, Axis 3)
- Has explicit hard constraints to avoid edge cases
- Falls back gracefully when data is partial

## Open design questions

1. **Weighting**: should the 5 axes have equal weight (1 each, max 5
   each) or should revenue (Axis 1) carry more weight than guidance
   (Axis 5)? Default proposed: equal weight. Pradeep would arguably
   prefer Axis 1 + Axis 2 + Axis 6 weighted higher than Axis 4/5.

2. **Acceleration threshold magnitude**: I used +10pp and +5pp Y/Y
   acceleration thresholds; these are rough. Should calibrate against
   user's hand-labeled set once that's in.

3. **Margin axis vs net income trajectory**: I went with margin
   trajectory because absolute net income jumps too much with
   buybacks / non-cash items. Margin direction = cleaner. Confirm?

4. **Cap rules**: I added 2 hard caps (no game_changer without
   crossing magnitude milestone; cap at routine if revenue
   contracting). Should there be more? Or none — let composite
   speak?

5. **Fixture validation**: rubric must correctly grade NBIS=
   game_changer (rev 700% yoy + 7x acceleration), CSCO=routine_correct
   (single-digit rev + flat acceleration), KLAR=routine_correct.
   Before we ship the fetcher, want to confirm these labels are
   what you'd assign.

6. **Once your catalyst sheet lands**: cross-tab rubric output vs
   your hand labels. Disagreement rate is the rubric's accuracy
   signal. If >30% disagreement, the rubric needs re-weighting.

## Implementation outline (once design is approved)

1. `scripts/fetch_ep_fundamentals.py` — pulls 8-quarter financials per
   ticker via Polygon (fallback yfinance). Caches as JSON per ticker.
2. `scripts/score_catalyst_rubric.py` — applies the 6-axis rubric to
   cached financials; writes `analysis/2026-05-16/catalyst_rubric_scores.csv`
   with composite + per-axis breakdown.
3. Apply to 50-ticker sample (6 fixtures + 44 stratified across
   outcomes) — verify fixture grades.
4. Cross-tab against your hand labels when those land.
5. Phase 2: ship as shadow audit `catalyst_rubric_shadow` (no live
   admit/reject change); accumulate ≥30 settled outcomes before
   replacing existing catalyst_quality column.

## Time estimate

- Design iteration with you: 30 min — 1 hr (this doc)
- `fetch_ep_fundamentals.py`: 1-1.5 hr (Polygon API + yfinance fallback)
- `score_catalyst_rubric.py` + tests: 45 min
- Fixture verification + cohort run: 30 min
- Cross-tab vs your labels (when ready): 30 min

**Total ~3-4 hours** of build time once design is locked.

## 11. SSoT location + quarterly review protocol

Per user discipline (memory: `user_quarterly_rule_review.md`): every
load-bearing filter/rubric must have a canonical document AND be
reviewed quarterly. NOT for frequent tuning — for **knowing deeply
what we filter and why**.

### SSoT location

When this rubric ships (Phase 2/3), the SSoT moves from this analysis
doc to **`docs/setups/catalyst_rubric.md`** alongside the existing
setup-SSoT pattern (`docs/setups/magna53_ep.md`, `docs/setups/ninem.md`,
etc. — established per CLAUDE.md "Trading Setup Changes" rule).

The SSoT will include:
- The 6 axes with their exact thresholds (this design doc's content)
- A change log: every threshold tweak with date + reversion-flag + N
- The quarterly review schedule + pointer to last review
- The catalyst-rubric data-gated review key in
  `data_gated_reviews.yaml::catalyst_rubric_quarterly`

### Quarterly review protocol

**Cadence**: every 90 days (e.g., 2026-08-15, 2026-11-15, 2027-02-15…),
fired automatically from `data_gated_reviews.yaml`.

**What the review computes** (single SQL + pandas pass):

1. **Rubric output × actual outcome cross-tab**:
   ```
   composite_label × 21d_max_high_pct_above_open
     game_changer × {n_winners ≥10%, n_losers, median return}
     strong × …
     routine_correct × …
     weak × … (named/skipped names that DID work — false negatives)
   ```

2. **Per-axis correlation with outcome**:
   Spearman rank correlation between each axis score (0-5) and 21d
   forward max-favorable-excursion. Surfaces which axes drove
   real outcome variance vs. which are decoration.

3. **False-positives** (rubric said `game_changer`, didn't work):
   Each one named with composite breakdown, prior 4-quarter financial
   history, and post-mortem note. **Goal: understand WHY rubric was
   wrong, not propose threshold tweak from N=1.**

4. **False-negatives** (rubric said `weak`/`routine_correct`, BIG winner):
   Same shape. Filter axes that under-scored a real winner — was
   it a data gap, a missing axis (e.g., M&A leak / contract-win that
   shows up in headline but not financials), or a calibration miss?

5. **Coverage report**: per axis, % of cohort with full data. Drives
   data-source improvement priorities (e.g., "Axis 5 guidance fills
   only 40% — should we invest in earnings-call-transcript parsing?")

6. **Threshold drift candidates**: any axis where ≥30 alerts in the
   cohort fall within ±1 score band of a threshold AND outcome
   variance suggests recalibration. Surface as REVIEW_REQUIRED status;
   actual ship requires standard SSoT change-log + N≥10 backtest +
   reversion flag.

**Output**: `docs/decisions/0003-quarterly-review-YYYY-MM.md` — short
2-3 page write-up with the cross-tabs, false-positives/negatives,
coverage notes, and explicit DECISIONS (ship tweak / keep rule / file
as long-term). Logged in `docs/setups/catalyst_rubric.md` change log.

**Threshold for proposing a change**:
- Single false-positive / false-negative case → NOT a change trigger.
  Log in review for awareness.
- ≥3 false-positives at same axis-score band over the quarter → file
  for recalibration with N≥30 backtest evidence.
- Coverage gap forcing the rubric to skip ≥10% of cohort → infra
  investment priority, not a rubric change.

**Anti-pattern explicitly avoided**: "we lost on KLAR therefore relax
the routine_correct floor." Single-case reactions create the ship-
revert-restore oscillation pattern documented in CLAUDE.md
(parabolic_short days_up_streak 2026-05-08 cycle is the cautionary
tale).

### Filing the first quarterly review entry

When the rubric ships (Phase 3), file
`data_gated_reviews.yaml::catalyst_rubric_quarterly`:

```yaml
- review_id: catalyst_rubric_quarterly
  title: "Catalyst rubric quarterly review"
  question: "Per-axis outcome correlation, false-positive/negative
             analysis, threshold drift surface."
  predicate_sql: |
    SELECT COUNT(*) FROM mi_catalyst_rubric_scores
    WHERE scored_at >= NOW() - INTERVAL '90 days';
  threshold: 30   # ≥30 settled scored alerts for a meaningful review
  earliest_review_date: <ship_date + 90 days>
  status: pending
  cadence: quarterly  # re-arms after each review completes
```

This treats the review like any other data-gated review — surfaces
in Sunday weekly digest when ripe, no ad-hoc remembering required.
