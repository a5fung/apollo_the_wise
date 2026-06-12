# Model Selection Baseline (SSoT)

**Last reviewed: 2026-06-10** (judge row added — Opus flip) · Next: quarterly (rides the #62 backward-check sweep) · Tasks: #188 (eval), #207 (institutionalize) · Memory: [[feedback_model_selection_quality_over_cost]]

This is the durable record of WHICH model powers each LLM role, WHY, and WHAT WOULD
CHANGE IT. Its purpose is **incremental** quarterly review — diff against this baseline,
don't re-evaluate every model from scratch.

## How to run the quarterly review INCREMENTALLY (do not start from zero)

1. **List what's new since `Last reviewed`:** new Claude releases, new Perplexity tiers,
   price changes. Only these are candidates — the incumbents already won the last round.
2. **Per role, re-run its eval script** (below) on the **Probe Library** (same accumulated
   hard cases) PLUS any new candidate model. The probes are the discriminating tests; the
   easy cases converge across all models and carry no signal.
3. **Diff, don't re-derive:** compare each new candidate to the `Current` row's verdict.
   A row only needs a decision if a new candidate beats the incumbent ON A PROBE.
4. **Append, don't replace:** add any newly-discovered hard case to the Probe Library so
   discriminating power accumulates over time.
5. **A model swap on any scoring/sourcing path = CHANGE_PROCESS + operator sign-off**
   (`docs/setups/CHANGE_PROCESS.md`). The eval is evidence; the flip is a gated decision.

> Quality is PRIMARY, cost is the tiebreaker (`feedback_model_selection_quality_over_cost`).
> Test the strongest candidate head-to-head; never skip it for cost. The cost lever is a
> tighter universe pre-filter (#191), not a weaker model.

## PLAYBOOK — evaluating a new model and executing a flip (end-to-end)

Codified 2026-06-10 from the JUDGE_MODEL Sonnet→Opus flip (the worked example —
eval → labels → registry → deploy → verify, one evening). Every step is
mandatory on a load-bearing scoring path; advisory paths may compress 5–6.

**0. Trigger.** Either (a) the quarterly review fires
(`data_gated_reviews::model_selection_quarterly_review`), or (b) a major model
release lands mid-quarter → pull the review forward AD-HOC for the roles where
quality is load-bearing (don't wait; also don't flip without the steps below).
A new release is a CANDIDATE, never an auto-adoption — pinned registry ids
exist precisely so a vendor release day cannot silently change live grades.

**1. Candidate intake.** New model ids go into `shared/llm_models.py` as
constants FIRST (versioned, e.g. `OPUS_4_9 = "claude-opus-4-9"`); pricing row
added to the Cost reference below. No role flips yet.

**2. Eval on discriminating input.** Run the role's eval script (per-role
table above) over the Probe Library + the current production disagreement
window, candidate vs incumbent. Two hard input rules learned 6/9→6/10:
(a) GROUNDED input only — thin-input divergence is an artifact; (b) input
gaps must be CLOSED first (the dark theme axis made RCAT measure
input-compensation, not model quality — 5 of 17 "disagreements" dissolved
when the input was fixed). If an eval shows models diverging, first ask
whether the INPUT is broken; fix that, re-run, then compare models.

**3. Operator labels.** The agent formats the disagreement table with a LABEL
column (SONNET/OPUS/NEITHER per row + exclusions for contaminated rows) and a
"patterns" read for convenience — **the agent never self-certifies** (HARD-gate
rule). Decision rule: majority of labeled rows wins; Neither/tie rows carry no
signal; an excluded row needs a recorded reason (e.g. #229 contamination).

**4. Decision + registry commit.** Winner → the role constant in
`shared/llm_models.py`, in its OWN commit citing the eval doc. Pin rule: if
the winning version should NOT flip every role sharing the family constant,
use a versioned pin for this role (`SONNET_4_5` precedent) — per-role
independence is the point of role constants. The `[5i/7]` deploy gate keeps
ids registry-only.

**5. Operational budgets move WITH the model.** A slower model behind an
unchanged timeout converts the quality win into fail-open noise — check and
raise the role's call timeout / gather budgets in the same commit (judge flip:
15→25s call, 60→110s post-loop; the eval's only ERR row was an Opus timeout).

**6. Record + verify-live + flip-back.** Same evening: baseline row updated
here (with the "what would FLIP it" condition), verdict appended to the eval
doc in `docs/analysis/`, change-log entry below. After deploy: verify the
first real production call on the new model (latency + fallback/error rate in
the role's decision/audit rows). The flip-back is always one registry commit —
record the condition that would trigger it, then watch it for a week.

## Decisions (per role)

| Role | Current model | Candidates tested (last review) | Verdict / evidence | What would FLIP it | Eval script |
|---|---|---|---|---|---|
| **Catalyst grade** (the EP quality grade) | `claude-sonnet-4-6` | Haiku 4.5, Sonnet 4.6, Opus 4.8 | CONVERGE on identical grounded input — the lever is the INPUT (sourcing #187), not the model. Production false-`strong` came from grading RAW headlines, fixed by grounding, not by a bigger model. | A new model that diverges UP in quality on the grounded-summary grade (won't happen unless the task changes). | `scripts/eval_catalyst_models.py` |
| **Materiality judgment** (rule 5: deal magnitude vs market cap; baked into the grade prompt) | `claude-sonnet-4-6` | Sonnet 4.6, Opus 4.8 | CONVERGE. Controlled deal/cap sweep: both MONOTONIC, both nail the RUM anchors, divergences tiny + mid-band + BIDIRECTIONAL. Opus = 6× cost for zero measurable edge. The hard-reasoning task where power "should" matter — it doesn't here. | A new model that is monotonic AND sharper on the 5–20% mid-band where Sonnet is fuzzy (test on the sweep + operator-labeled mid-band cases). | `scripts/eval_materiality_models.py` |
| **Catalyst SOURCING summary** (Perplexity grounded answer feeding the grade) | `sonar-pro` (`collector.search_news_perplexity`) | sonar, sonar-pro, sonar-reasoning-pro, sonar-deep-research | KEEP sonar-pro. Tier choice UNDECIDABLE on the 6/5 cohort (N=1 hard case). The cheaper tiers CONFABULATE the hard case (RUM → fake "Together AI" deal) — the dangerous failure mode for this pipeline. sonar-pro's conservatism (honest miss, no fabrication) is safer. **The real sourcing fix is #187 EDGAR**, not the Perplexity tier. | A tier that beats sonar-pro on the RUM-class confab probes **and** has a LOWER confabulation rate on clean no-catalyst controls (the control cohort #207 must build first). Latency must be < ~10s for the live scan (deep-research's 120s is out). | `scripts/eval_sourcing_perplexity.py` |
| **Catalyst cross-validation** (one-word GAME_CHANGER/STRONG/ROUTINE, `ep_detector:429`) | base `sonar` | (covered by the sourcing run) | KEEP base sonar. The earlier idea to bump → sonar-pro is CONTRA-indicated: sonar-pro confabulated on the RUM probe. | Same as sourcing row. | `scripts/eval_sourcing_perplexity.py` |
| **Catalyst sourcing — INDEPENDENT channel** (Gemini grounded search, #186) | none live (CANDIDATE) | gemini-2.5-flash (pro untested — 429) | CANDIDATE for ADDITIVE shadow grounding. On the unknown/coverage-gap cohort flash found REAL catalysts 4/4 incl. **SE (foreign 6-K filer EDGAR is blind to)** = unique non-8-K value. BUT confabulates on truly catalyst-less rows (PGY → fake earnings beat) → additive only, never authoritative. | A clean confab-rate run (#207) showing recall > confab cost on no-catalyst controls → wire as async shadow input (CHANGE_PROCESS). Free API tier 429-throttles → needs PAID tier for prod volume + the pro comparison. | `scripts/eval_sourcing_gemini.py` |
| **Theme membership validation** (Mon/Wed/Fri member-fit prune, `theme_engine._validate_theme_membership`) | `claude-sonnet-4-6` (was Haiku 4.5 until 2026-06-06) | Haiku 4.5, Sonnet 4.6 | SWAP Haiku→Sonnet (#213). Haiku misread narrowing momentum/driver qualifiers in theme names (the "AI" in "AI Memory & Storage") as membership filters → falsely evicted core sector members (SNDK/SIMO/AXTI). On the SAME prompt, Sonnet keeps them while still removing genuine mismatches (CAR wrong-industry; XOM/CVX integrated-majors from pure-play frac) — **deterministic across 4 runs**. Model was the lever, not the prompt. | A model that falsely removes core members on a driver-qualifier theme name (rerun the eval). Residual: both models over-prune the borderline optical name OPTX — a future surgical prompt-debias (NOT broad "keep when same-domain") would address it, gated on a clean cohort. | `scripts/eval_theme_validation_model.py` |
| **Theme discovery / narrative synthesis** (#167) | (record at next review) | — | NOT YET BASELINED — add when #167 narrative lane is reviewed. | — | — |
| **EP Holistic Grade Judge** (ADR 0011 — the load-bearing paper grade authority since 6/10) | `claude-opus-4-8` (was Sonnet 4.6 until 2026-06-10) | Sonnet 4.6, Opus 4.8 | SWAP Sonnet→Opus (#252). Operator-labeled CLOSED-GAP eval (grounded corpus + lit Lane-2 theme axis, 36 alerts → 17 disagreements): **Opus 9 · Sonnet 2 · Neither 4 · tie 1** (`docs/analysis/judge_model_eval_closed_gap_2026-06-10.md`). Operator pattern: Opus right on decisiveness in BOTH directions (KSS/KTOS severity floors, NOW/PGY/TNDM cuts, DELL/TTAN/SKM/AVAV holds-or-reads-the-real-catalyst); Sonnet's park-at-MODERATE disposition labeled wrong 9 times. The 4 Neither rows are all tier-only promote splits (PHR/ASAN/CHA) + the AGX contract oddity. Context: 5 of the 6/9 dark-axis disagreements DISSOLVED from input alone — input remains the bigger lever (#210), but on equal input Opus won the labels decisively. Cost gap small ($5/$25 vs $3/$15); quality-over-cost on the one load-bearing grade path. Live latency budgets raised with the flip (judge timeout 15→25s, post-loop 60→110s) — watch the fallback-authority rate. | A model that beats Opus on the labeled disagreement probes, or a sustained rise in judge fail-open/timeout rate that the 25s budget can't absorb (re-eval latency-vs-quality). | `scripts/eval_judge_models.py --grounded` |

## Standing test-case source: the production UNKNOWN / coverage-gap cohort

The richest, self-refreshing source of HARD probes is the real production cohort where
sourcing/classification could NOT confirm a catalyst — the live analogue of the RUM probe.
Pull it read-only with **`scripts/dump_unknown_cohort.py [--days N] [--json /tmp/unknown_cohort.json]`**
(feeds `eval_sourcing_perplexity.py`). Three forward-growing signals (see [[feedback_label_unknown_not_none]]):

- **`catalyst_type = 'unknown'`** — classifier couldn't name a fire type (#155/#190; fwd ~5/30).
- **`fire_status` non-fire** — `unknown` / `pre_catalyst_anticipation` / `no_fire_confirmed` / `real_unknown` (#201; fwd 6/5).
- **catalyst-text disclaimer** — Perplexity returned "not clearly identified" / "no specific catalyst found" (the SOURCING-MISS signal; available historically).

**Each is a CANDIDATE probe, not a labeled one** — adjudicate vs the actual filing before scoring a model (the RUM lesson): TRUE-unknown (no real catalyst) → staying unknown is CORRECT; MISSED-catalyst (real, sourcing gap) → a model/tier that surfaces it *verified vs filing* is a WIN. As the classifier/fire columns accrue, promote the clearest adjudicated cases into the fixed Probe Library below. (First pull 2026-06-05: N=14/120d — incl. RUM, and several `strong`/`game_changer` grades with "no catalyst found" text = false-positive candidates that also feed #189/#201.)

## Probe Library (the discriminating hard cases — accumulate, never reset)

Easy cases (clear earnings beats: TTAN/AGX/DELL/SNOW) converge across all models and carry
**no** discriminating signal — don't waste the review on them. These are the cases that
actually separate models:

- **RUM 2026-06-04 — sourcing CONFABULATION probe (GOLD).** Real 8-K (items 7.01/9.01,
  verified via `collector.get_sec_recent_filings`): a multi-year **$270M agreement with an
  UNNAMED third-party cloud customer** who buys dedicated GPU cloud capacity **FROM Rumble**,
  NVIDIA Blackwell B300. Failure mode: `sonar` + `sonar-reasoning-pro` fabricate *"an
  agreement with Together AI, compute as-a-service"* (wrong counterparty, no $270M) that
  merely contains the nvidia/blackwell keywords. `sonar-pro` honestly misses (flags the
  Pomerantz item). Only `sonar-deep-research` surfaces the real $270M. **LESSON: always
  adjudicate any "FOUND" against the actual filing — a keyword match is NOT a find.**
- **Materiality monotonicity sweep.** A fixed $250M deal swept across market caps
  (100% / 20% / 5% / 1% / 0.2% of cap) must produce NON-INCREASING grade (game_changer ≥
  strong ≥ routine). Non-monotonic = the model can't reason about materiality. Plus the two
  RUM anchors ($270M @ $2.5B → strong; @ $600B → routine). Ground-truth-free discriminator.
- **PGY 2026-06-04 — imperfect control** (a real $600M securitization existed → muddy). #207
  must build CLEAN no-catalyst controls (pure technical/short-squeeze, no 8-K, no earnings)
  to measure confabulation RATE — the cost the "winner" tiers hide.
- **AKTS 2026-06-12 — STALE-CATALYST freshness probe (operator-labeled, judge's first wrong
  live promote).** +11.9% gap, corpus = web-only Perplexity (`has_direct_source=false`, no
  8-K/wire that day); the synthesis surfaced the **May-2024** Lilly partnership ($60M upfront,
  $1.1B = milestones) UNDATED as "the clearest catalyst" + ticker confusion vs delisted
  Akoustis. Judge promoted MODERATE→HIGH `materiality=transformative` while itself noting
  verifiability concerns. Correct verdict: driver UNIDENTIFIED → MODERATE at best. Probes:
  (a) does the model demand a DATE before attributing a driver; (b) does
  `has_direct_source=false` + big-materiality trigger skepticism or promotion. Rubric/grade
  prompt v3 (`v3-2026-06-12-catalyst-freshness`) encodes the rule — this probe is its
  regression test.

## Cost reference (as of 2026-06-05, $/1M tokens in/out)

| Model | in | out | notes |
|---|---|---|---|
| claude-haiku-4-5 | 0.80 | 4.00 | |
| claude-sonnet-4-6 | 3.00 | 15.00 | **grading + materiality incumbent** |
| claude-opus-4-8 | 5.00 | 25.00 | **judge incumbent since 6/10** (was listed $15/$75 — 3× stale, corrected with #257); no edge on grading/materiality (those converge on input), decisive edge on the holistic judge per operator labels |
| perplexity sonar | ~1 | ~1 | cross-validation incumbent; fast (2–3s) |
| perplexity sonar-pro | ~3 | ~15 | **sourcing incumbent**; conservative (safer) |
| perplexity sonar-reasoning-pro | ~2 | ~8 | confabulated RUM; not adopted |
| perplexity sonar-deep-research | ~2/~8 + search/reason fees | | 120s + 10k-tok essays — not hot-path |

## Change log

- **2026-06-10 (EP holistic judge swap, #252):** Sonnet→Opus 4.8 for `JUDGE_MODEL` — the
  load-bearing paper grade authority (flipped load-bearing the same day). Operator-labeled
  closed-gap eval (grounded + lit Lane-2 theme axis, 36 alerts → 17 disagreements):
  **Opus 9 / Sonnet 2 / Neither 4 / tie 1** (`docs/analysis/judge_model_eval_closed_gap_2026-06-10.md`).
  Two durable lessons promoted into the Playbook above: (1) close INPUT gaps before comparing
  models — 5 of the 6/9 dark-axis disagreements dissolved from input alone (the #210 lever);
  (2) move operational budgets with the model — judge timeout 15→25s, post-loop 60→110s,
  because the eval's only ERR was an Opus timeout. Registry commit `6b53709`.

- **2026-06-06 (theme membership validation swap, #213):** Haiku→Sonnet for `_validate_theme_membership`. Root: Haiku read the narrowing "AI" qualifier in "AI Memory & Storage" as a membership filter and evicted SNDK/SIMO (NAND flash) — recurring, operator-noticed. Isolating eval `eval_theme_validation_model.py` ran BOTH models on the UNCHANGED prompt over a two-sided cohort (false-removal side: storage names keep; genuine-removal side: CAR wrong-industry + XOM/CVX integrated-majors-fail-pure-play remove). Sonnet 3/4 / Haiku 2/4, **stable across 4 runs**; Sonnet fixes the bug AND preserves both genuine removes. The prompt de-bias was the advisor-flagged high-risk half (reintroduces oil&gas mis-clustering, no clean cohort right now) → DEFERRED; model swap alone is the fix. `THEME_MODEL` already defined, now used. Shipped with the #213 operator-protection shield (bypassed-cooldown pairs never re-removed). Theme-NAMING defect (names narrower than the RS cluster — the oil&gas root) filed separately.
- **2026-06-05 (Gemini sourcing eval, #186):** evaluated Gemini grounded Google-Search as an INDEPENDENT sourcing channel (reframed from "3rd grade-validator" — graders converge on grounded input). `eval_sourcing_gemini.py` @0742c36. On the unknown/coverage-gap cohort, gemini-2.5-flash found real catalysts 4/4 (BHVN/SE/BZH/LIVN) incl. **SE — a foreign 6-K filer EDGAR's 8-K-only fetch is structurally blind to** (→ #208). Confabulates on catalyst-less controls (PGY) → ADDITIVE-only, never authoritative. gemini-2.5-pro UNTESTED (free tier 429-throttles even flash; pro needs a paid tier — but confab is a precision not horsepower issue, so pro is a footnote). Verdict: CANDIDATE for async shadow grounding, gated on a clean confab-rate run (#207) + paid tier, via CHANGE_PROCESS. Side-finds: SE→#208 (EDGAR 6-K gap); SMU/SMCZ leveraged/inverse ETFs mis-graded→#209 (universe hygiene).
- **2026-06-05 (initial baseline, #188):** grading=sonnet, materiality=sonnet,
  sourcing=sonar-pro, cross-val=base sonar — NO swaps. Grade + materiality both converge
  (lever is input/prompt, not model). Sourcing tier undecidable on N=1 cohort; cheaper
  tiers confabulate the RUM hard case; #187 EDGAR is the load-bearing sourcing fix. Advisor
  caught the keyword-FOUND trap (without the 8-K adjudication, a swap to a confabulating
  tier would have shipped). Eval scripts: `eval_catalyst_models.py` @6098a1b,
  `eval_materiality_models.py` @6429823, `eval_sourcing_perplexity.py` @f81e994.
