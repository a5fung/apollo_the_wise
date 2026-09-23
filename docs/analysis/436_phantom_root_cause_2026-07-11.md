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

## Side-effect sweep — the full blast radius of an un-confirmed proposal (operator chose fork B)

`pending_confirmation` is consumed in ~10 sites. Fork B ("a proposal isn't a position") is NOT a
one-liner — here is every consumer, classified:

**MUST change WITH fork B (behavioral):**
1. **The position cap lives in THREE sites, not one:** `db.get_open_position_count`,
   `live_tracker.py:115` (per-mode `MAX_CONCURRENT_LIVE_POSITIONS`), and `live_tracker.py:140`
   (per-strategy `max_concurrent_positions`). All three count `pending_confirmation`. B must exclude
   un-confirmed proposals at all three.
2. **`coverage_drift._OPEN_TRADE_STATUSES` must move in lockstep** — its own comment says it's
   reused *verbatim* from the cap vocabulary so "open" can never drift between the safeguard and the
   detector. A null-`entry_order_id` proposal falls through both D3 skips (`coverage_drift.py:283-286`)
   → logs `D3_DB_OPEN_NO_BROKER` every reconcile cycle. **CONFIRMED empirically: the 4 phantoms
   generated 32 `coverage_drift_detected` events on 7/6** (INFO, no Telegram — audit noise, not an
   alert storm, but real). If B changes the cap but not this, proposals keep polluting the drift stream.

**The altitude-right implementation:** the "is this row an open position?" definition is *shared*
across those sites. Change it ONCE — exclude `status='pending_confirmation' AND confirmed_at IS NULL`
(a proposal that was never confirmed) — and let every site that reuses the vocabulary inherit it.
Four independent edits would re-introduce exactly the drift the coverage-drift comment warns against.

**SAFE — no change needed (a proposal has no fill and no order):**
- **Daily-loss limit + drawdown breaker** — key off broker equity / filled-trade realized P&L; a
  0-share never-filled proposal contributes nothing.
- **`trade_stream` fill-matching** (`:960`) — matches on `entry_order_id = $1`, which is NULL for a
  proposal, so a real fill event can never bind to a phantom.

**COSMETIC — optional hygiene, not behavioral (a phantom shows as an open/entered trade):**
- `/trades` history + `/setup` outcome + the pending-entries list (`agent.py:4174/4253/5705/6631`)
  render a phantom as 🟡 open.
- Briefing / scheduler `entered_states` (`briefing.py:948`, `scheduler.py:1813`) bucket it as entered.
- These clear naturally once B + the self-heal land; worth a cleanup pass but nothing breaks.

**Existing-data cleanup: NONE required.** The 4 phantoms are already reaped to `status='cancelled'`,
which is in no open-status set anywhere — so they no longer pollute the cap, coverage-drift, P&L, or
displays. The historical mess is fully cleared; the fix is purely to stop the *next* ramp reproducing it.

## Deliverable

Diagnosis + design + side-effect sweep above. Next step is the operator's: fork B is chosen — wire
it at the shared "open position" predicate (the 3 cap sites + coverage-drift vocabulary, in lockstep),
plus the self-heal into the 15-min reconcile (with the 3-state broker-absent guard, composing with
#184 ingest) — via a committed dry-run-reviewed script (the #151 discipline), not an inline change.
Nothing to deploy tonight; the class is dormant (0 current strands).
