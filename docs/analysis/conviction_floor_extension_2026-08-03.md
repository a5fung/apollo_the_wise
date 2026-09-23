# Conviction floor extension — gap[10,15) + strong catalyst: **DO NOT LIFT** (2026-08-03)

**Review:** `data_gated_reviews.yaml::conviction_floor_extension` (added 2026-04-29, predicate fired
41/15). **Read-only analysis. Nothing changed — the recommendation IS no change.**

## Question

Does the `gap ∈ [10,15) + catalyst='strong'` cell carry enough forward edge to justify lifting
MODERATE alerts in that band to a HIGH conviction floor at 55 / 58 / 60?

The review's own bar: **positive-label rate ≥ 35%** (label = 5-day return ≥ +10%), with a close
condition of *"if the 90d cohort retains the ~1/6 win rate, close as 'filter doing its job'."*

## Result — the current 90-day cohort

| cohort | n | labelled | ≥ +10% in 5d | rate | mean 5d | median 5d |
|---|---|---|---|---|---|---|
| all `conviction_floor_eligible` | 44 | 35 | 9 | **25.7%** | +4.18% | +0.93% |
| **MODERATE only** (the band in question) | 22 | 19 | 4 | **21.1%** | +1.88% | **−0.77%** |

**21.1% against a 35% bar → DO NOT LIFT.** Up from the 16% measured 2026-07-13, still nowhere near.

The **median is negative**. The band's typical name goes nowhere or down; the mean is carried by two
outliers (QBTS +38.5%, ASPI +30.6%) against losers of similar size (LAC −25.4%, CAMT −6.6%).
Four winners out of nineteen is close to the 1/6 prior the review said to close on.

This also agrees with the independent 2026-05-04 ORB simulation recorded in the review (n=6,
1 win, −3.01R): five of six closed green but stopped intraday — closing-price edge is not entry
edge, and this band is exactly where that gap bites.

## ⚠ A units trap, recorded because it nearly produced a false answer

`mi_ep_missed_outcomes` mixes units **in the same row**: `gap_pct` is a PERCENT (11.4 = 11.4%) while
`ret_1d` / `ret_5d` / `max_high_5d` are **FRACTIONS** (3.54 = +354%). The review's own
`--label-threshold 0.10` is in fraction units.

The first run of this analysis compared `ret_5d >= 10` and returned a positive-label rate of
**0.0%** — a clean, plausible-looking number that was wrong by 100×, and would have read as
"catastrophically bad band, close immediately". Caught only because 0.0% alongside a mean of 0.04
did not cohere. **Anything joining this table must state its units.**

## Caveats — stated, not resolved

- **n = 19 labelled**, 4 positive. The confidence interval is wide; this rules out a 35% rate, it
  does not resolve the band to a point estimate.
- **3 of 22 have no outcome row** and are excluded rather than assumed.
- **The dead-zone caveat from 2026-04-29 is NOT confirmed resolved.** Names in this band with thin
  pre-market share counts are systematically dead-zoned by the 9:30–9:44 raw rel_volume gate and
  only projected after 9:45, outside the ORB window. `scripts/backfill_dead_zone.py` exists; I did
  not verify the gate calibration shipped. **So the cohort may still under-count the band's best
  shapes** — which biases toward the answer given here, and is the one way this could be wrong.
- Return basis is close_d0 → close_d5, not an entry-to-exit R. The 5/04 simulation is the R-based
  read and it was worse, not better.

## Recommendation

**Close as "filter doing its job", threshold unchanged.** That is the review's own stated close
condition, and both independent reads (label rate now, ORB simulation in May) point the same way.

**Not recommended:** lifting to 55/58/60. Nothing in this cohort supports it, and the negative
median means a lift would admit more losers than winners at the margin.

**If it is ever revisited**, the honest re-open trigger is the dead-zone fix landing — not more
time. More of a biased sample does not answer the question the bias creates.
