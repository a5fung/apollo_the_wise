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

### 3. SMA trail — requires ≥10 daily closes, so it cannot act before day 10.

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
