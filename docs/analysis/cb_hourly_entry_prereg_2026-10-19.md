# #702 — the HOURLY-CLOSE entry (buy only after an intraday bar closes above the line): pre-registration (2026-10-19, BEFORE any outcome)

**Why.** The holdout read FAILED the setup as tested and the 2017–21 read was CAN'T TELL; both named one mechanic: about a third
of all trades stop out on the breakout day itself (TSLA 2020: 7 of 12), because ORH5 buys the first 5-minute push over the line
with the day's low as stop — TSLA 05-18 poked, closed below, stopped; his breakout was the 06-01 range expansion, skipped as a
repeat. The operator (2026-10-19): *"on breakouts, should we move to intraday bars to scout for an entry once it's moving into
breakout area? I know he uses hourly bars, but 5min to 1hr intraday can show if the breakout is happening"* and *"Qullamaggie
claims his winrate is around 25%, his strategy depends on outliers and taking small losses."* This is the test the 2017–21
registration named as its consequence: the ENTRY and the STOP, read on 2022–24. Stated: "buy after an hourly bar CLOSES above
the line" is OUR reading of his question, not the article's hourly entry, which is the opening-range high of the first 60-minute
candle (our ORH60 uses the first 60 minutes — already read, C1 discovery −0.23R on 61 under the old exit; re-reported beside under
the primary exit). $0; no paper, no live.

## Method / population

**The confirmation rule (`h60`, primary).**
- Bars: regular hours, clock-anchored (the article: the first 60-minute candle is 09:30–10:00) = minute-index windows [0,29],
  [30,89], [90,149], [150,209], [210,269], [270,329], [330,389]. A bar's close = the close of the LAST minute bar present in its
  window; a window with no minute bar is no bar. "Closes above the line" = close > the row's `pivot`, the level for that break
  day as the runner computes it for THAT row (`tl`; `com` beside); strict, no margin. The entry is the FIRST confirming bar of
  the day; the final bar never fills (its close is the daily close = the registered CLOSE variant, the worst of five already
  measured; no order fills after the close). Earliest fill 10:00.
- Fill = the OPEN of the first minute bar PRESENT after the confirming window's last minute, × (1 + 0.1%) (`ENTRY_SLIPPAGE_PCT`).
  A fill at or under the line is legal (the next open can print under a bar that closed just above) and is taken as is; its
  share is reported. No minute after the window → abstain `no_minute_after_bar`, counted; the day does not confirm. A day with no
  bar that confirms AND can fill → the base's next row is tried. The registered pre-checks (`no_minutes`, `minute_daily_mismatch`
  > 1%, `minute_high_below_pivot`) stand: a data abstain is a row, never a gap; it confirms nothing and consumes nothing.
- **Early-close days (13:00).** The fetcher keeps every print stamped 09:30–15:59, so on these dates minutes 210+ are after-hours
  trades (1–8% of the day's bars, against ~47% on a full day). The 20 dates, read from the files and matching the exchange's list:
  2017-07-03, 2017-11-24, 2018-07-03, 2018-11-23, 2018-12-24, 2019-07-03, 2019-11-29, 2019-12-24, 2020-11-27, 2020-12-24, 2021-11-26,
  2022-11-25, 2023-07-03, 2023-11-24, 2024-07-03, 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24 (2026-07-02 checked:
  a full session). For the bar-close entries ONLY, minutes ≥ 210 are dropped before any minute check; the final window is [150,209]
  (`h30` [180,209]; `h5` [205,209]) and never fills. Rows on these dates: 389 / 400 / 481 (discovery / holdout / 2017–21), C1
  10 / 2 / 8. ⚠ The ORH5 twin is re-walked AS REGISTERED, after-hours prints included (disclosed), so the twin check stays exact.
- Beside, same code: `h30` (13 bars; every hourly boundary is one), `h5` (78 bars), final window never fills. `h60_first`: the rule on
  the FIRST break day only. `h60_m025`: close > line × (1 + 0.25 × ADR20 of the confirming row's D) — ⚠ 0.25 was fixed with TSLA's
  May 2020 highs in view (each earlier poke 0.2–0.8% over, ADR 5%); decides nothing. `h60_line0`: the FIRST-break night's line
  projected forward (anchor high × (1 + `tl_slope_pct` × sessions since the anchor), from `watch.tsv.gz`) — his drawn line does not
  move. ORH60 under the primary exit (the article's own hourly entry).

**Which break days are eligible; one trade per base.**
- A base = the spec key (ticker, pole date, K); its rows = every day the daily high crossed that day's line (first break
  `retrigger = 0`, repeats 1; minutes exist for all). The base's ONE trade = the first break day on which a bar confirms, in E order,
  over all its rows. A confirmed day consumes the base whether it fills or abstains `too_wide` / `stop_at_or_above_fill` (ORH5's
  first break consumes it the same way); a data abstain does not.
- **Eligibility, fixed now (rule (b); ruled in the main loop 2026-10-19 — the runner's and the shadow's own key): EVERY row under the pole is eligible — the runner's own key (`stamp_retrigger`), which never ends a base
  on a gap.** Watch rows exist only for passing nights (0 rows with a line and C0 off), so a stock that fails a gate (close under the
  50-day, base over 45 sessions, deal-pin, universe) is ABSENT that night and its rows resume when it passes: 2,230 of 7,672
  multi-break bases (discovery) / 1,723 of 6,564 (holdout) / 3,131 of 11,414 (2017–21) have a row after such a night (C1: 8 of 63 /
  5 of 29 / 11 of 129; rows after the first gap 7,635 / 6,362 / 13,384). A second gap kind: a high topping the base's highest high
  removes the line for 3 nights (first gap for 801 / 637 / 1,169 bases; C1 11 / 6 / 21). The runner's rule decides because it is the
  key the forward shadow records under, needs no code or pin, and keeps the paired base set identical to ORH5's. Beside, never
  deciding: confirmations after an absent night (STEP 0) and the C1 verdict restricted to confirmations with none since the first
  break. The 8 discovery C1 bases: TEN 2022-07-08, AIMC 2022-10-28, APLD 2023-05-25, M 2023-12-11, ZIM 2024-01-05, CAVA 2024-05-30,
  LUMN 2024-08-07, ULCC 2024-10-28.
- **A repeat day's line is REDRAWN, not his drawn line:** nightly the module redraws it from the base's highest high so no later high
  sits above it, so after a poke it passes near that poke's high (TSLA's nightly line 05-15..05-29 moved between 55.07 and 55.55;
  each repeat row's `pivot_date` = the previous poke). It decides because it is the level the forward shadow computes; `h60_line0`
  is the original-line reading, beside. Hole, counted not fixed (`last_bar_only`): a day whose only confirming bar is the final one
  gets no trade, split by what followed — the close ended the base (a close above the pole high: no row follows); the high topped
  the anchor (no line for 3 nights); the next row's line sat near that day's high and was not cleared; a later row confirmed.
  Also reported: sessions from first break to confirmed break; the share of confirmed entries after a data-abstained day.
- **TSLA (pole 2020-04-30, `tl`)**: rows 05-18, 05-21, 05-22, 05-26, 05-29, 06-01, all C1, no absent night; closes vs line: 05-18 below,
  05-21 +0.2%, 05-22 / 05-26 below, 05-29 +0.8%; 06-01 opened 3% above and its first bar closed above (58.31 vs 55.55; a layout
  check). The primary gives 06-01 UNLESS a bar closing at or before 15:00 on an earlier row closed above that row's line — possible,
  NOT computed here; whichever day it is IS the answer, printed at STEP 0. ORH5 traded 05-18 and was stopped the same day.

**The stop — the second registered question.** Primary `lod` = the lowest minute low from 09:30 through the END of the confirming
window (the minutes BEFORE the fill minute: the fill is that minute's open, so its own low is not yet known); abstain `too_wide` if
(fill − stop) ÷ fill > ADR20; a fill-minute OPEN ≤ the stop → the registered `stop_at_or_above_fill` abstain (consumes, counted;
the trigger is the open, tighter than the module's `stop ≥ fill` by the 0.1% slippage — same name, same consequence). **`cbar_low` is the registered STOP CANDIDATE:** the confirming bar's low (its window's lowest minute low), same abstains.
`base_low_cap1` = max(base low, fill − 1.0 × ADR20 × fill), never abstains, beside. Every stop variant is computed on the PRIMARY's
confirmed day; a side stop that abstains there has no trade (0R), never another row. **R is the deciding unit** for every paired
bar: under the article's fixed-risk sizing (0.25–1% of the account a trade) each trade risks the same money, so R per trade IS the
account result; a later fill that widens the stop costs R, and that cost belongs to the rule. ADR P&L and account % beside.

**Exits.** `c3_p33_t20_cut3` primary (sell 1/3 at +2R or at the close of session 3, whichever first; stop to the fill; trail the 20-day,
filled at the next open; stallers cut at the close of session 3 if no high reached +1R). Session 0 = the FILL day, walked FROM THE
FILL MINUTE INCLUSIVE: `day0_walk`, `day0_walk_target` and `day0_peak_high` take the confirming window's last present minute as
their start, so the fill minute's low is read against the stop first and its high against +2R / +1R in the module's pessimistic
order. Beside: `p33_s3_t10` (the article), `r2_p33_t20`. Horizon 120; mature = terminal exit or the horizon with 121 sessions behind
it. R against the entry stop. **Which row supplies what (pinned):** the DAY's facts come from the CONFIRMING row — `pivot`, `adr20`
(its own D's; TSLA's runs 0.063 on 05-18 to 0.045 on 06-01), `base_low`, the closes before E, the forward window, the day-0 minutes,
`gap_over_1adr` and the QQQ phase (slices labelled "at the confirmation"); the CELL and the PERIOD come from the FIRST-break row.

**Population, cells, periods.**
- Data: `apollo_data/cb702` (Polygon daily 2021-09..2026-10; `out/candidates.tsv` = `tl`, `out/candidates_com_comb.tsv` = `com`;
  `minutes/` = every break day incl. repeats) and `apollo_data/cb702_pre` (Alpaca 2017-03..2021-12; `out/candidates_tl_com.tsv`,
  `minutes/`). The ORH5 twins = the pinned `trades_{discovery,holdout,pre}_p5.tsv.gz`.
- Both split labels are read (`split=None`), rows grouped by spec key, period = the first-break row's label (205 `tl` / 193 `com`
  discovery bases have repeat rows labelled holdout — C1 0 / 1 — and stay discovery: the holdout registration's §1 leak class).
  2017–21 = first-break E in 2017-03..2021-12; "2020–21" = first-break E in 2020 or 2021. The pre file's last day 2022-01-03 holds
  70 rows: 57 repeats of 2021 bases (4 C1: FLR, NPTN, SLAB, SWIM), eligible; 13 first breaks, outside the era.
- A base belongs to the cell its FIRST-break row's flags put it in (C1 = 102 / 43 / 216 bases in discovery / holdout / 2017–21),
  whichever row confirms. Beside: the share of confirmed entries whose own watch night still passed the cell, and the C1 verdict
  restricted to those (his regime caution: a C1 base can confirm weeks after the QQQ 10/20 phase turned off).
- **2022-03-28..2024-12-31 (discovery) DECIDES. 2017–21 beside** (whole era and 2020–21), **2025-01..2026-10 descriptive only** (read
  once under ORH5; a positive there is not a holdout pass). C0 = the baseline under the SAME entry; **C1 decides**; C2–C7 and the
  three report cells reported. `tl` decides, `com` beside.
- **The paired entry comparison:** per base Δ = R(h60) − R(ORH5), no trade on a side = 0R there; excluded and counted: a base with an
  OPEN MARK on either side, and a base whose ORH5 first break was a DATA abstain. Month-block bootstrap on the first break's month,
  2,000 resamples, seed 702; n floor = 30 bases with a trade on at least one side. Split and reported: both filled the SAME day (the
  pure timing effect) vs h60 on a LATER row (the re-try); ORH5's mean R on the bases h60 never confirmed; the share of bases each
  rule traded; the same Δ for `h60_first`. His outlier point: per side the bases at ≥ 5R and ≥ 10R and their overlap — which of
  ORH5's big winners h60 misses, and the reverse. **The paired stop comparison (under `h60`, C1 2022–24):** Δ = R(`cbar_low`) −
  R(`lod`) per base, same exclusions, interval, seed and n floor; the ADR P&L Δ beside.
- Reported per cell × period × entry × stop × exit: n (filled, mature), confirmed-too-wide, never confirmed, data abstains; win rate,
  average win / loss, mean R, the month-block 95% interval, ≥ 5R / ≥ 10R / ≥ 20R per 100, total R, the top-2% share, ADR P&L,
  account % at the article's sizing, the share stopped on the fill day, median sessions held, the fill-minute and
  first-break-to-confirmation distributions, the stop width in ADR of every ≥ 10R trade; slices by year, QQQ phase and gap over
  1 ADR at the confirmation, Apollo regime (holdout only).
- Expected n from CANDIDATE COUNTS only (bases with a `tl` first break; brackets = bases with ≥ 2 distinct break days; "ORH5" = the
  published fill count; the registered ORH60 read 61 mature C1 trades in discovery and filled 21 of the 43 holdout C1 bases):

| period | C0 bases | C1 bases | ORH5 C1 fills | h60 C1 expected | C3 / C4 / C5 / C7 bases | C2 / C6 |
|---|---|---|---|---|---|---|
| 2022–24 (decides) | 12,285 (7,672) | 102 (63) | 79 | 60–90 | 183 / 507 / 198 / 127 | 7 / 20 — CAN'T TELL by n |
| 2017–21 | 17,392 (11,414) | 216 (129) | 180 | 150–200 | 355 / 1,252 / 414 / 305 | 16 / 36 |
| 2020–21 alone | 11,600 (7,672) | 88 (49) | 72 | 55–80 | 128 / 839 / 202 / 115 | 8 / 13 |
| 2025–26 (descriptive) | 10,554 (6,564) | 43 (29) | 31 | 25–40 (n < 30 is live) | 107 / 317 / 99 / 76 | 3 / 6 |

  `com` bases: C1 112 / 245 / 42 (discovery / 2017–21 / holdout). Row counts: `tl` 41,307 / 68,939 / 37,917.
  (2017–21 C0 = 17,392: the 13 first breaks on 2022-01-03 are outside the era; the pre-read's 17,405 rows include them.)

**Data checks the run must pass before any outcome column is opened.**
1. `freeze_check` on every pin below the marker; a mismatch refuses the run. Once only per period: the trades table and its `.partial`
   refuse a second run; the operator removes them by hand. The hindsight tables (the 39 multibaggers, TSLA row by row) are written
   by a separate command to a separate file that refuses to run until the C1 verdict file exists.
2. Minute coverage of EVERY eligible row in `_done.psv`: verified today, 0 missing pairs in all three trees; logged `empty` (→
   `no_minutes`) 53 / 4 / 62 on `tl`. Early-close check: each of the 20 dates shows < 25% of its bars at minute ≥ 210, every other
   date ≥ 25%.
3. Data-abstain share (`no_minutes` + `minute_daily_mismatch` + `minute_high_below_pivot` + `no_minute_after_bar`) ≤ 5% of the rows
   the rule actually READS (first break through the confirming or last eligible row), per period (ORH5: 1.2 / 0.4 / 0.4%).
4. The ORH5 twin: re-walked on the same first-break rows, as registered, equal to the pinned `trades_<period>_p5.tsv.gz` row by row
   (status, maturity, realized R to 1e-9); a difference exits non-zero and writes no report.
5. STEP 0 first: the entry-time table (per cell: confirmed and filled, confirmed too-wide, never confirmed, data abstains,
   `last_bar_only` by kind, confirmations after an absent night, `h60_line0` vs redrawn-line confirmations, the fill-minute and
   first-to-confirmed distributions, the share filled at or under the line, the TSLA day) is written and read before any exit is
   walked; its counts must equal the table above.
6. Independent re-derivation from the trades table alone (pandas, no runner code): C1 and C0 n / mean R / ≥ 5R, the paired entry Δ
   and stop Δ (point and interval, same seed), the ≥ 10R spread (tickers, months, stop widths); VERDICT MATCH first.

## Bars (C1, `tl`, `h60`, `lod`, `c3_p33_t20_cut3`, spec key, mature walks, 2022–24; precedence: n first)

- **PASS — all of:** n ≥ 30; the month-block interval's lower end > 0 (blocks = the FILL month); ADR P&L > 0; beats C0 under the same
  entry on mean R AND the ≥ 5R share; **the ≥ 10R trades come from ≥ 3 distinct tickers AND ≥ 3 distinct calendar months** (fill
  day), counting only trades whose stop is ≥ 0.25 ADR20 wide (a 10R trade on a 0.1-ADR stop is a 1-ADR move, the #327 tight-stop
  class; the count with no width rule is beside). Why 3 and 3: one stock often gives two bases in a run (his stair step), so 2
  tickers cannot separate the setup from the stock, nor 2 months from one burst. At 60–90 trades this asks 3–5 ≥ 10R per 100 —
  three times ORH5's 1.2, the profile he describes. The 2-and-2 reading is beside. This replaces "mean without the top five",
  which fails an outlier book by construction (the 2017–21 addendum).
- **FAIL:** n ≥ 30 AND (the interval's upper end < 0, OR the cell does not beat C0 on mean R). **CAN'T TELL:** n < 30 whatever the
  interval says; otherwise neither — an interval above zero that beats C0 but lacks the 3-ticker / 3-month tail is "CAN'T TELL
  (positive, no tail)" and follows the CAN'T TELL row of the table below.
- **The paired entry bar (C1 decides; C0 = the mechanism at scale):** Δ interval lower end > 0 → **the hourly close beats the
  opening-range entry on the same bases**; upper end < 0 → **it loses to it**; else can't tell. ⚠ A "win" can come from trimming
  small losses while losing ORH5's outliers — the ≥ 10R overlap is reported next to it, never deciding. **The paired stop bar
  (under `h60`):** Δ(`cbar_low` − `lod`) lower end > 0 AND its ADR P&L Δ > 0 → `cbar_low` is the stop `h60` carries forward; else
  `lod` stays. `base_low_cap1` decides nothing.
- Chance of a false pass: three deciding one-sided tests on 2022–24 (the C1 interval, the paired entry Δ, the paired stop Δ), each
  ≈ 2.5% under a true zero if the block bootstrap is calibrated → ≈ 7% that at least one passes by chance; the tail-spread and
  beat-C0 conditions make a C1 chance pass rarer. 2017–21 and 2025–26 are stamped "agrees / contradicts" (the sign of mean R and
  of Δ) beside the verdict; they decide nothing.
- **Expectations, numbers fixed now:** the share stopped on the fill day under `h60` in C0 < 25% (ORH5 ≈ 35%); C1 n in 60–90
  (confirmation skips pokes, re-tries add — no one-way expectation); on same-day pairs the h60 fill sits above ORH5's; the C0
  baseline under ORH5 is −0.17R, win 31%, ≥ 10R 0.9 per 100. A missed expectation is reported first and changes NO rule.
- **WOULD-FAIL-IF (a broken implementation):**
  - fill mechanics: fill ≠ open(first present minute after the confirming window's last present minute) × 1.001, recomputed per trade
    from the minute file; that last minute's close ≤ the row's `pivot`; a fill minute inside its own window; a window end outside the
    variant's set (`h60` 29/89/149/209/269/329, early-close 29/89/149; `h30` every 30th from 29 to 359, early-close to 179; `h5`
    every 5th from 4 to 384, early-close to 204); an `lod` ≠ the lowest low of the minutes ≤ the window end; a trade whose
    fill-minute open ≤ its stop; a day-0 walk that starts after the fill minute.
  - early close: any fill, stop, partial or exit at minute ≥ 210 on a listed date; check 2 failing.
  - row binding: a trade's E ≠ its confirming row's E; its line ≠ that row's `pivot`; its ADR20 ≠ that row's `adr20`; a side stop on
    a day other than the primary's; a cell or period taken from any row but the first break.
  - counts and keys: two trades in one spec key; a trade on a row of a consumed base; a cell's n above its base count; on confirmed
    days `h5` or `h30` confirming fewer days than `h60` (nesting: `h5` ⊇ `h30` ⊇ `h60`); `h60_first` with more trades than `h60`; the
    twin ≠ the pinned table; a paired-set base whose ORH5 side is a data abstain; STEP-0 ≠ the table.
  - golden series and TSLA: synthetic minutes — only minute 29 above the line → fill at 30; only 89 → fill at 90; only 90 (149 below)
    → no confirmation from the 10:00 or the 11:00 bar; only 329 → fill at 330; only 389 → no fill; early-close: only 149 → fill at
    150, only 209 → no fill. TSLA 2020-04-30 (`tl`): exactly ONE confirmed day among its six rows, printed at STEP 0, in {05-18,
    05-21, 05-22, 05-26, 05-29, 06-01} with status in {filled, too_wide, stop_at_or_above_fill}; none at all = broken re-try logic
    (06-01's first bar closed above its line).

**Beside, descriptive, decides nothing — written AFTER the verdict (check 1):** the 39 known 2020–21 multibaggers (the 2017–21
addendum's list; SQ absent from Alpaca): their C0 `tl` bases in 2020–21 under `h60` vs ORH5 (published under ORH5: 352 trades, +1.06R,
+375R, 35% stopped on the breakout day, 6.2% ≥ 5R) — n, mean R, total R, fill-day stop share, ≥ 5R / ≥ 10R counts, trades per ticker;
and TSLA's bases row by row with the day each rule entered. Hindsight: naming winners afterwards looks good.

## Consequence fixed now

"Record" = the forward shadow records `h60` as a sixth entry variant beside ORH5 (entry rows per (name, K); a recorder change, no
order path, no money) and `consolidation_breakout_forward_read` reads it beside ORH5. The shadow is the ONLY confirmation; **never
straight to paper**; live is his sign-off (THE LINE). The next tests proceed in EVERY cell, under the entry named.

| C1 verdict \ C1 paired Δ | win | can't tell | loss |
|---|---|---|---|
| **PASS** | RECORD; next tests under `h60` | RECORD; next tests under `h60`; "not separated from ORH5 on the same bases" is reported | LEAD only (recorded, no claim: ORH5 made more on the same bases); next tests under ORH5 |
| **CAN'T TELL** (incl. positive, no tail) | LEAD (recorded); next tests under `h60` | LEAD only if the C0 paired interval's lower end > 0, else not recorded; next tests under ORH5 | not recorded; next tests under ORH5 |
| **FAIL** | not recorded; "loses less than ORH5" reported; next tests under ORH5 | not recorded; next tests under ORH5 | not recorded; next tests under ORH5 |

- Whatever is recorded carries the stop the stop bar names (`cbar_low` or `lod`), also the next registration's primary stop; when
  the next tests run under ORH5 the stop bar is a reported row (no confirming bar there). The C0 paired result never promotes
  beyond LEAD.
- The next tests, named now: (2) a breakout-day quality rule read at the CONFIRMING BAR — range-so-far and volume-so-far (an entry
  rule may read only what is known at the fill; the recorded `trigger_bar_range_adr` is the WATCH NIGHT's range and `breakout_vol_x`
  the whole day's volume, so neither serves); its thresholds are set in its own registration (the 1 ADR / 1.5× numbers floated
  earlier were formed with TSLA 06-01 in view); (3) the stair-step number (first base of a run vs a later one).

## What the read may NOT do

- Switch the deciding entry (`h30`, `h5`, `h60_m025`, `h60_first`, `h60_line0`, `com`, ORH60), swap a stop outside the stop bar, or
  change a cell, the eligibility rule, a period, the horizon, the n floor, the seed or the draw count — after this registration, for
  any reason. A side row is never a finding. Run a period twice; read the hindsight file before the verdict; edit this document
  above the marker after the freeze commit.

## What this does not answer

- Only the ENTRY and the STOP are new; bases, cells, exit and stall cut were chosen on 2022–24 under ORH5, so discovery is blind to
  nothing but those two: a PASS here is a discovery PASS, and the forward shadow is the confirmation.
- Re-entry after a stopped CONFIRMED trade (CAN'T TELL under ORH5; not re-asked). What he actually watches on the hourly and whether
  his first partial bar is ours; the 1- and 5-minute "holy grail" version is a different setup. The regime question (his caution; the
  holdout regime split and the at-confirmation phase row only); sizing, slots, turnover; survivorship in 2017–21.

<!-- FREEZE -->
## Freeze record

The doc body pin covers every byte above the `<!-- FREEZE -->` marker. The run (`runner.py h60-read`) verifies every pin before it opens
a minute file and refuses on any mismatch; the RESULT is appended below this record. Data pins computed 2026-10-19 (`shasum -a 256`);
the code pins (module, runner incl. the new entry code, `constants.py`, `exit_logic.py`), the two minute-tree pins and the doc body
pin are printed by `h60-read --print-pins` after the code lands and pasted here in the commit that precedes the run.
- cb702/out/candidates.tsv sha256: `b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7`
- cb702/out/candidates_com_comb.tsv sha256: `138149b87eed950d62ca94512b04c408329d18ef9a79779dc51d1a51589fc117`
- cb702/out/watch.tsv.gz sha256: `59e757cacb3250066393d0395e4abe89adff3787c34d1f2f7ad5fd5e2f2a5c0b`
- cb702/out/watch_com_comb.tsv.gz sha256: `bc565c9bff60e9538a65d4a9dd3a65c39b6412273414a637d137043d8285017e`
- cb702/out/trades_discovery_p5.tsv.gz sha256: `8e906dc8d0242fba972e88d28eccb17c57b6b28d35f5f12fa1292208aa9c1bd4`
- cb702/out/trades_holdout_p5.tsv.gz sha256: `557a4152809aae22bb964653097a1684cfcedd8269777c69443227c9e794b673`
- cb702/minutes/_done.psv sha256: `cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178`
- cb702_pre/out/candidates_tl_com.tsv sha256: `4ee9e04ca80f82fc02f1659b078263f9dcd1b197c395733a5f389367277268e6`
- cb702_pre/out/watch_tl_com.tsv.gz sha256: `8f063d6bc613bcecb9827d8a961525fb589f48882873e2dbe82654eb030700e8`
- cb702_pre/out/trades_pre_p5.tsv.gz sha256: `07c10b952316b28daf8f6cfff15437efb23b939af74a27b4bb60c5948712ec86`
- cb702_pre/minutes/_done.psv sha256: `bbb38323a9b5748ed094e45332686804d9804760183d77c7f9ca9c74cdc2dc41`
- module sha256: `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b`
- runner sha256: `1c7f943c58f21b07b60bc86c350b00d31b82a35bbbfecb8cfe39669e1d9a4510`
- code/constants.py sha256: `72dadd72503a842f593621b0868f908ab99e1d77851330c2842be7797aa99400`
- code/exit_logic.py sha256: `dd032c0f5115c2d811561d455ad260e8b77559415bde68ae46f4a17eb92b7976`
- cb702/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
- cb702_pre/daily_closes_all.csv.gz sha256: `b10eea41775e657939c64e314068cb3c606d23d44de8488649fb67a4ac5ed773`
- cb702/minutes (tree) sha256: `f1d98fd9d2352c45e90849e18a163b8ca31d2526eb851e5a76dd11ffd79a9fe5`
- cb702_pre/minutes (tree) sha256: `c019a52c8ed624263bd8b3ef0c36f54c5f77ce3cbee75751c0fd2a3026eeccd8`
- doc body sha256: `97a29aea34babce0e89ab81b76e375a59a30510820a2a1504ed58a5578fe3979`
- freeze commit: the commit that adds this file on `main`; the read runs only after it is on `main`.
