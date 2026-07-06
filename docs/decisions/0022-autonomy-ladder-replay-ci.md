# ADR 0022 — P5 Autonomy Ladder + Allocator-Live · P6 Replay-Everything CI (D-6, #432)

**Status:** PROPOSED (2026-07-05, Fable design block D-6) — awaiting operator sign-off (§7).
Exists and stays: `mi_strategies.phase` ladder semantics (#66) · the weekly promotion checker
(eligibility + blocking_reasons in the Sunday review) · `cross_strategy_allocator.py` (shadow,
#415 telemetry accruing to the 8/4 registry read) · `replay_regression.py` (weekly surface,
no verdict) · kill/scale bands (#268b, live-money layer). This ADR formalizes the gates INTO
the registry, adds the demotion direction, and specs allocator-live + replay-CI.

## 1. The autonomy ladder — gates become registry DATA, not code constants

**REVIEW 7/5 — premise correction: promotion thresholds are ALREADY per-strategy data**
(`promotion_thresholds` dicts in the strategies seed, db.py — e.g. parabolic_short carries
min_climax_alerts:20). L1 therefore SHRINKS to: verify the thresholds live ON the DB row
(updatable at runtime, not just the code-side seed) + the checker reads the row; the
genuinely NEW pieces are demotion + history. Columns (additive):
`promotion_gates JSONB` — (largely exists as promotion_thresholds) per-rung criteria, e.g.
`{"paper":{"min_shadow_n":30,"min_median_r":0.0},"live_proposed":{"min_paper_n":30,
"min_expectancy_r":0.2,"max_dd_r":-8,"min_weeks":4},"live_reduced":{"min_label_precision":0.8,
"min_labels":20},"live_full":{"min_live_reduced_weeks":4,"min_capture_pct":null}}`
`demotion_triggers JSONB` — `{"consec_losses":6,"trailing20_expectancy_r":-0.3,
"dd_from_peak_r":-10,"harmful_auto_action":1}`
`phase_history JSONB` — append-only `[{"from","to","at","reason","signed_by"}]`.

- **Promotion stays HUMAN**: the checker (now reading gates from the registry instead of
  constants) reports ✓-eligible; the operator signs; the phase flip is a CHANGE_PROCESS event
  appended to `phase_history`. No auto-promotion, ever.
- **DEMOTION IS AUTOMATIC** (the new direction): a nightly `ladder_watchdog` step (rides the
  post-EOD audit job) evaluates `demotion_triggers` per live/paper strategy against DB ground
  truth; a breach → phase steps DOWN one rung immediately + 🔴 Telegram + audit row + a
  mandatory operator review before re-promotion. Demotion is risk-REDUCING — it needs no
  sign-off to fire, only to reverse (asymmetry principle, same as 0017's ladder).
- Deprecated strategies (#424): `phase='deprecated'` terminal — excluded from checker,
  watchdog, and surfaces.

## 2. Allocator to live — PROPOSE-then-sign, never self-directed

The shadow allocator matures into the capital brain in two steps:
- **A1 (post-8/4 registry read)**: `allocation_proposals` — monthly (1st trading day) the
  allocator emits a per-strategy risk-budget proposal: inputs = accrued per-strategy
  expectancy (min N=30 else prior 0.5× default), pairwise strategy correlation on daily P&L,
  **Kelly-fraction capped at 0.25**, floor 0.25× / ceiling 2.0× of current budget per step,
  regime_matrix (0020 §5) as an overlay not an input. Rendered as a digest section with the
  full math trace. **Operator signs → budgets bind** (they become the per-strategy
  `position_size_multiplier` + cap set — the existing plumbing, #65).
- **A2 (H3, aspirational per the pillar)**: auto-apply within hard bands (±20% of signed
  budgets, never crossing safeguards) — its own future ADR + sign-off; NOT in scope now
  beyond stating the boundary.
Invariants: allocator NEVER touches safeguards/breakers (outer floor), never sizes a
strategy above its ladder rung's envelope, and a demotion (§1) zeroes the pending proposal
for that strategy.

## 3. Replay-everything CI (P6) — regressions block DEPLOYS, not trades

Three scheduled regression jobs, one gating mechanism:
| Job | Cadence | Baseline | Red condition |
|---|---|---|---|
| Selection replay (#268b/#302 exists) | weekly (exists) | Phase-B calibration n=399 | replayed expectancy drop >0.3R vs baseline at N≥50 |
| Judge frozen-cohort eval (X6 harness, 0018) | on grade-path changes + monthly | the labeled cohort's grade-correctness | correctness drop >5pts |
| Entry-mechanics sim (the W2 rails) | monthly | current entry ruleset expectancy on the trailing 90d cohort | drop >0.3R |
- **Mechanism**: each job writes `/home/apollo/backups/ci_status/<job>.json` (REVIEW 7/5: the earlier `scripts/ci_status/` path was WRONG — scripts/ is inside the repo; the backups dir is the established host-state home, like the watchdog state) `{status:green|red, asof,
  detail}` (repo-external path on the host, like the watchdog state). New deploy gate
  **[5m/7]**: red status + age <7d ⇒ deploy BLOCKED (exit 17) unless
  `CI_OVERRIDE="<reason>"` env is set (logged + audit row — the escape is loud, for
  hotfixes). Stale (>7d) status = WARN not block (a dead CI job must not freeze deploys;
  its own freshness is watchdog-monitored).
- This makes "a methodology change that degrades replayed expectancy fails before deploy"
  literal — the trading equivalent of the pre-push test gate.

## 4. Build cards
| Card | Scope | Class |
|---|---|---|
| L1 | Registry columns + checker reads gates-from-registry (behavior-identical regression pin) + phase_history | Sonnet card |
| L2 | ladder_watchdog demotion step (nightly, DB-sourced) + Telegram/audit + tests (synthetic breach fixtures) | Sonnet card, Fable review (touches phase — risk-reducing only) |
| L3 | allocation_proposals job + math-trace digest section (dark until 8/4 read + sign-off) | Sonnet card |
| L4 | ci_status writers on the 3 jobs + deploy gate [5m/7] + override path + tests | Sonnet card |
Sequencing: L1 → L2 · L3 after the #415 8/4 read · L4 after X6 (0018) exists.

## 5. Interactions
0017's L-rungs and this ladder are the SAME mechanism at different scopes (position-action
authority vs strategy-capital authority) — both use evidence gates + human promotion +
automatic demotion. 0020's regime_matrix overlays allocation. Kill/scale bands stay the
live-money outer layer (this ladder never overrides a band verdict).

## 6. Test plan
L1: gates-from-registry produces byte-identical checker output on current data. L2: synthetic
breach → demotion + alert + history row; no-breach → zero writes. L3: golden math trace
(fixed inputs → exact proposal). L4: red file blocks a dry-run deploy; stale file warns;
override logs.

## 7. Operator sign-off forks (recs first)
- **M1f** Demotion triggers defaults: `{6 consec losses, trailing20 exp < −0.3R, DD −10R,
  1 harmful auto-action}` (rec) — or your numbers.
- **M2f** Kelly cap 0.25 + step bands 0.25×/2.0× (rec).
- **M3f** CI red thresholds (0.3R / 5pts, rec) + the 7d-stale WARN rule.
- **M4f** Gate [5m/7] scope: block `market-agent`+`execution` deploys only (rec) vs all.
