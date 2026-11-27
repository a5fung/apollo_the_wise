# Stage 4 part 2 — adversarial review of stages 1 and 3 (before gallery and check)

Written 2026-11-26 PT. Read-only: no bar after a break day was opened by this review (captured files only), no check
outcome computed, Qullamaggie's buys never set against an outcome. Prereg `3eb2b9b0`, A1 `4a7beda1`, A2 `0a6cc417`
asserted.

**What counts as a real defect (fixed before any check was run):** the run departs from prereg + A1 + A2 in a way that
changes a population row, a feature value, an outcome label, a verdict, or the 2024-12-31 seal — or a rule whose
application cannot be judged right without a ruling. Disclosed design limits and wrong figures in amendment text go
under "For the operator" and do not fail the gate.

## Verdict
- **GATE: FAIL on one item, tiny, cannot move a verdict.** 20 era-A break rows (NIO 9, SWI 6, REE 5) were dropped as "file start" on a reading stage 1e never recorded and that the prereg's own words mostly contradict (D1).
- Everything else reviewed holds: no look-ahead found, the cut holds, the keep rule reproduces exactly, truncation is as written, the permutation is valid and the four carried readings survive much harsher shuffles.
- **Operator fork (his call):** (a) amend — the 20 rows stay dropped as run, disclosed; (b) rebuild from stage 1e — changes the feature table and the calibration and re-runs discovery after its outcomes were seen. Rec: (a).

## Population first (seed 1124 kept events, outcome-free) — `r1_outcome_free.txt`
| Set | Events | Identities | Type | Median price | Median daily range | First breaks | Opened above level |
|---|---|---|---|---|---|---|---|
| Discovery 2017-2020 (era A) | 5,330 | 2,129 | common 90.8%, ADR 6.6%, unknown 2.6% | $23.26 | 5.1% | 33.9% | 26.7% |
| Check 2021 to 2022-Q1 (era A) | 2,910 | 1,768 | common 91.0%, ADR 5.9%, unknown 3.0% | $28.16 | 5.3% | 29.2% | 24.8% |
| Check 2022-04 to 2024-10 (era B) | 3,356 | 1,467 | common 78.1%, **unknown 15.5%**, ADR 6.3% | $21.21 | 5.2% | 33.5% | 26.1% |

- **Discovery is 53.8% one year:** 2020 holds 2,867 of 5,330 events and 620 of 846 big winners (73%); eight months of 2020 hold 68% of winners. Every month has a winner.
- **Events cluster by day:** 47% of discovery events sit on days with 10 or more events (max 95 on 2020-06-05).
- **Winners are not 846 separate stories:** 638 identities; 157 identities win twice or more (max 7).
- **Era B effectively starts July 2022:** 2022-04 / 05 / 06 hold 3 / 8 / 22 events (file-start drops); 2022-04 cannot form thirds.
- **Symbols carry later status:** 18 discovery events sit on a "Q" (bankrupt-later) symbol, one the second-largest winner (SUNWQ). The gallery must not show these symbols.
- Nothing in the composition is surprising for a momentum breakout list (mid-priced common stock, 4%+ daily range by the gate).

## Findings by area
| Area | Result | Evidence |
|---|---|---|
| Look-ahead per feature | **None found** (table below). | code read |
| The 2024-12-31 cut | **Holds.** Era-B bar copy rebuilt in this run (8,619,626 rows kept, 5,210,943 dropped on the date column alone); feature table and event file end at E 2024-10-04; stage 3 opened only era-A files, rows ≤ 2021-05-12. No stage script names a closed-list file; only stage 1c's three pull scripts name the discarded pull. | `r1`, `r4_counterfactual_paths.txt`, sealed-copy sidecar |
| Keep rule | **Reproduces exactly.** Own re-walk: 11,596 and 11,607 kept, 0 rows differ, smallest gap 61 sessions, no (identity, D) twice. A walk run only on rows up to a date gives the same decisions for those rows (three dates). | `r1` section 2 |
| Drops before the walk | **D1** (below). The other arms use dates ≤ E only. | `r2_file_start.txt` |
| Window truncation | **As written.** 6 discovery events cut, 0 winners among them, 0 winners lost to the cut. | code read `s3_outcomes.py` |
| Era-B guard file | **Live and not weaker than era A's.** It holds no date after 2024, so "0 dropped at the cut" is real. On the 2022-04..06 overlap it has 151 break dates to era A's 63; of era A's 63, 21 match, 27 are symbols absent from era B, 15 are present and unmatched (11 holes era B does not have, 4 jumps). Few event tickers carry a break (14 of 1,823) because most of its symbols are units and warrants. | `r1` section 3, `r5_guard_agreement.txt` |
| Truncation blind spot (design, not a defect) | The era-A split arm needs a raw/adjusted factor step, so a split NOT applied to the bars is invisible. Sized from audit-flag dates: split-sized days confirmed by volume inside a kept window: 3 events, **0 winners**. Unconfirmed split-sized days: 23 events, 9 winners (ANAB, ARQL, IMMU ×2, CODX, VXRT, DDD, WKHS, LXRX) — real news days as far as I recall, not checked against a source. The gallery should show these nine first. | `r3_outcomes.txt` B |
| Permutation | **Valid and robust.** Within-(era, month) shuffle among scored events, same thirds, two-sided on the log ratio. Ratios re-derived from counts equal stage 3's (3.245 / 2.315 / 1.984 / 0.584). With labels allowed to move only within one week, or one day, all four carried features stay at the floor p (0.0005 of 2,000). | `r3` C |
| Run-once | **Holds.** The discovery script's hash is the same in the synthetic header, the real header and on disk; the outcomes file was written after the synthetic run. | hashes + file times |
| Largest winners | MARA 10.4x, SUNW 8.3x, RIOT 6.9x, GEVO, DDD, TIGR … — 13 events ≥ 5x, all in 2020. No data-error pattern. | `r3` A |

## Look-ahead by feature group
| Group | Features | Inputs | Latest date read |
|---|---|---|---|
| volatility, run-up, base, tightness, averages | 1, 7, 8, 9, 12-16, 19, 20 | the name's own bars, live gate code | D |
| size | 2 (raw close), 3 (dollar volume) | raw close at D (era B: derived for 8.2%, NULL), 20-session median | D |
| strength | 4, 5, 6 | every pool name's trailing 21 / 63 / 126-session return on the night | D |
| highs, trend, stage | 10, 11, 21, 22, 23 | 252 / 200 sessions to D | D |
| volume | 17, 18 | volume to D | D |
| open | 24a / 24b, B4 | open(E), close(D), level(D) | open of E only |
| benchmarks | B1, B2, B3 | the night's list rows | D |
- **Mechanism:** every array is cut at D before any feature is computed; pool facts use trailing windows only; the strength rank does not use group codes.
- **Non-bar channels (disclosed in the prereg, none in a carried feature):** 2026 security types and fund names decide membership; 2026 group codes feed B3 and B1; era-B prices and volumes are adjusted as of 2026-10; the pick model behind B1 was fitted on 2017-20 picks.

## D1 — 20 rows dropped as "file start"
- **Text (§1.3):** drop when a check passed unscored because the file starts — first bar within 5 sessions of the file's first date and the look-back reaches before it "(era B to about 2022-06 and early 2017)"; a short listing is KEPT, "the live system would see the same".
- **Code (`s1e_events.py`):** `(first_ci <= 5) & unscored`. No reading recorded on disk.
- **What it hit:** NIO (9 rows, 2019-01/02), SWI (6, 2019-03/04), REE (5, 2021-12 to 2022-02). Each symbol has an old holder's bars in the file's first week, then a hole of 612 / 683 / 1,361 sessions, then a new listing 94 to 134 sessions old.
- **Reading that ran:** the live check counts rows, so its 189-row look-back does reach the file's first bar; literally the test is met.
- **Reading the text supports more:** the new company is a short listing the live system would pass the same way, and these dates are years outside the footprint the text names. So these rows should have stayed.
- **Effect (hash coins only, outcome-free):** seed 1124 would hold 3 more events — NIO E 2019-02-01, SWI E 2019-03-29 (discovery 5,330 → 5,332) and one REE event (check, era A; date assumes its identity string is its own ticker). None lost or moved. Seed 2411: 2 more.
- **Why no verdict can move:** two events among 879 in 2019; the carried readings sit at p = 0.0001.
- **For the fork:** row-based values on these rows span two companies across the hole (outside the guard's 85-session window), so leaving them out is defensible on its own, not only convenient.

## For the operator (not defects)
- **Daily range is mostly "wide-ranging stocks move more":** 3.2x on the fixed +50% yardstick, 1.04x on the range-scaled one. Inside equal-range groups: strength 1.47x, 6-month move 1.36x, low price 1.27x.
- **The four carried readings overlap:** daily range correlates 0.47 with the 6-month move and −0.29 with price.
- **Low price is tagged "against Qullamaggie's buys":** its winning third holds 19.9% of his buys.
- **A1's text quotes 0.80%; the real share is 7.20%.** Handling unchanged; the sentence is wrong.
- **Volume-underflow tag (era B):** three readings of the trigger disagree (160% / 0.57% / 0.13% against a 1% line); stage 1e took the narrowest and did not tag.
- **Real base rate 9.18% sits above the 3–8% power grid** — more power than §5.4 says, not less.
- **33% of winners (276) broke after 2020-10-06** and are held out of gallery A by the embargo.

## What this review did not do
- No independent outcome recount from bars (the blind recount's job; this stage reads no forward bar).
- Stage 2's calibration was not re-derived.
- Nothing on the check years after E was computed.

## Files
`r1_outcome_free.py/.txt` · `r2_file_start.py/.txt` · `r3_outcomes.py/.txt` · `r4_counterfactual_paths.py/.txt` · `r5_guard_agreement.py`, `r5b_guard_unmatched.py` → `r5_guard_agreement.txt`
