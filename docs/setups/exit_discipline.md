# Exit discipline — SSoT

**What this file owns:** how an open position is reduced or closed once it is filled — the
profit-take, the breakeven arm, the trail, and the time-stop. It does NOT own entry criteria (see
`magna53_ep.md`, `ninem.md`) or portfolio-level blocks (see `safeguards.md`).

Created 2026-08-01. **⚠ It is NOT true that the exit rule was undocumented — that was my error, twice.**
The operator wrote it down in **`EP_TRADING_RULES.md` §B5** (repo root) on 2026-03-27; I missed it by
searching only `docs/setups/`. What was missing is a file under the CHANGE_PROCESS discipline — with a
change log, a limitations section, and the measured record — which is what this file adds.
`EP_TRADING_RULES.md` remains the methodology statement; this file is the operational SSoT and defers
to it on intent. Read this
file **entirely** before changing any exit behaviour, per `CHANGE_PROCESS.md`.

---

## Current deployed behaviour (as of 2026-08-01)

**Decision cadence: DAILY. This is the single most misunderstood fact about the exit path.**
`exit_logic.py` is *"pure daily-exit-step decision logic"*; `apply_daily_exit_step(state, daily_bar, …)`
consumes **one daily bar**; `live_tracker.py:549` fetches `get_index_history(ticker, today, today)`.
Nothing in the exit path sees intraday price. A rule expressed as "when the trade reaches X" is
therefore evaluated **once, against the close**, not on the touch.

**Jobs:** `run_partial_exits` 3:45 PM ET (partial only, market-hours so the stop-replace settles
same-day — #361) and `update_open_positions_live` 4:45 PM ET (SMA trail + stop update + summary;
passes `skip_partial_decision=True` so the partial cannot double-fire).

**Stop-move invariant (2026-08-10): a protective stop is RAISE-ONLY, enforced against the BROKER,
in `update_stop` itself.** Before cancelling anything, `order_manager.update_stop` reads the live
stop from the broker; a requested price that is not strictly above it is refused (no cancel, no
re-place, `stop_update_aborted` audit row, returns False — the existing stop stays). An unreadable
broker stop refuses the same way — we cannot prove the move is a raise, and leaving protection
unchanged is the safe direction. A TERMINAL old stop (expired/cancelled/filled) or a NULL pointer
has nothing live to floor against, so the re-protect paths (`_stop_refresh` re-placing at the DB
price after a DAY leg expires; post-remediation naked re-protect) are exempt and unchanged. The
floor lives in `update_stop` — the one place that talks to the broker — so every current and
future caller inherits it; callers may still DECIDE against `mi_live_trades.stop_price`, which is
deliberately allowed to UNDERSTATE protection (#548 uncertain branch). Defect story: change log
2026-08-10. Tests: `tests/test_update_stop_raise_only_floor.py`.

### 1. Partial profit — day 3-5
```python
if hold_days >= 3 and not partial_taken and entry_price:
    take_partial = (hold_days <= 4 and bar_close > entry_price) or hold_days >= 5
```
- Day 3-4: take 1/3 **only if the close is above entry**.
- Day ≥5: take 1/3 **unconditionally, even underwater**.

  ⚠ **CORRECTION 2026-08-01: I twice called this undocumented. It is not.** It is the operator's own
  rule, written by him on 2026-03-27 (commit `bbbd442`, "v2 rules") and documented in
  **`EP_TRADING_RULES.md` §B5** at the repo root — which I missed because I searched `docs/setups/`
  only. Verbatim there: *Day 1-2 hold full · Day 3-4 sell 1/3 only if in profit · Day 5 sell 1/3
  regardless · after partial move stop floor to breakeven.* It is Qullamaggie methodology, not an
  accident.

  ⚖ **OPERATOR RULING 2026-08-01: the day-5 unconditional sell is NOT needed.** *"We don't need to
  sell on day 5, especially given we have breakeven stop and have taken profit if it survived 5d
  likely. Not that this is a bad rule per se — it may be a good one for example for biotech which
  tends to run just for days per Pradeep, but we can look into that later not now."*

  **His premise is confirmed empirically, and more strongly than he put it.** Every partial that has
  ever fired — all 10 across both cohorts — fired **while IN PROFIT**, at 1.24% to 23.00% above
  entry, on calendar days 4-7:

  | fire day | tickers | price vs entry at fire |
  |---|---|---|
  | 4 | BW, RCAT | +11.04%, +18.38% |
  | 5 | CRSR, TEAM, GOOGL | +23.00%, +5.07%, +2.83% |
  | 6 | SMCI, FTRE | +1.24%, +2.94% |
  | 7 | IBM, QURE, PURR | +10.75%, +7.76%, +5.60% |

  **So the "regardless" property has never once been exercised.** The day-5 branch has fired 8 times
  and every one of them was already profitable — the branch that makes it unconditional has no
  observed effect in 43 recorded trades. Removing it would have changed nothing that has ever
  happened.

  ▶ **Status: ruled, rides the profit-trigger change** (`508_change_proposal_profit_trigger_2026-08-01.md`,
  which removes the time-based partial entirely). It is not being ripped out separately.

  **What IS undocumented is the interaction**: at day 5 while underwater, taking 1/3 arms breakeven,
  breakeven sits above the current close, so the effective stop (`max(hard_stop, active_sma,
  entry_price)`) exceeds price and the remaining 2/3 closes in the same step. So the two documented
  rules together behave as a **day-5 full exit when the trade is underwater** — a consequence neither
  rule states on its own.
- `hold_days` is **calendar** days from `alert_date`, not trading days — a Friday entry reaches "day
  3" on its second trading day.
- Sizing: 1/3 of remaining, integer shares live. `scale_fraction` overrides the FRACTION only; it
  does not affect the trigger.

### 2. Breakeven — armed by the partial, not independently.

### 3. SMA trail — ⚠ NOT the stock's moving average. It averages OUR HOLDING PERIOD.

**Found 2026-08-08 by the operator**, and this line previously described the symptom as if it
were the design: *"requires ≥10 daily closes, so it cannot act before day 10."* That is true of
the code and false of the rule.

**The rule** (`EP_TRADING_RULES.md` §B4, his own file, Qullamaggie): *"Trail your stop with the
10- or 20-day moving average… Exit on first daily close below the active MA."* A stock's 10-day
MA exists every day, with or without our position.

**The code**: `sum(running_closes[-10:]) / 10`, where `running_closes` starts EMPTY at fill
(`JSONB NOT NULL DEFAULT '[]'`) and gains one entry per day WE held. It is the mean of our
holding period. Verified in prod — **nothing seeds it anywhere**: BW held 15d → 10 closes ·
GOOGL 17d → 11 · FPS 23d → 16 · every live trade → **0**.

**Consequence:** the trail cannot exist until ~10 TRADING days held (~14 calendar). Live max hold
is 2 days, so it is structurally dead there — **0 fires in 17 live trades**. It has fired twice
in the system's history, both paper, both at **exactly 10 closes** — it fired the first day it
was permitted to exist.

**What is NOT wrong:** `max(SMA10, SMA20)` is faithful to §B4 ("use 10-SMA when 10 > 20, else
20-SMA") — max() picks exactly that. Do not "fix" it.

**FIXED 2026-08-08 — operator: *"fix it, it's a bug"*.** `apply_daily_exit_step` takes a new
`prior_closes` kwarg (the stock's closes from BEFORE entry) and the trail now averages
`prior_closes + running_closes`. `live_tracker._load_exit_state` fetches a 40-calendar-day window
ending the **day before** `alert_date` — the entry day's own close arrives via `running_closes` on
the first pass, and including it here would double-count it.

**Three deliberate properties:**
- **`prior_closes=None` is byte-identical to the old behavior**, so every non-live caller
  (backtester, shadow trackers, sweep harnesses) is untouched.
- **The prior closes feed the TRAIL INDICATORS ONLY.** `giveback_floor` and its peak
  (`max(running_closes)`) still see the held period alone — a pre-entry high is not a gain the
  position ever had, and folding it in would arm the giveback floor against a peak we never
  reached. Seeding `running_closes` itself would have fixed the trail and silently broken this;
  a test pins it.
- **The fetch is FAIL-SOFT.** Any history error leaves `prior_closes` empty (= old behavior) and
  logs. That pass also carries the hard stop; an indicator input must never abort it.

Tests: `tests/test_ma_trail_uses_stock_history_548.py` (6), mutation-checked against reverting the
trail, leaking prior closes into the peak, and swapping `max()` for `min()`.

**REPLAYED against every recorded trade** (`scripts/probes/_548_seeded_ma_trail_replay.py`,
read-only). This answers the operator's own concern from the same morning — *does a trail that is
live from day one cut the runners short?*

| | n | trail fires | mean actual | mean with seeded trail | better / worse |
|---|---|---|---|---|---|
| paper | 33 | 10 | +0.64R | **+1.27R** | 8 / 2 |
| live | 17 | 3 | −0.74R | +0.31R | 1 / 2 |

**It does NOT cut the runners — it improves them.** The clearest case is **CRSR (peak +12.36R):
actual +1.80R → +3.31R**, because the trail held the position through a move the day-3/5 partial
had already clipped. QURE +0.49 → +1.14, IBM +0.47 → +0.72, FPS +0.16 → +0.50.

**Where it is worse, recorded rather than buried:** KURA +0.13 → −1.00 (fired d+4) and RCAT
+1.24 → +0.62 (d+8) on paper; MANE −0.23 → −0.92 (d+1) on live. The MANE shape is the one to
watch — a same-day round-trip can close below the trail on day one, and there the trail exits a
position the old code would have held.

⚠ **The live row is 3 trades.** 15 of 17 closed the same day, before any daily pass could run, so
the live cohort still cannot exercise this and the +0.31R is carried by QBTS alone (−1.00 →
+2.86). Paper is the only cohort with enough hold time to judge it.

Worth stating for that sign-off: §B4 activates the trail only once it **surpasses the hard-stop
floor**, and the effective stop is `max(hard_stop, active_sma, entry_price)` — so a seeded MA can
only ever RAISE the stop, never exit earlier than the hard stop already would. Seeding is
protective, not premature. ⚠ But what seeding would have done to the recorded cohort has **not
been replayed**, and that replay is the evidence the change needs.

### 4. Time-stop — 9M Day-2 only; does not apply to MAGNA53.

### 5. Giveback hook — present but **default-off with no live caller**.

**Consequence of 1-5 together:** between day 1 and day 3 there is **no mechanism that can reduce a
losing position** other than the original stop. That is the mechanical reason 10 of 12 live MAGNA53
losses printed almost exactly −1R.

---

## Measured behaviour (live MAGNA53, n=12 closed, through 2026-07-31)

| | |
|---|---|
| mean hold | **1.50 calendar days** |
| trades that ever reached day 3 | **1 of 12** |
| partials ever fired on live money | **0** |
| closed at ≈ full −1R | 10 of 12 |
| reached ≥ +2R intraday and round-tripped | 4 of 4 |
| measured value of the deployed rule | **+0.09R/trade** (last of 34 candidates replayed) |

**The deployed rule is effectively inert on live money.** It is gated at a day count the trades do
not survive to reach.

Full evidence, all figures independently recomputed twice:
`docs/analysis/508_exit_discipline_STATE_2026-08-01.md`.

---

## Known limitations / open questions

1. **Daily cadence vs intraday reality.** Trades round-trip inside day one (MANE touched +7.92R
   intraday, closed −0.23R). Any profit trigger evaluated at 3:45 PM will miss most of what the
   backtest models as a resting-limit fill. **A profit rule and a daily decision cadence are close to
   incompatible on this setup.**
2. **Recorded peaks are floors.** The peak instrumentation reads `highest_price_seen` and is blind
   under ~10 minutes; four live trades lived 0.8-11.7 minutes, so their recorded peaks are not
   trustworthy. CRCL's true intraday peak was +1.62R against a recorded 0.00.
3. **The unit question is unresolved.** Entry-to-stop distance spans 0.15-1.17 ADR (7.7×), so "+2R"
   is not one distance. Whether the trigger should be in R or in daily ranges cannot be settled with
   current data — see the state doc §3.2.
4. **DEFERRED (operator 2026-08-01, "later not now"): a character-conditioned time exit.** He noted
   the day-5 rule "may be a good one for example for biotech which tends to run just for days per
   Pradeep." So the question is not whether a time exit is wrong, but whether it should be keyed to
   the NAME's character rather than applied flat. This is the same axis as the exit review's
   segmentation item (c) — fast/gappy/small-cap/high-ADR names needing different handling from slow
   large caps. **Not being pursued now.** Revisit alongside that segmentation once the cohort supports
   it; do not re-open it earlier.
5. **The strategy's problem is probably upstream of exits.** The shadow ORB control — same alerts,
   same gates, no broker — shows **zero winners across bull AND correcting months**. Exit changes
   make losses smaller; they are not expected to make the strategy profitable.

---

## Change log (newest first)

### 2026-08-15 — BUILT (#566): OCO on the freed 1/3 at +2R + the accounting fix — SHIPPED DARK, default OFF

**Status: BUILT, NOT DEPLOYED, toggle DEFAULT OFF.** Implements the 2026-08-14 operator-signed
proposal below (design unchanged — do not re-litigate it there). Both defects in ONE change, as
directed: the protection hole (defect 1) and the accounting hole (defect 2).

**Protection half — the order shape (new runtime toggle `profit_take_oco`, default OFF):**
- At +2R, steps 1 (reduce stop to 2/3, cancel-then-new leg-safe) and 2b (price-only replace of
  the 2/3's stop to breakeven, gated on `breakeven_at_broker`) are **byte-for-byte unchanged**.
- Step 2, when `profit_take_resting_limit` AND `profit_take_oco` are both ON: the freed 1/3 is
  sold with **ONE OCO** (`alpaca_client.place_oco_sell`) — GTC limit at the +2R target +
  sibling GTC stop at **breakeven** (`max(current stop, entry)` — never below the stop the
  shares already had). Probe shape B verbatim: `order_class=oco` + top-level `limit_price` +
  `take_profit.limit_price` (bare limit_price → 40010001, banked fact) + tick-rounded
  `stop_loss.stop_price`. The limit **stays resting** — no cancel/re-place-on-price shapes
  (operator constraint). A parent returned without a stop leg is cancelled + raised
  (naked-third guard — a limit-only third IS the ETON hole).
- Both sides are mirrored into `mi_live_orders`: parent `purpose='partial_exit'`, held stop leg
  `purpose='stop_loss'` — the leg is **hidden from `get_open_orders` while held** (banked probe
  fact), so that row is the mirror's only record of it and what routes its fill.
  `stop_order_id` keeps tracking the 2/3's stop only; the trail governs the 2/3 only (the OCO
  stop stays AT breakeven by construction — `update_stop` sizes `remaining − pending exits`).
- No stop/entry anchor to price the sibling (both NULL) → falls back to the plain resting limit
  with a loud `partial_exit_oco_fallback` audit row — never a broken OCO, never worse than today.

**Accounting half — the invariant, enforced at every writer (NOT toggle-gated; these are
bookkeeping bug fixes enforcing already-signed intent, no order behaviour changes):**
- `trade_stream._process_stop_fill` + `order_manager._finalize_stop_fill_locked` (the two
  writers that zeroed ETON): a stop fill now decrements by the **actual filled qty** — a
  partial-qty fill (the 2/3 stop firing while the third rests) leaves the row **OPEN** with the
  true remainder and books P&L on the shares that actually sold (ETON booked 17 when 12 sold).
  Only a fill that exhausts the position closes the row. Day-1 **re-entry is gated on a FULL
  stop-out** — re-entering on a partial-qty fill would double the position.
- `_finalize_partial_exit_locked`: remaining is **clamped at 0** (never negative — the −5) with
  a loud `remaining_shares_clamped` audit row when the books already disagreed; and a partial
  fill that exhausts the position now **closes** the trade (remaining=0 on an open row is the
  mirror-image lie).
- A cancelled partial-exit order that had **partially filled** commits its filled portion via
  `finalize_partial_exit` before any restore sizing (those shares sold; dropping them recreates
  the drift).

**Coverage checks audited for the held-leg blind spot (build flag 2) — the wrong-reading class:**
- `check_position_coverage` (15-min detector) — **FIXED**: counts an open sell OCO parent's
  unfilled qty as stop coverage (an open parent is broker-proof the sibling stop holds those
  shares; the pair lives/dies as a unit). A **plain** sell limit still counts for NOTHING —
  that limit-is-not-protection reading IS defect 1 and the detector must keep firing on it.
- `trade_stream._handle_cancel_or_reject` — **FIXED (the dangerous one)**: an OCO parent's
  cancel (which the broker emits when the sibling stop FILLS) no longer runs the plain-partial
  restore, which would have cancelled the 2/3's good stop and placed a full-size stop the
  broker rejects 40310000 — a genuinely naked position announced as protected. Now: leg
  filled → no action (the leg's own fill event owns accounting); leg dead/unreadable → the
  third IS uncovered → `_ensure_stop_coverage` from broker truth (idempotent), never a blind
  cancel-and-restore.
- `coverage_drift` D2 — **FIXED**: the tracking set now unions `mi_live_orders.alpaca_order_id`
  (managed exits are tracked there, never as trade-row pointers), ending the false
  "untracked open order" HIGH a resting GTC limit / OCO parent fired every 24h window.
- `trade_stream._handle_partial_fill` — **FIXED**: terminal-partial routing now resolves the
  trade via `mi_live_orders` when the order is not an entry/stop pointer (pre-fix, a resting
  limit's terminal state reported through partial_fill events was silently dropped).
- Audited, **no change needed**: `_ensure_stop_coverage`, `update_stop`, `sync_positions`'s
  orphan loop (all size `broker/remaining − get_pending_exit_qty`, and the OCO parent is a
  pending exit — targets already exclude the third); `_try_adopt_existing_stop` (the hidden leg
  can never be adopted, correct — adopting a leg would hand the trail a pair-bound order); the
  stop-ack watchdog (counts remaining unfilled sell orders incl. the parent, and its stop-sync
  no-ops on a limit-only book — benign, verified by trace).

**Documented interaction (emergent, stated not hidden): the trigger can RE-FIRE after the OCO
stop scratches the third.** `scan_profit_triggers` selects on `partial_taken=FALSE` (which only
flips on a partial-PROFIT fill) with a sticky in-hold `MAX(high)`; while the OCO rests, the
dedup-pending guard blocks re-fires — but if the OCO **stop** side fills (third out at
breakeven, no `partial_taken`), the pending order is gone and a later poll re-fires the
trigger: reduce the (now 2/3) stop to its own 2/3 and rest a fresh OCO third at the same
target. Risk never increases — every share stays behind a breakeven stop throughout — and
re-arming a resting sell at the target after a scratch is aligned with the operator's
keep-the-limit-resting intent; suppressing it would itself be a trigger-discipline change.
The Telegram announcement stays once-per-trade (`_profit_trigger_already_announced`), so a
re-fire acts quietly. Recorded so the first live occurrence reads as designed-emergent, not
as a bug.

**Partial fill of a multi-share OCO limit — the one unprobed outcome, decided in advance:**
a 1-share OCO cannot partial-fill, so whether Alpaca down-adjusts the sibling held stop leg is
**unverifiable without a broker fact we do not have; we do not guess.** What ships: accounting
commits only from actual fills (terminal events + the cancelled-with-fills commit above), the
coverage detector counts only the parent's **unfilled remainder**, and the first real
occurrence is flagged loudly (`oco_partial_fill_observed` audit + a Telegram line saying the
sibling-leg adjustment is UNVERIFIED) so it can be confirmed at the broker before it is relied
on. If Alpaca in fact cancels rather than adjusts, the parent-cancel path above re-protects.

**Prod-row repair (defect-2 damage already written) — PROPOSED, operator-run only (production
write; nothing here executes it):**
```sql
-- 1. Review the damage (expected: exactly the ETON row at -5):
SELECT id, ticker, account_mode, status, remaining_shares, total_pnl, closed_at
FROM mi_live_trades WHERE remaining_shares < 0;

-- 2. Repair, only after the SELECT shows exactly the expected row(s).
--    Each row becomes remaining_shares = 0; status/closed_at/total_pnl/exits untouched
--    (ETON's net +$19.32 is correct; the position is genuinely flat).
UPDATE mi_live_trades SET remaining_shares = 0
WHERE remaining_shares < 0 AND status = 'closed';
```
Known cosmetic residue, deliberately NOT repaired: ETON's `exits` array over-states the
stop-hit entry's share count (17 booked vs 12 sold, at breakeven so ~$0 P&L impact). Rewriting
exit history is a bigger intervention than the defect warrants — recorded here instead.

**TO FLIP (operator only — this acts on live money; requires `profit_take_resting_limit` +
`breakeven_at_broker` already on for the same mode):**
```sql
INSERT INTO mi_safeguard_state (safeguard, account_mode, state, updated_at)
VALUES ('profit_take_oco', 'live', 'on', now())
ON CONFLICT (safeguard, account_mode) DO UPDATE SET state='on', updated_at=now();
```
Reverting is the same statement with `'off'`. No redeploy either way. Fails CLOSED (an
unreadable flag leaves the plain resting-limit behaviour).

**VERIFY-LIVE:** the next +2R fire should show `partial_exit_sell_placed` with
`order_class=oco` + a `stop_loss` leg row in `mi_live_orders`, the Telegram naming BOTH prices,
and the 15-min coverage detector staying silent while the OCO rests. Until seen in prod this is
built, not proven.

**Tests:** `tests/test_oco_carveout_566.py` (12), `tests/test_partial_carveout_accounting_566.py`
(14), `tests/test_oco_cancel_handler_566.py` (6), plus the D2 case in `tests/test_coverage_drift.py`
— every terminal outcome (limit fills part/last/over-fill · stop fills partial/full/leg/over-fill ·
neither = GTC placement · partial fill routing/cancel-commit) mutation-proven (15 mutations, each
reddening its target test; recorded per test docstring).

**Reversion-flag:** REFINEMENT of the 2026-08-10 resting-limit design (the resting limit was not
wrong, it was incomplete — it left the third stop-less if unfilled). The accounting fixes are bug
fixes enforcing signed intent (a closed row with live shares was never intended by anything).

### 2026-08-14 — PROPOSAL (operator-designed, NOT SHIPPED): OCO on the freed 1/3 at +2R — closes the uncovered-shares hole

> **SUPERSEDED 2026-08-15 — BUILT as specified; see the #566 entry above.** Kept for the design
> rationale and the banked broker facts.

**Status: DESIGN ONLY. Nothing in this entry is deployed. Ships only after operator sign-off
(THE LINE) + CHANGE_PROCESS.** The broker question it depends on is ANSWERED — paper probe
`scripts/probes/_548_oco_alongside_stop_probe.py`, run 2026-08-14 09:51 ET, full output in
`docs/analysis/548_oco_probe_run_2026-08-14.log`.

**THE HOLE (found live 2026-08-14 by the operator, on ETON).** The +2R resting-limit shape
(shipped 08-10) reduces the stop to cover 2/3 at breakeven and rests a GTC limit for the freed
1/3 at the target. **If that limit never fills, the 1/3 has NO stop.** ETON live at discovery:
17 shares held · stop covers 12 @ $55.20 (breakeven) · limit sells 5 @ $59.58 · **5 shares
uncovered** — a limit above the market protects nothing on a decline. Per his instruction
(*"let's not do anything one-off or manual"*), the ETON position was NOT touched; it stays as-is
until the real change ships.

**THE DESIGN — his, verbatim:** *"can we have the 2R limit sell matched with stop at original?
The other 2/3rd can still stick with the breakeven stop."* One accepted refinement: the 1/3's
stop goes at **BREAKEVEN**, not the original hard stop — no reason to protect those shares less
than the other 12.

**Design constraint from his own ruling — the limit must STAY RESTING.** The cancel-below-2R /
re-place-on-return alternative was proposed and REJECTED by him: *"stock is volatile and moves
in & out of 2R range, if we cancel the 2R and re-sell again when it hits chances are we'll
likely miss it again, so best way to actually fill is to keep the 2R limit sell on."* Do not
re-propose reactive cancel/re-place shapes.

**Order sequence at +2R fire (proposed):**
1. Reduce the full-size stop to a 2/3-quantity stop at breakeven — **unchanged** from shipped
   behaviour (verified-clear cancel-then-new on the bracket leg, leg-safe mechanism, breakeven
   via `max(stop, entry)`).
2. For the freed 1/3, submit **ONE OCO order** instead of the plain limit: `order_class=oco`,
   sell qty = 1/3, **GTC**, `take_profit.limit_price` = the 2R target, `stop_loss.stop_price` =
   breakeven. The broker holds a sibling stop leg (`status=held`) against the same shares —
   whichever side fills cancels the other.

**What covers what:** 2/3 → plain breakeven stop (trail governs it as today). 1/3 → the OCO
(exactly one of limit/stop fills). **Broker-proven property: every share is reserved** — the
probe's extra 1-share sell was rejected `40310000 available:0, held_for_orders:3`, naming both
orders. The ETON shape (an uncovered 1/3) cannot exist under this design.

**Terminal outcomes:**
- **Limit fills** (target reached): OCO sibling stop auto-cancels; 1/3 banked at the target
  price (not a market chase — the FIGS defect stays fixed); 2/3 unchanged behind breakeven+trail.
- **OCO stop fills** (price falls to breakeven): limit auto-cancels; 1/3 out at ~breakeven. The
  2/3's own stop sits at the same breakeven price and fires on the same move — the whole
  position scratches, which is the intent of breakeven.
- **Neither by close:** both OCO legs are GTC and rest overnight alongside the GTC 2/3 stop —
  no expiry hole, no daily re-place.
- **Partial fill of the limit** (possible when the 1/3 is >1 share): ⚠ **NOT probed** — a
  1-share OCO cannot partial-fill. Alpaca's documented advanced-order behaviour adjusts the
  sibling leg, but this must be confirmed (probe or first live observation via the existing
  coverage watchdog) before the design is declared fully verified.

**Broker facts (paper probe, 2026-08-14 — raw responses in the log):**
- Request shape: `order_class=oco` with only top-level `limit_price` → REJECTED `40010001 "oco
  orders require take_profit.limit_price"`. With `take_profit.limit_price` (+ matching top-level
  `limit_price`) + `stop_loss.stop_price` → **ACCEPTED first try**.
- **An OCO on the freed 1/3 COEXISTS with the separate plain 2/3 stop** — board readback shows
  both live (`oco/limit qty 1` + `simple/stop qty 2`); the sibling stop leg rides as
  `status=held`.
- Cancelling the OCO parent terminates **both** legs — the pair unwinds as a unit (one cancel,
  no orphan).
- Sequencing constraint STANDS (08-10 probe): the OCO can only be placed AFTER the stop
  reduction is verified-clear — a sell is rejected 40310000 while the full-size stop holds the
  shares. Same ordering the shipped code already uses.

**Build requirements to flag at implementation (not design changes):**
- `get_open_orders` does NOT surface the OCO's held stop leg as its own row — any coverage
  arithmetic that sums open stop-order qty would read the 1/3 as UNPROTECTED and try to
  "repair" it (the repair would itself be rejected 40310000). `_ensure_stop_coverage` / stop
  watchdogs must count the OCO parent's reservation as coverage.
- The OCO's legs are advanced-order LEGS: qty-replace is structurally rejected (42210000 class);
  price-only replace on a leg is allowed (T2). Design intent keeps the OCO stop AT breakeven —
  the trail governs the 2/3 only.

**Fallback:** not needed — the broker accepted the exact proposed shape. Had it been rejected,
the decision would have returned to the operator; no workaround was designed.

### 2026-08-10 — BUG FIX: update_stop could LOWER a live stop; raise-only floor added against the broker stop

**Classification: bug fix enforcing already-signed intent** (a protective long stop is raise-only —
the production comment on `execute_partial_exit`'s `_be_outcome == "live"` branch is the signed
intent: *"a stale (lower) value would let a later trail pass cancel this stop and re-place LOWER —
loosening protection"*). Not a detection-criterion or strategy change; no CHANGE_PROCESS N≥10 gate.
Nothing about WHEN the trail moves a stop or by how much changed — only whether an already-computed
move that would LOWER the live stop is allowed to execute (it never was, by intent).

**The defect.** `update_stop` cancelled the live stop and re-placed at whatever the caller computed;
its only price reference was `mi_live_trades.stop_price`. The EOD trail decides "am I raising?"
against that DB value (`live_tracker.py` — `step.effective_stop > current_stop + 0.01`), and
nothing reconciles `stop_price` back from broker truth. The reachable window: the #548 resting-mode
breakeven "uncertain" branch DELIBERATELY persists the successor stop pointer while withholding
`stop_price` (the DB understating protection is the safe direction — pinned in
`test_resting_mode_breakeven_548.py`; that branch is correct and was not touched). DB then sits at
the old, LOWER value while the broker rests at breakeven; a later trail pass whose `effective_stop`
lands between the two would cancel the good breakeven stop and re-place LOWER. Protection silently
loosens.

**The fix** — in `update_stop` itself, not at each caller, so any future caller inherits it:
- Live (non-terminal) broker stop + requested price not strictly above it → refuse: no cancel, no
  place, `stop_update_aborted` audit row (`reason=raise_only_floor`), return False. Equal price is
  refused too — cancel + re-place at the same price only opens a no-stop window (the #444 shape).
- **Fail direction, deliberate:** broker stop unreadable (`get_order` → None, or a non-terminal
  order with no `stop_price`) → refuse the same way (`reason=broker_stop_unreadable`). An
  unreadable stop means the move cannot be proven a raise; leaving the existing stop untouched
  keeps protection unchanged, while proceeding blind is exactly how the defect loosens it. Loud,
  never silent: `logger.warning` + audit row.
- Terminal old stop (cancelled/expired/rejected/replaced/done_for_day/filled) or NULL pointer → no
  floor; the re-protect paths re-place at the DB price exactly as before.

Tests: `tests/test_update_stop_raise_only_floor.py` (9), each mutation-proved (inverted comparison,
disabled floor, blind-proceed on unreadable, skipped no-price branch, floor applied to terminal
stops, broker read on NULL pointer — every mutation reddened its test). `execute_partial_exit`'s own
stop re-creation is a separate path and was not touched.

### 2026-08-08 — Real-time breakeven at the BROKER — SHIPPED DARK (#548 defect 2)

**Operator signed off** (*"yes to both… stop to breakeven needs to be real-time"*). **Deployed
INERT behind `mi_safeguard_state('breakeven_at_broker', <mode>)`, DEFAULT OFF**, because #508's
own history is the argument: that change shipped inert, was confirmed in prod, and only then
flipped — *"so the path was proven before it was allowed to act on money."*

**THE BUG.** The profit-take Telegram says *"stop moves to breakeven."* `finalize_partial_exit`
set `breakeven_active = TRUE` **in the database**, and the only consumer of that flag is
`exit_logic`'s DAILY pass, which runs after the close. FIGS 08-07 stopped out at **09:51 the same
morning** — ~6h before any daily pass could act — with the remaining 41 shares still behind the
ORIGINAL $15.19 stop, losing $13.74 on a trade that had already banked a profit. Structural, not
bad luck: live MAGNA53 averages ~1.5-day holds and most trades die on day 0-1.

**THE FIX IS A PRICE ARGUMENT, NOT NEW MACHINERY.** The stop is *already* re-created at partial
time — a bracket leg's quantity cannot be replaced (Alpaca 42210000), so it is cancel-then-new
regardless. Breakeven simply supplies `max(stop_price, entry_price)` to that existing operation.
**Zero extra orders, zero extra legs, zero new failure modes** — which is why this half could ship
while the 2R-limit half is still being designed, under the operator's ranked constraint (*"we've
been bitten by stop orders failing at broker when it gets complex"*).

- `max()` — it can only ever RAISE the stop. An original stop already above entry stays put.
- Fails CLOSED: an unreadable toggle leaves exit behaviour exactly as it is.
- Writes `partial_exit_breakeven_armed` naming old stop, new stop and entry — the original defect
  was invisible precisely because nothing recorded that breakeven had NOT happened.

**TO FLIP IT** (operator only — this acts on live money):
```sql
INSERT INTO mi_safeguard_state (safeguard, account_mode, state, updated_at)
VALUES ('breakeven_at_broker', 'live', 'on', now())
ON CONFLICT (safeguard, account_mode) DO UPDATE SET state='on', updated_at=now();
```
Reverting is the same statement with `'off'`. No redeploy either way.

**VERIFY-LIVE:** the next partial that fires should log `partial_exit_breakeven_armed` AND the
reduced stop should be created at the entry price, not the original stop. Until that is seen in
prod this is deployed, not proven.

Tests: `tests/test_breakeven_at_broker_548.py` (6), mutation-checked against removing the gate,
swapping `max()` for `min()`, and never applying the price.


### 2026-08-08 — ⚠ FINDING, NOTHING CHANGED: the +2R rule fired once on live money and BOTH halves under-delivered

**Operator's question, 2026-08-08:** *"if 5 got to +2R and our new profit take is at +2R with
breakeven entry then those 5 would be winners by definition, yet you said 0 winners."* The logic is
right. The answer is that the rule was live for only ONE of the five — and that one still lost.

**FOUR OF THE FIVE PREDATE THE RULE.** `PROFIT_TRIGGER_R = 2.0` went live 2026-08-01. MANE (07-15,
reached +7.92R), SMCI (07-22, +3.21R), NVCR (07-23, +2.00R) and QBTS (07-27, +3.74R) all closed
before it existed. They could not fire it.

**THE FIFTH — FIGS, 2026-08-07 — FIRED IT AND STILL LOST −0.37R.** Full audit trail:

| time (ET) | event |
|---|---|
| 09:32 | entry filled, 61 sh @ $15.4951, hard stop $15.19 (R = $0.305, 2R target = **$16.11**) |
| 09:35:01 | `partial_exit_stop_replaced` — stop reissued for 41 sh **@ $15.19** |
| 09:35:01 | `partial_exit_sell_placed` — **market** sell 20 |
| 09:35:02 | `profit_trigger_fired` — high $16.38 ≥ 2R target $16.11 |
| 09:35:04 | committed — sold 20 **@ $15.84**, +$6.90 |
| 09:51:02 | `stop_hit` — 41 sh @ **$15.16**, −$13.74 |

**DEFECT 1 — the partial sells at MARKET, so it does not get the target price.** The trigger
correctly detected the high at $16.38, then placed a market order that filled at **$15.84 = +1.13R,
not +2R**. The high had already passed. The 08-01 build-prep doc proposed a *resting LIMIT sell at
entry + 2×risk* precisely to avoid this; what shipped is 5-minute-poll → market sell.
Banked $6.90 where the target level was worth ~$12.30.

**DEFECT 2 — "stop moves to breakeven" is TRUE IN THE DATABASE AND ABSENT AT THE BROKER.** The
Telegram tells the operator *"stop moves to breakeven."* `finalize_partial_exit` does set
`breakeven_active = TRUE`. But the actual broker stop was reissued at **$15.19 — the original hard
stop** — and `mi_live_trades.stop_price` still reads 15.19. The flag is consumed only by
`exit_logic`'s DAILY pass (`if breakeven_active and entry_price > effective_stop: effective_stop =
entry_price`), which runs after the close. **FIGS stopped out at 09:51 the same morning, ~6 hours
before any daily pass could act on it.**

⚠ **This is structural, not bad luck.** Live MAGNA53 average hold is ~1.5 days and most trades die
on day 0-1, so the breakeven half of the rule can rarely protect the trades it was designed for.

**ARITHMETIC OF THE ONE LIVE FIRING:**

| | banked | remainder | total |
|---|---|---|---|
| as designed (limit @ $16.11, stop → $15.4951) | +$12.30 | $0 | **+$12.30** |
| as it actually ran (market @ $15.84, stop @ $15.19) | +$6.90 | −$13.74 | **−$6.84** |

**NOTHING HAS BEEN CHANGED.** Exit discipline is THE LINE — CHANGE_PROCESS + operator sign-off.
Both defects are recorded here and filed for his ruling. n=1, so this is a mechanism finding, not
a statistical one: the mechanism did not do what the rule and the Telegram both say it does.


### 2026-08-08 — #508 CLOSED: the sell-discipline surface is verified live, and it says the candidates are inert

**DISPLAY ONLY. No exit rule changed.** Verified by RENDERING the operator-facing section against
production, not by reading the code — which is how both defects below were found.

**THE HEADLINE, and it is the sharpest statement of the exit problem we have:**

| live MAGNA53 cohort | n=17 |
|---|---|
| winners | **0** |
| reached ≥ +1R | 8 |
| reached ≥ +2R | 5 |
| average REACHED | **+1.54R** |
| average KEPT | **−0.91R** |

Every one of the 17 ended a loser, including the five that got to +2R. Nothing banks the excursion.

**CANDIDATE RULES: both replayed, both INERT.** `mi_pivot_stop_shadow` carries each candidate
profile's would-have-kept per trade. On the live cohort, profile **p1 changed 0 of 12** trades and
**p2 changed 0 of the 5** it was populated on (7 of 12 abstained). They would have kept exactly
what we actually kept. Recorded here so neither is re-proposed on intuition — that is the entire
point of making candidates replayable rather than arguable.

**DEFECT 1 — the surface and the trigger disagreed on regime, 5 trades out of 17.** The section
was labelled `regime@entry` but the query RECONSTRUCTED regime by joining `mi_market_regime` on
`alert_date` — the regime as later REVISED. That reported **Bull 6**, while
`exit_tune_bull_regime_read` (the trigger that gates every bull-tape conclusion) counts
`mi_live_trades.regime`, stamped at entry, and reads **Bull 3**. The disagreeing trades: WULF,
TSEM, FTNT, BTDR, BLZE — 08-04 was Choppy at 09:31 and resolved Bull.

**RULE ADOPTED: for any exit-rule read, regime is the value STAMPED AT ENTRY.** The question an
exit-rule analysis asks is *what tape did we believe we were entering into*, because that is the
information the decision actually had. A later revision cannot retro-justify or retro-condemn a
decision made without it. The reconstruction-by-date join is still correct for other questions —
just not this one.

**DEFECT 2 — DoD leg 3 rendered a row count.** `counterfactual stores: giveback n=1 · pivot n=12`
answers "does the store have rows", not "what would a candidate rule have kept". The data was
already there; the surface never asked. It now renders reached / actual / p1 / p2 **plus the
CHANGED count** — deliberately load-bearing over the average, because an average drifts merely
because a profile is NULL on some trades, and only the changed count distinguishes an inert
candidate from a working one.

**CARRIED FORWARD:** `CRMD` trade 137 is skipped by the recorder every night (hard_stop $8.45
above entry $8.36 → no valid R frame) and cannot resolve on its own. Job-hygiene, filed on #528.


### 2026-08-04 — The partial-exit breaker can now be reset, because it had deadlocked the fix

**Trigger**: operator, 2026-08-04 — *"we take partial profit at 2R ... if not, then it's all
garbage."* The rule could not fire, and clearing the reason it could not fire was itself blocked.

**The deadlock**: the breaker closed on exactly one condition — a SUCCESSFUL partial
(`partial_exit_committed`). The bracket-leg defect made every partial fail, so the breaker opened by
that defect also prevented the automatic path from ever demonstrating the fix. Three failures, no
exit.

**Change**: `_consecutive_partial_exit_failures` now counts from the most recent
`partial_exit_committed` **or `partial_exit_breaker_reset`** row. The reset is a deliberate, audited
row naming the fault it clears. It deletes nothing — the failures stay in the log — and it moves
only the window, so failures after a reset count normally against the unchanged threshold of 3.

**Not a weakening**: without it the only escape was `/partialnow` (force=True), which bypasses the
breaker entirely AND requires the operator to act manually — strictly worse on both counts than an
audited reset.

**Tests**: `tests/test_partial_at_2r_is_reachable.py` (7).

### 2026-08-04 — The profit-trigger Telegram now announces ONCE per trade, not once per 5-minute poll

**Trigger**: operator, 2026-08-04 — *"profit take failed and I've been bombarded with these msg non
stop, this is a really really bad bug."* The volume was a **pair** of messages every 5 minutes for
hours on PLTR 307: the partial-exit circuit-breaker alert, and the `💰 Profit target hit`
announcement at the top of `scan_profit_triggers`.

**Why it repeated**: both of the trigger's selection conditions are *sticky while the partial keeps
failing*. `partial_taken` only flips TRUE on a SUCCESSFUL partial, so a trade whose partial fails is
re-selected on every pass; and detection is `MAX(high) >= target` over the whole in-hold window,
which having once been true is true forever. A position that cannot be harvested therefore
re-announces its target hit every poll for as long as it stays open — and would have resumed at
09:30 the next session.

**Fix**: both messages are now deduped per trade against `mi_audit_log` — `_breaker_already_alerted`
(breaker) and `_profit_trigger_already_announced` (announcement). The audit row IS the state, so the
dedupe **survives a service restart** (a process-local set would re-arm the loop on every deploy).
Both fail OPEN: on a read error the message still goes out, because a duplicate is a nuisance and a
missed one on a money path is not. **Only the Telegram is deduped — the `profit_trigger_fired` /
`profit_trigger_failed` audit rows still land every cycle**, so the durable record stays complete.

**Not a rule change**: no threshold, fraction, target or stop is touched. This is notification
behaviour on a fail-safe path. Tests: `tests/test_profit_trigger_508.py` (6 added, all fail against
the pre-fix code), including one that pins the audit trail as NOT deduped.

### 2026-08-04 — Profit-trigger partial could NEVER execute on MAGNA53 (bracket-leg stop) — leg-safe mechanism, shipped OFF

**Trigger**: PLTR trade 307, the FIRST live +2R profit-trigger fire. Alpaca rejected the stop
reduction with `42210000 "qty cannot be changed for advanced orders"`. Every MAGNA53 entry is an OTO
bracket, so its stop is an advanced-order LEG — the qty-replace in `execute_partial_exit` is
structurally rejected on ALL of them. Fail-safe (the rejected replace left the original stop live;
nothing harvested), but the operator-signed rule could never execute.

**Evidence** (mechanism bug fix, not a criteria change — the 2R trigger / 1/3 fraction / stop level /
breakeven move are untouched): empirical paper probe `scripts/probes/_508_oto_leg_probe.py` (full
responses + ms timings captured in `scripts/probes/_508_oto_leg_probe_output.json`, run 2026-08-04
15:52 ET on a real filled OTO bracket):
- qty replace on the leg → REJECTED 42210000 (reproduces PLTR); the leg stays LIVE after the
  rejection (atomic — confirms the abort path's fail-safe assumption).
- price-only replace on the leg → OK, but the replacement is STILL `order_class=oto`, and a qty
  replace on the replacement → REJECTED 42210000. Once a leg, always a leg — no detach trick.
- a second stop while the leg holds the shares → REJECTED 40310000 insufficient qty; a market sell
  while the leg holds → REJECTED 40310000. No over-cover transition, no sell-first ordering exists.
- cancel → cancel CONFIRMED +15ms → share reservation released +78ms (**the release lags the cancel
  confirm by ~60ms — the IBM 2026-05-27 race, now measured**) → reduced stop accepted FIRST try at
  +87ms → partial sell accepted with the reduced stop live.

**Conclusion**: cancel-then-new is the ONLY mechanism Alpaca permits on a bracket leg. The May
incident was not "cancel+new is unusable" — it was cancel+new WITHOUT waiting for the broker's
share-reservation release. New `_reduce_stop_via_cancel_new` (order_manager) gates the new-stop
submit on `qty_available` covering the remainder, retries the reservation-lag rejection, and funnels
every failure into the existing #151 abort machinery (old-stop probe → clean protected abort if the
leg still lives; null + in-process `_ensure_stop_coverage` re-protect to broker truth otherwise).
Simple (non-leg) stops keep the atomic replace path byte-for-byte.

**Naked window, stated honestly**: from cancel-confirm to new-stop-accept the position has NO resting
stop — measured ~72ms on paper, bounded by poll budgets (3s cancel-confirm + 5s release + 4 placement
attempts) with the in-process re-protect and the sync cron behind it. This exposure is structural on
Alpaca (every alternative ordering is rejected, per the probe); it occurs only at +2R in profit, with
the market far above the stop. Duplicate-stop risk is closed by the broker itself: a stop can never
be ACCEPTED while another one holds the shares (40310000), so an accept is broker-side proof the old
reservation cleared.

**Anticipated effect**: the +2R partial becomes executable on bracket-protected (= all MAGNA53)
positions. `partial_exit_stop_replaced` audit rows now carry `mechanism` +
`timings_ms` (cancel/release/accept) so the live naked-window size is verifiable per fire.

**Reversion-flag**: REFINEMENT of 2026-08-01 (mechanism only). Contains a scoped REVERSAL of the
#136 2026-05-27 "replace, never cancel+new" rule for LEGS ONLY — prior reasoning ("cancel+new races
the share reservation") was not wrong, it was incomplete: it treated the race as intrinsic to
cancel+new when it is intrinsic to submitting BEFORE the reservation release, and it never accounted
for bracket legs where replace-qty is impossible. Replace remains the rule for simple stops.

**Status**: shipped OFF (runtime toggle `partial_exit_leg_safe`, `mi_safeguard_state` /
`PARTIAL_EXIT_LEG_SAFE`, default off, ~60s flip, no deploy) — awaiting live verification, then flip.
Tests: `tests/test_partial_exit_leg_safe_508.py` (7 of 8 fail against the pre-fix code; the 8th pins
today's toggle-OFF fail-safe).

**Known limitation (same bug class, latent)**: `_ensure_stop_coverage`'s under-covered branch uses a
qty-only replace and would hit 42210000 if the surviving stop were ever a LEG under-covering a grown
position. A full-size bracket leg is never *under*-covered, so reaching that branch needs the position
to grow past the leg or the leg to partly die — argued rare, but UNMEASURED; the count of
`stop_coverage_repair_failed` audit rows is the number, and reading it is step 1 of #523. It fails LOUD
(`stop_coverage_repair_failed` audit + Telegram, retried next cycle). Not changed here to keep this
diff verifiable; fold into the leg-safe helper after the partial-exit path is verified live.


### 2026-08-01 — Intraday profit trigger BUILT (shipped OFF; operator-signed)

**Trigger**: operator 2026-07-30 (*"1/3rd at 3R then move stop to breakeven"*), sharpened 2026-08-01
— the day-3 gate "may not be optimal" because live trades die before reaching it. Confirmed: it has
fired **once in 12 live trades**.

**Evidence**: N=36 magna53 closed trades, 34 candidate rules replayed, every figure independently
recomputed twice. Incumbent +0.09R/trade on live; 1/3-at-+2R +0.47R. Re-scored under the REAL
5-minute-poll fill (not the idealised limit fill the proposal assumed): **+0.43R vs actual on the 11
measurable trades, and the mechanism change costs ≤0.04R** — nil at +2R.

**Anticipated effect**: partial fires ~1 in 3 live trades instead of 1 in 12; full −1R losses fall
from 10-in-12 toward ~6-in-12. **No change to win rate** — it makes some losses smaller, it does not
make losers into winners.

**Reversion-flag**: REVERSAL of the 2026-03-27 "v2 rules" decision (`EP_TRADING_RULES.md` §B5).
Per CHANGE_PROCESS r4 the prior reasoning was not *wrong* — it assumed trades survive to day 3, true
of the population it was designed against (paper mean hold 3.17d, 9 of 24 reached day 3) and false
live (1.50d, 1 of 12). **Inapplicable, not mis-specified** — so if live holds ever lengthen, revisit.

**Implementation**: `order_manager.scan_profit_triggers()`, called sequentially from the existing
5-minute `track_position_extremes` job on the bars that job just persisted. Deliberately NOT a branch
inside the recorder — that function is name-registered in the column-write authority gate, and a
money action there would trip Gate 5 G (#500 class). Detection is BAR-based (in-hold `MAX(high)`), so
a spike between polls is still caught. It reuses `execute_partial_exit`, which reduces the stop
**before** selling under a per-trade advisory lock — no window where the stop over-covers the
position, and no resting order.

**Status**: **LIVE — `constants.PROFIT_TRIGGER_R = 2` set 2026-08-01, operator-signed.**
Take 1/3 at entry + 2 × risk_per_share, then stop to breakeven. **Reversion = set the constant back
to `None`** (restores the day-3/day-5 rule with no code change) and redeploy market-agent +
execution.

Deployed inert first and verified in prod (both containers read `None`, `scan_profit_triggers`
present), THEN flipped — so the code path was proven live before it was allowed to act.

**Validation performed** (CHANGE_PROCESS r1 = N≥10 historical samples; we have 36):
- Replay over 36 magna53 closed trades, 34 candidate rules, every figure independently recomputed
  twice.
- **Re-scored under the REAL 5-minute-poll fill**, not the idealised limit fill the proposal assumed:
  +2R is −0.56 either way (delta −0.00), worst case across candidates 0.04R. **+0.43R vs actual.**
- **Code-vs-rule parity** (`scripts/probes/_508_trigger_parity.py`): the shipped predicate reproduces
  the replay's decisions — 11 agree, 0 diverge, 1 unmeasurable (MANE, which the shipped code DOES
  fire on, so the measured number excludes the cohort's biggest runner and is conservative).

**Watch for** (pre-committed, `docs/analysis/508_change_proposal_profit_trigger_2026-08-01.md`):
1. Partial fires, remainder scratched at breakeven, trade then runs ≥+4R same session — one
   occurrence is a review, two is a revert.
2. Next 10 closed live trades worse than the same 10 replayed under the incumbent.

⚠ **Not expected to make the strategy profitable.** The shadow control shows zero winners across
bull AND correcting months with no broker involved. This makes losses smaller.


### 2026-08-01 — SSoT created; no behaviour change

**Trigger**: A proposed change to the profit-take rule (`docs/analysis/508_change_proposal_profit_trigger_2026-08-01.md`)
had no file under CHANGE_PROCESS discipline to update (r6/r7). ⚠ Creating it also corrected TWO of my
own errors: the rule is **not** undocumented — it is in `EP_TRADING_RULES.md` §B5, written by the
operator 2026-03-27 — and describing it as "gates profit-taking at day 3" omitted the day-5
unconditional branch. What is genuinely unwritten is only the day-5-while-underwater INTERACTION that
closes the remainder.

**Evidence**: n/a — this entry documents existing behaviour, read directly from
`broker/exit_logic.py` at commit `6f8652d`. Measured columns above come from 43 recorded closed
trades, verified twice.

**Anticipated effect**: none. No code changed.

**Reversion-flag**: NEW.

**Status**: shipped (documentation only), no field validation applicable.

---

## 2026-08-11 — OPERATOR RULING: no peak-lock giveback floor. We let winners run.

**Asked and answered the same evening.** After the nightly sell-discipline digest showed the live
cohort reaching +1.5R on average and keeping −0.9R, I explained the peak-lock giveback floor
(ADR 0023 Card 1 / A3, `exit_logic.giveback_floor` — default-OFF) and asked whether to bring
evidence for arming it. His answer, verbatim:

> **"no, we let winners run"**

### What is ruled OUT
Arming `giveback_floor` — a stop that cannot fall below a FRACTION OF THE PEAK GAIN once a trade
runs past an arm threshold. It stays DEFAULT-OFF. **Do not re-propose it on the strength of a
reached-vs-kept table**; that table is the reason it looks attractive and the ruling was made with
that table in hand.

### Why — the reasoning behind the ruling, so it is not re-litigated
The methodology this system implements (Qullamaggie / Bonde / Stamatoudis) is carried by a small
number of very large winners. A floor set at a fraction of peak gain does its work by CUTTING THE
RIGHT TAIL: it converts the trade that would have run to +10R into one that stops at the floor on
the first sharp pullback. The giveback statistic cannot see that cost, because it only measures
what was reached and kept on trades we already exited — it has no column for the trade that would
have kept going. **Optimising the reached→kept gap directly optimises AGAINST the tail the whole
edge depends on.** He has flagged this risk before, on the 2R rule: *"if this +2R and especially
breakeven stops ends up killing our chance of big winners, then it would have failed its goal."*

### What is NOT ruled out — the distinction matters
This is not "no exit rules". Already accepted and LIVE:
- the **+2R partial** — take a third off at the target (fired correctly on ABCL 2026-08-11);
- **breakeven at partial** — the remainder cannot lose money;
- the **SMA10/20 trail** — it rises with the stock's own structure rather than with our P&L, and
  by construction it never caps a runner: it only follows one.

The accepted shape is therefore: **bank a piece, remove the risk, then let the rest run behind a
trail that follows the STOCK.** What is rejected is a stop that follows OUR GAIN.

### Live evidence at the moment of the ruling
PLTR: entry $149.05, peak +5.3R, now +4.6R on 4 shares, stop at breakeven, SMA10 $144.18 (still
below entry, so breakeven is the higher protection). ABCL: entry $8.96, +1.5R, 57 shares, stop at
breakeven, SMA10 $6.27 — the trail will not engage for some time on a name that gapped off a low
base. Under a half-of-peak floor PLTR would have been capped near +2.6R.

---

## 2026-08-15 — ⚠ ETON's +$21.89 was a LUCKY ACCIDENT, not evidence the design works

**Operator, unprompted, on the same day the fix shipped:**

> "we banked a profit on ETON but it was a lucky accident in this case given it would've been
> stopped out first if not for the bug, not a concern but something to keep in mind"

**He is right, and this must be recorded or it will be cited later as a win for the design.**

- ETON's carved-out 1/3 (5 shares) survived to fill its $59.58 limit **only because it had NO
  STOP.** That was the defect.
- Under the design that shipped today, those 5 shares carry an OCO with a stop at breakeven — so
  they would have been taken out at $55.20 alongside the other 12, and the limit would never have
  filled.
- **The correct fix therefore turns this specific trade from +$19.32 into roughly breakeven.**

### Why this matters beyond one trade

- **It is not an argument against the fix.** Being unprotected paid once; it is a coin-flip that
  can equally take the position to zero, and the operator's own framing has been consistent —
  positioning for positive expectancy over many trades, never optimising a single outcome.
- ⚠ **It IS an argument against citing ETON as the +2R rule's first success.** The rule's actual
  first success is still unproven: the mechanism fired correctly (limit at the target, stop to
  breakeven the same second — ABCL 08-11), but the one trade that produced realised profit did so
  through a hole, not through the design.
- ⚠ Anyone measuring the exit stack's performance must exclude or flag this trade. It is
  contaminated by the very defect the measurement would be testing.

This is the standing rule applied to a case in our own favour: **no single trade is evidence** —
including the ones that make money.

### ⚠ And the fill itself is LIQUIDITY-DEPENDENT — we have no model of this

Operator, same conversation:

> "ETON in theory is a success but in trading and getting a fill it's not because of it's small
> size / float, being more volatile, etc. If it was a 100B market cap, it would fill no problem but
> it's 1B market cap which is harder to fill at our limit"

**A resting limit is a promise about price, never about a fill.** On a ~$1B name with a thin book,
price can print through the level on size we cannot get, or gap past it entirely. On a $100B name
the same limit fills without thinking about it. **Today the exit stack treats every name the same.**

- ETON DID fill at $59.58 — so this is not a post-mortem on a miss. It is that the fill was never
  as certain as the design implicitly assumes, and we should not read one fill as proof it will
  repeat on the next small-cap.
- ⚠ **This makes the OCO MORE important on exactly these names, not less.** The no-fill branch is
  likeliest where the float is smallest, which is precisely where an unprotected third would sit
  longest.
- **Unmeasured and worth measuring** (cheap, from data we already hold): fill rate of the +2R
  resting limit, split by market cap / average dollar volume / float. If small caps systematically
  fail to fill at the limit, the 2R take on those names needs a different instrument, not a
  different price.
- ⚠ Do NOT tune a threshold off this note. It records a VARIABLE the design currently ignores; what
  to do about it is a detection/exit-criterion question = CHANGE_PROCESS + operator sign-off.
