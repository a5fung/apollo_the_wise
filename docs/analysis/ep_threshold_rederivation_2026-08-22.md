# EP threshold re-derivation — what each HIGH bar buys under the score we now have (2026-08-22)

**MEASUREMENT AND PRICING ONLY. The HIGH bar (`regime.py` 65/70/75/80), the 50 cutline
(`ep_detector.py:4235`) and the Bull ×1.2 multiplier (`ep_detector.py:2516`) are detection
criteria = the operator's sole authority (THE LINE). Nothing is changed, committed or
deployed. $0 — one read-only prod pull (regime series + member-day themes); everything else
reuses existing captures.**

## The question

The score changed twice today (liquidity tiers in, neglect + prior-momentum deleted,
catalyst lattice live) but the bars it is measured against did not: HIGH = 65/70/75/80 by
regime and MODERATE ≥ 50 were set against a score containing three components that are now
gone. Stage 0 proved the arithmetic: on 2026-04-08 (Correcting, bar 75) five real EPs got a
grading shot and their ceiling with a PERFECT catalyst grade was 50–65. This study re-derives
both thresholds against the score as committed at HEAD, per regime, and prices every
candidate bar in alerts per day.

## The headline — what a bar move buys

- **Today's Correcting bar (75) sits 10 points above the CEILING of a real EP.** The best
  score any of the 13 Correcting-day real EPs can reach with a perfect catalyst grade is 65
  (SNDK). Every alert that does clear 75 in Correcting is an ordinary gapper (100% share).
  Same shape in Crisis (bar 80, member ceiling 60).
- **A uniform bar of 60 makes 13 of 25 gradeable real EPs reachable (vs 6 today) for about
  three extra alerts a month system-wide** — because the 55–60 and 65–70 score bands are
  structurally EMPTY of ordinary gappers (the conviction floors quantise scores), a 60 bar
  admits the "gap ≥10% + game_changer" floor class at almost no junk cost.
- **A uniform bar of 50 makes 18 of 25 reachable for about ten extra alerts a month** — it
  additionally admits the liquid 9–10%-gap class (MU, BE at exactly 50.0 with a top grade).
- **The bar is NOT the whole fix and the numbers say exactly where it stops** (Result 5):
  the MEDIAN real EP (9.9% gap, $334M ADV$) tops out at raw 47 with a perfect grade — below
  the 50 cutline itself outside Bull. And a routine-graded real EP dies at every bar ≥50
  under every policy (ARM 48, AMD 36, QCOM 30). The bar buys an option that only pays when
  the lattice grader delivers the top grade — which is what it did for MRNA.

## Data, basis, and the one in-sample statement

- **Rubric = the committed code, verified line-by-line at HEAD**: gap 25/20/15/10/0 (at
  20/15/10/8%), liquidity ADV$-tiers 15/12/10/7/0 (at $500/250/100/50M, `adv × prev_close`),
  catalyst 25/15/0, theme +10, conviction floors (15+gc→80, 20+strong→80, 15+strong→70,
  10+gc→60), × regime multiplier (Bull 1.2 else 1.0). HIGH ≥ `ep_threshold` (Bull 65 /
  Choppy 70 / Correcting 75 / Crisis 80), MODERATE ≥ 50 post-multiplier. The catalyst grade
  reaching the score is now the **lattice verdict** (flip commit `2776e512`, default ON).
- **Populations**: the 26-member #577 fixture vs the 1,100-row tier-A gap corpus
  (03-01→08-21, close ≥$10, day $vol ≥$50M, open gap ≥8%; `533_q2.psv`, reused). Alert
  pricing filters controls to gap ≥9.0 (today's admission floor): 868 control rows over
  125 trading days (Bull 78 / Choppy 17 / Correcting 16 / Crisis 14, from `mi_market_regime`,
  pulled once).
- **Grade treatment**: members scored three ways — at their known grades (7 graded; MRNA
  = game_changer under the live lattice, INTC = strong with the gap≥20 floor), and as
  @strong / @game_changer scenarios. Controls priced by grade-mix blend using the **lattice
  mix** (routine 40.6% / strong 52.9% / game_changer 6.5% — the 700-row graded base rates
  pushed through the lattice's measured transition rates), with the raw-LLM mix as
  sensitivity (direction identical, levels ±5%).
- **Levels vs deltas**: the modeled baseline is 1.81 HIGH/day vs the live ~2.6/day — the
  corpus omits $5–10 close prices and sub-$50M-day names, and excludes the earnings-day
  MODERATE→HIGH override, the ×1.2 grade-agreement boost, and the float/vol-conviction
  points (≤10, not measurable point-in-time). Absolute levels understate; **the per-bar
  DELTAS are the priced quantity.**
- ⚠ **In-sample, said once**: the liquidity axis was discovered on these same 26 labels, 13
  of 26 fall on one session, only 7 were ever graded, and `mi_ep_missed_outcomes` outcome
  columns are not used anywhere (stale-row bug — presence evidence only). Every bar priced
  here is therefore chosen ROUND, not fitted; the honest out-of-sample judge is the
  post-07-16 label window (~mid-October) and the live lattice record.

## Result 1 — score distributions: the two populations sit on top of each other until the grade separates them

| population (post-multiplier) | p10 | p25 | med | p75 | p90 |
|---|---|---|---|---|---|
| members, mechanical+routine | 20 | 20 | 26 | 32 | 44 |
| controls, mechanical+routine | 17 | 20 | 26 | 30 | 36 |
| members @strong | 35 | 35 | 42 | 54 | 84 |
| controls @strong | 32 | 38 | 48 | 84 | 96 |
| members @game_changer | 45 | 45 | 60 | 72 | 96 |
| controls @game_changer | 45 | 54 | 72 | 96 | 96 |

- The mechanical score alone separates weakly (AUC 0.57 — the retained gap ladder still
  pays controls' bigger gaps; the liquidity tiers pull the other way). **At any given grade,
  controls out-score members** — the floors reward the big gaps controls have. So the bar
  cannot buy precision; what it CAN buy is reachability: today's non-Bull bars sit above the
  member distribution entirely, at every grade.
- The member score sits in narrow quantised bands: @game_changer the mass is at 45 / 50 /
  60 / 72 — which is why bar placement AT 50 or 60 moves whole classes at once (knife-edge
  members at exactly 50.0 and 60.0 are flagged in Result 2).

## Result 2 — THE DECISION TABLE (per regime; lattice mix; alerts = HIGH/Telegram)

Per-regime detail — members counted only in their own day's regime; `@known` = the grades
actually assigned; `@gc` = if the lattice awarded the top grade (the option the bar buys):

| regime (days) | bar | real EPs @known | @strong | @gc | HIGH/day | Δ vs today /mo | ordinary share (@gc, lower bound) |
|---|---|---|---|---|---|---|---|
| **Bull** (78) | **65 ← today** | 2 | 5 | 7 | 2.28 | — | 96% |
| | 60 | 2 | 5 | 9 | 2.30 | +0.4 | 95% |
| | 55 | 2 | 5 | 9 | 2.31 | +0.6 | 95% |
| | 50 | 2 | 6 | 10¹ | 2.83 | +11.6 | 96% |
| **Choppy** (17) | **70 ← today** | 0² | 0 | 0 | 1.15 | — | 100% |
| | 60 | 0 | 0 | 0 | 1.24 | +1.9 | 100% |
| **Correcting** (16) | **75 ← today** | 0 | 0 | **0 — unreachable** | 1.13 | — | 100% |
| | 65 | 0 | 0 | 1 | 1.56 | +9.0 | 96% |
| | 60 | 0 | 0 | 3 (SNDK, APLD, QBTS) | 1.88 | +15.8 | 91% |
| | 50 | 0 | 1 | 7³ (+BE, MU, IREN³, NBIS³) | 1.93 | +16.8 | 81% |
| **Crisis** (14) | **80 ← today** | 0 | 0 | **0 — unreachable** | 0.75 | — | 100% |
| | 60 | 0 | 0 | 2 (MRVL, AEHR) | 1.06 | +6.5 | 88% |
| | 50 | 0 | 1 | 2 | 1.07 | +6.7 | 88% |

Δ/mo here = 21 trading days OF THAT REGIME (the cost on the mornings that regime is in
force); the system-wide table below is the calendar-weighted aggregate.

¹ includes QURE, which the M&A hard filter blocks regardless of bar → 9 policy-relevant.
² no member fell on a Choppy day; Choppy is priced for volume only.
³ IREN (8.3%) and NBIS (8.1%) sit below the 9.0% admission floor — a bar change alone
never reaches them (the floor is a separately-ruled criterion). So Correcting-50 buys 5
floor-alive names; QCOM (8.7%, Bull) is likewise floor-dead.

**System-wide, the four policies worth ruling on:**

| policy | HIGH/day | ≈/month | Δ/month | real EPs reachable @gc | @strong | @known |
|---|---|---|---|---|---|---|
| **today (65/70/75/80)** | 1.81 | 38 | — | 6 of 25 | 4 | 2 of 6 |
| uniform 65 | 1.89 | 40 | +2 | 7 | 4 | 2 |
| **uniform 60** | 1.96 | 41 | **+3** | **13** (12 floor-alive) | 4 | 2 |
| 65 Bull / 60 elsewhere | 1.95 | 41 | +3 | 11 | 4 | 2 |
| **uniform 50** | 2.30 | 48 | **+10** | **18** (15 floor-alive) | 7 | 2 |

- **Why 60 is nearly free**: the conviction floors quantise control scores. In Correcting
  the 55–60 and 65–70 bands hold literally ZERO blended controls; the 60–65 band holds
  0.33/day (the floor-60 class) and 50–55 just 0.04/day. A bar of 60 pays only the floor-60
  class; 50 costs almost nothing more IN CORRECTING (+0.05/day) — the big cost of 50 is in
  Bull (+0.55/day, effective raw bar 41.7 after the multiplier).
- **Knife edges, stated**: the liquid 9–10% class scores exactly 50.0 @gc and the ≥10%
  floor class exactly 60.0 — members clear those bars inclusively. A one-point rubric drift
  moves whole classes across; round bars AT the quantisation points are still the honest
  choice because the quantisation IS the rubric's structure.
- **What no bar buys**: the routine-graded (ARM 48 / AMD 36 / QCOM 30 die at any bar ≥50),
  QURE (M&A filter), and the 7 members below the 9% admission floor. The @known column is 2
  of 6 under EVERY policy — the grade wall from the catalyst study is unchanged; the bar
  decision buys the option, the lattice exercises it.

## Result 3 — the 50 cutline: 45 is a dead zone; 40 is the visibility option

The cutline gates existence (score <50 = silent skip; 50–bar = morning briefing MODERATE).
No MODERATE has ever become a trade — this is visibility, not entries.

| cutline | Correcting: briefing/day | members visible @strong (of 13) | Bull: briefing/day | notes |
|---|---|---|---|---|
| **50 ← today** | 0.80 | 1 (SNDK) | 0.55 | strong-graded Correcting real EPs are invisible even in the briefing |
| 45 | 1.62 | 1 | 1.09 | **dead zone** — member @strong mass sits at 35–42; pays volume, buys ~nothing (ARM @routine 48 becomes visible in Bull) |
| 40 | 2.98 | 7 | 1.88 | the liquid class scores exactly 40.0 @strong; ~+2/day briefing rows on Correcting days |

- Keep 50 for noise discipline, or take 40 to make the strong-graded liquid class visible in
  the briefing on the mornings that matter; 45 is strictly dominated.

## Result 4 — the ×1.2 Bull multiplier: unsourced, redundant with the bar, and the double penalty is real arithmetic

- **Unsourced**: `regime_multiplier = 1.2 if Bull else 1.0` entered in the original POC
  commit (`cb289116`) and has never been re-derived against anything.
- **It is a second bar knob wearing a disguise.** Post-multiplier bars mean the REAL
  raw-score bars are: Bull 65/1.2 = **54.2**, Choppy 70, Correcting 75, Crisis 80 — a
  26-point selectivity spread where the nominal table reads 15. Same for the cutline: a
  strong-graded real EP needs raw 41.7 to exist in Bull, raw 50 anywhere else.
- **The double penalty points against the label**: 16 of 26 real EPs (62%) fell on non-Bull
  days vs 33% of ordinary gap-day rows — exactly where the effective bar is 70–80 and no
  multiplier helps. Honesty: that overrepresentation is carried by the one April session
  (ex-04-08 it is 3 of 13); n forbids a strong data claim either way.
- **What is defensible to say**: as a MECHANISM the multiplier does nothing a per-regime bar
  cannot do (Bull ×1.2 + bar 65 ≡ ×1.0 + raw bar 54.2 — verified equivalent in replay:
  no-multiplier Bull at bar 55 reproduces today's member clears and volume within 0.03/day),
  while it silently rescales the cutline and every floor. One knob (the bar) expressing the
  regime policy would make the table above the ONLY selectivity surface. Whether to fold it
  is the operator's ruling; nothing here requires it.

## Result 5 — the modal real EP's ceiling: the bar is not the only fix

Ceilings under the current rubric with a PERFECT grade (game_changer), no theme, float >50M:

| shape | raw ceiling | Bull (bar 65) | Choppy (70) | Correcting (75) | Crisis (80) |
|---|---|---|---|---|---|
| **median member: 9.9% gap, $334M ADV$** | **47** | 56.4 — no alert | **47 — below the 50 cutline** | below cutline | below cutline |
| same but gap 10.0% (floor keys) | 60 | 72 → HIGH today | 60 | 60 | 60 |
| liquid 12% gapper | 60 | 72 → HIGH today | 60 | 60 | 60 |
| liquid 15% gapper | 80 | 96 | 80 | 80 | 80 |

- **The median real EP cannot alert ANYWHERE at ANY bar ≥50, even with a perfect grade** —
  outside Bull it cannot even reach the briefing. The 0.1pp between 9.9% and 10.0% gap is
  worth 13 final points (the gap≥10 floor key) — half the label sits on that knife edge.
- So: a 60 bar fixes the ≥10%-gap half of the class (ceiling 60–65 becomes reachable); the
  sub-10% half stays dead on the gap axis (points + floor key + admission floor), which is a
  RUBRIC question (the unadopted gap-flatten / floor-key shape), not a bar question — and a
  separate ruling.

## ⚠ What this study does NOT answer

- **Whether any bar converts to R** — every number is reachability/volume against an
  outcome-conditioned label; no P&L is claimed. The @gc columns are contingent on the
  lattice awarding the top grade to the 04-08 class (unscheduled group repricing — its
  MRNA promotion lane, plausible, unmeasured on April: no scan log existed).
- **Downstream gates** — cap admission, session-RVOL pace, ORB timing still cull; RVOL@T on
  04-08 is unknowable (SNDK 0.91×, MU 0.96× day-total — the pace gate could kill both
  before any bar does). Bar clears are grading-shot upper bounds, not entries.
- **Choppy** — zero members fell on Choppy days; its bar is priced for volume only.
- **The admission floor and the M&A filter** — separately-ruled criteria; 7 members + QURE
  are out of any bar's reach.

## The one number that decides it

**In a Correcting regime the bar is 75 and the ceiling of a perfectly-graded real EP is 65 —
the class the system exists to catch is arithmetically excluded, and every alert clearing 75
is an ordinary gapper. A uniform bar of 60 converts 13 of 25 gradeable real EPs from
impossible to reachable for ≈3 extra alerts a month; 50 buys 18 for ≈10.** One line to rule:
**keep 65/70/75/80 · uniform 60 · uniform 50 · (and separately: cutline 50 or 40 · fold the
×1.2 into the bar or keep it).**

## Files

- This doc: `docs/analysis/ep_threshold_rederivation_2026-08-22.md`
- New capture + analysis (session scratchpad `/tmp/ep_threshold_scratch/`, pulled once):
  `thr_prod.{sql,psv}` (regime series 03-01→08-22 + member-day themes), `thr_analyze.py`,
  `thr_out.txt`, `thr_policy.py`
- Reused captures (prior session scratchpad, not re-run): `533_q2.psv` (corpus),
  `533b_scan.psv` (700-row grade record), `stage0_prod.psv` (flood-day themes/regimes);
  lattice transitions from `scripts/probes/_533c_eval_out.txt` (committed)
- Anchors: `selection_layer_533_2026-08-22.md` · `score_redesign_proposal_533_2026-08-22.md` ·
  `shortlist_survival_stage0_2026-08-22.md` · `catalyst_tier_shadow_533_2026-08-22.md` ·
  `tests/fixtures/must_not_miss_eps.py` · method template `adv_floor_556_2026-08-20.md`
