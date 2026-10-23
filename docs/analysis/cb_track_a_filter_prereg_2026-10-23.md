# #705 Track A — the breakout FILTER built from Qullamaggie's own stream grades: pre-registration (2026-10-23)

**Status: DRAFT — not frozen. OUTCOME-FREE so far: no forward return, R, P&L, stop, exit or bar after a breakout day has been read
for any event named here; nothing dated 2025-01-01 or later has been opened.** Measurement and registration only. Nothing here
changes or proposes to change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state — those are the
operator's (THE LINE). The filter, when frozen, is a flag per breakout event that the ONE combined sealed test reads; whether it is
ever used is his call.

His words this doc serves (2026-10-22, verbatim): *"The edge comes from which breakout to pick (the A+ setups), but also positive
risk v reward"*; *"That is ridiculous amount … we need to cut out 90% of the trades"*; *"We need to attack from both ends, we need
to filter to less breakouts, trade reasonable amount and have better way to keep winners without taking major losses"*; and on the
labels: *"The whole point is to quantify his system, what better labels then his own"* — *"He often say it's A+ or not, or say it
needs a few more days to tighten etc."*

## 0. In plain words

- **What was measured today (outcome-free, `scripts/probes/_705_track_a_1023/01_join_labels.{py,txt}`):** where his 854 attributed
  stream grades sit against OUR breakout events (the trendline level `tl`, the registered one). **In 2017–21, 392 of his 624 "bought"
  labels (62.8%) have one of our tl breakouts of the same stock within 10 sessions before or 20 after the screen date**, 86 of 128
  "not yet" labels (67.2%) and 32 of 60 "best" (53.3%). The screen date IS our breakout day on 113 of the 392 bought labels (28.8%) —
  **2.1× what a random near-a-base date of the same stocks reads (13.5% of 42,781 placebo sessions)** — with 163 (41.6%) before our
  breakout and 116 (29.6%) after it; the placebo reads 54.1% before / 32.4% after, so the before-share is chance and the on-the-day
  share is the signal. Against his OWN breakout definition (the first close above the base high, R1) his "bought" comes a median
  14 sessions EARLIER (98 of 109 labels with an R1 row, 89.9%): **he buys at or around our trendline break, well before the base high
  is cleared on a close.**
- **The target, by the rule fixed before the run:** neither "before" (41.6%) nor "on" (45.7% within −2..+1) reached 60%, so the
  registered target is **the breakout-day EVENT (ticker, E) with the base's STATE read at the watch night D** — the filter rates a base
  the night before, and the flag applies when the line breaks. That reading fits both facts: the on-the-day cluster, and his
  anticipation entries a day or two earlier (AMRX, 10-22).
- **What is registered (nothing run yet):** (1) a FROZEN FILTER — ≤ 5 features chosen from his labels against the OTHER breakouts of
  the same day, equal weights, directions fixed from his words, a trailing-pool percentile score and a weekly cap of 6 (his 5–7
  a week against a stream of 53 first breaks / 205 line-crossings a week); (2) a SANITY READ that the labelled breakouts carry edge
  against the same-day ungraded ones under two of Track B's exit cells (`pp` and 20-day · reclaim forgiven · no partial), tail
  first, month-block intervals, both deciding eras, nothing after 2024-12-31; (3) the interface to the ONE combined sealed test.
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
   likes (stream selection); (e) the 1.8% false-match rate of the frame check.

## 2. The join — what his labels sit on (outcome-free; run 2026-10-23; every choice fixed in the script header first)

**Fixed before the run.** Label session s0 = the last SPY session ≤ the screen date (9 of 854 fell on a weekend). Window: a tl event
with E in [s0 − 10, s0 + 20] sessions (why: "bought" is said at or soon after the entry; "needs a few more days" should resolve
within about a month; our tl trigger fires early relative to his base-high breakout, so the window reaches further forward). delta =
idx(E) − idx(s0): **positive = the label came BEFORE our breakout day, 0 = the screen date is the breakout day, negative = after.**
Nearest event by |delta| among first breaks and retriggers alike; a tie goes to the later E. Era A = screen date ≤ 2022-01-03 (the
rebuilt 2017–21 file `cb702_pre_v2`, candidates built on it 10-23); era B = later (`cb702`, discovery rows only; 174,495 holdout rows
and 328 rows dated after 2024-12-31 dropped at read, asserted). A label whose window does not touch the era's E range is a coverage
fact, not a miss (6 labels of 2017-01 and 13 of 2022-01..02, the gap between the eras).

**Symbol resolution (era A):** 783 own, 15 through `refetch_dropped.tsv` (NXTD→LGMK, SI→SICP, DPW→NILE, AHPI→AHPIQ, WTRH→ASAP,
MOXC→ABTS), 13 through `rename_map.tsv` (EXPI→AGNT, PKI→RVTY, CHK→EXE, SGH→PENG, SQ→XYZ); 0 unresolved.

### 2a. Funnel (labels with coverage)

| era | labels | coverage none | never in our watch table (untyped: ETF / ETN / leveraged) | watched, but no watch row in the window | in a base in the window, no tl event in it | MATCHED |
|---|---|---|---|---|---|---|
| A 2017–21 | n = 811 | 6 | 87 (84) | 140 | 72 | **506 of 805 (62.9%)** |
| B 2022–24 | n = 43 | 13 | 5 (4) | 9 | 4 | **12 of 30 (40.0%)** |

The never-watched names (53 symbols) are mostly funds our universe rule does not admit — TNA ×7, XOP ×5, TQQQ ×4, TAN ×4, QQQ ×4,
IGV ×4, NRGU, SPXL, SOXL, GDX, KWEB, SMH, KRE … — plus small stocks under its price / dollar-volume floors (LGMK ×4, EMAN, HCCH, GORO,
BIOC, MVST …); "untyped in the SIC file" is a proxy for the fund share, not a classification. The 140 "watched but not in the window" are bases our structural gates (prior
move ≥ 30%, base 10–45 sessions, close ≥ SMA50, the deal-pin guards) did not hold on those nights — the detection miss class, named
in §10, not fixed here.

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
bought 12 of 28); the horizontal levels less (era B bought: k5 13, k10 9, full 9 of 28). The registered level stays `tl`.

### 2c. Position relative to our breakout day E (matched labels; delta > 0 = label before the breakout)

| set | n | BEFORE (delta ≥ +1) | ON (delta = 0) | AFTER (delta ≤ −1) | within [−2, +1] | median (quartiles) |
|---|---|---|---|---|---|---|
| A · bought, nearest tl event | n = 392 | 163 (41.6%) | **113 (28.8%)** | 116 (29.6%) | 179 (45.7%) | 0 (−1..+5) |
| A · bought, nearest FIRST BREAK | n = 334 | 170 (50.9%) | 33 (9.9%) | 131 (39.2%) | 89 (26.6%) | +1 (−3..+10) |
| A · bought, distinct (stock, E) events | n = 297 | 108 (36.4%) | 100 (33.7%) | 89 (30.0%) | 151 (50.8%) | 0 (−1..+3) |
| A · not_yet, nearest tl event | n = 86 | 43 (50.0%) | 23 (26.7%) | 20 (23.3%) | 43 (50.0%) | 0 (0..+4) |
| A · best, nearest tl event | n = 32 | 12 (37.5%) | 9 (28.1%) | 11 (34.4%) | 16 (50.0%) | 0 (−1..+2) |
| B · bought, nearest tl event | n = 10 | 6 | 2 | 2 | 5 | +1 (0..+5) |
| **PLACEBO** — the same stocks' other near-a-base sessions (era A, bought symbols) | n = 42,781 | 23,145 (54.1%) | 5,775 (13.5%) | 13,861 (32.4%) | 12,743 (29.8%) | +1 (−2..+8) |

The histogram of the 392 (delta: n): −10:3 −9:12 −8:7 −7:6 −6:9 −5:5 −4:21 −3:12 −2:17 −1:24 **0:113** +1:25 +2:7 +3:12 +4:11 +5:11
+6:11 +7:4 +8:9 +9:10 +10:5 +11:6 +12:10 +13:3 +14:8 +15:4 +16:5 +17:4 +18:4 +19:4 +20:10. Of the 624 bought labels with coverage,
500 (80.1%) have a tl event within ±60 sessions; the window was not re-tuned after seeing this.

**Second anchor — his own definition's day (R1, the first close above the base high):** of the 392, 109 have an R1 row in the
breakout-definition tables (the OLD export's published fills). Disclosed: the R1 day's DATE (`entry_date`, a session after E on 89 of
the 109) was read from that table to place the labels — a date, no price, descriptive only; it is not an input to anything in §5. The label comes BEFORE the R1 day on 98 of 109 (89.9%), within
[−2, +1] of it on 12 (11.0%), after it on 8 (7.3%); median delta to the R1 day +14 sessions. The R1 day's offset from our E on those
109: on E itself 20, 1–5 sessions later 38, 6–20 later 29, more than 20 later 22. **The two anchors agree on what he is NOT doing:
waiting for the base-high close.**

### 2d. The base's state on the screen date (a watch row = the stock passed our C0 structural gates that night)

| era · grade | n | watch row AT s0 | … with a trendline (C0_tl = 1) | same base NOT yet broken at s0 | a watch row anywhere in the window |
|---|---|---|---|---|---|
| A · bought | n = 624 | 176 (28.2%) | 153 | 39 (6.2%) | 448 (71.8%) |
| A · not_yet | n = 128 | 50 (39.1%) | 50 | 13 (10.2%) | 97 (75.8%) |
| A · best | n = 60 | 17 (28.3%) | 15 | 4 (6.7%) | 38 (63.3%) |
| B · bought | n = 28 | 8 (28.6%) | 8 | 5 (17.9%) | 14 (50.0%) |

A base in our table ends when a close exceeds the pole high, so a stock that broke out on s0 often has no watch row that night —
"watch row at s0" is low for bought by construction. The "not yet" labels sit in an unbroken base more often than bought (10.2% vs
6.2%), the direction the readiness contrast (§5) expects.

### 2e. R1 / R2 membership of the matched events (descriptive; forward flags by construction — never a filter input)

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
small to say more.

### 2f. Distinct events, and the same-day population (the denominator of "which breakout to pick")

- **Era A: 388 distinct (stock, E) events** carry a label (bought 297, not_yet 80, best 30; 12 events carry both a bought and a
  not-yet label), over 288 distinct bases (spec key), 199 drift-robust chains and 147 stocks; 308 events carry one label, 54 two, 26
  three or more. Bought events by year: 2017 7 · 2019 8 · 2020 205 · 2021 77, on 180 distinct days in 88 ISO weeks. 11 of the 297
  bought events are C1 (3.7%) against 1.1% of the tl stream (81,015 rows).
- **Era B: 12 events** (bought 10 — 2022 1, 2023 9 — best 2, not_yet 0) over 11 bases and 10 stocks.
- **Same day:** a bought event in era A shares its E with a median 146 OTHER tl line-crossings (mean 162.7) and 29 other FIRST breaks
  (mean 40.9); its ISO week holds a median 651 line-crossings and 147 first breaks. The era-wide stream: a median 205 tl rows a week
  (n = 254 weeks) and 53 first breaks; era B 243 and 73 (n = 145 weeks). The published fills were 53 / 63 a week. His 5–7 a week is
  therefore about one in nine first breaks, one in 35 line-crossings.

### 2g. Positive controls — three labels checked by hand on the frame (picked by rule, printed by the script)

| frame | stock · screen date · grade | matched E (delta) | our base | hand read of the frame |
|---|---|---|---|---|
| `g_0466` | SQM · 2017-10-05 · bought | 2017-10-05 (0), a FIRST break; R1 | pole 09-20, D 10-04 | **CONFIRMED.** TC2000 daily: a run to 63.8 in mid-September, a 2-week pullback base with his drawn line at 56.07 and a down-sloping line from the pole, the 5-minute pane on 10-04/05 pushing through 59–60. The bars: 10-03 close 57.50 crossed his 56.07 line, 10-04 closed 59.44, 10-05 high 61.00 (our E). He bought at the break, one to two sessions before our tl event — the AMRX pattern. |
| `b1_00` | ROKU · 2021-06-16 · not_yet | 2021-06-18 (+2), a retrigger; not in the old fills | pole 04-14, D 06-17 | **CONFIRMED as a label; the daily tab is present but the WEEKLY pane is active (the OCR daily-tab test passed on the tab bar, not the active chart).** The weekly shows a 4-month 300–480 range; the hourly pane shows 06-14..06-16. "Not ready" fits a wide, long base; our line fired two sessions later on a retrigger of a 45-session base (the maximum our rule allows) — the readiness contrast in one frame. |
| `g_0957` | MDGL · 2023-01-26 · bought | 2023-01-24 (−2), a retrigger; not in the fills | pole 2022-12-22, D 01-23 | **CONFIRMED.** TC2000 daily: the December gap from ~65 to ~250–300 on the NASH results, then a 4–5 week flag at 290–310 with his drawn lines. Bars 01-20..01-24 pushed the flag's upper edge (highs 306.9, 313.6, 313.9); our tl event 01-24 is two sessions before the stream moment. ⚠ Disclosed: the hand check printed MDGL's bars through the SCREEN date 01-26, i.e. two bars (01-25, 01-26) after this candidate's E = 01-24; they were not used for anything and no number here rests on them, but the rule says no bar after E, so it is said. SQM's and ROKU's bar prints stop at their E. |

## 3. The target — decided by the rule written before the run

- **Rule (script header):** on the 392 joined bought labels of era A, ≥ 60% with delta ≥ +1 → a PRE-BREAKOUT STATE (decision time =
  the watch night D); ≥ 60% within [−2, +1] → the BREAKOUT DAY (decision time = E); otherwise both are reported and the registration
  takes **the breakout-day target with the state read at D**. Result: 41.6% / 45.7% → **the third branch.**
- **So the registered target is the breakout EVENT (stock, E) — a tl line-crossing, first break or retrigger — labelled 1 when a
  "bought" or "best" label marks it (the nearest-event join above), with every input read from bars dated ≤ D = E − 1 (the watch
  night).** The flag applies the moment the line breaks on E, before any fill. The R2 expansion shape is NOT an input (it needs
  E's close); it is a descriptive split beside.
- **"not_yet" is the not-ready side of the same state label**, not an outcome arm: it enters only the readiness contrast in §5
  (does the score separate bought from not-yet on the same bases?). **"best" (n = 30 events in era A) is reported beside bought,
  never its own arm;** it is merged into the positive class for the fit. **An event carrying both a bought and a not-yet label (12
  in era A) is POSITIVE in the fit (he bought it) and is EXCLUDED from the not-yet set of the readiness contrast** (a not-ready call
  he then acted on inside the window is a resolved one, not a negative).
- Why not his R1 day as the target: 89.9% of his bought labels precede it. A filter that waits for the base-high close would be
  rating a day he is already in.

## 4. The comparison population — the OTHER breakouts of the same day

The negatives for the fit, and the control of the sanity read, are **the other tl line-crossings on the same E date, same era, same
universe rules** (median 146 a day in era A), NOT matched ordinary stocks. Why: his question is *which breakout to pick* — the
decision is made among the day's breakouts, so the contrast that answers it is labelled-vs-unlabelled within the day. Within-day
comparison also removes the market day (phase, breadth) from every feature. Stated plainly: **"ungraded" means not shown on stream,
not rejected** — some ungraded breakouts are ones he would have bought; this makes the fit's separation an UNDER-estimate, never an
over-estimate.

## 5. The registered FILTER (to be fitted after the freeze; outcome-free throughout)

- **Unit and stream.** Every tl candidate row (stock, E) of the era — the high cleared the trendline level on E — first breaks and
  retriggers alike (both fill in the published population). Era A: 81,015 rows (20,650 first breaks); era B discovery: 41,200
  (12,250). The filter cuts THIS stream; the fill, stop and exit are Track B's business.
- **Decision time.** D's close (the watch night) for the state; the flag is attached when the candidate exists on E. **No bar, no
  minute of E enters the score** (not the gap, not the volume so far).
- **Feature candidates (12; each from the pinned watch / candidates tables or the daily export with bars ≤ D; definitions are the
  A+ registration's where it has them, cited; direction FIXED FROM HIS WORDS, never fitted):**

| # | family (his word) | feature · definition | better = | source of the direction (the SSoT's tags: **S** his words · **B** this registration's choice, not his word · **R** a reused constant) |
|---|---|---|---|---|
| 1 | tightness / contraction, daily | `tightening_ratio` (watch: mean (h−l)/c over D−4..D ÷ over P+1..P+5) | lower | S (*"tightening range"*; his 10-22 contraction ruling) |
| 2 | contraction, weekly scale | `wk_ratio` (A+ registration, concept 1: 5-session blocks from D back, last m ÷ first m, k ≥ 3; missing under 15 sessions) | lower | S (his 10-22 *"fractal"* ruling; the block reading is B) |
| 3 | contraction, pullbacks | `pb_ratio` (A+ registration, concept 1: last completed pullback ÷ the first; missing with < 2 pullbacks) | lower | S (same ruling, pullbacks as the third scale — ruled yes 10-22) |
| 4 | base depth ("long but wide and loose … not good") | `base_depth` = 1 − base_low ÷ pole_high (the module's `explain_watch`) | lower | S (*"wide and loose, that's not good"*) |
| 5 | retrace | `retrace` = (pole_high − base_low) ÷ (pole_high − pole_low), the share of the pole's range given back (module) | lower | R (the C1 term, `anticipation.COIL_HOLD_LIMIT`); the direction is B |
| 6 | prior run (the pole) | `prior_move` (pole high ÷ pole low − 1) | higher | S names the 30–100%+ range; "bigger is better" is B (the A+ read's orientation) |
| 7 | pole quality | `pole_day_vol_ratio` (the pole's volume vs its 20-day average, module telemetry) | higher | B — not his word |
| 8 | RS leadership | `rs_best` (best of the 1/3/6-month return percentiles on D) | higher | S (*"the 1 or 2% of stocks that are up the most"*) |
| 9 | group strength | `grp_pct` (the SIC group's 63-session return percentile on D; missing for small groups) | higher | S (his 10-21 *"group themes"*; the percentile is B) |
| 10 | volume dry-up | `vol_dry5` (A+ registration, concept 2: mean volume D−4..D ÷ D−9..D−5) | lower | S (his captured Deepvue note, 10-18) |
| 11 | distance to the level ("tight days anticipating breakout") | `dist_level_adr` = (pivot_tl(D) − close(D)) ÷ (close(D) × ADR20(D)) (watch row) | lower | S names anticipation of the break (AMRX, 10-22); the ADR reading is B |
| 12 | the watch night's own bar | `trigger_bar_range_adr` (the D bar's range ÷ ADR20, module; an inside day scores lowest) | lower | B — not his word (his AMRX chart marks *"second inside day"*, a hint, not a rule) |

  `base_len` is NOT a candidate (his 10-22 ruling: length is not rewarded on its own); it is a split beside. `atr14_slope` is not a
  candidate (its denominator is the pole's volatility, A+ registration). Market phase is a split, never an input (ruled 10-22).

- **The fit — the only fitted object is the SUBSET (≤ 5 of the 12).**
  1. **FIT set:** the labelled events (bought ∪ best) with E in 2017-03-02..2020-12-31 (≈ 220 bought events + best) against every
     other tl row of the same days. **CHECK sets:** (i) the 2021 labelled events (77 bought + best; the hold-out with power), (ii) the
     2022–23 labelled events on `cb702` (10 bought + 2 best; the check the task named — direction only at that n, said so).
  2. **Screen statistic:** within-day AUC = the mean over labelled events of the feature's percentile among that day's tl rows
     (ties half, the event itself excluded from its own denominator), in the fixed direction; 0.5 = no separation. A feature with a
     missing value on an event is skipped for that event (the coverage printed).
  3. **Subset rule:** the features with fit-set AUC ≥ 0.58, taken in descending AUC, at most 5; a feature whose fit-set AUC points
     AGAINST his word (< 0.50 in the fixed direction) is excluded and REPORTED as a disagreement, never flipped.
  4. **Score:** equal weights — the mean of the chosen features' percentiles against the trailing pool (the A+ registration's pool:
     every tl row with E′ in [E − 20, E − 1] on the SPY calendar; |S| ≥ 30 non-missing per feature, else that feature is missing;
     a missing feature counts 0.5, as the A+ read counts a missing scale). **No weight is fitted.**
  5. **The cap — TAKE:** the pool's reference scores (each member against the pool minus itself, the A+ member rule); the cutoff =
     the 24th-highest reference score (N = 6 a week × 4 weeks); TAKE = score ≥ cutoff AND fewer than 6 TAKE already in the ISO week
     (Mon–Sun by E) in (E, ticker A→Z) order; at-or-above after the week's six = CAPPED; fewer than 24 rated members = UNRATED.
     N = 6 is his "5–7"; N = 4 and N = 8 are reported beside, never deciding.
  6. **Plateau (decision 0023's convention: a pick whose neighbours collapse is an artefact):** the subset is re-derived at screen
     thresholds 0.56 and 0.60 and with each chosen feature left out in turn; the filter is frozen only if the check-set recall at
     N = 6 under every neighbour lies within 25% (relative) of the registered subset's. A spike is reported as CAN'T TELL.
- **What the fit measures (printed, outcome-free):** the 12 AUCs on fit and check sets with n; the chosen subset; TAKE per week
  (expected ≤ 6, median printed); **recall = the share of labelled events flagged TAKE** on the fit set, the 2021 hold-out and the
  2022–23 check; the same for the not-yet events (the readiness contrast — expected LOWER than bought's); the share of TAKE events
  that are C1, R2 (descriptive, forward flag), first breaks vs retriggers; the by-year and by-phase splits.
- **The fit's own bar (outcome-free; decided on the 2021 hold-out, n = 77 bought events + best):** the no-information rate = TAKE
  share of the 2021 stream (about 6 of 205 a week ≈ 3%). **PASS** = labelled recall ≥ 3× the no-information rate (≈ 9%) with the
  plateau holding and the 2022–23 recall ≥ its own no-information rate; **FAIL** = recall ≤ 1.5× (≈ 4.5%); **CAN'T TELL** otherwise.
  A PASS freezes the filter (its code, subset and pins written under the marker); otherwise his R2 definition is the combined
  test's filter (§7).
- **What the fit may NOT do:** fit weights; fit directions; add a feature outside the 12; read any outcome column, any bar after D for
  a feature, any minute; change the window, the pool, N, the cutoff rank, the thresholds or the 25% after seeing a result; run on
  2025–26.

## 6. The SANITY READ — do the labelled breakouts carry edge? (registered, NOT run; runs after the fit is frozen)

- **Populations (per era).** GRADED = the distinct tl events marked by a bought or best label (era A: the 297 bought-marked events
  plus the best-marked events not among them, ≤ 30; era B: 10 + 2). UNGRADED = every other tl row on the same E dates (era A: 180
  dates, about 26,000 rows; the exact n printed). NOT-YET = the 80 / 0 not-yet events, beside. The matching is the same-day population
  itself (§4); no ordinary-stock control.
- **Entry, stop, retry (held fixed at Track B's harness, `cb_trail_variants_2026-10-23.md` §D):** entry at E's CLOSE when close(E) >
  pivot_tl(D) (the SSoT's `close` variant), else the event abstains — counted on both sides; stop = entry − 1.0 × ADR20(D) × entry,
  never capped; up to two re-entries at the first close back above the level within 20 sessions (T2; both sides re-enter on the SAME
  tl level, so the 10-22 control-retry caveat is weaker here but is still stated on every T2 row); T0 is the clean comparison; the
  session-3 stall cut, the pessimistic touch-both rule, the 120-session horizon — all as there.
- **Exit cells (two, named now):** `A20_X1_P1` = `pp` (the carried exit: ⅓ at +2R, breakeven, the first close under the 20-day; his
  ruling) and `A20_X3_P0` (20-day · a 2-session reclaim forgiven · no partial — the cell that held the most doublers: 53% / 54% to
  half the move). No other cell.
- **Measures, tail first (per era × cell × T0/T2, n on every row):** ≥ 5R and ≥ 10R per 100 events; the worst trade and the
  5th-percentile trade (per-trade R); mean R per event (chain sum under T2); win rate descriptive; GRADED minus UNGRADED on each,
  with month-block bootstrap intervals (calendar month of E, 2,000 resamples, seed 702, key `track_a_sanity|<era>|<cell>|<retry>`);
  GRADED minus NOT-YET beside; the R2 subset of GRADED beside.
- **Eras and the data gate (STEP 0, `backtest_data_standard.md`):** 2017–21 on `cb702_pre_v2` (the file that clears the file-only
  checks; complete events only, E + 120 sessions ≤ 2022-06-30; the walker `trail_lib` re-pointed at its daily export — no minutes
  are needed for a close entry); 2022–24 on `cb702` with the G8 censor (complete events only, E + 120 ≤ 2024-12-31, the censored count
  printed beside every number) and `symbol_guard_B.tsv` (an event whose [E − 130, E + 120] straddles a listed break is excluded,
  counted). Corporate actions: any trade containing a G5 DISCONTINUOUS event (OPLN, ZWS, BEP …) is flagged and the worst-trade
  figure is quoted with and without it. No bar after 2024-12-31.
- **Bar (era A decides; era B, n = 12, is descriptive):** needs ≥ 100 GRADED entries, else CAN'T TELL. **PASS** = under `pp` at T0
  the GRADED − UNGRADED difference has its interval above zero on ≥ 5R per 100 AND on mean R; **FAIL** = the mean-R difference's
  interval has upper end < 0; **CAN'T TELL** otherwise. `A20_X3_P0` and T2 are reported beside, never deciding.
- **Expectations, written now:** GRADED ≥ 5R per 100 above UNGRADED's (the UNGRADED rate about the R1 population's 1.4–3.9 per 100 by
  cell); the worst GRADED trade a one-session gap of about −7 to −10 R as in every read; the NOT-YET events no better than UNGRADED.
  A miss changes no rule.

## 7. Consequence — fixed now

| fit (§5) | sanity (§6) | what the ONE combined sealed test reads as the PRIMARY filter | beside (descriptive, no bar) |
|---|---|---|---|
| PASS | PASS | **the frozen label filter** (TAKE flag) × Track B's exit | his R2 definition; the full stream |
| PASS | CAN'T TELL | the frozen label filter | R2; the sanity verdict quoted next to the result |
| PASS | FAIL | **his R2 definition** (the base high cleared on an expansion day) | the label filter, recorded not deciding |
| CAN'T TELL / FAIL | any | **his R2 definition** | the label fit's table, reported to him |

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
  ADR% and an axis price; 96% recall, 1.8% false match on wrong tickers).
- **Events:** era A `cb702_pre_v2/out/candidates_tl_com.tsv` (K = tl, split `pre`, E 2017-03-02..2022-01-03; 81,015 tl rows,
  20,650 first breaks); era B `cb702/out/candidates.tsv` + `candidates_com.tsv` (split `discovery`, every row with D or E after
  2024-12-31 dropped at read and asserted; tl 41,200 rows, 12,250 first breaks, E 2022-04-01..2024-12-31). Watch rows:
  `watch_tl_com.tsv.gz` / `watch.tsv.gz` (era B cut the same way: 109,961 holdout rows dropped). R1 / R2 flags: `bdef_r1_*` and
  `bdef_fills_*` of `cb702_pre/out` (the OLD export) and `cb702/out`, columns ticker, D, E, t, entry_date, r2_exp only. Calendars:
  `cb702_pre_v2/sessions.txt` (1,635 sessions) and the SPY dates of the cb702 export kept ≤ 2024-12-31 (821). Columns loaded from the
  candidates: ticker, D, E, K, pole_date, pole_ci, retrigger, retrigger_chain, base_id, split, C1 — no E-day bar column.
- **Windows:** the join window [s0 − 10, s0 + 20] sessions; the placebo over every session of the same symbols with a watch row in
  the same window shape and no label within ±20 sessions (42,781 sessions with an event).
- **Outputs:** `apollo_data/cb702/qm_streams/track_a_1023/labels_joined.tsv` (one row per label) and `matched_events.tsv` (one row
  per distinct (era, stock, E)); the printed summary `scripts/probes/_705_track_a_1023/01_join_labels.txt` with the sha256 pins of
  every input. No DB, no network, no subagent, no commit; nothing pinned was written or moved; the runner was not imported.

## 10. What this does not answer — known limits

- **Whether the labelled breakouts PAY under any entry / stop / exit.** Unread by design; §6 is registered, not run. Entries and
  exits stay undetermined for a new setup.
- **The negative class is noisy by construction:** "not shown on stream" is not "rejected". The fit's separation is a floor.
- **The labels are 2017–2023 stream moments, 91% from 2020–21** — one regime (the 2020 rebound and 2021). The 2022–23 check holds
  12 events; it checks direction, not a rate. The fit's hold-out is 2021, inside the same era.
- **Caption = screen = confirmed only:** 1,618 of 2,472 graded moments are unattributed (the stock on screen was not the one named,
  the chart was unreadable, or our bars could not confirm it — 227 frames on 114 names outside our bars, GBTC the most frequent). The
  1.8% false-match rate means about 15 of the 854 labels may be on the wrong stock.
- **Survivorship is fixed only for era A's event file (v2); era A's R1 / R2 flags are from the OLD export's published fills**, so 202
  of the 297 bought events have no R1 / R2 reading. The sanity read will walk v2 directly and does not need them.
- **Stream selection:** he shows what he likes; a base he never showed is not a base he rejected.
- **Detection misses are named, not fixed:** 87 labels on names outside our universe (ETFs, ETNs, leveraged funds) and 140 on bases
  our structural gates did not hold in the window. A filter cannot rate what the detector never watched; that is the "not missing
  the good ones" line of Track A (the 50-day and 30%-run-up gates), a separate read.
- **The retrigger ambiguity:** 190 of 392 matched bought labels sit on a retrigger; a label marks a base, and the first break of that
  base may be the event he meant. The fit labels the nearest event; the base-level reading (every event of a labelled base positive)
  is reported beside, never deciding.
- **The window and the placebo are session-based on daily data;** a stream moment is a time of day, and a chart shown at 11:34 on the
  breakout day (SQM) is "on the day" whether he bought that morning or the day before.
- **Nothing about 2025–26.** Unread; the interface in §8 is the only thing the combined test consumes from here.

<!-- FREEZE -->
## Freeze record

Pins (sha256) printed by `01_join_labels.py` on 2026-10-23 (the join's inputs and outputs; the fit module `02_fit_filter.py` and the
sanity module do not exist yet — their pins are added here in the freeze commit that precedes each run, and the doc body above the
marker is pinned in that commit):

- labels: `f4116fd99a1b7db88a74b88a7278aa6e434cf8788b7003af8bbc39e72ac2269a`
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
- join script `01_join_labels.py`: `4ff17ee08e2e67de6035272170c6ad18c8a4702c2932a48e107c7f2dd6fceaec`
- out labels_joined.tsv: `13df295286e6ba0369a0fd7fb53102dffe58500fd84e49196fdb78d34895d9a3`
- out matched_events.tsv: `4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc`
- doc body sha256: (taken in the freeze commit)
