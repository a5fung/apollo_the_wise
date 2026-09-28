# #327 — the free hypothesis tests on the 277 real EPs: what held, what failed, what cannot be told yet

**2026-09-27 (Sunday build slot).** $0: replayed from the 09-26 rerun's captured files plus ONE read-only SELECT
(`mi_alert_rank_shadow` + `mi_ep_alerts.catalyst_type/judge_*` for the same 277 campaigns → `rank_shadow.tsv`).
No prod write, no new bars, no toggle, no table, no deploy, no PLAN.md line, no live code touched. Probe:
`scripts/probes/_327_real_ep/hyptests.py` (+ `hyptests_run.py`, `hyptests_run2.py`, `hyptests_report.py`); its
docstring is the pre-registration of record and was written before any result. Outputs in the same folder:
`hyp_gate_out.txt`, `hyp_anchor_out.txt`, `hyp_rows_*.tsv` (the two over 500 KB are gitignored), `hyp_report.txt`,
`hyp_summary.json`, `hyp_team_handwalk.txt`. Hypotheses tested: `327_hypotheses_2026-09-27.md` (its VERIFIED
section governs). Nothing here cites the voided-cohort docs.

## ⚠ VERIFIED 2026-09-27 by the orchestrator (this section wins)

- **Population:** the probe's own gate output reproduces the 277 exactly (ERA A 261 / 243 names / HIGH 184 · MODERATE
  66 · other 11; ERA B 16 / 16 / 14 · 2) and every fire sits in the 277; the split (discovery 250 campaigns / 573
  fires; held-out A 11 / 22; ERA B 16 / 37) is stated before any result.
- **H4 reproduced to the decimal from `reentry_rows.tsv` and `scripts/ep_replay_data/campaigns_era_c.tsv` with the
  orchestrator's own code:** 1×ADR low reclaim, first fire, trail — admitted −0.12R (n 102, negative in every month:
  May −0.08 · Jun −0.33 · Jul −0.12 · Aug −0.03), rejected +0.35R (n 64), undecided +0.61R (n 36); of the 11 fires
  that made ≥ 3R, 7 are rejected and 3 undecided today, 1 admitted. The rejections are the score bar (score_hi < 65:
  those winners scored 30–60, mostly MODERATE) — the `reason` column in that file is the day-1 trade outcome, not the
  rejection cause. The lane's own stop: admitted −0.32R (n 102), rejected −0.43R (n 64).
- **H13 in context:** the lane's trailing exit ALREADY works the way he described — `compute_settlement` exits the
  trail arm on a daily CLOSE below the moving-average line, never on an intraday touch. What failed here is applying
  a close rule to the INITIAL stop (the tight one under the reclaim): with no hard floor, losers ran to −2R to −40R.
- **Label fix carried to the hypotheses doc:** 545p3's "142 admit" includes 6 ERA B campaigns; on ERA A the era-C
  verdict is 136 admit / 81 reject / 44 undecided.

## The answer first

**One line: none of the eight ideas gives the lane a new edge on real EPs; the one bar that clears (H1b) is the
already-known fact that any stop wider than the lane's razor stop loses less, and the operator's two ideas (H12, H13)
lose MORE than the lane as mechanised here. 3 of 35 pre-registered draws clear, all three nested on one mechanism
(H1b's three widths), above the noise band of 2 but under the family line of 5.**

- **H2 — the "+6 points better than a random session" FAILS the bar.** It is not the both-ways volatility artefact
  the hypothesis predicted (under the original barriers the fires are stopped 1.8 points LESS often than random
  sessions, n 197 fires vs 3,547 control sessions, low reclaim), but it fails the week-clustered permutation under
  every yardstick (p 0.07–0.09 as originally measured), and it depends on the yardstick: scaled to each session's own
  full realised range the gap is −2.4 / −2.9 points (fire sessions' range 1.19× the pre-EP ADR vs 0.94× for random
  sessions); under the look-ahead-free yardstick (the fire session's range through the fire bar) the close reclaim
  keeps +6.0 (p 0.07, drop-2 +4.8) and the low reclaim falls to +2.6. What survives on every yardstick is "loses a
  range-unit less often" (53% vs 67%, p 0.001, low reclaim), not "wins more".
- **H1b — a stop scaled to the post-gap range HOLDS against the lane's own stop, but is NOT the fix.** k = 0.5 / 0.75 /
  1.0 × the trailing post-gap range beats the lane's own stop by +0.17 / +0.22 / +0.21R per fire (n 573, p ≤ 0.005,
  same sign on both held-out parts, fillable entry agrees). Against the pre-EP 1×ADR stop the same fires read −0.06 /
  −0.01 / −0.02R (the −0.06 is p 0.015 in the WRONG direction), and it keeps FEWER of the winners: 4 / 4 / 3 of the 7
  big-winner EPs and 1 / 1 / 0 of his 3 labelled EPs that fired, where 1×ADR keeps 5 of 7 and 2 of 3. Plain words:
  wider than a razor stop wins; the post-gap yardstick adds nothing over the pre-EP ADR and throws away winners.
- **H1c — the age of the stop-defining low FAILS.** A stop under the fire session's first-30-minute low costs −0.11R
  per fire vs the lane's stop (n 226, p 0.26); the first-60-minute low is flat (+0.01, n 198). Fires whose low is
  ≥ 31 bars old or from an earlier session lose the same as fires whose low is < 4 bars old (−0.27 vs −0.26R per
  fire, n 301 vs 107, p 0.47); the oldest lows are stopped within 2 sessions 55% of the time vs 77% for the youngest,
  yet end no better.
- **H3 — the trigger FAILS.** Fires at 10:00 or later do WORSE than earlier fires on the lane's arm (−0.36 vs −0.12R
  per fire, n 343 vs 199, p 0.11 against the predicted direction). Reclaim bars on above-average volume lose less
  (−0.22 vs −0.57R per fire, top vs bottom tercile, n 128 vs 127) but at p 0.06 and with the held-out parts at 5-vs-4
  and 3-vs-6 fires, one agreeing and one contradicting — a lean, not a result. Reclaim volume ≥ the undercut bar's
  volume: −0.01 vs −0.27R (n 64 vs 263, p 0.18), gone after dropping two names.
- **H4 — the era split has TWO different answers.** (a) The wider-stop low-reclaim edge in ERA A is a COMPOSITION
  effect: on the 261 ERA A campaigns today's rules would ADMIT (136), the 1×ADR low reclaim reads −0.12R per fire
  (n 102) and is negative in every alert month; the +32R lived on the names today's rules REJECT (+0.35R, n 64) or
  cannot decide (+0.61R, n 36) — 10 of its 11 campaigns that made ≥ 3R are rejected or undecided under today's rules
  (admit vs reject p 0.049). Admitted-only (−0.12 ± 0.09) is indistinguishable from ERA B (−0.34 ± 0.18). (b) The
  lane's OWN arm is the opposite: admitted −0.32 ≈ ERA A overall −0.27, both far from ERA B's −0.93 (n 30) — its
  ERA B collapse is tape/time, not the rule. ⚠ Correction to the brief: the 545p3 "142 admit" includes 6 ERA B
  campaigns (08-27/28); on ERA A it is 136 admit / 81 reject / 44 undecided.
- **H5 — selection CAN'T TELL.** Extension at the EP close is the only feature with an in-sample signal (least-extended
  third: 19.5% run ≥ 5 ADR within 15 sessions vs 9.1% for the most-extended third, n 231, p 0.03; 5 of the 7 big
  winners sit in the least-extended third) — but the two held-out parts disagree (11 campaigns against, 14 for), and
  the features were chosen on these same alerts. Tightness moves the WRONG way in-sample (p 0.02). Nothing else moves.
  His 4 labelled EPs reach 4.9 (TEAM), 4.4 (HTFL), 2.7 (PLTR) and −1.3 (MRNA) ADR within 15 sessions — none clears
  the 5-ADR "runner" label, which is another reason that label is not his.
- **H12 (his) — a 620 turn near ANY pivot, stop under the turn's session low, FAILS as mechanised.** It fires on 267 of
  277 campaigns (median stop 1.86% wide) and loses −0.45R per campaign MORE than the lane's first fire on the same
  campaigns (n 242, p 0.003; worst −8.5R vs −2.4R; big losses 11 vs 3); with a 1×ADR stop it is flat (−0.01). It
  keeps 1 of the 6 big winners it fired on (the lane: 2). **TEAM hand-walk: on day 0 (08-07) the 11:40 ET cross at
  $143.68 QUALIFIES under the lane's own frozen guards and sits 0.23 ADR above the day-low-so-far pivot ($141.51 =
  his stop); entered there with that stop it marks +21.2R at session 20 (his entry $144.39 came 25 min later, same
  stop) — but day 0 is outside the lane by his 08-30 ruling and inside the live R3 same-day re-entry ban.** On
  session 1 (08-10) the first qualifying cross is 10:50 at $148.06 — exactly the lane's own 620 fire (+9.3R).
- **H13 (his) — the close-based stop FAILS at every threshold.** Exit on a daily close below the lane's stop: −0.55R
  per fire worse than the touch stop (n 573), worst single loss −44R (a 0.09%-wide stop held through a 20% slide; ex
  the sub-0.5% stops: −0.46R per fire, worst −38R), 295 of 573 fires lose beyond −1.5R vs 20 under the touch stop.
  The 0.5-ADR / 1.0-ADR / 3×-volume overrides shave it to −0.93 / −0.55 / −0.71R. Under a 10-day-SMA level (the
  level he actually names): −0.15R per fire vs touching the SMA (n 459, p 0.16), worst −17.9R vs −12.3R, 44 vs 6
  losses beyond −1.5R; held-out negative on both parts. A close stop saves nothing on the mean and multiplies the
  slice-day loss.

**Missing data that could have flipped a verdict: none of the eight.** ERA B's 23 lane-recorded fires (no minute
bars) blind H1c/H3/H12 there and the H13 volume override on 67–77 sessions — the affected reads were "can't tell" or
already failing on discovery; no verdict rests on them.

## Method and population

**Gate (`hyp_gate_out.txt`), reproduced from the files the probe loads before any test:** ERA A (alert_date < 08-22)
261 campaigns / 243 names / HIGH 184 · MODERATE 66 · other 11, median prior close $26.72; ERA B 16 / 16 / 14 · 2,
median $114.89; ALL 277 / 256; `fires.tsv` 632 first-attempt fires (ERA A 595, ERA B 37, of which 23 lane-recorded
on the 10 ERA B campaigns with no stored minutes); TEAM 08-07, MRNA 08-19, PLTR 08-04, HTFL 08-14 present; the era-C
verdict (`campaigns_era_c.tsv`) joins all 261 ERA A campaigns: **136 admit / 81 reject / 44 undecided**;
`rank_shadow.tsv` keys == the 277. GATE PASSED.

**Anchors (`hyp_anchor_out.txt`), all 0 drift:** (A) the 09-01 walker at the 09-25 horizon on the rerun's loaders
reproduces the 609 replayed rows of `fires.tsv` on (rung, fire date, fire minute, entry, stop) — 609 of 609; its own
6 fires on the 10 uncovered ERA B campaigns were replaced by the lane's recorded rows in the rerun, as pre-registered.
(B) the lane's `compute_settlement` at the lane's own stop reproduces `reentry_rows.tsv` attempt 1 on both arms —
1,264 of 1,264 (status, outcome, gap-charged R). (C) this probe's H13 walker in touch mode reproduces the same 1,264
(one label difference accepted: `reentry` calls a trail exit inside a sub-20-session window "marked" because its M-none
arm was still open — SEI 09-08 — same outcome, same R). (D) the volume-carrying 5-minute aggregator equals the lane's
`to_rth_5min` on o/h/l/c/m for all 5,106 sessions. (E) H2's control walker against the rerun's §A: DISC 197 fires at 28.4% +
HELD-OUT A 4 fires at 0% = 201 ERA A low-reclaim fires at 27.9% — the rerun's 27.9% exactly; controls 3,614 sessions
at 21.8% vs the rerun's 3,599 at 21.7% (15 sessions apart on the campaign-inclusion rule; the gap is +6.1 either way).

**Split, as loaded:** DISCOVERY = ERA A alerts ≤ 08-14: 250 campaigns / 573 fires. HELD-OUT A = ERA A alerts
08-15..08-21: 11 campaigns / 22 fires — one calendar week (AMLX ARGX BULL CBRS MRNA MRVL RARE SCSC TEM TWST UUUU).
ERA B = 16 / 37. A held-out part with fewer than 8 readable fires reads "can't tell".

**Draws and noise band (declared before running):** 35 draws — H2 4 · H1b 3 · H1c 3 · H3 3 · H4 2 · H5 10 · H12 2 ·
H13 8; 0.05 × 35 = 1.75 expected false clears → ≤ 2 clearing anywhere is noise, ≥ 5 on one mechanism is a family.
**Result: 3 clear, all H1b (one nested mechanism).**

**The bar on every draw:** predicted direction on DISCOVERY · survives dropping the best two names (by ticker) ·
week-block permutation p < 0.05 (2,000 draws, seed 327; paired differences sign-flip whole ISO weeks of the fire
date; group reads shuffle labels within weeks) · the fillable-entry version (next 5-minute bar's open + 5 bps on the
entry and on every exit fill) agrees in sign · same sign on BOTH held-out parts. The recorded 5-minute-close entry
is shown beside the fillable one, never instead. Primary measure = the per-fire DIFFERENCE against the lane's current
behaviour (its own stop + the trail arm) on the same fires, gap-through stops charged at the open, plus tail
retention (his 4 labelled EPs in the 277 and the rerun's 7 big-winner EPs: campaigns ending ≥ 3R on any first fire)
and the worst single loss. Instrument = the lane's own `compute_settlement` through `reentry.settle_attempt` for every
stop substitution (H1b, H1c, H12); the H13 rules use a walker anchored on the same rows in touch mode.

## H2 — is the reclaim patterns' entry edge a volatility-timing artefact?

+2-first / −1-first = share of non-abstaining walks resolved by session 10 with the +2 barrier (−1 barrier) hit
first; fires with ≥ 10 sessions after them vs every non-fire session of the same campaign windows entered at the
close; pess = stop first on a straddle. "Original" = ±pre-EP ADR$ (the rerun's §A); "scaled" = the trailing
3-session range Y over post-EP sessions max(1, s−2)..s, the same window for fires and controls.

| pattern | barriers | entry | DISC fires / controls | +2 first: fire vs control → gap (drop-2; p) | −1 first: fire vs control → gap (p) | HOA n / gap | ERA B n / gap |
|---|---|---|---:|---|---|---|---|
| low reclaim | original | recorded | 197 / 3,547 | 28.4% vs 21.7% → **+6.7** (+5.6; p 0.086) | 63.5% vs 65.3% → −1.8 (p 0.23) | 4 / can't tell | 11 / +1.8 |
| low reclaim | original | fillable | 197 / 3,547 | 27.4% vs 21.7% → +5.7 (+5.0; p 0.15) | 64.0% vs 65.3% → −1.3 | 4 | 5 / −5.4 |
| low reclaim | scaled | recorded | 197 / 3,547 | 20.3% vs 22.8% → **−2.4** (−3.2; p 0.18) | 53.3% vs 67.0% → **−13.7** (p 0.001) | 4 | 11 / +10.3 |
| low reclaim | scaled, fire range through the fire bar | recorded | 197 / 3,547 | 25.4% vs 22.8% → +2.6 (+1.9; p 0.29) | 57.4% vs 67.0% → −9.7 (p 0.014) | 4 | 5 / +3.1 |
| close reclaim | original | recorded | 135 / 2,413 | 27.4% vs 20.5% → **+6.9** (+6.1; p 0.067) | 66.7% vs 66.0% → +0.7 (p 0.58) | 6 / can't tell | 9 / −26.4 |
| close reclaim | scaled | recorded | 135 / 2,413 | 18.5% vs 21.4% → **−2.9** (−4.2; p 0.31) | 57.8% vs 66.4% → −8.7 (p 0.13) | 6 | 9 / −26.4 |
| close reclaim | scaled, through the fire bar | recorded | 135 / 2,413 | 27.4% vs 21.4% → +6.0 (+4.8; p 0.072) | 66.7% vs 66.4% → +0.2 | 6 | 5 / −37.5 |
| high break | original / scaled | recorded | 46 / 807 | +11.8 (p 0.32) / −1.7 | −2.5 / −25.8 (p 0.009) | 2 | 2 |
| 620 proximity | original / scaled | recorded | 195 / 3,502 | +2.1 (p 0.50) / −3.5 | +2.4 / −6.2 | 8 / +9.8 | 11 / −10.2 |

Yardstick per ADR: fire sessions 1.19 (low reclaim) / 1.38 (close reclaim) vs random sessions 0.94 / 0.96. Verdict per
pattern: **fails** (all four). The pre-registered artefact tell (−1-first gap ≥ half the +2 gap under fixed barriers)
is FALSE — so the +6 is not "fires are simply noisier"; it is "fires are measured on wide-range sessions with a
fixed yardstick", and it does not clear a week-clustered permutation on its own terms. Tail retention and worst
loss are not defined for a rate; the drop-2 names are ABVX/CRMD (low reclaim), ABCL/ALAB (close reclaim).

## H1b — a stop scaled to the stock's range AFTER the gap

R_post = mean high−low of the last ≤ 3 completed post-gap sessions known at the fire (the EP day is session 0; 334
of 632 fires have only that one session). Trail arm; vs the lane's own stop (median width 2.47%) and vs 1×ADR pre-EP.

| k | median width | DISC n | variant vs lane → diff (drop-2; p) | fillable diff (n) | HOA n / diff | ERA B n / diff | tail ≥ 3R: labelled / runners (lane) | worst (lane) | vs 1×ADR pre-EP: diff (p) | tail under 1×ADR |
|---|---:|---:|---|---|---|---|---|---|---|---|
| 0.5 | 4.97% | 573 | −0.09 vs −0.26 → **+0.17** (+64.2; 0.001) | +0.21 (572) | 22 / +0.48 | 29 / +0.53 | 1/3 · 4/7 (1 · 3) | −3.12 (−3.30) | **−0.06** (0.015) | 2/3 · 5/7 |
| 0.75 | 7.45% | 573 | −0.04 vs −0.26 → **+0.22** (+92.8; 0.000) | +0.26 (572) | 22 / +0.42 | 29 / +0.62 | 1/3 · 4/7 | −3.13 | −0.01 (0.32) | 2/3 · 5/7 |
| 1.0 | 9.94% | 573 | −0.05 vs −0.26 → **+0.21** (+90.3; 0.005) | +0.25 (572) | 22 / +0.42 | 29 / +0.74 | 0/3 · 3/7 | −2.75 | −0.02 (0.19) | 2/3 · 5/7 |

Verdict: **holds against the lane's own stop (3 nested draws) — and adds nothing over the pre-EP ADR stop.** Per
pattern on discovery the gain is on the low reclaim (+0.22 to +0.30R per fire, n 197) and the 620 rung (+0.33, n 195),
nil on the close reclaim and the high break. Ex the 60 lane stops under 0.5% wide the gain is +0.09 / +0.16 / +0.15R
(p 0.10 / 0.046 / 0.055). Losses beyond −1.5R: 11 / 7 / 8 vs the lane's 12.

## H1c — the age / testedness of the stop-defining low

| variant | DISC n | variant vs lane → diff (drop-2; p) | fillable diff | HOA n / diff | ERA B n / diff | tail labelled / runners (lane) | worst (lane) |
|---|---:|---|---|---|---|---|---|
| (c1) stop = first-30-min low, fires ≥ 10:00 (214 earlier fires excluded; 123 with that low at/above the entry) | 226 | −0.29 vs −0.18 → **−0.11** (−29.6; 0.26) | −0.14 | 8 / +0.01 | 8 / +0.29 | 1/2 · 0/3 (1 · 1) | −2.65 (−2.65) |
| (c1) stop = first-60-min low, fires ≥ 10:30 (280 excluded; 85 killed) | 198 | −0.18 vs −0.19 → +0.01 (−2.0; 0.33) | −0.02 | 10 / +0.01 | 6 / can't tell | 1/2 · 1/4 (1 · 1) | −2.86 |
| (c2) old low (≥ 31 bars or an earlier session, n 301) vs young (< 4 bars, n 107), lane's arm | 408 | −0.27 vs −0.26 → **−0.01** (−0.11; 0.47) | — | 11 vs 6 / +0.58 | 10 vs 3 / can't tell | — | — |

Stopped within 2 sessions: youngest tercile 77% (n 107), middle 68% (111), oldest 55% (109), earlier-session lows 71%
(192) — the older low IS tested less often, and the fires still end at the same R. Verdict: **fails** (all three).

## H3 — the trigger: time of day and the reclaim bar's volume

| read | DISC groups | lane's arm mean R | diff (drop-2; p) | at 1×ADR trail | HOA | ERA B |
|---|---|---|---|---|---|---|
| (a) 10:00+ vs before 10:00 | 343 vs 199 | −0.36 vs −0.12 | **−0.24** (−0.34; 0.11) | −0.01 vs −0.08 (+0.07) | 12 vs 8: −0.08 | 17 vs 11: −0.14 |
| (a) by bucket | 09:30 bar 106 · 09:35–09:59 93 · 10:00+ 343 | −0.20 · −0.04 · −0.36 | — | −0.11 · −0.05 · −0.01 | — | — |
| (b1) reclaim vol ≥ undercut bar's vol vs below | 64 vs 263 | −0.01 vs −0.27 | +0.26 (−0.00; 0.18) | — | 3 vs 10: can't tell | 0 vs 10 |
| (b2) reclaim vol / session mean: top (≥ 0.93×) vs bottom (< 0.54×) tercile | 128 vs 127 | −0.22 vs −0.57 | **+0.35** (+0.18; 0.059) | +0.10 vs −0.18 (+0.28; 0.060) | 5 vs 4: +0.95 | 3 vs 6: −0.77 |

117 of 590 minute fires are on the opening bar and have no earlier bar for (b2); the 23 lane-recorded fires carry no
volume. Verdict: **fails** (all three); (b2) is the one lean worth recording forward, once the lane carries bar volume
(gap G2 in the hypotheses doc).

## H4 — tape vs rule: today's admission verdict on the ERA A campaigns

| cell | ERA A admit (136 camp.) | ERA A reject (81) | ERA A undecided (44) | ERA A all | ERA B all | admit vs reject p | admitted-only by alert month |
|---|---|---|---|---|---|---|---|
| 1×ADR low reclaim, trail | n 102: **−0.12 ± 0.09**, 1 campaign ≥ 3R | n 64: +0.35 ± 0.23, 7 ≥ 3R | n 36: +0.61 ± 0.34, 3 ≥ 3R | n 202: +0.16 ± 0.11, 11 ≥ 3R | n 13: −0.34 ± 0.18, 0 | **0.049** | May −0.08 (23) · Jun −0.33 (18) · Jul −0.12 (24) · Aug −0.03 (37) |
| the lane's own cell (own stop, trail), all patterns | n 310: −0.32 ± 0.09 | n 182: −0.37 ± 0.10 | n 103: +0.07 ± 0.27 | n 595: −0.27 ± 0.07 | n 30: **−0.93 ± 0.10** | 0.52 | May −0.29 · Jun −0.62 · Jul −0.21 · Aug −0.28 |

The 10 of 11 ≥ 3R low-reclaim campaigns outside "admit": EFOR, BLSH, ELVN, KSS, AKTS, CBRL, MMYT (rejected); TE, BHVN,
KURA (undecided). Of the 7 big-winner EPs today's rules admit ARM and NRIX, reject EFOR and HQ, and cannot decide
ALOY, TE, VPG; they admit all 4 of his labelled EPs. Reading: the wider-stop edge is composition (rule), the lane's
own collapse in ERA B is tape/time. Held-out and tail legs do not apply to a group comparison.

## H5 — selection re-cut, stop-independent

Outcome = max high over sessions 1–15 above the EP close, in ADR$ (277 of 277 scored; 7 ERA B campaigns censored
under 15 sessions). 26 campaigns reach 5 ADR. Predicted direction from the hypotheses doc; Spearman rho.

| feature | DISC n / rho (p) | top vs bottom third: share ≥ 5 ADR | big winners in the predicted-good third | HOA n / rho | ERA B n / rho | verdict |
|---|---|---|---|---|---|---|
| ext_xadr_eod (less extended better) | 231 / **−0.109 (0.034)** | 19.5% vs 9.1% | 5 of 7 | 11 / +0.15 (against) | 14 / −0.29 (for) | can't tell — held-out split, in-sample |
| ext_xadr_pregap | 172 / +0.002 (0.44) | 15.8% vs 12.3% | 2 of 4 | 9 / +0.40 | 8 / −0.62 | can't tell |
| tightness_pct_eod (predicted −) | 250 / **+0.099 (0.017), wrong way** | 7.2% vs 10.8% | 1 of 7 | 11 / −0.22 | 16 / +0.06 | can't tell |
| composite_rank_eod (+) | 246 / −0.025 (0.35) | 8.5% vs 12.2% | 1 of 7 | 11 / +0.22 | 16 / −0.28 | can't tell |
| open_range_position (+) | 180 / +0.057 (0.13) | 8.3% vs 10.0% | 1 of 2 | 11 / −0.19 | 16 / −0.14 | can't tell |
| expct_scheduled | scheduled n 152: 9% run · unscheduled 62: 15% · unknown 36: 8% | | 3 · 3 · 1 | | | descriptive |
| expct_beat | beat n 60: 10% · no beat 190: 10% | | 2 · 5 | | | descriptive |
| catalyst_type | sales_acceleration 108: 9% · none 74: 9% · policy 16: 12% · theme 14: 7% | | 1 · 3 · 1 · 0 | | | descriptive |
| tier | HIGH 176: 11% · MODERATE 66: 8% · none 8: 0% | | 5 · 2 · 0 | | | descriptive |

## H12 (operator) — a 620 turn within 0.5×ADR of ANY pivot, stop under the turn's session low

Fixed pivot list: EP-day low, EP-day close, pre-EP base edge (20- and 60-session max high), completed post-EP swing
lows, rising SMA10 / SMA20. Fired on 267 of 277 campaigns (ERA A 259, B 8); 126 blind sessions on 9 campaigns; pivots
named on the fires: EP close 154, EP low 94, base20 51, SMA10 37, base60 35, swing low 23, SMA20 17; 154 of 267 fires
are within 0.5 ADR of the EP close (the lane's own rung); median stop 1.86% wide; 140 fires on session 1.

| comparison (same campaigns) | DISC n | variant vs lane → diff (drop-2; p) | fillable diff | HOA n / diff | ERA B n / diff | tail ≥ 3R labelled / runners (lane) | worst (lane) | losses < −1.5R (lane) |
|---|---:|---|---|---|---|---|---|---|
| turn-low stop, trail, vs the lane's FIRST fire (own stop, trail) | 242 | −0.53 vs −0.08 → **−0.45** (−118.3; 0.003) | −0.42 | 8 / +0.76 | 8 / −0.18 | 1/3 · 1/6 (1 · 2) | −8.50 (−2.43) | 11 (3) |
| turn-low stop, none arm | 242 | −0.70 vs −0.36 → −0.34 (−93.5; 0.011) | −0.30 | 8 / −0.33 | 8 / −0.31 | 1/3 · 1/6 | −8.50 | 14 (6) |
| same fires, 1×ADR stop, trail (descriptive) | 242 | −0.09 vs −0.08 → −0.01 (−19.9; 0.47) | +0.06 | 8 / +0.43 | 8 / −0.14 | 2/3 · 2/6 | −2.81 | 5 |
| vs the lane's BEST first fire, trail (descriptive) | 242 | −0.53 vs +0.43 → −0.96 (0.000) | — | 8 / −0.06 | 8 / −0.18 | | | |

Tail campaigns: TE +11.1R (lane +14.2), TEAM +9.3R (= the lane's own 620 fire; lane first +6.2), MRNA +9.8R on a
session-7 swing-low turn (the lane never fired on MRNA — one campaign, descriptive), ARM −0.3, HQ −0.7, ALOY / EFOR /
HTFL / NRIX / PLTR −1.0. Verdict: **fails** (both arms).

**TEAM hand-walk (`hyp_team_handwalk.txt`; ADR$ 9.41 → band $4.71, basing band $3.76):** day 0 (08-07) has no
warm-up bars on disk (08-05/06 absent), so MIN_CROSS_IDX = 12 is the binding guard. MACD(6,20)/signal at 11:10 /
11:15 / 11:40 / 12:05 = −1.86/−1.28, −1.72/−1.37, −1.54/−1.58, −0.89/−1.27 — identical to `620_chart.md`. Three
bullish crosses: 10:05 (index < 12, basing $9.86 > $3.76 → not qualified), **11:40 at $143.68 — index ok, MACD < 0,
basing $2.10, hook ok → QUALIFIED; nearest pivot = day-low-so-far $141.51 at 0.23 ADR; stop $141.51 (1.51% wide)**,
13:15 (MACD > 0). Entered at the 11:40 close with that stop: +21.15R recorded (fillable +20.59R), peak +25.3R, still
open at session 20. His entry $144.39 ~12:05 with the same stop is 25 minutes after the qualifying cross. Session 1
(08-10): crosses 09:50 (basing fails), **10:50 $148.06 qualified, 0.11 ADR from the EP close, stop $145.00 — the lane's
own 620 fire (+9.27R)**, 11:05 qualified, 11:30 / 13:45 / 15:30 not.

## H13 (operator) — close-based stops with a violence override

Per fire vs the TOUCH stop at the same level, in that level's R; M-none arm isolates the stop; trail beside.

| level | rule | arm | DISC n | variant vs touch → diff (drop-2; p) | fillable diff | worst (touch) | losses < −1.5R (touch) | HOA n / diff | ERA B n / diff | tail labelled / runners (touch) |
|---|---|---|---:|---|---|---|---|---|---|---|
| lane's stop | close | none | 573 | −1.05 vs −0.50 → **−0.55** (−609.9; 0.21) | −0.48 | −44.2 (−3.8) | 295 (20) | 22 / −1.06 | 30 / +3.77 (QCOM +183R alone; drop-2 −88) | 2/3 · 5/7 (1 · 3) |
| lane's stop | close + 0.5 ADR override | none | 573 | −1.43 vs −0.50 → −0.93 (−621.8; 0.011) | −0.77 | −32.9 | 312 | 22 / −1.30 | 30 / +2.32 | 2/3 · 5/7 |
| lane's stop | close + 1.0 ADR override | none | 573 | −1.05 vs −0.50 → −0.55 (0.21) | −0.48 | −44.2 | 299 | 22 / −1.14 | 30 / +3.82 | 2/3 · 5/7 |
| lane's stop | close + 3× volume override (blind 67 sessions) | none | 573 | −1.21 vs −0.50 → −0.71 (0.037) | −0.55 | −39.6 | 246 | 22 / −1.12 | 30 / +4.77 | 2/3 · 5/7 |
| lane's stop, ex stops < 0.5% wide | close / +0.5 / +1.0 / vol | none | 521 | −0.46 / −0.45 / −0.48 / −0.33 (p 0.08 / 0.04 / 0.07 / 0.11) | | −37.9 / −32.9 / −32.9 / −39.6 | 250 / 266 / 254 / 201 (19) | | | |
| lane's stop | close | trail (= vs the lane's current behaviour) | 573 | −0.48 vs −0.26 → −0.22 (−281; 0.29) | −0.20 | −44.2 (−3.3) | 179 (12) | 22 / −0.55 | 30 / −0.86 | 2/3 · 4/7 |
| SMA10 (126 inapplicable) | close | none | 459 | −0.16 vs −0.01 → **−0.15** (−131; 0.16) | −0.19 | −17.9 (−12.3) | 44 (6) | 18 / −0.34 | 29 / −0.71 | 0/3 · 2/6 (0 · 1) |
| SMA10 | close + 0.5 ADR | none | 459 | −0.07 vs −0.01 → −0.06 (0.35) | −0.09 | −17.0 | 37 | 18 / −0.12 | 29 / −0.25 | 0/3 · 2/6 |
| SMA10 | close + 1.0 ADR | none | 459 | −0.16 vs −0.01 → −0.15 (0.20) | −0.16 | −33.8 | 47 | 18 / −0.26 | 29 / −0.64 | 0/3 · 2/6 |
| SMA10 | close + 3× volume (blind 77) | none | 459 | −0.14 vs −0.01 → −0.13 (0.18) | −0.12 | −18.2 | 39 | 18 / −0.35 | 29 / −0.77 | 0/3 · 2/6 |
| SMA10 | close | trail | 459 | −0.08 vs −0.04 → −0.04 (0.38) | −0.09 | −17.9 | 29 (5) | 18 / −0.31 | 29 / −0.03 | 0/3 · 2/6 |

In the lane's R the SMA10 close rule reads −0.70 vs −0.36 for touching the SMA (−0.35R per fire; worst −70R). The
SMA10 R-unit has the same degeneracy as a razor stop when the entry sits a few cents above the SMA (that is the touch
baseline's own −12.3R worst) — which is why both units are shown. The close rules DO keep more winners (5 of 7 vs 3
under the touch stop at the lane's level) — and pay for each with hundreds of fires that lose 2–40R. Verdict:
**fails** (all 8 draws).

## What this does not answer

- **Whether a wider stop is right for the lane.** H1b confirms only that wider beats the razor stop (known); the
  choice of yardstick and width, and whether ERA B's 13-fire agreement is enough, are his (#616 reads it forward).
- **Why the wider-stop low-reclaim edge lived on names today's rules reject.** H4 shows the composition; whether
  the rules are wrong or those May names were a tape gift needs the paid catalyst re-grade (fork a) and his call.
- **Selection (H5).** In-sample by construction; the least-extended-third lean (19.5% vs 9.1%) is a candidate for a
  forward read, not a result. His 4 labelled EPs do not reach the 5-ADR / 15-session runner label — that label needs
  restating against his list before any selection test can use it.
- **The volume lean (H3 b2, p 0.06)** cannot be read forward until the lane records bar volume (G2).
- **The day-0 TEAM entry (H12 hand-walk).** The 11:40 turn qualifies and would have marked +21R, but it is one trade,
  on the EP day, outside the lane by his 08-30 ruling; the H7 day-0 replay was not in this program.
- **H12 is ONE mechanisation of his idea, not the idea.** Untried: a band other than 0.5×ADR; the pivot list WITHOUT
  the EP close (154 of 267 fires were the lane's own rung in disguise); a completed-base requirement in place of the
  8-bucket basing guard; a stop under the pivot rather than the session low; the day-0 arm.
- **ERA B** is 16 campaigns / 37 fires, 23 with no minute bars; it confirmed direction on H1b and contradicted or
  could not read everything else. HELD-OUT A is one week (11 campaigns).
- **Sizing.** Every R here is at equal risk per fire; the razor stops that dominate H13's lane-level numbers would
  be capped at 20% notional live (H10 in the hypotheses doc).

## THE LINE

Nothing live was touched: no strategy, stop, target, size, safeguard, trade state, table, toggle or deploy. Prod was
reached by exactly four read-only queries: a row count on `mi_alert_rank_shadow` (289 rows / 286 campaigns), two
`information_schema` column lookups (`mi_alert_rank_shadow`, `mi_ep_alerts`), and the one data SELECT captured to
`rank_shadow.tsv` (`rank_shadow.sql`, pulled 2026-09-27T16:53:41Z). Adopting
any entry, stop or exit tested here — the post-gap stop, a 620-near-pivot rung, a close-based stop, a volume gate —
is the operator's call under CHANGE_PROCESS (SSoT first, sign-off, backtest, verify-live). The TEAM day-0 entry (H12
hand-walk) sits inside the live **R3 same-day re-entry ban** (shipped 05-17); any H7-style day-0 re-entry would
reverse that rule and is a CHANGE_PROCESS reversal for him alone.

---
*Population: the 277 live-source `mi_ep_alerts` campaigns 2026-05-01 → 09-11 (ERA A 261 / ERA B 16), 632 first-attempt
fires; gate and four anchors at 0 drift. Related: `327_hypotheses_2026-09-27.md`, `327_reentry_stop_study_2026-09-27.md`,
`327_real_ep_rerun_2026-09-26.md`, `545p3_day1_stop_target_runner_sweep_2026-09-03.md`, `docs/methodology/620_chart.md`,
`docs/methodology/operator_labelled_eps.md`; PLAN #327, #616.*
