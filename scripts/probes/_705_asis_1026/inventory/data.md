# Rule-free inventory for steps 4-5: his buy and sell windows, and the bars that cover them

Date 2026-10-26. Measure only, no design. The as-is read: nothing here uses our rule library (breakout, EP, pivot, ORH5, stops).

## 0. The answer in nine lines

- **What we hold:** 1,874 positions: 1,861 with a buy window, 1,861 with a sale window, 1,848 with both (13 held at the first stream have no buy; 13 still held at the last have no sale).
- **Windows are mostly one session:** 62.2% of buy windows and 60.2% of sale windows are a single known session; 85.0% / 85.1% are 5 sessions or fewer. Both ends one session wide: 826 of 1,848 round trips (44.7%).
- **Only the morning is on screen:** the last in-session frame of a stream day is at 10:40 ET (median); frames at or after 12:00 are 14 of 1,926. A trade made after the stream ends shows only at a later stream: 723 buys (38.9%) were flat at an in-session frame and are next seen holding on a later date, and 1,068 sells (57.4%) were last seen holding in-session with the next evidence on a later date (overnight or several sessions).
- **Minute-level brackets exist for a minority:** same-day clock brackets for 805 buys (43.3%) and 595 sells (32.0%); the in-session ones are a median ~30 minutes wide (section 2.5).
- **659 positions (35.2%) are flickers** (one stream only, gone within 5 sessions: a short hold or a misread; the file cannot tell which). Without flickers and inverted windows, 1,172 round trips remain.
- **Rule-free columns:** 23 of 43 in `entries.tsv` and all of `exits.tsv`; the 18 rule-derived ones (E, setup, pivot, ep_*, ...) are not needed for steps 4-5, and the two panel-clock columns have a rule-free source in `snapshots.tsv` (section 1).
- **Daily bars (2020-01..2022-06):** every session of the window has a bar for 88.7% of buy windows (1,511) and 88.8% of sale windows (1,538); the gaps are names absent from the 2016-22 file (delisted, renamed without an alias, funds), not dates.
- **Minute bars on disk:** every session covered for 70.4% of buy and 60.5% of sale windows; one-session windows 76.0% / 64.9%. Missing (daily bar, no minute log): 1,921 (symbol, day) pairs on 486 dates = about 486 requests, ~4 minutes at the last run's speed; recorded as free, not run.
- **Action: none for the operator.** An inventory; it feeds the design of steps 4-5.

**Inputs (pinned, equal to the pins in `scripts/probes/_705_holdings_1024/01_timeline.txt`):**

| file | rows | sha256 (first 16) |
|---|---|---|
| `holdings_1024/entries.tsv` | 1,874 | 6a0dda2da7932b6d |
| `holdings_1024/exits.tsv` | 1,861 | 1ed76a2806091f7d |
| `holdings_1024/snapshots.tsv` | 2,907 | a8987fce15fa1a96 |
| `holdings_1024/control.tsv` | 236 | 193a5b985b1d979d |

**Guards kept:** no subagent, no network, no production server, no paid call. Nothing dated after 2024-12-31 was used: the 2021-26 daily export had 5,210,943 rows after the cut and its minute log 72,951 rows; all were counted and discarded at read, and the 449 minute date-files after the cut were never opened. The outcome folders `holdings_1024/{replay,his_exits,intraday,reverse,rule_mix,reverse_fit_events,reverse_recount_cache}` were not opened. Items marked *quoted* are copied from an earlier printout or registration because the TSVs cannot reproduce them.

## 1. Which columns are rule-free (a) and which used one of our definitions (b)

Test used: **(b) = the value was dated, labelled or selected with a breakout / EP / pattern / candidate-stream definition**; (a) = taken from the panel frames, the calendar or a bar-file lookup. All code lines are in `scripts/probes/_705_holdings_1024/01_timeline.py` (called `tl` below).

### 1.1 `entries.tsv` (43 columns, 1,874 rows)

| column | what it holds | class | computed at |
|---|---|---|---|
| eid | row id, in order of first sighting | a | tl L566 |
| sym | the symbol as shown on the panel, after the look-alike rename | a | tl L566; rename L610-618 |
| sym_a | the same name's symbol in the 2016-22 bar file (overlap-close signature or dedupe map). A data join, no trade definition | a | tl L737; `load_alias` L642-673 |
| has_bars | symbol exists in a bar file at all (any date 2016-2026). NOT a coverage test for a window (see 3.1) | a | tl L738 |
| ever_candidate | name appears anywhere in the breakout (`tl`) or EP candidate streams | **b** | tl L739; `cand_names` L912 built from `load_breakouts` L676 and `load_eps` L706 |
| setup | `breakout` / `EP` / `both` / `undated` / `initial`. Only `initial` is rule-free | **b** | tl L744, L752, L761 |
| E | 'buy day' = the LATEST breakout or EP event day inside the window | **b** | tl L756-762; `events_in` L722 |
| D | the breakout's detector date | **b** | tl L768, L773 |
| era | A or B bar era of the dating event (undated: split on window start) | **b** | tl L753, L765 |
| pivot | breakout pivot price | **b** | tl L768 |
| adr20 | 20-day average daily range, copied from the breakout row | **b** | tl L768 |
| base_id | consolidation base id of the breakout row | **b** | tl L768 |
| retrigger | breakout retrigger count | **b** | tl L768 |
| ep_prev_close | prior close of the matched EP gap day | **b** | tl L771 |
| ep_gap_pct | gap % of the matched EP gap day | **b** | tl L771 |
| n_events_in_window | how many of our breakout / EP events fall inside the window | **b** | tl L750 |
| E_earliest | earliest event day in the window | **b** | tl L763 |
| kind_earliest | kind of the earliest event | **b** | tl L763 |
| q1_2022_hole | window touches 2022-01-04..03-31, where no breakout stream exists. A coverage flag of OUR detector | **b** | tl L748 |
| undated_reason | `initial`, `no_bars`, `never_candidate`, `no_event_in_window` | **b** (`initial` and `no_bars` alone are data facts) | tl L745, L754 |
| first_clock_on_E | clock of the first sighting frame, filled only when that frame is on E | **mixed**: the clock is observed, the filter on E is (b) | tl L407-408 (`panel_clocks`) |
| flat_clock_on_E | clock of the last full frame without the name, filled only when on E | **mixed** (same) | tl L410-411 |
| orh5_infeasible | held on E before 09:35 (the end of the 5-minute opening range) | **b** | tl L409; `ORH5_FIRST` L139 |
| first_frame | frame id of the first sighting | a | tl L1096 |
| first_vid | stream (video) of that frame | a | tl L1096 |
| first_date | date of the stream (mode of its frames' taskbar dates) | a | tl L328-339, L1097 |
| first_ctx | `pre` / `in` / `closed`: frame clock before the open, in session, after the close | a | tl L351-354 (reader's `clock_ctx`) |
| prev_full_frame | last full panel snapshot that did not show the name (blank for the 13 initial) | a | tl L560-566; full flag L241-261 |
| prev_full_date | its stream date | a | tl L1098 |
| lo | first session on which the buy could have happened | a (reading rule: `lo_after` L419-423) | tl L561 |
| hi | last session by which the name was held | a (reading rule: `asof` L415-416) | tl L561 |
| window_len | `hi - lo + 1` in sessions | a | tl L474-476 |
| inverted | flat frame was after the close or `hi` fell before `lo` (a pre-/after-hours trade or a misread); `lo` is then set to `hi` | a | tl L562-565 |
| initial | held at the first full snapshot, buy unknowable | a | tl L470-472 |
| flicker | seen in one stream only AND sold within 5 sessions of the sighting | a (reading rule: `FLICKER_SESSIONS` = 5, L478) | tl L586-589 |
| n_sightings | number of snapshots showing the name | a | tl L569 |
| n_streams | number of distinct streams showing the name | a | tl L570 |
| exit_lo | first session on which the sale could have happened | a (`lo_after` of the last sighting) | tl L580 |
| exit_hi | last session by which the sale had happened | a (`asof` of the first of two full frames without the name) | tl L580 |
| exit_frame | that first full frame without the name | a | tl L573-577 |
| still_held | no exit seen by the last snapshot | a | tl L1103 |
| first_resolution | `1920x1080` or `1280x720` (the 2019-09..2020-01 streams) | a | tl L1103 |
| decides | dated AND window <= 10 sessions AND not initial | **b** | tl L1104; `WINDOW_CAP` L132 |

Count: 23 rule-free, 18 rule-derived, 2 mixed; total 43 (file has 43).

**Recovering the rule-free half of the two mixed columns:** `snapshots.tsv` holds `clock` and `ctx` for every frame, so the brackets are `snapshots[prev_full_frame]` -> `snapshots[first_frame]` for the buy and `snapshots[last sighting]` -> `snapshots[exit_frame]` for the sell, on any day, not only on E. Section 2.5 does this.

### 1.2 `exits.tsv` (8 columns, 1,861 rows): all rule-free

| column | what it holds | class | computed at |
|---|---|---|---|
| eid, sym, sym_a | position id, panel symbol, 2016-22 symbol | a | tl L1106 |
| exit_lo, exit_hi | sale window (sessions), as in entries | a | tl L580 |
| exit_frame | first full frame without the name | a | tl L577 |
| flicker, initial | copied from entries | a | tl L1106 |

Gaps in this file: the sale window's **length is not a column** (computed here as `exit_hi - exit_lo + 1`), the **last-sighting frame is not stored** (recovered here by scanning `snapshots.tsv`; the reconstruction reproduces all 1,861 `exit_lo` / `exit_hi` values exactly), and the **exit inversion is not stored**: `tl` L581-583 clamps `exit_lo` to `exit_hi` when the last sighting was after the sale bound, so 38 inverted sells look like true one-session windows in the file (38 recomputed here, equal to the printout's 38).

### 1.3 The other two files

- `snapshots.tsv` (22 columns, 2,907 rows): rule-free. Its `symbols` column is already after the look-alike rename (18 snapshots relabelled) and `blip_filled` names are NOT in `symbols`. Not in the file: the panel's per-row `% Change` cell (see section 5).
- `control.tsv` (19 columns, 236 rows): entirely rule-derived (the 236 are his labelled calls dated to our event days E; every column joins them to E). Not used here.

### 1.4 Reading rules baked into the (a) columns

These are not trading rules, but any step-7 reader inherits them. Each can be re-run differently from `snapshots.tsv`.

| reading rule | what it does | code | scale in these files |
|---|---|---|---|
| video date = mode of taskbar dates | a stray frame date never moves a snapshot | tl L328-339 | 2 videos carry two dates |
| duplicate uploads dropped, frames ordered by fitted ET clock | one stream uploaded twice is read once | tl L282-314, L340-347, sort L376 | 70 frames dropped, 17 videos on 13 dates (*quoted*, `01_timeline.txt`) |
| `ctx` pre / in / closed | from the frame's clock; unknown read as `in` | tl L351-354 | 142 snapshots with an unknown context, read as in-session |
| full snapshot = footer total equals rows read, else the list ends >= 1.5 row pitches above the panel bottom | only full snapshots can show a sale | tl L241-261; `FULL_GAP_PITCHES` L136 | 2,082 full of 2,907; footer-scrolled (not full) 751 |
| buy window = last full frame without the name -> first frame with it | `lo_after`, `asof` convert ctx to sessions | tl L415-423, L556-566 | 1,861 windows |
| sale needs TWO consecutive full frames without the name | a sighting between them cancels it | tl L571-584 | 229 single-frame drops cancelled (*quoted*) |
| blip fill | a name missing from every full frame of exactly one stream, present in the streams either side, is filled | tl L427-452 | 125 (stream, name) pairs, 518 snapshots touched; 118 of the 125 fill over a footer-consistent absence (*quoted*) |
| look-alike guard | a read X one edit from a held Y, with the reader flagging Y's row, relabels Y -> X | tl L492-535, L596-626 | 18 snapshots relabelled |
| flicker flag | one stream only and sold within 5 sessions | tl L478, L586-589 | 659 positions |

## 2. The rule-free windows (steps 4-5)

**Definitions.** *Buy window* = the sessions `lo..hi` between the last full panel snapshot without the name and the first snapshot with it; *length* = `hi - lo + 1` sessions (1 = the buy happened inside one known session). *Sell window* = from the session of the last sighting to the session of the first of two consecutive full snapshots without the name. *Year* of a buy = year of `hi`; year of a sell = year of `exit_hi`. 2023 is a flagged extra row (stream coverage there is sparse).

### 2.1 Counts by year

| row | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 (extra) | total |
|---|---|---|---|---|---|---|---|---|
| buys, all (incl. 13 initial) | 94 | 16 | 198 | 803 | 583 | 132 | 48 | 1,874 |
| buys with a window (not initial) | 81 | 16 | 198 | 803 | 583 | 132 | 48 | 1,861 |
|   of which flicker | 4 | 0 | 82 | 304 | 211 | 51 | 7 | 659 |
|   of which inverted (no regular session in the window) | 0 | 0 | 12 | 18 | 2 | 1 | 1 | 34 |
|   of which still held at the end (no sale seen) | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 13 |
| sells (with a sale window) | 46 | 48 | 184 | 814 | 589 | 139 | 41 | 1,861 |
|   of which flicker | 4 | 0 | 80 | 306 | 211 | 51 | 7 | 659 |
|   of which inverted | 0 | 0 | 10 | 21 | 4 | 1 | 2 | 38 |
|   of which belong to an initial holding (buy unknown) | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 13 |

Cross-check: buys by stream year (year of the first sighting) are the same seven numbers (94 / 16 / 198 / 803 / 583 / 132 / 48 with the 13 initial), sells by stream year of the exit frame are the same seven numbers as the sells row above, and both equal the table in `01_timeline.txt`.

### 2.2 Window length in sessions

| window | 1 | 2 | 3-5 | 6-10 | 11-20 | 21-60 | 61+ | n | median | 90th pct | <=1 | <=5 | <=10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **BUY, all years** | 1,158 | 251 | 173 | 128 | 63 | 40 | 48 | 1,861 | 1 | 8 | 62.2% | 85.0% | 91.9% |
| buy 2017 | 1 | 8 | 5 | 0 | 23 | 33 | 11 | 81 | 22 | 129 | 1.2% | 17.3% | 17.3% |
| buy 2018 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 16 | 250 | 250 | 0.0% | 0.0% | 0.0% |
| buy 2019 | 89 | 45 | 27 | 16 | 13 | 0 | 8 | 198 | 2 | 12 | 44.9% | 81.3% | 89.4% |
| buy 2020 | 560 | 107 | 75 | 61 | 0 | 0 | 0 | 803 | 1 | 4 | 69.7% | 92.4% | 100.0% |
| buy 2021 | 414 | 73 | 50 | 30 | 16 | 0 | 0 | 583 | 1 | 4 | 71.0% | 92.1% | 97.3% |
| buy 2022 | 80 | 11 | 15 | 14 | 11 | 0 | 1 | 132 | 1 | 9 | 60.6% | 80.3% | 90.9% |
| buy 2023 | 14 | 7 | 1 | 7 | 0 | 7 | 12 | 48 | 10 | 91 | 29.2% | 45.8% | 60.4% |
| **SELL, all years** | 1,120 | 288 | 176 | 113 | 44 | 6 | 114 | 1,861 | 1 | 9 | 60.2% | 85.1% | 91.2% |
| sell 2017 | 1 | 4 | 8 | 0 | 6 | 0 | 27 | 46 | 115 | 129 | 2.2% | 28.3% | 28.3% |
| sell 2018 | 0 | 0 | 0 | 0 | 0 | 0 | 48 | 48 | 221 | 250 | 0.0% | 0.0% | 0.0% |
| sell 2019 | 89 | 25 | 17 | 24 | 13 | 0 | 16 | 184 | 2 | 14 | 48.4% | 71.2% | 84.2% |
| sell 2020 | 533 | 147 | 81 | 51 | 2 | 0 | 0 | 814 | 1 | 4 | 65.5% | 93.5% | 99.8% |
| sell 2021 | 427 | 75 | 46 | 27 | 14 | 0 | 0 | 589 | 1 | 4 | 72.5% | 93.0% | 97.6% |
| sell 2022 | 57 | 37 | 24 | 9 | 9 | 0 | 3 | 139 | 2 | 8 | 41.0% | 84.9% | 91.4% |
| sell 2023 | 13 | 0 | 0 | 2 | 0 | 6 | 20 | 41 | 46 | 121 | 31.7% | 31.7% | 36.6% |

Reconciles with `01_timeline.txt` (buy buckets 1,158 / 251 / 173 / 128 / 63 / 40 / 48; median 1). Longest window: 273 sessions (buy), 273 (sell); the 61+ group is the sparse years (2017-18, 2022-11 on), where consecutive streams are months apart.

### 2.3 Classes and how they overlap (all 1,874 positions)

| class | positions | note |
|---|---|---|
| positions in the file | 1,874 |  |
| initial (held at the first full snapshot; buy unknowable) | 13 | all 13 were later sold; 13 sells with no buy window |
| still held at the last snapshot (sell unknown) | 13 | all 13 have a buy window; none is an initial holding |
| flicker (one stream only, sold within 5 sessions) | 659 | 479 have a one-session sell window, 455 a one-session buy window; 275 were seen in a single snapshot |
| inverted buy window | 34 | flat frame after the close, or two pre-market frames of the same day |
| inverted sell window | 38 | recomputed here; the file does not store it |
| **has BOTH a buy window and a sell window** | 1,848 | = 1,874 - 13 initial - 13 still held |
|   of which not flicker, not inverted either side | 1,172 | 63.4% of the round trips |
|   of which not flicker (inverted allowed) | 1,189 |  |
| flicker AND (inverted buy or sell) | 37 |  |

A flicker is a real short hold or a one-frame misread of a name: the timeline cannot separate them, and a one-snapshot sighting (275 positions) is the weakest evidence in the file.

### 2.4 How tight a round trip is

| measure | round trips | share / note |
|---|---|---|
| round trips (both windows) | 1,848 |  |
| both windows exactly 1 session | 826 | 44.7% |
| both windows <= 2 sessions | 1,188 | 64.3% |
| both windows <= 5 sessions | 1,432 | 77.5% |
| at least one window exactly 1 session | 1,451 | 78.5% |
| longest possible hold (sale hi minus buy lo) <= 1 session | 525 | 28.4%: same-day or next-day round trips |
| longest possible hold <= 2 / <= 5 sessions | 712 / 1,008 | 38.5% / 54.5% |
| shortest possible hold = 0 sessions (sale window may start the buy session) | 494 | 26.7% |
| windows that overlap in the impossible direction (sale window starts before buy window ends) | 2 | misreads or a re-buy on the same name |
| median shortest / longest possible hold (sessions) | 1 / 4 |  |

### 2.5 Clock brackets: how many minutes inside the window (the rule-free equivalent of the panel-clock columns)

Every frame carries a clock (`snapshots.tsv` `clock`, ET) and a context. A buy is bracketed by the clock of the earlier frame (last full frame without the name) and the later frame (first frame with it); a sale by the last frame that showed the name and the first full frame without it. When both frames are on the same date the bracket is a time span of that day.

| frame clock (ET) | pre-market frames | in-session frames | after-close frames | all |
|---|---|---|---|---|
| before 09:00 | 69 | 10 | 3 | 82 |
| 09:00-09:29 | 890 | 24 | 0 | 914 |
| 09:30-09:59 | 0 | 545 | 2 | 547 |
| 10:00-10:59 | 0 | 1,087 | 0 | 1,087 |
| 11:00-11:59 | 0 | 246 | 0 | 246 |
| 12:00 or later | 0 | 14 | 0 | 14 |
| no clock read | 0 | 17 | 0 | 17 |
| **all snapshots** | 959 | 1,943 | 5 | 2,907 |

- Stream days with an in-session frame: 488. The last in-session frame is at **10:40 ET** (median; 10th pct 09:59, 90th pct 11:23); the first at 09:55. On those days about 82% of the 09:30-16:00 session comes after the last frame.
- In-session frames at or after 12:00: 14 of 1,926. The afternoon is essentially never on screen.
- Sessions 2020-01-01..2022-06-30: 629; with at least one snapshot 449 (71.4%); with a full snapshot 385 (61.2%). Consecutive full frames on the same date are a median 5 minutes apart (90th pct 53).

**Bracket type (earlier frame -> later frame).** Buys are the 1,861 positions with a buy window; sells the 1,861 with a sale window. 'Span' = window end in 2020-01..2022-06.

| bracket type | buys | share | buys in span | sells | share | sells in span |
|---|---|---|---|---|---|---|
| same day, in-session -> in-session | 338 | 18.2% | 301 | 289 | 15.5% | 252 |
| same day, pre-market -> in-session | 436 | 23.4% | 400 | 271 | 14.6% | 252 |
| same day, other (pre>pre, in>closed ...) | 31 | 1.7% | 21 | 35 | 1.9% | 26 |
| next session, in-session -> pre-market (afternoon + overnight) | 318 | 17.1% | 305 | 490 | 26.3% | 460 |
| next session, in-session -> in-session | 64 | 3.4% | 44 | 81 | 4.4% | 74 |
| next session, other | 73 | 3.9% | 62 | 39 | 2.1% | 35 |
| 2-5 sessions apart | 353 | 19.0% | 287 | 395 | 21.2% | 341 |
| 6+ sessions apart | 248 | 13.3% | 91 | 261 | 14.0% | 98 |
| **all** | 1,861 |  | 1,511 | 1,861 |  | 1,538 |

**Width of the same-day brackets, in minutes** (the pre-market -> in-session rows count only the minutes after 09:30, the part that has minute bars). Zero-or-negative widths (same minute, or the clock order broken by a misread) are shown separately and excluded from the quantiles but kept in the shares' denominator.

| bracket | n with both clocks | width <= 0 | median (min) | quartiles (min) | <= 15 min | <= 30 min | <= 60 min | > 60 min |
|---|---|---|---|---|---|---|---|---|
| BUY in-session -> in-session | 338 | 9 | 31 | 16-50 | 21.9% | 48.2% | 81.1% | 16.3% |
| BUY pre-market -> in-session (part after 09:30) | 436 | 10 | 38 | 21-61 | 15.8% | 36.9% | 72.2% | 25.5% |
| SELL in-session -> in-session | 289 | 11 | 31 | 17-55 | 19.7% | 47.1% | 78.9% | 17.3% |
| SELL pre-market -> in-session (part after 09:30) | 271 | 3 | 44 | 25-72 | 13.3% | 33.6% | 64.6% | 34.3% |

- **Same-day brackets exist for 805 buys (43.3%) and 595 sells (32.0%).**
- **Brackets that run across the end of the stream:** 723 buys (38.9%) had their flat frame in-session and are first seen on a LATER date, so the buy is somewhere in the rest of that day, the night or the next pre-market; 1,068 sells (57.4%) were last seen in-session and are missing on a later date.
- **Already held before 09:35 ET:** 141 buys are first seen in-session before 09:35 (88 in the span), so they were bought by then: that morning, the prior afternoon or overnight. 35 of these have a flat frame on the same date, so the buy was that morning (14 in the span); a further 31 buys are first seen in a same-day pre-market frame. The 141 is the rule-free form of the earlier 'held before 09:35' count of 9, which was limited to the 264 dated buys of the account's window.
- Pre-market and after-hours trades are visible only as brackets that touch no regular session (the 34 inverted buys, 38 inverted sells): minute bars do not cover them (the fetcher stores 09:30-15:59 only).

## 3. Bars for 2020-01..2022-06

**Population:** buy windows with `hi` in 2020-01-01..2022-06-30 and sell windows with `exit_hi` in the same range. **Per window:** each session `lo..hi` is tested; a window is 'covered' only when EVERY session in it is (a one-session window is the strict case; a wide window can rarely be fully covered). **Bar symbol:** `sym_a` through 2022-03-31, `sym` after (the earlier reads' rule, `01_rev_frozen_e908253f7405.py` L987-988); daily = the 2016-22 export under `sym_a` OR the 2021-26 export under `sym`.

### 3.0 What is on disk

| daily source | rows | dates | note |
|---|---|---|---|
| daily export A `cb702_pre_v2/daily_closes_all.csv.gz` | 12,005,007 | 2016-01-04..2022-06-30 | keyed by TODAY's symbol (`tl` docstring); names later delisted or renamed away are absent |
| daily export B `cb702/daily_closes_all.csv.gz` | 13,830,569 read, 8,619,626 kept | 2021-09-27..2024-12-31 (kept) | symbol of the day; overlaps A on 2021-09-27..2022-06-30 |

| tree | path | what it was fetched for | date files (<= cut) | pairs ok / empty (<= cut) | dates |
|---|---|---|---|---|---|
| A | `cb702_pre_v2/minutes` | candidate-population fetch, era A | 1,219 | 149,476 / 111 | 2017-03-02..2022-01-03 |
| B | `cb702/minutes` | candidate-population fetch, era B | 691 | 80,747 / 111 | 2022-04-01..2024-12-31 |
| EP | `cb702/minutes_ep_1023` | EP gap days (targeted) | 48 | 196 / 0 | 2017-03-20..2023-06-08 |
| EP2 | `cb702/minutes_ep_1024` | EP gap days, 2nd pull (targeted) | 36 | 39 / 0 | 2019-10-28..2023-12-05 |
| REV | `cb702/minutes_rev_1024` | his early/late panel buys (targeted) | 508 | 1,302 / 20 | 2017-01-27..2023-12-14 |
| INTRA | `cb702/minutes_intra_1025` | hold windows of the 10-25 intraday read (targeted) | 1,005 | 19,184 / 286 | 2019-09-17..2024-01-16 |

The six are the trees named in `01_intra.py` (`MINUTES`, L149) and read through `_done.psv` fetch logs only (no minute file opened here). Three more folders on disk (`minutes_com_delta_1018`, `minutes_pre_com_1018`, `cb702_minutes_delta_out`) are not in that set; their logged pairs are all already in tree B and fill none of the gaps below. **Q1 2022 hole:** tree A stops at 2022-01-03 and tree B starts at 2022-04-01, so 2022-01-04..2022-03-31 has minute bars only where a targeted tree happens to cover it.

### 3.1-3.2 Coverage of the windows (daily and minute together)

| windows | n | every session has a daily bar | some sessions | no session | ...of which the name has no bars at all | daily: share of sessions | every session has minute bars | minute: share of sessions |
|---|---|---|---|---|---|---|---|---|
| **BUY, all widths** | 1,511 | 88.7% | 2 | 168 | 80 | 86.5% | 70.4% | 58.8% |
| BUY width 1 | 1,052 | 91.3% | 0 | 91 | 38 | 91.3% | 76.0% | 76.0% |
| BUY width 2-5 | 331 | 81.6% | 2 | 59 | 33 | 81.5% | 62.5% | 63.1% |
| BUY width 6-10 | 101 | 84.2% | 0 | 16 | 9 | 83.2% | 56.4% | 56.5% |
| BUY width 11+ | 27 | 92.6% | 0 | 2 | 0 | 90.7% | 3.7% | 11.4% |
| **SELL, all widths** | 1,538 | 88.8% | 1 | 172 | 80 | 88.0% | 60.5% | 51.9% |
| SELL width 1 | 1,016 | 89.9% | 0 | 103 | 41 | 89.9% | 64.9% | 64.9% |
| SELL width 2-5 | 410 | 86.3% | 1 | 55 | 32 | 85.4% | 56.8% | 55.3% |
| SELL width 6-10 | 87 | 86.2% | 0 | 12 | 6 | 86.2% | 37.9% | 42.8% |
| SELL width 11+ | 25 | 92.0% | 0 | 2 | 1 | 93.4% | 20.0% | 22.6% |

| windows | n | daily: every session | minute: every session | minute: at least one session |
|---|---|---|---|---|
| BUY 2020 | 803 | 87.7% | 73.7% | 73.8% |
| BUY 2021 | 583 | 87.8% | 67.9% | 68.8% |
| BUY 2022 (to 06-30) | 125 | 100.0% | 60.8% | 63.2% |
| BUY, 1080p-dense span 2020-01-27..2022-06-14 | 1,454 | 89.7% | 71.1% | 71.7% |
| BUY, not flicker | 946 | 90.8% | 75.8% | 76.5% |
| BUY, flicker | 565 | 85.3% | 61.4% | 61.8% |
| SELL 2020 | 814 | 88.0% | 65.6% | 66.6% |
| SELL 2021 | 589 | 87.3% | 58.1% | 58.9% |
| SELL 2022 (to 06-30) | 135 | 100.0% | 40.0% | 45.9% |
| SELL, 1080p-dense span 2020-01-27..2022-06-14 | 1,471 | 89.6% | 62.1% | 63.6% |
| SELL, not flicker | 971 | 90.8% | 61.2% | 62.5% |
| SELL, flicker | 567 | 85.2% | 59.3% | 60.7% |

**Why a window has no daily bar** (340 windows without any daily bar on any session; both kinds together):

- 340 windows, 89 names: 52 names have no bars anywhere in our files (`has_bars` False), and 37 names HAVE bars in some other period (`has_bars` True) but none in the window. `has_bars` is therefore not a window-coverage test.
- Windows ending before 2021-09-27 (only the 2016-22 export applies): 328; ending on or after 2021-09-27 (the point-in-time export applies): 12. So the gap is names absent from the 2016-22 file under the panel symbol: renamed names with no alias in the join (GSX -> GOTU and SBE -> CHPT: the bars EXIST in the 2016-22 file under the new symbol), delisted names the file does not carry (for example TCAC, VTIQ, FSR, NXTD), funds and ETNs (GBTC, ETHE, FNGU, TVIX), and symbols with no bars anywhere (NO). How many of the 340 are alias gaps is not measured here.
- Most frequent: GBTC 30, ETHE 28, FNGU 16, NO 14, SBE 14, GSX 12, TVIX 12, NXTD 12 (windows, buys + sells).

### 3.2b Pair view: every distinct (bar symbol, session) in all buy and sell windows of the span

|  | minute ok | logged empty | missing (no log row) | pairs |
|---|---|---|---|---|
| daily bar present | 3,114 | 0 | 1,921 | 5,035 |
| no daily bar | 25 | 17 | 688 | 730 |
| **all distinct (symbol, session) pairs** | 3,139 | 17 | 2,609 | 5,765 |

Minute pairs by tree (a pair is in exactly one tree here): A 716, B 27, EP 21, EP2 28, REV 1,093, INTRA 1,254. Candidate-population trees (A+B) supply 743 pairs; the targeted trees 2,396. The targeted trees were fetched around days our rules dated (E) or around his early/late buys, so coverage is denser near those days than elsewhere in a wide window.

| quarter | pairs | minute ok | missing (daily bar, no minute log) | no daily bar |
|---|---|---|---|---|
| 2019Q4 | 6 | 2 | 2 | 2 |
| 2020Q1 | 567 | 243 | 171 | 153 |
| 2020Q2 | 747 | 516 | 135 | 97 |
| 2020Q3 | 620 | 434 | 139 | 47 |
| 2020Q4 | 861 | 581 | 162 | 124 |
| 2021Q1 | 766 | 453 | 178 | 153 |
| 2021Q2 | 312 | 162 | 87 | 63 |
| 2021Q3 | 756 | 237 | 446 | 73 |
| 2021Q4 | 387 | 267 | 102 | 18 |
| 2022Q1 | 339 | 118 | 221 | 0 |
| 2022Q2 | 404 | 126 | 278 | 0 |

### 3.3 What is missing and what a fetch would cost

| fetch scope (buys + sells together) | pairs needed | of which missing | dates | requests (50 symbols each) | minutes at 0.465 s/request |
|---|---|---|---|---|---|
| windows of width <= 1 | 1,781 | 388 | 230 | 230 | 1.8 |
| windows of width <= 2 | 2,608 | 589 | 307 | 307 | 2.4 |
| windows of width <= 5 | 3,655 | 853 | 376 | 376 | 2.9 |
| windows of width <= 10 | 4,972 | 1,321 | 430 | 430 | 3.3 |
| all windows | 5,765 | 1,921 | 486 | 486 | 3.8 |

- **Missing** = a daily bar exists that session, no tree has a minute log row for the pair, and the pair is not logged `empty`. Pairs without a daily bar (730 here) are outside this count: a minute pull may or may not return bars for them (the A tree returned empty for 111 of 149,587 pairs, all retired or renamed symbols: `docs/methodology/backtest_data_standard.md` C2, L309).
- **Price:** the fetcher (`scripts/probes/_cb_backtest/fetch_minutes.py`) has no cost logic and its header says it pulls Alpaca SIP 1-minute bars, 50 symbols per request per date, 0.25 s pause. The registration of 2026-10-19 records the minute pull as **free** (`cb_2017_21_read_prereg_2026-10-19.md` L14); the 10-25 run of 19,470 pairs took 8.0 minutes and 1,032 requests (`cb_intraday_layer_prereg_2026-10-25.md` L58-59, L495-496), no charge itemised. Not run here. A pull needs the Alpaca data keys (the fetcher header says the production container holds them).
- **Scope note:** this sizes the windows only. The 10-25 fetch also pulled a 10-session warm-up before and a 20-session tail after each hold; any later design that needs the days around a window needs more pairs than the table.

## 4. Known blind spots, in numbers

| blind spot | number | source |
|---|---|---|
| Trades opened and closed between two streams (invisible round trips) | not countable from the file; bounds below | design of the panel |
|   sessions in 2020-01..2022-06 with no snapshot at all | 180 of 629 (28.6%), in 76 runs (1-session runs 52, longest 19) | `snapshots.tsv` vs the calendar |
|   trading hours never on screen on a stream day | about 82% of the 09:30-16:00 session (last in-session frame median 10:40 ET) | section 2.5 |
|   snapshots that are not full (cannot show a sale) | 825 of 2,907 (28.4%): 751 scrolled, 74 list reaches the panel bottom | `snapshots.tsv` `full_how` |
|   positions seen in one stream and gone within 5 sessions (flickers) | 659 of 1,874 | section 2.3 |
|   *quoted* (on the 264 breakout/EP-dated buys of the deciding span): first seen in session on E / after E's close / a session or more later | 172 / 75 / 17: only buys still held at a snapshot are seen | registration §1(h), L64-67 |
|   *quoted*: leave the panel by the close of the buy day (day trades or shorts) | 42 of 264 (EP-dated 11 of 43) | registration §1(i), L68-69 |
| Blip fill merges a real round trip into one hold | 118 of 125 fills sit over a footer-consistent absence (*quoted*); 125 (stream, name) pairs recomputed | registration §1(j), L70-72 |
| Single-frame drops cancelled (a name missing from one full frame, back before the next) | 229 (*quoted*) | `01_timeline.txt` |
| **The 47 fills that contradict the panel clock** | 47 (*quoted*; not recomputable here, it needs our ORH5 fill minute) | defined in the registration §7 'F5', L298-302; the number is in the RESULT block, L492 |
| Positions seen but not their side, size, adds or trims | a name already held creates no new entry: 280 of 684 names have 2+ entries (1,470 entries); 544 entries start within 14 calendar days of the same name's earlier sale window | registration §1(d): a short on a gap-up reads as a long |
| Initial holdings (buy before the first stream) | 13, all at 2017-01-27 | `entries.tsv` `initial` |
| Reader noise | ~2% per-symbol OCR miss (*quoted*, R3 row L402); 18 look-alike relabels; 21 clock misreads, all 2019 (*quoted*); 365 of 3,342 frames with no panel (*quoted*) | `01_timeline.txt` |
| Low-resolution streams | 253 buys first seen in the 1280x720 streams (hi 2019-09-30..2020-01-23), where symbols alternate between a name and its look-alike | `entries.tsv` `first_resolution` |
| Stream-date gaps over 30 days (*quoted*) | 2017-03-13->08-24, 2017-08-31->10-03, 2017-10-12->2018-08-29, 2018-08-29->2019-10-01, 2022-06-14->11-03, 2022-11-17->2023-01-26, 2023-01-26->05-18, 2023-06-09->12-01 | `01_timeline.txt` |
| Very wide windows (61+ sessions) | 48 buys, 114 sells (the sparse years) | section 2.2 |

**The 47, precisely.** For each filled trade in the 2020-01-27..2022-06-14 account, the registration compares our ORH5 fill minute with the panel's clock on the buy day E: a full snapshot on E that still shows him flat LATER than our fill means he bought after it; the first snapshot on E that already shows him holding EARLIER than our fill means he bought before it; the same minute is never counted (registration L298-302). It measures OUR fill minute against his clock, so for the as-is read the rule-free facts are the brackets themselves (section 2.5), not the 47. The same RESULT sentence quotes an account result; it is deliberately not carried here (outcome number, and it would anchor the as-is read).

Rule-conditioned panel-clock counts on the 264 dated buys (*quoted*, registration L174 and L415): held before 09:35 ET: 9; flat at an in-session full snapshot on E: 94 (50 at or after 10:00, 29 at or after 10:30; 92 on the 262-buy account after the two same-day re-buys leave, L174-176); bracketed on both sides within E: 53.

## 5. Other rule-free sources for steps 4-5

- **The panel's `% Change` cell, per held name, per frame** (`vision/positions_panel_all.jsonl`, `rows[].pct`; NOT carried into `snapshots.tsv`). 2,977 panel frames, 41,099 rows; a value was read on 39,137 (95.2%) and agrees with our daily bars on 34,355 (83.6%). The reader tests it either as an in-session range (2,613 frames) or as a close-to-close change (292 frames). Read per year: 2017 98.4%; 2018 100.0%; 2019 63.5%; 2020 97.1%; 2021 97.9%; 2022 97.8%; 2023 98.6%. It is a price-at-clock observation for every held name at every frame (change vs the prior close, per the reader's own check), so a bracket from section 2.5 can be paired with a price, not just a time. Whether it pins the minute is not measured here.
- **Captions:** 495 caption files (`qm_streams/subs/*.vtt`), `video_status.tsv` (588 videos), his spoken words with stream time. `stream_moments.tsv` (19,236 ticker-mention rows) mixes caption fields (`video, t, ticker, quote, window`) with keyword and base-feature columns (`kw_*`, `w_*`) that use our chart vocabulary: only the caption fields are rule-free.
- **Not rule-free:** `control.tsv` and the 236 labelled calls (dated to our event days E), `graded_moments.tsv` grades, and every `w_*` / `kw_*` column.

## 6. Reconciliation with the earlier printouts (my recomputation vs `01_timeline.txt`)

| item | here | printout | match |
|---|---|---|---|
| positions (entries.tsv rows) | 1,874 | 1,874 | yes |
| sale windows (exits.tsv rows) | 1,861 | 1,861 | yes |
| initial holdings | 13 | 13 | yes |
| flickers | 659 | 659 | yes |
| inverted buy windows | 34 | 34 | yes |
| inverted sale windows (recomputed) | 38 | 38 | yes |
| still held at the last snapshot | 13 | 13 | yes |
| snapshots | 2,907 | 2,907 | yes |
| full snapshots | 2,082 | 2,082 | yes |
| streams (distinct `vid`) | 517 | 517 | yes |
| blip-filled (stream, name) pairs | 125 | 125 | yes |
| look-alike relabelled snapshots | 18 | 18 | yes |
| buy window buckets 1 / 2 / 3-5 / 6-10 / 11-20 / 21-60 / 61+ | 1158 / 251 / 173 / 128 / 63 / 40 / 48 | 1158 / 251 / 173 / 128 / 63 / 40 / 48 | yes |
| sells by year 2017..2023 | 46 / 48 / 184 / 814 / 589 / 139 / 41 | 46 / 48 / 184 / 814 / 589 / 139 / 41 | yes |
| 1080p-era buys with a window: first_resolution 1920x1080 / 1280x720 | 1608 / 253 | n/a | n/a |
| exit_lo/exit_hi reproduced from snapshots.tsv (of 1,861) | 1,861 | 1,861 | yes |
| calendar equals the SPY sessions of both daily exports (2,264 sessions to 2024-12-31) | yes | yes | yes |
| initial holdings all first seen on 2017-01-27 | yes | yes | yes |

Method: every number above is recomputed from the four TSVs, `positions_pct_calendar.pkl.gz` (sessions, cut at 2024-12-31), the two daily exports (ticker and date columns only, rows after the cut discarded at read), and the six `_done.psv` fetch logs. The helper scripts were throw-away (session scratchpad, not committed); every definition needed to repeat a number is stated next to it. Items marked *quoted* are copied from `01_timeline.txt` or the 10-24 registration because the TSVs cannot reproduce them; none of them was recomputed.

