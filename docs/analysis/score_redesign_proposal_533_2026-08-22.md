# #533 — Score redesign: a priced proposal, one component at a time (2026-08-22)

**PROPOSAL WITH EVIDENCE — NOTHING IS CHANGED.** Every item below is a detection criterion =
the operator's sole authority (THE LINE). `_score_ep`, its weights, thresholds, the catalyst
prompt and the cap's rank axis are all untouched. Any adoption goes through CHANGE_PROCESS +
operator signature. $0 — prod read-only psql, local computation, no LLM calls.

Builds directly on `selection_layer_533_2026-08-22.md` (the evidence base: composite AUC
0.37–0.41 on the 26 labelled real EPs; three components run backwards; dollar volume is the
only separating axis and is absent from the score). Principles cited by name
(`ep_profitability_program.md` § THE PRINCIPLES).

## The label, the yardstick, and what is in-sample

- **Label**: the 26-member #577 fixture (`tests/fixtures/must_not_miss_eps.py`) — MRNA
  (operator-named) + 25 evidence-named ≥10R winners. Outcome-conditioned by construction;
  13 of 26 fall on ONE session (2026-04-08).
- **Pool**: the same 1,100-row tier-A gap corpus as the evidence base (03-01→08-21, close
  ≥ $10, day $vol ≥ $50M, open gap ≥ 8%, ever-sectored): 26 members / 1,074 controls (61 of
  the controls are other tail winners; every key AUC re-run excluding them, unchanged).
- **Yardstick per component (the validation bar)**: AUC before → after (0.50 = coin flip;
  robustness shown three ways: winners-excluded controls, all-04-08-rows-excluded,
  within-day pairs only), members clearing the 50 bar, and alert-volume cost (controls
  clearing 50, per day, grade-mix-blended). Then the composite re-check — a component that
  helps alone can be drowned by the rest, so every change is measured alone AND in-package.
- ⚠ **What is in-sample, said once and up front**: the dollar-volume axis was *discovered on
  these same 26* in the evidence base, so every $vol AUC here is confirmatory on the same
  label, not held-out validation. No weight was fitted (all tier shapes are round numbers or
  the operator's own MRNA annotations, declared before measuring — the two alternative ADV$
  tier sets give identical AUC 0.70, so nothing hinges on a cut). The base-quietness
  definition and its 74d/101d thresholds were pre-registered in #569 **before** this label
  existed. The catalyst-point rebalance in Change 6 is exploratory and labelled so. **True
  out-of-sample is the post-07-16 label window (settles ~mid-October) + the rank-shadow
  record.** The label's R-geometry (EP-day-low stop, ADR-relative) mechanically favours
  liquid, quiet names — some of the liquidity separation may BE the label definition; that
  definition is the operator's own choice of what "real" means.

## New data this session (captured once, read many)

- `533b_bars.psv` — 207k daily H/L/C rows, mi_daily_closes, all 772 corpus tickers from
  2025-07-14 (the table's start). Needed because the local #569 bar cache starts 2025-11-15,
  which would have mechanically shortened March–May bases.
- `533b_scan.psv` — MRNA's full 08-19 tick record, the graded members' ticks, and the full
  grade record: 700 graded ticker-days (04-13→08-21, `mi_ep_scan_log`) + all 264 live alerts
  (`mi_ep_alerts`). Scripts: `533b_analyze{,2,3,4}.py`, same scratchpad.
- Base axis computed with the **pre-registered** `compute_base_duration_unanchored` from
  `scripts/probes/_569_pregap_base_v2.py` (unchanged constants; MRNA pipeline cross-check
  reproduced the probe's own 106d / 38.4% / 43-sessions-detached exactly).
- Feed lag cannot touch any number here — everything is official daily prints (evidence base,
  Result 9). What IS feed-conditional is which names ever REACHED grading live.

---

# THE SIX CHANGES, smallest first (P9 — the ranker is what buys loose admission)

## Change 1 — DELETE the prior-momentum penalty *(smallest: a pure deletion)*

- **Today**: 3-month gain ≥ +30% → −15 points, ≥ +50% → −25 ("best if stock has not rallied").
- **Evidence**: it fires on 31% of real EPs and 32% of controls — no discrimination
  (AUC 0.52). It is why ARM 05-06 scored **−12, dead last of 16 graded that day**, and it hit
  SNDK (−25), INTC (−15), QCOM, AMD. On MRNA's own 07:05 tick the score arithmetic is only
  consistent with the penalty firing on the reference EP too.
- **AUC before → after**: alone 0.37 → 0.33 (slightly WORSE alone — the penalty does kill
  some junk; in-package it is worth +0.04: package 0.59 without this deletion, 0.63 with).
  Members clearing 50: unchanged either way. Alert volume alone: 2.46 → 2.56/day (+2/month).
- **Recommendation (plain words)**: delete it, but as part of the package, not solo — solo it
  is a wash; once liquidity does the junk-killing (Change 4), the penalty's only remaining
  effect is punishing real EPs. P1 note: it currently costs no member an alert by itself.

## Change 2 — DELETE the mis-coded neglect component; do NOT wire in a base measure yet

- **Today** (`ep_detector.py` ~1248): "neglect" = price < 50%/70% of the 52-week high → 15/8
  pts — a **beaten-down detector**, and it is computed from the FMP profile's **current
  (post-gap) price**, so the gap itself erases the points it is meant to award. The
  operator's definition (`ep_reference_mrna_2026-08-19.md`) is the opposite chart: a long
  QUIET base — *"no major movements up or down, so the news moving it significantly is truly
  unexpected."* **MRNA, at its 52-week high, scores ZERO on the component named after his
  thesis**; 65% of real EPs score zero vs 52% of controls — as coded it pays junk MORE.
- **The replacement was built and measured, and it declines itself.** Per the card's
  instruction I checked `structure_model.md` first: its primitives are zones-CLEARED (supply
  ladder), explicitly complementary to duration×quietness — and #569 v2 already carries the
  pre-registered, MRNA-calibrated quietness measure (unanchored longest-quiet-window; finds
  his base: 106d at the 40% ceiling, 83d at his literal 27%, detached 43 sessions — recall
  intact, P1 clean). Measured against THIS label on the full corpus (26/26 members covered,
  1,059/1,074 controls):

  | quietness axis | member med | control med | AUC | ex-04-08 | within-day |
  |---|---|---|---|---|---|
  | base_days_unanchored | 88.5d | 105d | **0.42** | 0.55 | **0.31** |
  | base ≥ 74d (his smaller annotation) | 62% of members | 73% of controls | — | — | — |
  | base depth (smaller=quieter) | 0.39 | 0.39 | 0.58 | 0.64 | 0.62 |

  **Real EPs have SHORTER quiet bases than the ordinary gappers they compete with** — the
  third null-to-backwards read on this axis in a week (#569 v1 and v2 on tail winners, now
  the fixture label; three definitions, two labels). On non-flood days it decays to nothing
  (0.55) rather than backwards — the sharpest inversion is the 04-08 regime; stated, not
  smoothed.
- **AUC before → after**: neglect deleted alone 0.37 → 0.38; in-package the deletion is worth
  **+0.09** (0.54 → 0.63) because p52-neglect actively boosts beaten-down junk. Replacing it
  with base-points instead (V4) makes the package WORSE within-day (0.49 vs 0.68) and adds
  +0.6 alerts/day. Members clearing 50: see the bar table in Change 6 (deleting neglect
  removes 8–15 pts some members were getting; the bar decision absorbs this).
- **Recommendation**: delete the component; do not replace it from this evidence. The base
  thesis stays where P2 already routed it — the vision lane (#519) and the rank-shadow
  record, which keeps accruing the out-of-sample read at $0. The definition is not the
  problem (it finds his MRNA base); the corpus says the axis does not RANK.

## Change 3 — FLATTEN the gap ladder: admission evidence, not ranking points

- **Today**: 0/10/15/20/25 pts monotone in gap size — pays MORE for BIGGER gaps.
- **Evidence**: gap runs backwards on real EPs (AUC 0.34 raw, 0.35 as points; member median
  9.9% vs control 12.0%; 22 of 26 members gap < 15%). The operator's own structure model
  says it in words: *"raw gap % has no reference frame."* Gap/ADR is also backwards (0.41).
- **Proposal**: any admitted gap = flat 10 pts (the value the modal member gets today). Gap
  stays what it already is — an admission floor (operator-ruled 9.0%) and a conviction-floor
  key — it just stops out-ranking real EPs.
- **AUC before → after**: alone 0.37 → 0.41 (the only solo change that helps and reduces
  alert volume: 2.46 → 2.15/day); in-package worth +0.16 (0.47 without, 0.63 with).
  ⚠ NOT proposing inversion (paying small gaps): that would be fitting the sign to 26 points.
- **Recommendation**: flatten. Cheap, evidence-aligned, cuts alert volume, and it removes the
  mechanism by which a 25%-gapping junk name out-scores a 10%-gapping real EP before either
  is graded.

## Change 4 — DOLLAR LIQUIDITY into the score, replacing the RVOL tiers *(buys the most)*

- **Today**: volume points = RVOL tiers (2×/3×/5×/10× → 7–15 pts). Real EPs run QUIET:
  member median day-RVOL 1.8× = **zero points**; AUC 0.31 — the axis is backwards.
- **The replacement axis, measured** (the only separating axis found anywhere in two cards):

  | axis | member med | control med | AUC | excl-winners | ex-04-08 | within-day | p |
  |---|---|---|---|---|---|---|---|
  | **ex-ante ADV$ (20d, pre-gap)** | **$306M** | **$100M** | **0.72** | 0.72 | 0.71 | 0.69 | 0.006 |
  | day $vol (proxy for projected) | $830M | $346M | 0.65 | 0.65 | 0.68 | 0.70 | 0.010 |

  **The ex-ante version — plain trailing average dollar volume — separates BETTER than the
  day's own volume, needs no projection, and is already computed per scan row (`adv` in
  `mi_ep_scan_log`).** The live change is small. Tier shape (declared, round numbers,
  mirroring the existing 4-rung ladder): ≥$500M→15, ≥$250M→12, ≥$100M→10, ≥$50M→7. A second
  tier set (1B/500/250/100) gives the same package AUC 0.70 — nothing hinges on the cuts.
- **AUC before → after**: alone 0.37 → 0.47; **in-package it is the load-bearing change —
  package without it 0.33, with it 0.63–0.70** (0.70 with ADV$ tiers). Alert volume: the
  full package at the current 50 bar is 2.07/day vs today's 2.46 — **the package as a whole
  is roughly alert-neutral-to-negative** (−8/month) before any bar decision.
- **Slot ordering (P4 — the MRNA-vs-MRVL problem)**: median within-day board percentile of a
  real EP — current score **28th** (the score actively sinks them below random), gap rank
  40th, **package score 75th, raw $vol 78th**. On limited slots this ordering IS the product.
- **Honest caveats**: (i) in-sample by discovery (header); (ii) the label's R-geometry
  favours liquid names — part of this axis may be the label; (iii) it selects mega-caps on
  beta days — the grader downstream must still separate catalyst from sector sympathy
  (Change 6), and (iv) RVOL still guards the funnel as the 2.0× session gate — this change
  removes it only from RANKING; whether that separate gate should stay is not priced here.
- **Recommendation**: adopt ADV$ tiers in place of the RVOL tiers. This is the single change
  that buys the most, and the mechanically simplest form of it is the strongest one measured.

## Change 5 — the admission CAP ranked by dollar volume, not gap *(separate ruling, evidence reused)*

- Priced in full in the evidence base (Part A, Result 4): on the flood boards, a top-20 by
  $vol keeps **5 of the killed real EPs including every ≥15R one** (MU ranked 1st, SNDK 2nd,
  ARM/SNOW 3rd on their day's $vol board); $vol ranks are tick-stable where gap ranks whip.
  Raising N instead buys one grading shot (top-25 → SNOW) at +21 HIGHs/4mo.
- This is a criterion redesign with its own caveats (projected-$vol at 9:31 unmeasured;
  beta-day heavyweights fill the board; ARM/UMC prove beating the cap still dies at the
  score without Changes 1–4 and 6). **It stands or falls together with Change 4** — same
  axis, two surfaces (rank into grading, points into ranking).
- **Recommendation**: rule it with Change 4 as one decision.

## Change 6 — the catalyst tiers: the wall everything else stops at *(biggest change)*

**Under EVERY variant priced above, a routine-graded real EP still dies: 0 of 26 clear 50 at
any bar ≥35 with a routine grade.** The catalyst axis holds the key it always held — 25 pts +
every conviction floor. So the tier fix is not one change among six; it is the gate on the
other five.

### The diagnosis, from the full grade record (no longer n=7)

- **Base rates measured** (700 graded ticker-days 04-13→08-21): routine 47% / strong 42% /
  **game_changer 11.6%** of graded candidates — but among names that become live alerts,
  game_changer is **30% all-time, 44% in the last 60 days, 42% of HIGH alerts**. (The card's
  "59%" was a different 60d window/denominator; direction identical.) Median gap by grade:
  game_changer 14.4% vs routine 15.6% — the top grade is near-modal on ordinary gappers and
  tracks nothing about the move's rarity.
- **The real EPs got**: ARM routine (−12) · QCOM routine (32.4) · AMD routine (32.4) · UMC
  05-06 strong (21.6) · MRNA **strong** (his textbook case, news that moved the whole biotech
  sector — one grade below top) · INTC the only clear game_changer · QURE mna (hard-filtered
  — a ~15R real EP killed by the M&A rule, flagged, not priced here). **At most 1–2 of 7.**
- **The MRNA tick record makes it exact** (`533b_scan.psv`): 07:05 ET, gap read 10.04%,
  graded strong, score **21.6 → "score 22 < 50" — the reference EP was KILLED at real-EP-modal
  gap size with its actual grade.** 07:10, gap read 33.1% → the gap≥20+strong conviction
  floor fired → 115.2. The grade was cached at 07:05 and never revisited (grades change
  intraday on only 15 of 700 ticker-days). **Only the freak gap saved it; a 10–13% MRNA dies
  in today's system every time.**
- **Why the definitions do this**: the prompt defines game_changer by catalyst FORM ("massive
  beat + raise, FDA approval, transformative contract") — near-modal in earnings season —
  with no rarity or surprise anchor; rule 4 demotes sector-wide moves to routine, which
  structurally mis-grades the 04-08 class of real EP (13 of 26 — a sector-wide repricing);
  and the operator's own separator — *"truly unexpected and/or gamechanging"* — appears
  nowhere. We already measure unexpectedness mechanically: `expct_scheduled` (#568, live) —
  unscheduled catalysts reach ≥8×ADR at **11.6% vs 3.8%** for scheduled. The tier system
  ignores it. Plus the known fail-open: truncation/timeouts grade as routine, silently
  (2026-08-06/07 incidents, detection #543).

### Proposed correction (proposal only, for his ruling)

1. Rewrite the tier definitions around SURPRISE, not form: game_changer requires an
   unscheduled/unforecastable event (or a scheduled one of extraordinary magnitude);
   wire `expct_scheduled` into the prompt as a mechanical input; delete the sector-momentum
   auto-demotion for names with a concrete company event on a sector-moving day.
2. Re-grade when the news corpus materially changes intraday (the 07:05 cache pinned MRNA's
   early grade all morning).
3. The bar/points decision — one lever, measured (package mechanics, strong-graded members):

   | bar (or equivalent strong pts) | of 26 @strong | of 26 @game_changer | pool cost vs today |
   |---|---|---|---|
   | 50 (today, strong=15) | 4 | 18 | **−0.4/day (−16%)** |
   | 45 (≈ strong=20) | 4 | 22 | −0.3/day |
   | **40 (≈ strong=25)** | **14** | **26** | **+0.4/day (+17%, ≈ +9/month)** |
   | 35 (≈ strong=30) | 20 | 26 | +1.2/day (+50%) |

   With the grades actually assigned, the package at bar 50 still clears only MRNA + INTC
   (2 of 7); bar 40 adds UMC 05-06 (3 of 7) — ARM/QCOM/AMD stay dead on their routine
   grades whatever the mechanics. The bar buys nothing until the grader stops inverting.
4. **The regrade of the 19 never-graded members — priced, NOT spent.** Raw cost is small:
   ~$0.03–0.05/name (one sonar-pro retrieval ≈ $0.02 + one sonnet-5 grade ≈ $0.007 intro /
   $0.011 after 08-31, ~2.2k in / ~300 out tokens) → **≈ $1–2 all-in for 19**. The real
   price is VALIDITY, not dollars: retrieval cannot reconstruct what was knowable that
   morning, and the grader's own freshness rule reads a correctly-dated April article as
   "predates today's gap → not today's catalyst" — **the replay is biased toward routine by
   construction, and would "confirm" the inversion as an artifact**
   ([[rigor-before-paid-eval-spend]]: it would exercise a lookalike, not the live mechanism).
   Making it faithful needs a date-scoped retrieval harness — build effort, not spend.
   **Decision left to the operator; recommendation: do not spend until the date-scoping
   question is answered; the live record accrues the honest n at $0, slowly.**

---

# THE COMPOSITE RE-CHECK — each change alone, and the package

| variant (mechanical part; catalyst/float/volconv/theme excluded) | AUC | within-day | members ≥50 @strong | pool ≥50 /day (mix-blend) |
|---|---|---|---|---|
| **P0 — current** (gap ladder + RVOL + neglect + momentum) | **0.37** | 0.41 | 4/26 (floors only) | 2.46 |
| Change 1 alone (momentum deleted) | 0.33 | 0.42 | 4 | 2.56 |
| Change 2 alone (neglect deleted) | 0.38 | 0.43 | — | — |
| Change 3 alone (gap flattened) | 0.41 | 0.43 | 4 | 2.15 |
| Change 4 alone ($vol for RVOL) | 0.47 | 0.46 | 9 | 2.68 |
| package minus Change 4 | 0.33 | 0.50 | — | — |
| **FULL package, day-$vol tiers** | **0.63** | **0.68** | 4 (14 at bar 40) | **2.07** |
| **FULL package, ADV$ tiers** | **0.70** | 0.65–0.67 | 4 (14 at bar 40) | 2.07 |

- Sanity anchor: the blend baseline 2.46/day matches the live record (~187 HIGHs over ~72
  sessions ≈ 2.6/day). Costs are corpus-proxy relatives — the scored pool still faces the
  RVOL session gate, extension, top-20 and M&A downstream, so absolute counts are upper
  bounds; the RELATIVE deltas are the honest number.
- The interaction the card warned about is real and now measured: three of the four
  mechanical changes are near-worthless ALONE (0.33–0.41) and only work as a package —
  and the package without the liquidity swap collapses back to 0.33.
- 0.63–0.70 is a RANKER, not a magic number: it means a real EP typically out-scores
  two-thirds of its board instead of one-third (28th percentile → 75th). At five slots,
  ordering is the product (P4: MRNA vs MRVL).

# ⚠ What this proposal does NOT answer

- **Whether any of it converts to R.** Every number is separation against an
  outcome-conditioned label, not P&L under our entry/stop. The label favours liquid quiet
  names by construction; the honest test is the post-07-16 label window (~mid-October) and
  the rank shadow, both already accruing.
- **The catalyst inversion beyond n=7.** The $0 evidence stops at 7 graded members; the
  regrade is priced above with its validity trap. Everything mechanical is downstream of
  this wall.
- **Admission.** 7 of 26 members still gap below the 9.0% floor (BASELINE_DEBT) and never
  reach scoring at all; feed lag adds ±4pp at the floor. No score change touches that; it is
  a separately-ruled criterion (P9's corollary: the floor ruling deliberately took the
  smaller loosening until the ranker is proven).
- **Whether the RVOL 2.0× session GATE (as opposed to the score tiers) should stay** — it
  killed UMC 04-17 and INTC's early ticks; not priced here.
- **Per-tick truth for 04-08** and the M&A hard-filter question (QURE) — flagged, out of
  scope.
- **Regime**: half the label is one April session. Every key read is shown ex-04-08 and
  within-day; the base-axis inversion specifically is mostly a flood-day phenomenon.

# Verdict — plain words

**The score can be taken from anti-selective (0.37 — it actively sinks real EPs to the 28th
percentile of their own board) to a usable ranker (0.63–0.70, 75th percentile) with four
mechanical changes that together REDUCE alert volume — but every one of them stops at the
catalyst wall: with a routine grade, no real EP clears any bar under any variant, and the
grader hands its top tier to ~40% of ordinary alerts while giving the operator's own textbook
EP one grade below top and killing it outright at 07:05 on the day he called it perfect.**
Rule the four small changes as a package (they only work together), rule the cap axis with
the liquidity component (same axis, two surfaces), and treat the tier rewrite as the change
that decides whether the rest matters. In-sample throughout; the mid-October label window and
the rank shadow are the judge.

## Files

- This doc: `docs/analysis/score_redesign_proposal_533_2026-08-22.md`
- Evidence base: `docs/analysis/selection_layer_533_2026-08-22.md`
- New captures + scripts (scratchpad, pulled once): `533b_bars.psv`, `533b_scan.psv`,
  `533b_pull_{bars,scan}.sql`, `533b_analyze{,2,3,4}.py`, `533b_analysis{,2,3,4}_out.txt`
- Reused: `533_q2.psv` corpus · `_569_pregap_base_v2.py` (pre-registered base axis) ·
  `pregap_base_v2_2026-08-20.txt` · `must_not_miss_eps.py` ·
  `ep_reference_mrna_2026-08-19.md` · `structure_model.md` · method template
  `adv_floor_556_2026-08-20.md`
