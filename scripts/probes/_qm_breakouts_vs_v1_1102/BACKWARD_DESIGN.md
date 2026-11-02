# Breakout v1 rebuilt from Qullamaggie's trades — the backward step (fixed BEFORE it runs, 2026-11-02)

His method (operator_shared_notes 2026-11-02, verbatim there): *"we need to get as close as possible, that is the starting
point and then work backwards from there to define our rules. If there's still gaps to the remaining few, I will review
their charts manually"* · *"if later you find his rules to introduce too many losers, I will review what they mean
manually as well via looking at samples"*. The scorecard is Qullamaggie's 269 dated breakout buys (holdings_1024/entries.tsv,
setup breakout|both, 2017-2023) and his 26 big winners among them (5R+ in his replay). **No R, book mean, win rate or
random thinning appears anywhere in this step.**

## Inputs
- The captured table (10_feature_table.py, one row per listable name-night, strength >= 30, eras A+B, nothing 2025+).
- The starting point S0 (11_starting_point.txt): history + universe + prior move kept, strength >= 35, range >= 2.1%,
  every shape rule off -> all 269 listed by construction.

## Split
- FIT = his buys with E in 2017-2020 (n ~162). CHECK = E in 2021-2023 (n ~107). Thresholds are chosen on FIT only.
  List size (names a night) is measured on all nights.

## A rule may be added only if (all four)
1. It drops at most **2% of his FIT buys** (<= 3 of ~162).
2. It drops **none of his 26 big winners** (any era).
3. It cuts the median names a night by **at least 5%** (relative to the list before it).
4. On CHECK it drops at most **4%** (else it is listed as "did not hold on the later years" and NOT added).

## Candidates (one-sided thresholds set at the value 98% of his FIT buys pass; two-sided bands where marked)
Strength rank (best of 1/3/6-month) · daily range (ADR20) · prior move size · base length (band) · base depth from the
pole top in daily ranges (band) · EMA21 rise across the base (G4 — matched every label on 11-02) · close vs EMA10 and vs
EMA21 in daily ranges · distance below the 52-week high · v1's surf / tightening / higher-lows VALUES as continuous
features (not their old pass rules) · dollar volume · price.

## Procedure
Greedy: at each step add the qualifying candidate with the largest names-a-night cut; recompute; stop when none
qualifies or when the total dropped reaches 10% of his buys. Every dropped buy is listed by name and date — those are the
charts that go to him.

## Reported each step
Rule + threshold · his buys kept (FIT / CHECK / all) · big winners kept · names a night (median / mean / 90th pct) ·
the buys it dropped by name.

## Secondary checks (stated, never deciding)
- MTW 2026-10-30 (his "no setup") — pass/fail under the final set (its 10-30 values from `_mtw_1102/q1.out` + bars).
- Qullamaggie's own 2020-08-10 calls on names on the list for 2020-08-07: MRNA and INO ("breaking down"), CDE (no setup on
  08-05/06) — pass/fail under the final set.
- If the final list is still large, samples of its non-his names go to him ("too many losers" -> his review), never a
  tightening chosen on returns.
