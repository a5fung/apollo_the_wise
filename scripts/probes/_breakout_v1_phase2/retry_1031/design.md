# Retry pass 2026-10-31 — design notes (breakout v1 phase 2, branch breakout-v1-phase2)

Scratch only. The SSoT entry is docs/setups/consolidation_breakout.md (RETRY PASS 2026-10-31, under the 10-29 PHASE 2 entry).

## 1. His ruling (finding 6) — "Retry the sale at the next day's close" / "Go with rec on both"

The trigger is the discriminating constraint: the retry must fire only when session 3 DECIDED to sell and the sale did
not happen — never on "session > 3 and partial_taken FALSE" (a trade whose session-3 close was at/under the fill got no
third by his rule; selling it on session 4 would be a rule change = THE LINE).

- Durable record `breakout_pp_session_third_due` (an audit row: trade, price, decision, resting order id), written by
  the 15:45 step the moment `session3_decision` resolves to `session_third` / `cancel_resting_third` — BEFORE the
  cancel and BEFORE the sale, on the `facts is None` path too.
- Reader `breakout_pp_exit.session_third_due`: the due row OR the planned-cancel marker OR the "selling N sh" row
  naming the trade (any one proves the decision; belt and braces for a crash between the decision and the due write).
  Fail direction: unreadable -> NOT due (a wrongful sale is irreversible; a delayed one is not), audited
  `breakout_pp_third_due_unreadable`.
- Pure rule `breakout_pp_rules.retry_decision(fwd, partial_taken, session_third_due)`: len(fwd) > 3, no third sold,
  due -> 'retry_third'. No price condition of its own (his rec had none) — named in the SSoT as the fork he can rule on.
- `live_tracker._breakout_pp_third_retry`: reached from `_breakout_pp_session3` when len(fwd) > 3. partial_taken ->
  nothing (not even a book read). Else due -> `resting_third` -> ONE sell path shared with session 3
  (`_breakout_pp_sell_third`): resting (the +2R limit, or a stuck session-3 market sale) -> `cancel_resting_third`
  (marker, bounded reads, the sibling leg, confirm-or-replace) -> filled / stop_filled = the third, dead = its own size
  sold, unconfirmed = nothing sold + withdraw + cover (retried next close); nothing resting -> profit_take_shares at
  market. Audit `breakout_pp_third_retry` then `_sold` / `_third_filled` / `_third_stopped` / `_failed`.
- One third ever: (C)'s under-the-lock re-check of partial_taken refuses a sale that lands after a fill; the poll's
  ban (`third_replacement_banned`) is untouched — the retry is a close sale, never a limit.
- ADVISOR FINAL-REVIEW FINDING (fixed before commit): a stop-leg fill of the third (the OCO sibling) is booked by
  `_finalize_stop_fill_locked` — remaining_shares decremented, a 'stop_hit' exit appended, `partial_taken` NEVER set.
  A retry on the flag alone would sell a second third the next session. Guard: `breakout_pp_exit.shares_already_sold`
  (the flag, then the row's booked exits, then a filled partial_exit / stop_loss order row; unreadable -> sold, fail
  closed) read by the session-3 step and the retry; the fuzz models the stop-leg fill as the finalizer books it.
- REVIEW (medium, after 9117c060): the reader never read the row's share counts nor the broker — a session-3 market
  sale the broker ACCEPTED whose `mi_live_orders` INSERT raised (execute_partial_exit's except returns False) fills as
  an 'Untracked SELL' (trade_stream._handle_fill step 4: a page, nothing booked); the 16:05 sync lowers
  remaining_shares alone (`sync_qty_overwrite`). Session 4's retry then sold a SECOND third. Fix: two more reads in
  `shares_already_sold`, after the exits — (1) `remaining_shares < entry_shares - 0.5` (both set to the FILLED qty at
  the entry fill by trade_stream ~1009 and check_fills ~1136; an entry partial_fill is visibility-only) and (2) the
  broker's position `qty` (never `qty_available`: a resting OCO reserves) `< remaining_shares - 0.5`; no position read
  -> sold (gone or unreadable: get_position answers None to both). Each read has its own `why`; either writes
  `breakout_pp_shares_left_unbooked`. The retry audits `breakout_pp_third_already_sold` (retry: true) when the wider
  read stops a retry that was due (it used to stop silently). The fuzz adds the unrecorded sale (after an accepted
  sale, and after a 'refused' one), synced and not; sessions after it cancel nothing and sell nothing.
- A retry whose plain sale raises: caught in `_breakout_pp_third_retry` -> `breakout_pp_third_retry_failed` + page;
  the pass goes on (session 3's raise path is unchanged: the guarded wrapper).

## 2. The 15:45 collision's REVERSE order (live_tracker ~1529)

`execute_partial_exit` returns bool; the dedup refusal is not distinguishable by return value. After a refused PLAIN
sale (no cancel happened) the step re-reads `resting_third` once: resting -> `breakout_pp_session_third_refused_limit_resting`
and the cancel path this session (the second pass; `after_refusal=True` stops a loop); nothing -> `breakout_pp_session_third_unsold`
+ page; the due record (already written) makes the next close retry it.

## 3. `fill_stop_checked`'s 3-day lookback vs the 16:45 caller (breakout_v1_entry ~786)

- `check_stop_at_fill_after_close` returns `fill_other_session` unless `row['alert_date'] == now_et.date()` — before
  any read. The pass's purpose is the 15:55 fill race, today's.
- `fill_stop_checked` drops the 3-day INTERVAL (pinned as SQL text; the World fake ignores intervals).
- Consequence owned: the (G) dead-leg path is no longer retried the next evening; the stop stands as it filled (never
  wider); the page and audit say "not retried". Test rewritten.

## Tests (tests/test_breakout_pp_exit.py §8, tests/test_breakout_v1_entry.py)

13 new + 1 rewritten; the three breakout suites 182 passed; full suite in full_suite.out.
