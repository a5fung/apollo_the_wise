# Breakout v1 — how Qullamaggie PICKED among a day's breakouts: PRE-REGISTRATION (2026-11-13)

**Status: PRE-REGISTERED, NOT FITTED.** This file is committed BEFORE any model is fitted or any label is joined to
the new features. Research only: no rule wired, nothing deployed, no prod write, $0. A ranking change to the paper
slots is the operator's sign-off (`docs/setups/CHANGE_PROCESS.md`); paper stays OFF.
Owner: `docs/setups/consolidation_breakout.md` (this file is the finding). Task: PLAN.md #717, the "SAT 11-14 BUILD" item (a).
Work folder: `scripts/probes/_717_pick_model_1113/`. Live rules read: `agents/market_intelligence/breakout_v1.py`
(ADR_MIN 0.04, deployed 2026-11-12).

## The decision it serves
Which ranking fills the 5 paper slots of breakout v1 (PLAN #717, "SAT 11-14 BUILD" item (a): *learn Qullamaggie's PICK among a day's fires*). What would change it: on the test years the model takes clearly more of Qullamaggie's buys in the daily top 5 than the live order score (§6) — then a ranking proposal goes to the operator; if not, the order score stays and the finding is "not shown". What would make this analysis wrong: the list under "What this does not answer".

## Why
- 11-12 (`scripts/probes/_717_precision_1112/03_adr_floor.out`): at the 4% floor a median 68 names fire a day; 375 of
  Qullamaggie's scorecard buys are among those fires, and the live order score's daily top 5 takes 50 of them (5 of
  the 26 big winners). Five paper slots, so the RANKING decides what the book holds.
- The only yardstick is Qullamaggie's own buys (757 stream-dated, `tests/fixtures/qm_breakout_scorecard/`). Returns
  are not read anywhere in this study.

## Method

### 1. Population
- Every watch night D of ERA A (the frozen replay's 1,322 nights, D 2016-12-30 .. 2022-03-31, breakout day E = the
  next session), bars from `cb702_pre_v2/daily_closes_all.csv.gz` only (2016-01-04 .. 2022-06-30; the `< 2025` assert
  kept). The sealed 2025–26 data and the `cb702/` store (it holds 2025–26 rows) are NOT opened; 2022-04 .. 2024 is not
  measured.
- LIST rows: names passing every live gate at D (`breakout_v1.v1_gates`, ADR floor 4%), the pool and strength rank
  built exactly as `02_picks.py` builds them. FIRE rows: list rows whose high on E is above the level
  (`breakout_triggered`, the daily-bar proxy of the buy; no volume condition, as wired).
- BRIDGE CHECK before any fit: the new capture must reproduce the 4% row of `03_adr_floor.out` on the full era —
  median fires 68, fired Qullamaggie buys 375 (26 big), order-score top 5 takes 50 (5 big). A mismatch stops the study.

### 2. Label (for FITTING only)
- y = 1 on a fire row (ticker, E) when a scorecard buy of that ticker falls in **E .. E+2 sessions**: a dated buy whose
  day is in that span, or an undated-widened buy whose window lo..hi overlaps it. Else y = 0.
- Why that window: the fire is a daily-bar proxy of the first session through the level; Qullamaggie's buy is often
  that session, but (a) 488 of the 757 buys are dated only to a 1–5 session window, and (b) his own level can sit a
  little above ours, so his buy lands a session or two after our fire. +2 sessions keeps the label on THIS break; a
  wider window starts labelling the next base. Days before E are excluded: a name he already owns is not a pick among
  today's fires.
- Fit rows: fire rows on days with a positions snapshot within ±5 sessions (the "covered" days of `02_picks.py`). On
  an uncovered day his buys are unobserved, so every row there would be a false negative.

### 3. Features — all from bars <= D (the night before), except the two opening features of the secondary model
Each feature enters as its **percentile within that night's LIST** (0..1, average ties; a missing value = 0.5) — never
as a raw value. Reason: his buys cluster in 2020–21 when daily ranges and dollar volume were also high everywhere; raw
values would teach the model the year, not the pick among the day's names.

| # | name | definition |
|---|---|---|
| 1 | rs_1m | strength rank: percentile of the 21-session return over the night's pool |
| 2 | rs_3m | same, 63 sessions |
| 3 | rs_6m | same, 126 sessions |
| 4 | prior_move | the gate's run-up into the pole top (pole high / lowest low of the 40 sessions before it − 1) |
| 5 | runup6m | the order score's 6-month move (`runup6m_at`), as a fraction |
| 6 | depth_adr | base depth from the pole top, in daily ranges (the gate's value) |
| 7 | base_len | sessions from the pole top to D (the gate's `base_len`) |
| 8 | spread10_adr | the last-10-close spread in daily ranges (the order score's tightness; small = tight) |
| 9 | adr20 | the 20-session daily range (the gate's own) |
| 10 | dollar_vol20 | 20-session median of close × volume |
| 11 | dist_52w | close(D) / the highest high of the last 252 sessions ending D (all sessions available when fewer: the store starts 2016-01-04, so early-2017 nights see ~250) |
| 12 | dist_level | (level / close − 1) in daily ranges — how far below the buy level the name closed |
| 13 | vs_ema21_adr | close vs the 21-day EMA in daily ranges (the gate's value) |
| 14 | since_low | sessions from the MAJOR LOW to D; the major low = the lowest low of the 252 sessions ending D |
| 15 | first_base | 1 when no earlier base completed since the major low, else 0 (entered as 0/1, not a percentile). A completed earlier base = a stretch of >= 10 sessions (`BASE_MIN`) between two consecutive "new high since the major low" days, both <= D. The base being broken on E is not counted. |
| 16 | group_strength | percentile of the name's industry group's median 63-session return among the night's groups (`cb.cross_section_one_date`, group = SIC 2-digit, groups under 10 members drop out). Missing = 0.5, no missing flag. |

SECONDARY model only (knowable at the open of E, i.e. at or before the break): 17 `gap_adr` = (open(E) / close(D) − 1)
in daily ranges; 18 `open_above` = 1 when open(E) > level. `high(E)` and `low(E)` are never features.

Not available, declared: theme / leading-group membership as Qullamaggie saw it (only the SIC proxy above); intraday
volume pace; the catalyst.

### 4. Model
- PRIMARY: logistic regression on features 1–16, intercept unpenalised, L2 penalty λ = 1.0 on the coefficients (fixed
  here, not tuned), fitted by Newton/IRLS in numpy (no scikit-learn on this machine). Inspectable: one coefficient per
  feature, each on a 0..1 percentile, so sizes compare directly.
- SECONDARY (reported beside, never the verdict): the same with features 17–18 added.
- No other model, no feature selection, no interaction terms, no re-fit after the test is read.
- Ties in a day's ranking break by ticker, ascending (as `02_picks.top_k`).

### 5. Split
- FIT: fire rows with E in 2017-01-03 .. 2020-12-31 (covered days).
- TEST: every day with E in 2021-01-04 .. 2022-04-01 (the end of era A), scored ONCE. The fit stage writes the
  coefficients to a file; the test stage only reads that file.

### 6. The bar (TEST days only)
- Metric = the `taken()` count of `02_picks.py`: DISTINCT scorecard buys a pick lands on (dated = on E; widened = any
  session of lo..hi), with picks = the day's top 5 fires by the score, all 5 slots free each day ("model B"). This is
  the reading behind "50 of 375", so the numbers are comparable. Big winners taken are counted the same way.
- Rows: the model · the live order score (re-ranked inside the night's 4% list, as `rank_rows`) · dollar volume (high
  first) · 5 at random (seed 717) · the ceiling (his buys that fire, at most 5 a day).
- Also per row: hits per day (pick-days landing on a scorecard buy / test days) and the share of picks that are names
  he bought within ±5 sessions on covered days (the 02 `bought` reading).
- **PASS** = the model takes more distinct buys than the order score AND the 90% interval of the difference (1,000
  bootstrap resamples of test DAYS, seed 717) excludes zero. The same comparison against dollar volume is reported;
  beating the order score but not dollar volume reads "dollar volume alone does as well". Anything else = NOT SHOWN.

### 7. Slot mechanics proxy (TEST days, descriptive — no pass/fail)
Daily bars cannot see the minute a name breaks, so "the first 5 to break" is bracketed, not measured:
- R, as wired: the model's top 5 of the LIST rest from 09:35 (a name too wide on the day skipped, by the DAILY low —
  look-ahead); a buy only if it fires (`02_picks.live_like`, hold 0, all 5 slots free each morning).
- K, break-only, best case: the day's top 5 FIRES by the model (= the bar row; an upper bound, because under
  hold-only an early lower-ranked breaker keeps its seat).
- G, break-only, open-first: fires already above the level at the open take seats first (model order), then the rest
  by the model.
- N, break-only, order-blind: only the model's top N of the list (N = 10, 20, 40) may take a slot; of those that fire,
  5 at random when more than 5 (seed 717) — the case where break order is unrelated to the score.
- Z, break-only, no model: 5 fires at random (the floor).
The same five rows are printed for the order score.

## What this does not answer
Declared before the read (also the "what would make this wrong" list):
- Whether the ranking makes money — returns are not read; the yardstick is his buys only.
- Whether it holds in 2022-04 .. 2024 or on the sealed years — era A only.
- Which names break FIRST inside a session — daily bars; §7 brackets it.
- Whether the model finds his reasons or only correlates of them (theme, catalyst and his chart read are not features).
- `02_picks.out` §3 already ranked single features over the FULL era, test years included (dollar volume took 67).
  The test is blind for the weights, not for the knowledge that dollar volume ranks well.
- The test set is small (his buys with E in 2021-01 .. 2022-04 that fire at the 4% floor; counted in the output) and
  holds few big winners; a difference of a handful of buys is noise, hence the interval in §6.
- Covered days are 706 of 1,322; his buys on other days are unobserved, so every count is a floor.
- `cb702_sic.psv` is a 2026-10-16 snapshot (~3,900 tickers): a missing code often means a later delisting — mild
  future information. It carries no price; coverage on fires and on his buys is printed.
- "First base" is cut off by the store's 2016-01 start and by the 252-session major-low window.
- The slots are modelled all-free every morning; real holds would fill them for days (not replayed).
- Era A only: nothing here says the ranking holds in 2022-04 .. 2024 or on the sealed years.

## ⚖ THE LINE
The slot ranking is entry discipline: any change is the operator's call. Nothing was flipped, wired or deployed by this study; paper stays OFF.

## The numbers
None yet — pre-registration. The test-years table is appended below after the single test run.

## 9. Files
`01_build.py` (the capture, once, outside git: `/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet`),
`02_fit_test.py` stages `bridge`, `fit` (writes `coef.json`), `test` (reads it; `02_test.out`). Results are appended
below this line after the single test run.
