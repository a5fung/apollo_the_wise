# #705 Track A — the breakout FILTER built from Qullamaggie's own stream grades: pre-registration (2026-10-23, round 3)

**Status: FROZEN 2026-10-23 for the FIT (the doc body above the freeze marker and the fit module are pinned below; `02_fit_filter.py` refuses to run if either changes). The sanity read and the combined test are registered here but each gets its own freeze before it runs. Round 3 (round 2's recheck returned FIX on three blockers; round 3's recheck on two one-line edits, applied — `verify/recheck_round3.md`). Round 2 came after two independent checkers returned FIX on round 1 (`scripts/probes/_705_track_a_1023/verify/
logic_report.md`, `recount_report.md`; every fix and where it landed is listed at the end). OUTCOME-FREE so far: no forward return, R,
P&L, stop, exit or bar after a breakout day has been read for any event named here. Every era-B file was read with its rows dated after
2024-12-31 DROPPED AT READ and asserted (candidates: 328 rows dated after the cut and 174,495 holdout rows; watch: 109,961 rows that
were holdout or dated after the cut, one counter; the bdef tables asserted ≤ 2024-12-31); no price of any era-B bar was read, and the
era-A daily export was read for its symbol column only.** Measurement and registration only. Nothing
here changes or proposes to change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state — those are the
operator's (THE LINE). The filter, when frozen, is a flag per breakout event that the ONE combined sealed test reads; whether it is
ever used is his call.

His words this doc serves (2026-10-22, verbatim): *"The edge comes from which breakout to pick (the A+ setups), but also positive
risk v reward"*; *"That is ridiculous amount … we need to cut out 90% of the trades"*; *"We need to attack from both ends, we need
to filter to less breakouts, trade reasonable amount and have better way to keep winners without taking major losses"*; and on the
labels: *"The whole point is to quantify his system, what better labels then his own"* — *"He often say it's A+ or not, or say it
needs a few more days to tighten etc."*

## 0. In plain words

- **What was measured (outcome-free, `scripts/probes/_705_track_a_1023/01_join_labels.{py,txt}`):** where his 854 attributed stream
  grades sit against OUR breakout events (the trendline level `tl`, the registered one). **In 2017–21, 392 of his 624 "bought" labels
  (62.8%) have one of our tl breakouts of the same stock within 10 sessions before or 20 after the screen date**, 86 of 128 "not yet"
  labels (67.2%) and 32 of 60 "best" (53.3%). **The one timing signal is ON THE DAY: the screen date IS our breakout day on 113 of
  the 392 bought labels (28.8%), against 52.9 expected from a random near-a-base date of the same stocks (13.5% of 42,781 placebo
  sessions) — an excess of about 60 labels, all of it at delta 0.** The share of labels said BEFORE our breakout is BELOW the
  placebo (163 = 41.6% against 212 = 54.1% expected), and there is no anticipation signal in the timing: one session early reads 25
  against 26.0 expected, two sessions early 7 against 18.6. After the breakout 116 (29.6%) against 127.0 expected. Against his OWN
  breakout definition (the first close above the base high, R1) his "bought" comes a median 14 sessions EARLIER (98 of 109 labels
  with an R1 row, 89.9%): he buys at or around our trendline break, well before the base high is cleared on a close.
- **The target, by the rule fixed before the run:** neither "before" (41.6%) nor "on" (45.7% within −2..+1) reached 60%, so the
  registered target is **the breakout-day EVENT (ticker, E) with the base's STATE read at the watch night D — the fixed rule's THIRD
  branch, and that alone.** The timing data neither supports nor contradicts a pre-breakout state: it says the labels cluster on E and
  are otherwise spread like a random near-a-base date.
- **Round 2's main change — which events count as positives:** 87 of the 323 labelled events (27%) carry only labels said AFTER our
  breakout day ("I bought" said when the stock was already worth showing). **The positive class and the deciding arm of the sanity
  read are now the 236 events with at least one bought / best label said ON or BEFORE E (170 in the 2017–20 fit set, 66 in the 2021
  hold-out; era B 9 of 12).** The 87 post-E-only events and the 127 strictly-before events (90 / 37) are reported beside. The
  same-day negatives drop a row only when its base carries a label (any grade) said ON OR BEFORE that row's own breakout day
  (round 3; 410 of 23,598 rows on the 156 graded dates; 23,188 negatives remain) — round 2 dropped a row for a label said at any
  time (654 → 22,944), which let a LATER label remove stocks that went on to be worth showing: hindsight in the control.
- **What is registered (nothing run yet):** (1) a FROZEN FILTER — ≤ 5 features chosen from his labels against the OTHER breakouts of
  the same day, equal weights, directions fixed before the fit (from his words where tagged S, this registration's choice where
  tagged B), a trailing-pool percentile score and a weekly cap of 6 (his 5–7 a week against a stream of 53 first breaks / 205
  line-crossings a week); (2) a SANITY READ that the labelled breakouts carry edge against the same-day ungraded ones under two of
  Track B's exit cells (`pp` and 20-day · reclaim forgiven · no partial), tail first, month-block intervals, **era A decides, era B
  (n = 9) is descriptive**, nothing after 2024-12-31; (3) the interface to the ONE combined sealed test.
- **Action from him: none now.** The freeze commit, the fit, then the sanity read follow in that order; every consequence is fixed
  in §7 before any of them runs.

## 1. The four questions of the standard

1. **Decision served:** which breakouts to TAKE — a filter that cuts the stream to about a tenth, built from what Qullamaggie
   himself called bought / best / not-ready, so that the combined sealed test reads Track A's filter × Track B's exit once. What
   to do with the result is his.
2. **What would change it:** if his labels do not separate from the same-day breakouts on any bar-derived feature (the fit cannot
   reach the bar in §5), the filter is not frozen and his own definition (R2, the expansion day) enters the combined test instead;
   if the labelled breakouts do not out-run the same-day ungraded ones under the registered exits (§6), the labels are a weak target
   and the consequence table (§7) says what enters the combined test.
3. **Population:** §9.
4. **What would make this wrong:** (a) the negative class is "not shown on stream", not "rejected" — a breakout he never
   discussed may be one he would have bought; (b) 48% of the matched labels sit on a RETRIGGER of the line, so a label marks a
   base more than one day; (c) the labels are 2017–2023 stream moments with 2020–21 holding 91% of them; (d) he shows what he
   likes (stream selection); (e) the 1.8% false-match rate of the frame check; **(f) after-the-fact selection: a label said after
   E is said about a stock that was still worth showing — the 87 post-E-only events are excluded from the positive class for this
   reason, and a label said ON E (delta 0, 119 events) is still said with part of E's bar visible (SQM at 11:34 on its breakout
   day), so the strictly-before set (127) is the only subset clean of E; (g) label-timing noise: beyond the ~60-label excess at
   delta 0, the labels' positions read like the placebo's — most of a label's information is WHICH base, not WHEN; (h) grade-phrase
   attribution: the grade regex was matched over the caption window around the ticker's line, and the phrase sits in the ticker's
   own line for only 350 of 669 bought labels, 58 of 129 not-yet and 35 of 64 best (the rest an upper bound on "window only", since
   the line is cut at 220 characters) — some grades belong to the neighbouring stock in the same breath.**

## 2. The join — what his labels sit on (outcome-free; run 2026-10-23; every choice fixed in the script header first)

**Fixed before the run.** Label session s0 = the last SPY session ≤ the screen date (9 of 854 fell on a weekend). Window: a tl event
with E in [s0 − 10, s0 + 20] sessions (why: "bought" is said at or soon after the entry; "needs a few more days" should resolve
within about a month; our tl trigger fires early relative to his base-high breakout, so the window reaches further forward). delta =
idx(E) − idx(s0): **positive = the label came BEFORE our breakout day, 0 = the screen date is the breakout day, negative = after.**
Nearest event by |delta| among first breaks and retriggers alike; a tie goes to the later E. Era A = screen date ≤ 2022-01-03 (the
rebuilt 2017–21 file `cb702_pre_v2`, candidates built on it 10-23); era B = later (`cb702`, discovery rows only; 174,495 holdout rows
and 328 rows dated after 2024-12-31 dropped at read, asserted). A label whose window does not touch the era's E range is a coverage
fact, not a miss (6 labels of 2017-01 and 13 of 2022-01..02, the gap between the eras). **Round 2 wrote out three round-1 rules the
code ran but the prose did not state** (the recount could not reproduce them from the text): the distinct-event delta, the placebo's
three conditions (§9) and the "same base not yet broken" key (§2d); none is a re-tune — no outcome exists.

**Symbol resolution (era A):** 783 own, 15 through `refetch_dropped.tsv` (NXTD→LGMK, SI→SICP, DPW→NILE, AHPI→AHPIQ, WTRH→ASAP,
MOXC→ABTS), 13 through `rename_map.tsv` (EXPI→AGNT, PKI→RVTY, CHK→EXE, SGH→PENG, SQ→XYZ); 0 unresolved.

### 2a. Funnel (labels with coverage)

| era | labels | coverage none | never in our watch table (untyped: ETF / ETN / leveraged) | watched, but no watch row in the window | in a base in the window, no tl event in it | MATCHED |
|---|---|---|---|---|---|---|
| A 2017–21 | n = 811 | 6 | 87 (84) | 140 | 72 | **506 of 805 (62.9%)** |
| B 2022–24 | n = 43 | 13 | 5 (4) | 9 | 4 | **12 of 30 (40.0%)** |

The never-watched names (54 symbols, 92 labels) are mostly funds our universe rule does not admit — TNA ×7, XOP ×5, TQQQ ×4, TAN ×4,
QQQ ×4, IGV ×4, NRGU, SPXL, SOXL, GDX, KWEB, SMH, KRE … — plus small stocks under its price / dollar-volume floors (LGMK ×4, EMAN, HCCH,
GORO, BIOC, MVST …); "untyped in the SIC file" is a proxy for the fund share, not a classification. The 140 "watched but not in the
window" are bases our structural gates (prior move ≥ 30%, base 10–45 sessions, close ≥ SMA50, the deal-pin guards) did not hold on
those nights — the detection miss class, named in §10, not fixed here.

### 2b. Join rate by grade (a tl event within the window; denominator = labels with coverage)

| era · grade | matched | full-coverage only | nearest event is a retrigger | a first break also in the window |
|---|---|---|---|---|
| A · bought | **392 of 624 (62.8%)** | 384 of 601 (63.9%) | 190 | 334 |
| A · not_yet | **86 of 128 (67.2%)** | 84 of 124 (67.7%) | 44 | 69 |
| A · best | 32 of 60 (53.3%) | 32 of 58 (55.2%) | 19 | 30 |
| B · bought | 10 of 28 (35.7%) | 9 of 20 (45.0%) | 3 | 10 |
| B · best | 2 of 3 | 2 of 3 | 2 | 2 |
| B · not_yet | n = 0 | — | — | — |

Beside, the center-of-mass level `com` matches a little more (era A bought 412 of 624, 66.0%; not_yet 88 of 128, 68.8%; era B
bought 12 of 28); the horizontal levels are mixed (era B bought: k5 13, k10 9, full 9 of 28, against tl 10). The registered level
stays `tl`.

### 2c. Position relative to our breakout day E (matched labels; delta > 0 = label before the breakout)

| set | n | BEFORE (delta ≥ +1) | ON (delta = 0) | AFTER (delta ≤ −1) | within [−2, +1] | median (quartiles) |
|---|---|---|---|---|---|---|
| A · bought, nearest tl event | n = 392 | 163 (41.6%) | **113 (28.8%)** | 116 (29.6%) | 179 (45.7%) | 0.0 (−1.0..+5.0) |
| A · bought, nearest FIRST BREAK | n = 334 | 170 (50.9%) | 33 (9.9%) | 131 (39.2%) | 89 (26.6%) | +1.0 (−3.0..+10.0) |
| A · bought, distinct (stock, E) events — the label CLOSEST to E | n = 297 | 103 (34.7%) | 110 (37.0%) | 84 (28.3%) | 163 (54.9%) | 0.0 (−1.0..+2.0) |
| A · bought, distinct events — round 1's first label in file order (beside) | n = 297 | 108 (36.4%) | 100 (33.7%) | 89 (30.0%) | 151 (50.8%) | 0.0 (−1.0..+3.0) |
| A · not_yet, nearest tl event | n = 86 | 43 (50.0%) | 23 (26.7%) | 20 (23.3%) | 43 (50.0%) | +0.5 (0.0..+3.8) |
| A · best, nearest tl event | n = 32 | 12 (37.5%) | 9 (28.1%) | 11 (34.4%) | 16 (50.0%) | 0.0 (−1.2..+2.0) |
| B · bought, nearest tl event | n = 10 | 6 | 2 | 2 | 5 | +1.0 (0.0..+5.2) |
| **PLACEBO** — the same stocks' other near-a-base sessions (era A, bought symbols; the three conditions in §9) | n = 42,781 | 23,145 (54.1%) | 5,775 (13.5%) | 13,861 (32.4%) | 12,743 (29.8%) | +1.0 (−2.0..+8.0) |
| **A · bought EXPECTED from the placebo** (placebo share × 392) | n = 392 | 212.1 | 52.9 | 127.0 | 116.8 | — |

**Reading it:** the labels' before-share is 12.5 points BELOW the placebo and the on-the-day share 15.3 points above it — the mass
moves from "before" to "on", and the excess is +60.1 labels at delta 0 and nowhere else (+1: 25 vs 26.0; +2: 7 vs 18.6). So the
timing says "he shows the base on the day our line breaks" and nothing about anticipation. The histogram of the 392 (delta: n):
−10:3 −9:12 −8:7 −7:6 −6:9 −5:5 −4:21 −3:12 −2:17 −1:24 **0:113** +1:25 +2:7 +3:12 +4:11 +5:11 +6:11 +7:4 +8:9 +9:10 +10:5 +11:6
+12:10 +13:3 +14:8 +15:4 +16:5 +17:4 +18:4 +19:4 +20:10. Of the 624 bought labels with coverage, 500 (80.1%) have a tl event within
±60 sessions; the window was not re-tuned after seeing this. The distinct-event row changes a little with the delta rule (closest
label / file order / min / max all stay under 60% on both arms), so the target rule's verdict does not depend on it; the not-yet
median is 0.5 (round 1 printed it as 0).

**Second anchor — his own definition's day (R1, the first close above the base high):** of the 392, 109 have an R1 row in the
breakout-definition tables (the OLD export's published fills). Disclosed: the R1 day's DATE (`entry_date`, a session after E on 89 of
the 109) was read from that table to place the labels — a date, no price, descriptive only; it is not an input to anything in §5 or
§6. The label comes BEFORE the R1 day on 98 of 109 (89.9%), within [−2, +1] of it on 12 (11.0%), after it on 8 (7.3%); median delta to
the R1 day +14 sessions. The R1 day's offset from our E on those 109: on E itself 20, 1–5 sessions later 38, 6–20 later 29, more than
20 later 22. **The two anchors agree on what he is NOT doing: waiting for the base-high close.**

### 2d. The base's state on the screen date (a watch row = the stock passed our C0 structural gates that night)

| era · grade | n | watch row AT s0 | … with a trendline (C0_tl = 1) | same base NOT yet broken at s0 — pole_date key (round 1) | … base_id key (drift-robust) | a watch row anywhere in the window |
|---|---|---|---|---|---|---|
| A · bought | n = 624 | 176 (28.2%) | 153 | 39 (6.2%) | 33 (5.3%) | 448 (71.8%) |
| A · not_yet | n = 128 | 50 (39.1%) | 50 | 13 (10.2%) | 13 (10.2%) | 97 (75.8%) |
| A · best | n = 60 | 17 (28.3%) | 15 | 4 (6.7%) | 4 (6.7%) | 38 (63.3%) |
| B · bought | n = 28 | 8 (28.6%) | 8 | 5 (17.9%) | 5 (17.9%) | 14 (50.0%) |

"Same base" in round 1 meant a tl candidate row carrying the watch row's `pole_date`; the module re-dates a pole by a day on
26,910 of 81,015 tl rows, so under that key six bought labels (SHOP g_0679, PINS g_0919, AMD g_1362, VIR g_1405, CMCM g_1634, HUYA
g_1686) read "unbroken" although the same base (`base_id`, the drift-robust key) had already fired on or before s0. Under `base_id`
the bought cell is 33 (5.3%); every other cell is unchanged. A base in our table ends when a close exceeds the pole high, so a stock
that broke out on s0 often has no watch row that night — "watch row at s0" is low for bought by construction. The "not yet" labels
sit in an unbroken base more often than bought (10.2% vs 5.3%), the direction the readiness contrast (§5) expects.

### 2e. R1 / R2 membership of the matched events (descriptive; forward flags by construction — never an input anywhere)

| era · grade | distinct events | R1 (base high closed above within 60 sessions) | published fill without R1 | not in the old fill population | R2 (expansion day) |
|---|---|---|---|---|---|
| A · bought | n = 297 | 69 | 26 | 202 | 17 |
| A · not_yet | n = 80 | 20 | 12 | 48 | 5 |
| A · best | n = 30 | 3 | 3 | 24 | 0 |
| B · bought | n = 10 | 6 | 1 | 3 | 0 |

Base rates over every published fill: R1 9,281 of 13,363 (69.5%) / 5,530 of 8,956 (61.7%); R2 1,582 of 13,363 (11.8%) / 1,076 of
8,956 (12.0%). Era A's membership is three-valued because the breakout-definition tables were built on the old survivors-only export
(`cb702_pre`) and on the published ORH5 fills only; "not in the old fill population" = not filled, a retrigger not filled, abstained,
or a name the old export lacked. 17 of 95 bought events with a known flag are R2 (17.9%), against 11.8% of fills — a lean, n too
small to say more. **These flags feed nothing: round 2 removed the only two places they were read downstream (the fit's "R2 share of
TAKE" and the sanity read's "R2 subset"); R2 appears again only as a descriptive GRADED-vs-UNGRADED share beside §6's table.**

### 2f. Distinct events, and the same-day population (the denominator of "which breakout to pick")

- **Era A: 388 distinct (stock, E) events** carry a label (bought 297, not_yet 80, best 30; 12 events carry both a bought and a
  not-yet label), over 288 distinct bases (`base_id`, the drift-robust key) and 147 stocks; 308 events carry one label, 54 two, 26
  three or more. Bought events by year: 2017 7 · 2019 8 · 2020 205 · 2021 77, on 180 distinct days in 88 ISO weeks. 11 of the 297
  bought events are C1 (3.7%) against 1.1% of the tl stream (81,015 rows).
- **Era B: 12 events** (bought 10 — 2022 1, 2023 9 — best 2, not_yet 0) over 11 bases and 10 stocks.
- **Same day:** a bought event in era A shares its E with a median 146 OTHER tl line-crossings (mean 162.7) and 29 other FIRST breaks
  (mean 40.9); its ISO week holds a median 651 line-crossings and 147 first breaks. The era-wide stream: a median 205 tl rows a week
  (n = 254 weeks) and 53 first breaks; era B 243 and 73 (n = 145 weeks). The published fills were 53 / 63 a week. His 5–7 a week is
  therefore about one in nine first breaks, one in 35 line-crossings. ("First break" here = `retrigger = 0`; 3,636 of the 20,650 era-A
  first breaks are drift re-fires of the same line (`retrigger_chain = 1`), so on a chain-first count the weekly median is 43 and his
  5–7 is about one in seven — §10.)

### 2g. Positive controls — three labels checked by hand on the frame (picked by rule, printed by the script)

| frame | stock · screen date · grade | matched E (delta) | our base | hand read of the frame |
|---|---|---|---|---|
| `g_0466` | SQM · 2017-10-05 · bought | 2017-10-05 (0); `retrigger` 0 but `retrigger_chain` 1 — the same base (`SQM\|2017-09-19`) had already fired on 10-04 and 10-05 is the re-fire after the pole re-dated 09-19 → 09-20; R1 | pole 09-20, D 10-04 | **CONFIRMED.** TC2000 daily: a run to 63.8 in mid-September, a 2-week pullback base with his drawn line at 56.07 and a down-sloping line from the pole, the 5-minute pane on 10-04/05 pushing through 59–60. The bars: 10-03 close 57.50 crossed his 56.07 line, 10-04 closed 59.44, 10-05 high 61.00 (our matched E). The frame's last daily bar is 10-04 (close 59.44; the taskbar reads 10-05 11:34), so the screen shows the state after our FIRST firing, one session before the matched re-fire — "one to two sessions before our tl event" holds only against E = 10-05. |
| `b1_00` | ROKU · 2021-06-16 · not_yet | 2021-06-18 (+2), a retrigger — a TIE with the 06-14 event at −2 (equally near; the later-E rule picked +2); not in the old fills | pole 04-14, D 06-17 | **CONFIRMED as a label; the daily tab is present but the WEEKLY pane is active (the OCR daily-tab test passed on the tab bar, not the active chart).** The weekly shows a 4-month 300–480 range; the hourly pane shows 06-14..06-16. "Not ready" fits a wide, long base of 45 sessions (the maximum our rule allows). The line had already fired on 06-14 and failed; the +2 reading is a tie artefact, not a clean "label before the break". |
| `g_0957` | MDGL · 2023-01-26 · bought | 2023-01-24 (−2), a retrigger; not in the fills | pole 2022-12-22, D 01-23 | **CONFIRMED.** TC2000 daily: the December gap from ~65 to ~250–300 on the NASH results, then a 4–5 week flag at 290–310 with his drawn lines. Bars 01-20..01-24 pushed the flag's upper edge (highs 306.9, 313.6, 313.9); our tl event 01-24 is two sessions before the stream moment (an earlier first break exists on 01-11 with retriggers 01-13, 01-18, 01-23, 01-24). ⚠ Disclosed: the hand check printed MDGL's bars through the SCREEN date 01-26, i.e. two bars (01-25, 01-26) after this candidate's E = 01-24; they were not used for anything and no number here rests on them, but the rule says no bar after E, so it is said. SQM's and ROKU's bar prints stop at their E. |

### 2h. Round 2 — the counts the registration rests on (script sections 11–14; outcome-free)

**Label timing per positive event** (bought or best; only the positive labels' deltas count — a not-yet label on the same event does
not; fit = E ≤ 2020-12-31, hold-out = 2021):

| era | positive events | ≥ 1 positive label ON OR BEFORE E (delta ≥ 0) | every positive label AFTER E (hindsight) | ≥ 1 positive label STRICTLY BEFORE E (delta ≥ +1) | a positive label exactly AT delta 0 |
|---|---|---|---|---|---|
| A 2017–21 | n = 323 (228 fit / 95 hold-out) | **236 (170 / 66)** | 87 (58 / 29) | 127 (90 / 37) | 119 |
| B 2022–23 | n = 12 | **9** | 3 | 6 | 3 |

**Same-day negatives** (every OTHER tl row on the positive events' E dates; **round 3 rule:** a row whose (stock, `base_id`) carries a
matched label of any grade said ON OR BEFORE that row's own E is excluded — a base he had already labelled is not "not shown on
stream"; a label said only AFTER the row's E does not exclude it, since that would drop the row for what happened later; the round-2
rule — a label at any time — beside):

| era · positive set | events · dates | other tl rows on those dates | excluded (round 3: base labelled on or before the row's E) | of them not-yet events · post-E-only positives | NEGATIVES (round 3) | round-2 rule beside: excluded → negatives |
|---|---|---|---|---|---|---|
| A · all 323 (round 1's GRADED) | 323 · 193 | n = 29,237 (19,138 fit / 10,099 hold-out) | 449 (296 / 153) | 30 · 0 | 28,788 (18,842 / 9,946) | 704 → 28,533 |
| **A · on-or-before 236 (the GRADED arm)** | 236 · 156 | n = 23,598 (15,377 / 8,221) | **410 (270 / 140)** | 29 · 18 | **23,188 (15,107 / 8,081)** | 654 → 22,944; 244 rows dropped only for a LATER label |
| B · all 12 | 12 · 8 | n = 471 | 6 | 0 · 0 | 465 | 7 → 464 |
| **B · on-or-before 9** | 9 · 7 | n = 352 | 7 | 0 · 1 | **345** | 9 → 343 |

**Readiness-contrast populations** (§5): not-yet labels with a watch row at s0 50 of 128 (all 50 with a trendline) — **43 once the
labels on the 15 events that also carry a positive (bought or best) label leave the not-yet set (§3)**; bought 176 of 624 (153); best
17 of 60 (15). Not-yet labels whose matched event is 0 or 1 session after the label (scorable at the event's D with at most one
session of drift) 32 of 86 — **25 after the same exclusion**; bought 138 of 392. 27 of the 80 not-yet events share a base with a bought event. Of the 12 events
carrying both labels: in 4 the bought label came on a LATER date than the not-ready call (AMC, RCL, WKHS, XYZ; AMC and WKHS also carry
bought labels before it); in 1 the two labels are 77 seconds apart in one stream (FSLY); in 2 one caption window was graded both (LRN,
OPK — a mixed window, not a reassessment); in 5 the not-ready call came AFTER every bought label (MRNA ×3, SAVE, TSLA).

**Grade-phrase attribution** (`02_graded_moments.py` matched the phrase over the caption WINDOW around the ticker's line; the same
regex re-applied to the ticker's own line, cut at 220 characters): bought 350 of 669 in the line (319 window-only, an upper bound);
not-yet 58 of 129 (71); best 35 of 64 (29).

## 3. The target — decided by the rule written before the run

- **Rule (script header):** on the 392 joined bought labels of era A, ≥ 60% with delta ≥ +1 → a PRE-BREAKOUT STATE (decision time =
  the watch night D); ≥ 60% within [−2, +1] → the BREAKOUT DAY (decision time = E); otherwise both are reported and the registration
  takes **the breakout-day target with the state read at D**. Result: 41.6% / 45.7% → **the third branch, and the target stands on
  that branch alone** — the timing data (§2c) shows an on-the-day cluster and otherwise placebo-like spread, not anticipation.
- **So the registered target is the breakout EVENT (stock, E) — a tl line-crossing, first break or retrigger — labelled POSITIVE when
  a "bought" or "best" label said ON OR BEFORE E marks it** (the nearest-event join; era A 236 events, era B 9), **with every input
  read from bars dated ≤ D = E − 1 (the watch night).** The flag applies the moment the line breaks on E, before any fill. An event
  whose only positive labels came AFTER E (87 / 3) LEAVES THE POSITIVE CLASS and is reported beside (its labels were said about a stock
  already worth showing — after-the-fact selection, §1.4f); **on a graded date it stays a NEGATIVE unless its base carried a label said
  on or before its E** (27 in era A — 19 fit / 8 hold-out — and 1 in era B are among the negatives: a label said later cannot move a
  row out of the control, §4). The R2 expansion shape is NOT an
  input (it needs E's close) and is no longer a split inside the fit.
- **"not_yet" is the not-ready side of the same state label**, not an outcome arm: it enters only the readiness contrast in §5, and
  §6 carries no not-yet row. **"best" (n = 30 events in era A) is reported beside bought, never its own arm;** it is merged into the
  positive class. **An event carrying a positive (bought or best) and a not-yet label (15 in era A, 12 of them with a bought label) is
  EXCLUDED from the not-yet set of the readiness contrast; it is POSITIVE when a positive label was said on or before E (13 of the
  15 — MRNA 2020-04-15 and ROKU 2020-08-04 carry only post-E positive labels and follow the post-E-only rule above) — not because every such pair is "a not-ready call he then acted on" (that fits 4 of the
  12; in 8 the not-ready call came at the same moment as or after the bought label, §2h), but because a bought event cannot stand
  on the not-ready side whatever the order of the two remarks.**
- Why not his R1 day as the target: 89.9% of his bought labels precede it. A filter that waits for the base-high close would be
  rating a day he is already in.

## 4. The comparison population — the OTHER breakouts of the same day

The negatives for the fit, and the control of the sanity read, are **the other tl line-crossings on the same E date, same era, same
universe rules** (median 146 a day in era A), NOT matched ordinary stocks. Why: his question is *which breakout to pick* — the
decision is made among the day's breakouts, so the contrast that answers it is labelled-vs-unlabelled within the day. Within-day
comparison also removes the market day (phase, breadth) from every feature. Stated plainly: **"ungraded" means not shown on stream,
not rejected** — some ungraded breakouts are ones he would have bought; this makes the fit's separation an UNDER-estimate, never an
over-estimate. **Exclusion rule (round 3): a same-day row whose (stock, `base_id`) carries a matched label of any grade said ON OR
BEFORE that row's own E — a not-yet event, a post-E-only positive, a second crossing of a labelled base — is EXCLUDED from the
negatives and from UNGRADED and counted** (era A: 410 of 23,598 rows on the 156 graded dates, 29 of them not-yet events and 18
post-E-only positives → 23,188 negatives, 15,107 fit / 8,081 hold-out; era B 7 of 352 → 345). A label said only after the row's E
does NOT exclude it: round 2 did, and 244 rows (148 fit / 96 hold-out, on 98 bases — 75 of them later labelled bought or best, 3 of those also not-yet) left
the control because he showed the stock later, plausibly because it worked; that is hindsight in the comparison (the round-2 rule
is printed beside: 654 → 22,944). A labelled base is not "not shown on stream", and a not-yet event is a
state he judged NOT READY: a not-yet event whose call came on or before its E is excluded (29 in era A); one whose call came only
AFTER its E stays a negative (4 in era A: LYFT 2021-03-03, NNDM 2020-12-21, PLUG 2020-07-21, TPIC 2020-10-07), for the same reason a
post-E-only positive does (27 in era A, 1 in era B). **The fit and sanity modules ASSERT the populations before any fit or walk:
era A negatives 23,188 (15,107 fit / 8,081 hold-out), era B 345.**

## 5. The registered FILTER (to be fitted after the freeze; outcome-free throughout — no forward flag of any kind is read in the fit)

- **Unit and stream.** Every tl candidate row (stock, E) of the era — the high cleared the trendline level on E — first breaks and
  retriggers alike (both fill in the published population). Era A: 81,015 rows (20,650 first breaks); era B discovery: 41,200
  (12,250). The filter cuts THIS stream; the fill, stop and exit are Track B's business.
- **Decision time.** D's close (the watch night) for the state; the flag is attached when the candidate exists on E. **No bar, no
  minute of E enters the score** (not the gap, not the volume so far).
- **Feature candidates (12; each from the pinned watch / candidates tables or the daily export with bars ≤ D; definitions are the
  A+ registration's where it has them, cited; every direction FIXED BEFORE THE FIT and never fitted — from his words where tagged
  S, this registration's own choice where tagged B, a reused constant where tagged R):**

| # | family (his word) | feature · definition | better = | source of the direction (**S** his words · **B** this registration's choice, not his word · **R** a reused constant) |
|---|---|---|---|---|
| 1 | tightness / contraction, daily | `tightening_ratio` (watch: mean (h−l)/c over D−4..D ÷ over P+1..P+5) | lower | S (*"tightening range"*; his 10-22 contraction ruling) |
| 2 | contraction, weekly scale | `wk_ratio` (A+ registration, concept 1: 5-session blocks from D back, last m ÷ first m, k ≥ 3; missing under 15 sessions) | lower | S (his 10-22 *"fractal"* ruling; the block reading is B) |
| 3 | contraction, pullbacks | `pb_ratio` (A+ registration, concept 1: last completed pullback ÷ the first; missing with < 2 pullbacks) | lower | S (same ruling, pullbacks as the third scale — ruled yes 10-22) |
| 4 | base depth ("long but wide and loose … not good") | `base_depth` = 1 − base_low ÷ pole_high (the module's `explain_watch`) | lower | S (*"wide and loose, that's not good"*) |
| 5 | retrace | `retrace` = (pole_high − base_low) ÷ (pole_high − pole_low), the share of the pole's range given back (module) | lower | R (the C1 term, `anticipation.COIL_HOLD_LIMIT`); **the direction is B** |
| 6 | prior run (the pole) | `prior_move` (pole high ÷ pole low − 1) | higher | S names the 30–100%+ range; **"bigger is better" is B** (the A+ read's orientation) |
| 7 | pole quality | `pole_day_vol_ratio` (the pole's volume vs its 20-day average, module telemetry) | higher | **B — not his word** |
| 8 | RS leadership | `rs_best` (best of the 1/3/6-month return percentiles on D) | higher | S (*"the 1 or 2% of stocks that are up the most"*) |
| 9 | group strength | `grp_pct` (the SIC group's 63-session return percentile on D; missing for small groups) | higher | S (his 10-21 *"group themes"*; the percentile is B) |
| 10 | volume dry-up | `vol_dry5` (A+ registration, concept 2: mean volume D−4..D ÷ D−9..D−5) | lower | S (his captured Deepvue note, 10-18) |
| 11 | distance to the level ("tight days anticipating breakout") | `dist_level_adr` = (pivot_tl(D) − close(D)) ÷ (close(D) × ADR20(D)) (watch row) | lower | S names anticipation of the break (AMRX, 10-22); the ADR reading is B |
| 12 | the watch night's own bar | `trigger_bar_range_adr` (the D bar's range ÷ ADR20, module; an inside day scores lowest) | lower | **B — not his word** (his AMRX chart marks *"second inside day"*, a hint, not a rule) |

  `base_len` is NOT a candidate (his 10-22 ruling: length is not rewarded on its own); it is a split beside. `atr14_slope` is not a
  candidate (its denominator is the pole's volatility, A+ registration). Market phase is a split, never an input (ruled 10-22).
  **Corporate actions inside a feature's window (the data standard's F4 / step 4):** the features with a RETURN window — `rs_best`
  (the 1/3/6-month returns to D), `grp_pct` (the group's 63-session return, used AS STORED in the watch row — its group aggregate still includes any
  DISCONTINUOUS ticker, since recomputing it needs the SIC file and each night's universe, both outside the whitelist; only the
  event's own-ticker rule here applies) and
  `prior_move` (pole low → pole high) — are MISSING for an event whose ticker has a G5 DISCONTINUOUS event dated inside that window
  (the G5 DISCONTINUOUS rows: era A `cb702_pre_v2/audit_1023/price/A_flags.tsv`, 93 pairs; era B
  `apollo_data/audit_runs_2026-10-23/B_flags.tsv`, 67 pairs — both pinned in the freeze record); a missing
  feature is skipped in that event's AUC and counts 0.5 in its score; the count of events affected is printed. The other nine
  features have no return window.

- **The fit — the only fitted object is the SUBSET (≤ 5 of the 12).**
  1. **FIT set:** the positive events (bought ∪ best, ≥ 1 positive label on or before E) with E in 2017-03-02..2020-12-31 — **170
     events** — against the 15,107 same-day negatives of those dates (§4). **CHECK sets:** (i) the 2021 positive events — **66** —
     against their 8,081 negatives (the hold-out with power); (ii) the 2022–23 positive events on `cb702` — **9** (8 bought + 1 best)
     against 345 negatives (the check the task named — direction only at that n, said so). **Beside, never deciding:** recall on the
     post-E-only events (58 fit / 29 hold-out / 3 era B) and on the strictly-before events (90 / 37 / 6).
  2. **Screen statistic:** within-day AUC = the mean over positive events of the feature's percentile among that day's negative tl
     rows (ties half, the event itself and every excluded labelled-base row out of the denominator), in the fixed direction; 0.5 =
     no separation. A feature with a missing value on an event is skipped for that event (the coverage printed).
  3. **Subset rule:** the features with fit-set AUC ≥ 0.58, taken in descending AUC, at most 5; a feature whose fit-set AUC points
     AGAINST its fixed direction (< 0.50) is excluded and REPORTED as a disagreement, never flipped. **An EMPTY subset (no feature
     reaches 0.58) = FAIL** (§7's bottom row), reported with all 12 AUCs.
  4. **Score:** equal weights — the mean of the chosen features' percentiles against the trailing pool (the A+ registration's pool:
     every tl row with E′ in [E − 20, E − 1] on the SPY calendar; |S| ≥ 30 non-missing per feature, else that feature is missing;
     a missing feature counts 0.5, as the A+ read counts a missing scale). **No weight is fitted.**
  5. **The cap — TAKE:** the pool's reference scores (each member against the pool minus itself, the A+ member rule); the cutoff =
     the 24th-highest reference score (N = 6 a week × 4 weeks); TAKE = score ≥ cutoff AND fewer than 6 TAKE already in the ISO week
     (Mon–Sun by E) in (E, ticker A→Z) order; at-or-above after the week's six = CAPPED; fewer than 24 rated members = UNRATED.
     N = 6 is his "5–7"; N = 4 and N = 8 are reported beside, never deciding.
  6. **Plateau (decision 0023's convention: a pick whose neighbours collapse is an artefact):** the subset is re-derived at screen
     thresholds 0.56 and 0.60 and with each chosen feature left out in turn; the filter is frozen only if every neighbour flags, at
     N = 6, at least max(4, ⌈0.75 c⌉) of the 66 hold-out events, c = the registered subset's count (round 2's "within 25%" stated in
     events, ONE-SIDED in round 3: a neighbour that flags more never fails the plateau). **With ONE chosen feature leave-one-out is
     undefined: its neighbours are the two thresholds plus the subset with the next-ranked feature (fit AUC ≥ 0.50) swapped in; if
     no such feature exists the plateau is CAN'T TELL.** A spike is reported as CAN'T TELL.
- **What the fit measures (printed, outcome-free):** the 12 AUCs on fit and check sets with n; the chosen subset; TAKE per week
  (expected ≤ 6, median printed); **recall = the share of positive events flagged TAKE** on the fit set, the 2021 hold-out and the
  2022–23 check; beside, the share of not-yet EVENTS flagged TAKE (descriptive — this is not the readiness contrast, which is
  scored at the label date s0 below); the share of TAKE events
  that are C1 and first breaks vs retriggers; the by-year and by-phase splits. **Beside rows, each with n:** recall on the
  post-E-only and strictly-before events; the AUCs on the delta-0 subset (119 events — the on-the-day cluster, the only timing
  signal; derived from `labels_joined.tsv`'s `delta_tl` on the positive labels); the AUCs on the events whose positive label's
  phrase sits in the ticker's OWN caption line (§2h; the cleaner attribution — the per-label flag is recomputed by the fit module
  from the pinned `graded_moments.tsv` with the `GRADE_RX` regex of `01_join_labels.py`, keyed (vid, ts, caption_ticker); the
  aggregate it must reproduce is 350 / 58 / 35); the base-level reading (every event of a labelled base positive). **No forward flag (R1, R2, fill, outcome) is read
  anywhere in the fit.**
- **The readiness contrast (outcome-free; the state he was looking at):** the score computed at the LABEL date s0 for every not-yet
  label with a watch row at s0 (43 of 128 after the 15 positive-and-not-yet events leave the set; 50 before) against the score at s0 for every bought label with a watch row at
  s0 (176 of 624; 153 with a trendline) — the same moment on both sides (the night he spoke), so neither side is scored on a state
  from after its own label. **Named asymmetry:** the fit scores a positive EVENT at D = E − 1, while this contrast scores a LABEL at
  s0; the two agree only for a label said the session before our break. Beside: the 25 not-yet labels (32 before the same exclusion) whose matched event is 0 or 1
  session later, scored at that event's D (the fit's own moment, with at most one session of drift) against the 138 bought labels
  of the same kind. Expected: the not-yet side scores lower; the 15 positive-and-not-yet events stay out of the not-yet set (§3). Only 27 of
  the 80 not-yet events share a base with a bought event, so this is a contrast of STATES he judged ready vs not ready, not a
  same-base pairing.
- **The fit's own bar (outcome-free; decided on the 2021 hold-out, n = 66 positive events) — stated in EVENTS (round 3):** the
  no-information rate = the largest share of the 2021 stream a 6-a-week cap can flag = Σ min(6, rows in the week) ÷ 23,632 tl rows =
  **1.32%** (2021 runs a median 372 tl rows a week, not the 2017–21 205 round 2 used — its "≈ 3% / ≈ 9% / about 6 events" was about
  2× off). A filter with no information flags **0.87 of the 66** on average. **PASS** = at least **5 of 66** flagged (chance alone
  reaches 5 with probability 0.2%, Poisson mean 0.87) with the plateau holding and at least 1 of the 9 era-B check events flagged;
  **FAIL** = at most **1 of 66** (what chance gives 78% of the time), or an empty subset; **CAN'T TELL** otherwise (2–4 flagged, or ≥ 5 with none of the 9 era-B events). The 0.2% is conservative: the 2021
  positives sit in heavy weeks, so chance would flag about 0.66 of them, not 0.87 (base clustering — 66 events on 59 bases — pulls
  slightly the other way). Round 2's 3× bar would
  have passed on 3 events, which chance reaches 5.8% of the time; the bar was raised to 5 before any fit, for that reason alone.
  **The bar stays coarse — one event moves a verdict at its edges, and that is said with the result.** A PASS freezes the filter (its code, subset and pins written under the marker); otherwise his R2
  definition is the combined test's filter (§7).
- **The fit module's own guards (round 3):**
  1. **Whitelist.** It reads only these files: `track_a_1023/labels_joined.tsv`, `matched_events.tsv`, `vision/graded_moments.tsv`
     (the own-line beside row), each era's candidates and watch tables (§9 pins), the daily export bars dated ≤ D, and each era's
     G5 DISCONTINUOUS flags (the two files named in the corporate-actions note above). From the candidates / watch tables only `ticker, D, E, K, base_id, pole_date,
     retrigger, retrigger_chain, pivot, adr20, C1, base_len, phase_qqq_10_20, phase_qqq_10_20_s5, phase_spy_qqq_50, apollo_regime,
     split` (the last for era B's discovery cut) plus the twelve features' named inputs; it asserts no other column is read.
  2. **Shuffle test, before the fit:** the positive flag permuted within each E date, 200 permutations, seed 702 — the mean fit-set
     AUC of every feature must lie in [0.48, 0.52], else the module stops (a leak or a bug).
  3. **Shuffle test, after the subset is chosen and before the hold-out is read:** the REAL subset scored with the 2021 positive flags
     permuted within each E date, 200 permutations — the mean hold-out count must be ≤ 1.5 (chance expects about 0.66), else stop.
  4. **Look-ahead test (scope as built):** on a 500-row sample, everything the module computes itself from bars — `wk_ratio`,
     `pb_ratio`, `vol_dry5`, the DISCONTINUOUS windows and the watch-row lookup — is recomputed after every bar dated > D is replaced
     with noise and must be identical (a shuffle of labels cannot catch a feature that reads bars after D). The other eight features
     are read exactly as the pinned watch row at D stores them; their point-in-time guarantee is the detector's own slice test and
     `rs_returns`, not this test.
- **Readings the fit module chose where this text was ambiguous (recorded before the freeze; the reviewer accepted all but R-b, R-c,
  R-j, which are now written into the text above or here):**
  - R-a (§5.4–5.5): every pool member is rated; a missing value or a feature under the |S| ≥ 30 floor counts 0.5; UNRATED = a pool
    under 24 members. The strict A+ rule (a member counts only with every chosen feature present) is printed beside as a count.
  - R-b (corporate actions): the return windows are rs_best (D−126, D], grp_pct (D−63, D], prior_move (pole_low_date, pole_date];
    every flagged row counts, liquid or not.
  - R-c (flag files): as named in the corporate-actions note (the repo's `run_all_B` folder holds console output only).
  - R-d (readiness): s0 is treated as the watch night D; its pool is the tl rows with E′ in [s0 − 19, s0].
  - R-e (plateau, leave-one-out): the subset rule is re-run without that feature, so a sixth qualifying feature can enter; an empty
    neighbour flags 0 events.
  - R-f (subset): an AUC tie breaks by this section's table order (#1 … #12).
  - R-g (own-line beside row): at least one of the event's on-or-before-E positive labels has its own grade's phrase in its own
    caption line, keyed (vid, ts, screen_ticker).
  - R-h (base-level beside row): the bases of the 236 / 9 positives; negatives = the other rows on those dates minus the rows the
    round-3 rule excludes.
  - R-i (calendar): the SPY calendar is derived from each export's SPY rows (1,635 / 821 sessions, asserted).
  - R-j (the bar's denominator): 23,632 = tl rows with E in calendar 2021; the hold-out set is E > 2020-12-31 as in the join, which
    adds 2022-01-03 (85 rows, 0 positives, 0 negatives — asserted, `pos_hold_2022 = neg_hold_2022 = 0`).
- **What the fit may NOT do:** fit weights; fit directions; add a feature outside the 12; read any outcome column, any forward flag,
  any bar after D for a feature, any minute; change the window, the pool, N, the cutoff rank, the thresholds, the plateau's event rule or the positive
  class after seeing a result; run on 2025–26.

## 6. The SANITY READ — do the labelled breakouts carry edge? (registered, NOT run; runs after the fit is frozen)

- **Populations (per era).** GRADED = the positive events with ≥ 1 bought / best label said ON OR BEFORE E (era A **236**; era B
  **9**). UNGRADED = every other tl row on the same E dates with the labelled-base rows excluded (§4, round-3 rule; era A **23,188** on 156
  dates, era B **345** on 7 dates; the exact n re-printed by the module). **No not-yet arm** (a state, not an outcome arm — §3). **Beside,
  descriptive, never deciding:** the 87 / 3 post-E-only events (27 / 1 of them also sit in UNGRADED, §3; expected to read BETTER than GRADED because they were selected
  after the fact — a reading of the size of the hindsight bias, which is why they are not in the deciding arm); the 127 / 6
  strictly-before events (the only subset clean of E's bar); the R2 share of GRADED vs UNGRADED (the bdef flag, three-valued in
  era A) — a share, with no outcome row of its own. The matching is the same-day population itself (§4); no ordinary-stock control.
- **Unit and mix (round 3).** Every event is walked INDEPENDENTLY — a base with several crossings contributes several walks, and
  overlapping walks of one base are allowed, in both arms alike (Track B trades once per base; this read does not). The arms differ in
  mix by construction — GRADED about 1.26 events per base and 44% retriggers, UNGRADED 2.72 per base and 76.0% retriggers on 8,540
  bases (re-verified under the round-3 rule; the module re-prints them) — so **the DECIDING difference is computed separately among first breaks and
  among retriggers and combined with GRADED's own first-break / retrigger shares as weights** (UNGRADED reweighted to GRADED's mix;
  strata by `retrigger` (not `retrigger_chain`); the weights FIXED at GRADED's full-sample shares, 132 first breaks / 104 retriggers
  of 236, and not re-estimated inside a resample; an abstained event stays in its group; the bootstrap redraws months and recomputes
  the weighted difference inside each resample).
  **Beside, never deciding:** the raw (unweighted) difference and a one-event-per-base reading (each base's first event in the arm).
- **Entry (fully stated here; Track B's §D mechanics with the LEVEL replaced):** at E's CLOSE when close(E) > pivot_tl(D) — the
  module's trendline value projected to E, `high[A] + m × (E − A)`, the level the high cleared; else the event ABSTAINS (0 R, counted
  in the per-100 denominator on both sides, never dropped). **Stop:** entry × (1 − 1.0 × ADR20(D)), ADR20 the watch row's 20-day
  average daily range as a fraction, never capped. **Re-entry (T2):** after a STOP exit (the original or the breakeven stop), at the
  first CLOSE above the D-night line's value on that session, `level(t) = pivot_tl(D) + m × (t − E)` sessions with `m =
  tl_slope_pct(D) × high[A]` and `high[A] = pivot_tl(D) ÷ (1 + tl_slope_pct(D) × (i + 1 − A))` (the runner's `h60_anchor_high`), within
  20 sessions of E, at most two re-entries, the stop re-anchored to that session's close and ADR20; **the line is frozen at D and
  never redrawn; a flat line (m = 0) re-enters at the same price; a projected level ≤ 0 → no re-entry.** Both arms re-enter on the
  same kind of level, so the 10-22 control-retry caveat is weaker here but is still stated on every T2 row; **T0 (no re-entry) is
  the clean comparison.** The session-3 stall cut, the pessimistic touch-both rule (a bar touching the stop and a level books the
  stop), the +2R third (P1) or none (P0), breakeven after it, the 120-session horizon — exactly as `cb_trail_variants_2026-10-23.md`
  §D. This is NOT "held fixed at Track B's harness": Track B enters at the base-high close and re-enters above the base high; here
  the level is the trendline and the re-entry level its projection.
- **Exit cells (two, named now):** `A20_X1_P1` = `pp` (the carried exit: ⅓ at +2R, breakeven, the first close under the 20-day; his
  ruling) and `A20_X3_P0` (20-day · a 2-session reclaim forgiven · no partial — the cell that held the most doublers: 53% / 54% to
  half the move). No other cell.
- **Measures, tail first (per era × cell × T0/T2, n on every row):** ≥ 5R and ≥ 10R **per 100 EVENTS (entered + abstained; an
  abstained event is 0 R and stays in the denominator), per 100 ENTRIES beside**; the worst trade and the 5th-percentile trade
  (per-trade R); mean R per event (chain sum under T2; 0 for an abstained event); win rate descriptive; GRADED minus UNGRADED on
  each, with month-block bootstrap intervals (calendar month of E; **one draw of months per resample applied to BOTH arms, the
  difference computed inside each resample**; 2,000 resamples, seed 702, key `track_a_sanity|<era>|<cell>|<retry>`).
- **Costs beside every headline (the standard's step 8):** every R number at 0 / 0.1 / 0.2% exit slippage per leg; the entry pays
  the published 0.1%. The W3 fill-minute run-through does not apply — a close entry has no fill minute — and that is said on the
  table rather than left open. An edge that disappears at 0.1% is not an edge.
- **Data gate (STEP 0, `backtest_data_standard.md`) and the point-in-time declarations (step 3):** 2017–21 on `cb702_pre_v2` (passes
  S0, G1–G7, G9 in `cb702_pre_v2/audit_1023/verdict.txt`; complete events only, E + 120 sessions ≤ 2022-06-30; the walker `trail_lib`
  re-pointed at its daily export — no minutes are needed for a close entry); 2022–24 on `cb702` (**daily bars loaded with every row
  dated after 2024-12-31 dropped at read; `assert max(date) ≤ 2024-12-31`; `assert E + 120 ≤ 2024-12-31` for every complete event;
  the censored count printed beside every number**) with `symbol_guard_B.tsv` passed as `--breaks` (an event whose [E − 130, E + 120]
  straddles a listed break is excluded, counted) and `cb702_pre_v2/symbol_guard.tsv` for era A. **G8:** `trade_impact.py --kind r1`
  runs on THIS read's own trade file for EACH era before any number is quoted — era A on v2 must read entered-after-cutoff = 0 and
  holds-past-last-bar = 0 (asserted), era B's two counts are printed beside the headline and censored; the existing
  `runs_2026-10-23/A_r1_*_impact.txt` are `cb702_pre` and Track B's cells and are not this read's G8. **G10:** `pit_lint.py overlap
  --era-a cb702_pre_v2 --era-b cb702` is run in the freeze commit and its member-night agreement and vendor-agreement line printed
  beside the two-era table (the existing `pit_overlap.console.txt` compares `cb702_pre`, not v2, and is not quoted). **Point in
  time:** era A's symbols are keyed by today's symbol with the rename map and dedupe aliases (the join's 28 resolutions), era B's
  are point-in-time; security type and SIC from `cb702_sic.psv` as of 2026-10-16 (one row per ticker — `grp_pct`'s group membership
  is NOT point-in-time and can move for a ticker whose SIC changed, said beside that feature); splits as adjusted by each vendor at
  its fetch date (Alpaca A / Polygon B); the RS denominator = that night's export members (v2's, including the refetched delisted
  names), not prod's `mi_stock_scores`, so RS percentiles do not compare across eras (F7); `pit_lint.py lint` exit 0 printed in the
  freeze commit, and of the standard's F7/F8/F10 items these touch this read: N3/N4 (`rs_best`), N1 (`grp_pct`), N2 (type), N5
  (today's-symbol regex), L7 (the sealed cut above), L8 (a walk whose bars end inside the horizon is booked at its last close and
  reported with and without), W2 (the slippage rows), W3 (not applicable, said), F1 (no minutes used). Corporate actions: any trade
  containing a G5 DISCONTINUOUS event (OPLN, ZWS, BEP …) is flagged and the worst-trade figure is quoted with and without it.
- **Bar (era A decides; era B, n = 9, is descriptive):** needs ≥ 100 GRADED entries, else CAN'T TELL. **PASS** = under `pp` at T0
  the mix-reweighted GRADED − UNGRADED difference has its interval above zero on ≥ 5R per 100 events AND on mean R per event;
  **FAIL** = that mean-R difference's interval has upper end < 0; **CAN'T TELL** otherwise. `A20_X3_P0`, T2, the per-100-entries rows and every
  beside row are reported, never deciding.
- **Expectations, written now:** GRADED ≥ 5R per 100 events above UNGRADED's (the UNGRADED rate about the R1 population's 1.4–3.9
  per 100 by cell); the post-E-only events above GRADED (hindsight); the worst GRADED trade a one-session gap of about −7 to −10 R as
  in every read. A miss changes no rule.

## 7. Consequence — fixed now

| fit (§5) | sanity (§6) | what the ONE combined sealed test reads as the PRIMARY filter | beside (descriptive, no bar) |
|---|---|---|---|
| PASS | PASS | **the frozen label filter** (TAKE flag) × Track B's exit | his R2 definition; the full stream |
| PASS | CAN'T TELL | the frozen label filter | R2; the sanity verdict quoted next to the result |
| PASS | FAIL | **his R2 definition** (the base high cleared on an expansion day) | the label filter, recorded not deciding |
| CAN'T TELL / FAIL (incl. an empty subset) | any | **his R2 definition** | the label fit's table, reported to him |

The sanity read does not change the fit (the fit is frozen first and touches no outcome); it decides only which filter is primary.
Recording the primary filter's flag in the forward shadow is a recorder change (no order path); paper or live is his sign-off.

## 8. Interface with the ONE combined sealed 2025–26 test (registered this weekend; this doc fixes only the interface)

- **Input:** a tl candidate row (stock, E) of the sealed table, the watch row (stock, D = E − 1), and the pool of tl rows with E′ in
  [E − 20, E − 1] (the first 20 sessions pool from the pinned 2022–24 table, as the RS-alone read does).
- **Output per row, computed from bars ≤ D only:** `score` ∈ [0, 1], `pool_n`, `cutoff`, `flag` ∈ {TAKE, PASS, CAPPED, UNRATED}, and
  the chosen features' percentiles. **When:** at the moment the candidate exists (the high clears the line on E) — before any
  fill; nothing about E's own bar or minutes, nothing about later rows of the same day, enters (the A+ read's WOULD-FAIL-IF
  invariance: shuffling every E-day-or-later column changes no flag).
- **Expected size:** ≤ 6 TAKE a week, about 5 on a median week (the cap binds only when the week has six at or above the cutoff).
- The combined test applies Track B's exit to the TAKE rows once, on the sealed table, with the full stream and R2 beside; its
  entry / stop and its bar are the weekend registration's, not this doc's.

## 9. Method / population

- **Labels:** `apollo_data/cb702/qm_streams/vision/grades_labels.tsv`, rows `status = attributed` — **n = 854** (bought 662, not_yet
  125, best 59, mixed 8; exploded bought 669 / not_yet 129 / best 64), 283 stocks, screen dates 2017-01-24..2023-06-09 (2020: 485,
  2021: 251). Built by `scripts/probes/_705_grades_1022/03_frame_check.py` (caption ticker = on-screen ticker = our bars confirm the
  ADR% AND an axis price — the a-AND-b rule: **94.0% recall (842 of 896 positive-control frames), 1.8% false match (398 of 22,218
  wrong-ticker draws)**; 95.6% is the ADR-only read, whose false match is 9.2%). The grade phrases: `02_graded_moments.py`, matched
  over the caption window; the ticker's own line (`graded_moments.tsv`, `quote`, 220 chars) is read in round 2 for §2h.
- **Events:** era A `cb702_pre_v2/out/candidates_tl_com.tsv` (K = tl, split `pre`, E 2017-03-02..2022-01-03; 81,015 tl rows,
  20,650 first breaks); era B `cb702/out/candidates.tsv` + `candidates_com.tsv` (split `discovery`, every row with D or E after
  2024-12-31 dropped at read and asserted; tl 41,200 rows, 12,250 first breaks, E 2022-04-01..2024-12-31). Watch rows:
  `watch_tl_com.tsv.gz` / `watch.tsv.gz` (era B cut the same way: 109,961 holdout rows dropped). R1 / R2 flags: `bdef_r1_*` and
  `bdef_fills_*` of `cb702_pre/out` (the OLD export) and `cb702/out`, columns ticker, D, E, t, entry_date, r2_exp only — descriptive
  (§2e), fed nowhere. Calendars: `cb702_pre_v2/sessions.txt` (1,635 sessions) and the SPY dates of the cb702 export kept ≤ 2024-12-31
  (821). Columns loaded from the candidates: ticker, D, E, K, pole_date, pole_ci, retrigger, retrigger_chain, base_id, split, C1 —
  no E-day bar column.
- **Windows:** the join window [s0 − 10, s0 + 20] sessions. **The placebo's three conditions (the code's, written out in round 2):**
  (1) the symbols are the 200 with a BOUGHT label and coverage in era A (158 of them have a watch row and a tl event); (2) t runs over
  the sessions whose whole window [t − 10, t + 20] sits inside the era's E range (indices Emin + 10 .. Emax − 20); (3) t is excluded
  when it lies within ±20 sessions of ANY attributed label of that symbol, of any grade; t counts when the symbol has a watch row in
  [t − 10, t + 20] (51,884 sessions) and a tl event in the same window (42,781, the nearest one by the join's tie rule).
- **Outputs:** `apollo_data/cb702/qm_streams/track_a_1023/labels_joined.tsv` (one row per label; round 2 added the column
  `no_break_yet_base`) and `matched_events.tsv` (one row per distinct (era, stock, E); byte-identical to round 1); the printed summary
  `scripts/probes/_705_track_a_1023/01_join_labels.txt` with the sha256 pins of every input. No DB, no network, no subagent; nothing
  pinned was written or moved; the runner was not imported.

## 10. What this does not answer — known limits

- **Whether the labelled breakouts PAY under any entry / stop / exit.** Unread by design; §6 is registered, not run. Entries and
  exits stay undetermined for a new setup.
- **After-the-fact selection is removed from the deciding arm, not from the data.** 87 of 323 events carried only labels said after
  our breakout and are out; but a label said ON E (119 events) was said with part of E's bar visible, so the positive class is not
  clean of E — only the strictly-before 127 are, and they are a beside row. Every result carries this against its headline.
- **The timing carries little information.** Beyond the ~60-label excess at delta 0, the labels sit where a random near-a-base
  session of the same stocks sits (before-share BELOW the placebo, no excess one or two sessions early). What a label tells us is
  WHICH base he liked, not when; the join window and the nearest-event rule are therefore the main source of noise in the positive
  class (190 of 392 bought labels sit on a retrigger).
- **Grade-phrase attribution.** The grade regex ran over the caption window around the ticker's line; the phrase sits in the
  ticker's own line for 350 of 669 bought labels, 58 of 129 not-yet and 35 of 64 best. The rest may belong to the neighbouring
  stock discussed in the same breath (an upper bound: the line is cut at 220 characters). The AUC on the own-line subset is a beside
  row in §5 for exactly this reason.
- **The negative class is noisy by construction:** "not shown on stream" is not "rejected". The fit's separation is a floor.
- **The labels are 2017–2023 stream moments, 91% from 2020–21** — one regime (the 2020 rebound and 2021). The 2022–23 check holds
  9 positive events; it checks direction, not a rate. The fit's hold-out is 2021, inside the same era, and at n = 66 its bar is coarse.
- **Caption = screen = confirmed only:** 1,618 of 2,472 graded moments are unattributed (the stock on screen was not the one named,
  the chart was unreadable, or our bars could not confirm it — 227 frames on 114 names outside our bars, GBTC the most frequent). The
  1.8% false-match rate is the rate at which a WRONG ticker passes the bar check; applied to 854 labels it bounds the number on the
  wrong stock at about 15 — an upper bound, not a count.
- **Survivorship is fixed only for era A's event file (v2); era A's R1 / R2 flags are from the OLD export's published fills**, so 202
  of the 297 bought events have no R1 / R2 reading. They feed nothing (§2e); the sanity read walks v2 directly.
- **Stream selection:** he shows what he likes; a base he never showed is not a base he rejected.
- **Detection misses are named, not fixed:** 87 labels on names outside our universe (ETFs, ETNs, leveraged funds; 54 symbols) and
  140 on bases our structural gates did not hold in the window. A filter cannot rate what the detector never watched; that is the
  "not missing the good ones" line of Track A (the 50-day and 30%-run-up gates), a separate read.
- **The retrigger ambiguity and the drift re-fires:** 190 of 392 matched bought labels sit on a retrigger; a label marks a base, and
  the first break of that base may be the event he meant. 3,636 of the 20,650 era-A "first breaks" (`retrigger = 0`) are re-fires of
  the same line after its pole re-dated by a day (`retrigger_chain = 1`): on a chain-first count the stream is 43 first breaks a week
  (era B 59), his 5–7 is one in seven rather than one in nine, and the bought-vs-first-break split reads 52.0 / 7.9 / 40.2% (n = 331)
  against 50.9 / 9.9 / 39.2%. The fit labels the nearest event; the base-level reading (every event of a labelled base positive) is
  reported beside, never deciding.
- **The window and the placebo are session-based on daily data;** a stream moment is a time of day, and a chart shown at 11:34 on the
  breakout day (SQM) is "on the day" whether he bought that morning or the day before.
- **Nothing about 2025–26.** Unread; the interface in §8 is the only thing the combined test consumes from here.

<!-- FREEZE -->
## Freeze record

Pins (sha256) printed by `01_join_labels.py` on 2026-10-23 (round 3 run, commit `84a19c0c`; the join's inputs and outputs; the fit module `02_fit_filter.py`
and the sanity module do not exist yet — their pins are added here in the freeze commit that precedes each run, and the doc body above
the marker is pinned in that commit). Round 1's script and doc were committed in `81c39f6b`, round 2 in `530ff2a0`, round 3 in the commit after it; every round's
`labels_joined.tsv` / `matched_events.tsv` hashes are printed above, and no outcome column exists in either.

- labels: `f4116fd99a1b7db88a74b88a7278aa6e434cf8788b7003af8bbc39e72ac2269a`
- moments `vision/graded_moments.tsv` (round 2, §2h): `f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0`
- cal_A `cb702_pre_v2/sessions.txt`: `098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0`
- cal_B `track_a_1023/spy_sessions_eraB_le_2024-12-31.txt`: `a17d991a25a1b6b6977c388f352213142868635f94c2010813a7a0f8ef79d2be`
- cand_A `cb702_pre_v2/out/candidates_tl_com.tsv`: `3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a`
- cand_B `cb702/out/candidates.tsv`: `b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7`
- cand_B_com `cb702/out/candidates_com.tsv`: `07c24ccea7dae4488428cb2f8fb6302c49c1090106f8a3cb6f13a6413a4ac6b3`
- watch_A `cb702_pre_v2/out/watch_tl_com.tsv.gz`: `976c19cd51a71637789817851e9b84d86504270b60f306e5a720b0915810cf43`
- watch_B `cb702/out/watch.tsv.gz`: `59e757cacb3250066393d0395e4abe89adff3787c34d1f2f7ad5fd5e2f2a5c0b`
- bdef_r1_A `cb702_pre/out/bdef_r1_2017-21.tsv.gz`: `02f02171bca20ce1d9379f1a30208f5167bf89c708d99ecb96d954b637c78ae0`
- bdef_r1_B `cb702/out/bdef_r1_2022-24.tsv.gz`: `adf84c0f65b031ce882e6cfb1521a90e005582aa4372cac08194f3fa943c50b0`
- bdef_fills_A `cb702_pre/out/bdef_fills_2017-21.tsv.gz`: `65a20d69ef4479c5ca13872e46a0ddfa5b77a39f31f338597b7018091f3392ce`
- bdef_fills_B `cb702/out/bdef_fills_2022-24.tsv.gz`: `7026e0ca4e887e7d6dae33fb537cf73bfa5657e23be49b831bded1f056441227`
- export_A `cb702_pre_v2/daily_closes_all.csv.gz`: `0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d`
- alias dedupe_applied.tsv: `223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64`
- alias refetch_dropped.tsv: `6e325eccfe159cdce596deff2261caffcd3113be632c0a4bf83a9974b5751dd0`
- alias rename_map.tsv: `02653560aa435762870dc90b0ef0d2fd7ab803a518f9e8c89772bcdd4fb34a57`
- join script `01_join_labels.py` (round 3b: §12 rule + one label and the one-decimal medians): `6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c` (round 3: `6b1dfb57…9c97`; round 2: `7fc6452c…cb88`; round 1: `4ff17ee0…ceac`)
- join printout `01_join_labels.txt` (round 3b): `5779b82bd954aa00f7294d52bc55afe0fe7478f4a58d8e0df9a1f10913b1d1f9` (round 3: `3b90134e…4793`)
- out labels_joined.tsv (round 2; one column added): `d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b` (round 1: `13df2952…95a3`)
- out matched_events.tsv (byte-identical to round 1): `4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc`
- **FIT FREEZE (2026-10-23, the commit that adds these lines; the real fit runs only after it):**
  - doc body sha256 (the bytes above `<!-- FREEZE -->`): `4ad0d14e2092c9dc51225978871a900c3ad87d72504ae6a3126f7f51cd2d627e`
  - fit_module `scripts/probes/_705_track_a_1023/02_fit_filter.py`: `3fca7bf4f26ffcdf7152ddc9d4180c295aafe29067591def812fcc6884f38d27`
  - its tests `test_02_fit_filter.py` (90 pass): `463e6d78f05323b236d60f616130ff3fa17ff0f850fb8764fe907fbb8860db34`
  - export_B `cb702/daily_closes_all.csv.gz`: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
  - flags_A `cb702_pre_v2/audit_1023/price/A_flags.tsv`: `5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d`
  - flags_B `apollo_data/audit_runs_2026-10-23/B_flags.tsv`: `8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5`
  - aplus_read `scripts/probes/_cb_backtest/aplus_read.py` (imported read-only): `e344277817db88de7af2e65ad8858d4ca515c3cc3a647b3e0a67e0df9f7ec9ee`
  - registered_read `scripts/probes/_cb_backtest/registered_read.py` (imported read-only): `28fbc47f862f205071ab921af3a29f6093fca95e2d41e3a0f4a0f7afcd9aa449`
  - join_script `01_join_labels.py` as the module reads it: `6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c`
  - review of the module: `scripts/probes/_705_track_a_1023/verify/review_fit_module.md` (Opus, FIX → fixes 1–6 applied: doc §5 text, two code guards, 37 tests)

## Revisions 2026-10-23 round 2 — each checker fix and where it landed

Two kinds, said on each: **(a)** a round-1 rule written out as the code actually ran it (no change to any count the join produced);
**(b)** a checker-mandated change to the registration or a new count. Neither is a re-tune — no outcome exists. L = `logic_report.md`
"Fixes required before freeze" 1–10; R = `recount_report.md` "Exact fixes" 1–9. Overlaps done once.

| fix | kind | what changed | where |
|---|---|---|---|
| L1 | b | positive class and the deciding GRADED arm = events with ≥ 1 bought/best label ON OR BEFORE E: 236 (170 fit / 66 hold-out); post-E-only 87 (58 / 29) and strictly-before 127 (90 / 37) beside; era B 9 / 3 / 6; after-the-fact selection named | §0, §1.4f, §2h, §3, §5 fit set + bar (n 170 / 66 / 9), §6 populations, §10; script §11 |
| L2 | b | "R2 subset of GRADED" deleted; "R2 share of TAKE" removed from the fit; R2 survives only as a descriptive GRADED-vs-UNGRADED share beside §6 and in §2e; "no forward flag of any kind is read in the fit" | §2e, §5 header + measures + may-not list, §6 |
| L3 | b | same-day rows on a labelled base (any grade) excluded from the negatives and from UNGRADED and counted: 704 / 36 not-yet on the 193 dates (round 1's set); 654 / 33 / 45 post-E-only on the 156 dates → 22,944 negatives (14,959 / 7,985); era B 9 of 352 → 343; what a not-yet event is, in both places | §2h, §4, §5 fit set, §6; script §12 |
| L4 | b | NOT-YET removed from §6 (populations, measures, expectations); §3 says "§6 carries no not-yet row" | §3, §6 |
| L5 | b | readiness contrast scored at the LABEL date s0 (not-yet 50 of 128 with a watch row, bought 176 of 624); the 32-of-86 / 138-of-392 restricted version beside; the asymmetry with the fit's D named; "on the same bases" → 27 of 80 share a base; the 12 both-label events' reason rewritten (4 later-buy, 1 same moment, 2 mixed window, 5 after) | §2h, §3, §5 readiness contrast; script §13 |
| L6 | b | entry, stop and re-entry fully stated incl. the sloping-line re-entry level (`pivot_tl(D) + m × (t − E)`, m from `tl_slope_pct` and `h60_anchor_high`, line frozen at D, flat line, level ≤ 0); "held fixed at Track B's harness" dropped and the difference from Track B stated | §6 entry bullet |
| L7 | b | G8 on BOTH eras' own trade lists (era A asserted 0/0, era B censored + printed; the existing impact files named as not this read's); cost rows 0 / 0.1 / 0.2% per exit leg + entry 0.1%, W3 not applicable said; G10 run on v2 vs cb702 in the freeze commit (the cb702_pre console not quoted); point-in-time declarations (symbol keying, SIC/type as of 2026-10-16, splits, RS denominator, `--breaks`, the F7/F8/F10 items that touch this read); DISCONTINUOUS exclusion inside `rs_best` / `grp_pct` / `prior_move` windows; era B walker cut + two asserts | §5 feature note, §6 data-gate bullet + costs bullet |
| L8 | b | §0 and §2c rewritten: before-share BELOW the placebo (163 vs 212.1), no anticipation signal (+1: 25 vs 26.0; +2: 7 vs 18.6), the excess +60.1 at delta 0 only; D stands on the fixed rule's third branch alone; label-timing noise and grade-phrase attribution added as limits; AUC on the delta-0 subset (119 events) and on the own-line-phrase subset registered as beside rows | §0, §1.4g–h, §2c (expected row + reading), §3, §5 beside rows, §10; script §4 excess line, §14 |
| L9 | b | empty subset = FAIL (§5.3, §7 bottom row); one-feature plateau defined (two thresholds + swap-in of the next feature ≥ 0.50, else CAN'T TELL); per-100 denominator = events (entered + abstained), per 100 entries beside; abstained event = 0 R, in the denominator; same-month resampling of both arms | §5.3, §5.6, §6 measures, §7 |
| L10 | a/b | 94.0% recall (842/896) with the ADR-only 95.6% / 9.2% beside; "about 15 on the wrong stock" → an upper bound from the 1.8% wrong-ticker pass rate; 193 dates / 29,237 rows (and 156 / 23,598 under the restriction); §0 "both deciding eras" → "era A decides, era B descriptive"; "nothing 2025+ opened" → "rows after 2024-12-31 dropped at read and asserted, no era-B price read"; "direction FIXED FROM HIS WORDS" → "fixed before the fit; S / B / R tags", the B-tagged directions bolded; **"commit the script and doc" — NOT done: the brief forbids commits; round 1 is in `81c39f6b` and that is stated in the freeze record** | status line, §0, §5 table header, §9, §10, freeze record |
| R1 | a | "53 symbols" → 54 symbols (92 labels) | §2a, §10 |
| R2 | b | "199 drift-robust chains" and era B's "11 chains" deleted (the count was distinct (symbol, 0/1 flag) pairs); 288 bases on `base_id` kept; the `distinct chains` item removed from the script | §2f; script §7 |
| R3 | a/b | the "same base not yet broken" rule stated (candidate `pole_date` = watch pole_date); the `base_id` key added beside: bought 33 (5.3%), others unchanged; the six drifted-pole labels named (SHOP, PINS, AMD, VIR, CMCM, HUYA) | §2d; script per-label `no_break_yet_base` + §5 |
| R4 | a | the placebo's three conditions written out (200 bought symbols with coverage; t with its whole window inside the E range; ±20 of ANY attributed label excluded) + 51,884 / 42,781 | §2c row label, §9; script header + §3b line |
| R5 | a/b | distinct-events delta = the label CLOSEST to E (103 / 110 / 84; 54.9% within [−2, +1]); round 1's first-in-file-order row beside; the not-yet median printed as 0.5 (one-decimal formatting) | §2c; script §3 + `split()` |
| R6 | a | "the horizontal levels less" → "mixed (k5 13, k10 9, full 9 of 28, against tl 10)" | §2b |
| R7 | a | SQM: retrigger flag 0 but chain flag 1, the same base fired 10-04, the frame's last daily bar is 10-04; ROKU: a tie with the 06-14 event at −2, the later-E rule picked +2, the line had already fired and failed | §2g |
| R8 | a | "96% recall" → 94.0% (with the ADR-only figure); "the before-share is chance" → below the placebo (41.6% vs 54.1%), on-the-day above it (28.8% vs 13.5%) — same edits as L8 / L10 | §0, §2c, §9 |
| R9 | a | the drift re-fire note (3,636 of 20,650; chain-first weekly median 43 / era B 59; one in seven; the chain-first bought split 52.0 / 7.9 / 40.2% on n = 331); the stale "22 labels before 2017-03-02" header comment → the 6 of 2017-01 and the 13 of 2022-01..02 | §2f, §10; script header |
| D11 (recount, cosmetic) | a | medians and quartiles printed to one decimal | script `split()` |

What round 2 did NOT change: the join window, the nearest-event tie rule, the era split, the target rule and its thresholds, the
12 features and their directions, the pool, N = 6, the cutoff rank, the exit cells, the bars' thresholds. `matched_events.tsv` is
byte-identical to round 1; `labels_joined.tsv` gained one column. The two checkers' reports are the record of why.

## Revisions 2026-10-23 round 3 — the recheck's three blockers and its small items (applied by the main loop)

| fix | what changed | where |
|---|---|---|
| P1 | the same-day exclusion counts a label only if it was said ON OR BEFORE the excluded row's own E (round 2 counted a label at any time, so 244 rows — 75 bases later labelled bought or best — left the control for what happened after their breakout day). Era A 410 excluded → **23,188** negatives (15,107 fit / 8,081 hold-out); era B 7 → **345**; the round-2 numbers printed beside. Recomputed by the join (`01_join_labels.py` §12, outcome-free) and equal to the recheck's own count | §0, §2h table, §4, §5 fit sets, §6 populations; script §12 |
| P2 | §6 states the unit (every event walked independently, overlapping walks of one base allowed in both arms) and makes the DECIDING difference mix-reweighted (first breaks and retriggers separately, combined with GRADED's shares); raw difference and one-event-per-base reading beside | §6 unit-and-mix bullet, §6 bar |
| P3 | the fit's bar in EVENTS from the true 2021 no-information rate (1.32%, 0.87 of 66 expected): PASS ≥ 5 of 66 (chance 0.2%), FAIL ≤ 1 (chance gives that 78% of the time), CAN'T TELL 2–4; the plateau in events (every neighbour ≥ 4 and ≥ the registered count − 1). Round 2's 3× bar would have passed on 3 events (chance 5.8%), so it was raised before any fit | §5 bar, §5.6 |
| small | readiness-contrast populations 43 / 25 (the 15 events carrying a positive AND a not-yet label leave the not-yet set — 12 with bought, the rest best; round 2 said 12 and 50 / 32); the not-yet TAKE share renamed (it is not the readiness contrast); the fit module's column whitelist and shuffle test registered; the join printout pinned | §2h, §3, §5 |

Not changed by round 3: the positive class (236 / 9), the features and directions, the pool, N = 6, the cutoff rank, the exit cells,
the sanity read's bar thresholds, the join's window and tie rule. `labels_joined.tsv` and `matched_events.tsv` are byte-identical to
round 2.

## Revisions 2026-10-23 round 3b — the round-3 recheck (`verify/recheck_round3.md`): two one-line blockers, three module fixes, nits

| fix | what changed | where |
|---|---|---|
| B1 | a post-E-only event (27 era A / 1 era B) and a not-yet event whose call came after its E (4) stay NEGATIVES on a graded date — the prose had said "neither class", which a module built from it would have turned back into P1's hindsight; both modules assert 23,188 (15,107 / 8,081) and 345 | §3, §4, §6 beside |
| B2 | plateau = every neighbour ≥ max(4, ⌈0.75 c⌉), one-sided — round 2's 25% stated in events (round 3's "c − 1" was stricter above 7 events while claiming to be the same rule) | §5.6, may-not list |
| I1–I3 | the whitelist names its files and the columns the fit prints (C1, base_len, the phase columns, apollo_regime, split); the shuffle test split into a pre-fit AUC band and a post-subset hold-out check (chance about 0.66), plus a look-ahead test on bars after D; bootstrap strata by `retrigger` with weights fixed at 132 / 104 | §5 guards, §6 unit and mix |
| nits | title / status round 3; CAN'T TELL "otherwise"; the chance figure's conservatism; 13 of the 15 positive-and-not-yet events positive (MRNA, ROKU post-E-only); 72 → 75; the mix counts re-verified; the pin record names `84a19c0c`; the script's §12 label and one-decimal medians | throughout; script |


## RESULT — the frozen fit, run once 2026-10-23 after the freeze commit `d254cf5a` (printout `scripts/probes/_705_track_a_1023/02_fit_filter.txt`)

- **BAR VERDICT: FAIL** — 1 of the 66 hold-out (2021) positive events flagged TAKE at N = 6 (FAIL ≤ 1; chance alone 0.87); fit set 4 of
  170 (plus 4 CAPPED); era B 0 of 9; N = 8 beside: 2 of 66. Plateau FAILS (every neighbour 0–3). Recounted independently from
  `fit_take.tsv` by the main loop: 170 / 66 positives, 1 TAKE on the hold-out, 4 TAKE + 4 CAPPED on the fit set, 2 at N = 8.
- **Guards:** look-ahead PASS (500 rows); pre-fit shuffle PASS (every feature's mean AUC in [0.48, 0.52]); post-subset shuffle PASS
  (mean 0.275 ≤ 1.5); every population assert passed.
- **Subset chosen:** `rs_best` (fit AUC 0.781, hold-out 0.720), `prior_move` (0.735 / 0.727), `pole_day_vol_ratio` (0.666 / 0.538),
  `wk_ratio` (0.591 / 0.597). Against their fixed direction, reported not flipped: `base_depth` 0.371 (his picks sit in DEEPER bases than
  the day's other breakouts), `dist_level_adr` 0.466, `pb_ratio` 0.499.
- **Why a real separation still fails the bar (descriptive, main loop, from `fit_take.tsv`; not a verdict):** his picks rank high on
  the score but not at the extreme — the median hold-out pick sits at the 75th percentile of its day's breakouts (fit set 84th);
  18 of 66 are in the top 10% of their day, 6 of 66 in the top 1.3%. The registered cap — 6 a week out of 372 trendline crossings a
  week in 2021 — keeps about the top 1.3%, so it misses almost all of them. Read from the hold-out after the verdict, so any wider cap
  is a NEW registration for data not yet read, never a re-read of 2021.
- **Readiness contrast:** none — at the label date the not-yet calls (n 43) and the bought calls (n 176) score the same
  (P(bought above not-yet) 0.511).
- **Consequence (§7, fixed before the run):** FAIL → **his R2 definition (the base high cleared on an expansion day) is the PRIMARY
  filter of the ONE combined sealed test**; the label fit's table is reported to him. The sanity read (§6) stays registered and
  runs under its own freeze.
