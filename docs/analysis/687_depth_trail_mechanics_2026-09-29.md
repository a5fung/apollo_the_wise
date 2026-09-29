# #687 part 3 — Can the depth rule be executed at Alpaca? The order mechanics, and what the timing costs (2026-09-29)

**DESIGN AND MEASUREMENT ONLY. $0: no new market data, no LLM calls; one read-only prod capture (`pull_mech.sql`, READ ONLY
transaction, rolled back, 2026-09-29 15:58:49Z). Nothing live, in PLAN.md or in prod was touched; nothing is committed.
Switching the live trail is CHANGE_PROCESS and his sign-off (THE LINE).** Probe: `scripts/probes/_687/mechanics.py` (its
docstring is the pre-registration, plus a stated after-the-first-run amendment), output `mechanics_out.txt` (two runs,
byte-identical after the timestamp line). "R" = money-R (profit ÷ dollars at risk; 1 money-R = 2 ORB-R), as in #685/#687.

## ⚠ CHECKED 2026-09-29 — the decision logic and every number reproduce (the check's own walker, 0 mismatches); the sale-vehicle recommendation and the change list are corrected here (this section wins)

- **Survives:** a close-auction order cannot be sent after 15:50 ET, and deciding at 15:45 on the 15:45 price kills
  the edge (rebuilt list: +26.9R → +2.9R vs today's stop, p 0.89 — the 15:45 check sells BE and FCEL on days they close
  0.2–0.8% back above the line). Deciding on the real close and selling next morning keeps it: +51.6R vs today on the
  rebuilt list (p 0.087), −2.5R on the 79 real EPs (p 0.25, noise); the lead survives a symmetric slippage stress
  (+54 to +60R rebuilt).
- **Corrected — the sale vehicle:** a plain queued market sell's fill vs the official open is NOT free. The two recorded
  paper next-open sales filled 0.44% (IBM) and 1.41% (BW) below the official open; next-open beats the 15:45 close
  auction only below ~0.5% slippage. **Recommended instead: a market-on-open auction order ('opg', submitted from 19:00 ET
  after the true-close decision)** — it fills IN the opening auction, the price the replay assumed;
  `place_market_on_open_sell` already exists (/timestop uses it). Needs the expiry-restore fallback (unfilled opg orders
  are cancelled after the open).
- **EXISTING live bugs in today's close-below-line exit (16:45 `execute_full_exit`) — they apply to TODAY's rule, not only
  the switch; the path has never fired live on a MAGNA53 trail:**
  (a) silently skipped when a +8R profit-take limit is still resting (`order_manager.py:4794`, INFO log, caller ignores
  the False); (b) `finalize_full_exit` marks the trade closed with 0 shares even when the profit-take third is still held
  at the broker (4940-4949); (c) the stop-restore after a failed exit asks for `remaining_shares`, which includes the
  OCO-held third → rejected → "UNPROTECTED" page while the 2/3 is actually naked (4816, `trade_stream.py:2276`); (d)
  `close_position(qty=…)` passes a dict and raises before any HTTP call (`alpaca_client.py:800`); (e) the stop-ack
  watchdog takes no lock and can re-place a stop between cancel and sell (M1); (f) false "position unprotected" pages at
  17:00 / 19:00 / 21:10 after every successful sale (coverage check ignores a queued sell; live only, cannot be
  rehearsed on paper).
- **Rehearsal correction:** paper cannot exercise the coverage-detector fix; replace the 09:00/09:15 assertion with a
  unit test of `check_position_coverage` with a pending full exit.
- **His decisions (surfaced in §10 plus two the check added):** sale vehicle (rec: market-on-open auction); open positions
  such as VICR (its stop sits on today's line; `update_stop` will not lower it — rec: new rule for NEW trades only);
  the resting profit-take third on a close-below sale (default: leave its own target and breakeven stop); next-open
  losses count toward the 2% daily loss limit and re-arm the circuit breaker about 4× as often; and the alarm-semantics
  changes to the #527 coverage detector and #649 slots (they change alarms he ruled on).

## Method and population

Code read at `origin/main` 2026-09-29 (file:line cited throughout); Alpaca rules from the official docs; the timing-gap re-score runs on the captured bars of the two replay populations — the paired trades of the rebuilt EP-like list (n = 1,505; 2024-01 → 2026-04, `687_depth_trail_backfill_2026-09-29.md`) and the real-EP trades of #685 (n = 79; live-source alerts 05-01 → 09-11) — plus the recorded paper next-open sales (BW, IBM) from `mi_live_orders`.

## 1. The answer first

- **Yes, with changes.** Every depth-rule *decision* can be executed exactly as the replay makes it; the *sale* on a close
  below the line cannot be at the close. It goes out at the next morning's open, as today's sales below the line already do.
- **Recommended design, plain words:** the stop rests one normal day's range under the line and is moved up each evening.
  At 16:45 ET, on the real close, if the stock closed below the line, cancel the stop and send a sell that executes at the
  next open. Do **not** try to sell at the close.
- **Why not at the close:** Alpaca rejects close-auction orders sent after 15:50 ET. Selling at the close therefore means
  deciding at ~15:45 on a price that is not the close. On the rebuilt list that 15:45 decision sold the two big winners
  that make up the depth rule's whole advantage (BE, FCEL; both closed 0.2–0.8% back above the line). The depth rule's lead
  over today's stop falls from **+29.5R to +2.9R** (p 0.89). The first number is replay vs replay, the second is live timing
  vs live timing; on the same live baseline the fall is +26.9R → +2.9R.
- **What the next-open sale costs:** nothing measurable. It *added* +24.7R over 385 sales on the rebuilt list (the stocks
  tended to open above where they closed) and cost −0.6R over 21 sales on the 79 real EPs.
- **Must fix before any live flip (today's code, found here):**
  - The sale is **silently skipped** when a +8R profit-take is still resting (`execute_full_exit` dedup, order_manager.py:4794).
  - It runs **without the per-trade lock**, so a re-protect can race it.
  - It sends a **false "position unprotected" page** after every successful sale (from reading the code; the paper
    rehearsal confirms).
  - The stop is **raise-only**, so switching VICR (live, 1 share, stop on the line at $239.38) would need a one-off
    *lowering* — his decision.
- **Does not change #687:** under live timing the depth rule vs today's stop reads +51.6R (p 0.087) on the rebuilt list
  and −2.5R (p 0.25) on the 79 real EPs — still not a clear win on the EPs we trade.

## 2. How today's exit is actually executed

**Every broker order a MAGNA53 position carries** (MAGNA53 = `magna53`, live account):

| stage | order at the broker | type / lifetime | when | code |
|---|---|---|---|---|
| entry | stop-limit BUY at the ORB high (limit 0.5% / $0.02 above), OTO with a SELL stop leg at entry − 2 ORB-R; or, if price is already above, a marketable limit + the same stop | DAY (leg dies 16:00) | submit 09:31; unfilled → cancelled 10:00 | order_manager.py:853-872 → alpaca_client.py:326-353, 1185-1213; 10:00 `orb_window_cleanup` scheduler.py:7269-7271 |
| hard stop, day 0 | the OTO stop leg | DAY | 09:31 fill → 16:00 | as above |
| breakeven at +3 ORB-R | price-only REPLACE of the full-position stop to entry (no cancel) | same order, new id | 5-minute poll 09:30–15:55 on the in-hold minute HIGH | scheduler.py:7427-7432 → `scan_breakeven_arms` order_manager.py:8337 → replace at :8526 |
| +8 ORB-R profit-take (1/3) | Step 1: reduce the stop to 2/3 (qty replace; for an OTO leg, verified cancel → new) and verify it live; Step 2: ONE OCO sell of the 1/3 — GTC LIMIT at the +8R target + GTC STOP at max(stop, entry); Step 3: move the 2/3 stop to entry by price-only replace | OCO = GTC | same 5-minute poll | `scan_profit_triggers` :8072 → `execute_partial_exit` :3071 (Step 1 :3334-3473, 1b :3640, Step 2 OCO :3899 → alpaca_client.py:535-605, Step 3 :4059); toggles `profit_take_resting_limit`, `profit_take_oco` ON (exit_discipline.md 2026-08-23) |
| overnight stop | GTC SELL STOP at the DB `stop_price`, placed if no stop is active | GTC | 16:20 (after the day-0 leg expired) | `post_close_stop_refresh` live_tracker.py:1127 / scheduler.py:7235-7237; backstop 09:35 `morning_stop_refresh` :7186-7188 |
| trail move | line = max(SMA10, SMA20) incl. today's close; stop = max(hard, line, entry if breakeven) — if > DB stop + $0.01: read broker stop (raise-only), CANCEL old, PLACE new GTC stop (one retry after 3 s) | GTC | 16:45 | scheduler.py:8009-8011 → live_tracker.py:766, :913-918 → exit_logic.py:341, :397-403 → `update_stop` order_manager.py:2130 (floor :2267, cancel :2306, place :2322, retry :2361) |
| detectors | stop-ACK watchdog (every 30 s), coverage detector (live only, every 15 min 09:00–15:45), sync (16:05, 21:00) | — | — | scheduler.py:7508-7513, :7199-7201, :7314-7316, :7354 |

- The 15:45 `partial_exit_scan` stands down while `PROFIT_TRIGGER_R` is set (constants.py:333; live_tracker.py:1077).
- 10:00 and 16:05 cleanups cancel **entry** orders only (`WHERE t.status = 'order_placed'`, order_manager.py:5216).

**Today, when the close is below the line:**

- **16:45 job:** `apply_daily_exit_step` returns `sma_stopped` (exit_logic.py:418) → `execute_full_exit(trade, "sma_trail_stop")`
  (live_tracker.py:899-900).
- **`execute_full_exit`** (order_manager.py:4773):
  - skips if any partial/full exit order is pending (:4794);
  - cancels the stop (:4818) and waits up to ~5 s for `qty_available` to cover the shares (:4821, #646);
  - calls `close_position`, which sends a **market** order (:4824).
- **Fill:** after 16:00 Alpaca queues that order for the next session, so it fills the **next morning**. The only two such
  sales on record filled 3–7 minutes after the open, not at the opening print: BW (trade 119, paper) 09:37 ET 2026-05-27;
  IBM (trade 167, paper) 09:33 ET 2026-06-10 (`pull_mech_out.txt`).
  - The capture has no submit/release timestamps, so whether the lag is Alpaca's release or our side is not recoverable.
  - Both were paper, whose fills do not model the opening auction.
  - The Day-B rehearsal step (section 8) is what settles it.
- **On rejection:** the stop is restored at its old price, `full_exit_rejected` audit row, page (:4845, #646). The one live
  attempt (OKTA 2026-09-11) was rejected before #646 (`held_for_orders 2`).

## 3. What Alpaca can do

| question | Alpaca, verbatim | source |
|---|---|---|
| market-on-close / limit-on-close (`cls`) | "CLS orders submitted after 3:50pm but before 7:00pm ET will be rejected. CLS orders submitted after 7:00pm will be queued and routed to the following day's closing auction." · "eligible to execute only in the market closing auction." · "Any unfilled orders after the close will be cancelled." | [Orders at Alpaca → Time in Force](https://docs.alpaca.markets/docs/orders-at-alpaca) |
| market-on-open (`opg`) | "OPG orders submitted after 9:28am but before 7:00pm ET will be rejected. OPG orders submitted after 7:00pm will be queued and routed to the following day's opening auction." (our `place_market_on_open_sell` docstring says 9:25, alpaca_client.py:428 — harmless, stricter) | same |
| a market order after 16:00 | "Orders not eligible for extended hours submitted after 4:00pm ET will be queued up for release the next trading day." · (day TIF) "If submitted after the close, it is queued and submitted the following trading day." | same |
| extended hours | "Only limit orders with `time_in_force` set to `day` or `gtc` orders are accepted as extended hours eligible." · sessions: after-hours 4:00–8:00pm, pre-market 4:00–9:30am, overnight 8:00pm–4:00am · bracket: "Extended hours are not supported." · day orders: "only valid during Regular Trading Hours (9:30am - 4:00pm ET)." | same |
| stop orders | "Once the order is elected, the stop order becomes a market order." · "Sell stop orders are not converted into stop limit orders." · no fill-price guarantee. A stop cannot be an extended-hours order, so it can only act 09:30–16:00. | same |
| replace vs cancel | `PATCH /v2/orders/{id}` returns a new order id; "A success return code from a replaced order does NOT guarantee the existing open order has been replaced. If the existing open order is filled before the replacing (new) order reaches the execution venue, the replacing (new) order is rejected." · "Order cannot be replaced when the status is `accepted`, `pending_new`, `pending_cancel` or `pending_replace`." · `pending_replace`: "The order will reject cancel request while in this state." | [Replace Order](https://docs.alpaca.markets/reference/patchorderbyorderid-1); lifecycle table in Orders at Alpaca |
| replace on our order types | OCO: "order replacement is supported to update limit_price and stop_price." OTO: "order replacement is not supported yet." Our paper probe found a **price-only** replace of the OTO stop leg accepted and a **qty** replace rejected (42210000) — the breakeven arm relies on the first (order_manager.py:8245-8256 comment; `_508_oto_leg_probe.py`). | Orders at Alpaca → OCO / OTO |
| held_for_orders | position `qty_available`: "Total number of shares available minus open orders". "When you submit a sell order (e.g., a Limit Sell or Stop Loss), the shares tied to that order are reserved until the order is filled or canceled." · "wait for confirmation that the open orders are actually canceled before sending the close request." (= the OKTA failure) | [Get Open Position](https://docs.alpaca.markets/reference/getopenposition-1); [Common API errors](https://alpaca.markets/learn/how-to-fix-common-trading-api-errors-at-alpaca) |
| OCO / OTO constraints | OCO: "currently only exit order is supported", the type "must always be 'limit'", TIF day/gtc. So no OCO can carry a close-auction leg, and a stop and a MOC cannot both hold the same shares: selling at the close forces cancel-stop-then-MOC. | Orders at Alpaca → OCO |
| close position | `DELETE /v2/positions/{symbol}` "Closes (liquidates) the account's open position", `qty` / `percentage` optional; the doc says nothing about cancelling open orders (it does not — OKTA). | [Close a Position](https://docs.alpaca.markets/reference/deleteopenposition-1) |
| paper | "does not simulate … Price slippage due to latency · Order queue position · Price improvement"; random partial fills 10% of the time. So paper rehearses order acceptance, share reservation and cutoffs, not auction prices. | [Paper Trading](https://docs.alpaca.markets/docs/paper-trading) |
| GTC ageing | GTC orders are cancelled 90 days after creation, "at 4:15 pm ET" on `expires_at`; the 16:20 refresh would re-place. | Orders at Alpaca |

## 4. The depth rule's order flow

**Recommended — decide on the real close, sell at the next open (reuses today's evening path):**

1. **Entry, day 0, breakeven, +8R profit-take:** unchanged (section 2).
2. **Resting stop, from day 1:** `depth stop = max(hard stop, entry once breakeven is armed, line × (1 − ADR20%))`, rounded to
   cents.
   - ADR20% = the stock's mean daily range over the 20 sessions before entry. It is recomputable from the prior bars the
     16:45 job already fetches.
   - The 16:45 job raises it through `update_stop`. Its raise-only floor against the broker stop does the ratchet the replay
     does, so no new stored line is needed.
   - The cancel → new swap happens after hours, when no stop can trigger.
3. **Close test, 16:45, on the settled close:** `apply_daily_exit_step`, unchanged — the same verdict the replay computes.
4. **Close below the line:**
   - Take the per-trade lock.
   - Cancel the depth stop and wait for `qty_available` (#646).
   - `close_position(qty = remaining − shares held by a resting OCO)` — a market order Alpaca queues for the next open.
     `close_position` cannot open a short.
   - Write the `full_exit` row and release the lock.
   - On rejection: restore the stop at its price and page (#646).
5. **Next morning 09:30:** the queued sell executes at the open. The fill event runs `finalize_full_exit`. If the order is
   rejected or cancelled at release, the stream handler re-places the stop and pages (trade_stream.py:2247-2290).
6. **Interactions:**
   - **+3R breakeven:** a price-only replace to entry only when the broker stop is below entry — compatible (the depth stop
     is ≥ entry once armed).
   - **+8R profit-take:** the 2/3 stop is the depth stop. The OCO third keeps its own stop at entry and limit at the target
     (#566). On a close-below sale the default here leaves the OCO third alone. It rests only when price fell back under
     the target before the 5-minute poll; KOD, the only live +8R partial, filled at once.
   - **Today's code:** it would skip the whole sale in the OCO case — must-fix.

**Never unprotected — the windows:**

| window | what covers it |
|---|---|
| day 0, 09:31 fill → 16:00 | the OTO stop leg (entry − 2 ORB-R) |
| day 0, 16:00 → 16:20 | nothing — outside regular hours, where no stop can execute anyway |
| 16:20 → next 16:45 | the GTC depth stop; 09:30–16:00 it sells on a touch, a gap below it fills at the open |
| 16:45 stop move | cancel → new, ~1–3 s (+3 s retry), after hours |
| 16:45 → 09:30 after a close-below sale | the queued sell itself: nothing can execute before 09:30; it is released at the open (the two prod sales filled 09:33 / 09:37) — a gapped-through stop would also have filled at the open |
| sale rejected (16:45) or at release (09:30) | stop restored within seconds + page (#646; trade_stream.py:2247); backstops: 30-second stop-ACK watchdog, 15-minute coverage detector, 09:35 refresh |

**Alternative (if he wants a same-day sale) — sell at the close by MOC:**

- **Steps:** 15:46 ET (after the 15:45 coverage pass) → take the lock → the same ladder on the 15:45 price → verdict SELL →
  cancel the depth stop (and any OCO) → wait for release → read the broker position → submit a **market-on-close** sell
  for min(remaining, position) before 15:50 → write the row → release.
- **If rejected before 15:50:** restore the stop, market-sell at once.
- **If unfilled at the close** (no auction, halt): Alpaca cancels it → the stop is restored → the 16:45 job sells at the
  next open (it is also the backstop for days that were above the line at 15:45 but closed below).
- **Uncovered window:** 15:46 → 16:00 with no stop, only the committed MOC. That cost is small (1 day in the rebuilt set).
  The 15:45 *decision* is what costs (section 5).

## 5. What the timing gaps cost

**Method:**

- Same 1,505 rebuilt and 79 real trades, same walker. Only the fill of the close-below sale moves.
- With the close timing the probe reproduces #687's and #685's per-trade R on every trade (0 mismatches).
- The 15:45 decision is `apply_daily_exit_step` on the 15:44 bar's close.
- Days without minute bars: the verdict is exact when the day's range lies wholly on one side of the threshold. It checks
  as identical to the code on every bar day (0 mismatches). Otherwise the day is ambiguous and resolved three ways.
- "Today live" = today's stop with its close-below sales at the next open.
- **The "next open" price is the official daily open.** The two prod sales filled 3–7 minutes later (section 2), so it is
  optimistic by an unmeasured few minutes of movement. The same bias applies to today's stop and the depth rule; it weighs
  ~4× as much on the depth rule (it sells this way ~4× as often).

**Rebuilt 1,505** (ambiguous days resolved as the close; bounds in brackets):

| sale on a close below the line | depth rule total | vs today live | p | ≥3 / ≥8 ORB-R winners | BE · HL · FCEL |
|---|---|---|---|---|---|
| at the close (replay) | +467.10 | +26.92 (vs today's replay +29.46, p 0.33) | — | 231 / 92 | +22.88 · +14.30 · +9.72 |
| next open (today's flow) | +491.79 | **+51.60**; without its top 2 +21.59 | 0.087 | 237 / 97 | +22.88 · +14.97 · +9.37 |
| 15:45 decision, MOC | +443.11 | **+2.92** [−7.88 … +5.23]; without its top 2 −13.11 | 0.889 | 229 / 93 | +4.83 · +13.70 · +0.86 |
| 15:45 decision, market at once | +442.78 | +2.59 | — | 231 / 94 | +4.66 · +13.53 · +0.72 |
| 15:49 decision, MOC (post-hoc) | +442.86 | +2.68 | — | 230 / 91 | — |
| today's stop, live (next open) | +440.18 | — | — | 241 / 89 | +4.67 · +3.17 · +0.70 |

**Real 79 EPs** (no ambiguous days — every day the 15:45 side mattered has minute bars):

| sale on a close below the line | depth rule total | vs today live (−5.68) | p | ≥3 / ≥8 ORB-R | FTK · INFQ |
|---|---|---|---|---|---|
| at the close (replay) | −7.59 | −1.91 (vs today's replay −1.82) | — | 8 / 3 | +5.07 · +2.67 |
| next open | −8.19 | −2.51 | 0.252 | 9 / 2 | same |
| 15:45 decision, MOC | −8.79 | −3.11 | 0.073 | 8 / 1 | same |
| 15:45 decision, market at once | −8.11 | −2.43 | — | 9 / 1 | same |

**Why 15:45 fails:**

- **False sells and misses** (the depth rule's own path, days with bars):
  - rebuilt: 34 false sells (below the line at 15:45, closed back above) and 24 misses (above at 15:45, closed below) on
    532 days; 263 agree to sell, 211 agree to hold;
  - real: 2 false sells and 1 miss on 253 days.
  - Plus, rebuilt only: 298 days without bars on which the 15:45 side is unknown (8 certain sells; 290 ambiguous, of which
    89 closed below).
- **The false sells land on the runners,** by pennies:
  - BE 2025-08-08: 36.50 at 15:44 under a 36.74 line, closed 36.80;
  - FCEL 2026-05-07: 12.16 under 12.18, closed 12.28;
  - AXGN 2024-02-13: closed $0.004 above.
  - The rule's biggest wins were decided by the closing print. No decision minute before the 15:50 cutoff reproduces that
    — 15:49 still sells BE.
- **The next-open sale:** on the depth rule's close-below exits, next open minus close is +24.69R over 385 sales on the
  rebuilt list (median +0.02R, 210 better / 155 worse; positive in both blocks, +8.8R and +15.9R), and −0.60R over 21 on
  the real EPs (7 better / 12 worse).
  - The depth rule sells this way ~4× as often as today's stop (385 vs 94; 21 vs 5).
  - That is why next-open timing lifts it more than it lifts today's stop.
- **Runners:** kept under next-open (BE, HL, FCEL, AXGN all held). Lost under 15:45: BE was sold 2025-08-08 at +4.83R
  instead of +22.88R, FCEL 2026-05-07 at +0.86R instead of +9.72R.
- **The swap window** (the depth stop touched after 15:45 on a sell-verdict day): 1 day in 1,505 trades, 0 in 79.
- **Blocks and outliers** (post-hoc, next-open vs today live):
  - discovery +0.80R, held-out +50.81R;
  - without BE, HL, FCEL +12.92R;
  - real EPs without FTK, INFQ +0.01R.

## 6. Failure modes and safeguards

| failure | handling | alert | status |
|---|---|---|---|
| sale rejected at 16:45 (shares still reserved — OKTA) | wait for release, sell; on reject restore the stop at its price, audit `full_exit_rejected` | "Full exit FAILED … Stop RESTORED" | exists (#646, order_manager.py:4711-4870) |
| cancel acknowledged but not settled | poll `qty_available` 10 × 0.5 s, then sell anyway; reject → row above | same | exists |
| a +8R profit-take still resting (OCO third) | today: whole sale **skipped**, INFO log only, caller ignores the `False` (order_manager.py:4794; live_tracker.py:900) | none | **must fix**: sell the stop-covered shares, page on any skip |
| a re-protect races the sale (OCO-cancel handler or coverage repair re-places a stop between cancel and sell) | `execute_full_exit` takes no per-trade lock; the re-protect paths already try-lock and defer (order_manager.py:5935, trade_stream.py:1304) | — | **must fix**: hold `_trade_advisory_lock` cancel → sell → row |
| stop fills during the swap | at 16:45 impossible (stops act only 09:30–16:00); `close_position` cannot open a short; MOC variant: read the cancel result + broker position, sell ≤ position | — | design |
| queued sell rejected/cancelled at the 09:30 release (halt, broker) | stream handler re-places the stop (reprotect-floored) | "Close order REJECTED … Stop re-placed" | exists (trade_stream.py:2247-2290) |
| partial fill at the open that never completes | rest keeps working; if the day ends unsold, the restore is sized on the pre-sale count → rejected | "STOP RESTORE FAILED" (over-alarm) | should fix: size from the broker position |
| false "unprotected" pages after every successful sale | stop-cancel handler finds no replacement **stop** (trade_stream.py:2102-2106: "no scheduled repair until tomorrow"); coverage detector counts stops only (order_manager.py:6751) → pages at 09:00 / 09:15 | false alarm | should fix (by code reading; the rehearsal confirms): ~4× more often under the depth rule |
| broker outage at 16:45 | cancel fails → stop may still rest; sale raises → restore raises → page says UNPROTECTED (over-alarm); 21:00 sync + 09:00 watchdog reconcile | page | exists |
| jobs overlapping | 10:00 / 16:05 cleanups touch entry orders only; 16:20 refresh precedes 16:45; the 5-minute poll ends 15:55; 09:35 refresh subtracts pending exits (`update_stop` → `get_pending_exit_qty`). MOC variant: run at 15:46 under the lock; the breakeven poll must skip a trade with a pending sale | — | design |
| MOC rejected / unfilled (MOC variant) | before 15:50: restore + market sell now; after: Alpaca cancels → stop restored → 16:45 sells next open | page | new code |
| safeguards | next-open losses land at 09:30, before the 09:31 entries: they count toward the day's 2% loss limit and re-arm the loss-count circuit breaker's 24-h cooldown inside the entry window (the 07-31 FTNT shape) — ~4× as often under the depth rule | — | his to weigh (THE LINE) |

## 7. Code changes needed

**Recommended flow** (~110 lines of code + tests; every broker path reused):

| # | change | file | size |
|---|---|---|---|
| 1 | per-strategy switch; depth stop = max(hard, entry if armed, round(line × (1 − ADR20%), 2)); ADR20% from the prior bars `_load_exit_state` already fetches; the decision call untouched | live_tracker.py:~913-918 + `_load_exit_state`; switch in `mi_strategies` or a runtime toggle | ~40 |
| 2 | `execute_full_exit`: hold the per-trade lock; sell `remaining − pending` via `close_position(qty=…)` instead of skipping on a resting OCO; audit + page every skip | order_manager.py:4773-4880 | ~40 |
| 3 | stop-cancel handler: a pending `full_exit` on the trade = intentional, "closing at the open", not "unprotected" | trade_stream.py:~1668-2110 | ~15 |
| 4 | coverage detector: subtract pending exits from the target | order_manager.py:6751 | ~5 |
| 5 | full-exit expiry restore sized from the broker position | trade_stream.py:2247-2290 | ~10 |
| 6 | SSoT: `exit_discipline.md` + `magna53_ep.md` change log; `scripts/live_rules.py` learns the switch | docs, script | — |

- **Reused unchanged:**
  - #646 cancel → wait → sell → restore (`_await_shares_released`, `_restore_stop_after_failed_exit`);
  - `update_stop`'s raise-only floor;
  - the stream's full-exit reject → restore;
  - the 16:20 / 09:35 refreshes;
  - `get_pending_exit_qty`;
  - `apply_daily_exit_step`.
- **MOC variant adds** (~200 lines):
  - `place_market_on_close_sell` (TIF `cls`, mirrors alpaca_client.py:417);
  - a 15:46 job + decision function (the `run_partial_exits` forming-bar call, live_tracker.py:1077);
  - a position-capped MOC sell;
  - the breakeven poll skipping pending sales;
  - the before/after-15:50 fallbacks.

## 8. Test plan

**Unit tests:**

- **Parity:** the live depth-stop function equals the walker's resting stop on every held day of the 1,505 + 79 (golden
  file from `mechanics.py`).
- **`execute_full_exit` with a resting OCO:** sells `remaining − OCO qty` under the lock and never asks for more than the
  broker position.
- **Stream:** the stop-cancel handler with a pending `full_exit` sends no "unprotected".
- **Detector:** the coverage detector subtracts pending exits.
- **Raise-only:** `update_stop` still refuses a lower price.

**Paper rehearsal:**

- **Setup:** PAPER account, a Tuesday–Thursday, 3 + 3 shares of one liquid large-cap, driven through the real functions on
  paper trade rows (the `_partial_exit_paper_validation.py` / `_548_*` probe pattern).
- **Day A:**
  - 10:00 buy 3 sh, GTC stop 5% below; assert `qty_available` 0.
  - 10:05 run `execute_partial_exit` with the limit far above → OCO third resting, 2/3 stop live; assert every share reserved.
  - 10:10 price-only replace of the 2/3 stop +1%; assert a new id, still covering.
  - 15:51 send a `cls` sell and 16:46 an `opg` sell; assert both **rejected** (the cutoffs).
  - 16:30 send a 1-share sell while the stop holds everything; assert `insufficient qty … held_for_orders` (the OKTA error).
  - 16:45 run the fixed `execute_full_exit`; assert:
    - lock held;
    - stop cancelled and shares free ≤ 5 s;
    - `close_position(qty=2)` accepted;
    - OCO untouched;
    - `full_exit` row written;
    - **no** "unprotected" page.
  - Second position: hold an extra sell so the shares stay reserved → run `execute_full_exit` → assert rejected, stop
    restored at the same price ≤ 5 s, page.
- **Day B:**
  - Assert the coverage detector is silent at 09:00 / 09:15.
  - At 09:30 the sale fills; record fill time and price vs the official open; the row closes; the 09:35 refresh does nothing.
  - Cancel the OCO → assert the third is re-protected (the existing handler); clean up.
- **MOC variant only:** a 15:46 run (cancel → wait → `cls` sell accepted before 15:50 → fills ~16:00). Paper cannot check
  the auction price; the first live MOCs must be checked against the official close.

**Live pre-registration:**

- **EXPECT** (baseline: today ~1 close-below sale a month; depth ~4–5 a month on the 79 real EPs, 21 in 4.5 months):
  - every close-below day → one `full_exit` order by 16:50 ET, released at the next open and filled by 09:40, within 1% of
    the official open (the two prod fills landed 09:33 / 09:37 — the Day-B rehearsal sets the real window before the flip);
  - the evening stop equals a recomputed max(hard, entry if armed, line × (1 − ADR20%)) to the cent and never falls;
  - 0 "unprotected" pages for those positions.
  - **Unintended, watched:** skipped sales; `full_exit_rejected` rows; loss-limit or circuit-breaker blocks at 09:30 caused
    by these sales.
- **WOULD-FAIL-IF:**
  - a day that closed below the line has no `full_exit` order by 16:50, or its sale is rejected;
  - a sale not filled by 09:40 — judged separately: the order was released late (broker) vs released on time but
    filled late (liquidity), from the order's own timestamps;
  - a resting stop ≠ the recomputed depth stop by > $0.01;
  - the coverage detector finds a depth position with no stop and no pending sale during 09:30–16:00.
- **DONE-WHEN:** 3 live close-below sales and 10 evening stop moves check clean, or 30 market days pass with none (then
  re-read).

## 9. What this does not answer

- **Whether the depth rule should replace today's stop.** #687 says it does not clearly beat it; this only prices the
  execution.
- **The rebuilt list's 290 ambiguous days.** They make the 15:45 result a range (−7.9R … +5.2R vs today live). The
  conclusion (the gain collapses) holds across it because BE and FCEL are days with bars.
- **The overnight gain.** It (+24.7R, rebuilt) may be this population's (look-ahead volume rule, no catalyst gate); on real
  EPs it is −0.6R.
- **The fill price of a queued market order.** It is measured against the official open. The two prod sales filled 3–7
  minutes after the open (cause unknown), so the next-open numbers are optimistic by an unmeasured amount; paper cannot
  measure it.
- **The 15:45 variant assumes a real-time 15:45 price.** If the forming daily bar the job reads lags, the decision is
  staler still — which only strengthens the case against it.
- **The replay's profit-take.** It books at the target on the touch, so the "OCO third still resting at a close-below sale"
  case is in no R total. Leaving that third alone is a design default, not measured.
- **Safeguards.** Max positions, loss limit and circuit breaker are not simulated. Their interaction with 09:30 sales is
  stated, not measured.
- **Not exercised:** halts / limit-up-limit-down at the open, and a partial fill that expires unfilled.
- **The false-page findings.** They are from reading the code; the paper rehearsal is what confirms them.

## 10. THE LINE

- **Nothing here is a change.** No live code, PLAN.md or prod state was touched; the one prod read was a rolled-back READ
  ONLY transaction.
- **His decisions (surfaced, not taken):**
  - **Sale timing:** next open (rec) vs 15:45 market-on-close.
  - **Open positions:** keep VICR / KOD on today's stop, or lower VICR's stop from the line to line − 1 ADR. Lowering a
    live stop is his call; `update_stop` refuses it by design.
  - **OCO third:** on a close-below sale, leave its own target + breakeven exit (default here) or sell it too.
  - **Safeguards:** whether the 09:30 sale timing's interaction with the loss limit and circuit breaker matters.
- **A catastrophic stop always rests at the broker.** Under this design it is the depth stop. During market hours the only
  moments without one are a queued sale executing at the open (the sale is the exit) and the seconds before a failed
  sale's stop is restored.
- **Any switch is CHANGE_PROCESS:** SSoT change-log entry, his sign-off on the list above, the paper rehearsal passed,
  then verify-live against the EXPECT / WOULD-FAIL-IF above.
