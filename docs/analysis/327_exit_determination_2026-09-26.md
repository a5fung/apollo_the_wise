# #327 Block 5 — is there any stop × target × exit under which a delayed-entry pattern pays? NO, on this population

> ⚠ **POPULATION NOTE (2026-09-26, verified):** this analysis measured the lane's pre-09-01 cohort — 98.5% of its
> ten-session fires are on names our EP scan did NOT alert (EP dates 08-24 to 08-28, 86–88% under $5), the population
> the 09-01 ruling voided; since 09-01 the lane enrols only EP alerts. Its conclusions describe that cohort, **not
> real EPs**. On real EPs the live lane has 51 fires on 15 stocks — too few to judge. See
> `327_delayed_entry_diagnosis_2026-09-26.md` §VERIFIED.


**2026-09-26 (Saturday build slot).** **0 of 588 stop × target × exit cells clear the pre-registered bar at
session 10, on the recorded entry AND on a fillable entry (1,176 cells in all); no cell has a positive
pooled mean (best −0.10R, n=3,314); and the one pattern that showed an entry edge, `ep_high_break`
(+8.4 points over a matched control, n=223), keeps +2.2 points once the entry is priced where a resting
stop-buy would actually have filled, with 0 positive cells under that entry.** The block's fork therefore
lands on option 3: **delayed entry is dead on this population; what would revive the question is listed
at the end.** Nothing is picked here — no stop, no target, no exit (THE LINE).

Every pass bar and kill rule below was fixed in `docs/roadmap/fable-weekend-blocks.md` §Block 5 before
any number was seen and is applied on its letter. The per-phase evidence is
`scripts/probes/_327_block5/` (README, `p0..p5_summary.json`, `p3_cells.tsv`); this document is the
read of those files, not a re-derivation.

## The decision it serves

His ruling of 2026-09-22 on #327: *"aligned, we need to find the right entries and exits for any new
setups, those are undetermined."* The four numbers in the 09-22 read (all four patterns negative,
30 of 2,980 reaching 3R) measured the PLACEHOLDER stop each pattern shipped with, not the patterns. This
day asks the question that ruling left open, in the block's words: **is there any stop × target × exit
combination under which one of the four delayed-entry patterns pays — beyond what buying the same names
on a random session in the same window would have paid?** The k-ladder reported on 09-22 is RETRACTED
and is not cited here; every path below is re-walked from bars.

## Method and population

**Population: every row of `mi_delayed_entry_trigger` — 3,767 fires on 700 tickers, fire_date 2026-08-25
→ 2026-09-25, extracted once on 2026-09-26 (`extract_p0.sh`) together with `mi_daily_closes` for every
name 2025-12-01 → 2026-09-25 and the day-0 minute bars that exist in `mi_intraday_bars`.** (The 09-22
read's window ended 09-21 with 3,652 rows; the four later fire dates add 115 rows, none of which has
10 sessions elapsed, so no s10 cell reads them.) The lane
watches every EP name for 20 sessions and fires four patterns — `ep_low_reclaim`, `ep_close_reclaim`,
`ep_high_break`, `ep_close_620_prox` — each with a recorded entry and stop; it is a passive observer, not
conditioned on outcome. Conventions, all pre-registered in the block or in the probes' docstrings:

- **The population of every cell is defined by SESSIONS ELAPSED — fires with ≥10 sessions after the fire
  date by 2026-09-25 (n=3,398) — never by settlement status.** Session 10 is the primary checkpoint
  (fixed by P0's completeness table, below); session 20 is secondary.
- **The walker is production's own `compute_settlement`**, imported, never re-implemented; the grid's
  scorer is checked against it cell by cell (P1, P3 cross-checks). The one code change the block allows
  is an inert-by-default `target_r` parameter on that function — the lane never sets it, the 67
  pre-existing tests are byte-identical before and after, and a behavioural pin proves the lane's settle
  path never passes it. **Nothing is deployed.**
- **Day 0** mirrors production: a daily-grade fire folds the whole fire-day bar; a minute-grade fire walks
  post-fire 5-minute bars from a $0 source (real `mi_intraday_bars`, else the row's own cached
  `day0_post_low/high`), else ABSTAINS when the day low reached that stop. Abstains are counted per cell
  and never scored; the first missing daily bar abstains every checkpoint at or beyond it.
- **Price scale:** 158 fires on 26 names had been retroactively rescaled in `mi_daily_closes` by a
  post-fire split; every fire-time input is rescaled by `close(fire_date) / trigger.day_close` rather than
  dropped. ADR$ is the real `compute_ep_adr_dollar` on the same table (matches 1,077 of the 1,098 stored
  values; every miss is a split-rescaled name).
- **Within a session:** stop (low) → target (high) → close-rule exit (close). A bar holding both stop and
  target resolves PESSIMISTICALLY (stop first); the optimistic bound is carried beside it and the
  straddle count is reported per cell.
- **Width floor:** every cell's legs are read on rows whose stop is ≥0.5% wide **in that cell's own stop
  units** (the 09-22 near-zero-stop rule, re-applied per cell so a wide stop cannot inherit a tight
  stop's floor).
- **Unit for the entry question (P2):** ADR dollars, not R — a unit the stop cannot contaminate. Control =
  every non-fire session inside the same (ticker, 20-session window) for the campaigns where that pattern
  fired, entered at that session's close, same clock, same abstain rule.
- **Two entry conventions, both run in full in P3:** RECORDED (the lane's `entry_price` — the bar as fixed)
  and FILLABLE (entry = max(level, fire-day open) for level-priced fires; unchanged for minute fires). See
  "What the P2 pass rests on" for why the second exists.
- **Time halves:** split at fire_date 2026-09-08; the second half is four fire dates (09-08..09-11) and is
  reported with its n everywhere it is used.
- $0 throughout: one read-only prod extract plus one read-only warm-up pull for the 50-day / 65-day
  lines; no paid API call; no toggle, table or PLAN.md touched.

## The bars, and what each phase returned

| phase | bar (fixed in advance) | returned | verdict |
|---|---|---|---|
| P0 bars complete? | ≥90% of settled fires complete through s10, ≥80% through s20; 70–90% at s10 moves the checkpoint to s5; <70% kills the day | **98.85% at s10, 96.35% at s20 (settled, n=3,304)**; clock-eligible cross-check 97.86% / 95.80% (n=1,214); day-0 minute hole: **2,213 of 2,437 settled fires needing minute resolution (90.8%) have no `mi_intraday_bars`** | PASS — checkpoint stays s10 |
| P1 walker reproduces production? | ≥99% exact `outcome` match and ≥99% `realized_r` within 0.001R on ≥500 settled rows | **1,281 of 1,283 scored = 99.84% on both** (M-none); the incumbent trail arm 1,283 of 1,283 = 100%; strict reading with the 14 abstains as failures 1,281 of 1,297 = 98.77%; all 16 non-clean rows carry an inferred 6×–80× post-fire split; split-adjusted 1,281 of 1,281 = 100% | PASS (scored reading claimed; strict reported) |
| P2 an entry at all? | +2ADR before −1ADR at s10 beats the matched control by ≥5 points under the pessimistic bound, survives dropping the best NAME, n≥150 fires on ≥60 names; all four within ±2 points on both bounds kills the day | three pullback patterns **2.5–2.9 points BELOW control** (n=1,028 / 790 / 1,099); `ep_high_break` **+8.4 points (n=223, 119 names), +7.1 after dropping VNRX** | PASS on its letter (one pattern); kill rule not fired — the three are outside ±2 on the wrong side |
| P3 the grid | a cell is a candidate only if ALL hold at s10: mean R > 0 · ≥3R rate ≥3% · positive on both halves · positive on ≥3 of 4 patterns · survives drop-best-NAME · n≥300 after the width floor in its own units; zero clearing kills | **0 of 588 recorded, 0 of 588 fillable; 0 cells with a positive pooled mean under either** | **KILL** on its first arm |
| P4 straddle audit | for every cell that clears P3, re-resolve every straddle pessimistically | input set empty — **moot on its own definition**; the per-cell straddle counts (`p3_cells.tsv`) and per-row straddle dates (`p3_events.csv`, gitignored) exist if he wants the audit anyway | not run |

**On the noise band.** The block sized its judgement at 294 draws ("1–3 clearing is noise; ≥25 is a
family"). This grid is 588 draws per convention (7 stops × 7 targets × 12 exits — the block's 6 exits,
the incumbent trail arm, and 5 arms from his 2026-09-23 marked charts); 324 of the 588 can reach 3R at
all (a 1R/2R target, or 1×ADR over a wide stop, never can). Scaled: ≤6 of 588 (≤3 of 324 eligible) is
noise; ≥50 (≥28) is a family. **Zero clearing is below the noise band — a null, not a finding of an
exit.**

## RESULT, tail first — the grid at session 10

| | recorded entry (the bar) | fillable entry (beside it) |
|---|---:|---:|
| cells clearing every leg | **0 of 588** | **0 of 588** |
| cells with ≥3R rate ≥3% | 203 | 170 |
| … of those with a positive mean | **0** | **0** |
| … of those with a positive second half (n=217–256 per cell) | **0** | **0** |
| cells with a positive pooled mean | **0** | **0** |
| best pooled mean R | −0.10 (`adr_150 / 1ADR / ema65_1x`, n=3,314) | −0.12 |
| the lane's own arm (`incumbent / none / trail_max10_20`) | n=1,320: ≥3R **2.6%** (34), mean −0.29, second half n=230 at −0.48 | n=1,323: ≥3R 2.3%, mean −0.33 |
| cells clearing mean + tail without the width floor | 0 | 0 |

The kill fires on its first arm — zero cells clear — and not through the floor: no cell has a positive
pooled mean even before the floor is applied. The ≥3R leg is met by 203 cells (the tightest stops, 3R /
3×ADR targets, exits that let a run extend), and **every one of them carries a negative mean and a
negative second half**: the tail exists, and the stop-outs around it cost more than it pays. The
incumbent's own s10 tail is 2.6% (n=1,320) — above the 1.01% the 09-22 read measured at s20 because open
positions are marked at session 10 — so 203 cells clearing a 3% tail bar and all failing on mean
strengthens the kill rather than softening it.

### Per pattern — where the only positive cells are, and why they do not count

| pattern (recorded entry) | n in the incumbent cell | incumbent cell ≥3R | incumbent cell mean | highest ≥3R rate in any cell | best mean in any cell | cells with mean > 0 and ≥3R ≥3% at n≥50 |
|---|---:|---:|---:|---:|---:|---:|
| `ep_low_reclaim` | 414 | 1.4% | −0.31 | 15.2% (mean negative) | −0.09 | **0** |
| `ep_close_reclaim` | 314 | 3.2% | −0.31 | 17.0% (mean negative) | −0.05 | **0** |
| `ep_high_break` | 209 | 3.8% | −0.004 | 25.6% | **+0.69** (`adr_025 / none / ema65_1x`, n=181, ≥3R 9.9%) | **189** |
| `ep_close_620_prox` | 383 | 2.6% | −0.41 | 13.5% (mean negative) | −0.10 | **0** |

`ep_high_break` alone shows 189 positive cells, and three things land on it at once: (1) **on the
fillable entry it has 0 such cells and its best mean is −0.001** — those cells are the level-priced
head start P2 measured, not the pattern; (2) the positive cells cluster on the tightest stop (0.25×ADR
under a level entry); (3) **its second half is n=23**, and across the 189 cells the second-half mean tops
out at +0.06R — a four-fire-date read that cannot carry a leg either way. It is one pattern on one entry
convention on one time half; the block's ≥3-of-4-patterns and both-halves legs are exactly the guards
that keep it from being called a finding.

## Is there an entry at all? (P2) — three patterns are below a random session; the fourth rests on an unfillable price

Session 10, +2×ADR$ before −1×ADR$, fire rate against the matched non-fire control, pessimistic bound
(stop first on a straddling bar), optimistic beside it:

| pattern | n fires (names) | n control sessions | pess: fire / control → gap | opt gap | drop best NAME → | bar |
|---|---:|---:|---|---:|---|---|
| `ep_low_reclaim` | 1,028 (452) | 4,860 | 13.2% / 15.7% → **−2.5** | −1.8 | PDSB → −3.0 | no edge |
| `ep_close_reclaim` | 790 (384) | 3,917 | 16.2% / 19.0% → **−2.8** | −1.9 | RNXT → −3.3 | no edge |
| **`ep_high_break`** | 223 (119) | 1,200 | 28.7% / 20.3% → **+8.4** | +10.2 | VNRX → +7.1 | **clears** |
| `ep_close_620_prox` | 1,099 (438) | 4,507 | 12.2% / 15.0% → **−2.9** | −2.3 | PDSB → −3.3 | no edge |

The three pullback rungs sit below a random non-fire session of the same window on every robustness
read — entered at the fire-day close (−0.9 / −2.1 / −1.1 points; n=1,145 / 859 / 1,115), first shape
only (−1.6 / −2.1 / −3.2; n=519 / 421 / 540), width-floored, all-sessions control, and paired per
campaign (−4.5 / −3.5 / −4.7 points over 536 / 441 / 542 campaigns). Their tail ladder is the
control's: +4×ADR and +6×ADR before −1×ADR sit within a point of the control on every rung (−0.9 to
+0.4; n=1,028 / 790 / 1,099). **No stop or target can
manufacture an edge for a pattern that picks worse-than-random sessions — this is a selection result,
which is what the block said a P3 kill would route to.** At s5 the pessimistic gaps are −2.6 / −2.1 /
+4.4 / −3.0; at s20 −7.2 / −3.4 / +7.1 / −6.4 (control thin at s20: 70–162 sessions).

### What the P2 pass rests on — the recorded entry is not always fillable

`ep_high_break`'s daily-grade fires (and every `new_high_break` re-entry on every rung) are resting
stop-buys priced AT the level. **The lane records the LEVEL as `entry_price` even when the session opened
above it — a stop-buy would have filled at the open. 44 of the 177 level-priced high-break fires at s10
opened above their level, median over-shoot 0.63 ADR**, so a +2×ADR target measured from the level is
only ~1.4 ADR from the real fill. Three reads separate "the pattern picks good sessions" from "the level
entry is a head start":

| read, s10 pessimistic unless stated | `ep_high_break` | the other three |
|---|---|---|
| **fillable entry** (max(level, fire-day open) for level-priced fires) | **+2.2 points** (n=222; opt +5.8); drop best NAME PDSB → +1.3; **would not clear 5** | −3.0 / −3.5 / −3.0 |
| entered at the fire session's CLOSE (the control's own entry) | **−0.3** (n=239) | −0.9 / −2.1 / −1.1 |
| by resolution, recorded entry | daily-grade +12.5 (n=175) · minute-grade **−5.8 (n=48)** | minute-grade −1.8 / −2.5 / −3.2 |
| tail ladder, recorded entry — +4ADR / +6ADR before −1ADR, fire vs control | 14.9 vs 8.3 · 7.7 vs 3.8 (n=223 vs 1,200) | at the control |
| tail ladder, fillable entry | **9.1 vs 8.3 · 3.6 vs 3.8 — the 2× tail is gone** | unchanged |
| first shape only, fillable | +8.9 points, **n=123 (<150 floor)**; re-entry shapes same_pattern −4.7 (n=63), new_high_break −14.0 (n=36) | −1.6 / −2.1 / −3.2 |

So on the recorded entry `ep_high_break` clears the bar; on a price a resting order could have filled it
reads +2.2 pessimistic / +5.8 optimistic and its tail is the control's. The first-shape thread (+8.9 on
a fillable entry) is under the n floor and is a thread, not a finding.

## What the exits did — every arm raises the mean and cuts the tail; none turns a cell positive

Stop = 1×ADR$, no target, s10, recorded entry (n=3,124–3,153 scored per cell after the floor):

| exit arm (source) | fired on | ≥3R rate | mean R |
|---|---:|---:|---:|
| none (hold to s10) | — | **3.1%** (n=3,124) | −0.37 |
| `hv21_50_noreclaim2` — the FVRR caution (Boik): close below both the 21- and 50-day on ≥1.5× volume, no 21-day reclaim within 2 sessions | **0.3%** (n=3,124) | 3.1% | −0.37 |
| `sma21_2x` — two closes below the 21-day (Boik) | 52% (n=3,140) | 2.1% | −0.29 |
| `ema23_2x` — two closes below the 23-EMA (TraderLion "at least a partial", scored as a full exit) | 54% (n=3,140) | 1.9% | −0.31 |
| `sma50_1x` — a close below the 50-DMA (TraderLion / Boik "out") | 65% (n=3,147) | 1.3% | −0.23 |
| `ema65_1x` — a close below the 65-EMA (TraderLion) | 69% (n=3,153) | 1.4% | −0.19 |
| trail SMA20 (block) | 66% (n=3,148) | 1.6% | −0.26 |
| trail SMA10 (block) | 74% (n=3,143) | 1.8% | −0.22 |
| trail MAX(SMA10, SMA20) — the lane's live arm | 78% (n=3,149) | 1.4% | −0.22 |

Two facts about the population fall out of the exits. **The 50-day / 65-day arms fire on 64–69% of fires
within ten sessions: these EP names mostly sit BELOW their 50/65-day lines at the fire** — a gap inside a
downtrend, not a leader above a rising average, which is the chart his 2020 examples are drawn on. And
the heavy-volume-cut-and-no-reclaim shape is real but fires on 0.3% because **the stop arrives first**
(the 1×ADR stop is hit on 68.5% of fires by s10, n=3,124). Targets, stop-first at the same stop: 1R /
1×ADR reached on 31.8% (n=3,142), 2R on 14.7% (n=3,134), 3R on 8.4% (n=3,126) — and the 3R cell's mean
is −0.37.

## The 2,042 fires the grid could not walk on the incumbent stop — which way do they lean?

The incumbent stop is scorable offline on 1,320 of the 3,398 fires (2,042 abstain: a minute-grade fire
whose day low reached its tight stop, with no $0 minute source to order day 0). Production DID settle
those rows, so their recorded columns are the ground truth the grid could not reach
(`p5_abstain_direction.py` → `p5_summary.json`; width-floored at ≥0.5% like the cell; scored n=1,325
here vs 1,320 in the cell — the same rows before the hole rule):

| recorded settlement, incumbent stop | walked by the grid (n=1,325, 1,116 settled) | abstained (n=1,961, 1,916 settled) |
|---|---:|---:|
| outcome = stop | 97.3% | 98.3% |
| trail arm ≥3R | 1.5% | 1.8% |
| trail arm median R | −0.94 | −1.00 |
| ever reached +3R before the stop (`mfe_r`) | 11.7% | 14.5% |
| `ep_high_break` rows | 211: 89% stopped, trail ≥3R 1.7% | **26: 26 of 26 stopped at −1.00R** |

The abstained rows are the same lane: stop rate and tail within a point of the walked rows on every
pullback rung, median −1.00 on both. **The hole hides no winners, and for `ep_high_break` it hides 26
straight full losses — so the grid's high-break read is, if anything, slightly flattering.** A minute-bar
fetch for these 2,042 fires would fill in the cells; it would not move the answer. (The recorded
no-target mean is not quoted for these rows: a stop is always exactly −1.00R, so a mean above −0.95 at
a 98% stop rate is a handful of enormous near-zero-stop time-exits, max +1,599R unfloored — the 09-22
artifact, not a signal.)

## What this does not answer

- **One month, one regime.** Every fire read at s10 is 2026-08-25 → 09-11; the "second half" leg is four fire dates
  (n=217–256 per cell, `ep_high_break` n=23). The matched same-window control holds regime fixed for the
  entry question, but nothing here says what these patterns do in a different tape.
- **This population is what the lane admits, not what he would buy.** The lane fires on every EP name;
  64–69% of fires close below their 50/65-day line within ten sessions, and the median entry price is
  $1.70 (n=3,767; 84% of fires under $5, 34% under $1). Whether a leader-only selection (above rising averages, the shape of his marked
  charts) changes the answer is not measured — it is the revive question, below.
- **Partials are not modelled.** TraderLion's "at least a partial sale" on two closes below the 23-EMA is
  scored as a full exit; a partial-plus-runner arm needs a position model the grid does not have.
- **2,042 of 3,398 fires are unscored on the incumbent stop** for lack of a $0 minute source (236 on the
  1×ADR stop, 75 on 1.5×ADR). Their recorded outcomes match the scored rows (above), so the direction of
  the hole is measured — but the cells themselves are read on the walkable subset.
- **The recorded-vs-fillable gap is inferred from the fire-day open, not from a fill.** The lane records
  neither the fire-day open nor a first-touch price, so "fillable" is max(level, open) — the best a
  resting stop-buy could have done, not what an order would have got with slippage.
- **The straddle audit did not run** (P4's input set is empty). The per-cell straddle counts are in
  `p3_cells.tsv` (e.g. 116 fires at `adr_100 / 1R`, 70 at `2R`, 29 at `3R`) and P2's straddle-decided
  fires at s10 are 26 / 19 / 7 / 19 per pattern (controls 88 / 60 / 16 / 54); every cell's pessimistic
  read already resolves them stop-first.
- **Sixteen split rows are inferred from price shape, not from a corporate-actions source.** The
  strict P1 reading (98.77%) is reported for that reason; it does not change any grid cell (those rows
  are rescaled, not dropped).
- **Nothing here re-prices the EP alert itself.** This is the delayed-entry watch lane only; day-1 entry
  and the day-1 harvest hole belong to `docs/design/545_entry_exit_program_2026-09-05.md` §7 and #482.
- P2's per-pattern day-0 abstain counts at s10 are 132 / 82 / 21 / 23 (sum 258); the P2 phase report
  quoted 257 for its row-level exclusion count. Both are in `p2_summary.json`; the difference is a
  checkpoint-vs-row count, not a scoring difference.

## THE FORK — determined by the bars, stated neutrally

The block allows exactly one of three, chosen by the pass bars, not by preference.

- Option 1, *a pattern graduates to shadow-with-a-real-exit*, requires a cell that clears P3. **None does,
  under either entry convention.** It is off the table.
- Option 2, *the lane is instrumented wrong*, would apply if the recorded lane could not answer the
  question. It can: the walker reproduces production (P1, 99.84%); the recorded-entry defect was
  answered by running the whole grid on the fillable entry as well, and **the kill holds there too (0 of
  588, `ep_high_break` 0 positive cells)**; and the 2,042 unwalkable fires recorded the same outcomes as
  the walked ones. Fixing the instrumentation would not change the verdict, so the bars do not route
  here. Its concrete capture is kept below because it is free.
- **Option 3 — delayed entry is dead on this population.** The three numbers: 0 of 588 cells clear on the
  recorded entry and 0 of 588 on the fillable; no cell has a positive pooled mean (best −0.10R,
  n=3,314); the single P2 pass (`ep_high_break` +8.4 points, n=223) is +2.2 points on a fillable entry
  with no positive cell behind it.

**What would revive the question** (candidates for his ruling — nothing here is a change):

1. **Record the fire-day open, or the actual first-touch price, beside the level on the trigger row.** A
   passive shadow costs nothing to widen, and the next 20 sessions would then read `ep_high_break`'s
   first-shape thread (+8.9 points on a fillable entry, n=123, under the 150 floor) at n≥150 without a
   probe.
2. **A different selection, not a different exit.** The lane admits every EP name; the exits show most of
   them below their 50/65-day lines at the fire. The population his marked charts describe — a leader
   above rising averages, respecting an average it has already respected — has never been the lane's
   population. Whether it should be is a selection question under CHANGE_PROCESS, and the 545 selection
   test (`docs/analysis/545_selection_test_2026-09-01.md`) is the prior null it would have to beat.
3. **A real second half.** The both-halves leg is thin by construction (four fire dates); another month
   of fires makes it a leg rather than a caveat, at $0, by waiting.
4. **Not a minute-bar fetch.** The 2,042 unwalkable fires recorded the same outcomes as the walked ones;
   buying minutes for them fills cells without moving the answer.

⚖ **THE LINE.** This day produced grids, measured tails and the fork above. It picked no stop, no target
and no exit; no toggle, table or strategy was changed; the lane keeps observing exactly as it did
yesterday. Whether any of the revive items is pursued, and under what selection, is his call under
CHANGE_PROCESS and sign-off.

## Files

- `scripts/probes/_327_block5/README.md` — every phase's result and reproduction commands.
- `p0_completeness.py` → `p0_summary.json` · `p1_probe.py` → `p1_summary.json` · `p2_probe.py` →
  `p2_summary.json` · `p3_grid.py` → `p3_summary.json` + `p3_cells.tsv` (all 1,176 cells, every leg) ·
  `p5_abstain_direction.py` → `p5_summary.json`. Bulk pulls and per-row walks (`*.csv`) are gitignored
  and regenerable via `extract_p0.sh` / `extract_p3.sh`.
- The one production change: `agents/market_intelligence/delayed_entry_shadow.py::compute_settlement(target_r=None)`,
  inert by default, pinned by `tests/test_delayed_entry_shadow.py::test_the_lane_never_passes_target_r`.

## Addendum 2026-09-26 — were there big winners we were in but lost? (operator question, $0)

**Method and population:** every watched (ticker, EP date) with EP date ≤ 2026-09-04 and ≥10 later sessions
of bars (n = 1,259; prices from `mi_daily_closes` on one scale, base = the EP-day close). "Ran" = the
highest high within 15 sessions ≥ +50% over the base; "held" = still ≥ +30% at session 15. Joined to every
lane fire for that (ticker, EP date).

| | all prices | EP close ≥ $5 |
|---|---|---|
| watched pairs | 1,259 | 279 |
| ran +50% within 15 sessions | 142 | 24 |
| …and still +30% at session 15 | 68 | 6 |
| of the 142 / 24: the lane never fired | 40 | 8 |
| the lane fired | 102 | 16 |
| any fire kept ≥ 3R | 14 | 1 |
| best fire's result, median | −1.00R | −1.00R |
| best fire's peak open gain before exit (MFE), median | +6.2R | +4.1R |

**Reading:** the big runners are there, the lane was in about 70% of them, and it was stopped out of most
while they were up several R — e.g. HVII (EP 08-28) peaked at +37.6R and closed −1R, VMAR (08-24) +10.6R
and −1R. So yes, winners were reached and not kept. But the stop × target × exit grid above already asked
whether ANY rule keeps them while limiting the losses on everyone else, and none did: holding on for the
runners cost more on the losers than it earned. And the runners are mostly penny stocks — among names over
$5 only 24 ran and 6 held.

**What this does not answer:** peak gain is recorded up to the stop session, including that session's
high, so on a session where both the high and the stop were touched the order is unknown and some of the
peak may have come after the stop; "ran" uses highs, not a price anyone was sure to get.

