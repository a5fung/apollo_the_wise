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
4. **The strategy's problem is probably upstream of exits.** The shadow ORB control — same alerts,
   same gates, no broker — shows **zero winners across bull AND correcting months**. Exit changes
   make losses smaller; they are not expected to make the strategy profitable.

---

## Change log (newest first)

### 2026-08-01 — SSoT created; no behaviour change

**Trigger**: A proposed change to the profit-take rule (`docs/analysis/508_change_proposal_profit_trigger_2026-08-01.md`)
had no SSoT to update, which `CHANGE_PROCESS.md` r6/r7 require. Creating the file also surfaced that
the deployed rule's day-5 unconditional branch — a de-facto full time-exit — was undocumented and had
been mis-stated in analysis as "gates profit-taking at day 3".

**Evidence**: n/a — this entry documents existing behaviour, read directly from
`broker/exit_logic.py` at commit `6f8652d`. Measured columns above come from 43 recorded closed
trades, verified twice.

**Anticipated effect**: none. No code changed.

**Reversion-flag**: NEW.

**Status**: shipped (documentation only), no field validation applicable.
