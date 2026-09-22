# #327 — the delayed-entry watch lane, read on the first date it could be read honestly

**2026-09-22.** The task's own ETA was set to today because *"2026-09-22 = the first date the
earliest fires complete 20 sessions and the lane can be read honestly."* This is that read.

## Method and population

Every rule below was fixed by the task line BEFORE the numbers were seen, not chosen after:
settled 20-session outcomes only · **exclude `stop_width_pct < 0.5`** (the #621/#623 near-zero-stop
class that carries BCTX at 5499R) · **measure the TAIL, not the median** (`analysis_standard.md`
§THE STATISTIC).

**Population: every row of `mi_delayed_entry_trigger` — 3,652 fires across 697 tickers, fire_date
2026-08-25 → 2026-09-21.** Not a sample and not hand-picked: the lane writes one row per fire and
the read is `GROUP BY rung` over the whole table. 115 rows are removed by the near-zero-stop rule,
leaving 3,537; of those, **2,980 (84%) carry a non-NULL `r_trail_s20`** and are the settled
population every number here is computed on. The 557 unsettled rows are EXCLUDED, never counted as
losses — see "What this does not answer". The lane is a passive observer: it is not conditioned on
outcome, which is what distinguishes this read from the 2026-08-30 Stage-2/campaign studies.

## RESULT — all four patterns are negative, and none is close

| pattern | n settled | ≥3R | ≥2R | ≥1R | >0 | mean R | total R |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ep_close_620_prox` | 1021 | 12 (1.2%) | 23 | 50 | 154 (15%) | **−0.581** | −593.7 |
| `ep_close_reclaim` *(his idea)* | 769 | 9 (1.2%) | 19 | 35 | 92 (12%) | **−0.635** | −488.1 |
| `ep_high_break` | 181 | **0** | 1 | 6 | 30 (17%) | **−0.575** | −104.0 |
| `ep_low_reclaim` | 1009 | 9 (0.9%) | 19 | 35 | 125 (12%) | **−0.605** | −610.8 |

**Pooled: 30 of 2,980 reach 3R = 1.01%, against the 13% that #624 records as the healthy
reference.** Thirteen times below. Total −1,797R across the four.

## THE TAIL IS LARGELY AN ARTIFACT OF TIGHT STOPS

A narrow stop inflates R mechanically, so the tail rate was re-read at four stop-width floors.
It does not survive:

| stop-width floor | n | ≥3R | rate | mean R |
|---|---:|---:|---:|---:|
| ≥0.5% *(the task's own cut)* | 2980 | 30 | 1.01% | −0.603 |
| ≥1.0% | 2720 | 18 | 0.66% | −0.621 |
| ≥2.0% | 2123 | 10 | 0.47% | −0.623 |
| ≥3.0% | 1654 | 4 | 0.24% | −0.632 |

**Four of the six biggest winners are gone at a 2% floor** — RCT +9.58R (stop 0.62%), BZAI +7.15R
(0.95%), RGNX +5.67R (0.65%), CALC +5.13R (1.21%). Only ZCMD (2.31%) and ILLR (2.47%) survive.
The mean does not improve at any floor, so this is not a case of a good signal hidden behind noise.

## THE FINDING THAT POINTS SOMEWHERE — it is the STOP, not the entry

**The no-target arm (`r_none_s20`) reads exactly −1.00R with ZERO positives across all 2,980 rows,
in every one of the four patterns.** With no target, every single fire eventually reaches its stop.

That is not a statement about entry timing. It says the stop, as these patterns place it, is inside
the noise of the instrument — so the only thing that ever produces a positive outcome is a target
taking profit before the stop is reached. A better entry cannot fix that; a different stop might.

⚖ **That routes to #545 (the entry/exit tactics programme), not to killing the lane.** Recommending
against the goal on one test's null is the error `recommend-against-the-goal-not-the-test` names.

## What this does not answer

- **557 fires (16%) are unsettled and their outcome is UNKNOWN — not "not winners".** `mfe_r` and
  `mae_r` are NULL on every one of them (verified: 0 of 557 populated), so a count of
  "unsettled rows reaching 3R" is a non-discriminating zero, not evidence. What is true is that
  they are YOUNG — 5.7 to 8.5 sessions elapsed of 20 — so they are recent fires, not long-running
  positions, which is what defuses the original "the settled rows are the losers by construction"
  trap the task warned about.
- Nothing here re-prices the EP alert itself. This is the delayed-entry WATCH lane only.

## THE DECISION — his, not mine

The task's DoD ends *"→ then his call on whether any pattern graduates."*

**Recommendation: none of the four graduates, and none should be retired either.** Keep the lane
as the passive observer it is (it costs nothing and writes no trade state), and hand the stop-width
finding to #545 as an input — because the measured defect is stop placement, which is #545's
subject, not entry timing, which is this lane's.
