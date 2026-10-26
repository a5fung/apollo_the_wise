# Generated tables — big-winner recall (03_report.py; n on every row)

## the +100% set (close at least doubled from the trough within 63 sessions)

### 2017-21, x200 — composition (n = 1,181 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 40, 2018: n = 55, 2019: n = 54, 2020: n = 889, 2021: n = 143 |
| tickers | n = 881 (episodes per ticker max 5) |
| close at the trough, $ (median, quartiles) | 16.81 (8.29 .. 35.91) (n = 1,181) |
| ADR20 at the trough (median, quartiles) | 0.083 (0.062 .. 0.107) (n = 1,181) |
| 63-session return into the trough (median, quartiles) | -0.30 (-0.59 .. 0.03) (n = 1,181) |
| gain trough → peak (median, quartiles) | 1.42 (1.14 .. 1.96) (n = 1,181); >= +200% n = 282 |
| sessions trough → peak (median, quartiles) | 56 (50 .. 73); peak extended past the 63-session window n = 421; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 12 / 30 (n = 1,181) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 105 (9%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 683 / 216 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 594 (50%) | 607 (51%) | 506 (43%) | 574 (49%) | 595 (50%) | 696 (59%) |
| ep_gap | 100 (8%) | 102 (9%) | 99 (8%) | 98 (8%) | 101 (9%) | 97 (8%) |
| late_base | 477 (40%) | 456 (39%) | 547 (46%) | 504 (43%) | 475 (40%) | 382 (32%) |
| no_consolidation | 5 (0%) | 7 (1%) | 2 (0%) | 2 (0%) | 5 (0%) | 5 (0%) |
| other | 5 (0%) | 9 (1%) | 27 (2%) | 3 (0%) | 5 (0%) | 1 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 100.

The measurable breakouts under the primary rule (n = 594): breakout day b − trough median (quartiles) 13 (7 .. 20) sessions; base length L 26 (17 .. 39); the base contains the trough 496 (84%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.4 (3.7 .. 5.0) ADR20; base depth 0.26 (0.22 .. 0.32); share of the episode's gain made at the close BEFORE b 0.11 (0.05 .. 0.17) and at b's close 0.18 (0.12 .. 0.25); the breakout close over the base high 0.39 (0.16 .. 0.89) ADR20; b opened with a gap of 1.7 (0.4 .. 4.5)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 192 (32%) of them — range ok 422 (71%), close location ok 438 (74%), volume ok 297 (50%).
The late-base episodes (n = 477): the first close above the longest base's high came when 0.50 (0.41 .. 0.62) of the gain was already made, b − trough 22 (16 .. 29) sessions, base depth 0.33 (0.28 .. 0.41), the base contains the trough 149 (31%).

### 2017-21, x200 — what we did

**2017-21, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 1,181 | 100% of 1,181 |
| with a measurable breakout (primary rule) | n = 594 | 50% of 1,181 |
| … whose base nights our watch covers | n = 586 | 99% of 594 |
| … WATCHED (a watch row on some base night) | n = 296 | 51% of 586 |
| … watched with a trendline level (C0_tl) on some base night | n = 296 | 51% of 586 |
| … watched on the night before the breakout day | n = 193 | 33% of 586 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 287 | 49% of 586 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 94 | 16% of 586 |
| … triggered and STILL IN at s50 (half the gain made) | n = 32 | 5% of 586 |
| … near the breakout and still in at s50 | n = 19 | 3% of 586 |
| … triggered and KEPT >= half of the episode's gain | n = 3 | 1% of 586 |
| … near the breakout and kept >= half of the episode's gain | n = 2 | 0% of 586 |
| … triggered and kept >= half of the gain available from the fill | n = 8 | 1% of 586 |

All 1,181 big winners, any class (covered n = 1,173): watched 473 (40%); triggered (tl fill in the catch window) 371 (32%); still in at s50 40 (3%); kept >= half of the episode's gain 5 (0%); a tl fill ANYWHERE in [trough − 20, peak] 909 (77%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 423 (36%).

**2017-21, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 586)

- NOT WATCHED on any base night: n = 290 (49% of 586). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 141 (49% of 290)
  - prior move < 30% (no pole) (`prior_move`): n = 97 (33% of 290)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 42 (14% of 290)
  - raw close under $5 (`universe_price`): n = 5 (2% of 290)
  - under $10M median dollar volume (`universe_dv`): n = 4 (1% of 290)
  - pole data artifact (`pole_artifact`): n = 1 (0% of 290)
  - on the night before the breakout day alone: `prior_move` n = 141; `sma50` n = 72; `universe_dv` n = 37; `close_above_pole_high` n = 32; `universe_price` n = 8
- WATCHED BUT NO TRIGGER in the catch window: n = 57 (10%); of them a trendline level existed on some base night (C0_tl) n = 57, watched on the night before the breakout n = 25, a tl fill came later anywhere before the peak n = 39, some other K filled in the window n = 24
- TRIGGERED: n = 287 (49%). Fills per episode in the window: median 1, max 7; retrigger rows as the first fill n = 23; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -6 (-23 .. 0); before b n = 195, on b n = 26, 1–5 after n = 22, later n = 44; share of the episode's gain already made at the fill: median (quartiles) 0.10 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 229 (80% of 287) — of which before the breakout day itself n = 158; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 26 (9%); still in at s50: n = 32 (11%); status split: stopped n = 118, stopped_day0 n = 111, trailed n = 49, time_exit n = 9
  - realized R of the catch: mean +1.94, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 37, >= 10R n = 21; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 23.1 (17.2 .. 30.2) ADR, the gain available from the fill = 20.5 (14.5 .. 27.3) ADR, the trade's P&L = -0.23 (-0.46 .. 0.28) ADR; kept share of the episode's gain median (quartiles) -0.010 (-0.021 .. 0.010), mean 0.032; kept share of the available gain median -0.010 (-0.023 .. 0.012); kept >= half of the episode's gain n = 3, >= half of the available n = 8, >= a quarter of the episode's gain n = 27
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 58; best fill's kept share of the episode's gain median 0.005 (-0.016 .. 0.056), >= half n = 5

Any-K view on the covered measurable breakouts (n = 586; the entry tables' ORH5 filled C0 rows, E in the catch window): com: 302 (52%), E − b median -7; tl: 287 (49%), E − b median -6.

#### 2017-21 without the 2020 troughs (2020 holds 889 of 1,181 episodes)

**2017-21 excluding 2020, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 292 | 100% of 292 |
| with a measurable breakout (primary rule) | n = 207 | 71% of 292 |
| … whose base nights our watch covers | n = 199 | 96% of 207 |
| … WATCHED (a watch row on some base night) | n = 102 | 51% of 199 |
| … watched with a trendline level (C0_tl) on some base night | n = 102 | 51% of 199 |
| … watched on the night before the breakout day | n = 71 | 36% of 199 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 98 | 49% of 199 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 34 | 17% of 199 |
| … triggered and STILL IN at s50 (half the gain made) | n = 8 | 4% of 199 |
| … near the breakout and still in at s50 | n = 4 | 2% of 199 |
| … triggered and KEPT >= half of the episode's gain | n = 1 | 1% of 199 |
| … near the breakout and kept >= half of the episode's gain | n = 1 | 1% of 199 |
| … triggered and kept >= half of the gain available from the fill | n = 4 | 2% of 199 |

All 292 big winners, any class (covered n = 284): watched 145 (51%); triggered (tl fill in the catch window) 126 (44%); still in at s50 13 (5%); kept >= half of the episode's gain 3 (1%); a tl fill ANYWHERE in [trough − 20, peak] 215 (76%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 148 (52%).

**2017-21 excluding 2020, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 199)

- NOT WATCHED on any base night: n = 97 (49% of 199). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 52 (54% of 97)
  - prior move < 30% (no pole) (`prior_move`): n = 24 (25% of 97)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 18 (19% of 97)
  - raw close under $5 (`universe_price`): n = 2 (2% of 97)
  - pole data artifact (`pole_artifact`): n = 1 (1% of 97)
  - on the night before the breakout day alone: `prior_move` n = 45; `sma50` n = 24; `close_above_pole_high` n = 13; `universe_dv` n = 12; `universe_price` n = 3
- WATCHED BUT NO TRIGGER in the catch window: n = 18 (9%); of them a trendline level existed on some base night (C0_tl) n = 18, watched on the night before the breakout n = 12, a tl fill came later anywhere before the peak n = 9, some other K filled in the window n = 10
- TRIGGERED: n = 98 (49%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 8; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -4 (-23 .. 1); before b n = 62, on b n = 11, 1–5 after n = 8, later n = 17; share of the episode's gain already made at the fill: median (quartiles) 0.11 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 79 (81% of 98) — of which before the breakout day itself n = 49; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 11 (11%); still in at s50: n = 8 (8%); status split: stopped n = 44, stopped_day0 n = 35, trailed n = 13, time_exit n = 6
  - realized R of the catch: mean +1.86, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 9, >= 10R n = 7; sessions held median 2
  - kept, in the trade's ADR unit: the episode's gain = 20.9 (16.2 .. 27.0) ADR, the gain available from the fill = 18.3 (14.1 .. 24.3) ADR, the trade's P&L = -0.22 (-0.36 .. 0.25) ADR; kept share of the episode's gain median (quartiles) -0.009 (-0.021 .. 0.012), mean 0.027; kept share of the available gain median -0.010 (-0.027 .. 0.014); kept >= half of the episode's gain n = 1, >= half of the available n = 4, >= a quarter of the episode's gain n = 8
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 15; best fill's kept share of the episode's gain median 0.001 (-0.014 .. 0.024), >= half n = 1

By trough year (measurable breakouts covered → watched → triggered → still in at s50 → kept >= half):

| year | big winners | measurable breakouts covered | watched | triggered | still in at s50 | kept >= half |
|---|---|---|---|---|---|---|
| 2017 | n = 40 | n = 30 | n = 12 | n = 13 | n = 0 | n = 0 |
| 2018 | n = 55 | n = 38 | n = 17 | n = 15 | n = 2 | n = 1 |
| 2019 | n = 54 | n = 41 | n = 17 | n = 18 | n = 4 | n = 0 |
| 2020 | n = 889 | n = 387 | n = 194 | n = 189 | n = 24 | n = 2 |
| 2021 | n = 143 | n = 90 | n = 56 | n = 52 | n = 2 | n = 0 |

Reverse view, 2017-21: 15903 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 565 (3.6%); anywhere in [trough-20, peak] of a big winner 1773 (11.1%)

## the +50% sensitivity set

### 2017-21, x150 — composition (n = 4,946 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 350, 2018: n = 535, 2019: n = 421, 2020: n = 2,745, 2021: n = 895 |
| tickers | n = 2,208 (episodes per ticker max 9) |
| close at the trough, $ (median, quartiles) | 23.99 (12.11 .. 48.21) (n = 4,946) |
| ADR20 at the trough (median, quartiles) | 0.059 (0.043 .. 0.082) (n = 4,946) |
| 63-session return into the trough (median, quartiles) | -0.18 (-0.42 .. 0.06) (n = 4,946) |
| gain trough → peak (median, quartiles) | 0.77 (0.60 .. 1.08) (n = 4,946); >= +200% n = 285 |
| sessions trough → peak (median, quartiles) | 56 (44 .. 73); peak extended past the 63-session window n = 1,736; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 9 / 27 (n = 4,946) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 205 (4%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 3,418 / 639 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 2,215 (45%) | 2,467 (50%) | 1,657 (34%) | 2,201 (45%) | 2,221 (45%) | 3,140 (63%) |
| ep_gap | 197 (4%) | 200 (4%) | 197 (4%) | 196 (4%) | 198 (4%) | 190 (4%) |
| late_base | 2,420 (49%) | 2,173 (44%) | 2,847 (58%) | 2,476 (50%) | 2,417 (49%) | 1,572 (32%) |
| no_consolidation | 28 (1%) | 49 (1%) | 13 (0%) | 7 (0%) | 25 (1%) | 28 (1%) |
| other | 86 (2%) | 57 (1%) | 232 (5%) | 66 (1%) | 85 (2%) | 16 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 182.

The measurable breakouts under the primary rule (n = 2,215): breakout day b − trough median (quartiles) 12 (7 .. 20) sessions; base length L 26 (16 .. 39); the base contains the trough 1,900 (86%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.4 (3.8 .. 5.0) ADR20; base depth 0.19 (0.14 .. 0.24); share of the episode's gain made at the close BEFORE b 0.13 (0.07 .. 0.18) and at b's close 0.23 (0.16 .. 0.29); the breakout close over the base high 0.42 (0.18 .. 0.92) ADR20; b opened with a gap of 1.3 (0.4 .. 3.9)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 641 (29%) of them — range ok 1,595 (72%), close location ok 1,597 (72%), volume ok 1,052 (47%).
The late-base episodes (n = 2,420): the first close above the longest base's high came when 0.52 (0.41 .. 0.66) of the gain was already made, b − trough 18 (13 .. 28) sessions, base depth 0.25 (0.20 .. 0.31), the base contains the trough 1,274 (53%).

### 2017-21, x150 — what we did

**2017-21, x150** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 4,946 | 100% of 4,946 |
| with a measurable breakout (primary rule) | n = 2,215 | 45% of 4,946 |
| … whose base nights our watch covers | n = 2,139 | 97% of 2,215 |
| … WATCHED (a watch row on some base night) | n = 864 | 40% of 2,139 |
| … watched with a trendline level (C0_tl) on some base night | n = 862 | 40% of 2,139 |
| … watched on the night before the breakout day | n = 491 | 23% of 2,139 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 714 | 33% of 2,139 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 217 | 10% of 2,139 |
| … triggered and STILL IN at s50 (half the gain made) | n = 59 | 3% of 2,139 |
| … near the breakout and still in at s50 | n = 43 | 2% of 2,139 |
| … triggered and KEPT >= half of the episode's gain | n = 6 | 0% of 2,139 |
| … near the breakout and kept >= half of the episode's gain | n = 4 | 0% of 2,139 |
| … triggered and kept >= half of the gain available from the fill | n = 12 | 1% of 2,139 |

All 4,946 big winners, any class (covered n = 4,857): watched 1,830 (38%); triggered (tl fill in the catch window) 1,207 (25%); still in at s50 88 (2%); kept >= half of the episode's gain 10 (0%); a tl fill ANYWHERE in [trough − 20, peak] 3,465 (71%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 1,455 (30%).

**2017-21, x150** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 2,139)

- NOT WATCHED on any base night: n = 1,275 (60% of 2,139). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - prior move < 30% (no pole) (`prior_move`): n = 726 (57% of 1,275)
  - close below the 50-day (`sma50`): n = 395 (31% of 1,275)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 117 (9% of 1,275)
  - under $10M median dollar volume (`universe_dv`): n = 21 (2% of 1,275)
  - raw close under $5 (`universe_price`): n = 12 (1% of 1,275)
  - pole data artifact (`pole_artifact`): n = 2 (0% of 1,275)
  - passes (my rebuild) (`pass`): n = 2 (0% of 1,275)
  - on the night before the breakout day alone: `prior_move` n = 827; `sma50` n = 208; `universe_dv` n = 146; `close_above_pole_high` n = 74; `universe_price` n = 18; `pass` n = 2
- WATCHED BUT NO TRIGGER in the catch window: n = 245 (11%); of them a trendline level existed on some base night (C0_tl) n = 243, watched on the night before the breakout n = 98, a tl fill came later anywhere before the peak n = 164, some other K filled in the window n = 101
- TRIGGERED: n = 714 (33%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 48; non-mature n = 1.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -10 (-25 .. -0); before b n = 535, on b n = 56, 1–5 after n = 46, later n = 77; share of the episode's gain already made at the fill: median (quartiles) 0.11 (0.06 .. 0.17)
  - the original STOP fired before s50: n = 591 (83% of 714) — of which before the breakout day itself n = 434; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 64 (9%); still in at s50: n = 59 (8%); status split: stopped n = 324, stopped_day0 n = 271, trailed n = 96, time_exit n = 22, degraded n = 1
  - realized R of the catch: mean +0.93, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 67, >= 10R n = 32; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 18.7 (13.6 .. 25.2) ADR, the gain available from the fill = 16.4 (11.9 .. 22.5) ADR, the trade's P&L = -0.23 (-0.46 .. 0.27) ADR; kept share of the episode's gain median (quartiles) -0.012 (-0.026 .. 0.014), mean 0.018; kept share of the available gain median -0.013 (-0.029 .. 0.015); kept >= half of the episode's gain n = 6, >= half of the available n = 12, >= a quarter of the episode's gain n = 40
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 96; best fill's kept share of the episode's gain median -0.004 (-0.021 .. 0.023), >= half n = 9

Reverse view, 2017-21: 15903 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 1677 (10.5%); anywhere in [trough-20, peak] of a big winner 6310 (39.7%)

## Validation of the gate rebuild (from 02_catch_<era>.txt)

- 2017-21: [x200] 1181 episodes; covered 1173; watched 474; triggered 371; validation on covered nights {'in_table_pass': 5156, 'in_table_fail': 0, 'not_in_table_fail': 28182, 'not_in_table_pass': 0} (in_table_fail + not_in_table_pass should be ~0); 3s
- 2017-21: [x150] 4946 episodes; covered 4857; watched 1863; triggered 1226; validation on covered nights {'in_table_pass': 19589, 'in_table_fail': 0, 'not_in_table_fail': 117824, 'not_in_table_pass': 62} (in_table_fail + not_in_table_pass should be ~0); 9s
