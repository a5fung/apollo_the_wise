# Step 4 adversarial review — discovery build (stage 3), EP winner study #594

**Verdict:** no defect in the checks listed below. I would stand behind the carried set f02 (LOW third wins), f03 (HIGH), f09 (HIGH) and f18 (LOW). This review does NOT replace the step-4 blind recount or the step-5 hard stop (his reply on gallery A), both of which come before confirm.

## Scope and inputs

**Reviewed (2026-11-21):**
- `build/stage3/discovery.py` (sha `2436cc77…`, which matches the sha printed in `discovery.txt`, so it was not edited after the run)
- `discovery.txt` (`2bd0b0d3…`) and `discovery_outcomes.tsv.gz` (`033b7fac…`)
- stage 1: `common.py`, `features.py`, `stats.py`, and the stage-1 scripts 01-06 (grepped)
- prereg sha `4f2dbe7f…`

**How:** independent code in the scratchpad (`rev.py`, `rev7.py`, the combination recount and the permutation rerun, outputs `rev.txt`, `rev7.txt`, `revc.txt`, `revp.txt`). It does not import `discovery.py`, `stats.py` or `features.py`. It reads the era-A daily CSV and `daily_raw_close.csv.gz` directly. It keeps only discovery tickers and rows dated ≤ 2021-03-30 at read, and asserts E ≤ 2020-12-31 on every event.

**Not opened by this review:**
- era B
- the stage-1 bar pickle
- `events_scored.tsv.gz`

From `run.txt` I read only the lines matched by `grep -nE "^    (2017|2018|2019|2020) era A: n"` plus the `per year` header line numbers.

## Results per check
| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | Look-ahead, 5 features × 3 events by hand | **CONFIRMED** | See the spot-check section below. |
| 2 | Sealed cut (#710) | **CONFIRMED** | `common.load_bars` drops era-B rows dated after 2024-12-31 at read and asserts it, and `bars_cached` re-asserts on load. `discovery.py` uses the pickle only in the loop at lines 322-332: era-B series are skipped and era-A series are cut at `ci(2020-12-31)+60 = 2021-03-30`, asserted, before any outcome. `02_identity.py` reads only 2021-09-27..2022-06-30 closes (sanctioned by prereg §1). `03_underflow_d2.py` cuts at read. Its mechanism test (part 1) uses in-cut rows only, and its line-74 count of the flag file before the date cut is a side print, not the bar. The split list through 2026-10-16 feeds only the raw-price reproduction disclosed in §8, and the script reads no outcome. Both `.err` files read `exit 0`. |
| 3 | Overlap / era rule | **CONFIRMED** | `population.tsv` has 4,665 events (A 3,281 · B 1,384); the first era-B E is 2022-04-05. The 2,414 discovery events are all era A. `build_population` asserts the 2 / 270 / 95 / 310 (273 twins) drops. |
| 4 | Survivorship (no drop of names lacking forward bars) | **CONFIRMED** | All 2,414 events have an outcome. 84 have fewer than 61 bars in E..E+60: in 75 the series ends, 9 only have holes. 8 of the 84 are big winners. All are kept, and the window is calendar-indexed (`ci ≤ ci(E)+60`), not row-indexed. |
| 5 | Within-month permutation | **CONFIRMED** | The build gives each event a uniform key (`default_rng(1121)`, 10,000 × 2,414). It sorts the events assigned within each (era, month) by key and gives labels in fixed order. That is a uniform permutation of the scored subset, as §5.1 requires. A fully independent `rng.permutation` (4,000 shuffles, other seed) gives the same pass/fail on condition 2 for all 20 features. At 10,000 shuffles the build's stated key convention, seed 1121, reproduces its p values exactly (f01 0.0224, f10 0.0207, f17 0.0546). Seeds 7 and 99 give f01 0.024 / 0.024, f10 0.019 / 0.019 and f17 0.057 / 0.053, so the condition-2 verdict holds under every seed. My first 4,000-shuffle run gave f01 0.0305, a high draw that still passes. |
| 6 | A1 Mantel-Haenszel ratio | **CONFIRMED** | The formula Σ a·n0/N ÷ Σ c·n1/N is correct. Recomputed independently: f15 2.383, f16 1.540, f15 ex-2020 2.687, all equal to the build. The no-effect check centres at 0.997-1.004 against a pooled ratio of 1.86, so the check can fail. f15 and f16 are not carried under any reading. |
| 7 | A3 reproduction vs `run.txt` | **CONFIRMED** | `run.txt` has one `per year:` block (line 79). Lines 80-83 are byte-identical to `A3_EXPECT`, and `discovery.txt` prints MATCH on all four rows. |
| 8 | No confirm outcome read | **CONFIRMED** | See the confirm-outcome section below. |
| 9 | Carried set follows the six conditions and floors | **CONFIRMED** | See the six-conditions section below. |
| 10 | §10 frozen before outcomes | **CONFIRMED** | See the freeze section below. |

### Check 1 — look-ahead spot-check
**Three seeded events with ≥ 260 bars of history:**
- EVH 2019-04-11
- TSG 2019-05-09
- WDR 2020-12-03

**Method:** the features are recomputed by hand from bars with `ci < ci(E)` plus open(E). The last bar used for each event is E−1.

**Results:**
- f02, f03, f08, f09, f18 and ADR20 equal the table on all three events.
- Over the whole discovery set, the same independent code finds 0 mismatches: f02 0/2,407 · f03 0/2,407 · f08 0/2,194 · f09 0/2,338.
- f18 matches `daily_raw_close.csv.gz` at E−1 on all 2,414 events.
- `med_dv20` (f19) is the median over rows i−20..i−1 (`01_ep_join.py` 307-313).
- The `ep_events` header has no forward column. `vol_E` and `vr*` are not features.

### Check 8 — no confirm outcome read
- `discovery.py` computes forward quantities only inside `for k in range(N)` over the discovery frame, and asserts E ≤ 2020-12-31 and era A on every event.
- Stage-1 scripts 01-06 hold no index after E except `05_corrupt.py`, which writes garbage into E and later bars as the look-ahead test; it reads no outcome.
- 06 (calibration) loads no bars.
- No script opens `events_scored.tsv.gz` or `run.txt`; the only mentions are comments.
- This review read no confirm-year outcome and no era-B bar.

### Check 9 — the six conditions and floors
**Conditions 1-4:** recomputed independently, with my own mid-rank thirds, ADR strata and MH. Every value matches the build to 3 decimals, and the pass/fail pattern is identical for all 20 features.

**Smoothing (R2):** the build smooths every bar, while §5.1 smooths only when a third holds zero winners. The raw ratios printed in `discovery.txt` keep all four carried features clear of every floor. The shift from raw to smoothed is under 1%, against z margins of 9% or more. f07's ex-2020 raw ratio is 22/466 ÷ 26/498 = 0.904, which is 1.106 in its own direction, so it still passes on raw; it is not carried either way. The prereg's stated reciprocals (≤ 0.91, ≤ 0.87) give the same verdicts as the build's log-symmetric floors.

**Two-group month rule:** `assign_two` uses months with ≥ 6 events AND ≥ 2 of each group. That is the rule printed in stage 1's `06_calibration.txt` layout header (accepted in §10 as the month rules), and it has no effect because f15 and f16 are not carried.

**Condition 5:** f05 1.681 and f07 1.415, both matching.

**Condition 6 — group winners on independent z:**
- gap f02 (8.12)
- run-up f03 (6.67 vs f04 5.74)
- highs f07
- base f09 (12.30 vs f08 11.28)
- tightness f10
- volume f12
- strength f14
- structure f20 (4.46 vs f15 4.02)
- size f18

**Cap on the all-20 set:** f09 10.82 > f02 7.75 > f18 6.58 > f03 5.58, then f20 4.48 in fifth.

**Same four:** f02, f03, f09, f18, and all four pass conditions 1-5. The closest margins are ≥ 9% in z; my z differs from the build's by at most about 3.2% (f08).

**Reading of condition 6:** the literal reading (candidates = all 20) and an "among 1-5 passers" reading give the same four.

### Check 10 — §10 frozen before outcomes
- The prereg's file mtime is 20:16:14. The run started at 20:24:13 and printed prereg sha `4f2dbe7f…`.
- Commit `4afb89e8` (20:26:31) holds a blob that also hashes to `4f2dbe7f…`, so §10 did not change after outcomes opened.
- The build's note that §10 is uncommitted is now stale: it was committed 2 minutes after the run, with identical content.

**Combination (§5.6):** recounted independently. 2,338 events are scored, the top third has 169 winners of 755 and the bottom third 37 of 806, the same as the build.

## Flags (none changes a verdict)
- **Bad price data in the 60 days after the gap.** The frozen data flags cover E and E−1 only.
  - **How many winners it touches:** 8 of the 302 big winners have one of two things in E+1..E+60.
    - An adjustment flag or identity break: DUST and DWT.
    - A one-day close jump above +100%: EXE ×2, NKLA ×2, FLNA and GME (NKLA and GME are likely real moves).
  - **Effect on the carried features:** scoring all 8 as non-winners moves f02 0.355→0.364, f03 2.430→2.336, f09 5.443→5.310 and f18 0.393→0.402. With the broader mechanical flag classes (11 winners) the moves are similar.
  - **Conclusion:** no verdict is close to moving.
- **Volatility.** All four carried features read 0.94-1.10 on the ADR-scaled tail in their carried direction, and plain ADR20 (B2 block) reads 5.78x. Each is likely to take the confirm-stage "— a volatility proxy" tag. That is a frozen tag, not a verdict change, and was already flagged by the build.
- **f18 at confirm.** It is carried, so §8's inherited post-cut input (era-B raw price built with splits through 2026-10-16) now applies to a carried feature at confirm. The era-A raw price is the vendor raw file, which this review confirmed (0 mismatches).
- **Builder disclosure.** Printing `run.txt` lines 79-89 exposed the 2021-24 per-year rates for shelf distance (B1). B1 is a benchmark whose confirm-year ratios §0 already discloses as seen. No carried feature's confirm outcome was exposed.
- **R3 reading** (MH within ADR / shelf-distance strata for conditions 4-5, where A1 names months only). This is an interpretation, but f15 and f16 are not carried under any reading, so it has no effect.

## Carried set I would stand behind
**f02 gap size in daily ranges (LOW third wins) · f03 short run-up 20 (HIGH) · f09 base depth 40 (HIGH) · f18 raw price (LOW)**, with the combination of the four as fixed in §5.6.
