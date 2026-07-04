# ADR 0015 — Theme as a Scored Meta-Rubric Axis (#328) — DRAFT for operator sign-off

Status: **ACCEPTED** (operator-signed 2026-07-04 AM, as proposed — Mainstream stays tie-break v1, upgradeable at the #329 checkpoint) (designed 2026-07-03 eve; the stage→credit table is the operator's
sign-off surface — Saturday). Author frame: #329 meta-rubric composition, child axis 1 of 3
(#328 theme · #330 structure · #331 gap-alignment).

## The problem
Theme is Pradeep's **#1 catalyst driver** (`user_pradeep_catalyst_hierarchy`), yet today it is
DISPLAY-only metadata on the EP alert plus a *qualitative* weighing inside the holistic judge.
It is not a scored, calibrated, traceable input anywhere (`user_meta_rubric_architecture`:
"NBIS = neo-cloud smack in the middle of hot AI themes… boost it to game-changer").
Evidence both ways, and the design must honor BOTH:
- **For credit**: in-theme cohort ran **+27pp WR** vs uncovered (Block-2 breakdown, 5/16).
- **Against gating**: the 6/5 backtest **refuted** the naive theme-gate — themeless names were
  88% of HIGHs, avg +5.73%, and held the +137% winner (`ep_fire_panel_load_bearing_design`).

## Decision (proposed)
**Theme = a BOUNDED, BOOST-ONLY, post-composite tier adjustment ("Axis T"), shadow-first.**

1. **Form: post-composite adjustment, NOT a 7th composite axis.** The 6-axis rubric keeps
   grading FUNDAMENTALS cleanly (the meta-rubric memory explicitly wants the fundamentals
   component recorded separately). Axis T acts on the LABEL boundary after the composite:
   `label + theme_credit → adjusted_label`. Legible in `/why` ("strong + Accelerating theme →
   game_changer"), impossible for a hot theme to arithmetically mask weak fundamentals.
2. **Boost-only (hard guardrail from the 6/5 evidence):** absence of a theme NEVER penalizes;
   Fading/Retired = zero credit, never negative. This axis can only ADD conviction.
3. **Stage→credit table (v1 — THE SIGN-OFF SURFACE):**

   | Membership state | Credit | Rationale |
   |---|---|---|
   | Accelerating | +1 tier-step eligibility (routine→strong, strong→game_changer) | Pradeep #1; the NBIS case |
   | Nascent | +1 step ONLY within the near-miss band (composite within ~10% of the boundary) | early = real but unproven |
   | Mainstream | boundary tie-break upward only | sustain, don't chase |
   | Fading / Retired | 0 | never negative |
   | **Stands-alone** (#319) | 0, marker `standalone` | no credit, NO penalty |
   | **Blind-spot** (#319/#325 coverage untrusted) | 0, marker `blind_spot` | unknown ≠ absent |

   v1 is stage-only — deliberately NO score/rs_avg scaler yet (anti-overfit; calibrate v2
   with accrued data, `user_quarterly_rule_review`).
4. **STEP-0 calibration before the shadow even ships:** run the proposed table against the
   **#329 backfill cohort (N=452 historical theme-axis rows**, `theme_axis_shadow.py` /
   `backfill_theme_axis_shadow.py`) — per-stage fwd-return deltas for adjusted-vs-actual
   labels. If a stage's boost direction is contradicted at N≥30, the table changes BEFORE
   any live exposure. (This converts sign-off from taste to evidence.)
5. **Shadow mechanics (the build, post-sign-off):** a pure
   `theme_axis_credit(membership, coverage_state) -> {credit_steps, marker, reason}` in
   `catalyst_rubric_runtime`; applied in the decision path SHADOW-ONLY — the adjusted label is
   logged (`theme_axis_shadow_adjusted` audit + a field on the decision row) beside the live
   label. The judge's qualitative weighing continues unchanged (double-count risk is accepted
   IN SHADOW; the #329 composition decides the judge-vs-axis split at flip time).
6. **Flip gate:** grade-affecting → CHANGE_PROCESS + operator sign-off + N≥10 shadow
   divergences with outcomes + the #335-cluster operator-label yield. Never on agent authority.

## Considered and rejected
- **(B) 7th composite axis (points):** lets theme arithmetically rescue weak fundamentals;
  muddies the fundamentals_grade contract. Rejected.
- **(C) Gate-threshold shift** (Accelerating → lower composite gate — the hint in
  `get_theme_membership`'s docstring): functionally near (A) but acts invisibly on the gate;
  (A)'s explicit tier-step is more legible/traceable in `/why` and in the shadow diff. Rejected.
- **(D) Theme-gating / penalty for absence:** refuted empirically 6/5. Rejected permanently.

## Composition & prerequisites
- Composes under **#329** with #330 (structure) and #331 (gap-alignment) as sibling
  post-composite adjustments; interaction rules (stacking caps — e.g. max +1 step TOTAL across
  axes) are #329's call, not this ADR's.
- **Soft-prereq #325** (theme coverage trust): the blind-spot marker consumes its output; the
  axis ships with blind-spot=0 regardless, so a coverage regression degrades to no-op, never
  to wrong credit.

## STEP-0 calibration — RUN 7/3 eve (read-only, mi_theme_axis_shadow ⋈ mi_ep_scan_outcomes)

| Stage | n | settled 5d | avg 5d | med 5d | win ≥+5% |
|---|---|---|---|---|---|
| Accelerating | 16 | 13 | **+18.0%** | +13.0% | **10/13 (77%)** |
| Mainstream | 15 | 12 | +14.0% | +11.4% | 8/12 (67%) |
| Fading | 11 | 9 | +11.1% | +8.8% | 6/9 (67%) |
| Nascent | 8 | 4 | +5.4% | +7.2% | 2/4 |
| (none) | 406 | 236 | +9.6% | +6.0% | 131/236 (56%) |

**Reading:** the table's DIRECTION holds. Accelerating full credit is strongly supported
(+18.0 vs +9.6 themeless; 77% vs 56% win). Fading-at-zero is validated as conservative —
Fading is not poison (+11.1%), merely not special, and boost-only means we never penalize it.
Nascent: no signal at N=4 → the near-miss-band-only caution stands. **Operator question:
Mainstream (+14.0%, 67%) outperforms more than tie-break credit implies — upgrade it to a
near-miss band like Nascent, or hold v1 conservative?** Caveats: N per themed cell is 9-13
(direction-check, NOT the N≥30 ship bar); the cohort is ALL HIGH-grade rows (the backfill's
scope), so tier-STEP effects (routine→strong) are unmeasurable until the shadow accrues
sub-HIGH rows — another reason the flip stays gated on shadow accrual.

## Rollout
1. Operator signs the table (or amends — the Mainstream question above) — Saturday.
2. ~~STEP-0 calibration~~ ✅ done 7/3 eve (above).
3. Shadow build + wire (Sonnet card; ~1 session) → accrue incl. sub-HIGH tiers.
4. Flip decision at the #329 composition checkpoint (CHANGE_PROCESS).
