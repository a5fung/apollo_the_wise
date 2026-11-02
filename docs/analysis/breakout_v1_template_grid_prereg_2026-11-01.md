# Breakout v1 — the TEMPLATE GRID on the frozen 2017-2024 paper replay — pre-registration (2026-11-01)

**Status: REGISTERED, NOT RUN.** The chain of steps, the exit definitions, the pick rule, the bar and its calibration, the
lists at the lower strength gates and the minute request are written here before any outcome of exits B, C, D, of the
floor on top of them, of the wider lists or of the wider books has been read. What HAS been read: the frozen baseline
(`breakout_v1_paper_replay_prereg_2026-11-01.md`: FAIL in every row), the two follow-ups (the 15-cent floor helps in both
eras; the slot order is unproven) and the big-winners study (of 872 real big breakouts v1 listed 44%, bought 26%) — those
are the inputs this grid was built from, and the parity stage re-walks the baseline's own exit (A) on its own fills, an
already-known outcome. The `walk` runs ONCE, after the pre-pull commit, the minute pull for the new names and the footer,
and refuses otherwise. Offline research, $0, nothing live changes, no date >= 2025-01-01 is opened (THE LINE; #710's
seal). **This document recommends nothing about live money; every rule change it measures (exit, list, slots, stop) is
the operator's call.**

Code: `scripts/probes/_breakout_v1_replay_1101/template_grid_1101/grid.py` (stages `parity | population | request |
coverage | dryrun | pins | walk`; it IMPORTS the frozen `v1_replay.py` and never copy-edits it). Outputs: the same folder
(`list90/` the lists at the 90 gate, `minute_request.tsv`, `raw_close_request.tsv`, `out/dryrun.txt`, `out/calibration.txt`,
`out/parity.txt`; after the run `out/results.txt`, `out/cells.json`, `out/trades_grid.tsv.gz`).

## 0. In plain words

- **The question.** The baseline said the lane as built loses money and finds too few big winners. His 11-01 note set the
  TEMPLATE: Qullamaggie's profile — a low win rate (he says 20-30%) paid by more and bigger big winners, maybe at the
  expense of the small winners — and his own 205 trades under our rules are the benchmark (win 37%, median −1.0R, mean
  +1.06R, 2.9 of every 100 trades at 10R or better). This grid asks, one variable at a time, which of four changes moves
  the lane toward that profile: the EXIT (three ways of holding the winners longer beside today's), the 15-cent MINIMUM
  STOP, the STRENGTH GATE (today's top 2% vs the top 5% / 10%) and the SLOT COUNT (5 / 8 / 10).
- **How it is scored.** Every cell is the paper book as it runs (five shared slots, one position per name) at 2 cents a
  share each way, decisive trades only, exactly the baseline's primary row. The score is the average R per trade (with its
  95% interval) and the number of trades per 100 reaching 10R; the win rate is reported and allowed to FALL — it is never
  a target. Every cell is printed against his benchmark row.
- **How a step is decided.** Each step changes ONE thing. Its pick is made on 2017-21 only (the rule in §4), judged ONCE
  on 2022-24 against the bar of §5, and the next step carries that pick whatever 2022-24 said. The chain is fixed in §2
  before any number exists.
- **What it is not.** Not a verdict on his setup (his trades already pass); not a live change; not a search over many exits
  (three, each pinned to a definition already on file). A cell that reads TEMPLATE is a statement about THIS
  implementation on history; the live paper months then say whether it holds.

## 1. The four questions of the standard

1. **Decision served:** none on money. The grid gives him, for each of four levers, the direction and the size of its
   effect on the paper lane's history, read against his own profile. Whether to move any lever is his.
2. **What would change the reading:** the verdict class (§5) of each step's pick on 2022-24, and the direction of the
   effect on both eras (a lever that helps in-sample and hurts out of sample is noise).
3. **Not asked:** the entry and the day-low stop (held at the live rule in every cell); 2025-26 (sealed); dollar P&L and
   sizing (R only); the lane's safeguards (the daily-loss limit, the breakers — not in the primary book, as in the
   baseline); exits other than A-D; strength gates other than 98 / 95 / 90; slot counts other than 5 / 8 / 10.
4. **Control:** the baseline (cell step1_A = the frozen primary row, reproduced to the row by `parity`) is the control
   for every step; the synthetic populations of §5 calibrate what the bar can tell apart.

## 2. The chain — four steps, one variable each, stated in advance

| step | the one variable | the cells | carried from before | the pick |
|---|---|---|---|---|
| 1 | the EXIT | A (today's, the live code) · B · C · D (§3) | today's list, entry, stop; no floor; 5 slots | on 2017-21 by §4; judged once on 2022-24 |
| 2 | the 15-cent MINIMUM STOP | step 1's pick without / with the floor | step 1's pick | **no pick**: the floor is RE-CONFIRMED (its direction on each era is reported) and carried into step 3 regardless — it was chosen on 2017-21 and shown to help in both eras in the follow-up (`followup_tests_1101/RESULTS.md`); re-selecting it here would be a second look |
| 3 | the STRENGTH GATE | rs ≥ 98 (live) · ≥ 95 · ≥ 90, everything else live | step 1's exit + the 15c floor; 5 slots | on 2017-21 by §4; judged once on 2022-24; BOTH directions counted (real big breakouts gained, losing trades added) |
| 4 | the SLOT COUNT | 5 (live) · 8 · 10 | steps 1-3 | **no pick** — information for him (the slot count is his); the 31 refused big winners reported under each |

Reporting eras split on the breakout day as the baseline did: **2017-21** (E ≤ 2021-12-31) and **2022-24** (E ≥
2022-01-03). A step's pick is read on the 2017-21 line of the PRIMARY row (the capped book, 2c, decisive); every other
line (the other cells on 2022-24, the uncapped guard book beside every cell, the 0c cost) is reported with the same
words and decides nothing. The 2022-24 lines of the non-picked cells are printed because he asked for every cell against
his benchmark; they are not a second pick.

## 3. The exits — definitions, their sources, where each departs from its source

The entry, the fill and the initial stop (the day's low at the fill, re-priced until the fill, the true low read one
minute after it — his ruling 2026-10-29) are the FROZEN rows' in every cell: the exit side alone is re-walked, session by
session on the stock's daily bars from E+1 over the same 120-session horizon, on the same forward store the baseline chose
(the Q1-2022 seam rule, `v1_replay.walk_inputs`). The breakout day's minutes after the fill are re-read for every fill
(they are all held locally). The stall cut (no high at fill + 1R by the close of session 3 → everything sold at that
close) is part of today's exit and is KEPT in every cell — the cells vary the partial sale and the trail only, so the
cut is not a confound; the 10-22 grid's cells kept it the same way. The stop leg always reads first inside a daily bar
(a gap under the stop books the open); the horizon mark and the open-mark rule are the baseline's.

| exit | definition (exact) | source | how it is built here; departures |
|---|---|---|---|
| **A — today's** | a third at +2R (at the target, or at the open when a session opened above it; on day 0 the minutes after the fill); else a third at the close of session 3 only when that close is above the fill; the stop at the fill from the session after any third; the rest at the next open after the first close under the 20-day simple average (live from session 3, or from a +2R third); the stall cut | the live code: `breakout_pp_rules` (`day0_facts`, `session3_decision`, `trail_decision`, `stop_after_third`), held equal to the definition `consolidation_breakout_pp.walk_pp` arm `pp` | CALLED: `v1_replay.exit_one` (the live decisions, asserted equal to `walk_pp` event for event on every trade). `parity` re-walks it on all 6,588 frozen fills and asserts the events, R, free point and decisive flag equal the frozen rows — that is the proof that B, C, D are fed the baseline's bars |
| **B — no partial, 20-day trail, a quick reclaim forgiven** | NO third anywhere. The stop moves to the fill from the session AFTER +2R is first reached (a high at fill + 2R, or an open at/above it; on day 0, a minute high after the fill — the breakeven then rests from session 1, never inside day 0). The trail is live once +2R has been reached or from session 3. A close under the 20-day while live OPENS A WATCH at that session sj; a close at or above the 20-day at sj+1 or sj+2 CANCELS it (a later close under opens a fresh watch); with no reclaim by sj+2's close, everything left sells at the OPEN of sj+3. The stop and the stall cut keep running inside the window | the 10-22 exit grid, cell **`A20_X3_P0`** ("20-day · X3 reclaim forgiven · P0 no partial" — the cell that held the most doublers), `docs/analysis/cb_trail_variants_2026-10-23.md` §definitions and `_702_trail_variants_1023/trail_lib.py` (`X3_GRACE = 2`; the P0 breakeven rule; the trail-live rule) | RE-IMPLEMENTED (`grid.step_rule`, rule B). Departures from the source cell: the entry there was the breakout CLOSE with a 1-ADR stop and up to two re-entries; here the live ORH5 fill, the day-low stop and no retry (the baseline's). The source had no day 0; here the day-0 +2R touch after the fill counts as "+2R reached" (the stop at the fill from session 1), mirroring how a day-0 third makes today's trail live from session 1 |
| **C — the speed trail, no partial** | NO third anywhere; the P0 breakeven rule as B. The trail average is the **10-day when ADR20 at D is ABOVE 4.79%** (`cb.TRAIL_SPEED_ADR_CUT`, the top tercile of the discovery distribution, fixed 2026-10-18 — never fitted to his calls), **else the 20-day**; trigger = the FIRST CLOSE BELOW it while live (live once +2R reached or from session 3) → everything left at the next open; the stall cut | round 3's W2 speed arm (`docs/analysis/cb_qm_replay_round3_prereg_2026-10-24.md` §4: *"trail the rest on the 20-day average, or on the 10-day when ADR20 at D is above 4.79%; first CLOSE below, filled at the next open"*; `cb.HIS_EXIT_ARMS["d3_p33_tspd"]`, `consolidation_breakout.walk_exit` trail_mode "speed"), with the partial removed as the task defines C | RE-IMPLEMENTED (`grid.step_rule`, rule C). Departures: the round-3 arm sold a third at session 3's close and had no stall cut; here no third (P0, the 10-22 grid's reading) and the cut kept. The stop to cost and the trail going live once +2R is reached come from the 10-22 grid's P0 rule (C is the 10-22 cells `A10_X1_P0` / `A20_X1_P0` with the round-3 speed rule choosing the average), NOT from W2, which moved the stop to cost after its session-3 third — so without +2R, C keeps the day-low stop until the trail or the stop ends the trade, where W2 sat at cost from session 4. ⚠ 78% of the frozen fills have ADR20 above the cut, so C is the 10-day trail on most trades and the 20-day on 22%. C differs from B in TWO things (the average and the trigger): step 1 picks among four NAMED exits, not one knob |
| **D — a third after day 3-5 only in profit, then the 20-day trail** | NO +2R leg at all. A third sells at the close of the FIRST of sessions 3, 4 or 5 whose close is strictly ABOVE the fill (one third ever; none when none of the three closes above it); the stop at the fill from the session after that third; the rest at the next open after the first close under the 20-day (live from session 3, as today); the stall cut at session 3's close before the third decision (as today) | his words as recorded (`cb_qm_replay_round3_prereg_2026-10-24.md` §4, l.1946 *"sell 1/3 to 1/2 of the position after 3-5 days"*, then breakeven, then the 10/20-day trail), and today's session-3 third widened to the 3-5 window | RE-IMPLEMENTED (`grid.step_rule`, rule D) = today's exit MINUS the +2R leg, with the session third's window widened from {3} to {3, 4, 5}. The dry run asserts D == A (the live code) on every random path where neither takes a third |

**Day 0 under B, C, D** (`grid.day0_no_partial`): the minutes after the fill minute against the day-low stop only
(`cb.day0_walk`, the live stop-only walk — a minute opening under the stop exits at its open, else a low at the stop
exits at the stop), the highest high after the fill (`cb.day0_peak_high`, the stall cut's day-0 reach) and whether it
reached +2R. A day-0 stop-out is booked by the live `cb.day0_result_to_outcome`. Under A the day-0 facts are the live
`breakout_pp_rules.day0_facts` (the +2R third inside day 0, breakeven from the next minute) — 921 of the 6,588 frozen
fills took a day-0 third; those are the fills whose day 0 differs between A and the no-partial exits.

**What the live machinery cannot express for B-D (stated now):** the live code has only A. B, C and D have no poll, no
resting order, no 15:45 / 16:45 job, no retry — they are walks on settled daily bars. If one is ever chosen, the live
build and its divergences from this walk are a new registration; nothing here says what that build would do.

## 4. The pick rule and the noise yardstick (fixed now)

- **Pick** = the cell with the highest mean R per trade on the 2017-21 line of the primary row (n ≥ 100); two cells
  within **0.02R** of each other are a tie, and the tie goes to the higher count of trades per 100 at ≥ 10R; a full tie
  keeps the earlier-listed cell (today's first). `grid.pick`, tested in the dry run.
- **The noise yardstick for an exit** (no random-order floor exists for exits): the PAIRED per-trade difference X − A on
  the SAME filled decisive trades of the uncapped book (so the book's path dependence is out), month-block bootstrap of
  its mean (2,000 draws, seed 702, the baseline's bootstrap). "Beyond noise" = the interval excludes zero. Reported on
  both eras beside the pick; it does not override the pick rule, it labels it.
- For step 3 the same pick rule on the three gates; the recall / losers table is reported, not picked on.
- The win rate is printed on every line and is not in the rule.

## 5. The bar — TEMPLATE / FAIL / CAN'T TELL, in numbers, before the run; its calibration

Read on the primary row (the capped 5-slot book — the step-4 cells at their own slot count — at 2c, decisive trades) of
each step's PICK on 2022-24; every other line is reported with the same words and decides nothing. `grid.verdict_template`.

- **TEMPLATE** — all of: **n ≥ 100** decisive trades; **the mean's 95% interval has its lower end above 0**; **≥ 2.0 trades
  per 100 at ≥ 10R** (his 2.9).
- **FAIL** — all of: n ≥ 100; **the interval's upper end under +0.25R** (a quarter of his +1.06R, the baseline's reference);
  **under 2.0 per 100 at 10R+**.
- **CAN'T TELL** — otherwise, with the sub-reading named (the baseline's words, the tail statistic swapped from the ≥ 3R
  share to the 10R+ rate because the template is about the biggest winners): *tail present, mean not shown positive* (the
  big winners are there, the rest gives it back); *mean positive, tail thin* (the big winners are not found or not held);
  *n < 100*; *interval spans the bar*. The ≥ 3R share and the ≥ 5R rate are printed beside.

**Calibration** (`out/calibration.txt`, 300 replicates per cell, seed 702; every drawn trade carries its REAL fill month so
the month-block interval sees the real clustering — the baseline's method on its anchor `empirical_pp_c0_r.npy`, 13,063
structural breakouts of 2017-21 under this exact exit: mean +0.04R, win 35%, 1.2 per 100 at 10R+). Populations: **N** the
anchor as it is (the mechanical null); **W(μ)** N's winners scaled by one factor so the mean lands on μ; **M** 12% W(+1.05)
+ 88% N; **Q — his PROFILE**: the smallest winners dropped until the win rate is 25%, the rest scaled so the mean is +1.06
(it then holds 5.2 per 100 at 10R+, average winner +7.3R); **T — his TAIL**: win 25% and exactly 2.9 per 100 at 10R+ (the
mean then falls at +0.38R); **H — his BENCHMARK on both counts** (added after the 11-01 review, appended last so every
earlier row's draws are unchanged): the anchor's trades as they are (win 35%, his 37%), the winners raised to one power
(0.46) and scaled so that exactly 2.9 per 100 reach 10R AND the mean is +1.06R. The n grid holds the real era sizes (581 and 1,058 decisive trades in the baseline; 520 and
986 under the floor).

| population | n = 300 | n = 581 (2022-24) | n = 700 | n = 1,058 (2017-21) | n = 2,000 |
|---|---|---|---|---|---|
| N the null — TEMPLATE / FAIL | 1.7% / 33% | 0.0% / 37% | 0.3% / 39% | 0.3% / 52% | 0.3% / 65% |
| W +0.30R (2.1 per 100 at 10R+) — TEMPLATE | 21% | 33% | 37% | 39% | 55% |
| W +0.50R (2.8 per 100) — TEMPLATE | 49% | 78% | 81% | 93% | 99% |
| W +0.75R (3.6 per 100) — TEMPLATE | 80% | 97% | 98% | 100% | 100% |
| W +1.05R (4.5 per 100) — TEMPLATE | 94% | 100% | 100% | 100% | 100% |
| M (12% his + 88% null; +0.15R) — TEMPLATE / FAIL | 5% / 13% | 6% / 12% | 9% / 12% | 8% / 11% | 6% / 8% |
| **Q his profile (win 25%, +1.06R, 5.2 per 100)** — TEMPLATE | **89%** | **100%** | **99%** | **100%** | **100%** |
| **T his tail (win 25%, 2.9 per 100, +0.38R)** — TEMPLATE | 25% | 39% | 51% | 62% | 82% |
| **H his benchmark (win 35%, +1.06R, exactly 2.9 per 100)** — TEMPLATE | **83%** | **93%** | **94%** | **95%** | **100%** |

**What the bar can tell apart, stated before the run:** the null reads TEMPLATE 0-2% of the time at every n and FAILS
37% at the 2022-24 size, 52% at the 2017-21 size — so, as in the baseline, a CAN'T TELL on the data is NOT evidence of an
edge. **A correct build of a working setup passes: a population matching his benchmark on both counts (H) reads TEMPLATE
83% at n = 300, 93% at the 2022-24 size and 95% at the 2017-21 size; his profile with its richer tail (Q, 5.2 per 100)
89% at n = 300 and 99-100% from n = 581; W +0.75R passes 97% at the 2022-24 size and W +0.50R 78%.** So a build as
good as his own trades still misses the bar about 1 time in 14 at the 2022-24 size. The binding half at the era sizes is the MEAN: a population
with exactly his tail but a +0.38R mean (T) reads TEMPLATE only 39% at n = 581 — the sub-reading *tail present, mean not
shown positive* is what to read then, and it is the reading that says "the big winners are there, the exit or the entry
gives the rest back". A +0.30R population passes a third of the time at the era sizes: a modest real gain reads CAN'T
TELL here, as declared for the baseline.

## 6. Step 2 — the 15-cent minimum stop, as the follow-up defined it

The planned risk at placement = the buy level minus the day-low stop at the moment the order is placed, in RAW cents
(`followup_tests_1101/tick_facts.tsv.gz`, `width_raw_cents`, pinned; the follow-up re-evaluated the live tick on the
minute bars for all 18,094 placed rows and the frozen placement reproduced on every one). A row under 15 cents is NEVER
PLACED: it holds no slot, blocks nothing, and the book cascades. A new name (step 3) gets the SAME reading, computed in
the walk the way the follow-up computed it (`grid.placement_width_cents`: the live `breakout_v1_entry.evaluate` on the
minutes through the placement minute − 1, level minus the day-low stop, × the raw factor × 100) — never the re-priced
stop, which is lower and would widen the reading (the frozen `placed_stop` column carries the re-priced stop on 1,055 of
the 6,347 re-priced rows, so it is NOT used). `parity` checks the walk's reading against the follow-up's on 300 sampled
frozen placed rows (filled, cancelled and re-priced among them): 0 differences required. The floor removed 1,911 placed
rows in the follow-up; the counts under the new exits are reported.

## 7. Step 3 — the strength gate at 98 / 95 / 90: the lists, the request, both directions

**The lists.** `v1_replay.run_population` is CALLED with `breakout_v1.RS_MIN` set to 90 for the call (the live gate
`v1_gates` reads that module constant at call time; the module file is not edited; the constant is restored after) —
everything else is the baseline's population stage: the same pool, the same `cross_section_one_date` percentiles, the
same seven other gates, the same fund rule, the same ranking by rs_best. The 95- and 98-lists are the rows with rs_best ≥
95 / ≥ 98 of that one run. **The nesting check (`parity`):** the 90-list restricted to rs_best ≥ 98 must equal the frozen
98-list row for row on every column, the rank included (the rs gate is one of eight and the rank sorts on rs_best, so
the old names keep their ranks and the new names rank BELOW them — the live tick would walk them in that order).

| | era A (D ≤ 2022-03-31) | era B (D ≥ 2022-04-01) | both |
|---|---|---|---|
| list rows at rs ≥ 98 (the frozen list) | 39,119 (29.6 a night) | 21,952 (31.8 a night) | 61,071 |
| list rows at rs ≥ 95 | 80,050 (60.6 a night) | 44,939 (65.1 a night) | 124,989 |
| list rows at rs ≥ 90 | 124,828 (94.4 a night) | 70,215 (101.8 a night) | 195,043 |
| NEW rows at 95 (rs in [95, 98)) | 40,931 | 22,987 | 63,918 |
| NEW rows at 90 (rs in [90, 98)) | 85,709 | 48,263 | 133,972 |

**The new names are walked end to end** through the SAME entry code the baseline called (`v1_replay.simulate_entry`:
the live `breakout_v1_entry.evaluate` tick by tick, the #500 fallback, the re-price, the fill-stop check), the same data
abstains (`minute_daily_mismatch`, `minutes_no_rows`, `no_daily_bar_E`, the raw-close re-judgement of a `raw_src = 2` row),
then every exit. The frozen rows' entry side is reused as it is (a name's entry does not depend on the list's other
names); only the BOOK changes, because a new name admitted on one day holds a slot on the next.

**The minute request** (`minute_request.tsv`, `ticker · session_date · why`, pinned, never rewritten): every new row's
breakout day the stores do not hold (the baseline's ten minute stores plus its 11-01 pull), the `why` rule the baseline's
(`fill_possible` when E's daily high is above 99% of the level; `cap_occupancy_only` otherwise — a resting order holds a
slot until 15:55 and can block a real fill, so BOTH classes are pulled). **97,829 rows over 2,004 sessions**
(46,689 fill-possible, 51,140 cap-occupancy-only); by level: **47,935 rows belong to the 95-list** (rs in [95, 98)) and
49,894 to the 90-95 band; 36,091 new rows are already held. **The pull:** `scripts/probes/_cb_backtest/fetch_minutes.py`
in the prod container, Alpaca SIP 1-minute, `Adjustment.SPLIT`, into **`apollo_data/cb702/minutes_tgrid_1101/`** (its own
`_done.psv` / `_failed.psv`), input `cut -f1,2 minute_request.tsv | tr '\t' '|'`. **The coverage rule** is the baseline's:
every requested pair HELD or UNFETCHABLE (in that directory's `_failed.psv`), at most 2% unfetchable; otherwise `walk`
refuses. ⚠ The request is pulled WHOLE: a 95-only pull is a change of the registered step (98 vs 95 vs 90 → 98 vs 95)
and would be recorded as a disclosed event before the walk, never a quiet narrowing. **The raw closes:** 3,733 new
era-B rows rest on the split list alone (`raw_src = 2`); 674 of them fall inside the baseline's Polygon raw pull
(same ticker and date) and are re-judged from it; the rest (245 tickers, `raw_close_request.tsv`) take the
baseline's second pull format (Polygon v2 daily aggregates, `adjusted=false`, point-in-time by ticker, dates ≤
2024-12-31; `pull_raw_closes_polygon.py`) into `apollo_data/cb702/raw_close_tgrid_1101.csv.gz` + `.meta.json` (sidecar
`request_sha256` = the sha of this folder's `raw_close_request.tsv`). **This second pull is REQUIRED, not optional:** 3,059
of the 3,733 new `raw_src = 2` rows (82%) have no raw close without it, and the walk refuses when more than 2% of them are
missing — the baseline's bound, kept. A row still missing after the pull is the counted abstain `raw_close_missing`
(never traded, no slot).

**Both directions, per level** (the chain's exit + the 15c floor, 5 slots): (a) the **872 real big breakouts** of the
big-winners study (`big_winners_2017_2024.tsv`, set +100%, class `measurable_breakout`; his 11-01 clarification: the
population that judges breakouts): LISTED = a list row (ticker, D) with trough ≤ D ≤ the half-way date (the study's
window), FILLED = a listed night whose row filled in the uncapped walk, the CATCH = the first filled night, SLOT = the
catch admitted by the capped book, made money / ≥ 3R / ≥ 10R on the catch's R under the chain's exit — the study's own
funnel, re-counted (at 98 under exit A with NO floor it must reproduce the study's 380 / 231 / 63 — the walk's parity
check at its start). **In step 3 the funnel is counted AFTER the 15-cent floor** (fixed after the 11-01 review): a row
the floor removes is never placed, so it never fills, never counts as the catch, and its R never counts as a winner; a
later night of the same breakout that passes the floor becomes the catch. The step-3 row at 98 therefore differs from
380 / 231 / 63 by the floor's removals — that is the floor, not a parity failure; (b) the **losing trades added**: the
capped decisive trades at the level minus at 98 — trades added, losers (R ≤ 0) added, 10R+ trades added, real big
breakouts filled added. The pick is by §4 on the score; the table is information.

## 8. Step 4 — the slots and the 31 refused big winners

`apply_book` (imported) with 8 and 10 slots beside the live 5, on the chain (step 1's exit, the floor, step 3's gate).
The **31 refused ≥ 3R catches** are the big-winners study's: of the 45 catches that made ≥ 3R in the uncapped walk under
today's exit, 31 took no slot — 30 refused by the full slots (`block:max_positions`), 1 by the same-ticker guard (DAC).
Named now, with their R under TODAY's exit (the catch's first filled night; 26 of the 31 are real big breakouts, 5 are
other kinds): TSLA 2020-04-09 +52.9R, RKLB 2024-09-25 +47.0R, SOL 2020-12-14 +28.4R, PACB 2020-09-16 +27.7R, ALT
2020-06-22 +25.4R, GOTU 2020-06-15 +17.7R, SMR 2024-10-14 +17.5R, GOTU 2020-01-02 +16.9R, FCEL 2020-12-17 +16.3R, KPTI
2019-10-15 +14.6R, QFIN 2022-11-29 +11.8R, FLNA 2021-06-02 +11.5R, CLNE 2020-12-21 +10.7R, SPCE 2020-01-10 +8.9R, CRK
2022-03-24 +8.5R, FOLD 2017-07-06 +8.1R, AAOI 2017-02-13 +7.4R, ADMA 2024-06-03 +7.2R, GDS 2024-08-19 +6.9R, WPRT
2021-01-12 +6.7R, BTDR 2024-12-04 +6.5R, HUT 2024-11-08 +5.8R, INO 2020-06-23 +5.3R, BEEM 2020-12-16 +5.0R, ARM
2024-06-06 +5.0R, RIOT 2023-07-05 +4.4R, ENPH 2022-07-27 +3.8R, DAC 2021-01-05 +3.8R, VST 2024-03-19 +3.8R, RYTM
2022-08-02 +3.6R, MARA 2021-01-06 +3.2R. Under each slot count the walk reports how many of the 31 are admitted, and their
R under the CHAIN's exit (which may differ from the R above — the names are fixed by the baseline; their outcomes are not).
A catch removed by the 15c floor or whose night is not on the chain's list is reported as such. **Five of the 31 are
never scored** (their breakout day is after the baseline's cutoff 2024-07-10, so they are open at the seal under every
exit): GDS 2024-08-19, RKLB 2024-09-25, SMR 2024-10-14, HUT 2024-11-08 and BTDR 2024-12-04. They still hold slots;
the walk lists them apart as "admitted but open at the seal, never scored" and never adds their R to the admitted ones'
(RKLB's +47.0R above is an open mark, not a result). 26 of the 31 are decisive.

## 9. The books, the costs, the measures, the benchmark row

- **Books:** the PRIMARY row = the capped book (the same-ticker guard + the slots) through `v1_replay.apply_book`, one
  chronological event loop in the live tick's order (day → minute → list rank), the free point of every trade recomputed
  per exit (`free_point`: a trail sale at the next open frees before the first tick; a stop or cut on a daily bar frees
  at the end of its day; a day-0 exit at its minute). Beside every cell the GUARD-ONLY book (no cap). The lane book
  (the daily-loss limit and the breakers) is not run here — the baseline declared it approximate and kept it out of the
  verdict; its legs and risk fractions are still computed per trade so it can be run later without a re-walk.
- **Costs:** 2 cents a share each way in the RAW price scale on the entry and every exit leg (the primary); 0c beside
  (`r_0c` in the trades file). R = P&L / (fill − stop), no cost in the denominator.
- **Decisive** = mature (a terminal exit, or the 120-session mark with the next open available) AND E on or before the
  baseline's cutoff 2024-07-10; open marks and later E's are walked (they hold slots) and never counted.
- **Per cell, per era and all years:** n, mean R with the 95% month-block bootstrap interval, win rate, median R, the
  average winner and the average loser, the count and rate per 100 at ≥ 10R / ≥ 5R, the ≥ 3R share, the sum of R, the
  blocked counts per book, the rows the floor removed, the exclusions of the new names.
- **The benchmark row on every table:** his 205 holdings trades under our rules — n 205, mean +1.06R, win 37%, median
  −1.0R, 2.9 per 100 at 10R+ (`cb_holdings_replay_prereg_2026-10-24.md` §RESULT). It is a different population (his
  selection, 2020-22) under a different exit (the speed trail with a session-3 third); it is the profile to shoot for,
  not a control.

## 10. What this does not answer

- **In-sample picks.** The 2017-21 line picks; 2020 holds most of that era's big winners (75% of the +100% doublings of
  2017-21), so a pick can be a 2020 story. The 2022-24 judge is one era of ~500-600 trades: the calibration says a
  +0.30R population reads TEMPLATE a third of the time there — a modest real gain reads CAN'T TELL.
- **Three exits, not the exit space.** B, C, D are the three already on file; the trigger (close vs decisive vs
  intraday), the average, the partial size and timing have other values the 10-22 grid read and this grid does not.
- **The book is path-dependent across cells.** A longer-holding exit fills the five slots longer, so the capped cells of
  different exits are NOT on the same admitted trades; the paired X − A yardstick on the uncapped set and the guard-only
  line beside each cell carry the like-for-like reading.
- **B-D have no live build.** The poll, the resting order, the 15:45 / 16:45 jobs, the retry and the whole-share rules of
  the paper lane exist for A only; a live B, C or D would depart from this walk in ways not modelled here.
- **The entry and the stop are not varied**, nor the fill quality beyond the 2c / 0c rows; the adverse fill-minute row of
  the baseline (6 of 6,588 fills) is not repeated.
- **Step 3's list is 2-3× longer live.** The 95-list is ~60 names a night, the 90-list ~95: the grading load, the
  operator-facing list and the small-cap lane's slot use are not modelled; the walk's cap binds on the paper lane alone.
- **Step 3's precision is measured only through the book:** the losers added are the ones the chain's entry bought; a
  gate that admits more names also changes which old names get a slot, and the delta is net of that.
- **The 31 refused catches are the baseline's names**; a different exit, floor or list changes which winners are caught
  at all, so "how many of the 31 get a slot" is one fixed view, and the step-3 recall table is the other.
- **2025-26** is sealed; nothing here reads it.

## 11. The dry run, the parity, the smoke (run before any outcome)

**Dry run** (`out/dryrun.txt`): **31 hand-computed cases, 31 pass, 0 fail**, each asserting the exact session, price or R
— the 20-day arithmetic equals the live `sma_at_last` on 50 random paths; B: a watch at session 3 reclaimed at 4
(forgiven), a fresh watch at 6 expiring at 8, sold at the open of 9 (−0.350R); B not reclaimed by sj+2, sold at the open
of sj+3 (+0.700R); the stop firing inside a watch window (−1.000R); C: ADR20 4.80% → the 10-day, sold at the open of 4
(+0.300R) vs 4.79% → the 20-day, stopped at 5 (−1.000R) on the same path; the cut constant and the averages are the live
ones; D: a third at session 4's close when 3 closed under the fill, the stop at cost from 5 (+0.200R); no third when none
of 3 / 4 / 5 closes above the fill (−1.000R at the day-low stop); the third at 3 and only one third (+0.167R); sessions 3 and 4 under the fill, the third at
session 5's close (10.7), stopped at cost at 6 (+0.233R; added after the review); D equals
the live pp on a path where neither takes a third; same-bar ties under no-partial: a bar touching +2R and the stop books
the stop (−1.000R); a gap open above +2R then the stop in the same bar → the breakeven rests from the next session,
stopped at the day low (−1.000R) where A books +0.200R; +2R at session 1 → stopped at cost at 2 (0.000R); the stall cut
under no-partial (+0.400R) and its day-0 reach; day 0: A's third at 12.0 at minute 14 and the breakeven stop hit at minute
20 (+0.667R) vs the no-partial day 0 not stopped, +2R reached, gapped out at 9.9 on session 1 (−0.100R); a day-0 stop
booked by the live `day0_result_to_outcome` (−1.000R, minute 11); the book fields of a trail sale (freed at the open, one
2c leg, −0.350 → −0.390R); the four verdict words; the pick rule's three branches; the floor at 14.9c vs 15.0c and a placed
row without a width raising. **Fuzz:**
400 random day-0 + daily paths through A / B / C / D — every status in the vocabulary, every share sold once, R equal to
the events' own arithmetic; D == A on 232 paths where neither takes a third; B == C(20-day) on 157 paths where C's exit
is not a trail sale. ⚠ Most of those 400 paths stop out on day 0 (263-293 per exit), so D == A there is mostly trivial;
a **second fuzz of 400 day-0 survivors** (the day-0 minutes redrawn calmer until neither day-0 walk stops; added after
the review) holds the same invariants on paths that all reach the daily rules: D == A on 235, B == C(20-day) on 146; D's
third fell at session 3 / 4 / 5 on 151 / 2 / 0 paths — random paths rarely reach sessions 4-5 still open and under the
fill, so the session-4 and session-5 thirds rest on the two hand cases.

**Parity** (`out/parity.txt`): the A exit re-walked through this module's loaders and `v1_replay.exit_one` equals the
frozen events, R, free point and decisive flag on **every one of the 6,588 fills**; the capped book re-run on those rows
reproduces the frozen `adm_cap` on **all 18,094 placed rows** (blocked 11,808 / 1,260) and both era lines (2017-21 n 1,058
−0.153; 2022-24 n 581 −0.412); the walk's placement width equals the follow-up's on all 300 sampled placed rows. **The
recall funnel** of §7 run on the frozen data (today's exit, 98, 5 slots) reproduces the big-winners study on the 872 real
big breakouts exactly: listed 380 / filled 231 / took a slot 63 / made money 113 / ≥ 3R 40 / ≥ 10R 17 (an outcome already
on file; `walk` re-asserts the first three before any new number). **Nesting:** the 90-list (195,043 rows over the 2,012 nights, 96.9 a night) restricted to rs_best ≥ 98 EQUALS the frozen 98-list (61,071 rows) row for row on every column, the rank included; at ≥ 95 it holds 124,989 rows (62.1 a night).

**Smoke** (`walk --force-unfrozen --limit-days N --smoke-from <date>`; outputs to scratch only, every outcome line
suppressed, no R column written, no pick recorded): three runs on real bars through all four steps — 2017-01-03 .. 01-05
(12 fills, 354 new rows none held), 2020-06-23 .. 06-24 (18 fills; 583 new rows: 14 filled, 93 abstained, 49 cancelled,
68 never placed, 359 pending the pull) and 2023-03-30 .. 03-31 (26 fills; 292 new rows: 22 filled, 11 `raw_close_missing`
before the raw pull, 1 minute-daily mismatch). The A re-walk equalled the frozen rows on every fill in each; every book
and the 31-catch lookup ran. The first smoke crashed on an era with no decisive trade (a `mean_r` read on an empty
group) — fixed, disclosed here. No R of B, C or D has been read. ⚠ **Disclosed (the 11-01 review):** those three
smokes wrote each exit's `status`, `sessions_held` and `exit_kind` for B, C, D on about 56 real fills to the scratch
`smoke_rows.tsv.gz` and the status counts to `smoke_tally.json` — no R, but hold length is partly an outcome; whether the
registrar read those values is not recorded, so they count as SEEN; the exit definitions, the pick rule and the bar are
unchanged by this review's fixes. The smoke writer now drops those three columns and the status counts. A **fourth smoke** after the review's
fixes (2020-06-23 .. 06-24, the fixed writer) ran all four steps without error; on a few days no cell reaches n ≥ 100,
so its step headers name the pick rule's default (A, rs ≥ 98) — no information. The new row-level raw-close coverage
check was run against the baseline's raw pull alone: it reports 3,059 of 3,733 new `raw_src = 2` rows without a raw
close and refuses, as the walk would.

## 12. Freeze and run — once only, in order (the main loop)

1. **Pre-pull commit** of this document and the probe folder (`grid.py`, the two request files, `request_summary.json`,
   `list_coverage_new.tsv`, `out/dryrun.txt`, `out/calibration.txt`, `out/parity.txt`) → `freeze_commit`. The `list90/`
   tables (7.5 MB gzipped) stay OUT of git as the baseline's list tables did — their shas are in §13 and `walk` checks
   them on disk. The pin table (§13) was computed after the final dry run, parity and smoke; an edit to `grid.py` after it
   is a new table and a new commit.
2. **The two pulls** (§7): the minutes into `minutes_tgrid_1101/` and the raw closes of the 245 tickers into
   `raw_close_tgrid_1101.csv.gz` (+ sidecar), in either order; then `python3 grid.py coverage` until it prints no problem.
3. **The footer:** `python3 grid.py pins` prints the table and `doc_body` (the sha256 of every byte above the FREEZE
   marker); paste `freeze_commit = <hash>` and `doc_body = <sha>` below the marker. Nothing above the marker is edited
   after step 1.
4. **`python3 grid.py walk`** — refuses unless every pin of §13 matches the disk, the footer carries `freeze_commit` and
   a matching `doc_body`, the BASELINE registration's own body pins still match their artefacts (the live rule modules, the
   stores, the frozen list), the coverage rule holds (the minutes AND, row by row, a raw close for every new
   `raw_src = 2` list row within the 2% bound — checked before any outcome is computed), and no output exists. Runs once (~10-20 min: the 6,588 fills × 4
   exits, the ~134,000 new name-days through the live tick, then 13 books). Writes `out/results.txt`, `out/cells.json`,
   `out/trades_grid.tsv.gz`.
5. **The RESULT is pasted below the footer, never above it**, in plain words: per step the pick, its 2022-24 verdict, and
   every cell against the benchmark row. A crash on real data is fixed, disclosed (what crashed, the fix, a new
   `freeze_commit`), and the run restarted from scratch.

## 13. — FROZEN 2026-11-01 — the pins (`walk` reads this table)

| key | sha256 |
|---|---|
| grid.py | `8c182eb3a07587516438780cc44df5329a9fcb271c8eeabb483f42b132162d7f` |
| v1_replay.py | `4df7e73ef7f2bd21cfc8c46941f45255b0ba9f6fb62b69380ce4d3b41f39bcb7` |
| trades.tsv.gz | `a46561f5f4e3bed091538b9e49bc405f2c49194bbbdf403d5db45b82a4caa740` |
| tick_facts.tsv.gz | `6aeb0859ec139e4b28c1fc578155353d69c022f5a737119ff71da8cc0835aa9f` |
| big_winners_2017_2024.tsv | `353fb65a37b26efbd3c55b74be07d2554322f082af1fdfd6f69ce179b94dd2a6` |
| trail_lib.py | `0f83e6bad75a1cc0e8cfe50d25d158d572537d5bbad646fe924e6af8d902d375` |
| consolidation_breakout.py | `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b` |
| breakout_pp_rules.py | `0294d18aa51e812cde6096c19f8d94ccca5a40399889f16db288dd11cdf9958b` |
| list90/list_eraA.tsv.gz | `253e3141b8465fe32bc281bfa83e68d45855d27ce92b6af2d7aef404a5558d71` |
| list90/list_eraB.tsv.gz | `5fa38b73584aa11d47c7d5bf801fad870dc3fcc32de901fe7b9f5a0ace182969` |
| list90/nights_eraA.tsv | `8e8e48ca034e217fdb88420c68101cae1a544d06f0c716efb1d882c148f2dfca` |
| list90/nights_eraB.tsv | `973dc4a2c2c3a9a92727d6056879e8a667f9eb0ce0374304809fa9b3a5aef144` |
| minute_request.tsv | `19d518b74b60241d366a66929980f5e8bddcf122e6351cf52873ed156526fb89` |
| raw_close_request.tsv | `e4559e75c9ac68c385e6e181a176217b876c7f2b32ea54a41dd0e12ce5b6de04` |
| dryrun.txt | `f8341fcc65919d05a09fba8648d75edcc911f04b034294b7defb80111eeb8c7f` |
| calibration.txt | `5a215bc0ca083330ce64030b55e3317218b3376beabefbc335596df8c2b3c9c1` |
| parity.txt | `e149af619da103c11858f87f7d822495857bcb2576a8cdb670cbf309a28845bc` |
| empirical_pp_c0_r.npy | `f7d03d59dee4807ff799ce6d0bf14366f779802b1d86a08452cca2c1471043f9` |
| empirical_pp_c0_months.npy | `6187698d336506791d7b3b88f13dd3df763c4411f4f815260ad58403c9e6ef16` |

The baseline registration's own body pins (the five rule modules, the stores, the frozen lists, the minute request,
`v1_replay.py`) are re-checked by `walk` against that document's table; a change there refuses this run too.

Every byte above the next line is the frozen body (`doc_body`). Below it, the main loop pastes the freeze record and,
after the run, the results.

<!-- FREEZE -->
## Freeze record (the main loop; pasted after the pre-pull commit and the pull, before `walk`)

- freeze_commit = (pending)
- doc_body = f6e88c7c812d742622519b4afe08005ed643115726ae68f5415838d8f9b17579
- minutes_tgrid_1101 pull: (pending)
- raw_close_tgrid_1101 pull (+ sidecar request_sha256): (pending)
- coverage: (pending)

## RESULTS (pasted after the one run; plain words; every cell against his benchmark row)

- Step 1 — the exit: (pending)
- Step 2 — the 15-cent floor on the pick: (pending)
- Step 3 — the strength gate: (pending)
- Step 4 — the slots and the 31: (pending)
- What this read cannot say: (pending)
