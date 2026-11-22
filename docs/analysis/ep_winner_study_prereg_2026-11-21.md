# EP big-winner chart study — what do the charts of EPs that became big winners share? (PRE-REGISTERED 2026-11-21, before any outcome is read)

**FROZEN v2 (committed 2026-11-21; draft history in `scripts/probes/_ep_winner_study_1121/design/`).** Written Sat 2026-11-21 PT from the outcome-free event
list only (every population count below was recounted from `ep_events_{A,B}.tsv.gz` columns for v2; no forward price was
read to write this). v2 resolves the adversarial critique (`design/critique.md`); see "Critique resolutions" at the end.
Spread numbers in §5.4 come from `design/spread_sim.py` → `spread_sim.txt` (synthetic labels only).

**Why.** His words 2026-11-21 (`docs/methodology/operator_shared_notes.md`): *"Qullamaggie suggests to review 1000s of charts to
find edge"* and *"we should keep testing this idea or other chart readings"*. The shelf-distance read (RESULT 8,
`ep_rank_v2_prereg_2026-11-03.md`) was one chart reading tested on the full history: real but modest (1.36x). This study
scales the same method to a pre-stated list of chart readings, then puts the strongest in front of his eye.

**What this is NOT.** Measurement only, $0, local files, no network / DB / paid API. No live change, no ranking change, no
entry or stop proposal (THE LINE: selection is his). **His eye is the judge; a chart feature only leans the odds**
(`charts-support-never-decide`). The tail is measured, never the median (`measure-the-tail-not-the-median`).

## 0. What is already known (disclosed, so nothing is re-run blind and prior looks are counted)
| Earlier read | Population | Target | What it found | Bearing here |
|---|---|---|---|---|
| RESULT 8 / PRE-REG 6 (`ep_rank_v2_prereg_2026-11-03.md`) | this same 2016-24 event list | big winner (+50% in 60 sessions) | shelf distance top vs bottom third 12.9% vs 9.6% = **1.36x**, p 0.0035; era A 1.48, era B 1.08 | **Outcomes for shelf distance, base rates per era and per year, and the short-history group's win rate have been SEEN on every year.** Shelf distance is therefore a benchmark here, outside the new-feature family. |
| #684 (`684_ep_runner_selection_2026-09-28.md`) | 604 live alerts, 2026 | runner = high within 15 sessions ≥ 5 daily ranges above the gap-day close | about 80 feature rows (pre-open, open, 09:44, close); none demonstrated; gap %, distance above the 20-day low, day range/ADR read the WRONG way; held-out block had 4 runners | Different population (2026 alerts, sealed years) and far smaller; these features are re-tested here on 2016-24, with direction left two-sided because of it. |
| #519 free step (`519_free_chart_read_2026-09-24.md`) | his 35 chart rulings + 30 labelled real EPs | his eye | only the run-up before the gap separated his condemned charts; base length, 50-day, local highs, dry-up, up/down volume each rejected real EPs | Target was his rulings, not the tail; the same reads are defined below against the tail. |
| `ep_synthesis_2026-08-18.md` | 2026 live book | mixed | recurring profile: modest gap, tight, little extension, MA-extension gradient | Gap size, extension and tightness are in the list for that reason. |
| RESULT 1-2 (`ep_rank_v2_prereg_2026-11-03.md`) | his rulings | his eye | zones cleared 0.67, EOD tightness 0.64, volume vs own year 0.62, pullbacks-held 0.51 | Gap-day range and gap-day volume are NOT knowable at 09:31, so they are excluded here (§4). |
| #533 within-day ranking (`533_within_day_ranking_2026-08-30.md`) | 141 live board rows, 2026 | 5-session move from the open | prior-day RS ranked best within a morning | RS vs SPY is in the list. |
| #714 (`ep_float_neglect_prereg_2026-10-31.md`) | his labelled EPs + the 2026 tail | his labels and the tail | the float points and neglect definitions | Float is not in the local daily files, not tested here; neglect is feature 7. |
| `ep_share_count_vs_rvol_2026-10-16.md` | 2026 alerts | runner | gap-day share count vs relative volume | Both use E's own volume — not knowable at 09:31, excluded (§4). |
| `structure_read_backtest_2026-08-25.md` | 2,787 scan name-days, 2026 | forward move | the supply-ladder (zones) read was liquidity class on labels and a coin flip forward (0.496) | Zones cleared scored best on his rulings (0.67, RESULT 1) but failed forward on 2026; re-tested on the 2016-24 tail as feature 20, with liquidity (19) beside it. |
| #705 (`cb_big_winner_recall_2026-10-22.md`) | 2017-24 big winners (breakout lens) | recall | which names were big winners was seen for the BREAKOUT study | Disclosed: names of 2017-24 big winners are not new to the repo; no EP feature was fitted on them. |
| #569 (`pregap_base_axes_2026-08-19.txt`, `pregap_base_v2_2026-08-20.txt`) | 749 tier-A gap days, 2026 | reach ≥ 8 daily ranges | pre-gap extension vs its own averages in daily-range units 11.7% vs 9.3%, p 0.55 (null); base length × quietness all p ≥ 0.08 | These are features **17 and 8** on a near-identical tail target. Re-tested here on 2016-24; the ADR-scaled tail (§2) is that study's target. |
| #331 (`331_gap_alignment_n3120_2026-09-09.md`) | 2026 alerts | forward move | gap open vs the 15-day base high and the trailing high: "the axis is wrong in SIGN" | That is feature **6** — one more reason every discovery test is two-sided. |
| `gap_floor_decision_table_2026-08-19.md` | ≥10R winners, 2026 | — | 15 of 25 gapped only 8.1-9.9% | Bears on feature **1**: the 9% population floor cuts off the small-gap end; stated in §8. |
| `545p2_missed_ep_tail_read_2026-09-02.md`, `ep_backtest_run1_2026-08-29.md` | 2026 | P&L | the tail is lost in conversion (entry and exit), not at the gates | Backs §8 "Money". |

**What has already been SEEN on the confirm years (2021-24) — the confirm set is out-of-time but NOT untouched:**
- shelf distance per year (2021 1.25 · 2022 era A 0.52 · 2023 0.95 · 2024 1.23), base rates per year and era, and the
  short-history group's win rate (RESULT 8);
- the outcomes of Qullamaggie's 62 EP buys by name (`run.txt`), and #705's big-winner names;
- **the split in §3 was chosen AFTER RESULT 8 showed shelf distance at 1.08 in era B.** The power argument for the split
  stands on its own, but it was made with that in view;
- any feature that measures much of what shelf distance measures inherits those seen outcomes — handled by the
  "shelf relative" tag and condition 5 of §5.2.

## 1. Population (fixed now; counts printed without outcomes)
- **Source:** every `primary == True` row of `ep_events_A.tsv.gz` / `ep_events_B.tsv.gz`
  (`/Users/alvinfung/apollo_data/cb702/qm_streams/ep_join_1023/`, built 10-23 by `scripts/probes/_705_ep_join_1023/01_ep_join.py`).
  An event = open(E) ≥ 1.09 × close(E−1), volume(E) ≥ 3 × the 20-session mean, raw close(E−1) ≥ $5, median 20-session dollar
  volume ≥ $10M, stock/ADR universe, no adjustment flag or identity break **on E or E−1**. **5,342 rows** (A 3,378, B 1,964).
- **Drops, in this order, each counted (the build asserts every number):**
  1. `flag_adj` / `flag_adj_Dm1`: **2**. These flags cover E and E−1 ONLY; splits, holes and symbol reuse inside a
     feature's lookback are handled per feature by the NULL rules of §4.0.
  2. Forward window (PRE-REG 6's R2, unchanged): era B E > 2024-09-30 → **270**; era A E > 2022-04-04 (no E+60 in the A file) → **95**.
  3. **Era overlap — the era-A file is the ONLY source for E ≤ 2022-04-04.** Every era-B event with E ≤ 2022-04-04 is
     dropped, twin or not → **310** (273 have a same-(ticker, E) era-A copy; 37 do not — the critique matched 19 of its 35
     to the same event under a LATER era-A symbol, e.g. DWAC→DJT, PTRA→PTRAQ, so a (ticker, E) twin key undercounts; the
     rest are vendor-volume near-misses or absent from era A). The era-A events of that span all stay.
  - **Study population: 4,665 events** (era A 3,281 · era B 1,384, era B's first E = 2022-04-05). 1,977 tickers,
    median 2 events per ticker, max 19.
- **Per year (era A / era B):** 2016 326/0 · 2017 378/0 · 2018 455/0 · 2019 484/0 · 2020 771/0 · 2021 707/0 · 2022 160/344 ·
  2023 0/527 · 2024 0/513. Security type: CS 3,541 · ADR 211 · untyped 913.
- **Bars — loader COPIED, not imported.** `scripts/probes/_594_outcome_qm_1121/build/run.py` runs its whole pipeline (and
  prints outcomes) at module level, so it must NOT be imported. The build copies its bar loader (the block that reads
  `DAILY[era]` in chunks, cuts era B at read, maps dates to the era calendar index `ci` and builds
  `bars[(era, ticker)] = (d, ci, o, h, l, c, v)`), its `CAL` / `DAILY` paths, `five_years_before` and `score_one`, with
  a comment citing the source lines; it loads ALL bars of every event ticker (not a slice). `f3_def.py` and
  `_533_nbis_structure_encoder.py` are loaded with `importlib` exactly as run.py's `_load` does (they are import-safe).
  **Eras are never stitched** (an era-A event reads only `cb702_pre_v2/daily_closes_all.csv.gz`, 2016-01-04 .. 2022-06-30; an
  era-B event only `cb702/daily_closes_all.csv.gz`, which starts 2021-09-27). **Sealed data (#710): every era-B row dated after
  2024-12-31 is dropped AT READ and asserted;** no file of 2025-26 outcomes is opened.
- **No survivorship drop** (RESULT 8's lesson): an event with fewer than 60 forward bars stays in; its window simply ends
  where its bars end (`_594 review/check.txt` (b): 148 such events, so the files do keep names that stopped trading).
  `scripts/probes/_594_outcome_qm_1121/build/events_scored.tsv.gz` (holds outcomes) is **never an input**; shelf
  distance is recomputed from bars.
- **Cross-era identity (for every ticker-keyed rule: one-per-ticker, the B-sheet exclusions).** The era-A file names
  tickers by a later symbol than era B. The build maps symbols across eras on the shared overlap 2021-09-27..2022-06-30,
  reading that span for ALL tickers of both daily files (a renamed counterpart need not be an event ticker; no row after
  2022-06-30 is needed). Era-A ticker a and era-B ticker b are the SAME identity when they share ≥ 40 sessions and their
  close-to-close returns agree within 0.002 on ≥ 90% of the shared consecutive-session pairs. (Returns, not price
  levels: a pilot on 21 large caps + 3 known renames, overlap bars only, read ≥ 0.995 on every true pair and 0.17 on
  AAPL-vs-MSFT; the level-ratio version failed IBM at 0.85 because of an adjustment step.) Candidates are found by
  hashing the first 10 shared returns rounded to 4 decimals, then tested in full. A same-symbol pair that fails is two
  identities (symbol reuse) and is printed, as are every rename (a ≠ b), any ticker matching more than one counterpart,
  and the three suspected mapping errors the critique named (LC→HAPN, PSTG→P, OSTK→NXH). The build asserts that
  DWAC→DJT, PTRA→PTRAQ and GPS→GAP are found. `identity` = the era-A symbol where mapped, else the event's own symbol.
- **Symbols that carry later status.** Every era-A event whose symbol is 5 letters ending in Q (a later bankruptcy
  marker) is printed. No feature reads the symbol; no sheet, key or file name shown to him may carry it.
- **Era-B volume underflow — a SUSPECTED survivorship leak the build must test before any outcome (outcome-free):**
  the era-B file holds 22,658 `zero_volume_underflow` rows; the suspected cause is volume divided by the factor of a
  LATER reverse split. The population's zero-free 20-session baseline would then remove names that later reverse-split
  (often losers, some after the 2024-12-31 cut).
  1. Mechanism test with IN-CUT inputs only (the split list's 2025-26 rows are sealed-year information and are not
     used for this): among era-B rows dated ≤ 2024-12-31, the share of zero-volume rows whose adjusted close is ≥ $1,000
     (a price only a later large reverse split produces) against the same share among all rows. Printed with both
     counts; a ratio ≥ 5 = "mechanism supported", else "not supported by this test".
  2. Copy `01_ep_join.py::wide_table`'s filter lines, assert they reproduce 1,964 era-B primaries, then count the
     era-B days that pass gap ≥ 9%, raw price, liquidity, type, 20 consecutive sessions, and volume(E) ≥ 3 × the mean of
     the NON-ZERO sessions of the baseline, but were excluded only because the baseline holds a zero. If that count
     exceeds **1% of the 1,964 era-B primaries (i.e. > 20)**, every era-B result line carries the tag **"era-B population thinned of later
     reverse-splitters"**. They are counted, not added to the population.

## 2. Outcomes (entry proxy = open of E, as PRE-REG 6)
- **PRIMARY — big winner (PRE-REG 6's, unchanged):** the highest close over the era calendar's sessions E..E+60 ≥ **1.5 ×** open(E).
  **The window includes E's own close** (an open-to-close run on the gap day counts); E's close is an outcome, never a feature.
- **MONSTER tier (stricter, same window):** highest close over E..E+60 ≥ **2.0 ×** open(E). Reported for every feature beside
  the primary; **never a bar**; printed with "thin" when the set under test holds fewer than 60 monsters.
- **ADR-SCALED TAIL (the #569 house target; description + one tag, never a carry bar):** highest close over E..E+60 ≥
  open(E) × (1 + 8 × ADR20/100). Its tercile ratio is printed beside the primary for every carried feature and read.
- **"Failed" (description only):** close(E+5) < open(E), and the 60-session return close(E+60)/open(E) − 1 (mean, never
  a verdict). **Gallery failure pool (§7A):** highest close over E..E+60 < 1.10 × open(E).
- **Volatility control (a fixed +50% is easier for a volatile stock):** ADR20 (the encoder's `adr20_pct`, the 20 bars
  before E) is a **benchmark, not a candidate**. **ADR-neutral reading:** terciles of the feature formed within
  (era, calendar quarter, ADR20 third of that era-quarter), strata with ≥ 9 scored events, pooled as §5.1. Two separate
  bars use it, each on its own set:
  - DISCOVERY carry floor (§5.2 condition 4): ADR-neutral ratio ≥ 1.15 in the carried direction;
  - CONFIRM tag: a feature or read carries the suffix **"— a volatility proxy"** when its CONFIRM ADR-neutral ratio
    is under 1.2 **or** its CONFIRM ratio on the ADR-scaled tail is under 1.10 (carried direction). A tag, not a verdict change.

## 3. DISCOVERY / CONFIRM split (fixed now, by event date)
| Set | Rule | Events | With ≥ 130 bars of history | (era, month) groups with ≥ 6 such events | Untyped |
|---|---|---|---|---|---|
| **DISCOVERY** | E ≤ 2020-12-31 (era A only) | **2,414** | 2,195 | 54 | 680 |
| **CONFIRM** | E ≥ 2021-01-01 (era A to 2022-04-04, era B from 2022-04-05) | **2,251** (A 867 · B 1,384) | 2,178 | 45 | 233 |
- **Why not era A discover / era B confirm:** era B alone is ~1,380 events; too few for a corrected test (§5.4).
  Disclosed in §0: the choice was made after seeing shelf distance fade in era B.
- **Confirm is out-of-time** and contains both eras, always printed per era beside the pooled number. The 250/252-session
  features (5, 16, 20, B1) have no era-B event before ~2022-09-26 (the B file starts 2021-09-27), so their confirm is
  mostly 2021 era A + 2023-24 era B; the 120-session ones are covered from era B's first event: **confirm n per feature per era is printed BEFORE the confirm read.**
- **Known weaknesses, stated:** (a) discovery winners are concentrated in 2020 — handled by the ex-2020 condition in
  §5.2, which is a weak guard (§5.4); (b) the forward windows of Oct-Dec 2020 discovery events overlap the first confirm
  months, and one identity can appear in both sets — the one-per-identity reading (§5.5) covers it; (c) the confirm
  years are partly seen (§0); (d) the sealed 2025-26 years stay sealed.

## 4. The candidate chart features (20 in 9 groups, exact; ALL knowable at the 09:31 entry)
### 4.0 Rules for every feature
- **Inputs:** the ticker's own daily bars dated **before E** plus **open(E)** only. Never E's high, low, close or
  volume. `vol_E`, `vr20_*`, `vr50_mean` and their flags use E's full-day volume and are **excluded as features**.
- **No adjusted price LEVEL is ever a feature** (it encodes later reverse splits); adjusted prices are used only in
  ratios within one ticker. Feature 18 uses the raw price.
- **Windows are CALENDAR sessions, not rows.** "E−n..E−1" = the era calendar indices ci(E)−n .. ci(E)−1; the feature
  uses the ticker's bars present in that window. "g−1" inside a feature = the ticker's bar on the previous calendar
  session (absent → that g is skipped).
- **NULL rules (each NULL carries ONE reason, first match; counts printed per feature × era × year × reason):**
  1. `history` — the ticker's first bar is later than session ci(E)−n (or ci(E)−n < 0);
  2. `coverage` — bars present in the window ÷ n < 0.90;
  3. `adjustment` — the window holds a (ticker, date) of klass `known_adjustment_event` or
     `discontinuous_across_known_adjustment` (the flag files `01_ep_join.py` loads: `FILES["flags_A"]`,
     `FILES["flags_B"]`, era B cut at 2024-12-31);
  4. `identity` — the window holds an identity-break date of the symbol guard (`symbol_guard_{A,B}.tsv`, parsed as
     `01_ep_join.py` does);
  5. `zero_volume` (features 12, 13 only) — the window holds a bar with volume 0 (never read a zero as a dry-up);
  6. a feature-specific reason named in the table.
  For features 20 and B1-clean the "window" for rules 3-4 is the whole 5-calendar-year slice the encoder reads.
- `ADR20` = `_533_nbis_structure_encoder.adr20_pct` on the 20 bars before E (the population guarantees those 20
  sessions are consecutive).

### 4.1 The list
| # | Name | Exact definition | Window n (sessions) | Prior read |
|---|---|---|---|---|
| 1 | Gap size, % | open(E) / close(E−1) − 1 | 1 | #684 wrong way (2026); #519 no separation; gap-floor table |
| 2 | Gap size, in daily ranges | feature 1 × 100 / ADR20 | 20 | synthesis: "modest gap" |
| 3 | Short run-up | close(E−1) / lowest low of E−20..E−1 − 1 | 20 | #519: the one read that matched his eye; #684 reverse |
| 4 | Long run-up | close(E−1) / lowest low of E−120..E−1 − 1 | 120 | new on the tail |
| 5 | Below the 52-week high | close(E−1) / highest high of E−252..E−1 − 1 | 252 | #684 no (2026) |
| 6 | Open vs the 6-month high | open(E) / highest high of E−120..E−1 − 1 (above 0 = the gap clears it) | 120 | #684 no; #519 R3; #331 wrong sign |
| 7 | Sessions since the 6-month high | ci(E)−1 minus the ci of the highest high of E−120..E−1 (latest on ties) | 120 | #684 neglect: no |
| 8 | Flat-base length | the largest n ≤ 120 such that max close / min close − 1 ≤ 15% over the bars present in E−n..E−1 | 120 | #519: 19 vs 2 sessions; #569 null |
| 9 | Base depth | 1 − lowest low / highest high over E−40..E−1 | 40 | new on the tail |
| 10 | Range tightening | mean (high−low)/close of E−10..E−1 ÷ the same mean of E−60..E−11 (under 1 = tightening) | 60 | his tightness (11-03), pre-gap version |
| 11 | Closing tightness | (max close − min close) / mean close over E−10..E−1, × 100 / ADR20 | 20 | his ANDG read 11-17 |
| 12 | Volume dry-up | mean volume E−10..E−1 ÷ mean volume E−60..E−11 (under 1 = dry-up) | 60 | #519 R6 rejected real EPs |
| 13 | Up vs down volume | volume summed on sessions closing up ÷ on sessions closing down, E−20..E−1 (vs the prior session's close; uses the bar at E−21) | 21 | #519 R4 |
| 14 | Strength vs SPY | [close(E−1)/close(E−61)] ÷ [SPY close(E−1)/SPY close(E−61)] − 1, SPY from the same era file at the same two calendar sessions; no ticker bar at session E−61 → the latest bar within the 5 sessions before it, else NULL | 61 | #533: prior-day RS ranked best within a morning |
| 15 | Earlier gap-ups (two groups) | any session g in E−120..E−1 with open(g) ≥ 1.05 × close(g−1): yes / no | 120 | new |
| 16 | Unfilled gap-down overhead (two groups) | yes when a session g in E−250..E−1 has open(g) ≤ 0.90 × close(g−1), no high from g..E−1 reached close(g−1), and open(E) < close(g−1) | 250 | his ASPN read: "failed to clear a major gap down" |
| 17 | Distance from the 50-day average, in daily ranges | (close(E−1) / mean close E−50..E−1 − 1) × 100 / ADR20 | 50 | synthesis gradient; #684 wrong way; #569 null |
| 18 | Price | `prev_close_raw` from the event list (unadjusted) | 1 | #684 price bands, description |
| 19 | Liquidity | `med_dv20` from the event list (median of adjusted close × adjusted volume, so splits cancel) | 20 | shortlist pre-score (08-22) |
| 20 | Qualified levels cleared by the open | `nbis.encode(ticker, E, {ticker: slice5}, {}, preopen=True)["n_cleared"]`, where slice5 = the bars of `score_one`'s 5-calendar-year slice ending at E. **`n_cleared` ONLY — never `cls` or `ma_cleared`** (`encode` reads E's high for those). It counts qualified levels above close(E−1) that open(E) exceeds (a level = ≥ 2 test episodes, or the 50-day average acting as resistance). | 250 | RESULT 1: 0.67 on his rulings; 08-25: coin flip forward (2026) |
| B1 | **Benchmark:** shelf distance | `dmin` via the copied `score_one` (`f3_def.f3_new`, `STATED`) — exactly PRE-REG 6: row-based 5-year slice, ties by ticker, `np.array_split` | 250 | RESULT 8: 1.36x, already seen |
| B2 | **Benchmark:** ADR20 | as above | 20 | mechanical with a fixed +50% |

**Feature 20, mechanical proofs (replace any prose proof):** (a) `rank_v2.py` is NOT imported (it loads data at module
level and its cache has no era in the key); `encode` is called directly, with any cache keyed `(era, ticker, E)`;
(b) on a seeded 600-event sample the build replaces E's high, low, close and volume with garbage and asserts
`n_cleared` is unchanged for all 600 (as `_594 review/check.py` (a) did for dmin) — any change → feature 20 is dropped
and said so; (c) the same corrupt-E test is run on ALL 20 features and both benchmarks and must read 0 changed.
On sheets feature 20 is named "levels cleared by the open", never "congestion zones".

**B1.** Its scored set is identical to RESULT 8's (checked: the 310 dropped era-B events have at most 131 bars of
history, so all were NULL there), so
the build ASSERTS the reproduction: the 2017-2020 per-year tercile counts in the discovery script, the pooled 12.9% vs
9.6% = 1.36x in the confirm script. A mismatch stops the run. **B1-clean** (dmin with the §4.0 NULL rules 3-4) is
printed beside it, description only. B1 uses run.py's 5-year row slice; features 1-19 use the calendar windows above.

**Edge cases, fixed now.** Feature 13 with no down-closing session → NULL (`no_down_day`). Two-group features (15, 16):
when the smaller group is under 100 scored discovery events or under 15% of them, the feature is description only and
cannot be carried. Feature 16 is NULL for all of 2016 and for era-B events before ~2022-09-26 (file start) — printed.

**Feature 12 is tied to membership (a collider), disclosed:** the population needs volume(E) ≥ 3 × the mean of
E−20..E−1, and feature 12's numerator sits inside that denominator, so a dried-up name gets in on less E-day volume.
The build prints, outcome-free, feature 12's within-month rank correlation with `vr20_mean`; §5.5 reads feature 12
within `vr20_mean` halves (description; `vr20_mean` is never a feature).

**Groups (near-duplicates; at most ONE feature per group can be carried):** gap {1, 2} · run-up / extension {3, 4, 17} ·
highs {5, 6, 7} · base {8, 9} · tightness {10, 11} · volume {12, 13} · strength {14} · structure {15, 16, 20} · size {18, 19}.

**Shelf relatives.** Outcome-free, on discovery: each feature's Spearman correlation with dmin, computed on
within-(era, month) percentile ranks pooled over events scored on both. |rho| ≥ 0.5 → tagged **"shelf relative —
confirm partly seen"** on every line it appears in, and subject to condition 5 of §5.2.

**No candidate feature is added, dropped or re-defined after outcomes are read.** The only later additions are HIS
reads from the winner gallery (§6 step 5): at most three, each coded and frozen BEFORE any confirm outcome is opened.
Any other new idea needs a new pre-registration and is confirmable only on the sealed years.

## 5. The statistic, the bars and the verdict words (fixed now)
**5.1 Statistic.** Within each (era, calendar month) holding ≥ 6 events scored on that feature, sort by the feature and
split into thirds with `np.array_split`. **Ties:** a block of equal values is never split — the whole block goes to the
third that holds its mid-rank position; the share of events this moves (vs a ticker-order split) is printed per
feature. **Tie-heavy fallback, decided in step 1 without outcomes:** if the pooled top or bottom third then holds under
20% of the feature's scored discovery events, the feature is read as a TWO-GROUP feature instead — its most common
value vs everything else — under the two-group rules (and their 100-event / 15% minimum). (B1 alone keeps PRE-REG 6's ticker tie-break so RESULT 8 reproduces.) **Ratio** = pooled big-winner rate of
the top third ÷ the bottom third. The middle third is always printed (shown, never tested). Two-group features
(15, 16): rate(yes) ÷ rate(no), months with ≥ 2 of each.
**Permutation (10,000 shuffles, `np.random.default_rng(1121)`).** Events are held in the fixed order (era, E, ticker).
For shuffle s every event gets one uniform random key u[s, event] (one draw per event, shared by all features). For
feature f, within each (era, month), the labels of the events **scored on f** are reassigned among those same events in
the order of their keys — a uniform permutation of the scored subset, never touching events NULL on f. Feature f's
own p = two-sided on |log ratio| (discovery) or one-sided in the fixed direction (confirm), (1 + count)/(10,001).
**Family-wide p** = share of shuffles whose LARGEST |log ratio| over the 20 features beats this feature's, computed on
the events scored on ALL 20 features (stated as such; description only). When a third holds zero winners the printed
ratio is inf or 0 and every test uses rates smoothed as (winners + 0.5)/(n + 1).
**Interval:** 90% bootstrap — (era, month) blocks resampled with replacement, 2,000 draws, `default_rng(1121)`, 5th-95th percentile.

**5.2 DISCOVERY — a feature is CARRIED to confirm when all SIX hold** (two-sided: either end may win):
1. ratio ≥ **1.25** or ≤ **0.80** (at discovery spread, condition 2 already needs about 1.30 — p is the binding one);
2. two-sided permutation p ≤ **0.05**;
3. with 2020 removed (2016-2019 pooled): ratio ≥ **1.10** in the same direction (or ≤ 0.91);
4. **ADR-neutral (§2), on discovery:** ratio ≥ **1.15** in the same direction (or ≤ 0.87);
5. **shelf relatives only (§4):** on discovery events with non-NULL dmin, terciles of the feature formed within
   (era, calendar quarter, dmin third of that era-quarter), strata ≥ 9 events: pooled ratio ≥ **1.10** in the same direction;
6. **group and cap, both free of the sample-size bias of "smallest p":** candidates = the features not ruled
   description-only. Strength z = |log ratio| ÷ the standard deviation of that feature's 10,000 permuted log ratios,
   computed on a COMMON set (so thirds-features and two-group features compete on one scale and on the same events).
   Group winner = the largest z on the discovery events scored on every candidate member of that group. Cap = the
   **four** largest z among group winners, each recomputed on the discovery events scored on ALL candidates. Ties →
   the smaller own p → the lower feature number. Both common-set sizes are printed. Conditions 1-5 are judged on the
   feature's own full scored set, and that ratio is printed beside the common-set one.
Anything else: **NOT CARRIED**, final (printed with every condition's value). The carried direction is frozen.
**Floors 3, 4 and 5 are calibrated before any outcome (§6 step 2), one floor per condition for all features:** the
pass rate of a floor = among synthetic draws with a planted TRUE 1.5x that pass conditions 1-2, the share that also
pass the floor; taken as the MEDIAN over the features it applies to. Under 80% → that floor is lowered in 0.05 steps
until the median reaches 80%, never below 1.05 (if 1.05 still fails it stays 1.05 and the pass rate is printed as a
stated weakness). The final floors are written into this document and its sha256 recorded before discovery outcomes open.

**5.3 CONFIRM — run ONCE, one-sided in the fixed direction, Holm-corrected over ONE family = everything tested on
confirm: ≤ 4 carried features + ≤ 1 combination + ≤ 3 of his gallery reads (≤ 8).** Every outcome has a word:
| Confirm ratio (fixed direction) | Holm p ≤ 0.05 | Same direction in the era-A part AND the era-B part | Verdict |
|---|---|---|---|
| ≥ 1.2 | yes | yes | **PICKS THE TAIL** |
| ≥ 1.2 | yes | no | **PICKS THE TAIL (one era only)** |
| ≥ 1.2 | no | either | **DIRECTIONAL, NOT PROVEN** |
| 1.0 ≤ ratio < 1.2 | either | either | **NOT CONFIRMED** |
| < 1.0 | either | either | **REVERSED** |
Every verdict is printed with its ratio and 90% interval, the monster and ADR-scaled ratios, and any tag ("— a
volatility proxy", "shelf relative — confirm partly seen", "era-B population thinned…"). **There is no STRONG vs LEAN:**
a true 1.5x reads ≥ 1.5 on confirm only half the time, so two words there would be a coin toss; the ratio and interval
carry the size. The per-era column is a qualifier only (a zero passes it 1 time in 4).

**5.4 What a correct build reads on these bars** (`design/spread_sim.py` → `spread_sim.txt`: seeded binomial, 40,000
draws, synthetic labels, discovery at 4.9% for 2016-19 and 25% for 2020, confirm 10.5% on 2,178 events. **Simulated:**
conditions 1-3 and the confirm test; family 5 / 8 figures use the FIRST Holm step (p ≤ 0.05/5, 0.05/8), so they are lower bounds. **NOT simulated here:** conditions 4-6, which can only lower the carry odds —
4 and 5 are calibrated on the real feature table in §6 step 2.)
| True effect | Carried (cond. 1-2) | …and ex-2020 ≥ 1.10 | PICKS THE TAIL on confirm, family of 1 / 5 / 8 | Whole chain, family 8 | Confirm ratio reads ≥ 1.2 / ≥ 1.5 |
|---|---|---|---|---|---|
| none (1.0x) | 2.4% per direction | 2.1% | 5% / 0.9% / 0.5% | ~1 in 10,000 per direction | 12% / 0.4% |
| 1.3x (shelf-distance size) | 49% | 44% | 52% / 25% / 20% | **~1 in 11** | 70% / 18% |
| 1.5x | 85% | 78% | 83% / 60% / 53% | **~2 in 5** | 93% / 50% |
| 2.0x | ~100% | 99% | ~100% / 98% / 97% | **~19 in 20** | ~100% / 96% |
- Null 95% bands of the ratio: discovery 0.77-1.30 · discovery ex-2020 0.59-1.70 · confirm 0.74-1.36 (250-session
  features: 0.77-1.31 · 0.56-1.83 · 0.72-1.39; for them a 1.5x passes confirm 46% at family 8, whole chain ~1 in 3).
- **The ex-2020 guard is weak, stated:** a pure-2020 artefact (1.5x in 2020, nothing in 2016-19) passes conditions
  1-2 56% of the time, and 52% of those still pass ex-2020 ≥ 1.10 (64% under the old "same direction"). Its real
  protection is the confirm set.
- Adding his reads (family 5 → 8) costs a real 1.5x about 7 points of confirm power (60% → 53%), a 1.3x about 5.
- A true-zero feature still shows a confirm ratio ≥ 1.2 about 1 time in 8: "DIRECTIONAL, NOT PROVEN" is not a finding.
**Plain reading: this study reliably finds a chart reading worth 2x, finds a 1.5x less than half the time, and will
usually MISS one worth 1.3x. A "NOT CARRIED" is not proof the reading is useless.**

**5.5 Pre-stated extra readings (printed for every carried feature and each of his reads; NONE is a bar):** per year;
common stock only (typed CS; untyped names are 680 of discovery vs 233 of confirm) and untyped only; one event per
identity (§1) per 60 sessions (first kept); gap ≥ 10% only; ADR-neutral (§2); the ADR-scaled tail (§2); the monster
tier; within each shelf-distance third; feature 12 within `vr20_mean` halves; each window length at ±50% on DISCOVERY
only (a direction flip or a ratio under 1.2 = "fragile").

**5.6 Combination — one, pre-stated, nothing fitted.** If ≥ 2 FEATURES are carried: the equal-weight mean of their
within-month percentile ranks (each signed by its discovery direction), on events scored on all of them, fixed on
discovery, tested ONCE on confirm as one member of the Holm family, read on the §5.3 table. His reads are never part
of it. No other combination, interaction, cut-off search or model. Fewer than 2 carried: no combination step.

**5.7 His gallery reads (≤ 3).** A read = something he names after looking at gallery A. Each is coded as an exact
definition under the §4.0 rules (knowable at 09:31, calendar windows, NULL rules, corrupt-E test), with the direction
HE states ("winners have more / less of it"). It skips the §5.2 gates (he saw the discovery winners, so discovery
numbers for it are description, printed and labelled "seen"). It is tested on confirm in the one Holm family. If he
names more than three, he picks the three; the rest are printed on discovery only. A read that cannot be coded from daily bars before E plus open(E) (news,
intraday shape, float) is recorded in his notes and takes no slot. If he names none, the family is ≤ 5.

## 6. Order of work (so no expectation is formed after seeing data)
1. **Feature table** for all 4,665 events from bars < E and open(E): the population asserts of §1, the identity map,
   the Q-suffix list, the underflow test, NULL counts per feature / era / year / reason, tie shares, the corrupt-E test
   on all features, feature 12 vs `vr20_mean`, the shelf-relative correlations, the count of event tickers whose last
   bar is before the era file's end (per era), and the fund count (untyped events = the #705 fund proxy; per set).
   Write the table, record its sha256. **This script contains no forward read.**
2. **Calibration, synthetic labels only (no forward read), discovery events only:** 2,000 draws per feature per case,
   `default_rng(1121)`. A planted effect k on feature f: an event's label is Bernoulli with rate b, b(1+k)/2 or bk by
   f's own within-month third (two-group: b, bk), b = 2p/(1+k), p = 4.9% for 2016-19 and 25% for 2020; events NULL on
   f get rate p. Cases: k = 1.0, 1.3, 1.5 on each feature, and one ADR-only case (rate by ADR20 third within era-quarter,
   2.0x, independent of f). Print per feature: pass rates of conditions 3, 4, 5 given 1-2, and how often the ADR-only
   label gets f through conditions 1-4. Apply the §5.2 floor rule, write the final floors here, record this document's sha256.
3. **Discovery outcomes** (separate script; reads forward bars ONLY for E ≤ 2020-12-31, asserted) → §5.2 verdicts and
   the B1 per-year reproduction (run.txt's "per year" lines for 2017-2020: n, bottom rate, top rate, ratio), written to a file, sha256 recorded.
4. **Blind recount** of steps 1 and 3 by a second build from this text alone, plus an adversarial review (look-ahead
   per feature, the sealed cut, the overlap rule, the survivorship rule, the permutation). Done BEFORE confirm,
   because confirm runs once.
5. **Winner gallery A** (§7) rendered from discovery; the first sheets shown to him. **HARD STOP: nothing below runs
   until he replies** — with his reads, or "none".
6. **Freeze his reads:** each coded, corrupt-E tested, appended to this document with its direction; sha256 recorded.
7. **Pre-confirm prints (outcome-free):** confirm n per feature and read, per era.
8. **Confirm outcomes, ONE run:** §5.3, §5.5, §5.6, the pooled B1 reproduction. Then its blind recount.
9. **Blind sheets B** (§7) if anything reached PICKS THE TAIL.

## 7. Chart sheets for his eye (12 per sheet, as #594; every draw seeded 1121, never hand-picked)
- **A. Winner gallery — outcome KNOWN (the "review 1000s of charts" ask), shown BEFORE confirm.**
  - EVERY discovery big winner (about 275 expected → about 23 sheets), **monsters (≥ 2x) first**, then the rest, seeded
    random order within each. Each winner sheet is paired with a sheet of 12 **failures** (§2 failure pool, not merely
    "non-winners" — a +45% name is not a contrast) drawn at random from the same (era, month)s. About 550 charts.
    The full discovery set (2,414) is rendered on request, so "1000s" is literally available.
  - Daily candles + volume, E−250 .. E+60, E marked, monsters tagged. **Every chart is padded to the same width** (a
    name that stopped trading shows blank bars, not a shorter chart).
  - Under each chart, in small text: its 20 feature values (and dmin), so his eye and the numbers meet on one sheet.
    Outcome is known here by design, so names and dates are shown — except a status-suffix symbol (§1), shown by its
    identity symbol. Untyped names are tagged **"untyped (likely a fund)"**.
  - The first 3 pairs go to him in chat (monsters), the rest on disk and on request. Discovery only: no confirm event is spent.
- **B. Blind sheets — outcome HIDDEN (his judgement of what passed).** For each PICKS THE TAIL feature or read (at most
  3, by confirm ratio): 2 sheets × 12 = 6 top-third + 6 bottom-third CONFIRM events per sheet, random within third, shuffled.
  - **Excluded from the draw (recognisable):** Qullamaggie's 62 EP buys (`holdings_1024/entries.tsv`, run.py's filter:
    `setup` in EP/both, `flicker` False, `has_bars` True, asserted 62 — an outcome-free file), and any identity with
    ≥ 3 confirm events.
  - **Rendering:** lettered A-L; log price axis with NO tick labels, unlabelled volume axis, no title, no round-number
    gridlines; no ticker, date, feature value or result; about 2 years of daily candles with EMA10/EMA21/SMA50/SMA200
    and volume, bars end at E−1 plus a mark at open(E); image files named by random 8-hex strings; PNG metadata
    checked to hold no ticker or date; the answer key in a separate file whose sha256 is recorded before the sheet is shown.
  - He rules good / okay / bad as in #594, plus a **"recognised?"** tick per chart; recognised charts are dropped from the score.
  - **What the score is:** the chance a good/okay chart sits in the FEATURE's winning third (0.5 = nothing), with n.
    It measures **his eye against the feature, not against outcomes** — 24 charts hold about 2-3 big winners, so the
    sheet cannot be scored against outcome. A lean, never a verdict. If nothing reaches PICKS THE TAIL, B is skipped and said so.
- Events shown on A or B are spent: they cannot serve later as outcome-blind labels.

## 8. What this does not answer
- **Money, and the entry.** The outcome is a +50% close within 60 sessions measured from the OPEN. The live trade buys
  the 1-minute opening-range high with a stop at entry − 2R (`docs/setups/magna53_ep.md`); Qullamaggie varies 1-, 5-
  and 30-minute ranges (his note 11-21). A gap that fades and later runs counts as a winner here but might never fill
  live; partials and the five slots are not modelled. Earlier reads (#545, backtest run 1) say the tail is lost in
  conversion, not at the gates. A reading that marks big winners is a selection lean, not a P&L claim.
- **Exactly the 09:31 list.** Membership needs E's full-day volume ≥ 3× its average, not known at 09:31. Features are
  clean; the population is "gap days that went on to trade heavy volume" — and feature 12 is tied to that rule (§4).
- **Gaps under 9%.** The population floor cuts them off; 15 of 25 of 2026's biggest winners gapped 8.1-9.9%.
- **A post-cut input, inherited.** Era-B raw price (feature 18 and the population's $5 floor) was built with split
  dates and ratios through 2026-10-16, as `01_ep_join.py` discloses; 5 era-B primaries change their $5 verdict under a
  2024-12-31 split cut. This study adds no new use of it and reads no post-cut bar.
- **Era-B survivorship via volume underflow** — tested in §1, tagged if it bites, not repaired.
- **An untouched confirm.** 2021-24 is out-of-time but partly seen (§0).
- **Funds.** Untyped events (913) are where leveraged and sector funds sit; they stay in, are tagged on sheets and read
  separately (§5.5). There is no clean single-asset fund list in the local files; "untyped" is the proxy #705 used.
- **The catalyst.** News quality, surprise, earnings vs other (`ep-edge-is-surprise-not-magnitude`) are not in daily bars.
- **Small effects.** See §5.4: a 1.3x reading is missed about 10 times in 11.
- **Recent listings.** History is cut by where each file starts (2016-01, 2021-09), so "new issue" cannot be told from
  "file starts here"; such events are NULL per feature, counted, never guessed.
- **2025-26** (sealed, #710), any intraday shape, float, and whether his eye agrees — that is §7, and it is his call.
- **Regime.** His 11-21 note: momentum is not expected to work in the current bear phase; nothing here is a claim about now.

## Critique resolutions (v2, 2026-11-21)
| Point | Resolution |
|---|---|
| D1 lookback holes / splits / symbol reuse | ACCEPTED — §4.0: calendar-session windows, 90% coverage, adjustment and identity NULLs, reasons printed. B1 keeps its row-based slice so RESULT 8 reproduces; B1-clean printed beside it. |
| D2 era-B volume underflow | ACCEPTED, numbers added — "extreme adjusted price" pinned at ≥ $1,000 on in-cut rows (ratio ≥ 5 vs all rows); the 1% trigger = more than 20 of 1,964; zero-volume NULL on 12, 13; the inherited post-cut input disclosed in §8. |
| D3 feature 20 import / proof / name | ACCEPTED — direct `encode` call, `n_cleared` only, era-keyed cache, corrupt-E assert (extended to all features), renamed. |
| D4 group winner by smallest p | ACCEPTED on the common-set principle, statistic MODIFIED — \|log ratio\| is not on one scale for thirds vs yes/no features, so the rank uses z = \|log ratio\| ÷ its permutation SD on the common set. Extended to the cap of four, which had the same bias. |
| D5 permutation over unscored events | ACCEPTED — per-event keys, labels permuted among scored events only; family-wide p on the all-20 set. |
| Look-ahead audit items (feature 12 collider, 16 coverage, no adjusted level, E's close in the outcome) | ACCEPTED — §4, §2. |
| Twins keyed on (ticker, E) | ACCEPTED, count corrected — all era-B events E ≤ 2022-04-04 dropped: **310** (273 + 37; the critique's 35 missed 2 on 2021-10-25). Population 4,702 → 4,665. Cross-era identity map added — on RETURNS, not the critique's "same open and close": a pilot showed price levels fail IBM (0.85). Q-suffix print added. |
| Confirm partly seen; split chosen in view of RESULT 8 | ACCEPTED — §0; shelf-relative tag and carry condition 5. |
| STRONG vs LEAN is a coin toss | ACCEPTED — one word, PICKS THE TAIL, with ratio and 90% interval. |
| Ex-2020 "direction only" is weak | ACCEPTED (≥ 1.10) — but the critique's rough "~35% artefact pass" is optimistic: simulated 52%. Kept and disclosed as a weak guard. |
| Condition 1 redundant | KEPT as written; stated that p binds. |
| ADR-neutral floor not simulated; thin cells | ACCEPTED — strata (era, quarter, ADR third) ≥ 9; floors 3-5 calibrated on the real feature table before outcomes, with a mechanical lowering rule. Two ADR bars stated separately. "all four" → six. |
| ADR-scaled tail as description | MODIFIED — "description only" and "is a volatility proxy whatever the strata say" conflict; made it a second numeric trigger (< 1.10) for the volatility-proxy TAG, never a carry bar. |
| Holm family / his reads fork | DECIDED: one family of ≤ 8 (his reads are the goal); cost printed in §5.4 (a 1.5x: 60% → 53%). |
| Uncited prior studies | ACCEPTED — four rows added to §0. |
| Sheet leaks (B exclusions, rendering, scoring, A padding) | ACCEPTED — §7. |
| Gallery before confirm; failures not non-winners; monsters first; feature values under charts | ACCEPTED — §6 reordered with a hard stop for his reply; §5.7. |
| Funds | PARTLY — no single-asset fund list exists in the local files (searched); untyped = the #705 fund proxy: counted, tagged on gallery A, read separately. |
| Mid-rank ties | ACCEPTED for features 1-20, with a two-group fallback when a tied block empties a third; REJECTED for B1 (it must reproduce RESULT 8 exactly). |
| B1 slice vs feature windows; delisted names; entry from the open | ACCEPTED — §4.1, §1, §8. |
| Draft's "run.py loader imported not copied" (not in the critique) | FIXED — run.py runs its pipeline at module level; the loader is copied with a source citation. |

## 9. ENTRY ARM — 1, 5 and 30-minute opening-range-high entries (added 2026-11-21 on his "Add it", BEFORE any minute bar of E is read for it)
**Why:** his note 2026-11-21 (`operator_shared_notes.md`): *"I know qullamaggie uses 1, 5, 30 min orb high entries, don't know exactly how but he varies"*. Apollo buys the 1-minute high live (`docs/setups/magna53_ep.md`); a 5-minute shadow lane and hourly arms are recorded (#482). **DESCRIPTION ONLY — no bar, no verdict word, no entry proposal** (an entry change goes through the periodic trade review #720 + CHANGE_PROCESS + his sign-off).
- **Population:** the §1 events (4,665) with E-day minute bars on file; coverage is RECOUNTED on the §1 population and printed first (a quick count on the pre-filter list gave 576 of 5,072). Minute source: Alpaca historical bars, **SIP feed** in both eras (`scripts/backtest_data_audit/pit_lint.py` F3, `feed=DataFeed.SIP`); the 11-22 fetch must use the same source and feed, asserted. The on-file set is — a NON-random subset (fetched for earlier studies); his "Do it TMR?" → the rest are fetched Sun 2026-11-22 (E-day only, never after 2024-12-31). The arm reports BOTH the 576 already-on-file subset and the full set, and prints coverage per year / era before any result.
- **Three entries, each on E's regular-session minute bars (09:30-16:00 ET):** the opening range = the high / low of the minutes stamped 09:30 .. 09:30+N−1 ET by the clock (N = 1, 5, 30), never "the first N rows"; any missing minute inside the range → that entry is NULL for the event (counted per N). Entry = the first minute AFTER the range whose high exceeds the range high, filled at max(range high, that minute's open) (a gap through the trigger fills at the open, never at a price that did not trade). No trigger by 16:00 → no fill. Same split-adjustment as the daily bars (minute prices are scaled by the E-day daily adjustment factor). Check against E's daily open with a TOLERANCE (first 09:30 minute open within 1% of the daily open): mismatches are counted and printed, the event kept and tagged — never an assert that halts the run.
- **Stop for the R read, unchanged from live:** `entry − 2R`, `R = entry − range low` (magna53_ep.md, post-2026-08-16), per entry's own range. Stop hit = the first LATER minute on E (never the entry minute itself — its intra-minute order is unknown) or daily low (E+1..E+60) at or below it. A non-positive or zero-width stop (range low ≥ entry, or entry − 2R ≤ 0) → that entry is NULL, counted.
- **Printed per entry (description):** fill rate; of the §2 big winners, the share each entry filled; median and mean return at the E+60 close in units of the placed stop (entry − stop; stopped trades booked at the stop price, or at the open when it gaps below the stop, so a clean stop-out is −1) AND the plain percent return from entry beside it (stop units differ across the 1/5/30-minute ranges, so only the percent column compares entries); stop-hit rate by E+5; and the same split by the carried features' thirds once §5 discovery is done. Never pooled across eras without the split beside it.
- **Cannot answer:** how Qullamaggie chooses among the three (his rule is unknown — this only shows what each would have done); partials and trailing exits (held to E+60 or the stop only).

## 10. STAGE 1 RECORD + PRE-OUTCOME AMENDMENTS (2026-11-21, after step 1-2, BEFORE any outcome is read)
Stage 1 (`scripts/probes/_ep_winner_study_1121/build/stage1/`, run on this document at sha256 `99621b6d…`): population reproduces 4,665 exactly; feature table `feature_table.tsv.gz` sha256 `ade1d780…`; corrupt-E look-ahead proof: 0 values changed on every feature; D2 underflow: mechanism supported, 0 excluded days.
- **Final floors (§5.2, step 2):** condition 3 (ex-2020) **1.10**, condition 4 (ADR-neutral) **1.15**, condition 5 (within shelf thirds, shelf relatives f05, f07) **1.10**; the lowering rule did not fire.
- **Amendment A1 — two-group features (f15, f16), decided on synthetic labels only:** the pooled rate(yes) ÷ rate(no) is biased by month composition (a NO-effect f15 reads 1.86 because its "yes" names cluster in 2020). Replaced, for every place §5 uses a two-group ratio, by the **Mantel-Haenszel ratio stratified by the same month groups** (months with ≥ 2 of each); the permutation is unchanged (within month). Stage 3 must print, on synthetic no-effect labels, that the MH ratio centres near 1.0 for f15 and f16 before the discovery outcome opens.
- **Amendment A2 — identity map:** the "first 10 returns rounded to 4 decimals" candidate step splits same-name pairs whose files differ in the third price decimal (NVDA 20.70 vs 20.699). Use `identity_alt` (same-symbol pairs that pass the full 40-session / 90% test are one identity; cross-symbol candidates still need the hash step, which blocks 8,204 flat-price false renames).
- **Amendment A3 — B1 reproduction:** stage 3 asserts the shelf-distance benchmark reproduces RESULT 8's discovery-year rows (run.txt "per year" 2017-2020) before any new-feature verdict prints; a miss stops the run.
- Stage-1 resolutions 5-13 (calibration p by the exact hypergeometric form; per-case seeding; mid-rank tie to the lower middle; month rules; ADR strata over all discovery events; B1 vs B1-clean; D2 terms; SPY fallback) are accepted as written in `stage1` printouts.

## 11. HIS GALLERY READS FROZEN + THE ADR RULING (2026-11-21, step 6 — after discovery and gallery A sheet 1, BEFORE any confirm outcome is read)
Appended only: every byte above this heading is unchanged (the document's first 49,932 bytes still hash to `4f2dbe7f…`, asserted by `stage4_freeze/02_preconfirm_n.py`). Where this section conflicts with §2, §4.1, §5.3 or §5.7 above, this section wins; each override is named below.

**His words** (gallery A sheet 1 and its failure sheet, verbatim in `docs/methodology/operator_shared_notes.md`, entry 2026-11-21 "EP winner gallery"):
> "on failures, several are on clear downtrends, even EP gap didn't make much difference to break it.
> ACB clear downtrend, weak
> GE, downtrend, EP didn't break out of it, still under 200d
> CRC ugly downtrend
> on contrary, TLRY broke out of downtrend, move above 200d, then 200d turned up and turned into uptrend
> same with NVAX downtrend started basing the flipped up above all moving avg"

> "on your point about more volatile stocks have more +50%, that is not a negative catch, qullamaggie suggests looking at higher ADR stocks precisely because it can lead to bigger moves. Purpose is to make money, %50 is same regardless of stocks volalitity, we shouldn't penalize high ADR stocks for it, in fact we may want to look for it provided risk adjusted it makes sense and we can place stop adequently."

### 11.1 The codings (frozen; code `scripts/probes/_ep_winner_study_1121/build/stage4_freeze/hreads.py`, sha256 `a4f13eb7…`)
Inputs: the ticker's daily bars dated before E plus open(E) only (§4.0). Windows are calendar sessions. Averages are of adjusted closes and are only compared with open(E) or with each other (no adjusted level is a feature).
- SMA200(E−1) = mean close of the bars present in sessions E−200..E−1 (the feature-17 precedent). SMA200(E−21) = the same over E−220..E−21. SMA50 = over E−50..E−1.
- EMA10 / EMA21 = recursive EMA, alpha = 2/(n+1), over the closes of the bars present in E−200..E−1 in date order, **seeded at the first bar of that window** (the gallery chart seeded at the ticker's first bar ever; with the 180-200 bars the coverage rule allows, the seed's weight in EMA21 is under 1e-7).

| # | Name | yes when | Window n | NULL (first match) | His direction | Confirm ratio, oriented so ≥ 1.2 = his direction |
|---|---|---|---|---|---|---|
| H1 | Below the 200-day at the open | open(E) < SMA200(E−1) | 200 | history · coverage (< 90% of 200) · adjustment · identity · bad_price | **NO wins** (above the 200-day wins) | rate(no) ÷ rate(yes) |
| H2 | In a downtrend | open(E) < SMA200(E−1) AND SMA200(E−1) < SMA200(E−21) | 220 | history (first bar later than E−220) · coverage (EITHER 200-session sub-window under 90%) · adjustment / identity anywhere in E−220..E−1 · bad_price | **NO wins** | rate(no) ÷ rate(yes) |
| H3 | Above all moving averages at the open | open(E) > max(EMA10, EMA21, SMA50, SMA200), all through E−1 | 200 | as H1; never computed on a subset of the four averages | **YES wins** | rate(yes) ÷ rate(no) |
| H4 | ADR20 (his ruling, not a gallery read) | benchmark B2 exactly — the stage-1 `B2` column, not recomputed | 20 | as B2 | **HIGH third wins** | top third ÷ bottom third |
- An open exactly equal to an average is "no" for H1 / H2 and "no" for H3.
- **Statistic.** H1-H3: two-group, Mantel-Haenszel ratio stratified by (era, month), months with ≥ 6 scored events and ≥ 2 of each group (§5.1 + amendment A1, as stage 3 read f15 / f16), one-sided permutation in the direction above. H4: thirds within (era, month) with ≥ 6 scored, mid-rank ties (stage 3's R9), one-sided HIGH.
- **Frozen values:** `stage4_freeze/h_reads.tsv.gz` (4,665 rows, sha256 `0b995389…`); the confirm run reads H1-H4 from that file. Printout `01_freeze_reads.txt` sha256 `c8a7bd12…`.
- **Corrupt-E test** (§5.7): the frozen 600-event sample of stage 1, three garbage patterns in E's high / low / close / volume and every later bar: **0 changed on H1, H2, H3, H4** (non-NULL in the sample: 520 / 506 / 520 / 600). Positive control: a deliberately leaky "close(E) < SMA200" answers differently under a huge vs a tiny garbage close on 520 of 520.
- **Outcome-free:** every event's series was cut at E with E's high / low / close / volume blanked before the coding saw it (asserted for all 4,665, including the 2,251 confirm events). **One slip, disclosed:** the first run of the positive control compared E's REAL close with the 200-day on the 520 scored sample events (discovery and confirm mixed) and printed three flip counts (149 / 371 / 258); that is a gap-day close, not a 60-session outcome, no label was formed, nothing was chosen on it, and the control now compares two garbage closes only. No discovery ratio for H1-H3 was computed at this step; at the confirm run their discovery numbers are description, labelled "seen" (§5.7).

### 11.2 What is and is not gated
- **His reads H1-H3 skip the §5.2 gates** (§5.7: he saw the discovery winners). The §4.1 two-group minimum (smaller group ≥ 100 events and ≥ 15%) is a carry rule and does not gate them; printed anyway and met on both sets (discovery yes/no: H1 492 / 1,551 · H2 438 / 1,540 · H3 1,504 / 539; confirm: H1 552 / 1,456 · H2 447 / 1,486 · H3 1,379 / 629).
- **H4 skips the gates too, and this is disclosed as chosen AFTER seeing discovery:** B2 read 5.78x there (top third 22.9% vs bottom 3.9%; ex-2020 10.9x; monster tier 19.6x; ADR-scaled tail 0.91). It is in the family because of his ruling above, not because of a pre-stated rule.
- **Overrides, named:** §2 "ADR20 is a benchmark, not a candidate" → on confirm ADR20 is BOTH the benchmark used for the ADR-neutral strata and hypothesis H4. §4.1 "at most three" later additions and "any other new idea needs a new pre-registration" → H4 is a fourth addition, made here, before any confirm outcome. §5.7 "≤ 3" → three gallery reads plus H4.
- **§5.3 family size, amended: the Holm family is exactly 9** = 4 carried features (f02 LOW, f03 HIGH, f09 HIGH, f18 LOW) + 1 combination (f02+f03+f09+f18, HIGH) + H1 + H2 + H3 + H4. "≤ 8" in §5.3 and §5.7 reads "9". **Power at 9 was not simulated** (§5.4 covers families of 1, 5 and 8); the first Holm step is 0.05/9 instead of 0.05/8, so the cost is a little above the family-8 column.
- **H1-H3 are close to one read, not three:** H2 "yes" is a subset of H1 "yes", H3 "yes" a subset of H1 "no" (discovery, scored on all three, n 1,978: above-200d and above all averages 1,459 · above-200d but not above all 39 · below-200d, 200d not falling 42 · downtrend 438). Holm counts them as three; stated, not corrected.
- **Coverage:** H1 / H3 need 200 sessions, H2 220: NULL for most of 2016 (first scored E 2016-10-18 / 2016-11-15) and for era B before 2022-07-18 / 2022-08-11. Confirm n per era is printed in `02_preconfirm_n.txt` before the confirm read. The month rule (≥ 2 of each group) also thins era A, where few EPs opened under the 200-day in 2021: H1 760 scored → 589 in the test (202 yes), H2 748 → 539 (156 yes); the per-era direction check for H1 / H2 in era A rests on those.
- **The combination (§5.6) is unchanged:** neither his reads nor H4 are part of it.

### 11.3 The volatility ruling (his words, quoted above)
- The suffix **"— a volatility proxy"** (§2) is still computed and printed on confirm exactly as defined. **It is a description, NOT a negative verdict:** it does not lower, qualify or re-word any §5.3 verdict, and no report may present it as a reason to discount a feature. High ADR is a reason to look at a stock (Qullamaggie), not a confound.
- **H4 itself:** the ADR-neutral reading of ADR20 (thirds of ADR within ADR thirds) is not meaningful and is printed "n/a"; the tag is not applied to H4. Its ADR-scaled-tail ratio is printed as description.
- **The risk-adjusted test of ADR is the §9 entry arm's job**, not this confirm: return in R multiples with the live stop (`entry − 2R`, `R = entry − range low`) and the plain percent beside it, for the 1- / 5- / 30-minute entries, **split by ADR20 third** (H4's thirds), after the 2026-11-22 minute fetch. Description only, as §9 states; whether a stop "can be placed adequately" is read there (stop-hit rate by E+5 per ADR third).

### 11.4 Known gap between his words and the coding (stated, NOT re-coded)
- On his named charts the coding reads: ACB 2020-05-21, GE 2019-01-31, CRC 2020-02-21 → below the 200-day, downtrend, not above all averages (matches his read). NVAX 2020-02-27 → above the 200-day, not a downtrend, above all averages (matches).
- **TLRY does not match at the open.** TLRY 2020-11-05 opened at 71.00 under a falling 200-day (84.76, was 96.32 21 sessions earlier): H1 yes, H2 yes, H3 no — the same reading as the three failures. TLRY 2018-09-05 is NULL (under 200 sessions of history). His words "broke out of downtrend, move above 200d, then 200d turned up" describe what the stock did AFTER the gap. Whether an EP goes on to break its downtrend is not knowable at 09:31, so that part of the read cannot be coded (§5.7) and takes no slot. H1-H3 test only the state at the open: "an EP that opens still under its 200-day / in a downtrend wins less often".

### 11.5 His ruling on the TLRY gap (2026-11-21, before confirm)
Shown that TLRY 2020-11-05 codes like his failures at the open (it reclaimed the 200-day only after the gap), he ruled: *"hit rate is low so we may miss some, if on EP day it doesn't look good and later it works, that may just mean it's not a catchable EP"*. **No post-gap reclaim read is added; H1-H3 stay as coded at the open.** An EP that only looks right after the gap day is out of scope for the gap-day entry, not a miss of the reads.

## RESULT — confirm run 2026-11-21 (one run; blind recount + adversarial review agree; `build/stage5_confirm/confirm.txt`)
- **PICKS THE TAIL, both eras:** H4 high ADR 8.32x (22.3% vs 2.6%), combination 7.70x, f09 base depth 7.35x, f18 low price 2.93x, f02 low gap-in-daily-ranges 2.89x, f03 20-day run-up 2.47x (Holm p 0.0009 each). The five non-H4 members carry the "volatility proxy" tag, which per §11 is NOT a negative verdict.
- **REVERSED:** his reads H1 (below the 200-day) 0.51, H2 (in a downtrend) 0.57, H3 (above all averages) 0.49 — EPs gapping from a downtrend reached +50% MORE often (13.5% vs 7.6%).
- **POST-HOC DESCRIPTION (not pre-registered; `review/posthoc_failure_side_1121.txt`), on his question "can we actually keep the money":** bought at the gap-day open and held 60 days with NO stop, none of these groups makes money — downtrend EPs median −4% (45% up at day 60) vs others −2% (46%); the most volatile third median −14% (36% up) vs least volatile +1% (52%). The tail is real but is given back by holding: the answer depends on the stop and selling into strength — the §9 entry arm with the live stop + partial, split by ADR third and H1-H3, after the 11-22 minute fetch.

## 12. AMENDMENT to §9 (2026-11-21, BEFORE any minute bar is fetched or read) — replay the LIVE exit, not stop-or-day-60
His question after the confirm run: *"can we actually keep the money and make a profit from these stocks? And is the risk actually managed?"*; and his correction *"current rule is not 2r sale"*. §9 as written held each entry to its stop or the E+60 close, with no partial — it cannot answer "keep the money". Amended:
- **Exit = the live MAGNA53 exit**, replayed through `scripts/ep_replay.py::walk_campaign` with `RULESETS["current"]` (= `era_d`): initial stop `entry − 2R` (R = entry − opening-range low), 1/3 sold the first time the minute high reaches `entry + 8R`, stop to breakeven, the rest on the live trail — imported, never re-coded, per `docs/setups/exit_discipline.md` §"Current deployed behaviour" (cited version at run time recorded). If `walk_campaign` cannot take a 5- or 30-minute range as its entry/stop input, the 1-minute arm uses it as-is and the 5/30-minute arms report the §9 stop-or-E+60 reading beside, labelled.
- **Printed per entry arm (description only, no verdict word):** fill rate; mean and median realized R per trade (and percent); win rate; the share of total R from the top 5% of trades (the tail); max losing streak; and the same split by **ADR third (H4)**, **H2 downtrend yes/no**, and the confirm-carried combination third — confirm-set and discovery-set shown separately, never pooled without the split.
- **"Risk managed" read:** stop-hit rate by E+5 and the share of losses worse than −1.5R (gap-through the stop), per ADR third and per H2 group.
- Everything else in §9 stands (SIP minute bars, clock-defined range, NULL rules, sealed cut).

## 13. AMENDMENT to §9/§12 (2026-11-22 08:00 PT, after the coverage count, BEFORE any minute price is read)
- **Coverage, recounted on the §1 population (printed first, `build/stage6_minutes/01_coverage_and_list.txt`):** 995 of 4,665 events already had E-day minute bars locally (all stores written by `scripts/probes/_cb_backtest/fetch_minutes.py`, which hard-codes `feed=DataFeed.SIP`); the other 3,670 (ticker, E) pairs are fetched 11-22 by the same script in apollo-market (SIP asserted by the code, not by a flag). All E ≤ 2024-12-31.
- **The live entry gate is applied, not skipped:** `walk_campaign` refuses a 1-minute range wider than 1.5×ATR(14) (`setup:stop_too_wide`, live). PRIMARY rows = the live behaviour (refused events counted per arm, booked as no trade). A second row per arm with `bypass_stop_too_wide=True`, labelled BYPASS, shows what the refused trades did — description only.
- **5- and 30-minute arms** pass their own range high / low as `orb_high` / `orb_low` to `walk_campaign` with the entry clock at the first minute after the range (`submit` = 09:35 / 10:00 ET); if the function's internal checks make that impossible, the §12 fallback applies, labelled.
- **Sealed cut:** daily bars after 2024-12-31 are dropped at read and asserted absent. A campaign still open at the last session on or before 2024-12-31 is marked to that close, tagged `open_at_cut` and counted per arm; never extended.
- **Order of reads:** the 995 on-file subset is printed beside the full set (it is non-random), discovery and confirm sets apart, both eras apart.

## RESULT — §9/§12/§13 entry arm, live exit (2026-11-22; one run, blind recount MATCH on the 1-minute arm; `build/stage6_minutes/02c_tables.txt`)
Description only (no verdict word, no entry/exit proposal). R = placed-stop units (a clean stop-out is −1).
- **1-minute ORB-high entry, live exit (PRIMARY, live gates applied):** discovery 1,549 trades mean **+0.33R** (95% +0.20..+0.47), confirm 1,479 mean **+0.21R** (+0.11..+0.32); win rate 28-29%, median trade −0.4..−0.6R; the top 5% of trades carry more than all of the profit (124% / 166%). Confirm era A (2021-22 Alpaca) +0.06 (−0.11..+0.24), era B (2022-24) +0.32 (+0.18..+0.45).
- **Robust to the outliers (main-loop check, same rows):** R capped at +10 → +0.27 / +0.18; ranges under 0.5% of price dropped → +0.30 / +0.22; common stock only → +0.35 / +0.23.
- **Risk managed:** ~70% of trades end on a stop by E+5 (breakeven stops included); only 1-2% of losing trades lose more than 1.5R (a gap through the stop); longest losing streak 10-11.
- **Volatility (H4 ADR thirds), confirm:** low +0.23, mid +0.09, high **+0.31** (median −0.02, the best median); discovery low +0.14, mid +0.55, high +0.28 — the most volatile third is NOT worse once the live stop and partial apply.
- **Downtrend (H2), confirm:** yes +0.12 (interval includes zero) vs no +0.31; discovery +0.19 vs +0.37 — downtrend EPs earn less but do not lose on the live exit.
- **5-minute entry:** fills about half as often (802 / 840 trades; more refused as stop too wide), discovery +0.39R, confirm +0.13R (era A −0.09). **30-minute entry cannot run through the live exit** (`walk_campaign` refuses any submit at or after 09:45); stop-or-E+60 fallback only: discovery +0.49R, confirm −0.05R.
- Deviations (card report, verified): the literal `RULESETS["current"]` keeps the pre-10-29 trail on historical dates (arming on moves means < 0.01); minute bars were already split-adjusted, so 27 events were rescaled by the daily/minute ratio and 6 set NULL; ambiguous intra-bar fills excluded (161 of 3,189 on the 1-minute arm); the on-file 995 subset reads higher than the full set (non-random, as disclosed).
