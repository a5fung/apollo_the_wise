# ADR 0008 — Trade-state: Alpaca is the source of truth; the DB is a read-through mirror

**Status:** Accepted (design) 2026-06-04 — build sequenced, cutover prerequisite. Tasks: #151 (leaf partial-exit fix, first) + #184 (mirror, this ADR).

## Context

Every trade-state incident in May–June 2026 shares one root: **the DB diverged from the
broker and Apollo acted on the DB's (wrong) view.**

- **2026-05-27 mass-close cascade** — `sync_positions` acted on a bad/empty Alpaca read and
  mass-closed 3 trades in the DB.
- **2026-06-04 FPS false-naked** — the partial-exit nulled `mi_live_trades.stop_order_id`
  when its rollback failed, *without confirming the broker had no stop*. The broker actually
  had **two** stops (a 163-share original stuck in `pending_replace` + a 109-share
  replacement). The position was **over**-covered; the DB reported **naked**. The original
  stop `a41e7c6a` had never been written to `mi_live_orders` at all — the mirror was
  incomplete from the start.

Operator directive (2026-06-04): *"Our database must work and have the source of truth at
all times."* You cannot put real money behind a DB that can lie about whether a position is
protected. This is a **hard live-cutover blocker**.

## Decision

**Alpaca is the single source of truth for trade state. The DB is a read-through MIRROR
that defers to the broker on every divergence.** Two enforcement rules:

1. **Write-side — never infer.** No code may null/mutate trade-state (`stop_order_id`,
   naked-flag, `status=closed`) from *inference* or a *failed operation* — only from a
   **confirmed broker read/event**. (Generalizes the #128/#136 "check the broker before
   alarming" discipline to every trade-state write.)
2. **Reconcile-side — broker wins.** A reconciler reads the broker (positions + ALL orders +
   stop coverage) and brings the DB into agreement; broker wins every divergence.

## The 5/27 guardrail (decisive constraint)

A naive "broker-wins, force the DB to match" reconciler is **literally the shape that caused
the 5/27 mass-close** (it acted on a degraded/empty broker read). Therefore the
reconcile-side must **never act on a non-confirmed/empty/partial/stale broker read** — the
#137 "refuse mass-close on empty read" guard, generalized to all auto-correction.

## Smallest-viable build order (do NOT reorder)

1. **Write-side invariant** — only a confirmed broker read may null `stop_order_id` / set
   naked. **This alone kills the false-naked class at the source**, is bounded, and is
   enforceable statically like the column-write-authority preflight (`audit_column_writes.py`).
   *Build this first.*
2. **Read-only coverage-drift detector** — alert when DB-vs-broker disagree on coverage.
   Observe-only; no mutation.
3. **Guarded auto-correction** — only after (1)+(2) bake: bring the DB to match the broker,
   gated by the generalized degraded-read guard. Never the first increment.

Plus: **ingest untracked broker orders** (the `a41e7c6a` gap) so the mirror is complete
(increment 2(b), not yet built), and **`/syncnow`** — the on-demand reconcile trigger.
~~currently broken ("Unknown command" despite full wiring; likely input-artifact / runtime
cmd mismatch)~~ **STALE — fixed 2026-06-04.** The "Unknown command" was a zero-width-char
input artifact (`_normalize_slash_cmd`, commit `6fe4114`), not a wiring gap; `/syncnow`
wiring was already complete on main. Confirmed RESOLVED 2026-06-24 (`#184` PLAN note,
"PART (c)"): routing-test coverage added (`test_operator_commands_partialnow_syncnow.py`
+ frozen in `test_execute_task_routing.py`). This paragraph was left stale in the ADR text
itself until this update (2026-07-05) — don't cite the struck-through line as current.

## Scope boundary — #151 is NOT part of this

#151 (the partial-exit fix: verify the old stop left `pending_replace`/cancelled before
selling + `qty_available` poll + coverage-invariant) is a **leaf fix, shipped first and
independently.** The "DB-must-have-SoT" principle must **not** pull #151 into this
architectural rewrite (the recurring scope-creep trap). #151 fixes the partial-exit; #184
(this ADR) makes the DB a faithful mirror. Both are validated on
`integration_test_partial_exit.py` (the harness must reproduce stuck-`pending_replace` +
untracked-order + false-naked, or the bug isn't understood). Both are cutover prerequisites.

## Build status

- **Increment 1 — write-side regression FENCE: SHIPPED 2026-06-06.**
  `scripts/audit_trade_state_demotions.py` (+ `tests/test_trade_state_demotions.py`,
  5 green incl. the pre-/post-#151 incident fixtures). Static gate: flags any
  trade-state demotion (`stop_order_id`→NULL / `status`→`'closed'`, via SQL SET or
  `set_stop_order_id(None)`) lexically inside an `except` block that lacks a
  `# broker-confirmed:` reviewed-escape tag. **Honest scope:** a regression fence +
  residual surfacer, NOT the "kills the class at source" claim — "broker-confirmed"
  is a control-flow property a comment can't verify (that's increment 3's runtime
  chokepoint). Fences the 6/4 false-naked class; does NOT cover 5/27 mass-close
  (runtime empty-read, #137-guarded).
  - First run found **5 except-enclosed demotions**: `order_manager.py:1288`
    (execute_partial_exit) is the #151 verify-stop-live fix → **broker-confirmed,
    tagged** (the proof case). The other **3 (L584, L905, L1575) are genuine
    residuals** of the banned pattern → **#225** (broker-read-before-demote, paper-
    integration-gated; do NOT refactor live error paths offline).
  - **Blocking deploy-wire deferred** until #225 clears the 3 residuals (wiring a
    failing gate would block all deploys). Until then the gate runs informationally.
- **Increment 2(a) — read-only coverage-drift detector: BUILT 2026-07-05.**
  `agents/market_intelligence/broker/coverage_drift.py::detect_coverage_drift(account_mode)`.
  Three drift classes, observe-only (audit rows + Telegram; zero mutation):
    - **D1 untracked broker position** (no open DB row for that ticker+mode) — HIGH,
      Telegram. This is the `a41e7c6a` mirror-gap class.
    - **D2 untracked open order** (order id not referenced by any open DB row's
      entry/stop) — HIGH + Telegram when `client_order_id` carries our
      `apollo_{mode}_` prefix (system-created, lost track of); INFO/audit-only
      otherwise (may be the operator trading manually in the same account).
    - **D3 DB-open-without-broker-presence** (open DB row with no broker position
      and no live entry order) — INFO/audit-only; `sync_positions` /
      `order_status_reconcile` already own closing this direction.
  Wired into the existing 15-min `_order_status_reconcile_job` (scheduler.py) right
  after `reconcile_all_modes` — consolidated onto that cadence rather than a new job,
  guarded per-mode so a coverage-drift exception can never break the order-status
  reconcile. Telegram dedup is DB-sourced (`mi_audit_log` `coverage_drift_alerted`
  rows, 24h window) — never module-level state. Degraded-broker-read guard (#137
  class): `alpaca_client.get_all_positions` / `get_open_orders` called with
  `raise_on_error=True` so a genuine read failure raises (logged +
  `coverage_drift_check_degraded`) instead of silently degrading to `[]` and being
  misread as "everything's untracked". Tests: `tests/test_coverage_drift.py`.
  **Increment 2(b) (ingest untracked broker orders into the mirror) and Increment 3
  (guarded auto-correction + runtime demote-helper)** — not started; increment 2(b)
  is the natural next PLAN item (#184 sibling), increment 3 stays gated on 2(a)/2(b)
  baking per the build-order above.

## Rule-1 corollary (2026-08-10) — an UNREADABLE broker is not a confirmed read

The #548 resting-mode breakeven failure path nulled `stop_order_id` whenever the reduced
stop was "not confirmed live" after a failed replace — folding two different worlds into
one write: a read that RETURNED a terminal status (confirmed dead — demotion legitimate)
and a read that FAILED (raised / returned None / never left `pending_*`) — nothing
confirmed. The increment-1 fence caught it at deploy `[5l/7]`; split in
`order_manager.py::execute_partial_exit` (breakeven-failure branch). Three rules worth
citing at every verify-read site:

1. **`alpaca_client.get_order` swallows errors and returns `None`** — so "status not in
   the live set" is NOT broker evidence of death. A `None` read is a FAILED read; only an
   actual returned status in the dead set (or `filled`) confirms. Any site that computes
   `_x_live = status in LIVE_SET` and demotes on `not _x_live` silently converts a read
   failure into a "confirmed" demotion.
2. **Bounded-retry the read before deciding** (Step-1b-sized budget) — transient failures
   and settling `pending_replace` usually resolve into a confirmed live/dead, turning an
   unknowable into a legitimate rule-1 write.
3. **Still unverifiable → KEEP the pointer (last confirmed broker truth), do NOT demote,
   alert, and let broker-truth machinery own it** — in-process `_ensure_stop_coverage`
   (discovers stops via `get_open_orders raise_on_error=True`, never via the DB pointer)
   plus the reconcile/coverage-drift net. Nulling on an unreadable broker adds NO
   protection — placing a stop needs the same broker the read couldn't reach; it only
   makes the DB assert something unconfirmed, which is rule 1's exact ban and the 6/04
   FPS incident's exact shape. The counter-risk (a stale pointer to a genuinely dead
   stop) is bounded precisely because no protective mechanism trusts the pointer — all
   act on broker reads.

Known residual of trap (1), found 2026-08-10 and deliberately NOT touched (tagged site,
gate-green; #225's "don't refactor live error paths offline"): the partial-exit
replacement-failure `old_stop_live` check (the `reason="partial_naked"` demotion) counts
a `None` read as "not live" before its tagged null — its tag over-claims for the
failed-read shape. Behavioral pin for the corollary:
`tests/test_resting_mode_breakeven_548.py` (Case A / Case B tests — mutation-proven,
including that a tag elsewhere in the same except block would launder a re-added
unconfirmed null past the fence; only the behavioral test catches that).

## Consequences

- A false-naked becomes structurally impossible: broker says covered → DB says covered.
- No real money goes live until the DB provably cannot disagree with the broker about
  protection (this ADR's increment 1 + #151, harness-gated).
- Subsumes the #123 trade-state derive-close follow-up and #179 (write-side root).
