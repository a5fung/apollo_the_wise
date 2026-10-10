# #594 step 0 — all 45 rulings scored: the ten new ones added no catches, and the read still does not beat the extension rule

**MEASUREMENT ONLY. No rule, threshold, filter or trade behaviour was changed or proposed.** His labels
are ground truth and are never scored themselves. Any change this implies is his call (THE LINE).

*Corrected 2026-10-10 after an independent check: (1) a forward result was on screen when he ruled,
so the 32-of-38 agreement is no longer read as evidence for his eye; (2) the lookback-window facts now
use the live gate's own cap of 50, not only 75; (3) four stored bar series are not clean and are now
stated; (4) the rule-era sentence is corrected; (5) the "which field leans" sentence is corrected.
New numbers come from `scripts/probes/_594_rescore/fix_checks_out.txt`.*

## The answer

- **The ten new rulings added no catches (0 of 4 new bad charts), and the supply read still does not beat the extension rule: it catches 5 of his 25 condemned charts against the live gate's 7, and of the 10 bad charts the system alerted HIGH it catches 0. Recommendation: dead end as a filter; keep labelling, outcome-blind from sample #4 — his 45 verdicts were given with the 20-day result on screen.**
- **No rule scored here loses a real EP or a chart he approved** — not the live extension gate, not the 20-session run-up, not the supply read: 0 of 31 real EPs, 0 of 14 approved dates, under all four. (A fifth variant, the live gate's own formula read over 20 sessions at today's cap of 50, would lose 2 of 31 and 2 of 14 — facts in "The one fork the numbers touch".)
- **They also catch little of what he condemned: 5 to 9 of 25** (supply read 5, live gate 7, 20-session run-up 9), so coverage fell again, 43% → 36% for the run-up rule the last two re-scores used.
- **The chart read (the supply ladder) is worse than the extension rule, and adds nothing the run-up number alone does not already see.** Its count of 5 moves to 6 if one stored series (QH) is repaired, still under the live gate's 7 (see "Four stored series").
- **The sharper cut: of the 10 bad charts the live system actually alerted HIGH, the run-up rule catches 1 and the supply read 0.** Eight of the run-up rule's nine catches had no alert row, and all eight are session-1 names the live stack rejected on their own dates (found by the 08-25 study); the bad charts that got through are the ones nothing here sees.
- **His agreement with the later move (32 of 38) does not show his eye beats the rules.** A forward result was printed beside the charts when he gave each verdict: the 20-session result in the last three sessions (30 verdicts), the 5-session return in the first (15 verdicts) (see "What he saw").
- **Action: one question for him, at the bottom.**

## Population (composition first)

| population | n | what it is |
|---|---|---|
| rulings | **45** | 4 sessions (08-25: 15 · 09-06: 10 · 09-23: 10 · 10-05: 10); scanned dates 2026-04-01 → 2026-08-20 |
| — condemned (BAD_CHART) | **25** | 21 in the 09-23 set + **4 new** (AEVA, RUM, IBTA, HURN) |
| — approved (GOOD 8 · OKISH 5 · OKISH_EARLIER 1) | **14** | 9 in the 09-23 set + **5 new** (BLZE, CDNA, MAN, KRO good; HPE ok) |
| — neither (wrong day 4 · wrong stage 1 · no setup 1) | **6** | kept apart, never counted as rejects; RXT 06-16 is new |
| — dates he pointed at without ruling | 4 | flags, not labels (CGEM 06-22, MXL 04-24, VEEE 07-13, **RXT 05-07 new**) |
| real EPs (RULE 0 bar) | **31** + 3 excluded | **PENG 2026-10-07 added since 09-23's 30**; 6 named by him, **25 picked because they were ≥10R winners** |
| bars | 74 tickers, 74,295 rows | prod `mi_daily_closes`, 2021-09-27 → 2026-10-09, pulled once; 0 unreadable dates, 0 null bars; prior bars per ruled date: median 1,161, min 136 (MRLN 06-05, of which 80 are a different company's — see "Four stored series") |

**Three traits that would mislead if not said first:**
- **His labels are tangled up with what happened next, twice over.** Samples were drawn from names that collapsed or ran, and a forward result was printed beside each chart when he ruled (see "What he saw"). So the verdicts line up with the outcome: the condemned names fell in 21 of 24 (median −43% over 20 sessions), the approved ones rose in 11 of 14 (median +21%). Catching "bad charts" is therefore partly catching "names that later collapsed".
- **The real-EP bar is a list of winners** (median +55%, 29 of 30 rose >20%). "Lost 0 of 31" is a statement about winners; it cannot show the rules are free on a loser that looks like a winner.
- **13 of the 25 bad charts have no alert row** (11 are session 1, which the live stack rejected on their own dates, found by the 08-25 study; plus IBTA and HURN, which the 10-05 page shows as scored under 50). No alert row means not alerted; it is not proof that a gate rejected each one. 10 got a HIGH alert, 2 a MODERATE.

**Rule eras:**
- **Extension cap:** 50 on every ruled date and every real-EP date. The only exception, 75 from 08-22 to 08-28, holds none of the 45 ruled dates or 31 real EPs. Both caps are shown below.
- **Extension formula:** the gate's formula changed on 2026-04-16 (commit 38e86996, 20:40 PT): from the close about 8 days back (the latest stored close on or before today minus 8 days) to the lowest close over the prior 10 calendar days. CAR 04-01 and the 17 real EPs dated 03-12 to 04-08 (18 dates, n = 18) predate it, so today's rule is replayed on them. Replaying the old formula too gives the same keep (cap 50) on all 18, so no count moves. `rule_eras.py` has no row for the 04-16 change (its first admission switch is 08-20), so the era stamps here cannot show it.
- **Other eras:** exit eras (era D, 09-06) do not apply: no trade row, fill or exit is read anywhere; this is bars only. 44 of 45 dates are before the 08-20 gap-floor change, RARE 08-20 is on it.

### Four stored series are not clean

Scan: every pair of consecutive stored bars where the next open is over 2.5x or under 0.4x the prior close, or the gap is over 10 calendar days, across all 74 tickers (`fix_checks_out.txt` §2). Four series break; the other flagged pairs are single-day moves with a 1 to 3 calendar-day gap, not breaks in coverage, and were not treated as seams.

| series | what is wrong | ruled date affected (n) |
|---|---|---|
| MRLN | 80 stored bars (2021-09-27 → 2022-01-19) are a different company's: 1,518 calendar days later the price restarts (23.49 → 7.16); its own history starts 2026-03-17 | MRLN 06-05: 136 stored prior bars, 56 its own |
| IBTA | 24 stored bars (2021-09-27 → 2021-11-30) are a different company's: 870-day gap, price 25.35 → 117; own history starts 2024-04-18 | IBTA 08-04: 598 stored, 574 its own |
| NIQ | 438 stored bars (2021-09-27 → 2023-06-23) are a different company's: 761-day gap; own history starts 2025-07-23 | NIQ 08-11: 702 stored, 264 its own |
| QH | prices are not split-adjusted: the close is 0.094 on 04-02, then the next stored bar (05-29) opens at 7.8, about 83x higher (a reverse split), with 57 calendar days (40 weekdays) of rows missing | QH 06-18: 14 prior bars after the split |

- **QH's 15,791% run-up is a split artifact.** On the 14 post-split bars alone the 20-session run-up is 250.7%, still over 75, so the run-up rule still catches it. The live gate's own 10-day window (223.7%) sits entirely after the split, so its catch is unaffected too. QH's 45 overhead zones as stored are the old unadjusted prices; there are 0 once they are removed.
- **What moves when the other company's bars are removed (MRLN, IBTA, NIQ):** no headline count. Live gate 7 of 25, run-up rule 9 of 25, supply read 5 of 25 (6 on the 13-month history), 0 of 31 real EPs, 0 of 14 approved dates are all unchanged. Two supply labels change class: MRLN 06-05 from IFFY_AT_FIRST_ZONE to LADDER_CLIMBING, NIQ 08-11 from IFFY_AT_FIRST_ZONE to INTO_SUPPLY (so the label table in "Does anything separate" becomes INTO_SUPPLY 9 bad / 2 approved, LADDER_CLIMBING 1 / 3). The congestion-zones separation measure moves 0.380 → 0.383; the other three do not move.
- **What moves when QH's pre-split bars are removed too (leaving 14 bars of QH history):** the supply read catches QH, so 5 of 25 becomes 6 of 25 on the full history and 6 becomes 7 on the 13-month history (7 ties the live gate's 7; neither beats it). The zones and overhead-volume separation measures move 0.380 → 0.354 and 0.433 → 0.426. The live gate and run-up counts do not move. A 14-bar history is not a clean test either, so both versions are shown and neither is chosen.

## The result

Four rules, each used with a value that already existed — nothing was searched or tuned on these 45:
**live gate (cap 50)** — today's extension rule · **gate at 75** — what the 08-25 study measured it at · **run-up 75** — the rule the 09-21 and 09-23 re-scores used (20-session run-up ≥ 75%, his number) · **supply read** — nothing overhead AND the same run-up ≥ 75%.

| rule | real EPs lost | approved lost | bad caught | bad caught that were **alerted HIGH** | new bad (of 4) caught |
|---|---|---|---|---|---|
| live gate (cap 50) | 0 of 31 | 0 of 14 | **7 of 25** | 0 of 10 | 0 |
| gate at 75 | 0 of 31 | 0 of 14 | 6 of 25 | 0 of 10 | 0 |
| **run-up 75** (committed scorer) | 0 of 31 | 0 of 14 | **9 of 25** | **1 of 10** (NVTX 06-03) | 0 |
| **supply read** | 0 of 31 | 0 of 14 | **5 of 25** (6 on a 13-month history; with QH repaired: 6 full history, 7 on 13 months) | 0 of 10 | 0 |

- The live gate reading 0 of 10 on the alerted ones is **by construction** — a name it rejects never gets an alert. The run-up rule's 1 of 10 is the only non-circular catch among them.
- The supply read is the run-up rule **plus** a "nothing overhead" condition, so it can only catch a subset of what the run-up catches: it drops 4 of the run-up's 9 (GDC, ADVB, QH, NVTX) and saves no approved date, because the run-up rule loses none. QH drops out only because its unadjusted pre-split bars read as overhead supply (see above).
- The run-up rule's only catches beyond the live gate are NVTX 06-03 and AEHR 08-14 — both from looking back 20 sessions instead of 5, not from any chart reading.
- 16 of the 25 bad charts are touched by neither extension rule — **all four new ones included**.

### Did the ten new rulings move anything?

| | the 35 (09-23 set) | the 10 new | all 45 |
|---|---|---|---|
| run-up 75: bad caught | 9 of 21 (43%) | **0 of 4** | 9 of 25 (36%) |
| live gate: bad caught | 7 of 21 (33%) | **0 of 4** | 7 of 25 (28%) |
| supply read: bad caught | 5 of 21 (24%) | **0 of 4** | 5 of 25 (20%) |
| approved lost (all rules) | 0 of 9 | 0 of 5 | 0 of 14 |
| real EPs lost (all rules) | 0 of 30 | — | 0 of 31 (PENG added; not a ruling) |
| pointed-at dates the run-up rule would reject | 1 of 3 (MXL 04-24) | 1 of 1 (**RXT 05-07**) | 2 of 4 |

**Yes, in one way: coverage fell, because the numerator held at 9 while the denominator grew.** The 35-set row reproduces the 09-23 doc exactly (9 of 21, 0 of 9, 0 of 30, 1 of 3), which is the check that this rebuilt driver is faithful. Both pointed-at flags (MXL 04-24, RXT 05-07) are also rejected by the **live gate at today's cap of 50** (59% and 55% extended) and by neither at 75 — days he named as the real date, flagged only, not ruled.

### Does anything separate his labels at all? (no cutline)

Plain version: how often a random condemned chart reads worse than a random approved one. 50% is a coin flip; at this n one standard error is about 9-10 points (20 on the ten new), so anything within ~10 of 50% is noise.

| measure (bigger = worse) | the 35 | the 10 new | all 45 |
|---|---|---|---|
| 20-session run-up | 71% | 40% | **65%** |
| extension on the live basis | 65% | 40% | 58% |
| share of volume still overhead | 41% | 70% | 43% (13-month: 55%) |
| congestion zones still overhead | 33% | 60% | 38% (13-month: 48%) |

- **Two measures lean the right way and neither is established:** the 20-session run-up (65%, standard error 9 points, 1.7 standard errors from a coin flip) and extension on the live basis (58%, 0.9 standard errors). The run-up **weakened from 71% to 65%** as labels were added; on the ten new ones alone both lean the wrong way (n = 4 vs 5, so not an estimate). Neither clears two standard errors.
- **The supply fields are at or below a coin flip and lean inverted** (volume overhead 43%, −0.7 standard errors; zones 38%, −1.25) — his approved charts have more zones overhead (median 14) than the bad ones (median 4), because a name that has already run has nothing left above it. That is the 08-25 mechanism, not a bug. On the 13-month history they flatten to 55% / 48%: **within the noise either way, no direction established.**
- The supply label by verdict (full history, as stored): INTO_SUPPLY 9 bad / 1 approved, LADDER_CLIMBING 0 / 3, the rest mixed (9 / 2 and 1 / 3 once MRLN and NIQ are repaired). **That pattern was found by looking, so it cannot be tested on this table — and the same label tags 9 of the 31 real EPs**, so a rule on it would cost real EPs. It vanishes on the 13-month history (8 / 3). Not a lead.

## What he saw when he ruled (why 32 of 38 is not evidence for his eye)

His 45 verdicts agree with the next 20 sessions in 32 of 38 cases (21 condemned names fell, 3 rose; 3 approved fell, 11 rose; one has no 20-session result in the stored bars). One-sided Fisher exact p = 0.00008 on that 2-by-2. **That agreement does not show his eye beats the rules**, because a forward result was in front of him each time:

| session (rulings) | what the evidence says he saw | verdict agrees with the later move |
|---|---|---|
| 08-25 (15) | the fixture records he was shown name-days "the read scored as clean that then fell 18-98%" and name-days it scored as buried "that then ran"; the review file he was shown (`scripts/probes/_srbt_review_sample.psv`) carries `ret_5d`, the **5-session** return, not the 20-session one | 11 of 11 (1 has no result) |
| 09-06 (10) | the 09-06 sample file lists `pct_20d` for each name, grouped "we said HIGH and it failed" / "we scored it below the bar and it ran"; the fixture's note on his reading of the set is organised by outcome and lists each later move (RNG +39%, OMER +70%, ABVX +60%, CGEM +39%, AVAH +37%) | 7 of 8 (ABVX went the other way) |
| 09-23 (10) | the 09-21 sample file lists `pct_20d` under the same two headings; the fixture note on RARE carries "20 sessions later -49%" | 9 of 10 (WYFI went the other way) |
| 10-05 (10) | the review page itself prints "20 sessions later" with "-41%" (AEVA) under "We alerted HIGH and it fell", and "+30%" (CDNA) under "We skipped it and it ran" | 5 of 9 (IBTA, HURN, BLZE, HPE went the other way) |

The agreement column is always scored on the 20-session move, including for the first session, where the number he saw was the 5-session return.

- **What this means:** agreement with the printed result cannot separate "he read the chart" from "he read the result". The 32 of 38 is a consistency figure, not a skill figure, and not a hit rate in the wild.
- **What it does not mean:** that his eye is poor. In the latest session 4 of his 9 verdicts went against the result on screen (n = 9, not an estimate), which neither confirms nor refutes the point. It says only that this sample cannot answer it.
- **The fix is a blind sample:** from sample #4 the page carries charts only (bars to the day before), no forward return and no heading that names the outcome ("it fell" / "it ran" prints it too). The rules then get scored against verdicts he gave without the result.

## The bar to beat, restated

- **(a) The supply read is a null as a winner predictor: 0.496 at matched dollar volume, n = 2,787** (2026-08-25). **Not re-tested here.** Carry the 09-06 caveat: it was measured on 13 months of bars while he judges multi-year structure.
- **(b) It adds nothing beyond the existing extension rule on his reject bar.** PLAN says "8 of 11, the gate alone gets there"; precisely, on session 1 the live gate gets 7 of 11 today (6 at the 75 cap the 08-25 study used) and **8 of 11 is the same rule read over 20 sessions at cap 75** — both reproduce here. On all 45 the supply read is **below** the live gate (5 vs 7), the 20-session run-up is above it by two (9 vs 7), and on the ten bad charts that reached a HIGH alert the supply read catches 0 against the run-up's 1.
- **So the read does not beat the bar.** What is left over is the extension rule's lookback window (5 sessions live, 20 here), which the 08-25 doc already named as its one narrow option.

### The one fork the numbers touch: the extension rule's lookback

Facts only, no change proposed. The basis is the live gate's own (lowest close, prior close against it); only the lookback and the cap vary (`fix_checks_out.txt` §1).

| extension rule | real EPs lost | approved lost | bad caught | bad caught that were alerted HIGH |
|---|---|---|---|---|
| live gate as coded (10 calendar days, about 5 sessions), cap 50 — today | 0 of 31 | 0 of 14 | 7 of 25 | 0 of 10 |
| the same gate, cap 75 (08-22 to 08-28) | 0 of 31 | 0 of 14 | 6 of 25 | 0 of 10 |
| **20 sessions, cap 50** | **2 of 31** (AMD 04-24, INTC 04-24) | **2 of 14** (CAR 04-01, HPE 06-02) | **10 of 25** | **2 of 10** (NVTX 06-03, NVTS 06-03) |
| 20 sessions, cap 75 | 0 of 31 | 0 of 14 | 9 of 25 | 1 of 10 (NVTX 06-03) |

- **At the cap he reverted to on 08-29 (75), a 20-session window loses nothing:** 9 of 25 caught, 0 of 31 real EPs, 0 of 14 approved. The earlier "2 more catches, nothing lost" reading is that version, set against the live gate at 50, so it moved the cap as well as the window.
- **At today's cap (50), the window alone:** catches 10 of 25 (the live gate's 7 plus NVTX 06-03 and NVTS 06-03, both alerted HIGH, and AEHR 08-14, no alert row; NVTS is the one the run-up rule does not catch). It also rejects AMD 04-24 (55.7% over 20 sessions, 19.7% live) and INTC 04-24 (62.1%, 4.7% live) from the real-EP bar, CAR 04-01 (52.1%, 35.8%) and HPE 06-02 (63.7%, 26.3%) from the approved dates, and MXL 04-21 (97.3%, 48.9%), a wrong-day ruling kept apart.
- Whether any of this is worth a change is entirely his call; this doc proposes none. It would be a detection-criterion change under CHANGE_PROCESS (sign-off, N ≥ 10 backtest).

## What would be worth testing next (named, not run, nothing declared yet)

Three things he cited that are computable on the day and that no number here sees: **where the gap day closed in its range** (his NVTS tell), **position against the 10/20/50/200-day averages** (OMER's reprieve), and **the quality of the base being cleared on the 5-year bars** (the 09-06 "fraction cleared" version came out inverted). Each needs its threshold written down **before** sample #4, not found in these 45, and sample #4 is scored against verdicts given outcome-blind.

## The one question for him

**Edge, dead end, or keep labelling?**

- **Recommendation: the $0 supply read is a dead end as a filter — rule it so; keep labelling, but outcome-blind from sample #4 (charts only: no forward return, no "it fell / it ran" heading), because those labels are the out-of-sample set for the three $0 measures above (declared before it is scored) and then the bar the paid vision test (#519) must beat.**
- **Why:** no edge — it is below the live gate (5 vs 7), the ten new labels added zero catches, and even the best of the three rules misses 9 of the 10 bad charts that reached a HIGH alert. **Whether his eye beats the rules is not shown either way:** his 45 verdicts agree with the next 20 sessions in 32 of 38, but a forward result was printed beside each chart, so that cannot say whether he read the chart or the result. For reference, the run-up rule flags only 9 of the 21 condemned names that fell and none that rose.
- **Cost of "dead end":** stop re-scoring this read after every ten labels. Nothing else changes except that the next review page leaves the outcome off.

## Reproduce

`python scripts/probes/_594_rescore/fetch_bars.py` and `fetch_alerts.py` (one read-only prod SELECT each, capture-once guarded), then `run_score.py` (local, $0). Outputs committed: `score_out.txt`, `results.json`. The corrections in this version come from `fix_checks.py` (imports `run_score.py` unchanged; local, $0), output `fix_checks_out.txt`. `bars.tsv` (3.4 MB) is git-ignored.

## What this does not answer

- **Whether chart reading has an edge.** This scores one $0 read against his labels. It says nothing about a paid vision read (#519) or about his own eye as a filter.
- **Whether his eye beats the rules.** A forward result was on screen for every verdict, so no blind sample exists yet; the first one is sample #4.
- **Whether the supply read predicts winners.** The 0.496 null is carried from 08-25 on 13 months; it was not re-run here.
- **How often he is right in the wild.** The 45 were chosen because our score and the outcome disagreed, and a forward result was printed beside each chart, so 32 of 38 matching the outcome is neither a hit rate nor evidence for his eye.
- **Whether "alerted HIGH" meant "traded".** It is read from `mi_ep_alerts`; entry-pipeline skips and safeguards were not checked. Two fixture notes (LPTH, WYFI) call a MODERATE alert HIGH; the table was used.
- **Whether a 5-year history is the right window for the supply read.** The 09-23 doc said bars only reached 2025-08; the table holds 2021-09 onward, so that was the pull's bound. The supply fields change with the window (5 of 15 stored labels flip from "clear air" on the full history; 13 of 15 match on the old window), while the extension and run-up verdicts do not (identical on both windows for all 45 dates and 31 real EPs). Neither window was chosen; both are shown.
- **Whether a fully clean bar history changes the supply read.** Four stored series cross a break (MRLN, IBTA, NIQ, QH). Removing the three other-company stretches moves no count; QH is the one that moves it (5 → 6 of 25), and repairing it leaves only 14 bars, so the true value is not known.
- **What the lookback change would do on live trades.** The fork table is bars only on 45 ruled dates and 31 real-EP dates; no fill, exit or trade outcome is read, and no cutline other than the existing caps 50 and 75 was tried.
- **Anything at a cutline other than the ones that already existed.** At n = 45 a favourable one is trivial to find and worthless; none was searched.
- **Why the four new bad charts are bad.** His words cite resistance and left-side highs; whether any computable measure captures that is untested.
