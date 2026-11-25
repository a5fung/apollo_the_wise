# Breakout v1 (#717) — does the chart TIGHTEN INTO THE BUY? Pre-registration, 2026-11-25

**Status: FROZEN before any candidate below was computed on any chart.** Research only, $0, offline. No production
code, no list rule, no deploy changes with this file. Any list-rule change still goes to the operator
(`docs/setups/CHANGE_PROCESS.md`, hard-gate sign-off). Detection is judged on Qullamaggie's buys and the operator's
chart grades, never on returns.

## 0. Why

- Breakout v1 (paper) bought VOR on 2026-11-23; stopped 11-25. Operator: *"the chart looks random to me, i don't see
  any pattern, any breakouts, there's no pattern"*.
- Our base detector (`breakout_v1.range_levels`, recorded as `gates.range`, never a gate) found no base on VOR — but a
  found-base REQUIREMENT loses Qullamaggie's buys: base found on 190 of 269 dated buys and 20 of 26 big winners
  (`scripts/probes/_vor_1125/01_range_on_qm_buys.out`). Dead as a gate.
- His markup of VOR beside the six big winners with no found base (`docs/methodology/operator_shared_notes.md`
  §2026-11-25; `docs/methodology/shared_images/2026-11-25_vor_vs_qm_no_base_markup.png`): *"many of these charts are
  messy ... SKLZ, QS and maybe OSTK have some higher low / tightness going into it so perhaps they are better. VOR is
  just a wide flat range."*
  - VOR: a flat box, top ~21.2, bottom ~17.2, no tightening.
  - SKLZ (buy day 2021-01-05): rising lower line under a falling upper line — converging.
  - QS (buy day 2021-10-29): falling upper line over a flat lower line.
  - OSTK (buy day 2021-01-22, "maybe"): rising lower line.
  - APT (2020-06-17), MDB (2020-09-21), JMIA (2020-11-18): no marks.
- The question: is there ONE measurable reading of "the gap between the top and the bottom narrows going into the
  buy" that (1) keeps Qullamaggie's buys, (2) fails VOR, (3) agrees with the operator's earlier chart grades?
- NOT the question: a blanket higher-lows rule. That gate was removed 2026-11-02 on his CODX / PENN read. Every
  candidate below passes on EITHER side narrowing (lows rising OR highs falling OR both), never on rising lows alone.

## 1. What has ALREADY been seen (so "frozen before any measure" is stated honestly)

Nothing in section 2 has been computed on any buy, graded chart or VOR. But these adjacent results are known to the
author and bound what is worth testing:

| Already known | Source | Consequence here |
|---|---|---|
| The three right-edge tightness gates already in `breakout_v1.py` (`SHAPE_TIGHT_GATES`: `range_contract`, `tight_closes5`, `tight_run3`) FAILED on these same buys and labels on 11-11, each stacked ON TOP OF that day's amendment 2 (which alone kept 249 of 263 listed buys, 25 of 26 big winners, 11 of 13 good-ok): kept 203 / 204 / 112 buys, 21 / 20 / 11 big winners, 2 / 6 / 0 good-ok. The `range_contract` rule standing alone blocked 56 of the 269 | `docs/analysis/cb_shape_gates_2026-11-11.md` amendment 4 | They are NOT candidates. They read the last 3-5 days; his 11-25 lines span the whole base. Carried only as reference rows (re-printed, not re-judged). |
| `higher_lows` (base bottom older than 5 sessions) — removed as a gate 11-02 | spec change log | Not a candidate; no candidate may reduce to it. |
| Wide-and-loose study: 40-odd box / churn / swing measures on 48 graded charts and the 757 buys; `b10_prev30` (10-day box over the prior 30-day box) had the best separation of wide-loose `no` from `ok` (AUC 0.97) but at its line 8 ok charts also failed | `scripts/probes/_717_wideloose_1114/02_study.out` | Candidate C1 is a NEIGHBOUR of `b10_prev{N}` (different windows, half-vs-half). Its (c) reading on the 48 historical charts is therefore weak evidence; its (a) and (b) readings are new. |
| The signed context check `lower_line` (re-widening swing + flat-or-falling lower line) was FIT on the historical graded charts; it flags COUP, DVAX, MELI, RRC, TDOC, TWTR, WPX | `_717_lowline_1114/02_score.out`; `CONTEXT_GATES` | Those 7 are already OFF the list. (c) is reported both with and without them. |
| The six big winners with no found base are APT, MDB, JMIA, SKLZ, OSTK, QS; he marked three as better and left three unmarked | `_vor_1125/01_range_on_qm_buys.out`, his markup | Bar (a) still requires every big winner the list keeps — marked or not. A measure that matches his eye can fail (a). That outcome is pre-worded in section 5. |
| VOR's chart, his box and the six charts have been looked at (image), not measured | his markup | VOR is one in-sample chart: bar (b) is a necessary check, not evidence of generality. |

## 2. Candidates (exact definitions; bars <= D only)

Shared conventions, all candidates:
- `D` = the watch night (the session before the buy day `E`). Only bars with index <= D are read. Highs and lows in
  natural log.
- A window of N sessions = bars D-N+1 .. D.
- Swing points = `breakout_v1.swing_pivots(h, l, k=SWING_K=3)` on the window (confirmed pivots only), reused verbatim.
- A non-finite input, or fewer bars than the reading needs, gives verdict **`unscored` = PASS** (a young or
  short-history name is never removed by this reading — the `lower_line` convention). Unscored counts are printed
  per cell; a cell where more than 10% of the 269 are unscored is void.
- Each candidate gives ONE boolean per chart per grid cell: `contracts` (pass) or not (fail).
- The grid is closed: 4 candidates, **51 cells** in total. No cell, window, threshold or candidate is added after the
  first score. A later idea is a new pre-registration.

### C1 `box_narrows` — the newer half of the base is narrower than the older half (pivot-free)
- His words: VOR *"just a wide flat range"* (the box is as wide at the end as at the start) vs *"tightness going into it"*.
- For n sessions: `new` = max(high) - min(low) over D-n+1..D; `old` = the same over D-2n+1..D-n (log).
  `ratio = new / old`.
- Pass when `ratio <= T`. Needs 2n bars and `old > 0`, else unscored.
- Grid: n in {10, 15, 20} x T in {0.6, 0.7, 0.8, 0.9, 1.0} = 15 cells.
- Reuse note: a neighbour of the wide-loose study's `b10_prev{N}` (section 1).

### C2 `lines_converge` — his two drawn lines, fitted, get closer toward D
- His markup: SKLZ rising lower line + falling upper line; QS falling upper over flat lower; OSTK rising lower;
  VOR two flat lines.
- Lower line: `breakout_v1.lower_line_slope`'s construction — a least-squares line through the confirmed swing LOWS
  of the last N sessions plus the lowest low of the bars after the last confirmed pivot. Upper line: the mirror — the
  confirmed swing HIGHS plus the highest high of the bars after the last confirmed pivot. x = session position in the
  window (0 .. N-1).
- A line with fewer than 2 points is horizontal: through its one point, or through the window's min low / max high
  when it has none.
- `gap(x) = upper(x) - lower(x)`. `ratio = gap(N-1) / gap(0)`.
- Pass when `ratio <= T`. `gap(0) <= 0` (lines crossed at the start) = unscored. `gap(N-1) <= 0` with `gap(0) > 0`
  (lines met before D) = pass.
- Grid: N in {30, 40, 60} x T in {0.5, 0.65, 0.8, 0.95} = 12 cells.
- Reuse note: `lower_line_slope` and `swing_pivots` reused; the signed `lower_line` context check reads the lower
  line's slope alone (flat-or-falling, with a re-widening swing) — C2 reads the GAP, so a flat lower line under a
  falling upper line (his QS) passes.

### C3 `swings_shrink` — the last swings are small against the base's biggest swing
- His words: *"higher low / tightness going into it"* — each pullback smaller than the one before; VOR's swings
  travel the full box to the end.
- `legs, _ = breakout_v1.swing_legs(h, l)` on the last N sessions (the last leg = the move from the last confirmed
  pivot to the extreme since it, as the function defines). `ratio = mean(the last 2 legs) / max(all legs)`.
- Pass when `ratio <= T`. Fewer than 3 legs = unscored.
- Grid: N in {30, 40, 60} x T in {0.4, 0.5, 0.6, 0.7} = 12 cells.
- Reuse note: `swing_legs` reused; a relative of `rewiden_v3` (which reads swings that WIDEN again after shrinking;
  C3 reads whether they shrank at all).

### C4 `daily_range_shrinks` — recent days are narrower than the base's days
- His words: *"tightness going into it"*; 11-02 *"the chart should tighten leading to the breakout, not the full base"*.
- `r(i) = (high - low) / close`. `ratio = mean r over D-9..D / mean r over D-9-m..D-10`.
- Pass when `ratio <= T`. Needs 10 + m bars, else unscored.
- Grid: m in {20, 30, 40} x T in {0.7, 0.8, 0.9, 1.0} = 12 cells.
- Reuse note: the base-scale version of `range_contract` (5 days vs the 5 before, known FAIL). If C4 fails the same
  way, day-range tightness is closed as a gate at every scale tested.

### Reference rows (printed, never eligible)
`range_contract`, `tight_closes5`, `tight_run3`, `tight10`, `higher_lows`, `gates.range` found-base — each at its
constant in `breakout_v1.py`, STANDING ALONE on the same populations, so the new readings sit beside the known ones.
These rows will NOT reproduce the 11-11 figures (203 / 204 / 112), which were stacked on amendment 2 — that
difference is expected, not a runner defect.

## 3. Populations and labels (located and counted; none measured)

| Set | Where | n | Composition |
|---|---|---|---|
| Qullamaggie's dated breakout buys | `tests/fixtures/qm_breakout_scorecard/buys.tsv` + `bars.psv.gz` (loader: `tests/test_breakout_v2_stage1.py` fixture `scorecard`) | 269 | 2017-2023; 26 big winners; the current list (LIVE `v1_gates` at D) keeps 218 per the 11-25 probe — the runner re-reads this count and the listed big-winner count from the gates; neither is assumed |
| His 11-25 markup | `operator_shared_notes.md` §2026-11-25 | 7 | better: SKLZ, QS; maybe: OSTK; bad: VOR; unmarked: APT, MDB, JMIA. The six Qullamaggie charts are rows of the 269 (D = the session before the buy days in section 0) |
| VOR | `scripts/probes/_vor_1125/vor_bars.psv` | 1 | D = 2026-11-20, bars through 11-20 ONLY (185 bars; the file runs to 11-24 — later rows are dropped before any reading) |
| His grades on live list charts | `tests/fixtures/breakout_list_grades.py::BREAKOUT_LIST_GRADES`, bars `tests/fixtures/breakout_list_grades_bars.psv.gz` (41 of 41 keys have bars, >= 130 each, none past the list night) | 41 | no 23, ok 7, good 6, conditional 5. By sheet: 11-06 sheet 12 (5 no / 3 good / 3 ok / 1 cond), 11-05 sheet 12 (7 / 3 / 2 / 0), 11-11 would-buy sheet 12 (6 no / 2 ok / 4 cond), 11-10 live buys 5 (5 no) |
| His grades on historical list charts | same file `::MODEL_PICK_GRADES`; bars: 48 rows in `scripts/probes/_717_wideloose_1114/graded_rows.tsv` + `graded_windows200.npy`; the 12 lower-line-sheet rows from the era-A store exactly as `_717_lowline_1114/03_sheet.py` reads them (`cb702_pre_v2`, calendar asserted < 2025) | 60 | no 26, ok 22, conditional 11, good 1. By sheet: model 12 (7 no / 4 ok / 1 cond), template 12 (8 no / 1 good / 2 ok / 1 cond), 50-day 12 (5 / 4 ok / 3 cond), context 12 (5 / 3 ok / 4 cond), lower-line 12 (1 no / 9 ok / 2 cond) |

Label rules, fixed now:
- **Good side** = `good` + `ok`. **No side** = `no`. `conditional` is printed in its own column and counts on neither side.
- **The lower-line sheet (12) is reported apart** and is outside the (c) bar: it was drawn AFTER a rising-lows check,
  so its 9 ok charts are pre-selected toward passing. Headline historical set = the other 48: no 25, good/ok 14, conditional 9.
- **Reason-matched `no`** (the `no` charts a contraction reading is expected to catch), by a mechanical rule on
  `operator_words`, case-insensitive regex `wide|range|chop|loose|lose\b|tight|higher low|lower low|random`:
  - live list: 7 of 23 — IAG, FNKO, RSKD, CVLT, MANE (the 11-11 regrade, *"can be interpreted as not making higher lows"*), ABCL, OUST.
  - historical (48): 14 match; OCGN is removed by name (*"why is it so tight, looks suspicious"* — the opposite
    complaint), leaving **13**: LCID, SWAV, FLGT, MVIS, DVAX, DOCN, THC, CDE, TWTR, TDOC, MELI, RRC, WPX.
  - The other `no` charts (late, extended, gapped, downtrend, bare "no") are NOT expected to fail a contraction
    reading; their fail rate is printed, not barred.
- **Not used for (c):** the `his_label` column of `buys.tsv`. Qullamaggie's buys are ground truth, not graded
  examples; they enter only through bar (a).
- **Sealed data:** `cb702/` (the 2025-26 research holdout, #710) is never opened. The only bars dated 2025 or later
  that are read are the 41 graded live-list names' own fixture bars (the 11-11 precedent, `cb_shape_gates_2026-11-11.md`
  §Populations), VOR's, and — for (d) only — the bars of names on the prod list on the nights in (d).

## 4. Bars, in priority order ((a) outranks (b) outranks (c))

**(a) Keep Qullamaggie's buys — the gate on everything else.** Let `L` = dated buys the current list keeps and `BL` =
big winners among them, both read from the live gates at run time. A cell passes (a) only if ALL hold:
1. It loses **zero** of the `BL` listed big winners.
2. It passes **>= 256 of the 269** dated buys standing alone (95%).
3. It keeps **>= ceil(0.95 x L)** of the listed buys (208 if L = 218).
- Printed with every cell: passed of 269, of L, of 26 big winners, of BL; every big winner failed, by name; unscored count.
- The 95% line is the caller's and matches the 11-11 precedent (250 of 263). No different bar is set: his words
  (11-11 *"stick with qullamaggie first"*, *"buy his setups period"*) argue for no looser one.
- Reported, not barred: the 488 undated positions (`buys_undated_widened.tsv`; pass on any night of the buy window).

**(b) VOR fails** at D = 2026-11-20. One chart, necessary only. Printed also at its list nights 11-13, 11-23, 11-24 (reported).

**(c) Agreement with his eye.** A cell passes (c) only if ALL hold:
1. Markup: SKLZ and QS both pass. OSTK ("maybe") and APT / MDB / JMIA (unmarked) are printed and count for nothing here.
2. Good side kept: live list >= 11 of 13; historical >= 12 of 14.
3. Reason-matched `no` failed: >= 4 of 7 live AND >= 7 of 13 historical.
- Printed as a lean, never a verdict: fail rate on reason-matched `no` / fail rate on good-ok, per set; the same
  with the 7 charts the signed `lower_line` check already removes left out; all-`no` fail rate; conditional column.

**(d) Reported, not a bar:** share of the prod list (`mi_breakout_v1_list`, scan dates 2026-11-16 .. 11-24, read-only
session) each plateau cell would remove, per night, with bars from `mi_daily_closes` up to each scan date only. If
prod is not reachable, (d) is skipped and said so. No outcome after the list night is read.

## 5. Choosing a threshold, and the pre-worded results

- **Plateau rule.** A plateau ON A SET OF BARS = within one candidate at one window, a run of >= 3 CONSECUTIVE grid
  thresholds that each pass every bar in that set. The chosen threshold is the middle of the longest run (an even
  run: the looser of the two middle values — looser = the HIGHER T, which keeps more buys). A lone passing cell or a
  run of 2 is a peak and is NOT a plateau. Printed beside it: whether the adjacent window(s) also hold a run (support,
  not a bar).
- If more than one candidate has a plateau: the one keeping the most of the 269; tie -> the most reason-matched `no` failed.
- **Correct-build check before any label is read:** the runner must reproduce 190 of 269 base-found, the listed count
  and the listed big-winner count from the live gates. Each candidate's RATIO (not its verdict) is also checked on two
  synthetic series: a flat box of constant width with equal daily ranges, ending on a completed swing, must read
  about 1.0 on C1, C2 and C4 and at least 0.75 on C3 (its last leg is provisional); a converging wedge whose swings and daily ranges both shrink toward
  the end must read clearly below the flat box on all four. A mismatch is a runner defect, fixed before scoring.
- **Each cell is scored once.** A crash-fix-rerun is disclosed with the diff.
- **No hand reads.** Every verdict above is mechanical. If any chart has to be read by eye to settle a result, the
  rule for that read is written first and a blind second reader repeats it.

Pre-worded outcomes — ONE result is reported for the study: read the table top-down across all candidates, first match wins:

| Result | Wording |
|---|---|
| Some candidate has a plateau on (a), (b), (c) | **"PROPOSE: `<candidate>` at `<window, threshold>` keeps `<x>` of Qullamaggie's 269 buys and every big winner the list keeps, fails VOR, keeps `<g>` of your good/ok charts and rejects `<n>` of the charts you called wide / choppy / not tight. It would remove about `<d>`% of a recent list. Your call whether it becomes a list rule."** Nothing is enforced by this study. |
| Else: some candidate has a plateau on (a) and (b) | **"PARTIAL: `<candidate>` keeps Qullamaggie's buys and fails VOR but does not match your earlier grades (`<numbers>`). Not proposed as a rule; a sheet of what it would remove is the next step if you want it."** |
| Else: some candidate has a plateau on (b) and (c) | **"NULL (expected): a reading that matches your eye on VOR / SKLZ / QS loses Qullamaggie buys — `<names of big winners lost>`. His messy buys (APT, MDB, JMIA were unmarked) are the cost. No contraction GATE is proposed. Next step: read the same measure as a ranking input (which names the paper book takes first), which loses no buy — a separate pre-registration."** |
| Else: (a) fails somewhere and nothing above matched (no plateau, or lone peaks only) | **"NULL: no stable reading of tightening-into-the-buy separates VOR and your `no` charts while keeping Qullamaggie's buys. Nothing proposed. VOR stays a labelled example."** |
| Else: every cell passing (a) also passes VOR | **"NULL: every reading that keeps his buys also keeps VOR — on daily bars VOR is not distinguishable from buys he took."** |

A NULL here is a verdict on these four readings as LIST GATES, not on contraction as an idea.

## 6. What this cannot answer

- **Returns.** No trade result, forward move or stop outcome is read. Whether a tighter list makes money is not tested.
- **Regime.** The 269 buys are 2017-2023; VOR and the 41 live grades are November 2026, a market the operator reads
  as a bear phase. A reading sized on the first may behave differently on the second; (d) shows the size of the cut,
  not whether the cut is right.
- **Why Qullamaggie bought the messy ones.** The panel shows holdings, not reasons. APT / MDB / JMIA may be bought on
  something daily bars do not show (intraday tightness, news, theme).
- **Intraday tightness.** Daily bars only.
- **Generality from VOR.** One in-sample chart; (b) can only falsify.
- **Fresh agreement.** Most graded charts have already been used to fit or judge other gates (section 1); (c) is
  agreement with known labels, not an out-of-sample test. A new blind sheet would be the out-of-sample check, and
  only after a PROPOSE.
- **Ranking.** Whether contraction should order the list rather than gate it is a separate question (named as the
  next step under the expected NULL).

---
# RESULT (scored once 2026-11-25; appended after scoring — the sections above are the frozen plan, sha256 20b36c4a…)
**NULL as a list gate.** 0 of 51 settings pass bar (a). The nearest, C3 `swings_shrink` w60 T0.7, keeps 252 of 269 and 207 of 218 listed, loses BLDP 2020-06-29 and keeps VOR. Every setting that fails VOR loses 3 to 23 listed big winners. No plateau exists. Output: `scripts/probes/_contraction_1125/01_score.out`; sheet `sheet.png`.
- **The readings lean his way:** `swings_shrink` w40 T0.6 rejects 11 of 13 historical reason-matched no charts, against 3 of 14 good/ok (`01_score.out:146`). As a gate, each reading costs Qullamaggie buys.
- **Verified** by a separate Fable pass that recomputed all 51 rows clean-room from bars truncated at D, with 0 mismatches. A threshold outside the grid doesn't rescue it either: the closest, `lines_converge` w30, still loses JMIA and APHA.
- **Record gaps (they cannot flip a NULL):**
  - The prod fetch was made opt-in after the classifier denied it, and the run was repeated. That repeat is not in the script's DEVIATIONS block.
  - Bar (d), the cut rate on the prod list, was skipped.
  - The plan's freeze is shown by a file time only.
  - The swing and line readings are phase-sensitive on a synthetic flat box.
- **Next (pre-worded NULL-expected branch):** tightening as a RANKING input, under its own pre-registration. That is his call.

## What this does not answer
See §6: returns are not read, the regime differs (buys from 2017-23 against a Nov 2026 list), intraday tightness is not measured, and agreement out of sample is not tested. A NULL here judges these four readings as list gates; it is not a verdict on contraction as an idea.
