# ADR 0011 — EP Holistic Grade Judge (the North Star grade decision)

**Status:** IMPLEMENTED-LIVE — program CLOSED 2026-06-11, one day ahead of the locked
Fri 6/12 date. Flipped load-bearing 2026-06-10 (operator-signed, first call CBRL
MODERATE→none); advisory stack retired same day (#249 — judge `fire_axes` is the one fire
signal; ADR 0010 superseded); model-checked via operator-labeled closed-gap eval →
`JUDGE_MODEL = OPUS 4.8` (Opus 9–Sonnet 2; `docs/analysis/judge_model_eval_closed_gap_2026-06-10.md`);
verified-live 2026-06-11 (3 Opus-judged alerts, exact alert↔decision↔authority reconcile,
0 fail-opens). Every DEFINITION_OF_DONE clause met. **North Star is closed and is not
reopened** — successor program: `docs/roadmap/apollo-v1.1-v2.0.md`.
**Original acceptance:** rubric SIGNED OFF by operator 2026-06-08 (§Rubric below is the
operative weighting). **Date:** 2026-06-08. **Supersedes the conviction-floor grade
authority** for the EP (MAGNA53) paper path; collapses the advisory stack
(#189/#190/#200/#201/#203) into one judge.
**Program:** task #240 (closed); plan `~/.claude/plans/optimized-tinkering-harp.md`.
**Driver memory:** `feedback_build_toward_vision_not_piecemeal`.

---

## Context — what's wrong with the current grade

`_score_ep` (ep_detector.py:660–675) promotes a name to **HIGH on gap % + a catalyst enum
alone** (`gap≥15 & game_changer → 80`, `gap≥20 & strong → 80`, …). Theme, narrative,
materiality, and technical structure are at most decorative `+10` bonuses or advisory shadow
columns. A discretionary EP trader does the opposite: they judge whether the catalyst is
**real and material relative to the company**, weigh theme heat + structure + gap alignment,
and move the grade **up or down** holistically. The current system is, by the operator's own
framing, **definitionally incomplete** for the EP method. #210 (the grounded direct-sourced
corpus the judge reasons over) just landed — so the LLM can now be a **judge over grounded
text**, not a discoverer.

## Decision

Introduce ONE holistic LLM grade judge that ingests the full per-candidate signal set and
outputs the EP grade **bidirectionally**, and make it the live **paper** grade — superseding
the conviction floor's authority. The judge is the realization of the North Star: the
real/material catalyst becomes **load-bearing**, not decorative.

## The contract

### Call site & shape
- **One LLM call**, tool-forced JSON, on the morning-scan hot path **before the 9:45 ORB
  cutoff**. Subsumes `_classify_catalyst_claude` in the Wave-2 end state.
- Per-call `asyncio.wait_for` (~15s) under the existing semaphore(5)+429-retry concurrency.

### Inputs (all already computed per-candidate; the judge assembles, builds nothing upstream)
- **Grounded catalyst:** `grounded_text` (SEC 8-K/6-K body + Benzinga wires + web synthesis,
  `build_grounded_text`) + `catalyst` + `claude_analysis` + `corpus_provenance.has_direct_source`.
- **Materiality:** the **deterministic** `rule_materiality` (deal-value ÷ market-cap ratio)
  tier ONLY — the exact ratio an LLM can't compute reliably. **W4 design decision (2026-06-09,
  advisor-endorsed):** the judge is NOT fed `assess_materiality`'s Sonnet abstain-leg as a
  pre-pass input. The judge's OWN call already outputs `materiality_tier` over the same
  grounded_text + market_cap, so a second hot-path Sonnet materiality call would be redundant
  inference the judge anchors on (cost + a new fail-open surface + against "ONE judge owns it").
  The judge IS the Sonnet that handles the abstain cases. None ratio (no parseable deal value)
  is passed as "judge materiality yourself." This satisfies #245's "rule-first→Sonnet" intent
  through a cleaner architecture — the deterministic rule is the shared single-source function;
  only the LLM leg is subsumed into the judge by design. Shadow-only, within the signed rubric
  → no re-sign-off. (Wired in `_judge_shadow` 2026-06-09; advisory-stack retirement —
  materiality_shadow / fire-panel compute / theme_gated_* — is DEFERRED to a post-flip task,
  since those writers still feed the live #200/#201 fire_status baseline until the judge is
  authoritative.)
- **Theme/narrative axes:** `in_active_theme` (Lane 1), `in_narrative_cohort` (Lane 2 / #167).
- **Technical structure:** `gap_pct`, `pm_rvol`, extension (MIN close 5d), `vol_percentile`,
  `score_breakdown`.
- **Company profile:** `market_cap`, `sector`, `revenue_stage`.
- **Raw magnitude** (`gap_pct`, `ep_score`) **as context, NOT as a floor.**

### Output schema (locked)
```json
{
  "grade": "game_changer | strong | routine | mna",
  "tier": "HIGH | MODERATE | none",
  "direction_vs_floor": "promote | hold | demote",
  "materiality_tier": "transformative | material | minor | immaterial | null",
  "fire_axes": ["catalyst", "theme", "narrative"],
  "rationale": "<= 3 sentences, must cite the load-bearing reason",
  "confidence": 0.0
}
```

### Rubric (THE OPERATOR-SIGNED PART)
1. **A real, material catalyst is REQUIRED for HIGH — gap alone never earns HIGH.** Gap+vol
   is the market's vote that a reason *might* exist, never sufficient on its own.
2. **Materiality is bidirectional.** Transformative-relative-to-size can **PROMOTE** a
   routine/strong (the under-rated small-cap outlier — the fat-tail winner). Immaterial
   **DEMOTES** a strong/game_changer (the big gap on a rounding-error catalyst).
3. **Pradeep catalyst hierarchy** weights the catalyst axis: theme #1 > govt policy #2 >
   shortage #3 > sales-accel / new product / management #4 (`user_pradeep_catalyst_hierarchy`).
4. **Theme heat + technical structure + gap alignment modulate up or down** (meta-rubric:
   a strong-on-fundamentals name can be boosted to game_changer by theme+technical context).
5. **mna:** advisory only — the **M&A filter stays the authoritative M&A gate**; the judge's
   `mna` never becomes a second M&A truth.

### Fail-open (load-bearing safety)
- Judge error/timeout → **conviction-floor grade**; emit `judge_timeout_fallback` audit.
- A **missing/uncertain** signal never demotes a real EP — only a CONFIRMED reason demotes.
- **Grader/judge/floor relationship:** the floor fallback needs `catalyst_quality`, which a
  failed judge call can't provide → **`_classify_catalyst_claude` is RETAINED as the fallback
  grader.** The judge supersedes the floor's grade *authority*, it does not delete the
  sub-grader. Always-concurrent vs lazy-on-timeout is a Wave-2 latency-eval decision.

### Comprehensive decision logging (OPERATOR REQUIREMENT, signed 2026-06-08)

Every grade decision must be **fully reconstructable after the fact** — so we can review,
debug, and tune exactly how a grade was arrived at. For each candidate that reaches grading,
persist the complete decision trace:
- **Inputs:** `grounded_text` (already persisted W1), `gap_pct`, `ep_score`, floor tier
  (`baseline_floor_tier`), floor `catalyst_quality`, `materiality_tier`, `has_direct_source`,
  `in_active_theme`, `in_narrative_cohort`, `market_cap`, `sector`, `revenue_stage`.
- **Judge verdict:** `judge_tier`, `judge_direction`, `judge_materiality_tier`, `fire_axes`,
  `judge_rationale` (the load-bearing reason, ≤3 sentences), `confidence` (W1 columns).
- **Decision:** `grade_engine_authority ∈ {floor, judge, fallback}` — which path drove the
  grade — plus the final tier used, and (when `fallback`) the explicit reason (timeout / null
  verdict / toggle-off). Emitted as a structured `ep_grade_decision` audit event (queryable)
  AND surfaced per-ticker via `/setup` and `/why`.

The rationale is REQUIRED (the schema enforces it) precisely so no demotion/promotion is ever
a black box. This is the substrate the W3 review (delta lists + Unjustified Demotion Sweep)
and the model-eval read from.

## The four fixed boundaries

1. **PAPER only** — the judge drives paper grades/entries; no real money.
2. **Fail-open to floor** + DB-backed `holistic_judge_enabled` toggle (instant revert, no
   redeploy; `mi_safeguard_state` pattern).
3. **All other safeguards intact** — M&A filter, revenue-stage, dedup, position caps,
   daily-loss, drawdown breaker, the 9:45 ORB window. The judge changes the **grade**, never
   the gates.
4. **6/22 real-money decision stays decoupled** — this realizes the vision on the paper path;
   the real-money flip remains the operator's separate decision (Wave 7).

## Go-live gate (Wave 2 flip)

The flip from shadow → live-paper ships ONLY when ALL hold:
1. Wave 1 judge shadow-emit verified live (judge_tier + delta accruing, latency in budget).
2. **Operator review of the promotion + demotion delta lists** for judgment-correctness
   (the HARD-gate — the agent never self-certifies the demotion list). The Unjustified
   Demotion Sweep (≥+3R-within-5d demotes) is the winner-killing guard.
3. **Operator sign-off on this rubric** (the exact weighting above).
4. CHANGE_PROCESS entry + this ADR updated in the same commit.

R-superiority (entry-aware paper R of promoted-vs-demoted) is a **refinement signal, NOT the
go-live gate** — forward-from-gap is the saturated metric that killed the materiality R-gate
(ADR 0010); the model eval and the go-live judgment use an **operator-labeled** sample.

## Status of the pieces it subsumes

`#189` materiality (shipped shadow), `#190` grounded-summary grade (= `_classify_catalyst_claude`),
`#200` theme-gated advisory, `#201` fire panel, `#203` consolidation — all fold into this one
judge at Wave 4. Until then they remain as-is (advisory), unchanged.
