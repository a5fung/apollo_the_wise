# Block 3 T2 — LLM-surface hardening (Fable design, 2026-07-11 eve; run early with T1)

**Scope (roadmap §Block 3 T2):** the judge is one of several LLM surfaces. (a) thin-payload
degradation behavior, (b) the theme-engine prompt corpus incl. the ADR 0025 merge-adjudicator
exemplars, (c) the R5 runtime drift band. All design/corpus work — **nothing changes live
behavior**; every flip stays gated where its owning ADR put it.

---

## T2a — Degradation tests: does a starved grader fail conservative or hallucinate?

**Mechanism: 8 degradation cases appended to the T1 corpus** (`scripts/evals/
judge_robustness_corpus_v1.json`, D01–D08) rather than a separate harness — starvation is just
another adversarial class, and folding it in means the SAME eval run + the SAME regression gate
(ADR 0030 [5m/7]) measure it forever, not a one-off study.

The 8 starvation shapes: empty corpus (D01) · retrieval-error artifact as corpus (D02) ·
catalyst-line contradicts the grounded corpus (D03) · one social line under a 30× volume gap
(D04) · all-items-stale corpus (D05) · truncation mid-claim before the numbers (D06) ·
irreconcilable figures between sources (D07) — golden for all seven: **fail conservative**
(`tier_not HIGH`; the driver is unidentified). **D08 is the anti-overcorrection control**: a
thin-but-COMPLETE corpus (one dated primary-sourced 8-K with real acceleration numbers, 20
minutes old) whose golden is `tier_is HIGH` — a judge that learns "thin corpus ⇒ demote" fails
D08, which is exactly the over-skepticism the control exists to catch.

Pass bars: D01–D07 zero-HIGH (hard classes); D08 must pass (control bar). Rides the ADR 0030
C1/C3 cards — no new build.

## T2b — Theme merge-adjudicator golden corpus (gates ADR 0025-C3)

**`scripts/evals/theme_merge_corpus_v1.json` — 14 golden pairs**: 8 REAL verdicts lifted from
the 7/11 live replay (both legit-kill anchors + the 3 real merges + 3 hard distincts) + 6
adversarial synthetics targeting exactly the failure modes a sector-label merger makes:

- **M09** the keyword trap ("AI datacenter power" × "AI memory" — same stem, different industry) → DISTINCT
- **M10** the mirror (different labels, SAME driver: grid equipment × datacenter power) → MERGE — tests the merge direction, not just refusal
- **M11** same-narrative/OPPOSITE-exposure (GLP-1 makers × GLP-1 collateral-damage staples) → DISTINCT — thesis coherence = same *directional* driver
- **M12** textbook parent-child (platform consolidators × zero-trust slice) → PARENT_CHILD
- **M13** nuclear-stem trap (uranium cycle × SMR milestones) → DISTINCT
- **M14** the membership-overlap trap (BTC miners × miners-pivoting-to-AI — SAME tickers, different drivers) → DISTINCT — shared tickers must not force a merge

**Gate wiring:** 0025-C3 (the Stage-B adjudicator build) must pass this corpus — `hard` pairs
at 100%, others ≥85% (an `accept_also` verdict counts as a pass) — BEFORE the live flip; the
result rides the C3 card's DoD. Scoring is the same predicate pattern as ADR 0030 so the T1
harness (C1) can run this corpus with a ~20-line loader variation — one eval mechanism, two
LLM surfaces. Validation/discovery/birth-validation prompt corpora: same pattern, deferred
until those prompts next change (their live behavior is already replay-validated; building
corpora now is speculative coverage).

## T2c — R5 runtime drift band (the premortem R5 precondition, specced to execution depth)

**Problem:** the ADR 0030 gate catches changes at DEPLOY; nothing catches silent drift in
PRODUCTION (model snapshot updates, corpus-mix shifts, upstream provider changes). R5
(pre-mortem: LLM authority creep) requires a runtime tripwire before the 7/18 authority flip.

**Mechanism — two new `MetricSpec` entries in `system_audit._TRADE_METRICS`** (post-EOD scan,
16:15 ET; the existing L2 machinery does the banding — 30d trimmed median ± 3 MAD, cold-start
tiers, Sonnet hypothesis on breach — zero new alert plumbing):

1. **`judge_high_rate_daily`** — of today's `ep_grade_decision` audit events, the fraction with
   `judge_tier='HIGH'`. Fetcher: pull today's rows, parse `detail` **in Python** (the column is
   TEXT and can hold malformed rows — the `->>`-in-SQL approach already failed once, 7/11 corpus
   mine), count. Diagnostic SQL: the day's decisions w/ tier+grade+rationale. Owning files:
   `ep_grade_judge.py`, `ep_detector.py`.
2. **`judge_demote_share_daily`** — same rows, share with `judge_direction='demote'`. Catches
   the over-skepticism drift direction at runtime (the D08/positive-control failure mode, live).

**Cold-start ceilings** (`_COLD_START_CEILINGS`): `judge_high_rate_daily ≤ 0.85`,
`judge_demote_share_daily ≤ 0.90` — generous by design; the band takes over at n≥14 days.
**Low-N note:** on days with <3 graded decisions the fetcher returns the rate anyway; the
trimmed-median band absorbs single-decision noise, and the L2's existing small-sample behavior
applies — do NOT add a bespoke N-floor (keep the metric shaped like every other L2 metric).
**Regime note:** neither metric joins `_REGIME_CONDITIONAL_METRICS` initially — HIGH-rate may
correlate with regime, but establish the unconditional baseline first; promote it there only if
the first weeks show regime-driven false breaches (a named re-open, not a default).

**Build:** one card (~40 lines + 2 tests: fetcher truth-table on synthetic audit rows,
malformed-detail row skipped not crashed). Deploy = market-agent scope. This is the R5
precondition line for the M1 sitting: **authority flips 7/18 WITH the tripwire in place.**

## Cards added to the queue (all Opus/Sonnet)

- **T2a**: none — D01–D08 ride ADR 0030 C1/C3 as-is.
- **T2b-C1**: theme-corpus loader variation in the 0030 harness (+ the 0025-C3 DoD line update).
- **T2c-C1**: the two MetricSpec entries + cold-start ceilings + 2 tests.

## Operator forks

- **F1 (T2b):** golden verdicts on M09–M14 (esp. M10's MERGE and M14's DISTINCT — the two
  direction-testing calls). *(Rec: sign; each carries its rationale.)*
- **F2 (T2c):** metric pair + ceilings as specced. *(Rec: accept; both metrics are observe-only
  L2 surfaces — no money path.)*
