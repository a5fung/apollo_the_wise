# Breakout v1 — how Qullamaggie PICKED among a day's breakouts: PRE-REGISTRATION (2026-11-13)

**Status: SCORED ONCE 2026-11-13 — the model beats the live order score on the test years (41 of Qullamaggie's buys in the daily top 5 against 18) but NOT plain dollar-volume ranking (43); results at the end. Nothing wired.** Pre-registered in commit `730db6c7`: this file was committed BEFORE any model is fitted or any label is joined to
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
See RESULTS at the end of this file (appended after the single test run; everything above it is the registration as committed in `730db6c7`).

## 9. Files
`01_build.py` (the capture, once, outside git: `/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet`),
`02_fit_test.py` stages `bridge`, `fit` (writes `coef.json`), `test` (reads it; `02_test.out`). Results are appended
below this line after the single test run.

---

# RESULTS (2026-11-13, one test run; outputs `scripts/probes/_717_pick_model_1113/02_bridge.out`, `02_fit.out`, `02_test.out`)

**Bridge: OK** — the new capture reproduces the 4% row of `03_adr_floor.out` exactly (listed median 190, fires median
68, 375 fired buys / 26 big, order-score top 5 takes 50 / 5).

**Fit (2017-2020, fires on covered days):** 62,051 fire rows on 403 days; 410 carry the label (0.66%) — 365 of them in
2020, 36 in 2019, 9 in 2017-18. So the model is, in practice, fitted on his 2020 buying.

## The test years (E 2021-01-04 .. 2022-04-01, 315 days; 138 of Qullamaggie's buys fire, 9 big winners; a median 153 fires a day)

| the day's top 5 fires by | his buys taken (of 138) | big winners (of 9) | picks landing on one of his buys | hits a day | picks he bought within ±5 sessions (panel, covered days, n=1,515) |
|---|---|---|---|---|---|
| **the model** (night-before features) | **41** | **3** | 40 of 1,575 = 2.5% | 0.13 | 12.8% |
| the live order score | 18 | 1 | 18 of 1,575 = 1.1% | 0.06 | 2.8% |
| dollar volume, high first | 43 | 1 | 42 of 1,575 = 2.7% | 0.13 | 16.0% |
| the model + the opening gap (secondary) | 40 | 3 | 39 of 1,575 = 2.5% | 0.12 | 12.9% |
| 5 at random (mean of 200 draws) | 4.3 | 0 | 0.3% | 0.02 | 1.9% (seed 717) |
| every fire, no ranking (188 a day) | 138 | 9 | — | — | — |

- **Registered verdict: PASS against the order score; "dollar volume alone does as well".** Model minus order score
  +23 buys (the interval excludes zero); model minus dollar volume −2 (interval −7 .. +4).
- ⚠ The printed 90% intervals (+10 .. +19) sit BELOW the point (+23): resampling days with replacement drops about a
  third of the distinct days, so every distinct-buy count shrinks. The sign of the comparison holds; the interval's
  position is an artefact of the registered method, not re-computed.
- By year: 2021 — fired 130, model 39, order score 16, dollar volume 40; 2022 Q1 — fired 8, model 2, order 2, dollar 3.
- Two readings of precision: on the strict scorecard (the pick lands on the buy's own day or window) even the best
  ranking is right on ~2.5% of picks, 0.13 a day (the ceiling, all 138, is ~0.44 a day); on the looser panel reading
  13–16% of the model's / dollar volume's picks are names he bought within ±5 sessions, against 2.8% for the order score.

## What carries the weight (each feature is its rank inside the night's list; "odds x" = bottom of the list to the top)

| feature | coefficient | odds x | reads as |
|---|---|---|---|
| dollar volume | +5.30 | 200 | he buys the MOST LIQUID names that break — by far the largest weight |
| 6-month strength rank | +1.26 | 3.5 | the strongest names over six months (the 1- and 3-month ranks add little) — a three-way tie with the next two rows, a quarter of dollar volume's weight |
| daily range (ADR) | +1.25 | 3.5 | the fast movers |
| sessions since the major low | +1.24 | 3.4 | a long advance behind it (not a fresh turn) |
| last-10-close spread | −0.88 | 0.41 | tight into the break |
| closeness to the 52-week high | −0.81 | 0.44 | NOT pinned at the high — somewhat below it |
| 6-month move | +0.81 | 2.3 | a big prior move |
| first base since the major low | +0.37 | 1.4 | a small lean to first bases (z 2.1) |

No weight found (|z| < 1.5): the run-up into the base, base depth, base length, the 1-month rank, distance below the
level, close vs the 21-day average, industry group strength (SIC proxy, present on 64% of rows). The opening gap
(secondary) carries some weight (+0.75) but did not add buys on the test.

## Slot mechanics proxy (test days; a bracket — daily bars cannot see which name breaks first)

| how the 5 slots fill | model: buys a day | model: his buys taken (big) | order score: his buys taken (big) |
|---|---|---|---|
| R — as wired: the top 5 of the LIST rest at 09:35, bought only if they break (56% do) | 2.8 | 33 (3) | 12 (1) |
| K — break-only, best case: the day's top 5 fires by rank | 5.0 | 41 (3) | 18 (1) |
| N — break-only, order-blind: only the top 10 of the list may buy (mean of 200 draws; big = the seed-717 draw) | 2.6 | 28.1 (3) | 13.3 (1) |
| N — top 20 of the list (same) | 3.9 | 28.4 (2) | 13.4 (1) |
| N — top 40 of the list (same) | 4.6 | 30.0 (0) | 11.4 (1) |
| G — break-only, open-first: names above the level at the open take seats first | 5.0 | 21 (1) | 7 (0) |
| Z — break-only, no ranking: 5 fires at random (mean of 200 draws) | 5.0 | 4.3 (0) | — |

- With a good ranking, RESTING on the top 5 (33) is within a few buys of break-only (28–41 depending on who breaks
  first); break-only without a rank cap is the random floor (~4). **The ranking, not the slot mechanics, is what moves
  the count** (18 → 41 from the ranking; 33 vs 28–41 from the mechanics).
- Giving seats to whatever is through the level at the open is WORSE (21): 25% of fires open above the level, 31% of
  his.
- Cannot see: the minute of each break, the too-wide cancel minute (the daily low is used — look-ahead), slots still
  held from earlier days (all five free each morning here).

## POST-HOC, not registered (`03_posthoc_split.py/.out`; no refit, the verdict above is untouched): is the liquidity weight an artefact of the undated sightings?
Of the 138 test-day buys that fire, 78 are stream-DATED buys and 60 are UNDATED positions-panel sightings.

| the day's top 5 fires by | dated buys taken (of 78) | undated sightings taken (of 60) | total | big |
|---|---|---|---|---|
| the model | 30 | 11 | 41 | 3 |
| the order score | 12 | 6 | 18 | 1 |
| dollar volume | 23 | 20 | 43 | 1 |

- No artefact: BOTH kinds sit at the 96th percentile of the day's list by dollar volume (all fires: the 51st). He buys
  the liquid end of the list whichever way the buy is known.
- The model and dollar volume are NOT the same picks: they share 17 buys; the model alone takes 24 (19 dated), dollar
  volume alone 26 (12 dated). On the dated buys — the firmer evidence — the model leads 30 to 23 and 3 big winners to
  1. Post-hoc and small; not a verdict.
- 165 of the 410 fit labels are fires one or two sessions BEFORE his buy (the +2 window), 123 land on a dated buy's
  own day, 122 inside an undated window.

## Reading, and what is NOT established
- The live order score (6-month run + tightness) is a poor picker of his buys: 18 of 138. A liquidity-first ranking
  takes ~2.3x as many; the 16-feature model adds nothing in COUNT over dollar volume alone, but takes 3 of the 9 big
  winners against 1 (3 vs 1 is too few to call).
- Dollar volume dominating is not an artefact of the undated sightings (post-hoc split above). ⚠ UNVERIFIED: whether
  it would hold outside 2020-21 — the fit is 89% 2020 and the test is 94% 2021, his largest-account years.
- ⚠ UNVERIFIED — 2022-04 .. 2024 and the sealed years; the fit label's +2-session window (no sensitivity run); the
  industry-group proxy (2026 snapshot, 36% of rows without a group).
- Not a rule. A ranking change to the paper slots is the operator's sign-off.
