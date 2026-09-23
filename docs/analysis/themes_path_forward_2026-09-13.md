# Themes — the goal, why it keeps recurring, and the path

Written 2026-09-13 after he asked: *"it keeps recurring that we don't assign themes, RS is not
looking far enough, etc. this has bit us many times, what's the path forward, what's the goal we're
trying to achieve with this and how do we achieve it."*

Five independent designs (coverage / identity / timeliness / validation / adversarial), two
adversarial judges. **Both judges ranked them identically: adversarial > timeliness > coverage >
validation > identity.** Every load-bearing claim below was re-verified against code or prod before
being written down; two of my own earlier claims did not survive that check and are corrected here.

## Method and population

**Population:** all 127 live themes and the 398 theme lineages on record; his 7 labelled real EPs
(`docs/methodology/operator_labelled_eps.md`); his 44 themed labels of 2026-09-13; the 353 stored
cluster-lineages since June. **Window:** June 2026 → 2026-09-13. Facts are taken from prod queries
run today, from `docs/analysis/step3_theme_runway_2026-09-07.md`, and from commits `268351df` and
`ccd9e5a9`, each re-read rather than quoted from summary.

## The goal — his words, made measurable

He stated it himself and it is **not coverage**:

> *"we don't have 100% coverage that is not the goal otherwise every gap will get boosted, our goal
> is to 1) boost the real EPs if there's a real theme attached and 2) the reflexive part, source new
> themes from the gap ups... low'ish coverage may not be a bad thing provided we catch the real EPs"*

| goal | the measurable form | today |
|---|---|---|
| **1. Boost real EPs with a real theme** | of his labelled real EPs (n=7), how many had a theme **that the rubric counted** on the day | **1 of 7** |
| **2. Source themes from gap-ups** | of gap-ups with no theme, how many seeded one that proved real | lane shipped 2026-09-12; **2 of 7 recurring judge-named groups** are unmatched and waiting |

At 100% coverage every gap is boosted and the boost carries no information. **Coverage is an
output.** My earlier "289 of 600 strong names unthemed = the problem" was the wrong denominator.

## Why it keeps recurring — the mechanism is not what we have been fixing

**Group-finding is already good. 54 of 58 (93%) of his labelled groups were found correctly by the
clustering** (`268351df`). Every shipped fix has tuned **supply and assignment** — RS floor 90→70
(#534), ceiling 200→600, pool shapes — a side that was not the bottleneck, and the code says so in
its own comment at `theme_engine.py:281`. Meanwhile the real defects sit **downstream in the
decision layer** and have been quantified for a week without being actioned:

**(1) The engine holds the group for five weeks before naming it.**
**140 of 398 themes (35%) had a stored cluster holding ≥ half their founders a median 26 sessions
before the birth.** Those themes matured at **37% — the same as the rest**, so naming them earlier
would not have cost quality. ⚠ And the delay is **not** on the cluster side: clusters convert at
48–54%, 37% of them the same night, median lead 2 sessions. There is no unused cluster time. **The
unused window is the birth decision.**

**(2) The rubric throws away the themes the engine does find.**
`in_active_theme` counts **only Accelerating or Mainstream** (`ep_detector.py:1568`). Of his 7 real
EPs, PLTR (+15.5%) and MRNA (+84.3%) were in **Nascent** themes the engine had found correctly —
and the boost did not fire. **The bonus switches on only once a theme is no longer early, which is
the opposite of the north star.** Its own docstring records it as decorative: 0 alerts crossed tier
in 60 days.

**(3) Goal 2 had no lane at all until yesterday.** Nothing routed a gap-up into theme creation.
TEAM and HTFL — two of his real EPs — were themed *later*; their gap was the early mover that should
have seeded the theme.

**And the switch built to fix supply safely has never been flipped:** `theme_birth_gate` has been in
**`observe` since 2026-07-30 — 45 days** (verified in `mi_safeguard_state` today, not assumed).
Several open tasks are dated behind a flip that never happens.

## What to stop doing — both judges, independently

- **Stop widening the assignment pool.** Done twice (#476, #534); the code's own comment says this
  lever structurally cannot move discovery supply.
- **Stop reaching for residual price correlation ≥0.80 as the correctness bar.** Three of five
  designs proposed it. He ruled it out a week ago: his 47 real themes sit at median fit **0.36**, so
  a 0.80 bar rejects **46 of 47**.
- **Stop filing display / parenting / health-check tasks** (#505, #506, #580, #640, #648) against a
  population that will change once the decision layer is fixed.
- **Stop treating his hand labels as a scorecard.** He called them supplementary and noisy.
- **Stop using trade returns as the metric.** Ruled out twice.

## The path — three moves, mapped to his two goals

| # | move | serves | cost | whose call |
|---|---|---|---|---|
| **1** | Count Nascent themes in the EP boost (2 of his 7 real EPs were Nascent-themed and got nothing) | goal 1 | $0 to measure | **his** — detection criterion |
| **2** | Name a group when the cluster is in hand, not 26 sessions later (n=140 of 398 themes) | goal 1 | $0 to measure | **his** — the target latency |
| **3** | Tap-promote the 2 judge-named candidates already waiting (ai-monetization, 3 tickers; semiconductor-equipment, 2) | goal 2 | $0 | **his** — one tap each |

**Move 1 is the cheapest real win.** The engine already found PLTR's and MRNA's themes. Nothing new
has to be discovered — a definition has to change so the rubric stops discarding them.

**Move 2 has its evidence already assembled:** the 140-theme cohort, with the maturity check that
says earlier naming does not degrade quality. It needs a target latency, which is his to set —
`ccd9e5a9` sized the payoff: 5 sessions earlier takes founder gaps still ahead from 29% → 55%, 10
sessions → 68%, 15 → 81%.

## What this does NOT answer

- **The right coverage percentage.** He said he does not know it; this says it is an output, not a
  target, and does not propose one.
- **Whether the boost should be bigger.** #368's D2 cannot be answered while the boost is excluded
  from Nascent — fix what it counts before sizing it.
- **Whether multi-membership is needed.** His HOOD point stands (5.4% of tickers are in >1 theme),
  but both judges rejected building that subsystem near-term; it is a real question deferred, not
  settled.
- **Whether the birth gate should be flipped on.** This reports that it is `observe` and has been
  for 45 days. Flipping it is a safeguard change and is his.

## ⚠ Two of my own claims did not survive verification

- **SION is sector-filtered** (Healthcare, $7.85 — the known Healthcare-under-$50 cut). It is not a
  discovery-cap victim and I should not have cited it. **XHLD is not filtered and stands.**
- **A judge's claim that strong clusters convert *less* (23% vs 54%) is not supported** by the
  source document, which says clusters convert at 48–54% and the plan's bar holds. Dropped.

---

# The birth gate — why it is still `observe`, and what flipping it would do

## Why it is still observe: it is UN-RUN, not blocked

The `observe → on` flip requires a forward-evidence review
(`theme_birth_gate_observe_calibration`) plus CHANGE_PROCESS sign-off. **That review's evidence bar
was met on 2026-08-07 — five weeks ago.** Its predicate (distinct clean `theme_date`s since
2026-07-29, threshold **8**) now reads **32**.

⚠ **Correction to my first read of this.** It did not surface because of a date — it surfaced as
nothing because **his own 2026-08-24 triage set it `status: deferred`**, reason: *"OFF the EP
critical path... observe mode keeps recording forward verdicts while deferred — the evidence base
grows, nothing is lost."* That entry also wrote its own pull-forward trigger: *"PULLS FORWARD when
the operator wants the observe->on flip decided."* **The system behaved exactly as designed and the
trigger fired the moment he asked.** Nothing was neglected.

## What flipping it would do — 168 recorded verdicts over 45 days in observe

| verdict | n | share | avg member RS | what happens at `on` |
|---|---|---|---|---|
| **join** | 86 | **51%** | 63.0 | folds into an EXISTING theme instead of creating a new one |
| **await_second_sighting** | 53 | **32%** | 68.5 | birth is delayed to a later day |
| **birth** | 26 | 15% | 70.6 | a genuinely new theme, as today |
| **held_floor** | 3 | 2% | 29.3 | blocked outright — genuinely weak |

**Expected effect: fewer, fuller themes.** Half of today's new births would become members of themes
that already exist — which is the direct remedy for *65% of themes hold five or fewer members* and
*20 themes sit at 2 members, below the engine's own `_PROMOTE_MIN_MEMBERS = 3`*. Almost nothing is
rejected outright (3 of 168).

## ⚠ AND IT CUTS AGAINST STEP 2 — measured, recorded 2026-08-11, not discovered now

**The gate moves theme birth LATER by design** — a first-sighting cohort must wait for a second
sighting. The measured case is the worst possible one for his stated goals:

> The defense theme holding **{PLTR, TSAT, VOYG, AMRC}** — created that evening **BY those four EP
> alerts** — carried an observe verdict of `awaiting-2nd-sighting`. **At `on` it would not have been
> born that night at all.**
> — `docs/analysis/theme_flow_and_the_0931_seam_2026-08-11.md`

**PLTR is one of his seven labelled real EPs.** And a theme created by EP gap-ups *is* goal 2 — the
reflexive lane he named. So:

| | step 1 — right themes | step 2 — early enough |
|---|---|---|
| flip the gate `on` | **helps** — 51% consolidate, churn falls | **hurts** — 32% of births delayed by a day or more |

**That is the real trade, and it is his.** It is not a bug in the gate; it was operator-ruled on
2026-07-27 for a real reason (churn). The point is that the ruling should be made knowing the
trade, which the file itself says.

## What this does NOT answer

- **Whether the trade is worth taking.** The delay is measured in verdicts, not in matured themes —
  nobody has yet checked how many `await_second_sighting` cohorts died vs merely birthed a day later.
  That check is the review's own clause (c) and it has never been run.
- **Whether a middle setting exists** — e.g. join-arm on, wait-arm off. The code has three modes and
  no per-arm control; adding one is a build, not a toggle.

---

# The flip decision — recommendation: FLIP IT ON

The 2026-08-11 objection does not survive the observe data, and the wait arm's record is clean.

## The counter-example resolves — it was a one-day delay, not a suppression

The note that has held this back said the defense theme **{PLTR, TSAT, VOYG, AMRC}** *"would not
have been born that night at all"* at `on`. True for that night. The candidate row says what
happened next:

```
U.S. Government/Defense Spending Surge | verdict: birth | sightings: 2
first_seen 2026-08-04 · last_seen 2026-08-05 · born_date 2026-08-05
```

It was seen again the next day and the verdict resolved to **birth**. At `on` it arrives
**2026-08-05 instead of 2026-08-04 — one day late.** The note described the first-night verdict and
stopped before the resolution.

## The wait arm lost nothing in 45 days

| verdict | n | sightings range | what it means |
|---|---|---|---|
| `await_second_sighting` | **53** | **1 to 1** | **never recurred — one-day corpses, correctly killed** |
| `birth` | 26 | 2 to 8 | all recurred, all birthed |

⚠ **Checked that this is not a broken counter before believing it:** the `sightings` column reaches
**14**, with 107 rows above 1 and 107 rows whose `last_seen > first_seen`. It increments fine. So
all 53 genuinely never came back.

**Zero real themes lost. 53 pieces of noise stopped.**

## The join arm is stopping outright duplication

Of the top 10 join verdicts by sightings, **three name the SAME theme as their join target** —
*Gold & Precious Metals Miners Rotation*, *Government & Defense IT Services Providers*, *Precious
Metals Royalty & Streaming Companies*. The engine is re-minting themes it already has. Others are
plain synonyms: *Major US Passenger Airlines* → *U.S. Domestic Passenger Airlines*; *Lumber &
Building Products Manufacturing-Distribution* → *Building Products & Construction Materials
Manufacturing*.

## ⚠ ONE JOIN NEEDS HIS EYE — the review's clause (b), which only he can answer

```
Emerging Bitcoin & AI Cloud Compute Miners  ->  Bitcoin Mining Equities Momentum Basket
members: APLD, BTDR, CIFR, CLSK, CORZ, GLXY, HUT, IOND, IREN, MARA, NBIS, RIOT, WULF
```

**This is his own #491 case.** He corrected us on 2026-08-04 that the crypto miners are *"converting
into AI infra plays"* — a fundamental shift, not a merge. APLD, NBIS and IREN are the converts.
**Folding them back into a Bitcoin Mining basket may be exactly the wrong join**, and clause (b) of
the calibration review reserves that judgement to him.

## Recommendation

**Flip to `on`.** The join arm stops real duplication, the wait arm cost is one day on real themes
and nothing else, and only 3 of 168 candidates were blocked outright (all at avg member RS 29).

**Mitigation for the one-day step-2 cost: it already exists and is live.** #651's judge-named lane
is independent of this gate and named a theme **11 days** before the engine had it. The gate delays
the engine's own birth by a day; the judge lane routes around it entirely. No per-arm build is
needed on this evidence.

⚖ This is a safeguard/detection change. The recommendation is mine; the flip, and the ruling on the
Bitcoin-miner join, are his.

## What this does NOT answer

- **Whether the join TARGETS are right in general.** One pair is checked above and it is the
  doubtful one. The other 85 joins have not had his eyeball, and clause (b) asks for it.
- **The effect on theme COUNT.** 51% joins should mean fewer, fuller themes, but nobody has
  projected the steady-state board size.
- **Anything after the flip.** The forward check — do consolidated themes mature at the same rate —
  needs a fresh observe period at `on`.
