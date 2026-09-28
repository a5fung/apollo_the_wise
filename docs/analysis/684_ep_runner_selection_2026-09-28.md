# #684 — What, known on the gap day, marks the EPs that run big? (2026-09-28)

**MEASUREMENT ONLY. $0 — prod read-only via psql, no LLM calls, no paid data. Nothing changed, nothing
proposed as decided. Any change to the score or admission is CHANGE_PROCESS and the operator's call
(THE LINE).** Probe: `scripts/probes/_684/` (gate.sql → gate.py → features.py → study.py, pre-registered
in `study.py`'s docstring before any outcome-by-feature number was computed; `posthoc.py` is labelled
post-hoc). Every number below carries its n.

## ⚠ VERIFIED AND CORRECTED 2026-09-28 — an independent critic re-derived the population and outcomes from prod with its own SQL and code (0 of 667 outcomes differ by more than 0.01 ADR); these corrections win over everything below

- **The answer stands, reworded:** no gap-day selection rule is DEMONSTRATED at this power — not "nothing marks
  them". The held-out block holds only 4 runners, all rejected, so it cannot confirm or refute a sign. The one pass
  (least-traded third by dollar volume) is at the rate chance produces.
- **"Today's score is flat" is RELABELLED:** `ep_score` in the scan log is the score logged at the time — on 630 of
  670 rows the retired pre-08-22 score with its bar of 50. What this study shows is that THAT score and bar were
  neutral: runners were rejected about as often as admitted (36 of 361 rejected rows = 10.0% vs 35 of 306 alerted =
  11.4%). Today's rule was never applied to the 363 then-rejected rows, so it is UNMEASURED there, not null. On the
  alerted runners, today's rule: admitted 9 of 139, rejected 9 of 79, undecided 6 of 41, no re-score 11 of 47.
- **The 09-27 extension lead does not confirm** and would down-rank all 5 of his labelled EPs in the window (PLTR,
  BFLY, TEAM, HTFL, MRNA sit in the "extended" group). Its held-out read on alerted rows is not fresh (they were read
  on 09-27); only the 43 rejected held-out rows are new.
- **The reversed leads were worded wrong.** Measured as "that third vs the rest": widest 20-day range 11.9% vs 10.7%;
  narrowest day range 10.9% vs 11.2%; furthest above the 5-day low 14.4% vs 9.5% (p 0.064). The 20/40-day range
  measures are the volatility (ADR %) family (rank correlation 0.77); in ADR units the range "reversal" disappears.
  If a next block is registered, register "the quietest third runs LESS" and "the widest gap-day-range third runs
  LESS", with ADR % controlled — not "already moving runs more".
- **Timing tags corrected:** 8 draws taken from the scan tick are "scan tick, 07:00–09:55", not pre-open (the chosen
  tick is 09:45–09:55 on 333 of 670 rows); the catalyst-expectedness features are BACKFILLED (248 of 265 computed after
  the alert day) and may carry hindsight. No verdict changes.
- **One composition line worth his eye:** alerts that first passed at 09:45–09:55, after the opening-range order
  window, ran more often — 14.1% (14 of 99) vs 10.1% (21 of 207) for alerts inside the window, and 10.0% (36 of 361)
  for rejected rows. Descriptive only.
- **Smaller fixes:** 12 rejected names ran ≥ 8 ADR, not 13 (ARM is 7.99), and 69 distinct moves (UMC 05-06/05-14 and
  CRSR 05-08 overlap later gaps); the discovery score cut is 60, not 80; the 3 rows without an ADR lack 20 PRIOR
  sessions (new listings), not forward ones; the day-level features (SPY vs its 50-day) cannot be tested by a
  week-block permutation; the diagnostic numbers (May split, percent-terms read) were reproduced by the critic but
  their code is `critic_recompute.py`, not the study's probe.

## The answer first

- **Nothing we can know on the gap day marks the EPs that run ≥ 5 ADR in the next 15 sessions in a
  way that would serve as a selection rule.** 63 gap-day features were pre-registered and tested on 667
  scored gap-day candidates (May 1 – Sep 3; 71 runners = 10.6 %). **One passes the pre-registered
  four-condition bar — the least-traded third by dollar volume (under ~$32 M a day) ran 15 % (31 of
  201) vs 9 % (36 of 403), p 0.01, held-out same sign, survives dropping the best week and the two
  biggest runs.** Its verdict is PASS and stays PASS. What limits it, all read AFTER the run and
  labelled so: (a) across 63 draws about 3 features clear the discovery bar by chance and — a
  correction to the registration, which said "well under 1" — about 1 to 1.5 clear all four, because
  the two drop tests rarely move a p across 0.05 and the held-out sign is a coin flip under the null;
  exactly 3 cleared discovery (price, dollar volume, ADR % — one "cheap / thin / wild names" family) and
  1 cleared all four; (b) its held-out support is 2 runners of 24 vs 2 of 39; (c) it is absent in May
  (12 of 68 vs 26 of 157) and lives in June–August; (d) in plain-percent terms (peak ≥ 25 %) it shrinks
  to 17 % vs 15 %. **One pass is consistent with chance, and thin dollar volume is a description of
  the names, not a selection rule.**
- **Today's EP score is flat, reproduced:** the top third by score ran 14 % (29 of 205) vs 10 %
  (38 of 399), p 0.14; on the held-out block the top third ran 0 of 25 vs 4 of 38. The alerted era-A
  rows reproduce the 09-27 read to the decimal (24 of 253 = 9.5 % vs 25 of 261 = 9.6 %; every score
  band 6–11 %). **The runners are split evenly between what the scan alerted (35 of 306 = 11.4 %)
  and what it scored and rejected (36 of 361 = 10.0 %) — admission neither finds nor throws away the
  runners; 36 runners are named below.**
- **The extension lead (09-27) does not confirm.** Under its own definition (the rank shadow's
  `ext_xadr_eod` — which is the gap-day **OPEN** vs the moving averages below it, a 09:30 quantity
  despite its name; replicated here to 3 decimals on 246 rows) it reproduces on its own population
  (least-extended third 14 of 82 = 17 % vs 10 of 143 = 7 %, p 0.01) **but** (a) it does nothing on the
  361 names the scan scored and rejected (10 of 97 = 10 % vs 20 of 202 = 10 %), (b) it is reversed in
  May (7 of 54 = 13 % vs 29 of 159 = 18 %) and lives only in June–August, (c) the held-out block reads
  2 of 22 vs 2 of 37 (can't tell), and (d) **all five of his labelled EPs in the population sit in the
  "extended" group** (PLTR 2.5, BFLY 4.4, TEAM 5.3, HTFL 5.3, MRNA 8.3 ADR above their averages at the
  open). A rule built on it would have down-ranked every EP he has named. The pre-registered plain
  version (prev close vs its SMAs, signed) went the other way (9 % vs 12 %). **Verdict: can't tell,
  and it conflicts with his labels.**
- **Seven features were significant the WRONG way** (against the direction declared before the run):
  names that were **already moving before the gap** (widest third by 20-day range 13 % vs 6 %,
  reverse p 0.001; furthest above their 5-day low 13 % vs 7 %, p 0.007) and gap days that were
  **small relative to the stock's normal range** (smallest third by gap at 09:44 13 % vs 7 %, p 0.003;
  narrowest day range 13 % vs 7 %, p 0.003). In plain-percent terms the "already moving" pair is
  large (peak ≥ 25 %: 28 % vs 10 % and 26 % vs 10 %) and it is not a repeat-gap artefact (24 % vs 9 %
  with every name that had a scored gap in the prior 30 days removed). **These cannot be promoted
  here — a reversed hypothesis is a new hypothesis and needs a fresh block; the held-out read is 4
  runners and agrees on only 3 of the 7.** Filed as the leads for the next block, with the direction
  now stated.
- **What it means for his goal** (*"catch big winners while limiting losses"*): on the gap day itself
  there is no ranking we can compute that finds the big winners, and the score's admission line is
  not costing us runners — it is not finding them either. The lever for "catch big winners" is not a
  better gap-day filter; it is (i) the next block's read of the two reversed leads, (ii) measuring the
  run from the 09:31 entry price rather than the close (this read under-credits names that ran on day
  1), and (iii) catalyst content we do not measure (surprise vs expectation is readable on 224 alerted
  rows holding 14 runners — descriptive only). Selection is his call (THE LINE); nothing here supports
  a change.

## Method and population

**The gate (`gate_out.txt`, printed before any outcome was computed).** Population = every gap-day
candidate the EP scan SCORED (`mi_ep_scan_log.ep_score NOT NULL`), scan dates 2026-05-01 → 2026-09-03
(the last scan date with ≥ 15 later sessions in `mi_daily_closes`; the daily table ends 09-25), ONE row
per (ticker, scan_date). 5,818 scored ticks → 670 pairs / 546 names / 86 scan dates. **Dedupe rule:**
prefer the tick that PASSED (filter_reason NULL and score_tier set), else the highest ep_score, ties →
the latest tick; 0 pairs change admission under a last-tick rule. All ticks were written the same day
(no backfill rows). 3 rows lack 15 forward sessions (AVEX 05-12, CHRN 05-28, BRUN 05-29) → 667 with an
outcome.

| | n | alerted (scan pass) | scored, not alerted |
|---|---|---|---|
| May | 228 | 111 | 117 |
| June | 110 | 53 | 57 |
| July | 119 | 41 | 78 |
| August | 198 | 99 | 99 |
| Sep 1–3 | 15 | 3 | 12 |
| **era A** (scan date < 08-22, old score: HIGH 201 · MODERATE 97 · none 332) | 630 | 298 | 332 |
| **era B** (08-22 on, separated score, bar 65: HIGH 9 · none 31) | 40 | 9 | 31 |
| **DISCOVERY** (≤ 08-14, 16 ISO weeks) | 607 | 287 | 320 |
| **HELD-OUT** (08-15 → 09-03, 3 ISO weeks) | 63 | 20 | 43 |
| price $5–20 / $20–100 / $100+ (none under $5: the universe floor) | 248 / 270 / 152 | 122 / 119 / 66 | 126 / 151 / 86 |

Median prior close $33.75; median gap at the scan 14.3 % (alerted 15.4 %, not 13.1 %); median score
72 alerted vs 32 not. Catalyst grade: strong 275 · routine 314 · game_changer 81.

**Alerted subset reconciled to the known 277** (live-source `mi_ep_alerts` 05-01..09-11, 261 before
08-22 — both reproduced by the same DISTINCT ON + live-source rule): 270 fall inside the window; the
other 7 are dated 09-04 (ALAB) and 09-08 (ERO IONQ PHVS QCOM ROIV SEI) with no 15-session outcome yet.
265 of the 270 join a scored scan-log row. Two disagreements between "the scan passed it" and "an
alert row exists", both explained and both alarms run down before any outcome was read:
- **44 scan-PASS rows (05-01..05-08) have no alert row** — `mi_ep_alerts` holds nothing before
  2026-05-11 (the old 90-day purge, `ep_profitability_program.md:843`). The scan-log pass row is the
  surviving record that the scan alerted them; counted as ALERTED.
- **7 alerts dated 05-20 were inserted at 18:40 ET** — an evening re-run after that morning's scan
  outage (CHANGELOG 2026-05-20) and after the pre-revenue-gate change shipped that afternoon. 5 (ALAB
  ARM DYN GH TATT) have no scored scan-log row at all and are outside the population; 2 (IMVT, SLS)
  were scored and REJECTED by the gap-day scan (best tick 48 and 20) — kept as scored-not-alerted.
  So alerted = 307 = 265 alert rows − 2 + 44.

**His labelled EPs:** BFLY 06-18 (scored 25, routine, rejected), PLTR 08-04, TEAM 08-07, HTFL 08-14,
MRNA 08-19 (all four alerted HIGH) are in the population; ABNB 08-07 (cut by the top-20 gap cap) and
CHPT 09-03 (`mcap_too_small`) were never scored and are outside it. Runs in ADR: BFLY 1.2, PLTR 2.7,
TEAM 4.9, HTFL 4.4, MRNA −1.3 — **none is a 15-session ≥ 5-ADR runner**, so the labelled check is
"where do they sit on each feature", never "are they runners".

**Data fact (checked on prod 09-27, re-checked here):** era-A scan-log rows carry only ep_score and
catalyst_quality — extension, market cap, float, ATR, prior-3-month change, theme flag and score
breakdown are empty on all 630 (era B: 18 of 40 filled). Every feature was therefore COMPUTED
(`features.py`) from `mi_daily_closes` (split-adjusted; 0 rows with a > 3 % raw-vs-adjusted prior-close
mismatch), `mi_stock_scores` (the latest row before the scan date, used only when ≤ 7 days old: 615 of
670 in the pool — `market_cap` is NULL on every row, so there is no size variable), `mi_themes` (the
hottest non-Retired snapshot containing the ticker as of the day BEFORE the scan — strictly prior,
the theme-axis shadow's rule; 186 themed, 116 within the live 7-day bound), `mi_market_regime` (the
row dated before the scan date; written 16:30 ET), `mi_intraday_bars` 09:30–09:44 aggregated on the
server (608 of 670 covered: 264 of 307 alerted, 344 of 363 not), sector from scores with
`mi_ticker_overrides` fallback, and the ticker's prior scored / passed scan-log dates (the scan log
starts 04-13).

**Outcome:** run = (max HIGH over sessions +1..+15 − gap-day CLOSE) ÷ ADR$, ADR$ = mean((h−l)/c) over
the 20 sessions before the gap × the gap-day close (the delayed lane's `compute_ep_adr_dollar`; the
09-27 H5 definition). Runner = ≥ 5 ADR (71 of 667); ≥ 8 ADR also reported (26). Median runner peak
+42 % in price; the smallest runner +11 %.

**Test, per feature (declared in `study.py` before running):** favourable tercile (cut points from
DISCOVERY, applied unchanged to HELD-OUT) vs the rest — runner rate each, AUC oriented to the declared
direction, week-block permutation p (labels shuffled within ISO week of the scan date, 2,000 draws,
seed 684, one-sided). **Pass = all four:** discovery p < 0.05 · same sign on HELD-OUT (a held-out
read with < 3 runners in total or < 8 rows on a side is "can't tell") · survives dropping the
discovery week with the most runners (W19, 18 of 67; same sign and p < 0.05) · survives dropping the
two largest runs (UMC 05-06 17.3 ADR, CRSR 05-08 16.8). **63 draws; 0.05 × 63 = 3.2 chance clears of
the discovery bar → up to 3 is noise.** Verdicts: **1 pass · 27 can't tell · 35 fail** (fail = the
discovery sign is against the declared direction).

**Held-out composition, stated before reading it:** 63 rows, 4 runners (MRVI 08-19 5.9 ADR, SMMT 08-26
5.8, GPRK 08-31 6.6, NTSK 09-03 5.6) — **all four were scored and rejected (scores 48 / 55 / 52 / 49);
the 20 alerts in the block produced no runner (best 3.5 ADR).** With 4 runners the block can contradict
a sign; it cannot carry one.

## Results — known before the open (PRE)

Rates are the share that ran ≥ 5 ADR; "favourable" is the declared side; n in brackets.

| feature (plain words) · favourable side | n disc | runner rate favourable vs rest | AUC | discovery p | held-out favourable vs rest (n) | drop best week | drop best two | labelled EPs in favourable | verdict |
|---|---|---|---|---|---|---|---|---|---|
| today's EP score · higher | 604 | 14% (205) vs 10% (399) +4.6pp | 0.53 | 0.135 | 0% (25) vs 11% (38) − | +3.5pp p 0.126 | +4.9pp p 0.107 | 4 of 5 | can't tell |
| gap % at the scan · higher | 604 | 10% (202) vs 12% (402) −1.8pp | 0.49 | 0.908 | 6% (16) vs 6% (47) − | −2.8pp | −0.9pp | 4 of 5 | fail (wrong way) |
| prev close above its 5-day low close (the live gate's own extension) · lower | 604 | 7% (201) vs 13% (403) −6.2pp | 0.43 | 0.993 | 8% (40) vs 4% (23) + | −4.2pp | −5.4pp | 1 of 5 | **fail, reverse p 0.007** |
| prev close vs SMA10, in ADRs · lower | 604 | 10% (201) vs 12% (403) −1.7pp | 0.45 | 0.745 | 6% (31) vs 6% (32) + | +1.6pp | −0.9pp | 0 of 5 | fail (wrong way) |
| prev close vs SMA20, in ADRs · lower | 604 | 9% (201) vs 12% (403) −3.2pp | 0.43 | 0.867 | 9% (22) vs 5% (41) + | −0.8pp | −2.4pp | 1 of 5 | fail (wrong way) |
| prev close vs SMA50, in ADRs · lower | 596 | 9% (198) vs 12% (398) −3.7pp | 0.43 | 0.862 | 13% (15) vs 4% (47) + | −2.2pp | −2.9pp | 1 of 5 | fail (wrong way) |
| mean distance to SMA10/20/50, in ADRs · lower | 596 | 9% (198) vs 12% (398) −3.7pp | 0.44 | 0.903 | 10% (21) vs 5% (41) + | −1.4pp | −2.9pp | 1 of 5 | fail (wrong way) |
| prev close above its 20-day low · lower | 604 | 8% (201) vs 13% (403) −4.7pp | 0.40 | 0.986 | 10% (30) vs 3% (33) + | −2.0pp | −3.9pp | 1 of 5 | **fail, reverse p 0.014** |
| 1-month change before the gap · lower | 604 | 8% (201) vs 12% (403) −4.0pp | 0.41 | 0.796 | 8% (13) vs 6% (50) + | −1.2pp | −3.2pp | 1 of 5 | fail (wrong way) |
| 3-month change before the gap · lower | 589 | 12% (196) vs 10% (393) +2.3pp | 0.49 | 0.357 | 14% (14) vs 4% (48) + | +3.7pp p 0.139 | +3.1pp p 0.255 | 1 of 5 | can't tell |
| 40-day close range / price (base tightness) · lower | 598 | 8% (199) vs 13% (399) −4.5pp | 0.48 | 0.983 | 6% (32) vs 7% (30) − | −0.9pp | −3.7pp | 1 of 5 | **fail, reverse p 0.017** |
| 20-day close range / price · lower | 604 | 6% (201) vs 13% (403) −6.9pp | 0.44 | 0.999 | 4% (25) vs 8% (38) − | −4.4pp | −6.2pp | 1 of 5 | **fail, reverse p 0.001** |
| net 40-day drift, in ADRs (flat base) · lower | 598 | 13% (199) vs 10% (399) +3.0pp | 0.50 | 0.147 | 13% (30) vs 0% (32) + | +5.1pp p 0.026 | +3.9pp p 0.083 | 4 of 5 | can't tell |
| sessions since the 6-month high (neglect) · higher | 604 | 11% (209) vs 11% (395) −0.9pp | 0.48 | 0.812 | 4% (23) vs 8% (40) − | −1.0pp | −0.1pp | 1 of 5 | fail (wrong way) |
| prev close below the 6-month high, % (depth) · higher | 604 | 12% (202) vs 11% (402) +1.2pp | 0.50 | 0.290 | 6% (16) vs 6% (47) − | +0.4pp p 0.431 | +2.0pp p 0.213 | 0 of 5 | can't tell |
| overhead to the 52-week high, in ADRs · lower | 604 | 10% (201) vs 11% (403) −1.0pp | 0.52 | 0.866 | 0% (15) vs 8% (48) − | −1.0pp | −1.3pp | 1 of 5 | fail (wrong way) |
| scan price above the 6-month high · yes | 604 | 11% (210) vs 11% (394) −0.2pp | 0.50 | 0.723 | 0% (21) vs 10% (42) − | −0.6pp | −1.8pp | 3 of 5 | fail (wrong way) |
| scan price above the 52-week high · yes | 604 | 11% (166) vs 11% (438) +0.5pp | 0.51 | 0.745 | 0% (14) vs 8% (49) − | +0.8pp p 0.654 | −0.0pp p 0.743 | 1 of 5 | can't tell |
| scan price above the all-time high · yes | 553 | 10% (89) vs 11% (464) −0.7pp | 0.50 | 0.791 | 0% (5) vs 6% (48) − thin | −0.9pp | −2.1pp | 0 of 5 | fail (wrong way) |
| prev close above SMA50 · yes | 596 | 11% (364) vs 11% (232) +0.5pp | 0.51 | 0.625 | 5% (41) vs 10% (21) − | −1.8pp p 0.826 | −0.4pp p 0.713 | 4 of 5 | can't tell |
| prev close above SMA200 · yes | 559 | 11% (349) vs 10% (210) +0.6pp | 0.51 | 0.424 | 9% (33) vs 5% (22) + | +0.2pp p 0.559 | −0.3pp p 0.569 | 4 of 5 | can't tell |
| how many of SMA10/20/50 the prev close is above · higher | 596 | 13% (268) vs 10% (328) +2.9pp | 0.53 | 0.298 | 5% (22) vs 8% (40) − | −0.8pp p 0.724 | +1.7pp p 0.437 | 4 of 5 | can't tell |
| Stage 2 (close > SMA50 > rising SMA200) · yes | 553 | 10% (187) vs 11% (366) −0.5pp | 0.49 | 0.680 | 7% (14) vs 8% (40) − | +0.0pp | −0.8pp | 2 of 5 | fail (wrong way) |
| RS composite the prior day · higher | 562 | 13% (188) vs 10% (374) +2.9pp | 0.53 | 0.327 | 0% (12) vs 8% (38) − | −0.3pp p 0.786 | +1.2pp p 0.532 | 3 of 5 | can't tell |
| in the RS pool the prior day · yes | 604 | 11% (562) vs 7% (42) +4.2pp | 0.51 | 0.804 | 6% (50) vs 8% (13) − | +2.1pp p 0.804 | +3.7pp p 0.796 | 5 of 5 | can't tell |
| catalyst grade game_changer/strong vs routine · higher | 604 | 13% (320) vs 9% (284) +3.7pp | 0.54 | 0.356 | 6% (35) vs 7% (28) − | +3.4pp p 0.272 | +2.5pp p 0.483 | 4 of 5 | can't tell |
| in an active theme the prior night (any age) · yes | 604 | 8% (159) vs 12% (445) −4.0pp | 0.46 | 0.774 | 4% (27) vs 8% (36) − | −4.2pp | −3.0pp | 2 of 5 | fail (wrong way) |
| in an active theme the prior night (7-day bounded) · yes | 604 | 8% (95) vs 12% (509) −3.2pp | 0.48 | 0.870 | 5% (21) vs 7% (42) − | −5.2pp | −2.2pp | 0 of 5 | fail (wrong way) |
| theme stage Nascent/Accelerating · yes | 604 | 11% (47) vs 11% (557) −0.5pp | 0.50 | 0.519 | 0% (7) vs 7% (56) − thin | −1.9pp | +0.1pp | 0 of 5 | fail (wrong way) |
| market regime Bull · yes | 604 | 12% (413) vs 9% (191) +3.2pp | 0.54 | 0.780 | 4% (27) vs 8% (36) − | +0.3pp p 0.779 | +2.4pp p 0.774 | 3 of 5 | can't tell |
| SPY vs its 50-day · higher | 604 | 14% (203) vs 10% (401) +4.8pp | 0.59 | 0.501 | 0% (0) vs 6% (63) thin | +4.4pp p 0.524 | +3.8pp p 0.516 | 0 of 5 | can't tell |
| share price · lower | 604 | 15% (201) vs 9% (403) +6.5pp | 0.61 | **0.018** | 18% (22) vs 0% (41) + | +6.7pp p 0.009 | +4.8pp p 0.053 | 1 of 5 | can't tell (fails drop-best-two) |
| ADR % · higher | 604 | 14% (202) vs 10% (402) +4.2pp | 0.56 | **0.020** | 0% (11) vs 8% (52) − | +5.2pp p 0.029 | +5.0pp p 0.010 | 1 of 5 | can't tell (held-out against) |
| 20-day dollar volume · lower | 604 | 15% (201) vs 9% (403) +6.5pp | 0.56 | **0.010** | 8% (24) vs 5% (39) + | +9.0pp p 0.001 | +6.1pp p 0.007 | 2 of 5 | **PASS** (see caveats above) |
| a scored gap on this name in the prior 90 days · no | 604 | 12% (507) vs 7% (97) +4.6pp | 0.53 | 0.369 | 8% (49) vs 0% (14) + | +4.6pp p 0.170 | +6.0pp p 0.181 | 5 of 5 | can't tell |
| pre-market relative volume · higher | 545 | 15% (182) vs 10% (363) +5.7pp | 0.54 | 0.175 | 3% (30) vs 10% (31) − | +3.8pp p 0.177 | +6.0pp p 0.160 | 4 of 5 | can't tell |
| projected volume multiple at the scan · higher | 297 | 7% (100) vs 11% (197) −3.7pp | 0.47 | 0.849 | 12% (24) vs 0% (10) + | −4.7pp | −4.8pp | 1 of 1 | fail (wrong way) |
| first scored tick before 09:30 (a pre-market gap) · yes | 604 | 11% (430) vs 11% (174) +0.2pp | 0.50 | 0.501 | 7% (44) vs 5% (19) + | −1.9pp p 0.816 | +0.2pp p 0.481 | 5 of 5 | can't tell |

Descriptive, no draw (share ≥ 5 ADR, n): sector — Technology 14 % (33/233), Healthcare 17 % (21/122),
Industrials 5 % (5/92), Consumer Cyclical 4 % (2/46), Financials 8 % (3/36), Energy 30 % (3/10);
theme stage — none 12 % (57/481), Fading 6 % (4/66), Mainstream 8 % (5/66), Nascent 7 % (2/29),
Accelerating 12 % (3/25); regime — Bull 12 % (51/440), Choppy 8 % (9/110), Correcting 11 % (11/97),
Crisis 0 % (0/20); tier — HIGH 10 % (22/210), MODERATE 14 % (13/96), none 10 % (36/361); catalyst —
routine 9 % (28/312), strong 12 % (34/274), game_changer 11 % (9/81); era A 11 % (68/627), era B 8 %
(3/40).

## Results — known at 09:30 (the open print)

| feature · favourable side | n disc | favourable vs rest | AUC | discovery p | held-out (n) | drop best week | drop best two | labelled in fav | verdict |
|---|---|---|---|---|---|---|---|---|---|
| gap % at the open print · higher | 604 | 10% (202) vs 11% (402) −1.0pp | 0.45 | 0.809 | 7% (15) vs 6% (48) + | −1.3pp | −0.1pp | 5 of 5 | fail (wrong way) |
| open above the 6-month high · yes | 604 | 11% (173) vs 11% (431) −0.2pp | 0.50 | 0.704 | 0% (16) vs 9% (47) − | −1.4pp | −1.4pp | 4 of 5 | fail (wrong way) |
| open above the 52-week high · yes | 604 | 11% (130) vs 11% (474) −0.4pp | 0.50 | 0.787 | 0% (11) vs 8% (52) − | −1.3pp | −1.2pp | 2 of 5 | fail (wrong way) |
| open above the all-time high · yes | 553 | 12% (69) vs 10% (484) +1.1pp | 0.51 | 0.598 | 0% (3) vs 6% (50) − thin | −0.0pp | −0.8pp | 0 of 5 | can't tell |
| open vs SMA50, in ADRs · lower | 596 | 12% (198) vs 11% (398) +1.6pp | 0.47 | 0.124 | 5% (20) vs 7% (42) − | +4.0pp p 0.048 | +2.4pp p 0.084 | 0 of 5 | can't tell |
| open vs SMA20, in ADRs · lower | 604 | 12% (201) vs 10% (403) +2.0pp | 0.49 | 0.125 | 10% (20) vs 5% (43) + | +4.7pp p 0.067 | +2.8pp p 0.092 | 0 of 5 | can't tell |
| Stage 2 with the open · yes | 553 | 10% (239) vs 10% (314) −0.0pp | 0.50 | 0.539 | 10% (21) vs 6% (33) + | +1.5pp | −0.1pp | 2 of 5 | fail (wrong way) |
| **post-hoc: the 09-27 lead under its own definition** — open vs the SMAs below it, median, in ADRs · lower (`posthoc.py`, replicated to 3 decimals on 246 stored rows) | 563 | 13% (187) vs 10% (376) +3.3pp | — | 0.040 | 9% (22) vs 5% (37) + (4 runners) | — | — | **0 of 5** | not a draw; can't tell, conflicts with his labels |
| ↳ on the alerted rows only | 264 | 17% (90) vs 10% (174) | — | 0.032 | 0% (8) vs 0% (11) | | | | |
| ↳ on the scored-not-alerted rows | 299 | 10% (97) vs 10% (202) | — | 0.450 | 14% (14) vs 8% (26) | | | | |
| ↳ on the 09-27 population (era-A alert rows) | 225 | 17% (82) vs 7% (143) | — | 0.010 | — | | | | reproduces the lead |
| ↳ by month, least-extended vs rest | | May 7/54 vs 29/159 · Jun 7/48 vs 3/52 · Jul 6/47 vs 3/58 · Aug 5/38 vs 3/107 | | | | | | | reversed in May |

## Results — known at 09:45 (opening range; 608 of 670 rows have minute bars, 264 of 307 alerted / 344 of 363 not)

| feature · favourable side | n disc | favourable vs rest | AUC | discovery p | held-out (n) | drop best week | drop best two | labelled in fav | verdict |
|---|---|---|---|---|---|---|---|---|---|
| where 09:44 sits in the opening range · higher | 547 | 9% (183) vs 12% (364) −2.8pp | 0.45 | 0.747 | 11% (19) vs 5% (42) + | −1.5pp | −2.8pp | 2 of 5 | fail (wrong way) |
| opening range / ADR · lower | 547 | 12% (182) vs 11% (365) +0.6pp | 0.53 | 0.177 | 6% (16) vs 7% (45) − | +3.9pp p 0.105 | +1.4pp p 0.146 | 1 of 5 | can't tell |
| gap % at 09:44 · higher | 547 | 7% (183) vs 13% (364) −6.1pp | 0.41 | 0.997 | 6% (17) vs 7% (44) − | −8.2pp | −5.4pp | 5 of 5 | **fail, reverse p 0.003** |
| 09:44 vs the open · higher | 547 | 10% (183) vs 12% (364) −2.0pp | 0.46 | 0.737 | 8% (25) vs 6% (36) + | −2.1pp | −1.3pp | 3 of 5 | fail (wrong way) |
| first-15-minute volume / 20-day average daily volume · higher | 547 | 11% (183) vs 11% (364) −0.3pp | 0.49 | 0.795 | 8% (39) vs 5% (22) + | −1.8pp | −0.4pp | 5 of 5 | fail (wrong way) |
| opening-range high above the 6-month high · yes | 547 | 10% (196) vs 12% (351) −2.3pp | 0.47 | 0.898 | 4% (24) vs 8% (37) − | −3.6pp | −3.5pp | 4 of 5 | fail (wrong way) |

The §0e read ("top 30 % of the ORB → 17 % vs 6.8 % reach 8 ADR", 91 HIGH alerts, run measured from
entry) does not appear here with the run measured from the close; the 09-27 H5 read on the rank
shadow's own `open_range_position` (8.3 % vs 10.0 %, n 180) already found the same null.

## Results — known at the close (a day-2+ entry only; never the 09:31 entry)

| feature · favourable side | n disc | favourable vs rest | AUC | discovery p | held-out (n) | drop best week | drop best two | labelled in fav | verdict |
|---|---|---|---|---|---|---|---|---|---|
| close location in the day's range · higher | 604 | 12% (203) vs 10% (401) +1.8pp | 0.49 | 0.468 | 4% (25) vs 8% (38) − | +0.1pp p 0.653 | +0.1pp p 0.713 | 4 of 5 | can't tell |
| day range / ADR · higher | 604 | 7% (202) vs 13% (402) −5.5pp | 0.48 | 0.997 | 9% (23) vs 5% (40) + | −5.5pp | −6.1pp | 4 of 5 | **fail, reverse p 0.003** |
| volume vs the biggest day in a year · higher | 604 | 13% (202) vs 10% (402) +2.7pp | 0.51 | 0.260 | 5% (22) vs 7% (41) − | +4.0pp p 0.101 | +3.1pp p 0.210 | 5 of 5 | can't tell |
| volume vs 50-day average · higher | 604 | 11% (202) vs 11% (402) +0.4pp | 0.51 | 0.674 | 7% (30) vs 6% (33) + | +1.7pp p 0.420 | +0.6pp p 0.646 | 5 of 5 | can't tell |
| close vs open · higher | 604 | 8% (202) vs 12% (402) −4.0pp | 0.46 | 0.953 | 8% (24) vs 5% (39) + | −5.1pp | −4.6pp | 4 of 5 | **fail, reverse p 0.047** |
| gap % at the close · higher | 604 | 10% (202) vs 11% (402) −1.0pp | 0.44 | 0.832 | 7% (15) vs 6% (48) + | −2.8pp | −0.9pp | 5 of 5 | fail (wrong way) |
| close vs SMA50, in ADRs · lower | 596 | 11% (198) vs 11% (398) −0.7pp | 0.47 | 0.416 | 10% (21) vs 5% (41) + | +1.6pp p 0.223 | +0.1pp p 0.345 | 0 of 5 | fail (wrong way) |
| close vs SMA20, in ADRs · lower | 604 | 11% (201) vs 11% (403) −0.2pp | 0.49 | 0.399 | 8% (24) vs 5% (39) + | +2.1pp p 0.288 | +0.6pp p 0.334 | 0 of 5 | fail (wrong way) |
| close above the 6-month high · yes | 604 | 10% (189) vs 12% (415) −1.5pp | 0.48 | 0.887 | 0% (19) vs 9% (44) − | −3.2pp | −3.3pp | 4 of 5 | fail (wrong way) |
| close above the 52-week high · yes | 604 | 10% (147) vs 11% (457) −1.2pp | 0.49 | 0.871 | 0% (13) vs 8% (50) − | −1.4pp | −1.8pp | 3 of 5 | fail (wrong way) |
| close above the all-time high · yes | 553 | 12% (82) vs 10% (471) +1.8pp | 0.51 | 0.674 | 0% (5) vs 6% (48) − thin | +0.1pp p 0.804 | +0.3pp p 0.786 | 1 of 5 | can't tell |

## Results — known when the alert was written (alerted rows only)

| feature · favourable side | n disc | favourable vs rest | AUC | discovery p | held-out (n) | drop best week | drop best two | labelled in fav | verdict |
|---|---|---|---|---|---|---|---|---|---|
| unscheduled catalyst (rank-shadow class) · yes | 208 | 15% (60) vs 8% (148) +6.9pp | 0.58 | 0.282 | 0% (9) vs 0% (11) thin | +6.9pp p 0.284 | +7.5pp p 0.226 | 1 of 4 | can't tell |

Descriptive (alerted rows with the field; share ≥ 5 ADR, n): judge tier HIGH 9 % (12/129), MODERATE
12 % (4/34); judge grade strong 8 % (6/72), game_changer 10 % (6/63), routine 10 % (4/40); catalyst type
sales_acceleration 8 % (10/119), policy 11 % (2/19), theme 6 % (1/16); scheduled 8 % (12/159) vs
unscheduled 13 % (9/69); beat 8 % (5/64) vs no beat 10 % (19/200); revenue growth is filled on 224
alerted rows holding 14 runners — too thin for a draw, so "surprise vs expectation" (his principle) is
unmeasured here beyond the unscheduled read above.

**Variables from `327_hypotheses §5` and what happened to each:** EP-day close location, range ÷ ADR,
volume vs its own history → built (CLOSE group). Opening-range position at 09:45 → built (608 covered).
Cleared a ≥ 6-month / 52-week / all-time high → built at the scan price, the open and the close. Pre-EP
base length / depth → built as sessions-since-high, depth below the high, 20/40-day range and drift.
Stage 1→2 and closes above SMA10/20/50 → built (prev close and open). Theme stage and strength → built
from `mi_themes` history, strictly prior. RS rank → built (fresh ≤ 7 days). Price / ADR % / liquidity /
sector → built (dollar volume from bars; sector from scores + overrides). Repeat EP / days since the
prior alert → built from the scan log (alerts before 05-11 are purged, so the scan log is the source).
Judge tier / grade, catalyst type, expectedness, beat → read from the alert / rank shadow (alerted rows
only). Revenue growth → 224 alerted rows, descriptive only. Market regime → built. **Not built:**
market cap / float (NULL everywhere — no size variable), his chart verdict (8 of 277, n too small to
score), per-stock pullback character (a post-gap variable, outside "known on the gap day"), the
follow-through gauge (a market-state series, not a per-name feature — a separate build).

## Which runners the score and filters dropped

36 of the 71 runners were scored by the gap-day scan and rejected on the score bar (10.0 % of the 361
rejected rows ran, vs 11.4 % of the 306 alerted). Named, largest run first (run in ADR / peak %):

UMC 05-06 (score 22, 17.3 ADR / +56 %) · CRSR 05-08 (38, 16.8 / +66 %) · HPE 05-29 (0, 12.6 / +49 %) ·
PSNL 05-13 (46, 12.5 / +96 %) · UMC 05-14 (0, 9.8 / +38 %) · QURE 05-29 (32, 9.1 / +76 %) · SHLS 05-05
(30, 9.0 / +54 %) · RDW 05-18 (36, 8.9 / +91 %) · BB 05-04 (−7, 8.7 / +54 %) · OMER 07-27 (38, 8.6 /
+60 %) · RNG 07-24 (37, 8.5 / +42 %) · SLS 05-13 (7, 8.2 / +46 %) · ARM 05-06 (−12, 8.0 / +47 %) · PENG
05-13 (0, 7.4 / +52 %) · VOD 07-10 (42, 7.2 / +11 %) · CGEM 06-08 (42, 7.1 / +46 %) · RLAY 05-19 (33,
7.0 / +45 %) · AVAH 06-02 (33, 6.8 / +33 %) · PURR 05-19 (7, 6.6 / +49 %) · AVAH 08-13 (30, 6.6 / +24 %)
· GPRK 08-31 (52, 6.6 / +19 %, held-out) · ABSI 06-15 (6, 6.6 / +66 %) · AAOI 07-31 (37, 6.5 / +71 %) ·
COHR 07-31 (30, 6.4 / +49 %) · DDOG 05-07 (48, 6.2 / +32 %) · NVAX 05-06 (34, 6.0 / +24 %) · GFS 05-05
(0, 5.9 / +25 %) · MRVI 08-19 (48, 5.9 / +30 %, held-out) · SMMT 08-26 (55, 5.8 / +32 %, held-out) · CEVA
05-11 (14, 5.8 / +36 %) · NTSK 09-03 (49, 5.6 / +32 %, held-out) · SHAZ 05-14 (29, 5.2 / +56 %) · WDAY
05-22 (43, 5.2 / +24 %) · CSTL 07-31 (40, 5.1 / +24 %) · YETI 05-14 (36, 5.1 / +20 %) · WIX 08-04 (35,
5.0 / +29 %).

Thirteen of these ran ≥ 8 ADR; 22 of the 36 carry a `routine` catalyst grade, 14 `strong`. Every one
was killed by the score bar (`score N < 50`, or `< bar 65` after 08-22) — none by a later gate. The
alerted runners for comparison are in `runners_dropped.txt` (35, led by VOYG 05-05 13.5 ADR, TE 05-12
13.3, HQ 06-15 12.4, NRIX 06-08 11.9, VPG 05-12 11.6).

Outside this population by construction (never scored): ABNB 08-07 (top-20 gap cap) and CHPT 09-03
(`mcap_too_small`) — the never-scored class is a separate question (#617 / #624).

## What this does not answer

- **Whether the two reversed leads are real.** "Already moving before the gap" (wide 20-day range,
  extended off the 5-day low) and "a small gap day relative to the stock's range" were significant
  against their declared direction. A hypothesis reversed after seeing the data is a new hypothesis;
  this read cannot confirm it. The next held-out block (scan dates 09-04 → 09-25, mature by ~10-16)
  is the test, with the direction now stated in advance.
- **The 09:31 entry's own frame.** The run is measured from the gap-day close (the pre-registered,
  09-27-comparable definition). A name that ran on day 1 itself is under-credited: 38 non-runners
  peaked ≥ 25 % in price. The ORB-entry question needs the run measured from the ORB high / fill
  price — a different outcome, his definition to choose.
- **Held-out power.** 63 rows and 4 runners can contradict a sign but cannot carry one; every "can't
  tell" above is exactly that, not a null.
- **ADR units vs percent.** The ≥ 5-ADR label and a ≥ 25 % label disagree on 38 rows; the one
  arithmetic pass (thin dollar volume) is mostly a unit effect (17 % vs 15 % in percent terms).
- **Size.** No market-cap or float variable exists for these rows; "thin dollar volume" and "low
  price" are the only proxies, and they carried the only discovery-bar clears.
- **Surprise vs expectation** (his principle) — readable only on 224 alerted rows holding 14 runners;
  descriptive here (unscheduled 15 % vs scheduled 8 %, p 0.28), and unreadable on the rejected rows.
- **His chart verdict** (8 of 277) and the never-scored names (ABNB / CHPT class).
- **May.** 18 of the 67 discovery runners sit in one ISO week (W19, the first-week-of-May earnings
  cluster). Every feature was re-read without it; the composition effects that survived that drop are
  the ones reported.
- **The score pools two scales.** Era A (old score, 630 rows) and era B (rescaled 08-22, bar 65, 40
  rows) are one column; the discovery tercile cut (score ≥ 80 = top third) is an era-A cut applied to
  the held-out block, which straddles 08-22. The score's 0-of-25 held-out read is partly a scale
  artefact, not only a null.
- **How many reverse-direction hits chance would give.** 7 draws were significant against their
  declared direction; two-sided chance at 0.05 across 63 draws is about 3. More than chance — but 4 of
  the 7 are one nested cluster (20-day range, 40-day range, extended off the 5-day low, off the 20-day
  low), so the "already moving before the gap" lead is one finding counted four times, not four.

## Proposal for his ruling

No change to the score or the admission line is supported by this read: nothing known on the gap day
separates the ≥ 5-ADR runners in a way that would serve as a rule: the one pre-registered pass (the
least-traded third of names, 15 % vs 9 %) is consistent with the 1 to 1.5 chance passes expected across
63 draws and its post-hoc reads (absent in May, 17 % vs 15 % in percent terms) argue against it, the 09-27
extension lead does not confirm out of sample and would have down-ranked every EP he has named, and
the score's admission neither finds nor loses the runners (35 alerted vs 36 rejected). Three things are
his to decide, none of which moves money: (1) whether the next block (scan dates 09-04 → 09-25,
mature ~10-16) is read with the two reversed leads — "already moving before the gap" and "a modest gap
day relative to the stock's range" — pre-registered in their observed direction, plus the same 63
draws for a second held-out; (2) whether that read is also made in the 09:31 entry's own frame (run
from the ORB high) alongside the close frame, so a day-1 selection answer is not judged on a day-2
outcome; (3) whether the 36 named runners the scan scored and rejected — all killed by the score bar,
none by a later gate — are a population he wants any lane to watch, which is a scope question about
what the delayed lane sees, not a proposal. Selection, admission and the bar itself stay exactly where
they are.

## Addendum 2026-09-28 — measured from the actual live MAGNA53 entry (replayed bar-by-bar)

> ⚠ **VERIFIED by the orchestrator 2026-09-28 against what we actually traded:** of the 59 live fills with alert dates 05-01..09-03, 51 are in this population; the replay marks 39 filled, 12 unreadable (minute-bar gaps) and 1 not filled (`triggered_above_limit_never_filled` — a real fill the replay misses). So 39 of the 40 readable real fills reproduce, with entry prices within cents (e.g. TEAM 05-01 $85.19 real vs $85.13 replay). The other 8 real fills (GOOGL 05-01, ARM 05-07, KLAR 05-15, PURR 05-20, ROIV 05-21, IBM 05-22 among them) are not in the scored population.


**v1 RETRACTED, one line:** an earlier version of this addendum measured FILLED against a
09:30–09:44 15-minute "opening range" that does not exist in the live code. Those numbers are not
carried forward as findings; this section replaces it entirely.

**MEASUREMENT ONLY, $0, read-only.** Probe: `scripts/probes/_684/study_orb_live.py` (imports
`study.py` + `study_orb.py`'s functions, does not overwrite their outputs), `live_entry_bars.sql` /
`live_entry_bars.tsv` (one new pull: every 1-minute bar 09:30–16:00 ET for all 670 rows, 236,265
bars). Same 63 features, same DISCOVERY/HELD-OUT split, same permutation and pass bar.

**The live entry, read from code, not summarized:**
- **ORB = the single 09:30–09:31 ET one-minute bar's high/low** (`alpaca_client.get_first_bar`,
  `order_manager.py:564-565`) — NOT a 15-minute range.
- **Submit time = the row's own scan time.** Alerted rows: the FIRST-PASS tick (`pop.tsv:
  first_pass_time`). Rejected rows never passed, so there is no "first pass" — they use the row's
  own CHOSEN tick (`pop.tsv: scan_time`, the same highest-score/latest-tie tick that already
  supplies every other feature for that row), per the coordinator's instruction to apply the
  mechanics "at their scan time." **This choice is NOT robust and materially changes the fill
  count** — checked, not assumed: re-running the fill walk with rejected rows submitting at their
  EARLIEST tick instead (`first_tick_time`) drops WINDOW_OUT_OF_ORB from 232 to 106 of 361 rejected
  rows and roughly doubles their raw pre-admission fill count (82 → 188). The alerted-vs-rejected
  fill-rate comparison below should be read as anchored to one defensible choice, not as a robust
  finding either way.
- Floored UP to 09:31 (an order cannot submit before the open); a tick at/after 09:45 ET is
  **WINDOW_OUT_OF_ORB** — never placed (`scheduler.py:1119`, `skip_reasons.WINDOW_OUT_OF_ORB`).
- **Admission, in the real pipeline's own order** (`submit_trade_entry` steps 4b then 5):
  1. Real-time gap re-check (`entry_pipeline.check_rt_gap_floor`, wired for MAGNA53
     `live_tracker.py:606`) — toggle `ep_rt_entry_gap_recheck` live since 2026-08-02
     (`docs/setups/magna53_ep.md:1127`, OFF/not modeled before that date); floor = `MIN_GAP_PCT`
     10.0% before 2026-08-19, 9.0% from (`docs/setups/magna53_ep.md:1917`). Real-time price is a
     tick (`alpaca.get_latest_trade`); this replay approximates it with the submit-minute bar's
     OPEN — the finest grain stored, not exact — and fails OPEN on a missing price, matching the
     real function.
  2. `validate_orb_entry` (`backtester/filters.py:207`, called from `order_manager.py:569`): zero
     ORB range, or ORB range > 1.5× ATR-14-prior (`alert_rank_shadow.compute_atr14_prior`, mirrored
     exactly — simple mean of the last 14 true ranges, 40 calendar days back, >=10 prior rows
     required else skipped).
  3. **Fade guard — verified, not assumed, to be a no-op.** The real MAGNA53 call site
     (`live_tracker.py:603`) passes `fade_midpoint_ratio=None` explicitly ("Sonnet+Perplexity
     validation + ATR stop width + 10:00 ET cleanup already cover dead-cat fills"). Nothing to
     model.
- **Fill walk** (`entry_walk`, mirrored verbatim from `sustain_reject_replay.entry_walk` — the same
  mirroring pattern that module itself uses against `scripts/ep_replay.entry_walk`): limit =
  `stop_limit_buy_price(orb_high)` (the 0.5%-or-$0.02 buffer). **A bar already trading above the
  trigger AT submission is not special-cased** — the code checks the FIRST scanned bar exactly like
  any later one: its own open decides fill-at-open, limit-arming, or an intra-bar cross at the
  trigger, same as every subsequent bar.
- **Cancel = 10:00 ET for scan_date >= 2026-08-01, else no cancel (fills any time through the
  close).** This date is `sustain_reject_replay.entry_cancel_asof`'s own documented inference
  ("era-A fills as late as 11:35 prove no cancel then") — attributed to that module, not read
  directly off a live cleanup-job deploy date.
- **NOT modeled:** portfolio-state safeguards (`_check_safeguards` — LIVE_TRADING_ENABLED, /pause,
  max-concurrent-positions, daily-loss limit, drawdown breaker) and sizing multipliers. These depend
  on the rest of the book at the exact historical moment, which this per-name replay does not
  reconstruct — same scope boundary the original study drew. A row marked FILLED here means "would
  have triggered," never "would have executed regardless of the rest of the book."

**Outcome (RUN_B):** (max high from the fill minute through session +15 − the ACTUAL FILL PRICE, not
the trigger) / `adr_dollar_ep` (frame A's own denominator). Day 0's own contribution reads from the
same `mi_intraday_bars` pull (fill minute through 16:00); only sessions +1..+15 fall back to
`mi_daily_closes`, as frame A already does.

**Readable population = 609 of the 667 frame-A-scored rows** (58 unreadable). 53 of those 58 are
`abstain` (a scan-window gap wide enough that a cross could be hidden) and **skew heavily toward
alerted rows — 42 of 53, vs 11 of 53 rejected** — the single unreadable slice most likely to move a
number if resolved. 5 more lack a 09:30 bar entirely; 3 lack a 15-session forward outcome (frame A's
own censoring). 6 of the 58 unreadable rows are frame-A runners (fillability unknown).

**Fill rate: 183 of 609 readable rows filled (30.0%).** Alerted rows fill MORE often (115 of 263 =
43.7%) than rejected rows (68 of 346 = 19.7%) — **subject to the submit-time caveat above.** The
dominant reason a row never fills is simply never being placed: 331 of 609 readable rows (54%) are
WINDOW_OUT_OF_ORB (99 alerted, 232 rejected — rejected rows are hit harder by this because their
"scan time" here is the highest-score/latest tick, which skews later as a move develops). Of the
remainder: 37 no_entry (placed, never crossed), 34 gap_below_floor, 24 orb_invalid (mostly
stop-too-wide vs 1.5× ATR).

**Runner composition:** published frame A (all 667) 71 (10.6%); frame A on the readable population
(609) 65 (10.7% — the readable subset is not a biased slice); frame B (609) 27 (4.4%). 20 runners
are runners in both frames. 7 are frame-B-only (not frame-A runners): ABCL 08-10, AMBQ 05-12, FCEL
05-12, FLEX 05-06, INFQ 05-21, **MRNA 08-19, TEAM 08-07** (both his labelled EPs — see below). 45 are
frame-A-only (never placed/filled, or filled short of 5 ADR).

**Of the 71 published frame-A runners: 65 are readable, 40 of those were never placed or never
filled** (25 were). 6 are unreadable (fillability unknown): MTSI 05-07, CRSR 05-27, NRIX 06-08, ELVN
06-11, DFTX 06-22, FCEL 06-24.

**Held-out power collapses further in frame B: only 1 runner in the whole HELD-OUT block** (MRNA,
below) vs frame A's 4 — below the pass bar's own 3-runner floor, so **no feature can clear the
four-condition bar in frame B by construction.** `0` PASS below is mechanical, not a null finding.
Frame A′ (same 609 rows) still shows 2 PASS (`dollar_vol_20d`, matching published; `prev_close`,
which read "can't tell" published) — both fall to "can't tell" in frame B.

**Per-feature results (readable population, 609 rows; rates = share >= 5 ADR in each frame):**

| feature (plain words) · favourable side | when | n | frame A′ (readable pop) fav vs rest | frame A′ verdict | frame B fav vs rest | frame B verdict | changed |
|---|---|---|---|---|---|---|---|
| today's EP score · HIGHER | PRE | 550 | 12.2% (197) vs 10.5% (353) | can't tell (discovery p >= 0.05) | 6.6% (197) vs 3.7% (353) | can't tell (discovery p >= 0.05) |  |
| gap % at the scan · HIGHER | PRE | 550 | 9.8% (184) vs 11.8% (366) | fail (wrong way) | 6.0% (184) vs 4.1% (366) | can't tell (discovery p >= 0.05) | **CHANGED** |
| prev close above its 5-day low close (live gate def) · LOWER | PRE | 550 | 6.6% (183) vs 13.4% (367) | fail (wrong way), p=0.006 the other way | 1.6% (183) vs 6.3% (367) | fail (wrong way), p=0.004 the other way |  |
| prev close vs SMA10, in ADRs · LOWER | PRE | 550 | 10.4% (183) vs 11.4% (367) | fail (wrong way) | 2.2% (183) vs 6.0% (367) | fail (wrong way), p=0.007 the other way |  |
| prev close vs SMA20, in ADRs · LOWER | PRE | 550 | 8.7% (183) vs 12.3% (367) | fail (wrong way) | 2.2% (183) vs 6.0% (367) | fail (wrong way), p=0.026 the other way |  |
| prev close vs SMA50, in ADRs · LOWER | PRE | 542 | 8.3% (180) vs 12.4% (362) | fail (wrong way) | 2.8% (180) vs 5.8% (362) | fail (wrong way) |  |
| mean distance to SMA10/20/50, in ADRs · LOWER | PRE | 542 | 8.3% (180) vs 12.4% (362) | fail (wrong way) | 2.8% (180) vs 5.8% (362) | fail (wrong way) |  |
| prev close above its 20-day low · LOWER | PRE | 550 | 8.2% (183) vs 12.5% (367) | fail (wrong way), p=0.021 the other way | 2.2% (183) vs 6.0% (367) | fail (wrong way), p=0.006 the other way |  |
| 1-month change before the gap · LOWER | PRE | 550 | 7.6% (183) vs 12.8% (367) | fail (wrong way) | 2.2% (183) vs 6.0% (367) | fail (wrong way) |  |
| 3-month change before the gap · LOWER | PRE | 535 | 12.9% (178) vs 9.5% (357) | can't tell (discovery p >= 0.05) | 3.9% (178) vs 5.3% (357) | fail (wrong way) | **CHANGED** |
| 40-day close range / price (base tightness) · LOWER | PRE | 544 | 7.7% (181) vs 12.7% (363) | fail (wrong way), p=0.009 the other way | 1.1% (181) vs 6.6% (363) | fail (wrong way), p=0.000 the other way |  |
| 20-day close range / price · LOWER | PRE | 550 | 6.6% (183) vs 13.4% (367) | fail (wrong way), p=0.002 the other way | 1.6% (183) vs 6.3% (367) | fail (wrong way), p=0.000 the other way |  |
| net 40-day drift, in ADRs (flat base) · LOWER | PRE | 544 | 13.3% (181) vs 9.9% (363) | can't tell (discovery p >= 0.05) | 2.8% (181) vs 5.8% (363) | fail (wrong way), p=0.029 the other way | **CHANGED** |
| sessions since the 6-month high (neglect) · HIGHER | PRE | 550 | 9.8% (184) vs 11.8% (366) | fail (wrong way) | 1.6% (184) vs 6.3% (366) | fail (wrong way), p=0.000 the other way |  |
| prev close below the 6-month high, % (depth) · HIGHER | PRE | 550 | 12.0% (184) vs 10.7% (366) | can't tell (discovery p >= 0.05) | 3.3% (184) vs 5.5% (366) | fail (wrong way) | **CHANGED** |
| overhead to the 52-week high, in ADRs · LOWER | PRE | 550 | 10.9% (183) vs 11.2% (367) | fail (wrong way) | 8.7% (183) vs 2.7% (367) | can't tell (held-out too thin) | **CHANGED** |
| scan price above the 6-month high · yes | PRE | 550 | 10.8% (186) vs 11.3% (364) | fail (wrong way) | 8.1% (186) vs 3.0% (364) | can't tell (held-out too thin) | **CHANGED** |
| scan price above the 52-week high · yes | PRE | 550 | 11.6% (146) vs 10.9% (404) | can't tell (discovery p >= 0.05) | 8.9% (146) vs 3.2% (404) | can't tell (discovery p >= 0.05) |  |
| scan price above the all-time high · yes | PRE | 504 | 10.7% (75) vs 10.7% (429) | fail (wrong way) | 6.7% (75) vs 4.2% (429) | can't tell (discovery p >= 0.05) | **CHANGED** |
| prev close above SMA50 · yes | PRE | 542 | 11.3% (328) vs 10.8% (214) | can't tell (discovery p >= 0.05) | 5.8% (328) vs 3.3% (214) | can't tell (discovery p >= 0.05) |  |
| prev close above SMA200 · yes | PRE | 510 | 10.4% (316) vs 10.3% (194) | can't tell (discovery p >= 0.05) | 6.0% (316) vs 2.1% (194) | can't tell (held-out too thin) |  |
| how many of SMA10/20/50 the prev close is above · HIGHER | PRE | 542 | 12.4% (241) vs 10.0% (301) | can't tell (discovery p >= 0.05) | 7.9% (241) vs 2.3% (301) | can't tell (held-out too thin) |  |
| Stage 2 (close > SMA50 > rising SMA200) · yes | PRE | 504 | 10.1% (169) vs 10.8% (335) | fail (wrong way) | 7.1% (169) vs 3.3% (335) | can't tell (discovery p >= 0.05) | **CHANGED** |
| RS composite the prior day · HIGHER | PRE | 508 | 13.5% (170) vs 10.4% (338) | can't tell (discovery p >= 0.05) | 9.4% (170) vs 2.7% (338) | can't tell (held-out too thin) |  |
| in the RS pool the prior day · yes | PRE | 550 | 11.4% (508) vs 7.1% (42) | can't tell (discovery p >= 0.05) | 4.9% (508) vs 2.4% (42) | can't tell (discovery p >= 0.05) |  |
| catalyst grade (game_changer/strong vs routine) · HIGHER | PRE | 550 | 12.8% (274) vs 9.4% (276) | can't tell (discovery p >= 0.05) | 7.7% (274) vs 1.8% (276) | can't tell (discovery p >= 0.05) |  |
| in an active theme the prior night (any age) · yes | PRE | 550 | 8.5% (141) vs 12.0% (409) | fail (wrong way) | 2.8% (141) vs 5.4% (409) | fail (wrong way) |  |
| in an active theme the prior night (7-day bounded) · yes | PRE | 550 | 8.3% (84) vs 11.6% (466) | fail (wrong way) | 4.8% (84) vs 4.7% (466) | can't tell (discovery p >= 0.05) | **CHANGED** |
| theme stage Nascent/Accelerating · yes | PRE | 550 | 9.1% (44) vs 11.3% (506) | fail (wrong way) | 2.3% (44) vs 4.9% (506) | fail (wrong way) |  |
| market regime Bull · yes | PRE | 550 | 12.4% (380) vs 8.2% (170) | can't tell (discovery p >= 0.05) | 6.3% (380) vs 1.2% (170) | can't tell (discovery p >= 0.05) |  |
| SPY vs its 50-day · HIGHER | PRE | 550 | 16.4% (195) vs 8.2% (355) | can't tell (discovery p >= 0.05) | 10.3% (195) vs 1.7% (355) | can't tell (discovery p >= 0.05) |  |
| share price · LOWER | PRE | 550 | 15.8% (183) vs 8.7% (367) | PASS ⚠ labelled-EP conflict | 7.6% (183) vs 3.3% (367) | can't tell (discovery p >= 0.05) | **CHANGED** |
| ADR % · HIGHER | PRE | 550 | 14.7% (184) vs 9.3% (366) | can't tell (held-out sign against) | 5.4% (184) vs 4.4% (366) | can't tell (discovery p >= 0.05) |  |
| 20-day dollar volume · LOWER | PRE | 550 | 15.3% (183) vs 9.0% (367) | PASS | 5.5% (183) vs 4.4% (367) | can't tell (discovery p >= 0.05) | **CHANGED** |
| a scored gap on this name in the prior 90 days · no | PRE | 550 | 12.3% (465) vs 4.7% (85) | can't tell (discovery p >= 0.05) | 4.7% (465) vs 4.7% (85) | can't tell (discovery p >= 0.05) |  |
| pre-market relative volume · HIGHER | PRE | 492 | 14.0% (164) vs 10.4% (328) | can't tell (discovery p >= 0.05) | 11.0% (164) vs 2.4% (328) | can't tell (held-out too thin) |  |
| projected volume multiple at the scan · HIGHER | PRE | 297 | 7.0% (100) vs 10.7% (197) | fail (wrong way) | 0.0% (100) vs 0.0% (197) | can't tell (discovery p >= 0.05) | **CHANGED** |
| first scored tick before 09:30 · yes ⚠ mechanical | PRE | 550 | 11.1% (378) vs 11.1% (172) | can't tell (discovery p >= 0.05) | 6.9% (378) vs 0.0% (172) | can't tell (held-out too thin) |  |
| gap % at the open print · HIGHER | 0930 | 550 | 9.8% (184) vs 11.8% (366) | fail (wrong way) | 6.5% (184) vs 3.8% (366) | can't tell (discovery p >= 0.05) | **CHANGED** |
| open above the 6-month high · yes | 0930 | 550 | 10.4% (154) vs 11.4% (396) | fail (wrong way) | 9.1% (154) vs 3.0% (396) | can't tell (held-out too thin) | **CHANGED** |
| open above the 52-week high · yes | 0930 | 550 | 10.5% (114) vs 11.2% (436) | fail (wrong way) | 10.5% (114) vs 3.2% (436) | can't tell (held-out too thin) | **CHANGED** |
| open above the all-time high · yes | 0930 | 504 | 11.9% (59) vs 10.6% (445) | can't tell (discovery p >= 0.05) | 8.5% (59) vs 4.0% (445) | can't tell (discovery p >= 0.05) |  |
| open vs SMA50, in ADRs · LOWER | 0930 | 542 | 12.8% (180) vs 10.2% (362) | can't tell (discovery p >= 0.05) | 3.3% (180) vs 5.5% (362) | fail (wrong way) | **CHANGED** |
| open vs SMA20, in ADRs · LOWER | 0930 | 550 | 12.6% (183) vs 10.3% (367) | can't tell (discovery p >= 0.05) | 2.2% (183) vs 6.0% (367) | fail (wrong way), p=0.049 the other way | **CHANGED** |
| Stage 2 with the open · yes | 0930 | 504 | 9.9% (213) vs 11.0% (291) | fail (wrong way) | 6.6% (213) vs 3.1% (291) | can't tell (discovery p >= 0.05) | **CHANGED** |
| where 09:44 sits in the opening range · HIGHER | 0945 | 531 | 9.6% (177) vs 12.2% (354) | fail (wrong way) | 5.1% (177) vs 4.5% (354) | can't tell (discovery p >= 0.05) | **CHANGED** |
| opening range / ADR · LOWER | 0945 | 531 | 11.9% (177) vs 11.0% (354) | can't tell (discovery p >= 0.05) | 4.5% (177) vs 4.8% (354) | fail (wrong way) | **CHANGED** |
| gap % at 09:44 · HIGHER | 0945 | 531 | 7.3% (177) vs 13.3% (354) | fail (wrong way), p=0.005 the other way | 6.2% (177) vs 4.0% (354) | can't tell (discovery p >= 0.05) | **CHANGED** |
| 09:44 vs the open · HIGHER | 0945 | 531 | 10.2% (177) vs 11.9% (354) | fail (wrong way) | 4.0% (177) vs 5.1% (354) | fail (wrong way) |  |
| first-15-minute volume / 20-day avg daily volume · HIGHER | 0945 | 531 | 11.3% (177) vs 11.3% (354) | can't tell (discovery p >= 0.05) | 7.9% (177) vs 3.1% (354) | can't tell (discovery p >= 0.05) |  |
| opening-range high above the 6-month high · yes | 0945 | 531 | 9.4% (191) vs 12.3% (340) | fail (wrong way) | 7.3% (191) vs 3.2% (340) | can't tell (discovery p >= 0.05) | **CHANGED** |
| close location in the day's range · HIGHER | CLOSE | 550 | 11.4% (184) vs 10.9% (366) | can't tell (discovery p >= 0.05) | 7.1% (184) vs 3.5% (366) | can't tell (discovery p >= 0.05) |  |
| day range / ADR · HIGHER | CLOSE | 550 | 7.1% (184) vs 13.1% (366) | fail (wrong way), p=0.004 the other way | 4.3% (184) vs 4.9% (366) | fail (wrong way) |  |
| volume vs the biggest day in a year · HIGHER | CLOSE | 550 | 12.5% (184) vs 10.4% (366) | can't tell (discovery p >= 0.05) | 7.1% (184) vs 3.5% (366) | can't tell (discovery p >= 0.05) |  |
| volume vs 50-day average · HIGHER | CLOSE | 550 | 10.3% (184) vs 11.5% (366) | fail (wrong way) | 8.2% (184) vs 3.0% (366) | can't tell (discovery p >= 0.05) | **CHANGED** |
| close vs open · HIGHER | CLOSE | 550 | 8.7% (184) vs 12.3% (366) | fail (wrong way) | 4.3% (184) vs 4.9% (366) | fail (wrong way) |  |
| gap % at the close · HIGHER | CLOSE | 550 | 10.3% (184) vs 11.5% (366) | fail (wrong way) | 6.5% (184) vs 3.8% (366) | can't tell (discovery p >= 0.05) | **CHANGED** |
| close vs SMA50, in ADRs (the 09-27 EOD lead) · LOWER | CLOSE | 542 | 10.0% (180) vs 11.6% (362) | fail (wrong way) | 2.8% (180) vs 5.8% (362) | fail (wrong way) |  |
| close vs SMA20, in ADRs · LOWER | CLOSE | 550 | 10.4% (183) vs 11.4% (367) | fail (wrong way) | 2.2% (183) vs 6.0% (367) | fail (wrong way) |  |
| close above the 6-month high · yes | CLOSE | 550 | 9.2% (174) vs 12.0% (376) | fail (wrong way), p=0.041 the other way | 7.5% (174) vs 3.5% (376) | can't tell (discovery p >= 0.05) | **CHANGED** |
| close above the 52-week high · yes | CLOSE | 550 | 9.6% (136) vs 11.6% (414) | fail (wrong way) | 8.1% (136) vs 3.6% (414) | can't tell (discovery p >= 0.05) | **CHANGED** |
| close above the all-time high · yes | CLOSE | 504 | 12.2% (74) vs 10.5% (430) | can't tell (discovery p >= 0.05) | 6.8% (74) vs 4.2% (430) | can't tell (discovery p >= 0.05) |  |
| unscheduled catalyst (alerted rows only) · yes | ALERT | 175 | 11.6% (43) vs 8.3% (132) | can't tell (discovery p >= 0.05) | 2.3% (43) vs 3.8% (132) | fail (wrong way) | **CHANGED** |

**27 of 63 verdicts change — read this as "frame A's negative/reversed reads mostly wash out to
noise," NOT as a new confirmed signal.** 24 of the 27 flip sign in the raw rate difference, but
almost every frame-B side lands on "can't tell" (does not clear discovery p<0.05), and the held-out
block has exactly ONE runner (MRNA) — the pass bar is unclearable by construction this time, so
nothing can be promoted regardless. **This does NOT reproduce the earlier (retracted) v1 addendum's
"day-0/close-strength persists conditional on fill" claim** — re-checked directly on this frame's
183 filled rows (not assumed to carry over): the pattern does not hold cleanly here, because the
filled population itself is composed completely differently once WINDOW_OUT_OF_ORB is modeled as a
real, dominant gate. No cluster claim is made in this replacement. **Two features clear discovery
p<0.05 in the favourable direction and read as leads, but are flagged mechanical, not continuation
signal:** `first_tick_preopen` (p=0.000) and `pm_rvol` (p=0.0125) both predict how MUCH WINDOW a
candidate gets before the 09:45/10:00 cutoffs (a pre-open first tick submits at 09:31 with the full
window; a 09:40 first tick has 5 minutes) — they predict FILL, not what happens after a fill, and
should not be read as selection leads without separating that out. **0 PASS in frame B**, mechanically
(see held-out above); the two frame-A′ PASSes (share price, dollar volume) both fall to "can't tell."

**Timing: alerts by when they first passed, in frame B** (alerted, readable rows with a computed
outcome): pre-open, n 161, filled 113, runnerB5 14 (8.7%); 09:30–09:44 (still inside the order
window), n 3, filled 2, runnerB5 0; 09:45+ (WINDOW_OUT_OF_ORB), n 99, filled 0 by construction,
runnerB5 0. Rejected rows for comparison, n 346, runnerB5 13 (3.8%). **This inverts the published
doc's "late-passing alerts run more" lead**: in the live frame, alerts that first pass AFTER 09:45
never get an order placed at all (0% by construction, not by outcome), so the finding that mattered
for a close-based read (late-passing alerts ran more) is not translatable to a live-entry frame —
those are exactly the alerts the live order never touches.

**His labelled EPs — status / fill / outcome (verified against the actual code, not the earlier
frame):** **BFLY 06-18 — WINDOW_OUT_OF_ORB**, never placed (its scan time was at/after 09:45).
**TEAM 08-07 — FILLED at 09:31, px $146.80** (run_xadr from the close 4.88 → run_xadr_B from the
fill 5.12 — a runner in BOTH frames now, not "never filled" as v1 wrongly said). **HTFL 08-14 —
orb_invalid: ORB range $2.55 > 1.5× ATR $1.46 (stop_too_wide)** — never placed; the admission gate
itself, not the fill window, is why. **PLTR 08-04 — FILLED at 09:31, px $148.63** (run_xadr 2.69 →
run_xadr_B 4.59, short of the 5-ADR bar). **MRNA 08-19 — FILLED at 09:33, px $120.15** (run_xadr
−1.30 → run_xadr_B **5.66, a runner** — the only held-out-block runner in frame B, and the sharpest
reversal of the five: frame A's close-based read said MRNA never ran; measured from the actual live
fill, it did).

**What changes for the live entry.** Two of his five labelled EPs never get an order placed at all —
one on timing (BFLY, scan time too late), one on the ATR admission gate (HTFL, opening range too
wide relative to its own volatility) — neither is a gap-day SELECTION question; both happen before
any of the 63 features could act. Two others (TEAM, MRNA) fill at 09:31–09:33 and are runners in the
live frame that frame A's close-based read missed or understated — MRNA specifically flips from "no
recovery" to "a real runner" once measured from where the order actually bought. Across the whole
population, the single largest determinant of "ran big or not" is whether the order was ever placed
or ever filled at all (54% never placed, mostly WINDOW_OUT_OF_ORB) — a fill/timing-mechanics
question the 63 gap-day features were never built to answer, not a selection-rule gap. Nothing here
argues for a rule change: 0 features pass in frame B, and the bar is mechanically unclearable this
time (1 held-out runner). The frame-B-only runners (ABCL, AMBQ, FCEL 05-12, FLEX, INFQ, plus TEAM
and MRNA above) are worth his eye only as names where the actual live entry outperformed the
close-based read — descriptive, not a rule.

**What this addendum does not answer / known approximations (stated, not hidden):**
- The submit-time choice for REJECTED rows (chosen tick vs earliest tick) is not robust — see the
  sensitivity check above; the fill-rate split by alerted/rejected should not be over-read.
- The real-time gap re-check uses the submit-minute bar's OPEN as a proxy for a live tick
  (`get_latest_trade`) — a coarser signal than the real gate sees.
- Portfolio-state safeguards (position caps, daily-loss limit, drawdown breaker, /pause) are not
  modeled — a FILLED row here is "would have triggered," not "would have executed regardless of the
  rest of the book."
- The 53 `abstain` (scan-window-gap) rows skew heavily toward alerted candidates (42 of 53) — the
  single unreadable slice most likely to move a number if resolved.
- Whether a limit-price buffer failure (price gaps clean through the limit before ever printing
  below it again) affects any of the 183 fills was not separately audited beyond what `entry_walk`
  already returns (`triggered_above_limit_never_filled` is counted inside `no_entry`, 37 total,
  not broken out further).
- Same 63 features only, no add/drop; the two reversed leads from the main study are not
  re-registered here (out of scope).

**Files:** `scripts/probes/_684/live_entry_bars.sql` (the one new pull) → `live_entry_bars.tsv`
(236,265 rows, gitignored) → `study_orb_live.py` (imports `study.py` + `study_orb.py`, mirrors
`sustain_reject_replay.entry_walk` verbatim) → `orb_live_status_out.txt`, `orb_live_results.tsv`
(frame B), `orb_live_results_A.tsv` (frame A′, same population), `orb_live_outcomes.tsv` (per-row
status/fill/outcome detail, all 667 rows).

## THE LINE

Measurement only. No strategy, score, threshold, admission rule, stop, size, safeguard or live trade
state was changed or is proposed as decided; every ruling above is his. Prod was read-only (`ssh` +
`psql` SELECTs, captured once to `scripts/probes/_684/`); no LLM call, no paid API, no deploy, no
table written, no PLAN.md edit, no commit.
