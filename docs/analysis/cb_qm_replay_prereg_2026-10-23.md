# #705 — Qullamaggie's own calls, replayed under his own rules: pre-registration (2026-10-23)

**Status: REGISTERED, REVISED AFTER THE ADVERSARIAL REVIEW (§13), NOT FROZEN, NOT RUN.** Outcome-free: no fill, stop, exit, R, return, or bar after a breakout day E has been read
for any event named here. The module's dry run (`scripts/probes/_705_qm_replay_1023/01_replay_dryrun.txt`) loaded the inputs, asserted
the populations, and read the minute fetch logs only. It opened no minute file and called no entry or exit function. Every era-B row
dated after 2024-12-31 was **dropped at read and asserted**. That covers 5,210,943 export rows, 109,478 + 240 candidate rows (holdout /
after the cut), and 72,951 fetch-log rows. Measurement and registration only. Nothing here changes or proposes to change a strategy, an
entry, a stop, an exit, a size, a safeguard or any live trade state. Those are the operator's (THE LINE). The main loop freezes this
doc and the module, commits, and runs the replay ONCE.

His words this read serves (2026-10-23 evening, verbatim, `docs/methodology/operator_shared_notes.md`):
*"the truth is qullamaggie used these setups to achieve 10x return in a year, in fact his ~10yr record consist of multiple 100%+
years. This works, we need to figure it out"* — *"If we hit 1/66, if those 66 are real, why we miss them is the question"* — *"his
record is audited, the returns are real, this means we can put the trades back together and achieve the same returns when looking
back in those periods, that should be a fact"*.

## 0. In plain words

- **The question:** take the breakouts Qullamaggie himself called on stream, on or before the breakout day (236 in 2017–21). Trade
  them his way, then compound them in one account year by year. Do they make money of the kind his audited record shows? And do they
  make more than the other breakouts of the same days?
- **His way:** buy the 5-minute opening-range high on the breakout day, with the stop at that day's low at the fill. Sell a third
  after day 3, move the stop to breakeven, and sell the rest on the first close under the 10-day average. Every rule is quoted from
  his article (§4).
- **The account, at his sizing (his words, §6):** start 1.0, risk 1% of equity per trade, at most 20% of equity in one position and
  30% in one stock, no margin. Run the same account on 200 random same-day picks as the reference band.
- **What it decides (written now, §8):**
  - his picks beating the same day's other breakouts (a strong curve ABOVE the band, or a per-trade edge on the same days) means the
    gap between our system and his record is **which breakouts are taken (selection)**;
  - a strong curve that the band matches means **the dates / the market carry it, not his picks**;
  - neither means the gap is **how they are traded or the data (execution)**.
- **Action from him: none now.**

## 1. The four questions of the standard

1. **Decision served:** where the next #705 work goes. One branch fixes the FILTER (his calls carry the result, so our pick of
   breakouts is the gap). The other varies ENTRY / STOP / EXIT / SIZING per his words (even his calls do not carry it under these
   rules). What to do with either is his.
2. **What would change it:** the fork in §8, fixed before any outcome.
3. **Population:** §2–§3 and §11.
4. **What would make this wrong:**
   - (a) **109 of the 236 calls rest ONLY on a label said ON E**, with part of E's bar visible (SQM at 11:34). 119 calls carry an
     on-E label; 10 of those also carry one said before E. 127 strictly-before + 109 on-E-only = 236 (all asserted). The on-E calls
     can carry intraday conditioning: he names a stock that is already working that morning. A strong curve is partly that, not
     pre-market selection. The 127 strictly-before calls are the only subset clean of E; both fork arms are printed on them beside the
     verdict (§8).
   - (b) The calls are a stream-confirmed SLICE of his trades: caption = screen = our bars, 854 of 2,472 graded moments attributed.
     He shows what he likes, and he may show winners more often than losers.
   - (c) The nearest-event join is noisy in timing. 104 of the 236 sit on a RETRIGGER of our trendline, not its first break, and his
     real entry day may differ from our E.
   - (d) Our ORH5 / low-of-day / day-3 / 10-day walk is our reading of his article, not his fills.
   - (e) His record also holds EPs and parabolic shorts, which this read cannot reproduce.
   - (f) 2020 holds 156 of the 236 calls, so the curve is mostly one regime.

## 2. POPULATION — his calls (outcome-free counts from the dry run)

**HIS CALLS** = the Track A positive events (`docs/analysis/cb_track_a_filter_prereg_2026-10-23.md` §3): a tl breakout event
(stock, E) whose nearest-event join carries at least one bought / best label said ON OR BEFORE E. Era A n = 236 (fit 170 / hold-out
66), era B n = 9. The module derives the set with the FROZEN fit module's own `label_sets` + `assign_classes` (imported read-only,
pinned `3fca7bf4…`), so it is the registered set by construction, and asserts every count below. The 2021 hold-out was burned for
FITTING only; its outcomes have never been opened.

| year of E | his calls n | first breaks | retriggers | control n (§3) | control first breaks | post-E-only n (beside) |
|---|---|---|---|---|---|---|
| 2017 | 6 | 6 | 0 | 223 | 77 | 1 |
| 2018 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2019 | 8 | 6 | 2 | 446 | 77 | 0 |
| 2020 | 156 | 80 | 76 | 14,438 | 3,370 | 57 |
| 2021 | 66 | 40 | 26 | 8,081 | 2,051 | 29 |
| **era A (decides)** | **236** | **132** | **104** | **23,188** | **5,575** | **87** |
| era B 2022 / 2023 (descriptive) | 1 / 8 (n = 9) | 6 | 3 | 78 / 267 (n = 345) | 106 | 3 |

- His era-A calls fall on 156 dates. 107 dates hold one call, 30 hold two, 12 three, 5 four, 1 five and 1 eight.
- They sit on 188 bases (`base_id`); 48 events are a second or later crossing of a base he had already called.
- The one-event-per-base reading (each base's first called event, n = 188) is beside.
- **Beside, never deciding:**
  - The **87 post-E-only events** (era B 3): every bought / best label said after E. This is the hindsight reading. He showed these
    stocks because they were already worth showing, so they are expected to read BETTER than his calls. The gap measures the
    hindsight bias.
  - **27 of the 87 are also in the control** (Track A round-3 rule: a label said later cannot move a row out of the control).
  - The **127 strictly-before events** (era B 6): the only subset clean of E's bar.
- **Limits stated now:**
  - The calls are a stream-confirmed slice of his trades.
  - His record also holds EPs and parabolic shorts, which are not here.
  - The caption = screen = our-bars restriction (94.0% recall, 1.8% false match, Track A §9) drops what our bars cannot confirm.
  - He shows what he likes (stream selection).
  - 2018 has NO call, and 2017 / 2019 hold 6 / 8.

## 3. CONTROL — the same day's other breakouts

- **The control is every OTHER tl breakout on his calls' E dates:** same era, same universe and data rules, walked under the identical
  rules.
- **Exclusion (Track A round-3 rule):** a row is excluded only when its (stock, `base_id`) carries a matched label of any grade said
  ON OR BEFORE that row's own E. Era A excludes 410 of 23,598 rows, leaving n = 23,188 (fit 15,107 / hold-out 8,081). Era B excludes
  7, leaving n = 345. Asserted.
- **"Not shown on stream" is not "rejected":** some control breakouts are ones he would have bought, so a his-minus-control difference
  is a floor.
- **First breaks and retriggers are reported apart in both arms.** The mix differs by construction: his calls are 132 / 104, the
  control 5,575 / 17,613.
- The DECIDING difference is **date-matched** (§5): each control trade is weighted to his trade count in its own (date, first-break /
  retrigger) cell, so the control is read on exactly his days and his mix. The control's events per date run from 2 to 625 (median
  126.5); pooled across dates, the mass-breakout days would dominate it.

## 4. HIS RULES — the walk (primary from his article's S-quotes; the runner's functions, unchanged)

| piece | rule | his words (S) / source | code (imported read-only) |
|---|---|---|---|
| entry (PRIMARY) | **ORH5 on E**: the first minute after the 5-minute opening range whose high exceeds max(the opening-range high, the trendline level projected to E), filled at that level, or at the minute's open if it gapped through, plus 0.1% slippage | **S** *"The opening range highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle"* | `cb.entry_variants` |
| stop | **the low of the day AT THE FILL** (minutes 09:30 … fill); the trade is **skipped (`too_wide`) when the stop is wider than ADR20** of the watch night | **S** *"Stop is always lows of the day"* · *"stop should not be wider than the ATR or ADR"* | same |
| day 0 | after the fill, the rest of E is walked on the minutes; a stop-out is −1R, or worse on a gap | the runner's day-0 walk | `cb.day0_walk` |
| exit (PRIMARY) | **`p33_s3_t10`**: sell 1/3 at the close of session 3 (E = session 0); the stop moves to breakeven from the next session; the rest sells at the NEXT OPEN after the first close under the 10-day simple average (live only after the third); a daily bar touching the stop exits there (at the open on a gap); horizon 120 sessions, then marked | **S** *"sell 1/3 to 1/2 of the position after 3-5 days, and then move the stop to break even … trailed with the 10- or the 20-day moving average … You wait for the first CLOSE below the 10-day"*; next-open fill = his 2026-09-29 execution ruling | `cb.walk_arms` (what `runner.walk_arms` wraps; called directly because the account needs each exit's date, which `runner.arm_result` drops; equality with `runner.walk_arms` and `runner.evaluate_candidate` is tested) |

- **Beside, never deciding:**
  - The other 7 cells of the same S grid: 1/2 sold (`p50_*`), day 5 (`*_s5_*`), and the 20-day trail (`*_t20`).
  - **His operator exit `pp`**: `runner.exitpb_walk_arms`, unchanged. It sells a third at +2R (day 0 on the minutes) or at the
    session-3 close only if that close is above the fill. The stop moves to breakeven after the third. The 20-day trail is live from
    session 3. The stall cut sells everything at the session-3 close if no +1R was reached by then. His 10-19 ruling; it is built on
    `c3_p33_t20_cut3`, not on `p33_s3_t10`.
  - **ORH1 and ORH60** under the primary exit (the same S-quote).
- **Re-entries: COUNTED, never walked.**
  - For each of his trades stopped out (the primary exit), count the later tl breaks of the same (stock, `base_id`) strictly after the
    exit day and within 20 sessions of E, and how many of those are themselves his calls.
  - The runner walks no re-entry on these events. `reentry_read.py` composes later breaks that the runner had walked anyway, and a
    called base's later breaks are on other days, outside this population.
- **Every event is walked independently.** A base with two called crossings contributes two walks, as in Track A §6. The
  one-event-per-base reading is beside.
- **Costs (the standard's step 8):** the entry pays 0.1% (in the fill). Every R headline is printed at 0 / 0.1 / 0.2% exit slippage
  per leg. The headline itself is at 0, the runner's own convention. An edge that disappears at 0.1% is not an edge.
  **W3 (the fill at half the fill-minute's run-through) is NOT built.** The fill is the runner's: the level, or the minute's open when
  it gapped through, plus 0.1%. W3 applies to an ORH entry, unlike Track A's close entry; it is a sensitivity for a later read and
  never decides here.
- **Early-close days (G9):** the ORH entries read the minutes as stored, for parity with the pinned runner. 2 of his calls and 133
  control events fall on a 13:00-close day; fills after 13:00 on those days are counted beside every fill statistic.

## 5. MEASURES — tail first (era A decides; era B, n = 9, descriptive)

- **Per trade R** (`realized_r`, R = fill − the entry stop, measured against the entry stop after the breakeven move). Only MATURE walks
  count: a terminal exit, or the 120-session horizon with its next open behind it. A walk that is not mature (degraded / open mark) is
  counted and in no per-trade number.
- **Order of every table:**
  - ≥5R, ≥10R and ≥20R **per 100 trades** (filled + mature);
  - max R, worst R;
  - win rate (descriptive: entry and exit do not control it);
  - mean R, median R, sum R;
  - **per 100 EVENTS beside**: an event that did not fill or abstained counts 0R in the denominator.
- **Splits:** his calls, the control, first breaks vs retriggers in each, by year of E, by QQQ state (§7), the strictly-before
  subset, the one-event-per-base reading, and the post-E-only events (hindsight). Era B is in the same table, descriptive.
- **The difference (DECIDING input of the fork's interval arm):** his calls minus the control, per filled mature trade, on mean R,
  with ≥5R and ≥10R per 100 beside.
  - **Date-matched.** A cell is (date of E, first break / retrigger). Each control trade is weighted by his trades ÷ the control's
    trades in its own cell, filled + mature only. So his-minus-control = the sum over cells of his trades × (his mean − control
    mean), divided by his trades.
  - A cell holding his trades but no control trade is **dropped and counted** (cells and his trades).
  - **Beside:** the stratum-only difference (first breaks and retriggers apart, combined with his filled mature trades' shares, pooled
    across dates) and the pooled difference (no weighting).
  - **Month-block bootstrap:** calendar month of E (a month carries whole dates); 2,000 resamples; seed 702, key
    `qm_replay|A|orh5|p33_s3_t10|<measure>`.
  - **ONE draw of months per resample is applied to BOTH arms and to all three differences**, each computed inside the resample.
  - The cell weights are his trade COUNTS from the full sample. A month drawn twice enters twice and its cells' means do not change,
    so nothing is re-estimated inside a resample.
  - A resample with no covered cell (date-matched) or an empty weighted stratum (stratum-only) is dropped and counted. 95% interval.
- **Corporate actions:** any of his trades holding a G5 DISCONTINUOUS event (`A_flags.tsv`) is flagged, and the worst trade is quoted
  with and without it.

## 6. ACCOUNT CURVE — putting his trades back together

- **His calls only, chronological** (era A; era B beside), over the filled walks of the primary rule.
  - Start equity 1.0 at the close before the first E of the walk set (his calls and the control share their dates).
  - **His sizing:** **risk 1% of equity per trade**: position value = equity × min(risk ÷ width, cap), with width = (fill − stop) ÷
    fill. **Position capped at 20% of equity.** This is the SSoT's article sizing, position = min(20%, 1% ÷ stop width).
  - **At most 30% of equity in one stock, at cost** (his per-stock limit): the cost still held in a ticker (shares not yet sold × their
    fill) may not exceed 30% of the sizing equity. A second position in a held stock takes only the room left (counted), and with no
    room left it is skipped (counted). A sell leg takes its shares' cost off the held cost.
  - Equity for sizing is the **mark-to-market at the PREVIOUS close** (cash + every open position at that close), so there is no
    E-day look-ahead.
  - **No margin:** a trade whose full position does not fit the free cash is **SKIPPED and counted**. That is the "no room" rule; it
    needs a gross cap, because a per-position cap alone never leaves "no room".
  - **Concurrent positions allowed**, including a second position in a stock already held, inside the 30% per-stock limit (counted).
  - **Partial sells and the trail exactly as the walk:** each sell leg sells its fraction of the ORIGINAL shares at its own price and
    on its own date.
- **Order inside a day:**
  1. Exits at the open (trail fills, gaps through a stop).
  2. Entries in fill-minute order.
  3. Intraday exits (stops / targets touched, every day-0 exit).
  4. Exits at the close (session partials, the stall cut, marks).
- A walk whose bars end inside the horizon (delisting) is closed at its last close, as the walk books it, and counted.
- **Reported:**
  - equity at each year end, and the yearly return 2017–21 (2022 = exits only);
  - the final equity;
  - **max drawdown** on the daily marked curve;
  - trades entered and skipped per year; the totals skipped for no room, skipped or trimmed by the per-stock limit, skipped for the
    same stock (beside), cap-bound, and concurrent in one stock;
  - max open positions and max gross exposure.
- **Beside (never deciding):**
  - risk 0.25% and 0.5% (the rest of his range) at the 20% cap;
  - caps of 10% (the bottom of his position range) and 30% (his per-stock limit) at 1% risk;
  - "trim to the free cash" instead of skip;
  - a second position in a held stock skipped;
  - 0.1% exit slippage;
  - his calls under every beside exit / entry at the primary configuration;
  - the post-E-only events' curve (hindsight);
  - era B's curve (9 calls).
- **The reference band:** the SAME simulation, same configurations, on **200 draws of control events**. On every date, the draw takes
  as many control events as his calls on that date (without replacement; all of them on a date that holds fewer, counted — 0 such
  dates). Seed 702, key `qm_replay|band|A|<band>`.
  - **Reported:** the 5th / 25th / 50th / 75th / 95th percentile of each year's return, the final equity and the max drawdown, and
    the share of draws at or above his calls. For max drawdown, higher is WORSE: that share is the draws whose drawdown is as deep
    as his or deeper, and the printout labels it so.
  - The share of draws at or above his **final equity at the primary config** is an input of the fork's curve arm (§8).
  - **Beside:** a mix-matched band (each date's first-break / retrigger counts matched; a short stratum topped up from the other,
    counted).
- **Sizing source: his captured words.** `docs/methodology/operator_shared_notes.md` (his consolidation-breakout article, "Size"):
  *positions 10–20% of the account; risk 0.25–1% a trade, rarely more than 1%; at most 30% of the account in one stock overnight*. And
  the SSoT, `docs/setups/consolidation_breakout.md` (Paper path): *the article's sizing (position = min(20%, 1% ÷ stop width))*.
  - The primary takes the top of his risk range with the SSoT's 20% cap and his 30% per-stock limit.
  - The rest of his range (0.25% / 0.5% risk, a 10% cap) and the 30% cap are beside.
  - The per-stock limit is applied at entry, at cost. His word "overnight" is not modelled apart: a position bought on E is held
    overnight by every walk except a day-0 exit.

## 7. EXPOSURE / MARKET split

- **QQQ at D** (the close of the watch night, the last close known when the entry is made on E): "up" = the close is above BOTH its
  10- and 20-day simple averages (the registration's "uptrend"); "down" = below both; "mixed" otherwise.
- Every per-trade measure is reported per state for both arms.
- Outcome-free counts: his calls up 163 / mixed 35 / down 38 (n = 236); control up 17,282 / mixed 3,123 / down 2,783 (n = 23,188).
  Era B: his up 8 / down 1; control up 267 / down 78.
- A reading of the state, never a filter; no number here decides on it.

## 8. THE FORK — written now, before any outcome

| reading (era A, primary rule, primary account) | → where the gap is | the next work |
|---|---|---|
| **STRONG** = (the **curve arm**: the his-calls curve returns **≥ +50% in at least 2 of the 2017–21 years** at the primary sizing **AND at most 5% of the 200 registered same-day band draws end at or above his final equity**), OR (the **interval arm**: the **date-matched** his-calls minus control **mean-R interval has its lower end above zero**) | **SELECTION** — his calls, traded his way, beat the same day's other breakouts; our system's gap to his record is WHICH breakouts it takes | fix the filter: the unit becomes first breaks of leaders, the base-depth direction is corrected, a wider cap; validated on unread data, never on 2017–21 |
| **DATES / MARKET** = his curve returns ≥ +50% in at least 2 of the 2017–21 years, BUT more than 5% of the band draws end at or above his final equity, and the interval arm is not met | **THE DATES / THE MARKET** carry it, not the stock picks — the same day's other breakouts compound as well | which DAYS to be in (the market / exposure question, §7's QQQ state is only a reading here), its own registration |
| **WEAK** = none of the above (the curve not strong, the interval arm not met) | **EXECUTION / data** — even his own calls do not carry it under these rules | vary entry, stop, exit and sizing per his words (ORH1 / ORH60, the stop variants, his `pp` and 20-day trail, his sizing), each as its own registration |

- **Read honestly — the curve arm is effectively "2020 AND 2021".** 2018 holds no call, and 2017 / 2019 hold 6 / 8.
  - What +50% in a year needs at the primary sizing: about 50R summed over the year's trades when no trade is cap-bound (1% each).
  - The 20% cap binds whenever the stop is under 5% wide (§9 expects most ORH5 stops to be). A cap-bound trade risks only 20% × its
    stop width: 0.4% of equity at a 2% stop, so +50% needs about 125R there and about 250R at 1% stops.
  - No margin allows at most five 20% positions at once.
  - So six or eight trades rarely make +50%, and the curve arm needs both 2020 (156 calls) and 2021 (66 calls) at +50% or more. The
    rule stands as written; this note is said with it.
- **The band condition** keeps the curve arm from reading the days as picks: if 2020–21 lifted every breakout, his curve can be strong
  while the same day's other breakouts compound as well. That reading routes to DATES / MARKET, not to SELECTION.
- **The interval arm** reads the per-trade difference. It can be met with a modest curve (his picks beat the day's other breakouts,
  even if neither compounds hugely). The fork calls that SELECTION too, because the picking is what separates.
- **What NEITHER outcome can show:**
  - **A strong reading does not show:**
    - that our detector finds his picks (Track A's fit FAILED, 1 of 66);
    - that the ON-E calls were knowable before the open — 109 of the 236 rest only on a label said with part of E's bar visible
      (119 carry an on-E label, 10 of them also an earlier one), so the strictly-before 127 are the clean subset;
    - that the result transfers to 2022+ or to the sealed 2025–26 table;
    - that he sized these trades this way: 1% / 20% / 30% is one point of the ranges he wrote, not his fills.
  - **A weak reading does not show** that his selection lacks edge:
    - our trendline E may not be his entry day;
    - the stream slice may not be his book;
    - ORH5 / the low-of-day stop / the day-3 third may not be how he traded these;
    - his record also holds EPs and shorts.
  - **Neither shows his returns.** The account is an illustration of our replay of a slice of his calls, never a reconstruction of
    his audited P&L.
- **Beside the verdict, deciding nothing:** both arms on the **127 strictly-before calls**, the subset clean of E's bar. The curve on
  their trades at the primary config, against their own same-day band (200 draws of control events, as many per date as their calls,
  seed 702, key `qm_replay|band|A|strictly-before (beside)`), and the date-matched interval (key `…|mean R|strict`). No rule changes.
- **Era B (n = 9) never decides**; it is read for direction only.

## 9. Expectations, written now (a miss changes no rule)

- His calls beat the control on ≥10R per 100 trades and on mean R. The control reads like the published R1 / C0 populations: mean
  R near zero, ≥10R in about 1–4 per 100.
- The post-E-only events read above his calls (hindsight). The strictly-before calls read at or below the ON-E calls (the
  intraday-conditioning worry in §1.4a).
- 2020 is the strongest year for both arms. 2021 is weaker.
- The worst trade is an overnight gap through the low-of-day stop, about −3 to −10R.
- The win rate is near his own ~25%. The control's median yearly return sits near zero.
- Most of the curve's growth comes from fewer than 10 trades (outliers, his 10-19 point).
- The 20% cap binds on most of his calls: it binds whenever the low-of-day stop is under 5% wide (1% ÷ 20%), as most ORH5 stops are.
- The 30% per-stock limit binds only on a second crossing of a stock still held: rare (48 events are a second or later crossing of a
  called base).

## 10. DATA GATE (STEP 0) and the point-in-time declarations

- **Era A = `cb702_pre_v2`.** It passes S0, G1–G7 and G9 (`cb702_pre_v2/audit_1023/verdict.txt`, pinned; the module prints the lines).
  - **G8 = THIS read's own trade list:** the real run writes the `--kind r1` file (`g8_A.tsv`: cell = the arm, attempt 0, entry_date
    = E, exit_j = sessions held) and runs `scripts/backtest_data_audit/trade_impact.py --kind r1 --cell p33_s3_t10 --cutoff
    2024-12-31` on it BEFORE any number is printed.
  - **It must read entered-after-cutoff 0 and holds-past-last-bar 0 (asserted; else STOP, exit 3).** Its console is kept
    (`g8_A_impact.txt`).
  - G10 (overlap parity) is not run: no era comparison decides here; era B is descriptive.
- **Era B = `cb702`.**
  - Every export, candidate and fetch-log row dated after 2024-12-31 is dropped at read and asserted. No minute file after the cut is
    opened; the fetch log's bytes are hashed whole for its pin, and its later rows are dropped at read.
  - G8 runs the same way, with its two counts printed beside the headline and every walk that is not mature censored.
  - All 9 + 345 events have E + 121 sessions ≤ 2024-12-31 by the calendar (dry run: 0 run past it).
- **Identity breaks:** era A `cb702_pre_v2/symbol_guard.tsv` (667 symbols; equal to the audit's `symbol_guard_A.tsv`, checked); era B
  `scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv` (1,292 symbols).
  - **Before E:** an event whose (E − 130, E] window holds a listed break is EXCLUDED and counted, as in Track A §6. Outcome-free; the
    dry run reads it: 0 events in every arm.
  - **After E: no exclusion.** A break dated inside the walk's forward window cuts that window at the session before the break, the
    way `forward_window` already treats a hole. A trade that exited before the break is unchanged and stays mature. One still open
    there ends `degraded`: booked in the account at its last close, in no per-trade number, counted and listed by name. (Excluding
    the event instead would drop it on forward information, even when the trade had exited long before the break.)
  - The forward half is forward information and is read in the real run only.
- **Minute coverage:** from the fetch logs (`_done.psv` status) only — every event is `ok` (his 236 / 9, control 23,188 / 345,
  post-E 87 / 3; 0 empty, 0 missing).
  - A fetched-but-empty block would abstain `no_minutes`.
  - A pair never fetched would be excluded and counted.
  - `minute_daily_mismatch` and the other entry abstains are counted per arm in the real run.
- **Point in time:**
  - era A symbols keyed by today's symbol with the rename map and dedupe aliases (the join's resolutions); era B point-in-time;
  - splits as adjusted by each vendor at its fetch date (Alpaca A / Polygon B);
  - the candidates' trendline level, ADR20 and RS are the detector's values at D (its own slice test guards them);
  - the QQQ state from QQQ closes ≤ D;
  - nothing from E's bar enters a selection: the classes come from the labels and the candidate keys; E's bar enters only the
    entry, as the walk requires;
  - era A is the survivorship-fixed v2 export, so the *survivors only* label does not apply.

## 11. Method / population — files, the module, its guards, the readings chosen

- **Inputs (pinned; the Track A pins re-checked at start, a drift refuses even the dry run):**
  - labels and joins: `track_a_1023/labels_joined.tsv`, `matched_events.tsv` (columns era, sym, E_tl, bought, not_yet, best only —
    never `r1_status` / `r2`), `vision/graded_moments.tsv` (the frozen `label_sets` reads it);
  - era A: `cb702_pre_v2/out/candidates_tl_com.tsv` (K = tl; 81,015 rows, 20,650 first breaks), its `daily_closes_all.csv.gz`
    (2,548 tickers kept of 12,532: the walk set + SPY + QQQ), `sessions.txt` (1,635 sessions, asserted equal to the export's SPY
    dates), `minutes/` (the 193 date files of the walk set: his calls' 156 dates + 37 dates that carry only post-E-only events; tree hash pinned) and `minutes/_done.psv`;
  - era B: `cb702/out/candidates.tsv` (discovery, tl, ≤ the cut; 41,200 rows, 12,250 first breaks), its export (247 tickers kept), its
    minutes (8 date files, all ≤ the cut) and `_done.psv`;
  - the guard and flags files of §10.
  - From the candidates only `ticker, D, E, K, base_id, pole_date, retrigger, retrigger_chain, pivot, adr20, split, C1` are read (no
    E-day column; the walk reads E's bar from the export).
- **Code (pinned):**
  - `scripts/probes/_705_qm_replay_1023/01_replay.py`, its tests `test_01_replay.py` (42 pass: the hand-computed fill / stop / third /
    trail trade; parity with `runner.walk_arms`, `runner.exitpb_walk_arms` and `runner.evaluate_candidate`; the loader equal to
    `runner.load_daily`; the era-B cut; the identity-break cut after E (a break after the exit leaves the walk unchanged and mature,
    one before it degrades it, one on E + 1 leaves an empty window); an `empty` event with no date file abstaining `no_minutes`; the
    account (his sizing as the primary, cap, the 30% per-stock limit at cost, compounding, skip, trim, same-stock, partial cash,
    previous-close sizing, marked drawdown, slippage); the control draw; the paired bootstrap, and the date-matched difference
    against the pooled one on a control heavy on bad days; the three-way fork; the slippage pin; the G8 file through the real
    `trade_impact.py`; the freeze lock; an end-to-end synthetic run of the real-run path);
  - `scripts/probes/_cb_backtest/runner.py` and `registered_read.py` (read-only, never edited);
  - `agents/market_intelligence/consolidation_breakout.py` (= `runner.EXITPB_MODULE_SHA`, `pp`'s hard pin);
  - `agents/market_intelligence/constants.py` (`ENTRY_SLIPPAGE_PCT`, the 0.1% every fill pays by default; the module asserts
    `cb.ENTRY_SLIPPAGE_PCT == 0.001` and `entry_variants`' default at import);
  - the frozen Track A fit module, `01_join_labels.py` (its grade regex) and `aplus_read.py`;
  - `trade_impact.py`.
- **The module's guards:**
  1. **Freeze lock:** the real run refuses (exit 2) unless every pin printed by the dry run — including the sha256 of this doc's text
     above the freeze marker, taken at run time — appears under the marker.
  2. It refuses (exit 2) if `01_replay.txt`, a STOPPED file or any output under `apollo_data/cb702/qm_streams/qm_replay_1023/` exists.
     An unreadable control band at the fork is a refusal too (the run STOPS), never a silent arm.
  3. **Populations asserted:** every count in §2–§3 plus the stream sizes. A miss stops before any minute file is opened or any walk
     runs.
  4. **G8 before numbers**, era A asserted 0 / 0.
  5. Per trade, the realised R recomputed from the dated sell legs must equal the walk's own `realized_r` (to 1e-9), and the legs'
     fractions must sum to 1.
  6. A crash after the walk writes a STOPPED file with the traceback (never a silent re-run).
- **Readings chosen where the brief was open (B = this registration's choice):**
  - **R1 (unit):** per 100 TRADES headline, per 100 events beside; the deciding mean-R difference is per filled mature trade.
  - **R2 ("no room"):** no margin, full position or skip (parameter-free); trim beside.
  - **R3:** sizing on the previous close's marked equity; the within-day order of §6.
  - **R4:** a second position in a held stock is allowed (Track A's every-event unit) inside his 30% per-stock limit at cost (it takes
    the room left, else it is skipped and counted); skip beside.
  - **R5:** the QQQ state at D's close, not E's.
  - **R6:** the date-matched weights are his FILLED AND MATURE trade counts per (date, stratum) cell, from the full sample; the
    stratum-only beside uses his filled and mature trades' shares (Track A fixed them at event shares, 132 / 104, for a per-event
    measure); a zero-weight stratum is ignored.
  - **R7:** the band draws EVENTS, not trades — a sampled control event that does not fill is no trade, exactly as one of his calls
    that does not fill. So the band holds his calls' per-day event count, not their trade count.
  - **R8:** the identity-break exclusion follows Track A §6 for the (E − 130, E] half only. A break after E CUTS the forward window
    at the session before it (§10), over the whole forward window the walk reads (E + 1 … E + 121), never excludes. A "jump"-kind
    break may be a real move, so every cut event is listed by name with its break date and whether its primary walk had exited.
  - **R12:** a (date, stratum) cell of his trades with no control trade is dropped from the date-matched difference and counted,
    never filled from another date.
  - **R9:** the early-close fills are counted, not trimmed (runner parity).
  - **R10:** re-entries counted within 20 sessions of E (Track A's T2 window).
  - **R11:** the dry-run counts `cand_B_not_discovery` 109,478 / `cand_B_after_cut` 240 are of `candidates.tsv` alone. Track A's
    174,495 / 328 also counted `candidates_com.tsv`, which this read never opens.
- **Outputs (real run):**
  - `scripts/probes/_705_qm_replay_1023/01_replay.txt`;
  - under `apollo_data/cb702/qm_streams/qm_replay_1023/`:
    - `trades.tsv.gz` (one row per event × entry × arm, with the dated legs);
    - `g8_{A,B}.tsv` and `g8_{A,B}_impact.txt`;
    - `account_his.tsv` (the daily curves);
    - `account_band.tsv`.

## 12. What this does not answer

- **His actual returns.** The account compounds OUR walk of a stream-confirmed slice of his calls under OUR reading of his rules
  and one point (1% / 20% / 30%) of the sizing ranges he wrote. It is never a reconstruction of his audited P&L, which includes EPs,
  parabolic shorts, his own fills, his adds and his sizing.
- **Whether the calls were knowable before the open.** 109 of 236 rest only on a label said on E with part of E's bar visible (119
  carry an on-E label, 10 of them also an earlier one); only the strictly-before 127 are clean of it. Every headline carries this.
- **Whether our detector finds his picks.** That is Track A (FAIL at 6 a week); this read assumes his picks and asks only whether they
  pay.
- **Anything about 2022+ beyond 9 descriptive calls, and nothing about 2025–26** (unread; sealed).
- **Re-entries' value.** Counted, never walked; a re-buy campaign is a separate registration.
- **What the uncovered cells would have read.** A (date, stratum) cell of his trades with no control trade drops out of the deciding
  difference; the count is printed.
- **Single-regime dependence.** 156 of 236 calls are in 2020 and 2018 holds none; a strong curve can be the 2020 rebound.
- **The selection of what he showed.** He shows what he likes and may show winners more than losers. The post-E-only reading
  measures the after-the-fact part of it, not the whole.

## 13. Revisions after review (2026-10-23, before the freeze)

The adversarial review (`scripts/probes/_705_qm_replay_1023/verify/review.md`, verdict FIX) opened no outcome. Every fix below was
applied before the freeze; no outcome was read to make any of them. Line numbers are of `01_replay.py` (module) and
`test_01_replay.py` (tests) as frozen.

| fix | what changed | where it landed |
|---|---|---|
| 1 (HIGH) the deciding comparison was pooled across dates | date-matched: each control trade weighted by his trades ÷ the control's in its own (date, stratum) cell, filled + mature only; uncovered cells dropped and counted; month blocks kept; stratum-only and pooled beside | doc §3, §5, §11 R6 / R12, §12 · module `paired_block_diff` l.679 (date-matched block l.738), `his_minus_control` l.1338, fork input l.1511 · tests l.440, l.456 (a control heavy on bad days: date-matched 0 vs pooled +1.23), l.471 |
| 2 (MEDIUM) sizing source misstated, not the SSoT's, no per-stock limit | primary = his words + the SSoT: 1% risk, 20% cap, 30% per stock at cost (a second position takes the room left, else skipped and counted); beside 0.25% / 0.5% risk, caps 10% / 30%; §6's false claim corrected | doc §0, §6, §8, §9, §11 R4, §12 · module `Config` l.181, `CONFIGS` l.199, the limit in `simulate` l.817 · tests l.323, l.333–418 (l.380 the limit at cost) |
| 3 (MEDIUM) the curve arm could read the days as picks | the curve arm also needs at most 5% of the registered band's draws at or above his final equity (primary config); third row DATES / MARKET registered; §8's "~100R at 0.5%" replaced by what the primary sizing needs | doc §0, §6 (band), §8 · module `BAND_SHARE_MAX` l.174, `fork_verdict` l.933, the fork l.1511 · test l.496 |
| 4 (MEDIUM) a break after E excluded the event on forward information | no exclusion: the forward window is cut at the session before the break; an exited trade stays mature, an open one ends `degraded` (booked in the account, in no per-trade number, counted, listed by name) | doc §10, §11 R8 · module `cut_at_break` l.541, `walk_event` l.559 / l.571, `walk_all` l.1199, the listing l.1242 · tests l.214, l.231, l.246, l.269 |
| 5 (LOW) the on-E calls in the deciding set; the 119 / 109 / 10 wording | both fork arms printed on the 127 strictly-before calls beside the verdict (their own band; the date-matched interval); no rule change. Wording: 109 rest only on an on-E label, 119 carry one, 10 carry both; 127 + 109 = 236, asserted | doc §1.4a, §8, §12 · module `EXPECT` l.210, `population_counts` l.447, the beside print l.1536 · test l.659 (end to end) |
| 6 (LOW) `constants.py` not pinned | pinned in `CODE`; `cb.ENTRY_SLIPPAGE_PCT == 0.001` and `entry_variants`' default asserted at import | doc §11 · module l.69, l.125 · test l.637 |
| 7 (LOW) R6 wording | "filled AND mature" | doc §11 R6 |
| 8 (LOW) an `empty` event with no date file raised a KeyError | `.get`; no file → no block → the entry abstains `no_minutes`, counted | module `walk_all` l.1181 · test l.257 |
| 9 (LOW) degraded walks were in no printed number | per group: the not-mature count, degraded / cut at a break, and their summed booked R, beside the per-trade table | module l.1327 · test l.659 |
| 10 (NOTE) the band's max-drawdown share read inverted | labelled: max drawdown "higher = WORSE"; the share column says draws as deep or deeper | doc §6 · module l.1475, l.1494 · test l.659 |

<!-- FREEZE -->
## Freeze record

Empty until the freeze commit. The main loop pastes, below this line, every pin `01_replay.py --dry-run` prints under "## Pins
(sha256)", including `doc_body` (the sha256 of the bytes above `<!-- FREEZE -->`). It then commits, and then runs
`python3 scripts/probes/_705_qm_replay_1023/01_replay.py` once. Any edit above the marker after that changes `doc_body`, and the run
refuses.

Pre-flight (outcome-free, 2026-10-23): `trade_impact.py --kind r1 --cell p33_s3_t10` on each era's REAL flags file and export, with a
one-row dummy SPY trade list (no event), exits 0. The module's `parse_g8` reads both G8 lines on each: era A (0, 0), era B (0, 0).

Recovery after a STOPPED run: a stop after the walk leaves files under `apollo_data/cb702/qm_streams/qm_replay_1023/` (`trades.tsv.gz`,
`g8_*`), and each one blocks a re-run. Recovery = fix, delete `01_replay.STOPPED.txt` AND those files, and re-freeze if the module
changed. Any outcome the stopped run printed is recorded as seen.

### FREEZE 2026-10-23 (this commit; the one real run follows it)

The inline mention of the marker inside §11 was reworded before the pins were taken (the round-3 recheck's blocker: the hash had split at that mention), so the doc_body hash below covers every line above the real marker (line 422).

- labels_joined: d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b  /Users/alvinfung/apollo_data/cb702/qm_streams/track_a_1023/labels_joined.tsv
- matched_events: 4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc  /Users/alvinfung/apollo_data/cb702/qm_streams/track_a_1023/matched_events.tsv
- moments: f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0  /Users/alvinfung/apollo_data/cb702/qm_streams/vision/graded_moments.tsv
- cand_A: 3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a  /Users/alvinfung/apollo_data/cb702_pre_v2/out/candidates_tl_com.tsv
- cand_B: b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7  /Users/alvinfung/apollo_data/cb702/out/candidates.tsv
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d  /Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba  /Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0  /Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt
- guard_A: 876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08  /Users/alvinfung/apollo_data/cb702_pre_v2/symbol_guard.tsv
- guard_A_audit: 729741b4cfc5759b6ea5d81da6afdd36c11d806bbcad845964b2b37c72d94057  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/universe/symbol_guard_A.tsv
- guard_B: b6cb81b6c4a1f415defc5adcf236402d93cd654c33736aa0b120b78c357b5650  /Users/alvinfung/apollo_the_wise/scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv
- flags_A: 5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/price/A_flags.tsv
- flags_B: 8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5  /Users/alvinfung/apollo_data/audit_runs_2026-10-23/B_flags.tsv
- verdict_A: 02cbb1c0106101cb12e8d5deb9448051ae3ced67966ac11d2475d06f26538de3  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/verdict.txt
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6  /Users/alvinfung/apollo_data/cb702_pre_v2/minutes/_done.psv
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178  /Users/alvinfung/apollo_data/cb702/minutes/_done.psv
- runner: 213cbe6ddf0ff05555a11c347efd14bfa37f99096fd83961e9f5127f6c7c8dcf  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/runner.py
- registered_read: 28fbc47f862f205071ab921af3a29f6093fca95e2d41e3a0f4a0f7afcd9aa449  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/registered_read.py
- cb_module: e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b  /Users/alvinfung/apollo_the_wise/agents/market_intelligence/consolidation_breakout.py
- constants: 72dadd72503a842f593621b0868f908ab99e1d77851330c2842be7797aa99400  /Users/alvinfung/apollo_the_wise/agents/market_intelligence/constants.py
- fit_module: 3fca7bf4f26ffcdf7152ddc9d4180c295aafe29067591def812fcc6884f38d27  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/02_fit_filter.py
- join_script: 6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/01_join_labels.py
- aplus_read: e344277817db88de7af2e65ad8858d4ca515c3cc3a647b3e0a67e0df9f7ec9ee  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/aplus_read.py
- trade_impact: 9b7cce415479c1abfda422c432c6de1f3a6d591f298a1167fa637a578051e146  /Users/alvinfung/apollo_the_wise/scripts/backtest_data_audit/trade_impact.py
- replay_module: c44785889670b31f3e9baf1ac0e1563aeacfefacc5de5ef426ee7b15724e7bfa  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/01_replay.py
- replay_tests: 37c918a08329b138f6c37c5787af3c95e0ea2abeceb100209cd0f5f0dd0a96ad  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/test_01_replay.py
- minutes_A_used: b6a99cdf084ad42c1a4d846e05d10b48404f8225499253583ff78170e95b592a  the 193 minute date files the walk set opens
- minutes_B_used: d548f85679b9ded20bfa4650c45535d685d820d4dd2040fce84d01bae7b2b652  the 8 minute date files the walk set opens
- doc_body: aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab  the doc text above the marker

## RESULT — the one real run, 2026-10-23 after the freeze commit `2c080f19` (printout `scripts/probes/_705_qm_replay_1023/01_replay.txt`)

- **Registered verdict: EXECUTION / data.** Curve arm: no 2017–21 year reached +50% at the primary sizing (2020 +47.9%, 2021 +25.3%;
  final equity 1.850), although the same-day band sits at or above his final equity in only 0.5% of 200 draws (≤ 5% needed). Interval
  arm: his minus same-day control, date-matched, +0.543R per trade [−0.132, +1.424] — includes zero.
- **His picks beat the field clearly:** final equity 1.850 against the same-day random-pick band's median 1.111 and 95th percentile
  1.441; per trade +0.639R (174 filled) against +0.120R (17,939); 2020 +47.9% against a band median of +2.4%.
- **But far below his audited record**, and the run shows where our version leaks (descriptive, read after the verdict):
  - **62 of his 236 calls never fill:** 42 never trade above OUR level after the opening range, 20 are skipped as a stop wider than
    the ADR — he bought them, so our level or our stop rule is not his.
  - **Re-entries are not walked:** 134 of 174 trades stop out; 91 of those bases break again within 20 sessions of E (33 of the
    re-breaks are themselves his calls) — his "even if we need to retry" is missing from the account.
  - **Sizing without margin:** 28 calls skipped for no room at a 20% cap; the 30% cap reads final 2.044 (2020 +62.8%).
  - **2021:** his calls −0.199R per trade (50) against the control's +0.207R — the year the growth names broke in Feb–Mar.
  - The 20-day trail and selling on day 5 lift the mean (+0.82 / +0.83R) but not the curve.
- **Era B (descriptive):** 9 calls, all losers (−0.94R mean).
- **What this cannot show:** his full P&L (these are 236 stream-confirmed breakout calls; his record also holds EPs, parabolic
  shorts, adds and the trades never mentioned on stream). Independent recount: running (`verify/recount/`).
