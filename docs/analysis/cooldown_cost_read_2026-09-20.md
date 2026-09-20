# What the 60-day EP cooldown actually costs — and why the weekly review's numbers overstate it

**2026-09-20. Read on his instruction after the Sunday review put four cooldown-blocked names at the
top of the should've-entered table. ⚖ REPORTS ONLY — the cooldown is a safeguard, THE LINE. Nothing
here changes a rule; it exists so a ruling rests on the right number.**

## Method and population — which rows, over what window, derived how

**Population, DERIVED not listed:** every row in `mi_ep_missed_outcomes` with
`skip_category = 'cooldown'` and `alert_date >= CURRENT_DATE - 60`, i.e. 2026-07-22 to 2026-09-20.
`skip_category` is the machine key; the weekly review renders it as the label "60-day cooldown"
(`missed_outcomes.py:1354`). The underlying `skip_reason` on every row reads *"EP cooldown —
alerted within last 60 days"*, which is the per-ticker re-alert cooldown and is NOT the
circuit-breaker cooldown (`live_tracker.py:308`, `CIRCUIT_BREAKER_COOLDOWN_DAYS`). The two are
different mechanisms that both print the word cooldown, and the first version of this read counted
the wrong one.

**n = 26** rows carrying a non-null `max_high_5d`. `ret_5d` is null on the most recent names
(RPD 2026-09-14 has not settled), so the return figures are over the settled subset.

**Peak** is `max_high_5d`, which is stored as a RATIO (AEHR 2026-09-04 = 0.3175 → +32%), not a
price. **5-day return** is `ret_5d`, likewise a ratio.


## THE HEADLINE

**The cooldown's cost is PEAK-shaped, not RETURN-shaped.** Over 60 days, 26 blocked names with
settled outcomes:

| measure | value |
|---|---|
| average peak (`max_high_5d`) | **+12%** (n=26) |
| average 5-day return (`ret_5d`) | **−0%** (n=26, settled subset) |
| closed positive at 5 days | **10 of 26 (38%)** |
| peaked ≥10% intraday | 13 of 26 (50%) |

Half the cohort touched +10%. The average one gave all of it back.

## THE FOUR NAMES THE REVIEW LED WITH

| ticker | date | peak | 5-day |
|---|---|---|---|
| ALOY | 2026-07-29 | +47% | +25% |
| AEHR | 2026-09-04 | +32% | +7% |
| IREN | 2026-07-30 | +30% | +17% |
| RPD  | 2026-09-14 | +22% | *not settled* |

The review's table shows the PEAK column. That is the correct thing for a should've-entered
surface to rank on — it is sized opportunity — but it is not what a trade would have returned, and
reading it as a cost is the error.

## WHY THIS IS NOT A CLOSE CALL — WE ALREADY PAID FOR THIS LESSON ONCE

On 2026-08-22 the extension cap was loosened 50% → 75% on exactly this kind of evidence: names in a
blocked band with big forward numbers. It was **reverted seven days later**, operator-signed, after
#595 showed `mi_ep_missed_outcomes` was crediting names whose pre-market spike faded before the
open. The corrected re-run cut the band's winners 21 → 12, and — the part that matters here —
replayed through the LIVE bracket on minute bars, **the band returned −1.00R on 15 of 15 (n=15). Five of
those names ran 2.9R to 15.2R and every one still paid −1R**, because the 9:30 bar's low was taken
out first.

`ep_detector.py:249` records that conclusion in its own words — **THE CAP IS NOT THE BINDING
CONSTRAINT, THE STOP IS** — ⚠ **but that half has since been corrected and must not be repeated.**
The 08-29 doc flags its own geometry paragraph as wrong (*"its premise is true but the conclusion
is wrong"*), and the document written to correct it,
`docs/analysis/482_geometry_counterfactual_2026-08-29.md`, is **RETRACTED at the top: "DO NOT CITE
ANY NUMBER IN THIS FILE."** Replaying our real trades under five stop geometries put all five
within 0.08R of each other, all negative, with the LIVE one best — so widening the stop does not
recover these names either.

**So what IS the lever is an open question, not a settled one.** What survives from 08-29 is the
narrow replay finding — the 50-75% band paid −1.00R on 15 of 15 on real minute bars — and that is
enough to say a peak-based read overstates. It is not enough to say geometry is the answer.

A peak-based read of the cooldown is the same shape of evidence that produced that reversal.

## RECOMMENDATION

**Do not rule on these numbers.** They are directionally interesting and they are not a cost.

**What would settle it — and it is more than a query, which is the honest answer.** A bracket
replay of the 26 is the obvious next step and it carries a KNOWN FATAL DEFECT if done naively.
The retracted 482 doc names it as its own defect 3: *"Every trade in it was ADMITTED by whatever
filter ran that day. Re-running the stops on that set measures the stop GIVEN A MIXED ADMISSION
POPULATION — which answers nothing."* Our 26 span 2026-07-22 to 2026-09-20, across the 2026-09-06
exit change and August's rubric rescale, so they have exactly that shape.

A replay worth ruling on therefore needs what that doc specifies and what does not exist yet:
re-score the historical universe under TODAY's rubric (the 08-22 rescale means stored `ep_score`
is era-stamped), re-apply today's admission stack to it, reconstruct entries and stops from
`mi_intraday_bars` for whatever survives, and hold live and paper separate. That is the #482 build.

**Recommendation, therefore: the cooldown question cannot be settled cheaply, and should not be
ruled on until #482's instrument exists.** What CAN be said today is the headline above — the cost
is peak-shaped, the average blocked name returned zero over five days, and the review's +32% is not
a number to act on.

⚠ **Stated limits.** `ret_5d` is null for the most recent names (RPD 09-14 has not settled), so the
38% positive rate is over the settled subset. `max_high_5d` is a RATIO in this table, not a price —
computing a peak as `max_high_5d / open_d0 - 1` returns ≈ −100% for every row, which is how this
read was wrong twice before it was right.

## What this does not answer

- **It does not say what the cooldown COST, and cannot.** Peak and 5-day return are both
  hold-to-a-date measures over n=26; neither is what the live bracket would have returned. The
  recommendation exists precisely because that number does not exist yet.
- **It does not cover the circuit-breaker cooldown** (`live_tracker.py:308`) — a different
  mechanism with its own blocked population, not read here.
- **It does not establish the counterfactual entry.** A name blocked by the cooldown might also
  have been stopped by a later gate; this read counts the FIRST recorded skip reason only, so
  "the cooldown blocked it" does not mean the cooldown was the only thing that would have.
- **n=26 is small and era-mixed.** It spans 2026-07-22 to 2026-09-20, across the 2026-09-06 exit
  rule change — so if these were replayed, the replay must split on era or say it did not.
  [[check-the-rule-era-before-comparing-to-actual]]
- **It says nothing about whether the cooldown is right.** Its purpose (not re-alerting the same
  ticker within 60 days) is a separate question from what the blocked names went on to do.
