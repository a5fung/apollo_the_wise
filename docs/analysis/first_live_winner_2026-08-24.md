# first_live_winner — what a profit-take rule actually cost on the first two live winners (2026-08-24)

**MEASUREMENT ONLY. Nothing changed. Exit discipline, profit-taking and stops are the operator's
sole authority (THE LINE); every fork below is his, not a recommendation.**

Closes the gated review `first_live_winner` (armed 2026-08-04, ready 20 days, never read). Its
premise: *every exit candidate scored so far has been measured against LOSING trades only, so the
cost of a profit-take rule — what the remaining two-thirds gives up when a trade RUNS — has never
been observed on real money.* It has now been observed once.

## ⚠ Read the era caveat first — it decides which numbers transfer

Both winners were **entered under the old ORB-low stop**. The `entry − 2R` stop went live
2026-08-16 (first live fill AMLX 08-18). What that change did, and did not do:

| | old era (both winners) | 2R era (today) | transfers? |
|---|---|---|---|
| the price the +2R partial fires at | `entry + 2×(entry − ORB low)` | **identical** — the target is ORB-anchored, not stop-anchored | **YES** |
| the placed stop | ORB low | `2×ORB low − ORB high` | no |
| what one "R" means | entry − ORB low | ~2× that distance | **NO** |
| shares | full | about half | no |
| dollar risk per trade | budget | same budget | yes |

- **The trigger price does not move.** `magna53_ep.md` 2026-08-16 §3 is explicit and prod-verified:
  the +2R target stayed on the ORB frame precisely so it would not silently become +4R. So
  **anything stated as a price, or as a multiple of the ORB range, carries over unchanged** — and
  that includes the headline cost below, which is a difference between two fill prices.
- **Anything labelled "R" does not carry over.** Under the new stop, PLTR's peak relabels from
  **+5.39R to +2.80R** and ETON's from **+2.09R to +0.99R** — same price paths, bigger R. Any count
  of "trades that reached +2R" roughly halves at the switch. ⚠ Keep the two frames apart: the LIVE
  +2R partial is ORB-anchored, so it still fires on an ETON-shaped trade; a candidate written in
  **placed-stop R** (which is what the replay engine means by `R2`) would not fire on it at all.
- The multiplier is **not exactly 2×** — it is 1.93× on PLTR (the fill chased $0.42 above the ORB
  high) and 2.11× on ETON (the fill landed $0.24 below it). Chase and slippage move it either way.
- **A replay candidate named `R2` run on any post-08-16 trade is a different rule** from the one
  that is live, because the engine defines R off the placed stop. That mismatch does not affect
  this document (both winners predate the change) but it will affect the next cohort run.

## Data

- One read-only prod capture, 2026-08-24: `scripts/probes/_508e_winner_capture.sql` →
  `_508e_winner_capture_out.psv` (trades, exit legs, orders, full audit trail), plus
  `_508e_winner_bars_out.csv` (**complete RTH minute bars** — PLTR 08-04→08-20, ETON 08-14; 5,460
  bars) and `_508e_winner_fwd_daily.psv`. Captured once, read many.
- Replay engine `_508_exit_rule_replay.py` reused **unchanged**, pointed at the 2026-08-22 snapshot
  (copied to `scripts/probes/_508e_winner_2026-08-24/`). That snapshot was verified equal to prod
  today — 53 records then and now, and both winner rows match prod field for field.
- Arithmetic: `scripts/probes/_508e_first_live_winner_2026-08-24.py` →
  `_508e_first_live_winner_out.txt`.
- The two winners: **PLTR** (trade 307, entered 08-04, closed 08-19, +$118.60, +3.42R) and **ETON**
  (trade 367, entered and closed 08-14, +$19.32, +0.52R). The three open positions (ABCL, AMLX,
  MRNA) are not closes and are excluded.

## Result 1 — the minute bars confirm both recorded peaks; nothing was hidden

The review asked for minute-bar reconstruction because the peak recorder is blind under ~10 minutes.
**On these two trades it was not blind, and the reconstruction changes nothing.**

| | true in-hold high, minute by minute | when | recorded peak | agree? |
|---|---|---|---|---|
| PLTR | **$180.18** | 08-14 09:32 ET, session 9 of 12 | $180.18 | exact |
| ETON | **$59.79** | 08-14 09:32 ET, **1 minute after the fill** | $59.79 | exact |

- The high-water marks in dollars: PLTR was **$186.75 up** at its best and booked $118.60 — it gave
  back **$68.15**. ETON was **$78.01 up** ninety seconds in and booked $19.32 — it gave back **$58.69**.
- ETON is the "peak unreadable" shape the review worried about (14 minutes, 14 bars) and it still
  read correctly, because the peak landed inside the recorded window.

## Result 2 — the headline: on PLTR, taking a third off at +2R cost **$9.40**, or 7% of the trade

PLTR is the **only** trade of the two on which a profit-take rule can be priced, because it is the
only one with a real do-nothing baseline (below). One R on the whole position was **$34.65**.

- **What would have happened with no rule:** the ORB-low stop at $143.28 was **never touched after
  the fill** (lowest print in twelve sessions: $145.59). All 6 shares ride to the trailing stop that
  actually closed the trade, $170.3875 on 08-19 → **+$128.00, +3.69R**. **This baseline is observed,
  not modelled** — verified in code, not assumed: `exit_logic.apply_daily_exit_step` raises the stop
  to the SMA10/20 trail unconditionally (line 375) and the breakeven branch is a *separate* max()
  applied after it. Only the opt-in `sma_10_20_handoff` mode consults `partial_taken`, and the live
  caller never passes it. So without the partial the stop still trails the identical ladder and the
  trade still closes at $170.3875.
- **What actually happened:** 2 shares out at $165.6895, 4 out at $170.3875 → **+$118.60, +3.42R**.
- **The rule therefore cost $9.40 — 0.27R, or 7% of what the trade was worth.** That is the first
  time the cost side has ever been read off real money.

Two things sit behind that small number, and both matter:

- **The partial fired a day late and the delay was worth +$10.17.** The +2R target of $160.6035 was
  first touched **08-04 at 12:13 ET**; the system tried to act at 12:15, 12:20 and 12:25 and
  **aborted all three times on a broker API error** ("replacement stop rejected"), then three more
  times on 08-05 morning, finally filling at **08-05 09:45 ET at $165.6895** — $5.09 per share above
  its own target, because PLTR kept going.
- **Had it filled on time, the cost would have been $19.57 (0.57R, 15% of the trade)** — a little
  over twice as much. **The rule working as designed is the more expensive number; use $19.57, not
  $9.40, when pricing the rule.**

## Result 3 — what every candidate rule would have given up on PLTR

Baseline = riding to the trail stop, **+3.69R / +$128.00**. "Cost" = what the rule hands back.
Full table in `_508e_first_live_winner_out.txt`; the spread of the family:

| candidate rule | keeps | cost in R | cost in $ | % of the trade |
|---|---|---|---|---|
| breakeven-only after +1R or +2R (no shares sold) | +3.69R | 0.00 | **$0.00** | 0% |
| 1/3 off at +3R, then breakeven | +3.46R | 0.23 | **$8.02** | 6% |
| **1/3 off at +2R, then breakeven — the deployed rule** | +3.13R | 0.57 | **$19.57** | **15%** |
| 1/3 off at +1R, then breakeven | +2.80R | 0.90 | **$31.12** | 24% |
| 1/2 off at +2R, then breakeven | +2.85R | 0.85 | **$29.35** | 23% |
| **exit ALL at +3R** | +3.00R | 0.69 | **$24.06** | 19% |
| **exit ALL at +2R** | +2.00R | 1.69 | **$58.70** | **46%** |
| exit ALL at 1 average daily range | +1.18R | 2.51 | **$87.07** | 68% |

- **The cost is monotone in how much you sell and how early.** Nothing here is a surprise
  mechanically; what is new is that the numbers are real dollars from a live account.
- **The trade paid its rent long after every trigger.** +2R was first cleared at 12:13 on day 1, +3R and +4R
  on day 4, +5R on day 5, and the high came on day 9 of a twelve-session hold. Every rule that
  sells at +1R to +3R is selling inside the first third of the trade's life.

## Result 4 — this is the first live evidence on partial vs full exit (state doc §3.3), and it points the other way

§3.3 has been undecidable because **no live trade had ever run**, so full exits scored best purely
by cutting losers. On the 15 old-era live trades the replay still says full-exit-at-+2R beats
partial-at-+2R by **+4.20R**. But:

- **On PLTR alone the partial beats the full exit by +1.13R** — the full exit banks +2.00R and
  walks away from a trade that delivered +3.69R.
- **About 3.7 more PLTR-shaped winners flips the ranking.** The EP profitability program's own
  sufficiency target is ~4 converted tail winners. Those two numbers landing on top of each other
  is worth the operator's attention: the exit rule that looks best today is best *only* at the
  current winner rate.
- **This does not decide §3.3.** It converts it from "no evidence exists" to "one data point exists
  and it favours the partial." That is the review's stated purpose and the limit of what it earned.

## Result 5 — ETON prices something else entirely: the breakeven leg, not the partial

ETON cannot price a profit-take rule, for a concrete reason: **there is no do-nothing baseline.**
The ORB-low stop at $53.01 was never touched (lowest print after the fill: $53.88), so without the
rule the position was simply still open. What the data does show is sharper than a cost estimate:

- **09:31:02** fill, 17 shares at $55.2012. **09:32** high $59.79 — the whole move, in one minute.
- **09:35:01** the +2R trigger fires at $59.58. It places a **resting limit** for 5 shares — and in
  the same step **arms a breakeven stop at $55.2012 on the other 12**.
- **09:45:11** the breakeven stop fills 12 shares at $55.05. The trade is over in 14 minutes.
- **15:58:02** — six hours and twenty-three minutes later — the resting 5-share limit finally fills
  at $59.58, on a minute whose high was **$59.59** in our own bar store — one cent of headroom.
  ⚠ That store is IEX by default, so the consolidated tape may have printed higher and the penny may
  be a thin-feed artifact; do not lean on the exact margin. What is not an artifact: a resting limit
  sat unfilled for six hours and filled in the last two minutes of the session.
- **ETON then ran.** It closed $61.73 (08-17), $63.43 (08-18), $63.47 (08-21) — **+3.77R**. The 12
  shares scratched at breakeven would be worth **$101 more** at the last close (unrealised, a mark,
  not an observation).

**What ETON CAN answer — which trigger levels it would have reached at all.** Its peak of $59.79
clears +1R ($57.39) by $2.40 and +1.5R ($58.49) by $1.30, but clears the **+2R target of $59.5836 by
only $0.21 — 0.09R**. **+2.5R and above never fire on it.** So ETON banked at +2R off twenty-one
cents of margin: a rule set one-tenth of an R higher takes nothing off this trade, and its entire
realised profit disappears. That fragility is the honest content of an N=2 sample.

**Plainly: on ETON the profit-take did its job and the breakeven stop attached to it threw away the
runner.** The rule that cost money here is *breakeven-after-partial*, which the replay grid scores
as free (`R1_BE_only` and `R2_BE_only` both cost $0.00 on PLTR, because PLTR never came back to
entry). ETON is the case where it is not free, and no candidate in the 34-rule grid separates the
two halves of the deployed rule.

## Result 6 — three live firings now exist and they still disagree in sign

The review complained the cost/win column rested on 2 paper trades that disagree in sign. The
deployed +2R partial has now fired on live money **three times**, and they also disagree:

| trade | date | what the partial did | net effect of the rule |
|---|---|---|---|
| **PLTR** | 08-04→08-19 | sold 2 of 6 a day late at $165.69 into a run to $180.18 | **cost $9.40** (as designed, $19.57) |
| **FIGS** | 08-07 | sold 20 of 61 at $15.84, the other 41 stopped at $15.16 | **saved $13.60** (a loser, −$6.84 instead of −$20.44) |
| **ETON** | 08-14 | banked 5 of 17 at the +2R target, breakeven ejected the other 12 | **banked $21.89, its breakeven leg gave up ~$101** |

- The sign disagreement is **reproduced on real money, not resolved.** That is the honest answer.
- FIGS is included as context only — it is a loss, not a winner — but it is the third live firing
  and it is the one that shows the rule paying for itself.

## Data defect found (reported, not fixed)

**ETON's booked P&L is $0.76 too low.** `mi_live_trades.exits` records the stop leg as **17 shares**
at $55.05 — the whole position — while `mi_live_orders` shows that stop order filled **12**. The
partial's 5 shares are counted twice against the loss (the audit line even prints
`remaining -5`). Booked $19.3236 / +0.5187R; true **$20.0796 / +0.5390R**. It flows into
`mi_sell_discipline_records`, so every cohort figure quoting ETON inherits it. Under-states a
winner by 4% — small here, but the same double-count on a bigger partial would not be.
Not touched by this task; it belongs to the main session.

## ⚠ What this does NOT answer

- **Which trigger level is right.** One winner cannot rank +1R / +2R / +3R. It says only that on
  *this* trade every level below +3R sold into the first sixth of the move.
- **Anything about the 2R-stop era.** Both winners predate it. No live trade entered under the new
  stop has closed green yet; the first three 2R-era fills are MRVL (closed, −0.95R) and two still
  open. The whole cost table above is denominated in old-era R.
- **Whether the deployed rule is net-positive.** Three firings, two green closes. The repo's own bar
  for a criterion change is **N≥10** and this is nowhere near it.
- **What ETON's twelve shares were really worth.** They never exited; $101 is a mark at an arbitrary
  date, and ETON was $59.91 on 08-20 and $63.47 on 08-21 — the number moves 30% day to day.
- **Whether breakeven-after-partial should be conditioned on anything.** ETON says it can be
  expensive; PLTR says it was free. Two trades, opposite readings, and no candidate rule in the grid
  currently isolates it.
- **Whether the broker-side execution defects matter.** The PLTR partial aborted six times over two
  sessions and the ETON partial sat unfilled for six hours while a `position_unprotected` gap ran.
  Both happened to end well. Neither is measured here.
- **The unit question** (state doc §3.2, R vs daily range) was deliberately not re-opened — it has
  its own gate.

## What this means

1. **The cost side finally has a real number: about 15% of a winner, at the rule as designed** —
   $19.57 of a $128 trade, or $9.40 as it actually executed. It is smaller than the exit debate has
   been assuming, and it is the first non-hypothetical figure in that column.
2. **Exiting the whole position at +2R would have cost 46% of the one trade that worked.** The
   candidate that ranks first on a cohort of losers ranks worst on the winner. That is §3.3's
   evidence, one data point deep, and it favours the partial.
3. **The live risk is no longer only the profit-take — it is the breakeven stop it arms.** ETON was
   ejected at breakeven in 14 minutes and then ran to +3.77R. Nothing in the current 34-rule grid
   prices that leg separately.
4. **Operator forks, stated and not pre-decided** — (a) whether the +2R partial level should move
   now that a winner exists to price it against, (b) whether breakeven-after-partial should arm
   immediately or wait, given ETON, and (c) whether either should wait for the 2R-era cohort, since
   neither winner is in it. **No change is proposed; all three are his call under CHANGE_PROCESS.**
5. **Housekeeping for the main session:** the ETON $0.76 exit-leg double-count above, and the fact
   that the replay engine's `R2` candidate no longer means the live rule for post-08-16 trades —
   both worth filing before the next cohort run.
