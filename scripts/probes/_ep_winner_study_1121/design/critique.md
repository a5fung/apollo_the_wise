# Adversarial critique — `prereg_draft.md` (EP big-winner chart study), 2026-11-21

Read: the draft; `_594_outcome_qm_1121/build/run.py` + `run.txt` + `review/check*.txt`; `_705_ep_join_1023/01_ep_join.py`
(event definition, `wide_table`) + `01_ep_join.txt`; `_533_nbis_structure_encoder.py` (`adr20_pct`, `pivot_levels`,
`encode`); `_ep_rank_v2_1103/build/rank_v2.py` (`features`, F1); `docs/setups/magna53_ep.md` (entry/stop); the last notes in
`operator_shared_notes.md`; headers of the uncited `docs/analysis` EP studies below. Outcome-free reads only, plus one $0
binomial simulation (§S). No new outcome was computed; `run.txt` (which prints RESULT 8's outcomes) was read as directed.

**Verdict: sound frame, not ready to freeze.** Five defects must be fixed before freezing (D1-D5); the rest are fixes or
disclosures.

---

## MUST FIX before freezing

### D1. Long-window features read across bar holes, splits and ticker reuse that the population filter never checked
- Quote §1 drop 1: *"`flag_adj` / `flag_adj_Dm1`: 2 (a split in the lookback fakes chart structure)."* Those two flags cover
  **E and E−1 only** (`01_ep_join.py:339-340`: `(ticker, E)` and `(ticker, D)`), so they do not cover the lookback. Same for
  `break_on_E_or_D` (identity break). A 250-bar feature (5, 16, 20, B1) can still span a split or a reused symbol.
- Quote §4: *"index E−1 = the last bar before E"*, *"E−120..E−1"*. These are **row** offsets. The files have holes: rows whose
  prior bar is not the previous session = **211,391 (A) / 188,545 (B)** (`01_ep_join.txt` lines 12/18). On a holed ticker,
  "E−120" by row covers more than 120 sessions, so 120-, 60- and 20-bar windows silently differ in length between names. (Feature
  14 is not affected: the draft already reads SPY at the ticker's own E−1 and E−61 bar dates.)
- **Fix:** define every window on the era calendar index `ci` (as run.py's R2 does for the forward window). Make a feature
  NULL when its window has under 90% bar coverage, when it holds a `known_adjustment_event` /
  `discontinuous_across_known_adjustment` date (the two klasses `01_ep_join` already loads), or when it holds an identity-break
  date of the G4 symbol guard (`symbol_guard_{A,B}.tsv`, already loaded there). Print each NULL reason per feature, era and year.

### D2. SUSPECTED: era-B volume underflow may carry future information into the population and into features 12 and 13 (the build must test it)
- The era-B adjusted file carries 22,658 `zero_volume_underflow` rows (`01_ep_join.py` header), and the draft notes an
  adjusted open of 655,000. The suspected mechanism, which I did NOT test: volume divided by the factor of a *later* reverse
  split rounds to 0. If so, the primary filter's zero-free 20-session baseline removes names that later reverse-split hard
  (often losers, some after the 2024-12-31 cut). That would thin era B of future losers using information from after E, a
  survivorship drop the draft's "no survivorship drop" line does not see.
- Supporting but NOT decisive: `rows_gap_ge_9_vr_ge_3_but_dirty_baseline` is **5,462 in B against 1,555 in A**
  (`01_ep_join.txt`). That counter is `has20 & ~clean20`, so it mixes zero-volume baselines with baselines that have missing
  sessions, and it is counted BEFORE the price, liquidity and type floors. It cannot size the effect.
- **Fix:** (a) the build tests the mechanism outcome-free. Do era-B zero-volume rows dated ≤ 2024-12-31 sit on tickers whose
  adjusted prices are extreme (a later large reverse split)? Then it prints how many era-B gap ≥9% days fail ONLY on the
  zero-volume part of `clean20` while passing the price, liquidity, type and ≥3x tests. If that count is above 1% of the
  era-B primaries, era-B confirm results carry the tag "era-B population thinned of later reverse-splitters". (b) Volume
  features 12 and 13 are NULL when their window holds a zero-volume row, and that count is printed. Never read a zero as a
  real dry-up. (c) Disclose in §8 that the era-B raw price (feature 18) uses split dates up to 2026-10-16, a post-cut input
  `01_ep_join.py` already discloses.

### D3. Feature 20 "imported not copied" from `rank_v2.py` would run another study and collide twins
- Quote: *"feature 1 of `scripts/probes/_ep_rank_v2_1103/build/rank_v2.py` … imported not copied."* `rank_v2.py` is a script
  that loads data at module level (`rows_c`, `daily`, `IDX`). Importing it runs that pipeline. Its `_enc_cache` is keyed
  `(t, d)` with no era, which is the same class of bug as run.py fix (b) and the id()-keyed cache crash in memory.
- I read the full path (`_533_nbis_structure_encoder.py` lines 288-410 and 411-585). F1 =
  `nbis.encode(t, d, {t: slice5}, {}, preopen=True)["n_cleared"]`. With `preopen=True`, `minute={}`, so `breached()` tests
  `open_px > level` only. `pivot_levels` loops `range(end)` with `end = ia`, and its episode counting reads `days[k]` for k < ia.
  `sma50_level` reads closes up to `ia−1`. **`n_cleared` uses no E field except the open.** ⚠ `encode` DOES read E's high
  (`day_high = days[ia][2]`, line ~557) for `ma_cleared`, and `cls` can depend on it. The build takes `n_cleared` ONLY, never
  `cls` or `ma_cleared`.
- **Fix:** call `nbis.encode(..., preopen=True)` directly on the 5-calendar-year slice (`run.py::score_one`'s slice), with
  the cache keyed `(era, ticker, E)`. Keep a mechanical proof in the build instead of the prose one: corrupt E's
  high/low/close/volume on a 600-event sample and assert `n_cleared` is unchanged, as `_594 review/check.py` (a) did for dmin.
  Note that `n_cleared` counts qualified levels above close(E−1) that the open exceeds (≥2 test episodes, or SMA50 as
  resistance). It is not "congestion zones" in the plain sense; state it that way so the sheets name it correctly.

### D4. The group winner is picked by smallest p, which favours short-history features for n alone
- Quote §5.2 (5): *"it has the smallest p in its group."* Group members need 20 to 252 bars, so their n differs by ~1,000
  (run.txt: `history<250` alone is 1,170 of 4,975; every NULL reason together, 1,300). Within run-up {3: 20, 4: 120, 17: 50}, highs {5: 252, 6: 120, 7: 120}
  and structure {15: 120, 16: 250, 20: 250}, the 20-bar member wins on sample size, not on strength. NULLs are also not random
  for outcome, and the sign flips by era: short-history events ran 0.157 against 0.117 in era A but 0.075 against 0.102 in era B
  (run.txt). So the n difference is a population difference too, and it points different ways in discovery and confirm.
- **Fix:** pick the group winner on the events scored on **every** member of that group, by |log ratio|. Ties go to the
  smaller p, then the lower feature number. That also handles p ties at the 1/10,001 floor, which the draft leaves unresolved.
  Report each feature's own full-population ratio beside it.

### D5. The permutation shuffles labels across events the feature never scored
- Quote §5.1: *"the big-winner labels are shuffled within each (era, month), jointly for all features."* If a month's
  shuffle includes events NULL on feature f, the null distribution mixes in the NULL group's different win rate (D4). That is
  not the hypothesis "label independent of f among scored events".
- **Fix:** for each feature's own p, shuffle within (era, month) among the events **scored on f**, using the same 10,000
  seeded permutation index per month, restricted. For the family-wide p, use the joint shuffle but compute it on the events
  scored on all 20 features, and say so.

---

## Look-ahead audit, feature by feature (with D1-D3 applied)
- Clean as written: 1-11, 14, 15, 17, B1, B2. `adr20_pct` uses `days[ia−20:ia]`, so E is excluded (`_533…:288-293`).
  B1/dmin is clean (`_594 review/check.txt`: "changed by garbage E bar 0/600"). Feature 20 is clean (D3).
- 12, 13: clean in time, but contaminated by underflow zeros (D2). **Collider:** the population needs v(E) ≥ 3 × mean of
  E−20..E−1, and feature 12's numerator (E−10..E−1) sits inside that denominator. A dried-up name is admitted on less absolute
  E-day volume, so feature 12 is mechanically tied to membership. **Fix:** print, outcome-free, the within-month rank
  correlation of feature 12 with `vr20_mean`. Add feature 12 read within `vr20_mean` halves to §5.5 (description only;
  `vr20_mean` is never a feature).
- 16: *"no high from g..E−1 reached close(g−1)"* is clean. It needs 250 bars, so it is NULL for all of 2016 and for era-B
  events before about 2022-09-26 (the B file starts 2021-09-27).
- 18, 19: clean. `med_dv20` is the median of adjusted close × adjusted volume over E−20..E−1, which split cancels out of. The
  draft is right to use raw price for 18; no feature may use an adjusted price LEVEL (it encodes later reverse splits). Add
  that as a rule.
- Outcome: "highest close over E..E+60" includes E's own close. That is fine, but say so, because E's close is not knowable
  at 09:31 and a reader may think the window starts at E+1.

## Era stitching / twins: the (ticker, E) key misses renamed symbols
- The twin rule (keep the era-A copy) is right, but it is keyed on (ticker, E). 35 era-B events dated ≤ 2022-04-04 have no
  same-ticker era-A twin. I matched them outcome-free on (E, open within 0.2%, gap within 0.3 pt) and checked `ep_wide_A`:
  - **19 are the SAME event under another era-A symbol.** The era-A file names tickers by a LATER symbol: DWAC→DJT (×2),
    YNDX→NBIS, BIGC→CMRC, GPS→GAP, YY→JOYY, FREY→TE, ISIG→TULP, PTRA→**PTRAQ**. The Q suffix is a later bankruptcy marker,
    which is future information in a symbol. A few look like mapping errors, not renames (LC→HAPN, PSTG→P, OSTK→NXH), and the
    build must check them.
  - 8 are vendor-volume near-misses: era A has the same ticker and day at vr20 2.81-3.00 (MRNA 2.98, GOOGL 2.91, AFRM 3.00,
    MELI 3.00, INTU 2.81).
  - 8 do not appear in era A's wide table at all (SQ, SAVA ×2, CNR ×2, GOEV, STAR, TMX).
- So the draft's **273 twins is an undercount (≥ 292)**, and every ticker-keyed rule inherits the hole across the era boundary:
  §5.5 "one event per ticker per 60 sessions", the tie-break "by ticker", and my own "≥ 3 confirm events" exclusion below.
- **Fix:** (a) within 2021-10-26..2022-04-04 the era-A file is the only source: drop every era-B event in that span, twin or
  not, and count it (35). The 31 A-only events in the span stay. (b) Key ticker-level rules on an identity that spans eras:
  map era-A symbols to era-B symbols by matching shared-overlap bars (2021-09-27..2022-06-30, same date, same open and close).
  Print the map and the mismatches. (c) Print every era-A event whose symbol carries a post-event status suffix (5 letters
  ending in Q). No feature reads the symbol, but sheets and keys must never show it.
- "Never stitched" holds. Consequence to print: long features (≥120 bars) have almost no era-B 2022 confirm events, so their
  confirm is mostly 2021 A plus 2023-24 B. Print confirm n per feature per era BEFORE the confirm read.

## Is the confirm set untouched? Partly, and the draft under-discloses it
- Already seen on 2021-24: shelf-distance ratios per year (2021 1.25, 2022 A 0.52, 2023 0.95, 2024 1.23), base rates per year
  and era, the short-history group's win rate, the outcomes of Qullamaggie's 62 EP buys (run.txt lists them by name, e.g.
  VKTX 6.51x, PLTR 2.17x), and #705's big-winner names. The split was chosen after RESULT 8 showed era B at 1.08 for dmin.
  The power argument holds, but say the choice was made with that in view.
- **Shelf relatives inherit seen outcomes.** Features 5, 6, 16 and 20 measure much of what dmin measures. Anyone who saw
  RESULT 8 can predict that a dmin-like feature carries on 2016-20 and fades in era B. **Fix:** print, outcome-free on
  discovery, each feature's within-month Spearman with dmin. Any |rho| ≥ 0.5 is tagged "shelf relative — confirm partly
  seen", and for those the within-shelf-third read (§5.5) becomes a carry condition: pooled within-third ratio ≥ 1.10 in the
  same direction.

## Bars a correct build can fail by spread alone (§S has the numbers)
- **The task's question, ~1,000 confirm events at 11%** (~37 winners per third): the null 95% band of the tercile ratio is
  **0.64-1.57**. A true-zero feature reads ≥1.2 21% of the time, ≥1.25 17% and ≥1.5 4%. **At that n, anything under about 1.5
  is noise.**
- At the draft's real confirm (~2,180 scored, 45 months, 10.5%): the null band is **0.74-1.36**, and a zero reads ≥1.2 12% of
  the time. That matches the draft's "1 in 8". Long features drop to ~1,850, so their band is wider.
- **STRONG vs LEAN is a coin toss.** A TRUE 1.5x reads ≥1.5 on confirm only **51%** of the time, and a true 1.3x only 19%.
  Quote §5.3: *"≥ 1.5 | yes | yes | STRONG"* against *"1.2 ≤ ratio < 1.5 | yes | LEAN"*. The two words cannot be told apart
  for any true effect between about 1.3x and 1.7x. **Fix:** merge them into one word, "PICKS THE TAIL", printed with the
  ratio and its within-month bootstrap 90% interval. Keep "(one era only)" as the qualifier. Never present STRONG vs LEAN to
  him as a difference.
- Per-era halves (confirm A ~870, B ~1,300): null bands 0.63-1.57 and 0.67-1.50. "Same direction in both" is passed by a zero
  about 1 time in 4 (0.5 × 0.5). That is acceptable only as a qualifier, which is how the draft uses it.
- **The ex-2020 guard is weak.** Discovery ex-2020 (2016-19, ~4-5% base, ~80 winners) has a null band of 0.57-1.73. For 250-bar
  features it is 2017-19 only, ~57 winners, band 0.50-2.00. "Same direction" is passed by a pure-2020 artefact about half the
  time. **Fix:** require ex-2020 ratio ≥ 1.10 in the same direction, and simulate the pass rate for true 1.3x and 1.5x before
  freezing. My rough read: ~70% / ~80% pass for real effects, ~35% for a 2020-only artefact.
- Discovery condition 1 (≥1.25) is redundant. At discovery spread (null band 0.76-1.30), two-sided p ≤ 0.05 already needs
  about ≥1.30. Keep it, but say p binds.
- The ADR-neutral floor (1.15) was not simulated. Rough read: a real non-volatility 1.3x passes it about 75-80% and a 1.5x
  about 95%. Simulate it and print that in §5.4. The cells are thin: terciles inside (month, ADR half) with 12 events are 2
  per cell. **Fix:** form the ADR-neutral strata as (era, calendar quarter, ADR tercile) with ≥ 9 events.
- Text defects: §5.2 says *"all four hold"* and lists five conditions. §2 puts the volatility-proxy tag at a CONFIRM ADR-neutral
  ratio under **1.2**, while §5.2(4) carries at a DISCOVERY floor of **1.15**. State both as two separate bars, each with its set.

## Too many features for the confirm n?
- **Discovery, 20 two-sided tests.** Under a global null, conditions 1-2 pass about 1 feature (20 × 0.05). With the ex-2020 and
  ADR-neutral conditions (correlated with 1-2) it is roughly 0.4-0.6 false carries, and the group rule caps it below that. That
  is acceptable, and the printed family-wide p is the right companion.
- **Confirm, Holm over ≤ 5 (≤ 4 features + 1 combination).** This is adequate and is the design's power ceiling. The top-ranked
  test needs one-sided p ≤ 0.01 (z ≈ 2.33). A true 1.5x on ~2,180 events (expected z ≈ 2.6) passes about 62% of the time, and a
  true 1.3x (z ≈ 1.7) about 25%. That matches §5.4.
- **Cost of my reorder proposal below (adding up to 3 of his reads):** the family grows to 8, so the first Holm step needs p ≤
  0.00625 (z ≈ 2.50). A true 1.5x then passes about 54% (from 62%) and a true 1.3x about 20% (from 25%). These are rough
  normal approximations, not simulated. The alternative is a separate family for his reads at α 0.05, which keeps feature
  power but raises the study-wide false-positive rate. That fork is a design call for the study's owner. My rec: one family,
  because his reads are the goal.

## Volatility confound: use the repo's own tail outcome as a description
- The house tail outcome in the #569 / #552 studies is ADR-scaled ("reach ≥ 8×ADR", `pregap_base_axes_2026-08-19.txt`). A fixed
  +50% outcome is largely an ADR detector. **Fix:** pre-register now, as description only and never a bar, the ADR-scaled
  tail: highest close E..E+60 ≥ open × (1 + 8·ADR20/100), with its tercile ratio printed beside the primary for every carried
  feature. A feature that holds on +50% but flattens there is a volatility proxy, whatever the ADR-neutral strata say.

## Features already tested that §0 misses (cite them; none bars a re-test, since population and target differ)
- `pregap_base_axes_2026-08-19.txt` / `pregap_base_v2_2026-08-20.txt` (#569, 749 tier-A gap days 2026, ≥8×ADR tail).
  Pre-gap extension vs its own SMAs in ADR units: 11.7% vs 9.3%, perm p 0.55, null. Base duration × quietness: all p ≥ 0.08.
  These are features **17 and 8** on a near-identical tail target.
- `331_gap_alignment_n3120_2026-09-09.md`: gap open vs the 15-day base high and the trailing high on 2026 alerts — "the axis is
  wrong in SIGN". That is **feature 6**. Keep feature 6 two-sided for this reason.
- `gap_floor_decision_table_2026-08-19.md`: 15 of 25 ≥10R winners gapped only 8.1-9.9%. This bears on **feature 1** (small
  gaps among the biggest winners) and on the 9% population floor truncating it.
- `545p2_missed_ep_tail_read_2026-09-02.md` and `ep_backtest_run1_2026-08-29.md`: the tail is lost in conversion (entry/exit),
  not at the gates. That backs §8 "Money".

## Chart sheets: unintended outcome leaks
- **B, recognisable names.** Confirm is 2021-24: meme mania (GME, AMC, BB) and every Qullamaggie EP buy of those years. The
  operator studies Qullamaggie's trades (#717, 757 buys), and run.txt lists 2021-23 QM buys with outcomes. Shape alone
  identifies these. **Fix:** exclude Qullamaggie's 62 EP buys and any ticker with ≥ 3 confirm events (on the cross-era identity, see twins) from the B
  draw. Add a
  "recognised?" tick per chart, and drop recognised charts from the score.
- **B, rendering.** Quote: *"no … price scale label that identifies the name"*. Tighten it to: log price axis with NO tick
  labels, unlabelled volume axis, no title, no round-number gridlines. Random 8-hex image file names. The answer key goes in a
  separate file with its sha256 recorded before the sheet is shown, and the PNG metadata is checked for ticker/date.
- **B, scoring.** Quote: *"the chance a good/okay chart sits in the winning third"*. The third is the FEATURE's tercile, so
  this measures his eye against the feature, not against outcomes. Say that. 24 charts at 11% hold ~2.6 winners, so it cannot
  be scored against outcome.
- **A,** shown first in chat: these are winners, so the outcome is known by design and nothing leaks. Two points still need
  fixing. (i) Non-winner charts end at E+60 or where the bars end, so a short right side shows the name stopped trading. Pad
  every chart to the same width. (ii) Monster tags are on winner sheets only, which is fine.

## Does it serve the goal (his words: "review 1000s of charts to find edge", "keep testing … other chart readings")?
- Yes for the stats; under-built for the eye. Three changes:
  1. **Gallery BEFORE confirm, and his reads join the confirm family.** §6 runs confirm straight after discovery. §4 sends
     anything he names to the sealed years, which are 2025-26, years he has watched live. Reorder: discovery → gallery A
     shown → he names reads → each is coded and pre-registered (frozen, sha256) → ONE confirm run over the carried features
     plus his reads (Holm family grows; cap it at 3 of his). The untouched 2021-24 set then tests HIS chart reads, which is
     what the goal is.
  2. **Contrast winners with failures, not all non-winners.** "Non-winner" includes +45% names, so the contrast is blurred.
     Pre-state the failure pool for the gallery (description only): highest close E..E+60 < 1.10 × open(E). Draw same-month
     failures from it.
  3. **Order the gallery monsters first** (≥2x, the Qullamaggie-scale tail), then the rest. Put each chart's 20 feature values
     in small text under it on A only (the outcome is known there anyway), so his eye and the numbers meet on the same sheet.
- Size: ~275 discovery winners ≈ 23 winner sheets + 23 failure sheets ≈ 550 charts. Say that count, and offer the full
  discovery set (2,414) as an on-request extension so "1000s" is literally available.

## Funds in the population and the gallery
- run.txt shows leveraged and sector funds as primary EP events (KOLD, BOIL, KWEB, among Qullamaggie's own buys). 916 study
  events are untyped (680 of them in discovery), and that is where funds hide. Without a fix, gallery A will show him
  leveraged-fund charts as "EP winners". **Fix:** the build prints a fund count, using the universe's single-asset fund list
  from the breakout v1 work (10-29 ruling) or a name/issuer match on the untyped set. Gallery A tags each fund chart, and the
  §5.5 common-stock-only read is printed for every carried feature (already listed).

## Smaller fixes
- §5.1: features 7 and 8 have many ties (7 = 0 whenever E−1 is the 6-month high). The ticker-alphabet tie-break moves real
  mass between thirds. Assign a tied block to the third that holds its mid-rank, and print the share moved.
- §1: say B1 uses run.py's 5-calendar-year slice (`score_one`) while the new features use the full era history, or put both
  on one slice.
- §8 "Delisted names" can be partly answered now: `_594 review/check.txt` (b) found 148 events with fewer than 60 ticker rows
  after E, so the files do keep names that stopped trading. The build still prints the per-era count of event tickers whose
  last bar comes before the file end.
- §8: add that the outcome is measured from the OPEN while the live entry is the 1-minute ORB high, and Qullamaggie varies
  1/5/30-minute ranges (his note 11-21). A gap-and-fade that later runs counts as a winner here and might never fill live.

---

## §S. Spread simulation (binomial, terciles within month, `default_rng(1)`, 4,000 draws; an approximation, not a power proof)
| Set (events, base) | Null 95% band | P(zero ≥1.2) | P(zero ≥1.5) | True 1.3x: P(≥1.2) / P(≥1.5) | True 1.5x: P(≥1.5) | True 2.0x: P(≥1.5) |
|---|---|---|---|---|---|---|
| 1,000 @ 11% (task's case) | 0.64-1.57 | 0.21 | 0.04 | 0.63 / 0.26 | 0.49 | 0.89 |
| Confirm 2,178 @ 10.5% | 0.74-1.36 | 0.12 | 0.006 | 0.72 / 0.19 | 0.51 | 0.97 |
| Confirm era-A part 867 @ 12% | 0.63-1.57 | 0.20 | 0.04 | 0.64 / 0.27 | 0.52 | 0.90 |
| Confirm era-B part ~1,300 @ 10% | 0.67-1.50 | 0.19 | 0.03 | 0.66 / 0.25 | 0.50 | 0.92 |
| Discovery 2,414, per-year rates (2020 at 25%) | 0.76-1.30 | 0.09 | 0.001 | 0.73 / 0.16 | 0.51 | 0.98 |
| Discovery ex-2020 | 0.57-1.73 | 0.26 | 0.07 | 0.63 / 0.33 | 0.51 | 0.85 |
| Discovery 2017-19 (250-bar features) | 0.50-2.00 | 0.29 | 0.11 | 0.61 / 0.35 | 0.52 | 0.82 |
Per-year base rates for discovery come from RESULT 8's printed per-year terciles for 2017-2020 (already seen; used only for
spread). 2016 has no printed rate (all NULL on dmin), so its 0.08 is ASSUMED.
The draft's §5.4 figures agree with these to within its stated roughness.
