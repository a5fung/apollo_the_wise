# Pre-merge pass 2026-10-31 — design notes (breakout v1 phase 2, branch breakout-v1-phase2)

Scratch only. The SSoT entry is docs/setups/consolidation_breakout.md (appended under the 10-29 PHASE 2 entry).

## A. The unstopped-third window (findings 1, 2 + advisor item 1) — one defect

Today (`breakout_pp_exit.cancel_resting_third` + `live_tracker._breakout_pp_session3`):
- marker (PLANNED_THIRD_CANCEL) -> cancel -> ~3 s poll of the PARENT only -> dead | filled | open | unknown.
- the stream leaves a MARKED unfilled cancel alone (no re-protect) -> if the cancel settles after the wait, nobody
  covers the third (the OCO took its sibling stop) until the 5-minute coverage repair.
- the parent read alone cannot see a sibling STOP-leg fill (parent canceled, 0 filled) -> read as 'dead' -> a SECOND
  third sold at market.
- the order-row update raising after a confirmed cancel -> 'unknown' -> nothing re-protected, and the open row makes
  `_ensure_stop_coverage` net the dead limit as pending (reads "covered").

Fix (breakout rows only; the stream's / poll's EP paths untouched):
1. `cancel_resting_third` polls the parent AND the sibling stop leg (leg id from the stored OCO row's raw_response, else
   the live read's legs), each read `get_order(.., timeout=CANCEL_READ_TIMEOUT_S)` (B) under a wall-clock deadline.
   States: 'filled' (the limit filled: that is the third) | 'stop_filled' (the LEG filled: the third sold at its stop —
   nothing more sold, the leg's own fill event books it) | 'dead' (parent terminal, 0 filled, leg not filled: the row
   closed by CAS, the third sold at the close) | 'open' | 'unknown'.
2. CONFIRM-OR-REPLACE on 'open' / 'unknown' after the deadline: WITHDRAW the stream's "leave it alone" (a
   `breakout_pp_planned_third_cancel_withdrawn` row naming trade + order) so a LATE settle is handled by the ordinary
   OCO-parent cancel path (`_handle_oco_parent_cancel` -> leg dead -> `_ensure_stop_coverage` from broker truth,
   idempotent). Then ONE more read: dead now -> the 'dead' path (sell); still open -> the OCO is intact (its sibling stop
   covers the third) — nothing placed on top of a possibly-live leg (that is two sells for one third).
   The POLL's ban is a separate read (`third_replacement_banned`: any marker row, withdrawn or not, or an unreadable
   log -> banned) so the withdrawal never re-opens the +2R limit (finding 6 stays the operator's).
3. The order-row CAS close gets one retry; if it still fails the result is 'dead' + `row_update_error` and the step
   does NOT sell (the dedup would refuse on the stale row anyway) — it re-protects (`reprotect_after_unsold_third`, which
   retries the CAS first so `get_pending_exit_qty` stops counting the dead limit, then `_ensure_stop_coverage`).
4. Pages say plainly "No third was sold" and that the +2R limit will not be re-placed.

## B. Finding 3 — `get_order(.., timeout=3.0)` per read, `CANCEL_DEADLINE_S` wall-clock (time.monotonic).
## C. Finding 4 — the poll fails CLOSED (`third_replacement_banned`); `execute_partial_exit` re-checks `partial_taken`
   (fresh row under the lock) and, for a +2R placement (limit_price given), the ban, before any order — breakout_pp only.
## D. Finding 5 — `_breakout_pp_stop_to_fill_after_third` reads (qty, status, filled_qty) of the order row; a
   'partially_filled' row whose cumulative fill == qty is set 'filled' (CAS) before `update_stop`, so the stop is sized
   on the whole rest. A real partial (cum < qty) still defers.
## E. Finding 7 — `_finalize_partial_exit_locked -> str | None`; SSoT names which path pages.
## F. Advisor 2 — audit_column_writes.py hard_stop comment; harness: a trade whose stop was LOWERED after the fill.
## G. Advisor 3 — the 16:45 pass (`update_open_positions_live`'s breakout branch) runs the stop-at-the-fill check for a
   filled breakout row with no `breakout_v1_fill_stop_checked` row, BEFORE the day-0 facts (they read hard_stop).
   Why 16:45 and not the next session's first tick: the tick's population is TODAY's rows for last night's list — a
   row filled yesterday is never in it; the 16:45 pass already visits every open breakout row on its breakout day.
