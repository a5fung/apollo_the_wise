# Adversarial critique — `docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md` (breakout big-winner chart study), 2026-11-24

**Read:** the draft; `design/spread_sim.py` + `.txt`; `design/count_events_outcome_free.py` + `.txt`; the EP critique and the EP
study's "Critique resolutions"; `agents/market_intelligence/breakout_v1.py` (`v1_gates`, `context_gates`, `breakout_triggered`,
`security_admitted`); `breakout_v1_list.py` (`scan_members`, `evaluate_members`, `night_cross_section`);
`broker/breakout_v1_entry.py::evaluate` (level / opening range / width lines only); `_717_pick_model_1113/01_build.py`,
`05_paths_build.py` and `06_template.py` headers; `_717_precision_1112/01_precision.py` header; `_breakout_v1_replay_1101/v1_replay.py`
(header, `load_store`, `era_b_raw_factor`, `night_members`, `sealed_copy_of_daily`, `load_types`); `_cb_backtest/runner.py::break_mask`.
**Outcome-free data reads, disclosed:** file listings of `apollo_data/cb702`, `cb702_pre_v2`, `bv1_pick_model_1113`; the two raw-close
pull `meta.json` files and their ticker / date columns (counts only); the year of the DATE column of `cb702_splits.psv` (a count per
year, no ticker read); `small_pulls.psv` first 3 rows and the row-kind count; `population_eraA.json` / `population_eraB.json` and the
first two rows of `nights_eraB.tsv` (the 11-01 replay's outcome-free population stage); `export_stats.tsv`; the first rows of the era-A
bar files and NVDA's 2016-01-04 row (price format only, before any event). **Not opened:** `cb702/daily_closes_all.csv.gz`, any
`trades*`, `walk*`, `report*`, `big_winners*`, `*_holdout*`, `features_eraB.parquet`, any 2025-26 store, any outcome or big-winner list.
Also read (no outcome in them): `raw_ratio_check_polygon.txt` (first lines: per-ticker raw / adjusted ratio counts), the header and
first rows of `symbol_guard.tsv`, `dedupe_applied.tsv`, `run_all.out`, the first two rows of `cb702_splits.psv` (two 2021 rows, tickers
visible), and `ended_by_year_{A,B}.tsv` for years before 2025.
**Two $0 synthetic runs:** `design/critique_thin_sim.py` → `.txt` (finding 1) and `design/critique_power_rerun.py` → `.txt` (finding 9).

**Verdict: sound frame, not ready to freeze.** 3 BLOCKERS, 9 MAJOR, 9 MINOR. The frame (measurement only, the tail, the operator's eye as
judge, one check run, gallery before check) copies the EP study correctly. The breaks are in what is NEW here: the thinning rule, the
break-day membership, the outcome window, and era B's inputs.

---

## BLOCKER

### 1. The random thinning picks events using what happened AFTER the break (BLOCKER)
- **Hits §1.2:** *"a row is kept when no kept row of that identity lies within 60 sessions either side"* and *"a random draw is an
  unbiased sample of what the list actually fires"*.
- **Why it breaks.** A row's chance of being kept falls with the number of the same name's break rows within ±60 sessions, and half of
  that neighbourhood is AFTER E. Later break rows exist only if the stock set new levels and took them out — the forward path. So
  whether an event is in the study depends on its own future. The population is not knowable at the break, and the "unbiased sample"
  line is false: it is one event per cluster, and how big the cluster grows is decided after E.
- **Mechanism demo (synthetic only; `critique_thin_sim.txt`).** A feature tied to how many breaks came BEFORE a row, an outcome tied to
  how many came AFTER, the two drawn independently (true ratio 1.00). Under the draft's rule the winner rate among kept rows falls from
  10% to 4-8%, and the feature reads **1.05x, 1.32x and 1.57x** on three densities — from nothing. A rule that decides on earlier rows
  only (the `forward_coin` rows) reads 0.95-1.02; ignore `forward_first` in the first block, it keeps almost no dense-past rows. ⚠ This shows the mechanism, not the size or sign on real rows (a failing name that re-bases may re-break more
  often than a runner); the within-month permutation cannot remove it because the dependence is inside the kept sample.
- **Which features it would touch:** everything correlated with "has been breaking out lately" — run-up (7, 8, 9), strength (4-6),
  extension (19), distance to the 52-week high (10, 11), sessions since the low (22), B1.
- **Fix.** The keep decision reads rows dated ≤ D only. Walk each identity's break rows forward in time; a row is ELIGIBLE when no
  kept row lies in the 60 sessions before it; an eligible row is kept when a per-row hash of (seed 1124, identity, D) falls under q.
  q is set outcome-free so the early / late mix matches the break rows (the draft's 14.4% vs 15.2% check, re-run on the new unit). The
  hash (not a stream of `default_rng` draws) makes the blind recount reproduce it without re-creating iteration order. Apply it per
  IDENTITY across both eras (the count script thins per ticker, per era — a name can be kept at D 2022-03 in era A and again at
  2022-04 in era B with overlapping windows). Reprint the event counts and re-run §5.4 on them. Print a second seed on discovery as an
  extra reading (the draft's own unresolved 4).

### 2. Nothing stops the outcome window at a symbol change-of-hands or an unadjusted jump (BLOCKER)
- **Hits §2** (*"highest close over E..E+60 ≥ 1.5 × the buy-point proxy"*), **§1.3** (*"its window ends where its bars end"*) and
  unresolved 8, which covers only the LOOK-BACK.
- **Why it breaks.** The only identity guard in the call chain is `runner.break_mask`: it looks at the 86 bars ENDING D
  (`v1_replay.py:386`). A reused ticker, a twin series or an unapplied split inside E+1..E+60 produces a close ≥ 1.5× the level that no
  holder ever received. Era A's guard file marks 667 symbols with a break (`export_stats.tsv`); era B is worse — `load_store("B")` sets
  `breaks = {}`, so era B has no guard at all in this code path, although one exists on disk
  (`scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv`, the file the EP join used). Fake winners land in the
  low-priced, wide-ranging names, which is exactly where the EP study found its two strongest readings (features 1, 2, 13). At a 3-5%
  base rate a handful of fake winners per hundred real ones moves a ratio.
- **Also:** the window is not pinned to the calendar. The EP study counts E+60 on the era calendar index; the draft says "sessions".
  On a name with missing bars, 60 rows is longer than 60 sessions.
- **Fix.** (a) Wire both guard files; an event is DROPPED (counted, per era and year) when a guard break or a known-adjustment flag
  falls in D−85..E, and its outcome window ENDS at the session before a break dated in E+1..E+60 (counted). (b) The window is
  calendar sessions `ci(E)..ci(E)+60`. (c) Before discovery opens, print outcome-free the count of kept events with a guard date
  inside their window; and a mechanical screen, fixed now: a window also ends at the session before any close-to-close move of
  ≥ 70% up or ≤ −50% down that falls on a guard date or a split-list date (≤ 2024-12-31) — no by-hand call after outcomes.
- **The frozen EP twin:** its text applies the identity / adjustment rule to feature windows (§4.0); I found no line that cuts its
  forward window either. Likely the same gap — worth one outcome-free count there, not reopened here.

### 3. Fork 3b's inputs exist only in part — the raw close for 7,184 of era B's 15,702 tickers (about 9% of list rows on 11-01) is a derived number that can be wrong, and fixing it needs a network pull (BLOCKER; the choice is the operator's)
- **Hits §1.3:** *"Era B needs a raw close and a security type per name-night … source not yet verified (unresolved 1). Without it,
  fork 3 falls back to (a)."* and the header's *"$0 … no network"*.
- **What exists (verified by file listing; full list under "Era-B inputs" at the end).** Adjusted bars: yes (need the sealed copy
  rebuilt). Splits: yes, with a loader that skips 2025-26 rows. Security type: one snapshot per ticker, not per night. **Raw close per
  name-night: no such file.** The 11-01 replay DERIVES it: exact for the 8,518 tickers bridged across the two stores, and "the split list ≤ 2024-12-31
  only" for **7,184 tickers** (224 of them bridge failures; `population_eraB.json`). By list rows it is smaller than by tickers: on
  the 11-01 list 2,072 of 21,952 era-B rows (about 9%) rested on the split list alone. For a split-list-only name that split in
  2025-26 the derived raw price is wrong by the split factor — and the error is information from the sealed years (a later reverse
  split makes a penny stock read as a $20 stock; it passes the $2 floor, and feature 2 "Price" reads high).
- The 11-01 work patched this with a Polygon raw-close pull — but only for the names on the 10-31 list: 192 + 245 tickers, **326 in
  all**. Today's list is far wider (era A: 420,158 rows against 39,119 then), so most of today's split-list-only list names have no
  pulled raw close.
- **Why "just drop them" is not free:** split-list-only names are mostly listings after mid-2022 (IPOs, de-SPACs). Dropping them
  removes the new issues from 2022-24.
- **The fork (not pre-decided here):** (i) one more raw-close pull for era-B split-list-only list names (the 11-01 precedent; breaks the
  draft's "no network" line and needs his allow), or (ii) no pull: the name stays, `raw_src` is carried per event, feature 2 is NULL on
  derived-only rows, the count of derived-only events within a factor of 10 of the $2 floor is printed, and every era-B line carries the
  tag "era-B price partly derived", or (iii) fall back to 3a. **Rec: (i)** — it is the only one that keeps 3b as he ruled it.

---

## MAJOR

### 4. The bridge check as written cannot be run, and the pin is too narrow (MAJOR)
- **Hits §1.1:** *"Code is CALLED from `agents/market_intelligence/breakout_v1.py` at one pinned commit"* and *"with the context gates
  switched off, the era-A rebuild must reproduce the 11-13 capture"*.
- **Findings.** (a) `v1_gates` has NO context switch — it always calls `context_gates` and folds the result into `failed` / `ok`
  (`breakout_v1.py` end of `v1_gates`). "Off" must be DEFINED: one call, list row = `set(g["failed"]) <= set(CONTEXT_GATES)`, which is
  exactly the live `context_only` test in `evaluate_members`. Monkeypatching is the re-coding the draft forbids. (b) The list is not
  made by `breakout_v1.py` alone. The pool, floors and strength rank come from `breakout_v1_list.scan_members`,
  `consolidation_breakout.cross_section_one_date` / `percentile_ranks` / `_dollar_vol_median`, and the capture reached them through
  `v1_replay.night_members` — a COPY of `scan_members` that the 11-01 replay asserts equal in its `parity` stage — plus
  `_cb_backtest/runner.py` and `_717_precision_1112/01_precision.py::setup`. Pin and assert ALL of them, and re-run the parity stage at
  the pinned sha. (c) `01_precision.py` sets `BV1_SCRATCH` at import to a scratch folder that no longer exists, and era B's sealed bar copy lived
  under it; both scripts have a `__main__` guard, so importing them is safe, but the build must set its own scratch path and rebuild
  the sealed copy rather than inherit one. (d) "375 of 757 buys" also depends on the two fixture files —
  pin their sha256.
- **Will it reproduce?** Plausibly yes: `git diff 0210a5f0..HEAD -- breakout_v1.py` is +183 / −1, all of it the context block, and
  none of the other chain files changed since the capture. Not proven until run.
- **Era B has no capture to bridge to.** Free bridge: both stores cover 2022-04..06. Build nights D 2022-04-01..2022-06-29 from BOTH
  stores and print list-membership and break agreement for names in both (features that need under 130 bars only). A mismatch there is
  the only pre-outcome evidence that the era-B rebuild is the same rule.

### 5. EP critique D2 (era-B volume underflow) is not carried (MAJOR)
- **Hits "Critique resolutions":** the carried list names D1, D3, D4, D5 — not D2.
- **Why.** The era-B bars are adjusted as of 2026-10-16. Volume divided by a later reverse split's factor rounds to 0. Here that bites
  harder than in the EP study: `scan_members` puts the 20-session median of close × volume against the $5M floor on EVERY night, so
  later reverse-splitters (many after the 2024 cut) can drop out of the pool and the list — a thinning of era B by sealed-year
  information — and features 3, 17, 18 read a fake dry-up.
- **Fix.** Re-run the EP study's outcome-free D2 test on THIS population (era-B list nights failing only on the dollar-volume floor
  with a zero-volume row in the window, by adjusted-price level); same 1% trigger and tag; features 3, 17, 18 NULL when their window
  holds a zero-volume row. Disclose in §8 that era-B adjustment carries post-cut split information.

### 6. Membership needs E's high above the level, which selects on E-day strength unevenly across features (MAJOR)
- **Hits §4.0:** *"Membership uses E's high (the break itself) … features are clean"* and feature 24.
- **Why.** A name that closed 2 daily ranges under its level is in the study only if it rallied 2 ranges on E; a name sitting on its
  level needs nothing. So every feature tied to the gap between close(D) and the level (tightness 15-16, extension 19, distance to the
  high 10-11, shape 20) compares "needed a huge day" with "needed no day", and E's own close counts toward the outcome (§2). Feature
  24 is the sharpest case: a low or negative opening gap is in the population only if the stock then ran through the level intraday —
  the EP critique's feature-12 collider again. A reading on 24 could be entirely this.
- **Fix (pre-stated now, before outcomes).** (a) Add **"distance from close(D) to the level, in daily ranges"** (knowable at D) as
  benchmark B4, printed on every table. (b) Every carried feature also prints its ratio within B4 thirds; a feature that reads under
  a floor inside them is tagged "break-day selection" (a tag, not a bar — the EP study's shelf-relative handling). The floor starts
  at 1.10 and is calibrated in stage 2 on the real feature table with synthetic labels, by the EP study's lowering rule. (c) Feature 24 is
  computed and tested in two fixed groups — opened above the level / opened at or below — never pooled. (d) The outcome also prints
  with E's close excluded (E+1..E+60) as an extra reading.

### 7. The buy-point proxy is lower than the live buy, and the population includes breaks the live rule refuses (MAJOR, disclosure + two readings)
- **Hits the §2 header** (*"max(level(D), open(E))"*) and fork 1a (*"every break of the LIVE breakout-v1 rule set"*).
- **Why.** `breakout_v1_entry.evaluate` buys the break of `max(ORH5, list level)` after the 09:30-09:34 range, and abstains when the
  stop (the day's low) sits more than one ADR20 under that level. So (i) on a gap through the level the live buy is at or above the
  5-minute high, never the open — the proxy understates the buy most on gap days and on wide-ranging names, which is feature 24 and
  feature 1; (ii) a break that happens only inside the first five minutes, or on a "too wide" day, is in this study and never bought.
  The population is "list names whose level was taken out", not "what the live rule buys". §8 says the first half; it should say both.
- **Fix.** Reword fork 1a's population line and §8. Add two extra readings (no minute bars needed): the outcome measured from
  max(level, high of E) as the pessimistic bound, and gap-through events apart (already in §5.5 — make it apply to benchmarks too).
  The real answer stays with #720.

### 8. Verdict words: a null can be read as a finding (MAJOR)
- **Hits §5.3's table** and §5.2 (*"NOT CARRIED, final"*).
- (a) **"REVERSED" at any check ratio under 1.0, significance "either".** The null band on check is 0.75-1.33 (§5.4), so close to half
  of true-zero carried features — and a real 1.2x on a bad draw — get the strongest negative word in the study. In the EP study that
  word overturned three of the operator's reads. **Fix:** REVERSED needs ratio ≤ 0.83 AND a Holm-adjusted p ≤ 0.05 on the opposite
  one-sided test, in its OWN family of the same size m (not added to the PICKS THE TAIL family, so §5.3's control and §5.4's
  family-of-9 figures stand); otherwise **NOT CONFIRMED**.
- (b) **No pre-written sentence for the all-null result,** which §5.4 says is the LIKELY result at a 3% base rate even with a real
  1.5x. **Fix:** freeze it now — "No chart reading reached the bar. With N events and a base rate of X this study finds a real 1.5x
  reading P% of the time; it says nothing about whether Qullamaggie's breakouts pay — they did, for years. The miss is in our
  measurement or our list." Every NOT CARRIED / NOT CONFIRMED line prints the smallest true ratio it had an 80% chance to detect,
  computed from the real n and base rate BEFORE the check opens.
- (c) **B1-B3 on every table read as a returns verdict on the grade.** A pick-score third reading under 1.0 will be read as "the grade
  points the wrong way" — judging detection on returns, which the draft's own "What this is NOT" forbids. **Fix:** benchmarks print in
  ONE table per stage with the fixed line "not a test of the grade — the grade is judged on Qullamaggie's buys only (#717)", not beside
  every feature.
- (d) "NOT CARRIED, final" → "NOT CARRIED in this study" (final for this study's family, not for the reading).

### 9. §5.4's power figures rest on three soft assumptions; the arithmetic itself is right (MAJOR)
- **Checked:** the table matches `spread_sim.txt` line for line; the Beta month-rate algebra (mean p, CV 0.6), the third rates
  (mean = p) and the first-step Holm quantile are correct; chain = carried × confirm is valid for independent draws.
- (a) **"Base rate" in the grid is the rate OUTSIDE 2020.** With 2020 at 3×, the "5%" row has a pooled discovery rate of about 9.8%.
  Stage 3 prints the pooled rate first; a reader will match a pooled 5-6% to the "5%" row when the right row is about 3% — power
  overstated about two-fold. **Fix:** label the grid "rate outside 2020" and pre-state that the row is chosen by the 2017-19 rate.
- (b) **Era B is given the same base rate as 2017-19.** #705's only hint is 10.5% vs 7.9% between the eras, and 2022 was a bear
  market. Re-run (`critique_power_rerun.txt`): with era B at 0.75× the rate (that hint) a real 1.5x at "5%" falls from **55-81% to
  46-74%**; at 0.5× (a stress) to 39-67%; at "3%", from 26-49% to 20-43% / 16-38%. Fork 3b still beats 3a at every setting. Print
  the 0.75× column beside the draft's.
- (c) Era B is simulated as 33 months / 3,985 events; §1.3's rule (E+60 by 2024-12-31) gives 30 months / about 3,620 (measured
  effect: under 2 points — small, fix the constant). Five features (10, 11, 21, 22, 23) are NULL in era B until about 2022-09, so
  their era-B check set is about 25 months.
- (d) Not simulated and all in the same direction: the group / cap-of-four rule (the EP study suggests more than four real readings
  exist here), same-day clustering, and the event counts themselves change with finding 1. Re-run after the recount; keep the
  "lower bound / upper bound" wording honest — the family figure is a lower bound, the chain is not.

### 10. Seven candidate features were already read against the tail on the check years (MAJOR)
- **Hits §0** (the #705 A+ rating row: *"A prior feature-vs-tail look at what are features 4-6, 7, 15-17 here, on older fills"*, both
  eras) **and §5.3**, which treats all 24 alike.
- **Why.** The EP study moved shelf distance OUT of the family for the same reason and tagged its relatives. Here the draft discloses
  and then does nothing. RS leadership was the top reading in both eras — if a strength feature is carried, its check is partly a
  re-read. The 11-01 replay also read breakout-v1 R by list rank on the check years, which is B1 / B2's neighbourhood.
- **Fix.** Features 4-6, 7, 15-17 carry the tag "seen on the check years (A+ read 10-22)" on every line; a PICKS THE TAIL on one of
  them prints as "PICKS THE TAIL (check years partly seen)". Keep them in the family (dropping them would cost more than it buys), and
  restate unresolved 6 in §5.3: nothing here answers the #710 RS test.

### 11. The Holm family size and the "ruling" slot are not pinned (MAJOR)
- **Hits §5.3:** *"ONE family of at most 9 = ≤ 4 carried + ≤ 1 combination + ≤ 4 of the operator's reads (three gallery reads and one
  ruling …)"*.
- **Why.** (a) "At most 9" does not say whether Holm's m is 9 or the number actually tested. Either is valid; choosing after the
  p-values are seen is not. (b) In the EP study the ruling arrived late. §5.7 hashes the gallery reads before check, but the ruling
  slot has no such line. A ruling made after check outcomes are seen is post-hoc and cannot share the family.
- **Fix.** m = the count frozen at step 6, printed and hashed with the reads. The ruling slot closes at step 6 too; anything he rules
  after the check run is printed as "after the check — description", outside the family, no verdict word.

---

## MINOR (finding 20 is MAJOR — it was verified late and kept its number)

12. **Embargo (§3, §7A).** Discovery events with E in Oct-Dec 2020 have outcome windows and gallery charts running to about 2021-03.
    The operator's reads are formed with 2021 bars of names that can also be check events. Fix: gallery A and the discovery outcome use
    events with E ≤ 2020-10-05 as an extra reading ("embargoed discovery"), and §7B excludes identities shown on gallery A (the draft
    excludes shown name-nights, not identities).
13. **Era seam (§1.3).** Era A ends at D 2022-03-31, era B is written as starting D 2022-04-04; the replay's seam is D 2022-04-01. The
    night D 2022-04-01 (E 04-04) belongs to neither as written. State it and count it.
14. **File-start artefacts (§4.0, unresolved 8).** Rec for unresolved 8: an event is DROPPED when a gate passed unscored BECAUSE THE
    FILE STARTS (lower line under 189 bars in era B to about 2022-06 and early 2017), and KEPT when the name is simply a short
    listing — the live system would see the same. Add feature 23 (`bases_before`, the same 252-session window as 22) to the NULL-under-90%
    list, and tag B1 in early era B (three of its inputs are on a short year).
15. **Feature 14 (range length)** has no value when the level is the 5-day high, not a range. That is a non-random NULL and it shrinks
    the base group's common set. Fix: test it as two groups first ("level from a range" yes / no), length inside the yes group as
    description.
16. **"Against Qullamaggie's buys" at under 25% (§1.4).** With about 375 buys the sampling error on a third is about 2.4 points, so
    25% is three errors out — a reading that holds 27% of his buys leans against them and escapes the tag. Fix: tag under 29%, print
    the share with its interval. Pre-state which break row stands for an undated buy with a 1-5 session window (the first in it).
17. **B1's population.** The live pick score ranks within the night over the list PLUS the names only a context gate removed
    (`rank_all(extra_inputs)`). Say so and build it so, or B1 is not the live grade. B3 uses a 2026-10-16 industry-code snapshot
    (names gone by 2026 have none) — tag it.
18. **Security type is one 2026 snapshot per ticker, unknown types are admitted** (`security_admitted`). Not a per-night fact in either
    era. Print per era the share of events with unknown type; the "common stock only" extra reading already bounds the effect.
19. **Closed-file list (§1.3) is too short.** Add by name: `cb702/big_winners_1101/`, `_breakout_v1_replay_1101/out/trades.tsv.gz`,
    `walk_stdout.txt`, `report.txt`, `list_eraB.tsv.gz`, `cb702_pre_v2/out/*`, the 2025-26 rows of `cb702_splits.psv` (3,090) and the
    regime rows of `small_pulls.psv`. `bv1_pick_model_1113/fire_paths90.npz` is closes ≤ D only (safe), the capture's `hE` / `lE` are
    not features (already said).
20. **(MAJOR) Era A's early years look thin on names that later died.** `ended_by_year_A.tsv` (the 10-23 data audit; years before
    2025 only): series ending per year, all / liquid non-derivative — 2016 53 / 4 · 2017 45 / 6 · 2018 177 / 46 · 2019 390 / 117 ·
    2020 542 / 105 · 2021 660 / 144. Era B: 2022 1,294 / 200 · 2023 1,698 / 150 · 2024 1,487 / 135. So era B carries its dead names;
    era A carries few for 2016-18 (the 2,669 refetched symbols helped, the early years still read low). **Hits §1.3** *"No
    survivorship drop"*: true of the rule, not shown of the FILE. Names that broke out in 2017-18 and were later delisted are mostly
    non-winners; missing them lifts the 2017-18 base rate and removes failures from the low-price, wide-range end. It also weakens the
    ex-2020 guard (condition 3 leans on 2017-19). **Fix (no network):** stage 1 prints, outcome-free, kept events whose bars end
    inside E..E+60 per year; discovery readings also print on 2019-20 alone as an extra reading; 2017-18 lines carry the tag "few
    delisted names on file". A refetch of dead 2016-18 symbols would be a network pull — his call, not assumed.
21. **§0 misses three earlier looks.** `cb_selection_test_prereg_2026-10-19.md` (does Qullamaggie's own selection beat the average
    base — an outcome read on fills), `cb_track_a_filter_prereg_2026-10-23.md` (a filter from his stream grades) and
    `610_htf_replay_2026-09-10.md` (flag breakouts over five years, R). Add a row each, or one line saying why they do not bear. On
    the draft's own "not read in full" line for the 11-11..11-15 printouts: a file-name-only search of those four documents for
    return words found none — consistent with the draft, still not a full read.

---

## What holds (checked, no change needed)
- Features read bars ≤ D: `v1_gates`, `context_gates`, `range_levels`, `settled_level`, `base_facts`, the strength cross-section all
  index ≤ D; `breakout_triggered` reads E's high only (volume recorded, not used). The corrupt-E proof is the right mechanical test.
- Adjusted prices carry 4 decimals (NVDA 2016 at 0.8073), so later forward splits do not quantise the range features.
- The sealed years: nothing in the design opens 2025-26, provided the sealed copy is rebuilt by the date-column filter
  (`sealed_copy_of_daily`; the old copy lived in a scratch folder that is gone) and finding 3 is settled.
- Fork wording, the ADR ruling, "not a verdict on the setup", gallery before check with a hard stop: as the EP study, no objection.

## Era-B inputs (fork 3b) — files found
| Need | File | State |
|---|---|---|
| Adjusted daily bars 2021-09-27 .. | `apollo_data/cb702/daily_closes_all.csv.gz` (269 MB) | EXISTS; holds 2025-26 rows — must be stream-filtered to < 2025-01-01 (`v1_replay.sealed_copy_of_daily`); the earlier sealed copy is gone, rebuild |
| Splits | `apollo_data/cb702/cb702_splits.psv` | EXISTS; 3,864 rows ≤ 2024, 3,090 dated 2025-26 — read through `load_splits_sealed` only |
| Raw close, 2022-04 .. 06 overlap | `apollo_data/cb702_pre_v2/daily_raw_close.csv.gz` | EXISTS; the bridge that makes raw exact for 8,518 tickers |
| Raw close per name-night 2022-04 .. 2024 | — | **DOES NOT EXIST as a file.** Derived by `v1_replay.era_b_raw_factor`; split-list-only for 7,184 tickers |
| Raw close pulls (Polygon, unadjusted) | `cb702/raw_close_bv1_1101.csv.gz` (192 tickers, 16,266 rows), `cb702/raw_close_tgrid_1101.csv.gz` (245 tickers, 39,626 rows); both 2022-04-01 .. 2024-12-30 | EXIST; 326 tickers in all, requested for the 10-31 rule set's list — far short of today's list |
| Security type | `apollo_data/cb702/small_pulls.psv` (14,102 `sectype` rows) | EXISTS; one snapshot per ticker, NOT per night; its 424 regime rows are dated inside the seal — not read |
| Fund names | the committed 2026-10-28 names (`v1_replay.load_etv_names`) | EXISTS (92 funds typed, 90 named) |
| Symbol guard | `scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv` | EXISTS, but NOT wired in `load_store("B")` (`breaks = {}`) |
| Industry codes | `apollo_data/cb702/cb702_sic.psv` | EXISTS (2026 snapshot; B3 only) |
| Loader that already did era B | `scripts/probes/_breakout_v1_replay_1101/v1_replay.py::load_store("B")` | EXISTS; ran 690 nights D 2022-04-01 .. 2024-12-30 on 11-01 |

**Verdict on 3b's inputs: PARTIAL.** Bars, splits, types and a working loader are local. The raw close is exact for 8,518 tickers
and derived for 7,184 (about 9% of list rows on the 11-01 list; today's wider list not counted); making it exact for today's wider list needs one more unadjusted pull, which the draft's "no network"
line rules out. That is finding 3 — his call between the pull, the tag, or falling back to 3a.
