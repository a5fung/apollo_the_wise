# #702 — his exit on 2022–24: the +2R / day / combo partial, the 10- or 20-day trail switches, the stop variants (read 2026-10-18)

**MEASUREMENT ONLY. $0. Nothing here changes or proposes to change a strategy, an entry or exit rule, a stop, a size, a
safeguard or any live trade state — the stop and the exit are the operator's call (THE LINE); every row below is a
REPORTED alternative, never a choice.** The registered primary (`docs/analysis/cb_preregistration_2026-10-18.md` §3:
trendline level, ORH5, the low-of-day stop, `p33_s3_t10`) is unchanged and sits in every table as the reference row.
The holdout (2025–26) is untouched: `runner.py holdout` still refuses `--levels` and nothing here opened a holdout row.

## 0. Answer first

- **His exit reads a little less bad than the article's day-3 partial on the big populations, inside the noise, and the
  pattern still loses in 2022–24.** On the trendline level, C0 (n = 8,985 mature trades at ORH5): the registered arm
  loses 0.087 ADR per trade (−0.19R); the best of the 125 new arm × stop combos that keep the same trades, "sell 1/3 at
  +2R or at the close of day 3 — whichever first, breakeven, trail the 20-day" on the day-low stop capped at half an
  ADR, loses 0.070 ADR (−0.18R), interval [−0.29, −0.05]: a 0.017-ADR difference with a bootstrap half-width of
  ±0.12R. The same ordering holds on `com` (−0.093 → −0.066 ADR, n = 10,739) and `comb` (−0.064 → −0.053, n = 6,697).
- **The +2R partial trades the tail for the win rate.** Every +2R / combo arm has a LOWER share of ≥ 5R trades than the
  day-3 arm (C0 `tl`: 2.6–2.8% vs 3.6%) and a higher win rate (29–31% vs 24%): a third sold at +2R caps the biggest
  winners; the breakeven stop then lets the rest out flat. The 10- vs 20-day choice and both of his switches move the
  mean by ≤ 0.01 ADR; the switches resolve to the 20-day on most trades.
- **On C1 (the article's cell, 79 trades on `tl`) the combo arm reads +0.32R where the registered arm reads −0.05R, but
  the interval is [−0.26, +1.19]** — a handful of trades carry it (≥ 5R: 4 of 79 vs 3 of 79) — and on `com` (91) / `comb`
  (64) the same arm reads WORSE than the registered one (−0.28R vs −0.16R; −0.36R vs −0.49R is the one C1 improvement,
  from a 1.6% tail). Not a signal; a lead for the forward read at most.
- **The wider stops do not help; the base-low stop is a different population.** The level − ½ ADR stop drops 1,149 of
  8,989 `tl` fills as wider than one ADR and reads the same as the registered arm on the trades it keeps (−0.084 vs
  −0.085 ADR, n = 7,836 / 7,838). The base-low stop keeps 755 of 8,989 (the bases whose low sits within one ADR of
  the fill — the tightest 8%) and on those 755 reads −0.011 ADR against −0.047 for the registered arm on the SAME
  trades: a 0.04-ADR edge on a hand-picked tenth, interval spanning zero. Capping the day-low stop at half an ADR
  (`lod_cap05`) changes nothing by itself (−0.083 vs −0.087 ADR under the registered timing); flooring it at half an
  ADR (`lod_floor05`) lowers R and raises the win rate as a wider stop should (−0.16R / 28% win vs −0.19R / 24%) and
  costs 0.006 ADR.
- **Tightness: the tightest fifth of bases is still the worst fifth under his exit** (C0 `tl`, last-5-day range in ADR
  units, n ≈ 1,797 per fifth: −0.33R / 2.1% ≥ 5R under the registered arm, −0.28R / 1.7% under the best new combo;
  the middle fifths read −0.06 to −0.10R / 3.2–4.6%). The 10-18 evening finding is reproduced, not reversed, by the
  exit. C1 cannot be sliced this way: its tightening term puts every C1 trade in the two tightest fifths.
- **Action: none from this data.** The registered primary stays; the his-exit grid is a reported alternative for the
  forward read. Whether a +2R partial, a 20-day trail or a wider stop is ever used is his, under CHANGE_PROCESS.

## 1. Method and population

**Population:** every DISCOVERY first break (watch night D 2022-03-28 .. 2024-12-31, spec key `(ticker, pole_date, K)`,
`retrigger = 0`) on the trendline level `tl` (from the pinned `candidates.tsv`: 12,285 candidate rows) and on the two
center-of-mass levels `com` / `comb` (from `candidates_com_comb.tsv`: 14,562 / 8,984), filled at the headline entry ORH5
under the registered stop and width rule (`tl` 8,989 fills; `com` + `comb` 17,447) — exactly the rows the pinned
discovery reports read; the registered row of every table reproduces the pinned report's `orh5 / p33_s3_t10` numbers
to the last digit (12 of 12 cells × levels checked: n, mean R, interval, tail shares, ex-top-5, ADR P&L). MATURE walks
only (a terminal exit, or the 120-session horizon with its next open behind it). n on every number.

**What was walked (every decision is a call into `agents/market_intelligence/consolidation_breakout.py`):**

| piece | reading | code |
|---|---|---|
| partial trigger | `r2` = 1/3 at fill + 2 × (fill − stop): a session whose high reaches it sells AT it, one that OPENS above it sells at the open; on the breakout day the MINUTES after the fill are walked (`day0_walk_target`); `d3` / `d5` = the close of session 3 / 5 (the registered timing); `c3` / `c5` = whichever comes first | `HIS_EXIT_ARMS`, `walk_exit`, `day0_walk_target` |
| both touched in one bar | daily bars: the STOP books (pessimistic — the bar's order is unknown), unless the bar OPENED above the target (the open precedes the low: the partial at the open, the rest at the old stop); day-0 minutes: the same rule per minute | `walk_exit` step 0 / 1 |
| after the partial | the stop moves to breakeven, resting from the NEXT bar (session; minute on day 0); the trail arms only after the partial (the registered sequence); a trail signal = the first close under the average, filled at the next open | `walk_exit` |
| trail average | `t10` / `t20` fixed; `tspd` = his "faster stocks": the 10-day when ADR20 at D is above 0.0479 (the top tercile of the discovery C0 ADR distribution, the com/comb report's own cut; the four-level report's is 0.0475 — the band between them holds 65 of 8,989 `tl` fills, 2 of 79 in C1), else the 20-day; `td1` / `td2` = his "how far from the 10/20": at the partial, the 10-day when the close is more than 1 / 2 ADR20 above its own 10-day, else the 20-day | `TRAIL_SPEED_ADR_CUT`, `_distance_trail_n` |
| stop variants | `lod` = the low of the day at the fill (registered); `lod_cap05` = max(lod, fill − ½ ADR) — the brief's "floored at 0.5 ADR below the fill" read as a price floor, the width capped; `lod_floor05` = min(lod, fill − ½ ADR) — the same words read as a width floor; `level_m05` = the breakout level (the pivot K(D), not the opening-range level) − ½ ADR; `base_low` = the base's lowest low. ½ ADR = 0.5 × ADR20 × the fill. Each is skipped as `too_wide` beyond one ADR20 (the registered width rule) — a variant can only REMOVE a trade, never add one. R = fill − that stop | `stop_variants` |
| ranking | combos are ordered on **mean P&L in ADR units** (R's unit changes with the stop) and ONLY among combos that kept ≥ 95% of the registered row's trades; a stop that abstains on most trades is compared against the registered arm on exactly the trades it kept (`matched`), never ranked. Written down before any table was read | `EXITS_RANK`, `EXITS_FULL_POP_MIN` |
| intervals | month-block bootstrap of the mean R (calendar month of E, 2,000 draws, seed 702) | `block_bootstrap_ci` |

Files: `scripts/probes/_cb_backtest/runner.py exits --levels tl` → `DATA/out/trades_discovery_exits_tl.tsv.gz` (933,995 rows);
`exits --keys com,comb` → `trades_discovery_exits_com_comb.tsv.gz` (1,714,060 rows); `exits-report` → `exits_report_tl.{tsv,txt}`
and `exits_report_com_comb.{tsv,txt}` (`DATA/out/` full; `scripts/probes/_cb_backtest/out/` the repo copies, every number
below). Nothing pinned was rewritten (§5).

## 2. Results (2022–24, ORH5, spec key, mature walks; "ADR" = mean P&L in ADR20 × price units, size-free)

### 2.1 Headline — the registered row and the best three same-population combos, ranked on C0

| level / cell | stop | arm | n | ADR | mean R | 95% interval | ≥ 5R | ≥ 10R | ex-top-5 | win |
|---|---|---|---|---|---|---|---|---|---|---|
| tl / C0 | lod | p33_s3_t10 (registered) | 8,985 | −0.087 | −0.189 | [−0.31, −0.06] | 3.6% | 1.0% | −0.224 | 23.5% |
| tl / C0 | lod_cap05 | c3_p33_t20 | 8,984 | −0.070 | −0.176 | [−0.29, −0.05] | 2.7% | 1.1% | −0.203 | 29.3% |
| tl / C0 | lod_cap05 | c5_p33_t20 | 8,984 | −0.070 | −0.176 | [−0.29, −0.06] | 2.7% | 1.1% | −0.203 | 29.0% |
| tl / C0 | lod_cap05 | c5_p33_tspd | 8,985 | −0.070 | −0.175 | [−0.29, −0.06] | 2.9% | 1.0% | −0.205 | 29.0% |
| tl / C1 | lod | p33_s3_t10 (registered) | 79 | +0.027 | −0.051 | [−0.44, +0.49] | 3.8% | 1.3% | −0.517 | 27.8% |
| tl / C1 | lod_cap05 | c3_p33_t20 | 79 | +0.142 | +0.324 | [−0.26, +1.19] | 5.1% | 2.5% | −0.371 | 38.0% |
| tl / C1 | lod_cap05 | c5_p33_t20 | 79 | +0.142 | +0.327 | [−0.28, +1.15] | 5.1% | 2.5% | −0.367 | 38.0% |
| tl / C1 | lod_cap05 | c5_p33_tspd | 79 | +0.063 | +0.108 | [−0.27, +0.57] | 3.8% | 1.3% | −0.347 | 38.0% |
| com / C0 | lod | p33_s3_t10 (registered) | 10,739 | −0.093 | −0.239 | [−0.34, −0.13] | 3.5% | 1.0% | −0.260 | 22.1% |
| com / C0 | lod_cap05 | c5_p33_t20 | 10,738 | −0.066 | −0.186 | [−0.29, −0.07] | 2.9% | 1.1% | −0.213 | 28.8% |
| com / C0 | lod_cap05 | r2_p33_t20 | 10,737 | −0.066 | −0.186 | [−0.30, −0.07] | 2.9% | 1.1% | −0.213 | 28.7% |
| com / C0 | lod_cap05 | c3_p33_t20 | 10,738 | −0.067 | −0.190 | [−0.30, −0.08] | 2.8% | 1.1% | −0.217 | 29.2% |
| com / C1 | lod | p33_s3_t10 (registered) | 91 | −0.030 | −0.163 | [−0.58, +0.31] | 4.4% | 1.1% | −0.575 | 23.1% |
| com / C1 | lod_cap05 | c5_p33_t20 | 91 | −0.092 | −0.282 | [−0.58, +0.07] | 2.2% | 1.1% | −0.631 | 28.6% |
| com / C1 | lod_cap05 | r2_p33_t20 | 91 | −0.100 | −0.299 | [−0.60, +0.09] | 2.2% | 1.1% | −0.649 | 27.5% |
| com / C1 | lod_cap05 | c3_p33_t20 | 91 | −0.089 | −0.278 | [−0.57, +0.10] | 2.2% | 1.1% | −0.628 | 29.7% |
| comb / C0 | lod | p33_s3_t10 (registered) | 6,697 | −0.064 | −0.144 | [−0.28, −0.00] | 3.6% | 1.0% | −0.172 | 25.4% |
| comb / C0 | lod | c3_p33_t20 | 6,695 | −0.053 | −0.131 | [−0.26, −0.00] | 3.0% | 1.0% | −0.162 | 31.7% |
| comb / C0 | lod_cap05 | c5_p33_t20 | 6,695 | −0.053 | −0.143 | [−0.27, +0.01] | 3.2% | 1.2% | −0.179 | 29.4% |
| comb / C0 | lod | c3_p33_tspd | 6,696 | −0.053 | −0.125 | [−0.24, −0.01] | 3.1% | 1.0% | −0.155 | 31.7% |
| comb / C1 | lod | p33_s3_t10 (registered) | 64 | −0.206 | −0.488 | [−0.75, −0.18] | 0.0% | 0.0% | −0.768 | 18.8% |
| comb / C1 | lod | c3_p33_t20 | 64 | −0.192 | −0.361 | [−0.61, −0.06] | 1.6% | 0.0% | −0.594 | 29.7% |
| comb / C1 | lod_cap05 | c5_p33_t20 | 64 | −0.192 | −0.443 | [−0.68, −0.17] | 1.6% | 0.0% | −0.680 | 26.6% |
| comb / C1 | lod | c3_p33_tspd | 64 | −0.192 | −0.370 | [−0.62, −0.10] | 0.0% | 0.0% | −0.591 | 29.7% |

The C1 rows of the chosen combos are a SELECTED read (the combos were picked on C0), not an independent test.
C3 (C1 without the market filter) and C5 (RS ≥ 95) are in the TSV / txt with the same layout: C3 `tl` n = 144, C5 `tl`
n = 143; C3 `com` / `comb` 166 / 131; C5 `com` / `comb` 164 / 121.

### 2.2 The trigger × trail grid on the registered stop (ADR / mean R / share ≥ 5R)

| tl, C0 (n = 8,985) | t10 | t20 | tspd | td1 | td2 |
|---|---|---|---|---|---|
| r2 (+2R) | −0.087 / −0.183 / 2.7% | −0.086 / −0.185 / 2.6% | −0.085 / −0.184 / 2.8% | −0.087 / −0.179 / 2.7% | −0.091 / −0.190 / 2.6% |
| d3 (day 3; t10 = registered) | −0.087 / −0.189 / 3.6% | −0.083 / −0.186 / 3.4% | −0.084 / −0.184 / 3.6% | −0.087 / −0.183 / 3.6% | −0.087 / −0.179 / 3.5% |
| d5 (day 5) | −0.093 / −0.199 / 4.2% | −0.090 / −0.196 / 3.9% | −0.090 / −0.196 / 4.2% | −0.096 / −0.202 / 4.2% | −0.092 / −0.186 / 4.1% |
| c3 (+2R or day 3) | −0.080 / −0.176 / 2.6% | −0.075 / −0.170 / 2.6% | −0.075 / −0.172 / 2.7% | −0.080 / −0.172 / 2.5% | −0.080 / −0.176 / 2.5% |
| c5 (+2R or day 5) | −0.082 / −0.177 / 2.7% | −0.079 / −0.176 / 2.6% | −0.079 / −0.176 / 2.8% | −0.082 / −0.173 / 2.6% | −0.084 / −0.181 / 2.6% |

| tl, C1 (n = 79) | t10 | t20 | tspd | td1 | td2 |
|---|---|---|---|---|---|
| r2 | +0.102 / +0.229 / 5.1% | +0.156 / +0.338 / 3.8% | +0.086 / +0.153 / 3.8% | +0.089 / +0.172 / 5.1% | +0.068 / +0.112 / 3.8% |
| d3 | +0.027 / −0.051 / 3.8% | +0.082 / +0.064 / 3.8% | +0.011 / −0.121 / 2.5% | +0.088 / +0.105 / 3.8% | +0.085 / +0.069 / 3.8% |
| d5 | +0.062 / +0.041 / 3.8% | +0.114 / +0.147 / 5.1% | +0.043 / −0.038 / 3.8% | +0.066 / +0.006 / 5.1% | +0.104 / +0.135 / 5.1% |
| c3 | +0.107 / +0.202 / 5.1% | +0.162 / +0.317 / 3.8% | +0.092 / +0.132 / 3.8% | +0.095 / +0.151 / 5.1% | +0.074 / +0.091 / 3.8% |
| c5 | +0.106 / +0.213 / 5.1% | +0.158 / +0.319 / 3.8% | +0.088 / +0.134 / 3.8% | +0.091 / +0.153 / 5.1% | +0.070 / +0.093 / 3.8% |

| com, C0 (n = 10,739) | t10 | t20 | tspd | td1 | td2 |
|---|---|---|---|---|---|
| r2 | −0.077 / −0.190 / 2.8% | −0.074 / −0.186 / 2.9% | −0.077 / −0.193 / 3.0% | −0.080 / −0.199 / 2.8% | −0.082 / −0.200 / 2.7% |
| d3 | −0.093 / −0.239 / 3.5% | −0.087 / −0.232 / 3.4% | −0.091 / −0.239 / 3.6% | −0.097 / −0.250 / 3.4% | −0.096 / −0.249 / 3.5% |
| d5 | −0.096 / −0.242 / 4.0% | −0.089 / −0.231 / 4.0% | −0.095 / −0.243 / 4.1% | −0.097 / −0.251 / 4.0% | −0.091 / −0.230 / 4.0% |
| c3 | −0.079 / −0.194 / 2.5% | −0.072 / −0.186 / 2.7% | −0.077 / −0.194 / 2.7% | −0.082 / −0.204 / 2.6% | −0.082 / −0.201 / 2.5% |
| c5 | −0.077 / −0.189 / 2.7% | −0.072 / −0.184 / 2.8% | −0.076 / −0.192 / 2.9% | −0.079 / −0.198 / 2.7% | −0.081 / −0.199 / 2.6% |

| comb, C0 (n = 6,697) | t10 | t20 | tspd | td1 | td2 |
|---|---|---|---|---|---|
| r2 | −0.059 / −0.129 / 3.1% | −0.056 / −0.135 / 3.2% | −0.056 / −0.129 / 3.4% | −0.062 / −0.134 / 3.0% | −0.065 / −0.147 / 3.0% |
| d3 | −0.064 / −0.144 / 3.6% | −0.061 / −0.151 / 3.7% | −0.060 / −0.145 / 3.8% | −0.070 / −0.157 / 3.6% | −0.070 / −0.161 / 3.7% |
| d5 | −0.073 / −0.155 / 4.2% | −0.070 / −0.162 / 4.2% | −0.070 / −0.156 / 4.3% | −0.073 / −0.161 / 4.2% | −0.074 / −0.163 / 4.2% |
| c3 | −0.059 / −0.128 / 2.8% | −0.053 / −0.131 / 3.0% | −0.053 / −0.125 / 3.1% | −0.062 / −0.134 / 2.8% | −0.063 / −0.143 / 2.9% |
| c5 | −0.060 / −0.129 / 2.9% | −0.055 / −0.134 / 3.1% | −0.055 / −0.128 / 3.2% | −0.061 / −0.133 / 3.0% | −0.065 / −0.146 / 2.9% |

The C1 grids of `com` (n = 91: every cell −0.009 to −0.096 ADR; the registered −0.030) and `comb` (n = 64: −0.179 to
−0.235 ADR; the registered −0.206) are in the txt. Reading the grids: the row (the trigger) moves the number more than
the column (the trail); every +2R / combo row has a lower tail share than the day rows on every level; the two switches
sit between their fixed arms because they resolve to the 20-day on most trades (`tspd`: 3,142 of 8,989 `tl` fills are
above the ADR cut and take the 10-day).

### 2.3 The stop variants, under the registered timing and under the best combo (C0; n / ADR / mean R / interval / ≥ 5R / win / skipped)

| level | arm | lod | lod_cap05 | lod_floor05 | level_m05 | base_low |
|---|---|---|---|---|---|---|
| tl | d3_p33_t10 (= registered) | 8,985 / −0.087 / −0.189 / [−0.31, −0.05] / 3.6% / 23.5% / 0 | 8,985 / −0.083 / −0.201 / [−0.32, −0.06] / 4.1% / 21.0% / 0 | 8,984 / −0.093 / −0.164 / [−0.27, −0.04] / 3.1% / 27.9% / 0 | 7,837 / −0.100 / −0.159 / [−0.26, −0.04] / 2.8% / 29.6% / 1,149 | 755 / −0.014 / −0.050 / [−0.20, +0.13] / 2.6% / 35.2% / 8,231 |
| tl | c3_p33_t20 | 8,984 / −0.075 / −0.170 / [−0.29, −0.05] / 2.6% / 30.5% / 0 | 8,984 / −0.070 / −0.176 / [−0.29, −0.05] / 2.7% / 29.3% / 0 | 8,983 / −0.082 / −0.149 / [−0.26, −0.03] / 2.6% / 31.9% / 0 | 7,836 / −0.084 / −0.132 / [−0.24, −0.02] / 2.5% / 32.9% / 1,149 | 755 / −0.011 / −0.046 / [−0.21, +0.14] / 1.6% / 37.6% / 8,231 |
| com | d3_p33_t10 | 10,739 / −0.093 / −0.239 / [−0.34, −0.12] / 3.5% / 22.1% / 0 | 10,739 / −0.091 / −0.251 / [−0.36, −0.13] / 3.9% / 19.7% / 0 | 10,738 / −0.102 / −0.187 / [−0.29, −0.07] / 3.1% / 27.2% / 0 | 6,508 / −0.091 / −0.137 / [−0.25, −0.00] / 2.9% / 30.6% / 4,236 | 44 / −0.169 / −0.183 / [−0.44, +0.07] / 0.0% / 36.4% / 10,702 |
| com | c3_p33_t20 | 10,738 / −0.072 / −0.186 / [−0.29, −0.08] / 2.7% / 30.4% / 0 | 10,738 / −0.067 / −0.190 / [−0.30, −0.08] / 2.8% / 29.2% / 0 | 10,736 / −0.088 / −0.161 / [−0.26, −0.05] / 2.7% / 31.7% / 0 | 6,506 / −0.081 / −0.117 / [−0.25, +0.02] / 2.7% / 33.7% / 4,236 | 44 / −0.081 / −0.094 / [−0.41, +0.30] / 0.0% / 36.4% / 10,702 |
| comb | d3_p33_t10 | 6,697 / −0.064 / −0.144 / [−0.28, −0.01] / 3.6% / 25.4% / 0 | 6,697 / −0.063 / −0.159 / [−0.31, −0.01] / 4.2% / 22.1% / 0 | 6,696 / −0.075 / −0.134 / [−0.26, −0.01] / 3.3% / 29.0% / 0 | 6,136 / −0.084 / −0.139 / [−0.28, −0.00] / 3.1% / 29.5% / 563 | 40 / −0.161 / −0.180 / [−0.44, +0.10] / 0.0% / 37.5% / 6,661 |
| comb | c3_p33_t20 | 6,695 / −0.053 / −0.131 / [−0.26, −0.00] / 3.0% / 31.7% / 0 | 6,695 / −0.054 / −0.144 / [−0.28, −0.01] / 3.1% / 29.8% / 0 | 6,693 / −0.063 / −0.114 / [−0.24, +0.02] / 3.1% / 33.0% / 0 | 6,133 / −0.074 / −0.122 / [−0.26, +0.02] / 2.9% / 33.3% / 563 | 40 / −0.066 / −0.085 / [−0.43, +0.35] / 0.0% / 37.5% / 6,661 |

The registered arm on the trades each subpopulation stop kept ("matched"): `tl` level_m05 −0.085 ADR (n = 7,838) vs
−0.084 under the variant's best arm; `tl` base_low −0.047 (n = 755) vs −0.011; `com` level_m05 −0.074 (6,508) vs −0.081;
`com` base_low −0.121 (44) vs −0.052; `comb` level_m05 −0.064 (6,136) vs −0.074; `comb` base_low −0.118 (40) vs −0.033.
Capping the stop (`lod_cap05`) binds on few trades (the registered stop is already under half an ADR on most fills, the
§2.4 band table: 54% of `tl` fills sit under 0.5 ADR), which is why it reads as the registered row to ±0.005 ADR.

### 2.4 How often the +2R fires, and when (`tl`, lod stop, mature walks)

| cell | arm | n | no partial at all | +2R on day 0 (minutes) | +2R on a later session | day-3 close partial | ended on day 0 |
|---|---|---|---|---|---|---|---|
| C0 | r2_p33_t20 | 8,982 | 6,318 (70.3%) | 857 (9.5%) | 1,807 (20.1%) | — | 3,341 |
| C0 | c3_p33_t20 | 8,984 | 5,860 (65.2%) | 857 (9.5%) | 1,424 (15.9%) | 843 (9.4%) | 3,341 |
| C0 | d3_p33_t10 (registered) | 8,985 | 6,468 (72.0%) | — | — | 2,517 (28.0%) | 3,250 |
| C1 | r2_p33_t20 | 79 | 47 (59.5%) | 12 (15.2%) | 20 (25.3%) | — | 24 |
| C1 | c3_p33_t20 | 79 | 43 (54.4%) | 12 (15.2%) | 17 (21.5%) | 7 (8.9%) | 24 |
| C1 | d3_p33_t10 (registered) | 79 | 56 (70.9%) | — | — | 23 (29.1%) | 22 |

Seven in ten trades never reach +2R (they stop out first, 3,341 of them on the breakout day itself); one in ten reaches
it within the breakout day. "Ended on day 0" is higher for the +2R arms because a day-0 +2R partial followed by the
breakeven stop the same day is a day-0 exit with a profit (91 of the 3,341). `com` / `comb` read the same shape (70% /
69% never reach +2R).

### 2.5 Tightness — the operator's A+ question (fifths cut per level on its C0 filled population; n / mean R / ≥ 5R / ADR)

| tl, last-5-day range ÷ ADR20 (cuts 0.756 / 0.860 / 0.951 / 1.065) | 1 (tightest) | 2 | 3 | 4 | 5 (widest) |
|---|---|---|---|---|---|
| C0, registered | 1,798 / −0.33 / 2.1% / −0.14 | 1,797 / −0.10 / 3.6% / −0.04 | 1,797 / −0.06 / 4.6% / −0.03 | 1,797 / −0.21 / 3.8% / −0.12 | 1,796 / −0.24 / 3.9% / −0.11 |
| C0, lod_cap05 c3_p33_t20 | 1,798 / −0.28 / 1.7% / −0.10 | 1,796 / −0.20 / 2.6% / −0.06 | 1,797 / −0.07 / 3.2% / −0.03 | 1,797 / −0.18 / 2.8% / −0.09 | 1,796 / −0.15 / 3.2% / −0.06 |
| C1, registered | 54 / +0.02 / 3.7% / +0.12 | 21 / −0.05 / 4.8% / −0.13 | 3 / −1.01 / 0% / −0.41 | 1 / −1.00 / 0% / −0.35 | 0 |
| C1, lod_cap05 c3_p33_t20 | 54 / +0.52 / 7.4% / +0.25 | 21 / −0.08 / 0% / −0.08 | 3 / −0.45 / 0% / −0.27 | 1 / +0.67 / 0% / +0.23 | 0 |

| tl, tightening ratio last 5 ÷ first 5 (cuts 0.696 / 0.836 / 0.977 / 1.169) | 1 (tightest) | 2 | 3 | 4 | 5 (widest) |
|---|---|---|---|---|---|
| C0, registered | 1,798 / −0.30 / 2.7% / −0.12 | 1,798 / −0.11 / 4.1% / −0.05 | 1,797 / −0.13 / 4.2% / −0.05 | 1,796 / −0.21 / 3.6% / −0.10 | 1,796 / −0.19 / 3.5% / −0.11 |
| C0, lod_cap05 c3_p33_t20 | 1,798 / −0.21 / 2.0% / −0.08 | 1,798 / −0.26 / 2.2% / −0.10 | 1,797 / −0.15 / 3.3% / −0.06 | 1,796 / −0.06 / 3.2% / −0.03 | 1,795 / −0.21 / 2.8% / −0.09 |
| C1, registered | 60 / +0.08 / 5.0% / +0.13 | 19 / −0.46 / 0% / −0.29 | 0 | 0 | 0 |
| C1, lod_cap05 c3_p33_t20 | 60 / +0.52 / 6.7% / +0.24 | 19 / −0.29 / 0% / −0.16 | 0 | 0 | 0 |

`com` and `comb` (in the txt) read the same way: the tightest fifth is the worst or joint-worst on both measures under
both exits (e.g. `comb` C0 range ÷ ADR: −0.33R / 2.2% in the tightest fifth vs −0.02R / 4.7% in the middle). The C1
rows are the two tightest fifths by construction (the C1 tightening term is ≤ 0.75, under the second cut); within C1,
fifth 1 beats fifth 2 on every arm (54 vs 21 trades; 60 vs 19) — too thin to call, and the "tightest = worst" reading
of the big cell is the one with n behind it.

## 3. What this does not answer

- **Whether his exit beats the article's — the differences are inside the noise.** The best same-population combo is
  0.017 ADR better per trade on 8,985 trades with a ±0.12R bootstrap half-width; the 125-combo grid was read in full,
  so the best cell is also the luckiest of 125. The C1 numbers for the chosen combos are a selected read.
- **One era, one read.** Discovery 2022–24 (a bear year and a recovery), no holdout, no forward trades. The pinned
  holdout read keeps its registered exit; a his-exit read on 2025–26 would need its own registration first.
- **The entry is fixed** (ORH5, the registered fill); the stop variants can only remove trades (`too_wide`), never add
  one — the cap-not-skip and ATR14 sensitivities of §2.4 of the registration were not re-run under the new arms.
- **The reading of the brief's second stop variant is ambiguous**, so both were run (`lod_cap05` = a price floor, the
  width capped; `lod_floor05` = a width floor); neither moves the picture.
- **Day 0 is exact, later sessions are not.** The +2R touch is read on the minutes only on the breakout day; from E+1
  a daily bar that touches both the stop and the target books the stop (pessimistic), and a bar that touches the
  target and then the breakeven stop the same day is read as surviving to the next session (the registered convention:
  breakeven rests from the next bar). The true +2R arm sits between those two readings.
- **"Faster" and "how far from the 10/20"** are two computable readings of one sentence (the ADR tercile cut; the
  close more than 1 or 2 ADR above the 10-day at the partial); he may mean something else, and both resolve to the
  20-day on most trades, so the switches barely separate from `t20`.
- **The tightness measures are ours** (last-5 range in ADR units; last 5 ÷ first 5), cut on each level's own C0
  population — not necessarily what he calls "tight"; the 10-18 evening slice used the same two measures on the
  registered arm and is reproduced here, not re-derived from its cut points.
- **No sizing, no capacity, no slot competition, no chain-key read** (a subset of these trades), no 60-session horizon.
- **The base-low stop was read on 755 / 44 / 40 trades** (the bases whose low sits within one ADR of the fill): a
  tight-base subpopulation, not a stop test.

## 4. Freeze consequence and what was NOT touched

The module (`consolidation_breakout.py`: additive — new constants, four default-valued `Arm` fields, guarded branches
in `walk_exit`, `day0_walk_target`, `day0_target_to_outcome`, `walk_his_arms`, `stop_variants`, `HIS_EXIT_ARMS`) and
the runner (`read_candidates(extra_floats=)`, the `exits` / `exits-report` stages, `--levels`, the holdout's refusal
of it) changed by bytes, so the `module` and `runner` pins of the registration's freeze record are stale — the state
already declared by the P4b `com` steps; `holdout` refuses until the main loop re-pins after the `com` minute fetch.
Proof the registered outputs did not move: the four pinned default-key stages (`daily` | `minute` | `step0-entries` |
`report`) re-run into a scratch directory after the change give the same seven content hashes as before it
(`candidates.tsv`, `discovery_report.tsv`, `entries_holdout_composition.tsv`, and the decompressed `watch`,
`trades_discovery`, `entries_discovery`, `close_variant_discovery` tables), and every existing `*_com_comb` file in
`DATA/out/` hashes identically before and after (the new stages write new names only). `cb.ARMS` is still the 15 arms
the shadow iterates: no production table, job or Telegram changes. No PLAN.md edit, no prod query, no ssh, no paid call.

## THE LINE

Registration-grade read, measurement only. No strategy, entry or exit rule, stop, size, safeguard or live trade state
was changed or is proposed as decided; the his-exit arms and the stop variants are reported alternatives beside the
registered primary, and any use of them — on paper or live — is the operator's call under CHANGE_PROCESS.
