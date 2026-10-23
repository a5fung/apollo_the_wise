# #705 — the trail exit, sixteen ways: which cells keep more of the good-setup winners' moves, and what each costs on every real breakout against ordinary stocks (2017–21 and 2022–24; read 2026-10-23)

**MEASUREMENT ONLY. $0, local data, no network. Nothing here changes or proposes to change a strategy, an entry or exit rule, a stop,
a partial, a size, a safeguard or any live trade state — those are the operator's (THE LINE). Every cell of the grid below is reported;
none is picked. The grid was frozen in `scripts/probes/_702_trail_variants_1023/BRIEF.md` on 2026-10-22 and its silent spots filled in
`DEFINITIONS.md` on 2026-10-23 06:40 PDT, both before any walk ran.**

**The sealed 2025–26 table is untouched.** No 2025–26 file was opened; the 2022–24 export is cut at 2024-12-31 at load (asserted); nothing
past the last readable session is read.

His words (2026-10-22): *"On trailing the 10/20, we can test a decisive break vs quick reclaim, close below, etc. as stop"*; *"we need to
filter to less breakouts, trade reasonable amount and have better way to keep winners without taking major losses."* The 10-22 read found
the exit is what loses the winners: the 1-ADR stop with two retries holds 44–48% of the good-setup doublers to half their move but keeps a
median 5–7% of the gain, because the third sold at +2R and the first close under the 20-day end the trades.

## 0. What this grid can and cannot say — read before any number

- **The doublers (P-win) say what a cell HOLDS, never whether it pays.** They were chosen after the fact (a +100% move began with a measurable
  breakout). Whether a cell pays is the P-all vs P-ctl comparison only: every real breakout against ordinary stocks of the same day, volatility
  and prior strength, given the SAME entry, stop, retry and exit.
- **Entry, stop and retry are held fixed at the best-holding cell of the 10-22 read** — entry at the breakout close, stop = entry − 1.0 ADR20,
  up to two re-entries (T2; T0 beside). Only the trail average (10 / 20-day), the trail trigger (X1 close below · X2 decisive · X3 reclaim
  forgiven · X4 intraday) and the partial (P1 ⅓ at +2R · P0 none) vary. The session-3 stall cut, breakeven after the third (P1) or after +2R
  (P0), and the touch-both-books-the-stop rule are unchanged.
- **Daily bars.** A bar touching both the stop and a level books the stop. Under X4 the level is the PRIOR session's average, the one known
  when the low prints; a bar touching both the level and the +2R target books the exit at the level.
- **The retry rows' control is not comparable** (10-22 §V): the control re-enters at its 20-session prior high, a different event from the
  breakouts' base high. Only the no-retry (T0) comparisons against the control are clean; every T2 line below carries that caveat.
- **A gap through the stop is the stop's cost, not the trail's.** The worst trade of every cell is the same gap in both eras; a trail variant
  changes it only by how much of the position was still on (P0 keeps the whole position where P1 had sold a third).

## 0b. The answer, in plain words

- **(1) Which trail cells keep more of the good-setup winners' moves (P-win: the 481 / 258 doublers, entered at the breakout close under the
  1-ADR stop with two retries)?** The **20-day average · reclaim forgiven · no partial** cell holds the most: **256 of 481 (53%) / 140 of 258
  (54%) of the doublers were still in a trade when the close first made half the gain** (the carried `pp` exit: 213 (44%) / 125 (48%)), its
  chain **kept at least half the episode's gain on 92 (19%) / 44 (17%)** (`pp`: 8 (2%) / 9 (3%)), the **median share of the gain kept is
  0.086 / 0.125** (`pp` 0.054 / 0.072) and the **median sessions held per base is 25 / 23** (`pp` 18 / 18). Every cell, T2 (T0 and every
  other measure in §1a):

  | cell (20- or 10-day average · trigger · partial) | still in at half the move, 2017–21 (n = 481) | 2022–24 (n = 258) | chain kept ≥ ½ of the gain | kept ≥ ¼ | median share of the gain kept | median sessions held (chain) |
  |---|---|---|---|---|---|---|
  | **20 · X1 close below · P1 ⅓ at +2R (= `pp`)** | **213 (44%)** | **125 (48%)** | 8 (2%) / 9 (3%) | 121 (25%) / 70 (27%) | 0.054 / 0.072 | 18 / 18 |
  | 20 · X1 close below · P0 no partial | 222 (46%) | 131 (51%) | 67 (14%) / 39 (15%) | 152 (32%) / 89 (34%) | 0.060 / 0.072 | 19 / 19 |
  | 20 · X2 decisive · P1 | 227 (47%) | 129 (50%) | 10 (2%) / 9 (3%) | 142 (30%) / 73 (28%) | 0.059 / 0.073 | 19 / 19 |
  | 20 · X2 decisive · P0 | 241 (50%) | 136 (53%) | 77 (16%) / 41 (16%) | 170 (35%) / 93 (36%) | 0.074 / 0.091 | 22 / 20 |
  | 20 · X3 reclaim forgiven · P1 | 239 (50%) | 134 (52%) | 13 (3%) / 11 (4%) | 148 (31%) / 80 (31%) | 0.067 / 0.092 | 21 / 21 |
  | **20 · X3 reclaim forgiven · P0** | **256 (53%)** | **140 (54%)** | **92 (19%) / 44 (17%)** | **191 (40%) / 97 (38%)** | **0.086 / 0.125** | **25 / 23** |
  | 20 · X4 intraday · P1 | 193 (40%) | 119 (46%) | 8 (2%) / 5 (2%) | 108 (22%) / 63 (24%) | 0.048 / 0.066 | 15 / 15 |
  | 20 · X4 intraday · P0 | 195 (41%) | 125 (48%) | 42 (9%) / 34 (13%) | 130 (27%) / 90 (35%) | 0.039 / 0.066 | 15 / 16 |
  | 10 · X1 close below · P1 | 157 (33%) | 99 (38%) | 3 (1%) / 6 (2%) | 67 (14%) / 53 (21%) | 0.045 / 0.059 | 10 / 10 |
  | 10 · X1 close below · P0 | 154 (32%) | 102 (40%) | 33 (7%) / 25 (10%) | 89 (19%) / 69 (27%) | 0.036 / 0.045 | 10 / 11 |
  | 10 · X2 decisive · P1 | 182 (38%) | 109 (42%) | 5 (1%) / 7 (3%) | 90 (19%) / 59 (23%) | 0.051 / 0.060 | 11 / 12 |
  | 10 · X2 decisive · P0 | 181 (38%) | 112 (43%) | 44 (9%) / 28 (11%) | 112 (23%) / 77 (30%) | 0.039 / 0.057 | 12 / 12 |
  | 10 · X3 reclaim forgiven · P1 | 199 (41%) | 118 (46%) | 9 (2%) / 12 (5%) | 116 (24%) / 67 (26%) | 0.054 / 0.070 | 14 / 14 |
  | 10 · X3 reclaim forgiven · P0 | 203 (42%) | 123 (48%) | 59 (12%) / 43 (17%) | 139 (29%) / 85 (33%) | 0.058 / 0.069 | 14 / 16 |
  | 10 · X4 intraday · P1 | 128 (27%) | 85 (33%) | 2 (0%) / 3 (1%) | 51 (11%) / 44 (17%) | 0.034 / 0.038 | 8 / 9 |
  | 10 · X4 intraday · P0 | 124 (26%) | 85 (33%) | 16 (3%) / 15 (6%) | 66 (14%) / 54 (21%) | 0.025 / 0.033 | 8 / 9 |

  - **The partial, not the trigger, is what moves "kept half".** Every no-partial (P0) cell keeps ≥ ½ of the gain on 3–19% / 6–17% of the
    doublers; every ⅓-at-+2R (P1) cell on 0–3% / 1–5%. As computed: under P1 a third of the position sells at +2R — two ADR20 above the entry,
    a median 13% / 12% of price against a median episode gain of +167% / +138% — and the chain's kept share is then carried by the two-thirds
    that trail. P0 trails the whole position and raises its stop to breakeven once +2R has traded.
  - **The 20-day holds more than the 10-day under every trigger and partial** (the 10-day cells are 26–42% / 33–48% still in against the 20-day's
    40–53% / 46–54%): the first trade is trailed out before half the move on 44–135 / 22–64 doublers under the 10-day, on 21–67 / 10–27 under
    the 20-day (`pp` 30 / 16).
  - **The intraday trigger (X4) holds the fewest on both averages** — a low under the prior session's average fires before a close under it
    would — and **decisive (X2) and reclaim-forgiven (X3) each hold more than the close-below (X1)** on the same average and partial, X3 by the
    most (20-day P1: 239 vs 213 / 134 vs 125).
  - **No cell keeps half the gain on more than 19% of doublers, and the median kept share is under 0.13 in every cell.** The stall cut (117–119 / 52–54
    doublers cut at the session-3 close; it precedes the trail, and only an X4 level on session 3's low can pre-empt it) and the 1-ADR stop before
    half the move (149–221 / 84–116 first trades) are untouched by the trail.
- **(2) What each costs on every real breakout, against ordinary stocks given the same rules (P-all R1: 9,239 / 4,457 complete bases, about
  38 / 39 trades a week without retries; T0 is the clean comparison; every cell in §1b):**
  - **Mean R per base, no retry (T0): no cell clears the matched control in either era.** 2017–21: the entries make +0.02 to +0.08 R per trade (no retry)
    against a control of +0.02 to +0.07; every difference lies between −0.03 and +0.02 and every interval spans zero (`pp` +0.005, −0.035 ..
    +0.050; 20 · X3 · P0 +0.010, −0.050 .. +0.076; the 10-day cells −0.012 to −0.033). 2022–24: every cell loses, −0.09 to −0.15 R per trade,
    and so does the control (−0.06 to −0.14); every difference is −0.00 to −0.04 and spans zero (the nearest to clearing on the losing side is
    20 · X4 · P1, −0.037, −0.079 .. +0.004). The median trade is negative in every cell of both eras.
  - **The realized tail (bases with some trade ≥ 5R, per 100 bases).** The no-partial cells roughly double it on BOTH sides (2017–21: 20 · X3 ·
    P0 3.9 vs 3.3; `pp` 1.9 vs 1.4; 2022–24: 2.8 vs 2.5; `pp` 1.6 vs 1.2) — the whole position is on when a +5R print comes. The entries-minus-
    control difference is +0.1 to +0.8 per 100 bases in every cell and clears zero in BOTH eras in three cells only: `pp` (+0.5, +0.1 .. +0.9 /
    +0.4, +0.1 .. +0.9), 20 · X4 · P1 (+0.5, +0.2 .. +0.8 / +0.6, +0.2 .. +0.9) and 20 · X4 · P0 (+0.8, +0.4 .. +1.3 / +0.6, +0.1 .. +1.3) —
    about half a base per 100, i.e. one extra ≥ 5R base every five to six weeks at 38 bases a week. ≥ 10R bases: the differences are −0.0 to
    +0.3 per 100; in 2017–21 six 20-day cells clear zero (`pp` +0.3, +0.1 .. +0.4), in 2022–24 only the two 20-day X4 cells (+0.1, +0.2) do.
  - **The worst losses (his "without taking major losses").** The **5th-percentile trade is −1.00 to −1.04 R in 2017–21 and −1.09 to −1.15 R in
    2022–24 in every cell** (the control's −1.08 to −1.22): nineteen trades in twenty lose no more than about the stop's own width, under every
    trail. **The worst trade is a one-session gap through the stop and is the same trade under every cell of an era:** OPLN, entered 2019-06-04 at a
    1.8% ADR, opened 62% under the prior close eighteen sessions in — **−21.9 R under every P1 cell (a third had sold at +2R) and −33.9 R under
    every P0 cell (the whole position was on)**; 2022–24 EXPE 2024-02-08 (−18% on earnings) −7.1 R (P1) and APPS 2023-05-17 (−37%) −9.8 R (P0).
    Trades losing more than 5 R: 7 / 6 of 9,239 / 4,457 first trades under P1 (0.8 / 1.4 per 1,000), 11 / 9 under P0 (1.2 / 2.0 per 1,000) — every
    one a one-session open 9–72% under the prior close (the list is in §1c; ZWS 2021-10-05 is the Zurn spin-off distribution, which the
    split-adjusted export does not adjust, so it is not a tradeable loss — it printed 2.7× its prior 20-session median volume; OPLN printed 8.9×
    and AVIR 53×, the mark of a repricing, so both are read as real; the rest are earnings / news gaps). Trades
    losing more than 2 R: 6–8 per 1,000 in 2017–21 and 9–11 per 1,000 in 2022–24, the P0 cells one to two per 1,000 more than the P1 cells.
    The trail cannot touch these; the partial sizes them.
  - **Account view (0.5% of equity risked per trade, additive, no position cap — the size of the swings, not a return).** 2017–21 `pp` +239%
    with a worst drawdown of 153% of starting equity; 20 · X3 · P0 +355% / 360%; 20 · X2 · P0 +312% / 312%; the 10-day cells +85% to +166% /
    117% to 266%. 2022–24 `pp` −252% / 318%; 20 · X3 · P0 −334% / 450%; the 10-day cells −199% to −246% / 241% to 353%. The matched control book
    reads the same order (2017–21 +116% to +258%; 2022–24 −59% to −174%). The no-partial cells carry the larger drawdowns in both eras.
  - **Win rate per trade (descriptive only — the exit cannot earn it):** 46% / 41% under every P1 cell, 22–36% under the P0 cells (no +2R third
    is booked), the control 26–47%. Sessions held per trade: median 3 in every cell without retries (the stall cut and the stop end most first
    trades by session 3).
  - **With retries (T2; ⚠ control not comparable).** 2017–21: the 20-day no-partial cells read +0.10 R per base over the control (X1 +0.100,
    +0.016 .. +0.196; X2 +0.100, +0.020 .. +0.185; X3 +0.099, +0.018 .. +0.184; `pp` +0.071, +0.016 .. +0.136) and the 10-day cells +0.03 to
    +0.05; 2022–24 every T2 difference is negative (−0.01 to −0.04) and spans zero. Trades per week 53–69 / 55–69 with two retries.
  - **The expansion-day subset R2 (6.5 / 7.4 trades a week):** every per-base difference spans zero in both eras under every cell (T0: 2017–21
    −0.12 to +0.00; 2022–24 −0.06 to −0.01); its worst trade −9.7 / −7.1 R.
- **So:** within the grid, dropping the +2R third and forgiving a two-session reclaim on the 20-day average lifts the good-setup doublers held
  to half their move from 44% / 48% to 53% / 54% and the share whose chain keeps half the gain from 2% / 3% to 19% / 17% — with the same gap
  through the stop costing −34 R instead of −22 R, book drawdowns about twice `pp`'s, and no cell reading better than ordinary stocks per base
  on every real breakout in either era without retries (the clean comparison; the 2017–21 retry rows that do clear zero, +0.07 to +0.10 R per
  base, carry the control-retry caveat and do not repeat in 2022–24). The 10-day average and the intraday trigger hold fewer doublers than `pp` in every pairing. A trail
  cell moves what a good setup HOLDS; whether the population of breakouts pays did not move with any cell — that is selection, as the 10-22
  read said.
- **Action: none from this data (THE LINE).** The trail, the partial and the average are his; no cell is picked. Two independent verifiers
  (recount + logic) follow, as on 10-22.

## D. Definitions — FIXED BEFORE ANY OUTCOME WAS COMPUTED (the brief of 2026-10-22; the silent spots filled 2026-10-23 06:40 PDT, before any walk)

The four questions of the standard, answered first:
1. **Decision served:** whether a trail variant (average × trigger × partial) keeps more of the good-setup winners' moves than his carried `pp`
   exit, and what each variant costs on every real breakout against ordinary stocks, including the worst losses. What to do about it is his.
2. **What would change it:** if no cell holds more doublers to half the move than `pp`, the exit is not where the kept share is lost. If a cell
   holds more but reads no better than the matched control per base on P-all, the exit moves what a good setup holds and not whether the
   population pays. If a cell beats the control with intervals clear of zero in both eras at T0, the exit is a lever.
3. **Population:** §M. 4. **What would make this wrong:** (a) the pessimistic touch-both rule, which books the stop (or the X4 level) over a +2R
   print in the same bar; (b) the control-retry mismatch on every T2 line; (c) censoring at the cut in 2022–24 (complete bases only in the
   headline); (d) the X4 level is the prior session's average on daily bars — an intraday rule read on daily data.

**Held fixed (from the 10-22 read, §D there):** sessions = SPY's calendar; ADR20 at t − 1; entry at the close of the breakout day t (session 0);
stop S2 = entry − 1.0 × ADR20(t − 1) × entry, never capped; up to two re-entries after a STOP exit (the original or the breakeven stop), at the
first close above the base high within 20 sessions, the stop re-anchored to that day; the session-3 stall cut (+1R not reached by the session-3
close → all sold at that close); a bar touching the stop and a level books the stop; the 120-session horizon (`censored`), bars running out
(`degraded`); R per trade against the original stop; per-base R = the chain's sum.

**The grid (BRIEF.md): 2 averages × 4 triggers × 2 partials = 16 cells per era, the `pp` baseline (20 · X1 · P1) one of them.**
- **Averages.** SMA10 / SMA20 = the mean close over the 10 / 20 sessions ending at the session (the stock's own closes), built from the same
  wide close frame with the same rolling call as the 10-22 frame's SMA20 (asserted equal).
- **Trail live** (every trigger): P1 — once a third has sold OR j ≥ 3 (as `pp`). P0 — once +2R has first been reached OR j ≥ 3. For X4 the level
  must exist before the session: live at session j iff a third sold (P1) / +2R was reached (P0) BEFORE session j, or j ≥ 3.
- **X1 close below** = `pp`: close < SMA while live → everything left sells at the NEXT open.
- **X2 decisive** = (close ≤ SMA × (1 − 0.5 × ADR20)) OR (close < SMA on this and the previous readable session), while live → the next open.
  ADR20 = the trade's own ADR20 at its entry (bday − 1; the object the stop is built from, fixed per trade). The "previous session under" flag
  is tracked on every readable session from the first walked one.
- **X3 reclaim forgiven**: a close < SMA while live starts a watch at session sj. A close ≥ SMA at sj + 1 or sj + 2 cancels it (a later close
  under starts a fresh watch). With no reclaim by the sj + 2 close, everything left sells at the open of sj + 3. The stop, the +2R leg and the
  stall cut keep running inside the window.
- **X4 intraday**: the level = the PRIOR session's average. While live, the effective stop for the session = max(stop in force, level); open ≤
  level → everything left at the open, else low ≤ level → at the level. A bar touching both the level and the +2R target books the exit at the
  level unless it opened at/above the target (the third at the open first, P1). A level exit is a TRAIL exit (no retry); a stop-bound one
  (stop ≥ level) is a STOP exit.
- **P1** = `pp`: ⅓ at +2R (at the open if it gapped there), the session-3 third only in profit with no third yet, breakeven from the session
  after the first third. **P0**: no third anywhere; breakeven from the session after +2R was first reached (a high ≥ fill + 2R, or an open
  at/above it); the stall cut unchanged.
- **Cells:** named `A<avg>_<trigger>_<partial>`; `A20_X1_P1` is `pp`.

**MEASURES (n on every row, tail first).** P-win: still in a trade at s50 (entry ≤ s50 ≤ exit of some chain trade); chain kept ≥ ½ / ≥ ¼ of
the episode's per-share gain (Σ chain P&L per share ÷ (close(p) − close(t))); the median share kept; **median sessions held** = per base Σ
(exit session − entry session) over the chain, a duration; the first trade's exits before s50 by kind; retries used; chain R; ≥ 5R / ≥ 10R
bases; per-trade worst and 5th percentile. P-all (R1, R2) and P-ctl: trades per week; mean R per trade and per base; win rate (R > 0, per
trade); ≥ 5R and ≥ 10R per 100 trades and per 100 bases; **the WORST trade and the 5th-percentile trade** = per-trade realized R over every chain
trade of the cell (T0: first trades; T2: all), on the control the FULL control's per-trade distribution and the seed-702 account-view sample's
worst beside; sessions held per trade; P-all minus P-ctl (cell means) on per-base R, first-trade R, win rate, ≥ 5R / ≥ 10R per 100 bases with
month-block bootstrap intervals (calendar month of t, 2,000 resamples, seed 702); the account view (0.5% of equity per trade, additive,
sequenced by exit; total, worst drawdown, positions open at once) on the entries and on the sampled control. The matched control = the mean
of the entry's (day, ADR20 decile, 63-session-return quintile) cell, the cells and the seed-702 draw reused from the 10-22 read (asserted equal).

**Parity, before any new cell was read:** (a) SMA20 rebuilt from the close frame equals the 10-22 frame's SMA bit for bit; (b) the
parameterised walker at (20, X1, P1) returns every array bit-equal to the 10-22 walker on P-win, R1 and a 300,000-row control subsample; (c)
the whole `pp` cell through the new chain reproduces every number of the 10-22 read's `S2_close` cell to the digit (2,014 numeric leaves,
max |diff| 0, both eras) — the build stops before any new arm otherwise; (d) the published `pp` rows re-walked reproduce 7,334 / 7,335 and
4,905 / 4,905 as on 10-22.

## 1. Results (n on every row; T2 = up to two retries, T0 = none; every other table in the generated section at the end)

### 1a. P-win — do the doublers stay in, and how much do they keep? (covered measurable-breakout doublers; s50 = the session the close first made half the gain)

**2017-21** (n = 481; sessions from the breakout day to half the gain, median 25 (13 .. 39); to the peak 52 (37 .. 75); the published catch on the same bases — early trendline trigger, day-low stop, `pp`: triggered 237, still in at s50 25, kept half 3)

| cell | retries | bases | still in a trade at s50 | chain kept ≥ ½ of the gain | kept ≥ ¼ | kept share: median (quartiles) | sessions held: chain median (quartiles) | first trade: stopped before s50 / cut at session 3 / trailed out before s50 | retries used: mean (1 / 2) | chain R mean / median | bases with a ≥ 5R / ≥ 10R trade | per-trade R: worst, 5th pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20 · X1 · P1 (= `pp`) | T2 | n = 481 | 213 (44%) | 8 (2%) | 121 (25%) | 0.054 (−0.004 .. 0.255) | 18 (3 .. 31) | 218 / 119 / 30 | 0.66 (144 / 86) | +2.89 / +1.22 | 119 / 36 | −3.66, −1.00 |
| 20 · X1 · P0 | T2 | n = 481 | 222 (46%) | 67 (14%) | 152 (32%) | 0.060 (−0.006 .. 0.337) | 19 (3 .. 32) | 191 / 119 / 44 | 0.55 (139 / 63) | +4.04 / +1.03 | 158 / 71 | −3.66, −1.00 |
| 20 · X2 · P1 | T2 | n = 481 | 227 (47%) | 10 (2%) | 142 (30%) | 0.059 (−0.004 .. 0.283) | 19 (3 .. 34) | 220 / 119 / 27 | 0.67 (147 / 87) | +3.22 / +1.26 | 127 / 46 | −3.66, −1.00 |
| 20 · X2 · P0 | T2 | n = 481 | 241 (50%) | 77 (16%) | 170 (35%) | 0.074 (−0.006 .. 0.399) | 22 (3 .. 38) | 192 / 119 / 35 | 0.57 (138 / 68) | +4.62 / +1.37 | 171 / 84 | −3.66, −1.00 |
| 20 · X3 · P1 | T2 | n = 481 | 239 (50%) | 13 (3%) | 148 (31%) | 0.067 (−0.002 .. 0.295) | 21 (3 .. 43) | 221 / 119 / 21 | 0.68 (146 / 90) | +3.55 / +1.22 | 142 / 54 | −3.66, −1.00 |
| 20 · X3 · P0 | T2 | n = 481 | 256 (53%) | 92 (19%) | 191 (40%) | 0.086 (−0.006 .. 0.427) | 25 (3 .. 46) | 194 / 119 / 27 | 0.58 (137 / 72) | +5.26 / +1.47 | 188 / 101 | −3.66, −1.00 |
| 20 · X4 · P1 | T2 | n = 481 | 193 (40%) | 8 (2%) | 108 (22%) | 0.048 (−0.005 .. 0.220) | 15 (3 .. 27) | 211 / 118 / 46 | 0.61 (148 / 72) | +2.48 / +0.89 | 102 / 27 | −3.66, −1.00 |
| 20 · X4 · P0 | T2 | n = 481 | 195 (41%) | 42 (9%) | 130 (27%) | 0.039 (−0.011 .. 0.287) | 15 (3 .. 27) | 180 / 118 / 67 | 0.49 (138 / 50) | +3.33 / +0.70 | 138 / 56 | −3.66, −1.00 |
| 10 · X1 · P1 | T2 | n = 481 | 157 (33%) | 3 (1%) | 67 (14%) | 0.045 (0.000 .. 0.155) | 10 (3 .. 17) | 200 / 119 / 75 | 0.57 (143 / 65) | +1.98 / +0.89 | 75 / 16 | −3.66, −1.00 |
| 10 · X1 · P0 | T2 | n = 481 | 154 (32%) | 33 (7%) | 89 (19%) | 0.036 (−0.009 .. 0.178) | 10 (3 .. 17) | 173 / 119 / 97 | 0.47 (132 / 48) | +2.47 / +0.62 | 105 / 39 | −3.66, −1.00 |
| 10 · X2 · P1 | T2 | n = 481 | 182 (38%) | 5 (1%) | 90 (19%) | 0.051 (0.000 .. 0.190) | 11 (3 .. 22) | 208 / 119 / 56 | 0.60 (144 / 72) | +2.33 / +0.96 | 94 / 25 | −3.66, −1.00 |
| 10 · X2 · P0 | T2 | n = 481 | 181 (38%) | 44 (9%) | 112 (23%) | 0.039 (−0.006 .. 0.234) | 12 (3 .. 22) | 179 / 119 / 78 | 0.50 (133 / 53) | +3.01 / +0.71 | 126 / 49 | −3.66, −1.00 |
| 10 · X3 · P1 | T2 | n = 481 | 199 (41%) | 9 (2%) | 116 (24%) | 0.054 (0.000 .. 0.232) | 14 (3 .. 27) | 214 / 119 / 44 | 0.63 (144 / 79) | +2.73 / +1.11 | 117 / 34 | −3.66, −1.00 |
| 10 · X3 · P0 | T2 | n = 481 | 203 (42%) | 59 (12%) | 139 (29%) | 0.058 (−0.005 .. 0.302) | 14 (3 .. 27) | 186 / 119 / 62 | 0.52 (136 / 58) | +3.74 / +1.02 | 149 / 74 | −3.66, −1.00 |
| 10 · X4 · P1 | T2 | n = 481 | 128 (27%) | 2 (0%) | 51 (11%) | 0.034 (−0.002 .. 0.127) | 8 (3 .. 13) | 183 / 117 / 102 | 0.48 (144 / 43) | +1.55 / +0.68 | 52 / 11 | −3.66, −1.00 |
| 10 · X4 · P0 | T2 | n = 481 | 124 (26%) | 16 (3%) | 66 (14%) | 0.025 (−0.014 .. 0.131) | 8 (3 .. 12) | 149 / 117 / 135 | 0.37 (124 / 28) | +1.87 / +0.48 | 70 / 23 | −3.66, −1.00 |

**2022-24** (n = 258; the published catch: triggered 112, still in at s50 14, kept half 0)

| cell | retries | bases | still in a trade at s50 | chain kept ≥ ½ of the gain | kept ≥ ¼ | kept share: median (quartiles) | sessions held: chain median (quartiles) | first trade: stopped before s50 / cut at session 3 / trailed out before s50 | retries used: mean (1 / 2) | chain R mean / median | bases with a ≥ 5R / ≥ 10R trade | per-trade R: worst, 5th pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
GEN_PWIN_2022_T2

The no-retry (T0) rows of both eras and the trail-exit kinds are in the generated section. Reading it: the same 119 / 54 doublers are cut at
the session-3 close under every cell (the cut precedes the trail), and the 1-ADR stop ends the first trade before half the move on 149–221 /
80–112 — fewest under the P0 cells, where no third has raised the stop to breakeven. What the cells move is the third column from the right:
the first trade trailed out before half the move, 21 (20 · X3 · P1) to 135 (10 · X4 · P0) in 2017–21. On the doublers the retries fire as on
10-22 (97–100% of stop-outs see a close back above the base high within 20 sessions); a level exit under X4 never earns one.

### 1b. P-all vs P-ctl — what each cell costs on every real breakout, against ordinary stocks given the same rules (R1 = every first close above a base high; COMPLETE bases; control = the mean of the entry's (day, ADR decile, 63-session-return quintile) cell; intervals = month-block bootstrap of the per-entry difference, seed 702, 2,000)

**No retry (T0) — the clean comparison.** Columns, tail first: ≥ 5R bases per 100 (entries vs control, the difference with its interval);
mean R per trade and the per-base difference; the entries' worst and 5th-percentile trade (the control's 5th percentile beside — the FULL
control's worst trades, −241 to −385 R, are an unadjusted 2-for-1 split (IGIB / IGSB, August 2018, a 0.13% ADR) and deal-pinned or reassigned
tickers (BHVN October 2022, COHR July 2022): corporate-action artifacts of the export, not tradeable losses; the seed-702 sample's worst, −12
to −25 R, is in the generated tables); win rate per trade (descriptive); the account view.

**2017-21** (R1 complete n = 9239 bases, 244 weeks, 37.8 trades a week in every cell)

| cell | ≥ 5R bases per 100: entries vs control; diff (95%) | ≥ 10R bases per 100; diff | mean R per trade: entries vs control | per-base diff (95%) | median R per trade | worst / 5th-pct trade (control 5th pct) | trades under −2R per 1,000 | win rate per trade | account: total / worst drawdown | control book |
|---|---|---|---|---|---|---|---|---|---|---|
GEN_R1T0_2017

**2022-24** (R1 complete n = 4457 bases, 114 weeks, 39.0 trades a week)

| cell | ≥ 5R bases per 100: entries vs control; diff (95%) | ≥ 10R bases per 100; diff | mean R per trade: entries vs control | per-base diff (95%) | median R per trade | worst / 5th-pct trade (control 5th pct) | trades under −2R per 1,000 | win rate per trade | account: total / worst drawdown | control book |
|---|---|---|---|---|---|---|---|---|---|---|
GEN_R1T0_2022

**With up to two retries (T2; ⚠ the control re-enters at its 20-session prior high, a different event — not comparable, stated for every row)**

| era | cell | trades / week | mean R per base: entries vs control; diff (95%) | ≥ 5R bases per 100; diff | worst / 5th-pct trade | account: total / worst drawdown | control book |
|---|---|---|---|---|---|---|---|
GEN_R1T2

**The expansion-day subset R2** (range ≥ 1 ADR, close in the top 30%, volume ≥ 1.5× the 50-day; 6.5 / 7.4 trades a week without retries;
control re-cut on R2's own deciles and quintiles):

| era | cell | retries | bases | mean R per trade: entries vs control | per-base diff (95%) | ≥ 5R bases per 100 diff | worst / 5th-pct trade |
|---|---|---|---|---|---|---|---|
GEN_R2

### 1c. The mechanics the grid exposes

- **Why the no-partial cells keep more of the gain and lose more on the same gap.** Under P1 a third sells at +2R (two ADR20 ≈ 13% / 15% of
  price at the median) and the stop rises to breakeven; the kept share is then the two-thirds' trail. Under P0 the whole position trails and
  the breakeven stop rests once +2R has traded. The same OPLN gap (−59% in one session) is −21.9 R with a third sold and −33.9 R with none;
  the ≥ 5R bases per 100 roughly double on both sides because a +5R print is reached by the whole position.
- **Why the 10-day average holds fewer.** A close under the 10-day comes earlier in a run than a close under the 20-day: the first trade is
  trailed out before half the move on 56–135 / 36–71 doublers against 21–67 / 12–45. Median sessions held per base 8–14 vs 15–25.
- **Why X4 holds the fewest.** The intraday low trades under the prior session's average before the close does; the level is also tested in
  the stop's own order (pessimistic), so a bar that prints both the level and +2R books the level. Its first trade is trailed out before s50
  on 46–135 / 23–71 doublers.
- **X3's grace costs nothing visible on the worst trade** — the stop keeps running inside the two-session window, so a gap inside it is the
  stop's gap; and the 5th-percentile trade is the stop's width in every cell.
- **Exit mix of the first trade (R1, T0, 2017–21):** stopped 39–64%, cut 24–26%, trailed 10–36% (10 · X4 · P0 the extreme); the P0 cells are
  stopped less (no breakeven stop) and trailed more. The 2022–24 mix is the same shape (generated tables).
- **Every first trade losing more than 5 R (R1, complete, T0), with its worst one-session open against the prior close.** 2017–21, P1 (`pp`):
  OPLN 2019-06-04 −21.9 R (−62% on 8.9× its prior median volume), BMA 2019-08-09 −9.7 (−42%, the Argentine peso), FG 2020-05-21 −9.1 (−12% at a 1.4% ADR), ATHN
  2017-04-25 −7.6 (−17%), RHI 2019-04-23 −6.1 (−9% at a 1.5% ADR), QDEL 2020-11-05 −5.3 (−29%), AVIR 2021-09-30 −5.2 (−72%, a failed trial);
  P0 adds ZWS 2021-09-27 −21.2 (−50% on 2.7× volume: the Zurn spin-off distribution, an export artifact), AVIR −10.1, TVRD 2021-04-05 −8.2 (−43%), MYGN
  2019-10-21 −7.9 (−39%), CGNX 2019-04-12 −6.8 (−15%). 2022–24, P1: EXPE 2024-02-08 −7.1 (−18%), GMED 2023-02-01 −6.6 (−15%), MTZ 2023-08-01
  −6.3 (−13%), APPS 2023-05-17 −5.8 (−37%), DBI 2024-06-03 −5.1 (−21%), TGT 2022-11-15 −5.1 (−16%); P0: APPS −9.8, NERV 2022-10-11 −7.3
  (−67%), THO 2024-02-22 −6.2 (−16%), PANW 2024-01-10 −5.4 (−25%). A 1-ADR stop is 1.4–9% of price here; a 10–70% gap is 5–35 of them.
- **Trades per week** do not change with the trail without retries (37.8 / 39.0 = one trade per base); with retries 56–67 in both eras,
  because a level exit (X4) or a trail exit never earns a retry while a stop exit does, and the P0 cells (no breakeven stop) are stopped
  less often.
