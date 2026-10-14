# ADR 0022 — P5 Autonomy Ladder + Allocator-Live · P6 Replay-Everything CI (D-6, #432)

**Status:** ACTIVE — operator-signed 2026-07-05 ('Signed.', all forks resolved per the recommendations with the Gemini 7/5 modifications adopted; full review trail in-doc).
**L4 BUILT 2026-10-14 (#313 / #302) — the gate and the one writer that exists; see §3 "What shipped".** Deploy gate is **[5p/7], exit 21** (the ADR's [5m/7] / exit 17 were taken by ADR 0030's judge-eval gate before this shipped). Of the three §3 jobs only (a) the selection replay has a writer; (b) and (c) are NOT built — their absent files read WARN on every deploy by design (missing never blocks), and what each would need is recorded in §3.
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
  expectancy (min N=30 else prior 0.5× default), pairwise strategy correlation on daily P&L
  — **review 7/5: BOTH inputs are GREENFIELD computations (cross_strategy_allocator is a
  same-day ORB-slot-contest ranker, unrelated; no per-strategy expectancy query or P&L
  correlation exists anywhere) — L3 builds them, it does not extend the shadow allocator**,
  **Kelly-fraction capped at 0.25 per strategy AND a GLOBAL portfolio Kelly ceiling of 0.40
  (Gemini am. 7/5, M2f modification): if the sum of per-strategy proposals exceeds it, ALL
  budgets scale down pro-rata** — four strategies at 0.25 each would otherwise stack to 1.0
  Kelly, ruin-grade under correlation-1 stress; floor 0.25× / ceiling 2.0× per step,
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
| Entry-mechanics sim — **review 7/5: does NOT exist as a recurring job yet** (the W2 study was one-off analysis; this row is a build, honestly flagged like X6) | monthly | current entry ruleset expectancy on the trailing 90d cohort | drop >0.3R |
- **Mechanism**: each job writes `ci_status/<job>.json` — **REVIEW 7/5 eve (second correction;
  the first fix traded one error for another): the regression jobs run IN-CONTAINER and
  `/home/apollo/backups` is NOT mounted into market-agent/execution (compose mounts only
  `logs`). L4's explicit prerequisite: add a `/home/apollo/backups/ci_status:/app/ci_status`
  bind mount to the market-agent service (one compose line, lands with the L4 deploy) so
  in-container writers and the on-host deploy.sh gate see the same files** `{status:green|red, asof,
  detail}` (repo-external path on the host, like the watchdog state). New deploy gate
  **[5m/7]**: red status + age <7d ⇒ deploy BLOCKED (exit 17) unless
  `CI_OVERRIDE="<reason>"` env is set (logged + audit row — the escape is loud, for
  hotfixes). Stale (>7d) status = WARN not block (a dead CI job must not freeze deploys;
  its own freshness is watchdog-monitored).
- This makes "a methodology change that degrades replayed expectancy fails before deploy"
  literal — the trading equivalent of the pre-push test gate.

**What shipped (L4, 2026-10-14, #313) — derived from the code, not restated from the table:**
- **Writer module** `agents/market_intelligence/ci_status.py`: `write_status(job, green|red,
  detail)` → `ci_status/<job>.json` `{job, status, asof (ET, offset-aware), detail}`, atomic,
  never raises (a failed write leaves the OLD file to age into the gate's WARN — an error in the
  writer is not a regression). In-container the dir is `/app/ci_status` (WORKDIR `/app`); the
  compose bind mount `/home/apollo/backups/ci_status:/app/ci_status` is on **market-agent only**
  — the only writer runs in `weekly_system_review` (INTELLIGENCE-owned → apollo-market).
- **(a) Selection replay — LIVE.** `replay_regression.run_replay_regression(persist=True)`
  (the Sunday review) writes `selection_replay.json` on every run, n=0 included (the file
  existing is the liveness proof). M3f exactly: red iff `n ≥ 50` and
  `CALIBRATION_ENVELOPE.expectancy_r (+0.95R) − live expectancy > 0.3R`; below 50 the detail
  says "threshold not armed". The verdict uses the POOLED live fingerprint (the number M3f was
  signed against); the #662 rule-era clause rides in `detail` for the reader.
- **(b) Judge frozen-cohort eval — NOT BUILT.** ADR 0018's X6 (A/B regrade over the
  operator-labelled cohort) was never built. The nearest existing tool, ADR 0030's robustness
  eval (`scripts/evals/run_judge_robustness_eval.py`), is a $3.49 **operator-triggered** run on
  the synthetic adversarial corpus — not the labelled cohort, not scheduled — so any `asof` it
  wrote would be stale (>7d) on nearly every deploy, a permanent WARN that means nothing; and
  `[5m/7]` already BLOCKS a deploy whose grade surface changed without a passing eval, which is
  strictly stronger than a status file. Would need: the X6 harness over
  `mi_operator_labels`, a scheduled trigger that refreshes within 7 days (a paid run per month
  is an operator cost decision), and a baseline definition for "correctness".
- **(c) Entry-mechanics sim — NOT BUILT** (the 7/5 review already flagged it as a build).
  `scripts/ep_replay.py` is the fidelity-validated replay harness but it reads hand-pulled TSV
  captures (`scripts/ep_replay_data/_pull*.sql`), takes an explicit ruleset, and prints per-label
  mean R — there is no trailing-90d cohort definition, no "previous run" baseline, no in-container
  data path and no schedule. Each of those is a judgement call, so nothing was invented.
- **Gate** `scripts/preflight_ci_status_gate.py` (host-side, stdlib, the [5h/7] pattern), wired
  as **[5p/7] BEFORE the image build** (`[1/5] pull` → gate → `[2/5] build`): a block must stop
  the deploy from STARTING, whereas every other [5x/7] verifies code already up. Fresh red
  (≤7d) ⇒ `exit 21` for `market-agent` / `both` / `execution` only (M4f); `orchestrator` is
  never blocked; stale (>7d) / missing / unreadable ⇒ WARN. The three expected jobs are named so
  a missing writer prints rather than vanishes. `mkdir -p` of the host dir runs in the same
  block as `apollo` (uid 1000 = the container user) so docker never creates it root-owned.
- **Override** `CI_OVERRIDE="<reason>" bash scripts/deploy.sh <scope>` — banner printed, a line
  appended to `logs/ci_override.log`, and an `mi_audit_log` row `ci_override_deploy` relayed
  through the running container via `scripts/log_judge_envelope_change.py` (payload-generic, the
  [5m/7] relay); an empty reason is not an override. Tests: `tests/test_ci_status.py`,
  `tests/test_preflight_ci_status_gate.py` (the deploy.sh block is extracted and RUN dry),
  `tests/test_replay_regression.py`.

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
- **M2f** Kelly cap 0.25/strategy + **global 0.40 portfolio ceiling, pro-rata scale-down**
  (Gemini-modified 7/5, adopted) + step bands 0.25×/2.0×.
- **M3f** CI red thresholds (0.3R / 5pts, rec) + the 7d-stale WARN rule.
- **M4f** Gate [5m/7] scope: block `market-agent`+`execution` deploys only (rec) vs all.
