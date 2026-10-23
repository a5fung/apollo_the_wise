# Generated tables — big-winner recall (03_report.py; n on every row)

## the +100% set (close at least doubled from the trough within 63 sessions)

### 2017-21, x200 — composition (n = 994 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 26, 2018: n = 48, 2019: n = 40, 2020: n = 751, 2021: n = 129 |
| tickers | n = 739 (episodes per ticker max 5) |
| close at the trough, $ (median, quartiles) | 17.26 (8.38 .. 36.49) (n = 994) |
| ADR20 at the trough (median, quartiles) | 0.082 (0.062 .. 0.108) (n = 994) |
| 63-session return into the trough (median, quartiles) | -0.31 (-0.59 .. 0.03) (n = 994) |
| gain trough → peak (median, quartiles) | 1.42 (1.14 .. 1.97) (n = 994); >= +200% n = 239 |
| sessions trough → peak (median, quartiles) | 56 (49 .. 73); peak extended past the 63-session window n = 343; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 11 / 30 (n = 994) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 94 (9%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 579 / 182 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 489 (49%) | 495 (50%) | 420 (42%) | 472 (47%) | 490 (49%) | 575 (58%) |
| ep_gap | 89 (9%) | 91 (9%) | 88 (9%) | 87 (9%) | 90 (9%) | 86 (9%) |
| late_base | 408 (41%) | 394 (40%) | 462 (46%) | 431 (43%) | 406 (41%) | 328 (33%) |
| no_consolidation | 4 (0%) | 6 (1%) | 1 (0%) | 1 (0%) | 4 (0%) | 4 (0%) |
| other | 4 (0%) | 8 (1%) | 23 (2%) | 3 (0%) | 4 (0%) | 1 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 89.

The measurable breakouts under the primary rule (n = 489): breakout day b − trough median (quartiles) 13 (7 .. 20) sessions; base length L 25 (17 .. 39); the base contains the trough 403 (82%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.3 (3.7 .. 4.9) ADR20; base depth 0.26 (0.21 .. 0.32); share of the episode's gain made at the close BEFORE b 0.11 (0.05 .. 0.16) and at b's close 0.18 (0.12 .. 0.25); the breakout close over the base high 0.38 (0.16 .. 0.89) ADR20; b opened with a gap of 1.8 (0.5 .. 4.6)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 161 (33%) of them — range ok 347 (71%), close location ok 361 (74%), volume ok 251 (51%).
The late-base episodes (n = 408): the first close above the longest base's high came when 0.51 (0.42 .. 0.62) of the gain was already made, b − trough 22 (15 .. 29) sessions, base depth 0.33 (0.28 .. 0.41), the base contains the trough 133 (33%).

### 2017-21, x200 — what we did

**2017-21, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 994 | 100% of 994 |
| with a measurable breakout (primary rule) | n = 489 | 49% of 994 |
| … whose base nights our watch covers | n = 481 | 98% of 489 |
| … WATCHED (a watch row on some base night) | n = 240 | 50% of 481 |
| … watched with a trendline level (C0_tl) on some base night | n = 240 | 50% of 481 |
| … watched on the night before the breakout day | n = 160 | 33% of 481 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 237 | 49% of 481 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 83 | 17% of 481 |
| … triggered and STILL IN at s50 (half the gain made) | n = 25 | 5% of 481 |
| … near the breakout and still in at s50 | n = 15 | 3% of 481 |
| … triggered and KEPT >= half of the episode's gain | n = 3 | 1% of 481 |
| … near the breakout and kept >= half of the episode's gain | n = 2 | 0% of 481 |
| … triggered and kept >= half of the gain available from the fill | n = 6 | 1% of 481 |

All 994 big winners, any class (covered n = 986): watched 390 (40%); triggered (tl fill in the catch window) 310 (31%); still in at s50 33 (3%); kept >= half of the episode's gain 5 (1%); a tl fill ANYWHERE in [trough − 20, peak] 756 (77%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 355 (36%).

**2017-21, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 481)

- NOT WATCHED on any base night: n = 241 (50% of 481). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 118 (49% of 241)
  - prior move < 30% (no pole) (`prior_move`): n = 80 (33% of 241)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 35 (15% of 241)
  - raw close under $5 (`universe_price`): n = 5 (2% of 241)
  - under $10M median dollar volume (`universe_dv`): n = 2 (1% of 241)
  - pole data artifact (`pole_artifact`): n = 1 (0% of 241)
  - on the night before the breakout day alone: `prior_move` n = 119; `sma50` n = 62; `universe_dv` n = 26; `close_above_pole_high` n = 26; `universe_price` n = 8
- WATCHED BUT NO TRIGGER in the catch window: n = 43 (9%); of them a trendline level existed on some base night (C0_tl) n = 43, watched on the night before the breakout n = 18, a tl fill came later anywhere before the peak n = 27, some other K filled in the window n = 19
- TRIGGERED: n = 237 (49%). Fills per episode in the window: median 1, max 7; retrigger rows as the first fill n = 19; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -6 (-23 .. 0); before b n = 161, on b n = 21, 1–5 after n = 20, later n = 35; share of the episode's gain already made at the fill: median (quartiles) 0.10 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 190 (80% of 237) — of which before the breakout day itself n = 127; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 22 (9%); still in at s50: n = 25 (11%); status split: stopped n = 97, stopped_day0 n = 93, trailed n = 39, time_exit n = 8
  - realized R of the catch: mean +1.66, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 30, >= 10R n = 15; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 23.7 (17.7 .. 31.0) ADR, the gain available from the fill = 21.2 (14.8 .. 28.4) ADR, the trade's P&L = -0.23 (-0.46 .. 0.28) ADR; kept share of the episode's gain median (quartiles) -0.010 (-0.020 .. 0.009), mean 0.030; kept share of the available gain median -0.011 (-0.023 .. 0.010); kept >= half of the episode's gain n = 3, >= half of the available n = 6, >= a quarter of the episode's gain n = 20
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 49; best fill's kept share of the episode's gain median 0.004 (-0.015 .. 0.049), >= half n = 5

Any-K view on the covered measurable breakouts (n = 481; the entry tables' ORH5 filled C0 rows, E in the catch window): com: 252 (52%), E − b median -7; tl: 237 (49%), E − b median -6.

#### 2017-21 without the 2020 troughs (2020 holds 751 of 994 episodes)

**2017-21 excluding 2020, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 243 | 100% of 243 |
| with a measurable breakout (primary rule) | n = 166 | 68% of 243 |
| … whose base nights our watch covers | n = 158 | 95% of 166 |
| … WATCHED (a watch row on some base night) | n = 83 | 53% of 158 |
| … watched with a trendline level (C0_tl) on some base night | n = 83 | 53% of 158 |
| … watched on the night before the breakout day | n = 60 | 38% of 158 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 80 | 51% of 158 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 30 | 19% of 158 |
| … triggered and STILL IN at s50 (half the gain made) | n = 5 | 3% of 158 |
| … near the breakout and still in at s50 | n = 2 | 1% of 158 |
| … triggered and KEPT >= half of the episode's gain | n = 1 | 1% of 158 |
| … near the breakout and kept >= half of the episode's gain | n = 1 | 1% of 158 |
| … triggered and kept >= half of the gain available from the fill | n = 2 | 1% of 158 |

All 243 big winners, any class (covered n = 235): watched 122 (52%); triggered (tl fill in the catch window) 105 (45%); still in at s50 10 (4%); kept >= half of the episode's gain 3 (1%); a tl fill ANYWHERE in [trough − 20, peak] 177 (75%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 124 (53%).

**2017-21 excluding 2020, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 158)

- NOT WATCHED on any base night: n = 75 (47% of 158). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 42 (56% of 75)
  - prior move < 30% (no pole) (`prior_move`): n = 17 (23% of 75)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 14 (19% of 75)
  - raw close under $5 (`universe_price`): n = 1 (1% of 75)
  - pole data artifact (`pole_artifact`): n = 1 (1% of 75)
  - on the night before the breakout day alone: `prior_move` n = 37; `sma50` n = 20; `close_above_pole_high` n = 10; `universe_dv` n = 6; `universe_price` n = 2
- WATCHED BUT NO TRIGGER in the catch window: n = 13 (8%); of them a trendline level existed on some base night (C0_tl) n = 13, watched on the night before the breakout n = 8, a tl fill came later anywhere before the peak n = 6, some other K filled in the window n = 7
- TRIGGERED: n = 80 (51%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 6; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -4 (-22 .. 0); before b n = 51, on b n = 9, 1–5 after n = 8, later n = 12; share of the episode's gain already made at the fill: median (quartiles) 0.10 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 65 (81% of 80) — of which before the breakout day itself n = 38; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 10 (12%); still in at s50: n = 5 (6%); status split: stopped n = 36, stopped_day0 n = 29, trailed n = 10, time_exit n = 5
  - realized R of the catch: mean +1.58, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 6, >= 10R n = 5; sessions held median 2
  - kept, in the trade's ADR unit: the episode's gain = 21.6 (16.7 .. 27.2) ADR, the gain available from the fill = 18.5 (14.6 .. 25.3) ADR, the trade's P&L = -0.23 (-0.36 .. 0.25) ADR; kept share of the episode's gain median (quartiles) -0.010 (-0.020 .. 0.009), mean 0.021; kept share of the available gain median -0.011 (-0.023 .. 0.010); kept >= half of the episode's gain n = 1, >= half of the available n = 2, >= a quarter of the episode's gain n = 5
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 10; best fill's kept share of the episode's gain median -0.004 (-0.015 .. 0.021), >= half n = 1

By trough year (measurable breakouts covered → watched → triggered → still in at s50 → kept >= half):

| year | big winners | measurable breakouts covered | watched | triggered | still in at s50 | kept >= half |
|---|---|---|---|---|---|---|
| 2017 | n = 26 | n = 18 | n = 6 | n = 8 | n = 0 | n = 0 |
| 2018 | n = 48 | n = 33 | n = 16 | n = 12 | n = 2 | n = 1 |
| 2019 | n = 40 | n = 29 | n = 13 | n = 15 | n = 3 | n = 0 |
| 2020 | n = 751 | n = 323 | n = 157 | n = 157 | n = 20 | n = 2 |
| 2021 | n = 129 | n = 78 | n = 48 | n = 45 | n = 0 | n = 0 |

### 2022-24, x200 — composition (n = 414 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2022: n = 136, 2023: n = 142, 2024: n = 136 |
| tickers | n = 289 (episodes per ticker max 6) |
| close at the trough, $ (median, quartiles) | 13.80 (7.50 .. 26.05) (n = 414) |
| ADR20 at the trough (median, quartiles) | 0.069 (0.054 .. 0.088) (n = 414) |
| 63-session return into the trough (median, quartiles) | -0.24 (-0.41 .. 0.04) (n = 414) |
| gain trough → peak (median, quartiles) | 1.31 (1.14 .. 1.68) (n = 414); >= +200% n = 70 |
| sessions trough → peak (median, quartiles) | 59 (45 .. 69); peak extended past the 63-session window n = 159; extension truncated at the cut n = 31 |
| sessions trough → s25 / s50 (median) | 15 / 33 (n = 414) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 45 (11%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 261 / 81 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 9 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 260 (63%) | 290 (70%) | 197 (48%) | 267 (64%) | 261 (63%) | 335 (81%) |
| ep_gap | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) |
| late_base | 107 (26%) | 73 (18%) | 163 (39%) | 101 (24%) | 106 (26%) | 32 (8%) |
| no_consolidation | 2 (0%) | 5 (1%) | 1 (0%) | 0 (0%) | 2 (0%) | 2 (0%) |
| other | 0 (0%) | 1 (0%) | 8 (2%) | 1 (0%) | 0 (0%) | 0 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 41.

The measurable breakouts under the primary rule (n = 260): breakout day b − trough median (quartiles) 12 (7 .. 22) sessions; base length L 27 (17 .. 40); the base contains the trough 231 (89%); base span 4.5 (4.1 .. 4.7) ADR60 = 4.4 (3.8 .. 5.0) ADR20; base depth 0.25 (0.20 .. 0.31); share of the episode's gain made at the close BEFORE b 0.11 (0.05 .. 0.16) and at b's close 0.20 (0.13 .. 0.26); the breakout close over the base high 0.51 (0.21 .. 1.03) ADR20; b opened with a gap of 1.7 (0.5 .. 5.7)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 88 (34%) of them — range ok 200 (77%), close location ok 197 (76%), volume ok 143 (55%).
The late-base episodes (n = 107): the first close above the longest base's high came when 0.46 (0.36 .. 0.58) of the gain was already made, b − trough 22 (14 .. 30) sessions, base depth 0.34 (0.30 .. 0.41), the base contains the trough 81 (76%).

### 2022-24, x200 — what we did

**2022-24, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 414 | 100% of 414 |
| with a measurable breakout (primary rule) | n = 260 | 63% of 414 |
| … whose base nights our watch covers | n = 258 | 99% of 260 |
| … WATCHED (a watch row on some base night) | n = 115 | 45% of 258 |
| … watched with a trendline level (C0_tl) on some base night | n = 115 | 45% of 258 |
| … watched on the night before the breakout day | n = 71 | 28% of 258 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 112 | 43% of 258 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 43 | 17% of 258 |
| … triggered and STILL IN at s50 (half the gain made) | n = 14 | 5% of 258 |
| … near the breakout and still in at s50 | n = 11 | 4% of 258 |
| … triggered and KEPT >= half of the episode's gain | n = 0 | 0% of 258 |
| … near the breakout and kept >= half of the episode's gain | n = 0 | 0% of 258 |
| … triggered and kept >= half of the gain available from the fill | n = 3 | 1% of 258 |

All 414 big winners, any class (covered n = 409): watched 183 (45%); triggered (tl fill in the catch window) 152 (37%); still in at s50 18 (4%); kept >= half of the episode's gain 1 (0%); a tl fill ANYWHERE in [trough − 20, peak] 307 (75%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 188 (46%).

**2022-24, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 258)

- NOT WATCHED on any base night: n = 143 (55% of 258). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 75 (52% of 143)
  - prior move < 30% (no pole) (`prior_move`): n = 47 (33% of 143)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 16 (11% of 143)
  - under $10M median dollar volume (`universe_dv`): n = 3 (2% of 143)
  - raw close under $5 (`universe_price`): n = 2 (1% of 143)
  - on the night before the breakout day alone: `prior_move` n = 73; `sma50` n = 30; `universe_dv` n = 24; `close_above_pole_high` n = 12; `universe_price` n = 4
- WATCHED BUT NO TRIGGER in the catch window: n = 25 (10%); of them a trendline level existed on some base night (C0_tl) n = 25, watched on the night before the breakout n = 9, a tl fill came later anywhere before the peak n = 15, some other K filled in the window n = 16
- TRIGGERED: n = 112 (43%). Fills per episode in the window: median 1, max 4; retrigger rows as the first fill n = 4; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -4 (-18 .. 0); before b n = 72, on b n = 13, 1–5 after n = 7, later n = 20; share of the episode's gain already made at the fill: median (quartiles) 0.12 (0.07 .. 0.17)
  - the original STOP fired before s50: n = 89 (79% of 112) — of which before the breakout day itself n = 60; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 9 (8%); still in at s50: n = 14 (12%); status split: stopped_day0 n = 48, stopped n = 42, trailed n = 22
  - realized R of the catch: mean +1.62, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 14, >= 10R n = 7; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 22.8 (17.4 .. 28.3) ADR, the gain available from the fill = 19.5 (13.7 .. 25.2) ADR, the trade's P&L = -0.30 (-0.49 .. 0.28) ADR; kept share of the episode's gain median (quartiles) -0.013 (-0.023 .. 0.016), mean 0.032; kept share of the available gain median -0.015 (-0.027 .. 0.019); kept >= half of the episode's gain n = 0, >= half of the available n = 3, >= a quarter of the episode's gain n = 12
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 20; best fill's kept share of the episode's gain median 0.002 (-0.018 .. 0.043), >= half n = 1

Any-K view on the covered measurable breakouts (n = 258; the entry tables' ORH5 filled C0 rows, E in the catch window): com: 130 (50%), E − b median -6; comb: 89 (34%), E − b median -8; full: 76 (29%), E − b median +0; k10: 122 (47%), E − b median -4; k5: 126 (49%), E − b median -6; tl: 122 (47%), E − b median -5.

Reverse view, 2017-21: 13368 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 482 (3.6%); anywhere in [trough-20, peak] of a big winner 1473 (11.0%)

Reverse view, 2022-24: 7791 judgeable fills (E in the watch window and E <= last session - 83; 1170 later fills unjudgeable): in a big-winner catch window 182 (2.3%); anywhere in [trough-20, peak] of a big winner 527 (6.8%)

## the +50% sensitivity set

### 2017-21, x150 — composition (n = 4,182 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 265, 2018: n = 439, 2019: n = 351, 2020: n = 2,365, 2021: n = 762 |
| tickers | n = 1,871 (episodes per ticker max 10) |
| close at the trough, $ (median, quartiles) | 24.48 (12.48 .. 49.93) (n = 4,182) |
| ADR20 at the trough (median, quartiles) | 0.059 (0.042 .. 0.081) (n = 4,182) |
| 63-session return into the trough (median, quartiles) | -0.19 (-0.42 .. 0.05) (n = 4,182) |
| gain trough → peak (median, quartiles) | 0.77 (0.60 .. 1.08) (n = 4,182); >= +200% n = 243 |
| sessions trough → peak (median, quartiles) | 56 (45 .. 73); peak extended past the 63-session window n = 1,457; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 9 / 27 (n = 4,182) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 170 (4%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 2,886 / 535 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 1,864 (45%) | 2,073 (50%) | 1,411 (34%) | 1,861 (45%) | 1,869 (45%) | 2,632 (63%) |
| ep_gap | 162 (4%) | 166 (4%) | 162 (4%) | 161 (4%) | 163 (4%) | 156 (4%) |
| late_base | 2,064 (49%) | 1,861 (45%) | 2,405 (58%) | 2,098 (50%) | 2,061 (49%) | 1,362 (33%) |
| no_consolidation | 21 (1%) | 37 (1%) | 11 (0%) | 5 (0%) | 18 (0%) | 21 (1%) |
| other | 71 (2%) | 45 (1%) | 193 (5%) | 57 (1%) | 71 (2%) | 11 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 155.

The measurable breakouts under the primary rule (n = 1,864): breakout day b − trough median (quartiles) 12 (7 .. 20) sessions; base length L 25 (16 .. 39); the base contains the trough 1,595 (86%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.4 (3.8 .. 4.9) ADR20; base depth 0.18 (0.14 .. 0.24); share of the episode's gain made at the close BEFORE b 0.13 (0.08 .. 0.18) and at b's close 0.22 (0.16 .. 0.29); the breakout close over the base high 0.43 (0.18 .. 0.92) ADR20; b opened with a gap of 1.4 (0.4 .. 3.8)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 531 (28%) of them — range ok 1,335 (72%), close location ok 1,347 (72%), volume ok 879 (47%).
The late-base episodes (n = 2,064): the first close above the longest base's high came when 0.52 (0.41 .. 0.66) of the gain was already made, b − trough 18 (13 .. 28) sessions, base depth 0.25 (0.20 .. 0.31), the base contains the trough 1,066 (52%).

### 2017-21, x150 — what we did

**2017-21, x150** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 4,182 | 100% of 4,182 |
| with a measurable breakout (primary rule) | n = 1,864 | 45% of 4,182 |
| … whose base nights our watch covers | n = 1,801 | 97% of 1,864 |
| … WATCHED (a watch row on some base night) | n = 709 | 39% of 1,801 |
| … watched with a trendline level (C0_tl) on some base night | n = 707 | 39% of 1,801 |
| … watched on the night before the breakout day | n = 403 | 22% of 1,801 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 589 | 33% of 1,801 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 184 | 10% of 1,801 |
| … triggered and STILL IN at s50 (half the gain made) | n = 45 | 2% of 1,801 |
| … near the breakout and still in at s50 | n = 31 | 2% of 1,801 |
| … triggered and KEPT >= half of the episode's gain | n = 5 | 0% of 1,801 |
| … near the breakout and kept >= half of the episode's gain | n = 3 | 0% of 1,801 |
| … triggered and kept >= half of the gain available from the fill | n = 8 | 0% of 1,801 |

All 4,182 big winners, any class (covered n = 4,108): watched 1,518 (37%); triggered (tl fill in the catch window) 1,005 (24%); still in at s50 70 (2%); kept >= half of the episode's gain 9 (0%); a tl fill ANYWHERE in [trough − 20, peak] 2,936 (71%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 1,215 (30%).

**2017-21, x150** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 1,801)

- NOT WATCHED on any base night: n = 1,092 (61% of 1,801). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - prior move < 30% (no pole) (`prior_move`): n = 634 (58% of 1,092)
  - close below the 50-day (`sma50`): n = 332 (30% of 1,092)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 96 (9% of 1,092)
  - under $10M median dollar volume (`universe_dv`): n = 15 (1% of 1,092)
  - raw close under $5 (`universe_price`): n = 11 (1% of 1,092)
  - pole data artifact (`pole_artifact`): n = 2 (0% of 1,092)
  - passes (my rebuild) (`pass`): n = 2 (0% of 1,092)
  - on the night before the breakout day alone: `prior_move` n = 721; `sma50` n = 175; `universe_dv` n = 117; `close_above_pole_high` n = 60; `universe_price` n = 17; `pass` n = 2
- WATCHED BUT NO TRIGGER in the catch window: n = 205 (11%); of them a trendline level existed on some base night (C0_tl) n = 203, watched on the night before the breakout n = 79, a tl fill came later anywhere before the peak n = 135, some other K filled in the window n = 86
- TRIGGERED: n = 589 (33%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 38; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -9 (-24 .. 0); before b n = 436, on b n = 44, 1–5 after n = 41, later n = 68; share of the episode's gain already made at the fill: median (quartiles) 0.11 (0.06 .. 0.17)
  - the original STOP fired before s50: n = 491 (83% of 589) — of which before the breakout day itself n = 350; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 53 (9%); still in at s50: n = 45 (8%); status split: stopped n = 267, stopped_day0 n = 227, trailed n = 77, time_exit n = 18
  - realized R of the catch: mean +0.82, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 52, >= 10R n = 25; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 19.0 (13.9 .. 25.6) ADR, the gain available from the fill = 16.7 (12.1 .. 23.3) ADR, the trade's P&L = -0.23 (-0.46 .. 0.26) ADR; kept share of the episode's gain median (quartiles) -0.011 (-0.024 .. 0.013), mean 0.017; kept share of the available gain median -0.012 (-0.028 .. 0.014); kept >= half of the episode's gain n = 5, >= half of the available n = 8, >= a quarter of the episode's gain n = 30
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 77; best fill's kept share of the episode's gain median -0.005 (-0.020 .. 0.022), >= half n = 8

### 2022-24, x150 — composition (n = 2,381 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2022: n = 924, 2023: n = 807, 2024: n = 650 |
| tickers | n = 1,176 (episodes per ticker max 9) |
| close at the trough, $ (median, quartiles) | 22.32 (11.14 .. 46.84) (n = 2,381) |
| ADR20 at the trough (median, quartiles) | 0.051 (0.039 .. 0.068) (n = 2,381) |
| 63-session return into the trough (median, quartiles) | -0.21 (-0.35 .. -0.03) (n = 2,381) |
| gain trough → peak (median, quartiles) | 0.70 (0.58 .. 0.94) (n = 2,381); >= +200% n = 72 |
| sessions trough → peak (median, quartiles) | 56 (39 .. 69); peak extended past the 63-session window n = 815; extension truncated at the cut n = 134 |
| sessions trough → s25 / s50 (median) | 10 / 26 (n = 2,381) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 135 (6%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 1,601 / 326 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 26 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 1,153 (48%) | 1,325 (56%) | 787 (33%) | 1,152 (48%) | 1,156 (49%) | 1,739 (73%) |
| ep_gap | 132 (6%) | 134 (6%) | 134 (6%) | 132 (6%) | 133 (6%) | 132 (6%) |
| late_base | 1,060 (45%) | 887 (37%) | 1,362 (57%) | 1,073 (45%) | 1,057 (44%) | 497 (21%) |
| no_consolidation | 8 (0%) | 21 (1%) | 3 (0%) | 2 (0%) | 7 (0%) | 8 (0%) |
| other | 28 (1%) | 14 (1%) | 95 (4%) | 22 (1%) | 28 (1%) | 5 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 124.

The measurable breakouts under the primary rule (n = 1,153): breakout day b − trough median (quartiles) 10 (6 .. 18) sessions; base length L 24 (15 .. 36); the base contains the trough 1,030 (89%); base span 4.5 (4.1 .. 4.7) ADR60 = 4.3 (3.8 .. 4.8) ADR20; base depth 0.17 (0.14 .. 0.22); share of the episode's gain made at the close BEFORE b 0.13 (0.07 .. 0.18) and at b's close 0.24 (0.17 .. 0.30); the breakout close over the base high 0.47 (0.19 .. 1.01) ADR20; b opened with a gap of 1.5 (0.3 .. 4.6)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 379 (33%) of them — range ok 886 (77%), close location ok 863 (75%), volume ok 580 (50%).
The late-base episodes (n = 1,060): the first close above the longest base's high came when 0.50 (0.40 .. 0.63) of the gain was already made, b − trough 19 (12 .. 29) sessions, base depth 0.24 (0.20 .. 0.30), the base contains the trough 782 (74%).

### 2022-24, x150 — what we did

**2022-24, x150** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 2,381 | 100% of 2,381 |
| with a measurable breakout (primary rule) | n = 1,153 | 48% of 2,381 |
| … whose base nights our watch covers | n = 1,138 | 99% of 1,153 |
| … WATCHED (a watch row on some base night) | n = 319 | 28% of 1,138 |
| … watched with a trendline level (C0_tl) on some base night | n = 315 | 28% of 1,138 |
| … watched on the night before the breakout day | n = 184 | 16% of 1,138 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 262 | 23% of 1,138 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 108 | 9% of 1,138 |
| … triggered and STILL IN at s50 (half the gain made) | n = 26 | 2% of 1,138 |
| … near the breakout and still in at s50 | n = 20 | 2% of 1,138 |
| … triggered and KEPT >= half of the episode's gain | n = 1 | 0% of 1,138 |
| … near the breakout and kept >= half of the episode's gain | n = 1 | 0% of 1,138 |
| … triggered and kept >= half of the gain available from the fill | n = 5 | 0% of 1,138 |

All 2,381 big winners, any class (covered n = 2,351): watched 809 (34%); triggered (tl fill in the catch window) 503 (21%); still in at s50 40 (2%); kept >= half of the episode's gain 3 (0%); a tl fill ANYWHERE in [trough − 20, peak] 1,530 (65%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 753 (32%).

**2022-24, x150** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 1,138)

- NOT WATCHED on any base night: n = 819 (72% of 1,138). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - prior move < 30% (no pole) (`prior_move`): n = 481 (59% of 819)
  - close below the 50-day (`sma50`): n = 280 (34% of 819)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 42 (5% of 819)
  - under $10M median dollar volume (`universe_dv`): n = 10 (1% of 819)
  - raw close under $5 (`universe_price`): n = 6 (1% of 819)
  - on the night before the breakout day alone: `prior_move` n = 579; `sma50` n = 106; `universe_dv` n = 97; `close_above_pole_high` n = 26; `universe_price` n = 11
- WATCHED BUT NO TRIGGER in the catch window: n = 107 (9%); of them a trendline level existed on some base night (C0_tl) n = 103, watched on the night before the breakout n = 34, a tl fill came later anywhere before the peak n = 71, some other K filled in the window n = 73
- TRIGGERED: n = 262 (23%). Fills per episode in the window: median 1, max 5; retrigger rows as the first fill n = 14; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -3 (-19 .. 0); before b n = 170, on b n = 33, 1–5 after n = 19, later n = 40; share of the episode's gain already made at the fill: median (quartiles) 0.14 (0.08 .. 0.19)
  - the original STOP fired before s50: n = 207 (79% of 262) — of which before the breakout day itself n = 141; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 29 (11%); still in at s50: n = 26 (10%); status split: stopped n = 107, stopped_day0 n = 101, trailed n = 48, time_exit n = 6
  - realized R of the catch: mean +0.98, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 30, >= 10R n = 13; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 18.8 (13.9 .. 26.6) ADR, the gain available from the fill = 15.7 (11.8 .. 23.2) ADR, the trade's P&L = -0.29 (-0.47 .. 0.30) ADR; kept share of the episode's gain median (quartiles) -0.014 (-0.027 .. 0.017), mean 0.022; kept share of the available gain median -0.016 (-0.031 .. 0.020); kept >= half of the episode's gain n = 1, >= half of the available n = 5, >= a quarter of the episode's gain n = 20
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 39; best fill's kept share of the episode's gain median -0.005 (-0.021 .. 0.040), >= half n = 2

Reverse view, 2017-21: 13368 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 1400 (10.5%); anywhere in [trough-20, peak] of a big winner 5323 (39.8%)

Reverse view, 2022-24: 7791 judgeable fills (E in the watch window and E <= last session - 83; 1170 later fills unjudgeable): in a big-winner catch window 615 (7.9%); anywhere in [trough-20, peak] of a big winner 2448 (31.4%)

## Validation of the gate rebuild (from 02_catch_<era>.txt)

- 2017-21: [x200] 994 episodes; covered 986; watched 391; triggered 310; validation on covered nights {'in_table_pass': 4284, 'in_table_fail': 0, 'not_in_table_fail': 23491, 'not_in_table_pass': 0} (in_table_fail + not_in_table_pass should be ~0); 3s
- 2017-21: [x150] 4182 episodes; covered 4108; watched 1546; triggered 1021; validation on covered nights {'in_table_pass': 16149, 'in_table_fail': 0, 'not_in_table_fail': 99642, 'not_in_table_pass': 30} (in_table_fail + not_in_table_pass should be ~0); 8s
- 2022-24: [x200] 414 episodes; covered 409; watched 186; triggered 155; validation on covered nights {'in_table_pass': 1684, 'in_table_fail': 2, 'not_in_table_fail': 10502, 'not_in_table_pass': 7} (in_table_fail + not_in_table_pass should be ~0); 1s
- 2022-24: [x150] 2381 episodes; covered 2351; watched 828; triggered 516; validation on covered nights {'in_table_pass': 6903, 'in_table_fail': 10, 'not_in_table_fail': 58913, 'not_in_table_pass': 45} (in_table_fail + not_in_table_pass should be ~0); 5s
