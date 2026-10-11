# #698 — can the +8R partial sell a SECOND slice after its OCO stop scratches? (read-only check, 2026-10-10)

**Answer: the code path is real but it needs the slice's stop to sit ABOVE the main stop, which today's
live configuration does not produce on its healthy path (both stops land on the same cent — 4 of 4 real
OCO events, 6 of 6 resting-mode partials); it has never happened (0 of 4 OCO stop legs ever filled; 0 of 19
partial trades ever sold a second slice); and closing it is HIS ruling, not a bug fix — the SSoT records the
re-fire as intended (08-15) and as his call (10-10), while the mechanism's own words ("first trades",
`partial_taken`) and the 08-14 signed design read as one partial per position. Nothing on the open book is
exposed today (0 of 3 positions).**

> ⚠ **Independent check (Opus, 2026-10-10) — corrections to read with this page.** (1) **A second backstop this page missed:** the +3R breakeven arm (`scan_breakeven_arms`) runs in the same 5-minute job right after `scan_profit_triggers` (scheduler.py ~2419 then ~2435), selects trades with `breakeven_active = FALSE` (which includes a trade whose OCO is still resting), reads the LIVE broker stop and raises any stop below entry to round(entry, 2) — so a failed breakeven move is repaired within seconds, narrowing reachability further. (2) **Mis-cited support:** exit_discipline.md 2026-08-04 ("`partial_taken` only flips TRUE on a SUCCESSFUL partial") explains why the trigger re-selects a trade; it is not a one-partial rule, and read literally it argues against flipping `partial_taken` on a scratch. EP_TRADING_RULES.md §B5 is the Day 3-5 ladder, not the +8R trigger. (3) **Not minimal:** a one-site read-side fix exists — exclude from `scan_profit_triggers` any trade with a FILLED stop leg of a `purpose='partial_exit'` OCO — with no new trade-state writer. (4) **Second-sale outcome unverified:** after a scratch at entry the second OCO's stop sits at or near the market, so it more likely scratches a second share (or Alpaca rejects the leg and the partial aborts) than fills at the target. (5) **Facts:** 5 live MAGNA53 fills had exactly 3 shares (TSEM, NET, CRWD, PHVS, CEG), not 1; only CRWD took a partial (old +2R level); none reached +8R. 'Rare by construction' is empirical, not structural (ETON's pre-OCO limit rested 6 h 23 m on 08-14). (6) TEAM 57 / SMCI 82 `partial_exit_started` after a `stop_hit` are May PAPER re-entries, not leg scratches. **The conclusion stands:** real in code, not reachable on today's live path, never happened (0 on every prod check); closing it would be his sell-discipline ruling.

Scope: READ-ONLY. Code at `fa39f5ef`; prod read once (`scripts/probes/_698_refire/q1_refire.sql` → `.out`,
`q2_followup.sql` → `.out`, 2026-10-10, SELECT only). No code, PLAN or SSoT edited. Known limitation 7 of
`docs/setups/magna53_ep.md` (2026-10-10 entry) is the claim under test.

## Population and method

- **Decision this serves:** whether #698's Sunday verify must treat a second 1-share sale as a defect to fix
  NOW (and whether the fix is mine to make), or whether Known limitation 7 stands as written until he rules.
- **What would change it:** n ≥ 1 OCO stop leg ever filled while the trade stayed open, or a live
  configuration in which the leg's stop sits ABOVE the main stop on the healthy path. Either makes it urgent.
- **Rows, window, derivation (prod, read 2026-10-10 ~20:00 UTC; the question is "ever", so NO window —
  all-time, every table):**
  - `mi_live_orders`: every row `purpose = 'partial_exit'` (n = 18 real + 2 deleted-harness; Q4) and, for each
    with `raw_response->>'order_class' = 'oco'` (n = 4), its sibling leg via `raw_response->'legs'` joined to
    the leg's own `purpose='stop_loss'` row (Q5); every FILLED `purpose='stop_loss'` row with `qty <
    entry_shares` (n = 15; Q6).
  - `mi_live_trades`: every trade with `partial_taken = TRUE` OR a `partial_exit` order (n = 19; Q9), the
    `exits[]` array counted by `reason`; the open book (`status='filled'`, n = 3; Q11/Q12) with
    `MAX(high)` since `filled_at` from `mi_intraday_bars`.
  - `mi_audit_log`: per-trade counts of `profit_trigger_fired/failed`, `partial_exit_started/sell_placed/
    committed/aborted` (n = 29 trades; Q3); all-time counts of the OCO-unwind and breakeven-degrade events
    (Q7, F7); the full per-trade timeline for the 18 partial trades (192 rows; Q10). `detail` is parsed as JSON
    only where it starts with `{` (trade_stream writes '' details).
  - Toggles and levels from `mi_safeguard_state` / `mi_strategies` (Q1/Q2), not from prose.
- **Eras inside the all-time set, named:** the OCO shape exists since 08-15 (built) / 08-17 (live on), so the
  population the QUESTION is about is the 4 OCO partials 08-18 → 09-28; the +8R level since 09-06 (1 event,
  KOD); the 2-share sizer since 10-10 (0 events). Pre-OCO partials (May–Aug: market and plain-limit shapes)
  are in the counts only to prove no trade ever sold two slices under ANY shape.
- **Live and paper, split:** all 4 OCO events are live MAGNA53; the paper lane (`magna53_smallcap`) has 0 fills;
  the paper rows in Q3/Q9 are 9M/MAGNA53 paper trades from May–July (market shape). KO 407/417 were paper
  harness trades, since deleted.
- **Dead strategies:** `9m_day2` rows (GOOGL 56, PURR 161, IBM 167, FPS 183) are deprecated and appear only as
  non-events in the double-sale count.
- **What would make this wrong:** a leg that FILLED at the broker without our tables recording it. The leg is
  hidden from `get_open_orders` while held, so the mirror row + the WS fill event are its only record. Check: all
  4 leg rows read `cancelled`, a status only the WS cancel handler / `reconcile_order_states` write after the
  broker reported it — so each leg's terminal state WAS received; none reads `held`. A second blind spot: a
  re-fire would leave a second `partial_exit` row for the trade (Q4 shows at most one per trade) — a check that
  does not depend on the leg's status at all.

---

## 1. The order lifecycle of a +8R partial under TODAY's configuration

### 1a. The configuration (prod, 2026-10-10 — `q1_refire.out` Q1/Q2)

| switch | live | paper | effect on this question |
|---|---|---|---|
| `profit_take_resting_limit` | on (since 08-10 21:15 UTC) | on (10-10) | the slice is a resting GTC limit, not a market sell |
| `profit_take_oco` | on (since 08-17 15:03 UTC) | on (10-10) | the slice rests as ONE OCO: limit at target + stop |
| `breakeven_at_broker` | on (no transition date recorded) | on (10-10) | Step 2b moves the main stop to breakeven |
| `partial_exit_leg_safe` | on (global, 08-04) | — | Step 1 reduces a bracket-leg stop by cancel+new |
| `magna53_depth_exit` | NO ROW = off | NO ROW = off | depth stop not in play; `exit_rule` stamped on 0 trades (Q11) |
| `mi_strategies.profit_trigger_r` / `breakeven_arm_r` | magna53 8.0 / 3.0 | magna53_smallcap 8.0 / 3.0 | +8R partial, +3R price-armed breakeven; every other strategy NULL/NULL, none holds a position |

### 1b. The sequence, with the price each stop carries

1. **+3R arm (before +8R, same 5-minute job, runs AFTER the partial poll).** `scan_breakeven_arms`
   (`order_manager.py:9926`) → `_arm_breakeven_on_full_stop` (:10020): price-only replace of the FULL
   position's stop to `be = round(entry, 2)`; on a confirmed successor `_mark_breakeven_armed` (:9859)
   writes `stop_price = be`, `breakeven_active = TRUE`. Prod since 09-06: `breakeven_armed` 3,
   `breakeven_arm_noop` 1, rejected 0, failed 0, skipped 0 (Q7). KOD 404: 09-28 13:40 UTC, $58.08 → $63.15.
2. **+8R poll.** `scan_profit_triggers` (:9655) selects `status='filled' AND remaining_shares > 0 AND
   COALESCE(partial_taken, FALSE) = FALSE` (:9699-9707), tests `MAX(high)` since `filled_at` against
   `entry + 8 × (entry − orb_low)`, sizes with `profit_take_shares` (:9749; 2 → 1 since 10-10, 3-5 → 1,
   6 → 2), calls `execute_partial_exit(trade_id, shares, limit_price=target)` (:9787).
3. **Dedup** (:3360-3385): abort if any `mi_live_orders` row for the trade with `purpose IN
   ('partial_exit','full_exit')` is NOT in `PENDING_EXIT_TERMINAL_STATUSES` = {filled, cancelled, canceled,
   rejected, expired} (:1674).
4. **Step 1 — reduce the main stop to `new_remaining` at the DB `stop_price`** (:3460+; bracket leg →
   `_reduce_stop_via_cancel_new` :2997 → `place_stop_order`, which rounds `round(stop_price, 2)`
   (`alpaca_client.py:406`)). The DB price, not the broker's — after a VERIFIED arm the DB price is `be`.
5. **Step 2 — the OCO for the slice** (:4025, `place_oco_sell` `alpaca_client.py:536`): limit at the
   target; **sibling stop at `oco_stop_price = max(DB stop_price, entry)`** (:3429-3433), tick-rounded
   by `_round_stop_to_tick` (:610, `ROUND_DOWN` to the cent). The leg is mirrored as a
   `purpose='stop_loss'` row with `qty = shares` (:4073-4090); `stop_order_id` keeps pointing at the
   main stop.
6. **Step 2b — move the main stop to breakeven** (:4172-4190): `_be = max(DB stop_price, entry)`; **only
   if `_be > stop_price + 1e-9`** → `replace_order(new_stop_id, stop_price=_be)` (also
   `_round_stop_to_tick`, `alpaca_client.py:666`). Rejected → `partial_exit_breakeven_deferred` (the main
   stays at its Step-1 price); successor dead/unknown → `_unverified` / `_unverifiable` + re-protect at
   the DB price.
7. **Afterwards.** The daily trail (`update_stop` :2227, 16:45 ET) raises ONLY `stop_order_id` (the main
   stop) — it never touches the OCO leg (the leg is deliberately not the pointer; `_try_adopt_existing_stop`
   cannot adopt a held leg; the 08-15 SSoT: "the OCO stop stays AT breakeven by construction"). The +3R arm
   running after a partial finds the main at/above entry → `breakeven_arm_noop` (flag only). The depth exit
   (OFF) would floor its stop at `max(hard, entry)` once `breakeven_active` is set — above or equal to the
   leg, never below it unless breakeven was never armed.

### 1c. Where the two stops sit — the same cent on every healthy path, including the rounding

| path at +8R | main stop after Step 1 → 2b | OCO leg stop | equal? |
|---|---|---|---|
| arm fired first (DB `stop_price = round(entry,2)`) — KOD | Step 1 at `round(be,2) = be`; 2b skipped (`_be == stop_price`) | `ROUND_DOWN(max(be, entry))` = `be` (be ≥ entry rounded-down) | **yes** — KOD main $63.15, leg $63.15 (Q5, Q10) |
| arm not yet fired (DB `stop_price` < entry) — AMLX, MRNA, CRWD | Step 1 at the old price; 2b → `ROUND_DOWN(entry)` | `ROUND_DOWN(entry)` | **yes** — 2b wrote $30.21 / $120.75 / $213.31 (`:.2f` of the same unrounded `_be`); the broker received `ROUND_DOWN` of the identical float on both orders |
| main trailed above entry before +8R (DB `stop_price` > entry) | Step 1 at `round(stop,2)`; 2b skipped | `ROUND_DOWN(stop)` | equal, or the leg ONE CENT BELOW the main (`ROUND_DOWN ≤ round`) — never above |

`ROUND_DOWN(x) ≤ round(x)` for every x, so **rounding can never put the leg's stop ABOVE the main's**. The
only ways the leg sits above the main are the degraded paths in 1d.

### 1d. Can the slice's stop fill WITHOUT the main stop filling? — every configuration

| # | configuration | leg stop vs main stop | slice's stop fills alone? | second partial reachable? | prod occurrences |
|---|---|---|---|---|---|
| A | **today's healthy path**: resting + OCO + breakeven_at_broker on, arm or Step 2b applied | same cent | the same print triggers both stop→market orders; both fill; `remaining → 0`, trade closes. Not broker-guaranteed atomic (a halt between two fills), but the gap is milliseconds against a 5-minute poll, and a poll landing in it would find Step 1 facing an already-filled main stop (`_reduce_stop_via_cancel_new` → `stop_filled` → `partial_exit_aborted`) | **no** | 4 of 4 OCO events; 6 of 6 resting-mode partials ended with the main at breakeven (5 via 2b, 1 via the arm) |
| B | after ≥1 daily trail raise (main ABOVE the leg) | main higher | the MAIN fills first → `_process_stop_fill` decrements, trade stays open with `remaining = slice qty`, `partial_taken` FALSE; the OCO still rests → the poll's dedup aborts every 5 min (`partial_exit_aborted dedup_pending_exit` + `profit_trigger_failed` rows; the Telegram stays deduped); then the leg or the limit takes the last share(s) → `remaining 0` | **no** (the slice is the LAST out) | 0 (every OCO so far filled 3 s – 3 m 43 s after placement, before any trail bump) |
| C | **Step 2b rejected / deferred / unverifiable with no prior arm** (DB stop < entry) | **leg ABOVE main** (leg at entry, main at the old stop) | **yes** — a pullback to entry fills the 1-share leg; the main (−2R) survives | **YES — the re-fire** (§2) | **0 ever**: `partial_exit_breakeven_deferred` 0, `_unverified` 0, `_unverifiable` 0, `_oco_fallback` 0, `_reprotect_failed` 0 (Q7 lists no such rows) |
| D | `breakeven_at_broker` OFF while resting + OCO stay on, **AND the +3R arm not applied** (DB stop < entry at +8R) | leg above main (2b skipped; the arm is gated on `mi_strategies.breakeven_arm_r` + a broker read and never consults this toggle — `_breakeven_at_broker_enabled` is called only at :3499 and :4179 — so on the normal +3R → +8R timeline the arm has already put the DB stop at `round(entry,2)` and both stops still coincide) | yes | **YES**, with the same precondition shape as C (a gap from < +3R past +8R inside one poll, or an arm skip) | not today's config (on for live AND paper) |
| E | `stop_order_id` NULL at +8R (post-remediation naked) | Step 1 and 2b both skipped (`if old_stop_id and …`); OCO at entry; the main shares re-protected at the DB price | yes | YES | 0 (`breakeven_arm_skipped` "no_stop_pointer" 0; no naked +8R trade on record) |
| F | resting ON, OCO OFF (plain limit) | no leg at all | n/a | no (this is the ETON hole, a different defect) | not today's config |
| G | resting OFF (market sell) | no leg | n/a | no — `partial_taken` flips TRUE on the fill within seconds | not today's config |
| H | origin size | — | — | 2-share origin: 1 left → `profit_take_shares(1) = 0` → **cannot** re-fire. **3-share origin: re-fire reachable ONLY since 10-10** (`2 → 1`; before: `2 → 0`). 4+ shares: pre-existing (`4 // 3 = 1`). | — |

**So:** the slice's stop filling alone requires C, D or E. Under today's toggles that means a Step-2b
breakeven failure that has not occurred in 6 of 6 resting-mode partials (or a NULL pointer at +8R, 0 on
record). The 08-14 operator-signed design states the healthy expectation exactly: *"OCO stop fills … The 2/3's
own stop sits at the same breakeven price and fires on the same move — the whole position scratches, which is
the intent of breakeven."* The data agrees.

---

## 2. If it fires (configuration C/D/E): the exact sequence, lines, and what the rows look like

Take a 3-share MAGNA53 position (entry E, target T = E + 8R, original stop S < E), Step 2b rejected.

| step | event | code | `mi_live_trades` after | `mi_audit_log` rows |
|---|---|---|---|---|
| 1 | poll fires, 1 of 3 | `scan_profit_triggers` :9749 → `execute_partial_exit` | unchanged (`remaining 3`, `partial_taken f`) | `partial_exit_started` "sell 1 of 3 (new_remaining=2)" |
| 2 | main stop reduced to 2 at S | Step 1 :3460+ | — | (`partial_exit_stop_replaced`-class rows) |
| 3 | OCO: limit 1 @ T, stop 1 @ E | :4025; leg row `purpose='stop_loss'` qty 1 :4073 | — | `partial_exit_sell_placed` "OCO resting for 1: limit @ T / stop @ E" (`order_class: oco`, `oco_stop_price: E`) |
| 4 | 2b rejected → main stays at S | :4181-4236 | — | **`partial_exit_breakeven_deferred`** (the precondition; Telegram "breakeven move rejected") + `profit_trigger_fired` (shares 1) |
| 5 | price pulls back to E: the LEG fills (1 sh); the broker cancels the parent | WS fill → `trade_stream._handle_fill` :788-823 (`purpose='stop_loss'`) → `finalize_stop_fill` :6166 / `_finalize_stop_fill_locked` :6179 | `remaining 3 → 2`; **`partial_taken` untouched (FALSE)**; `exits += {reason: stop_hit, shares 1, order_id = leg id}`; `stop_order_id` kept (CASE: the leg ≠ pointer) | `stop_exit_committed` "stopped out 1 @E … — 2 sh remain, trade stays OPEN"; Telegram "❌ Stopped out … 2 sh remain — position stays open (resting exit still working)" — **wrong in this case: no resting exit remains** |
| 6 | parent cancel event | `_handle_cancel_or_reject` §3 :2342 marks the parent row `canceled`/`cancelled` (both terminal) → `_is_oco_parent` :2383 → `_handle_oco_parent_cancel` :1315 → leg `filled` → **world A returns** (:1353-1370): no restore, **no `partial_taken` write** | — | `oco_parent_cancelled_sibling_filled` |
| 7 | next poll (≤ 5 min) | selection :9699-9707 passes again (`partial_taken f`, `remaining 2`, `MAX(high) ≥ T` is sticky); `profit_take_shares(2) = 1` (10-10); dedup :3360 finds no pending exit (parent terminal) | — | **`partial_exit_started` "sell 1 of 2 (new_remaining=1)"** — `full_remaining 2`, the SAME signature as a genuine 2-share event |
| 8 | second OCO: limit 1 @ T, stop 1 @ max(S, E) = E; main reduced to 1 | as 2-4 | `remaining` still 2 until a fill | second `partial_exit_sell_placed` (oco), second `profit_trigger_fired` (the Telegram trigger line is suppressed by `_profit_trigger_already_announced`, but Step 3 still sends "📋 Profit-take resting (OCO): … Limit sell 1 sh @ T" — it acts quietly, not silently) |
| 9 | second limit fills | `finalize_partial_exit` :4778-4795 | `remaining 1`, `partial_taken TRUE`, `exits += partial_profit 1` | `partial_exit_committed` "sold 1 … remaining 1" |

**What a real occurrence looks like in the tables (the positive observable for any verify):** one `trade_id`
with (a) an `oco_parent_cancelled_sibling_filled` row FOLLOWED by a `partial_exit_started` row; or (b) a
`stop_exit_committed … remain` row (`exits[]` carries a `stop_hit` whose `order_id` is an OCO leg) preceding a
SECOND `partial_exit_sell_placed`; or (c) two `mi_live_orders` rows `purpose='partial_exit'` for one trade
with `order_class = 'oco'`. **Today each of (a), (b), (c) reads n = 0.**

**Discriminator for the #698 verify:** a `partial_exit_started … sell 1 of 2` row on a trade whose
`entry_shares ≥ 3` and whose `exits[]` already holds a `stop_hit` is this re-fire, NOT the new 2-share branch.
A genuine 2-share event has `entry_shares = 2` and an empty `exits[]` at that moment.

---

## 3. Has it ever happened? — n on everything (prod, 2026-10-10)

| question | n | detail |
|---|---|---|
| OCO partials ever placed (`purpose='partial_exit'`, `order_class='oco'`) | **4** | AMLX 372 (5 sh, 08-18), MRNA 374 (1 sh, 08-19), CRWD 383 (1 sh, 08-27), KOD 404 (1 sh, 09-28) — all live MAGNA53 (Q4/Q5) |
| …whose LIMIT filled | 4 of 4 | 3 m 43 s / 3 s / 75 s / 3 s after placement |
| …whose STOP LEG filled | **0 of 4** | all 4 legs `cancelled` by the limit fill (Q5) |
| `oco_parent_cancelled_sibling_filled` rows (world A — the re-fire's precondition) | **0 ever** | Q7 |
| `oco_parent_cancelled_unfilled` rows (world B) | 2 | KO 407 (10-05) and KO 417 (10-09), PAPER, leg status `canceled` (both legs dead — not a fill); both are the #687 Day A/B rehearsal harness (`scripts/probes/_687/expiry_path_test.py`; rows deleted by its cleanup — `q2_followup.out` F1: 0 trade rows). Not the shape |
| Step-2b breakeven failures (`partial_exit_breakeven_deferred` / `_unverified` / `_unverifiable`) | **0 / 0 / 0 ever** | `partial_exit_breakeven_armed` 5 (ABCL, ETON, AMLX, MRNA, CRWD); KOD arm-first (Q7, Q10) |
| resting-mode partials since 08-10 that ended with the main stop at breakeven | **6 of 6** | 2 plain-limit (ABCL, ETON — pre-OCO flip) + 4 OCO |
| partial-quantity STOP fills ever (`purpose='stop_loss'`, filled, qty < entry_shares) | 15 | every one is the MAIN stop (qty = entry − slice) filling AFTER the slice sold, closing the trade (Q6); 0 are OCO legs |
| `stop_exit_committed … remain` rows (a stop fill that left shares open) | 0 | Q8 |
| trades that ever took a partial | 19 | Q9 |
| …with ≥ 2 `partial_profit` entries in `exits[]` | **0 of 19** | max 1 each (Q9) |
| trades with > 1 `partial_exit_sell_placed` | 2 | GOOGL 56 and TEAM 57 — PAPER, 2026-05-05/06, market mode, 3 months before the OCO existed. The first order of each (`82ebdc29`, `ce35d7a8`) was an after-hours queued market sell that the broker later shows `canceled`, never filled; the second (placed 02:33 UTC, after the #180 deferred-commit fix) filled once. Shares reconcile exactly: GOOGL 17 + 34 = 51; TEAM (attempt 2) 76 + 153 = 229 (Q9, F5, F6). **Actual double sales: 0** |
| `profit_trigger_fired` rows ever | 8 | 8 distinct trades (PLTR, FIGS, ABCL, ETON, AMLX, MRNA, CRWD, KOD), 1 each (Q3) |
| open positions exposed right now | **0 of 3** | KOD 404: `partial_taken TRUE` (not selectable), main stop $88.25 trailed far above entry $63.15; PENG 414: 10 sh, max high $78.75 < +8R $124.29; HUM 419: 1 sh, $456.50 < $593.68 (Q11, Q12) |

**Why the precondition is rare by construction:** the trigger is bar-high-based and the limit rests AT the
target, so the slice fills within seconds–minutes (4 of 4). A slice has never rested long enough to be scratched.

**#698's contribution, bounded:** the re-fire from a 4+-share origin pre-dates 10-10; a 2-share origin cannot
re-fire; the 10-10 sizer adds exactly the 3-share origin (3 → 1 sold → scratch → 2 left → `profit_take_shares(2)
= 1`). Live MAGNA53 fills holding exactly 3 shares: CRWD 383 (closed) — its OCO filled in 75 s.

---

## 4. If real — the minimal fix, its sites, the tests, and what kind of change it is

### 4a. Minimal fix (NOT built here)

Treat **the slice exiting at its OWN stop as the partial having been taken**: write `partial_taken = TRUE`
when a `purpose='partial_exit'` OCO's sibling stop leg fills. The poll's selection then excludes the trade for
good, exactly as a limit fill does today.

| site | change | why |
|---|---|---|
| `order_manager._finalize_stop_fill_locked` (:6179; the `new_remaining > 0` UPDATE ~:6261-6270) | add `partial_taken = TRUE` when `order_id` is the leg of a `partial_exit` OCO for this trade. Discriminator: the id appears in `raw_response->'legs'` of a `mi_live_orders` row with `purpose='partial_exit' AND raw_response->>'order_class'='oco' AND trade_id = $1` (works for every historical row); or tag the leg row at placement (:4073-4090) with `exit_reason='partial_oco_stop'` and pass it from `_handle_fill`'s `RETURNING exit_reason` (:788-796). `order_id != stop_order_id` alone is NOT a discriminator — the TEAM 5/06 / ARM 5/07 stale-pointer class also matches it | the leg's fill is the one authoritative fact; `_process_stop_fill` (pointer match) is never reached for a leg |
| `trade_stream._handle_oco_parent_cancel` world A (:1353-1370) | the same idempotent `partial_taken = TRUE` write | Alpaca's parent-cancel and leg-fill events are not ordered; a poll between them would still re-fire if only the finalizer writes. A dropped leg-fill event + a reconciler-marked `canceled` parent reaches only this path |
| `scripts/audit_column_writes.py:190` `ALLOWED_WRITERS["partial_taken"]` (today: `{"order_manager._finalize_partial_exit_locked"}` ONLY) and `scripts/preflight_db_updates.py` (:87, :116) | register each new writer by name | Gate 5 G — an unregistered trade-state writer fails the deploy preflight (#500 cost a deploy on exactly this) |
| `docs/setups/exit_discipline.md` 2026-08-15 paragraph "Documented interaction (emergent …) the trigger can RE-FIRE" and `docs/setups/magna53_ep.md` Known limitation 7 | rewrite in the same commit — the 08-15 text says the opposite of the fix | stale SSoT is worse than none |
| `scripts/live_rules.py` | optional fingerprint on the new write | a silent revert reads ABSENT at OPEN |

**Not minimal — "set `partial_taken` on placement":** it also stops the re-arm after a world-B death (the whole
OCO cancelled unfilled → `_ensure_stop_coverage` re-protects → today the poll re-arms the slice at the target).
That is a second behaviour the 08-15 entry calls designed; two decisions, not one.

**Left alone on purpose:** `breakeven_active`. In configuration C the main stop is NOT at breakeven; setting
the flag would make the 16:45 pass raise it to entry (the `deferred` branch already relies on the limit fill
doing this). Whether the scratch should ALSO force breakeven on the survivors is a third question.

### 4b. Tests that FAIL on today's code (state-writer level; a poll-level test cannot discriminate —
`tests/test_545_per_strategy_exit_levels.py::test_poll_sells_one_of_two_shares_at_the_8r_target` asserts the
second sale's sizing as the FEATURE)

1. `test_oco_leg_stop_fill_marks_the_partial_taken` — model on
   `tests/test_partial_carveout_accounting_566.py::test_oco_leg_stop_fill_decrements_without_matching_the_tracked_pointer`
   (`_wire_finalizer`, `_trade_row(remaining=3)`), with the trade's `partial_exit` OCO parent row carrying
   `legs: [{id: "oco_leg_1"}]`: `await om.finalize_stop_fill(731, 1, 55.20, "oco_leg_1")` → the
   `UPDATE mi_live_trades` SQL must contain `partial_taken = TRUE` and `remaining_shares = 2`. **Today's SQL
   (:6261-6270) carries no `partial_taken` → FAILS.**
2. `test_main_partial_qty_stop_fill_does_not_mark_the_partial_taken` — the regression guard for the
   discriminator: `finalize_stop_fill(731, 12, 55.20, "stop23")` (the pointer) → no `partial_taken` in the SQL.
   Passes today; pins that a MAIN-stop fill is not a partial.
3. `test_oco_parent_cancel_world_a_marks_the_partial_taken` — extend
   `tests/test_oco_cancel_handler_566.py::test_oco_parent_cancel_with_filled_leg_never_touches_the_good_stop`:
   with the leg `filled`, assert one `UPDATE mi_live_trades … partial_taken = TRUE`. **Today world A writes
   nothing to the trade row → FAILS.**
4. `test_the_new_partial_taken_writers_are_registered` — extend
   `tests/test_545_per_strategy_exit_levels.py::test_the_arm_writer_is_registered_in_both_trade_state_gates`
   for the new writer names. **FAILS today** (only `_finalize_partial_exit_locked` is registered).

### 4c. Bug fix or rule change? — a RULE CHANGE by the SSoT's own words; the rule text conflicts, quoted

- **The signed 10-10 rule (size only):** *"when a third rounds to zero but 2 or more shares are held → sell 1
  share; when 1 share is held → sell nothing; … everything else … is unchanged"* (`magna53_ep.md`
  2026-10-10, his *"go with rec"*). It says nothing about HOW MANY times.
- **One partial per position — the mechanism's own words:** `scan_profit_triggers` docstring (:9656)
  *"take 1/3 when the position **first** trades at entry + PROFIT_TRIGGER_R x risk"*; `exit_discipline.md`
  2026-08-04 *"`partial_taken` only flips TRUE on a SUCCESSFUL partial"*; `EP_TRADING_RULES.md` §B5 one 1/3
  then *"move stop floor to breakeven"*; and the **08-14 operator-signed OCO design**: *"OCO stop fills …
  The 2/3's own stop sits at the same breakeven price and fires on the same move — the whole position
  scratches, which is the intent of breakeven"* — the signed design never contemplates the slice scratching
  alone, let alone re-arming.
- **Re-fire is designed — the recorded position:** `exit_discipline.md` 2026-08-15 (#566 BUILD entry,
  agent-written; NOT in the 08-14 signed proposal): *"the trigger can RE-FIRE after the OCO stop scratches the
  third … Risk never increases … re-arming a resting sell at the target after a scratch is aligned with the
  operator's keep-the-limit-resting intent; **suppressing it would itself be a trigger-discipline change** …
  Recorded so the first live occurrence reads as designed-emergent, not as a bug."* The `profit_take_oco`
  flip (08-17) was his, via the flip SQL; whether he read that paragraph is not recorded. `magna53_ep.md`
  Known limitation 7 (10-10): *"Changing it … is a separate sell-discipline call for him — NOT made here."*
- **Verdict:** the text is ambiguous and the two SSoT files point opposite ways on this exact question.
  Enforcing one partial per position would REVERSE the 08-15 recorded position → CHANGE_PROCESS step 3
  applies: the prior reasoning ("a re-arm after a scratch, risk never increases") was **wrong, not just
  incomplete** — on the healthy path the slice cannot scratch alone (both stops share a cent; the signed
  08-14 design says the whole position scratches), so the re-fire exists ONLY when breakeven protection
  already failed (C/D/E); a second sale there is not a re-arm of the signed shape but a new sale on a
  position whose stop was left at −2R. Either way it is **his ruling**, not a defect I may close.
- **The fork for him:** (a) one partial per POSITION — set `partial_taken` when the slice scratches (§4a);
  (b) keep as recorded — one partial per SLICE, re-arm at the target after a scratch.
  **Rec (one line): (a)** — it matches the signed 08-14 expectation and the trigger's "first trades" wording,
  and nothing observable changes today (n = 0, both stops on the same cent).

---

## What this does not answer

- **Broker atomicity of two same-price sell stops** on one position: never observed (0 leg fills ever); a
  trading halt between the two market fills is the residual in configuration A and is not measurable from our
  tables.
- **Multi-share OCO partial fills** (does Alpaca down-adjust the held leg?) — unprobed since the 08-14 design
  said so; all 4 real legs were cancelled whole.
- **Whether the operator read the 08-15 "designed-emergent" paragraph before flipping `profit_take_oco` on
  08-17** — not recorded anywhere; the 08-23 record-of-state entry says only that the flips were his.
- **How often Step 2b would fail at +8R specifically** — 6 of 6 resting-mode successes, but 5 of them were +2R-era
  (08-11 → 08-27) and only KOD ran at +8R (2b skipped, arm-first). At +8R the main stop sits far below the
  tape, so a "price at/above market" rejection is less likely than at +2R, but n = 1.
- **The ordering of Alpaca's leg-fill and parent-cancel WS events** — decides which write site closes the gap
  first; only observable on a real occurrence.
- **The paper lane** (`magna53_smallcap`): 0 fills, 0 partials; same code, same toggles.
- **The misleading Telegram in step 5 of §2** ("resting exit still working" when none remains) — a message
  defect that only shows in configuration C/D/E; not scoped here.
- **Step 1 re-creates the main stop at the DB `stop_price` with no broker floor** (`_replace_stop_leg_via_cancel_new`
  "places the caller's price" — the #600 entry; no `_apply_reprotect_floor` call site there). In the arm's
  UNVERIFIED branch (pointer persisted, price withheld) that would cancel a broker stop at entry and re-create it
  at the original until Step 2b restores it. A separate loosening question, named not analysed;
  `breakeven_arm_unverified` n = 0.
- **Linking this finding from its owner** (`magna53_ep.md` KL7) — not done (read-only run; the router test
  does not require it for this filename); add the pointer in the commit that carries his ruling.
