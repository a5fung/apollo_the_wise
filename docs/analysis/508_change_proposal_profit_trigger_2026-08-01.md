# CHANGE PROPOSAL — replace the day-3 time gate with a +2R profit trigger

**Status: PROPOSED — awaiting operator sign-off. NOTHING SHIPPED.**
**Prepared 2026-08-01 per `docs/setups/CHANGE_PROCESS.md`.**

---

## ⚠ Two process items to resolve before this can ship

**1. There is no SSoT file for exit discipline.** `docs/setups/` covers detection setups and
portfolio safeguards; the profit-taking rule lives only in `broker/exit_logic.py` and in analysis
docs. CHANGE_PROCESS rules 6 and 7 require an SSoT to update in the same commit. **This proposal
therefore includes creating `docs/setups/exit_discipline.md`**, with this change as its first
change-log entry and the day-3 rule backfilled as the prior state.

**2. CHANGE_PROCESS rule 5 says field-validate before live** — *"Shadow phase or paper-only first…
Live promotion requires the 'shipped + validated against [N] live sessions' status."* The operator's
proposal is to ship live now. **These conflict, and it is his call, not mine.** The options:

- **(a) Follow rule 5** — run the new rule in shadow/paper for N sessions, then promote. Cost: the
  incumbent (worth +0.09R/trade) stays live meanwhile, and at ~1.5 trades/week a meaningful N is
  weeks away.
- **(b) Ship live on sign-off**, treating the 36-trade replay below as the field validation. The
  argument: the rule being replaced has **fired once in twelve live trades**, so there is almost no
  live behaviour to validate against, and the replay already exercises the exact fill mechanics.
- **(c) Hybrid** — ship live but with a pre-committed reversion trigger (below), so the live phase
  *is* the validation with a defined abort.

I am not choosing. **(c) is what the rest of this document is written for**, because it is the only
one that both ships and keeps rule 5's intent.

---

## The change

**FROM** (`broker/exit_logic.py:300-303`, deployed):
```python
if hold_days >= 3 and not partial_taken and entry_price:
    take_partial = (hold_days <= 4 and bar_close > entry_price) or hold_days >= 5
```
Take 1/3 at hold-day 3-4 **only if the close is above entry**; at day ≥5 take it **unconditionally,
even underwater** — which arms breakeven and, with breakeven above an underwater close, closes the
remainder in the same step (a de-facto day-5 full time-exit). `hold_days` is **calendar** days from
`alert_date`, so a Friday entry reaches day 3 on its second trading day.

**TO**: take 1/3 when the position first trades at **entry + 2 × risk_per_share**, then move the stop
to breakeven. Time-based partial removed.

## 🔴 IMPLEMENTATION GAP — found by the operator 2026-08-01, and it changes the build

**The deployed exit path is DAILY-CLOSE ONLY, but the replay modelled an INTRADAY limit fill.**

Verified in code: `exit_logic.py` is *"pure **daily**-exit-step decision logic"* (line 1);
`apply_daily_exit_step(state, daily_bar, ...)` takes **one daily bar**; `live_tracker.py:549` fetches
`get_index_history(ticker, today, today)` — today's daily bar — and the partial condition tests
**`bar_close`**, not the day's high. The job runs once at 3:45 PM ET.

**So a +2R rule dropped into the existing machinery would fire only if the trade is still ≥+2R at
3:45 PM.** On this cohort that is close to never: trades round-trip inside day one (MANE touched
+7.92R intraday and closed −0.23R). The replay's contract is explicitly a resting limit —
*"fill AT the trigger price… an in-hold peak ≥ trigger guarantees a limit fill"* — so **the +0.47R
in the evidence table is only achievable with an intraday mechanism. Implemented on the daily close
it would capture a small fraction of it, and the proposal's headline number would be wrong.**

**Correct implementation: a resting broker-side limit order for 1/3 at `entry + 2 × risk`, placed at
entry time**, alongside the existing bracket. That matches the replayed contract exactly, needs no
intraday polling, and fires on the touch rather than at 3:45 PM.

⚠ **This is a bigger change than the daily-close version and its risks are different:**
- The current entry is an OTO bracket (entry + stop). Adding a profit leg makes it a three-leg
  order, and **the stop's quantity must reduce when the profit leg fills** or the position is
  over-protected/under-protected. That interacts with `#184`'s stop-pointer mirror and the
  `extract_stop_leg_id` path.
- Partial fills of the profit leg (odd lots at 1-53 shares live) need defined handling.
- It touches order submission, not just an EOD decision — i.e. `broker/` code on the money path.

**Consequence for sign-off: the "one config flag" reversion claim below is TOO OPTIMISTIC for this
version.** Reverting a resting-order design means cancelling live legs, not flipping a boolean. That
should be part of what is being signed.

**Unchanged**: position sizing, the initial ORB-low stop, the SMA trail (day ≥10), the time-stop,
every portfolio safeguard, and the 9M Day-2 path.

---

## Required fields

**Trigger.** Operator, 2026-07-30: *"+3R is a good spot to take partial profit, 1/3rd at 3R then move
stop to breakeven — however, this requires R to be set correct."* Sharpened 2026-08-01: the day-3 gate
"may not be optimal" because trades die before reaching it. Confirmed in data — see Evidence.

**Evidence.** N=36 magna53 closed trades (12 live, 24 paper), all 34 candidate rules replayed under a
conservative fill contract (limit-at-level fills, breakeven stops that gap through, bar-by-bar replay
where minute data covers the day, pessimistic tie-breaks on ambiguous intra-day ordering). Engine
`scripts/probes/_508_exit_rule_replay.py`; every figure independently recomputed twice, once by a
reviewer who reimplemented the contract from prose and matched to the digit.

| rule | live fires | live Δ/trade | paper fires | paper Δ/trade |
|---|---|---|---|---|
| **incumbent (day 3)** | **1 of 12** | **+0.09** | 7 of 24 | +0.36 |
| **1/3 at +2R → BE** | **4 of 12** | **+0.47** | 8 of 24 | +0.27 |
| 1/3 at +3R → BE | 3 of 12 | +0.41 | 6 of 24 | +0.29 |
| 1/3 at +1R → BE | 4 of 12 | +0.36 | 9 of 24 | +0.37 |

Supporting facts: live trades hold **1.50 days** on average; **1 of 12** has ever reached day 3;
**zero partials have ever fired on live money**. Four live trades reached ≥+2R and all four
round-tripped (MANE +7.92R → −0.23R).

⚠ **Evidence limitations, stated rather than buried:**
- **The live cohort has zero winners.** Every measured gain is loss-reduction, not profit-banking.
- **On PAPER the incumbent beats this proposal** (+0.36 vs +0.27) — and paper is the only cohort
  containing winners. The case rests on live, where the money is.
- Paper is confounded twice: 22 of 24 are Bull-regime, and 19 of 24 predate the 2026-06-05 ORB-window
  fix (fills as late as 11:35 ET that the current system cancels at 10:00).
- Recorded peaks are **floors** — the instrumentation is blind under ~10 minutes, so the true fire
  count is ≥ the numbers above, never less.

**Anticipated effect.** Concrete and falsifiable:
- Partial fires on roughly **1 in 3 live trades** instead of 1 in 12.
- Expected ≈ **+0.47R per trade** on a cohort resembling the last 12 — about **+$9/trade** at the
  current ~$18.5 per R.
- Full −1R losses should fall from 10-in-12 toward ~6-in-12; the loss distribution gains a cluster
  near −0.33R (the 1/3-at-+2R-then-breakeven outcome).
- **No change to win rate.** This does not make losers into winners; it makes some of them smaller.

**Reversion-flag: REVERSAL of the 2026-03-27 "v2 rules" decision.** ⚠ **Corrected 2026-08-01 — an
earlier draft called this NEW and said the day-3 gate was undocumented. Both wrong.** The operator
wrote the rule himself (commit `bbbd442`) and documented it in `EP_TRADING_RULES.md` §B5: *Day 1-2
hold full · Day 3-4 sell 1/3 only if in profit · Day 5 sell 1/3 regardless.* It is Qullamaggie
methodology — hold through the early noise, let the move develop, take profit into strength.

**So CHANGE_PROCESS r4 applies: a reversal must explain why the prior reasoning was WRONG, not merely
incomplete.** The honest statement is narrower than "wrong":

- The prior reasoning assumes trades SURVIVE to day 3 to be reduced. That assumption held in the
  paper/backtest population it was designed against (mean hold 3.17 days, 9 of 24 reached day 3).
- It does not hold for the live population: **mean hold 1.50 days, 1 of 12 ever reached day 3, zero
  partials ever fired.** The rule is not mis-specified; it is **inapplicable** to how these trades
  actually behave.
- That is a change in the FACTS, not a defect in the original judgement — which is exactly why this
  should be reversible if live holds lengthen. If the strategy's holds return to 3+ days, the day-3
  rule becomes applicable again and this reversal should be revisited.

**Status: proposed, awaiting operator sign-off.**

---

## Pre-committed reversion triggers (option (c))

Written before shipping so the abort is not a judgement call afterwards:

1. **Any trade where the partial fires and the remaining 2/3 is stopped at breakeven while the trade
   subsequently trades ≥ +4R that same session.** One occurrence = review; two = revert. This is the
   cap-the-runner failure, and it is the specific risk the live cohort could not measure.
2. **Realized R over the next 10 closed live trades worse than the same 10 replayed under the
   incumbent.** The replay scores both counterfactually on every trade, so this is measurable without
   any extra instrumentation.
3. **Reversion cost.** ⚠ Depends on the implementation above: a daily-close version is one config
   flag, but the resting-limit version — the only one that delivers the modelled +0.47R — requires
   cancelling live profit legs on open positions as well. Plan the revert as an operation, not a
   toggle.

## Notification coverage — checked 2026-08-01, and there is a gap

**What DOES reach you today:**
- Broker-side fills, partial fills, stop fills, cancels and rejects — `trade_stream.py` has 23
  Telegram sites, incl. `📊 Partial fill: {symbol}`. So when a profit leg actually fills at the
  broker, you are told.
- Regime **flips** (label change / EP-filter change) surface in the evening brief's regime block.
- Review triggers T1 and T2 escalate on their own (nightly 17:30 ET).

**What does NOT reach you, and should before this ships:**
- ⚠ **`run_partial_exits` — the 3:45 PM partial job — contains ZERO Telegram calls.** Verified. Its
  scheduler wrapper only logs (`scheduler.py:1417-1427`) and notifies on *failure*. So a partial that
  the SYSTEM decides to take is announced only as a downstream broker fill, with no message saying
  *why* it fired or at what level. On a rule whose whole point is "take profit at +2R", the decision
  itself should be announced, not just its execution.
- ⚠ **No trigger fires on a WINNER.** Nothing watches for the first profitable live close — which is
  the single event that would most change this analysis (it is what unlocks §3.3, partial-vs-full).
- ⚠ **No trigger fires on a regime CHANGE per se** — the brief reports it, but nothing links a regime
  flip back to "the exit review's regime cell just became reachable".

**Recommended to ship WITH the rule (all no-money, observability only):**
1. Telegram on every profit-take decision: ticker, trigger level, R at fire, shares taken, new stop.
2. A `first_live_winner` data-gated review — fires the first time a live trade closes green.
3. Extend T2's review to also fire on a regime flip INTO Bull while live positions exist, so the
   regime cell being reachable is announced when it happens rather than at n=20.

## What continues unchanged either way

The recorder logs peak, give-back and capture on every closed trade **regardless of which rule is
live**, and the replay scores all 34 candidates counterfactually. **So shipping this does not cost us
the comparison** — the incumbent keeps being evaluated as a counterfactual on every new trade. That
is the technical fact that makes the operator's "ship one, keep observing the other" proposal work
without a shadow deployment.

Triggers T1 (n=20 closed live) and T2 (n=4 live Bull) continue to fire on their own schedule.

## What this does NOT claim

The shadow ORB control — same alerts, same gates, **no broker** — shows **zero winners across bull
AND correcting months** (n=16 closed). So the strategy's problem is very likely upstream of exits.
**This change makes losses smaller. It is not expected to make the strategy profitable**, and it
should not be signed off on that basis.

---

## If signed, the ship sequence

1. Create `docs/setups/exit_discipline.md` (SSoT) with this entry and the incumbent backfilled.
2. Implement in `exit_logic.py`. ⚠ Correction to an earlier draft of this line: the existing
   `scale_fraction` parameter controls the partial's SIZE, not its trigger, so it cannot carry this
   change — the trigger needs its own flag, with the day-3 branch left reachable so reversion is a
   config change rather than a code revert.
3. Backtest through the #151 harness — CHANGE_PROCESS rule 1 (N≥10; we have 36).
4. Tests pinning: fires at +2R not before, breakeven arms after, no double-partial, 9M Day-2 path
   untouched.
5. Deploy market-agent **and** execution — verified: `broker/exit_logic.py` is in
   `scripts/exec_loaded_modules.txt`, so `deploy.sh execution` is required or the change ships
   silent-dark. Pre-open, and read the delta first.
6. Verify-live on the first qualifying trade; record it against the pre-committed triggers above.
