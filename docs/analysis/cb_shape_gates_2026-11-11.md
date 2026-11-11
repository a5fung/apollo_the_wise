# Breakout v1 — Qullamaggie's shape rules as list gates: PRE-REGISTRATION (2026-11-11)

**Status: SCORED 2026-11-11 — FAIL (first set and the one revision; RESULT below). Pre-registered and committed BEFORE any score was run (commit `48bb6458`). Nothing is
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
