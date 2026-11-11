# Breakout v1 — Qullamaggie's shape rules as list gates: PRE-REGISTRATION (2026-11-11)

**Status: SCORED 2026-11-11 — FAIL in both rounds (round 2 after his regrade is at the END of this file: amendment 2 rejects 13 of 17 `no` and keeps 249 of Qullamaggie's 263 listed buys; nothing enforced). Pre-registered and committed BEFORE any score was run (commit `48bb6458`). Nothing is
deployed, merged or switched on; paper stays OFF (the operator's 11-10 ruling). A hard gate needs his sign-off on the
filter list before it ships (`docs/setups/CHANGE_PROCESS.md` rule 3).**
Owner when shipped: `docs/setups/consolidation_breakout.md` (this file is the finding). Task: PLAN.md #717.
Work folder: `scripts/probes/_717_shape_gates_1111/`. Code under test: `breakout_v1.shape_gates` (pure, bars <= D).

## Why
- 2026-11-10: the first paper session bought five charts the operator said were not breakouts — *"where's the higher
  low, where's the surfing moving avg? ... still flagging at best"* (ABCL), *"just chopping around, no pattern at all"*
  (OUST), *"we're not creating a new setup, we are using qullamaggie's breakout first and foremost"*.
- Cause (ours): the 11-02 rebuild (`cb_rebuild_from_qm_trades_2026-11-02.md` row 43) REMOVED higher-lows /
  riding-an-average / tightening instead of rewriting them, and tuned every remaining rule for recall of Qullamaggie's
  buys. Nothing tested that a non-breakout is rejected.
- This REVERSES row 43. Why row 43 was wrong (not just incomplete): the CODX / PENN finding of 11-02 voided two
  DEFINITIONS ("three back-to-back 5-day blocks", "every close for 10 days above a SIMPLE average") — it never said the
  pattern has no higher lows or no surfing. The operator's words that day were that both charts DO make higher lows and
  DO surf the 10/21. Dropping the criteria themselves was our inference, and the first paper session disproved it.

## Sources (the words each gate is written from)
- Qullamaggie, the article (operator_shared_notes L1934-1937): *"A big move higher ... 30-100%+"*; consolidation
  *"usually 2 weeks to 2 months"*; the stock *"'surfs' the rising 10- and 20-day and sometimes the 50-day moving
  average"*, with *"higher lows and tightening range."*
- The operator, 10-28: *"pulling back and 'surfing' the key moving averages (10,20, or 50), making higher lows, then
  breakout on volume"*; *"touch MAs can be flexible, if it comes within a reasonable range and turns back up"*; *"it's
  not touch and done, it'll surf for multiple days near the MAs, tighten, then breakout"*. His "Yes" that day to the
  band: near an average = within 1.0 daily range (ADR) of it.
- 10-29: *"clear strong up move, pulls back into around moving averages, make higher lows, tightens then breaks out"*;
  bad charts: *"under all moving avg and not surfing it, no high lowers, no tightness"*, *"surfing DOWNWARDS"*,
  *"chopping around"*.
- 11-02, MTW (not a breakout): *"choppy around the 10/20ma and not really making higher lows"*; of an earlier date,
  *"it made a lower low the day prior"*. CODX / PENN (Qullamaggie's graded good setups): *"how are they not making
  higher lowers and surfing 10/20? Those fit perfectly"* — his drawn charts (`docs/methodology/operator_shared_charts/
  2026-11-02_codx_penn_base_reads/`): a rising line under the lows FROM THE BASE'S BOTTOM (a shakeout allowed); price
  holding around the 10/21-day EMAs across the base.
- 11-02: *"Yes, the chart should tighten leading to the breakout, not the full base"*.
- 11-07 / 11-09 sheets: *"looks extended"* (SIG, VFC, ASO), *"already gapped up"* (ONT). 11-10: the five quotes above.

## Why the 11-02 definitions misread CODX / PENN (read before writing these)
- "Rising lows" as three 5-day blocks each above the last: CODX's lows after its bottom go 249.6 -> 225.3 -> 204.3 ->
  255.8 — lower among themselves, all ABOVE a rising line from the 167.1 bottom. His "higher lows" is measured from
  the bottom, not block to block.
- "Riding" as every close for 10 days above a 10/20-day SIMPLE average: his charts carry EMA10 / EMA21, and CODX closes
  under the EMA10 on 18 of its 30 base days. His "surfing" is price holding AROUND the averages, not above them.
- Counting closes under / crosses of the average cannot separate the trio: MTW (his no) is cleaner than CODX (good) on
  every such count (`scripts/probes/_his_charts_1102/three_way.out`). So no gate below counts closes against an average.

## The gates (bars <= the watch night D; every threshold fixed here)
Shared terms: P = the pole top the list already finds (`v1_gates`' `pole_idx`, in [D-45, D-10]); the base = sessions
P+1..D; B = the session of the base's lowest low (first occurrence); ADR20 = the mean of (high-low)/close over the 20
sessions to D; EMA10 / EMA21 = exponential averages of the close seeded at the series' first bar (`ema_at`'s
arithmetic — the averages on his charts).

| # | Gate | Rule (pass when) | DoD shape | Source of the rule and of each number |
|---|---|---|---|---|
| S1 | `higher_lows` | B <= D-5: the lowest low of the last 5 sessions (D-4..D) is STRICTLY above low(B) | higher lows | his CODX/PENN line "from the base's bottom"; ABCL "no higher lows ... still flagging" (the bottom is still being made). 5 sessions = v1's own unit (the level window), his 10-28 approved rule |
| S2 | `no_lower_low` | no swing low i in [P+3, B-3] (low(i) <= every low of i-2..i+2, the 5-bar pivot wholly inside the base) with low(i) <= low(B) x (1 + 1.0 x ADR20). Strict: any undercut of such a low fails | higher lows | MTW "not really making higher lows" (21.09 then 21.05), "it made a lower low the day prior". 1.0 ADR = his 10-28 "near" band; a swing low far above the bottom (CODX 339 vs 167) is a pause on the way down, not a lower low |
| S3 | `rising_avg` | EMA10(D) > EMA10(D-5) AND EMA21(D) > EMA21(D-5), strict | surfing a RISING 10/20-day | "surfs the rising 10- and 20-day"; ABCL both EMAs falling; "surfing DOWNWARDS". 5 sessions = the same unit as S1 |
| S4 | `not_extended` | (close(D) / EMA10(D) - 1) / ADR20 <= 1.0 | surfing (price NEAR the average) | "looks extended", "already gapped up"; "surf ... near the MAs". 1.0 ADR = his 10-28 band |
| S5 | `tight10` | (max close / min close - 1 over D-9..D) / ADR20 <= 4.0 | tightening into the breakout | his 11-02 "tighten leading to the breakout, not the full base"; the measure is the one he confirmed (the list's `spread10_adr`). 4.0 = the tightest line on the printed 11-02 table that keeps >= 80% of his 48 yes labels (within 3: 28/48; within 4: 40/48, QM buys 230/245; `32_tight_recently.txt`) |

- The existing seven list rules are unchanged; S1-S5 are ADDED. The existing `ema21` floor (close no more than 0.6335
  daily ranges under the 21-day EMA) stays as the lower side of "near the average"; S4 is the upper side.
- A value that cannot be computed fails its gate.
- No gate reads a return, an outcome or anything after D.

## Calibration (declared; done BEFORE this commit, on three charts only)
`00_calibration_trio.py` -> `00_calibration_trio.out`: the three charts he read in his own words on 11-02.
| Chart | his read | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|---|
| CODX-1, D 2020-04-15 | fits perfectly | pass | pass | pass | pass (0.20) | pass (3.22) |
| PENN-2, D 2020-06-22 | fits perfectly | pass | pass | pass | pass (-0.07) | pass (1.74) |
| MTW, D 2026-10-30 | not a breakout | pass | **FAIL** (21.09 on 10-09, then 21.05) | pass | pass (0.31) | pass (2.37) |
- One change was made from this read, before any score: S2 was first written as "no swing low at all before the
  bottom"; it failed CODX-1 on a one-day dip at 339 on the way down to 167. The "within 1.0 ADR above the bottom" term
  was added to read his chart correctly. Nothing else moved.
- Known limit, stated now: only S2 fails MTW, on a 4-cent undercut. MTW's "choppy around the 10/20ma" is NOT encoded —
  no close-count measure separates it from CODX.
- CODX / PENN bars come from the scorecard fixture's file at nights that are not scored rows. No graded list row and no
  scored Qullamaggie buy was computed before this commit. The 29 graded names' bars were only COPIED into
  `tests/fixtures/breakout_list_grades_bars.psv.gz` (`01_build_grades_bars_fixture.py`, no gate computed).
- What was read beforehand: the printed 11-02 research (`01_gate_misses.txt`: the OLD v1 gates blocked 47 / 69 / 56 of
  the 269 — higher lows / surf / tightening; `32_tight_recently.txt`; `shape_gates_1102/RESULTS.md`).

## Populations
- **His list grades (n = 29):** `tests/fixtures/breakout_list_grades.py`, 29 name-nights (2026-11-05 / 11-06 / 11-09): 12 `no`,
  16 good or ok (8 good, 8 ok), 1 conditional. Every one passed the existing seven rules on its night (it was on the
  list), so only S1-S5 are computed on them. Never sampled on outcomes.
- **Qullamaggie's buys (n = 269):** `tests/fixtures/qm_breakout_scorecard/` — 269 dated breakout buys, 2017-2023, 26 big winners;
  263 pass the existing rules. His labels on 65 of them (`his_label`): ok-or-better vs no / EP-like.
- Nothing dated 2025 or later is read except the 29 graded names' own bars and MTW's. The sealed 2025-26 holdout is
  not opened. No trade result is read.

## What this does not answer
- Whether the gated list makes money (detection is judged on his grades and Qullamaggie's setups, never returns).
- Whether the names it would BUY look right to him — DoD (3), a fresh outcome-blind sheet, his grades.
- Anything about the entry, the stop, the exit or sizing — untouched.
- (1) is partly in-sample for S4: "extended" is defined from his words on the same sheets it is scored on. The check
  that it generalises is DoD (3), not this score.

## The bars (fixed now)
| # | Check | Bar |
|---|---|---|
| (1) | his `no` rows rejected by S1-S5 | **12 of 12** (the DoD) |
| (1b) | his good / ok rows kept | **>= 13 of 16** (80%, the DoD's own sheet bar) |
| (2) | Qullamaggie's buys on the list (existing rules AND S1-S5) | the only stated recall is the scorecard test's **263 of 269 and 26 of 26 big winners** — no other number is written in PLAN / SSoT / spec |
| (2b) | his ok-or-better labelled Qullamaggie buys kept | **>= 80%**; the no / EP-like labelled ones reported beside |
- Expectation, written now: (2) will FAIL at 263. The old shape gates each blocked 17-26% of the 269, and many of
  Qullamaggie's buys are reclaim days whose night-before chart sits under falling averages (the `ema21` floor was
  loosened on 11-02 to keep seven such ok-or-better buys). A night-before shape gate and "list every Qullamaggie buy"
  pull against each other; how much recall the shape is worth is the operator's fork, not ours.
- Reported with the score, not used to choose: a per-gate miss table (which gate drops which Qullamaggie buy / passes
  which `no`; alone and any), and a sweep of each number — S1 window 3/5/10, S2 band 0.5/1.0/1.5/none, S3 window
  3/5/10, S4 cap 0.5/1.0/1.5/2.0, S5 cap 3/4/5/6.

## Verdict rule (fixed now)
- PASS = (1) and (1b) and (2) and (2b).
- If a bar fails: ONE revision, written below as a dated amendment with its reason BEFORE the re-score. Allowed moves
  only: drop a gate, or move one number to another value of its declared sweep — and only onto a plateau (the
  neighbouring sweep value gives the same pass/fail on (1)), never a single-point peak (ADR 0023). Both scores are
  reported.
- What gets built on the branch: the gate set that meets (1), (1b) and (2b) is implemented in `breakout_v1.py` as list
  gates with the `no`-rejection test and a recall test pinned at the MEASURED recall, each dropped buy named with his
  label. If (2) fails at 263, that is NOT tuned away: the fork — accept the measured recall, or loosen a named gate at
  a named cost in `no` charts — goes to the operator with the miss table. Nothing merges or deploys from this card.
- If no set meets (1) and (1b) even after the revision: the functions stay as telemetry-ready code, the list is left as
  it is, and the result is reported as a FAIL with the charts that defeat each gate.

## RESULT — first score (2026-11-11, the pre-registered set; `02_score_first.out`)
**FAIL on all four bars.**
| Check | Bar | First score |
|---|---|---|
| (1) his `no` rejected (n = 12) | 12 of 12 | **11 of 12** — SIG ("looks extended") passes every gate |
| (1b) his good / ok kept (n = 16) | >= 13 | **6 of 16** |
| (2) Qullamaggie's buys kept (n = 269) | 263, 26 of 26 big winners | **108**, **11 of 26** |
| (2b) his ok-or-better Qullamaggie buys kept (n = 39) | >= 80% | **11 of 39 (28%)** |

Per gate (each one alone on top of the existing rules):
| Gate | `no` rejected (n = 12) | good / ok kept (n = 16) | Qullamaggie buys kept (n = 263 on today's list) | big winners (n = 26) | his ok-or-better buys kept (n = 39) | his no / EP buys removed (n = 16) |
|---|---|---|---|---|---|---|
| S1 `higher_lows` | 3 (DUOL, SPCE, ABCL) | 11 | 216 | 20 | 29 | 0 |
| S2 `no_lower_low` | 3 (CHTR, SPCE, ABCL) | 12 | 195 | 22 | 26 | 2 |
| S3 `rising_avg` | 3 (SPCE, ABCL, NVAX) | 11 | 168 | 13 | 25 | 3 |
| S4 `not_extended` | **9** (VFC, ONT, CHTR, DUOL, PLNT, ASO, MRNA, SPCE, OUST) | **13** | 227 | **25** | 31 | **10** |
| S5 `tight10` | 7 (a subset of S4's nine) | 13 | 246 | 24 | 32 | 6 |

What it means:
- **"Extended" is the read that matches his grades.** One gate — the close more than one daily range above the 10-day
  EMA — rejects 9 of his 12 `no`, keeps 13 of his 16 good / ok, keeps 25 of 26 big winners, and removes 10 of the 16
  Qullamaggie buys he himself called no or EP-like.
- **The three structure gates (S1-S3) still misread his pattern.** Each rejects only the 11-10 trio's members (3 of 12)
  and each drops 4-5 of the 16 charts he graded good or ok on the same sheets: RSKD (good), FNKO, MANE (ok) make their
  base's lowest low ON the list night; IAG, RSKD (good), FNKO, CVLT, MANE (ok) have a 10- or 21-day EMA lower than five
  sessions before. By these measurements they look like ABCL and NVAX. Whatever separates them to his eye is not a
  night-before "the bottom is 5 sessions old" or "both averages higher than last week".
- **A night-before shape gate costs Qullamaggie's buys heavily**, as expected: S3 alone blocks 95 of 263 (13 big
  winners). Many of his buys are reclaim days from under flat or falling averages.
- SIG passes all five (close UNDER its 10-day EMA, last-10 spread 3.17): his "looks extended" there is something these
  bars do not measure (S5 at 3.0 would reject it, but 4.0 does not — a single-point peak, not allowed).

## AMENDMENT 2026-11-11 (the ONE revision; written BEFORE the re-score)
- **Move: drop S1 `higher_lows`, S2 `no_lower_low` and S3 `rising_avg`. Keep S4 `not_extended` and S5 `tight10` at
  their pre-registered numbers (1.0 and 4.0). No number moves.** (The verdict rule's allowed moves; three drops, each
  for the same reason.)
- Reason: each dropped gate fails the (1b) floor by itself or in any pair — it removes 4-5 of his 16 good / ok charts
  to reject 3 `no` — so it does not encode his read; that is a definition defect, the same class as 11-02's, not a
  threshold to nudge (the declared sweeps move good/ok kept between 4 and 7 of 16, never near 13). S4 and S5 each keep
  13 of 16.
- Not a single-point peak: S4 at 1.0 / 1.5 / 2.0 and S5 at 4 / 5 / 6 give the same (1) reading in the first score's
  sweep rows apart from one `no` (10 vs 11 of 12 with S4 >= 1.5).
- Expected before the re-score, from the first score's per-gate rows: (1) will still FAIL — SIG, ABCL and NVAX pass
  S4 and S5 — and (1b) should pass at 13 of 16. So this revision cannot reach PASS; it is reported as the part of the
  shape that is measurable today. Under the verdict rule a set that misses (1) is NOT wired into the list.
- No new formulation is introduced here (not an allowed move). The rewrite of higher-lows and rising-average needs his
  eye first — see "Next" below, filled after the re-score.

## RESULT — the revision's re-score (2026-11-11; `02_score_revised.out`)
**FAIL. The verdict is final for this registration: no shape gate is wired into the list.**
| Check | Bar | First set (5 gates) | Revised (`not_extended` + `tight10`) |
|---|---|---|---|
| (1) his `no` rejected (n = 12) | 12 | 11 (SIG passes) | **9** (SIG, ABCL, NVAX pass) |
| (1b) his good / ok kept (n = 16) | >= 13 | 6 | **13** (IAG, PAR good and BHC ok dropped) — PASS |
| (2) Qullamaggie's buys kept (n = 269) | 263 | 108 | **225** |
| (2) big winners kept (n = 26) | 26 | 11 | **24** (APT 2020-06-17, JMIA 2020-11-18 dropped) |
| (2b) his ok-or-better Qullamaggie buys kept (n = 39) | >= 80% | 11 (28%) | **30 (77%)** |
| his no / EP-like Qullamaggie buys removed (n = 16) | reported | 13 | **11** |

- The amendment's expectation held ((1) fails on SIG, ABCL, NVAX; (1b) passes at 13).
- **CORRECTION to the amendment's "not a single-point peak" line (read from the revised sweep, n = 12 `no`):** in the
  two-gate set the 9 of 12 holds ONLY at the 1.0 cap. With `not_extended` at 1.5 or 2.0 it is **7 of 12** (MRNA +1.19
  and SPCE +1.48 pass; good / ok still 13 of 16, Qullamaggie buys 241-245); at 0.5 it is 10 of 12 but good / ok falls
  to 9 of 16. So two of the nine rejections sit on a threshold edge. `tight10` is flat from 4 to 6 (9 of 12).
- Of the five 11-10 paper buys, the revised set rejects MRNA, SPCE and OUST and PASSES ABCL and NVAX — ABCL is the
  chart he named.
- Built on the branch (per the verdict rule, a set that misses (1) is not wired): `breakout_v1.shape_gates` (pure,
  tested), `ENFORCED_SHAPE_GATES = ()` (empty: the list is unchanged), `tests/test_breakout_v1_shape_gates.py` (the
  measured numbers pinned by name; DoD (1) as a strict xfail — red today).

## Next (proposals; nothing here is decided)
- **The fork for the operator:** `not_extended` + `tight10` remove 9 of his 12 `no` and 11 of the 16 Qullamaggie buys
  he called no / EP-like, at the cost of 3 of his 16 good / ok and 38 Qullamaggie buys (2 big winners). Enforce it now
  as a partial fix, or wait for a set that also rejects ABCL / NVAX / SIG. His call (a hard gate; the filter list is in
  `02_score_revised.out`).
- **Higher lows and the rising average need his eye, not another threshold.** By every night-before measure tried,
  RSKD / FNKO / MANE / CVLT / IAG (his good or ok) read like ABCL / NVAX (his no). One sheet for him: those charts side
  by side, "what separates these?" — then the next registration is written from that answer.
- **"Extended" has a second form these bars miss** (seen on the chart only AFTER the score, not scored): SIG closed
  under its 10-day EMA on the list night after a straight run far above its 50-day. A candidate for the next
  registration: distance above the 50-day in daily ranges, or the run over the last ~20 sessions.
- **DoD (3), the bought-names sheet:** the renderer is ready (`11_render_bought_sheet.py`); it needs the newest
  night's list and bars from prod (`10_sheet_latest_list.sql`, read-only) — no 2026 bars for a whole list night exist
  locally.

---
# ROUND 2 (2026-11-11, after his regrade) — "stick with qullamaggie first"

## What changed
- His words on the contrast sheet: *"on second look the charts on first line can be interpreted as not making higher
  lows, what's fine, stick with qullamaggie first. On ABCL, i drew lines on the chart, it's clearly not making higher
  lows."* RSKD, FNKO, MANE, CVLT, IAG are now `no`: n = 29 graded = 17 `no`, 11 good / ok, 1 conditional.
- The binding bar is now Qullamaggie's own buys (n = 269; 263 on today's list; 26 big winners).

## Re-score of the two earlier sets on the new labels (`03_score_regraded.out`)
| Set | `no` rejected (n = 17) | good / ok kept (n = 11) | Qullamaggie buys kept (n = 269) | big winners (n = 26) |
|---|---|---|---|---|
| First (5 gates) | 16 (SIG passes) | 6 | 108 | 11 |
| Revised (`not_extended` + `tight10`) | 10 | 9 | 225 | 24 |
- `rising_avg` now agrees with his grades (rejects 8 `no`, drops 0 good / ok) — but it blocks 95 of Qullamaggie's 263.

## Diagnosis — why the first structure gates block Qullamaggie's buys (`04_diagnose.out`, `qm_blocked_sheet.png`)
- **The pole and the base are found correctly** (12 blocked buys drawn outcome-blind: the pole top is the visible peak
  on all 12). The lookback is not the defect.
- **He buys the turn of a short pullback.** On his 263 listed buys the base's lowest low is a median 10 sessions old,
  but 3 or fewer sessions old on 10% of them and 6 or fewer on 25% — `higher_lows` (the low at least 5 sessions old)
  rejects exactly those. The night before he buys, the pullback is often still in progress.
- **The 10-day EMA dips inside every pullback.** `rising_avg` asks both EMAs to be higher than 5 sessions ago; the
  10-day is lower on about a third of his buys (25th percentile -0.11 daily ranges) while the 21-day is still rising
  (median +0.27). A 5-session change of the 10-day measures the pullback itself, not the trend.
- **`no_lower_low`** fires on any volatile base that pauses once on the way to its low (68 of 263).
- **What his buys never do** (the measures with a hard edge on all 263): none closed above the pole top the night
  before (max -0.08 daily ranges); only 8 had the 21-day EMA below its value 5, 10 AND 20 sessions earlier; only 3 had
  the 21-day EMA more than one daily range under the 50-day; only 4 made the base's lowest low on the night itself.
- **Seven of his 17 `no` sit INSIDE Qullamaggie's night-before range on every measure tried** (SIG, DUOL, CVLT, OUST
  fully; RSKD, MANE, FNKO only by the low-made-today rule): the price of rejecting each is in `05_explore_rules.out`.

## AMENDMENT 2 (2026-11-11; written BEFORE its score; ONE score)
In-sample, stated plainly: the measures and numbers below were chosen after looking at both populations
(`04_diagnose.out`, `05_explore_rules.out`). Each number sits at the edge of QULLAMAGGIE'S buys (the 11-02 backward
method), not at the edge of his `no` charts. The out-of-sample check is DoD (3), the bought-names sheet.

Replaces the first five gates with four (`breakout_v1.SHAPE_GATES_V2`; bars <= D):
| # | Gate | Passes when | His shape | Why this number |
|---|---|---|---|---|
| V1 | `in_base` | close(D) <= the pole top's high | not extended ("price already well above its base") | none of his 263 listed buys closed above it |
| V2 | `ema21_not_falling` | the EMA21 is NOT lower than 5, 10 AND 20 sessions earlier (all three) | surfing a RISING average; ABCL's falling channel | no number: a sign at three scales; 8 of 263 fail |
| V3 | `ema21_vs_sma50` | (EMA21 / SMA50 - 1) / ADR20 >= -1.0 | the averages stacked, not rolled over | 3 of 263 fail; his lowest is -1.66 |
| V4 | `low_not_today` | the base's lowest low is not made on D itself | higher lows (a lower low on the list night) | 4 of 263 fail (1 big winner) |

Bars for amendment 2 (fixed now):
| # | Check | Bar | Expected from the exploration |
|---|---|---|---|
| (1) | his `no` rejected (n = 17) | 17 | **FAIL at 13** — SIG, DUOL, CVLT, OUST pass |
| (1b) | his good / ok kept (n = 11) | >= 9 | 9 (PAR, BHC dropped by V1) |
| (2) | Qullamaggie's buys kept (n = 263 listed) | the stated 263 and 26 of 26; "near" = >= 250 and >= 25 | ~249-250, 25 of 26 |
- Why not add gates for the last four: on these measures each costs Qullamaggie's buys — SIG by distance above the
  50-day: 16 of 263 (1 big winner); DUOL and OUST by more than 1.5 daily ranges above the 10-day EMA: 16; CVLT by a
  falling 10-day with the close under it: 17. With all of them, about 55 of 263 go. "Qullamaggie first" is read as:
  do not pay that without his word.
- Plateau check declared: V1's limit swept 0 / 0.25 / 0.5 / 1.0 and V3's -1.5 .. 0, reported with the score.
- Step 4 rule (the coordinator's): enforce only if every bar passes. (1) is expected to fail, so the expected outcome
  is NOTHING ENFORCED and a priced fork for the operator.

## RESULT — amendment 2 (scored once; `07_score_amendment2.out`)
**FAIL on (1): 13 of 17 `no` rejected — SIG, DUOL, CVLT, OUST pass. Nothing is enforced.** Every other number landed
where the exploration said.
| Check | Bar | First (5 gates) | Revised (`not_extended` + `tight10`) | Amendment 2 (4 gates) |
|---|---|---|---|---|
| his `no` rejected (n = 17) | 17 | 16 | 10 | **13** |
| his good / ok kept (n = 11) | >= 9 | 6 | 9 | **9** (PAR, BHC dropped by `in_base`) |
| Qullamaggie's buys kept (n = 263 listed) | 263; near = >= 250 | 108 | 225 | **249** |
| big winners kept (n = 26) | 26; near = >= 25 | 11 | 24 | **25** (SI 2021-01-22, by `low_not_today`) |
| his ok-or-better Qullamaggie buys kept (n = 39) | >= 80% | 11 | 30 | **38** (BMA 2019-08-09) |
| his no / EP-like Qullamaggie buys removed (n = 16) | reported | 13 | 11 | **0** |

Per gate (n = 17 `no`; n = 263 buys): `in_base` rejects VFC, ONT, PLNT, ASO, MRNA and blocks 0 buys;
`ema21_not_falling` rejects IAG, SPCE, ABCL, NVAX and blocks 8; `ema21_vs_sma50` rejects IAG, CHTR, SPCE and blocks 3;
`low_not_today` rejects FNKO, RSKD, MANE and blocks 4 (1 big winner).

Plateau: `in_base` at 0 and 0.25 read the same (13 of 17); at 0.5 it is 12 and at 1.0 it is 11 (ONT +0.31 and MRNA
+0.56 sit just above the pole top) — Qullamaggie's count does not move at any of them. `ema21_vs_sma50` reads 13 of 17
from -1.5 to -1.0 (249-250 buys); -0.75 adds OUST for 2 more buys.

What it means:
- **All five 11-10 paper buys but OUST are now rejected** (ABCL and NVAX by the falling 21-day, SPCE, MRNA), at a cost
  of 14 of Qullamaggie's 263 listed buys and one big winner.
- **It does NOT remove the Qullamaggie buys he called no / EP-like (0 of 16)**; the earlier "extended" gate removed 11
  of them but cost 38 buys.
- **The last four `no` cannot be rejected on night-before bars without paying in Qullamaggie's buys** (16-17 each on
  the measures tried; `05_explore_rules.out`). That is the operator's fork.
- In-sample: these four gates were chosen with both populations in view. The real test is the bought-names sheet.

Built: `breakout_v1.SHAPE_GATES_V2` computed by `shape_gates`; `ENFORCED_SHAPE_GATES` still `()`; the tests pin the
measured numbers by name; DoD (1) stays a strict xfail.

---
# ROUND 3 (2026-11-11) — one trend-context gate on top of amendment 2

## Why
The would-buy sheet under amendment 2 (list night 2026-11-10: 117 of 190 names survive, the top 12 drawn;
`bought_sheet.png`) failed the main loop's first pass (`13_my_first_pass_bought_sheet.md`): six of the 12 are
recoveries from a long decline sitting at or just over a FALLING 200-day, one a falling drift off a spike. The article's
setup is a leader's consolidation after a big move, not a recovery under a falling long-term average.

## AMENDMENT 3 (written BEFORE any score; each variant scored ONCE; `08_score_amendment3.out`)
Amendment 2's four gates + ONE of these, on bars <= D (SMA200 = the mean of the 200 closes to D; a name with fewer than
200 sessions — or 220 for the slope — has no long-term trend to read and does NOT fail):
| Variant | Passes when |
|---|---|
| T1 `above_200` | close(D) >= SMA200(D) |
| T2 `sma50_above_200` | SMA50(D) >= SMA200(D) |
| T3 `sma200_rising` | SMA200(D) > SMA200(D-20) |
| T4 `above_rising_200` | T1 AND T3 |
- Bars unchanged: `no` rejected 17 of 17 (n = 17); good / ok kept >= 9 of 11 (n = 11); Qullamaggie's listed buys kept
  >= 250 of 263 (n = 263); big winners >= 25 of 26 (n = 26).
- Stated now: amendment 2 alone already sits at 249 of 263, one under the bar, and an added gate can only lower it; the
  four `no` it passes (SIG, DUOL, CVLT, OUST) are not known to be under a falling 200-day. So a full PASS is not
  expected; the variants are reported for what each costs and removes.
- Pick rule (fixed now): among variants that keep good / ok >= 9 and big winners >= 25, the one that blocks the FEWEST
  additional Qullamaggie buys; a tie goes to the one rejecting more `no`. The sheet letters a variant removes are
  REPORTED, never used to pick (the sheet is the out-of-sample check). Plateau: T3's window reported at 10 / 20 / 40.
- Also reported per variant: how many of the 190 names of list night 2026-11-10 survive.
- Enforce only if a variant meets every bar; otherwise nothing is enforced.

## RESULT — amendment 3 (each variant scored once; `08_score_amendment3.out`)
**FAIL: no variant meets the bars, and by the pick rule none qualifies (every one drops big winners below 25).
Nothing is enforced.**
| Variant (on top of amendment 2) | `no` rejected (n = 17) | good / ok kept (n = 11) | Qullamaggie buys kept (n = 263) | big winners (n = 26) | list night 11-10 survivors (n = 190) | sheet letters removed (n = 12) |
|---|---|---|---|---|---|---|
| amendment 2 alone | 13 | 9 | 249 | 25 | 117 | - |
| T1 `above_200` | 13 | 9 | 233 | 23 (LCID 2021-10-25, QS 2021-10-29 go) | 104 | none |
| T2 `sma50_above_200` | 13 | 9 | 222 | 23 | 90 | none |
| T3 `sma200_rising` | 14 (adds DUOL) | **6** (AMPH, BILL, BLKB go) | 219 | 23 | 76 | B, F, G, H |
| T4 `above_rising_200` | 14 | **6** | 217 | 22 | 75 | B, F, G, H |
- Plateau (T3 / T4's slope window 10 / 20 / 40): the same reading at each — good / ok 6 of 11, Qullamaggie buys
  219 / 219 / 213 (T3), survivors 77 / 76 / 72. Not a peak; a consistent miss.
- 21 of Qullamaggie's 269 buys had no 200-day at D (young listings); they do not fail the gate.

What it means:
- **A long-term-trend gate is not Qullamaggie's rule.** 16 to 32 more of his own buys sat under the 200-day or over a
  falling one the night before (2020 recoveries — CCL, UAL, SAVE, ACB; and LCID, QS, both big winners).
- **It is not the operator's read either.** A rising 200-day drops three charts he graded good or ok (BILL, AMPH good;
  BLKB ok). BLKB is letter B of the amendment-2 sheet — a chart the main loop's first pass called a recovery under a
  falling 200-day, and he graded it ok on the 11-05 sheet.
- The only variants that remove any of the first pass's letters (B, F, G, H) are the ones that fail his own grades;
  E, L and J stay under every variant.
- `bought_sheet_a3.png` is rendered with T1 (the variant costing the fewest Qullamaggie buys) for the record only: it
  holds the SAME 12 names as the amendment-2 sheet (letters reshuffled), because T1 removes none of them.
- So the would-buy sheet's problem is not a missing trend gate that the labels support. What he sees in those charts
  is a question for him, on the sheet itself.
