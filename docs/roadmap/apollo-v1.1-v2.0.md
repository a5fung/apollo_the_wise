# Apollo Next Phase — v1.1 (fast-follow) & v2.0 (tier-one trader)

**Status: APPROVED — operator aligned 2026-06-11** (amended same day with the adopted
points from an external Gemini review — see §Amendments). Drafted 2026-06-10 (the
judge-flip day), from the operator-requested critique of Apollo as an automated EP
system + the founding thesis (LLMs replicating the human discretionary factor, riding
the capability curve). This is the successor program to North Star (CLOSED 2026-06-11,
never reopened — everything after lives HERE). #268 (W1) is unblocked.

How to use this doc: it is the durable map, not the task tracker. Items promote into
#-tasks when execution starts (filing rule unchanged); this doc gets a monthly review
ride-along (first: the 8/1 quarterly model review window). Dates on v1.1 are
sequencing intent, not commitments; v2.0 carries horizons, not dates.

---

## The diagnosis this program answers (from the 6/10 critique)

1. **The realized paper record (−$9.5k, ~23% win, N≈30) does not test the current
   system** — every realized trade predates the judge; +2.27R of it is IEX fill
   artifact; N is meaningless for a fat-tail strategy. The system worth evaluating
   started existing 6/10. *Nothing has yet measured it.*
2. **The expectancy leak is concentrated in entry/exit mechanics, not selection** —
   1-min ORB stops inside the opening noise band (KLAR 8min, DELL 6min, NVTS 6min
   stop-outs); winners under-harvested vs their excursions (IBM peaked +30%, exited
   +3.5% on the trail with a 8/26-share partial). Selection got two months of
   iteration; the entry got its initial implementation.
3. **Three improvement axes, unevenly built** (the founding-thesis frame):
   - **Axis 1 — model capability**: rides the vendor curve; registry + playbook
     make a flip a one-evening evidence-gated event (proven 6/10, Sonnet→Opus 9–2).
     *Strong. Free compounding.*
   - **Axis 2 — what the judge can see**: news/sourcing largely closed (#210);
     **chart structure is the open frontier** (judge grades the news better than
     the chart); intraday/tape context absent. *Half-built.*
   - **Axis 3 — accumulated experience**: LLMs don't learn Apollo's outcomes
     between releases — experience must be SYSTEM memory (labeled corpus,
     precedent retrieval, rubric distillation). *The under-built axis. The version
     of Apollo that worries a discretionary trader is a strong model reading a
     complete picture with five hundred labeled precedents behind it.*
4. **Boundary held**: LLM judgment lives at decision points (minutes/days);
   seconds-scale execution stays mechanical structure. The thesis must not creep
   into the milliseconds.

---

# PART I — Apollo v1.1 (fast-follow: days→weeks after 6/12)

Sequenced waves. Each item ships with its evidence gate; nothing touches live
behavior without the standing discipline (CHANGE_PROCESS, shadow-first, N≥10–30,
operator sign-off on grade-path/filter changes). The 6/22 live-money decision is
DECOUPLED — v1.1 work must not destabilize the paper cohort that decision reads.

## v1.1-W1 — Evidence before anything (week of 6/15)

| Item | What / why | Gate / output |
|---|---|---|
| **Judge-era selection replay** (NEW — the highest-value week of work left) | Replay the CURRENT system (Opus judge, lit theme axis, grounded corpus) over ~12 months of alert candidates; simulate ORB outcomes on SIP-reconstructed fills (#180 infra). Pieces all exist: `judge_backfill_replay`, grounded reconstruction, backtester, SIP replay. | N=hundreds expectancy estimate of the system we actually have, BEFORE real money. Caveats logged (lookahead-safe corpus, point-in-time themes via `as_of`). |
| **Pre-committed 6/22 kill/scale criteria** (NEW) | Rolling 30-trade expectancy bands + max-drawdown lines defined BEFORE going live, so live results get judged by rules, not mood — in either direction. | One page in `docs/setups/safeguards.md`; operator sign-off. |
| North Star closure mechanics | #247/#252 verify-live → #240 closed; CHANGELOG/ADR/roster/memory. | Fri 6/12 (committed). |

## v1.1-W2 — The entry-mechanics program (the #1 leak; weeks of 6/15–6/29)

The same rigor the judge got, aimed at entry geometry. All replay/shadow-driven —
the intraday data to do this is already collected (mi_intraday telemetry, dead-zone
and window-extension analysis scripts exist).

- **OR-window adaptivity**: 1-min vs 5-min vs first-pullback entry by gap
  size/character; the violent-open cohort (KLAR/DELL/NVTS class) is the test set.
- **Stop geometry study**: ORB-low vs ATR-floor vs day-low by gap bucket — measure
  noise-stop rate vs give-back. (9M Day-2 already uses prior-day low; MAGNA53 is
  the open question.)
- **Skip-wide-open filter**: when the opening range is already >X% of ATR, the
  bracket is structurally bad — pass or switch entry technique.
- Gate: replayed N≥30 per change; ship one change at a time behind per-strategy
  flags; paper-verify before 6/22 only if cleanly separable, else post-decision.

## v1.1-W3 — Exit & management upgrades (weeks of 6/22–7/6)

- **Winner-harvesting tune**: partial size (the 8-of-26-share IBM partial),
  trail selection (10 vs 20MA by character), excursion-capture metric
  (`capture_pct` already computed in the dashboard — promote it to the weekly
  review as THE management KPI).
- **Time-stop refinement** on the meanderer cohort (#91 data accruing).
- Gate: backtest on closed-trade history + replay; management changes are
  trade-state code → full integration-test discipline (#151 harness).

## v1.1-W4 — Judge sight, first expansion (#267; week of 7/6)

- **Chart-vision input**: point-in-time matplotlib renderer from `mi_daily_closes`
  (NOT fetched charts — lookahead-safe for replay), image block in
  `grade_holistic`, chart-structure rubric axis (prior base, linearity, extension).
  Pennies per alert; fail-open to text-only.
- Gate: with-vs-without-chart replay over the judged cohort; operator labels the
  verdict diffs (the exact 6/10 model-flip playbook — this is an input change,
  playbook step 2).
- **Conviction-scaled sizing (shadow)**: judge tier+confidence → size multiplier,
  logged as telemetry only. The judge currently gates binary; tier-one traders
  size by conviction. Live flip gated on the selection replay + accrued shadow.

## v1.1-W5 — Experience seed (axis 3 v1; weeks of 7/6–7/20)

- **Labeling cadence**: the weekly verified-miss review (#219) + ground-truth
  corpus (#254) become a RITUAL — ~15 min/week of operator labels (the 6/10 eval
  proved the unit economics: 17 labels → a model decision).
- **Precedent retrieval v1 (#255)**: at grade time, retrieve the K most similar
  PAST judged alerts (kind='review' labels only — hindsight-segregation rule) and
  inject as few-shot context. Start crude (catalyst-type + sector + gap-bucket
  match); embeddings later.
- Gate: shadow — log retrieved precedents alongside verdicts; measure verdict
  shift + operator-labeled improvement before load-bearing.

## v1.1 engineering rail (parallel, already in flight)

#256 W2 process split (~6/17 or post-6/22) + W3 staging pipeline · #266
event-driven theme validation · #226 Lane-2 canonization (~6/16) · #215 validation
de-bias (post-#214 cohort) · dashboards db-flip (7/15 gate) · hygiene queue
(#261 scripts reorg, #259 decorator adoption, #216 jsonb root-fix post-6/22,
#258 ensure_schema, #265 residuals).

---

# PART II — THE PHASE-2 PROGRAM (revised in place 2026-07-05, #419 — Fable planning block 2)

**Phase 2 begins at the v1.0 declaration** (#418 / #425 walk, window ~7/20–7/31; the finish line
is `v1-closeout-productization.md` §2). Its intake is exact: the **79 open tasks dispositioned
PHASE-2** at the #418 walk, absorbed pillar-by-pillar below (every task ID appears exactly once;
re-dated in PLAN.md per the milestone map — no more July date-parking). The v1.1 waves (PART I)
fold in: W3 exit-tuning → P3, W4 chart-vision → P2, W5 experience-seed → P1; W1/W2 closed.

**Program milestones (dated, trigger-armed — same discipline as the v1.0 glide path):**

| Milestone | Date | What lands / decides | Trigger |
|---|---|---|---|
| **M1 — Judge-axes checkpoint** | **7/18** | The ONE batched event: theme+structure axis shadows read → batched regrade eval → #335 flip decision + #299 subset + #329 composition | dated sitting (already standing) |
| **M2 — First setup graduations** | **7/14–7/25** | #395 coil GO/NO-GO (7/14) · #397 HTF GO/NO-GO (7/18) · S-E deprecations verified in the digest | evidence gates in the tasks |
| **M3 — Quarterly reviews cluster** | **8/1** | #207 model review (Sonnet-5 evidence banked 7/5) · this doc's first monthly ride-along · crypto SMA90 history completes → readiness verdict flips (E1) | dated tasks + registry |
| **M4 — Management program start** | **8/15** | #306 STEP-3 exit-tune decision executed → P3 management-judge design kickoff (the money pillar) | gated on STEP-2 sweep + operator decision |
| **M5 — H2 gate** | **10/1** | P3/P5 H2 items activate; #381 swallow-baseline ZERO (the D-8 dated milestone) | horizon boundary |

What "tier-one" means, measurably: (1) selection a strong discretionary trader
would respect (judge precision on labeled cohorts), (2) sizing that scales with
conviction and regime, (3) management that captures >50% of winner MFE
consistently, (4) adaptation across regimes without re-tuning panic, (5) a review
loop that converts every outcome into compounding skill. Pillars below map to
those five. Horizons: **H1 = Q3 2026, H2 = Q4 2026 (aligns with the existing
theme-gating Track-B endpoint), H3 = 2027 / aspirational.**

## P1 — The Experienced Judge (axis 3 at scale) · H1→H2

**Absorbed (12):** #255 #299 #301 #307 #337 #212 #230 #233 #269 #215 #207 #308. First gate: M1
(the eval/labeling spine); #307's weekly labeling ritual is the corpus engine and starts
immediately post-declaration.

The step change: from "smart at each decision" to "experienced at this craft."

- **Precedent corpus at scale**: every judged alert + outcome + operator label
  becomes a retrievable case (pgvector is already in the stack); grade-time
  retrieval matures from rule-match to embedding similarity over (catalyst,
  structure, theme-state) — "the last 12 times we saw this shape, here is what
  was true."
- **Self-review → rubric distillation loop**: weekly, the judge re-reads its own
  graded cohort WITH outcomes and drafts rubric amendments; operator signs off;
  amendments version-controlled (the rubric becomes a living document with a
  changelog, like the setups SSoT). The system journals like a trader.
- **Ensemble/uncertainty judging**: two models grade independently; divergence =
  uncertainty signal → size down or abstain (the 6/10 eval showed divergence is
  informative). Cost-bounded to HIGH-tier candidates.
- **Model-curve riding**: the playbook (`model_selection_baseline.md`) executes
  per major release — already institutionalized; v2.0 adds the probe library
  growing automatically from mislabeled-outcome cases.
- *Feasibility: all buildable today; the work is corpus accumulation + retrieval
  quality. The bet is that experience compounds — by H2 the judge should cite
  precedents in its rationale.*

## P2 — Full Sight (axis 2 complete) · H1→H2

**Absorbed (17):** #367 #368 #322 #328 #329 #330 #331 #332 #333 #335 #343 #309 #167 #210 #211
#235 #416. First gate: M1 (7/18) — the axis flip decision; the #210/#211 sourcing backbone is
this pillar's data spine (LLM = judge, never discoverer).

- **Multimodal decision context**: daily chart (v1.1-W4) → intraday chart at
  entry decision → sector/peer chart + SPY/QQQ context panel. The judge sees what
  the human sees at the moment the human would look.
- **Real-time narrative radar**: the nightly synthesis lane upgraded to intraday —
  co-moving cohort detection on the live tape (the RCAT drone-cohort class,
  caught at 10:00 instead of 18:05). Feeds the judge's narrative axis same-day.
- **Tape features at decision points**: opening-range character, premarket volume
  curve vs the minute-volume baselines (already collected), spread/liquidity
  flags — as STRUCTURED payload fields, not tick-level reaction (the
  milliseconds boundary holds).
- **Negative-catalyst sight (#238)**: dilution/offering filings as a downgrade
  axis — the judge currently sees mostly positive-catalyst sources.
- *Feasibility: intraday narrative radar needs streaming news + cohort detection
  at minutes cadence — real engineering, H2. The rest is incremental.*

## P3 — The Manager (the second judge) · H2

**Absorbed (3):** #306 #310 #414. First gate: M4 (8/15) — the #306 STEP-3 decision seeds the
management program; the 18%-MFE-capture STEP-0 number is the pillar's baseline KPI (bar >50%).

The money in this methodology is in the management. Today management is mechanical
(bracket, partial rule, MA trail, time-stop). The step change is a **management
judge**: once per day (and on triggers: gap against, +2R excursion, theme-state
change), an LLM pass over each open position — chart, thesis state, theme health,
days held — choosing among the BOUNDED action set (hold / partial / trail-tighten /
exit / add-not-allowed). Same architecture as the grade judge: fail-open to the
mechanical rules, decision trace, operator-visible rationale, shadow→load-bearing
promotion gates.

- **Structure-based stops via PIVOT identification** (operator principles,
  2026-06-11 — SSoT: `docs/methodology/pivots-and-stock-character.md`): a pivot
  is ANY reasonable risk-reference point serving BOTH sides (locates the entry,
  IS the stop) — MAs/lows are the computable tier; congestion/resistance zones
  are the structural tier chart-vision sees. AND pivots are conditioned on the
  STOCK'S OWN CHARACTER (some names resolve pullbacks at the 10MA, others the
  20MA, others undercut habitually; durations differ — the NBIS markup is the
  canonical example): per-ticker character profiles from the name's own
  history, never one global parameter. The management judge proposes against
  the stock's OWN respected pivots; mechanics execute.
- **Conviction sizing matured**: judge-tier sizing (v1.1 shadow) → portfolio-aware
  scaling (drawdown-adaptive risk curve; the dual-account + per-strategy
  multiplier plumbing already exists).
- *Why step-change: this is where Qullamaggie says the money is, and it is
  currently Apollo's most mechanical layer. Feasibility: high — it is the grade
  judge pattern applied to a second decision point. The gate discipline matters
  most here (trade-state mutations).* 

## P4 — The Multi-Setup Book · H1→H2

**Absorbed (23):** Family-A program #402 #327 #353 #354 #356 #396 #397 #357 #297 #283 #385 #386
#394 #395 #358 + #311 #314 #146 #168 #170 #178 #359 #316. First gates: M2 (the 7/14 + 7/18
GO/NO-GOs). Per #418 D-2/D-4: 9M = a stock CONDITION feeding these setups (never a tradeable
setup); flag_continuation deprecated in favor of HTF + Anticipation; wick_fill = backlog idea.

Diversify the edge across setups and regimes — one gap-long strategy is one
regime's book.

- **Tightness→expansion graduation**: the five entry-technique detectors have been
  accruing shadow data since May (7/15 evidence gate). Flag/coil entries are
  structurally gentler than day-1 ORB (defined risk vs a base, not vs opening
  chaos) — prior: some will beat ORB expectancy. Per the operator's 6/8 direction:
  **per-setup judges sharing components, not one universal judge.**
- **9M-universe → flag-entry pipeline**: Bonde's actual model (9M day = universe
  admission; entry = later tightness), already filed as telemetry-first.
- **Parabolic short (TI1)**: the first short tactic = the first counter-regime
  book. Detector exists; entry/management/borrow mechanics are the build.
  *Shorts are operationally harsher (borrow, squeeze risk) — H2, evidence-first.*
- **Regime-adaptive book selection**: breadth/regime state modulates which setups
  are active and at what risk (regime detection + breadth tools exist; today they
  only halve risk).

## P5 — Capital & Autonomy Ladder · H2→H3

**Absorbed (3):** #312 #415 #197. First gate: M5 (H2) — nothing here activates before the
allocator shadow accrues contested days (#415 registry re-review 8/4).

- **Unified allocator live**: `unified_allocator_shadow` (already running) becomes
  the capital brain — per-strategy risk budgets from accrued expectancy +
  correlation, Kelly-fraction-capped.
- **The autonomy ladder formalized**: per strategy, the promotion path
  shadow → paper → live-proposed (operator confirm) → live-auto-reduced →
  live-auto-full, each step an evidence gate in the strategy registry (the
  `phase` column already encodes most of this; v2.0 adds the criteria and the
  automatic *demotion* on breach).
- **Scaling**: multi-account, larger size, slippage telemetry feeding sizing caps
  (edge capacity is finite; measure it before it measures you).
- *Aspirational end-state: the operator sets risk appetite and reviews labels;
  Apollo runs the book inside hard guardrails.*

## P6 — Institution-grade operations (the rail under everything) · H1→H2

**Absorbed (21):** #313 #379 #381 #340 #348 #363 #407 #258 #265 #216 #176 #281 #338 #239 #274
#384 #121 #334 + operator surfaces #194 #185 #315. Dated: #381 swallow-baseline ZERO = M5
(10/1); #121 HTML migration early (kills the Telegram fence-bug class); the dashboards carry
their standing trigger (Apollo-Trades tab at ≥10 closed live trades).

- #256 completed: execution/intelligence split + staging pipeline (no commit
  reaches prod execution unbooted); per-service deploys; DR matured.
- **Replay-everything CI**: the selection replay, entry sims, and judge evals run
  as scheduled regression jobs — a methodology change that degrades replayed
  expectancy fails loudly before deploy (the trading equivalent of the test suite).
- **Cost governance**: per-role LLM spend telemetry vs P&L; the cost lever stays
  "tighter universe," never "weaker model."

---

## Amendments from external review (Gemini, adopted 2026-06-11)

1. **W2 skip-wide-open: ATR-relative threshold as the starting hypothesis.** Evaluate
   the opening candle's range against trailing ATR20; first 1m/5m candle spanning more
   than ~**0.25–0.30 × ATR20** ⇒ the bracket geometry is mathematically broken (stop
   distance caps R-multiples at normal sizing) → route to a first-pullback entry
   matrix instead of skipping outright. The exact threshold is REPLAY-DECIDED, not
   adopted on authority — but it's the right *shape* (relative to the name's own
   volatility, not absolute %). Note: the minute data to test this ALREADY EXISTS
   (`mi_intraday_bars`, 120-day retention — the KLAR/DELL/NVTS shakeout cohort is
   in there); W2 needs analysis scripts, not new tracking structures.
2. **W4 chart-vision payload discipline.** Text payload stays the PRIMARY engine;
   the image is strictly a structural filter (overhead resistance, parabolic
   extension). Render simple (price + volume + the 3 MAs, small canvas, no
   decorative indicators) to keep image tokens ~1k. Persist the chart-axis read as
   its own column (`structural_chart_verdict`) so the with-vs-without eval and
   post-6/22 segmentation have clean provenance. Latency note: the hazard is real
   but bounded — the judge already runs post-alert in a budgeted concurrent gather
   (25s/110s), so vision rides the same rails; measure judge latency in
   `ep_grade_decision` after the flip, same as the Opus rollout.
3. **W5 precedent retrieval: temporal-distribution constraint.** K retrieved
   precedents must span distinct multi-week periods — naive attribute matching
   (catalyst-type+sector+gap) would retrieve 3 cases from one hot sector-week and
   inject recency/regime bias, the opposite of "experience." Enforce in the
   retrieval query from v1, not as a later fix.
4. **P3 management judge: bounded-enum contract REAFFIRMED** (independent
   convergence with the original design): the LLM outputs a strict enum
   (HOLD / PARTIAL_TAKE / TRAIL_TIGHTEN / FORCE_EXIT), mechanical layer maps enum →
   deterministic execution. Never free-form order generation; the seconds-scale
   boundary stays un-crept.
5. *Not adopted / already done:* the proposed mi_ep_alerts schema additions already
   exist (shipped via `_ensure_ep_alert_columns`, #247) except
   `structural_chart_verdict`, which lands with #267 (point 2).

## Exploration lanes (E-series — parked ideas with explicit activation triggers, never silent)

- **E1 — Crypto RS as an INFORMATION surface**: the shadow module's designed endpoint — RS/regime
  briefing sections go live when the SMA90 trigger data completes (**~8/1**, M3) and the readiness
  verdict flips. Crypto TRADING stays excluded (below); this is eyes only, operator decision at M3.
- **E2 — Cross-ticker narrative synthesis maturation**: the known capability gap (dev-session
  reasoning ≠ deployed tooling) — Lane-2 narrative (#167) + the questioner/investigator loop
  (#212) converge into a top-down emerging-theme pass. Rides P1/P2 absorbed tasks; called out so
  the gap's closure is explicit, not incidental.
- **E3 — Day-trade capacity unlock**: #316 (Alpaca Rule-4210 rollout) — when confirmed, the PDT
  lockout relaxes via CHANGE_PROCESS and intraday re-entry capacity expands (P4 sizing input).
- **E-intake rule**: new ideas enter HERE with a trigger + evidence gate, not as floating tasks —
  the monthly ride-along (M3 cadence) is the review point.

## What is explicitly NOT in this program

- Tick-level / millisecond tape reaction (boundary holds: judgment at decision
  points, mechanics in the seconds).
- Options overlays, futures, crypto trading — separate theses; not before P5
  maturity.
- Auto-adopting model releases without the playbook (the registry exists to
  prevent exactly that).
- Reopening North Star — its scope is closed 6/12; P2 items that resemble it
  (theme gating maturity) ride the existing Track-B Q4 line.

## Review cadence & governance

- This doc: monthly review (first ride-along: 8/1 = M3). All 79 absorbed items are ALREADY
  #-tasks (PLAN.md, re-dated to their milestone map 7/5) — the board and this program are the
  same list viewed two ways; on any conflict, PLAN.md wins.
- Every grade-path/filter/management change: CHANGE_PROCESS + evidence + operator
  sign-off — unchanged. The autonomy ladder never bypasses the safety line.
- Success metrics reviewed with each phase: replayed expectancy (W1 baseline),
  live R-distribution vs replay, MFE capture %, judge precision on labels,
  fail-open rates, miss-rate on labeled should-have-takens.
