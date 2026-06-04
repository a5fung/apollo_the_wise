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

Plus: **ingest untracked broker orders** (the `a41e7c6a` gap) so the mirror is complete, and
**fix `/syncnow`** — the on-demand reconcile trigger, currently broken ("Unknown command"
despite full wiring; likely input-artifact / runtime cmd mismatch).

## Scope boundary — #151 is NOT part of this

#151 (the partial-exit fix: verify the old stop left `pending_replace`/cancelled before
selling + `qty_available` poll + coverage-invariant) is a **leaf fix, shipped first and
independently.** The "DB-must-have-SoT" principle must **not** pull #151 into this
architectural rewrite (the recurring scope-creep trap). #151 fixes the partial-exit; #184
(this ADR) makes the DB a faithful mirror. Both are validated on
`integration_test_partial_exit.py` (the harness must reproduce stuck-`pending_replace` +
untracked-order + false-naked, or the bug isn't understood). Both are cutover prerequisites.

## Consequences

- A false-naked becomes structurally impossible: broker says covered → DB says covered.
- No real money goes live until the DB provably cannot disagree with the broker about
  protection (this ADR's increment 1 + #151, harness-gated).
- Subsumes the #123 trade-state derive-close follow-up and #179 (write-side root).
