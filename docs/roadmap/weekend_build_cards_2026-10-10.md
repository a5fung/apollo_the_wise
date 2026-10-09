# Weekend build cards — Sat 2026-10-10

Reviewed 2026-10-09 (one Opus reviewer per card, against the code; both 'fix first', fixes applied below).
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

**The fix — the NARROW change (reviewed 10-09: replacing the whole branch with
`_restore_stop_after_failed_exit` would change his live pages, the pointer reason `cancel_or_reject_restored`
(rehearsal B2b, `test_600_reprotect_floor.py:455`), the audit site `trade_stream.full_exit_cancel_restore`
(`test_687_ruling_i_flat_vs_unreadable.py:240`) and the convergence harness's recorded cases s14/s15/s40 —
so the branch STAYS):**
1. **Exclude the dead sale.** At the `_broker_free_qty_for_restore(...)` call (~L2426) pass
   `exclude_ids=(trade_row["stop_order_id"], order_id)` — `order_id` is the event's own (expired/cancelled)
   sale. Day B's log shows the stream still saw that sale as live; this alone fixes that reading.
2. **Retry on a held-shares refusal.** In the branch's `except` around `place_stop_order`, BEFORE the ruling
   (3) check: if `_is_shares_held_refusal(e)` → hand off to `order_manager._retry_restore_while_shares_held`
   (0.5 s polls, ≤ 15 s), which gains `also_exclude_ids: tuple = ()` for its own free-share reads (pass
   `(order_id,)`). Map its result to the branch's EXISTING pages and pointer reason: placed → `set_stop_order_id(
   ..., reason="cancel_or_reject_restored")` + the existing *"Stop re-placed @$X for N sh"* page; sold →
   the existing sold-at-market page; covered/flat/failed → the existing pages. Audit rows `stop_restore_retried`
   / `stop_restore_retry_ended` as the order_manager path writes them.
3. **Only the retry runs in the background.** alpaca-py awaits each stream handler one at a time
   (`stream.py:90`, `_consume` ~L146), so a 15 s wait inline would stall every other fill at the open. The
   FIRST attempt and every existing outcome stay inline and unchanged; only the held-shares retry is spawned
   as a task kept alive by a module-level strong-ref set (the `_WATCHDOG_BG_TASKS` idiom), with its own
   try/except that sends the existing FAILED page. Tests drain the set.
4. **No lock taken** (decided, not his call: unchanged from today — the branch holds no per-trade lock now,
   and taking an unbounded `_trade_advisory_lock` from the stream is the #621 bound question he owns). The
   retry window ends ~15 s after the expiry (09:31:12 on a Day-B-like morning), long before the 09:35 refresh,
   which only try-locks anyway.
5. **`signal_type`** added to the branch's trade SELECT (~L2385) so the retry's mode-bound order id names the
   strategy (today it would read "unknown").

**Tests (each must fail on today's code):**
- broker lists the dead sale as holding every share → with the exclusion, the stop is placed on the first
  attempt, pointer reason `cancel_or_reject_restored`, the existing 'Stop re-placed' page;
- the place is refused for held shares, freed after 2 polls → stop placed by the retry, `stop_restore_retried`
  row, the same page, and the handler returned before the retry finished;
- held throughout the window → `stop_restore_retry_ended` + the existing FAILED page;
- convergence harness: s14, s15, s40 IDENTICAL to their recorded baseline; allow-list entries only for the new
  held-shares case (`tests/_convergence_687_harness.py`, `test_687_toggle_off_convergence.py`).
- price through the stop (ruling 3) and broker flat (ruling i): unchanged (existing tests stay green).

**Deploy:** `both`, then `execution` (trade_stream and order_manager run in apollo-execution). After 08:00 ET.

**Monday paper test (ruled: one test of this path at Monday's open, then the switch-on).** Script
`scripts/probes/_687/expiry_path_test.py` (reuse paper_rehearsal.py's paper guard, tagging,
`make_client_order_id('paper', 'integration_test', ticker)` and cleanup):
- **08:30 ET:** extended-hours LIMIT buy of 3 KO at the ask via alpaca-py `LimitOrderRequest(extended_hours=
  True)` directly (no helper exists). Its fill pages "Untracked fill" — expected. Then the trade row:
  `signal_type='integration_test'`, `account_mode='paper'` (the account check at trade_stream L330 joins on it),
  `status='filled'`, `remaining_shares=3`, `stop_order_id` NULL (as on Day B), `stop_price`/`hard_stop` well
  BELOW the market (else ruling 3 sells instead of restoring).
- **09:05:** opg sell for 3 sh, recorded with `order_manager._record_full_exit_order(trade_id, ticker, order,
  qty, reason)` (L5565 — call it, do not copy its SQL). Order type: a LIMIT at 2× the last price cannot fill;
  but only a MARKET opg expiring unfilled is proven on paper (Day B). If paper rejects the opg limit, fall
  back to a market opg (may fill → VOID).
- **Outcomes:** PASS = a stop for 3 sh at the row's price within 15 s of the expiry, its id on the row, the
  'Stop re-placed' page — and RECORD whether a `stop_restore_retried` row appeared (a first-attempt stop passes
  but leaves the retry unit-tested only, as on Day A). FAIL = no stop by 09:31:30, or the 'No stop re-placed'
  / UNPROTECTED page. INCONCLUSIVE = no expiry by 09:32, or the opg order rejected. VOID = the sell filled.
- **09:46 cleanup:** write the planned-sale cancel row for the restored stop BEFORE cancelling it, wait for the
  shares to free, sell 3 KO at market, delete the rows.
- Then his yes → `magna53_depth_exit` ON at noon ET.

**PLAN text (#687) ready to paste:** EXPECT (Mon open, paper): the expired opg sell is followed within 15 s
by a stop for the full position and the 'Stop re-placed' page; no 'No stop re-placed' page. UNINTENDED: the
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
1. In `run_ep_scan`, before the shortlist block (~L4160): open a connection from the pool and call
   `latest_complete_score_date(conn, on_or_before=today - 1 day, on_or_after=today - 7 days)` (db.py:8833 —
   it needs a live conn and returns None when no complete date exists). None, an exception or an empty map →
   skip, log one line, today's behaviour. Otherwise `shortlist_adv = await get_adv_map(that_date)`.
2. `ep_shortlist_shadow.compute_shortlist_ranking(candidates, in_theme_set, *, last_night_adv=None)`: when a
   candidate's own `adv_source` is not real and `last_night_adv` has it, the ENTRY (not the candidate dict —
   the function stays pure) carries `adv` = last night's `adv_20` in shares and `adv_source='rs_prev_complete'`,
   so the shadow row stores what acted (today it would store yesterday's single-day volume placeholder under a
   20-day label — review 10-09). Add `rs_prev_complete` to `_REAL_ADV_SOURCES` (ep_shortlist_shadow.py:59),
   to `_REAL_ADV` in `scripts/probes/ep_rubric_replay.py:58`, and to the `adv_source` column comment
   (db.py:4362).
3. `ep_rubric.shortlist_sort_key(ticker, composite, adv_dollar, pm_dollar=None)` →
   `(-composite, -(adv_dollar or 0.0), -(pm_dollar or 0.0) if adv_dollar is None else 0.0, ticker)`, so
   pre-market dollar volume orders ONLY the no-record names. `pm_dollar` = the candidate's `today_volume` ×
   its current price **as the sort sees them**: the sort runs before the real-time volume swap
   (`_apply_rt_volume` is in the grading loop; `current_price` IS set before the sort by the real-time
   overlay ~:4095), so the volume is the 15-minute-delayed snapshot (`:2843`) — the same value the 694 test
   measured. His option-2 text left "read real-time volume before the sort, or order on delayed" open: this
   card picks DELAYED (no new data call); record it in the change log as a known limitation.
4. Update the shortlist comment block in ep_rubric.py (term 2's "fixed the night before" is now true) and
   the `shortlist_sort_key` docstring's "replays reproduce the live order exactly" (ep_rubric.py:563-564) —
   no longer true unless a replay joins `mi_ep_scan_log` for `today_volume`/`current_price`; say so.
5. `docs/setups/magna53_ep.md` change-log entry with EVERY CHANGE_PROCESS.md field (L13-38): Trigger (the
   empty pre-open lookup, #694, found 10-05); the change; Evidence (the 694 doc: 14 crowded mornings, every key
   keeps all 5 real EPs; alone, 20-day dollar volume ranks them highest, 87% of 257 pairs, n=10 real EPs);
   Reversion-flag = **REFINEMENT of the 2026-08-22 shortlist pre-score + a BUG FIX** (the category, not a
   switch); Anticipated effect; Status; sign-off = his option 2 on 10-08; known limitation = delayed
   pre-market volume. Note: `ep_shortlist_prescore` OFF returns to GAP ordering, not today's A→Z — no switch
   restores the pre-fix state, and the entry says so.

**Tests (fail on today's code):**
- the DoD test: a pre-open `run_ep_scan` with TODAY's scores absent and yesterday's complete → the shortlist
  entries carry a real `adv_dollar` (the volume term is populated);
- no complete prior date → today's behaviour (fail-open), logged;
- the sort key: two no-record names tied at 32.5 → the higher pre-market dollar volume ranks first;
  names with a record are ordered by ADV$ exactly as before (pm_dollar ignored);
- regression from `scripts/probes/_694/dataset.csv` (lists replayed by the 10-09 reviewer):
  10-05 → option 2 cuts **SBS, PAGS, INTR, GRML, VIV** (that day's tie sits among names WITH a record, so this
  exercises the record path); 07-30 → option 2 cuts **STGW, CMCO, SMHI** and keeps PN, SMTI, BOOM (today's
  A→Z cuts SMHI, SMTI, STGW) — this exercises the pre-market tie-break (07-30's pre-market figures are rebuilt
  from logged values; fine for a sort test);
- an AFTER-OPEN tick too (the lookup is empty all day): drive `run_ep_scan` as
  `tests/test_605_decision_vector_capture.py` / `tests/test_533_catalyst_tier_flip.py` do;
- keep `tests/test_ep_shortlist_prescore.py` green, incl. its source pins on `run_ep_scan` (L226-288) and
  the existing tie-break tests (L126-135) — names with a record get 0.0 in the new slot.

**Deploy:** `market-agent`, then `execution` (the scan runs on the market agent, scheduler.py:160; ep_detector,
ep_rubric and db are execution-loaded).

**PLAN text (#694) ready to paste:** EXPECT (first weekday scan, baseline today = every pre-open shortlist
row has `adv_source` pending and ranks A→Z within its score): shadow rows show `rs_prev_complete` volume on
most rows and the logged prescore rank no longer follows A→Z within a score; graded set unchanged in size (20).
UNINTENDED: a different 20 graded on a crowded morning (expected — record which); a scan error or a fail-open
log line every tick. DONE-WHEN: the first weekday with more than 20 gap names shows ranks ordered by volume,
not A→Z (the task's own DoD). WOULD-FAIL-IF: `rank_by_prescore` still equals the A→Z order within a score on
a crowded morning, or the fail-open line appears on a day with a complete prior score date.

**Open question for him:** none — option 2 is ruled; grading stays untouched as his fix (b) said.

---

## Also riding Saturday's deploy (already on main, built Fri 10-09)

- #693: the theme validator thinks again (`theme_validation` out of THINKING_DISABLED, ceiling 2024).
- #505: generic ecosystem keyword stems removed from `theme_ecosystems.yaml`.

## 3–4. Not carded (capacity)

#505 (closest-theme pick — criteria recorded on its PLAN line), #655 sector cap, #624 / #692 wait for the
next free slot, per the order he agreed.
