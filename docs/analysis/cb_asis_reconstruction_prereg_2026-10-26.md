# #705 — his trades as they are (steps 5-7 of his plan) — registration (2026-10-26)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** Written for the operator's review; nothing runs until he says go. His words that
set this (2026-10-26, verbatim, `docs/methodology/operator_shared_notes.md` l.2608-2612): *"The key thing is stop trying to pigeon
hole his trades, we're starting without any preconceptions, I want to reverse eng his trades as they are, not as we want them to be
and fit into our rules, that reconciliation comes later"*, and his eight steps (l.2606): steps 1-4 are held (his outsized returns,
his list of traded stocks, his rough rules, the approximate day he entered and left each stock); **this document designs steps 5, 6
and 7 and names where step 8 begins.** His reference for step 6 (l.2610): *"I have nothing but his streams, but he streamed daily for
years, it should be sufficient"* — his own words on stream.

**What this read does NOT use:** our rule library (breakouts, EP, opening-range entries, the day-low stop, the 10/20-day exit, the
60-minute chart — every rule named in the four earlier reads). Those reads (`cb_reverse_engineer_his_rules_prereg_2026-10-24.md`,
`cb_intraday_layer_prereg_2026-10-25.md`, `cb_rule_mix_prereg_2026-10-25.md`, `cb_context_rules_prereg_2026-10-26.md`) each started
from our rules and went in circles; here a rule may appear only at step 8 (§6). **Inputs:** the two inventories measured today
(`scripts/probes/_705_asis_1026/inventory/captions.md`, `data.md`), the rule-free columns of his positions list, his captions, and the
daily and minute bars on disk. **Guards:** no paid model call, no network, no production server, nothing dated after 2024-12-31 (the
2025-26 data is sealed for #710), and none of the seven outcome folders of the earlier reads is opened
(`holdings_1024/{replay,his_exits,intraday,reverse,rule_mix,reverse_fit_events,reverse_recount_cache}`). Nothing here changes or
proposes to change a strategy, entry, stop, exit, size, safeguard or live trade state (THE LINE).

## 0. In plain words

- **What we will do.** For each of his trades we know the day (sometimes the half-hour) he bought and the day he sold, from the
  holdings panel on his screen. Step 5 turns each window into the minutes in which the trade could have happened, the lowest and
  highest price in them, and a list of every price point inside them that a trader looking at the chart could have acted on — the
  open, the first minutes' high, the previous day's high, a swing point, a round number, the close, and so on — with no opinion
  about which one he used. Step 6 tests the WINDOWS: do the prices he said on stream ("bought X at 42", "stopped out of Y") fall
  inside the range we reconstructed, better than they would for a wrong day or a wrong stock, and do the trades replayed at the
  average traded price add up to the kind of year he said he had. Step 7 reads the POINTS: what the trades have in common on the
  chart, with no names for the groups decided in advance.
- **What we will NOT do.** No list of rules is written before step 8. No point is labelled with one of our setup or rule names. No
  candidate is preferred because it fits something we believe. Nothing from the earlier reads' results is reused. Trades whose
  stated price disagrees with our reconstruction are kept and flagged, never dropped — his words outrank the screen.
- **Some listed points are the same levels our old rules used** — the first 5 minutes' high is our opening-range entry, the
  20-session high is a breakout level, the 10- and 20-day averages are our old exit line. They stay on the list because any trader
  sees them on a plain chart and leaving them out would hide his point by construction; they are never a pass bar in step 6, they
  are left out of step 7's grouping, and they are flagged so step 7 can be read with and without them.
- **What he gets at the end of each step, and the decision after it.**
  - **Step 5** → a table: one row per trade per candidate point, in chart terms, plus the lowest-to-highest price he could have paid
    or received. **His decision:** go to step 6, or first run the free four-minute minute-bar pull (§3.6; it runs on the production
    container, so it is his call) — with it, minute data goes from about 70% of buy windows / 60% of sale windows to about 90%.
  - **Step 6** → two readouts: how often his spoken price lands inside our range, against two wrong-answer controls (the same stock
    three days off; another stock he held that day), and how his spoken days line up with the windows; plus the account floor —
    the trades replayed at the average traded price, compounded, against the 15 dated figures he gave on stream. **His decision:**
    the windows are close enough to build on (go to step 7); or they are wrong somewhere and we fix and re-run; or the list's blind
    spots (trades between streams, sizes) are the problem and he decides whether to count them from the captions first.
  - **Step 7** → groups of trades with a plain-words description of what each group shows on the chart, and the share of trades in
    each. **His decision:** accept the groups, merge or split them, then step 8.
- **One thing to know now:** step 6's account check is a floor, not a proof. The panel misses trades made between streams (29% of
  sessions have no screenshot at all) and never shows sizes, so an account that falls short of his stated return cannot tell a wrong
  reconstruction from a blind one. The per-trade price check (§4.2) is the part that can.
- **Cost:** $0. About ten build-and-read sessions of my capacity over three weekend slots (the caption reading is the big one).
  His time: this review (about 30 minutes), then three short reports.
- **Action from him now:** read §12 (one decision: the minute pull, with or without extended hours) and say go or change.

## 1. The four questions of the standard

1. **Decision served:** whether his trades, reconstructed as they are, can be reproduced closely enough from the chart alone that the
   groups found at step 7 are groups of HIS behaviour and not of our assumptions. It changes nothing live and no branch of the sealed
   2025-26 test (#710 stays blocked on his 10-25 ruling).
2. **What would change it:** step 6's per-trade check failing its bar (§4.2 R1: his stated prices inside our range no better than
   for a wrong day or a wrong stock) — then the windows, the symbol join or the clock reading is wrong and must be found before any
   grouping; step 6's day-offset chart showing a systematic shift in statements whose day the reader pinned; a candidate list so
   dense (§3.5 density check) that "where on the chart he acts" cannot be read — then step 7 describes the trades from the band and
   the continuous chart measures only, and the point list is a description, never a finding.
3. **Population:** §2 — the 1,848 round trips with a buy window and a sale window from his holdings panel, 2017-01 to 2023-12, with
   2020-01..2022-06 as the primary span (1,511 buy windows, 1,538 sale windows) because that is where the captions and the bars are.
4. **Limits:** §11.

## 2. Steps 1-4 as they stand — POPULATION and what we hold

**Population (which rows, what window):** every row of `holdings_1024/entries.tsv` (1,874 positions) and `exits.tsv` (1,861 sale
windows); a round trip is a position with both a buy window and a sale window (1,848). Dates 2017-01-27 to 2023-12-14 (the span
of his streams on disk); nothing after 2024-12-31 is read from any file. Windows are read from `snapshots.tsv` (2,907 panel
screenshots), never from the rule-derived columns (§3.1).

Plain terms used throughout:

| term | meaning |
|---|---|
| **position** | one appearance of a stock name on his holdings panel, from first sighting to the first screenshot that shows it gone (a re-buy of the same name later is a new position) |
| **buy window** | the sessions between the last full screenshot WITHOUT the name and the first screenshot WITH it (`lo`..`hi`); one session wide when both screenshots are on the same day |
| **sale window** | the sessions between the last screenshot showing the name and the first of two full screenshots without it (`exit_lo`..`exit_hi`) |
| **clock bracket** | when the two screenshots are on the same day, the time span between their on-screen clocks (ET) |
| **full screenshot** | the panel shows every name (footer count equals rows read); only a full one can show a sale |
| **flicker** | a name seen in one stream only and gone within 5 sessions — a real short hold or a misread; the file cannot tell which |
| **inverted** | a window with no regular session in it (bought or sold pre-market / after hours) |

What each of his steps 1-4 rests on, in numbers (measured in the two inventories):

| step | what we hold | n | the hole |
|---|---|---|---|
| 1 his returns | 133 statements of account results in the captions; yearly 2013-2019 told identically twice; 2020 +710% to +1000%; 2021 a dated year-to-date path (+60% on 02-09 … +100% on 05-06); full-year 2021 never stated | n = 133 | 2020 and 2021 are ranges, not numbers; the base changes with withdrawals |
| 2 his list | 1,874 positions from the panel, 1,848 round trips | n = 1,874 | sizes, side (long/short), adds and trims never shown; trades between streams invisible (180 of 629 sessions in 2020-01..2022-06 have no screenshot) |
| 3 his rough rules | his words, `operator_shared_notes.md` l.1941-2096 | — | used at step 8 only |
| 4 approximate days | 62% of buy windows and 60% of sale windows are one session; 85% are 5 or fewer; same-day clock brackets for 43% of buys and 32% of sells, a median ~30 minutes wide | n = 1,861 / 1,861 | the afternoon is almost never on screen (last in-session frame median 10:40 ET); 659 flickers; 34 + 38 inverted |

## 3. STEP 5 — every plausible entry and exit, read off the chart

### 3.1 The windows we start from, and what is excluded by name

**Used (rule-free, from `entries.tsv` / `exits.tsv` / `snapshots.tsv`):** `eid`, `sym`, `sym_a` (the bar-file symbol — a data join),
`lo`, `hi`, `window_len`, `inverted`, `initial`, `flicker`, `n_sightings`, `n_streams`, `first_frame`, `prev_full_frame`, `first_date`,
`prev_full_date`, `first_ctx`, `exit_lo`, `exit_hi`, `exit_frame`, `still_held`, `first_resolution`; from `snapshots.tsv` every
frame's `date`, `clock`, `ctx`, `full`, `symbols`; from `vision/positions_panel_all.jsonl` each held row's `pct` (the panel's own
"% change" cell, a price-at-clock observation). The sale window's last-sighting frame and its inversion flag are recomputed from
`snapshots.tsv` (the inventory showed the file does not store them; the recomputation reproduces all 1,861 windows).

**Excluded by name (each is dated, labelled or selected by one of our rules):** `E`, `D`, `era`, `setup`, `pivot`, `adr20`, `base_id`,
`retrigger`, `ep_prev_close`, `ep_gap_pct`, `n_events_in_window`, `E_earliest`, `kind_earliest`, `q1_2022_hole`, `undated_reason`
(except the two data facts `initial` / `no_bars`), `first_clock_on_E`, `flat_clock_on_E`, `orh5_infeasible`, `decides`,
`ever_candidate`; the whole of `control.tsv`; every `w_*` / `kw_*` column of `stream_moments.tsv`; the grades; and every output of
the seven outcome folders. **A module-scan test fails the build if any of these names, or any of `level_at`, `intraday_levels`,
`stop_levels`, `held_through`, `exit_walk`, `h60_bars`, `ema_series`, `armed_index`, `load_breakouts`, `load_eps`, `events_in`,
`date_entry`, `control_rows`, appears in the step-5/6 code** (§10).

**Population per side:**

| set | buys | sales | note |
|---|---|---|---|
| windows, all years | 1,861 | 1,861 | n = 1,861 each |
| primary span, window end in 2020-01-01..2022-06-30 | 1,511 | 1,538 | where captions and bars are |
| of which flicker | 565 | 567 | kept, flagged, reported beside — "as they are" means not dropped |
| of which inverted (no regular session) | 21 | 26 | by year of the window end (2020 + 2021 + 2022); candidates cannot be read (no extended-hours bars); counted, not scored |
| of which no daily bar on any session of the window | 168 | 172 | §3.6: alias gaps fixed first, funds / delisted names listed |
| beside: 2017-2019, 2023, the 13 initial, the 13 still held | — | — | run and printed, never in a bar |

### 3.2 What "plausible" means here — two layers, no rule

**Layer A — the reachable set.** The minutes and sessions in which the trade could physically have happened, from the panel alone:

| bracket type (earlier screenshot → later screenshot) | reachable minutes | buys | sales |
|---|---|---|---|
| same day, in-session → in-session | the later day's minutes from the earlier clock to the later clock | 338 | 289 |
| same day, pre-market → in-session | 09:30 to the later clock, plus a `pre_market_possible` flag (no bars before 09:30) | 436 | 271 |
| next session, in-session → pre-market | the earlier day from its clock to the close, plus an `extended_hours_possible` flag | 318 | 490 |
| next session, in-session → in-session | the earlier day from its clock to the close, and the later day 09:30 to its clock | 64 | 81 |
| 2-5 sessions apart | the earlier day from its clock, every full session between, the later day to its clock | 353 | 395 |
| 6+ sessions apart | the same, daily resolution only (§3.5) | 248 | 261 |
| same day or next session, other clock pairs (pre-market → pre-market, in-session → after the close, …) | the full regular sessions `lo`..`hi` at minute resolution, flagged `bracket_other` (the clocks give no narrower rule); counted in the coverage printout | 70 | 36 |
| inverted | none (extended hours only) | 34 | 38 |

(n = 1,861 per side; the counts are the inventory's table in `data.md` §2.5; the `bracket_other` row is its two "other" rows — 31 + 73
buys, 35 + 39 sales — less the inverted windows they contain, 70 and 36, which had no reachable set in the first draft of this table;
each column now sums to 1,861.) **Reachable price range** = the lowest
low to the highest high over the reachable minutes (minute bars) or over the reachable sessions' daily lows and highs when minutes
are missing (flagged `daily_only`). **Pre-market:** the 436 buys and 271 sales whose earlier screenshot is before the open may have
been made before 09:30, where we have no bars (the fetcher stores 09:30-15:59 only); they carry `pre_market_possible` and are scored
separately in §4.2 R1, and §12 asks whether the minute pull should fetch extended hours for these sessions. **The panel's own price:** at the first screenshot showing the name, the row's `pct` is the stock's change
against the prior close at that clock. It is a second, independent reading of where price was when he was already holding: the range
is reported twice, once from the bars alone and once with the panel's price as an extra point, and the two are compared (the panel's
cell agreed with our daily bars on 34,355 of the 41,099 rows, 84%; a disagreement is flagged, never silently resolved).

**Layer B — chart-event points inside the reachable set.** A fixed list of price events that any trader sees on a plain chart with
no strategy attached. The test for inclusion: *could a person who has never heard of a trading rule point at it on the chart?* Each
point is (price, session, minute) plus the raw features of §3.4.

### 3.3 The candidate families — and why each is chart-observable, not a strategy

| family | the point | why it is on every chart | buys | sales |
|---|---|---|---|---|
| F1 open | the session's first print (minute 0 open) | the first price of the day | yes | yes |
| F2 opening-range high / low, k = 1, 5, 15, 30, 60 minutes | the high (and low) of the first k minutes, and the first later minute that trades through it | the first candle of any intraday chart at those lengths; a level the eye draws at once | both directions | both directions |
| F3 prior session's high, low, close | the level, and the first minute price crosses it inside the reachable set | yesterday's bar is the one every chart shows next to today; the close is the gap reference | both | both |
| F4 the session's own high and low | the extreme print and its minute (known in hindsight; a trader sees it as "the high of the day" as it forms) | the day's range | both | both |
| F5 intraday swing points | on 5-minute bars, a bar whose high is above the 3 bars either side (swing high) or whose low is below them (swing low); the point is the swing itself and the first minute it is traded through | "the last little high / low" on the intraday chart | both | both |
| F6 the close | the 15:59 print, and the 15:55 print (market-on-close) | the last price of the day | yes | yes |
| F7 recent-session highs and lows, 5, 10, 20, 60 sessions | the highest high / lowest low of the prior N sessions, and the first minute crossed | the daily chart's visible range at a glance (a week, two weeks, a month, a quarter) | both | both |
| F8 moving-average touches, 10-, 20-, 50-day simple, with a length sweep (5, 8, 10, 13, 20, 30, 50) printed beside | the first minute price touches the line, from above or below | a line drawn on most default charts | both | both |
| F9 the window's reachable-range ends | the lowest low and the highest high of the reachable set | not a point he chose; the two ends of the band (§4.3) | — | — |
| F10 round numbers | whole dollars, half dollars, and $5 / $10 multiples inside the reachable range, and the first minute each is crossed | the numbers a person says and types; where a spoken "about 42" lands | both | both |
| F11 the average traded price | the volume-weighted average price over the reachable minutes so far at each minute, and the first minute price crosses it | where most of the day's shares changed hands; where an unplanned fill most likely sits | both | both |

Notes written now so they are not re-argued later:
- **Some families are our old rule levels under chart names, and that is said here, not discovered later:** F2 at k = 5 is our
  opening-range entry and k = 60 our 60-minute chart; F7 at 20 and 60 sessions is a breakout level; F3's prior close is the EP gap
  reference; the F2 / F4 lows are our day-low stop; F8 at 10 and 20 days is our old exit line. They stay because a trader who has
  never heard of a rule still sees them on a plain chart, and leaving them out would let the list hide his point by construction.
  **What keeps them from pulling the read back toward our rules:** (1) no family is a pass bar in step 6 — step 6 tests the windows
  (§4.2), and "which points he acts at" is a step-7 DESCRIPTION with no bar (§5); (2) the family and direction tags are left out of
  step 7's grouping features, which use continuous chart measures only; (3) the families whose lengths are our settings (F2 k = 5 and
  60, F7 at 20 and 60, F8 at 10 and 20, and the §3.4 columns built on those lengths) carry a `our_length` flag, so step 7 is run with
  and without them and F8 is swept over seven lengths rather than read at ours; (4) the family tags come back at step 8 (§6), where
  they are the point.
- **Density check, in the dry run before anything is scored (F2 of the review):** for each family set (all families; without the
  `our_length` ones; F1 + F3 + F4 + F6 + F10 + F11 only) the median share of a side's reachable range that the candidates' tolerance
  (§4.2) covers is printed. **Above 60%, "where he acts" is marked NOT DECIDABLE for that set before any statement is read** — any
  price in the range sits near some point — and the tolerance is narrowed or the set thinned, decided then and recorded in the ledger.
- **Every family is used in BOTH directions on BOTH sides.** He sells into strength and buys on weakness as well as the reverse; the
  direction of the cross is a feature carried on the row (§3.4) for step 8, not a filter and not a step-7 input.
- **Every level is recomputed from bars.** Nothing is read from `adr20`, `pivot` or any (b) column; the 20-session average daily range
  used as a descriptor in §3.4 is computed from the daily export.
- Points that fall on the same minute are merged (one row, several family tags); a level never crossed inside the reachable set
  produces no point (a `not_reached` count per family is printed).
- Minute bars run 09:30-15:59 (the fetcher stores nothing else), so pre-market and after-hours points exist only as the flags of §3.2.

### 3.4 What each candidate carries — raw chart terms only

One row per (position, side, candidate). Columns, all computed from bars and the calendar:

| column | meaning |
|---|---|
| `price`, `date`, `minute` | the point; minute = minutes since 09:30 (blank when daily-only) |
| `family`, `direction`, `k`, `our_length` | F1-F11; crossed from below / from above / the level itself; the family's length (k minutes or N sessions); whether that length is one our old rules used (§3.3) — carried for step 8, not a step-7 input |
| `pos_in_day` | where the price sits in that day's full low-high range, 0 (the low) to 1 (the high) |
| `pos_in_day_so_far` | the same against the range formed up to that minute |
| `gap_pct` | the day's open against the prior close, in % |
| `range_pct`, `range_vs_avgrange20` | the day's high-low as % of price, and against the average of the prior 20 sessions' ranges (`our_length`) |
| `dist_prev_high`, `dist_prev_low`, `dist_prev_close` | % distance from the prior session's high, low, close |
| `dist_hi_N`, `dist_lo_N` for N = 3, 5, 10, 20, 40, 60 | % distance from the prior N sessions' highest high / lowest low (20 and 60 carry `our_length`) |
| `dist_ma_N` for N = 5, 8, 10, 13, 20, 30, 50 | % distance from the N-day simple moving average of prior closes (10 and 20 carry `our_length`) |
| `dist_round`, `dist_vwap` | % distance from the nearest round number (F10) and from the average traded price so far (F11) |
| `ret_N` for N = 3, 5, 10, 20, 40, 60 | the stock's % change over the prior N sessions |
| `vol_day_vs_20`, `vol_sofar_vs_20` | the day's volume, and the volume up to that minute, against the prior 20 sessions' average (`our_length`) |
| `vol_min_vs_median` | that minute's volume against the day's median minute (minute rows only) |
| `sessions_since_hi_N` for N = 5, 20, 60 | sessions since the N-session high (20 carries `our_length`) |
| `source` | `minute` / `daily_only` / `panel_pct` |

For the sale side the same columns are computed at the sale candidate, plus the trade-level columns `hold_sessions_min/max` (from
the two windows), and — only after step 6 chooses a matched entry — `result_pct` and `result_in_day_ranges` (the move divided by the
entry day's range). **No column is named for a setup, a pattern, a pivot or a rule.** Where a length is one of ours (20-session
range, 10/20-day averages, the 20- and 60-session highs) the column says so with `our_length`, and the length sweep beside it is what
step 7 reads first, so a group cannot rediscover our 10/20-day exit because 10 and 20 were the only lengths on offer.

### 3.5 How many points per trade, and the data each needs

| window shape | candidates per side (expected) | data needed |
|---|---|---|
| same-day bracket with minute bars (~30 minutes wide) | 5-15 after merging | minute bars of that day; 60 prior daily bars for the F7/F8 levels and features |
| one session, no bracket, minute bars | 15-30 | the same |
| one session, daily only | 6-10 (F1, F3 levels crossed that day, F4, F6, F7/F8 crossed that day) | daily bars only |
| 2-5 sessions | the one-session count × sessions | the same per session |
| 6+ sessions (n = 248 buys, 261 sales, mostly 2017-19 and late 2022-23) | daily-only, 6-10 per session, capped at the first and last 5 sessions plus every session's close | daily bars |
| inverted | 0 (flag only) | — |

Expected totals (a guess, scored at the report): about 30,000-55,000 candidate rows over the primary span (F10 and F11 add rows), a
median of about 14 per bracketed side and about 26 per unbracketed one-session side. **The number that matters is the density of
§3.3 (the share of the reachable range the points' tolerance covers), printed per family set in the dry run; it decides whether
"where he acts" can be read at all, before any statement is opened.**

### 3.6 What is missing, and the one thing that needs his say-so

- **Minute bars:** every session of the window has minute bars for 70% of buy windows and 60% of sale windows (76% / 65% of the
  one-session ones). 1,921 (symbol, session) pairs have a daily bar but no minute file; filling them is 486 requests, about four
  minutes, recorded as free by the 10-19 registration — but the fetcher needs the Alpaca data keys, which sit in the production
  container, so **running it is the operator's call** (§12). Step 5 runs on what is on disk first and prints coverage both ways; the
  daily-only fallback is scored separately in step 6 so the fetch's value is measured, not assumed. The minute holes are by quarter
  (2021Q3: 446 of 756 pairs; 2022Q1: no candidate-population tree), so without the pull the second half of 2021 is mostly daily-only.
- **Daily bars:** 340 windows (168 buy, 172 sale) have no daily bar on any session. Two known alias gaps (GSX → GOTU, SBE → CHPT) are
  fixed by extending the alias join from the lexicon's own rename evidence (a data join, no rule); funds and notes with no bars in our
  exports (GBTC, ETHE, FNGU, TVIX) and delisted names the export does not carry are listed by name and count, and excluded with the
  reason printed. The number recovered by the alias fix is printed (the inventory did not measure it).
- **Extended hours:** 34 buys and 38 sales happened outside 09:30-16:00 and cannot be placed on a bar today; a further 436 buys and
  271 sales MAY have (`pre_market_possible`, §3.2). The fetcher requests 09:30-16:00 only, but the same free endpoint returns
  04:00-20:00 minute bars when the request window is widened — a flag on `fetch_minutes.py` writing a separate `ext_asis/` tree,
  the same zero cost, run with the pull on his say-so (§12). Without it: counted, a candidate list of zero for the 72, and the 707
  scored separately in R1.
- **Not fetchable at any price:** his sizes, his side, adds and trims, and the trades opened and closed between two streams.

### 3.7 Outputs and the step-5 report

Files under `/Users/alvinfung/apollo_data/cb702/qm_streams/asis_1026/`: `candidates.tsv` (§3.4 rows), `ranges.tsv` (one row per
position per side: reachable minutes, the range from bars, the range with the panel price, the average traded price over the
reachable minutes, flags), `coverage.tsv` (per position: minute / daily-only / none, by side). Printout
`scripts/probes/_705_asis_1026/01_points.txt`: coverage by year and window shape, candidates per side by family, the density per
family set (§3.3), the `not_reached` counts, the alias recoveries, the excluded names. **The report to him is one screen:** coverage,
points per trade, the density verdict (readable / not decidable, per family set), the width of the reachable band (median % of
price), and the one decision (§12).

## 4. STEP 6 — check the reconstruction against his own words, then against his returns

### 4.1 (a) The caption reference — sized on the measured yield, with a blind second reader

**What the captions can give (inventory, 2020-2022, n = 7,607 candidate statements):** 14% (range 4-24%) name the stock, his own
action and the day — about 1,070 statements (320 to 1,820); 43% name stock and action with the day bounded only by the stream date
(about 3,250); 10% carry stock, action and a price (6% a clean number); when a number is given it is more often a share count or a
dollar result than a price. 24% of regex hits are not his own trade. The ticker is unidentifiable in 18% of his own events, mostly
garbles with a fixable pattern (TVIX heard as twix / tweaks; GUSH as gosh / cash; TQQQ as tqq / tq).

**Tiers, each with its use:**

| tier | content | expected n (from the yield) | what it checks in §4.2 |
|---|---|---|---|
| T1 price | stock + his own buy / sell / stop / partial / short / cover + the day + a stated price | 100-250 (about 20% of the ~1,070 dated statements carry a price; roughly half clean) | the price against the reachable range (R1) — the INDEPENDENT check; against the chart points only as a step-7 description |
| T1b result | stock + action + a share count AND a dollar result ("lost 180k on 20k shares") → an implied price move | 50-150 | the implied move against the trade's band |
| T2 day | stock + action + the day, no price | about 1,070 (n = 320-1,820) | the day-offset histogram (§4.2) — mostly NOT independent of the window |
| T3 bounded | stock + action, day only bounded by the stream date | about 3,250 | a weak bound: the window must not end before the stream day |
| T4 trade results | the 19 single-trade results of $200k or more | 19 | spot checks: the band's biggest winners and losers are where he says |
| account | the 133 account statements, of which 21 dated year-to-date figures | 133 / 21 | §4.3 |

**Procedure (every stage printed, nothing silent):**
1. **Machine pass** (reuse the inventory's `captions_inventory.py` regex and clustering, the duplicate-upload drop, and the 8 "Late upload"
   stream-date corrections): every first-person trade statement in the 485 unique streams, 2020-01 to 2022-06 primary. **Two
   statement kinds the inventory does not have are added first: `shorted` ("shorted / I'm short / short it / went short") and
   `covered` ("covered / I'm out of my short / bought back").** The inventory's kinds are stopped, sold, sold_part, added, bought,
   buy_now, profit, cost_stop and account — a short never reached its readers, so the inventory's 120 hand-read rows are re-scored
   through the widened search and the statements gained are printed as the recall change.
2. **Ticker search and alias list, built from the WHOLE market of that period, not from his held names.** The search set for a
   stream is every symbol the lexicon carries whose bar-file span covers the stream date (the lexicon stores each of its 22,744 symbols'
   first and last session in both daily exports), plus the funds and notes we hold no bars for (GBTC, ETHE, FNGU, TVIX, …).
   The alias list (spoken garbles: TVIX as twix / tweaks, GUSH as gosh / cash, TQQQ as tqq / tq) is built from the captions alone —
   a caption word within 30 s of a trade statement that is no English word and is one or two edits from a symbol in the search set
   — and an alias is accepted only on its caption evidence (the stretch it was heard in, listed), **never because that stock was on
   his screen that day and never from the bars.** Without this, a trade in a stock that never reached his panel could not be read
   and the invisible-trade count (step 6) would be held near zero by construction.
3. **Filter to the hand-read set:** a statement enters the hand-read set when a search-set symbol or alias is within ±30 s of it. The
   price tier adds: a number with "$", a decimal, "and a half / quarter", or "at <number>" within the cluster. Expected hand-read set:
   1,500-2,500 statements (the 43% with stock + action, before the day test), of which 300-600 are price-tier candidates. The filter's
   recall loss is stated, not guessed: the inventory's 120 hand-read rows are re-scored through the filter and the share of usable
   rows it drops is printed (expected under 10%). **Added, for the blind spot:** a seeded sample (seed 705) of 200 trade statements
   with NO search-set symbol within ±30 s — the statements the filter would otherwise never show a reader — is read blind alongside,
   to estimate the share of his own trades the symbol search cannot see at all.
4. **Reader 1** (Sonnet, no subagents, in batches — §8): labels each statement with the inventory's label sheet — ticker (Y / ambiguous
   / N, inferred flagged), his own trade (Y / advice / plan / viewer / other), action (buy, add, sell_part, sell_all, sell_unspec,
   stopped, **shorted, covered**), day pinned (stream_day / stated_earlier / implied_recent / approx_earlier / unstated), **side (long /
   short, when he says it)**, price (number, clean / garbled), shares, dollar result. Reads ±30 s of caption context, as the inventory
   did, **and nothing else: no holdings window, no bar, no panel** — a ticker or a price is resolved from the words alone, and a
   garbled price ("forty-two fifty" against "forty to fifty") stays `garbled` rather than being settled by looking at where the stock
   traded. The price-tier candidates are read FIRST (300-600 statements), which is enough to decide R1; the rest follow in batches.
   A short's appearance on the panel is its ENTRY and its disappearance its cover; the share of stated shorts per block is printed —
   the first rule-free measurement of how much of his trading was short (he said "20% long and 100% short" on 2021-02-18).
5. **Blind reader 2** (a second Sonnet card): 150 rows drawn with seed 705 — 100 from the price-tier candidates, 50 from the rest —
   labelled from the same sheet with NO sight of reader 1's labels, plus the 200-statement no-symbol sample of step 3 (read once, by
   reader 2 only, as the blind-spot estimate). **Agreement bar: ≥ 80% on the joint label (ticker, action, day class) and ≥ 85% on the
   price number where both read one.** Below the bar: the two readers' disagreements are listed, the sheet's wording is fixed, and
   BOTH re-read a fresh 150 (a disclosed event, once; a second failure stops step 6a and goes to him). The agreement numbers are
   printed in the report whatever they are.
6. **Join to a position — by symbol and day ONLY, never by the statement's action and never by price:** symbol (after alias) + the
   stated day; the statement takes the NEAREST window of EITHER side (buy or sale) whose span contains the day or lies within one
   session of it (he says "yesterday" on the next morning). A name with several positions takes the nearest window. Whether the
   statement's action agrees with the side of the window it landed on is then a MEASUREMENT (R5, §4.2), not a construction. Printed:
   the count of ambiguous joins; the count of statements with no position at all (**the invisible trades** — his own trade, named,
   dated, never on the panel); and beside it the count of own-trade statements whose ticker the readers could not identify, so the
   blind-spot figure is read with how far unreadable tickers could push it down.
7. **Before any trade is anchored (step 6b / 6c), the price-stated trades are printed beside the rest** on hold length, flicker share,
   result sign, bracket type and time of day of the window. He names a price when he chooses to — notable winners, stop-outs, live
   morning trades — and the stream ends at a median 10:40 ET, so the checked trades are a self-chosen, morning-heavy subset; the table
   says how far they are from the 1,848, and R1 is reported by bracket type for the same reason.

### 4.2 (b) The per-trade check — positive observables, bars, controls, WOULD-FAIL-IF

**Step 6 tests the WINDOWS (the reachable minutes and range of §3.2), not the point list.** The one readout with a pass bar is R1;
the others are printed with what the BROKEN reconstruction would show. "Which chart points he acts at" is NOT a step-6 readout any
more — the first draft scored it family by family against a random-price line, which is the rule-mix read's method with levels in
place of rules and would have looped the same way; it is a step-7 description (§5) and is decidable only if the dry-run density
check of §3.3 says so.

| readout | positive observable | bar (written now, with the reason) | controls | WOULD-FAIL-IF |
|---|---|---|---|---|
| **R1 containment** (T1, clean prices only) | share of stated fill prices that lie inside the trade's reachable range (bars-only range primary; with the panel price beside). Tolerance: inside if within max(1% of price, 10% of that session's range, $0.05) of the range edge — rounding and tick size, not a fit | **the real share minus the shifted-window share ≥ 25 points, AND the real share minus the cross-symbol share ≥ 25 points.** The raw share is printed but is not the bar: in a stock that barely moves a window off by a day still contains the price, so only the gap over a wrong window says the window is right. 25 points is the smallest gap the n (100-250 statements) tells from noise at this size (a 95% interval on a share near 70% is about ±9 points; the gap of two such shares is about ±13; 25 clears it with room) | **(a) shifted window:** the same stated prices against the SAME stock's reachable range shifted by −3, −2, −1, +1, +2, +3 sessions (the mean share is the control). **(b) cross-symbol:** the same statement against the window of ANOTHER name he held that same day (every other held name, the mean share), so a wrong symbol alias is tested, not only a wrong day | a window off by a day, a wrong symbol alias or a misread clock shows as a gap near zero over control (a) or (b); a raw share near the controls in every volatility band means containment cannot tell anything for that span, and the read says so |
| **R1 by bracket type** | the same, split by the §3.2 bracket types, with `pre_market_possible` brackets on their own line | no separate bar; printed because the checked trades are morning-heavy (step 7 of §4.1) and because a pre-market fill lands outside the 09:30-15:59 range by construction | the same controls per line | the pre-market line far below the others: the pull with extended hours (§12) is the fix, not a dropped trade |
| **R1 garbled** | the garbled-price statements (step 4 of §4.1) scored the same way, OUTSIDE the primary count | no bar; printed beside | the same | — |
| **R3 day offset** (T2) | histogram of (stated day − window start) and (stated day − window end) in sessions, split by the reader's day class (stream_day / stated_earlier / …) | no pass bar; the SHAPE is the readout: a peak at 0 and nothing systematic elsewhere | — (the stream date and the window come from the same screenshot session, so a high "inside" share is near-automatic and is printed as secondary only) | a peak at −1 session among `stream_day` statements means he talks about yesterday's trade the next morning and the reader's `stated_earlier` resolution is what is checked — a dating question for the readers, not a late window; a window is re-read only if statements whose day the reader RESOLVED still sit one session off; a spread wider than the windows means the caption dating is loose |
| **R4 implied move** (T1b) | share of implied moves (dollar result ÷ shares, as % of entry price) that fall inside the trade's band of outcomes | ≥ 70% (the band is wide; a miss means sizes or the trade identity are wrong) | — | the implied moves land outside the band more often than inside: the statement is about a different trade or the positions are merged |
| **R5 side agreement** | after the symbol-and-day join of §4.1 step 6 (which never looks at the action), the share of statements whose action agrees with the side of the window they landed on: stopped / sold / covered on a sale window, bought / added / shorted on a buy window | **≥ 90%.** It can now fail: a broken window set (sale windows a session late, two positions merged) puts a "sold" on the next buy window. 10% is left for his next-morning talk landing on an adjacent window of the other side; the disagreements are listed by day class | — | agreement near 50%: the windows or the join are wrong, and 6c is not read |

Every readout is printed for 2020 and for 2021-22 side by side, and with / without flickers, with / without `daily_only` sources.
**Consequence table, decided now:** R1 passes its gap bar on both controls → the windows are accepted at ballpark (his bar, 10-24:
*"We're not going to be exact, but we should be in the ballpark"*), and the trades whose stated price falls outside our range are
KEPT, anchored on the stated price (his words are the stronger evidence) and flagged `stated_outside_range` — never excluded, because
dropping the trades where his words disagree with the screen would be fitting him to the screen; R1 fails on either control → stop,
find the cause (window / alias / clock) in the listed failures by bracket type, fix, re-run once as a disclosed event; R5 under 90% →
the same; the density check (§3.3) says "where he acts" is not decidable → step 7 reads the band and the continuous chart measures
only, and the point description is dropped.

### 4.3 (c) "Reproduces his returns" — an account BAND against his stated numbers

**Per trade, three readings from the reachable minutes of §3.2 — NOT from the candidate list, so the reading does not carry the
choice of point families:** WORST (buy at the highest reachable price, sell at the lowest), BEST (the reverse), MIDDLE (the
volume-weighted average price over the reachable minutes — the price a trade placed somewhere in those minutes most likely got; the
daily-only fallback uses each reachable session's typical price, (high + low + close) / 3, weighted by the session's volume, flagged).
Where step 6b matched a clean stated price, that price replaces the middle reading for that side (the T1 trades are the anchors,
including the `stated_outside_range` ones; the rest are the band).

**Sizing — OUR convention, not his rule, stated once:** the panel never shows sizes. Middle arm: equal weight across the names held at
the same time, full account (exposure 1.0). Band arms: exposure 0.5 and 1.5 (he used margin; he also said 20% long / 100% short on
2021-02-18). The panel does not show the side: a position is read as SHORT when a T1/T2 statement says so, as long otherwise, and the
share read by statement is printed; the unknown-side remainder is the known bias and the reason the spread, not the middle reading, is
the claim (the short-heavy months of early 2021 are where this bites most, and the band is read there with that said). Flickers are
run both ways (in / out).

**Comparison:** the account path is compounded by session and read at the DATES of his year-to-date statements, which is a stronger
check than year-ends because the shape is checkable where the magnitude is not: 2020-06-09 (+150% or more), 07-20 (more than +200%),
11-19 (about +300%), 12-07 (+500-700%), 12-09 (+710%), 12-22 (+800-900%); 2021-02-09 (+60%), 02-18 (+60%), 02-23 (nearing +100%),
02-24 (+90%), 03-10 (+100-120%), 03-12 (+120%), 03-24 (+90-100% from a +130% peak), 05-06 (+100%); 2022-04-14 (+15%). Fifteen
dated points, n = 15.

**6c has NO pass bar, and this is said plainly rather than dressed as one.** The first draft barred it on "the worst-to-best band
contains his figure" — but best buys every trade at its low and sells at its high, worst the reverse, and compounded over about 800
trades a year at 0.5-1.5× the account that band runs from a wiped-out account to many thousands of percent, so it could not miss; and
"the middle within a factor of 3" accepted anything from about +240% to +2,100% for 2020. A control for the middle reading does not
exist either: a random price drawn from the reachable minutes weighted by volume has the volume-weighted average price as its
expectation, so "the middle against the random-price middle" compares a number to itself. **What is printed instead, as readouts:**
(1) the middle-reading account path at the 15 dated points, with his figure beside each; (2) the same path with the T1 anchors in
place of the middle on the anchored trades; (3) the same path on the shifted windows of R1 control (a) — if the real windows sit
closer to his figures than the shifted ones at most of the 15 points, the dates carry information, reported as a count, not a bar
(15 correlated points cannot support one); (4) the 2021 drawdown (03-12 → 03-24) as a shape readout — whether the middle path also
falls between those two dates; (5) the sizing arms and flicker arms as the spread.

**WOULD-FAIL-IF — and what it cannot tell:** a wrong reconstruction (days or prices off) and a correct-but-blind one (invisible
round trips in 29% of sessions, sizes unseen, shorts read as longs, 659 flickers that may be misreads) produce the SAME shortfall.
**So 6c is a floor, never a verify.** It is read with 6b: if 6b passes and 6c sits far under him, the panel's blind spots are the gap
and the next move is a count of the invisible trades from the captions (the two counts of §4.1 step 6 and the 200-statement blind
sample of step 3) — his decision; if 6b fails, 6c is not read at all. An account that misses him is NOT evidence against his
returns (audited, his standing rule of 10-23); it bounds what the panel can show.

## 5. STEP 7 — the shape only; registered in its own document after step 6 reports

Step 7 is not registered here. What is fixed now is what it may and may not use; the method is chosen after step 6 reports.

- **Unit of analysis:** the anchored entry and exit (the T1 trades, including `stated_outside_range`) and, separately, the middle
  reading of the unanchored trades. **The anchored and the unanchored trades are grouped SEPARATELY before any joint run**, because
  the anchored ones are the trades he chose to talk about (morning-heavy, winners and stop-outs — §4.1 step 7), and a group found
  among them is not carried into a type of trade (by bracket type, hold length, time of day) that has no checked trade in it.
- **Features: continuous chart measures only (§3.4) — NO family tag, NO direction tag.** A grouping on "family and direction of the
  point" would hand back our rule levels as groups by construction; the families return at step 8 as labels. Run with and without the
  `our_length` columns (the length sweep in their place), with and without flickers, 2020 and 2021-22 side by side.
- **"Where on the chart he acts" is a description printed with the groups, with no bar:** for the anchored trades, which families the
  stated price sits on, against a chance line drawn from the reachable minutes weighted by volume and rounded the way he speaks (to
  the nearest $0.50 under $100, the nearest dollar above — a uniform draw is not comparable, since real fills cluster where volume
  traded and spoken prices are round). Printed only for family sets the §3.3 density check marked readable.
- **Open questions that depend on step 6:** how the unanchored trades' uncertainty is carried (the band's width as a weight, or
  the middle alone); whether the day-offset shape (R3) re-dates any windows; whether flickers group on their own (then they are
  misreads or a distinct short-hold behaviour, and he decides which); whether daily-only trades can sit in the same groups as
  minute-resolved ones; the grouping method and how many charts per group are read by hand (decided in step 7's own registration).
- **What he gets:** the groups, each with its share of trades, its plain-words chart description, example charts, and the features
  that separate it. **Not a rule list.**

## 6. STEP 8 — where our rule library finally enters

Only after step 7's groups are named in plain words does our rule library (his stated rules in `operator_shared_notes.md` l.1941-2096
and the rules the four earlier reads tested) enter, and it enters as a LABEL applied to groups, not to trades: for each group, the
rule it most resembles, read four ways — **matched** (the group's typical point is the rule's point within its tolerance, and the
group's share is reported as that rule's share), **flexed** (the group is the rule with one parameter moved — a wider stop, a later
opening range, a different average — and the move is named), **broken** (the group is the rule's context with the rule's action NOT
taken, or the opposite action), and **no rule** (a group no rule in the library describes; it is described on its own terms and left
standing). The family and direction tags of §3.3-3.4, held out of step 7, are used here: a group's typical point is read against the
families (and the `our_length` flag says when a match is at one of our settings). The shares of the four classes are the result; what
to rebuild for Apollo from them is a separate, later design and his call.

## 7. Data and time split

- **Sealed:** nothing dated after 2024-12-31 is opened (asserted at every read, `MinuteStore.seal` and the daily loader's cut). The
  2025-26 data stays for #710, unchanged by this read.
- **2020 and 2021-22 are both already seen.** Every earlier read fit on 2020-01-27..2020-12-31 and checked on 2021-01-04..2022-06-14,
  so neither block is unseen for any rule. This read fits nothing (there is no parameter chosen by an outcome), so the question of
  an unseen block does not arise for steps 5 and 6: both blocks are read and printed side by side, and a difference between them is
  a finding about him (or the captions), not a test. Step 7's grouping is unsupervised; its stability is checked by running 2020 and
  2021-22 separately and reporting whether the same groups appear (a stability read, not a holdout).
- **The captions are dense only to mid-2021:** 82% of trading days covered 2020-01..2021-06, 23% after. So step 6's reference is a
  2020-to-mid-2021 reference; 2021-07..2022-06 is checked on whatever T1 statements exist there (printed with its own n), and the
  report says so rather than pooling.
- **The forward shadow and the one sealed 2025-26 test remain the only confirmatory reads.** This read changes no branch of either.

## 8. Cost — the whole path priced up front

| item | $ | my capacity (build / read sessions, tokens) | slot | his time |
|---|---|---|---|---|
| this registration | 0 | written (this session) | — | review, about 30 min; one decision |
| step 5 build + tests + dry run + run | 0 (no model calls; bars on disk) | 1 Fable build (~250k) + 1 Sonnet tests (~70k) | weekend 1 | 10 min on the report |
| the optional minute pull (+ extended hours) | 0 (recorded as free; SIP minute bars) | none (main loop, ~4-8 min, runs in the production container — his say-so, §12) | weekend 1 | the say-so |
| step 6a machine pass + widened kinds + market-wide alias list + filter | 0 | 1 Sonnet (~90k) | weekend 1 | none |
| step 6a reader 1, price-tier batch (300-600 statements × ~300 tokens of caption context and labels) | 0 | 1 Sonnet (~200k) — enough to decide R1 | weekend 2 | none |
| step 6a reader 1, the remaining 1,200-1,900 statements (~500k), in batches of ~500 (~150k each) | 0 | 3-4 Sonnet (~500k in all) | weekend 2 → 3 | none |
| step 6a blind reader 2 (150 rows + the 200-statement no-symbol sample) | 0 | 1 Sonnet (~110k) | weekend 2 | none |
| step 6b + 6c checks + the report | 0 | 1 Fable (~200k) | weekend 3 | 15 min; one decision |
| step 7 (registered after step 6; priced then) | 0 expected (no vision or model call proposed; if a chart-reading model call is ever proposed it is priced then and is his call) | ~2 sessions | later | 20 min; one decision |
| **total through step 6** | **$0** | **~10 sessions, ~1.4M tokens; three weekend slots (R1 is decidable after weekend 2)** | | **~1 hour + 2 decisions** |

The first draft priced reader 1 at ~150k; 1,500-2,500 statements with 30 s of captions either side is ~250 tokens of context plus
~50 of labels each, about 600-700k, so the read is batched and the price-tier batch goes first. No paid API call is proposed anywhere
in steps 5-7. The hand reads are Sonnet sessions (capacity, not dollars).

## 9. Expectations, written now (guesses to be scored at each report; a miss changes nothing by itself)

| step | expectation | if it holds | if it misses |
|---|---|---|---|
| 5 coverage | minute-resolved on about 70% of buy sides, 60% of sale sides without the pull; 90%+ with it | step 6 runs on both sources, scored separately | the daily-only share drives whether the pull is worth asking for |
| 5 band width | the reachable range is a median 5-8% of price for one-session windows, 2-4% for bracketed ones | the band is narrow enough for 6c to mean something | a wide band makes 6c uninformative; 6b carries the step |
| 5 points | median ~14 candidates per bracketed side, ~26 per one-session side; density (§3.3) 40-55% for the full family set and under 35% without the `our_length` ones | "where he acts" is readable for at least the thinner set | density over 60% on every set: the point description is marked not decidable before any statement is read; step 7 is the band and the continuous measures only |
| 6a yield | T1 100-250 statements, T1b ~100, T2 ~1,000; the market-wide alias list recovers a third of the unidentified tickers; shorts are 5-15% of stated trades in 2020 and 30-60% in Feb-Mar 2021; the no-symbol blind sample finds his own trade in 10-25% of its 200; readers agree ≥ 85% | the reference is big enough for R1 at the stated n | under 100 T1: R1's gap bar cannot be told from noise; the read reports the n and the bar is marked not decidable |
| 6b R1 | raw containment 80-90%; shifted-window control 40-60%; cross-symbol control 20-40%; gaps of 30+ and 45+ points; the pre-market line 15-25 points under the in-session lines | accepted at ballpark; the pre-market shortfall is the extended-hours pull's case | a gap under 25 on either control: a reconstruction error to find first, by bracket type |
| 6b R5 | side agreement 92-97%, the misses mostly `stream_day` statements on an adjacent window | the join and the windows hold | under 90%: a merged position or a late sale window to find first |
| 6b R3 | a peak at 0 sessions with a visible −1 shoulder among `stream_day` statements and none among `stated_earlier` ones | the one-session join tolerance stands | a −1 peak among RESOLVED-day statements: the windows are dated a day late and are re-read |
| 6c | 2020's middle path positive and large (over +200%) but under his +710-1000%; closer to his 15 dated figures than the shifted-window path at 10 or more of them; the 2021 drawdown present between 03-12 and 03-24 | the trades as seen carry the shape of his year; the shortfall is the blind spots' size | middle ≤ 0 for 2020 with 6b passing: the panel misses the money — the invisible-trade count becomes the question, his call |

## 10. Files, reuse, guards, tests

**Code (new, under `scripts/probes/_705_asis_1026/`):**
- `01_points.py` + `test_01_points.py` — step 5: windows → reachable sets → candidates → features; printout `01_points.txt`.
- `02_captions.py` + `test_02_captions.py` — step 6a: machine pass, alias list, filter, the reader sheets, the agreement score;
  printouts `02_captions.txt`, `02_agreement.txt`.
- `03_check.py` + `test_03_check.py` — step 6b: the symbol-and-day join, R1 with both controls, R3, R4, R5; printout `03_check.txt`.
- `04_band.py` + `test_04_band.py` — step 6c: the three readings from the reachable minutes, sizing arms, the dated readouts;
  printout `04_band.txt`.
- Shared `asis_common.py`: paths, the seal, the forbidden-folder guard, the identifier scan (below), `rng_for`, the byte-identical
  COPIES of every helper listed under "reused" below, and pins and ledger helpers called with THIS read's paths (the earlier helpers
  default to the intraday read's files and would pass on its dry run). **The step-5/6 modules import nothing from
  `_705_holdings_1024`, `_705_reverse_1024`, `_705_intraday_1025` or `_cb_backtest`.**

**Outputs** under `/Users/alvinfung/apollo_data/cb702/qm_streams/asis_1026/`: `candidates.tsv`, `ranges.tsv`, `coverage.tsv`,
`statements.tsv`, `statements_reader2.tsv`, `aliases.tsv`, `joins.tsv`, `check_r1_r5.tsv`, `band_by_session.tsv`, `band_at_dates.tsv`.
Inputs pinned by sha256 at the freeze (the four holdings TSVs — their pins are in `data.md`'s input table — the panel jsonl, the
calendar cache, the lexicon, the two daily exports' cut rows, the six minute-tree `_done.psv` logs, the 485 caption files via
`subs_list_sha`, this doc's body).

**Reused as they are (rule-free) — every one COPIED into `asis_common.py`, byte-identical, never imported.** The first draft
imported from three of these files and caught the hazard for one of them only: `01_timeline.py` runs `ex = _load_frozen()` at import
(the rule-laden replay module); `01_intra.py` runs `rev = _load_frozen_rev()` at import (l.108), which loads `01_rev.py`, which runs
`H = _load_holdings()` (l.97), which loads `02_replay.py`, which runs `ex = _load_frozen()` (l.72) and with it the execution-variants
module, the cb module, the runner and the sec module. A text scan of the step-5/6 source cannot see a rule module that arrives
through an import, so nothing is imported from these files: each named function is copied, and a test compares every copy to its
source line by line (`inspect.getsource`), so a drift in either direction fails the build.
- `_705_holdings_1024/01_timeline.py`: `Sessions`, `load_sessions` (the calendar), `load_snapshots`, `dedupe_uploads`, `full_flag`,
  `blip_fill`, `lookalike_pairs`, `timeline` / `build_timeline` (the reading rules of the inventory's §1.4 — reading rules, not trading
  rules), `load_lexicon`, `load_alias` (extended for the rename gaps), `panel_clocks`' clock reading (re-applied on every day, not on E).
- `_cb_backtest/runner.py`: `load_daily` (asserts the calendar and finite values), `read_minute_file`, `minute_bars_from_rows`.
- `_705_intraday_1025/01_intra.py`: `MinuteStore` (the per-file cache with the 2024-12-31 seal), `IdCache`, `fnum`, `rng_for` (needs
  only `SEED` and `zlib`), `session_end_minute`, `EARLY_CLOSE` (the 13:00 closes), `smas_for` (the averages — descriptors here, called
  with the swept lengths).
- `_705_reverse_1024/01_rev.py`: `bar_sym`, `covered_tree`, `minute_state`, `subs_list_sha`; the freeze / ledger / dry-run / pins helpers
  with explicit paths.
- `_705_asis_1026/inventory/captions_inventory.py`: `parse_vtt`, `load_videos`, `Video`, `find_matches`, `cluster`, the duplicate-upload
  drop, `show` for reading a stretch; the label sheet of `captions.md`. (This file imports nothing of ours; it may be imported.)
- `_cb_backtest/fetch_minutes.py` for the optional pull (one flag added for the extended-hours window; run by the main loop on his
  say-so; never imported by the step-5/6 modules).

**NOT reused, because each embeds a rule:** `01_timeline.py`'s `date_entry`, `events_in`, `load_breakouts`, `load_eps`, `his_calls`,
`control_rows`, `orh5_infeasible`, `WINDOW_CAP` / `decides`; `01_rev.py`'s `level_at`, `random_levels` (levels are rule levels), the
select / enter / stop / exit fits and `recs_for` (built around the buy day E); `01_intra.py`'s `intraday_levels`, `enter_score_trade`,
`shifted_control` (shifts around E), `stop_levels_intra`, `held_through_intra`, `exit_walk_intra`, `prior_low`, `h60_bars`,
`ema_series`, `armed_index`, `ema_is_thin`, `BarGuard` (its horizon is the fit window; nothing is fitted here), `trees_for` (its
order was fixed for a gate); `01_mix.py` entirely; `stream_moments.tsv`'s `w_*` / `kw_*` columns; `control.tsv`; `graded_moments.tsv`.

**Guards:** (1) the seal — every daily and minute read asserts date ≤ 2024-12-31; (2) the forbidden folders — the module refuses to
open any path under the seven outcome folders (the earlier `FORBIDDEN_DIRS` covered two; this read's guard lists all seven and is
tested); (3) the identifier scan — the step-5/6 modules may not contain any of the excluded column or function names of §3.1 as a
WHOLE identifier or a whole string literal, matched with Python's `tokenize` (not as a substring: `era` sits inside `average` and
`operator`, `setup` inside `setup_paths`, `D` inside every identifier, and the first draft's own column `range_vs_adr20` would have
failed on `adr20` — renamed `range_vs_avgrange20`); **plus the import test** — a test imports each step-5/6 module in a fresh
interpreter and fails if `sys.modules` then holds any module loaded from `_705_holdings_1024`, `_705_reverse_1024`,
`_705_intraday_1025`, `_cb_backtest` or the execution-variants, cb, runner or sec modules; (4) no network — the modules import
nothing that opens a socket, and the fetcher is never imported;
(5) no paid call — no model client imported; (6) one calendar per record — every session offset is a bisect on the record's own
export calendar; (7) seeded draws only through `rng_for` with a named key; (8) the reader cards spawn no subagents and read only the
caption stretch and the label sheet.

**Tests:** synthetic minute days with known opens, k-minute highs, prior-day levels, swings and closes → the candidate generator
returns exactly the hand-listed points with the right minutes and directions; a same-day bracket narrows the reachable set
correctly for every bracket type of §3.2; daily-only fallback on a day with no minutes; the alias extension recovers a renamed
symbol from a fixture lexicon; the agreement scorer on fixture labels; R1-R5 on fixture statements with a known answer, including a
deliberately shifted window and a deliberately swapped symbol that must each fail R1's gap bar; a join fixture where a "sold"
statement lands on a buy window and R5 must count it as a miss; the band's three readings (the volume-weighted middle on a fixture
with known volume) and the dated readouts on a two-trade fixture; the seal and the forbidden-folder guard each raise; the identifier
scan fails on a planted forbidden name and passes on `average`; the import test fails on a planted `import` of `01_intra`; every
copied helper matches its source. Synthetic fixtures cannot catch
real-data crashes (10-24's lesson), so the first real run is planned as a possible crash-fix-rerun, disclosed in the ledger.

## 11. What this does not answer

- **Which candidate he actually used** on a trade with no stated price — step 5 bounds it (the reachable range and its middle) and
  step 7 groups it; nothing resolves it. "Where on the chart he acts" is read on the anchored trades only, as a description.
- **His sizes, his side, adds and trims, and the trades between two streams.** 6c is a floor for this reason; the invisible-trade
  counts of §4.1 (no position; ticker unreadable; the 200-statement blind sample) are the first measurement of the gap, not its
  closure.
- **Whether the trades he named a price for stand for the rest** — they are the ones he chose to talk about; §4.1 step 7 prints how
  far they sit from the 1,848 and step 7 keeps them apart, but the unanchored trades are never checked against his words.
- **Whether a stated price is a fill or a level** ("my stop is 40" is a level; "I sold at 40" is a fill) — the reader labels the
  kind; only fills enter R1; levels are kept beside for step 8.
- **Anything about rules** — no rule is named, matched or rejected before step 8; a group at step 7 is a description, not a rule.
- **2021-07 to 2022-06 with the same confidence as 2020** — the captions cover 23% of those days; the n is printed and it is not pooled.
- **Extended-hours trades** (34 buys, 38 sales) — no bars, no candidates.
- **Funds and notes with no bars in our exports** (GBTC, ETHE, FNGU, TVIX and the delisted names) — listed and excluded.
- **Stability beyond 2020 vs 2021-22** — both are already seen by the earlier reads; the forward shadow and the sealed 2025-26 test are
  the only confirmatory reads, and this read is not one.

## 12. Decisions

**His (one):** run the free minute-bar pull (1,921 symbol-days, 486 requests, Alpaca SIP, no charge recorded; with the extended-hours
window added, about twice the requests, still free — it is what can place the 707 possible pre-market trades and the 72 known
extended-hours ones) on the production container BEFORE step 5, or run step 5 on what is on disk first (70% / 60% minute coverage) and
decide after seeing the daily-only share? **Rec:** run step 5 on disk first — it costs nothing, it measures what the pull would add,
and the pull (with extended hours) can follow in the after-hours deploy window without a deploy.

**Mine, decided here (no money, not THE LINE; listed so they are not re-argued):** flickers kept and flagged, never dropped; trades
whose stated price falls outside our range kept and anchored on the stated price, never dropped; the old-rule-level families kept,
flagged `our_length`, held out of step 7's features and read with and without; both directions on both sides for every family; the
price tolerance and the 25-point gap bar of §4.2; the 60% density line of §3.3; the symbol-and-day join (never by action or price);
the sizing convention of §4.3 as OUR assumption and 6c without a pass bar; equal treatment of 2020 and 2021-22 (both seen); the
reader agreement bar of 80% / 85%; the readers see captions only; step 7 registered after step 6 reports, with steps 5 and 6 frozen
together after the dry run; the one-session join tolerance in §4.1 step 6.

## 13. Revisions before the freeze (2026-10-26)

| source | finding | change |
|---|---|---|
| advisor, first pass | the T2 day check is near-tautological (same screenshot session) | §4.2 R3: the offset histogram is the readout, the inside share secondary; T1b and T4 added as independent references |
| advisor, first pass | the panel's `% change` cell is rule-free and measured but was unused | §3.2: a second reachable range with the panel price; compared, disagreements flagged |
| advisor, first pass | 6c cannot discriminate a wrong reconstruction from a blind one | §0 and §4.3: 6c is a bound; the dated year-to-date path and the sizing convention stated; read only with 6b |
| advisor, first pass | 6a needed the reading procedure, the filter's recall loss, the second reader's scope; the forbidden-folder guard covered two folders of seven | §4.1 steps 1-6; §10 guard (2) |
| advisor, first pass | F8 is the family nearest a rule; `adr20` is a (b) column | §3.3 notes: F8 kept and flagged, the control is the fix; every level recomputed from bars |
| advisor, first pass | plain words throughout, not only §0 | §2's term table; plain terms used after it |
| advisor, final pass | short / cover absent; the 84% pair misquoted; 14 vs 15 dated points; T1 n misaligned; module-scan and import-chain hazards | §4.1 step 4 and R5: short / cover actions and side; §4.3 side by statement; §3.2 34,355 of 41,099; 02-23 and 02-24 split; §9 T1 100-250; §10 scan on names not letters, rule-free functions copied not imported |
| review, F1 (high) | the import chain still brought the rule library in: `01_intra.py` loads the frozen reverse read at import, which loads `01_rev.py` → `02_replay.py` → the execution-variants, cb, runner and sec modules; the text scan cannot see a transitive import | §10: every reused helper copied into `asis_common.py` (byte-identical, tested against its source); an import test fails the build if any of those modules is in `sys.modules`; the "carries no rule module" sentence corrected |
| review, F2 (high) | the per-family hit test (R2) was the rule-mix read's method with levels in place of rules; ~22 points with tolerance would cover most of the range, the random control would score as high, and the plan would fall back to a new read — the same loop | §4.2: step 6 tests the windows only (R1 and controls, 6c readouts); "where he acts" moved to step 7 as a description with no bar (§5); a density check per family set in the dry run, not decidable above 60%; family and direction tags out of step 7's features, back at step 8 (§3.3, §5, §6) |
| review, F3 (high) | the invisible-trade count was held near zero by construction: aliases from held names only, the hand-read filter on held names only | §4.1 steps 2-3, 6: the search set is every lexicon symbol live on the stream date; a seeded 200-statement no-symbol sample read blind; the unidentified-ticker count printed beside the no-position count |
| review, F4 (high) | R5 always passed — the join sent buys to buy windows and sells to sale windows, then R5 checked that | §4.1 step 6: join by symbol and day only, nearest window of either side; §4.2 R5 measures whether the action agrees with the side it landed on, bar ≥ 90% |
| review, F5 (high) | the worst-to-best band could not miss his figure; "within a factor of 3" accepted +240% to +2,100% for 2020; the middle (median candidate) carried the family choices | §4.3: the middle is the volume-weighted average price over the reachable minutes (not the candidate list); the containment bar dropped; no pass bar for 6c, stated plainly — the random-price middle equals the VWAP in expectation, so it is no control; the shifted-window path printed as a readout |
| review, F6 (medium) | R1 barred on raw containment, not the gap over control; no wrong-symbol control; R2's uniform random prices not comparable to round spoken fills | §4.2 R1: bar = gap ≥ 25 points over the shifted-window control AND over a new cross-symbol control (another held name's window, same day); §5: the chance line drawn from volume-weighted minutes, rounded to $0.50 / $1 |
| review, F7 (medium) | the price-stated trades are a self-chosen, morning-heavy subset; anchoring them and grouping them with the rest would carry their groups into all 1,848 | §4.1 step 7: the price-stated trades printed beside the rest on hold length, flicker share, result sign, bracket type, time of day; R1 by bracket type; §5: anchored and unanchored grouped separately, no group carried into a trade type with no checked trade; §11 |
| review, F8 (medium) | trades whose stated price missed our range were to be excluded from step 7 — fitting him to the screen; 436 buys may be pre-market, where we have no bars | §4.2 consequence: those trades kept, anchored on the stated price, flagged; `pre_market_possible` brackets scored on their own R1 line; §3.2, §3.6, §12: the fetcher can return 04:00-20:00 bars with a widened request window — one flag, free, offered with the pull |
| review, F9 (medium) | the inventory has no `short` / `cover` statement kind, so the "share of stated shorts" could never be measured | §4.1 step 1: `shorted` and `covered` kinds added to the search; the 120 inventory rows re-scored through it and the recall gain printed; step 4's action list carries both |
| review, F10 (medium) | the bracket table covered 1,791 buys / 1,825 sales; the inventory's "other" rows (31 + 73 buys, 35 + 39 sales, of which 34 / 38 are the inverted windows) left 70 buys / 36 sales with no reachable set | §3.2: a `bracket_other` row (70 / 36; both columns sum to 1,861) — the full sessions `lo`..`hi` at minute resolution, counted in the coverage printout |
| review, F11 (medium) | `range_vs_adr20` contained the banned string; `era` / `D` / `setup` as substrings match ordinary words; the 10/20/50 and 20-session lengths are our settings, so step 7 could rediscover the 10/20-day exit; no round-number or VWAP points | §3.4: renamed `range_vs_avgrange20`; §10: the scan matches whole identifiers and string literals via `tokenize`; §3.3-3.4: `our_length` flag, a length sweep (3-60 sessions; 5-50 days), step 7 run with and without; F10 round numbers and F11 the average traded price added as families |
| review, F12 (medium) | reader 1 priced ~4× too low (~150k vs ~600-700k for 1,500-2,500 statements with context) | §8: reader 1 at ~700k, batched; the price-tier batch (~200k) first because it decides R1; total through step 6 ~1.4M tokens over three weekend slots; §0 updated |
| review, F13 (low) | a mis-heard ticker or a garbled price could be resolved by looking at the screen or the bars — a check built to succeed | §4.1 steps 2 and 4: aliases accepted on caption evidence only, never the holdings windows or the bars; garbled prices stay garbled and are scored outside the primary R1 count (§4.2 "R1 garbled") |
| review, F14 (low) | a −1 peak in the day-offset chart was to re-read the windows, but it means he talks about yesterday's trade next morning — a reader dating question | §4.2 R3 and §9: a −1 peak among `stream_day` statements checks the reader's `stated_earlier` resolution; windows are re-read only if resolved-day statements still sit one session off |
| review, F15 (low) | step 7's method was over-specified before step 6 reported, and the plan had three freezes | §5 cut to what step 7 may and may not use plus open questions; steps 5 and 6 frozen together after the dry run (one review cycle); the Freeze record paragraph updated |
| review, F16 (low) | leftover jargon in §0 ("agent cards", "offset chart", "BOUND", "census", "against chance"); "fills 30% of the windows" vague; the first-minutes' high is our old opening-range entry and it was not said | §0 rewritten in plain words; the pull's effect given as 70% / 60% → about 90% of windows; one bullet names which points overlap our old rule levels and why they stay |
| review, F17 | the doc checker passed | none |
| operator 2026-10-26 ("Ok", after the main loop's summary of steps 5-8, the choices of §12 and the one decision) | the plan and the main loop's choices approved; the decision of §12 | the minute pull runs AFTER step 5 (the rec); step 5 builds and runs this week on the data on disk (capacity reset 10-26) |
| step-5 build review F2 (high), main loop 2026-10-26 | the daily and minute bars are split-adjusted to 2026, so 358 of 1,298 in-span buy windows (28%) sat more than 2% from the prices he saw (NVDA Oct-2020 13.48-13.75 against $541; SBE reads CHPT's 2025 reverse split) — his spoken prices would miss by construction | two inputs added and pinned (`cb702_pre_v2/daily_raw_close.csv.gz`, `cb702/cb702_splits.psv`, cut at the seal): a per-session factor raw ÷ the record's own export close; every bar-space column kept, raw columns added (`price_raw`, `range_lo_raw` / `range_hi_raw`, `avg_traded_price_raw`, `panel_price_raw`); round numbers and their tolerance read the RAW price; three names absent from the raw file (FSR, PROG, RSX) take factor 1.0, printed (module R12 / R31) |
| step-5 build review F3 | the band ends (F9) were emitted as each day's range ends, not the window's | F9 is not a candidate family; the band ends stay in `ranges.tsv` (module R33) |
| step-5 build (R28 / R32) | the inventory's 'other' / '6+' split (and F10's 70 / 36 above) differs from the measured one by 6 buys / 5 sales, all outside 2020-01..2022-06 (2017-19 Sunday frames, pre→pre pairs) | the in-span per-bracket counts are the claims (exact); in-span `bracket_other` 62 buys / 35 sales; the all-years split printed as a readout |
| step-5 dry run, main loop 2026-10-26 | the density check reads 100% on all three family sets at the §4.2 tolerance (round numbers every $0.50 and a 1%-of-price tolerance cover any band on a stock above ~$25) | per §9's consequence, written before the run: "where he acts" is NOT DECIDABLE — step 7 reads the band and the continuous chart measures, and the point description is dropped. The narrowed readouts (without round numbers at ½ tolerance 0.598, at ¼ 0.389) are printed beside and NOT acted on: picking a tolerance after seeing the density would be a fit |
| main loop 2026-10-26, the freeze | the step-5 module's run gate needs this doc frozen before `--run` | the doc body (steps 5-8, every bar of §4.2-4.3) freezes NOW, before any statement is read or any check runs; step 6's modules and dry run are pinned below the marker when they are built (pins below the marker do not change the body), so steps 5 and 6 still share one frozen text |

<!-- FREEZE -->
## Freeze record

Empty until the freeze. After his go: the main loop freezes this doc (`doc_body` pinned), copies the step-5 and step-6 modules beside
their pins, runs the step-5 `--dry-run` (coverage, the candidate families and the density per family set printed, no candidate
scored, no statement read), runs `--pins`, pastes every pin below, then runs step 5 once and step 6 in its batches. **Steps 5 and 6
are frozen together here** (the first draft froze them separately; step 6's design does not depend on step 5's numbers except the
density check, which the dry run prints before the freeze); step 7 is registered in its own document after step 6 reports. Nothing
above the marker is edited after the freeze; any edit changes `doc_body` and the run refuses.

### FREEZE 2026-10-26 (step 5; the doc body is frozen for steps 5-8)

Frozen after his "Ok" (§13). Step 5's dry run: 49 claims, 49 OK, 0 MISMATCH. Step 6's modules and dry run are pinned below when built; pins appended below the marker do not change `doc_body`.

### Pins (step 5)

- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- splits_B: 3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- asis_common.py: 90197bef2a329b2661d831781b4701b52a3786de311c8b4e4ceb199f80b39104
- 01_points.py: 3537f72ca1a3e6265fe01fc8e5536d6cfc32316f1aab7174edd779af2111d3bf
- forbidden_identifiers.txt: ba8f4bb5f23f2325b6e1ed78e299d2044d3182313955f4509b1e16969e3ff81c
- dryrun_printout: 9445be53e0c35cde4a383ac7110895527c9d66f9ac11ec29ebd09792fc2b2965
- run_printout: ABSENT
- ledger: ABSENT
- doc_body: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0

### RE-RUN 1 of step 5 — the minute pull (his "Yes", 2026-10-26; regular hours only, his note "he doesn't buy premarket")

Disclosed event: 1,721 missing (session, symbol) pairs fetched (1,366 ok, 355 empty; `00_fetch_list.py`, `fetch_list_asis_1026.tsv`) into a new tree `ASIS`, read LAST so no covered pair changes tree; every dry-run claim stays computed on the six pre-pull trees and the post-pull coverage prints beside (buys 70.4% → 88.8%, sales 60.5% → 88.3% of in-span windows with minute bars on every session); run 1's outputs archived as `*_run1` with ledger rows. Dry run 49 / 49 OK.

#### Pins (step 5, re-run 1)

- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- done_ASIS: b18dea5e0e75d64991c1c0de366c7deee65d9488ebd921a6b26b37994ba598e1
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- splits_B: 3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- asis_common.py: 89116c1ab9dc7aa2592737747884772776a3be8e9e58d113cebb42eab1b75f6b
- 01_points.py: 0864c933d7e8364d3002053a92fcf1b9fdd4751ff110f14cdbe272374e0e651e
- forbidden_identifiers.txt: ba8f4bb5f23f2325b6e1ed78e299d2044d3182313955f4509b1e16969e3ff81c
- dryrun_printout: 35232be6a47bc23c5e5e9a0e5987760193bb02ab7ae5446316dc192b170ef452
- run_printout: ABSENT
- ledger: dc0971a82e7e057830a1e4d76d7ad4fb9e04f7b614e9b01a28774aba87ac328a
- doc_body: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0

### Step 6a — the caption machine pass (`02_captions.py`), pinned before any sheet is drawn

Dry run 24 / 24 OK. Reading order (main loop, 2026-10-26; capacity, not a criterion): reader 1 reads the T1 price batch (434 statements) first — it alone decides R1 — and the blind reader 2 its 150 + 200 rows; the remaining strata wait for R1's result. Tickers are resolved by the readers from the captions; the machine's tied symbols (e.g. 'tesla' → TSLA / TELA) decide only the reading order.

#### Pins (step 6a)

- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- done_ASIS: b18dea5e0e75d64991c1c0de366c7deee65d9488ebd921a6b26b37994ba598e1
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- splits_B: 3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- asis_common.py: 89116c1ab9dc7aa2592737747884772776a3be8e9e58d113cebb42eab1b75f6b
- 01_points.py: 0864c933d7e8364d3002053a92fcf1b9fdd4751ff110f14cdbe272374e0e651e
- forbidden_identifiers.txt: ba8f4bb5f23f2325b6e1ed78e299d2044d3182313955f4509b1e16969e3ff81c
- doc_body: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0
- 02_captions.py: 40e5df6fbd5b069f38eb4b5a1b40c22f2ab8a25f697ecb807b0fc31e7759d308
- captions_inventory.py: 23eaf3dae1cf68b87dfa70c6cda05a011b5af923a9a9dc01a82585afe81e0f08
- video_status: 9f7a7e4cb1fd8ae5eb69a4daa4eb9eec7f9e969341249d41ffa469cb1bf9c692
- caption_sample: c8bef564780f39bca8698e9d6f7290c5b0a38564530d944da595ea35e3aa0bb4
- account_statements: 30474545b6e017cc25a72e3189d249b301d84052abaeba844780ad60d85926ad
- dict_web2: be41ad97963bf8dabedd5871d5d691596175269d540956b0f9965a885c2bbab9
- dict_web2a: 9313e251fee3e56204db2b284346d61c3a80ce613d7a077c5674f15f9cb33ab3
- dict_connectives: 5d2e495b5b12226bc89802ac6ebfabfc7fe1b0b374b2bfa19eb50145d5ccff76
- dryrun6a_printout: 31f2dabb2f684340aacc9394c2fb6e23086dc34645d3345d03c6c1c65ec2a5a4

### Step 6a agreement — first test BELOW the bar, and the plan's one re-test (2026-10-26, disclosed)

- **First test** (`02_agreement.txt`): reader 1 (the 434 priced statements) vs the blind reader 2 on the 100 shared rows — joint label 67% (bar 80%), the price number 89% where both read one (bar 85%, PASS). The 33 disagreements: ticker identified vs not 21, 'today' vs 'live position, no day word' 17, action 4. Before scoring, reader 2 and reader 1's batch 3 were RE-READ in private folders because the first readers shared a scratch folder (14 shared statements could have been seen; the first outputs are kept in `sheets_filled/_contaminated_1026/`).
- **The re-test, as §4.1 step 5 prescribes (once):** the wording fixed on those labels (`reader_wording_v1.txt` → `reader_wording_v2.txt`: ticker_ident judged by 'would a second reader write the same symbol from these words', stream_day only on a said 'today' word, sell_all only on a said 'all'); a FRESH 150 neither reader saw (100 priced + 50 other, the first 150 excluded, keys `asis_6a_reread_*`; `02b_fresh150.py` → `sheets/reread_150.tsv`); two NEW independent readers. A second miss stops step 6a and goes to him.

#### Pins (the re-test)

- reread_draw: 8e2ca858f23c5f9e692b6e691ab27c0b7c3f53edc4f95c6fa727b3ffd823634c
- reread_sheet: 184d3a455dc6f1e4b8f3c4e197b798ab819abbb7d5a1653a2d9658886857d5e7
- reader_wording_v1: 51a1b516e73fbcb33a21fac3db1cd5932fdb65e8b2284a19d91b590890fd1a68
- reader_wording_v2: 84a939c93d5ee9c1a693e55eddbcebb8db46c0b11dd610a7bc688118cbbc8510

- **Re-test RESULT** (`02_agreement_retest.txt`; the first test's printout kept as `02_agreement_test1.txt`): two new readers on the fresh 150 under wording v2 — joint label 121 / 150 = 80.7% (bar 80%) PASS, narrowly; the price number 34 / 39 = 87.2% (bar 85%) PASS. Step 6a continues.
- **Reading (main loop, the stricter one):** the agreement validates the v2 wording, so the price batch that feeds R1 is RE-LABELLED under v2 (reader 1's 434 rows, three batches, private folders) before R1 runs; the v1 labels are kept beside, never mixed.
- **The price batch re-labelled under v2** (three readers, private folders; the v1 labels kept in `sheets_filled/_v1_wording/`): 434 rows, every data column identical to the sheet; his own trade with the ticker identified and a price stated: **102** (the R1 input — inside the plan's 100-250, at its low end); with any ticker reading incl. `amb`: 174. One reader filled price fields on rows that are not his own trade; R1 reads his own trades only, so this changes nothing.

#### Pins (the v2 price batch)

- reader1_t1_v2_part1: 62c27b319e6fd2d9f1e81fafdeabfe5146401036fb33f998dff67737d5a6444a
- reader1_t1_v2_part2: 42473ba3f0cb8b8eb9a4de0f1f20a5763126538003139e6a9950a5fbcfae9fe3
- reader1_t1_v2_part3: c0de450d9af7a1a5cf6e2097a03adc2109e7ef7834ec30b1915fe65e74085905
- reread_150_A: 41b449d6e4226dbf53508658b1197df24f8bc2a34fdfa70082314f54111238c2
- reread_150_B: 0d606f37db021748744331cdd9a8504ea87e9ef50d99c241136b433c0c373259
- **What the v2 wording did to R1's input (disclosed):** his own trade + ticker identified + price stated reads 116 under v1 and 102 under v2 (91 in both, 25 v1-only, 11 v2-only); with any ticker reading 185 vs 174. The stricter ticker test moved 14 statements out of R1 — a smaller n, not a different bar. The re-test's pass margin, plainly: 121 of 150, two rows above the 80% line (120).

### Step 6b — built, reviewed, and the R1 floor read BEFORE the run (2026-10-27)

- **Built** (`asis_check_common.py`, `03_check.py`, `04_band.py`, `tests/test_asis_check.py`; Fable build, Opus review 9 findings all applied, Fable fix). Dry runs: 6b 12/12 OK, 6c 8/8 OK. No R1 number has been computed.
- **The floor, read on the SCORED n (the stricter reading, review F1):** of the 102 R1-input statements the join places 33 uniquely, 14 tie (9 one position's buy and sale), 29 sit mid-hold, 20 on another date, 6 never on the panel; the primary (a clean fill whose kind matches the action's side, on a named day, uniquely joined to a window with a range) is **11 < the §9 floor of 100** → R1's gap bar will read NOT DECIDABLE.
- **The fork, measured before any price was compared** (`fork/count_heldjoin.py` → `fork/count_heldjoin.out`; labels and window existence only): a HELD-POSITION join (a statement made during a hold → that position's window on the action's side) would raise the primary to 21 (named day) or 29 (any day class) — still far under the floor and under the ~35 at which an amendment was worth a re-freeze. **Decision (main loop, the registered default, no amendment):** 6b runs AS REGISTERED; R1 reads NOT DECIDABLE (his spoken prices are too sparse for a per-trade check); R5 (side agreement, 66 statements, bar 90%) and R3 are the readable parts; 6c runs only if 6b's gates allow it (R79).

#### Pins (step 6b)

- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- done_ASIS: b18dea5e0e75d64991c1c0de366c7deee65d9488ebd921a6b26b37994ba598e1
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- splits_B: 3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- asis_common.py: 89116c1ab9dc7aa2592737747884772776a3be8e9e58d113cebb42eab1b75f6b
- 01_points.py: 0864c933d7e8364d3002053a92fcf1b9fdd4751ff110f14cdbe272374e0e651e
- forbidden_identifiers.txt: ba8f4bb5f23f2325b6e1ed78e299d2044d3182313955f4509b1e16969e3ff81c
- doc_body: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0
- 02_captions.py: 40e5df6fbd5b069f38eb4b5a1b40c22f2ab8a25f697ecb807b0fc31e7759d308
- captions_inventory.py: 23eaf3dae1cf68b87dfa70c6cda05a011b5af923a9a9dc01a82585afe81e0f08
- reader1_t1_v2_part1: 62c27b319e6fd2d9f1e81fafdeabfe5146401036fb33f998dff67737d5a6444a
- reader1_t1_v2_part2: 42473ba3f0cb8b8eb9a4de0f1f20a5763126538003139e6a9950a5fbcfae9fe3
- reader1_t1_v2_part3: c0de450d9af7a1a5cf6e2097a03adc2109e7ef7834ec30b1915fe65e74085905
- reader_wording_v2: 84a939c93d5ee9c1a693e55eddbcebb8db46c0b11dd610a7bc688118cbbc8510
- candidates: 37c3c96cc6f16697b48a13224197f7f7c1303ee667c579158408e9f7865fc0f0
- ranges: 85efdf138f9d103ee805858f5acf8b9f51a5bc4f5164d8bbdfc2542b1378833b
- coverage: e304d2d67f991115be6ec8c5ce497b48170996da4f6a23e9fecf4b68d52fb10e
- joins_6a: 00a1108d16b18f14c410a22fb74201846a1dee02c95f148df21e0505eadb18ad
- asis_check_common.py: d80220da0d3cb02b0c4205d9ce8341dd2b0c562b650db6093418ad57cc2f4fc1
- 03_check.py: 0a4314131a6d0fe40f4d3345d95920f65025ca94d28bd28313a063ad336058f8
- dryrun6b_printout: 99f07613f2569ae7ced6c23881c5806ae55475300935431dba8aaac0b76ca822
