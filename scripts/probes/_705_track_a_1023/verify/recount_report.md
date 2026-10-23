**Verdict: FIX.** Every count reproduces and the per-label join differs on 0 of 854 labels. The one off-by-one is never-watched symbols (doc 53, mine 54). The doc text needs 9 fixes below, 3 of them in rules the doc does not state.

Evidence: `/Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/verify/recount_out.txt` and `recount_labels.tsv`. `run_recount.sh` regenerates the extracts in about 50 s. `recount.py` was written before I read `01_join_labels.py`, but four items (placebo, "not yet broken", distinct-event delta, chain count) only matched after I read it. Era B was filtered at read to discovery rows dated 2024-12-31 or earlier. No price, return or outcome column was opened. Nothing under `bdef_*` was opened (see the last list).

**Claims**

| claim | doc | mine | match |
|---|---|---|---|
| attributed labels (bought / not_yet / best / mixed) | 854 (662 / 125 / 59 / 8) | same | yes |
| grade words exploded | 669 / 129 / 64 | same | yes |
| labels with coverage, A (bought / not_yet / best) | 624 / 128 / 60 | same (all labels: 629 / 129 / 60) | yes |
| labels with coverage, B (bought / best) | 28 / 3 | same (all labels: 40 / 4) | yes |
| era split A / B | 811 / 43 | same | yes |
| coverage none / partial / full, A | 6 / 29 / 776 | same | yes |
| coverage none / partial / full, B | 13 / 8 / 22 | same | yes |
| screen dates mapped to a prior session (weekend) | 9 | 9, all era A | yes |
| symbol resolution (own / refetch_dropped / rename_map) | 783 / 15 / 13, 0 unresolved | same; dedupe_applied resolves 0 | yes |
| era A tl rows (first breaks) | 81,015 (20,650) | same | yes |
| era B tl rows (first breaks) | 41,200 (12,250) | same | yes |
| era B rows dropped at read | 174,495 + 328 | same | yes |
| era B watch rows dropped | 109,961 | same | yes |
| funnel A (none / never watched / no watch row / no event / matched) | 6 / 87 (84 untyped) / 140 / 72 / 506 of 805 (62.9%) | same | yes |
| funnel B | 13 / 5 (4) / 9 / 4 / 12 of 30 (40.0%) | same | yes |
| never-watched symbols | 53 | 54 (A 51 + B 5, minus NRGU and KWEB in both) | **no** |
| join A bought: matched, full-only, nearest is a retrigger, first break in window | 392/624, 384/601, 190, 334 | same | yes |
| join A not_yet | 86/128, 84/124, 44, 69 | same | yes |
| join A best | 32/60, 32/58, 19, 30 | same | yes |
| join B bought | 10/28, 9/20, 3, 10 | same | yes |
| join B best | 2/3, 2/3, 2, 2 | same | yes |
| other levels, matched | A com bought 412, not_yet 88; B bought com 12, k5 13, k10 9, full 9 of 28 | same numbers | yes (wording false, D6) |
| A bought nearest event: before / on / after / within [-2,+1] | 163 / 113 / 116 / 179, full histogram | same, histogram identical | yes |
| A bought nearest first break (n=334) | 170 / 33 / 131, 89 within | same | yes |
| A bought distinct events (n=297) | 108 / 100 / 89, 151 within | same only if the first label in file order sets the delta | yes (D3) |
| A not_yet (n=86) | 43 / 23 / 20, 43 within | same; true median 0.5 is printed as 0 | yes |
| A best (n=32) | 12 / 9 / 11, 16 within | same | yes |
| B bought (n=10) | 6 / 2 / 2, 5 within | same | yes |
| placebo sessions | 42,781 (13.5% on, 54.1% before, 32.4% after, 29.8% within) | blind run 43,822 / 45,274; exact once the t-range is applied | yes after D2 |
| "2.1×" on-the-day vs placebo | 28.8 / 13.5 | 2.13 | yes |
| watch row at s0: bought / not_yet / best / B bought | 176 / 50 / 17 / 8 | same | yes |
| of those with a trendline (C0_tl = 1) | 153 / 50 / 15 / 8 | same | yes |
| watch row anywhere in the window | 448 / 97 / 38 / 14 | same | yes |
| same base NOT yet broken at s0 (A bought / not_yet / best / B bought / B best) | 39 / 13 / 4 / 5 / 0 | 39 / 13 / 4 / 5 / 0 on the script's pole_date rule; 33 / 13 / 4 / 5 / 0 on base_id | yes, rule-dependent (D4) |
| same-day other tl rows, A bought | median 146, mean 162.7 | same | yes |
| same-day other first breaks | 29 / 40.9 | same | yes |
| ISO week, bought events: all rows / first breaks | 651 / 147 | same | yes |
| weekly stream A (254 weeks): all rows / first breaks | 205 / 53 | same | yes |
| weekly stream B (145 weeks): all rows / first breaks | 243 / 73 | same | yes |
| distinct events A: total (bought / not_yet / best), bought and not_yet both | 388 (297 / 80 / 30), 12 | same | yes |
| distinct bases / stocks | 288 / 147 | same | yes |
| labels per event (1 / 2 / 3+) | 308 / 54 / 26 | same | yes |
| bought events by year | 7 / 8 / 205 / 77 over 180 days, 88 weeks | same | yes |
| C1 among bought events vs stream | 11 (3.7%) vs 1.1% | 11 vs 1.14% | yes |
| era B events | 12 (10 bought, 1 in 2022 and 9 in 2023, 2 best), 11 bases, 10 stocks | same | yes |
| "199 drift-robust chains" | 199 | 199 is the number of distinct (symbol, 0/1 flag) pairs | number reproduces, meaning does not (D5) |
| control join values | SQM 10-05 (0), ROKU 06-18 (+2), MDGL 01-24 (-2) | same | yes |

**Discrepancies and causes**

| id | doc says | what is true | cause |
|---|---|---|---|
| D1 | 53 never-watched symbols | 54 | The doc's own `.txt` list has 54 entries (92 labels). |
| D2 | placebo rule as written in §9 | the blind run read 43,822 / 45,274, not 42,781 | The script restricts t to sessions whose whole window sits inside the E range (indices 302..1491) and excludes any attributed label of the symbol. The symbol set is the 200 bought symbols with coverage, not 205. §9 states none of this; with it applied I get 51,884 / 42,781 exactly. |
| D3 | distinct bought events 108 / 100 / 89 | those numbers need a rule the doc does not state | `drop_duplicates(['sym','E_tl'])` keeps the first label in file order. Closest-to-E gives 103 / 110 / 84 (on 37.0%, within [-2,+1] 54.9%). Min gives 102 / 102 / 93, max gives 116 / 100 / 81. All stay under 60%, so the target rule is unchanged. |
| D4 | "same base NOT yet broken" is 39 (6.2%) | 33 (5.3%) if "same base" means base_id | The script matches the candidate `pole_date` column to the watch row's pole_date. Six bought labels (g_1405 VIR, g_1634 CMCM, g_0919 PINS, g_1362 AMD, g_0679 SHOP, g_1686 HUYA) had a same-base break on or before s0 under a pole date that drifted a day. 26,910 of 81,015 tl rows have a base_id date different from `pole_date`. The not_yet vs bought direction holds (10.2% vs 5.3%). My blind attempts read 94 (base_id string against the watch pole_date, which fails under drift) and 38 (nearest event after s0). |
| D5 | "199 drift-robust chains" | not a chain count | `01_join_labels.py` line 545 uses `drop_duplicates(['sym','chain'])`, and `chain` is the 0/1 `retrigger_chain` flag. 147 symbols give 199 pairs because 52 have both values. Era B's 11 matches the base count only by coincidence. The drift-robust key is `base_id`, which is the 288. |
| D6 | horizontal levels "less" (k5 13, k10 9, full 9) | k5 13/28 is more than tl 10/28 and com 12/28 | Wording error. |
| D7 | SQM control "a FIRST break"; "one to two sessions before our tl event" | `retrigger`=0 but `retrigger_chain`=1: the same base_id fired E=10-04 (D 10-03), and 10-05 is the re-fire after the pole date drifted 09-19 to 09-20 | In the frame, both panes are stamped 2017-10-04 and the daily last close is 59.44, which is the 10-04 close (taskbar says 10-05 11:34). So the screen shows the state after our first firing. The doc's phrase holds only against E=10-05. |
| D8 | ROKU control "our line fired two sessions later" | E=06-14 (-2, retrigger) is equally near; the later-E tie rule picks 06-18 (+2) | The line had already cleared on 06-14 and failed. The control is a tie artefact, not a clean "label before the break". |
| D9 | frame check "96% recall, 1.8% false match" | the rule used (a AND b) has 94.0% recall (842/896) and 1.8% false match (398/22,218) | 95.6% is the ADR-only read, whose false match is 9.2%. |
| D10 | "the before-share is chance" | labels read 41.6% before against 54.1% for the placebo | The labelled before-share is 12.5 points lower and the on-the-day share 15.3 points higher, so mass moves from before to on. |
| D11 | (cosmetic) | the script header says "22 labels before 2017-03-02" and the output shows 6; `:+.0f` prints the not_yet median 0.5 as "+0" and the 3.75 quartile as "+4" | Stale comment and number formatting. |

**Sensitivity, no fix needed.** 3,636 of 20,650 era-A first breaks (17.6%) carry `retrigger_chain`=1, i.e. drift re-fires. On a chain-first definition the era-A weekly median is 43 rather than 53 (era B 59 rather than 73). "One in nine first breaks" reads about "one in seven". The bought nearest chain-first split is n=331, 52.0% before / 7.9% on / 40.2% after, against the doc's 50.9 / 9.9 / 39.2.

**Positive controls against the frame report** (`grades_frame_check.tsv` and `03_frame_check.txt`; all three rows have `confirmed`=1, daily_tab=1, screen date equal to the label's, `triple_agree`=1)

| frame | report row | join | hand read |
|---|---|---|---|
| g_0466 SQM | ADR 5.2, diff 0.01, 2 axes, price_ok=1 | E 10-05, delta 0 | Bars match the doc (10-03 close 57.50, 10-04 close 59.44, 10-05 high 61.00, 09-20 high 63.80). His 56.07 line is visible. See D7. |
| b1_00 ROKU | present with src=b1 (it lives in `frames/`, not `frames_grades/`); ADR 3.7, diff 0.16 | E 06-18, +2, retrigger | Weekly pane is active, so the doc's disclosure is right. Hourly pane runs 06-14 to 06-16. base_len is 45, the rule maximum. See D8. |
| g_0957 MDGL | ADR 5.4, diff 0.13, 1 axis | E 01-24, -2, retrigger | Daily chart, December gap and a flag at 290–310 with a line at 258.26. Highs 306.94 / 313.63 / 313.93 match. An earlier first break exists on 01-11, with retriggers on 01-13, 01-18, 01-23 and 01-24. My bar prints stop at E. |

**Exact fixes**

1. §2a: "53 symbols" becomes "54 symbols".
2. §2f: delete "199 drift-robust chains" and era B's "11 chains". Keep "288 distinct bases (base_id, the drift-robust key)". Drop the `distinct chains` item from `01_join_labels.py` line 545 or key it on `base_id`.
3. §2d: state the rule used ("same base = same candidate pole_date"), or change it to `base_id`. Under `base_id` the A bought cell is 33 (5.3%) and the other cells are unchanged. Add that six bought labels are drifted-pole bases already broken.
4. §9 placebo: add three conditions. t must have its whole [t-10, t+20] window inside the era's E range. Symbols are those with a bought label and coverage not none (200). Excluded t is within ±20 sessions of any attributed label of the symbol, any grade.
5. §2c distinct-events row: say the delta is the first label in file order, or switch to closest-to-E (103 / 110 / 84; on 37.0%, within [-2,+1] 54.9%). Add that the not_yet median 0.5 is rounded.
6. §2b: replace "the horizontal levels less (...)" with "the horizontal levels mixed (era B bought: k5 13, k10 9, full 9 of 28, against tl 10)".
7. §2g: SQM becomes "retrigger flag 0 but chain flag 1; the same base fired 10-04; the frame's last bar is 10-04". ROKU gets "tie with the 06-14 event at -2; the later-E rule picked +2".
8. §9 and §0: "96% recall" becomes "94% recall (842/896; 95.6% is the ADR-only read)". "The before-share is chance" becomes "the before-share is lower than the placebo (41.6% vs 54.1%) and the on-the-day share higher (28.8% vs 13.5%)".
9. §10: add the 3,636 / 20,650 drift re-fire note with the chain-first weekly median of 43. Fix the stale "22 labels" comment in the script header.

**Not recounted, by design.** I did not open `bdef_*`, which carries `entry_date`, a forward date. So these remain unverified:
- §2c second anchor (109 / 98 / 89.9% / +14).
- The §2e R1/R2 table and the base rates.
- The "R1" cells of the controls.
- "published fills 53 / 63 a week".