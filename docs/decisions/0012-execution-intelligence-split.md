# ADR 0012 — Execution / Intelligence service split

**Status:** BUILT (combined byte-identical, deployed) — CUTOVER GATED. W1 (in-process
facade) + W2 (role-aware single process, HTTP transport, compose topology, seam fixes)
are code-complete and live in `combined` mode. The actual two-service cutover and the
Monday live-ORB `EXECUTION_MODE=http` flip are operator-gated (see
`docs/ops/execution_split_cutover.md`). **Date:** 2026-06-13.
**Driver:** operator directive 2026-06-09 — split execution out of the market agent before
real money (#256), targeted ~6/22. **Plan:** `~/.claude/plans/execution-intelligence-split-256.md`.

---

## Context — one process, one blast radius

The market agent is a single process where a theme-engine prompt tweak and the stop-loss
replace path deploy, restart, and fail together. Every outage class we've logged
(UnboundLocalError 5/20, `ALPACA_LIVE_API_KEY` 5/13, import-shadow) restarted **trade
execution** because **detection** code changed. With real money, two properties must hold:

1. **Blast-radius isolation** — an intelligence deploy must not restart trade execution.
2. **Credential isolation** — Alpaca keys must live in exactly one service, so an
   intelligence-side bug/compromise cannot place orders except through a typed API.

The dependency arrow already points one way: `broker/`'s upward deps are infra-only
(constants/db/collector/briefing); broker never imports the detection engines. So the
boundary is natural — the work is making it physical without forking the codebase.

## Decision

**One image, two compose services, role chosen by `SERVICE_ROLE` env** — not a separate
`main.py`. `agents/market_intelligence/agent:app` is role-aware; the same image runs as
`apollo-execution` (`SERVICE_ROLE=execution`, holds the creds) or as the intelligence role
(`market-agent` keeps its name, gains `SERVICE_ROLE=intelligence` + `EXECUTION_MODE=http`,
blanks its `ALPACA_*`). Pre-cutover both default to `combined`/`inprocess` = **byte-identical
to the single process.**

Key mechanisms (all shipped, dormant at the default):

- **Facade seam** (`execution_client.py`, W1): intelligence reaches trade execution ONLY
  through ~15 typed async functions; direct `broker.*` imports are banned outside the facade
  by deploy gate `[5j]` (`check_execution_boundary.py`). The 44-site migration happened once.
- **HTTP transport** (W2 5a): each cross-boundary fn is `_<name>_inprocess` (broker body) +
  a dispatcher. `EXECUTION_MODE=http` → POST `/exec/{name}` (X-Apollo-Secret, the same auth
  as orchestrator→market) to apollo-execution; else in-process. Routes register only when
  `runs_execution_jobs()`; handlers call the `_inprocess` bodies directly (no http→route→http
  loop) and the route module imports only the facade (stays `[5j]`-clean). Route↔client parity
  is asserted at boot.
- **Scheduler partition** (W2): one `EXECUTION_OWNED_JOB_IDS` set (27) + a declared
  `INTELLIGENCE_OWNED_JOB_IDS` manifest (42). `_apply_role_partition` keeps the owned set
  per role; `combined` is a no-op. Three fail-loud guards: a de-registered owned id, a
  leaked execution id surviving in intelligence, and — the class an audit caught — a
  **registered-but-unclassified** job (the omission guard, `registered ⊆ EXEC ∪ INTEL`,
  split-roles-only so it can't break combined boot).
- **Boot coherence** (`assert_service_role_coherent`): a misread role NEVER falls back to
  `combined` (= double execution); `http`+`combined` and `http`+intelligence+no URL fail loud.
- **Creds + streams in execution only**: the trade/bar streams and the credential bootstrap
  are gated on `runs_execution_jobs()`. The trade stream runs in exactly one service — the
  #1 cutover risk (double fill-processing) is structurally prevented by the partition + the
  cutover ordering (stop combined → up execution → recreate intelligence).
- **Fail-loud transport**: a wire-hop failure raises `ExecutionUnreachable`, never collapsing
  into a broker empty/`None` default — "couldn't reach execution" must stay distinct from
  "execution answered: flat" (`no_silent_trading_failures` / `ground_truth_verification`).

## What is NOT routed (deliberate)

- `get_data_feed_name` — pure config (`ALPACA_DATA_FEED`); reimplemented as a direct env
  read, stays local in both roles.
- `verify_accounts` — execution-only; gated off in intelligence.
- `handle_confirm_callback` — takes a Telegram object (not JSON-serializable); deferred,
  stays a local shim until confirm-callback routing is designed (plan risk 2).
- The **read serialization** the plan budgeted for turned out already done: all reads return
  JSON-safe dicts (`_order_to_dict`/`_position_to_dict` stringify enums + isoformat datetimes).

## Alternatives considered

- **Separate `main.py` per service** — rejected: duplicate boot-logic drift. The role-aware
  single image keeps one boot path; blast-radius isolation still holds via independent
  per-service restart.
- **Redis queue transport** instead of HTTP — rejected: more moving parts, no need for async
  fan-out; HTTP reuses the existing orchestrator→market pattern.
- **Per-`add_job` role tag** across 64 sites instead of the central owned-set — deferred: the
  central set is greppable/testable and the omission guard closes its one failure class; revisit
  only if the partition keeps drifting post-cutover.

## Consequences

- Intelligence iterates daily without touching execution; execution is small and rarely
  deployed. `deploy.sh` gains an `execution` scope (trade preflights run against the execution
  container); the scope-drift guard treats `apollo-execution` as covering `market_intelligence/`.
- Rollback is instant and exact: collapse to `SERVICE_ROLE=combined` + `EXECUTION_MODE=inprocess`
  and restart = byte-identical prior behavior.
- The markets-closed two-service soak validates boot/reads/reconcile only; the handoff/command
  path (`trigger_orb_entry`, submits, partials) is exercised only during market hours — hence
  the Monday live-ORB flip is a separate operator gate.
- Follow-ons: W3 staging pipeline (nightly prod-restore-seeded), W4 hardening (DR runbook for
  two services, per-service uptime checks, `#258` db.py split along the same boundary).

## Validation as-built

- `combined` deployed + verified-live across the W2 commits: role log, "all 69 jobs kept",
  paper equity intact, streams up.
- Real partition dry-booted per role (`scripts/_w2_role_dryboot.py`): execution 27 /
  intelligence 42, neither guard raises.
- Tests: `test_service_role`, `test_job_partition`, `test_trigger_orb_entry_seam`,
  `test_execution_transport` (transport routing, `ExecutionUnreachable` fail-loud, parity,
  coherence). 734-test suite green; deploy gates `[5j]` + datetime/import-shadow/model-registry pass.
