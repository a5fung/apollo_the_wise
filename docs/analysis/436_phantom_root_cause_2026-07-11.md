# #436 — phantom `pending_confirmation` root cause + fix design (read-only diagnosis, 2026-07-11)

**Scope:** this is the #436(a) root-cause diagnosis + a fix-design recommendation for operator
sign-off. It is READ-ONLY — nothing implemented. The fix touches the position-cap safeguard and
trade-state (THE LINE) → the operator decides + a committed dry-run-reviewed script does it.

## Headline reframe: this is NOT an active bug. It was a one-time pre-go-live-ramp artifact.

#436 is filed as if magna53 entries are *actively* stranding in `pending_confirmation`. They are
not. **The auto-enter path is atomic and correct** — every real trade since go-live proves it
(AVAV 6/30, WULF 7/6, DOCN 7/7, CRCL/WDFC 7/10 all have `confirmed_at` AND `entry_order_id` set
within ~2ms of `proposed_at`). The phantom class does **not** recur for magna53 as it runs today.

## The evidence chain (prod, read-only)

The 4 phantoms (ABSI/FCEL 6/24, SNX 6/25, ACAD 6/26) are the **only** pre-6/30 live-account rows,
and all four have `confirmed_at` NULL + `entry_order_id` NULL. The first *real* auto-enter was
**AVAV on 6/30** — the go-live day. So on 6/24–6/29 magna53 was `phase='live'` /
`live_real_enabled=False` = the **staged-paper ramp**: `_should_auto_enter` returns False, so each
ORB candidate is inserted `pending_confirmation` and a Telegram proposal is sent, awaiting MANUAL
confirm (`entry_pipeline.py:529`). `confirmed_at` NULL = line 472 (the auto-enter confirm) never ran
= these were proposals, correctly, never a stranded auto-enter.

**Root cause:** an un-confirmed staged-paper proposal has **no expiry**. The operator didn't confirm
these 4 (informational, during the ramp); they persisted as `pending_confirmation` forever and —
because `get_open_position_count` counts that status — consumed 4 of 5 position-cap slots, which is
what nearly blocked the WULF-class real entry on 7/6. *(The `telegram_markdown_fallback` 400s near
those alerts are cosmetic — a send failure strands the row identically via line 537, so they're not
the cause.)*

## Does it recur? Only for a FUTURE live-staged ramp.

- **magna53 today** (`live_real_enabled=True`): auto-enters, no proposals → cannot produce this class.
- **A future ramp** (9M Day 2, HTF when they promote to `phase='live'`/`live_real_enabled=False`):
  WOULD reproduce it exactly. So the fix is **forward-looking hardening for the next ramp**, not an
  urgent live-bug patch. Current state is clean — **0 rows** in `pending_confirmation`/`confirmed`/
  `submitting` with null `entry_order_id` (the #287 reaper cleared the 4; nothing new).

## Fix-design blind spot: THREE stranded states, not one — and two are dangerous to blind-cancel

A self-heal must not cancel by status alone. Non-terminal rows with null `entry_order_id`:

| state | how it strands | broker order exists? | safe to cancel? |
|---|---|---|---|
| `pending_confirmation` | proposal never confirmed | **No** (never submitted) | ✅ safe |
| `confirmed` | auto-enter crashed after line 472, before submit | maybe not | ⚠ only if broker-absent |
| `submitting` | `submit_entry` set it (order_manager:200), crashed before the `order_placed` write (:270) | **maybe YES** (real Alpaca order/fill) | ❌ NEVER blind-cancel |

**Hard constraint:** anything past `pending_confirmation` must be **broker-confirmed-absent** before
cancel. Blindly cancelling a `submitting` strand while a real order/fill lives on = orphaned real
position with no DB tracking — exactly the trade-state corruption THE LINE guards against.

## Recommended fix (design only — operator signs, #151 script implements)

**#436(b) self-heal — compose with the #184 ingest, do NOT build a separate reaper.** Fold into the
15-min `order_status_reconcile` job (the same job #184's `order_ingest` now runs in):
- `pending_confirmation` aged > 1 trading day, null `entry_order_id`, broker-absent → cancel
  (`phantom_expired`).
- `confirmed`/`submitting` with null `entry_order_id`: broker HAS an order → **reconcile/ingest via
  #184's path** (adopt the real order into the mirror), NOT cancel; broker has nothing → safe cancel.

**The prevention fork (operator's call — THE LINE, present both):**
- **(A) Expire proposals at the 10:00 ET ORB cleanup** — a staged-paper proposal not confirmed by
  10:00 ET is dead for that day's ORB entry; cancel it alongside the unfilled `order_placed` sweep.
  Altitude: same place the ORB day already cleans up.
- **(B) Don't count un-confirmed `pending_confirmation` toward the live position cap** — a proposal
  isn't a position. More targeted at the actual harm (cap starvation), and independent of timing.
- **Recommendation: (B)** as the primary (it fixes the real harm — cap starvation — directly and
  can't strand a slot regardless of when a proposal is actioned), with (A)'s expiry as hygiene so
  stale proposals don't accumulate. Both change safeguard/discipline semantics → **operator sign-off
  required**; neither implemented here.

## Deliverable

Diagnosis + design above. Next step is the operator's: pick the prevention fork (A/B/both), then a
committed dry-run-reviewed script wires the self-heal into the reconcile (with the broker-absent
guard) — the #151 discipline, not an inline change. Nothing to deploy tonight; the class is dormant.
