# #714 — Pre-registration: the float points and neglect, read on his labelled EPs and on the tail (frozen 2026-10-31)

**MEASUREMENT ONLY. $0. Nothing here changes or proposes to change the score, a threshold, admission, sizing, a safeguard or
live trade state — any such change is CHANGE_PROCESS and the operator's call (THE LINE).** This is a REGISTRATION: it fixes,
before any output of the capture files exists, what is measured, on which rows, by which rule, and what each possible result
will be called. Written Sat 2026-10-31 PT. The capture SQL is `scripts/probes/_714_study_1031/capture/*.sql` (hashes §14). The
read itself (stage 2) is not written yet; §12 fixes what it must compute and in what order. Template followed:
`docs/analysis/686_preregistration_2026-10-04.md`.

**Plain-words key.** *Separates* = his real EPs sit on the favourable side of their same-day rivals AND the favourable group
runs big more often. *Null* = neither shows. *Not powered / not measured* = the data cannot say, which is NOT a null. A feature
only reaches him as "a lead" if it is favourable on BOTH legs (§8).

## 0. The questions, and the answers each can give

- **Q1 (float).** The +5 raw points for float under 50M shares (`ep_rubric.SCORE_WEIGHTS['float']`; +6.25 presented, +7.5 on a Bull
  day) have been in the score since the first prototype and were never measured (the 08-22 redesign left them out as "not
  measurable point-in-time", `selection_layer_533_2026-08-22.md` L198). Answer: **KEEP-rec / DROP-rec / NO-REC** (§5.5) with the
  separation read, the tail read and the count of alerts that exist only because of the +5.
- **Q2 (neglect).** Was deleted 08-22 after three nulls on three definitions; he asked to revisit it ("mentioned many times").
  Answer: for each pre-registered definition one of **SEPARATES · TAIL-ONLY · LABEL-ONLY · CONFLICT · NULL · BACKWARDS · NOT
  POWERED · NOT MEASURED** (§8), plus the list of what is still untried and why (§4).
- The deliverable to him is ONE results table (§12) and a one-line recommendation per row. No score change without his sign-off.

## 1. What was already seen, said once and up front (blindness)

Read locally before this registration was written (none of it is a float- or neglect-versus-outcome tabulation):
- `_686/data/pop.tsv` (the September block, 75 rows): float is stored on 75 of 75 rows, 26 of 75 are under 50M, and the stored
  score parts show float 0 or 5. `_684/pop.tsv`: stored float is 0 of 228 / 110 / 119 rows in May / Jun / Jul, 3 of 198 in Aug,
  15 of 15 in Sep (the stored-float era starts with #605, ~2026-08-29). `_ftai_1029/q4_float.out`: float points were awarded on
  492 of 1,705 scored TICKS (29%, 34 names) in the 30 days to 10-29.
- Published aggregates the registration leans on: #684/#686 (12 runners in the 75 September rows; the base/neglect features 11–16
  held on nothing; L1 "quietest third" 13.0% vs 17.3%, can't tell), #533 (AUCs in §4), the 08-16 RS probe (§4).
- The runner label of the 05-01..09-25 rows was therefore SEEN in aggregate by #684/#686, but NO feature defined here was ever
  computed on those rows. This registration protects against feature-versus-outcome fishing, not against knowing the base rate.
- **Never read by any study: scan dates 2026-10-12..10-30** (the fresh block, §10). Their rows are not in the main pull. Blindness
  caveat as in #686: for a ticker present in BOTH blocks, the main bars file (loaded through 2026-10-30) already holds the early
  sessions of its fresh-block forward window; stage 2 truncates every main-window row's outcome at +15 sessions and does not open
  fresh-block rows.
- No capture output exists at the time of writing; the writer of this document could not read production.

## 2. Populations (named before any read)

**Labelled set L** = the 8 names in `shared/operator_labelled_eps.py::OPERATOR_LABELLED_EPS` (his words,
`docs/methodology/operator_labelled_eps.md`): BFLY 2026-06-18 · PLTR 08-04 · ABNB 08-07 · TEAM 08-07 · HTFL 08-14 · MRNA 08-19 ·
CHPT 09-03 · PENG 10-07. Stage 2 asserts this list equals the SQL's. ABNB and TEAM share ONE board (08-07): 8 EPs on **7 boards**,
not 8 independent trials. ABNB (cut by the top-20 shortlist) and CHPT (`mcap_too_small`) never reached scoring; they are still
read, from their own scan-log row and daily bars.

**Population A (his ground truth: selection).** For each labelled EP, its **rivals R1** = every OTHER ticker with at least one
scan-log row that scan date with `ep_score IS NOT NULL` (it reached scoring: the board the ranker actually ranks, and the only
rows on which float points exist), one row per ticker by the #686 dedupe (prefer the tick that PASSED, else highest `ep_score`,
ties → latest tick), minus every labelled EP of that date. Why scored rows and not "every gapper at or above the floor": the
admission floor moved 10→9% on 08-19, so a floor-defined rival set would mix rule eras across the 7 boards.
Secondary rival sets (sensitivity only, never a verdict): **R2** = every LOGGED ticker that date (any `filter_reason`) with
prior close ≥ $5 and 20-session average dollar volume ≥ $5M (computed from bars); **R3** = rivals that PASSED (an alert of any
tier). `10_labelled_and_rivals.sql` captures every logged ticker with its `filter_reason`, so R2/R3 are computable.
A board with fewer than 4 rivals having a valid value for a definition is **thin** for that definition (excluded from its mean,
counted).

**Population B (the tail).** Every deduped scored row (`ep_score IS NOT NULL`, same dedupe, safeguard-blocked rows INCLUDED as
EPs, per his 09-28 ruling) with `scan_date` from **2026-05-01** (the #684 start) to the last scan date with 15 forward NYSE
sessions of stored bars — **2026-10-09** if the 10-30 bar is loaded (Stage 2 recomputes it from the SPY calendar and censors,
never fills, a row whose forward window is short). The unscored labelled rows (ABNB, CHPT) are NOT in B. Expected n ≈ 800
(#684 had 671 through 09-03, #686 added 75, ≈ 55 more through 10-09); STEP 0 prints the real one.
**Blocks** (calendar thirds of the 112 NYSE sessions in the window, fixed now, outcome-blind): **B1** 05-01..06-25 (38 sessions) ·
**B2** 06-26..08-19 (38) · **B3** 08-20..10-09 (36). Eras: the 08-19 admission-floor change falls at the B2/B3 boundary and the
08-22 score rescale inside B3; the stored-float era (§5.2) is inside B3. Pooling across B1–B3 is allowed because every neglect
feature is bar-derived and every verdict must be sign-consistent across blocks (§8.1), never because the eras are assumed equal.

**Neglect population N** ⊂ rows of A and B = rows with ≥ 504 prior daily sessions in `mi_daily_closes` (history starts
2021-09-27, so ~4.9 years exist for the 2026 events), no un-applied or phantom split inside the window, and ≥ 95% non-null
volume/close in the window. Short-history names (~1/3 of recent rows) cannot have "years of neglect": they are excluded from
EVERY neglect definition identically, counted, and their runner rate is printed descriptively. Float has no history requirement.

## 3. Outcome and tail measure (frame A of #686, verbatim — nothing invented)

`run_xadr = (max HIGH over sessions +1..+15 − gap-day CLOSE) / ADR$`, `ADR$ = mean((h−l)/c) over the 20 sessions before the gap
day × the gap-day close`, bars from `mi_daily_closes`, session calendar from SPY. **RUNNER = run_xadr ≥ 5.0** (the verdict
statistic, as in #684/#686). Reported, no verdict: ≥ 8 ADR; max excursion ≥ +50% from the gap-day close; the **P90 of the max
excursion** (the tail, not the median). Cross-check (§11 C3): the bar-derived gap-day close must equal
`mi_ep_scan_outcomes.baseline_close` on ≥ 95% of rows. Unit effect (≥ 5 ADR vs ≥ 25% disagree on 38 of 667 old rows) is a limit, not a dial.
Rows are never dropped for a bad outcome; a row without 15 forward sessions is censored and counted.

## 4. Neglect: what was tried, what never was, and what $0 can measure

**Bonde's five kinds** (`docs/methodology/images/bonde_what_is_neglect_2026-10-11.jpg`, read 10-31): financial ("long period
with no growth, then suddenly growing"), price ("a long period with no meaningful price rally; years better"), volume/liquidity
("long period of below-average daily volume"), news/attention ("no analyst coverage; no major news for months/years"),
ownership ("below 20 to 30 funds owning it"). His own words add: *"a large base… indication of neglect (at least there's no major
movements up or down) so the news moving it significantly is truly unexpected"* (08-19); *"the tail is where I'd expect neglect to
form"* (08-16); on coverage *"I don't think it's good, if might just include thin stocks that's are tiny caps. A corollary to that may be the lack
of or deceleration of analyst upgrades, just a thought"* (10-11, verbatim; he added "no action yet": thin coverage alone is RULED
OUT; no/slowing upgrades is his candidate).

| # | Kind / candidate | Tried before? | Measurable at $0 from stored data? | Registered here as |
|---|---|---|---|---|
| 1 | Price neglect: no meaningful RALLY for a long time (Bonde) | **Never.** Notes say a "largest rally in the past 1–2 years stayed small" measure was untested | **Yes** — `mi_daily_closes`, 4.9 yrs | **NP** (primary) + 2 encodings |
| 2 | Quiet sideways base, no big move EITHER way (his 08-19) | **Tried 3×, null/backwards:** #569 v1/v2 quiet-base duration (AUC 0.42; within-day 0.31; ex-04-08 0.55), #684/#686 features 11–16 (none held) | — | not re-run |
| 3 | Beaten-down: price < 50/70% of the 52-week high | **Tried, deleted 08-22** (it measured beaten-down; MRNA at its high scored 0; 65% of real EPs scored 0 vs 52% of controls) | — | not re-run |
| 4 | Volume neglect: long period below own average volume (Bonde) | **Never** as a long-run state (the live liquidity part is the ABSOLUTE ADV$ level; gap-day volume features read null/backwards) | **Yes** — bar volume | **NV** (primary) + dry-up ratio |
| 5 | News/attention: no major news for months (Bonde) | **Never** | **No headline history is stored** (`raw_*_news_json` fills only on the alert-time earnings path; `mi_tv_news_shadow` is a rolling ~25-headline post-hoc table; `mi_coverage_probe` is theme peers). **$0 proxy from bars: attention-event days.** True headlines: Alpaca news API (X3) | **NA** (primary, a PROXY, named as one) |
| 6 | Thin analyst coverage (Bonde) | **Never**; **ruled OUT alone by him 10-11** (tiny caps). Testable only size-matched | `mi_analyst_estimates` starts 2026-08-31 with ≈28-day reach per ticker → at most PENG among the 8 EPs, and Sept–Oct rows of B | **D4** descriptive, size-matched, partial |
| 7 | No / slowing analyst upgrades (his corollary) | **Never.** The 07-18 #332 test was the OPPOSITE sign (a ≥3-upgrades bonus; no outperformance, p 0.29) | Not stored; dated events via `collector.get_recent_upgrade_events` (yfinance `upgrades_downgrades`), external, $0 | **X2** (Stage 1b, Tier A, Leg L only) |
| 8 | Fund ownership < 20–30 funds (Bonde) | **Never** | **No** — 13F not stored. Sources: SEC EDGAR 13F (free, quarterly, 45-day lag, heavy to build); yfinance `major_holders` institution count is a CURRENT snapshot only (verify the field first) | not run; named |
| 9 | Financial neglect: long flat growth, then sudden acceleration (Bonde, Qullamaggie) | The acceleration half is scored (catalyst rubric; #333 holds the forward leg). The "long flat" half **never** | **No** — `mi_fundamental_flags` is purged at 30 days; `q_revenue_yoy_pct` exists only at alert time on the earnings path. Source: SEC EDGAR companyfacts (free, filing-date stamped) | not run; lives with #333 |
| 10 | Out of favour (his 08-16: "the bottom is where neglect forms") | **Tried on tail winners, null/backwards:** RS level (dead as a grade input), slope, curvature (his deceleration↔neglect mapping read BACKWARDS), duration at the bottom — 240 tail tests, 0 survive. **Never read on his labelled list** | **Yes** — `mi_stock_scores` | **D3** descriptive, Leg L only |
| 11 | A catalyst that is truly unexpected | **Partly:** #568 `expct_scheduled` shipped 08-18 (unscheduled reached ≥ 8 ADR 11.6% vs 3.8%) — alerted rows only | Yes but ALERTED rows only (`mi_alert_rank_shadow`); rivals that never alerted have no value | **D2** descriptive |
| 12 | Qullamaggie: sideways months/years, then ~10× average volume (a COMBINATION) | **Never** as a combination (the 10-06 test map assigned it to the #686 follow-up) | Yes | **D5** descriptive |
| 13 | Shipped tag `setup_class='episodic_neglect'` ($2–10B, price < 70% of the 52-week high, `upgrades_30d == 0`) | Stored visibility tag since 07-18, never read against his list | Yes, alerted rows only | **D1** descriptive |
| 14 | Prior-momentum penalty; gap/ADR ("19×ATR") | **Tried:** AUC 0.52 (deleted); gap/ADR AUC 0.41 (backwards) | — | not re-run |

**Stated up front:** the ONLY new verdict-bearing neglect definitions are rows 1, 4, 5 (NP, NV, NA). They are three encodings of
"quiet for a long time" that differ from the three tried definitions in WHAT is held quiet (rally size, volume level relative to
own history, attention events) — not a fourth variant of the same base-tightness measure. Three nulls already exist on the
price-SHAPE reading; a fourth null here would still leave rows 6–9 (coverage, upgrades, ownership, financial) unread, and the
final table says so.

## 5. FLOAT

### 5.1 Definitions
- **F1 (verdict).** `lowfloat = 0 < float_shares < 50,000,000` — exactly the live rule (`ep_detector.py:2075-2080`); unknown float
  is "not low" in the live score, but here it is **excluded and counted** (a missing value is not evidence of a large float).
- **F2 (descriptive, no verdict).** Alternative cuts 20M and 100M; float quintile runner rates; Spearman of float with ADV$ (the
  tilt the task names: float points favour small names while the liquidity part, up to +15, favours large).
- **F3 (descriptive).** Gap-day volume ÷ float (turnover).

### 5.2 Float source and the coverage problem (the blocker, stated first)
`mi_ep_scan_log.float_shares` and `score_breakdown` exist only from the #605 decision-vector capture (~2026-08-29). Of the 8
labelled EPs only **PENG (10-07)** is certain to carry a stored float; **CHPT (09-03)** was killed at the market-cap filter before
the profile fetch and probably has NULL; BFLY, PLTR, ABNB, TEAM, HTFL and MRNA are before the era. Per row, the value used is, in
order: (a) `float_shares` on the chosen tick; (b) the largest `float_shares` on any tick that day (`float_any_tick`); (c)
**`yf_now`** — yfinance `Ticker.info['floatShares']` fetched in Stage 1b (the SAME field and vendor the live score reads,
`collector.get_fmp_profile`, but a 2026-11 snapshot, as `_622sweep_driver.py` did with `float_shares_fmp_now`); (d) unknown.
`float_source` is carried on every row. **Era rule:** the stored-float era starts at the first scan date from which ≥ 90% of that
date's deduped scored rows carry a stored float on every later date too (read from `CENSUS_SCORED_BY_DATE`; expected 08-29).
- **Drift, and its direction.** Float moves slowly except through offerings, lock-up expiries and splits. A name that ran after the
  alert often raised equity after the run, so its `yf_now` float is LARGER than at the alert: the flag under-counts low-float
  winners and biases the pooled read AGAINST float. Consequence for the bars (§5.4): a pooled PASS survives the bias; a pooled
  NULL or BACKWARDS is reported as such only if the stored-float-only sensitivity does not point the other way.
- **Fetch tiers** (`50_fetch_lists.sql`): **Tier A** = Population A (8 EPs + their scored rivals), mandatory for the labelled read
  of float. **Tier B** = the rest of B with no stored float, recommended: without it the float tail leg is only the stored-era rows
  (~130) and is declared NOT POWERED by §11 C2, which is a stated limit, not a null.

### 5.3 Strata (float is read CONDITIONAL on liquidity)
Because the score already pays liquidity (up to +15) and float correlates with it, the float effect is read **within ADV$ strata**:
ADV$ = mean(close × volume) over the 20 sessions before the gap day, from bars; strata = the live liquidity ladder's rungs
[0,$50M) · [$50M,$100M) · [$100M,$250M) · [$250M,$500M) · [$500M,∞); a stratum with < 15 rows merges into the next lower one.

### 5.4 Float bars
Leg T statistic = the stratified risk difference of §7.1 with groups lowfloat vs not-low. Verdict words as §8.1. Additional rules:
- A **pooled** (stored + `yf_now`) read counts toward PASS/LEAD only if the **stored-only** read has RD ≥ 0 or is NOT POWERED.
- A pooled NULL or BACKWARDS becomes **CAN'T TELL (drift)** if the stored-only read has RD > 0 with one-sided p ≤ 0.10.

### 5.5 The counterfactual and the keep/drop rule (pre-registered)
**Era note.** The float rule (5 raw points, 50M cut) is identical on the legacy and the separation tables, so pooling the
ATTRIBUTE read across score eras is legitimate; only the counterfactual below is era-B-only (the stored parts and bar exist only there).
**Counterfactual (era rows only: stored `score_breakdown` and `ep_bar`).** For each deduped scored row: `raw` = sum of the stored
parts; the regime multiplier is worked back exactly as `ep_score_math.score_math_lines` does (`final = round((ep_score − 15)/1.25, 1)`,
`mult = final/raw`); `need` = the smallest whole raw total that presents ≥ `ep_bar` (`ep_score_math._raw_needed`, a search, not an
inversion); the conviction-floor part is re-resolved with `ep_rubric.resolve_conviction_floor(gap_pct, catalyst_quality)` when
the float points are removed. **Calibration first (§11 C5):** the factual rebuild must reproduce the stored `ep_score` within 0.05
on ≥ 99% of era rows, or the counterfactual is withheld. **N_flip** = rows that clear the bar with float and would not without it.
Reported: N_flip, how many of those were HIGH-alerted, how many ran; the same count one tier down for context.
**Rule:**
- **KEEP-rec** if the float verdict is SEPARATES or TAIL-ONLY.
- **DROP-rec** if the float verdict is BACKWARDS, or NULL with **N_flip ≥ 3** (the +5 is unsupported AND it is changing who is
  alerted). Precedent: #533 Changes 1–2 deleted the momentum penalty (AUC 0.52) and neglect on a null.
- **NO-REC** otherwise (CONFLICT, LABEL-ONLY, CAN'T TELL, NOT POWERED, or a NULL with N_flip < 3 = inert in the stored window).
The recommendation is the operator's to accept; a null here cannot exclude an effect below the MDE printed by §11 C2.

## 6. NEGLECT definitions (exact computations; every one reads bars with `trade_date < scan_date` only)

Notation: sessions k = 1..N counted backwards from the session before the gap day (k = 1 is D−1); `c`, `v`, `h`, `l` = close,
volume, high, low. Orientation fixes which side is "favourable" (more neglect).

| Def | Computation | Favourable | Role |
|---|---|---|---|
| **NP** price neglect | `maxrally_504` = max over j of (c_j / min(c_i, i ≤ j) − 1) × 100 across the 504 sessions before D (largest close-to-close rise from any prior low) | LOWER | **verdict** |
| NP-s1 | `maxrally_504 / (ADR20% )`, ADR20% = mean((h−l)/c)×100 over 20 sessions before D (volatility-normalised twin) | LOWER | must agree in sign (§8.1) |
| NP-s2 | `sess_since_rally50` = sessions since the last day j with c_j ≥ 1.5 × min(c over j−59..j); 504 if none | HIGHER | must agree in sign |
| **NV** volume neglect | `share_below_mean_250` = share of the last 250 sessions with v < the stock's own mean volume over the 504 sessions | HIGHER | **verdict** |
| NV-s | `vol_dryup_60_504` = median(v, last 60) ÷ median(v, last 504) | LOWER | must agree in sign |
| **NA** attention neglect (a PROXY) | `n_event_days_250` = count of the last 250 sessions that were an ATTENTION EVENT: v_s ≥ 3 × the median volume of the 60 sessions before s AND |c_s/c_{s−1} − 1| ≥ 5% | LOWER | **verdict** |
| NA-s | `sess_since_event` within 504 (504 if none) | HIGHER | must agree in sign |

NA is named a proxy because no headline history is stored (§4 row 5): a volume-and-price event is what news looks like in bars;
an unscheduled filing with no reaction is invisible to it, and a mechanical spike (index rebalance) is screened only by the 5% move.
**Descriptive only, no verdict (printed beside the verdicts):** D1 the stored `setup_class = 'episodic_neglect'` share (alerted
rows); D2 `expct_scheduled = 'unscheduled'` share (alerted rows); D3 RS rank at D−1 and sessions in the bottom 30% of RS over the
prior 120 sessions (Population A only, `RS_HIST_LABELLED`); D4 `num_analysts_eps`, binned within market-cap terciles (rows with a
stored estimate only); D5 the Qullamaggie combination — NP-favourable AND gap-day volume ≥ 5× its own 50-day average — counted
for the 8 EPs vs their rivals; D6 float F2/F3.
The external reads X1–X3 (float, analyst events, headlines) are specified in §9; they carry no verdict unless §9 says so.

Split guard: a window is excluded when `mi_splits` holds a split inside it with `adjustment_applied = false` or
`adjustment_outcome in ('phantom','skipped_no_data')`. A large single-day price move is NOT used as a split test: a prior +60% day
is exactly the attention event NA counts, and excluding it would select for neglect.

## 7. Statistics (identical machinery for F1, NP, NV, NA)

### 7.1 Leg T — the tail (Population B)
- **Groups.** F1: lowfloat vs not-low. Neglect: the **favourable third** vs the rest, cut WITHIN each ADV$ stratum on the feature
  oriented so higher = more favourable; a row is favourable iff its average rank (ties share) ÷ n_stratum ≥ 2/3. Cuts depend
  only on features (outcome-blind) and are frozen at STEP 2, before any outcome is attached.
- **Statistic.** Mantel–Haenszel stratified risk difference of the RUNNER rate, `RD = Σ w_s·RD_s / Σ w_s`, `w_s = n1_s·n0_s/n_s`
  (strata missing a group get no weight). Also printed: the unstratified RD, the P90 excursion difference, ≥ 8 ADR and ≥ +50% rates.
- **p.** One-sided permutation: shuffle the favourable flag within strata, 20,000 draws, seed 714,
  `p = (1 + #{RD_perm ≥ RD_obs}) / 20,001`; `p_rev` the same in the other direction. A 90% bootstrap interval (2,000 stratified
  draws) is printed for context and decides nothing.
- **Robustness (all part of PASS):** the RD is > 0 in at least 2 of the 3 blocks B1–B3 with the frozen strata and cuts; and
  > 0 after dropping the single scan date that contributes the most runners (the 04-08 lesson).

### 7.2 Leg L — his labelled EPs (Population A)
For each EP, orient the feature so higher = more favourable (F1: the continuous `−log10(float_shares)` — the live binary flag
would only add ties; NP/NV/NA per §6). **Percentile** =
(#rivals R1 with a less favourable value + 0.5 × #ties) ÷ #rivals on its board. Reported: each EP's percentile, the **mean**, and
**k of n_eligible above 0.5** (thin boards and EPs lacking a value excluded and counted). The 90% chance band for the mean of
eight uniform percentiles is ≈ 0.33–0.67 (sd ≈ 0.10), recomputed in Stage 2 from the actual board sizes by 20,000 draws. ABNB/TEAM
share a board, so the sign count is nominal.
- **L+** (favourable): mean ≥ 0.65 AND ≥ 75% of eligible EPs above 0.5, with n_eligible ≥ 5.
- **L−** (backwards): mean ≤ 0.35 AND ≥ 75% of eligible EPs below 0.5.
- **L0** (null): mean in [0.40, 0.60] and neither L+ nor L−. **L?**: anything else. **NOT READ**: n_eligible < 5.
- Sensitivity: the same on R2 and R3. A primary L+ becomes L? if either R2 or R3 reads L−.

## 8. Bars, verdict words, multiplicity

### 8.1 Leg T verdict (per definition)
| Word | Rule (all must hold) |
|---|---|
| **PASS** | RD ≥ **+6.0 pp** AND p ≤ **0.0125** AND ≥ 2 of 3 blocks RD > 0 AND drop-top-day RD > 0 AND each encoding listed as "must agree" (§6) has RD > 0 (F1: §5.4) |
| **LEAD** | RD > 0 AND p ≤ 0.05, not PASS |
| **BACKWARDS** | RD ≤ **−3.0 pp** AND p_rev ≤ 0.05 |
| **NULL** | none of the above, and the definition is POWERED (§11 C2) |
| **NOT POWERED** | the planted +10 pp effect is recovered as PASS in < 80% of simulations at this row count (decided BEFORE outcomes are attached) |
| **NOT MEASURED** | the feature is non-null on < 85% of the rows that meet the history rule (§11 C1) |
| **CAN'T TELL (drift)** | F1 only: a pooled NULL/BACKWARDS contradicted by the stored-only read (§5.4); treated as NOT POWERED in §8.2 |

The bars were set from the sampling spread, not from a wish: with n ≈ 800 and ~15% runners the standard error of an RD is ≈ 2.7–3 pp,
so +6 pp at α = 0.0125 is the smallest effect with roughly even odds of being found (MDE ≈ 6 pp at 50% power, ≈ 8–9 pp at 80%,
re-simulated at the actual n in C2).

### 8.2 Combined verdict (Leg T × Leg L)
| Leg T \ Leg L | **L+** | **L0 / L? / NOT READ** | **L−** |
|---|---|---|---|
| **PASS / LEAD** | **SEPARATES** | **TAIL-ONLY** | **CONFLICT** |
| **NULL** | **LABEL-ONLY** | **NULL** | NULL (leans backwards) |
| **BACKWARDS** | CONFLICT | **BACKWARDS** | BACKWARDS |
| NOT POWERED / NOT MEASURED | LABEL-ONLY (unconfirmed) | NOT POWERED / NOT MEASURED | NOT POWERED / NOT MEASURED |

Only **SEPARATES** (and TAIL-ONLY on a PASS) reaches him as "a lead worth a CHANGE_PROCESS look"; everything else is "not
supported". Descriptive rows (D1–D6, X1–X3) carry no verdict word.

### 8.3 Multiplicity, counted in advance
Verdict-bearing definitions: **F1, NP, NV, NA = 4**, each read on 2 legs. Leg T uses α = 0.05/4 = 0.0125 for PASS; LEAD is nominal
and labelled so. Secondary encodings (NP-s1/s2, NV-s, NA-s) add NO verdict — they can only demote a PASS. Leg L bars are fixed
thresholds on n = 8 and are not corrected (they cannot be, at this n); that is why Leg L alone never yields SEPARATES.

## 9. Stage 1b externals (not SQL, not prod; optional except X1 Tier A; a missing read is NOT a null)
- **X1 float.** yfinance `Ticker.info['floatShares']` — the field the live score reads — for the `50_fetch_lists.sql` tiers. A
  ticker that returns nothing is *unknown*, never 0; smoke-test 3 names first; record the fetch date on every value. Pacing: the
  repo's own yfinance jobs sleep 24 s between tickers (`analyst_estimates_recorder.YFINANCE_PACE_SECONDS`); Tier A is ~70–100
  tickers, Tier B up to ~400 — the main loop chooses the pace against the vendor's tolerance.
- **X2 analyst rating events (his 10-11 corollary: no / slowing upgrades).** `collector.get_recent_upgrade_events(ticker)` for Tier A
  tickers (`None` = fetch failed ≠ `[]` = no events on file; same handling as the #332 probe). Per (ticker, D): `n_events_365` (events in
  D−365..D−1), `n_up_90` (action `up` in D−90..D−1), `n_up_prior` (action `up` in D−365..D−91, as a per-90-day rate); favourable =
  fewer events and no upgrade in the last 90 days. Caveats stated now: Yahoo's table is a CURRENT snapshot of dated events and thin
  for small caps, so "no events" can mean "no coverage" — the tiny-cap confound he named — hence the read is shown against R1 rivals
  inside market-cap bands only.
- **X3 headline counts.** Alpaca news API (the same API the live catalyst path calls): headlines in D−365..D−1 (the gap day
  excluded) and distinct headline days, Tier A only; favourable = LOWER. Smoke-test that a 365-day historical range returns.
- **Verdict ceiling.** X2 and X3 exist for Tier A only, so they read on Leg L alone and can never exceed "L+ = a lead for a wider
  pull"; they never produce SEPARATES. X1 feeds F1 (§5).
- **Named, not registered (no definition fixed here):** X4 fund counts (SEC EDGAR 13F); X5 financial neglect (EDGAR companyfacts,
  filing-date stamped revenue/net income; "flat then accelerating" needs its own registration). They appear in "still untried".

## 10. Fresh-block confirmation (conditional, one shot)
Scan dates **2026-10-12..10-30** (15 sessions; expected ≈ 80 rows, ≈ 12 runners). No study has read them; they are NOT in the main
pull (`20_tail_population.sql` stops at 10-09). Pulled by `60_fresh_block.sql`, which carries a hard date gate and refuses before
**2026-11-21** (the 15th session after 10-30 is 11-20; its bar lands that evening). Read ONLY for a definition that reached
PASS/LEAD on the main window and is not L−, with the SAME code and the strata/cut points FROZEN from the main window (no
re-fitting). **Confirmed** = RD > 0 and one-sided p ≤ 0.10; otherwise "not confirmed on the fresh block". At n ≈ 80 this block
can contradict a lead but cannot establish one; it is reported exactly that way.

## 11. Checks that make a null mean something

What would a BROKEN pipeline print? The same table as a real null. These checks make the two distinguishable BEFORE any verdict:
- **C0 Look-ahead assertion.** Every feature asserts `max(trade_date used) < scan_date`; the count of rows checked is printed.
- **C1 Coverage floor.** A definition reports NOT MEASURED if its feature is non-null on < 85% of eligible rows; the census prints
  each EP's `n_hist_bars` and high/low gaps.
- **C2 Planted effect and size (run before outcomes).** On the real strata and row counts, 200 simulations each: (i) runner flags
  drawn at the observed base rate with a planted +10 pp for the favourable group must read PASS in ≥ 80% (else NOT POWERED); (ii)
  planted 0 pp must read PASS in ≤ 3% (the registered size). The same simulation prints the real MDE at 50% and 80% power.
- **C3 Outcome bridge.** Bar-derived gap-day close equals `mi_ep_scan_outcomes.baseline_close` on ≥ 95% of rows, and the bar-derived
  10-session forward close-to-close return matches `fwd_10d_pct` within 0.5 pp on ≥ 90%. Else every outcome number is withheld.
- **C4 Positive control for Leg L.** The 20-session ADV$ percentile of the 8 EPs among their R1 rivals must read ≥ 0.60 (the
  26-name #533 label gave AUC 0.72; member median $306M vs $100M). A reading below 0.50 means the board construction is suspect and
  every Leg L result is NOT READ, never a null.
- **C5 Float counterfactual calibration** (§5.5): ≥ 99% of era rows reproduce the stored `ep_score` within 0.05.
- **C6 STEP 0 composition printed before any outcome:** scored rows per date, float coverage per date, board sizes on the 7 labelled
  dates, rows per history-length band, split-flagged rows, rows with short forward windows, rows excluded per definition.

## 12. Order of computation and the table he gets (stage 2 spec)

1. **STEP 0** composition from the census and pulled files (no outcome read). Stop conditions: any `CENSUS_SCHEMA_CHECK` missing
   column; fewer than 7 distinct labelled boards present; SPY not loaded through 2026-10-30 (the tail end then moves earlier and is
   re-derived, never hard-coded).
2. **STEP 1** features for every row (bars strictly before the gap day) — NO forward bar, NO `fwd_*_pct`, NO `mi_ep_scan_outcomes` column read.
3. **STEP 2** freeze strata, cuts and the F1 groups; run C2 (simulated flags only) and print each definition's n and MDE — no real
   runner count is printed yet; run C4 and C5.
4. **STEP 3** outcomes attached (frame A) and C3.
5. **STEP 4** each definition read ONCE: Leg T, Leg L, verdict word, combined verdict. No re-run; a re-run for a defect is disclosed with the reason.
6. **STEP 5** the table, then the float counterfactual and the keep/drop line.

**The results table to him (one table, plain words):** one row per F1, NP, NV, NA — columns: the tail read first (runner rate
favourable vs rest, the gap in points, p, the big-winner P90 gap), then his EPs (mean place among same-day rivals, k of n), the
combined word, and one plain line of meaning; then the float line (separation, tail effect, alerts that exist only because of the
+5, KEEP/DROP/NO-REC); then D1–D6 as context; then **"still untried"**: coverage, analyst-upgrade pace, headlines, fund ownership,
financial neglect — each with its source and whether it ran.

## 13. What this cannot answer (stated before the data)
- **Float at the time** for the 6 pre-08-29 labelled EPs and most of B's early rows: only a 2026-11 snapshot exists (§5.2, drift
  direction stated). The stored-float era alone is ~130 rows — too few for a tail read.
- **Anything that needs headlines, upgrades, fund counts or multi-year financials** (§4 rows 5–9): not stored; the externals are
  optional and Tier-A only. NA is a bar-based PROXY for news silence.
- **Whether a separating feature converts to R.** Every number is separation and runner rate from the gap-day close, not P&L under
  our entry and stop. Selection quality and trading profit are different questions.
- **EPs the system never admitted** (7 of the 26 evidence-named fall under the 9% floor): Population A contains ABNB and CHPT
  only because he named them; boards are what the system logged, so a floor-blocked EP has no board at all.
- **Statistical power at n = 8:** 8 EPs on 7 boards; Leg L can show "not backwards", it cannot confirm. The ~800-row tail leg
  has ~100–140 runners: effects below ≈ 6–9 pp are invisible, and "none held" would mean none held here (as in #686).
- **Label noise:** rivals include unlabelled real EPs and big winners (he has not named every EP); this blurs, never inflates, Leg L.

## 14. Capture files, run order and freeze record

Run from `/Users/alvinfung/apollo_the_wise/scripts/probes/_714_study_1031` (`mkdir -p out`); every file begins
`SET default_transaction_read_only = on;`; output is `psql -A -F "|"`, sections start at `=== NAME`:
```
H=apollo@87.99.134.162
P='docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|" -v ON_ERROR_STOP=1'
ssh $H "$P" < capture/00_census.sql              > out/00_census.out              2> out/00_census.err      # FIRST
ssh $H "$P" < capture/10_labelled_and_rivals.sql > out/10_labelled_and_rivals.out 2> out/10.err
ssh $H "$P" < capture/20_tail_population.sql     > out/20_tail_population.out     2> out/20.err
ssh $H "$P" < capture/30_daily_bars.sql 2> out/30.err | gzip > out/30_daily_bars.out.gz
ssh $H "$P" < capture/40_context.sql             > out/40_context.out             2> out/40.err
ssh $H "$P" < capture/50_fetch_lists.sql         > out/50_fetch_lists.out         2> out/50.err
# 60_fresh_block.sql: ONLY on/after 2026-11-21 (it refuses earlier), then gzip its FRESH_BARS section
```
`out/` is local and large (`30_` roughly 10–25 MB gzipped, an estimate from ~650 tickers × ~1,250 sessions); do not commit it.

| File | Sections | Why |
|---|---|---|
| `00_census.sql` | scored rows + float coverage per date, labelled presence, board sizes, bars freshness, RS/analyst/split coverage, schema check (wanted vs found) | STEP 0, float era, power |
| `10_labelled_and_rivals.sql` | every tick of the 8 EPs; every LOGGED ticker on the 7 boards (R1/R2/R3) | Population A |
| `20_tail_population.sql` | `POP_B`: the #686 column shape + float, score parts, alert/judge, `expct_*`, stored outcomes (not opened until STEP 3) | Population B |
| `30_daily_bars.sql` | bars from 2021-01-01 for A∪B∪SPY/QQQ/IWM; from 2024-01-01 for logged-only rivals | every feature and outcome |
| `40_context.sql` | regime, RS at D−1, RS history (A), analyst as-of, splits | D3, D4, split guard |
| `50_fetch_lists.sql` | Tier A / Tier B float fetch lists, counts | Stage 1b |
| `60_fresh_block.sql` | the fresh block (gated) | §10 |

Verification before freeze: each file parses with `sqlglot` (Postgres dialect) and every section ran to completion against a
synthetic DuckDB schema built from the column names in `agents/market_intelligence/db.py` (binding errors only; Postgres
semantics were not exercised, and no production read was possible from the writing session).

SHA-256 of the capture files at freeze (stage 2 refuses to run if any differs):
```
165e69954bc5070961f6e2e08f12ab5aa6894438b52589575f4c5efc5aaea597  00_census.sql
6d8dc93c3ea5a61f4a534d4b2643ac3672c6043aecd70692585b0cd7e7a62ab8  10_labelled_and_rivals.sql
bdd31824635e40e5d6b1410b7ab44bbb4481e5bdab80d99da6b532015ee78fcf  20_tail_population.sql
8f550146140cffcaf39923095e3d908550e0293960eef416271bc8ce53429fbc  30_daily_bars.sql
a2305689d9d911e881029370b4fc0f455b315caad626d9b740c8a4032f1075b0  40_context.sql
b7267a943639dcfd9724f9cd9331514cc625c9428f85a9b7ddd542cbb22462e5  50_fetch_lists.sql
3b494b3ccd3b240552b61a669599a9fb78271ea76fa373b4b5b86758731d8060  60_fresh_block.sql
```

**FREEZE — 2026-10-31 PT. Everything above this line is fixed before any capture output is read. Any later change is a dated
addendum BELOW this line, labelled post-freeze, and cannot alter a definition, a bar or a verdict word above.**

---

## POST-FREEZE ADDENDUM 1 — 2026-10-31 PT (stage 2, written BEFORE the read, labelled post-freeze) — C3b was mis-specified

Nothing above the freeze line is edited. This addendum records a defect in ONE calibration check and how it was handled; it changes
no hypothesis definition, no stratum or cut, no outcome frame, no verdict bar and no verdict word.

- **What failed.** Stage 2 STEP 3, first attempt (printout kept as `scripts/probes/_714_study_1031/s2_step3_first_attempt_printout.txt`):
  C3a (bar gap-day close = `mi_ep_scan_outcomes.baseline_close`) read **100.0% of 798** (bar 95%, passes). C3b as registered (§11: "the
  bar-derived 10-session forward close-to-close return matches `fwd_10d_pct` within 0.5 pp on ≥ 90%") read **2.0% of 797**.
- **Cause, from the code, not from the data pattern.** `agents/market_intelligence/outcome_tracker.py::_compute_ep_scan_outcomes`
  (the writer of `mi_ep_scan_outcomes`) documents and implements `fwd_5d_pct` / `fwd_10d_pct` as **high-watermark returns**:
  `(MAX(high) over the first n_sessions forward sessions − baseline_close) / baseline_close`, "Uses MAX(high) over forward sessions vs
  scan_date close". The registration described the column as a close-to-close return — a registration error (stage 1 assumed the
  column's meaning without reading its writer). Confirmed on the data: the bar-derived max-high matches the stored column on 99.1% of
  rows (median absolute difference 0.00); no close-to-close variant exceeds 2.6% (`scripts/probes/_714_study_1031/c3_diag.py`).
- **Disposition (a bug in a check, not a change of criteria).** C3b is restated on the column's own definition — max HIGH over the first
  `n_sessions_10d` forward sessions vs the gap-day close, within 0.5 pp on ≥ 90% — and THAT form gates. The registered form is still
  printed, labelled mis-specified. This is a STRONGER bridge than the registered one: it validates the very high-watermark construction
  that frame A (§3) uses for the runner label. The 95% / 90% bars are unchanged. **The freeze text forbids an addendum from altering a
  "definition, bar or verdict word"; C3b's comparator is a check definition, so the main loop / operator should ratify this correction.
  If it is not ratified, treat every outcome-dependent number from this stage-2 run as withheld (§11 C3).**
- **Disclosure of a sequencing slip.** The first STEP 3 attempt printed the overall runner counts BEFORE the C3 gate fired (a code-order
  defect, fixed): 86 of 797 rows ran ≥ 5 ADR (10.8%; by block B1 49/327, B2 19/296, B3 18/174), 28 reached ≥ 8 ADR, 30 reached ≥ +50%,
  P90 of the max excursion 32.2%. These are overall counts, not split by any float or neglect feature; no feature-by-outcome table had
  been computed or seen. `s2_step2_printout.txt` (STEP 0-2: frames, strata, groups, cuts, C1, C2, C4, C5) was saved before any outcome
  was attached and is diffed against the rerun's STEP 2 block before STEP 4 is read.
- **Capture notes (not defects of the study).** `50_fetch_lists.sql` FETCH_COUNTS under-counts Tier B (printed 77; the FETCH_B list
  holds 655 rows / 541 distinct tickers, 464 beyond Tier A): its `ticks` CTE is restricted to the labelled boards. The lists themselves
  are correct and all 541 were fetched. `ANALYST_ASOF` returned no stored `num_analysts_eps` for any row (D4 is therefore not measurable
  from this capture).

## POST-FREEZE ADDENDUM 2 — 2026-10-31 PT (stage 2, written AFTER the read) — what was filled in or added, all labelled post-hoc

Results: `scripts/probes/_714_study_1031/RESULTS.md`. The read was run once (`s2_read_printout.txt`) after the C3b correction of Addendum 1;
the only rerun was that one. Nothing above the freeze line was changed. Items below are gap-fills where the frozen text was silent, or additions:

- **Strata (§5.3).** The <15-row merge is applied to each analysis set's OWN rows (float pooled, float stored-only, neglect set), top rung
  downward into the next lower rung. A lowest rung that is still short would merge UP (the text is silent; it never triggered). One B row has no
  20-session dollar volume and is in no frame; 5 rows have no float; 1 row is censored (short forward window) and is dropped from every tail read.
- **C2 (§11).** Base rate = the registered 15% (the real rate was not read before STEP 3). The plant keeps the OVERALL rate at the base rate
  (rest = base − effect × share favourable). 200 simulations per cell, 2,000 inner permutation draws (the verdict uses 20,000), effect swept 0-15 pp
  in 1 pp steps, seed 714. "Must-agree" encodings are not simulated, so power is a slight upper bound. Float pooled read POWERED at exactly 80.0%
  (160 of 200) — on the line. Re-run at the observed 10.8% rate (post-hoc, decides nothing): all four powered, stored-only still not.
- **Permutation test (§7.1).** Implemented as exact hypergeometric draws of the runner count in the favourable group within each stratum — the same
  distribution as shuffling the flag within strata, and exact. Bootstrap = 2,000 stratified resamples.
- **Verdict-word precedence (§8.1).** NOT MEASURED first; then PASS, LEAD, BACKWARDS; then NULL (if powered) or NOT POWERED. A powered/unpowered flag
  never overrides a detection. "CAN'T TELL (drift)" fired for float: pooled NULL with a stored-only gap of +11.0 pp, one-sided p 0.059 (§5.4).
- **Leg L (§7.2).** Thin board = fewer than 4 rivals with a valid value (BFLY is thin for neglect: 3 of 4 rivals have 504 sessions of history; PENG is
  thin for everything: 1 rival). Place counts ties at 0.5. Chance band = 20,000 draws of a uniform rank per readable EP. R3 = R1 rivals with a PASS tick
  (`any_pass_tick`). R2 float reads use only rivals with a float, i.e. mostly the scored rivals. "Above 0.5" is strict (BFLY, exactly 0.5, counts as neither).
- **Neglect conventions (§6).** Windows are the last 504 / 250 / 60 / 20 SPY-calendar sessions before the gap day; "sessions since" counts D−1 as 1; the
  rolling-minimum lookback of NP-s2 may reach before the 504 window; the NA volume median is the prior 60 sessions (≥45 non-null), shifted one day.
  No row was flagged by the split guard (the only unapplied splits are dated Nov-Dec 2026).
- **Float counterfactual (§5.5).** Float points set to 0, conviction floor re-resolved with `resolve_conviction_floor`, multiplier worked back from the
  stored score (1.0 on all 146 era rows: no Bull day in the window, so the ×1.2 branch is unexercised), bar 65. Rebuild matched 146/146; the
  conviction-floor part matched 146/146. The "one tier down" count is undefined (the separation table has no MODERATE cutline).
- **Descriptives.** D3 uses `rs_composite ≤ 30` as "bottom 30%" on weekday score rows (last 120). D4 not measurable (0 stored estimates). D5's
  NP-favourable cut is the per-stratum cut frozen on B; gap-day volume is read from the gap-day bar (a descriptive row, not a feature of any verdict).
- **External reads (§9).** X1: yfinance `floatShares` for 541 tickers (Tier A 77 + Tier B 464), 1 s pace, fetched 2026-10-31 20:08-20:19 UTC; VCX
  (a Tier A rival), AFYA, LION and NIQ returned no float (unknown, not 0); smoke test on PENG/MRNA/BFLY first. X2: `upgrades_downgrades` for the 86 Tier A
  tickers, fetched 20:28-20:30 UTC, bands from the scan-log market cap, else the `mi_market_caps` snapshot, else yfinance's current market cap (post-hoc
  fallback, a current value); NOT READ (4 of 8 EPs have ≥4 same-band rivals). X3 not run: no Alpaca credentials on this machine.
- **Stage-1 oversight on the stored-float era (§5.2, §13).** The plan called the stored-float era "too few rows" for a tail read. The binding constraint is
  the block rule: all 145 stored-float rows fall in B3, so "RD > 0 in at least 2 of 3 blocks" (§7.1) can never be met and C2 reads 0% at every planted
  effect. The stored-only read is therefore a nominal number that cannot confirm anything; §5.4's drift rule does not need it to be powered, so the verdict stands.
- **Post-hoc diagnostics (no verdict):** `c3_diag.py` (why C3b failed), `s2_f1_strata.py` (float gap by dollar-volume stratum: the stored-era +11.0 pp
  is carried by the under-$50M group, 6 of 35 vs 1 of 38).

### POST-FREEZE ADDENDUM 2026-10-31 (main loop) — the C3b correction RATIFIED

The stage-2 reader found check C3b mis-specified and ran a disclosed corrected comparator (see RESULTS.md). Ratified by the
main loop after checking the writer: `agents/market_intelligence/outcome_tracker.py::_compute_ep_scan_outcomes` computes
`fwd_10d_pct` as a HIGH-WATERMARK return (MAX(high) over the forward sessions against the scan-date close), not
close-to-close — so the registered comparator fails a CORRECT pipeline (2.0% agreement), and on the column's own
definition the bridge reads 99.9% of 798 (C3a 100.0%). No definition, bar or verdict word above changes. The results
stand as reported; his ruling 2026-10-31 ("Take all recs"): keep the float points for now (re-read 2026-11-21,
`float_points_stored_era_reread_714`), stop testing neglect with price / volume bars.

## What this does not answer (post-freeze addendum 2026-10-31, from the stage-2 read)

- Float AT THE TIME for 648 of 793 rows — only a 2026-10-31 snapshot exists for them; the stored-float era (145 rows,
  17 runners) is too small and sits in one time block, so it cannot confirm under the registered block rule.
- Whether his EPs separate: 5-7 readable EPs on 4-6 independent boards give chance bands of 0.27-0.73 / 0.30-0.70; the
  label leg alone can never read SEPARATES.
- Neglect beyond price bars: headlines, analyst-upgrade pace, coverage, fund ownership and multi-year financials were not
  available or not run; "attention neglect" is a bar-based proxy for "no news".
- Trading profit: every number is how often a name ran big from the alert-day close, not R under our entry and stop.
- EPs the system never admitted (no board exists for them), effects smaller than ~7-10 points, and the 10-12..10-30
  fresh block (date-gated to 2026-11-21, `float_points_stored_era_reread_714`).
