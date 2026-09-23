# #533 — The selection layer: pricing the top-20-by-gap cap, and whether the score can rank a real EP at all (2026-08-22)

**MEASUREMENT ONLY. No cap, floor, weight or criterion is changed or proposed as decided —
selection is entry discipline and is the operator's sole authority (THE LINE). $0 — prod
read-only via psql, no LLM calls, no paid data.**

## The question

Operator's frame, on the 562b retention result (26 labelled real EPs → 0 held at day 5):
*"we're back to selection… we're selecting on gap size, not on whether it's a real EP."* And the
card's original ask (2026-08-05): *"given 10 alerts this morning and 5 slots, did we take the
right ones?"* Two measurable halves:

- **A — price the top-20-by-gap admission cap**: how often it binds, what it dropped in real
  EPs, and what top-25 / top-30 / a non-gap-ranked cap would have kept. Reconciled against
  `gates_extension_top20_577_2026-08-22.md`, which priced the same cap from
  `mi_ep_missed_outcomes` and found it nearly costless.
- **B — can `_score_ep`'s components rank real EPs**: which of `gap`, `rel_volume`,
  `catalyst`, `float`, `neglect`, `vol_conviction`, `prior_momentum`, `theme_bonus`,
  `conviction_floor` separate the 26 labelled real EPs from ordinary gap days — anchored on
  the operator's own definition of a real EP (`ep_reference_mrna_2026-08-19.md`: big gap,
  game-changing news, long quiet base = neglect).
- **Mid-study addition (operator)**: whether feed lag — the delayed feed admitting a different
  population than the real-time feed would (TWST 08-19) — contaminates either answer.

## The label and the traps, restated up front

- **Real EP = the 26-member #577 fixture** (`tests/fixtures/must_not_miss_eps.py`): MRNA
  (operator-named) + 25 evidence-named ≥10R winners (TDIC excluded on the source's own flag).
  The label is **outcome-conditioned by construction** — so this study banks **no returns**,
  only counts, ranks and separation statistics of ex-ante features against the label.
- `mi_ep_missed_outcomes` is used **only as frozen presence evidence** (which surface a name
  hit); every outcome column dropped (#583 stale rows + gap-day-open basis, traps 1/4/5).
- All price/volume features are point-in-time from `mi_daily_closes` (official Polygon daily
  prints, bars strictly before or on the event day; forward windows only to reproduce the
  label, never as a bankable result).
- n = 26, only 7 ever graded, 13 of 26 on one session (2026-04-08). Confidence is priced
  accordingly throughout.

## Data and provenance

- **New captures** (pulled once, read many): scratchpad `533_q1.psv` (table ranges,
  cap-binding series 04-13→08-21, live alert pool, 05-06/05-07 scan-log boards),
  `533_q2.psv` (the rebuilt 1,100-row tier-A gap corpus 03-01→08-21 **with point-in-time
  score components** — trailing-year high, 3-month momentum, 20d ADV/RVOL, RS/SMA join — plus
  full-market boards for 04-08/05-06/05-07), `533_q3.psv` (intraday-high boards for the three
  flood days; the #489 rt-vs-delayed shadow: `gap_pct_rt/gap_pct_delayed/price_source` per
  scan row, all `ep_rt_*` audit events, the TWST 08-19 rows). SQL alongside each capture.
- **Reused captures**: `562c_q2/q3/q4.psv` (member funnel sweep, day boards), `577_top20.psv`,
  `577_batch4.out` (cap-depth series) — same scratchpad, not re-run.
- **Corpus**: identical screen to 562b (ever-sectored, close ≥ $10, $vol ≥ $50M, open gap
  ≥ 8%, 03-01→08-21): 1,100 rows; **all 26 members present**; 1,074 controls (61 of which are
  other tail winners — key results re-run excluding them, unchanged).
- **Lookback limits**: `mi_daily_closes` starts 2025-07-14, so "52-week high" is a
  trailing-165–252-session high (March events have the least). This UNDER-counts
  neglect-as-coded points equally for members and controls; direction stated where it matters.
- **Feed-lag instrumentation exists only from 2026-07-21** (audit events) / **07-27** (scan-log
  rt columns). 25 of 26 members predate it.

---

# PART A — the top-20-by-gap admission cap

## Result 1 — how often it binds: 30 of 91 logged sessions, all the damage on a handful

- From `mi_ep_scan_log` (04-13→08-21, 91 sessions): **30 sessions ever logged an
  `outside top-20 gap cap` name**. Heavy days: 05-06 (119 capped names), 04-14 (80), 07-30
  (70), 05-07 (64), 06-15 (53), 08-07 (43). **Zero binding in the 9 sessions since 08-10.**
- Binding is measured on the **delayed-feed board** (Result 5): a real-time board is strictly
  deeper on busy opens, so 30-of-91 is a floor, not a ceiling.
- Unchanged from 577's read: the cap is a flood-day phenomenon. What changes is what those
  floods contained (Result 2).

## Result 2 — the "16 cap kills" decompose: 3 floor kills, 2 score kills, 1 at rank 22, 10 unknowable-at-depth

562b attributed 16 of the 26 real EPs to this cap. Where a scan log EXISTS (the 05-06/05-07
three), the logged per-tick ranks are authoritative and they correct the attribution:

| what actually killed it (best evidence) | n | members |
|---|---|---|
| day high NEVER crossed the floor — the **gap floor** was the killer on any feed/basis | 3 | ASX, IREN, NBIS (official 04-08 highs < +9% vs prev close) |
| **cracked the cap at some tick, WAS graded, died at the SCORE** | 2 | ARM 05-06 (logged min rank **18**, scored **−12**, catalyst=routine) · UMC 05-06 (min rank **14**, scored **21.6**) |
| cap-killed for real, one rank outside | 1 | SNOW 05-07 (logged min rank **22**, never graded; next wall would have been the 2.0× session-RVOL gate — raw 0.11×, projected 2.9×, outcome unknowable) |
| pre-log (04-08), rank truth unreconstructable at tick level | 10 | MU, STRL, ALGM, AMKR, QBTS, SNDK, USAR, BE, HUT, APLD |

- **For the 04-08 ten, daily bars bound but cannot pin the rank.** At the OPEN tick the board
  was thin (52 names ≥ the 10% floor): APLD ranked **11 (inside the cap)**, QBTS 33, SNDK 48;
  the other seven were below the floor at the open and crossed later, when the board had
  flooded — peak-vs-peak ranks 17–241. ⚠ The three logged cases show peak-basis reconstruction
  OVERSTATES depth several-fold (ARM peak-basis 85 vs logged 18; UMC 208 vs 14; SNOW 106 vs
  22), because ranks are per-tick and a name can crack the cap early before junk runs. So
  "rank 97–342" (562b, market-wide, no universe floors) and my 17–241 are upper bounds on
  depth, not measurements.
- What survives every basis: on a flood morning a real EP gapping 8–13% competes with 40–130
  names gapping more (05-06: ranks 21–30 were gapping 22–26%), its board position is
  unstable tick to tick, and the cap denies it most of its grading ticks even when one tick
  slips through.
- Net attribution across the 26: **at most 14 cap kills** (10 unknowable-rank + SNOW + the
  borderline 04-08 cases), 3 floor kills, and **the score's kill count rises from 2 to 4**
  (QCOM, AMD + ARM, UMC 05-06) — consistent with 562b's own Result 4 (5 of 7 graded members
  below the 50 bar) but correcting its stage-of-death table, which had counted ARM and UMC
  as cap deaths.

## Result 3 — reconciling the two prior readings: both true, each blind on the other's axis

`gates_extension_top20_577` priced the cap from `mi_ep_missed_outcomes` and found ~5
recoverable winner names, "not toxic, a throughput limiter". The retention study found the
same cap killed 16 of 26 real EPs. Both are correct on their own instrument:

1. **Era censoring**: the missed-outcomes table starts 04-14. **13 of the 16 kills are 04-08**
   — before any skip row existed. 577's cohort could not contain them by construction.
2. **Metric censoring**: 577's prize metric was the ≥100% 20-day peak ("doublers"), a
   percent-space screen. Of the 16 killed real EPs, **only 2 (STRL +110%, BE +106%) ever
   reach it** — the other 14 peaked +42–85% in percent terms while being 10–49R monsters in
   the EP-day-low stop geometry (MU 49R on a +64% move; ASX 32R on +42%). (Peak basis here is
   vs the EP-day close; 577 used the open — the 2-vs-14 split moves by at most a name.) ARM,
   UMC and SNOW sit inside 577's 789-row cohort and were invisible to its winner count
   because a large-cap real EP is an **R-space** winner, not a percent-space one.

**Reconciled statement: the cap's cost is real, it lives almost entirely in one pre-log week
(04-08) plus 05-06/07, and it is denominated in R, which a percent-peak screen structurally
cannot see.** 577's within-era load pricing (top-25 ≈ +21 HIGHs/4mo, top-30 ≈ +35) stands and
is reused below.

## Result 4 — priced alternatives: raising N buys nothing; the rank AXIS is the lever

Measured on the three flood boards (intraday-crossed field, the fullest competitive picture):

| cap rule (same 20 slots unless noted) | of the 13–14 cap-implicated real EPs, demonstrably keeps | load (from 577) | caveats |
|---|---|---|---|
| top-20 by gap (today) | ARM/UMC got one tick each and died at the score; APLD inside at the open tick | — | — |
| top-25 by gap | **+1 grading shot (SNOW, logged rank 22)** | +21 HIGHs/4mo | the other rank-21–25s it admits are not the real EPs |
| top-30 by gap | +0 demonstrable (QBTS at open-rank 33, SNDK 48 need top-35/50) | +35 HIGHs/4mo | 04-08 tick-ranks unknowable |
| top-20 by session RVOL | 1 (HUT, peak basis) | similar | real EPs run QUIET (B, Result 6) — wrong axis |
| top-20 by gap/ADR | **0** | similar | junk out-gaps its own ADR too on flood days |
| **top-20 by dollar volume** | **5 (MU, SNDK, BE, ARM, SNOW)** | similar | see below |

- The five the $vol axis recovers are the five biggest R winners in the killed set (MU 49R,
  SNDK 31R, SNOW 24.5R, BE 15.9R, ARM 11R). MU ranked **1st**, SNDK **2nd**, ARM and SNOW
  **3rd** on their day's $vol board — and unlike gap ranks, a mega-cap's dollar-volume rank
  is stable across ticks, so the tick-level unknowability that clouds the gap ranks does not
  apply here.
- **Caveats, stated hard**: (i) full-day dollar volume is a look-ahead proxy — live would rank
  on projected/premarket $vol, the same projection the scanner already computes for RVOL, so
  the signal is implementable but unmeasured at 9:31 granularity; (ii) on a market-wide gap
  day the $vol top-20 fills with index heavyweights (04-08's board: MU, SNDK, INTC, LITE,
  WDC, STX, LRCX, HOOD…), so the catalyst/score stage becomes the binding filter — and Part B
  shows that stage currently inverts on real EPs; (iii) "recovers 5" means past the CAP, not
  into the book — ARM and UMC prove a real EP that beats the cap still dies at the score, so
  no rank-axis change alone fixes selection; (iv) whether an intraday floor-cross happened
  before the 09:45 ORB close is not knowable from daily bars for any of these.
- Changing the rank axis is a **criterion redesign** (CHANGE_PROCESS, operator sign-off), not
  a threshold move. This is the fork the measurement surfaces; the ruling is the operator's.

## Result 5 — feed lag, part A: the cap verdict is robust to it; the FLOOR verdict is not

From the #489/#490 shadow (07-21→08-21; 25 of 26 members predate it — their feed truth is
unknowable):

- **The live funnel still selects on the delayed feed**: 608 of 609 scan ticker-days since
  07-27 carry `price_source=polygon_delayed` as the decided price; rt columns are shadow.
- Disagreement across the admission floor is **routine, not rare**: `ep_rt_floor_flip_up`
  (rt ≥ floor, delayed below) fired on **591 ticker-days in 24 sessions** (~25/day, median
  rt−delayed **+3.7pp**); flip_down on 399 (median −4.1pp). 194 of the 560 post-07-27
  flip-up ticker-days **never became a scan candidate at all that day**; the curated
  `ep_rt_live_miss` (passes mechanical gates, never a candidate) counts **90 ticker-days in
  21 sessions ≈ 4/day**. TWST 08-19 is the worked case: rt 19.5% vs delayed 10.4% at 09:45;
  HIGH alert only at 09:55 — ten minutes after the ORB window shut.
- **Why A survives**: near rank 20, gap boards are dense at ~1 name per 0.5–1pp, so a ±3.7pp
  mis-read moves a name 2–8 ranks (04-08/05-06/08-07 boards). That cannot rescue the deep
  kills, and it cannot change the structural finding (gap-rank is the wrong axis) — but it
  IS enough to flip a boundary name like SNOW (rank 22) or ARM (rank 18) across the cap, so
  per-name attributions within ~±8 ranks of the cap are feed-conditional.
- **Where it is NOT robust**: members killed at the FLOOR boundary (ASX 8.16 / IREN 8.28 /
  NBIS 8.07 vs the then-10% floor; today's BASELINE_DEBT seven at 8.1–8.7% vs 9.0%) sit
  **closer to the floor than the median feed disagreement**. Which side of admission they
  land on in a real-time world is genuinely undetermined. Feed lag compounds with selection
  at the floor, not at the cap — and the binding frequency in Result 1 is conditional on the
  delayed board (understated on busy days).

---

# PART B — can `_score_ep` rank a real EP at all?

## Result 6 — component by component: one axis separates, and it is not in the score

26 members vs 1,074 tier-A controls, point-in-time, mirroring `_score_ep`'s exact bucketing.
AUC = P(random member > random control); 0.50 = no signal, <0.50 = runs backwards.
(Winners-excluded controls and day-clustered reruns in parentheses where they differ.)

| component / axis | member median | control median | AUC | verdict |
|---|---|---|---|---|
| `gap` raw % | 9.9% | 12.0% | **0.34** (0.41 within-day) | **backwards** — real EPs gap SMALLER |
| `gap` points (0–25) | 10 | 15 | 0.35, p=0.06 | backwards |
| `rel_volume` (day-RVOL proxy) | 1.8× | 2.8× | **0.31** (0.32 excl-winners) | **backwards** — real EPs run QUIET; member median earns **0 points** (<2×) |
| `neglect` as coded (pct of trailing-yr high) | 0.78 | 0.71 | 0.45–0.54, p=0.31 | **nothing** — both medians score 0 pts |
| `prior_momentum` penalty fires (3m ≥ +30%) | 31% of members | 32% of controls | 0.52 | nothing — punishes real EPs at the same rate as junk (ARM −25, SNDK −25, INTC −15, QURE −25…) |
| `theme_bonus` / `float` / `vol_conviction` | — | — | — | not measurable point-in-time (declared, not guessed); ≤10 pts combined |
| RS composite / rs_rank (pit) | 63 / 1410 | 57 / 1439 | 0.51 / 0.54 | **nothing — the 08-11 SE case does NOT generalize** |
| above SMA-10/20/50 (pit) | 42% | ~40% | 0.51 | nothing |
| gap / ADR | 1.7× | 2.2× | 0.41 | backwards |
| **day dollar volume** | **$830M** | **$346M** | **0.65** (0.68 within-day and day-clustered, p=0.01) | **the only separator found** — and it appears nowhere in the score |
| pseudo-composite (gap+vol+neglect+mom pts) | 16 | 23 | **0.37–0.41** | **the composite is anti-selective end to end** |

## Result 7 — the catalyst axis inverts too, on the only seven ever graded

- Grades actually assigned to real EPs: **routine** — ARM (score −12, dead last of 16), QCOM
  (32.4), AMD (32.4), QURE (14–32, plus the M&A hard filter); **strong** — UMC 05-06 (21.6),
  MRNA (115.2); INTC's 100 is consistent only with game_changer + the gap≥15 floor (alert row
  purged). **At most 1–2 of 7 got the top grade.**
- The pool baseline runs the other way: **59% of all live alerts in 60d were graded
  game_changer** (48 of 81, #533 card) — the top grade is modal on ordinary gappers and
  denied to real EPs. n=7; underpowered but perfectly consistent with 562b's 0-for-5 below
  the 50 bar.
- **The architecture makes this fatal, not incidental**: 22 of 26 members gap < 15%, so no
  conviction floor is reachable without a game_changer grade; a modal real EP (gap ~10%,
  quiet RVOL <2×, near highs, no theme) scores **gap 10–15 + catalyst 15 + 0 + 0 ≈ 25–30 —
  structurally below the 50 bar** unless the LLM awards game_changer (floor 60). Exactly the
  scores QCOM/AMD/UMC/QURE actually got (21.6–32.4). The score does not merely mis-weight
  real EPs; for the modal real-EP shape it has no path to 50 that does not run through the
  one grader that inverts.

## Result 8 — neglect and base-length: the operator's core idea is not what the code measures

- **What is in the score**: `neglect` = percent below the 52-week high (15 pts if price <
  50% of it, 8 if < 70%) — computed from the FMP profile's **current (post-gap)** price. It
  is a **beaten-down detector**. The operator's neglect — *"a large base… no major movements
  up or down, so the news moving it significantly is truly unexpected"* — is a **quiet base
  near highs**. These are opposites on this cohort: **65% of real EPs sit at ≥70% of their
  trailing-year high and score ZERO neglect points** (controls: 52%). MRNA — the reference EP,
  AT its 52-week high — scores 0 on the component named after his thesis.
- **Base LENGTH / quietness is in the score nowhere.** The only corpus tests of it
  (#569, `pregap_base_axes_2026-08-19.txt`, two definitions) ran null-to-backwards on tail
  winners — so this study does not claim adding it would work; it reports only that the
  operator's stated mechanism has no live operationalisation, and the one axis wearing its
  name rewards the opposite chart.

## Result 9 — feed lag, part B: robust

Every Part-B feature is computed from official Polygon daily prints, not either intraday
feed — feed lag cannot touch the component measurements. What IS feed-conditional is the
funnel trace (who alerted/entered: the live path ran delayed through 08-21) and therefore
which real EPs ever REACHED grading — i.e. the n=7 could have been a different seven on a
real-time feed. The component AUCs stand regardless.

---

## ⚠ What this study does NOT answer

- **Per-tick truth for 04-08** — no scan log existed and the delayed-feed board of that
  morning is unreconstructable; my crossed-board ranks are peak-vs-peak approximations with
  a DEMONSTRATED overstatement bias (the three logged members' true min ranks were 14–22
  against peak-basis reconstructions of 85–208), and whether any member's floor-cross
  happened before 09:45 is unknowable from daily bars.
- **562b's stage-of-loss table needs a two-name correction** (ARM and UMC 05-06: score
  kills, not cap kills — their scan rows show both a cap tick AND a graded tick). Noted
  here; amending that doc is a follow-up, not done silently in this one.
- **Feed-lag involvement for the 26 members** — instrumentation begins 07-21; 25 of 26
  predate it. Bounded by reasoning (Result 5), not measured.
- **Whether the $vol signal survives out of regime** — 13 of 26 members are one session;
  and the label itself is R-geometry (ADR-relative), which mechanically favours liquid,
  quiet, low-ADR names — some of the dollar-volume separation may BE the label definition.
  That definition is the operator's own choice of what "real" means, but a fresh flood day
  with post-07-16 labels (settle ~mid-October) is the honest out-of-sample test.
- **Catalyst behaviour beyond n=7** — regrading the 19 never-graded members would cost LLM
  spend and is a paid step the operator would have to authorize; the $0 evidence stops at 7.
- **Anything about what to change.** Both the cap's rank axis and every score weight are
  detection criteria: CHANGE_PROCESS, N≥10, operator sign-off. This document prices; it does
  not propose.

## Verdict — A, plain words

**The cap binds on ~1 session in 3 and does nearly all its real-EP damage on three flood
mornings — but the "16 cap kills" headline overstates it: 3 were gap-floor kills, 2 (ARM,
UMC) actually cracked the cap, got graded, and were killed by the score, and only SNOW is a
demonstrated one-rank-outside cap kill. Raising the cap to 25 demonstrably buys ONE grading
shot (SNOW); to 30, none we can prove; the 04-08 ten are unknowable at tick level but sat
behind 40–130 bigger gappers whenever they crossed the floor.** The two prior readings
disagree only because the skip-table study could not see 04-08 (no logs existed) and counted
winners in percent space (14 of the 16 never double in %; they are 10–49R in stop geometry).
The one axis that would have held the big ones inside a 20-name cap is **dollar volume**
(MU 1st, SNDK 2nd, ARM/SNOW 3rd on their day's $vol board — 5 recovered, including every
≥15R name in the killed set) — a rank-axis redesign, not a threshold move, with real caveats
(projected-$vol proxy, heavyweight beta-day junk, and a grader downstream that currently
inverts). And the sharpest lesson from the logged cases: **cracking the cap did not save a
single real EP — the RVOL gate or the score killed every one that got through (UMC 04-17,
INTC's rvol tick, ARM −12, UMC 21.6)**. The cap is the first of three walls; Part B shows
the last wall is the one that runs backwards. Feed lag: the cap verdict is robust to it
(±4pp mis-reads move a name 2–8 ranks, not 80); the FLOOR verdict is not (the delayed feed
mis-reads gaps by ±4pp routinely and ~4 rt-passing names/day never become candidates at
all), and binding frequency is measured on the delayed board — a floor, not a ceiling.

## Verdict — B, plain words

**No component of the current score separates real EPs from ordinary gap days, and the three
heaviest — gap, volume intensity, catalyst — run backwards on them.** Real EPs gap smaller
(AUC 0.34), trade quieter (0.31 — the median real EP earns zero volume points), get graded
routine while 59% of ordinary alerts get the top grade, and 22 of 26 can't reach any
conviction floor. The component named `neglect` measures distance below the 52-week high —
a beaten-down detector — and pays 0 to two-thirds of real EPs including MRNA itself; the
operator's actual neglect mechanism (long quiet base near highs) exists nowhere in the code.
RS strength and above-MA structure — the SE hypothesis — showed no signal on this set either.
**The only axis that separates at all is sheer dollar liquidity (AUC ~0.65, robust within-day),
and it is not in the score.** With n=26, one dominant session, and a label that itself favours
liquid quiet names, this is evidence the current composite cannot rank real EPs — not yet
evidence of what would. What settles it: the post-07-16 label window (mid-October), the
rank-shadow record, and — if the operator authorizes paid spend — retro-grading the 19
never-graded members' catalysts.

## Files

- This doc: `docs/analysis/selection_layer_533_2026-08-22.md`
- New captures + SQL (scratchpad, pulled once): `533_q1.{sql,psv}`, `533_q2.{sql,psv}`,
  `533_q3.{sql,psv}`; analysis `533_analyze_a.py`, `533_analyze_b.py`
- Reused captures: `562c_q2/q3/q4.psv`, `577_top20.psv`, `577_batch4.out`
- Label + anchors: `tests/fixtures/must_not_miss_eps.py` ·
  `docs/methodology/ep_reference_mrna_2026-08-19.md` ·
  `docs/analysis/real_ep_retention_562b_2026-08-22.md` ·
  `docs/analysis/gates_extension_top20_577_2026-08-22.md` · method template
  `docs/analysis/adv_floor_556_2026-08-20.md`
