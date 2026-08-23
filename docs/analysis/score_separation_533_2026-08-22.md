# #533 — Separation: where an ordinary gapper's score comes from, and what pushing it down buys (2026-08-22)

**MEASUREMENT AND PRICING ONLY. The gap ladder, the conviction floors and every weight in
`ep_rubric.SCORE_WEIGHTS` are detection criteria = the operator's sole authority (THE LINE).
Nothing is changed, committed or deployed. $0 — no prod pull at all: every number is computed
locally from existing captures.**

## The question

The operator's frame: *"there's two parts to this coin, real EP to score higher and non real EP
to score lower, the combo will make lowering the bar, or setting the bar anywhere more
meaningful in terms of filtering properly."* Every signed change so far (liquidity tiers,
deleting neglect + prior-momentum, the catalyst lattice) lifts or protects real EPs. This study
measures the other side: **what makes an ordinary big gapper score HIGH, and what removing that
buys in separation** — with the prime suspect the four `conviction_floor` branches that force a
raw 80/80/70/60 on gap + catalyst alone.

## Data

- **Populations**: the 26-member #577 fixture (25 gradeable; QURE is M&A-filtered) vs the
  1,100-row tier-A gap corpus (03-01→08-21; 868 controls at today's 9.0% admission floor for
  per-day pricing). Reused captures: `533_q2.psv` (corpus + point-in-time components),
  `533b_scan.psv` (700 graded ticker-days + the live alert record), `thr_prod.psv` (regime
  series). `mi_ep_missed_outcomes` is used **nowhere** (its stale-row bug is moot here).
- **Rubric = committed HEAD** (`ep_rubric.SCORE_WEIGHTS`): gap 25/20/15/10 at 20/15/10/8%,
  ADV$-liquidity 15/12/10/7, catalyst 25/15/0, theme +10, floors 80/80/70/60, ×1.2 Bull.
  The V0 baseline reproduces the threshold study's published numbers exactly (1.81 HIGH/day,
  6/13/18 members reachable at bars today/60/50) — same harness, extended.
- **Grades**: controls carry the lattice grade mix (routine 40.6% / strong 52.9% / gc 6.5%);
  members measured at the same mix AND per grade scenario. Same-mix is GENEROUS to the current
  system — the 7 graded members actually skew routine. Controls get 0 theme points (membership
  not knowable point-in-time; understates control scores equally across variants).
- ⚠ **In-sample, said once**: the label was discovered on this data, 13 of 26 fall on one
  session, 7 of 26 ever graded, and the label's R-geometry favours liquid quiet names. Every
  candidate shape below is round and pre-declared (flat-10 = the modal member's gap credit;
  branch cuts are the existing ones), not fitted. Out-of-sample = the post-07-16 label window
  (~mid-October) + the live lattice record.

## Result 1 — where an ordinary HIGH's points actually come from: 71% is gap, 41% is the floor

Decomposing the raw score of every control that clears today's bar (blended, HEAD rubric):

| component | avg points | share of an ordinary HIGH's raw 76 |
|---|---|---|
| **conviction-floor lift** | **31.3** | **41%** |
| gap ladder | 22.8 | 30% |
| catalyst | 16.8 | 22% |
| liquidity | 5.1 | 7% |

- **Gap-linked total (ladder + floor, both keyed on gap size): 71 points in 100.**
- **93% of ordinary HIGHs need the floor to clear their bar** — floors off, the modeled HIGH
  stream collapses from 1.81/day to 0.14/day at today's bars.
- Corroboration from the live record: **55% of all 337 HIGH alerts ever sat in a floor cell**
  (gap+grade keying a branch) — lower than 93% because the OLD rubric had other point paths
  (neglect, RVOL) that are now deleted; under HEAD the floor carries more than ever. Same
  mechanism family as the known result: 57 HIGHs in 90d that the holistic judge graded `none`
  (`ep_profitability_program.md` §gate-1).

## Result 2 — the floors, priced: they fire 3–5× more often on ordinary gappers and lift them 5× harder

Branch geometry is the whole story: **only 3 of 25 members gap ≥15%** vs 43% of admissible
controls — so three of the four branches are structurally reserved for ordinary gappers.

| branch | binds on members (of graded pop) | binds on controls | avg lift when binding |
|---|---|---|---|
| 15%+ game_changer → 80 | 0.8% | 2.8% | +31 pts (controls) |
| 20%+ strong → 80 | 4.2% | **14.7%** | +41 |
| 15%+ strong → 70 | 2.1% | 8.0% | +33 |
| 10%+ game_changer → 60 | 1.3% | 2.6% | +14 |
| **any** | **8.4%, mean +2.1 pts** | **28.1%, mean +9.9 pts** | — |

Floors ON vs OFF, blended score distributions — **the floors act ONLY on the upper tail, and
they hand it to the controls**:

| | member p75 / p90 | control p75 / p90 | share of pop ≥65 (lowest HIGH bar) |
|---|---|---|---|
| floors OFF | 48 / 60 | 48 / 54 | members 5.5% / controls **2.0%** |
| floors ON | 48 / 66 | **72 / 96** | members 10.3% / controls **27.3%** |

- Without floors the region above every HIGH bar belongs to real EPs (5.5% vs 2.0% — the
  liquidity axis working). Floors flip it: controls 14×, members 2×. **The floors are the
  mechanism that builds an ordinary-gapper-only tail above every bar.** AUC (mix-blended):
  0.433 → 0.477 floors-off; @game_changer scenario 0.257 → 0.422.
- Live-record confirmation: 195 of 700 graded ticker-days (28%) sat in a floor cell —
  2.2/session, matching the model's 1.95/day.

## Result 3 — the gap ladder, same lens

Members' median gap is 9.9% (modal credit: 10 pts); controls' 12.0%+ — 28% of admissible
controls gap ≥20% and take the full 25. Flattening every admitted gap to 10 pts (admission
evidence, not ranking points — the shape the operator already leaned toward in "stop paying
for gap size"): mechanical AUC 0.514 → **0.745**; alone (floors untouched) the blended AUC
moves only 0.433 → 0.498 **because the floors still pay gap size through the back door** —
the 72/96 control tail is floor-built and survives any ladder change. The two are one axis:
points AND floors are both gap payment.

## Result 4 — combined separation: the package flips the board

Candidate = **flat gap 10 + delete floor branches 1–3 + keep 10%+gc→60** ("V4"; V5 = also
delete the last branch). AUC three ways (mix-blended; within-day = each member vs its own
day's board — the honest slice given 13 members on one session):

| variant | AUC all | ex-04-08 | winners-excl | **within-day** | controls ≥ member-median | member board pctile (mech) |
|---|---|---|---|---|---|---|
| V0 HEAD | 0.433 | 0.521 | 0.435 | **0.537** | 62% | 57th |
| floors trimmed only (keep b4) | 0.474 | 0.586 | 0.475 | 0.572 | 61% | 57th |
| gap flattened only | 0.498 | 0.553 | 0.500 | 0.589 | 51% | 79th |
| **V4 both** | **0.599** | 0.658 | 0.596 | **0.649** | **38%** | **79th** |
| V5 both + last floor gone | 0.607 | 0.670 | 0.604 | 0.658 | 38% | 79th |

- Each half alone buys ~+0.04; **together +0.11–0.17** — same interaction as the redesign
  package: the tail has two builders and both must go.
- V5 adds +0.01 over V4 but fails the guard case in Result 6 — not worth it.

## Result 5 — the bar table, re-priced under the improved separation

Per-day volume is the corpus proxy (V0 today = 1.81 modeled vs ~2.6 live; **deltas and shares
are the honest numbers, levels understate**). "Reachable" = clears the bar if the lattice
awards game_changer; **floor-alive** = also above the 9.0% admission floor (18 of 25 members;
7 are floor-dead at any score). @known = the grades actually assigned (6 members).

| change | separation (within-day AUC) | real EPs reachable @gc (floor-alive) | @strong | @known | ordinary HIGH/day | Δ alerts/mo |
|---|---|---|---|---|---|---|
| **today** (V0, bars 65/70/75/80) | 0.537 | 6 | 4 | 2 of 6 | 1.81 | — |
| bar-only move: V0 uniform 60 | 0.537 | 12 | 4 | 2 | 1.96 | +3 |
| bar-only move: V0 uniform 50 | 0.537 | 15 | 7 | 2 | 2.30 | +10 |
| **V4 bar 40 — matched volume** | **0.649** | **18 of 18** | 10 | **4 of 6** | **1.78** | **−1** |
| V4 bar 45 | 0.649 | 17 | 6 | 2 | 0.81 | −21 (−55%) |
| V4 bar 50 | 0.649 | 15 | 4 | 2 | 0.42 | −29 (−77%) |
| V4 bar 60 | 0.649 | 12 | 2 | 2 | 0.39 | −30 (−80%) |

- **The headline the operator asked for**: at today's alert volume, the re-shaped score makes
  **every floor-alive real EP reachable (18/18 vs 6)** and drops the ordinary share of the
  HIGH stream from 97% to 90%; at bar 45 it holds 17 of 18 on **half** today's alerts.
- **The bar becomes meaningful at every level** — under V0, moving 65→50 buys +9 members at
  +10 alerts/mo and the ordinary share never leaves 94–97%; under V4 the same 10-point bar
  range trades 12↔18 members against 8↔38 alerts/mo with ordinary share 74–90%. That is the
  operator's "combo" made concrete.
- @known at V4 bar 40 = 4 of 6 (MRNA, INTC, UMC 05-06, **ARM — a routine-graded real EP
  becomes visible on liquidity alone**). The catalyst wall still holds QCOM/AMD; no score
  change fixes the grader.
- Knife edges, stated: INTC @known sits at exactly 60.0, the liquid @gc class at exactly 50.0
  and 60.0 — bars at those round points move whole classes inclusively; that quantisation IS
  the rubric's structure.

## Result 6 — ⚠ the floors are not all junk: branch 4 is load-bearing (trap 5)

- **Provenance**: branches 1–3 were built 2026-03-20 (`77179405`, "a 20%+ game-changer gap
  should score ≥70 on its own"; `63eda07a` added 20%+strong→80) — **calibrated on the big
  gapper by design**, five months before any real-EP label existed. Branch 4 (10%+gc→60) is
  different: added 04-14 (`ed3e514e`) as the **scoring-dead-zone fix for a real EP** — BE at
  13.4% was invisible below MODERATE, and BE is in the fixture.
- **The MRNA guard case**: at MRNA's operational 10.04% gap read @gc, V4 scores 72 (floor 60
  ×1.2) → HIGH at today's Bull 65. Under V5 (all floors gone) MRNA scores 56.4 — **no alert
  at bar 65 or 60, at EITHER gap read** (even 33% gap: flat 10 + liq 15 + cat 25 = 50 ×1.2).
  V5's +0.008 AUC is not worth re-killing the reference EP; **keep branch 4**.
- Other dependents checked: the `conviction_floor_eligible` telemetry + the
  `conviction_floor_extension` data-gated review watch the gap[10,15)+**strong** cell — the
  08-03 analysis already ruled DO-NOT-LIFT (21% hit rate vs a 35% bar), consistent with, not
  broken by, trimming branches 1–3. The Wave-C boost shadow calls `_score_ep` directly —
  unaffected. Stage-2 baseline tests pin current outputs and would be regenerated with any
  signed change.

## ⚠ What this study does NOT answer

- **Whether separation converts to R** — every number is rank/reachability against an
  outcome-conditioned label; no P&L claimed.
- **The grade wall** — @gc columns are contingent on the lattice awarding the top grade;
  @known stays 2–4 of 6 under every variant. The grader, not the bar or the shape, decides
  whether reachability pays.
- **The 7 floor-dead members** (gap <9.0%) and QURE (M&A filter) — out of any score's reach;
  separately-ruled criteria.
- **Bar 40's absolute volume** — the corpus proxy omits $5–10 names and sub-$50M days; the
  matched-volume claim rests on the RELATIVE anchor (V4@40 ≈ V0@today within 2%).

## The one number that decides it

**71% of an ordinary gapper's HIGH score is payment for gap size — 30 points from the ladder,
41 from the conviction floors — and 93% of ordinary HIGHs need the floor to clear. Stopping
that payment (gap flat at 10, floor branches 1–3 deleted, the 10%+game_changer→60 rescue
kept) flips the top of the distribution from ordinary-only to real-EP-first: within-day AUC
0.537 → 0.649, controls above the member median 62% → 38%, and at today's exact alert volume
the reachable real EPs go from 6 to all 18 that survive admission.** One line to rule:
**keep the score's gap payment as-is · adopt flat-10 + trim floors to branch 4 (then choose
bar 40 / 45 / 50 from the table above).**

## Files

- This doc: `docs/analysis/score_separation_533_2026-08-22.md`
- Analysis (session scratchpad `/tmp/sep533_scratch/`, $0, no prod pull):
  `sep_analyze{,2,3,4}.py`, `sep_out{,2,3,4}.txt`
- Reused captures: `533_q2.psv`, `533b_scan.psv` (prior scratchpad) · `thr_prod.psv`
  (`/tmp/ep_threshold_scratch/`)
- Anchors: `selection_layer_533_2026-08-22.md` · `score_redesign_proposal_533_2026-08-22.md` ·
  `ep_threshold_rederivation_2026-08-22.md` · `conviction_floor_extension_2026-08-03.md` ·
  `tests/fixtures/must_not_miss_eps.py` · method template `adv_floor_556_2026-08-20.md`
