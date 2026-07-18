# ADR 0028 — Setup-class conviction profiles (#332): one rubric, class-conditional salience

**Date**: 2026-07-11
**Status**: **C1 SHIPPED 2026-07-18** (§2/§7 F4 pins operator-signed same day) — **P1-P3 still
DESIGN, awaiting operator sign-off** (Fable weekend block 1; the meta-rubric long pole, D7 of
`meta_rubric_groundwork_2026-06-24.md:273-276`). Rolls out visibility→shadow→authority like
every axis; the authority flip is an operator sitting per ADR 0024's milestone machinery.
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
| `mature_leader` | mcap ≥ $10B OR (Stage-2 AND within 25% of 52w-high AND **ADV_20_dollar ≥ $100M/day, operator-signed 2026-07-18** — F4 resolved below) | structure context ↑↑ (the #330 axis carries) · a5 guidance ↑, a4 beat ↑ · gap-vs-structure (#331) salient · a6 milestone ↓ |
| `episodic_neglect` | $2B ≤ mcap < $10B AND price < 70% of 52w-high AND **upgrades_30d == 0, operator-signed 2026-07-18** (upgrade RECENCY, not analyst-coverage breadth — F4 resolved below) | a6 milestone ↑, a4 beat ↑ (the re-rating surprise) · neglect depth ↑ · momentum penalty STAYS (a neglected name already +50% is late, not early) |
| `unclassified` | anything else / missing fields | **uniform (current) rubric — fail-to-baseline, never penalized** |

Class tag rides the alert row + judge DecisionContext from day one (visibility before authority —
every downstream readout becomes class-splittable immediately, including the axes' own STEP-0s).

**C1 SHIPPED 2026-07-18** (#332, `agents/market_intelligence/setup_class_classifier.py`):
`classify_setup_class` built to this table verbatim, with the two operator-signed pins above.
Reuses `structure_axis_shadow.compute_structure_features`'s `stage2` (a REAL `week52_high` —
from the FMP profile, distinct from that module's own ~13-month `mi_daily_closes` trailing-high
— is threaded separately for the `price ≥/< X% of 52w_high` cuts; the two "highs" are never
conflated). `ADV_20_dollar` is a new ticker-scoped, strictly-prior-to-`alert_date` median-volume
query (`db.get_adv_20_dollar_asof`) — mirrors `get_adv_from_daily_closes`'s formula but scoped
to one ticker (that function is a whole-market batch query; calling it once per EP candidate
would re-scan `mi_daily_closes` for a single-ticker answer). The tag persists on
`mi_ep_alerts.setup_class` (P0 — visibility only) and rides
`ep_grade_judge.assemble_judge_inputs`'s payload — but is **deliberately never rendered into
the judge prompt** in P0, so the judge is structurally incapable of being influenced by it
(stronger than the existing byte-identical-when-absent axis-plumbing pattern: byte-identical
ALWAYS, present or not).

**`upgrades_30d` SOURCE REPAIR (same day, operator-signed).** The ORIGINAL C1 build (this
paragraph, first version) threaded `upgrades_30d` from `ep_detector.py`'s
`get_fmp_analyst_ratings`-based count (with a same-day fix so the catalyst-cache's cached-grade
path returned the real cached value instead of a hardcoded `0`). Hours later,
`docs/analysis/332_analyst_bonus_backtest_2026-07-18.md` found that ENTIRE feed structurally
dead in production since 2026-03-14 (yfinance `Ticker.recommendations` returns an aggregate
grade-count table; the string-matcher can never match an integer count) — under it, EVERY
candidate read `upgrades_30d == 0`, so this class's 3rd AND-clause was VACUOUSLY satisfied by
construction (the cache fix above was itself a no-op: threading a constant 0 changes nothing).
**REPAIRED same day (operator-signed)**: `setup_class_classifier.py` now fetches
`collector.get_recent_upgrade_events` (yfinance `Ticker.upgrades_downgrades` — dated events,
the source the backtest reconstructed against and validated) directly, and counts
POSITIVE-DIRECTION events (`action == "up"`, not the backtest's broader "faithful" grade-set
semantic, which was shown to select analyst-coverage BREADTH rather than upgrade RECENCY) in
the 30 calendar days ending `alert_date` (`count_recent_upgrades`, lookahead-honest). The
catalyst-cache thread-through (`CachedGrade.upgrades_30d` / `_resolve_cached_upgrades_30d`) was
REMOVED — `upgrades_30d` no longer rides `r`/the cache at all; it is fetched independently
inside `compute_setup_class_fields`. Re-verified the repair actually discriminates: a
coverage-heavy mid-cap with real recent upgrades no longer reads `upgrades_30d == 0` (correctly
excluded from `episodic_neglect`); a genuinely-uncovered small/mid-cap still can (see
`tests/test_setup_class_classifier.py`'s discrimination tests). **`_score_ep`'s OWN
analyst-upgrades bonus was separately REMOVED** (not repaired) in the same backtest's wake —
see `docs/setups/magna53_ep.md`'s 2026-07-18 change-log entry; that is an unrelated scoring
change, tracked there, not here.

52 tests total, post-repair (`tests/test_setup_class_classifier.py` 37,
`tests/test_setup_class_db_helpers.py` 12, `tests/test_ep_grade_judge.py` +3). The 3 cached-tick
`upgrades_30d` tests briefly added to `tests/test_405_catalyst_cache_filters.py` during the
original build were removed same-day along with the cache thread-through they tested (that
mechanism no longer exists post-repair).

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

- **C1 — classifier + tag — SHIPPED 2026-07-18** (pure fn + alert-row/DecisionContext wiring;
  `upgrades_30d` source repaired same-day after a backtest found the original feed dead;
  52 tests incl. every boundary cut + unclassified-fail-to-baseline + missing-fields +
  a lookahead-honesty pin + the discrimination re-verification).
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
- **F4 — C1 build-time finding (2026-07-18), RESOLVED same day (operator, Option A):** a prior
  #332 build pass found 2 of the ~12 leaf predicates in §2's table were NOT operationalized —
  no exact threshold in the ADR, no reusable existing repo primitive — despite §2's premise
  that the tag is "computed at detection from fields already on the candidate" (verified false
  for exactly these two; neither was on the candidate row `r`):
  - **`ADV-large`** (`mature_leader`'s 2nd path). Every "ADV" number elsewhere in the repo is a
    MINIMUM tradability floor, not a "large" classification (EP's `MIN_ADV_DOLLAR_VOLUME`=$1M,
    HTF's `_HTF_MIN_ADV_SHARES`=500k shares, 9M's $50M/$30M turnover gates) — reusing any of
    these as "large" would be a category error (floor ≠ ceiling), not a search-before-build
    reuse.
  - **`low coverage (no recent upgrades)`** (`episodic_neglect`'s required 3rd clause — the
    class was unreachable without it). The ADR's own parenthetical conflated two DIFFERENT
    things: coverage BREADTH (analyst count — nothing in the repo measures this) vs upgrade
    RECENCY (`upgrades_30d`, computed but discarded in `ep_detector.py` pre-C1). Which reading
    was meant was part of the ask, not just the threshold.

  **Operator ruling (2026-07-18): Option A** — pin both gaps, ship C1 whole:
  - `ADV-large` = **`ADV_20_dollar ≥ $100M/day`** (20-day median dollar volume).
  - "low coverage" = **upgrade RECENCY**: `upgrades_30d == 0` (no upgrade in the trailing
    window), NOT analyst-coverage breadth.

  Built same day per this ruling — see the "C1 SHIPPED 2026-07-18" note under §2 above for the
  implementation (`setup_class_classifier.py`, 52 tests post source-repair, ADR + `meta_rubric.md`
  updated in the same commit per `CHANGE_PROCESS`).
