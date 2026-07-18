# ADR 0033 — Gap-vs-Structure ALIGNMENT as a Scored Meta-Rubric Axis (#331) — DRAFT for operator sign-off

Status: **DRAFT** (designed 2026-07-18, on the ADR-0015/0016 pattern). #329 child axis 3 of 3
(#328 theme · #330 structure · **#331 gap-alignment**). Read 0015 → 0016 first — the form
(boost-only post-composite credit), guardrails, and rollout discipline are inherited verbatim;
this ADR specifies only what differs. **Numbering note:** the #331 task line anticipated "0017"
as the next slot; 0017 was since taken by the management-judge load-bearing ADR — this axis is
0033. DESIGN ONLY: no code ships from this doc; the operator signs the credit table, then
STEP-0 runs, then (and only then) the shadow build is carded.

## The problem

The judge already sees raw `gap_pct` and can reason about gap-vs-structure qualitatively
(ADR 0011 rubric clause 4/5) — but, exactly as with theme (#328) and structure (#330) before
their axes, that read is implicit, uncalibrated, and untraceable. Meanwhile `ep_score` already
credits gap **MAGNITUDE** (tiered at 8/10/15/20%, `ep_detector.py::~1089`). What nothing
scores explicitly is gap **ALIGNMENT**: *where the gap lands relative to the structure the
stock brought in.* A 25% gap that still lands under a year of overhead supply (post-crash
bounce) and a 10% gap out of a tight base into blue sky get identical alignment treatment
today — magnitude alone can't tell them apart, and magnitude is the only gap signal scored.

## Scope boundary vs #330 (the other half of 0016's boundary)

**#330 grades the structure the stock brought INTO the catalyst day** (long-term trend, base
quality, extension). **#331 grades what the GAP did to that structure**: did it punch THROUGH
the overhead resistance (institutional conviction — buyers paid up through the entire supply
zone) or fade INTO the congestion it came from (gap absorbed by the base's own overhead)?
Keeping them separate keeps each calibratable alone — same reason as 0016.

## The alignment definition (v1 — the sign-off surface)

**Landing point** = the gap's arrival price: live shadow uses the alert row's `current_price`
at scoring time (the same row `_judge_shadow` already hands the #328/#330 shadows); the
historical STEP-0 backfill uses the alert-day `open_price` from `mi_daily_closes` (the only
stored landing point — an honest live-vs-backfill measurement difference, flagged, not hidden;
both are "where the gap put the price," one at 9:3x, one at the open).

**Structure levels** = #330's EXISTING as-of-prior primitives, reused not reinvented (all
computed strictly PRIOR to alert_date via `db.get_daily_bars_asof` — no lookahead):

| Level | Meaning | Reused primitive (search-before-build) |
|---|---|---|
| **`trailing_high`** | the overhead resistance ceiling (52w-ish high — the #356 Stage-2 gate's own reference level) | `structure_axis_shadow.compute_structure_features` already computes it (relaxed "whatever-history-is-loaded" variant, the only adequately-powered STEP-0 read) |
| **`base_high_15`** | top of the congestion zone the stock gapped out of — `max(high)` over the SAME prior ~15 sessions the RMV base-tightness window (`_RMV_LOOKBACK=15`) already covers | derived from the same `get_daily_bars_asof` bar list #330 already loads; the congestion zone IS the base RMV measures — one `max()`, no new data path |
| `prior_close`, `stage2`, `rmv_15` | context / telemetry on the shadow row | already on `compute_structure_features`' output |

**Round-number proximity** (named in the meta-rubric groundwork §D): NO existing primitive
exists anywhere in the codebase — v1 records `nearest_round_number` distance as **telemetry
only** (exactly how 0016 handled extension_ratio: rides along in the shadow row for future
calibration, never enters the credit decision). Anti-overfit: v1 credits on the two levels we
already trust, calibrates the third with accrued data.

### The credit mapping (v1 — boost-only, mirroring 0015/0016)

| Alignment state | Condition (landing L vs levels) | Credit | Marker |
|---|---|---|---|
| **Punch-through** | `L > trailing_high` — gap cleared the ENTIRE overhead supply, blue sky | **+1 tier-step eligibility** | `punch_through` |
| **Clears base only** | `base_high_15 < L ≤ trailing_high` — out of the near congestion, but overhead remains | 0 (near-miss band, recorded for calibration — same 0-until-evidence call as #330's `stage2_only_near_miss`) | `clears_base_near_miss` |
| **Fades into congestion** | `L ≤ base_high_15` — the gap landed inside the zone it came from | 0, **never negative** | `fades_into_congestion` |
| **Uncomputable** | insufficient prior history for either level | 0 | `unknown` |

Boost-only rationale, inherited: absence of alignment NEVER penalizes (the shared 6/5
evidence class — a naive gate risks the same false-negative class the theme gate was refuted
for; grossly broken structure is already hard-gated at detection). A bidirectional v2
(penalizing a gap into heavy overhead — the very question 0016 explicitly deferred to this
axis's territory) is a CHANGE_PROCESS question **with data**: STEP-0 + shadow accrual first;
if `fades_into_congestion` shows materially WORSE fwd outcomes at N≥30, that evidence goes to
the operator as a separate signed decision — never shipped inside this v1.

## Distinct from raw gap magnitude (the anti-double-count with ep_score)

`ep_score` already scores gap SIZE (8/10/15/20% tiers). This axis is deliberately
**scale-free**: `gap_pct` appears NOWHERE in the credit function — a small gap from a tight
base's top can punch through; a huge gap off a crushed base can still land under supply. The
credit conditions ONLY on WHERE the landing sits vs the two structure levels. `gap_pct` IS
recorded on the shadow row — as telemetry, so STEP-0 and the shadow can PROVE the axis adds
signal beyond magnitude (the stratified cross-tab below), not so it can be credited twice.

## STEP-0 calibration (before any shadow ships — same discipline as 0015/0016)

Read-only probe, mirroring `scripts/probes/_330_structure_step0.py` exactly:
`scripts/probes/_331_gap_alignment_step0.py` — backfill the alignment features onto the
`mi_theme_axis_shadow` cohort (461+ rows and accruing) ⋈ `mi_ep_scan_outcomes`:

1. Landing = alert-day `open_price` from `mi_daily_closes` (flagged live-vs-backfill
   difference above); levels = as-of-prior `trailing_high` + `base_high_15` from the same
   bars `_330_structure_step0` already loads (the probe can extend it, not fork it).
2. **Primary cross-tab**: `punch_through` vs `clears_base_near_miss` vs
   `fades_into_congestion` on fwd-5d avg / median / win≥+5% — does punch-through actually
   separate outcomes in the boosted direction?
3. **Magnitude-independence check (this axis's extra, load-bearing table)**: the same
   cross-tab STRATIFIED by gap-magnitude band (<10% / 10–15% / ≥15%). The axis earns its
   keep only if alignment separates outcomes WITHIN magnitude bands — otherwise it is
   magnitude in a costume and must not ship (that finding would go to the operator as
   "drop the axis," the yield discipline working).
4. Coverage honesty, inherited from #330's STEP-0: `trailing_high` has the same
   strict-252 vs relaxed variants — report both, credit on the relaxed one only if it is
   again the only adequately-powered read.
5. **N-gate**: if the boost direction is contradicted at N≥30 in any powered cell, the
   table changes BEFORE any shadow exposure. Cells under N≥30 are direction-checks only,
   never ship evidence (0015's caveat discipline).

## Composition under ADR 0024 (anti-triple-count of structure)

- Composes through the EXISTING `meta_rubric_compose.compose_final_tier` credits list —
  no new mechanism. **`NET_CAP = 1` is unchanged and is the anti-stacking backbone**: net
  movement across ALL axes (theme #328 + structure #330 + gap-alignment #331) clamps to
  ±1 tier-step total. `stage2_tight` (+1) and `punch_through` (+1) WILL co-occur (a
  Stage-2 name near its high is closer to blue sky) — the cap makes the stack
  structurally incapable of compounding: correlated boosts clip to +1, so
  triple-counting structure is impossible at the composition layer by construction.
- Below the cap, the axes stay honest by SCOPE, not arithmetic: #330 reads only pre-gap
  state, #331 reads only the landing vs that state, and gap magnitude stays in ep_score
  only — three disjoint questions sharing primitives, not three reads of one question.
- The judge's qualitative clause-4/5 gap-alignment read continues unchanged in shadow
  (double-count accepted IN SHADOW, exactly as 0015 accepted it for theme); the judge-vs-axis
  split resolves in the same rubric amendment that rides the M1/#335 flip commit (ADR 0024's
  established mechanism) — this axis adds a clause-5 line to that amendment, not a new one.

## Considered and rejected

- **Numeric alignment score** (continuous distance-through-resistance): more expressive,
  uncalibratable at current N, and breaks the sibling pattern (credit_steps ∈ {0, +1} is
  what compose_final_tier and the shadow diff read). Rejected for v1 — revisit with data.
- **Penalty for fades-into-congestion in v1**: rejected per the boost-only guardrail; it is
  the designated v2 question, data-gated (above).
- **Crediting `clears_base_near_miss` at +1 now**: no evidence yet either way; mirrors the
  #330 `stage2_only_near_miss` 0-until-evidence call. STEP-0/shadow accrual may promote it.
- **New resistance-level machinery** (anchored VWAP, pivot clusters, volume profile):
  violates search-before-build; the two levels the system already trusts come free from
  #330. Extensions are #329-checkpoint questions.

## Mechanics, guardrails, rollout — inherited from ADR 0015/0016 verbatim

Pure `gap_alignment_credit(features) -> {credit_steps, marker, reason}` (markers pinned to
the vocabulary above, never bespoke strings); a `gap_alignment_shadow.py` sibling of
`structure_axis_shadow.py` (same never-raises / never-mutates-`r` / audit-on-failure
discipline), writing `mi_gap_alignment_shadow` one row per (ticker, alert_date),
upsert-latest-scan-wins; called from `ep_detector._judge_shadow` immediately after the #330
call — same gate, same bar list (ONE `get_daily_bars_asof` fetch can serve both axes — an
implementation note for the build card, not a new data path). THE LINE: grade-affecting →
**operator signs this table + STEP-0 runs + the N-gate holds BEFORE any shadow ships;
shadow accrues BEFORE any flip**; flip = CHANGE_PROCESS + operator sign-off + N≥10 shadow
divergences with outcomes, folded into the ONE batched #335 re-grade (never a per-axis
spend, the operator's 6/18 cost directive). No detection gate, no threshold, no live grade
change on any agent authority.

## Rollout

1. Operator signs the credit table (or amends — the `clears_base_near_miss`-at-0 and
   telemetry-only round-number calls are the likely questions).
2. STEP-0 backfill + primary cross-tab + the magnitude-stratified independence check
   (read-only probe; N-gate applied).
3. Shadow build (Sonnet card, the #330 shadow's sibling — one session) → accrue.
4. Composition + flip at the #329/#335 checkpoint (CHANGE_PROCESS).
