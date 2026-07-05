# ADR 0020 — P4 Multi-Setup Book architecture (D-4, #430)

**Status:** PROPOSED (2026-07-05, Fable design block D-4) — awaiting operator sign-off (§8).
The pillar: diversify the edge across setups and regimes — one gap-long strategy is one
regime's book. Anchors already decided: Family taxonomy (A = consolidation [HTF +
Anticipation]; B = EP/gap-ups) · **9M = a stock CONDITION, never a tradeable setup** (#418
D-2; `9m_day2` + `flag_continuation` deprecate via #424) · per-setup judges SHARING
components, not one universal judge (operator 6/8) · established setups use the PRIMARY
methodology definition (operator 6/28).

## 1. The book model — a setup is a registry row plus four bindings

`mi_strategies` already carries phase/multiplier/cap (#65/#66) and the promotion machinery.
A SETUP in the book = a registry row bound to:
1. a **detector** (produces candidates + going-in shape telemetry),
2. a **judge profile** (§2),
3. **entry mechanics** (a `spec_builder` into the ONE entry pipeline — the funnel stays single),
4. a **management profile** (mechanical params + ADR 0017 judge coverage).
Book v1 rows: `magna53` (live) · `anticipation_coil` (#353 ladder) · `htf_breakout` (#397
ladder) · `parabolic_short` (§4, shadow) · deprecated rows retained for history, excluded
from surfaces (#424).

## 2. Per-setup judges, shared components (the #332 rail)

ONE judge runtime (the ADR 0011 pattern: assemble → LLM → bounded output → fail-open →
trace), parameterized by a **SetupJudgeProfile**:
```
setup_id · rubric_prompt_ref (a SECTION of catalyst_rubric.md / a setup rubric doc) ·
axis_set (subset of: catalyst, theme [0015], structure [0016], gap-alignment, tape) ·
payload_assemblers (shared library: corpus [0019], character/pivots [0017 §2], precedents
[0018, case-filtered to the SAME setup]) · verdict_enum (per-setup vocabulary if needed;
magna53 keeps tiers) · promotion_gates (per-setup evidence bars)
```
SHARED (never forked): corpus assembly, axis implementations, fail-open/trace/CHANGE_PROCESS
machinery, the label store (0018 §1 — labels carry setup_id via subject_ref). PER-SETUP: the
rubric text and conviction criteria (#332's distinct-rubrics work = writing profiles, not new
runtimes). Consolidation setups (Family A) weight structure/character axes; EP (Family B)
weights catalyst/theme — same components, different profile weights.

## 3. The condition layer — `mi_setup_universe` (formalizing 9M-as-condition)

A thin admission table replacing implicit universe plumbing:
`ticker · admitted_date · condition TEXT CHECK IN ('9m_day','ep_alert','rs_leader',
'sugar_cohort') · expires_date (condition-specific TTL: 9M ~20 trading days) · detail JSONB`.
Producers: the 9M EOD sweep, EP alerts, RS top-N, the sugar cohort job (all exist — they gain
one INSERT). Consumers: Family-A detectors (flag/coil/HTF) scan `universe ∪ admissions`
instead of ad-hoc lists; every downstream candidate carries its origin condition (telemetry:
"do 9M-origin coils outperform RS-origin coils" becomes ONE GROUP BY — the Bonde
model finally measurable). Card-sized; no behavior change to detection thresholds.

## 4. Parabolic short (TI1) — first counter-regime book (SHADOW first)

Detector EXISTS (`parabolic_detector.py`: cap-tiered prior-move + burst checklist, 28 climax
alerts accrued). This ADR specs entry/management/borrow — the missing mechanics:

- **Entry = BACKSIDE CONFIRMATION, never knife-catching the climax** (Stamatoudis): after a
  climax-flagged day, arm a short trigger at the **break of the prior day's low**; cancel if
  price first closes above the climax high (invalidated) or after 3 unarmed days. Entry order:
  stop-limit SHORT at prior-day low, limit offset per the existing stop_limit convention.
- **Stop**: above the climax high (cap-tier-aware buffer: min(3%, 0.5×ATR14)); **max-loss cap
  1R where R sizes at HALF the long book's per-trade risk** (squeeze asymmetry).
- **Management**: cover 1/3 on the first −1R-equivalent flush · stop trails to prior-day-high
  daily · hard time-stop 5 trading days (backside either works fast or doesn't) · NO adds,
  ever · no overnight holds through earnings dates.
- **Borrow mechanics v1**: Alpaca `asset.shortable AND asset.easy_to_borrow` checked at arm
  time and again at trigger; **ETB-only** (HTB names skipped + telemetry row — locate costs
  not modeled v1). Reg-SHO locate rides Alpaca on ETB.
- **Ladder**: SHADOW (arm/trigger/outcome rows to `mi_parabolic_short_shadow`, no orders) →
  N≥30 triggered-shadow cohort + positive expectancy → PAPER (real short mechanics surface
  borrow realities) → live-reduced. Each rung CHANGE_PROCESS + sign-off. Shorts stay
  **excluded from L2 mgmt-judge authority** (0017) until their own review.

## 5. Regime-adaptive book selection (v1 = a signed static matrix)

`mi_strategies.regime_matrix JSONB` — per-setup multiplier by regime state (the existing
regime vocabulary): e.g. `magna53: {trend_up:1.0, choppy:0.6, risk_off:0.3}` ·
`parabolic_short: {trend_up:0.0, choppy:0.7, risk_off:1.0}` · consolidation setups damped in
high-churn regimes. Applied as ONE multiplier in the entry pipeline's existing sizing step
(composes with #65's per-strategy multiplier — same code point, no new mechanism). **Matrix
CONTENTS are operator-signed methodology** (§8-J3); NULL = 1.0 (today's behavior). The
existing regime-halving safeguard stays as the outer floor. Data-driven matrix tuning = P5.

## 6. Build cards
| Card | Scope | Class |
|---|---|---|
| B1 | `mi_setup_universe` + producer INSERTs + Family-A consumer switch + origin-cohort telemetry query | Sonnet card |
| B2 | SetupJudgeProfile plumbing (profile table/dataclass + runtime parameterization; magna53 profile = current behavior byte-identical — regression-pinned) | Sonnet card, Fable review |
| B3 | Parabolic-short shadow: arm/trigger state machine + borrow check + shadow table + digest line | Sonnet card |
| B4 | regime_matrix column + sizing-step application (NULL=1.0 default) + tests | Sonnet card, Fable review (sizing-adjacent, ships dark until J3 signs the matrix) |
| B5 | Anticipation/HTF judge profiles (the #332 rubric writing) — post-M2 graduations | Fable block |
Sequencing: B1 → B3 accrues while B2 lands → M2 graduations (#395/#397) slot their setups
into profiles (B5) → B4 last, dark until signed.

## 7. Interactions
0017: management profiles per setup; shorts excluded from auto-authority. 0018: precedents
filter on setup_id. 0019: corpus shared. #297 (Family-B anticipation rework) consumes the
condition layer. #146/#168/#170/#178/#359: detector-side tasks unchanged, now with a home rail.

## 8. Operator sign-off forks (recs first)
- **J1** Parabolic entry variant: **backside prior-day-low break** (rec, primary-definition
  faithful) vs same-day fade variants (rejected v1: knife-catching).
- **J2** ETB-only v1 (rec) vs HTB-with-locate-modeling (real borrow-cost engineering, later).
- **J3** The regime_matrix contents — pure methodology, yours to set at sign-off (a proposed
  starting matrix ships in the B4 card for you to edit/sign; nothing activates before).
- **J4** Short-book risk basis: **half the long book's per-trade R** (rec) — or a fixed $ cap.
- **J5** `mi_setup_universe` TTLs (9M ~20 trading days rec; others per condition).
