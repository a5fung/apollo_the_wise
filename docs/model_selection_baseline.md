# Model Selection Baseline (SSoT)

**Last reviewed: 2026-06-05** · Next: quarterly (rides the #62 backward-check sweep) · Tasks: #188 (eval), #207 (institutionalize) · Memory: [[feedback_model_selection_quality_over_cost]]

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

## Decisions (per role)

| Role | Current model | Candidates tested (last review) | Verdict / evidence | What would FLIP it | Eval script |
|---|---|---|---|---|---|
| **Catalyst grade** (the EP quality grade) | `claude-sonnet-4-6` | Haiku 4.5, Sonnet 4.6, Opus 4.8 | CONVERGE on identical grounded input — the lever is the INPUT (sourcing #187), not the model. Production false-`strong` came from grading RAW headlines, fixed by grounding, not by a bigger model. | A new model that diverges UP in quality on the grounded-summary grade (won't happen unless the task changes). | `scripts/eval_catalyst_models.py` |
| **Materiality judgment** (rule 5: deal magnitude vs market cap; baked into the grade prompt) | `claude-sonnet-4-6` | Sonnet 4.6, Opus 4.8 | CONVERGE. Controlled deal/cap sweep: both MONOTONIC, both nail the RUM anchors, divergences tiny + mid-band + BIDIRECTIONAL. Opus = 6× cost for zero measurable edge. The hard-reasoning task where power "should" matter — it doesn't here. | A new model that is monotonic AND sharper on the 5–20% mid-band where Sonnet is fuzzy (test on the sweep + operator-labeled mid-band cases). | `scripts/eval_materiality_models.py` |
| **Catalyst SOURCING summary** (Perplexity grounded answer feeding the grade) | `sonar-pro` (`collector.search_news_perplexity`) | sonar, sonar-pro, sonar-reasoning-pro, sonar-deep-research | KEEP sonar-pro. Tier choice UNDECIDABLE on the 6/5 cohort (N=1 hard case). The cheaper tiers CONFABULATE the hard case (RUM → fake "Together AI" deal) — the dangerous failure mode for this pipeline. sonar-pro's conservatism (honest miss, no fabrication) is safer. **The real sourcing fix is #187 EDGAR**, not the Perplexity tier. | A tier that beats sonar-pro on the RUM-class confab probes **and** has a LOWER confabulation rate on clean no-catalyst controls (the control cohort #207 must build first). Latency must be < ~10s for the live scan (deep-research's 120s is out). | `scripts/eval_sourcing_perplexity.py` |
| **Catalyst cross-validation** (one-word GAME_CHANGER/STRONG/ROUTINE, `ep_detector:429`) | base `sonar` | (covered by the sourcing run) | KEEP base sonar. The earlier idea to bump → sonar-pro is CONTRA-indicated: sonar-pro confabulated on the RUM probe. | Same as sourcing row. | `scripts/eval_sourcing_perplexity.py` |
| **Catalyst sourcing — INDEPENDENT channel** (Gemini grounded search, #186) | none live (CANDIDATE) | gemini-2.5-flash (pro untested — 429) | CANDIDATE for ADDITIVE shadow grounding. On the unknown/coverage-gap cohort flash found REAL catalysts 4/4 incl. **SE (foreign 6-K filer EDGAR is blind to)** = unique non-8-K value. BUT confabulates on truly catalyst-less rows (PGY → fake earnings beat) → additive only, never authoritative. | A clean confab-rate run (#207) showing recall > confab cost on no-catalyst controls → wire as async shadow input (CHANGE_PROCESS). Free API tier 429-throttles → needs PAID tier for prod volume + the pro comparison. | `scripts/eval_sourcing_gemini.py` |
| **Theme discovery / narrative synthesis** (#167) | (record at next review) | — | NOT YET BASELINED — add when #167 narrative lane is reviewed. | — | — |

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

## Cost reference (as of 2026-06-05, $/1M tokens in/out)

| Model | in | out | notes |
|---|---|---|---|
| claude-haiku-4-5 | 0.80 | 4.00 | |
| claude-sonnet-4-6 | 3.00 | 15.00 | **grading + materiality incumbent** |
| claude-opus-4-8 | 15.00 | 75.00 | 5× sonnet; tested, no edge on these tasks |
| perplexity sonar | ~1 | ~1 | cross-validation incumbent; fast (2–3s) |
| perplexity sonar-pro | ~3 | ~15 | **sourcing incumbent**; conservative (safer) |
| perplexity sonar-reasoning-pro | ~2 | ~8 | confabulated RUM; not adopted |
| perplexity sonar-deep-research | ~2/~8 + search/reason fees | | 120s + 10k-tok essays — not hot-path |

## Change log

- **2026-06-05 (Gemini sourcing eval, #186):** evaluated Gemini grounded Google-Search as an INDEPENDENT sourcing channel (reframed from "3rd grade-validator" — graders converge on grounded input). `eval_sourcing_gemini.py` @0742c36. On the unknown/coverage-gap cohort, gemini-2.5-flash found real catalysts 4/4 (BHVN/SE/BZH/LIVN) incl. **SE — a foreign 6-K filer EDGAR's 8-K-only fetch is structurally blind to** (→ #208). Confabulates on catalyst-less controls (PGY) → ADDITIVE-only, never authoritative. gemini-2.5-pro UNTESTED (free tier 429-throttles even flash; pro needs a paid tier — but confab is a precision not horsepower issue, so pro is a footnote). Verdict: CANDIDATE for async shadow grounding, gated on a clean confab-rate run (#207) + paid tier, via CHANGE_PROCESS. Side-finds: SE→#208 (EDGAR 6-K gap); SMU/SMCZ leveraged/inverse ETFs mis-graded→#209 (universe hygiene).
- **2026-06-05 (initial baseline, #188):** grading=sonnet, materiality=sonnet,
  sourcing=sonar-pro, cross-val=base sonar — NO swaps. Grade + materiality both converge
  (lever is input/prompt, not model). Sourcing tier undecidable on N=1 cohort; cheaper
  tiers confabulate the RUM hard case; #187 EDGAR is the load-bearing sourcing fix. Advisor
  caught the keyword-FOUND trap (without the 8-K adjudication, a swap to a confabulating
  tier would have shipped). Eval scripts: `eval_catalyst_models.py` @6098a1b,
  `eval_materiality_models.py` @6429823, `eval_sourcing_perplexity.py` @f81e994.
