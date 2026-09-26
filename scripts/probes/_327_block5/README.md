# Block 5 (2026-09-26) — P0 · P1 · P2 · P3 · P5 · P6 · P7

The write-up (the deliverable, with the fork) is `docs/analysis/327_exit_determination_2026-09-26.md`.

$0, read-only prod extract + offline replay. Raw CSVs are gitignored (regenerate with
`extract_p0.sh`); only scripts + the small JSON summaries are committed.

## Regenerate

```bash
./extract_p0.sh          # prod pull via ssh+psql, ~2M-4M CSVs, gitignored
python3 p0_completeness.py   # -> p0_summary.json
python3 p1_probe.py          # -> p1_summary.json (needs trigger.csv, daily_closes.csv,
                              #    intraday_day0_raw.csv from extract_p0.sh)
python3 p2_probe.py          # -> p2_summary.json + p2_fire_walks.csv / p2_control_walks.csv
                              #    (gitignored; per-row checkpoint outcomes for P3/P4)
./extract_p3.sh              # the ONE extra read-only pull: MA warm-up daily bars 2025-12-01..
                              #    2026-06-20 for the same names (daily_closes_warmup.csv, gitignored;
                              #    pulled 2026-09-26T20:26:04Z — see daily_closes_warmup.pulled_at)
python3 p3_grid.py           # -> p3_summary.json + p3_cells.tsv (every cell, both entry
                              #    conventions; committed) + p3_events.csv (33 MB, gitignored:
                              #    per row x stop x target decisions with straddle DATES, for P4)
python3 p5_abstain_direction.py   # -> p5_summary.json: the recorded outcomes of the 2,042 fires
                              #    the grid cannot walk on the incumbent stop vs the walked ones
                              #    (needs trigger.csv + p3_events.csv)
python3 p6_leaders_mgmt.py   # -> p6_summary.json + p6_cells.tsv (committed) + p6_events.csv (49 MB,
                              #    gitignored): leader selection x EP-style management (partial /
                              #    breakeven / trail) x 3 stops, both checkpoints, matched control,
                              #    the big-runner read (needs the P0 + P3 pulls; ~8 s)
./extract_p7.sh              # three more read-only pulls (gitignored): SPY/QQQ/IWM daily bars, the EP
                              #    scan log 08-20..09-25, mi_ep_alerts since July (ep_scan_log.pulled_at)
python3 p7_diagnosis.py      # -> p7_summary.json (committed) + p7_rows.csv / p7_q2_rows.csv (gitignored):
                              #    the DIAGNOSIS — cohort cut (EP-alert vs screen-rejected), the path (Q1),
                              #    fire vs P2's control with pre-entry features (Q2), buckets + runner AUCs
                              #    (Q3), the EP's own sessions 1-3 (Q4), loss shares (~4 s)
```

## P0 result — PASS, checkpoint stays s10

Population: 3,767 trigger rows (700 tickers), 3,304 settled. Completeness denominator
is fires whose session *k* has actually occurred by 2026-09-26 (never the fixed
population — a fire fired last week has no session-20 bar to be missing yet, that is
"not happened", not a hole; an earlier cut of this script conflated the two and wrongly
read 35% at s20 before the fix).

| | s10 | s20 |
|---|---|---|
| settled fires | 98.85% | 96.35% |
| clock-eligible (>=20 sessions elapsed, any status) | 97.86% | 95.80% |

Both populations agree closely -> the settled-only read is not a survivorship artifact
here. **s10=98.85% >= 90% and s20=96.35% >= 80% -> PASS, primary checkpoint stays s10**
(the 70-90% move-to-s5 rule never triggers).

Day-0 minute-bar hole (the judges' fix): of 2,437 settled fires whose walk needs
minute resolution (`fire_minute_et` not null and `day_low <= stop_price`), **2,213
(90.8%) have zero 1-min bars in `mi_intraday_bars`** for that ticker/day. 867 settled
fires never need minutes at all (daily-grade fire, or the day low never reached the
stop). This is the number P3 needs before deciding how day-0-needing fires without
minute coverage get walked (fold to a whole-day pseudo-bar, the same convention
`compute_settlement` already uses for daily-grade fires, or exclude them — an
operator/P3 design choice, not decided here).

## P1 result — PASS, and every non-match is explained

Wired to the REAL `compute_settlement` (imported, never re-implemented), fed inputs
assembled to mirror `_assemble_settle_window`'s exact fallback rules. Day-0 minutes,
when needed, come from one of three $0 sources tried in order: (a) `mi_intraday_bars`
already covers the (ticker, fire_date) -> real 5-min bars via the production
`to_rth_5min`, (b) the row's own `day0_resolved`/`day0_post_low/high` cache -> the
production `day0_pseudo_bars`, (c) neither -> the probe abstains (documented, not
attempted, never silently dropped from view).

- **1,283 of 1,297 attempted rows scored** (n >= the 500 floor); 14 abstained
  (`window_open` — ran out of forward calendar without a stop touch, see below).
- **M-none (the pass bar), SCORED reading: outcome exact match 1,281/1,283 = 99.844%;
  realized_r within 0.001R = 99.844%.** Both clear the >=99% bar.
- **STRICT reading** (denominator = all 1,297 rows a day-0 source existed to attempt,
  counting the 14 abstains as non-reproductions): **1,281/1,297 = 98.77% — below 99% on
  its own.** Reported because "reproduce row-for-row" can be read either way; the case
  below is why the scored reading is the one claimed.
- **M-trail (free cross-check): 100.0% on both**, after fixing a probe-only bug (see
  below) — a clean signal that the incumbent walk itself, not just its stop/target
  logic, replays exactly.
- **All 16 non-clean rows (2 scored-mismatch + 14 abstained) carry a clean-integer
  post-fire price-scale jump** (6x-80x, verified per-row against 10 distinct tickers)
  between the trigger row's own contemporaneous `day_high` and today's
  `mi_daily_closes` high for the same date. This is an **inference from price shape**
  (nearest-integer ratio, not a lookup against a corporate-actions source) but a strong
  one on penny stocks: a **stock split between the fire and this extract retroactively
  rescales `mi_daily_closes` while `entry_price`/`stop_price` stay frozen at the
  fire-time scale** — a data-adjustment artifact of replaying against a continuously-
  adjusted table, not a wiring defect in `compute_settlement` or in this probe.
  **Split-adjusted reading: 1,281/1,281 = 100%.** This is the reading claimed for PASS;
  the strict 98.77% would need a corporate-actions source (not available at $0) to
  confirm rather than infer the 16 splits.
- 2,007 settled rows (60.8%) needed day-0 minutes with no offline source available —
  abstained, counted, never dropped silently. This is the same fetch-cost tradeoff P3
  will face at scale; it does not affect the pass-bar verdict (n_scored already clears
  the floor) but bounds how much of the incumbent lane a $0 replay can currently touch.
  **P3 implication:** `day0_pseudo_bars` (the cache-based reconstruction) is only ever
  populated when a #616 ADR variant stays pending past its incumbent settlement — it is
  not a general substitute. For the ~60% of the settled population with no offline
  minute source, a from-scratch daily-grain re-walk has no minute path available either
  and will have to fold day 0 to a whole-day range, which is exactly the pessimistic
  daily-grade convention `compute_settlement` already uses when `fire_minute is None` —
  not a new design decision, just naming that the existing house convention already
  covers this gap.

**Bug found and fixed in the probe itself** (not in production code): the first cut
sorted `closes_before_fire` as `(close, date)` tuples — sorting by PRICE, not
chronologically — which silently corrupted the SMA trail seed. It never touched M-none
(which does not read that list) which is exactly how it surfaced: a trail-only
divergence (89.6%/76.0%) with a clean M-none pointed straight at the seed, per the
advisor's steer, rather than at the walk. Fixed in `p1_probe.py`
(`closes_before_fire = [... for d, v in sorted(daily_for_ticker.items()) ...]`).

## P2 result — PASS on the letter of the bar (one pattern clears), and the pass rests on the recorded entry price

**The question:** does any of the four patterns reach +2×ADR$ before −1×ADR$ more often
than buying the same names on a non-fire session of the same 20-session window? Unit =
EP-anchored ADR$ (the real `compute_ep_adr_dollar`, recomputed on today's adjusted price
scale and matched to the 1,098 stored values on 1,077; every miss is a split-rescaled
name). Population = SESSIONS ELAPSED (>=K after the fire by 2026-09-25), never settlement
status; re-entry shapes pooled into their rung as the 09-22 read did. Control = every
non-fire session of the window for the campaigns where that pattern fired, entered at the
close, same clock, same abstain rule. pess = stop checked first on every bar, opt = target
first. Day 0 mirrors `compute_settlement` (daily-grade fold; minute-grade uses real or
cached post-fire bars, else abstains when the day low reached the stop — 257 rows).

**The walker's own anchor first:** given the incumbent stop and no target, it reproduces
production's `stop_hit_date` / time-exit on **1,295 of 1,297 = 99.85%** of the settled rows
it can walk (the 2 misses are AIXI and NRSN, the same reverse-split rounding rows P1 found).

### s10, the primary checkpoint — fire rate vs matched control, +2ADR before −1ADR

| pattern | n fires | names | control n | pess fire / ctl → gap | opt fire / ctl → gap | drop-best-NAME (pess) | bar |
|---|---:|---:|---:|---|---|---|---|
| ep_low_reclaim | 1,028 | 452 | 4,920 | 13.2% / 15.7% → **−2.5pp** | 15.8% / 17.5% → −1.8pp | PDSB → −3.0pp | no edge |
| ep_close_reclaim | 790 | 384 | 3,940 | 16.2% / 19.0% → **−2.8pp** | 18.6% / 20.5% → −1.9pp | RNXT → −3.3pp | no edge |
| **ep_high_break** | 223 | 119 | 1,222 | 28.7% / 20.3% → **+8.4pp** | 31.8% / 21.7% → +10.2pp | VNRX → +7.1pp | **clears** (≥5pp, n≥150, ≥60 names, survives drop) |
| ep_close_620_prox | 1,099 | 438 | 4,519 | 12.2% / 15.0% → **−2.9pp** | 13.9% / 16.2% → −2.3pp | PDSB → −3.3pp | no edge |

s5 and s20 are in `p2_summary.json` (s20 is thin on the control side — 71–163 sessions —
because only window sessions ≤ 08-27 have 20 sessions elapsed). The kill rule ("all four
within ±2pp on both bounds") does NOT fire: three patterns sit 2.5–2.9pp BELOW control
under pess (outside ±2pp, on the wrong side) and the fourth is +8.4pp. Per the block's
literal rule the verdict is **pass**: at least one pattern shows entry edge.

### What the pass rests on — the recorded entry is not always fillable

`ep_high_break`'s daily-grade fires (and every `new_high_break` re-entry on every rung, via
`replay_level_break`) are resting stop-buys priced AT the level. The lane records the
LEVEL as `entry_price` even when the session OPENED ABOVE it — a stop-buy would have filled
at the open. 44 of the 177 level-priced high-break fires at s10 opened above the level
(median over-shoot 0.63 ADR), and the +2ADR target measured from the level is then only
~1.4 ADR from the real fill. Three reads separate "the pattern picks good sessions" from
"the level entry is a head start", all reported beside the bar and never in place of it:

| read (s10, pess unless stated) | ep_high_break | the other three |
|---|---|---|
| **FILLABLE stop-buy** — entry = max(level, fire-day open) for level-priced fires, unchanged for minute fires | **+2.2pp** (opt +5.8pp); drop-best-NAME PDSB → +1.3pp; would NOT clear 5pp | −3.0 / −3.5 / −3.0pp |
| fire entered at the fire session's CLOSE (same entry as the control) | **−0.3pp** | −0.9 / −2.1 / −1.1pp |
| by resolution, recorded entry | daily-grade +12.5pp (n=175) · minute-grade **−5.8pp** (n=48) | daily −11 to −16pp (level-priced re-entries, pess-folded) · minute −1.8 / −2.5 / −3.2pp |
| tail ladder, recorded entry: +4ADR / +6ADR before −1ADR, fire vs ctl | 14.9 vs 8.3 · 7.7 vs 3.8 | at or below control on every rung |
| tail ladder, FILLABLE entry | **9.1 vs 8.3 · 3.6 vs 3.8** — the 2× tail is gone | unchanged, at or below control |
| paired per-campaign difference (equal weight per campaign) | +14.0pp over 133 campaigns | −4.5 / −3.5 / −4.7pp |
| `first` shape only | +14.3pp (n=124); fillable +8.9pp (n=123) | −1.6 / −2.1 / −3.2pp |

So: **on the recorded entry, `ep_high_break` clears the bar; on a fillable entry it reads
+2.2pp pessimistic / +5.8pp optimistic and its tail is the control's.** The three pullback
patterns are below control on every read. This is the fact P3–P5 and the fork carry: P3
should run the high-break cells under BOTH entry conventions (the recorded level and the
fillable open), and the "lane is instrumented wrong" fork option has a concrete capture
behind it — the trigger row should record the fire-day open (or the actual first-touch
price) beside the level so the next 20 sessions answer this without a probe. ⚖ No stop, no
target and no convention is picked here.

### P4's inputs, per pattern at s10

Straddle-decided fires (s10 outcome differs between bounds): 26 / 19 / 7 / 19 of 1,028 /
790 / 223 / 1,099; straddle-decided control sessions 88 / 60 / 16 / 54. Day-0 abstains
(minute fire, day low reached the 1×ADR stop, no $0 minute source): 132 / 82 / 21 / 23.

## P3 result — KILL on the block's rule: 0 of 588 cells clear, under either entry convention

**The draws, listed before the run** (the block sized 294 = 7 × 7 × 6; this grid is
7 stops × 7 targets × **12** exits = **588** per convention). Exits = the block's six
(none · trail SMA10 · trail SMA20 · time s3 · s5 · s10) **+ `trail_max10_20`** (the
incumbent arm, the production `sma_trail_line`, so the lane's recorded exit sits inside
the grid as its baseline) **+ five arms drawn from his marked charts** (2026-09-23):
`sma21_2x` (a close below the 21-day SMA two sessions running — Boik), `ema23_2x` (the
same on the 23-EMA — TraderLion's "at least a partial", scored as a full exit),
`sma50_1x` (a close below the 50-DMA), `ema65_1x` (a close below the 65-EMA), and
`hv21_50_noreclaim2` — the FVRR caution: a close below BOTH the 21-day SMA and the 50-DMA
on volume >= 1.5x the prior 50 sessions' mean, having closed at/above at least one of them
the session before; a close back above the 21-day SMA within the next two sessions makes
it an add-on (no exit, scanning resumes), otherwise the exit is the close of the second
session after the break. Every definition is in `p3_grid.py`'s docstring; MA lines include
the session's own close, an EMA is seeded with its first N closes, a line needs N closes or
cannot exit (the live None-guard). **Tail-eligible draws: 324 of 588** (a 1R/2R target,
and a 1×ADR target over a wide stop, can never reach 3R — those cells are dead on arrival
for the tail leg, not draws in the noise sense). The noise band scales to <= 6 of 588 /
<= 3 of 324; a family is >= 50 / >= 28.

**Cross-checks first, both clean.** (a) The incumbent cell reproduces the recorded
settlement on **1,296 of 1,297** M-none and **1,295 of 1,297** M-trail rows the $0 day-0
sources can walk (the misses are AIXI and NRSN, P1's two reverse-split rounding rows;
2,007 rows have no offline day-0 minute source and are abstained, never scored). (b)
**Every (stop, target) cell at s10 under exit none / time s5 / trail_max matches the REAL
`compute_settlement(target_r=…)` on the same scaled inputs: 107,604 of 107,604** — the
only production change the block allows (an inert-by-default `target_r`, existing tests
byte-identical and results diffed, mutation proof + lane-never-sets-it pin appended to
`tests/test_delayed_entry_shadow.py`) is the oracle for the grid's own scorer. 329
(stop, target) rows are excluded from (b) because the grid walks real post-fire 5-min bars
whenever they exist while production only consults minutes when the day low reached the
stop — the grid is the more informative of the two on those, and they are counted.

**The bar, applied on the width-floored (>= 0.5% in the cell's OWN stop units) s10
population, every leg at once: mean R > 0 · >=3R rate >= 3.0% · both time halves > 0
(split at fire_date 09-08; the second half is the four fire dates 09-08..09-11, n = 217–256
per cell) · >= 3 of 4 patterns mean > 0 · survives dropping the best NAME by summed R ·
n >= 300.**

| | recorded entry (the bar) | fillable entry (beside it) |
|---|---:|---:|
| cells clearing every leg | **0 of 588** | **0 of 588** |
| cells with mean R > 0 (pooled) | **0** | **0** |
| cells with >=3R rate >= 3% | 203 | 170 |
| both halves positive | 0 | 0 |
| best pooled mean R | −0.10 (`adr_150/1ADR/ema65_1x`, n=3,314) | −0.12 |
| cells clearing mean+tail only WITHOUT the floor | 0 | 0 |
| incumbent baseline cell (`incumbent/none/trail_max10_20`) | n=1,320, mean −0.29, >=3R 2.6%, H2 −0.48 | n=1,323, −0.33, 2.3% |

So the kill rule fires on its first arm — **zero cells clear** — and not through the
floor: no cell even has a positive pooled mean before the floor is applied. The
>=3R leg is met by 203 cells (tightest stops, 3R/3ADR targets, exits that let a run
extend), but every one of them carries a negative mean and a negative second half, so
the tail exists and the stop-outs around it cost more than it pays.

**Tail-first, per pattern (recorded entry):** the three pullback patterns have no cell
with mean R > 0 at n >= 50 (best means −0.09 / −0.05 / −0.10; their >=3R rates reach
15%/17%/14% only in cells whose mean is negative). **`ep_high_break` alone has 189 cells
with mean > 0 and >=3R >= 3% (n = 181–235), best +0.69R at `adr_025/none/ema65_1x`** — and
all three of P2's caveats land on it at once: (1) on the FILLABLE entry (a resting stop-buy
fills at the open when the session opens above the level) it has **0** such cells and its
best mean is −0.001; (2) the positive cells cluster on the tightest stop (0.25×ADR under a
level entry), the head-start P2 measured; (3) on the second time half its n is **23**, and
across those 189 cells its second-half mean tops out at +0.06R (positive in a handful of
cells, negative in the rest — a four-fire-date read that cannot carry a leg either way). The pattern's own incumbent cell reads −0.004R (n=181, >=3R
3.8%). It is one pattern on one entry convention on one time half — the block's >= 3-of-4
and both-halves legs are exactly the guards that keep it from being called a finding.

**What the exits did (stop = 1×ADR, no target, s10):** the trail arms fire on 66–78% of
fires and cut the mean from −0.37 (none) to −0.22..−0.26 while cutting the >=3R rate from
3.1% to 1.4–1.8%; `sma50_1x`/`ema65_1x` fire on 64–69% (these EP names mostly sit BELOW
their 50/65-day lines at the fire — a penny-stock gap inside a downtrend, not a leader
above a rising average); `sma21_2x`/`ema23_2x` fire on 52–54%; `hv21_50_noreclaim2` fires on
**0.3%** — the heavy-volume cut-through-both-and-no-reclaim shape is real but the stop
almost always arrives first, so that arm reads as "none" here. No exit arm turns any
stop/target cell positive. A target of 1R/1×ADR is reached on 32%, 2R on 15%, 3R on 8%
(stop-first); the straddle-decided count per cell is in `p3_cells.tsv` (e.g. 70 fires for
`adr_100/2ADR`) with the straddle session DATES per row in `p3_events.csv` for P4.

**Population honesty:** 3,398 fires have >= 10 sessions elapsed. The incumbent stop is
scorable on only ~1,320 of them (2,042 abstain: a minute fire whose day low reached its
tight stop, no $0 minute source); the ADR stops widen out of that hole (adr_100 abstains
236, adr_150 75). `prior_low` kills 298 fires at birth (the prior session's low sits at or
above a reclaim entry). Both are counted per cell (`n_killed`, `n_abstain`), never scored.

⚖ **THE LINE:** nothing here picks a stop, a target or an exit. The grid is the deliverable;
the fork is P5's to state.

## P5 — the line item P3 left: which way do the 2,042 unwalkable fires lean? (they lean nowhere)

P3 scores the incumbent-stop cells on ~1,320 of the 3,398 s10 fires; 2,042 abstain (a minute-grade
fire whose day low reached its tight stop, no $0 minute source). Production settled them live, so
`trigger.csv` carries their recorded outcomes. `p5_abstain_direction.py` rebuilds the grid's own s10
population (elapsed via the real `_trading_days`), takes SCORED = the ids in `p3_events.csv` for
(recorded, incumbent, none), KILLED = stop at/above entry (3), ABSTAINED = the rest — the counts
reproduce P3's (1,353 / 2,042 / 3) — and compares the recorded columns, width-floored at >= 0.5%
like the cell:

| recorded, incumbent stop (floored) | walked n=1,325 (1,116 settled) | abstained n=1,961 (1,916 settled) |
|---|---:|---:|
| outcome = stop | 97.3% | 98.3% |
| trail arm >= 3R | 1.5% | 1.8% |
| trail arm median R | -0.94 | -1.00 |
| mfe reached +3R | 11.7% | 14.5% |
| `ep_high_break` | n=211, 89% stopped, trail >= 3R 1.7% | n=26, 26 of 26 stopped at -1.00R |

Same lane on both sides; the hole hides no winners, and for `ep_high_break` the grid's walkable
subset is the slightly flattering one. The no-target MEAN is not read on either side: a stop is
always exactly -1.00R, so a mean above -0.95 at a 98% stop rate is a few enormous near-zero-stop
time-exits (max +1,599R unfloored, +22.66R floored) — the 09-22 artifact. A minute fetch for the
2,042 would fill cells without moving the answer. Verdict and fork: the analysis doc.

## P6 — leaders + EP-style management (his 09-26 response to Block 5): NO LIFT, 0 of 122 cells clear

The write-up (the deliverable, with the fork) is `docs/analysis/327_leaders_ep_management_2026-09-26.md`;
the probe's docstring is the pre-registration of record (committed before any result, `2868bdc2`).
Draws: 2 selections (all / leaders: >= $5, above a rising 50-day, above the 20-day) x (M0 + 3 stops x
20 arms) = 122 per checkpoint; s20 the bar, s10 beside it. Arms: M0 = the lane's recorded trail; M1 = the
LIVE MAGNA53 stack via `rule_eras.exit_rules_as_of` + `live_fill_counterfactuals.stack_walk_inputs` +
`walk_arm(harvest="live_ladder")` in two declared ORB-R frames; 18 grid arms = partial 1/3 at +2R/+3R x
breakeven at +1R/+2R/after the partial x remainder on SMA10 / SMA20 / held to s20. Gap-charged R.

| | s20 (bar) | s10 |
|---|---:|---:|
| cells clearing | **0 of 122** | **0 of 122** |
| cells with mean R > 0 (either selection) | 0 | 0 |
| best mean, all fires | -0.07 (adr_050 / P2_B1R_sma20, n=864) | -0.20 (incumbent / P2_B1R_sma10, n=1,316) |
| best kept>=3R, all fires | 4.4% (adr_100 / P3_Bpart_hold, mean -0.34) | 3.6% |
| leaders: mean range / best kept>=3R | -0.49..-1.06 (n=18-33) / 1 of 19 | -0.48..-0.84 (n=73-130) / 2.8% |

Leaders read WORSE than the population in every cell (M0 stops 99.2% of leader fires, n=117); the matched
non-fire control beats the fire cells on mean in 40 of 40 cells at both checkpoints. Runner read (120 ran
+50%, the lane fired on 102 = the addendum's 102): hold-with-breakeven keeps >=3R on 26% of runner fires
(82 of 320) vs 5.6% for M0 (15 of 267), runner mean +2.15R — and the other 91% of fires cost -0.69R vs
-0.55R under M0, net -0.35R/fire. Validation: (a) 1,296/1,297 and 1,295/1,297 vs recorded; (b) 784 exact vs
`walk_arm(trail_only)`, 235 = the live ladder's resting stop ratcheted to the trail line and hit on the LOW
(a mechanism difference: live exits on an intraday touch of yesterday's MA, compute_settlement on a close
below), 11 = the day-0 close in the SMA window, 3 pending at a hole.

## P7 — the diagnosis (his 09-26 question: "we need to understand what the issue is")

The write-up is `docs/analysis/327_delayed_entry_diagnosis_2026-09-26.md`; the probe's docstring is the
pre-registration of record (committed before any result, `0f8fa521`). Population = the 3,398 fires with >= 10
sessions elapsed, cut FIRST by what our own EP screen did on the gap day (live `mi_ep_alerts` join; scan-log
rejection stage). Outcome = the lane's own arm at s10 from production's recorded settlement (+ the 259 still-open
rows walked with the real `sma_trail_line`), Block 5's 0.5% width floor applied. Anchors: the walk reproduces
production on 1,139 of 1,141 settled rows; this read on P3's own ids is -0.283R vs P3's verified -0.290R.

| | value |
|---|---|
| fires on campaigns our screen REJECTED on the gap day | 3,347 of 3,398 (98.5%); 3,460 of all 3,767 fires — 92% at the universe floor, 783 campaigns for a prior close under $5 |
| fires on real EP alerts | 51 (44 floored) on 15 names; 22 alert campaigns / 100 fires in the whole extract |
| total R10, floored (n = 3,228) | -1,278.6R, mean -0.40R, 88.9% stopped by s10, 2.26% kept >= 3R |
| stopped on the fire session / within two sessions | 1,383 (42.8%) = 108% of the loss / 2,346 (72.7%) = 135% of the loss; the 882 survivors net +451.5R (+0.51R a fire) |
| ten sessions after a same-session stop | 72% below the stop level, 21% above the entry (n = 1,370) — the stock kept falling |
| fire vs P2's matched control, both at the close, +2ADR before -1ADR | 15.4% vs 17.4% (n = 3,358 / 7,853); within-stratum -2.0, composition +0.05 — not overhead, not the bounce; the reclaim session itself |
| real-EP cohort | -0.81R mean, 68% stopped within one session, 0 kept >= 3R; fires 6 of 51 vs control 21 of 58 reach +2ADR first; the fires arrive after a +1.5 ADR three-session bounce (control +0.06) |
| runners (+50% campaigns, 324 fires) | 0 on alerts; AUC adr20 0.72, stop width 0.68, price 0.34 — volatility proxies only; ep_score / catalyst / theme DARK on 98% |
| EP failed within 3 sessions (a close below the EP low) | 467 of 931 campaigns; 52% of fires, 73% of the loss — but on fires at session >= 4 (label knowable) HELD -0.46 / FADED -0.40 / FAILED -0.34: no separation |

Files: `p7_diagnosis.py` -> `p7_summary.json` (committed) + `p7_rows.csv` / `p7_q2_rows.csv` (gitignored);
`extract_p7.sh` -> `index_daily.csv`, `ep_scan_log.csv`, `ep_alerts.csv` (gitignored) + `ep_scan_log.pulled_at`.

## Files

- `p6_leaders_mgmt.py` -> `p6_summary.json` + `p6_cells.tsv` (+ gitignored `p6_events.csv`) — the P6 read above.
- `p5_abstain_direction.py` -> `p5_summary.json` — the abstain-direction read above.
- `extract_p0.sh` — the one prod extract (gitignored CSV outputs).
- `p0_completeness.py` -> `p0_summary.json` — bar-completeness / abstain-rate / day-0
  minute-hole read + the pass-bar verdict.
- `p1_probe.py` -> `p1_summary.json` — the settlement-replay probe + the pass-bar
  verdict + the full mismatch/abstain detail with split-ratio annotation.
- `p2_probe.py` -> `p2_summary.json` (+ gitignored `p2_fire_walks.csv`,
  `p2_control_walks.csv`) — the ADR$ entry-edge grid vs the matched control, both
  bounds, s5/s10/s20, the tail ladder, the fillable-stop-buy read, the walker's anchor.
- `extract_p3.sh` -> `daily_closes_warmup.csv` (gitignored) + `daily_closes_warmup.pulled_at`
  — the MA warm-up pull for the chart-drawn exit arms.
- `p3_grid.py` -> `p3_summary.json` (verdict, cross-checks, per-convention counts, per-pattern
  tail-first), `p3_cells.tsv` (all 1,176 cells: n / mean / >=3R / halves / per pattern /
  drop-best-name / exit-fired / straddle / opt-bound / gap-charged / every leg), gitignored
  `p3_events.csv` (per row x stop x target: pess/opt decision, straddle date, exit sessions).
