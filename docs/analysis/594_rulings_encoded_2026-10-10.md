# #594 step 0 — all 45 rulings scored: the ten new ones added no catches, and the read still does not beat the extension rule

**MEASUREMENT ONLY. No rule, threshold, filter or trade behaviour was changed or proposed.** His labels
are ground truth and are never scored themselves. Any change this implies is his call (THE LINE).

## The answer

- **No rule loses a real EP or a chart he approved** — not the live extension gate, not the 20-session run-up, not the supply read: 0 of 31 real EPs, 0 of 14 approved dates, under all four.
- **They also catch little of what he condemned: 5 to 9 of 25** (supply read 5, live gate 7, 20-session run-up 9). **The ten new rulings added zero catches** (0 of 4 new bad charts), so coverage fell again, 43% → 36% for the run-up rule the last two re-scores used.
- **The chart read (the supply ladder) does not beat the extension rule — it is worse.** It catches 5 of 25 against the live gate's 7, and adds nothing the run-up number alone does not already see.
- **The sharper cut: of the 10 bad charts the live system actually alerted HIGH, the run-up rule catches 1 and the supply read 0.** Eight of the run-up rule's nine catches were never alerted anyway (the live stack had already stopped them); the bad charts that got through are the ones nothing here sees.
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
| bars | 74 tickers, 74,295 rows | prod `mi_daily_closes`, 2021-09-27 → 2026-10-09, pulled once; 0 unreadable dates, 0 null bars, min 136 prior bars per date |

**Three traits that would mislead if not said first:**
- **His labels are tangled up with what happened next, by how the samples were built.** Samples were drawn from names that collapsed or ran, so the verdicts line up with the outcome: the condemned names fell in 21 of 24 (median −43% over 20 sessions), the approved ones rose in 11 of 14 (median +21%). Catching "bad charts" is therefore partly catching "names that later collapsed".
- **The real-EP bar is a list of winners** (median +55%, 29 of 30 rose >20%). "Lost 0 of 31" is a statement about winners; it cannot show the rules are free on a loser that looks like a winner.
- **13 of the 25 bad charts were never alerted** (11 are session 1, which the live stack already rejected on 08-25; plus IBTA and HURN). 10 got a HIGH alert, 2 a MODERATE.

**Rule eras:** only one element is era-sensitive — the extension cap (50; it was 75 from 08-22 to 08-28, then reverted). **None of the 45 ruled dates or 31 real EPs fall in the 75 window**, so every date was live under 50. Both caps are shown below. Exit eras (era D, 09-06) do not apply: no trade row, fill or exit is read anywhere; this is bars only. 44 of 45 dates are before the 08-20 gap-floor change, RARE 08-20 is on it.

## The result

Four rules, each used with a value that already existed — nothing was searched or tuned on these 45:
**live gate (cap 50)** — today's extension rule · **gate at 75** — what the 08-25 study measured it at · **run-up 75** — the rule the 09-21 and 09-23 re-scores used (20-session run-up ≥ 75%, his number) · **supply read** — nothing overhead AND the same run-up ≥ 75%.

| rule | real EPs lost | approved lost | bad caught | bad caught that were **alerted HIGH** | new bad (of 4) caught |
|---|---|---|---|---|---|
| live gate (cap 50) | 0 of 31 | 0 of 14 | **7 of 25** | 0 of 10 | 0 |
| gate at 75 | 0 of 31 | 0 of 14 | 6 of 25 | 0 of 10 | 0 |
| **run-up 75** (committed scorer) | 0 of 31 | 0 of 14 | **9 of 25** | **1 of 10** (NVTX 06-03) | 0 |
| **supply read** | 0 of 31 | 0 of 14 | **5 of 25** (6 on a 13-month history) | 0 of 10 | 0 |

- The live gate reading 0 of 10 on the alerted ones is **by construction** — a name it rejects never gets an alert. The run-up rule's 1 of 10 is the only non-circular catch among them.
- The supply read is the run-up rule **plus** a "nothing overhead" condition, so it can only catch a subset of what the run-up catches: it drops 4 of the run-up's 9 (GDC, ADVB, QH, NVTX) and saves no approved date, because the run-up rule loses none.
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

- Only the run-up leans the right way, and it **weakened from 71% to 65%** as labels were added; on the ten new ones alone it leans the wrong way (n = 4 vs 5, so not an estimate).
- **The supply fields are at or below a coin flip and lean inverted** — his approved charts have more zones overhead (median 14) than the bad ones (median 4), because a name that has already run has nothing left above it. That is the 08-25 mechanism, not a bug. On the 13-month history they flatten to 55% / 48%: **within the noise either way, no direction established.**
- The supply label by verdict (full history): INTO_SUPPLY 9 bad / 1 approved, LADDER_CLIMBING 0 / 3, the rest mixed. **That pattern was found by looking, so it cannot be tested on this table — and the same label tags 9 of the 31 real EPs**, so a rule on it would cost real EPs. It vanishes on the 13-month history (8 / 3). Not a lead.

## The bar to beat, restated

- **(a) The supply read is a null as a winner predictor: 0.496 at matched dollar volume, n = 2,787** (2026-08-25). **Not re-tested here.** Carry the 09-06 caveat: it was measured on 13 months of bars while he judges multi-year structure.
- **(b) It adds nothing beyond the existing extension rule on his reject bar.** PLAN says "8 of 11, the gate alone gets there"; precisely, on session 1 the live gate gets 7 of 11 today (6 at the 75 cap the 08-25 study used) and **8 of 11 is the same rule read over 20 sessions** — both reproduce here. On all 45 the supply read is **below** the live gate (5 vs 7), the 20-session run-up is above it by two (9 vs 7), and on the ten bad charts that reached a HIGH alert the supply read catches 0 against the run-up's 1.
- **So the read does not beat the bar.** What is left over is the extension rule's lookback window (5 sessions live, 20 here), which the 08-25 doc already named as its one narrow option. The facts, stated neutrally: the 20-session version catches 2 more of the 25 bad charts (NVTX 06-03, which was alerted HIGH, and AEHR 08-14), loses 0 of 31 real EPs and 0 of 14 approved dates, and flags one extra neither-kind date (MXL 04-21, a "wrong day" ruling). Whether that is worth a change is entirely his call; this doc proposes none.

## What would be worth testing next (named, not run, nothing declared yet)

Three things he cited that are computable on the day and that no number here sees: **where the gap day closed in its range** (his NVTS tell), **position against the 10/20/50/200-day averages** (OMER's reprieve), and **the quality of the base being cleared on the 5-year bars** (the 09-06 "fraction cleared" version came out inverted). Each needs its threshold written down **before** sample #4, not found in these 45.

## The one question for him

**Edge, dead end, or keep labelling?**

- **Recommendation: the $0 supply read is a dead end as a filter — rule it so; keep labelling, because the labels are the out-of-sample set for the three $0 measures above (sample #4, declared before it is scored) and then the bar the paid vision test (#519) must beat.**
- **Why:** no edge — it is below the live gate, the ten new labels added zero catches, and even the best of the three rules misses 9 of the 10 bad charts that reached a HIGH alert. **Not a dead end for the program:** his own verdicts match the next 20 days in 32 of 38 (samples built from collapsers and runners, so chance is about half), while these rules flag only 9 of the 21 condemned names that fell and none that rose. His eye is the signal; the machine read is not yet.
- **Cost of "dead end":** stop re-scoring this read after every ten labels. Nothing else changes.

## Reproduce

`python scripts/probes/_594_rescore/fetch_bars.py` and `fetch_alerts.py` (one read-only prod SELECT each, capture-once guarded), then `run_score.py` (local, $0). Outputs committed: `score_out.txt`, `results.json`. `bars.tsv` (3.4 MB) is git-ignored.

## What this does not answer

- **Whether chart reading has an edge.** This scores one $0 read against his labels. It says nothing about a paid vision read (#519) or about his own eye as a filter.
- **Whether the supply read predicts winners.** The 0.496 null is carried from 08-25 on 13 months; it was not re-run here.
- **How often he is right in the wild.** The 45 were chosen because our score and the outcome disagreed, so 32 of 38 matching the outcome is not a hit rate.
- **Whether "alerted HIGH" meant "traded".** It is read from `mi_ep_alerts`; entry-pipeline skips and safeguards were not checked. Two fixture notes (LPTH, WYFI) call a MODERATE alert HIGH; the table was used.
- **Whether a 5-year history is the right window for the supply read.** The 09-23 doc said bars only reached 2025-08; the table holds 2021-09 onward, so that was the pull's bound. The supply fields change with the window (5 of 15 stored labels flip from "clear air" on the full history; 13 of 15 match on the old window), while the extension and run-up verdicts do not (identical on both windows for all 45 dates and 31 real EPs). Neither window was chosen; both are shown.
- **Anything at a cutline other than the ones that already existed.** At n = 45 a favourable one is trivial to find and worthless; none was searched.
- **Why the four new bad charts are bad.** His words cite resistance and left-side highs; whether any computable measure captures that is untested.
