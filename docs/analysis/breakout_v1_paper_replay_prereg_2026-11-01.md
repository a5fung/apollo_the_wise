# Breakout v1 — the PAPER BASELINE replay, 2017-01-03 .. 2024-12-31 — pre-registration (2026-11-01)

**Status: REGISTERED, NOT RUN.** The nightly population (a pre-outcome count), the minute coverage and the two data
requests are computed and pasted below; **no entry, exit or R has been read** on the registered population. A three-day
smoke run (§10, dates named) checked that the code walks real bars without crashing; its rows carry no R column and its
tally no price outcome. The outcome walk (`walk`) runs ONCE, after the two pulls land, the pre-pull commit is made and
the footer is pasted, and refuses otherwise. Offline research, $0, no live change, nothing dated 2025-01-01 or later
opened or hashed (THE LINE; #710's seal). **This document recommends nothing about live money.**

**Revision 2 (2026-11-01, after the adversarial review; nothing has been run):** the review's eight findings and the
LOWs are built in — the same-ticker guard, the lane's safeguards, the slot freed at an open mark's last bar, the
adverse fill-minute row, the raw-close pull for the split-list-only tickers, the calibration on real fill months, the
smoke rows without R, the re-implemented rules pinned and asserted equal, the sealed tree hash, the decisive cutoff on
E, the coverage rule for unfetchable pairs, the two-stage freeze. Each is named where it lives.

Code: `scripts/probes/_breakout_v1_replay_1101/v1_replay.py` (stages `population | request | parity | dryrun | pins
| coverage | walk`). Outputs: `scripts/probes/_breakout_v1_replay_1101/out/` (the list per era, the night tables, the
coverage table, the dry run, the calibration, the parity check; after the run `trades.tsv.gz` + `report.txt`). Requests:
`scripts/probes/_breakout_v1_replay_1101/minute_request.tsv` and `raw_close_request.tsv`.

## 0. In plain words

- **The question:** what would the breakout v1 PAPER lane — the nightly list, the `orh5` buy with the F1 volume pace,
  the stop at the day's low (re-priced until the fill, then the true low), the cancels, the `pp` exit, one position
  per name, five shared slots — have produced over 2017-2024, traded exactly as the lane trades it? The number is a
  **yardstick** for the live paper results that start 2026-11-02: it says what "normal" looks like for this
  implementation, so a paper month can be read as in line / better / worse.
- **What it is not:** not a verdict on Qullamaggie's breakout (his own trades under our rules are the only PASS on
  file, `cb_holdings_replay_prereg_2026-10-24.md`: +1.06R a trade); a weak number here is a statement about THIS
  implementation — the selection, the entry, the stop or the exit — never "no edge".
- **Measured tail first:** the share and count of trades at ≥ 3R / ≥ 5R / ≥ 10R, then the mean R with its interval,
  then the win rate and the median.
- **The bar (§6) is fixed here, in numbers, before any outcome exists**, and is calibrated on synthetic populations
  drawn with their real fill months so that what it can and cannot tell apart is stated (§6.3).
- **Three books (§5):** the PRIMARY row is the capped book (the same-ticker guard + 5 slots) at 2c; beside it the
  guard-only book (no cap) and the LANE book (guard + slots + the 2% daily-loss limit + the 10-loss circuit breaker on a
  declared risk-fraction model). Decisive trades = mature AND E on or before an outcome-independent cutoff.

## 1. The four questions of the standard

1. **Decision served:** none on money. The replay gives the paper lane a historical baseline (mean R, tail shares,
   fill rate, the bite of the guard, the cap and the safeguards) against which its live paper months are read. It
   changes no rule, threshold, size, safeguard or live state.
2. **What would change the reading:** the verdict class in §6 on the primary row (the capped book, 2c, decisive trades,
   all years) and per era.
3. **Not asked:** 2025-26 (sealed); the live lane's defined divergences from the walk (§9); dollar P&L, equity and
   sizing (R only; the lane row's risk fractions are a declared model); whether another entry, stop or exit would do
   better (one configuration, his rulings as built).
4. **Control:** none — the baseline IS the number. The synthetic populations of §6.3 calibrate what the bar can and
   cannot tell apart; they are not controls on the data.

## 2. Population — the nightly list, the live gates on the historical bars (COMPUTED, pre-outcome)

The list is rebuilt night by night by CALLING the live rule module on the stored daily bars: the RS pool and its
members exactly as `breakout_v1_list.scan_members` tests them (every security at the $2 raw-close / $5M floors with a
63-session return over consecutive sessions — funds and ETFs included, his ruling (a) 2026-10-29), `cb.cross_section_one_date`
for rs_best, `bv.security_admitted` for who may be LISTED, `bv.history_ok` (86 consecutive sessions) and `bv.v1_gates`
(universe, rs ≥ 98, prior move, higher lows, surf, tightening, the breakdown check) for every listable member. The
gates are evaluated for the members whose rs_best ≥ 98 (the rs gate is one of the eight and every gate must pass, so
the list is identical; the per-gate fail counts are among those members, not the whole pool). Ranked by rs_best. The
per-name pool arithmetic (`rs_returns_contiguous`, `history_ok`, `cb._dollar_vol_median`) is re-implemented vectorised
and `scan_members` is copied as `night_members`; both are ASSERTED EQUAL to the live functions on the stores by the
`parity` stage (§10; `out/parity.txt`, pinned).

| | era A store (`cb702_pre_v2`) | era B store (`cb702`, sealed) | source |
|---|---|---|---|
| watch nights D | 1,322 (2016-12-30 .. 2022-03-31) | 690 (2022-04-01 .. 2024-12-30) | `out/population_era{A,B}.json` |
| breakout days E | 2017-01-03 .. 2022-04-01 | 2022-04-04 .. 2024-12-31 | the next SPY session after D |
| calendar | 1,635 sessions 2016-01-04 .. 2022-06-30 | 821 sessions 2021-09-27 .. 2024-12-31 (the export filtered to < 2025-01-01 before any bar is parsed) | the loaders' console |
| RS pool a night (mean) | 2,935 | 3,160 | `nights_era{A,B}.tsv` |
| listable a night (mean) | 2,414 | 2,485 | |
| **list rows** | **39,119 (29.6 a night)** | **21,952 (31.8 a night)** | `list_era{A,B}.tsv.gz` |
| nights with ≥ 1 name | 1,322 of 1,322 | 690 of 690 | |
| per-gate fails among rs ≥ 98 listable names (a name can fail several) | surf 84,803 · tightening 55,462 · higher lows 32,110 · prior move 22,440 · breakdown 18,612 · history 1,977 | surf 46,728 · tightening 28,675 · higher lows 18,796 · breakdown 11,065 · prior move 9,996 · history 450 | `population_era{A,B}.json` |
| the fund rule on the pool (name-nights): kept / excluded leveraged-inverse / basket / several / no known underlying / no name | 41,695 / 16,925 / 11,255 / 2,644 / 937 / 0 | 24,106 / 8,970 / 6,210 / 1,380 / 1,108 / 575 | `nights_era{A,B}.tsv` (the live first night: 39 kept, 15 excluded) |
| pool name-nights admitted with NO type row (`type_unknown`, admitted as live) | 977,119 | 1,625,138 | `nights_era{A,B}.tsv` |
| funds LISTED (kept funds passing every gate) | 2 name-nights | 20 name-nights | `list_era{A,B}.tsv.gz` |
| funds EXCLUDED by the rule that pass every other gate (the rule's own exclusion, not a loss) | 55 name-nights | 121 name-nights | `etv_would_list` |
| list rows by type: common / ADR / untyped / fund | 34,985 / 2,715 / 1,417 / 2 | 15,769 / 1,525 / 4,638 / 20 | |

**Both eras: 61,071 list rows over 2,012 nights = 30.4 names a night**, in line with the live first night (27 names,
2026-10-30). On the next session **3.14 names a night FIRE** (high above the level on ≥ 1.2× the 50-day volume,
`bv.breakout_triggered` on the E daily bar — the 2020 check read ~3.7) and 10.0 a night clear the level on any volume.
**The same name repeats:** 72% of list rows (43,786) follow a same-ticker row within four calendar days, and 1,505 of
the 6,319 fires come one to four days after an earlier fire of the same ticker — which is why the same-ticker guard of
§5 is load-bearing. **Expected n, stated now:** 6,319 fires in all; a fill further needs F1's pace at the break minute,
the day-low stop inside 1 ADR and the 15:55 window — on the prior reads roughly half to two thirds of level breaks fill
at ORH5 — so every name-day walked should hold about 3,000-4,000 fills before any book; the guard-only book removes
the re-buys of a held name (an upper bound of ~1,500 of the fires), the cap removes more, and the decisive cutoff (§5)
removes E after 2024-07-10. **The capped decisive n is expected at ~1,000-2,000** (era A ~700-1,300, era B ~300-700). The n
floor of §6 (100) is met in every era on that expectation; a calendar year or a QQQ-phase slice under 100 reads CAN'T
TELL on n.

**Reporting eras** split on the breakout day: **2017-21** (E ≤ 2021-12-31) vs **2022-24** (E ≥ 2022-01-03); the
STORE boundary (D ≤ 2022-03-31 on pre_v2, D ≥ 2022-04-01 on cb702) is a data seam inside era B's first quarter, walked
forward on the sealed cb702 copy (§5).

## 3. The stores, the seal and every approximation of a live gate (named, never silently dropped)

| what the live job reads | what the replay reads | how it differs |
|---|---|---|
| `mi_daily_closes` (Polygon grouped daily, adjusted) | `cb702_pre_v2/daily_closes_all.csv.gz` (2016-01-04 .. 2022-06-30, delisted names restored, duplicates removed) for D ≤ 2022-03-31; `cb702/daily_closes_all.csv.gz` stream-filtered to bar dates < 2025-01-01 for D ≥ 2022-04-01 (the filtered copy carries a sidecar naming its source's sha256; a copy whose source moved is regenerated, never reused) | the same vendor family; two export dates (2026-10-23 / 2026-10-16), each adjusted as of its own date |
| the RAW close for the $2 floor (`raw_close` = tonight's stored close) | era A: `daily_raw_close.csv.gz` per bar (exact). Era B: a **bridge** — for the 8,518 tickers in both stores, raw / adjusted on the last common date of the 2022-04-01 .. 06-30 overlap (= every split executing after it, 2025-26 ones included, DERIVED without reading a 2025 row), then the split list dated ≤ 2024-12-31 forward and back; 224 tickers whose overlap ratio was not stable and the 7,184 tickers not in pre_v2 use the ≤ 2024 split list alone (`raw_src = 2`) | **the 192 `raw_src = 2` tickers that reach the LIST (2,072 rows, 9.4% of era B; 576 rows show an apparent raw close under $10) get their UNADJUSTED daily closes from the main loop's raw-close pull (§7), and the walk re-judges their $2 floor and their cost cents from it** (a row whose true raw close at D is under $2 is `below_floor_raw`: never on the live list, no order, no slot); the remaining `raw_src = 2` tickers matter only as POOL members (the RS denominator) and keep the split-list scale — a 2025-26 splitter among them is mis-ranked by its floor only (declared); the 3,090 split rows dated ≥ 2025-01-01 are skipped on their date column alone |
| `mi_security_types` (type + Polygon's stored NAME) | `small_pulls.psv` `sectype` rows (type as of 2026-10, applied to every night) + the committed Polygon NAMES of the ETV tickers as of 2026-10-28 (`tests/fixtures/breakout_v1_parity/etv_names_2026-10-28.tsv`, 90 of the 92 typed ETVs; pinned) through the live `fund_rule` | the type and the name are point-in-time as of 2026-10, applied to every night (a fund renamed or re-listed since reads today's rule); the 2 ETVs with no name fail CLOSED (`no_name`, the live rule's own branch: 575 pool-nights in era B, 0 in era A). A ticker with no type row is admitted (`type_unknown`), as live — a delisted name has no 2026 type, so delisted names are admitted untyped (one warrant reaches the list this way: ASTSW, 1 row) |
| `get_unapplied_splits` (a series across an unapplied split sits out) | era A: the identity-break guard of `symbol_guard.tsv` (`runner.break_mask` over the 86-session window; a reused or corrupted series is out that night, counted `identity_break`, 33,056 name-nights). Era B: none (the export carries no guard file) | an era asymmetry, declared: a glued or reused series in era B is not caught by this guard (the 1% minute-vs-daily mismatch check on E is the only backstop there) |
| `cb_get_universe_bars` SQL prefilter (≥ $2, ≥ 0.7 × $5M) | none — every bar is tested by the module (the prefilter is a superset by design) | none |
| the 150-bar history | the full store history | none (every gate reads ≤ 86 bars; the 126-session return reads 127) |
| the market regime (`mi_market_regime`) | not available before 2025-03 in the local stores (the regime rows are inside the seal and are not read) | **no Apollo-regime slice; the QQQ phase at D (`cb.phase_qqq_10_20`, the registered market-state slice of every prior read) is reported instead, labelled as such** |
| the paper account's equity, the regime-keyed risk % and the 20% notional cap | not modelled for R; the LANE book (§5) uses the per-trade risk FRACTION min(2%, 20% × (fill − stop)/fill) = `size_breakout`'s arithmetic on a constant equity of 1.0 | R only; a `size_too_small` / `price_exceeds_cap` abstain cannot occur here; whole shares and the regime multiplier are not modelled (declared) |
| **the paper safeguards** (`live_tracker._check_safeguards`, run by `submit_trade_entry` on every paper entry): the max-positions cap; the 2% daily-loss limit; the 10-loss circuit breaker; the tiered drawdown breaker | the cap: the capped book. The daily-loss limit and the circuit breaker: the LANE book, on the declared risk fractions and the leg timing of §5. **The drawdown breaker (active on paper since 2026-06-03, per mode, a 30-day equity peak with WATCH / REDUCE / BLOCK tiers) is NOT modelled** — it needs the equity path this replay does not carry | the primary row does not carry the daily-loss limit or the breakers; the lane row reads beside it. Live trades FEWER and, in a drawdown, SMALLER than the primary row: every unmodelled safeguard removes or shrinks trades, never adds |
| the same-ticker guard (`entry_pipeline.submit_trade_entry` step 1b: a filled position of the ticker with shares left, from any earlier day, blocks a new entry) | every book: `block:ticker_open_position` in the chronological event loop (§5) | none in rule; the holding window is daily-bar resolution (§5) |
| `order_manager.submit_entry`'s `entry_ask_aware` (a quote's ASK above the trigger also selects the limit fallback; `mi_safeguard_state`, default OFF) | not modelled (no quotes in the stores; the flag is OFF) | none while OFF |
| `CHASE_RISK_INFLATION_CAP` (default 1.5; an environment override exists) | the default 1.5 (the override is not read; pinned as the constant's source line) | none unless the override is set in prod |
| minute bars from Alpaca (SIP, split-adjusted at read time) | the stored SIP minute files (`Adjustment.SPLIT`, fetched 2026-10-17 .. 10-26) plus the main loop's pull into `minutes_bv1_1101/`, `ticker\|minute\|o\|h\|l\|c\|v`, minute 0 = 09:30 ET, regular hours only, read through `runner.read_minute_file` / `minutes_for` with each store's `_done.psv` (its rows dated ≥ 2025-01-01 dropped on the date column) | a minute day whose high or low is more than 1% off the daily bar's (a split between the two fetches, a bad print) is the data abstain `minute_daily_mismatch`, counted, never traded (the registered backtests' rule) |

**Files that carry 2025+ dates and how each is handled:** `cb702/daily_closes_all.csv.gz` (bar rows → filtered out by
date string before parsing; the filtered copy is regenerated deterministically in scratch at run time from the pinned
source export, and the loader asserts its calendar ends 2024-12-31);
`cb702/cb702_splits.psv` (3,090 rows → skipped on the date column); `cb702/small_pulls.psv` (424 `regime` rows dated
2025-03-03 .. → never parsed; the `sectype` rows carry no date); `cb702/cb702_sic.psv` (a pull-date STAMP column,
not a bar date — not read by this replay at all); `cb702/minutes*/*.psv.gz` (files named by date → files ≥ 2025-01-01
are neither opened nor HASHED: the minute-store pins hash the data files named by a date < 2025-01-01 and the two logs
only). The walk asserts every E and every forward bar < 2025-01-01; the raw-close pull refuses on a 2025 row.

## 4. The entry — the next session's minute bars, tick by tick (the live tick, re-played)

For every list name on night D, on E = the next session, from 09:35 to 15:55 (`FIRST_MINUTE` 5 .. `EOD_MINUTE` 385),
the tick at minute m reads the bars through m−1 (`breakout_v1_entry.evaluate` — CALLED: ORH5 / ORL5 from minutes
0-4, `level = max(ORH5, list level)`, the day low so far → `stop_from_low` (the cent at or below it), the width
(level − stop)/level against the list's ADR20, F1 = cumulative volume ≥ the list's volume bar × `CUM_SHARE[m−1]`
(`f1_permits`, the pooled curve)), decides, then bar m prints and a resting order is checked for a fill.

| step | the live rule (called) | the broker mechanics (re-implemented; declared; the live source pinned at function level, §8) |
|---|---|---|
| no order yet | `evaluate`: `wait` → nothing; `abstain` (no opening-range bars, stop ≥ level, width > ADR20) → terminal for the day; F1 not permitting → hold; else place | — |
| the order | — | **#500 (`order_manager.submit_entry`):** when the last completed bar's close > level ("the latest trade", read at second 10 of the tick), a LIMIT at round(close × 1.002, 2); refused `setup:stop_too_wide` when (limit − stop)/limit > ADR20 (`width_at_expected_fill`) and `setup:chase_cap_exceeded` when (limit − stop) > 1.5 × (level − stop) (`CHASE_RISK_INFLATION_CAP`'s default). Else a STOP-LIMIT at `level`, limit `order_manager.stop_limit_buy_price(level)` (called: max(level × 1.005, level + 0.02)). A crossing in the first ten seconds of the placement minute fills at the level here where live would read the latest trade and use the fallback (favourable to the walk, declared) |
| the fill | — | stop-limit: the first bar ≥ the placement tick whose high ≥ level triggers it: filled at `level` when the bar opened at or under the level; at the open when it opened between the level and the limit; at the limit when the bar's low came back to it; else it rests as a limit at `limit` for a later bar (open ≤ limit → the open; low ≤ limit → the limit). The fallback limit: the open when the bar opens at or under it, else the limit when the low reaches it |
| resting | `_terminal_reason(st, m)` (called): m ≥ 385 → `window:breakout_unfilled_eod`; an abstain state → cancel (`setup:stop_too_wide`, `setup:zero_range`); F1 lapsed → `setup:breakout_volume_below_curve` — each terminal for the day | a cancel is instantaneous (no race with a fill) |
| the re-price (`_manage` / `_replace`) | a new day low more than half a cent under the placed stop → the stop moves to `stop_from_low(new low)` | cancel + re-place is instantaneous; the share re-size is not modelled (R only); the width at the expected fill is judged at the level for a stop-limit and at its limit for the fallback (live reads the latest trade again) |
| the stop at the fill (his ruling (1), 2026-10-29) | `stop_at_fill_decision(fill, true low through the fill minute, ADR20, placed stop)` (called) at the tick after the fill minute: `sell_all` → the whole position sold at the next bar's open (`setup:stop_too_wide_after_fill`, booked as a trade with that one exit); `lower` → the stop at the cent at or below the true low; `keep` | the fill minute's own low AFTER the fill is not read (cb's day-0 convention) — the PRIMARY reading. **The ADVERSE row (review HIGH 4):** live's protective stop is OTO to the buy and active from the fill, so when the fill bar's low is under the placed stop and the low came AFTER the fill, live is stopped out inside that minute. The walk cannot order the two inside one bar; every such fill is flagged (`adverse_stop`, counted) and a beside row books it stopped at the placed stop, R against the placed risk. A fill in the 15:55 minute has no tick after it (the live job pages; here the stop stands as placed, `unchecked_eod`) |
| the breakout day after the fill | `breakout_pp_rules.day0_facts` (called; equal to the recorder's `day0_facts`, re-checked in the dry run): the minutes after the fill minute against the stop AND the +2R target, breakeven from the next minute; the day's peak for the stall cut | the +2R third is the walk's **touch-is-a-fill** reading (live: a 5-minute poll places a resting limit after a touch — §9) |

Data abstains before the tick (counted, never traded, holding no slot): `minutes_unfetchable` (the vendor returned
no bars for a requested pair, §7), `minutes_no_rows` / `minutes_invalid`, `no_daily_bar_E`, `minute_daily_mismatch`,
`raw_close_missing` (a `raw_src = 2` row with no pulled raw close on D; bounded, §7) and `below_floor_raw` (never on
the live list). Live would have held a slot on a `minute_daily_mismatch` name (favourable to the walk, declared).

## 5. The exit, the free point, the decisive cutoff, the three books, the costs

**Exit** — session by session from E+1 on the stock's daily bars, CALLING the live decision functions
(`breakout_pp_rules`): the broker's stop leg first (a gap under the stop books the open; a bar touching both the stop
and the +2R target books the stop unless it OPENED above the target); the +2R third at the target (at the open when
the bar opened above it); on session 3 `session3_decision` (the stall cut when no high reached fill + 1R by then —
everything at that close; else the third at the close only when that close is above the fill and no third yet);
`trail_decision` on every settled close (live from session 3, or from a +2R third: a close under the 20-day simple
average sells the rest at the next open; `sma_at_last`'s arithmetic); `stop_after_third` (the stop rests at the fill
from the session after any third); `retry_decision` asserted wired (it is never reached: every sale completes in a
replay). **The stepper is asserted equal, event for event and to 1e-9 in R, to the DEFINITION
`consolidation_breakout_pp.walk_pp` (arm `pp`) on every trade of the walk and on 600 random paths in the dry run; a
mismatch raises and stops the run.** Horizon 120 sessions (the registered maturity convention: `cb.is_mature`); a
walk that reaches a calendar hole, a delisting or a store's end first is an OPEN MARK — counted, never in a decisive
number (`cb.forward_window` cuts before the first missing session).

**The Q1-2022 seam** — an era-A list row with E in the reporting era B (E ≥ 2022-01-03) walks forward on the SEALED
cb702 copy when that store has the ticker with an E bar whose high and low agree with pre_v2's within 1%
(`walk_inputs`; the count is reported); else on pre_v2, whose bars end 2022-06-30 (an open mark if still open then).

**The free point** (review HIGH 3) — every filled trade carries the session its LAST share leaves and, when known,
the minute: a day-0 stop at its exit minute; a sale after the fill at the minute after the fill; a degraded walk at
its last forward bar (E itself with none); a terminal exit or the 120-session mark at the session of its last event
(a trail sale at the next open frees before that day's first tick). The slot and the ticker guard both free there — an
open mark no longer holds a slot to the data's end.

**The decisive cutoff on E** (review LOW) — decisive = mature AND E on or before the last session whose 120-session
walk plus the trail's next open fits before the seal (the sealed calendar's session 821 − 1 − 121: **2024-07-10**).
A trade with a later E is walked — it holds its slot, blocks its ticker, feeds the safeguards — but is never decisive,
whatever its outcome; otherwise a late-2024 fill keeps its fast losers and loses its slow winners.

**The three books** — ONE chronological event loop over every list name-day that placed an order (`apply_book`),
in the live tick's order (day → minute → list rank; admissions cascade: a blocked name holds nothing, so a later name
may take its place). At each placement, in this order:
1. **the same-ticker guard** (`entry_pipeline` step 1b; every book): an admitted FILLED position of the same ticker
   from an earlier day still holding shares at this tick → `block:ticker_open_position`. A position whose last share
   left before this tick does not block; a day-0 exit does not block the next day; one with 2/3 left does;
2. **the cap** (the capped and lane books): held = carried positions not yet freed + today's admitted orders not yet
   cancelled (`OPEN_POSITION_STATUSES` = filled, order_placed, confirmed); 5 held → `block:max_positions`. A cancel at
   tick m frees its slot only for LOWER-ranked names placed at m (the tick walks names in list order); a day-0 exit at
   minute x frees it from minute x + 1; a trail sale at the open frees it before the first tick; a stop, cut or mark on
   a daily bar frees it at the end of that day (the minute is unknown; unfavourable to the walk, declared). The
   small-cap lane's historical occupancy is unknown and set to 0 (the live cap binds sooner);
3. **the lane's safeguards** (the lane book only; `live_tracker._check_safeguards`): the **daily-loss limit** — each
   admitted trade's legs dated today, netted per trade (a close day nets the trade's earlier legs out, ruling (iv);
   a losing partial on an open trade counts at once, ruling (1)), weighted by the trade's risk fraction
   min(2%, 20% × (fill − stop)/fill), the losses summed; a daily-bar leg counts from the day's first tick
   (pessimistic), a minute-timed leg from its minute; trip at ≤ −2% of a constant equity 1.0 → `block:daily_loss`.
   The **circuit breaker** — the last 10 outcomes before this tick (closed trades' totals at their close time; the
   partial legs of trades still open, each at its own time; a partial profit is a win) all ≤ 0 → blocked until one
   calendar day after the latest loss's time; a daily-bar loss (no time) blocks the rest of its session and the whole
   next session of the walk's calendar (every breakout day, placement or not) → `block:circuit_breaker`. The legs are read at the primary cost (2c).

**Which row is PRIMARY, and why:** the CAPPED book (guard + 5 slots) at 2c. The lane book is what the paper lane
literally runs, but its two extra safeguards rest on a risk-fraction model and on leg timing the daily bars cannot
give (declared above) and on an equity path this replay does not carry; a verdict must not rest on a model the
registration itself calls approximate. The lane row is reported FIRST beside the primary, with the same words, and the
guard-only row (no cap) beside both. Every blocked count is reported per book.

**Costs** — three rows, declared: **exact** (the model's prices), **2c** and **5c** per share on the entry AND on every
exit leg, in the RAW price scale (the cents are divided by the bar's raw factor before they meet the adjusted prices,
so a later split does not inflate them; a `raw_src = 2` row's factor comes from the pulled raw close). R = P&L /
(fill − stop) with the stop after the fill check and no cost in the denominator (the sized risk). **The primary row is
the CAPPED book at 2c.** The adverse row (§4) is reported at 2c on the primary population.

**Measures, per book, per cost row and per group** (all / era 2017-21 / era 2022-24 / calendar year / the QQQ phase
at D), decisive trades only: n, mean R with the 95% month-block bootstrap interval (`runner.block_bootstrap_ci`:
2,000 draws, seed 702, blocks = the fill month), win rate, median R, the share AND count at ≥ 3R / ≥ 5R / ≥ 10R, the
sum of R, the 15 biggest winners of the primary row (ticker, E, R, sessions held, exit kind), the entry funnel (every
list name-day's named state), the fill-stop decisions, the adverse-flag count, the order kinds, the exit kinds, the
open marks, the walked-not-decisive count, the seam count, every block count per book.

## 6. The bar — PASS / CAN'T TELL / FAIL, in numbers, before the run

Read on the primary row (the capped book, 2c, decisive trades), for ALL years and for each era; every other row is
reported beside with the same words and decides nothing.

**6.1 PASS** — all of: **n ≥ 100** decisive trades; **the interval's lower end > 0**; **the ≥ 3R share ≥ 8%**.
**6.2 FAIL** — all of: n ≥ 100; **the interval's upper end < +0.25R** (a quarter of his +1.06R a trade); **the ≥ 3R
share < 8%**.
**6.3 CAN'T TELL** — otherwise, with the sub-reading named: *tail present, mean not shown positive* (≥ 3R ≥ 8% and
the lower end ≤ 0: the big winners are found, the entry or exit gives the rest back — an entry / exit question, not
selection); *mean positive, tail thin* (lower end > 0 and ≥ 3R < 8%: the winners are not found or not held); *n < 100*;
*interval spans the bar*.

**Where the numbers come from.** The tail bar 8% sits between the two anchors on file: every structural breakout of
2017-21 under this exact exit (`cb702_pre_v2/out/trades_pre_exitpb.tsv.gz`, C0 / orh5 / tl / pp / mature / first
break: n 13,063 over 59 fill months, mean +0.04R, win 35%, **≥ 3R 6.0%**, ≥ 5R 3.6%, ≥ 10R 1.2%; saved beside the
code as `empirical_pp_c0_r.npy` + `empirical_pp_c0_months.npy`, pinned) and his own trades under our rules
(`_705_holdings_1024/02_replay.txt` §PER TRADE: n 205, **+1.06R**, win 37%, ≥ 5R 13.7 / 100, ≥ 10R 2.9 / 100).
The FAIL reference +0.25R is a quarter of his mean.

**Calibration** (`out/calibration.txt`, 300 replicates per cell, seed 702; the bar applied exactly as `verdict()` will
apply it to the data; **every drawn trade carries its REAL fill month, so the month-block interval sees the real
clustering** — review MEDIUM 6: random months understated it 2.75×): **N** = draws from the empirical anchor; **W(μ)**
= N's losers as they are, N's winners scaled by one factor so the mean lands on μ, for μ = +0.30 / +0.50 / +0.75 /
+1.05 (his replay; ≥ 3R 7.5% / 8.5% / 9.5% / 10.3%); **M** = 12% W(+1.05) + 88% N (mean +0.15R, ≥ 3R 6.4%).

| population | n = 300 | n = 700 | n = 1,000 | n = 2,000 | n = 3,000 |
|---|---|---|---|---|---|
| N (the mechanical null) — PASS / FAIL | 1.0% / 32.7% | 0% / 40.7% | 0% / 43.7% | 0% / 63.7% | 0% / 72.0% |
| W +0.30R — PASS | 13.3% | 24.7% | 30.7% | 20.7% | 13.3% |
| W +0.50R — PASS | 41.0% | 66.7% | 68.0% | 77.0% | 85.3% |
| W +0.75R — PASS | 76.0% | 91.7% | 93.7% | 99.3% | 100% |
| W +1.05R (his replay) — PASS | 88.0% | 99.0% | 99.3% | 99.7% | 100% |
| M (12% W + 88% N) — PASS / FAIL | 3.3% / 12.7% | 3.3% / 14.7% | 4.0% / 11.0% | 0% / 10.0% | 0% / 8.3% |

**What the bar can tell apart, stated before the run:** the null never passes (0-1% at every n) and FAILS 44% of the
time at n = 1,000, 72% at 3,000 — it reads CAN'T TELL more often than FAIL at the expected n, so a CAN'T TELL on the
data is NOT evidence of an edge. **The smallest working mean that PASSES more than 80% of the time is +0.75R a trade at
n ≥ 700 and +0.50R at n = 3,000; a +0.30R population passes under a third of the time at any n** — a modest real edge
reads CAN'T TELL here, and the sub-reading (tail present / mean positive) is what to read then. The 8% tail bar is the
binding half: W(+0.30)'s tail sits at 7.5%. Per-era slices at n ≈ 300-700 separate his-replay-like populations from
the null and little else.

## 7. Data contract — the two pulls the main loop makes (COMPUTED; both requests pinned, never rewritten)

**7.1 Minute sessions** — `minute_request.tsv` (`ticker · session_date · why`), **47,584 rows over 2,008 sessions**,
against **13,438 list rows already held** locally (22%; `out/request_summary.json`, `out/list_coverage.tsv`). A pair
a store logged as `empty` (no bars that session) is HELD — it walks as the data abstain `minutes_no_rows`, never as a
missing pull:

| | held locally | missing (in the request) |
|---|---|---|
| `fill_possible` — E's daily high above 99% of the level, so a fill can happen | 7,958 | **21,563** |
| `cap_occupancy_only` — E's high under the level: no fill, but a resting order (F1 permitting, stop inside 1 ADR) holds a slot until 15:55 and can block a real fill in the capped and lane books | 5,480 | **26,021** |
| of the 6,319 FIRES (level + 1.2× volume on the daily bar) | 1,590 | 4,729 |
| no daily bar on E (not requested; `no_daily_bar_E`) | 49 | — |

The holes are structural: the local minute stores were pulled for the consolidation-breakout backtest's own
candidates (2017-03-02 .. 2022-01-03 and 2022-04-01 onward), so every E in 2017-01 .. 2017-03-01 and 2022-01-04 ..
2022-03-31 is missing outright, and the v1 list's names are a different population from that backtest's. **The whole
request is pulled — both `why` classes; there is no fill-possible-only option** (the capped book is the primary row
and its slot occupancy needs the resting orders). **The pull:** `scripts/probes/_cb_backtest/fetch_minutes.py` in the
prod container (the Alpaca data keys), Alpaca market data v2, **feed = SIP, 1-minute, `Adjustment.SPLIT`** (the same
basis as every store the walk reads and as the daily files; the 1% minute-vs-daily check guards it), regular hours
09:30-16:00 ET, into **`apollo_data/cb702/minutes_bv1_1101/`** (`<date>.psv.gz` + `_done.psv` + `_failed.psv`, the
fetcher's own layout); its input is the request's first two columns as `ticker|date` (`cut -f1,2 minute_request.tsv
| tr '\t' '|'`). **The coverage rule (`coverage` stage; the walk re-derives it):** every requested pair must be HELD
(logged ok / empty in a store that has the day's file) or UNFETCHABLE (in `minutes_bv1_1101/_failed.psv`: the vendor
returned an error or nothing after the fetcher's retries — a counted data abstain `minutes_unfetchable`, never traded,
holding no slot); a pair in neither state is MISSING and the walk refuses; more than 2% of the request unfetchable
refuses too (a partial pull cannot run as a silently smaller population). The request file is pinned in the body (§11)
and never rewritten.

**7.2 Raw closes** — `raw_close_request.tsv` (`ticker · first_date · last_date · n_list_rows`): the **192 era-B list
tickers whose raw price scale rests on the split list alone** (`raw_src = 2`; 2,072 list rows; §3). **The pull:**
their UNADJUSTED daily closes (Alpaca v2 daily bars with `adjustment = raw`, or Polygon aggregates with
`adjusted=false`) from `first_date` to `last_date` inclusive — every date ≤ 2024-12-31 — written as ONE headerless
gzipped CSV **`apollo_data/cb702/raw_close_bv1_1101.csv.gz`** (`ticker,date,raw_close`, the shape of
`daily_raw_close.csv.gz`) plus the sidecar **`raw_close_bv1_1101.meta.json`** = `{"adjustment": "raw", "feed":
"<sip|iex|polygon>", "request_sha256": "<sha256 of raw_close_request.tsv>", "source": "<api>", "pulled_at": "<ISO>"}`.
The loader refuses a row dated ≥ 2025-01-01, a sidecar not saying `raw`, or a sidecar naming another request. At walk
time a `raw_src = 2` list row takes its raw close on D from the pull: under $2 → `below_floor_raw` (never listed live;
counted, no slot); else its cost factor; a row with no pulled close on D → `raw_close_missing` (counted, no slot; more
than 2% of the 2,072 refuses). The list itself stays pinned (the pool-level scale of §3 is declared, not corrected).

## 8. Freeze and run — the once-only procedure, in order (the main loop)

1. **Pre-pull commit.** This document and the probe folder (`v1_replay.py`, the two request files, `out/dryrun.txt`,
   `out/calibration.txt`, `out/parity.txt`, the two anchor arrays; the list / night tables stay out of git — their
   shas are in the table of §11) go in ONE commit on `main` — `freeze_commit`. The body table (§11) was computed after
   the final dry run; a code edit after it is a new table and a new commit, never a quiet re-run.
2. **The two pulls** (§7), in either order; then `python3 scripts/probes/_breakout_v1_replay_1101/v1_replay.py
   coverage` until it prints no problem (it names every missing pair and the raw-close gaps).
3. **The footer.** `python3 ... v1_replay.py pins footer` prints the post-pull lines (every minute-store tree, sealed,
   the pull's included; the raw-close file and its sidecar); they are pasted BELOW the FREEZE marker (the HTML comment that opens the footer; it must appear ONCE in this file) with
   `freeze_commit = <hash>` and `doc_body = <sha256 of every byte above the marker>` (printed by the same stage as
   `doc_body`). Nothing above the marker is edited after step 1.
4. **`python3 ... v1_replay.py walk`** — refuses unless: every body pin (§11) matches the file on disk; the footer
   carries `freeze_commit`, `doc_body` and every post-pull pin, each matching; `git show <freeze_commit>:<path>` of
   every repo-tracked body pin and of this document's body hashes to what is on disk (local git, no network); the
   coverage rule holds; the raw-close pull is present; no `trades.tsv.gz` / `report.txt` exists; no E or forward bar
   ≥ 2025-01-01. Runs once (~1-1.5 hours single core: 61,071 name-days × up to 380 ticks of the live `evaluate`, then the
   three books). Writes `out/trades.tsv.gz` (every list name-day with its named state, its admission and reason per
   book, its legs and events as JSON) and `out/report.txt`.
5. **The RESULT is pasted below the footer, never above it.** A crash on real data is fixed, disclosed as an event
   (what crashed, the fix, a new `freeze_commit`), and the run restarted from scratch (the outputs deleted) — the
   crash-fix-rerun is a disclosed event, not a second look at the numbers.

**Pins.** Whole-file (body): the five RULE modules (`breakout_v1.py`, `consolidation_breakout.py`,
`consolidation_breakout_pp.py`, `breakout_pp_rules.py`, `breakout_v1_volume_curve.py` — a change there is a new
registration), the committed ETV name list, the replay itself, the seven data files, the two list tables, the two
night tables, the two request files, the dry run, the calibration, the parity check, the two anchor arrays.
**Function-level** (body): the modules edited often are pinned on the SOURCE SEGMENTS of exactly the functions and
constants the replay calls OR re-implements (`FUNCTION_PINS`): `breakout_v1_entry.py` (`evaluate`, `f1_permits`,
`stop_from_low`, `_terminal_reason`, `stop_at_fill_decision`, `width_at_expected_fill`, `prepare_breakout_order`,
`_enter`, `_replace`, `_manage`, `size_breakout`, `resize_for_new_stop`, the minute constants); `breakout_v1_list.py`
(`scan_members`, `evaluate_members`, `rank_rows`); `order_manager.py` (`stop_limit_buy_price`,
`CHASE_RISK_INFLATION_CAP`, `submit_entry`); `entry_pipeline.py` (`submit_trade_entry`); `live_tracker.py`
(`_check_safeguards`, `count_open_positions`, the two realized-loss helpers); `constants.py` (the cap, the daily-loss
and breaker constants, `RISK_PCT`, `MAX_POSITION_PCT`); `runner.py` (the loaders, the minute readers, the bootstrap,
the freeze helpers). **The rule:** an edit elsewhere in those files does not refuse the run and needs no
re-registration; an edit inside a pinned function or constant refuses it and is a new registration (a renamed function
is a change, never a silent pass). **Post-pull** (footer): every minute-store tree (data files named by a date <
2025-01-01 plus `_done.psv` / `_failed.psv`; nothing dated 2025+ is opened or hashed) including the pull's, the
raw-close file and its sidecar, `freeze_commit`, `doc_body`.

## 9. What this does not answer — the replay's reach (stated before the run)

- **The live lane's defined divergences from the walk** (the SSoT's "where the live machinery cannot express the walk
  exactly", 1-10): the +2R third is a resting limit placed by a 5-minute poll after a touch — a touch whose limit does
  not fill is NOT a third live (no early trail, the session-3 third still applies, the limit cancelled on session 3
  and the third sold at that close); here a touch IS a fill. "The close of session 3" is the 15:45 price live; here
  the close. Whole shares (1-2 shares → no third); the next open as a DAY order queued at 19:02; the retry of a failed
  session-3 sale; the 16:45 backstops. Each makes live a little worse or later than the walk, never better.
- **The stop between the fill and its check**: the primary row reads the fill minute the favourable way (§4); the
  adverse row brackets it from the other side. Neither is the truth; the truth is between them.
- **Fill quality**: a stop-limit "fills at the level" when the bar opened under it — the paper broker fills at the
  quote; the 2c / 5c rows are the only allowance. A crossing inside the placement minute's first seconds fills at the
  level here, at latest × 1.002 live.
- **The book, where daily bars cannot time it:** a stop, cut or mark on a daily bar frees its slot and its ticker at
  the END of that day (live frees at the minute: the walk holds longer — unfavourable); a `minute_daily_mismatch`
  abstain holds no slot (live would have — favourable); the small-cap lane's slot use (0 here; the live cap binds
  sooner); the lane row's daily-loss timing (a daily-bar loss counts from the day's first tick — pessimistic) and its
  constant equity; whole shares and the regime multiplier in the risk fraction; the drawdown breaker (not modelled,
  active on paper: live trades fewer and smaller in drawdowns).
- **Sizing** (R only — the 20% notional cap enters the lane row's fractions only; the account's equity is not modelled;
  nothing here is a dollar number).
- **Single-asset funds**: the fund rule reads the 2026-10-28 names on every night; a fund renamed, re-listed or delisted since is judged on today's name (2 typed ETVs have none and fail closed).
- **Regimes**: no Apollo regime before 2025-03 locally; the QQQ phase at D is the market-state slice.
- **The era-B raw scale of POOL members** absent from pre_v2 (their $2 floor as RS-denominator members): the split-list
  scale; only the 192 LIST tickers are corrected by the pull. A 2025-26 forward splitter among the pool members fails
  the floor wrongly (missing from the pool); a reverse splitter passes it wrongly (present).
- **The Q1-2022 seam**: a trade whose ticker the sealed cb702 copy lacks, or whose E bar disagrees across the stores,
  walks on pre_v2 to 2022-06-30 and is an open mark if still open then (counted, not decisive).
- **E after 2024-07-10**: walked, holding slots and feeding the books and the safeguards, never decisive (§5).
- **2025-26** (sealed) and **any other configuration** (level, entry minute, stop, exit, size): one configuration,
  his rulings as built.
- **Survivorship in era B**: `cb702` carries delisted names (the 2022+ export includes them); era A's store was
  rebuilt for it (`cb_2017_21_rerun_v2_prereg_2026-10-25.md`). A degraded walk at a delisting is an open mark; the
  identity-break guard runs in era A only (§3).
- **Whether the list is "too long"**: 30 names a night is the live count's twin; the grade-ability question goes to
  him on the live list, not here.

## 10. The dry run (synthetic, hand-computed; `out/dryrun.txt`), the parity check and the smoke run

**37 hand-computed cases, 37 pass, 0 fail** (plus the four checks at the end of this paragraph; `out/dryrun.txt` ends
`DRY RUN COMPLETE`), each asserting the exact minute, price, R or admission: the fill at the level with the stop at
the day low (kept); never filled → cancelled 15:55 `window:breakout_unfilled_eod`; too wide at 09:35 (abstain, no
order); a new low widening past ADR while resting (cancelled at the next tick); the F1 lapse while resting (the lapse
minute derived from `CUM_SHARE`, cancelled at the tick after it); F1 never permitting (380 holds, never placed); the
flush inside the fill minute → the stop LOWERED to the true low; the true low too wide → sold at the next minute's
open; the #500 fallback refused by the chase cap, and admitted and filled at the next open inside it; the re-price of
the resting stop on a new low; a bar opening between the level and the limit (filled at the open); a bar opening above
the limit (the triggered limit rests, filled at the limit on a later low); the +2R third then the trail (+0.800R); the
session-3 third then the stop at cost (+0.200R); session 3 under the fill → no third, the trail from session 3
(+0.400R); the stall cut (+0.400R); a gap under the stop (−1.500R); the same-bar tie booking the stop (−1.000R) and,
opened above the target, the third then the stop (+0.0667R); a day-0 third then the day-0 stop at cost (+0.667R);
`retry_decision` wired; the 2c row (+0.800 → +0.760); the cap (rank order, a cancel freeing its slot, an open-exit
freeing before the first tick, the 6th slot blocked). **Added for revision 2:** the ticker guard (a held name blocks
its re-buy on 01-06 and on its exit day, frees the day after; a day-0 exit does not block the next day; a trail sale at
the open frees before the first tick; 2/3 remaining still blocks); a degraded / censored walk freeing its slot at its
last bar (the 6th name blocked that day, admitted the next); the same-minute order (a cancel at tick m frees only for
lower-ranked names placed at m: rank 2 blocked, rank 7 admitted, rank 8 blocked); a day-0 stop at minute 50 freeing
from minute 51; the adverse row on case 5's shape (flagged; R −1.000 / −1.133 primary vs −1.000 / −1.200 adverse at
0c / 2c; case 1 not flagged; the risk fraction 0.2 × 2.97% = 0.0059); the risk fractions (a 10%-wide stop → 0.02, a
3%-wide → 0.006); the daily-loss limit (one full-size −1R stop blocks the rest of its day and not the next; a day-0
stop at minute 100 blocks tick 101 not tick 50; a 0.6% loss trips nothing); the circuit breaker (ten straight 3%-wide
losses block the 10th loss's day and the next session, admitted the session after; a partial profit inside the window
breaks the streak; the cooldown is one session of the CALENDAR, not of the placement days — with no placement on the
session after the 10th close, a placement two sessions after it is admitted); the coverage rule (held / unfetchable / missing; the 2% bound); the decisive cutoff (index 78 of a
200-session calendar); the raw-close loader (a clean pull loads; a 2025 row refuses; a sidecar naming another request
refuses). Plus: 600 random day-0 + daily paths — the stepper equals `walk_pp` event for event (314 stopped on day 0,
186 stopped, 46 trailed, 47 cut, 7 degraded); no look-ahead in the entry loop on 60 random days (41 placements and 11
cancels unchanged when every bar from the decided minute on is garbled); `breakout_pp_rules.day0_facts` equals the
recorder's on 200 random minute days. Hand numbers the dry run corrected (the code was not changed): a blocked name
was counted as holding a slot (revision 1); the adverse case's risk fraction was written as 0.02 for a 2.97%-wide stop
(it is 0.0059); the breaker case's losses were sized to trip the daily-loss limit first (re-sized to 3%-wide stops);
the coverage case expected one refusal where the rule gives two (a missing row AND 1 of 4 over the 2% bound).

**Parity (`out/parity.txt`, pinned; the stores, not fixtures):** `ticker_facts` (the vectorised pool arithmetic) equals the live `cb._dollar_vol_median`, `bv.rs_returns_contiguous` and `bv.history_ok` on 11,801 sampled bars of 300 era-A tickers and 11,809 of 300 era-B tickers — 0 differences; `night_members` (the copy) equals the live `breakout_v1_list.scan_members` member for member (ticker, r21 / r63 / r126, listable, history, type) and on every shared count on six sampled watch nights (2017-08-24, 2017-10-23, 2018-07-03; 2023-06-22, 2023-09-06, 2023-12-04: 2,552 / 2,594 / 2,832 / 3,131 / 2,965 / 3,041 members) — 0 differences; `PARITY COMPLETE`. The live function is fed the night's series on the LIVE basis (prices × the raw factor at D, volume ÷ it, so the dollar volume is unchanged): `mi_daily_closes` holds each day's row as printed and never re-adjusts it (a name across an unapplied split sits out), so `bars.c[D]` IS the raw close there — `v1_gates`'s own docstring — while the stores are adjusted as of 2026. The first parity run, before that rescale, read 1-16 floor differences a night (names near $2 with a later split): the basis of the CHECK, not the rule.

**Parity spot check of the rebuilt list (pre-outcome; `tests/fixtures/breakout_v1_parity/meta.json.gz`, his 24 dated
good setups + 4 secondary):** every one of the 12 HITs of the parity test is on the rebuilt list on the night before
his day (CELH-1 / CELH-3 / CODX-1 / LVGO-4 / OPK-2 / PRTS / ARCT / HL / IBIO-1 / PENN-2 / CLSK / INO-4), and 11 of
the 16 non-HITs are on no list night around his day. The five that ARE listed (NVAX, OSTK-2, SRNE-2, OPK-3, INO-3)
are the parity's LATE / MISS verdicts on the FIRE — the next session's level break on 1.2× volume (NVAX's volume
miss is the SSoT's own example) — which the list does not judge; the walk's F1 does.

**Smoke run** (`walk --force-unfrozen --limit-days 3 --smoke-from 2020-06-01`, outputs to scratch, not pinned; run on
the revision-2 code): the three breakout days 2020-06-01 .. 06-03, 65 list rows, 45 without local minutes (`minutes_pending`, in the request), 20 walked — 3 fills (every fill-stop check `keep`; 2 stopped on a later session, 1 stopped on day 0; no adverse flag), 3 F1 cancels, 5 too-wide abstains, 9 never placed; the three books each blocked ONE re-buy of a held name (`block:ticker_open_position`), nothing on the cap or the safeguards in three days; every forward walk on store A; the decisive cutoff printed 2024-07-10; the stepper-equals-walk_pp assertion held on every fill. **No R was computed into any written row and none was printed** — the smoke rows carry
no `realized_r` / `r_*` / `events` / `legs` column by construction (the scratch rows of revision 1, which did, were
deleted). The three days are inside the registered population and are walked again by the registered run.

## 11. — FROZEN 2026-11-01 — the body pins (pre-pull; computed after the final dry run, the parity check and the smoke; `walk` reads this table)

| key | sha256 |
|---|---|
| breakout_v1.py | `bcc8625e004df65ae4ba4989049a4fb550dfa10e4440b63773af811cb024da34` |
| consolidation_breakout.py | `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b` |
| consolidation_breakout_pp.py | `bc74d54e1194a0a43b3fae908932fdfc323c7a29d7f093ef09e571b89ca05f3d` |
| breakout_pp_rules.py | `0294d18aa51e812cde6096c19f8d94ccca5a40399889f16db288dd11cdf9958b` |
| breakout_v1_volume_curve.py | `3c92fda6ad5aa6b995f24e773dc85316d16b934199753af7316176da1c0d2f50` |
| etv_names_2026-10-28.tsv | `042f90db0643f2b0773802c36283b537e964bbf8d3e034e1aa649476602eb447` |
| v1_replay.py | `4df7e73ef7f2bd21cfc8c46941f45255b0ba9f6fb62b69380ce4d3b41f39bcb7` |
| breakout_v1_entry.py (called functions) | `e9c6c5045e30be0a9f256a0849c5a5d76557261fab2082d9b295930c3c8fcf79` |
| breakout_v1_list.py (called functions) | `1188c4b71292a8a61ec71b0748546b11a5a890ea3fb0d00c94c2e5b87a1bbab1` |
| order_manager.py (called functions) | `628c7e982fa265ad24f444d18763f5d39006fca0b40b7fd5ec06db688f493247` |
| entry_pipeline.py (called functions) | `ee44730e570e5f8b91f2904d4dd456f850de3f9e69b074d4455d529ace39c4ee` |
| live_tracker.py (called functions) | `dab3b55ee784b59f0c4def58a594df5019bdc41b181ea5e4dbb35cb061c5d1e4` |
| constants.py (called constants) | `c1d11a3c6429fdec32a6e63b285775b3a987d96917307cb969993937a1e4b8b2` |
| runner.py (called functions) | `4bb1d8f0e954bda59b486f28e770c049f7e27476d3377b5428383ca92d0d639b` |
| data/cb702_pre_v2/daily_closes_all.csv.gz | `0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d` |
| data/cb702_pre_v2/daily_raw_close.csv.gz | `f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444` |
| data/cb702_pre_v2/small_pulls.psv | `d18e925b82ede2f5d4ca9ec8993d3d81f34ff10ebebec91b16f8b20e1aab0ff8` |
| data/cb702_pre_v2/symbol_guard.tsv | `876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08` |
| data/cb702/daily_closes_all.csv.gz | `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba` |
| data/cb702/cb702_splits.psv | `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b` |
| data/cb702/small_pulls.psv | `b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643` |
| list_eraA.tsv.gz | `83d0398e95eae46b5ed6881cfb653e2d0c7a076d275e5641c76f201118c2d907` |
| nights_eraA.tsv | `68bcda5e19c60c9e11a7fcbb5422652097d72d4754d7cdbabe53e1a38e793e90` |
| list_eraB.tsv.gz | `d057597c99204238b5df5b4656d8db750d2306f33f07abee274dda9a2b8e179f` |
| nights_eraB.tsv | `d7640c7256c59b0c066f4da50461bdebabc617c7e3e300ba1f6a95ab92cb8e6b` |
| minute_request.tsv | `f8bbf9f58d91fabd840f47617d5abb3364601dd230345474d5857cd3ea8803c8` |
| raw_close_request.tsv | `2f256edfe4f9b232ac8e69921c649f96cf3d9efa4bba1d4574ea5310a02e5d4d` |
| dryrun.txt | `962e871b7dcbc82ddc3e53f4069eea5a3d9253c51be6a2cc53700dcf392f84d5` |
| calibration.txt | `e9612371a6d057a23f3e08707e57a607c12ddcc35d3b489b28b849d2f2a8c184` |
| parity.txt | `c7cc2201bf3f4b9aaf0944ef02ecac607981a98391087ed3a2de40716bead430` |
| empirical_pp_c0_r.npy | `f7d03d59dee4807ff799ce6d0bf14366f779802b1d86a08452cca2c1471043f9` |
| empirical_pp_c0_months.npy | `6187698d336506791d7b3b88f13dd3df763c4411f4f815260ad58403c9e6ef16` |

Every byte above the next line is the frozen body (`doc_body`). Below it, the main loop pastes the post-pull pins
(§8 steps 3-4); the disclosed step the registration names in advance.

<!-- FREEZE -->
## Freeze record (the main loop; pasted after the pre-pull commit and the two pulls, before `walk`)

- freeze_commit = e2c7938db9a82cfc10d669daf591dbfa0a4eb30e
- doc_body = 6c407f1fe1c1c4277c70d5a0ce813f97fed5e49800edf604e2010756874c756b
- minutes (cb702_pre_v2/minutes) (tree) sha256: `9d5b332a4a6c31594b3c13302e1e6fa25c7cc7aa18a21c177a56333b65086a65`
- minutes (cb702/minutes) (tree) sha256: `9b6d5cf4875b4b5276337965ff3c6aaa216076d3c19c5a39256dfe20beb0e08b`
- minutes (cb702/minutes_asis_1026) (tree) sha256: `079f475f5e42c7391a155634fc00aaa4d71b9b8ccc4f59a34faebb9859285ed5`
- minutes (cb702/minutes_rev_1024) (tree) sha256: `bcdc099910020c178e221dc11d79c3d6212d16b2bf0903fdf941b54c84f6e460`
- minutes (cb702/minutes_intra_1025) (tree) sha256: `1d326d2fa23ba6aa4f32ec5b334fa86fac38451784838ff9e83cd4d959e8aacc`
- minutes (cb702/minutes_ep_1023) (tree) sha256: `08394cc622b8d273b76aee366e1f42796d6f41b8e4a876649456e7471eb6247a`
- minutes (cb702/minutes_ep_1024) (tree) sha256: `74832cfa550c673c016aeb84deee96a8696c1e73a0445ad81f36a4d9a9d72ba4`
- minutes (cb702/minutes_com_delta_1018) (tree) sha256: `595ee6638dc5565ed350bb829fd45c11aa0ad1520db6045497cf210cece6e13a`
- minutes (cb702/minutes_pre_com_1018) (tree) sha256: `dec337798e6c8226c1bf786649bef88af9fea87547705e958b1db1c754cdc000`
- minutes (cb702/cb702_minutes_delta_out) (tree) sha256: `91a713323a2bd91f5b47a076c651f7028f49e6293a6cbb256905bd0fea357422`
- minutes (cb702/minutes_bv1_1101) (tree) sha256: `1e0035d02c2b60efd73b8d40af3e983944d5c59cdeec501cb35ceeb4c1ff7646`
- raw_close_bv1_1101.csv.gz sha256: `1c0e3f8c1edf3c0344a8a43249bb8da4e0fa0c7c4c62d7de8892b4c165ba2f07`
- raw_close_bv1_1101.meta.json sha256: `16e54977009ebc9e0c77eb489632fb28e66594d6af1b3c0cf9fbe15ca93fc840`
- pull (2026-11-01, main loop, his "Allow"): minutes — `fetch_minutes.py` in apollo-market, Alpaca SIP 1-min, Adjustment.SPLIT, the whole request: 47,584 pairs / 2,008 sessions, 47,555 with bars, 29 empty, 0 failed (139 MB, `apollo_data/cb702/minutes_bv1_1101/`); raw closes — `pull_raw_closes.py`, Alpaca daily RAW: 192 tickers, 15,553 rows <= 2024-12-31, 1 empty, 0 errors. `coverage`: 0 missing, 0 unfetchable, no problem.
- walk (2026-11-01, run ONCE on the Polygon raw pull; `out/report.txt`, `out/trades.tsv.gz`): PRIMARY (capped book, guard + 5 slots, 2c) n 1,639, mean R -0.245 [-0.38, -0.09], win 33.1%, >= 3R 4.6% (75), >= 10R 0.9% (15) -> FAIL; 2017-21 n 1,058 -0.153 [-0.34, +0.05] FAIL; 2022-24 n 581 -0.412 [-0.58, -0.21] FAIL. Beside: the uncapped guard book n 4,819 -0.147 [-0.27, -0.02] FAIL. A blind recount and an adversarial audit run before it is reported.
- ⚠ the raw-close pull REPLACED before any outcome (2026-11-01, disclosed): the first walk REFUSED at its end-of-walk coverage check — 48 of 2,072 raw_src=2 list rows had no pulled raw close (INBX 43: Alpaca returned no rows; ARIS 5) — and wrote nothing (no R printed, no output file; only the per-50-day fill/cancel counts). Checking every pulled raw close against the store's adjusted close on the same day (`raw_ratio_check_alpaca.txt`) then showed Alpaca maps a symbol to its CURRENT owner: 8 tickers' raw/adjusted ratio DRIFTED instead of holding a clean split constant (ARIS, TEN, CNR, CD, SPWR, OSG, VIVO, SAVA — other companies' prices). The pull was re-made from Polygon v2 daily aggregates, adjusted=false, point-in-time by ticker (§7 allows either source; `pull_raw_closes_polygon.py`, `raw_close_pull_log_polygon.txt`): 192 tickers, 16,266 rows, 0 empty, 0 errors; the same check (`raw_ratio_check_polygon.txt`): 0 missing, 0 drifting tickers (SAVA on two levels). The Alpaca file is kept as `apollo_data/cb702/raw_close_bv1_1101.alpaca_superseded.csv.gz`. The two raw pins above are the Polygon file's; nothing above the marker changed (doc_body unchanged); the walk is re-run once on it.

