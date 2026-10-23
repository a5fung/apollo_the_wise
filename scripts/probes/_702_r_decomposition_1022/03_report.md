## Population and completeness (n on every row)

| era | published mature fills | with a readable E bar | 20-session window complete | 60-session window complete | fwd_hole rows (a missing session inside the walk) |
|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 13,363 | 13,363 | 13,363 | 25 |
| 2022-24 | n = 8,984 | 8,956 | 8,711 | 8,047 | 19 |

## 1. The stock's path after the fill, independent of our stop (ADR units; window (E, E+k] starts the session AFTER E)

| era | n (60-window complete) | max move from the fill within 60: >= 5 ADR | >= 10 ADR | p90 | median | max move within 20: >= 5 ADR | >= 10 ADR | worst low within 60 from the fill, median | fills with a 10R result (= about 4.5 ADR at the median stop) |
|---|---|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 5,756 (43.1%) | 1,855 (13.88%) | 11.46 ADR | 4.26 ADR | 2,170 (16.2%, n = 13,363) | 294 (2.20%) | -2.81 ADR | 165 (1.23%) |
| 2022-24 | n = 8,047 | 2,829 (35.2%) | 808 (10.04%) | 10.02 ADR | 3.47 ADR | 1,178 (13.5%, n = 8,711) | 167 (1.92%) | -3.90 ADR | 69 (0.86%) |

What was on the table vs what was kept, in ADR units (fills whose best 60-session move from the fill reached the threshold; 'on the table' = the sum of those best moves, a CEILING no exit reaches, not a forecast; 'kept' = the sum of realized R x width_adr on the same fills):

| era | threshold | n fills reaching it | on the table (ADR) | kept (ADR) | kept share | per fill: on the table | kept |
|---|---|---|---|---|---|---|---|
| 2017-21 | >= 5 ADR | n = 5,756 | 56,868 | +2,120 | 3.7% | 9.9 | +0.37 |
| 2017-21 | >= 10 ADR | n = 1,855 | 29,347 | +1,540 | 5.2% | 15.8 | +0.83 |
| 2022-24 | >= 5 ADR | n = 2,829 | 26,587 | +721 | 2.7% | 9.4 | +0.25 |
| 2022-24 | >= 10 ADR | n = 808 | 12,395 | +539 | 4.3% | 15.3 | +0.67 |

Same, measured from E's CLOSE (the control's base; the fill is earlier in the day, so moves from the close read smaller):

| era | n | >= 5 ADR within 60 | >= 10 ADR within 60 | p90 | mean close-to-close +20 (ADR) | mean +60 (ADR) |
|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 5,776 (43.2%) | 1,851 (13.85%) | 11.50 | +0.48 | +1.23 |
| 2022-24 | n = 8,047 | 2,832 (35.2%) | 819 (10.18%) | 10.11 | -0.23 | +0.07 |

## 2. The waterfall: every fill with a complete 60-session window lands in exactly one bin

**Within 60 sessions of the fill; C_in = in at the move's start but kept < half the threshold move (pnl in ADR < T/2)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 13,363 | 7,607 (56.9%) | 3,194 (23.9%) | 2,077 (15.5%) = 1,768 / 309 | 485 (3.6%) | 55.5% of 5,756 | 36.1% |
| 2017-21, +10 ADR | n = 13,363 | 11,508 (86.1%) | 1,013 (7.6%) | 712 (5.3%) = 662 / 50 | 130 (1.0%) | 54.6% of 1,855 | 38.4% |
| 2022-24, +5 ADR | n = 8,047 | 5,218 (64.8%) | 1,642 (20.4%) | 979 (12.2%) = 865 / 114 | 208 (2.6%) | 58.0% of 2,829 | 34.6% |
| 2022-24, +10 ADR | n = 8,047 | 7,239 (90.0%) | 474 (5.9%) | 274 (3.4%) = 262 / 12 | 60 (0.7%) | 58.7% of 808 | 33.9% |

B split by WHEN the original stop was hit (fill day = the ORH5 entry's own-day shake-out; later = a stop hit on sessions 1+ before the move):

| era / threshold | B total | stopped on the fill day | stopped on a later session (before s*) | share of B on the fill day |
|---|---|---|---|---|
| 2017-21, +5 ADR | n = 3,194 | 1,768 | 1,426 | 55.4% |
| 2017-21, +10 ADR | n = 1,013 | 562 | 451 | 55.5% |
| 2022-24, +5 ADR | n = 1,642 | 954 | 688 | 58.1% |
| 2022-24, +10 ADR | n = 474 | 289 | 185 | 61.0% |

Bin detail (mean realized R per bin; the stock's mean best move in the B / C bins = what was on the table; n per bin above):

| era / threshold | mean R: A | B | C_out | C_in | D | mean best move (ADR) B | C_out | C_in | D | 10R trades in D / C_in / elsewhere | same-bar stop at s* (counted in B/C_out) | big movers whose daily LOW reached the original stop level on a session in E+1..s*-1 (whatever our stop was by then) | median s* (sessions) | E's own high already >= T ADR over the fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR (n = 13,363) | -0.50 | -1.04 | +0.85 | +3.29 | +10.20 | +9.82 | +9.34 | +7.74 | +13.63 | 158 / 4 / 3 | 0 | 4177 | 26 | 5 |
| 2017-21, +10 ADR (n = 13,363) | -0.23 | -1.04 | +1.91 | +7.80 | +18.62 | +15.73 | +14.75 | +13.41 | +22.89 | 96 / 11 / 58 | 0 | 1290 | 40 | 0 |
| 2022-24, +5 ADR (n = 8,047) | -0.58 | -1.09 | +0.83 | +2.92 | +10.11 | +9.39 | +8.85 | +8.56 | +12.22 | 67 / 1 / 1 | 0 | 2130 | 28 | 0 |
| 2022-24, +10 ADR (n = 8,047) | -0.37 | -1.13 | +1.77 | +9.59 | +16.57 | +15.20 | +15.00 | +11.82 | +18.65 | 40 / 3 / 26 | 0 | 573 | 38 | 0 |

**Sensitivity: 'small' read as kept < half of the stock's own best move (instead of half the threshold)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR, small = kept < half the stock's best 60-session move | n = 13,363 | 7,607 (56.9%) | 3,194 (23.9%) | 2,462 (18.4%) = 1,768 / 694 | 100 (0.7%) | 55.5% of 5,756 | 42.8% |
| 2017-21, +10 ADR, small = kept < half the stock's best 60-session move | n = 13,363 | 11,508 (86.1%) | 1,013 (7.6%) | 796 (6.0%) = 662 / 134 | 46 (0.3%) | 54.6% of 1,855 | 42.9% |
| 2022-24, +5 ADR, small = kept < half the stock's best 60-session move | n = 8,047 | 5,218 (64.8%) | 1,642 (20.4%) | 1,136 (14.1%) = 865 / 271 | 51 (0.6%) | 58.0% of 2,829 | 40.2% |
| 2022-24, +10 ADR, small = kept < half the stock's best 60-session move | n = 8,047 | 7,239 (90.0%) | 474 (5.9%) | 313 (3.9%) = 262 / 51 | 21 (0.3%) | 58.7% of 808 | 38.7% |

**Sensitivity: the move must come within 20 sessions (more fills have a complete window)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR within 20 sessions | n = 13,363 | 11,193 (83.8%) | 1,014 (7.6%) | 722 (5.4%) = 435 / 287 | 434 (3.2%) | 46.7% of 2,170 | 33.3% |
| 2017-21, +10 ADR within 20 sessions | n = 13,363 | 13,069 (97.8%) | 127 (1.0%) | 97 (0.7%) = 63 / 34 | 70 (0.5%) | 43.2% of 294 | 33.0% |
| 2022-24, +5 ADR within 20 sessions | n = 8,711 | 7,533 (86.5%) | 562 (6.5%) | 397 (4.6%) = 280 / 117 | 219 (2.5%) | 47.7% of 1,178 | 33.7% |
| 2022-24, +10 ADR within 20 sessions | n = 8,711 | 8,544 (98.1%) | 82 (0.9%) | 44 (0.5%) = 37 / 7 | 41 (0.5%) | 49.1% of 167 | 26.3% |

What the bins cost in R (sum of realized R per bin; the published mean R is the sum over all bins / n):

| era / threshold | n | sum R: A | B | C_out | C_in | D | total | mean R (this subset) |
|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 13,363 | -3,786 | -3,336 | +1,496 | +1,016 | +4,949 | +339 | +0.025 |
| 2017-21, +10 ADR | n = 13,363 | -2,686 | -1,051 | +1,265 | +390 | +2,421 | +339 | +0.025 |
| 2022-24, +5 ADR | n = 8,047 | -3,018 | -1,793 | +719 | +333 | +2,104 | -1,655 | -0.206 |
| 2022-24, +10 ADR | n = 8,047 | -2,692 | -536 | +463 | +115 | +994 | -1,655 | -0.206 |

## 3. The matched control (selection): the same E dates, the setup's universe filter at D, matched on ADR20 decile (and on the 63-session return quintile)

**2017-21 — composition first.** Breakouts n = 13,363 over 1176 E dates; control n = 2,233,746 (ticker-dates; mean 1899 per E). ADR20 deciles cut on the breakouts: [0.025, 0.0298, 0.0336, 0.0374, 0.0412, 0.0455, 0.0511, 0.0593, 0.0744]; 63-session return quintile cuts: [0.01, 0.15, 0.259, 0.428]. Breakouts' median ADR20 0.0412 vs the pooled control's 0.0229; median 63-session return +0.204 vs +0.022; median 20-session dollar volume $38M vs $47M.

Per decile, POOLED over all E dates (not date-matched - breakouts cluster in strong months; the date-matched rows below are the verdict):

| ADR20 decile | breakouts n | control n | breakout >= 5 ADR from E close within 60 | control >= 5 ADR | breakout >= 10 ADR | control >= 10 ADR | breakout mean +20 close (ADR) | control mean +20 |
|---|---|---|---|---|---|---|---|---|
| 1 | n = 1,337 | n = 1,259,285 | 47.2% | 47.5% | 18.25% | 15.44% | +0.32 | +0.06 |
| 2 | n = 1,336 | n = 253,964 | 47.9% | 43.2% | 14.15% | 11.75% | +0.54 | +0.27 |
| 3 | n = 1,336 | n = 147,921 | 46.6% | 42.9% | 15.42% | 12.14% | +0.43 | +0.27 |
| 4 | n = 1,336 | n = 110,407 | 42.6% | 42.6% | 11.08% | 12.83% | +0.31 | +0.37 |
| 5 | n = 1,337 | n = 85,860 | 44.2% | 42.2% | 12.64% | 12.80% | +0.39 | +0.38 |
| 6 | n = 1,336 | n = 75,360 | 43.9% | 41.7% | 12.80% | 12.86% | +0.55 | +0.37 |
| 7 | n = 1,336 | n = 72,703 | 43.3% | 41.4% | 13.10% | 12.59% | +0.60 | +0.41 |
| 8 | n = 1,336 | n = 71,701 | 41.2% | 40.3% | 14.15% | 12.25% | +0.57 | +0.40 |
| 9 | n = 1,336 | n = 72,572 | 40.8% | 38.7% | 14.22% | 11.95% | +0.61 | +0.47 |
| 10 | n = 1,337 | n = 83,973 | 34.6% | 35.0% | 12.72% | 10.36% | +0.45 | +0.54 |

| 2017-21: matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval | fills whose cell had no control (fell back to decile / to the date) |
|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 (from E close) | n = 13,363 | 43.22% | 42.08% | 1.14% | -0.64% .. 2.83% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 (from E close) | n = 13,363 | 13.85% | 13.10% | 0.75% | -0.19% .. 1.85% | 0 / 0 |
| ADR decile | mean +20-session close return (ADR) | n = 13,342 | +0.48 | +0.43 | +0.05 | -0.08 .. +0.18 | 0 / 0 |
| ADR decile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +0.92 | +0.31 | +0.11 .. +0.54 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 (from E close) | n = 13,363 | 43.22% | 42.36% | 0.87% | -0.81% .. 2.58% | 170 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 (from E close) | n = 13,363 | 13.85% | 13.36% | 0.49% | -0.36% .. 1.54% | 170 / 0 |
| ADR decile x 63-session return quintile | mean +20-session close return (ADR) | n = 13,342 | +0.48 | +0.45 | +0.03 | -0.09 .. +0.14 | 172 / 0 |
| ADR decile x 63-session return quintile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +1.07 | +0.16 | -0.03 .. +0.36 | 184 / 0 |

**2022-24 — composition first.** Breakouts n = 8,047 over 608 E dates; control n = 1,387,809 (ticker-dates; mean 2283 per E). ADR20 deciles cut on the breakouts: [0.0241, 0.0286, 0.0326, 0.0361, 0.0403, 0.0454, 0.0513, 0.0589, 0.0718]; 63-session return quintile cuts: [-0.01, 0.103, 0.197, 0.324]. Breakouts' median ADR20 0.0403 vs the pooled control's 0.0245; median 63-session return +0.152 vs +0.001; median 20-session dollar volume $37M vs $47M.

Per decile, POOLED over all E dates (not date-matched - breakouts cluster in strong months; the date-matched rows below are the verdict):

| ADR20 decile | breakouts n | control n | breakout >= 5 ADR from E close within 60 | control >= 5 ADR | breakout >= 10 ADR | control >= 10 ADR | breakout mean +20 close (ADR) | control mean +20 |
|---|---|---|---|---|---|---|---|---|
| 1 | n = 805 | n = 673,943 | 46.7% | 48.0% | 18.14% | 16.79% | +0.11 | +0.17 |
| 2 | n = 805 | n = 182,293 | 38.0% | 43.8% | 11.06% | 12.20% | -0.13 | +0.30 |
| 3 | n = 804 | n = 117,814 | 42.2% | 42.3% | 10.07% | 11.70% | -0.24 | +0.26 |
| 4 | n = 805 | n = 79,029 | 40.2% | 41.8% | 9.81% | 11.88% | -0.32 | +0.26 |
| 5 | n = 805 | n = 73,559 | 33.8% | 40.5% | 10.06% | 11.47% | -0.41 | +0.18 |
| 6 | n = 804 | n = 67,184 | 35.3% | 38.8% | 11.44% | 11.48% | -0.27 | +0.14 |
| 7 | n = 805 | n = 54,835 | 31.4% | 37.8% | 8.45% | 11.01% | -0.24 | +0.14 |
| 8 | n = 804 | n = 46,896 | 29.1% | 36.1% | 6.47% | 10.75% | -0.25 | +0.03 |
| 9 | n = 805 | n = 45,582 | 26.1% | 33.6% | 7.45% | 10.14% | -0.43 | -0.07 |
| 10 | n = 805 | n = 46,674 | 29.1% | 31.2% | 8.82% | 9.26% | -0.10 | -0.20 |

| 2022-24: matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval | fills whose cell had no control (fell back to decile / to the date) |
|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 (from E close) | n = 8,047 | 35.19% | 35.99% | -0.79% | -2.30% .. 0.90% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 (from E close) | n = 8,047 | 10.18% | 10.43% | -0.25% | -1.06% .. 0.84% | 0 / 0 |
| ADR decile | mean +20-session close return (ADR) | n = 8,026 | -0.23 | -0.22 | -0.01 | -0.11 .. +0.10 | 0 / 0 |
| ADR decile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | -0.01 | +0.08 | -0.15 .. +0.32 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 (from E close) | n = 8,047 | 35.19% | 34.53% | 0.66% | -0.77% .. 2.23% | 27 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 (from E close) | n = 8,047 | 10.18% | 9.73% | 0.45% | -0.44% .. 1.64% | 27 / 0 |
| ADR decile x 63-session return quintile | mean +20-session close return (ADR) | n = 8,026 | -0.23 | -0.22 | -0.01 | -0.11 .. +0.10 | 28 / 0 |
| ADR decile x 63-session return quintile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | -0.12 | +0.19 | -0.05 .. +0.45 | 29 / 0 |

## 4. The 39-winner lens (2017-21 only; selection held fixed at perfect by hindsight - NOT evidence about selection)

The 39 tickers (parsed from `aplus_read.py` `THE_39`, cross-checked against `aplus_hindsight_pre.txt`) have n = 527 C0 `tl` ORH5 fills in 2017-21 with a complete 60-session window (the whole era, not only 2020-21; 39 of the 39 appear).

| group | n | mean R | 10R trades | best 60-session move from the fill: >= 5 ADR | >= 10 ADR | p90 (ADR) | median (ADR) | sum of best moves (ADR, fills >= 5 ADR) | sum kept (pnl in ADR, same fills) | fill-day stop share |
|---|---|---|---|---|---|---|---|---|---|---|
| the 39's fills | n = 527 | +1.006 | 17 (3.23%) | 304 (57.7%) | 167 (31.7%) | 18.37 | 5.92 | 4,493 | +346 | 34.0% |
| all other 2017-21 fills | n = 12,836 | -0.015 | 148 (1.15%) | 5452 (42.5%) | 1688 (13.2%) | 11.20 | 4.20 | 52,375 | +1,773 | 36.9% |

**The 39's waterfall (60 sessions)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| the 39, +5 ADR | n = 527 | 223 (42.3%) | 158 (30.0%) | 107 (20.3%) = 89 / 18 | 39 (7.4%) | 52.0% of 304 | 35.2% |
| the 39, +10 ADR | n = 527 | 360 (68.3%) | 89 (16.9%) | 61 (11.6%) = 54 / 7 | 17 (3.2%) | 53.3% of 167 | 36.5% |

| the 39 / threshold | mean R: B | C_out | C_in | D | mean best move (ADR): B | C_out | C_in | D | 10R trades in D / C_in / elsewhere |
|---|---|---|---|---|---|---|---|---|---|
| the 39, +5 ADR (n = 527) | -1.03 | +0.84 | +3.35 | +17.00 | +13.98 | +11.79 | +8.01 | +27.97 | 17 / 0 / 0 |
| the 39, +10 ADR (n = 527) | -1.03 | +1.83 | +6.26 | +30.77 | +19.24 | +16.12 | +13.43 | +50.05 | 15 / 0 / 2 |

Per ticker (fills with a complete window; sorted by the sum of best moves):

| ticker | n fills | mean R | sum R | 10R | fills whose best 60-session move >= 5 ADR | of those: stop hit first (B) | exit gave it back (C) | captured (D) | sum best move (ADR) | sum kept (ADR) |
|---|---|---|---|---|---|---|---|---|---|---|
| GME | n = 10 | +5.30 | +53.0 | 1 | 2 | 1 | 0 | 1 | 606 | +49 |
| MRNA | n = 19 | +2.44 | +46.4 | 2 | 16 | 7 | 7 | 2 | 284 | +25 |
| ENPH | n = 20 | +0.16 | +3.2 | 0 | 16 | 9 | 5 | 2 | 238 | +6 |
| TSLA | n = 17 | +2.73 | +46.4 | 1 | 11 | 5 | 2 | 4 | 226 | +38 |
| SHOP | n = 27 | +3.02 | +81.4 | 2 | 21 | 7 | 10 | 4 | 202 | +27 |
| ROKU | n = 19 | +0.49 | +9.4 | 0 | 15 | 9 | 5 | 1 | 195 | +7 |
| ETSY | n = 25 | -0.19 | -4.7 | 0 | 18 | 11 | 6 | 1 | 180 | +0 |
| TTD | n = 20 | -0.34 | -6.8 | 0 | 14 | 8 | 6 | 0 | 153 | -2 |
| TDOC | n = 29 | -0.25 | -7.3 | 0 | 13 | 5 | 8 | 0 | 131 | -0 |
| NVDA | n = 18 | +0.20 | +3.6 | 1 | 12 | 8 | 3 | 1 | 130 | +2 |
| AMC | n = 22 | +1.54 | +33.9 | 1 | 4 | 3 | 0 | 1 | 123 | +21 |
| SNAP | n = 15 | -0.53 | -8.0 | 0 | 9 | 6 | 3 | 0 | 122 | -3 |
| NXH | n = 17 | +3.65 | +62.1 | 1 | 6 | 1 | 4 | 1 | 117 | +29 |
| AMD | n = 17 | +1.17 | +19.8 | 1 | 10 | 4 | 4 | 2 | 115 | +10 |
| PENN | n = 16 | -0.09 | -1.5 | 0 | 11 | 6 | 4 | 1 | 108 | +1 |
| SE | n = 17 | +2.25 | +38.3 | 2 | 10 | 3 | 5 | 2 | 101 | +18 |
| FSLY | n = 8 | +3.99 | +31.9 | 1 | 5 | 3 | 1 | 1 | 99 | +25 |
| NVAX | n = 13 | +0.49 | +6.4 | 0 | 4 | 1 | 3 | 0 | 94 | +2 |
| PINS | n = 15 | +0.84 | +12.7 | 0 | 8 | 4 | 2 | 2 | 91 | +17 |
| CVNA | n = 20 | +0.08 | +1.6 | 0 | 8 | 5 | 2 | 1 | 91 | +4 |
| NET | n = 10 | +1.07 | +10.7 | 0 | 8 | 4 | 2 | 2 | 89 | +8 |
| FVRR | n = 10 | +2.84 | +28.4 | 2 | 8 | 4 | 2 | 2 | 89 | +11 |
| PLUG | n = 4 | +14.79 | +59.2 | 1 | 3 | 2 | 0 | 1 | 80 | +24 |
| W | n = 17 | -0.69 | -11.7 | 0 | 8 | 6 | 2 | 0 | 77 | +1 |
| CRWD | n = 15 | +0.49 | +7.3 | 0 | 8 | 2 | 5 | 1 | 75 | +4 |
| BLNK | n = 9 | -0.54 | -4.9 | 0 | 3 | 3 | 0 | 0 | 75 | -2 |
| PTON | n = 10 | +0.51 | +5.1 | 0 | 6 | 2 | 3 | 1 | 72 | +2 |
| DDOG | n = 11 | +1.87 | +20.6 | 1 | 5 | 3 | 0 | 2 | 68 | +16 |
| SPCE | n = 9 | +0.63 | +5.7 | 0 | 6 | 3 | 2 | 1 | 65 | +4 |
| NIO | n = 7 | +0.26 | +1.8 | 0 | 5 | 2 | 3 | 0 | 64 | +1 |
| ZM | n = 7 | -0.14 | -1.0 | 0 | 5 | 3 | 2 | 0 | 64 | +1 |
| LULU | n = 7 | -0.61 | -4.3 | 0 | 5 | 5 | 0 | 0 | 46 | -2 |
| UPST | n = 3 | -0.44 | -1.3 | 0 | 2 | 2 | 0 | 0 | 43 | -1 |
| APPS | n = 8 | +1.72 | +13.8 | 0 | 5 | 2 | 1 | 2 | 42 | +5 |
| DOCU | n = 14 | -0.53 | -7.4 | 0 | 6 | 2 | 4 | 0 | 42 | +0 |
| LVGO | n = 7 | -0.29 | -2.0 | 0 | 2 | 2 | 0 | 0 | 41 | -1 |
| DKNG | n = 6 | -1.00 | -6.0 | 0 | 4 | 4 | 0 | 0 | 29 | -2 |
| QS | n = 5 | -0.58 | -2.9 | 0 | 2 | 1 | 1 | 0 | 27 | -0 |
| FUBO | n = 4 | -0.70 | -2.8 | 0 | 0 | 0 | 0 | 0 | 0 | +0 |

## 5. Side rows

Day-0 stop-out share by stop width (width_adr = (fill - stop) / (ADR20 x fill); quartiles cut per era on the mature population):

| era | width quartile (ADR) | n | stopped on the fill day | mean R | 10R trades | best 60-session move >= 5 ADR (complete windows) |
|---|---|---|---|---|---|---|
| 2017-21 | Q1 <= 0.32 | n = 3,341 | 68.1% | -0.119 | 54 | 39.2% (n = 3,341) |
| 2017-21 | Q2 0.32-0.45 | n = 3,341 | 42.8% | +0.074 | 56 | 43.5% (n = 3,341) |
| 2017-21 | Q3 0.45-0.63 | n = 3,340 | 24.8% | +0.047 | 35 | 43.8% (n = 3,340) |
| 2017-21 | Q4 > 0.63 | n = 3,341 | 11.6% | +0.100 | 20 | 45.8% (n = 3,341) |
| 2022-24 | Q1 <= 0.33 | n = 2,239 | 66.8% | -0.190 | 30 | 34.2% (n = 2,023) |
| 2022-24 | Q2 0.33-0.48 | n = 2,239 | 43.9% | -0.213 | 25 | 35.7% (n = 2,033) |
| 2022-24 | Q3 0.48-0.65 | n = 2,239 | 25.9% | -0.198 | 16 | 35.0% (n = 1,994) |
| 2022-24 | Q4 > 0.65 | n = 2,239 | 12.1% | -0.075 | 14 | 35.8% (n = 1,997) |

R vs ADR (why 10R is not a big move): realized R x width_adr = pnl in ADR units.

| era | n 10R trades | their median stop width (ADR) | their median pnl (ADR) | their median best 60-session move (ADR) | fills with best move >= 10 ADR that were NOT 10R trades |
|---|---|---|---|---|---|
| 2017-21 | n = 165 | 0.38 | 6.0 | 13.5 | 1730 of 1855 |
| 2022-24 | n = 69 | 0.40 | 5.9 | 12.3 | 759 of 808 |

