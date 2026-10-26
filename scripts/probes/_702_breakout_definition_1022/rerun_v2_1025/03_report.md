# 2017-21

## A. Was our trigger early? (2017-21; n = 15,894 published fills with a readable E bar)

| era | n fills | fill distance below the base high (ADR20 at D): median | quartiles | p10 / p90 | fill already at/above the base high | E's own close above it (s_c = 0) | trendline level below the base high, median (ADR) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 15,894 | 1.17 | 0.42 .. 2.14 | 0.04 / 3.13 | 1,284 (8.1%) | 1,849 (11.6%) | 1.35 |

First CLOSE above the base high (E = session 0; cumulative; 'never' needs the 60-session window complete):

| era | n (window complete) | on E itself | by session 5 | by session 20 | by session 60 | never within 60 | window cut (unknown) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 15,894 | 1,849 (11.6%) | 5,828 (36.7%) | 9,528 (59.9%) | 12,050 (75.8%) | 3,844 (24.2%) | 0 |

Sessions from our fill (E) to that first close above the base high, where it happened within 60:

| era | n | median | quartiles | p90 | share at s_c <= 5 | <= 20 |
|---|---|---|---|---|---|---|
| 2017-21 | n = 12,050 | 6 | 1 .. 17 | 34 | 48.4% | 79.1% |

The big movers (s\* = yesterday's first session 1..60 whose HIGH reached fill + T x ADR20; 60-session window complete): did the stock clear the base high on a close first, and how long from that close to the move?

| era / threshold | n big movers | closed above the base high at or before s\* (s_c <= s\*) | move started before any close above it (s_c > s\*) | never closed above it within 60 | fill -> first close above base high (s_c): median / quartiles | that close -> the move (s\* - s_c): median / quartiles | fill -> move (s\*): median | s_c <= 5 | s_c <= 20 |
|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 6,765 | 6,668 (98.6%) | 69 (1.0%) | 28 (0.4%) | 6 / 2 .. 15 | 13 / 5 .. 27 | 26 | 49.0% of those | 81.7% |
| 2017-21, +10 ADR | n = 2,151 | 2,151 (100.0%) | 0 (0.0%) | 0 (0.0%) | 5 / 1 .. 12 | 29 / 16 .. 41 | 40 | 52.1% of those | 86.8% |

Same, for the fills that never made the move (A bin): how often did they still clear the base high on a close?

| era | n fills with no +5 ADR move within 60 | closed above the base high within 60 | never |
|---|---|---|---|
| 2017-21 | n = 9,129 | 5,313 (58.2%) | 3,816 (41.8%) |

Where the fill sat vs the move rate (distance below the base high in ADR20 at D, quartiles cut on this era; from the fill, yesterday's columns):

| era | distance quartile | n (window complete) | >= 5 ADR within 60 | >= 10 ADR | mean R | closed above the base high within 60 |
|---|---|---|---|---|---|---|
| 2017-21 | Q1 <= 0.42 (at/near the base high) | n = 3,974 | 42.6% | 13.9% | -0.081 | 93.3% |
| 2017-21 | Q2 0.42-1.17 | n = 3,973 | 43.5% | 13.6% | +0.111 | 84.1% |
| 2017-21 | Q3 1.17-2.14 | n = 3,973 | 44.4% | 14.4% | +0.064 | 72.9% |
| 2017-21 | Q4 > 2.14 (deep in the base) | n = 3,974 | 39.8% | 12.2% | -0.007 | 52.9% |

## B. Does a REAL breakout follow through? (2017-21; every entry against its matched control; tail first)

Composition of the entry sets (one row per (ticker, entry day) for the new sets):

| era | entry set | n | entry days | median ADR20 (unit) | median 63-session return at t-1 | median 20-session dollar volume | notes |
|---|---|---|---|---|---|---|---|
| 2017-21 | our fills (C0 tl ORH5, from E's close) | n = 15,894 | 1197 | 0.0420 | +0.203 | $36M | published rows; retrigger_chain = 1: 2,831 |
| 2017-21 | R3 — E meets the expansion test | n = 636 | 406 | 0.0462 | +0.202 | $35M | range >= 1 ADR: 5,640 (35.5%); close in top 30%: 6,886 (43.3%); volume >= 1.5x: 1,850 (11.6%) |
| 2017-21 | R3 — E does NOT meet it | n = 15,258 | 1192 | 0.0418 | +0.203 | $36M | |
| 2017-21 | R1 base-high close (ADR20 at t-1) | n = 10,912 | 1129 | 0.0386 | +0.222 | $35M | from 12,023 fills reaching a close above the base high in sessions 0..59; dedup removed 1111; R1 day = E itself 1,607 (14.7%); median s_c 6; close over the base high median 0.33 ADR; next-open gap median +0.04 ADR; splits in the volume window unknown |
| 2017-21 | R2 expansion breakout (R1 + range/close/volume) | n = 1,902 | 761 | 0.0407 | +0.208 | $31M | range >= 1 ADR: 6,713 (61.5%); close in top 30%: 7,820 (71.7%); volume >= 1.5x: 3,149 (28.9%); R2 day = E itself 262 |
| 2017-21 | R1 but NOT R2 | n = 9,010 | 1091 | 0.0381 | +0.225 | $36M | |
| 2017-21 | K = com (ORH5 first break, from E's close) | n = 18,572 | 1200 | 0.0416 | +0.190 | $35M | fill below the base high: median 1.20 ADR; fill at/above it 4.6%; includes the 5 non-mature fills |
| 2017-21 | K = tl (ORH5 first break, from E's close) | n = 15,903 | 1198 | 0.0420 | +0.203 | $36M | fill below the base high: median 1.17 ADR; fill at/above it 8.1%; includes the 5 non-mature fills |

**our fills (from E's close) — composition.** n = 15,894 over 1197 entry days; control rows on those days 2,510,927. ADR20 (the entry's unit): median 0.0420, decile cuts [0.0254, 0.0302, 0.0341, 0.038, 0.042, 0.0465, 0.0522, 0.0605, 0.0754]; 63-session return quintile cuts [0.011, 0.149, 0.26, 0.433] (entries' median +0.203 vs the pooled control's +0.018).

| 2017-21: our fills (from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 15,894 | 42.66% | 41.37% | 1.28% | -0.31% .. 2.83% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 15,894 | 13.52% | 12.82% | 0.70% | -0.14% .. 1.68% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 15,894 | 1.67% | 1.74% | -0.07% | -0.39% .. 0.23% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 15,894 | 15.72% | 15.40% | 0.32% | -0.65% .. 1.46% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 15,893 | +0.005 | +0.014 | -0.009 | -0.027 .. +0.007 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 15,886 | +0.126 | +0.131 | -0.005 | -0.062 .. +0.049 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 15,864 | +0.425 | +0.380 | +0.045 | -0.081 .. +0.166 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 15,762 | +1.082 | +0.787 | +0.296 | +0.108 .. +0.514 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 15,894 | 42.66% | 41.80% | 0.86% | -0.69% .. 2.36% | 144 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 15,894 | 13.52% | 13.14% | 0.38% | -0.41% .. 1.29% | 144 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 15,894 | 1.67% | 1.76% | -0.09% | -0.41% .. 0.20% | 144 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 15,894 | 15.72% | 15.55% | 0.17% | -0.86% .. 1.30% | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 15,893 | +0.005 | +0.019 | -0.014 | -0.029 .. -0.000 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 15,886 | +0.126 | +0.147 | -0.021 | -0.065 .. +0.021 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 15,864 | +0.425 | +0.405 | +0.020 | -0.091 .. +0.124 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 15,762 | +1.082 | +0.956 | +0.127 | -0.045 .. +0.319 | 155 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 6,780 entries / 233,405 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 2,149 / 71,946 | 40 | 39 | - | - | - |

**R3: E meets the expansion test — composition.** n = 636 over 406 entry days; control rows on those days 845,454. ADR20 (the entry's unit): median 0.0462, decile cuts [0.0268, 0.0327, 0.0374, 0.0406, 0.0462, 0.0519, 0.0583, 0.0672, 0.0869]; 63-session return quintile cuts [0.011, 0.149, 0.258, 0.467] (entries' median +0.202 vs the pooled control's +0.018).

| 2017-21: R3: E meets the expansion test | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 636 | 42.30% | 39.06% | 3.24% | -0.10% .. 6.79% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 636 | 14.47% | 13.12% | 1.34% | -1.40% .. 4.12% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 636 | 3.30% | 2.18% | 1.12% | -0.52% .. 2.91% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 636 | 17.30% | 15.40% | 1.90% | -1.62% .. 5.56% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 636 | -0.063 | +0.031 | -0.093 | -0.213 .. +0.014 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 636 | +0.064 | +0.110 | -0.046 | -0.286 .. +0.197 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 636 | +0.201 | +0.295 | -0.094 | -0.378 .. +0.211 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 633 | +0.421 | +0.249 | +0.172 | -0.225 .. +0.585 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 636 | 42.30% | 39.16% | 3.14% | -0.47% .. 6.75% | 8 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 636 | 14.47% | 13.00% | 1.47% | -1.51% .. 4.24% | 8 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 636 | 3.30% | 2.20% | 1.10% | -0.55% .. 2.90% | 8 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 636 | 17.30% | 15.37% | 1.93% | -1.59% .. 5.48% | 8 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 636 | -0.063 | +0.030 | -0.093 | -0.209 .. +0.015 | 8 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 636 | +0.064 | +0.073 | -0.009 | -0.245 .. +0.234 | 8 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 636 | +0.201 | +0.290 | -0.089 | -0.393 .. +0.236 | 8 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 633 | +0.421 | +0.376 | +0.045 | -0.386 .. +0.470 | 9 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 269 entries / 12,355 control rows | 26 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 92 / 3,891 | 32 | 37 | - | - | - |

**R3: E does not meet it — composition.** n = 15,258 over 1192 entry days; control rows on those days 2,499,862. ADR20 (the entry's unit): median 0.0418, decile cuts [0.0253, 0.0301, 0.034, 0.0378, 0.0418, 0.0463, 0.0519, 0.0602, 0.075]; 63-session return quintile cuts [0.011, 0.149, 0.26, 0.432] (entries' median +0.203 vs the pooled control's +0.018).

| 2017-21: R3: E does not meet it | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 15,258 | 42.67% | 41.48% | 1.19% | -0.41% .. 2.74% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 15,258 | 13.48% | 12.82% | 0.66% | -0.19% .. 1.67% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 15,258 | 1.60% | 1.72% | -0.12% | -0.41% .. 0.15% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 15,258 | 15.66% | 15.41% | 0.24% | -0.71% .. 1.33% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 15,257 | +0.008 | +0.014 | -0.006 | -0.024 .. +0.011 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 15,250 | +0.129 | +0.132 | -0.003 | -0.058 .. +0.047 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 15,228 | +0.434 | +0.385 | +0.049 | -0.078 .. +0.174 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 15,129 | +1.110 | +0.811 | +0.300 | +0.105 .. +0.524 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 15,258 | 42.67% | 42.01% | 0.66% | -0.88% .. 2.16% | 128 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 15,258 | 13.48% | 13.22% | 0.27% | -0.52% .. 1.19% | 128 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 15,258 | 1.60% | 1.75% | -0.15% | -0.44% .. 0.13% | 128 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 15,258 | 15.66% | 15.60% | 0.05% | -0.94% .. 1.16% | 128 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 15,257 | +0.008 | +0.018 | -0.011 | -0.026 .. +0.004 | 128 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 15,250 | +0.129 | +0.151 | -0.022 | -0.063 .. +0.017 | 128 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 15,228 | +0.434 | +0.416 | +0.018 | -0.094 .. +0.124 | 128 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 15,129 | +1.110 | +0.991 | +0.119 | -0.062 .. +0.313 | 138 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 6,511 entries / 228,812 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 2,057 / 70,489 | 40 | 39 | - | - | - |

**R1 base-high close — entry at that close — composition.** n = 10,912 over 1129 entry days; control rows on those days 2,373,849. ADR20 (the entry's unit): median 0.0386, decile cuts [0.0231, 0.0276, 0.0313, 0.0348, 0.0386, 0.0428, 0.0477, 0.0549, 0.0659]; 63-session return quintile cuts [0.053, 0.172, 0.27, 0.415] (entries' median +0.222 vs the pooled control's +0.018).

| 2017-21: R1 base-high close — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 10,912 | 43.13% | 41.97% | 1.16% | -0.97% .. 3.16% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 10,912 | 14.59% | 13.05% | 1.54% | 0.79% .. 2.50% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 10,912 | 2.41% | 1.79% | 0.62% | 0.11% .. 1.15% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 10,912 | 16.22% | 15.18% | 1.04% | -0.72% .. 2.67% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 10,911 | +0.021 | +0.019 | +0.002 | -0.019 .. +0.022 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 10,907 | +0.122 | +0.095 | +0.028 | -0.027 .. +0.085 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 10,879 | +0.333 | +0.296 | +0.037 | -0.093 .. +0.169 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 10,799 | +1.094 | +0.834 | +0.259 | +0.056 .. +0.487 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 10,912 | 43.13% | 42.12% | 1.00% | -0.66% .. 2.71% | 89 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 10,912 | 14.59% | 13.17% | 1.42% | 0.63% .. 2.41% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 10,912 | 2.41% | 1.81% | 0.60% | 0.11% .. 1.12% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 10,912 | 16.22% | 15.10% | 1.12% | -0.48% .. 2.58% | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 10,911 | +0.021 | +0.023 | -0.002 | -0.021 .. +0.016 | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 10,907 | +0.122 | +0.101 | +0.021 | -0.024 .. +0.070 | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 10,879 | +0.333 | +0.292 | +0.041 | -0.059 .. +0.145 | 92 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 10,799 | +1.094 | +0.991 | +0.103 | -0.067 .. +0.305 | 93 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 4,706 entries / 167,157 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,592 / 52,083 | 39 | 40 | - | - | - |

**R1 — entry at the next open — composition.** n = 10,912 over 1129 entry days; control rows on those days 2,373,849. ADR20 (the entry's unit): median 0.0386, decile cuts [0.0231, 0.0276, 0.0313, 0.0348, 0.0386, 0.0428, 0.0477, 0.0549, 0.0659]; 63-session return quintile cuts [0.053, 0.172, 0.27, 0.415] (entries' median +0.222 vs the pooled control's +0.018).

| 2017-21: R1 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 10,912 | 42.27% | 41.43% | 0.84% | -1.43% .. 3.06% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 10,912 | 14.29% | 12.78% | 1.51% | 0.72% .. 2.52% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 10,912 | 1.86% | 1.51% | 0.35% | -0.04% .. 0.78% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 10,912 | 15.34% | 14.59% | 0.75% | -1.29% .. 2.57% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 10,911 | -0.043 | -0.024 | -0.020 | -0.033 .. -0.004 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 10,907 | +0.059 | +0.053 | +0.006 | -0.049 .. +0.067 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 10,879 | +0.270 | +0.254 | +0.016 | -0.124 .. +0.154 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 10,799 | +1.028 | +0.791 | +0.237 | +0.030 .. +0.471 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 10,912 | 42.27% | 41.50% | 0.77% | -1.05% .. 2.62% | 89 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 10,912 | 14.29% | 12.89% | 1.40% | 0.61% .. 2.38% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 10,912 | 1.86% | 1.53% | 0.33% | -0.07% .. 0.75% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 10,912 | 15.34% | 14.55% | 0.79% | -1.04% .. 2.36% | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 10,911 | -0.043 | -0.028 | -0.015 | -0.029 .. +0.001 | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 10,907 | +0.059 | +0.051 | +0.008 | -0.038 .. +0.061 | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 10,879 | +0.270 | +0.242 | +0.028 | -0.076 .. +0.139 | 92 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 10,799 | +1.028 | +0.938 | +0.090 | -0.082 .. +0.294 | 93 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 4,613 entries / 165,563 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,559 / 51,169 | 39 | 40 | - | - | - |

**R1 — measured from the NEXT close (same-day-effect check) — composition.** n = 10,912 over 1129 entry days; control rows on those days 2,373,849. ADR20 (the entry's unit): median 0.0386, decile cuts [0.0231, 0.0276, 0.0313, 0.0348, 0.0386, 0.0428, 0.0477, 0.0549, 0.0659]; 63-session return quintile cuts [0.053, 0.172, 0.27, 0.415] (entries' median +0.222 vs the pooled control's +0.018).

| 2017-21: R1 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 10,912 | 43.08% | 42.01% | 1.07% | -1.17% .. 3.19% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 10,912 | 14.72% | 13.07% | 1.65% | 0.70% .. 2.79% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 10,912 | 2.25% | 1.78% | 0.47% | 0.04% .. 0.95% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 10,912 | 16.32% | 15.18% | 1.15% | -0.64% .. 2.74% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 10,910 | +0.015 | +0.029 | -0.014 | -0.044 .. +0.013 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 10,905 | +0.123 | +0.086 | +0.037 | -0.023 .. +0.097 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 10,876 | +0.340 | +0.295 | +0.045 | -0.101 .. +0.184 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 10,799 | +1.064 | +0.830 | +0.234 | +0.022 .. +0.469 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 10,912 | 43.08% | 42.14% | 0.94% | -0.79% .. 2.66% | 89 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 10,912 | 14.72% | 13.22% | 1.50% | 0.59% .. 2.60% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 10,912 | 2.25% | 1.79% | 0.46% | 0.06% .. 0.94% | 89 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 10,912 | 16.32% | 15.07% | 1.25% | -0.27% .. 2.65% | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 10,910 | +0.015 | +0.032 | -0.018 | -0.044 .. +0.009 | 89 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 10,905 | +0.123 | +0.091 | +0.031 | -0.015 .. +0.082 | 88 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 10,876 | +0.340 | +0.290 | +0.050 | -0.055 .. +0.162 | 92 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 10,799 | +1.064 | +0.990 | +0.074 | -0.096 .. +0.276 | 93 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 4,701 entries / 167,711 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,606 / 52,550 | 39 | 40 | - | - | - |

**R2 expansion breakout — entry at that close — composition.** n = 1,902 over 761 entry days; control rows on those days 1,589,563. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0251, 0.0296, 0.0335, 0.0372, 0.0407, 0.0453, 0.0515, 0.0597, 0.0736]; 63-session return quintile cuts [0.052, 0.159, 0.261, 0.421] (entries' median +0.208 vs the pooled control's +0.018).

| 2017-21: R2 expansion breakout — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,902 | 44.53% | 41.04% | 3.49% | 0.85% .. 6.00% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,902 | 16.30% | 13.68% | 2.62% | 1.01% .. 4.37% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,902 | 4.05% | 2.24% | 1.81% | 0.47% .. 3.06% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,902 | 18.24% | 15.50% | 2.75% | 0.47% .. 5.00% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,902 | -0.039 | +0.022 | -0.061 | -0.116 .. -0.008 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,902 | +0.066 | +0.084 | -0.018 | -0.143 .. +0.101 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,901 | +0.264 | +0.300 | -0.036 | -0.218 .. +0.149 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,891 | +0.729 | +0.685 | +0.044 | -0.286 .. +0.385 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,902 | 44.53% | 41.29% | 3.24% | 1.02% .. 5.36% | 24 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,902 | 16.30% | 14.09% | 2.21% | 0.57% .. 3.96% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,902 | 4.05% | 2.21% | 1.84% | 0.56% .. 3.09% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,902 | 18.24% | 15.51% | 2.74% | 0.61% .. 4.88% | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,902 | -0.039 | +0.024 | -0.063 | -0.114 .. -0.009 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,902 | +0.066 | +0.080 | -0.014 | -0.131 .. +0.104 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,901 | +0.264 | +0.326 | -0.063 | -0.257 .. +0.134 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,891 | +0.729 | +0.852 | -0.122 | -0.414 .. +0.173 | 25 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 847 entries / 43,819 control rows | 25 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 310 / 14,208 | 38 | 38 | - | - | - |

**R2 — entry at the next open — composition.** n = 1,902 over 761 entry days; control rows on those days 1,589,563. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0251, 0.0296, 0.0335, 0.0372, 0.0407, 0.0453, 0.0515, 0.0597, 0.0736]; 63-session return quintile cuts [0.052, 0.159, 0.261, 0.421] (entries' median +0.208 vs the pooled control's +0.018).

| 2017-21: R2 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,902 | 43.38% | 40.67% | 2.70% | -0.04% .. 5.29% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,902 | 15.93% | 13.40% | 2.54% | 1.04% .. 4.14% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,902 | 3.15% | 1.87% | 1.29% | 0.31% .. 2.23% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,902 | 17.77% | 14.87% | 2.90% | 0.61% .. 5.14% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,902 | -0.088 | -0.014 | -0.073 | -0.113 .. -0.031 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,902 | +0.019 | +0.048 | -0.029 | -0.147 .. +0.082 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,901 | +0.217 | +0.262 | -0.045 | -0.215 .. +0.133 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,891 | +0.678 | +0.646 | +0.033 | -0.294 .. +0.373 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,902 | 43.38% | 40.87% | 2.50% | 0.08% .. 4.70% | 24 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,902 | 15.93% | 13.86% | 2.07% | 0.56% .. 3.68% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,902 | 3.15% | 1.86% | 1.30% | 0.42% .. 2.19% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,902 | 17.77% | 14.93% | 2.84% | 0.61% .. 4.94% | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,902 | -0.088 | -0.017 | -0.071 | -0.111 .. -0.029 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,902 | +0.019 | +0.039 | -0.020 | -0.129 .. +0.086 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,901 | +0.217 | +0.284 | -0.067 | -0.262 .. +0.120 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,891 | +0.678 | +0.805 | -0.127 | -0.419 .. +0.171 | 25 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 825 entries / 43,538 control rows | 25 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 303 / 14,037 | 38 | 39 | - | - | - |

**R2 — measured from the NEXT close (same-day-effect check) — composition.** n = 1,902 over 761 entry days; control rows on those days 1,589,563. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0251, 0.0296, 0.0335, 0.0372, 0.0407, 0.0453, 0.0515, 0.0597, 0.0736]; 63-session return quintile cuts [0.052, 0.159, 0.261, 0.421] (entries' median +0.208 vs the pooled control's +0.018).

| 2017-21: R2 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,902 | 44.22% | 41.06% | 3.16% | 0.27% .. 5.90% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,902 | 16.30% | 13.61% | 2.69% | 1.33% .. 4.21% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,902 | 3.47% | 2.09% | 1.38% | 0.37% .. 2.42% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,902 | 17.98% | 15.31% | 2.67% | 0.50% .. 4.72% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,901 | -0.025 | +0.019 | -0.043 | -0.117 .. +0.023 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,902 | +0.101 | +0.076 | +0.025 | -0.099 .. +0.138 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,901 | +0.319 | +0.297 | +0.022 | -0.147 .. +0.196 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,891 | +0.722 | +0.659 | +0.064 | -0.279 .. +0.405 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,902 | 44.22% | 41.52% | 2.70% | 0.30% .. 4.98% | 24 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,902 | 16.30% | 13.92% | 2.38% | 0.86% .. 3.98% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,902 | 3.47% | 1.98% | 1.49% | 0.55% .. 2.50% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,902 | 17.98% | 15.32% | 2.66% | 0.63% .. 4.52% | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,901 | -0.025 | +0.016 | -0.041 | -0.108 .. +0.020 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,902 | +0.101 | +0.073 | +0.028 | -0.088 .. +0.131 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,901 | +0.319 | +0.317 | +0.002 | -0.181 .. +0.185 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,891 | +0.722 | +0.810 | -0.087 | -0.388 .. +0.214 | 25 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 841 entries / 44,178 control rows | 25 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 310 / 14,321 | 37 | 39 | - | - | - |

**R1 but NOT R2 — entry at that close — composition.** n = 9,010 over 1091 entry days; control rows on those days 2,292,786. ADR20 (the entry's unit): median 0.0381, decile cuts [0.0228, 0.0272, 0.0309, 0.0344, 0.0381, 0.0422, 0.0469, 0.0541, 0.0645]; 63-session return quintile cuts [0.053, 0.175, 0.273, 0.415] (entries' median +0.225 vs the pooled control's +0.018).

| 2017-21: R1 but NOT R2 — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 9,010 | 42.83% | 42.13% | 0.70% | -1.54% .. 2.89% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 9,010 | 14.23% | 12.94% | 1.29% | 0.50% .. 2.30% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 9,010 | 2.06% | 1.70% | 0.36% | -0.09% .. 0.91% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 9,010 | 15.79% | 15.14% | 0.66% | -1.07% .. 2.30% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 9,009 | +0.033 | +0.018 | +0.015 | -0.005 .. +0.035 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 9,005 | +0.134 | +0.097 | +0.037 | -0.009 .. +0.088 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 8,978 | +0.347 | +0.296 | +0.052 | -0.087 .. +0.190 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 8,908 | +1.171 | +0.862 | +0.309 | +0.095 .. +0.561 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 9,010 | 42.83% | 42.46% | 0.37% | -1.34% .. 2.17% | 75 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 9,010 | 14.23% | 13.06% | 1.17% | 0.37% .. 2.14% | 75 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 9,010 | 2.06% | 1.75% | 0.31% | -0.17% .. 0.87% | 75 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 9,010 | 15.79% | 15.04% | 0.75% | -0.83% .. 2.25% | 75 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 9,009 | +0.033 | +0.022 | +0.012 | -0.005 .. +0.030 | 75 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 9,005 | +0.134 | +0.109 | +0.025 | -0.015 .. +0.070 | 75 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 8,978 | +0.347 | +0.293 | +0.054 | -0.045 .. +0.164 | 77 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 8,908 | +1.171 | +1.008 | +0.162 | -0.015 .. +0.380 | 79 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 3,859 entries / 140,536 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,282 / 43,022 | 39 | 40 | - | - | - |

**K = com (ORH5 first break, from E's close) — composition.** n = 18,572 over 1200 entry days; control rows on those days 2,518,345. ADR20 (the entry's unit): median 0.0416, decile cuts [0.0254, 0.0302, 0.0339, 0.0376, 0.0416, 0.0461, 0.0516, 0.0594, 0.0732]; 63-session return quintile cuts [0.002, 0.135, 0.246, 0.41] (entries' median +0.190 vs the pooled control's +0.018).

| 2017-21: K = com (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 18,572 | 43.18% | 41.40% | 1.78% | 0.08% .. 3.37% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 18,572 | 14.02% | 12.88% | 1.14% | 0.26% .. 2.15% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 18,572 | 1.76% | 1.67% | 0.08% | -0.18% .. 0.34% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 18,572 | 16.01% | 15.32% | 0.69% | -0.25% .. 1.77% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 18,570 | +0.009 | +0.019 | -0.010 | -0.026 .. +0.007 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 18,560 | +0.091 | +0.110 | -0.019 | -0.088 .. +0.043 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 18,533 | +0.393 | +0.319 | +0.073 | -0.053 .. +0.192 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 18,409 | +1.172 | +0.835 | +0.337 | +0.155 .. +0.524 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 18,572 | 43.18% | 41.85% | 1.34% | -0.22% .. 2.75% | 150 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 18,572 | 14.02% | 13.20% | 0.82% | 0.08% .. 1.67% | 150 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 18,572 | 1.76% | 1.72% | 0.03% | -0.22% .. 0.29% | 150 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 18,572 | 16.01% | 15.52% | 0.50% | -0.50% .. 1.57% | 150 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 18,570 | +0.009 | +0.022 | -0.013 | -0.027 .. +0.001 | 150 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 18,560 | +0.091 | +0.124 | -0.033 | -0.091 .. +0.018 | 151 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 18,533 | +0.393 | +0.332 | +0.061 | -0.047 .. +0.164 | 151 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 18,409 | +1.172 | +1.002 | +0.169 | +0.022 .. +0.324 | 159 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 8,020 entries / 261,841 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 2,603 / 80,231 | 40 | 39 | - | - | - |

**K = tl (ORH5 first break, from E's close) — composition.** n = 15,903 over 1198 entry days; control rows on those days 2,513,202. ADR20 (the entry's unit): median 0.0420, decile cuts [0.0254, 0.0302, 0.0341, 0.038, 0.042, 0.0465, 0.0522, 0.0605, 0.0754]; 63-session return quintile cuts [0.011, 0.149, 0.26, 0.433] (entries' median +0.203 vs the pooled control's +0.018).

| 2017-21: K = tl (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 15,903 | 42.65% | 41.38% | 1.28% | -0.32% .. 2.83% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 15,903 | 13.53% | 12.82% | 0.70% | -0.14% .. 1.69% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 15,903 | 1.67% | 1.74% | -0.08% | -0.39% .. 0.23% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 15,903 | 15.73% | 15.40% | 0.33% | -0.64% .. 1.46% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 15,902 | +0.005 | +0.014 | -0.009 | -0.027 .. +0.008 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 15,892 | +0.126 | +0.131 | -0.004 | -0.062 .. +0.050 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 15,868 | +0.426 | +0.380 | +0.046 | -0.080 .. +0.168 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 15,763 | +1.082 | +0.787 | +0.295 | +0.108 .. +0.514 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 15,903 | 42.65% | 41.80% | 0.85% | -0.69% .. 2.36% | 144 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 15,903 | 13.53% | 13.14% | 0.38% | -0.39% .. 1.29% | 144 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 15,903 | 1.67% | 1.76% | -0.10% | -0.41% .. 0.20% | 144 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 15,903 | 15.73% | 15.55% | 0.18% | -0.85% .. 1.32% | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 15,902 | +0.005 | +0.019 | -0.014 | -0.029 .. -0.001 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 15,892 | +0.126 | +0.147 | -0.021 | -0.064 .. +0.022 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 15,868 | +0.426 | +0.405 | +0.021 | -0.088 .. +0.125 | 144 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 15,763 | +1.082 | +0.957 | +0.125 | -0.046 .. +0.314 | 155 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 6,783 entries / 233,444 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 2,151 / 71,954 | 40 | 39 | - | - | - |

