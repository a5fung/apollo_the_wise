# BREAKOUT big-winner chart study — what do the charts of breakouts that became big winners share? (pre-registration v2, FROZEN 2026-11-26 on his "go"; no outcome read before the freeze)

**DRAFT v2 — design only.** Written Tue 2026-11-24 PT. The breakout twin of the frozen EP study
(`docs/analysis/ep_winner_study_prereg_2026-11-21.md`, "the EP study" below); same structure, with the EP study's own
amendments and the operator's rulings on it built in from the start. **v2 resolves the adversarial critique**
(`scripts/probes/_breakout_winner_study_1124/design/critique.md`: 3 blockers, 9 major, 9 minor) — see "Critique
resolutions" at the end; draft history is `design/prereg_draft_v1.md`. Nothing was run that reads a price after a break day.
Every count below is **indicative**: era A only, identity = ticker, from the 11-13 list capture (columns
`ci / ticker / fire` only), which predates the 11-14 context gates — `design/count_events_v2_forward_hash.py` → `.txt`
(v1's `count_events_outcome_free.*` is kept as history). Spread numbers in §5.4 come from `design/spread_sim_v2.py` →
`spread_sim_v2.txt` (synthetic labels only; v1's `spread_sim.*` kept because the critique's re-run reads it).
**FROZEN Thu 2026-11-26 PT** on the operator's "go" to run the study (11-26, after his 11-24 "go with recs" on forks 1a/2a/3b/4); sha256 of this file is recorded in the freeze commit's PLAN.md #717 line. Nothing in §6 ran before this commit.

**Cost of the whole REMAINING path, stated once.** **$0 paid.** One free network pull (stage 1c: unadjusted daily bars
from Alpaca with the existing keys — at most about 7,800 tickers × 690 sessions ≈ 5.4 million rows, about 540 pages, a
few minutes, run ONCE and captured to a file). Local compute: one list rebuild over about 1,950 nights (1,322 in era A,
about 630 in era B) plus feature, calibration and permutation runs — two to three hours of laptop time. Agent cards
still to spend: **about 3 Fable + 7 Sonnet** (stage 1 build incl. the era-B rebuild and the pull · calibration ·
discovery · blind recount + adversarial review · gallery · freeze of the operator's reads · check + its recount ·
blind sheets), staggered, never three at once. Already spent: 1 design card, 1 critique card, 1 revision card.
An entry / exit arm (fork 4) is NOT in that number: the EP study's arm cost a minute-bar fetch and about 4 more cards.

**✅ FORKS RULED 2026-11-24 — the operator: "go with recs" → 1a (live breakout-v1 breaks), 2a (+50% in 60 sessions), 3b (add 2022-04..2024 by rebuilding the list, cut 2024-12-31), 4: left to #720.** Original table kept below.
**✅ ERA-B RAW CLOSE RULED 2026-11-24 (critique blocker 3; ruling as handed to the v2 revision): option (i) — ONE
raw-close pull for the era-B names whose raw price rests on the split list alone, run as stage 1c of the eventual run
(Alpaca daily bars, `adjustment=raw`, free, captured once and read many). The pull requests ONLY dates ≤ 2024-12-31.
Not performed yet.** This replaces v1's "no network" line; nothing else touches the network, a DB or a paid API.

**The operator's forks (as put to him; all four are ruled above):**
| # | Fork | Options | Recommendation |
|---|---|---|---|
| 1 | Which breakouts are studied | (a) every break of the LIVE breakout-v1 rule set · (b) a looser, gate-free breakout definition (the #705 "measurable breakout" kind) | **(a)** — it is the setup as Qullamaggie trades it and as wired; (b) would study charts the list never shows. |
| 2 | What counts as a big winner | (a) the EP study's: a close at least +50% above the buy point within 60 sessions, +100% as the stricter tier · (b) another size or window | **(a)** — same yardstick as the EP study, so the two can be read side by side. |
| 3 | The check years | (a) 2021 to 2022-Q1 only (what is already built) · (b) add 2022-04 to 2024 by rebuilding the list there, cut at 2024-12-31 | **(b)** — it roughly doubles the chance of finding a real 1.5x reading (about 25-50% → 55-80% at a 5% base rate, §5.4), and (a) alone is 15 months of one market. |
| 4 | Entry / stop / exit replay on these breakouts | (a) now, as an arm of this study · (b) left to the periodic trade review #720 | **(b)** — this study answers "which charts"; keeping the money is #720's question and needs a minute-bar fetch. |

- ⚠ **Fork 3's figures moved in v2** (the row above is kept as it was ruled on): on the corrected event rule and
  counts the chance of finding a real 1.5x is about **17-37% → 37-67%** (30-57% if 2022-24 holds fewer winners), and
  the "5%" is the rate OUTSIDE 2020 (§5.4). (b) still about doubles (a) at every setting, so the ruling's basis holds.
- ⚠ **Fork 1a's population, said exactly (critique 7):** the study covers **list names whose level was taken out on the
  next session**, not "what the live rule buys". The live entry (`broker/breakout_v1_entry.evaluate`) buys the break of
  max(the first five minutes' high, the list level) and stands aside when the day's low is more than one daily range
  under it; a break inside the first five minutes or on a too-wide day is in this study and is never bought (§8).

**Why.** The operator's words 2026-11-21 (`docs/methodology/operator_shared_notes.md`): *"Qullamaggie suggests to review
1000s of charts to find edge"*, and his order of work 11-21/22: *"EP first, then breakout"*. The EP study found chart
readings that mark the tail on gap days (high daily range 8.3x, deep base, low price, a short run-up) and reversed three
of the operator's own gallery reads. This study asks the same of breakouts, then puts the strongest in front of his eye.

**What this is NOT.**
- Measurement only, $0 paid, local files plus the one free pull of stage 1c. No live change, no ranking change, no
  gate, entry, stop or exit proposal (THE LINE).
- **Not a test of the detection rules.** Breakout v1 is detection as Qullamaggie trades it, judged ONLY on keeping his
  buys (#717). No result here is a reason to add, drop or move a list gate or the pick model. **The benchmarks (§4.1)
  are not a test of the grade either.**
- **Not a grading of Qullamaggie's buys.** They are ground truth. They are used outcome-free only (§1.4); they are
  never tabulated against an outcome, and the scorecard's `big_winner` column is never read.
- **Not a verdict on the setup.** Qullamaggie's breakouts paid him for years; a null here is our measurement, not "no
  edge". The sentence printed if nothing reaches the bar is frozen in §5.3.
- **The operator's eye is the judge; a chart feature only leans the odds.** The tail is measured, never the median.

## 0. What is already known (disclosed, so nothing is re-run blind and prior looks are counted)
| Earlier read | Population | Target | What it found | Bearing here |
|---|---|---|---|---|
| **EP study** (11-21/22) | 4,665 gap days 2016-24 | +50% close in 60 sessions | PICKS THE TAIL: daily range (ADR20) 8.32x, base depth 7.35x, low price 2.93x, small gap in daily ranges 2.89x, 20-day run-up 2.47x; the operator's three "downtrend" reads REVERSED | Sets the expected direction of features 1, 2, 8, 13 and 21-22 on a different setup. Discovery stays two-sided; the expectation is disclosed, not used. |
| #702 trendline breakout backtests (10-18/19) | trendline fills 2017-24 by cell | realized R | discovery +0.32R on the primary cell, 2017-21 "can't tell" | R outcomes of an OLDER breakout rule set were seen on every opened year. |
| **#702 P5 holdout read** (`cb_preregistration_2026-10-18.md` §RESULT, run once 2026-10-19) | 2025-01 .. 2026-10-15 | realized R | FAIL (the primary cell −0.72R on 30 trades) | **2025-26 was read once, for that old rule set. Everything else there stays sealed (#710); this study opens none of it.** |
| **#705 big-winner recall** (`cb_big_winner_recall_2026-10-22.md`) | every +100% (994 / 414) and +50% (4,182 / 2,381) winner of 2017-21 / 2022-24 | recall | about half begin with a measurable breakout; misses are "under the 50-day", "no 30% prior move", "already resolved"; of trendline fills 10.5% / 7.9% sat inside a +50% winner's early window | **The NAMES of 2017-24 big winners and their gate-failure shares were seen.** The 10.5% / 7.9% is the only hint of a base rate, on a different event definition — used for the §5.4 grid range only. |
| `big_winners_1101/big_winners_2017_2024.tsv.gz` (11-01) | the same winners joined to breakout v1 | listed / broke / filled, gate pass flags | per-winner v1 gate passes and realized R | Outcome-conditioned gate shares were seen. **Never an input here.** |
| #705 A+ rating (`cb_aplus_rating_prereg_2026-10-21.md`, 10-22) | trendline fills, both eras | trades of 10R+ per 100 | seven concepts (contraction, volume dry-up, RS leadership, prior move, stair-step, expansion, volume pace): can't tell; RS leadership alone highest (1.76 / 1.74 per 100) | **A prior feature-vs-tail look** at what are features 4-6, 7, 15-17 here, on older fills. RS leadership alone is registered for the sealed test (#710); this study reads strength on opened years only and does not replace that test. |
| #702 / #705 R decomposition, breakout definition, entry-stop retry, trail variants (10-22/23) | trendline fills | realized R | the tail carries the mean; stops end most trades early | Outcome looks on fills, not on chart features. |
| #705 reverse-engineering of Qullamaggie's rules (`cb_reverse_engineer_his_rules_prereg_2026-10-24.md`) | Qullamaggie's stream panel vs what was available | Qullamaggie's picks; his exits vs ours | scan: ADR20 ≥ 4.26%, not down more than 5.8% over 60 sessions, a 52-week high within 233 sessions; its EXIT stage read the results of his 2020-22 trades (his exits 1.73x of cost vs ours 1.50x) | Features 1, 9, 10 were fitted to QULLAMAGGIE'S PICKS (not to outcomes). The results of his own trades were seen by name — one more reason his buys are never tabulated by outcome here. |
| 11-01 paper baseline replay + template grid (`breakout_v1_paper_replay_prereg_2026-11-01.md`, `..._template_grid_...`) | breakout v1 (the 10-31 rules), 2017-2024, 5 slots | realized R | 1,639 trades −0.245R; list ranks 1-5 read worse than 11-40; per-year R seen | **R outcomes of breakout v1 were seen on 2017-2024, by year and by list rank.** The check years are out-of-time but not untouched. |
| 11-01 spot-check of Qullamaggie's 28 biggest buys | Qullamaggie's buys replayed with OUR exit | 5R+ | strength and shape misses look the same on his winners and losers; trades after a wide up day lost 68% | A prior look at feature 19's neighbourhood; the replayed outcomes of Qullamaggie's buys were seen by name. |
| 11-11 rating, initial rules, shape gates; 11-12 ADR floor; 11-13 pick model; 11-14 rank / context / extended / low line / wide-loose; 11-15 grades | Qullamaggie's 757 buys, the operator's 41 list grades, era-A list rows | Qullamaggie's buys and the operator's grades | the current gates, the pick model and its grades | Registered against Qullamaggie's buys and the operator's grades, not returns; a word search of five of the printouts found no return column, **the rest were not read in full (not verified)**; the critique's file-name search of those four documents for return words found none — consistent, still not a full read. The scorecard's `big_winner` flag (26 dated buys) was COUNTED in head-to-head tables ("big winners in the top 5"). The pick model was fitted on Qullamaggie's picks 2017-2020 — in-sample for benchmark B1 on discovery, said wherever B1 prints. |
| `cb_selection_test_prereg_2026-10-19.md` | trendline fills | realized R | asks whether Qullamaggie's own selection beats the average base — an outcome read on fills (per the critique; not re-read for v2) | A prior outcome look on an older rule set's fills; no feature here was chosen on it. |
| `cb_track_a_filter_prereg_2026-10-23.md` | trendline fills | realized R | a filter built from Qullamaggie's stream grades (per the critique; not re-read) | A prior filter-vs-outcome look; the neighbourhood of benchmark B1. |
| `610_htf_replay_2026-09-10.md` | flag breakouts over five years | realized R | a replay of the flag detector (per the critique; not re-read) | R outcomes of a different breakout-family detector on opened years. |
| Live paper book (from 11-09) | 2026 | — | — | Sealed years; not opened. |
| **Slip while drafting (2026-11-24)** | — | — | a `head -3` of `big_winners_2017_2024.tsv.gz` to learn its columns printed two outcome rows (AKAO 2017, NKTR 2017: gain and replayed R) | Two discovery-year names seen as winners; no feature was chosen on them; the file was not opened again. |
| **Reads made for v2 (2026-11-24, all outcome-free)** | — | — | the capture's `ci / ticker / fire` columns and its calendar file (the recount); the first rows of both guard files (two era-B and two era-A tickers with their break dates were printed); a per-year count of era-B guard break kinds (the pass ran over the file's post-2024 rows and printed only years ≤ 2024); code and headers of the chain files | No price after a break day, no outcome file, no 2025-26 value was printed or used. |

**What has been SEEN on the check years (2021-24):** big-winner names (#705); breakout-v1 R by year and by rank (11-01);
Qullamaggie's buys and their results by name; the EP study's confirm results on the same years' gap days.
The split in §3 mirrors the EP study's and was chosen knowing all of that.
**Seven candidate features were already read against the tail on the check years** (the A+ rating row: features 4-6,
7, 15-17, both eras; RS leadership read highest in both) and breakout-v1 R was read by list rank there (B1 / B2's
neighbourhood). They stay in the family and carry the tag **"seen on the check years (A+ read 10-22)"** on every line
(§5.3). Nothing here answers the #710 RS-leadership test, which is registered for the sealed years.

## 1. Population (to be fixed at freeze; counts printed without outcomes)
**1.1 The break (fork 1a).** A row = (identity, night D, break day E = the next session of the era calendar) where
- the name is on breakout v1's nightly list at D under the LIVE rules — `breakout_v1.v1_gates` (history, universe $2 / $5M,
  pinned, ADR20 ≥ 4%, strength rank ≥ 35, prior move ≥ 20%, base depth 1.51-11 daily ranges, close vs EMA21 ≥ −0.9), which
  itself calls `breakout_v1.context_gates` (not under a falling 50-day, not a 6-month downtrend, not a re-widening base on
  a flat or falling lower line). A list row is a row with **no failed gate**;
- on E the high takes out the level: `breakout_triggered` (the daily-bar proxy of the buy; no volume condition, as wired).
- **Code is CALLED at one pinned commit, never re-coded, and the pin covers the whole chain** (critique 4b): the commit
  sha is written here at freeze and the run asserts it, plus the sha256 of each file the list passes through —
  `agents/market_intelligence/breakout_v1.py`, `breakout_v1_list.py` (`scan_members`, `evaluate_members`,
  `night_cross_section`, `rank_all`), `consolidation_breakout.py` (`cross_section_one_date`, `percentile_ranks`,
  `_dollar_vol_median`), `breakout_v1_pick_model.py`, `scripts/probes/_breakout_v1_replay_1101/v1_replay.py`
  (`load_store`, `night_members`, `era_b_raw_factor`, `sealed_copy_of_daily`, `load_splits_sealed`, `load_types`,
  `load_etv_names`), `scripts/probes/_cb_backtest/runner.py` (`break_mask`, `load_breaks`),
  `scripts/probes/_717_precision_1112/01_precision.py::setup`, `_717_pick_model_1113/01_build.py` — and of the two
  buys fixtures (`buys.tsv`, `buys_undated_widened.tsv`). `v1_replay.night_members` is a COPY of `scan_members`; the
  11-01 replay's `parity` stage (which asserts the two equal on sampled nights) is **re-run at the pinned sha** and
  must pass. The system changes weekly; the pinned sha is the rule era this study describes.
- **The build sets its own scratch folder** (`01_precision.py` sets `BV1_SCRATCH` at import to a folder that no longer
  exists; both scripts have a `__main__` guard, so they are imported, never run) and **rebuilds the sealed era-B bar
  copy** itself (§1.3) rather than inheriting one.
- **Bridge check, era A (critique 4a — "context gates off" is DEFINED, not switched):** `v1_gates` has no context
  switch. One call per name-night; the bridge row set is `set(g["failed"]) <= set(CONTEXT_GATES)` — exactly the live
  `context_only` test in `evaluate_members`, plus the rows with no failed gate. That set must reproduce the 11-13
  capture: 420,158 rows, 156,695 break rows on 1,322 nights, median 68 a night, 375 of Qullamaggie's 757 buys on a
  break row. A mismatch stops the run unless every difference is traced to a named rule change after 11-13. (Expected
  to hold: `git diff 0210a5f0..HEAD -- breakout_v1.py` is the context block only, +183 / −1. Not proven until run.)
- **Bridge check, era B (there is no capture to bridge to):** both stores hold 2022-04 .. 06. Nights D 2022-04-01 ..
  2022-06-29 are built from BOTH stores; list membership and break agreement are printed per gate for names in both
  (gates and features needing under 130 bars only). No pass line is frozen blind: under 99% agreement on any gate,
  every difference is traced to a named cause (pool membership, adjustment date, a twin series) before stage 1e; an
  untraced difference stops the run.

**1.2 One event per identity per 60 sessions — decided on rows dated ≤ D only (critique blocker 1).** A name on the
list breaks its level again and again — the median ticker has 22 break rows — so break rows are not independent events.
- **v1's rule was wrong and is withdrawn.** It kept a row by what lay 60 sessions EITHER side; the later half of that
  neighbourhood exists only if the stock went on to set and break new levels, so membership depended on the event's
  own future. The critique's synthetic demo read 1.05x-1.57x on a feature with NO true effect.
- **PRIMARY unit (v2).** Each identity's break rows are walked forward in time, across both eras as one sequence. A
  row is ELIGIBLE when no KEPT row of that identity lies in the 60 sessions before it. An eligible row is KEPT when
  `sha256("1124|<identity>|<D as yyyy-mm-dd>")`, its first 8 bytes read as a fraction of 2⁶⁴, is under **q**. `<identity>` is a fixed string: the identity's era-A ticker when
  it has one, else its era-B ticker (the alphabetically first if an era holds several) — never a map-assigned
  number, which would depend on build order. Nothing
  dated after D enters the decision; outcome windows of one identity never overlap. A hash (not a stream of random
  draws) so the blind recount reproduces it whatever its loop order; the D string, not a row index, because row
  indices differ between the era files.
- **Every drop runs BEFORE the walk and reads nothing after E** (§1.3: guard or adjustment flag in D−85..E, a gate
  passed unscored because the file starts, E+60 past the file end or the 2024-12-31 cut). A dropped row is not a
  break row for the walk. Nothing dated after E ever removes a row — a later guard break only shortens the outcome
  window (§2).
- **q is set outcome-free by a rule fixed here:** the LARGEST q on the grid {1, 1/2, 1/3, 1/4, 1/5, 1/6, 1/8, 1/10} at
  which the share of kept events that are "a first break after 10 quiet sessions" is at most **twice** that share
  among all break rows (both eras pooled, seed 1124). Stage 1e applies the rule on the real list and prints the grid.
  On the indicative capture the rule gives **q = 1/5** (`count_events_v2_forward_hash.txt`).
- **Why not q = 1 ("the first break, then the next after 60 sessions") and why the mix cannot be matched exactly.**
  Any rule that looks only backward keeps the START of a cluster more often than its later rows. On the capture, first
  breaks after 10 quiet sessions are 15.2% of break rows and 14.4% of Qullamaggie's 375 break-row buys, but 77% of
  kept events at q = 1, 38% at 1/3, **30% at 1/5**, 25% at 1/8 — at a cost in events (15,312 / 12,384 / **10,514** /
  8,621). The 2× rule is the trade between describing what the list fires (and what he buys) and keeping power.
  **Stated: kept events are first-break-heavy by about 2×.** Two readings cover it (§5.5): every carried feature is
  printed apart for first breaks and later breaks (knowable at D), and on a second seed (2411).
- Thinning keeps about 1 break row in 15, so only about 36 of his buys land on a kept event; his position tables
  (§1.4) therefore use all 375 of his break-row buys, not the kept events.
- Indicative size, era A, per ticker, before the context gates and before the §1.3 drops: **10,514 events** (n = 10,514) (2017 814 ·
  2018 1,232 · 2019 1,198 · 2020 3,439 · 2021 3,083 · 2022-Q1 748), 3,054 tickers, 64 months, smallest month 20
  (v1's withdrawn rule: 13,461). The second seed gives 10,545 with 1,108 events in common. The context gates and
  the drops will cut this by a share not yet known (stage 1 prints it); §5.4 is simulated at 100% and 60%.

**1.3 Years, files, drops.** Eras are never stitched (the EP study's rule).
- **Era A: D 2016-12-30 .. 2022-03-31** (E to 2022-04-01), bars `cb702_pre_v2/daily_closes_all.csv.gz` (2016-01-04 ..
  2022-06-30), raw closes `cb702_pre_v2/daily_raw_close.csv.gz`, guard `cb702_pre_v2/symbol_guard.tsv`.
- **Era B (fork 3b): D 2022-04-01 .. the last D whose E+60 is a session ≤ 2024-12-31** (E to about 2024-10-04; 30
  months), bars `cb702/daily_closes_all.csv.gz` (starts 2021-09-27).
- **The seam (critique 13):** the night D 2022-04-01 (E 2022-04-04) belongs to era B, as in the 11-01 replay; era A is
  the only source for D ≤ 2022-03-31. Stage 1 prints the event count on the seam night and asserts no (identity, D)
  appears in both eras.
- **The 2024-12-31 cut, era B.** The bar file holds 2025-26 rows: the build stream-filters it to rows dated
  < 2025-01-01 into its own sealed copy (`v1_replay.sealed_copy_of_daily`), reads only that copy, and asserts the copy's
  last date. Splits are read through `load_splits_sealed` only (3,864 rows ≤ 2024; the 3,090 rows dated 2025-26 are
  never parsed). The era-B guard file was built on the full store: its break dates after 2024-12-31 are dropped at
  read and counted, never used.
- **Era-B raw close per name-night (critique blocker 3, ruled option (i)).** No such file exists. The 11-01 loader
  derives it: exact for the 8,518 tickers bridged across the two stores, and from the split list ≤ 2024 alone for
  7,184 tickers — wrong by the split factor for a name that split in 2025-26, which is sealed-year information leaking
  into the $2 floor and into feature 2. **Stage 1c pulls the unadjusted close for those names** (§6, with its own gate).
  The pulled closes replace the derived ones BEFORE the era-B pool is built — the $2 floor sits in the strength pool
  itself (`scan_members` / `night_members`), not only in `v1_gates`, so the pool, the ranks and the list are built
  once, on corrected prices. Each event carries `raw_src` = bridged / pulled / derived-only. Derived-only = ANY
  split-list-only name-night without a pulled close that passed the gate (not requested, not returned, or failed):
  it stays, the $2 floor uses the derived value, **feature 2 is NULL**, the count of such events
  within a factor of 10 of the $2 floor is printed, and if they exceed 1% of era-B kept events every era-B line
  carries the tag **"era-B price partly derived"**. (A derived-only name with a wrong price can also sit in or out of
  the strength pool wrongly and nudge other names' ranks; stage 1c prints the derived-only share of pool name-nights.)
- **Security type (critique 18)** is one 2026 snapshot per ticker in both eras (`small_pulls.psv` `sectype` rows only;
  its 424 regime rows are dated inside the seal and are never read), and `security_admitted` admits unknown types.
  Stage 1 prints, per era, the share of events with an unknown type; the "common stock only" reading (§5.5) bounds it.
- **Identity and adjustment guard (critique blocker 2a).** Both guard files are wired (era A's is already in the list
  chain through `break_mask`, which looks at the 86 bars ending D; era B's `load_store("B")` sets `breaks = {}`, so it
  is applied here as an event filter and the era-B list itself stays as the live code makes it). An event is DROPPED,
  counted per era and year, when a guard break or a split-list date not reflected in the bars falls in the calendar
  sessions D−85..E.
- **File-start artefacts (critique 14; closes v1's unresolved 8).** An event is DROPPED when a gate or context check
  passed unscored BECAUSE THE FILE STARTS — the name's first bar is within 5 sessions of the era file's first date
  and the check's look-back reaches before it (the 189-bar lower line in era B to about 2022-06 and in early 2017).
  It is KEPT when the name is simply a short listing: the live system would see the same. Otherwise live-code gate
  values stay "as the live system would have seen them".
- **Window end.** An event needs the calendar session ci(E)+60 inside its era's file (era A) or ≤ 2024-12-31 (era B);
  others are dropped and counted.
- **Survivorship (critique 20).** The RULE drops no one: a name that stops trading inside its window stays and its
  window ends where its bars end. The FILE is thinner than the rule: the 10-23 data audit shows era A holding few
  names that later died for 2016-18 (series ending per year, all / liquid non-derivative: 2016 53 / 4 · 2017 45 / 6 ·
  2018 177 / 46 · 2019 390 / 117 · 2020 542 / 105 · 2021 660 / 144; era B 2022 1,294 / 200 · 2023 1,698 / 150 ·
  2024 1,487 / 135). Missing failures lift the 2017-18 base rate and weaken the without-2020 guard. Stage 1e prints,
  outcome-free, the kept events whose bars end inside E..E+60 per year; **2017-18 lines carry the tag "few delisted
  names on file"**; discovery readings also print on 2019-20 alone (§5.5). **No refetch of dead 2016-18 symbols is
  planned** (decided here: the tags and the 2019-20 reading bound it; a refetch would be a second pull).
- **Era-B volume underflow (critique 5 = EP critique D2).** Era-B bars are adjusted as of 2026-10-16; volume divided
  by a later reverse split's factor can round to 0, and the list puts the 20-session median of close × volume against
  the $5M floor every night — so a later reverse-splitter can fall off the era-B list on sealed-year information.
  Stage 1e re-runs the EP study's outcome-free test on THIS population: era-B name-nights failing only the
  dollar-volume half of the universe gate with a zero-volume row in the 20-session window, by adjusted-price level.
  Over 1% of era-B list rows → every era-B line carries **"era-B population thinned by volume underflow"**. Features
  3, 17, 18 are NULL when their window holds a zero-volume row. The stage-1c pull also captures raw volume for its
  names, used ONLY to print how many underflow name-nights would have passed the floor on raw numbers — membership is
  not repaired (that would be re-coding the list).
- Identity across eras: the EP study's map (`_ep_winner_study_1121/build/stage1/identity_pairs_all.tsv`, amendment A2),
  rebuilt for these tickers by the same code. Status-suffix symbols (5 letters ending in Q) are printed and never shown.
- Funds: the live `security_admitted` rule decides (stocks, ADRs, single-asset funds). Printed per type.
- **Files that stay CLOSED, by name (critique 19):** `features_eraB.parquet`; every `*_holdout*` file; every 2025-26
  store; `cb702/big_winners_1101/` (all of it); `_breakout_v1_replay_1101/out/trades.tsv.gz`, `walk_stdout.txt`,
  `report.txt`, `list_eraB.tsv.gz`; `cb702_pre_v2/out/*`; the 2025-26 rows of `cb702_splits.psv`; the regime rows of
  `small_pulls.psv`; any `trades*`, `walk*`, `report*`, `big_winners*` file. `bv1_pick_model_1113/fire_paths90.npz` is
  closes ≤ D only (safe). The capture's `hE` / `lE` columns are never features.

**1.4 Qullamaggie's 757 buys — outcome-free, three uses only.**
1. Coverage: how many fall on a break row and on a kept event, per year, printed in stage 1.
2. Position: for every feature, the share of his break-row buys (about 375) that sit in the top / middle / bottom third
   of that night's month group — printed BEFORE any outcome, each share with its 90% interval. An undated buy with a
   1-5 session window is placed on the FIRST break row inside its window. A carried feature whose winning third holds
   **under 29%** of his buys is tagged **"against Qullamaggie's buys"** on every line (a rule that drops his buys is
   the defect). Why 29 and not v1's 25: on about 375 buys a third's share has a sampling error of about 2.4 points,
   so 25% sat three errors out and a reading holding 27% of his buys escaped.
3. Exclusion from the blind sheets (§7B). Sources: `tests/fixtures/qm_breakout_scorecard/buys.tsv`,
   `buys_undated_widened.tsv` — columns `ticker / E / lo / hi` only.

## 2. Outcomes (buy-point proxy = max(level(D), open(E)) — the level, or the open when the stock gaps through it)
- **The window is CALENDAR sessions ci(E) .. ci(E)+60 of the era calendar** (critique 2b), never "the next 60 rows":
  a name with missing bars gets fewer bars, not a longer window.
- **The window ends early, mechanically (critique blocker 2; fixed now, no by-hand call after outcomes):** at the
  session before (i) any guard break dated E+1 .. E+60, or (ii) any close-to-close move of ≥ +70% or ≤ −50% that falls
  on a split date — era B: a row of the split list (≤ 2024-12-31, through `load_splits_sealed`); era A: a session
  where the raw ÷ adjusted close factor steps (era A has an exact raw close per bar and no split list in its
  loader). A reused ticker, a twin series or an unapplied split there would otherwise
  print a "+50% close" no holder received. Truncated events stay, are counted per era and year, and are tagged.
  **Before discovery opens, stage 1e prints outcome-free how many kept events have a guard or split-list date inside
  their window.** The frozen rule costs some real winners (a true +70% day on a guard date is cut); the un-truncated
  outcome is printed as an extra reading (§5.5) so the size of that is seen.
- **PRIMARY — big winner (fork 2a):** highest close over the window ≥ **1.5 ×** the buy-point proxy. E's own close counts.
- **MONSTER tier:** ≥ **2.0 ×**, same window. Reported beside the primary; never a bar; "thin" under 60 monsters.
- **Clean winner (description only):** a big winner with no session low under low(E) between E+1 and the first +50%
  close — "would the day-low stop have survived it". Never a bar; the real stop question is fork 4.
- **ADR-scaled tail (description only):** highest close ≥ proxy × (1 + 8 × ADR20/100).
- **Failed (description; the gallery's contrast pool):** highest close over the window < 1.10 × the proxy.
- **The proxy is LOWER than the live buy (critique 7).** The live rule buys the break of max(first-five-minute high,
  level), so on a gap through the level its buy is at or above the five-minute high, never the open — the proxy
  understates the buy most on gap days and on wide-ranging names (features 24 and 1). Two extra readings bound it
  with daily bars only (§5.5): the outcome measured from **max(level, high of E)** (the worst buy of the day), and
  the outcome over **E+1 .. E+60** (E's own close excluded — the break day's strength is then out of the outcome).
- **Daily range is NOT treated as a confound** (the operator's ruling 2026-11-21, EP study §11.3: *"we shouldn't
  penalize high ADR stocks for it"*). The ADR-neutral reading is printed for every carried feature as description; it
  gates nothing and re-words no verdict.
- The base rate of the primary is **not known** and is not estimated here. Stage 3 prints it first — the 2017-19 rate
  on its own line, because that rate (not the pooled one) picks the row of §5.4.

## 3. DISCOVERY / CHECK split (by break day, the EP study's cut)
| Set | Rule | Indicative events (before the context gates and the drops) |
|---|---|---|
| **DISCOVERY** | E ≤ 2020-12-31 (era A) | about 6,700 (2020 alone about 3,400) |
| **CHECK** | E ≥ 2021-01-01: era A to 2022-04-01, plus era B (fork 3b) | era A about 3,800; era B not counted (assumed about 2,700 in §5.4 — the 2017-19 mean × 2.5 years) |
- Out-of-time, both eras printed apart. Known weaknesses: discovery is half 2020; one identity can sit in both sets;
  the check years are partly seen (§0); 2025-26 stays sealed.
- **Embargo (critique 12).** Discovery events with E after 2020-10-06 have outcome windows and charts running into
  2021 — the check years. So (a) **gallery A draws only from events whose whole window ends by 2020-12-31
  (E ≤ 2020-10-06)**: no chart the operator forms a read on shows a 2021 bar; later 2020 winners are rendered on
  request after the check run; (b) every discovery reading is also printed on that "embargoed discovery" set (§5.5);
  (c) the blind sheets exclude every IDENTITY shown on gallery A (§7B).
- Five features (10, 11, 21, 22, 23) are NULL in era B until about 2022-09, so their era-B check set is about 25
  months; step 6 prints the check n per feature and era before the check opens.

## 4. The candidate chart features (24 in 12 groups, plus 4 benchmarks; ALL knowable when price crosses the level on E)
### 4.0 Rules for every feature
- **Inputs:** the name's daily bars dated ≤ D, the level computed at D, and — for group "open" only — open(E). **Never
  E's high, low, close or volume, and nothing after E.**
- **Membership uses E's high** (the break itself), as the EP study's used E's volume: features are clean, the population
  is "listed names whose level was taken out". **This selects on E-day strength unevenly (critique 6):** a name that
  closed 2 daily ranges under its level is here only if it rallied 2 ranges on E; a name sitting on its level needed
  nothing. Every feature tied to the gap between close(D) and the level (tightness 15-16, extension 19, distance to
  the high 10-11, shape 20) therefore compares "needed a huge day" with "needed no day", and feature 24 is the
  sharpest case (a low opening gap is in the population only if the stock then ran through the level intraday — the
  EP critique's collider). Handling, fixed now: **benchmark B4** (distance from close(D) to the level, in daily
  ranges; knowable at D) prints on every table; every carried feature also prints its ratio within B4 thirds and is
  tagged **"break-day selection"** when that ratio is under a floor (§5.2); feature 24 is never pooled (§4.1).
- **Gate values are read as the live code computes them** at the pinned sha (columns of `v1_gates` / `context_gates` /
  `shape_gates` / the pick inputs). **These — about half the features, and list membership itself — are NOT under the
  calendar-window rules:** the live code works on rows and passes a check it cannot score. What v2 puts on top
  (critique 2a, 14): the event-level drops of §1.3 (a guard or adjustment flag in D−85..E; a check passed unscored
  because the file starts), and **features 10, 11, 21, 22, 23 are NULL** when under 90% of their 252-session (200 for
  feature 21) window is present or a guard break lies inside it. Stage 1 prints, per feature and per gate, the events
  scored on short history or passed unscored, by era and year. B1 is tagged "short year" in era B before about 2022-09
  (three of its inputs sit on a short year).
  Other features use CALENDAR-session windows with the EP study's NULL rules
  (§4.0 there: history · coverage under 90% · adjustment · identity · zero volume for volume features), each NULL
  counted per feature × era × year × reason.
- **Corrupt-E proof, all features and benchmarks:** on a seeded 600-event sample, E's high / low / close / volume and
  every later bar are replaced with garbage (three patterns); 0 values may change. A positive control (a deliberately
  leaky feature) must change. Features of group "open" are additionally proven to move only with open(E).
- **Gate-truncated features** (marked ✂): the list already cut their range, so a NOT CARRIED says nothing about the gate.
- **Seen features** (marked ◐): read against the tail on the check years before (the A+ read 10-22, §0). Tag on every line.

### 4.1 The list
| # | Group | Name | Definition (bars ≤ D unless stated) | Prior look |
|---|---|---|---|---|
| 1 | volatility | Daily range ✂ | ADR20 at D (the gate's value; floor 4%) | EP 8.32x; Qullamaggie's scan (10-24) |
| 2 | size | Price | raw close at D (era B: bridged or pulled; NULL when derived-only, §1.3) | EP 2.93x for LOW |
| 3 | size | Dollar volume ✂ | 20-session median of close × volume | best simple ranker of Qullamaggie's picks (11-13) |
| 4 | strength | Strength rank, best ✂ ◐ | `rs_best` (the gate's value, floor 35) | A+ read: RS highest |
| 5 | strength | Strength rank, 1 month ◐ | `rs_1m` percentile over the night's pool | pick-model input |
| 6 | strength | Strength rank, 6 months ◐ | `rs_6m` | pick-model input |
| 7 | run-up | Prior move ✂ ◐ | the gate's run into the pole top (floor 20%) | A+ read |
| 8 | run-up | 20-session run-up | close(D) / lowest low of D−19..D − 1 | EP 2.47x for HIGH |
| 9 | run-up | 6-month move | `runup6m_at` | Qullamaggie's scan (not down over 60 sessions) |
| 10 | highs | Distance below the 52-week high | close(D) / highest high of the 252 sessions to D | Qullamaggie's scan; pick-model input |
| 11 | highs | The level IS a 52-week high (two groups) | level(D) ≥ highest high of D−251..D | new |
| 12 | base | Base length | sessions from the pole top to D (`base_len`) | pick-model input |
| 13 | base | Base depth, % | 1 − lowest low / highest high over the base (pole top+1 .. D) | EP 7.35x for DEEP |
| 14 | base | The level comes from a range (two groups) | yes when the level is a qualifying range's (`range_levels`), no when it is the 5-day high. The range's LENGTH in sessions is printed inside the yes group as description only — it has no value in the no group | 11-11 rating |
| 15 | tightness | Last-10-close spread ◐ | `spread10_adr` (small = tight) | order score; A+ contraction |
| 16 | tightness | Range contraction ◐ | mean (high−low) of D−4..D ÷ mean of D−9..D−5 (the `range_contract` value) | the operator's 10-28 "tightens" |
| 17 | volume | Volume dry-up ◐ | mean volume D−9..D ÷ mean volume D−59..D−10 | A+ read |
| 18 | volume | Up vs down volume | volume on up-closing ÷ down-closing sessions, D−19..D | EP #519 |
| 19 | averages | Extension above the 10-day | (close(D) / EMA10(D) − 1) / ADR20 (the `not_extended` value) | the operator's "looks extended"; 11-01 wide-up-day note |
| 20 | averages | Shape count | how many of the five shape gates pass at D (0-5: higher lows, no lower low, rising averages, not extended, tight) | 11-11: failed as GATES against Qullamaggie's buys |
| 21 | trend | Close vs the 200-day, in daily ranges | (close(D) / SMA200(D) − 1) × 100 / ADR20; 200 calendar sessions, ≥ 90% present | EP: "below the 200-day" REVERSED |
| 22 | trend | Sessions since the 52-week low | `since_low` | pick-model input |
| 23 | stage | First base since the major low (two groups) | `bases_before` = 0 | pick-model input |
| 24a / 24b | open | Gap at the open, in daily ranges — scored in TWO fixed populations, never pooled | (open(E) / close(D) − 1) × 100 / ADR20 — **open(E) only**. 24a = events that opened ABOVE the level; 24b = events that opened at or below it | pick model's secondary; EP 2.89x for SMALL |
| B1 | **Benchmark** | Pick-model score | `pick_score` (what the live grade A+ / A / B / C is cut from) | fitted on Qullamaggie's picks 2017-20; never on returns |
| B2 | **Benchmark** | Live order score | `order_score` | 11-01: top ranks read worse in R |
| B3 | **Benchmark** | Group strength | `group_strength` (industry-group proxy; codes are a 2026-10-16 snapshot, so names gone by 2026 have none — tagged) | A+ "+grp": can't tell |
| B4 | **Selection control** | Distance from close(D) to the level, in daily ranges | (level(D) / close(D) − 1) × 100 / ADR20 — how big a day E had to be | new (critique 6) |


- **Benchmarks are never carried and are not in the test family.** **B4 prints on every table** — it is the control
  for how the population was selected, not a grade. **B1-B3 print in ONE table per stage** (critique 8c), under the
  fixed line *"not a test of the grade — the grade is judged on Qullamaggie's buys only (#717)"*, never beside each
  feature: a pick-score third reading under 1.0 is not "the grade points the wrong way".
- **B1 is built as the live grade is (critique 17):** the pick score ranks within the night over the list PLUS the
  names only a context gate removed (`rank_all(extra_inputs)`); the build passes the same extra rows. In-sample for
  2017-20 (fitted on Qullamaggie's picks), said wherever it prints.
- **Groups (at most ONE carried per group):** volatility {1} · size {2, 3} · strength {4, 5, 6} · run-up {7, 8, 9} ·
  highs {10, 11} · base {12, 13, 14} · tightness {15, 16} · volume {17, 18} · averages {19, 20} · trend {21, 22} ·
  stage {23} · open {24a, 24b}.
- Two-group features (11, 14, 23): description only when the smaller group is under 100 scored discovery events or
  under 15%. Feature 24a / 24b: each needs ≥ 300 scored discovery events, else description only.
- **Not in the list, said now:** theme / leading group as Qullamaggie saw it, the catalyst, float, intraday volume pace,
  the market's own state. Market state is an extra reading (§5.5), not a chart feature of the stock.
- **No candidate is added, dropped or re-defined after outcomes are read.** The only later additions are the operator's
  reads from the winner gallery (§5.7).

## 5. The statistic, the bars and the verdict words
**5.1 Statistic (the EP study's, with its amendments built in).** Within each (era, calendar month) holding ≥ 6 events
scored on the feature: thirds by `np.array_split`, tied blocks never split (mid-rank, lower middle), two-group fallback
when ties empty a third. **Ratio** = pooled big-winner rate of the top third ÷ the bottom third; the middle is printed.
Two-group features: the **Mantel-Haenszel ratio stratified by month** (EP amendment A1), months with ≥ 2 of each.
Permutation: 10,000 shuffles, `default_rng(1124)`, labels permuted within (era, month) among the events scored on that
feature. Rates smoothed (winners + 0.5)/(n + 1) when a third holds none. Interval: 90% bootstrap over (era, month) blocks,
2,000 draws. Before the discovery outcome opens, stage 2 prints on synthetic no-effect labels that every statistic
centres on 1.0 (the EP study's two-group ratio read 1.86 on nothing before A1).

**5.2 DISCOVERY — a feature is CARRIED when all four hold** (two-sided):
1. ratio ≥ **1.25** or ≤ **0.80**;
2. two-sided permutation p ≤ **0.05**;
3. with 2020 removed (2017-2019): ratio ≥ **1.10** in the same direction (or ≤ 0.91) — floor calibrated on the real
   feature table with synthetic labels before any outcome (the EP study's rule: lowered in 0.05 steps to a median 80%
   pass rate for a planted 1.5x, never under 1.05);
4. **group and cap:** strength z = |log ratio| ÷ the SD of its permuted log ratios on a common set; the largest z wins
   its group; the **four** largest group winners are carried. Ties → smaller own p → lower number. Features 24a / 24b live on
   disjoint populations, so the common set is defined WITHOUT them and each takes its z on (the common set ∩ its
   own population).
Dropped from the EP study's six: the ADR-neutral floor (his ruling) and the shelf-relative condition (no shelf here).
Anything else: **NOT CARRIED in this study** — final for this study's family, not for the reading — printed with every
value. The carried direction is frozen.
- **The "break-day selection" TAG (critique 6b; a tag, never a bar).** For each carried feature the ratio is recomputed
  within strata (era, quarter, B4 third) holding ≥ 9 scored events (the EP study's ADR-strata form), in the frozen
  direction. Under the floor → the feature carries "break-day selection" on every line. The floor starts at **1.10**
  and is calibrated in stage 2 by the same lowering rule as condition 3.

**5.3 CHECK — run ONCE, one-sided in the frozen direction, Holm over ONE family of m ≤ 9** = ≤ 4 carried features
+ ≤ 1 combination + ≤ 4 of the operator's reads (three gallery reads and one ruling, the size the EP study ended at).
- **m is pinned before any check outcome (critique 11):** m = the number of things actually to be tested, counted,
  printed and hashed with the operator's reads at step 6. The ruling slot closes at step 6 too: anything he rules
  after the check run is printed as **"after the check — description"**, outside the family, with no verdict word.
| Check ratio (frozen direction) | Test | Same direction in every era present | Verdict |
|---|---|---|---|
| ≥ 1.2 | Holm p ≤ 0.05 in the family of m | yes | **PICKS THE TAIL** |
| ≥ 1.2 | Holm p ≤ 0.05 in the family of m | no | **PICKS THE TAIL (one era only)** |
| ≥ 1.2 | not met | either | **DIRECTIONAL, NOT PROVEN** |
| ≤ 0.83 | Holm p ≤ 0.05 on the OPPOSITE one-sided test, in its own family of the same m | either | **REVERSED** |
| anything else (including any ratio under 1.0 without that proof) | — | — | **NOT CONFIRMED** |
- **Why REVERSED now needs proof (critique 8a).** v1 gave it to any check ratio under 1.0. A reading with no true
  effect lands under 1.0 about half the time (47-49% in §5.4's runs) and a real 1.2x does about 1 time in 10 (4-24% across the grid) — the
  strongest negative word in the study, on a coin toss. Under the v2 rule a true-zero reading is called REVERSED about
  1 time in 200 and a real 1.2x under 1 in 1,000. The REVERSED family is separate from the PICKS THE TAIL family, so
  the tail family's error control and §5.4's figures are unchanged.
- **Seen features (4-6, 7, 15-17; critique 10):** a PICKS THE TAIL on one of them prints as **"PICKS THE TAIL (check
  years partly seen)"**. Strength features are NOT the #710 RS-leadership test's answer.
- **Every NOT CARRIED and NOT CONFIRMED line prints the smallest true ratio it had an 80% chance to detect**
  (critique 8b), computed BEFORE the check opens from the real event counts and the discovery 2017-19 rate, with the
  era-B rate at 1.0x and 0.75x.
- **The sentence for the all-null result, frozen now (critique 8b):** *"No chart reading reached the bar. With N
  events and a base rate of X this study finds a real 1.5x reading P% of the time; it says nothing about whether
  Qullamaggie's breakouts pay — they did, for years. The miss is in our measurement or our list."* (N, X, P filled
  from the pre-check print.) §5.4 says this is a LIKELY result if big winners are rare.
Every verdict prints its ratio and 90% interval, the monster / clean-winner / ADR-scaled ratios, B4 beside it, and any
tag: "✂ gate-truncated", "◐ seen on the check years (A+ read 10-22)", "against Qullamaggie's buys", "break-day
selection", "few delisted names on file" (2017-18 lines), "era-B price partly derived", "era-B population thinned by
volume underflow". B1-B3 print once per stage in their own table (§4.1).

**5.4 What a correct build reads on these counts** (`design/spread_sim_v2.py` → `spread_sim_v2.txt`: 20,000 draws,
synthetic labels, months as blocks with month-to-month swings in the rate, 2020 at 3× the other years — a guess — and
the v2 event counts of §1.2). **The base rate is unknown, so it is a grid — and the grid's rate is the rate OUTSIDE
2020** (critique 9a). With 2020 at 3×, the pooled discovery rate is about twice it; **the row is chosen by the
2017-19 rate that stage 3 prints, never by the pooled rate.** Era B is run at the same rate as 2017-19 and at
0.75× (the only hint: #705's 7.9% vs 10.5%, and 2022 was a bear market) and 0.5× (a stress). Era B is 30 months and an
ASSUMED 2,700 events (no era-B count exists). Share of runs in which a reading of the stated TRUE size is carried AND
reaches PICKS THE TAIL (family of 9):
| True size | Rate outside 2020 (pooled discovery rate) | Fork 3a: check = 2021 to 2022-Q1 only | **Fork 3b (ruled): + 2022-24, same rate** | 3b, 2022-24 at 0.75× | 3b, 2022-24 at 0.5× |
|---|---|---|---|---|---|
| 1.5x | 3% (6%) | 7% - 16% | 14% - 34% | 13% - 29% | 11% - 25% |
| 1.5x | 5% (10%) | 17% - 37% | **37% - 67%** | **30% - 57%** | 26% - 51% |
| 1.5x | 8% (16%) | 37% - 65% | 62% - 91% | 59% - 87% | 50% - 82% |
| 2.0x | 3% (6%) | 37% - 62% | 65% - 90% | 59% - 86% | 52% - 81% |
| 2.0x | 5% (10%) | 65% - 90% | 92% - 100% | 87% - 99% | 82% - 97% |
| 2.0x | 8% (16%) | 91% - 99% | 99% - 100% | 99% - 100% | 97% - 100% |
| 1.3x | 3% (6%) | 2% - 4% | 3% - 8% | 2% - 7% | 2% - 6% |
| 1.3x | 5% (10%) | 4% - 8% | 9% - 18% | 7% - 14% | 6% - 12% |
| 1.3x | 8% (16%) | 9% - 18% | 16% - 35% | 15% - 31% | 12% - 27% |
| none (1.0x) | any | under 1 in 1,000 | under 1 in 1,000 | under 1 in 1,000 | under 1 in 1,000 |
(Each range: 60% of the indicative event count surviving the context gates and drops → 100%.)
- **These are lower than v1's** (a real 1.5x at 5%: v1 said 55-81%). Two causes, both corrections: the v2 keep rule
  holds about 22% fewer events, and era B is 30 months / 2,700 events, not 33 / 3,985. Fork 3b still about doubles 3a.
- **Smallest true ratio found 4 times in 5 on check** (family of 9), at 5% outside 2020: 1.6x-1.8x with 2022-24 (1.7x-1.9x
  at 0.75×); 1.9x-2.3x without. At 3%: 1.9x-2.2x (1.9x-2.3x at 0.75×); 2.3x-2.9x without.
- Features 10, 11, 21, 22, 23 (25 months of era B): a real 1.5x at 5% reads 31% - 62% (29% - 54% at 0.75×).
- Null 95% band of the ratio at 5% outside 2020, 60% of the count: discovery 0.80-1.25, discovery without 2020
  0.62-1.62, check 0.65-1.56 (fork 3a) or 0.71-1.40 (3b; 0.70-1.43 at 0.75×). A true-zero feature shows a check ratio
  ≥ 1.2 about 1 time in 5 (3a) or 1 in 7 (3b): "DIRECTIONAL, NOT PROVEN" is not a finding.
- The 2020 guard is weak, as in the EP study: a reading that works only in 2020 passes conditions 1-2 about 4 times in
  5 and the without-2020 floor then stops about 6 in 10 of those. The real protection is the check set — and the
  2017-19 leg itself leans on years with few delisted names on file (§1.3).
- **What is and is not a bound (critique 9d).** The per-member family figure is a lower bound (first Holm step). The
  whole-chain figures in the table are NOT bounds: the group / cap-of-four rule (the EP study suggests more than four
  real readings may exist here), same-day theme clustering and gate truncation are not simulated and all push the
  real figure DOWN. The event counts are still era-A-only, per-ticker and pre-context-gate; stage 1e reprints the
  table's inputs and stage 2 re-runs this simulation on the real counts before any outcome.
**Plain reading (if big winners outside 2020 run about 5%): with 2022-24 added this study reliably finds a 2x reading,
finds a 1.5x between 1 time in 3 and 2 in 3, and usually misses a 1.3x. Without those years a 1.5x is found between
1 time in 6 and 1 in 3. If big winners are as rare as 3%, a 1.5x is found 1 time in 7 to 1 in 3 — so "nothing
reached the bar" is a likely result and is not proof a reading is useless.**

**5.5 Pre-stated extra readings (for every carried feature and each of the operator's reads; NONE is a bar):**
- population: per year; per era; **first breaks (after 10 quiet sessions) vs later breaks**, apart; **the second seed
  (2411) of the keep rule, on discovery**; the two first-break populations of v1 §1.2 (first break after 10 / after
  60 quiet sessions); common stock only; price ≥ $5 only; **embargoed discovery (E ≤ 2020-10-06)**; **2019-20 alone**;
  full 60-session windows only (no truncated or short-listed window);
- outcome: the monster tier; clean winners; the ADR-scaled tail; ADR-neutral; **the un-truncated window**; **from
  max(level, high of E)**; **E+1 .. E+60 (E's close excluded)**;
- conditioning: **within each B4 third** (the break-day selection tag reads this); within each B1 (pick-score) third
  — the FEATURE's ratio only, never the grade's own rates; break days with QQQ above / below its 50-day at D; breaks
  that gapped over the level at the open vs those that did not — **for the benchmarks too**; each window length ±50%
  on discovery only ("fragile" on a flip or a ratio under 1.2).

**5.6 Combination — one, pre-stated, nothing fitted.** If ≥ 2 features are carried: the equal-weight mean of their
within-month percentile ranks, each signed by its discovery direction, tested once on check as one family member.

**5.7 The operator's gallery reads (≤ 3, plus one slot for a ruling).** A read = something he names after looking at
gallery A. Each is coded as an exact definition under §4.0 with the direction HE states, corrupt-E tested, appended and
hashed BEFORE any check outcome — together with m (§5.3). It skips the §5.2 gates (he saw the discovery winners); its
discovery numbers are printed "seen". **A read must be knowable when price crosses the level** — the EP study's TLRY
ruling applies: what a stock did after the break cannot be coded and takes no slot. **The ruling slot closes at
step 6**; a later ruling is description outside the family (§5.3).

## 6. Order of work (no expectation formed after seeing data; every stage-1 step has its own gate)
0. Draft v1 → adversarial critique → **v2 (this)** → the operator's review → **freeze commit** (sha256 recorded) —
   a separate step; nothing below starts before it.
1. **Stage 1 — no forward read anywhere in it:**
   - **1a. Pins and parity.** Assert the commit sha and the file sha256s of §1.1; re-run the 11-01 `parity` stage.
     *Gate: parity equal, every pin matches.*
   - **1b. Era-A list rebuild + bridge** to the 11-13 capture (§1.1). *Gate: exact reproduction, or every difference
     traced to a named rule change.* Prints the context gates' cut.
   - **1c. Era-B inputs + THE RAW-CLOSE PULL (the only network step in this study; free; run ONCE).**
     1. Rebuild the sealed bar copy (rows < 2025-01-01, asserted); splits through `load_splits_sealed`; guard B with
        dates > 2024-12-31 dropped at read.
     2. **Request list, built from sealed local files only:** every era-B ticker whose raw scale rests on the split
        list alone (`raw_src` 2) and whose 20-session dollar volume passes the $5M floor on at least one era-B night
        — a test that does not touch the raw price scale (adjusted close × adjusted volume). That is the superset of
        every name the $2 floor could admit to the strength pool or the list: a derived price cannot be trusted to
        choose who gets checked. At most 7,184 tickers. Plus two control sets with a KNOWN raw close:
        a seeded 300 of the bridged tickers and the 326 tickers of the 11-01 Polygon pulls. Columns `ticker /
        first_date / last_date` (the span of its nights at the dollar-volume floor). Written once, sha256 pinned, never rewritten.
     3. **The pull requests ONLY dates ≤ 2024-12-31.** Alpaca historical daily bars through alpaca-py (`Adjustment.RAW`, as
        `scripts/probes/_620_fetch_bars.py` does), feed **SIP**, pinned and asserted (the EP entry arm's precedent),
        the existing keys, `start` = first_date, `end` = min(last_date, 2024-12-31). The stage REFUSES to run if any request row
        carries a date after 2024-12-31, and REFUSES to write its output if any returned bar is dated after
        2024-12-31. Close and volume captured once to `apollo_data/cb702/raw_close_bwin_1124.csv.gz` + a `meta.json`
        (request sha256, row and ticker counts, min / max date, pull time). **Captured once, read many — never
        re-pulled to re-read.**
     4. ***Gate (all printed, outcome-free):*** (a) max returned date ≤ 2024-12-31; (b) coverage — the share of
        requested tickers and ticker-nights returned, per year; (c) SCALE agreement on the two control sets — what the gate protects is the price scale,
        so a control ticker agrees when its median |pulled ÷ known − 1| is ≤ 10% (a split-factor error is ≥ 33%);
        under 99% of control tickers agreeing → STOP (the source is not what we think it is; nothing is fixed by
        hand). The share of rows within 0.5% is printed as description, not a pass line — two vendors' closes on
        thin names can differ; (d) per pulled ticker, raw ÷ adjusted close must be stable between split-list dates
        (≤ 2024) — max ÷ min − 1 ≤ `BRIDGE_TOL` (0.005, the replay's own bridge tolerance) on rows with an adjusted
        close ≥ $1 — and step only on those dates; a ticker that fails (a reused symbol returning another company)
        is treated as NOT returned. Not-returned names fall to the derived-only handling of §1.3; coverage of delisted
        names is not known until the pull and is not a stop.
   - **1d. Era-B list rebuild + the overlap bridge** (§1.1). *Gate: agreement printed per gate; no untraced difference.*
   - **1e. Events.** Identity map → the §1.3 drops, counted per reason × era × year → the q grid and rule → the keep
     walk (seed 1124, and 2411 for the extra reading). Prints, all outcome-free: the seam night; unknown security
     type per era; the underflow test (§1.3); kept events whose bars end inside their window per year; kept events
     with a guard or split-list date inside their window; derived-only events near the $2 floor.
     *Gate: no identity kept twice within 60 sessions across eras; no (identity, D) in both eras.*
   - **1f. Feature table**, NULL counts, tie shares, corrupt-E proof, Qullamaggie's coverage and position tables
     (§1.4). Table hashed. *Gate: 0 values change under corrupt-E; the leaky control changes.*
2. **Calibration, synthetic labels only:** the without-2020 floor; the B4 "break-day selection" floor; every statistic
   centred on 1.0 under no effect; `spread_sim_v2` re-run on the real counts.
3. **Discovery outcomes** (reads forward bars ONLY for E ≤ 2020-12-31, asserted): the 2017-19 rate and the pooled rate
   first, then §5.2.
4. **Blind recount** of stages 1 and 3 from this text alone + an adversarial review (look-ahead per feature, the
   2024-12-31 cut, the keep rule, the window truncation, the permutation) — BEFORE check, because check runs once.
5. **Winner gallery A** shown to the operator. **HARD STOP until he replies** with his reads, or "none".
6. Freeze his reads, the ruling slot and **m**; print check n per feature and era and the smallest detectable ratio
   per line (outcome-free). Hashed.
7. **Check outcomes, ONE run**, then its blind recount.
8. **Blind sheets B** if anything reached PICKS THE TAIL.

## 7. Chart sheets for the operator's eye (12 per sheet, seeded 1124, never hand-picked)
- **A. Winner gallery — outcome KNOWN, discovery only, shown before check.** Discovery big winners **with
  E ≤ 2020-10-06** (§3 embargo: no chart shows a 2021 bar), monsters first; each winner sheet paired with a sheet of 12
  failures (§2) from the same months. Daily candles + volume, D−250 .. E+60, the level drawn, E marked, EMA10 / EMA21
  / SMA50 / SMA200, every chart padded to one width; the feature values and the pick grade in small text under each.
  The first 3 pairs go to him in chat, the rest on disk. The count is unknown until stage 3; if over 600, a seeded
  sample of 600 winners is rendered and the rest on request.
- **B. Blind sheets — outcome HIDDEN.** For each PICKS THE TAIL feature or read (at most 3): 2 sheets × 12, 6 top-third
  + 6 bottom-third CHECK events, shuffled. Bars end at D with the level drawn; no ticker, date, value or axis labels;
  random file names; answer key hashed first. **Excluded from the draw:** every ticker-window of Qullamaggie's 757 buys,
  every name-night the operator has already graded or been shown (the 41 list grades, the 11-07 .. 11-16 sheets),
  **every IDENTITY shown on gallery A**, and any identity with ≥ 3 check events. He rules good / okay / bad plus
  "recognised?"; the score is his eye against the feature's thirds (0.5 = nothing), a lean, never a verdict.
- Events shown on A or B are spent as outcome-blind labels.

## 8. What this does not answer
- **Money, the entry and the stop.** The outcome is a +50% close measured from the level (or the open on a gap). The
  live rule buys later and higher — the break of the first five minutes' high — with a stop at the day's low; a break
  that stops out and later runs counts as a winner here. That is fork 4 / #720.
- **What the live rule would actually have bought.** The population is list names whose level was taken out — it
  includes breaks inside the first five minutes and too-wide days that the live entry refuses.
- **Whether the detection rules or the grade are right.** Judged only on Qullamaggie's buys (#717). Truncated
  features (✂) cannot speak about their own gate; the benchmarks are not a test of the grade.
- **Charts the list never shows** — about half of all big winners do not start with a breakout these rules see (#705).
- **Exactly the moment of decision.** Membership needs E's high above the level; the population is breaks that
  happened, at whatever minute, and it leans toward names that had a strong E (the B4 control and tag bound that,
  they do not remove it). Which name breaks first in a morning is not in daily bars.
- **A clean era B.** Its bars are adjusted as of 2026-10-16, so its volume (and through the $5M floor, its list)
  carries information from splits after the cut; its security types are a 2026 snapshot; part of its raw prices may
  stay derived. Each is counted and tagged (§1.3), none is removed.
- **A full 2017-18.** Few names that later died are on file for those years (§1.3).
- **Small effects** (§5.4), **2025-26** (sealed, #710), theme, catalyst, float, intraday pace.
- **Regime.** The operator's 11-21 note: momentum is not expected to work in the current bear phase. Nothing here is a
  claim about now; the QQQ split in §5.5 is description.
- **An untouched check set** (§0) — seven features and the list rank were read there before.

## Critique resolutions (v2, 2026-11-24)
Critique: `design/critique.md` (3 BLOCKER, 9 MAJOR, 9 MINOR; its finding 20 is MAJOR and kept its number). v1 text:
`design/prereg_draft_v1.md`.
| # | Finding | Resolution | Where in v2 |
|---|---|---|---|
| 1 BLOCKER | The random thinning chose events by what happened AFTER the break | ACCEPTED — keep rule reads rows ≤ D only: forward walk, eligible when no kept row in the prior 60 sessions, kept on a sha256 coin under q; per identity across both eras; all drops before the walk; second seed printed. **MODIFIED on q:** the critique's "q so the mix matches the break rows" cannot be met by any backward-only rule (first breaks are 15% of break rows, 30% of kept events even at q = 1/5), so q is set by a fixed rule (largest grid q with the first-break share ≤ 2× the break rows'), the imbalance is stated, and first vs later breaks print apart. Counts recounted: 13,461 → 10,514. | §1.2, §5.5, §6 1e; `count_events_v2_forward_hash.*` |
| 2 BLOCKER | Nothing stops the outcome window at a symbol change or an unadjusted jump | ACCEPTED — both guard files wired (era B's as an event filter, dates > 2024 dropped at read); event dropped on a flag in D−85..E; window = calendar sessions ci(E)..ci(E)+60, ending the session before a guard break or a ≥ +70% / ≤ −50% move on a split-list date; outcome-free count of affected events before discovery. ADDED: the un-truncated outcome as an extra reading, since the mechanical cut can also remove real winners. The same gap in the frozen EP study is NOT reopened here (follow-up noted under Unresolved). | §1.3, §2, §5.5, §6 1e |
| 3 BLOCKER | Era-B raw close per name-night does not exist for 7,184 tickers; fixing it needs a pull | **RULED: option (i)** — one raw-close pull as stage 1c with its own gate; requests ONLY dates ≤ 2024-12-31; captured once. Request = the superset (every split-list-only name at the dollar-volume floor on any era-B night — the $2 floor also sits in the strength pool, so a gate-level superset would not be one), plus two control sets; pulled closes go in before the pool is built. Names not returned get the critique's option-(ii) handling (`raw_src`, feature 2 NULL, the tag). Not performed in v2. | header, §1.3, §4.1 (feature 2), §6 1c |
| 4 MAJOR | The bridge check cannot be run as written; the pin is too narrow | ACCEPTED — "context off" defined as `set(failed) <= CONTEXT_GATES`; the whole chain and both fixtures pinned by sha256; the parity stage re-run at the pinned sha; own scratch folder; sealed copy rebuilt; era-B bridge on the 2022-04..06 overlap from both stores. The era-B bridge has no blind pass line (untraced difference stops the run) — a frozen number would be a guess. | §1.1, §6 1a-1d |
| 5 MAJOR | EP critique D2 (era-B volume underflow) not carried | ACCEPTED — the outcome-free underflow test re-run on this population, 1% trigger and tag, features 3 / 17 / 18 NULL on a zero-volume window, disclosed in §8. ADDED: the pull captures raw volume to SIZE the effect; membership is not repaired. | §1.3, §8 |
| 6 MAJOR | Membership on E's high selects on E-day strength unevenly | ACCEPTED — B4 (distance from close(D) to the level) on every table; each carried feature within B4 thirds with a "break-day selection" tag under a calibrated floor (start 1.10); feature 24 split into 24a / 24b, never pooled; outcome over E+1..E+60 as an extra reading. | §4.0, §4.1, §5.2, §5.5 |
| 7 MAJOR | The proxy is lower than the live buy; the population includes breaks the live rule refuses | ACCEPTED — fork 1a's population reworded; §8 says both halves; two extra readings (outcome from max(level, high of E); gap-through split for benchmarks too). The real answer stays with #720. | header, §2, §5.5, §8 |
| 8 MAJOR | Verdict words: a null can read as a finding | ACCEPTED, all four — (a) REVERSED needs ratio ≤ 0.83 AND Holm p ≤ 0.05 on the opposite test in its own family, else NOT CONFIRMED (simulated: fires on a true zero about 1 in 200, was about 1 in 2); (b) the all-null sentence frozen and the smallest detectable ratio printed on every null line; (c) B1-B3 in one table per stage under a fixed line — **B4 stays on every table** (it is a selection control, not a grade; this settles 6a against 8c); (d) "NOT CARRIED in this study". | §4.1, §5.2, §5.3 |
| 9 MAJOR | §5.4's power rests on three soft assumptions | ACCEPTED — simulation re-run (`spread_sim_v2`): grid labelled "rate outside 2020" with the pooled rate beside it and the row chosen by the 2017-19 rate; era B at 1.0 / 0.75 / 0.5×; era B 30 months; the 25-month features; the v2 event counts; bound wording corrected. A real 1.5x at 5%: 55-81% → 37-67% (30-57% at 0.75×). Group / cap and clustering are still not simulated — said. | §5.4, header fork note |
| 10 MAJOR | Seven features already read against the tail on the check years | ACCEPTED — features 4-6, 7, 15-17 tagged ◐ on every line; their PICKS THE TAIL prints "(check years partly seen)"; kept in the family; the #710 line restated. | §0, §4.0, §4.1, §5.3 |
| 11 MAJOR | Holm family size and the ruling slot not pinned | ACCEPTED — m = the count actually tested, frozen and hashed at step 6; the ruling slot closes there; later rulings are description. | §5.3, §5.7, §6 step 6 |
| 12 MINOR | Late-2020 discovery windows and gallery charts run into 2021 | ACCEPTED, gallery part STRENGTHENED — gallery A draws only from E ≤ 2020-10-06 (the exact session whose E+60 is 2020-12-31; the critique wrote 10-05) instead of an extra reading alone; embargoed discovery printed as an extra reading; blind sheets exclude identities shown on A. | §3, §5.5, §7 |
| 13 MINOR | The night D 2022-04-01 belongs to neither era | ACCEPTED — it is era B's first night (the 11-01 replay's seam); counted and asserted. | §1.3, §6 1e |
| 14 MINOR | File-start artefacts; feature 23; B1 in early era B | ACCEPTED — dropped when a check passed unscored because the FILE starts, kept when the name is a short listing; feature 23 on the NULL-under-90% list; B1 tagged "short year". Closes v1's unresolved 8. | §1.3, §4.0 |
| 15 MINOR | Feature 14 has no value when the level is the 5-day high | ACCEPTED — tested as two groups (level from a range: yes / no); length is description inside the yes group. | §4.1 |
| 16 MINOR | "Against Qullamaggie's buys" at under 25% is too loose | ACCEPTED — tag under 29%, share printed with its interval; an undated buy stands on the first break row in its window. | §1.4 |
| 17 MINOR | B1's population; B3's snapshot | ACCEPTED — B1 ranked over the list plus the context-only rows, as live; B3 tagged as a 2026 snapshot. | §4.1 |
| 18 MINOR | Security type is one 2026 snapshot; unknown types admitted | ACCEPTED — unknown-type share printed per era; "common stock only" bounds it; stated in §8. | §1.3, §8 |
| 19 MINOR | Closed-file list too short | ACCEPTED — every named file added. | §1.3 |
| 20 MAJOR | Era A's early years hold few names that later died | ACCEPTED (the no-network fix) — per-year print of kept events whose bars end inside the window; 2019-20-alone reading; "few delisted names on file" on 2017-18 lines. **DECIDED: no refetch of dead 2016-18 symbols.** | §1.3, §5.4, §5.5, §8 |
| 21 MINOR | §0 misses three earlier looks | ACCEPTED — three rows added from the critique's descriptions (the documents were not re-read for v2); the "not read in full" line updated. | §0 |

Carried over from the EP study's critique and amendments (unchanged from v1): calendar windows and NULL reasons for the
features this study computes itself (D1 — only PARTLY: live-code values are exempt, §4.0) · **D2 now carried
(finding 5)** · code called, never imported from a script that runs at module level (D3) · group winner
by z on a common set (D4) · permutation among scored events only (D5) · Mantel-Haenszel for two-group features (A1) ·
identity on returns (A2) · one verdict word, no STRONG / LEAN · gallery before the check with a hard stop · failures,
not non-winners, as the contrast · the volatility ruling (§11.3) · reads knowable at the decision (§11.5).

## Unresolved (for stage 1 and the freeze step, not for the operator)
Closed in v2: v1's 1 (era-B inputs → ruled, stage 1c), 4 (second seed → §5.5), 6 (RS leadership → §5.3), 8 (live-code
values and bad bars → §1.3, §4.0).
1. **The context gates' and drops' cut** of the event count (§5.4 brackets it at 60%-100%) and whether the pinned-sha
   rebuild reproduces the 11-13 capture — stage 1b prints both.
2. **The 2020 multiple** in the simulation (3×) is a guess; the EP study's was 5×. Stage 3's first print replaces it.
3. **Alpaca's coverage of delisted and renamed era-B names** is not known until the pull; the gate prints it and the
   derived-only handling covers the rest (§1.3). If coverage is poor the "era-B price partly derived" tag will fire.
4. **Era B's event count** is an assumption (2,700) until stage 1d-1e; no era-B list file was opened to write this.
5. **Pick-score for era-A nights before the model existed** is computed by the live function on historical inputs —
   fine as a benchmark, but confirm `pick_scores` needs nothing unavailable historically (the SIC group file).
6. When committed, the file needs its pointer in `docs/SSoT.md` (findings are never owners) and a PLAN.md line.
7. **Follow-up outside this study:** the frozen EP study has no line cutting its forward window at a guard break
   either (critique 2). One outcome-free count there would size it; the frozen document is not touched from here.
