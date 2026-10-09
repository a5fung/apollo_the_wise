# Weekend build cards — Sat 2026-10-10

Order agreed with him 2026-10-09 ("Ok"), capacity-limited: **1. #687 → 2. #694 → 3. #505 only if capacity
remains → 4. #655 cap / #624 / #692 next free slot.** Alpaca maintenance Sat 07:00–08:00 ET: no deploys or
broker tests in that hour. Weekends have no deploy window; check the clock against the weekend jobs anyway.

---

## 1. #687 — the expired / cancelled full-exit sale must re-place its stop (Monday launch depends on it)

**What broke (Day B, `scripts/probes/_1008/dayB_*.out`).** PEP's opening-auction sale expired unfilled at
09:30:57. `trade_stream._handle_cancel_or_reject` §3 (`pending_exit["purpose"] == "full_exit"`, ~L2379)
asked `_broker_free_qty_for_restore(..., exclude_ids=(stop_order_id,))`, which still counted the JUST-EXPIRED
sale as holding all 3 shares → `restore_qty <= 0 and source == "broker"` → paged *"No stop re-placed"* and
returned. PEP had no stop until the 09:35 refresh.

**The fix — one implementation, not two.** The stream's §3 full-exit branch re-implements what
`order_manager._restore_stop_after_failed_exit` (~L5316) already does (broker sizing, flat → nothing placed,
price-through-stop → ruling (3) sale, held-shares refusal → Wednesday's `_retry_restore_while_shares_held`),
minus the retry. Replace the branch's inline restore with a call to that function:

1. `_restore_stop_after_failed_exit` gains `also_exclude_ids: tuple = ()`, passed into
   `_broker_free_qty_for_restore(exclude_ids=(cancelled_stop_id, *also_exclude_ids))` and into the retry's
   own free-share reads. The stream passes `also_exclude_ids=(order_id,)`, the dead sale itself, so a
   just-expired order is never counted as holding shares. If the broker has not released them yet, the place
   is refused for held shares → the retry waits (0.5 s polls, ≤ 15 s) → places.
2. Keep the stream's `_apply_reprotect_floor(... consult_dead_stop=True)` price; pass it as `stop_price`.
   `shares` = the existing `_fallback_qty`; `reason` = the sale's `mi_live_orders.exit_reason` (already read
   for ruling (3)); `cancelled_stop_id` = `trade_row["stop_order_id"]`.
3. Page = the existing header `*Close order {EVENT}:* {symbol}` + `_restore_outcome_line(outcome, price)`
   (PLACED / COVERED / SOLD / FLAT / FAILED wording already reviewed). On PLACED, the pointer write is done
   inside the shared function. Delete the branch's now-dead inline code.
4. **Lock + never block the stream.** The retry assumes the caller holds the #151 per-trade lock, and the
   09:35 refresh try-locks and defers to it. But a 15 s wait inside the WS handler would delay every other
   fill at the open. So run the restore as a background task under `_trade_advisory_lock(trade_id)`, kept
   alive by a module-level strong-ref set (the `_WATCHDOG_BG_TASKS` idiom, ep_detector.py:3373), with its
   own try/except that pages FAILED on any exception. The handler returns at once.

**Tests (each must fail on today's code):**
- expiry, broker lists the dead sale as holding every share, then frees it after 2 polls → stop placed at
  the floored price, `stop_restore_retried` row, page carries "Stop RESTORED";
- the dead sale's id is excluded (fake open orders include it, no refusal) → placed on the first attempt;
- held throughout the window → `stop_restore_retry_ended`, page carries the FAILED / UNPROTECTED line;
- price already through the stop → ruling (3) market sale, unchanged;
- broker flat → nothing placed + `restore_skipped_broker_flat` row (ruling (i)), unchanged;
- the handler returns before the restore finishes (background task; awaited in the test via the ref set);
- the 09:35 refresh run concurrently with the held lock → it defers (no second stop).

**Deploy:** `both`, then `execution` (trade_stream and order_manager run in apollo-execution). After 08:00 ET.

**Monday paper test (ruled: one test of this path at Monday's open, then the switch-on).** A
limit-on-open (tif `opg`, LIMIT far above the market) SELL cannot fill and expires ~30 s after the open, which
drives exactly this branch. Script `scripts/probes/_687/expiry_path_test.py` (reuse paper_rehearsal.py's
paper guard, tagging, `make_client_order_id('paper', 'integration_test', ticker)` and cleanup):
- **08:30 ET:** an extended-hours LIMIT buy of 3 KO at the ask (paper allows extended-hours limit orders; stops
  are not accepted pre-market, so the paper position is bare until the open — paper only). Then write an
  `integration_test` trade row (paper) the way the rehearsal does, with stop_price and hard_stop.
- **09:05:** place the opg LIMIT sell at 2× the last price for 3 sh, and write its `mi_live_orders` row with
  `purpose='full_exit'` exactly as `execute_depth_open_sale` does (copy the insert, not a lookalike).
- **09:30:30–09:31:30:** the broker expires it → the stream re-places the stop.
- **PASS:** a stop for 3 sh at the row's price within 15 s of the expiry, its id on the row, a 'Stop RESTORED'
  page. **WOULD-FAIL-IF:** no stop by 09:31:30, or the 'No stop re-placed' / UNPROTECTED page.
- **09:46:** cleanup: cancel our orders, sell 3 KO at market, delete the rows (after the ORB window).
- Then his yes → `magna53_depth_exit` ON at noon ET.

**PLAN text (#687) ready to paste:** EXPECT (Mon open, paper): the expired opg sell is followed within 15 s
by a stop for the full position and a 'Stop RESTORED' page; no 'No stop re-placed' page. UNINTENDED: the
stream lagging other fills at the open (would show as late fill commits). DONE-WHEN: that PASS + his yes on
the flip → a new line for the live watch. WOULD-FAIL-IF: as above.

**Open question for him:** none (the order and the Monday test are already ruled).

---

## 2. #694 — option 2: the shortlist reads last night's volume; pre-market dollar volume orders the no-record names

**Why (docs/analysis/694_tiebreaker_2026-10-08.md).** `run_ep_scan()` is called with no date
(scheduler.py ~1200, agent.py ~783), so `prev_date` = today (ep_detector.py:3638) and `get_adv_map(prev_date)`
(:3695) reads today's `mi_stock_scores` rows, which the RS run writes only at ~17:00. The lookup is empty
**all day**, not only pre-open. His pick 10-08 (option 2): the signed key, with pre-market dollar volume
ordering names that have no volume record.

**The fix — the shortlist ranking only; grading untouched.** Do NOT change `adv_map` (it feeds the candidate
build, the liquidity gates and the grading score; that would be a separate change he has not ruled).
1. In `run_ep_scan`, before the shortlist block (~L4160), read
   `shortlist_adv = await get_adv_map(await latest_complete_score_date(conn, on_or_before=today - 1 day))`
   (the newest COMPLETE score date strictly before today; never today's partial rows). Fail-open: an
   exception or empty map → today's behaviour, logged.
2. `ep_shortlist_shadow.compute_shortlist_ranking(candidates, in_theme_set, *, last_night_adv=None)`: when a
   candidate's own `adv_source` is not real, use `last_night_adv.get(ticker)` × prev_close as `adv_dollar`
   for the PRE-SCORE and the sort (source label `rs_prev_complete` in the shadow row's raw inputs, so the
   shadow table shows which value acted). Candidates' dicts are not mutated (the function is pure).
3. `ep_rubric.shortlist_sort_key(ticker, composite, adv_dollar, pm_dollar=None)` →
   `(-composite, -(adv_dollar or 0.0), -(pm_dollar or 0.0) if adv_dollar is None else 0.0, ticker)`, so
   pre-market dollar volume orders ONLY the no-record names. `pm_dollar` = the candidate's `today_volume` ×
   its current price **as the sort sees them**: the sort runs before the real-time volume swap
   (`_apply_rt_volume` is in the grading loop), so this is the delayed snapshot's volume. Say so in the
   docstring; it is the value live will use.
4. Update the shortlist section's comment block in ep_rubric.py (term 2's "fixed the night before" is now
   true), and `docs/setups/magna53_ep.md` with a CHANGE_PROCESS change-log entry: evidence = the 694 doc
   (14 crowded mornings; every key keeps all 5 real EPs; alone, 20-day dollar volume ranks them highest, 87%
   of 257 pairs); sign-off = his option 2 on 10-08; reversion flag = runtime toggle `ep_shortlist_prescore`
   OFF restores gap ordering (existing); a backtest is the 694 replay itself.

**Tests (fail on today's code):**
- the DoD test: a pre-open `run_ep_scan` with TODAY's scores absent and yesterday's complete → the shortlist
  entries carry a real `adv_dollar` (the volume term is populated);
- no complete prior date → today's behaviour (fail-open), logged;
- the sort key: two no-record names tied at 32.5 → the higher pre-market dollar volume ranks first;
  names with a record are ordered by ADV$ exactly as before (pm_dollar ignored);
- regression on the stored 10-05 board (`scripts/probes/_694/dataset.csv`): fix (b) cuts SBS, PAGS, INTR,
  GRML, VIV (the doc's expected list); on the 07-30 board the 6 no-record names tied at the cut are ordered
  by pre-market dollar volume (assert the order from `dataset.csv`'s k2 column), not A→Z.

**Deploy:** `market-agent`, then `execution` (ep_detector is execution-loaded). After 08:00 ET.

**PLAN text (#694) ready to paste:** EXPECT (first weekday scan, baseline today = every pre-open shortlist
row has `adv_source` pending and ranks A→Z within its score): shadow rows show `rs_prev_complete` volume on
most rows and the logged prescore rank no longer follows A→Z within a score; graded set unchanged in size (20).
UNINTENDED: a different 20 graded on a crowded morning (expected — record which); a scan error or a fail-open
log line every tick. DONE-WHEN: the first weekday with more than 20 gap names shows ranks ordered by volume,
not A→Z (the task's own DoD). WOULD-FAIL-IF: `rank_by_prescore` still equals the A→Z order within a score on
a crowded morning, or the fail-open line appears on a day with a complete prior score date.

**Open question for him:** none — option 2 is ruled; grading stays untouched as his fix (b) said.

---

## 3–4. Not carded (capacity)

#505 (closest-theme pick — criteria recorded on its PLAN line), #655 sector cap, #624 / #692 wait for the
next free slot, per the order he agreed.
