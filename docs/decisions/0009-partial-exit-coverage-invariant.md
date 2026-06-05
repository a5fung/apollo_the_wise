# 0009 — Partial-exit hardening: coverage invariant + split (#151/#184)

**Status:** PLAN — awaiting operator scope approval (do NOT implement without it).
**Date:** 2026-06-05. **Advisor-validated.**

## Why now
FPS partial-exit failed two consecutive sessions (6/4, 6/5). Root cause
(broker-confirmed): the atomic `replace_order` *succeeded* (new reduced-qty
stop created) but the **OLD stop got stuck in `pending_replace`, still
reserving all shares** → the partial sell saw `available=0` → failed; rollback
starved; DB pointer nulled (false-naked). "New stop is live" was TRUE and it
still broke — the check is insufficient.

## The failure surface (pin this)
The broker's **async replace lifecycle**: `pending_replace → replaced/canceled`.
The invariant must assert the **OLD order reached a terminal / share-released
state**, not merely that a new stop exists.

## Plan — two phases, sequenced (advisor: leaf-fix now → component later)

### Phase 1 — LEAF recurrence-fix (ship FIRST, independent of the component)
In `execute_partial_exit` Step-1b, after `replace_order` returns: **poll until
the OLD stop leaves `pending_replace` (terminal/share-released) OR the position
`qty_available` covers the sell**, bounded timeout. If it does NOT release in
time → **ABORT BEFORE SELL** — leave the position over-covered (safe), retry
next window, calm audit (no naked alarm). This makes FPS a clean no-op both
days. Validate via `integration_test_partial_exit.py` reproducing a stuck
`pending_replace`. **This is the gate to un-pause the 16:45 cron with
confidence.** No new component required.

### Phase 2 — SHARED coverage invariant (the "split"; deliberate #184 work)
Extract `ensure_stop_coverage(trade, broker_truth)`: reads broker orders →
guarantees **exactly one live stop covering `remaining`**, idempotent; ADOPTS an
existing covering stop (never place-a-duplicate — the sync bug, #184 part-a /
#199-sibling); releases stuck/duplicate stops. Build behind
`integration_test_partial_exit.py`. **Migrate ONE path at a time:**
`execute_partial_exit` FIRST → prove live → THEN `sync_positions`. Never both at
once (a bug in it = a both-paths trade-state outage). This collapses #151
hardening and #184's reconciler into one shared invariant.

## Scope decision (operator)
#151 was deliberately reframed away from "the architectural split" to leaf-level
fixes on 5/29 (post-G6/TRIO). Swinging back to the split is **justified by the
6/4–6/5 recurrence** but is a scope call, not a default — approve Phase 2 as
deliberate #184-family work before it is built.

## Sequence
1. Operator approves scope.
2. Implement **Phase 1** (leaf fix) → deploy → validate via integration test →
   un-pause 16:45 cron (watched).
3. **Phase 2** as scheduled #184-family work, one path at a time, behind the
   integration harness. Promote by inspection.

Discipline: trade-state code — STOP-and-CONSULT; no implementation at the tail
of a long session. This doc is the durable artifact; implementation is a fresh
focused session.
