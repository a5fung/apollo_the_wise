# #519 free step — his chart reasons measured from daily bars, $0, scored against his 35 rulings

**MEASUREMENT ONLY. Nothing was changed, proposed or tuned.** Read-only against prod, no rule, threshold
or trade behaviour touched. Operator ruling 2026-09-23: build the free step first, hold the ~$190 paid
vision run until it is scored. This is that score.

**The one sentence: the only read that separates his condemned charts from his approved ones without
rejecting real EPs is the one we already had — how far the stock has ALREADY run before the gap — and
every other measurable reason in his words or the books either rejects real EPs by the handful (base
length, the 50-day, clearing local highs, volume dry-up, up-versus-down volume) or does not separate at
all (the supply ladder, the gap's size), while the 200-day cannot even be evaluated on 25 of the 30 real
EPs; the 12 condemned charts the run-up rule does not catch are not told apart from his 9 approved
charts by any daily-bar measure that does not also reject real EPs.**

Probe: `scripts/probes/_519_free_read.py`. Bars and per-row output: `scratchpad/519/bars.sql`,
`bars.psv` (one prod pull, 17,184 rows), `reads.psv` (68 rows × 66 fields), `run3.out` (the full print).

## Method and population

**Rules were declared before any number was seen.** They are written in the probe's docstring, each
traced to his words or to the two book sets he shared on 09-23
(`docs/methodology/traderlion_2020_leaders_2026-09-23.md`, `boik_monster_stock_lessons_2026-09-23.md`).
No cutline was searched, no window was re-picked after looking, no union of rules is scored. One measure
(`pivot_age_120`, sessions since the left-side high) was added after the first run because the declared
one (`left_high_age`) came back with a median of 1 in every population — it measured nothing. That
addition is disclosed; no rule uses it.

**Bars.** Prod `mi_daily_closes`, pulled once (SSH → psql → file) for the 63 tickers named by the two
fixtures, derived from the fixtures rather than listed by hand. **History starts 2025-08-18**, so every
row has between 56 and 253 prior sessions and nothing here sees more than ~13 months. Every measure reads
prior bars plus the alert-day open, the same no-lookahead basis as `structure_read_v2/v3`, whose fields
(overhead volume share, zones cleared/remaining, run-up family, live-extension replica) are reused, not
re-implemented.

**Populations, all derived from the fixtures** (`must_not_trade_charts.py`, `must_not_miss_eps.py`):

| population | n | what it is |
|---|---|---|
| real EPs — the RULE 0 bar | **30** | `MUST_NOT_MISS` minus its 3 `excluded=True` members. ⚠ 13 of the 30 share ONE date, 2026-04-08 (a market-bottom day), and all 30 are Mar–Aug alerts with 142–252 sessions of history |
| his approved dates | **9** | GOOD_CHART 4 (RNG, AVAH 08-13, TBBB, HAE) · OKISH_CHART 4 (OMER 07-27, WYFI, NIQ, MRVI) · OKISH_EARLIER 1 (CAR 04-01) |
| dates he condemned | **21** | every BAD_CHART ruling, sessions 1–3 |
| of which the run-up rule does NOT catch | **12** | NVTS, MRLN, AVGU, CRWG, ABVX, IPCX, YOU, QTTB, RARE, BW, LPTH, FRMI — the population a paid read would have to separate |
| other rejected dates | 4 | WRONG_DAY own dates (CGEM 06-08, AVAH 06-02, MXL 04-21) + WRONG_STAGE (ARQQ). Shown separately; never folded into "condemned" |
| data defect | 1 | VEEE 07-08 — a measurement defect, not a chart opinion |
| pointed-at | 3 | flags, not labels |

**Data integrity, checked before anything was read:**

- **Gap basis.** The fixtures' `gap_open_pct` for review samples #1/#2 is the scan-log's alert-tick read
  (`_594_review_sample.py` reads mi_ep_scan_log `gap_pct`), not the daily open; 15 rows differ by 1–16pp
  (RNG: 4.9% at the daily open vs 20.7% in the fixture). A basis difference, not a population error —
  tickers and dates line up bar for bar, and the daily open is the basis every prior scoring used.
  Two WRONG_DAY dates show no gap in daily bars at all (CGEM 06-08 opened +1.6%, AVAH 06-02 +7.3%),
  which agrees with his "garbage / wrong day" verdicts.
- **`mi_daily_closes` is unadjusted and carries scale defects.** Detected by rule (docstring): the first
  ten rows of CRWG, VEEE and TDIC carry open/high/low on one scale and close on another; GDC jumps
  4.41 → 1105 on 248 shares (2025-10-22); **QH's whole series after 2025-11-10 is unusable** — prices in
  the tens of thousands on volumes under 1,000 shares. Any window that reaches back past the last artifact
  is n/a for that row — never a pass, never a fail. Rows affected before their alert: CRWG (186 of 197
  sessions usable), GDC (133 of 180), **QH (13 of 172)**, VEEE (211 of 222).
  ⚠ **This changes one prior number: the 09-21/09-23 scorings counted QH 06-18 as caught by ANCHOR-75
  on a 20-session run-up of 15,791% — that number crosses the artifact. On the 13 usable sessions QH is
  still up ~250% from its 10-session low, so the substance holds, but the rule is n/a for QH here and
  the comparator reads 8 of 20 evaluable, not 9 of 21.** GDC 05-06 sits on the same kind of data (a
  $1,100 print on 248 shares seven months earlier; its five-day return of −98% is SUSPECT, not shown to
  be an artifact — a thin post-reverse-split name can trade like that). ⚠ How he viewed these two on
  08-25 is not recorded: the fixture says session 1 was shown as the `_srbt_review_sample.psv` table,
  so he may well have ruled on his own platform's adjusted charts. What is established is only that
  the bars WE hold for QH and GDC are defective.

## The result

### The pre-declared rules — RULE 0 first

"Real EPs rejected" is the expensive direction and is reported first. A rule that loses one real EP is
worse than one that admits every bad chart. "Cannot evaluate" is its own column.

| rule (his words / the books) | real EPs rejected, of 30 | of which the 04-08 cluster | approved lost, of 9 | condemned caught, of 21 | of the 12 the run-up rule misses | cannot evaluate |
|---|---|---|---|---|---|---|
| R1 base shorter than 5 weeks (25 sessions, 35% band) — the books' minimum | **16** | 8 | 2 (CAR 04-01, WYFI) | 14 | 6 | condemned 1 (QH) |
| R2 gap opens at or below the 50-day — "still below 50d" | **8** | 5 | 1 (WYFI) | 4 | 4 | condemned 1 |
| R3 gap opens below the 60-session high — "didn't clear local highs" | **22** | 12 | **5** (OMER, RNG, CAR, WYFI, MRVI) | 9 | 8 | condemned 2 |
| R4 down-day volume ≥ up-day volume, 20 sessions — the books | **10** | 6 | 4 (OMER, WYFI, AVAH, MRVI) | 5 | 5 | condemned 1 |
| R5 prior close at or below the 200-day — nearest "downtrend" read | 1 (PLTR) | 0 | 2 (OMER, NIQ) | 4 | 4 | **real EPs 25 of 30**, approved 1, condemned 11 |
| R6 last-10-session volume ≥ 50-session average — no dry-up | **11** | 1 | 4 (RNG, CAR, NIQ, HAE) | 11 | 5 | condemned 1 |
| R7 run-up from the 20-session low ≥ 75% — ANCHOR-75, the comparator | **0** | 0 | **0** | 8 | 0 (by construction) | condemned 1 (QH, artifact) |

What this says in plain words:

- **Every rule taken from the books or from his stated reasons rejects real EPs — between 8 and 22 of
  the 30 — and loses between 1 and 5 of his 9 approved charts.** None of them can be used as a filter.
- **"Didn't clear local highs" is the worst of them against the ground truth**: 22 of 30 real EPs opened
  below their 60-session high, and so did 5 of his 9 approved charts (RNG opened 19% below it, OMER 27%,
  WYFI 41%). Real EPs gap from inside corrections — the 04-08 cluster alone is 12 of the 22 — and his
  "cleared the left side" is a judgement about WHICH highs, not a trailing-window test.
- **The books' 5-week base floor rejects 16 of 30 real EPs** (TEAM had a 10-session base, MRNA 28, INTC
  14) and 2 of his approved. His own reference EP, MRNA, measures 28 sessions here against the 74 he
  annotates; the definition is disclosed, not tuned, and the gap says the base he sees is not a trailing
  35% band.
- **The 200-day cannot be evaluated on 25 of 30 real EPs** — they are March–May alerts with 142–180
  sessions of history. A "multi-year downtrend" read is not available on the RULE 0 bar at all.
- **The run-up rule is still the only one that is clean in both directions**: 0 real EPs lost, 0 approved
  lost, 8 of the 20 evaluable condemned charts caught. Unchanged from 09-23 except for the QH artifact.

### Distributions — median (min to max), n

Where each population actually sits, per measure. No cutline is implied by any row.

| measure | condemned, all 21 | condemned the run-up rule misses (12) | approved (9) | real EPs (30) | other rejected (4) |
|---|---|---|---|---|---|
| sessions of history before the alert | 199 (56–253) | 220 (56–253) | 247 (156–252) | 160 (142–252) | 200 (169–207) |
| base length, sessions (closes within 35%) | 8 (1–227) | 20 (1–227) | 40 (6–144) | 20 (8–79) | 43 (2–81) |
| flat-base length, sessions (within 15%) | 2 (1–32) | 6 (1–32) | 19 (4–52) | 8 (3–39) | 5 (1–7) |
| sessions since the 120-session high (left-side high) | 5 (0–114) n=20 | 32 (0–114) | 35 (2–112) | 34 (0–119) | 80 (0–110) |
| of the available 10/20/50/200-day averages, how many the OPEN clears | 3 (0–4) | 3 (0–4) | 4 (3–4) | 3 (1–4) | 2 (1–3) |
| open vs the 50-day, % | 48 (−31 to 348) n=20 | 6 (−31 to 87) | 11 (−8 to 39) | 10 (−18 to 89) | 2 (−6 to 80) |
| prior close vs the 200-day, % (where it exists) | 19 (−39 to 538) n=10 | −1 (−39 to 106) n=7 | 12 (−9 to 37) n=8 | 8 (−18 to 63) **n=5** | −12 n=2 |
| 50-day average's change over 20 sessions, % | 4 (−21 to 93) n=19 | 3 (−21 to 50) n=11 | 4 (−14 to 13) | 3 (−21 to 26) | 2 (0–3) |
| last-10-session volume ÷ 50-session average (under 1 = dry-up) | 1.02 (0.39–4.94) n=20 | 0.92 (0.48–2.27) | 0.89 (0.62–1.66) | 0.87 (0.56–1.98) | 1.14 (1.07–1.72) |
| up-day volume ÷ down-day volume, 20 sessions (over 1 = accumulation) | 1.32 (0.41–46.7) n=20 | 1.04 (0.41–5.52) | 1.11 (0.24–1.47) | 1.19 (0.39–3.77) | 0.96 (0.74–8.10) |
| open vs the 20-session high, % (positive = clears it) | 2 (−40 to 25) n=20 | −2 (−40 to 22) | 1 (−14 to 13) | 1 (−29 to 77) | −15 (−24 to 1) |
| open vs the 60-session high, % | 0 (−46 to 25) n=19 | −22 (−46 to 22) n=11 | −3 (−41 to 13) | −8 (−51 to 36) | −15 (−24 to 1) |
| open vs the 120-session high, % | 0 (−46 to 25) n=19 | −22 (−46 to 22) n=11 | −8 (−41 to 11) | −10 (−67 to 36) | −23 (−51 to 1) |
| share of the last 120 sessions' volume traded ABOVE the open | 0.00 (0–0.99) n=19 | 0.25 (0–0.99) n=11 | 0.09 (0–0.48) | 0.10 (0–0.96) | 0.56 (0–0.74) |
| congestion zones the open clears (v2) | 0 (0–7) n=18 | 2 (0–7) n=11 | 3 (0–8) | 2 (0–8) | 0 (0–2) |
| congestion zones still overhead (v2) | 0 (0–16) n=18 | 3 (0–16) n=11 | 9 (0–16) | 4 (0–19) | 13 (0–19) |
| prior close vs 60 sessions earlier, % | 69 (−54 to 619) n=19 | 5 (−54 to 215) n=11 | 16 (−33 to 52) | 14 (−53 to 175) | −3 (−8 to 64) |
| prior close vs 120 sessions earlier, % | 70 (−39 to 1006) n=19 | 9 (−39 to 211) n=11 | 22 (−16 to 76) | 12 (−66 to 428) | −10 (−43 to 103) |
| where the prior close sits in the 120-session range (0 low, 1 high) | 0.70 (0.03–1.00) n=19 | 0.43 (0.03–0.96) n=11 | 0.63 (0.36–0.95) | 0.59 (0.03–0.97) | 0.37 (0.12–0.93) |
| run-up from the 10-session low, % | 32 (4–255) | 10 (4–48) | 7 (3–54) | 17 (2–35) | 8 (0–77) |
| run-up from the 20-session low, % | 37 (4–574) n=20 | 11 (4–73) | 14 (3–58) | 20 (2–64) | 10 (1–100) |
| the 10-session run in ADR units | 2.27 (0.32–6.13) | 1.45 (0.32–3.36) | 1.23 (0.80–5.06) | 2.39 (0.29–8.86) | 0.73 (0.05–7.26) |
| the gap itself in ADR units | 1.80 (0.16–5.79) n=20 | 2.26 (0.80–5.79) | 2.14 (0.18–4.12) | 1.82 (0.99–14.7) | 0.75 (0.24–1.49) |
| 15-session close span in ADR units (v2 tightness) | 4.05 (1.52–14.3) n=20 | 3.33 (1.52–9.54) | 2.74 (1.80–7.11) | 3.67 (1.23–10.3) | 3.37 (2.94–13.2) |

(n is 21 / 12 / 9 / 30 / 4 unless shown; a smaller n is rows where the window crossed a data artifact or
the history was too short.)

Reading it: on every measure the real EPs sit with, or between, the two ruled groups. The condemned set
as a whole is separated from the approved set by run-up (37% vs 14% median from the 20-session low, 69%
vs 16% over 60 sessions) and by base length (8 vs 40 sessions) — but the real EPs sit at 20% run-up and
a 20-session base, i.e. closer to the condemned side on base length. The 12 condemned charts the run-up
rule misses sit ON TOP of the approved set on nearly everything: run-up 11% vs 14%, open vs 50-day 6% vs
11%, averages cleared 3 vs 4, volume ratio 0.92 vs 0.89. The one visible gap — open vs the 60-session
high, −22% vs −3% — is the measure that rejects 22 of 30 real EPs.

### Separation, threshold-free

For each measure, the chance that a randomly drawn condemned date sits on the bad side of a randomly
drawn approved date (0.5 = no separation, 1.0 = perfect). The bad side is declared from his words / the
books. The last column is a control: real EPs against approved should read near 0.5 if the measure
separates good from bad rather than "his approved set" from everything else.

⚠ Noise floor: at 21 vs 9 the standard error of a null is about 0.12, so anything between 0.30 and 0.70
is indistinguishable from chance; at 12 vs 9 it is about 0.13.

| measure | bad side | condemned vs approved | the 12 the run-up rule misses vs approved | condemned vs real EPs | real EPs vs approved (control) |
|---|---|---|---|---|---|
| flat-base length (15% band) | shorter | **0.90** | **0.82** | 0.80 | **0.78** ⚠ |
| base length (35% band) | shorter | **0.82** | 0.70 | 0.75 | 0.65 |
| run-up from the 10-session low | higher | **0.76** | 0.58 | 0.71 | 0.63 |
| 15-session close span in ADR (tightness) | wider | **0.76** | 0.63 | 0.58 | **0.74** ⚠ |
| sessions since the 120-session high | fewer | **0.72** | 0.55 | 0.69 | 0.48 |
| averages the open clears | fewer | 0.70 | 0.71 | 0.39 | **0.82** ⚠ |
| run-up from the 20-session low | higher | 0.69 | 0.49 | 0.65 | 0.59 |
| zones the open clears | fewer | 0.69 | 0.58 | 0.61 | 0.61 |
| last-10 ÷ 50-session volume | higher | 0.66 | 0.58 | 0.65 | 0.53 |
| the 10-session run in ADR units | higher | 0.62 | 0.45 | 0.53 | 0.61 |
| gap in ADR units | smaller | 0.56 | 0.43 | 0.57 | 0.50 |
| open vs the 60-session high | lower | 0.49 | 0.63 | 0.46 | 0.54 |
| open vs the 120-session high | lower | 0.45 | 0.62 | 0.44 | 0.54 |
| overhead volume share, 120 sessions | higher | 0.44 | 0.62 | 0.40 | 0.57 |
| up ÷ down volume | lower | 0.36 | 0.54 | 0.44 | 0.34 |
| prior close vs 120 sessions earlier | lower | 0.35 | 0.60 | 0.31 | 0.59 |
| zones still overhead | more | 0.31 | 0.41 | 0.33 | 0.46 |

What it says:

- **Four measures clear 0.70 on condemned vs approved, and three of them fail the control.** Flat-base
  length (0.90), tightness (0.76) and averages-cleared (0.70) read 0.74–0.82 on real EPs vs approved too
  — they tell his nine August approved charts apart from EVERYTHING, real EPs included. ⚠ The control
  has two readings: the real EPs are March–May alerts (13 on the 04-08 market bottom) and his approved
  charts are August ones, so part of that 0.78 may be era rather than chart. The load-bearing evidence
  is the RULE 0 table, which reaches the same place without the control: the base rule rejects 16 real
  EPs outright.
- **The two that pass the control are the run-up family** — sessions since the left-side high (0.72 vs a
  0.48 control) and run-up from the 10-session low (0.76 vs 0.63). Both are "how far has it already run",
  the concept ANCHOR-75 already encodes, and both collapse to chance (0.55, 0.58) on the 12 condemned
  charts the run-up rule misses.
- **On those 12, nothing separates.** Every value in that column is inside the 0.30–0.70 noise band except
  flat-base length (0.82) and averages-cleared (0.71), both of which fail the control. The supply-ladder
  fields — overhead volume share, zones remaining, open vs prior highs — read 0.41–0.63, and several run
  the WRONG way on the full set (zones still overhead 0.31: his approved charts have MORE overhead than
  his condemned ones, because the condemned ones already ran through it).

### His reasons, tagged to what can be measured

Read off the words in the fixture, one tag per concept per ruling. 10 of 35 rulings carry no per-name
words (the six session-1 charts he called "horrendous" as a list, plus TBBB and HAE "good"); their only
recorded reason is the run-up note the sample was shown with.

| concept | what he said | rulings using it | measurable from our bars today? |
|---|---|---|---|
| clears the left side | "didn't clear the left side / local highs / any of these areas", "cleared highs", "bumping into recent highs", "cleared low of basing area into previous highs" | 11 (5 bad, 2 good, 4 ok) | **yes, within 13 months** — open vs the 20/60/120-session high, zones cleared/remaining, overhead volume share. ⚠ Measured this way it separates nothing (0.45–0.63) and rejects 22 of 30 real EPs as a rule |
| multi-year structure | "a long base since 2022", "a double top from Oct 2025", "stuck in multi year downtrend" | 3 (2 bad, 1 good) | **NO** — bars start 2025-08-18. RNG's base, NVTX's double top and RARE's downtrend are all outside the data |
| prior trend | "in downtrend", "multi year downtrend" | 2 (2 bad) | partly — 60/120-session change and the 50-day slope; the 200-day exists for 5 of 30 real EPs only |
| moving-average position | "still below 50d", "didn't clear … nor 50d", "did clear all key moving averages 10/20/50 and 200", "moved above all moving averages on gap day" | 4 (1 bad, 1 good, 2 ok) | yes — open/close vs 10/20/50 (200 where available). He said himself "moving avg is not black or white"; as a rule the 50-day rejects 8 real EPs |
| a base / its length / its stage | "long base", "still in base", "bottoming base", "3 tight days prior" | 6 (2 good, 2 ok, 1 wrong-day, 1 wrong-stage) | yes, within 13 months — but the books' 5-week floor rejects 16 real EPs and MRNA reads 28 sessions against his 74 |
| gap strength | "gap up weak", "don't see a gap up, just chopping in range", "gap up ok but not super strong" | 4 (2 bad, 1 ok, 1 defect) | yes — gap % and gap in ADR units. LPTH's "no gap" opened +10.0% / 2.3 ADR; BW's "weak" gap opened +33.6% — what he calls weak is not the open print |
| a recent gap down | "recent gap down and gap up didn't clear any of these areas" | 1 (bad) | yes — v2 gap zones |
| close within the day's range | "closed on bottom of range on EP day", "closed near high of day" | 2 (1 bad, 1 good) | computable but **not at admission** — it reads the alert-day close |
| what happened after | "still ok until 3rd day", "which held", "still holding up", "failed to make new highs" | 4 (2 bad, 1 good, 1 ok) | computable but **not at admission** — it reads later sessions |
| already run up | the session-1 list: "already up 77 / 92 / 242 / 137 / 224 / 135%" | 9 (8 bad, 1 okish-earlier) | **yes** — the run-up family, and the one concept that scores clean |

## What this does not answer

- **Whether any of this predicts outcomes.** It measures agreement with his labels. The 2026-08-25
  backtest found the supply read a null winner predictor and nothing here changes that.
- **Whether the 12 uncaught condemned charts are separable at all from daily bars.** At 12 vs 9 nothing
  outside 0.30–0.70 is readable, and the two measures that got there fail the control. "No separation
  found" here is "none with these declared measures at this n", not "none exists".
- **His multi-year reasons.** Three rulings — RNG's 2022 base (his only outright-good chart from sample
  #1), NVTX's Oct-2025 double top, RARE's multi-year downtrend — rest on structure our bars cannot see.
  The 09-06 notes record a 5-year backfill as approved and run; prod `mi_daily_closes` starts 2025-08-18
  today (it read 2025-08-04 on 09-06 — the window rolls forward), and no other daily table exists. Until
  that lands, no read of ours can score those three reasons, and any vision read fed the same bars cannot
  either.
- **Two condemned charts stand on defective bars.** QH 06-18 (prices in the tens of thousands on volumes
  under 100) and GDC 05-06 (a 250x scale jump on 248 shares) — his verdicts were given on charts rendered
  from these rows. Recorded here, not fixed: the unadjusted-history defect in `mi_daily_closes` is its own
  task, and it also means the fixture's stored `extension_live_pct` and returns for those two are suspect.
- **The live extension cap.** `MAX_EXTENSION_PCT` is 50.0 live (reverted 08-29); `_structure_read_v3.py`'s
  docstring still says 75. The ANCHOR-75 comparator is a separate constant and is unaffected; the
  `blocked_by_live_extension_rule` field imports the live 50. Flagged, not fixed.
- **OMER 08-13.** He stated it as "another good gap up on 8/13 which held" but it is recorded only as a
  `better_date` note and is not in `MUST_NOT_REJECT_DATES`, so it is not in the approved 9. Not added.
- **Concept coverage is thinner than 35.** Only 25 rulings carry per-name words; the tags above are read
  off those. The ten without words contribute nothing to "which reasons are measurable".

## What this means for the paid run

The bar a paid vision run has to beat, stated from the numbers above: **lose none of the 30 real EPs and
none of his 9 approved dates, and catch some of the 12 condemned charts the run-up rule cannot** — because
the free read already catches the other 8 for nothing, and no daily-bar measure we can compute tells
those 12 (NVTS, MRLN, AVGU, CRWG, ABVX, IPCX, YOU, QTTB, RARE, BW, LPTH, FRMI) apart from RNG, AVAH, TBBB,
HAE, OMER, WYFI, NIQ, MRVI and CAR 04-01. A vision read that only re-derives run-up, base length or
"cleared the 60-day high" adds nothing: the first is already in hand and the other two reject real EPs.
One of the twelve (RARE, "stuck in multi year downtrend") rests on a reason no model fed our 13 months
of bars can see, and six of them (AVGU, CRWG, ABVX, IPCX, YOU, QTTB) carry no stated reason at all, so
the honest ceiling for the paid run on this fixture is AT MOST 11 of the 12 — and the first thing it
should be checked against is whether it rejects any of the 22 real EPs that open below their 60-session
high.
