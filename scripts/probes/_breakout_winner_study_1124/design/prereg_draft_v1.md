# BREAKOUT big-winner chart study — what do the charts of breakouts that became big winners share? (DRAFT pre-registration, 2026-11-24; NOT frozen, NOT committed, no outcome read)

**DRAFT v1 — design only.** Written Tue 2026-11-24 PT. The breakout twin of the frozen EP study
(`docs/analysis/ep_winner_study_prereg_2026-11-21.md`, "the EP study" below); same structure, with the EP study's own
amendments and the operator's rulings on it built in from the start. Nothing was run that reads a price after a break day.
Every count below is **indicative**: it comes from the 11-13 list capture (columns `ci / ticker / fire` only), which
predates the 11-14 context gates — `scripts/probes/_breakout_winner_study_1124/design/count_events_outcome_free.py` → `.txt`.
Spread numbers in §5.4 come from `design/spread_sim.py` → `spread_sim.txt` (synthetic labels only).
**Before this freezes it needs:** the operator's four forks (next block), an adversarial critique (as the EP draft got), and
the stage-1 recount on the live code.

**Cost of the whole path, stated once.** $0 paid (no API, no network, no DB). Local compute: one list rebuild over about
2,000 nights (the 11-13 era-A capture is the precedent) plus feature and permutation runs — an hour or two of laptop time.
Agent cards, counted from what the EP study used: **about 4 Fable + 6 Sonnet** (critique of this draft · stage-1 build and
calibration · discovery · blind recount + adversarial review · gallery · freeze of the operator's reads · confirm + its
recount · blind sheets), staggered, never three at once. Dropping the 2022-24 rebuild (fork 3) saves about one Fable card.
An entry / exit arm (fork 4) is NOT in that number: the EP study's arm cost a minute-bar fetch and about 4 more cards.

**✅ FORKS RULED 2026-11-24 — the operator: "go with recs" → 1a (live breakout-v1 breaks), 2a (+50% in 60 sessions), 3b (add 2022-04..2024 by rebuilding the list, cut 2024-12-31), 4: left to #720.** Original table kept below.

**The operator's forks (each with a one-line recommendation; nothing below is decided for him):**
| # | Fork | Options | Recommendation |
|---|---|---|---|
| 1 | Which breakouts are studied | (a) every break of the LIVE breakout-v1 rule set · (b) a looser, gate-free breakout definition (the #705 "measurable breakout" kind) | **(a)** — it is the setup as Qullamaggie trades it and as wired; (b) would study charts the list never shows. |
| 2 | What counts as a big winner | (a) the EP study's: a close at least +50% above the buy point within 60 sessions, +100% as the stricter tier · (b) another size or window | **(a)** — same yardstick as the EP study, so the two can be read side by side. |
| 3 | The check years | (a) 2021 to 2022-Q1 only (what is already built) · (b) add 2022-04 to 2024 by rebuilding the list there, cut at 2024-12-31 | **(b)** — it roughly doubles the chance of finding a real 1.5x reading (about 25-50% → 55-80% at a 5% base rate, §5.4), and (a) alone is 15 months of one market. |
| 4 | Entry / stop / exit replay on these breakouts | (a) now, as an arm of this study · (b) left to the periodic trade review #720 | **(b)** — this study answers "which charts"; keeping the money is #720's question and needs a minute-bar fetch. |

**Why.** The operator's words 2026-11-21 (`docs/methodology/operator_shared_notes.md`): *"Qullamaggie suggests to review
1000s of charts to find edge"*, and his order of work 11-21/22: *"EP first, then breakout"*. The EP study found chart
readings that mark the tail on gap days (high daily range 8.3x, deep base, low price, a short run-up) and reversed three
of the operator's own gallery reads. This study asks the same of breakouts, then puts the strongest in front of his eye.

**What this is NOT.**
- Measurement only, $0, local files. No live change, no ranking change, no gate, entry, stop or exit proposal (THE LINE).
- **Not a test of the detection rules.** Breakout v1 is detection as Qullamaggie trades it, judged ONLY on keeping his
  buys (#717). No result here is a reason to add, drop or move a list gate or the pick model.
- **Not a grading of Qullamaggie's buys.** They are ground truth. They are used outcome-free only (§1.4); they are
  never tabulated against an outcome, and the scorecard's `big_winner` column is never read.
- **Not a verdict on the setup.** Qullamaggie's breakouts paid him for years; a null here is our measurement, not "no edge".
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
| 11-11 rating, initial rules, shape gates; 11-12 ADR floor; 11-13 pick model; 11-14 rank / context / extended / low line / wide-loose; 11-15 grades | Qullamaggie's 757 buys, the operator's 41 list grades, era-A list rows | Qullamaggie's buys and the operator's grades | the current gates, the pick model and its grades | Registered against Qullamaggie's buys and the operator's grades, not returns; a word search of five of the printouts found no return column, **the rest were not read in full (not verified)**. The scorecard's `big_winner` flag (26 dated buys) was COUNTED in head-to-head tables ("big winners in the top 5"). The pick model was fitted on Qullamaggie's picks 2017-2020 — in-sample for benchmark B1 on discovery, said wherever B1 prints. |
| Live paper book (from 11-09) | 2026 | — | — | Sealed years; not opened. |
| **Slip while drafting (2026-11-24)** | — | — | a `head -3` of `big_winners_2017_2024.tsv.gz` to learn its columns printed two outcome rows (AKAO 2017, NKTR 2017: gain and replayed R) | Two discovery-year names seen as winners; no feature was chosen on them; the file was not opened again. |

**What has been SEEN on the check years (2021-24):** big-winner names (#705); breakout-v1 R by year and by rank (11-01);
Qullamaggie's buys and their results by name; the EP study's confirm results on the same years' gap days.
The split in §3 mirrors the EP study's and was chosen knowing all of that.

## 1. Population (to be fixed at freeze; counts printed without outcomes)
**1.1 The break (fork 1a).** A row = (identity, night D, break day E = the next session) where
- the name is on breakout v1's nightly list at D under the LIVE rules — `breakout_v1.v1_gates` (history, universe $2 / $5M,
  pinned, ADR20 ≥ 4%, strength rank ≥ 35, prior move ≥ 20%, base depth 1.51-11 daily ranges, close vs EMA21 ≥ −0.9) AND
  `breakout_v1.context_gates` (not under a falling 50-day, not a 6-month downtrend, not a re-widening base on a flat or
  falling lower line), pool and strength rank built as `scripts/probes/_717_pick_model_1113/01_build.py` builds them;
- on E the high takes out the level: `breakout_triggered` (the daily-bar proxy of the buy; no volume condition, as wired).
- **Code is CALLED from `agents/market_intelligence/breakout_v1.py` at one pinned commit** (sha written here at freeze;
  the run asserts it), never re-coded. The system changes weekly; the pinned sha is the rule era this study describes.
- **Bridge check before anything else:** with the context gates switched off, the era-A rebuild must reproduce the 11-13
  capture — 420,158 list rows, 156,695 break rows on 1,322 nights, median 68 a night, 375 of Qullamaggie's 757 buys on a
  break row. A mismatch stops the run unless every difference is traced to a named rule change after 11-13.
**1.2 One event per identity per 60 sessions, drawn at random (decided here; the reason is a count).** A name on the
list breaks its level again and again — the median ticker has 22 break rows — so break rows are not independent events.
- **PRIMARY unit:** per identity, its break rows are taken in a seeded random order (`default_rng(1124)`) and a row is kept
  when no kept row of that identity lies within 60 sessions either side. Outcome windows of one name never overlap.
- **Why random, not "the first break":** a random draw is an unbiased sample of what the list actually fires, early
  and late breaks in the mix the list produces. Checked outcome-free (`count_events_outcome_free.txt`): Qullamaggie's
  buys are spread over early and late breaks about as the break rows are — 14.4% of his 375 break-row buys sit on a
  "first break after 10 quiet sessions" against 15.2% of all break rows; 3.2% against 5.1% for "after 60 quiet
  sessions". So neither unit is closer to his buying; the first-break sets are printed as extra readings (§5.5).
- Thinning keeps about 1 break row in 12, so only about 40 of his buys land on a kept event; his position tables
  (§1.4) therefore use all 375 of his break-row buys, not the kept events.
- Indicative size, era A before the context gates: **13,461 events** (2017 1,080 · 2018 1,608 · 2019 1,660 · 2020 3,977 ·
  2021 3,916 · 2022-Q1 1,220), 3,523 tickers, 64 months, smallest month 49. The context gates will cut this by a share
  not yet known (stage 1 prints it); §5.4 is simulated at 100% and 60%.
**1.3 Years and files.** Eras are never stitched (the EP study's rule).
- Era A: D 2016-12-30 .. 2022-03-31, bars `cb702_pre_v2/daily_closes_all.csv.gz` (2016-01-04 .. 2022-06-30), raw closes
  `cb702_pre_v2/daily_raw_close.csv.gz`. An event needs E+60 inside the file; later ones are dropped and counted.
- Era B (fork 3b): D 2022-04-04 .. 2024-09-30 (E+60 must end by 2024-12-31), bars `cb702/daily_closes_all.csv.gz`
  (starts 2021-09-27). **Every row dated after 2024-12-31 is dropped AT READ and asserted absent** — the EP study's
  precedent for this same file. `features_eraB.parquet`, every `*_holdout*` file and every 2025-26 store stay closed.
  Era B needs a raw close and a security type per name-night for the $2 / fund rules: **source not yet verified
  (unresolved 1)**. Without it, fork 3 falls back to (a).
- Era overlap: era A is the only source for E ≤ 2022-04-01; era B starts after it.
- Identity across eras: the EP study's map (`_ep_winner_study_1121/build/stage1/identity_pairs_all.tsv`, amendment A2),
  rebuilt for these tickers by the same code. Status-suffix symbols (5 letters ending in Q) are printed and never shown.
- **No survivorship drop:** a name that stops trading inside its window stays; its window ends where its bars end.
- Funds: the live `security_admitted` rule decides (stocks, ADRs, single-asset funds). Printed per type.
**1.4 Qullamaggie's 757 buys — outcome-free, three uses only.**
1. Coverage: how many fall on a break row and on a kept event, per year, printed in stage 1.
2. Position: for every feature, the share of his break-row buys (about 375) that sit in the top / middle / bottom third
   of that night's month group — printed BEFORE any outcome. A carried feature whose winning third holds under 25% of his
   buys is tagged **"against Qullamaggie's buys"** on every line (a rule that drops his buys is the defect).
3. Exclusion from the blind sheets (§7B). Sources: `tests/fixtures/qm_breakout_scorecard/buys.tsv`,
   `buys_undated_widened.tsv` — columns `ticker / E / lo / hi` only.

## 2. Outcomes (buy-point proxy = max(level(D), open(E)) — the level, or the open when the stock gaps through it)
- **PRIMARY — big winner (fork 2a):** highest close over E..E+60 ≥ **1.5 ×** the buy-point proxy. E's own close counts.
- **MONSTER tier:** ≥ **2.0 ×**, same window. Reported beside the primary; never a bar; "thin" under 60 monsters.
- **Clean winner (description only):** a big winner with no session low under low(E) between E+1 and the first +50%
  close — "would the day-low stop have survived it". Never a bar; the real stop question is fork 4.
- **ADR-scaled tail (description only):** highest close ≥ proxy × (1 + 8 × ADR20/100).
- **Failed (description; the gallery's contrast pool):** highest close over E..E+60 < 1.10 × the proxy.
- **Daily range is NOT treated as a confound** (the operator's ruling 2026-11-21, EP study §11.3: *"we shouldn't
  penalize high ADR stocks for it"*). The ADR-neutral reading is printed for every carried feature as description; it
  gates nothing and re-words no verdict.
- The base rate of the primary is **not known** and is not estimated here. Stage 3 prints it first.

## 3. DISCOVERY / CHECK split (by break day, the EP study's cut)
| Set | Rule | Indicative events (before the context gates) |
|---|---|---|
| **DISCOVERY** | E ≤ 2020-12-31 (era A) | about 8,300 (2020 alone about 4,000) |
| **CHECK** | E ≥ 2021-01-01: era A to 2022-04-01, plus era B to 2024-09-30 under fork 3b | era A about 5,100; era B not counted yet (assumed about 4,000 in §5.4) |
- Out-of-time, both eras printed apart. Known weaknesses: discovery is half 2020; Oct-Dec 2020 windows run into 2021;
  one identity can sit in both sets; the check years are partly seen (§0); 2025-26 stays sealed.
- With fork 3a the check set is 15 months of one regime (2021 to early 2022) — said on every check line.

## 4. The candidate chart features (24 in 12 groups; ALL knowable when price crosses the level on E)
### 4.0 Rules for every feature
- **Inputs:** the name's daily bars dated ≤ D, the level computed at D, and — for group "open" only — open(E). **Never
  E's high, low, close or volume, and nothing after E.** (The capture's `hE` / `lE` columns are never features.)
- **Membership uses E's high** (the break itself), as the EP study's used E's volume: features are clean, the population
  is "listed names whose level was taken out". Stated in §8.
- **Gate values are read as the live code computes them** at the pinned sha (columns of `v1_gates` / `context_gates` /
  `shape_gates` / the pick inputs). **These — about half the features, and list membership itself — are NOT under the
  calendar-window and NULL rules:** the live code works on rows, guards only its own 86 consecutive sessions, and
  passes a check it cannot score. Where each file starts that bites: the lower-line context gate (needs 189 bars)
  passes by default in early 2017 and in era B until about 2022-06; the 52-week features (10, 11, 22) see a short
  year in early 2017 and in era B until about 2022-09. Stage 1 prints, per feature and per gate, the events scored
  on short history or passed unscored, by era and year; such events are tagged, and features 10, 11, 21, 22 are NULL
  under 90% of their window. Whether live-code values should also carry the adjustment / identity NULLs is unresolved 8.
  Other features use CALENDAR-session windows with the EP study's NULL rules
  (§4.0 there: history · coverage under 90% · adjustment · identity · zero volume for volume features), each NULL
  counted per feature × era × year × reason.
- **Corrupt-E proof, all features and benchmarks:** on a seeded 600-event sample, E's high / low / close / volume and
  every later bar are replaced with garbage (three patterns); 0 values may change. A positive control (a deliberately
  leaky feature) must change. Features of group "open" are additionally proven to move only with open(E).
- **Gate-truncated features** (marked ✂): the list already cut their range, so a NOT CARRIED says nothing about the gate.

### 4.1 The list
| # | Group | Name | Definition (bars ≤ D unless stated) | Prior look |
|---|---|---|---|---|
| 1 | volatility | Daily range ✂ | ADR20 at D (the gate's value; floor 4%) | EP 8.32x; Qullamaggie's scan (10-24) |
| 2 | size | Price | raw close at D | EP 2.93x for LOW |
| 3 | size | Dollar volume ✂ | 20-session median of close × volume | best simple ranker of Qullamaggie's picks (11-13) |
| 4 | strength | Strength rank, best ✂ | `rs_best` (the gate's value, floor 35) | A+ read: RS highest |
| 5 | strength | Strength rank, 1 month | `rs_1m` percentile over the night's pool | pick-model input |
| 6 | strength | Strength rank, 6 months | `rs_6m` | pick-model input |
| 7 | run-up | Prior move ✂ | the gate's run into the pole top (floor 20%) | A+ read |
| 8 | run-up | 20-session run-up | close(D) / lowest low of D−19..D − 1 | EP 2.47x for HIGH |
| 9 | run-up | 6-month move | `runup6m_at` | Qullamaggie's scan (not down over 60 sessions) |
| 10 | highs | Distance below the 52-week high | close(D) / highest high of the 252 sessions to D | Qullamaggie's scan; pick-model input |
| 11 | highs | The level IS a 52-week high (two groups) | level(D) ≥ highest high of D−251..D | new |
| 12 | base | Base length | sessions from the pole top to D (`base_len`) | pick-model input |
| 13 | base | Base depth, % | 1 − lowest low / highest high over the base (pole top+1 .. D) | EP 7.35x for DEEP |
| 14 | base | Range length | sessions of the qualifying range behind the level (`range_levels`) | 11-11 rating |
| 15 | tightness | Last-10-close spread | `spread10_adr` (small = tight) | order score; A+ contraction |
| 16 | tightness | Range contraction | mean (high−low) of D−4..D ÷ mean of D−9..D−5 (the `range_contract` value) | the operator's 10-28 "tightens" |
| 17 | volume | Volume dry-up | mean volume D−9..D ÷ mean volume D−59..D−10 | A+ read |
| 18 | volume | Up vs down volume | volume on up-closing ÷ down-closing sessions, D−19..D | EP #519 |
| 19 | averages | Extension above the 10-day | (close(D) / EMA10(D) − 1) / ADR20 (the `not_extended` value) | the operator's "looks extended"; 11-01 wide-up-day note |
| 20 | averages | Shape count | how many of the five shape gates pass at D (0-5: higher lows, no lower low, rising averages, not extended, tight) | 11-11: failed as GATES against Qullamaggie's buys |
| 21 | trend | Close vs the 200-day, in daily ranges | (close(D) / SMA200(D) − 1) × 100 / ADR20; 200 calendar sessions, ≥ 90% present | EP: "below the 200-day" REVERSED |
| 22 | trend | Sessions since the 52-week low | `since_low` | pick-model input |
| 23 | stage | First base since the major low (two groups) | `bases_before` = 0 | pick-model input |
| 24 | open | Gap at the open, in daily ranges | (open(E) / close(D) − 1) × 100 / ADR20 — **open(E) only** | pick model's secondary; EP 2.89x for SMALL |
| B1 | **Benchmark** | Pick-model score | `pick_score` (what the live grade A+ / A / B / C is cut from) | fitted on Qullamaggie's picks 2017-20; never on returns |
| B2 | **Benchmark** | Live order score | `order_score` | 11-01: top ranks read worse in R |
| B3 | **Benchmark** | Group strength | `group_strength` (industry-group proxy) | A+ "+grp": can't tell |

- **Benchmarks are printed on every table, are never carried and are not in the test family.** B1 answers a question the
  operator will want beside every feature: does the grade already lean toward the tail? In-sample for 2017-20, said so.
- **Groups (at most ONE carried per group):** volatility {1} · size {2, 3} · strength {4, 5, 6} · run-up {7, 8, 9} ·
  highs {10, 11} · base {12, 13, 14} · tightness {15, 16} · volume {17, 18} · averages {19, 20} · trend {21, 22} ·
  stage {23} · open {24}.
- Two-group features (11, 23): description only when the smaller group is under 100 scored discovery events or under 15%.
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
   its group; the **four** largest group winners are carried. Ties → smaller own p → lower number.
Dropped from the EP study's six: the ADR-neutral floor (his ruling) and the shelf-relative condition (no shelf here).
Anything else: **NOT CARRIED**, final, printed with every value. The carried direction is frozen.

**5.3 CHECK — run ONCE, one-sided in the frozen direction, Holm over ONE family of at most 9** = ≤ 4 carried features
+ ≤ 1 combination + ≤ 4 of the operator's reads (three gallery reads and one ruling, the size the EP study ended at).
| Check ratio (frozen direction) | Holm p ≤ 0.05 | Same direction in every era present | Verdict |
|---|---|---|---|
| ≥ 1.2 | yes | yes | **PICKS THE TAIL** |
| ≥ 1.2 | yes | no | **PICKS THE TAIL (one era only)** |
| ≥ 1.2 | no | either | **DIRECTIONAL, NOT PROVEN** |
| 1.0 ≤ ratio < 1.2 | either | either | **NOT CONFIRMED** |
| < 1.0 | either | either | **REVERSED** |
Every verdict prints its ratio and 90% interval, the monster / clean-winner / ADR-scaled ratios, B1-B3 beside it, and any
tag ("✂ gate-truncated", "against Qullamaggie's buys", "check = one regime" under fork 3a).

**5.4 What a correct build reads on these counts** (`design/spread_sim.py` → `spread_sim.txt`: 20,000 draws, synthetic
labels, months as blocks with month-to-month swings in the base rate, 2020 at 3× the other years — a guess; family
figures use the first Holm step, so they are lower bounds). **The base rate is unknown, so it is a grid.** Share of
runs in which a reading of the stated TRUE size is carried AND reaches PICKS THE TAIL (family of 9):
| True size | Base rate | Check = 2021 to 2022-Q1 only (fork 3a) | Check adds 2022-24 (fork 3b) |
|---|---|---|---|
| 1.5x | 3% | 11% - 27% | 26% - 49% |
| 1.5x | 5% | 25% - 52% | 55% - 81% |
| 1.5x | 8% | 51% - 80% | 81% - 97% |
| 2.0x | 3% | 52% - 81% | 84% - 98% |
| 2.0x | 5% or 8% | 80% - 100% | 98% - 100% |
| 1.3x | any | 3% - 26% | 5% - 49% |
| none (1.0x) | any | under 1 in 1,000 | under 1 in 1,000 |
(Each range: 60% of the indicative event count surviving the context gates → 100%.)
- Null 95% band of the ratio at a 5% base rate, 60% of the count: discovery 0.82-1.22, discovery without 2020
  0.66-1.52, check 0.69-1.46 (fork 3a) or 0.75-1.33 (3b). A true-zero feature shows a check ratio ≥ 1.2 about 1 time
  in 6 (3a) or 1 in 10 (3b): "DIRECTIONAL, NOT PROVEN" is not a finding.
- The 2020 guard is weak, as in the EP study: a reading that works only in 2020 passes conditions 1-2 about 3 times in
  4 and the ex-2020 floor then stops about 6 in 10 of those. The real protection is the check set.
- NOT simulated: same-day theme clustering (it widens every band), gate truncation, the group / cap rule.
**Plain reading (at a 5% base rate): with the 2022-24 years added this study reliably finds a 2x reading and finds a
1.5x somewhat more often than not; a 1.3x reading is usually missed. Without those years a 1.5x is found between 1
time in 4 and 1 in 2. If big winners turn out as rare as 3%, halve the 1.5x odds. NOT CARRIED is not proof a reading
is useless.**

**5.5 Pre-stated extra readings (for every carried feature and each of the operator's reads; NONE is a bar):** per
year; per era; the two first-break populations of §1.2; common stock only; price ≥ $5 only; the monster tier; clean
winners; the ADR-scaled tail; ADR-neutral; within each B1 (pick-score) third; break days with QQQ above / below its
50-day at D; breaks that gapped over the level at the open vs those that did not; each window length ±50% on
discovery only ("fragile" on a flip or a ratio under 1.2).

**5.6 Combination — one, pre-stated, nothing fitted.** If ≥ 2 features are carried: the equal-weight mean of their
within-month percentile ranks, each signed by its discovery direction, tested once on check as one family member.

**5.7 The operator's gallery reads (≤ 3, plus one slot for a ruling).** A read = something he names after looking at
gallery A. Each is coded as an exact definition under §4.0 with the direction HE states, corrupt-E tested, appended and
hashed BEFORE any check outcome. It skips the §5.2 gates (he saw the discovery winners); its discovery numbers are
printed "seen". **A read must be knowable when price crosses the level** — the EP study's TLRY ruling applies: what a
stock did after the break cannot be coded and takes no slot.

## 6. Order of work (no expectation formed after seeing data)
0. This draft → adversarial critique → v2 → the operator's forks → **freeze commit** (sha256 recorded).
1. **Stage 1, no forward read:** the list rebuild at the pinned sha, the bridge check, the context-gate share, the
   random draw, the identity map, feature table, NULL counts, tie shares, corrupt-E proof, Qullamaggie's coverage and
   position tables (§1.4). Table hashed.
2. **Calibration, synthetic labels only:** the ex-2020 floor; every statistic centred on 1.0 under no effect.
3. **Discovery outcomes** (reads forward bars ONLY for E ≤ 2020-12-31, asserted): base rate first, then §5.2.
4. **Blind recount** of stages 1 and 3 from this text alone + an adversarial review (look-ahead per feature, the
   2024-12-31 cut, the random draw, the permutation) — BEFORE check, because check runs once.
5. **Winner gallery A** shown to the operator. **HARD STOP until he replies** with his reads, or "none".
6. Freeze his reads; print check n per feature and era (outcome-free).
7. **Check outcomes, ONE run**, then its blind recount.
8. **Blind sheets B** if anything reached PICKS THE TAIL.

## 7. Chart sheets for the operator's eye (12 per sheet, seeded 1124, never hand-picked)
- **A. Winner gallery — outcome KNOWN, discovery only, shown before check.** Every discovery big winner, monsters
  first; each winner sheet paired with a sheet of 12 failures (§2) from the same months. Daily candles + volume,
  D−250 .. E+60, the level drawn, E marked, EMA10 / EMA21 / SMA50 / SMA200, every chart padded to one width; the
  feature values and the pick grade in small text under each. The first 3 pairs go to him in chat, the rest on disk.
  The count is unknown until stage 3 (at a 5% base rate, several hundred winners); if over 600, a seeded sample of 600
  winners is rendered and the rest on request.
- **B. Blind sheets — outcome HIDDEN.** For each PICKS THE TAIL feature or read (at most 3): 2 sheets × 12, 6 top-third
  + 6 bottom-third CHECK events, shuffled. Bars end at D with the level drawn; no ticker, date, value or axis labels;
  random file names; answer key hashed first. **Excluded from the draw:** every ticker-window of Qullamaggie's 757 buys,
  every name-night the operator has already graded or been shown (the 41 list grades, the 11-07 .. 11-16 sheets), and
  any identity with ≥ 3 check events. He rules good / okay / bad plus "recognised?"; the score is his eye against the
  feature's thirds (0.5 = nothing), a lean, never a verdict.
- Events shown on A or B are spent as outcome-blind labels.

## 8. What this does not answer
- **Money, the entry and the stop.** The outcome is a +50% close measured from the level. The live rule buys the break
  intraday with a stop at the day's low; a break that stops out and later runs counts as a winner here. That is fork 4 / #720.
- **Whether the detection rules are right.** Judged only on Qullamaggie's buys (#717). Truncated features (✂) cannot
  speak about their own gate.
- **Charts the list never shows** — about half of all big winners do not start with a breakout these rules see (#705).
- **Exactly the moment of decision.** Membership needs E's high above the level; the population is breaks that
  happened, at whatever minute. Which name breaks first in a morning is not in daily bars.
- **Small effects** (§5.4), **2025-26** (sealed, #710), theme, catalyst, float, intraday pace.
- **Regime.** The operator's 11-21 note: momentum is not expected to work in the current bear phase. Nothing here is a
  claim about now; the QQQ split in §5.5 is description.
- **An untouched check set** (§0).

## Critique resolutions
None yet — this is draft v1. Carried over from the EP study's critique and amendments: calendar windows and NULL
reasons for the features this study computes itself (D1 — only PARTLY: live-code values are exempt, §4.0) · code called, never imported from a script that runs at module level (D3) · group winner
by z on a common set (D4) · permutation among scored events only (D5) · Mantel-Haenszel for two-group features (A1) ·
identity on returns (A2) · one verdict word, no STRONG / LEAN · gallery before the check with a hard stop · failures,
not non-winners, as the contrast · the volatility ruling (§11.3) · reads knowable at the decision (§11.5).

## Unresolved (for the critique and stage 1, not for the operator)
1. **Era-B inputs for the list rebuild** — a raw close and a security type per name-night for 2022-04 .. 2024, and
   whether the split file behind them carries post-2024 dates (the EP study inherited that and disclosed it). The
   11-01 replay ran 2017-2024, so the pieces exist under `scripts/probes/_breakout_v1_replay_1101/`; not verified here.
2. **The context gates' cut** of the event count (§5.4 brackets it at 60%-100%) and whether the pinned-sha rebuild
   still reproduces the 11-13 capture.
3. **The 2020 multiple** in the simulation (3×) is a guess; the EP study's was 5×. Stage 3's first print replaces it.
4. **The random draw is one draw.** A second seed should be printed on discovery as an extra reading so a verdict does
   not rest on which break of a name was picked; not yet written into §5.5.
5. **Pick-score for era-A nights before the model existed** is computed by the live function on historical inputs —
   fine as a benchmark, but confirm `pick_scores` needs nothing unavailable historically (the SIC group file).
6. **RS leadership alone** is registered for the sealed test under #710; features 4-6 here must not be reported as
   that test's answer.
7. When committed, the file needs its pointer in `docs/SSoT.md` (findings are never owners) and a PLAN.md line.
8. **Live-code values and bad bars.** Gate values and list membership are computed by the live code on rows, with no
   adjustment / identity NULL and default passes on short history (§4.0). Decide at the critique: apply the EP study's
   NULL rules on top (the event is dropped or the feature NULLed when its look-back holds a flagged date), or keep
   "as the live system would have seen it" and tag.
