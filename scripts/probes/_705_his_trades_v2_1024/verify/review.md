# #705 his trade list v2: adversarial review of the prereg and the census (2026-10-24)

**Verdict: FIX.** The census reproduces exactly, but the list as registered has three problems. Most of the 149 "new" breakout trades come from talk after the event, which conditions on the outcome. They double-count positions already in the 236. And the hand read finds the event day right on only 3 to 5 of 15.

FIX does not depend on check 1(a), which is a selection mechanism whose direction I show by example, not a measured bias.
It stands on three facts alone: check 4 (the 149 "new" trades sit on 91 bases), the event-day result in check 2, and the arithmetic in check 6.
It does not rest on §1.2 either: the wrong-stock rate 5/15 is AT that bar, not above it.

Scope: `docs/analysis/cb_his_trade_list_v2_prereg_2026-10-24.md`, `01_census.py`, `01_census.txt`. Nothing edited except this file.
Blinding: I read no trade, account or replay output, and did not read `trades_v2.tsv` (I rebuilt it from my own pairs).
I read the exports for ticker and date only, and the candidate tables for `ticker, D, E, K, retrigger, retrigger_chain, base_id, pole_date, split` only.
I opened full frames only where the frame cannot show a bar after the event day E (stream on or before E: n = 1, 3, 11, 13, 17, 21), plus #29.
#29's chart is ALYA, not CVNA, but its positions panel showed the EP day's % changes: day E for the EP row, and 7 sessions after E for the tl row (05-30).
For every other frame I viewed only a crop of the bottom-right positions panel's symbol column, with no prices and no chart.
Scratch code (not in the repo; the scratchpad is session-local): `/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/recount.py` and `analyze_v2.py` (outputs in `analyze_v2.out`).

## Checks

| check | PASS/FAIL | evidence |
|---|---|---|
| 1. Outcome-conditioned? | **FAIL** | (a) **98 of the 149 new strict breakout rows come from talk 1–10 sessions AFTER E** (43 at 1–2 after, 55 at 3–10 after). Only 47 are same-day and 4 came before E. Of the 100 rows shared with the 236, 80 are same-day, 16 before E and 4 after. A row enters because he still called it bought/long days after E, which depends on how the trade went. Examples from the hand read: FUBO "up 50–100% since I bought them", TWLO "they all broke out 4–6 weeks ago", PDD chart walk. Repeat rows per position compound this: a stock he keeps discussing keeps gaining rows (check 4). (b) §6 picks the W2 configuration "because it is the best registered reading on the 236", so 236 of the 381 era-A headline rows are in-sample for it. (c) "Fixed before the first run" cannot be verified. Doc, script and outputs are all untracked, and the script (10:09) was saved after the cached passes (10:04–10:05), so at least one run came before the final text. The census itself reads no outcome: the `usecols` are as stated, and my recount reads ticker and date only and matches. Minor: the planted-control pool filters on close × volume on s0, which is a bar after E for most draws (control only). |
| 2. Precision (hand read, n = 15) | **FAIL** | Rows n = 1, 3, …, 29 (odd n, a rule set before reading). Wrong stock: **5/15 (33%, 95% CI 15–58%)**, right at §1.2's "above a third → beside only" line. **Stock right AND E is his buy day: 3/15 sure, 5/15 with plausible (20–33%)**. 3 of the 10 right-stock rows were already in his positions panel before E (FSLY 12-10, ESTC 10-06, NIO 01-08), and 2 are unknown. §1.2 has no event-day bar. My read disagrees with the doc's text read on 7 of these 15 rows (5, 9, 13, 15, 17, 19, 25), plus row 7's ticker (DOCU, not ROKU). E.g. SPOT = he bought BA, and the MRNA starter = SOXL. |
| 3. Positive control | PASS (counts) | Of the 664 frame-attributed bought pairs (669 labels), STRICT + event recovers **187 (28.2%)** and WIDE recovers 319 (48.0%). By year: 2017 1/36, 2019 4/30, 2020 139/398, 2021 38/160, 2022 2/22, 2023 3/18. Misses: 301 fail the own-line test (132 of them have an event, which WIDE picks up). 176 are own-line with no event in the window: 71 have no tl or EP event within ±60 sessions (our detectors silent), 64 have a tl event 3–60 sessions AFTER the talk (he bought before our line broke: 20 at 3–10, 44 at 11–60), 36 have a tl event 11–60 sessions before, and 5 have only an EP outside the window. ⚠ The 96.6% registered bar compares two nearest-event picks on the SAME candidate table and the same s0 rule. It is a consistency check and cannot detect a wrong stock or a wrong buy day, so it is not evidence of precision. |
| 4. Double counting | **FAIL** | The 249 strict breakout rows sit on **187 bases** (`base_id`, the drift-robust chain key; `retrigger_chain` is a 0/1 flag), so 62 are repeat rows. **Of the 145 era-A new rows, 50 sit on a base already in the 236**, 32 within 5 sessions of a 236 event of the same stock. The headline's 381 era-A rows cover 279 bases: the 236 = 188, **v2 adds 91 bases, not 149 trades**. 68 headline rows fall ≤ 5 sessions after the previous row of the same stock. MRNA has 20 rows on 9 bases, FSLY 15 on 6, SHOP 17 on 8. Across setups: 31 strict pairs yield both a breakout and an EP row (25 on different days), and 21 of the 46 strict EP rows have a strict breakout row of the same stock within 10 sessions, so "295 trades" counts them twice. Rows reached from more than one video: 82 (the dedupe on symbol and E works). Same (symbol, E, setup) in both eras: 0. |
| 5. Trade day = event day | PASS (code) | Trade rows are keyed (era, symbol, E, setup), event year = E[:4], and s0 only places the window. My rebuild matches. Caveats: **20 strict breakout and 5 EP rows have E AFTER the "I bought" talk** (4 of them new), so E cannot be his buy, against the doc's own "a buy already made" premise. 180 of the 249 rows are retriggers, and 159 of those have a first break of the same base ≤ 20 sessions earlier. The hand read found 3 held-before-E rows. "The event is the trade" is assumed, not measured. |
| 6. Census reproduces | PASS | An independent recount matched **all 18 columns × 7 years** (2017–2023; 2017 and 2022 asked). It re-derives the bought moments from the extractor windows rather than `graded_moments.tsv` (2024 = 2024), reads era-B bars from the export rather than `universe_dates.pkl`, and uses my own join. Phrase hits use the same VTT parser (`qmlib.parse_vtt`) with my own regex pass; the alias order (dedupe → refetch → rename) is the registered rule, re-implemented rather than reused. The trade list also matches: 295 / 249 / 46 / 100 / 149 / 111 and the event-year table. Prose errors: (i) 2017: the 34 Jan–Feb pairs are INSIDE the 57 no-event (31) and the 14 unresolved (3). The sentence adds them on top: 34 + 57 + 14 + 9 = 114 ≠ 84. (ii) "385 = 236 + 149": era A is 236 + 145 = 381, plus 4 era-B rows outside 2017-03..2021-12. (iii) "100 among the 236" = 97 era A + 3 of the era-B 9. |

## Precision estimate

Hand read of 15 rows, from captions ±30 s, the frame, and his positions panel on the stream and on the stream before E:

| n | stock | E (Δ) | his words | frame / positions panel | stock right? | E = his buy? |
|---|---|---|---|---|---|---|
| 1 | MDCO | tl 03-08 (+1) | "same news as mdco … jnc was the one i bought … bought this one 20 min ago" | screen ESPR | no | no |
| 3 | ACAD | tl 10-21 (0) | "i also bought some acad … new positions today" | ACAD in positions | yes | yes |
| 5 | CELH | tl 11-05 (−9) · EP 11-12 (−4) | positions walk; buy phrases are IGV / COUP | in positions 11-18; absent 11-04 (8/8), 11-10 (6/6) | held | tl no · EP plausible |
| 7 | TWLO | tl 12-11 (−9) | "they all broke out 4–6 weeks ago, toku this is the one i bought" | screen DOCU (= "toku"); no TWLO 12-10 (15/15) | no | no |
| 9 | MRNA | tl 10-12 (−1) | "mrna yesterday … i took a starter on sock sole" | screen SOXL; no MRNA 10-13 (18/18) | no | no |
| 11 | TTD | tl 07-31 (0) | "the stocks i bought today … i bought ttd" | TTD in positions | yes | yes |
| 13 | FSLY | tl 12-10 (+2) | "pen is triggering … i bought silo yesterday" | FSLY in positions 12-08 | held | no |
| 15 | SPOT | tl 05-19 (−2) | "today it broke out, that's why i bought it" = BA; SPOT "potential short" | — | no | no |
| 17 | FSLY | tl 08-24 (0) | "tou [DOYU] i bought today … fastly is fading" | FSLY + DOYU in positions | held | unknown |
| 19 | ESTC | tl 10-06 (−6) | "i bought fastly csd estc twitter" | ESTC in positions 10-01, 10-02 | yes | no |
| 21 | FUBO | EP 12-22 (0) | "up 50–100% since i bought them, last week or two" | in positions 12-22; not in 17/20 on 12-21 | yes | uncertain |
| 23 | PEN | tl 02-24 (−10) | "i wish i had bought the pen" | no PEN/PENN 03-10 (9/9) | no | no |
| 25 | NIO | tl 01-08 (−1) | "i'm long nio … sold down on nio" | NIO in positions 01-07 | held | no |
| 27 | LCID (CCIV) | EP 01-12 (−1) | "opening range highs on this thing … stopped out … bought this flag break" | in positions 01-13; not in 17/24 on 01-11 | yes | plausible |
| 29 | CVNA | tl 05-30 (−7) · EP 06-08 (0) | "added back … when it took out the opening range highs" | CVNA in positions 06-08 | yes | EP yes · tl unknown |

- **On the new rows with no attributed label (the sampled population):** the stock is in his book 10/15 (67%, CI 42–85%). The line says he bought it in 6/15 (40%), and it names the wrong stock in 5/15 (33%). **Right stock AND right day: 3–5/15 (20–33%, CI ≈ 7–52%).**
- **On the 149 new breakout rows:** 59 carry a frame-attributed bought label (stock confirmed, day unmeasured). The other 90 sit in the sampled population, where the frame shows a different ticker on 105 of 146 pairs (72%). Blended, the stock is right ≈ 64–80% of the time; the day is right ≈ 20–33% on the 90 and unmeasured on the 59.
- I knew the doc's text read before reading. Even row 26 (SKLZ, text read "wrong") also turns out to be in his positions on 01-11 and 01-13.

## Exact fixes (before `05_v2_list.py` freezes)

| # | fix | where |
|---|---|---|
| 1 | Collapse to **one row per (symbol, `base_id`)**: keep the earliest listed E on the base. "New" = bases not in the 236 (91). Apply the same collapse to the control draw. | `01_census.py` trade build (l.558–580); §0, §3, §6 |
| 2 | Register a talk-timing split: headline new rows = the 47 same-day rows (51 if #3 is not applied). The 98 rows talked about 1–10 sessions after E go beside and never decide. | §2 window row; §6 populations |
| 3 | Drop or move beside the 25 rows whose E comes after "I bought" (20 breakout, 5 EP). | §2; trade build |
| 4 | One trade per stock across setups: an EP row within 10 sessions of a breakout row of the same stock (21 of 46) is one trade, and the EP registration dedupes against the breakout list. | §6 EP rows |
| 5 | Measure the buy day at $0 from his positions panel. OCR only the symbol column of the bottom-right A-Positions list (crop, no prices), one frame per stream, 2019–2023. A row is confirmed when the stock is absent on the last stream before E and present on the first stream on or after E. Register its bar before reading. | new step; §4 |
| 6 | Make the deciding readout the new rows alone, since W2 was chosen on the 236; the union goes beside. | §6 |
| 7 | Commit the doc, script and `01_census.txt` as the freeze before 05 runs; they are untracked today. | git |
| 8 | Fix the prose: the 2017 sentence; 381 era A + 4 era B (not 385); 100 = 97 + 3; describe the 96.6% bar as a consistency check only; correct the text read on rows 5, 9, 13, 15, 17, 19, 25, 26 and on row 7's ticker (DOCU, not ROKU). | §0, §3, §4a, §4d |
| 9 | `same_day_other_setup` is taken from the first contributing pair only (l.569); compute it across the trade table. | `01_census.py` |
| 10 | Weight the hand-check estimate by stratum: the floor-1 allocation is not self-weighting. | §4d |
