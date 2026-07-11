# ADR 0028 — Setup-class conviction profiles (#332): one rubric, class-conditional salience

**Date**: 2026-07-11
**Status**: **DESIGN — awaiting operator sign-off** (Fable weekend block 1; the meta-rubric long
pole, D7 of `meta_rubric_groundwork_2026-06-24.md:273-276`). Rolls out visibility→shadow→authority
like every axis; the authority flip is an operator sitting per ADR 0024's milestone machinery.
**Authors**: Fable (operator-triggered weekend block, 2026-07-11)
**Relates**: ADR 0024 (composition architecture — this composes INSIDE it), ADR 0015/0016 (the
axis rollout discipline this copies), #357 memo (sugar-baby credit is class-relevant),
`user_pradeep_revenue_over_eps` (the salience-differs-by-class seed fact).

## 1. The D7 fork, resolved: NOT three rubrics — one rubric, class-conditional profiles

**Decision: one rubric + per-class SALIENCE PROFILES** (weight vectors + floor-feature switches),
never three parallel rubrics. Grounds:
1. **Corpus arithmetic.** Three rubrics need three calibration corpora. The graded, trustworthy
   corpus is ~hundreds of alerts TOTAL; per-class slices go thin fast — three independently
   calibrated rubrics is an overfit machine (the exact ship→revert→restore scar CHANGE_PROCESS
   exists to prevent).
2. **The axes are universal; salience isn't.** Revenue growth, guidance, margin — every class
   *has* these; what differs is which evidence should carry the composite (Pradeep: revenue
   acceleration IS the story, EPS noise; Qullamaggie mature-leader: structure quality carries,
   catalyst is confirmation; episodic-neglect: the surprise/milestone + the neglect depth carry).
3. **ADR 0024 already built the seam.** Class-conditioning slots into existing machinery
   (`AXIS_WEIGHT` lookup + `_score_ep` feature switches) without touching the composition
   contract: `compose_final_tier`, NET_CAP=1, and the TIER_LATTICE are **class-blind and
   unchanged**. One bar (`composite_min=22`) stays GLOBAL — profiles redistribute weight, they
   do not move the bar (three drifting bars = uncalibratable).

## 2. The classifier (P0 — deterministic, visibility-first)

`classify_setup_class(candidate) -> 'pradeep_explosive' | 'mature_leader' | 'episodic_neglect'
| 'unclassified'` — pure function, computed at detection from fields already on the candidate:

| class | rule (testable defaults — boundaries re-derived in P1) | salience hypotheses (P1 tests these DIRECTIONS) |
|---|---|---|
| `pradeep_explosive` | mcap < $2B AND (RVOL ≥ 3× OR 9M-print same-day OR sugar-baby cohort) | a1 revenue ↑↑, theme axis ↑, float/neglect ↑ · a2 EPS ↓ · a5 guidance ↓ (small caps rarely guide) · **prior-runup penalty OFF** (recurring momentum = confirmation here — `_score_ep`'s −25/−15 momentum penalty is a mature-market prior misapplied to this class) |
| `mature_leader` | mcap ≥ $10B OR (Stage-2 AND within 25% of 52w-high AND ADV-large) | structure context ↑↑ (the #330 axis carries) · a5 guidance ↑, a4 beat ↑ · gap-vs-structure (#331) salient · a6 milestone ↓ |
| `episodic_neglect` | $2B ≤ mcap < $10B AND price < 70% of 52w-high AND low coverage (no recent upgrades) | a6 milestone ↑, a4 beat ↑ (the re-rating surprise) · neglect depth ↑ · momentum penalty STAYS (a neglected name already +50% is late, not early) |
| `unclassified` | anything else / missing fields | **uniform (current) rubric — fail-to-baseline, never penalized** |

Class tag rides the alert row + judge DecisionContext from day one (visibility before authority —
every downstream readout becomes class-splittable immediately, including the axes' own STEP-0s).

**Field provenance (lookahead honesty):** the tag is computed AT DETECTION from point-in-time
fields and **persisted on the alert row** — the P1 calibration replay classifies historical rows
from their *stored* fields, never re-fetched current values (FMP mcap/profile today ≠ mcap at
alert — the #268 replay-caveat class). Historical rows missing stored fields classify
`unclassified` in P1 rather than being backfilled from current data; the N-gates absorb the loss.

## 3. P1 — calibration replay (weights are OUTPUTS, not opinions)

`scripts/probes/_332_class_calibration.py` (read-only): classify the historical graded corpus
(post-3/16 `mi_ep_alerts` + rubric axis scores from `mi_ep_catalyst_metrics`/re-derivation + fwd
returns) → per class: (i) axis-score↔outcome correlation table (does a1 predict in
`pradeep_explosive` but a5 in `mature_leader`? — the salience hypotheses above are the priors this
confirms or kills); (ii) the floor's momentum-penalty effect per class (does the −25/−15 branch
cost winners in `pradeep_explosive`?); (iii) proposed weight profile per class, **N-gated: any
class with corpus N<20 ships NO profile** (stays uniform) until it accrues.
Boundary sensitivity: re-run at mcap ±25% / RVOL 2.5-4× / neglect 60-75% — classifier boundaries
land on plateaus (the #170/#290 anti-knife-edge discipline).

## 4. P2 — shadow profiles → P3 — authority

- **P2:** compute the class-conditioned composite ALONGSIDE live (uniform stays authoritative);
  log `class_profile_shadow` rows: (class, uniform_composite, profile_composite, tier-if-flipped).
  Exactly the theme_axis_shadow rollout shape. Runs ≥2 weeks or ≥30 shadowed alerts.
- **P3:** operator sitting (ADR 0024 milestone style) reviews the shadow delta table: tier flips
  by class, would-be winners gained / losers admitted. Authority = the profile lookup goes live
  per-class (a class can flip alone). CHANGE_PROCESS entry + SSoT (magna53_ep.md scoring section
  + this ADR's status) same commit. Instant-revert runtime toggle (`get_runtime_toggle` shape,
  fail-open to UNIFORM — the safe direction here is baseline, not off).

## 5. What is explicitly out of scope

- **Axis-credit conditioning by class** (e.g. theme credit worth more for `pradeep_explosive`):
  deferred until the axes themselves hold authority (post-M3) — the composition layer stays
  class-blind so NET_CAP semantics stay auditable. Revisit as its own fork with shadow evidence.
- Any threshold move on `composite_min` or `ep_threshold` — not this ADR.
- 9M/HTF/consolidation lanes — this ADR conditions the **EP grade path** only; Family-A setups
  have their own signed models (ADR 0013/0026).

## 6. Cards

- **C1 — classifier + tag** (pure fn + alert-row/DecisionContext wiring; 8 tests incl.
  boundary cases + unclassified-fail-to-baseline + missing-fields).
- **C2 — P1 calibration probe** (the correlation/weight-derivation replay; verdict table per
  class + N-gates + boundary sensitivity).
- **C3 — P2 shadow profiles** (profile lookup in `composite_with_scaling(profile=...)` default
  uniform + `_score_ep` momentum-penalty switch + shadow logging; 7 tests incl.
  uniform-byte-identical-when-no-profile).
- **C4 — the P3 sitting doc** (auto-assembled shadow delta table for the operator).

**Sequencing:** C1 ships now (visibility, no behavior change) → C2 runs → profiles exist → C3
shadows → C4 sitting. Each stage is independently useful (C1's class tag alone upgrades every
other program's readouts — #357 STEP-0, the axes' calibrations, the weekly review).

## 7. Operator forks

- **F1 (the D7 core):** rec = one-rubric-with-profiles as designed. Alternative (three rubrics)
  rejected on corpus arithmetic — presented for completeness.
- **F2 — class taxonomy:** rec = the 3 classes + unclassified as defined. Alternative: add a
  4th `parabolic_short` class — NOT recommended now (different trade direction, own detector,
  own program).
- **F3 — the momentum-penalty switch for `pradeep_explosive`:** rec = test in P1, flip in P2
  shadow only if the replay shows the penalty costs winners (it's the single highest-conviction
  salience hypothesis — the class exists because repeat-momentum names behave differently).
