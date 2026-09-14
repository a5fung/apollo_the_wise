# Correlation engine revalidation — precision 36%, not 0.5%; keep it, do not build the alert gate (2026-09-14)

**Review:** `data_gated_reviews.yaml` → `correlation_engine_revalidation` (ripe 104 days). **Decision it
serves:** retire `correlation_engine.py` + `/clusters` (the entry's own action if precision < 5%), keep
as-is, or keep and gate on alerting. **Read-only, $0:** prod queries captured once, local numpy; no
LLM call; no code, config, DB, YAML or PLAN change. ⚖ THE LINE: evidence and a recommendation only —
retiring a detector or adding an alert gate is a detection-criterion change (CHANGE_PROCESS + sign-off).

## The answer

- **Precision (the 2026-04-17 definition, same matcher) = 36.2% — 354 of 979 cluster-days stored
  in the live nightly era (04-17 → 07-31) had at least half their members inside one `mi_themes` row
  2–6 weeks later.** The retire condition ("still < 5%") is not met by a factor of seven.
- **It is the same definition as the old 0.5%, but the old number was never a measurement:** the
  04-17 run's own rows (Dec–Feb) reproduce 0.5% exactly here (3 of 560) because their 2–6-week
  lookahead fell before `mi_themes` begins (2026-03-19). The 5% bar was set against a data gap.
- **Not useless:** random same-size groups from the same universe score 0.20% (45 of 22,900). Recall
  on genuinely new themes with a 2–6-week lead is 12.6% (27 of 215) against 1.9% for random groups.
- **But "precision" here is what the theme engine chose to name.** It tracks the theme engine's own
  birth rate month by month (April 0 of 125 with 38 births; July 144 of 224 with 126 births), and the
  engine's strongest clusters are the ones discovery names least (RS ≥ 70: 19.8%, n = 247).
- **Recommendation: keep as-is (option 2), do not build the alert gate (option 3) — there is no
  high-precision stratum to gate on, and "the theme engine later named it" is not a page-worthy fact.**

## 1. Definitions and bars — declared before anything was computed

**The 2026-04-17 pipeline exists:** `scripts/backtest_clusters.py` (commits `f70bf9ab`, `69eb761a`;
result recorded in commit `88aa5110` / CLAUDE.md session 4). Its definitions, used verbatim here:

- **Precision** — per **cluster-day** (a cluster emitted on day D): a hit if ≥ 50% of the cluster's
  tickers appear in ONE `mi_themes` row dated D+14 … D+42 (calendar days). Denominator = cluster-days,
  so the same four names for 25 nights are 25 trials; a distinct-member-set denominator is given
  alongside.
- **Recall** — per **theme birth** (first `theme_date` of a name): a hit if ≥ 50% of the birth row's
  tickers sit inside ONE cluster dated birth−42 … birth−14. Denominator = distinct names.

**Why I did not run the pipeline as-is (and it must not be run against prod):** each day it calls
`run_correlation_clustering(day)`, which (a) `DELETE`s and re-`INSERT`s that day's
`mi_correlation_clusters` rows — a rerun over 04-17 → 09-11 would overwrite 106 nightly dates — and
(b) dedups against `get_active_themes()`, which is **now-relative** (`theme_date >= CURRENT_DATE − 7`):
the Dec–Feb backfill rows in the table today were deduped against April 2026 themes. The metric was
therefore replicated locally on captured exports; the proof the replication is faithful is that it
reproduces the recorded 0.5% on the backfill rows to the digit.

**Comparability to 0.5% / 8.2%:** definitions identical; **eras not comparable.** The old precision
lookahead (Jan 2026 – mid-Mar 2026) contains no theme rows at all, and the old recall population was
themes born 03-19 → ~04-13 matched against February clusters. Every number below is on a window where
both sides exist.

**What a WORKING and a USELESS engine would each produce (declared before running):**

| reading | WORKING | USELESS |
|---|---|---|
| precision on uncovered-at-D clusters vs random same-size groups from the same day's universe | well above random | indistinguishable from random |
| where the hits sit | on clusters NOT already covered by a theme | on covered-at-D clusters only (theme persistence, not detection) |
| recall on NOVEL births (not re-namings) with a 14–42-day lead, ≥ 2 shared names | materially above its random null | at its null, or hits only at lead 0 (same-night self-naming) |

**Honesty note on the recall row:** the bar declared before the first run was the definition as
written (any birth, ≥ 50% of names). "NOVEL" and "≥ 2 shared names" were added AFTER pass 1 showed
the written definition degenerates on 2–3-name themes (one shared name suffices; random groups reach
36%) and counts re-namings of an existing group as births. Both refinements LOWER the engine's recall
(27.1% → 12.6%) — they cut against the engine, not for it — and the as-written number is still
reported in §4.2.

Stated limit of the test: the random null is a **low bar** — a random 4-set from ~2,000 names rarely
half-overlaps a 5-name theme — so beating it is necessary, not sufficient. A sector-lookup null (would
"same GICS industry" match themes as well?) was not available at $0 (no full-universe sector table).

## 2. The dedup bias and how it was handled

`correlation_engine._dedup_against_themes` drops any cluster with ≥ 50% of its members inside ONE
non-Fading active theme **before the write**, so `mi_correlation_clusters` holds uncovered clusters
only, and once a cluster is named it stops being stored. A "did a stored cluster become a theme" measure
is biased against the engine by construction.

**Choice: recompute from closes with no dedup, then split.** `_compute_tight_clusters_sync` (the live
function, current code) was run on every trading day 03-09 → 09-11 with the live universe rules
reproduced from `db.get_closes_for_correlation`; each cluster was then tagged **covered-at-D** (≥ 50%
inside one non-Fading theme active on D, reproducing the dedup's input — latest row per name with
`theme_date` in [D−7, D−1], Retired dropped, alphabetical "last theme wins" as in
`get_active_themes`) or **uncovered-at-D**. Precision is reported for both halves and their union, so
the bias is measured (§4.1: it is worth +7 points) rather than asserted. The stored table is reported
too, for continuity with the old number.

## 3. Method — population, window, how derived

- **Closes:** `mi_daily_closes` rows 2026-02-02 → 2026-09-11, `close ≥ 5`, `volume > 0`, security
  type CS/ADRC via `mi_security_types` plus SPY (629,417 rows, 4,924 tickers, 154 trading days).
  Live universe rule per day: 35-calendar-day window, full coverage, average close×volume ≥ $20M, SPY
  exempt. Resulting matrix universe: median **2,042 names/day**; the live SQL on the 09-10 window gives
  **2,021** (the "~2,800" in the docs is an April figure). ~15 tight clusters/day (6–28).
- **Themes:** all 7,235 `mi_themes` rows, 124 dates 03-19 → 09-11, 552 names. Births by month after
  03-19: Mar 48 · Apr 38 · **May 6** · Jun 43 · Jul 126 · Aug 194 · Sep (to 11th) 84.
- **Stored clusters:** all 12,917 `mi_correlation_clusters` rows = 1,973 clusters over 148 dates. The
  42 Dec–Feb dates were all written on **2026-04-18** — they are the April backtest's output, not
  nightly runs; the nightly era is 04-17 → 09-11 (106 dates).
- **RS:** `scripts/probes/_step1_scores_all.tsv` (frozen `mi_stock_scores` export, 01-16 → 09-04) for
  the per-cluster `avg_rs` the engine would have attached.
- **Windows:** precision on cluster dates ≤ 07-31 so the whole 42-day lookahead is observed; recall on
  births 04-20 → 09-11 (the recompute reaches 42 days before 04-20). Live consumption of clusters by
  discovery began **04-17** (`f70bf9ab`); 03-19 → 04-16 is reported separately as the pre-feeding era.
- **Bridge (recompute vs stored, same-day dedup reproduced):** 09-09 8/8 · 09-10 8/8 · 09-11 7/7 (post-#486
  dates, identical code) · 06-15 16/16 · 08-20 13/14, the one miss being GOOG/GOOGL/GOOGM/GOOGN, which
  the current share-class collapse (#486, 2026-09-09) removes. Recompute + dedup precision in the live
  era = 35.6% vs stored 36.2% — the two populations agree.
- **Null:** for every cluster-day, 20 random groups of the same size drawn from that day's matrix
  universe, scored with the same matcher; for recall, every day's clusters replaced by random same-size
  groups, 20 replicates.
- **Discovery recorder:** the 8 `theme_discovery_shown_declined` rows (09-08 → 09-11; one nightly +
  one shadow per night).
- Scripts and captured outputs: `/Users/alvinfung/.claude/jobs/02473824/tmp/` (`revalidate.py`,
  `revalidate2.py`, `01_schema.txt`, `02_closes.tsv`, `03_themes.tsv`, `04_clusters.tsv`,
  `05_recorder.txt`, `06_recomputed_clusters.tsv`, `07_revalidate_out.txt`, `08_universe_size.txt`,
  `09_revalidate2_out.txt`).

## 4. Results

### 4.1 Precision — ≥ 50% of the cluster in one theme row 14–42 days later

| population | n = cluster-days | hits | precision | distinct member-sets |
|---|---|---|---|---|
| Dec–Feb backfill (the 04-17 run's own rows; reproduces the old number) | n = 560 | 3 | **0.5%** | 2 / 345 = 0.6% |
| **STORED, live nightly era 04-17 → 07-31 (uncovered-only, as live)** | **n = 979** | **354** | **36.2%** | 167 / 494 = 33.8% |
| RECOMPUTED, uncovered-at-D, 04-17 → 07-31 | n = 962 | 342 | 35.6% | 166 / 490 = 33.9% |
| RECOMPUTED, covered-at-D, 03-19 → 07-31 (what the dedup deletes) | n = 161 | 147 | 91.3% | 86 / 98 = 87.8% |
| RECOMPUTED, all (no dedup), 04-17 → 07-31 | n = 1,107 | 473 | 42.7% | 213 / 538 = 39.6% |
| RECOMPUTED, uncovered, pre-feeding era 03-19 → 04-16 | n = 183 | 3 | 1.6% | 2 / 112 = 1.8% |
| RECOMPUTED, uncovered, 06-01 → 07-31 | n = 533 | 318 | 59.7% | 153 / 279 = 54.8% |
| **random null** — same day, same size, same universe (20 per cluster-day) | n = 22,900 | 45 | **0.20%** | — |

- **Quality-adjusted (live era, n = 962):** the matched theme ever reached Accelerating/Mainstream in
  274 = 28.5%; every matched theme lived ≥ 2 snapshot days (no one-day-Nascent hits).
- **The dedup bias is +7 points:** including the covered-at-D clusters lifts 35.6% → 42.7%. Their
  91% "precision" is theme persistence, not detection, and is rightly excluded from the headline.
- **Distinct groups:** chaining member-sets across days (Jaccard ≥ 0.5, ≤ 14 days apart) gives 242
  groups from the 1,145 uncovered cluster-days; **70 = 28.9% became a theme.** 866 distinct member-sets
  over 1,824 cluster-days; 561 appear on exactly one day — clusters churn nightly even when the group
  persists.

**By month — precision follows the theme engine's birth rate, not the clusters:**

| cluster month (stored, live era) | n = cluster-days | hits | precision | theme births that month (a cluster's lookahead lands 2–6 weeks later, i.e. mostly the NEXT month's births) |
|---|---|---|---|---|
| 2026-04 | n = 125 | 0 | 0.0% | 38 |
| 2026-05 | n = 308 | 24 | 7.8% | 6 |
| 2026-06 | n = 322 | 186 | 57.8% | 43 |
| 2026-07 | n = 224 | 144 | 64.3% | 126 |

The pre-feeding era (1.6%) therefore cannot serve as a "no-cluster counterfactual": April is ~0 in
both eras because the theme engine named almost nothing in April–May.

**Stratification (for option 3) — recomputed, uncovered-at-D, 03-19 → 07-31:**

| stratum | n = cluster-days | hits | precision |
|---|---|---|---|
| avg RS < 50 | n = 591 | 195 | 33.0% |
| avg RS 50–70 | n = 290 | 101 | 34.8% |
| **avg RS ≥ 70** | n = 247 | 49 | **19.8%** |
| mean corr 0.80–0.85 | n = 795 | 218 | 27.4% |
| mean corr 0.85–0.90 | n = 315 | 121 | 38.4% |
| **mean corr ≥ 0.90** | n = 35 | 6 | **17.1%** |
| size 4 | n = 453 | 126 | 27.8% |
| size 5–8 | n = 527 | 174 | 33.0% |
| size 9+ | n = 165 | 45 | 27.3% |
| stored live era, engine's own avg_rs ≥ 70 | n = 223 | 46 | 20.6% |

No stratum exceeds 40%. The tightest and strongest clusters are the **least** likely to be named —
the same read as the 09-07 runway doc (RS ≥ 70 lineages converted 23%).

### 4.2 Recall — ≥ 50% of the birth row inside one cluster dated birth−42 … birth−14

| population (births 04-20 → 09-11) | n = births | hits | recall | random null |
|---|---|---|---|---|
| ALL births, the definition as written | n = 462 | 125 | 27.1% | 18.5% |
| … theme size 2–3 | n = 225 | 39 | 17.3% | 36.0% |
| … theme size 4–6 | n = 185 | 60 | 32.4% | 2.4% |
| … theme size 7–12 | n = 33 | 18 | 54.5% | 0.0% |
| … theme size 13+ | n = 19 | 8 | 42.1% | 0.0% |
| ALL births, ≥ 50% **and ≥ 2 shared names** | n = 462 | 111 | 24.0% | 1.8% |
| **NOVEL + reachable births, ≥ 2 shared, lead 14–42 d** | **n = 215** | **27** | **12.6%** | **1.9%** |
| NOVEL + reachable, ≥ 2 shared, any lead ≥ 1 day | n = 215 | 46 | 21.4% | 2.5% |
| STORED nightly clusters, births 05-29 → 09-11 (for continuity) | n = 448 | 122 | 27.2% | — |

- **Against the old 8.2%:** same definition, 27.1% (125 of 462 births) — but, as with precision, the
  old number's era is not comparable (themes born 03-19 → ~04-13 matched against February clusters),
  and the definition itself is not interpretable below 4 names (next bullet).
- **The definition as written is not interpretable for 2–3-name themes** (225 of 462 births): ≥ 50% of
  a 2-name theme is one shared name, which random groups achieve 36% of the time. Requiring ≥ 2 shared
  names fixes that (null 1.8%).
- **Half the births are re-namings.** 237 of 462 birth rows overlap ≥ 50% with a theme row that
  already existed under another name (five separate "tanker" births 06-22 → 09-08; eight refiner
  births; ten precious-metals births). Only 225 are **novel**; 215 of those are reachable (≥ 50% of
  their names inside the $20M-ADV matrix universe).
- **The honest lead number:** the engine pre-flags **1 in 8 genuinely new themes 2–6 weeks before
  birth** (27 of 215), against 1 in 50 for random groups; 1 in 5 with any lead at all. Examples:
  tankers (06-22, lead 21 d), airlines (06-25, 30 d), regional banks (07-01, 27 d), self-storage REITs
  (07-06, 33 d), trucking (08-10, 14 d). Recall rises with theme size (4–6 names 14.3%, n = 84; 7–12
  names 4 of 7).

### 4.3 What discovery does with the clusters — the recorder, 4 nights (09-08 → 09-11)

| run | clusters shown | taken (all members claimed) | partial | already named | declined |
|---|---|---|---|---|---|
| nightly, precision disposition | n = 35 | 6 (17%) | 5 | 3 | 21 (60%) |
| shadow, recall disposition | n = 35 | 3 | 8 | 4 | 20 |

Four nights is a direction, not a rate.

## 5. Working vs useless — verdict against the declared bars

| bar | reading | verdict |
|---|---|---|
| uncovered precision vs random | 35.6% (n = 962) vs 0.20% (n = 22,900) | far above random |
| where the hits sit | headline excludes covered-at-D clusters; the excluded half scores 91% | hits are on uncovered clusters |
| novel-birth recall, ≥ 2 shared, 14–42 d lead | 12.6% (n = 215) vs 1.9% | above null; modest in absolute terms |

**Not useless.** The engine carries real grouping information and front-runs a minority of new themes
by 2–6 weeks. **But its measured "precision" is controlled by its consumer:** the number moves with
the theme engine's naming rate (0% → 64% across four months with the clustering unchanged), and the
strongest clusters are the ones discovery declines. The engine is working as a **discovery feeder**;
as an **early-warning instrument** its yield is about one new theme in eight.

## 6. Dependents — who reads it today

- **Live path:** `scheduler.py:619` step 4.5 of the nightly job (before the 17:07 ET theme engine) →
  `theme_engine._discover_new_themes` in BOTH dispositions (nightly precision `:8303`, ADR-0007 shadow
  recall `:1341`) via `_partition_discovery_pools` / `_render_cluster_block` (#486 rendering) → the
  `theme_discovery_shown_declined` recorder (`:5917`). Persisted by `db.upsert_correlation_clusters`
  (`db.py:15426`); table created at `db.py:2030`.
- **Operator surface:** `/clusters` — `channels/telegram.py:536, 813, 1527, 1798`,
  `scripts/preflight_command_parity.py:50`, `agent.py:1028` → `_handle_correlation_clusters` (`:3981`).
- **Sunday digest:** `system_review._aggregate_clusters` (`:1241`, count + mean cohesion).
- **Planned reuse:** ADR 0006 (catalyst discovery loop) names it the co-movement primitive; the
  deferred ADR-0006 review in `data_gated_reviews.yaml:5264` says "reuse correlation_engine".
- **Analysis reuse:** `scripts/probes/_step1_theme_precision.py` imports
  `_compute_residual_correlations`; `docs/methodology/primitives.md` lists "tight cluster".
- **Tests:** `tests/test_correlation_engine_artifacts_486.py`, `test_theme_cluster_rendering_486.py`,
  `test_theme_batching.py`.
- **NOT a dependent, do not conflate:** `ep_theme_belonging.py`'s SPY-subtraction correlation (the
  2026-09-13 membership test, 0.35 bar) is different math, calibrated separately; PLAN #660 already
  rules that `correlation_engine.py` is not its home and that the two must not be unified (THE LINE).
- **Cost:** numpy only; no LLM call of its own. Cluster members outside every pool count as rendered
  stocks toward the discovery batch cap (`_DISCOVERY_LLM_BATCH_STOCKS = 22`, up to 12 described per
  cluster — `_partition_discovery_pools._weight`), so a cluster-heavy night can add a batch, i.e. one
  more discovery call on the same path; never a separate call. Not quantified here.

## 7. The three options

| option | evidence | recommendation |
|---|---|---|
| **1. Retire** `correlation_engine` + `/clusters` | The entry's own retire condition (precision < 5%) is not met: 36.2%, n = 979. Removal touches the nightly discovery input in both dispositions, the recorder, the Sunday digest, four Telegram sites + the parity gate, three test files, and the ADR 0006 plan. | **No.** The evidence the entry asked for points the other way. |
| **2. Keep as-is** | No LLM call of its own (its only spend is an occasional extra discovery batch); discovery takes 17% of showings outright and 36% of shown clusters are a theme within 2–6 weeks; 1 in 8 new themes pre-flagged 2–6 weeks early vs 1 in 50 random. | **Yes — recommended.** Close the review as revalidated. |
| **3. Keep and gate on alerting** ("HIGH-precision clusters trigger Telegram") | No high-precision stratum exists: RS ≥ 70 → 19.8% (n = 247), corr ≥ 0.90 → 17.1% (n = 35); the best band (corr 0.85–0.90) is 38.4% (n = 315). And a hit means "the theme engine later named it" — not a fact worth paging the operator for. | **No, not as written.** If an operator-facing cluster surface is wanted, the question to answer first is whether a cluster precedes an EP or RS move (ADR 0006 / #486 territory), which this review did not ask. |

**Recommendation: option 2.** Operator's call; nothing changed here.

**Side findings for the parent (not actions):** (a) `scripts/backtest_clusters.py` writes prod and
dedups against today's themes — it should not be run against prod again as-is; (b) 237 of 462 theme
births in the window are re-namings of an existing group — the #555 churn, quantified; (c) the docs'
"~2,800 tickers" universe is ~2,020 today.

## What this does not answer

- **The counterfactual.** Whether the themes discovery took from clusters would have been named from the
  bare pools anyway. Answering it needs a paired discovery run without the cluster block — LLM spend —
  and the recorder has four nights.
- **Whether correlation beats a sector lookup.** A "same industry" null was not available at $0 (no
  full-universe sector table). Beating random groups is necessary, not sufficient.
- **Whether clusters precede price moves or EPs.** The review asked about theme precision/recall;
  runway/ignition is the 09-07 doc's question, not this one.
- **A clean no-feed baseline.** The pre-feeding era (03-19 → 04-16, 1.6%) is confounded by the
  April–May birth drought (38 and 6 births), so it does not isolate the feeding effect.
- **Recall for 2–3-name themes** (225 of 462 births) — the definition degenerates to one shared name
  there; reported, not interpreted.
- **Membership correctness.** Theme rows are read as written, including any names the no-thesis
  validation held wrongly (the 09-07 docs' caveat).
- **Pre-09-09 stored rows under the current code.** The recompute uses the #486 share-class/cash-like
  filters throughout; on the bridge dates the only difference was the GOOG cluster.
- **Cluster dates after 07-31.** Their 42-day lookahead is censored; recall uses them, precision does not.
- **Renames vs rebirths.** "First occurrence of a name" inherits every rename as a birth (name
  canonicalization was never shipped); the NOVEL split is the correction, not a lineage model.
