# #448 b6 — re-score path scoping decision (Lane-1 pre-build, 2026-07-11)

**The #448 question:** does the catalyst rubric (composite_min=22) downgrade LOSERS more than
WINNERS? To answer it we must RE-SCORE the historical cohort with the current rubric, then crosstab
verdict×outcome. The #458 pre-build task = **scope the cheaper re-score path first** (the #448 line
flagged a possible LLM cost). This is that scoping. No crosstab is run here — that belongs in the
#448 dedicated session (7/16) after the mandated advisor-check on lookahead + fidelity.

## Decision: PATH 1 — deterministic re-derive (NO LLM). Confirmed cheaper than corpus re-extraction.

Three facts settle it:

1. **The rubric is pure deterministic code.** `catalyst_rubric.py` — `score_axis_1..6(deltas/
   beat/guidance)` + `composite_with_scaling()` — has ZERO LLM calls. The LLM work lives only in
   *extraction* (`catalyst_metrics_extractor.py` / `catalyst_materiality.py` /
   `catalyst_type_classifier.py`). So re-scoring, given the inputs, is free + reproducible.
2. **The alert-quarter extraction is already cached** in `mi_ep_catalyst_metrics.raw_json`:
   `q_revenue_usd` (value, yoy_pct, beat_vs_est_pct), `q_eps`, `q_margins`, `guidance_change`,
   `fy_revenue_usd`, `subscription_revenue_yoy_pct`. **No LLM re-extraction of the 96 corpora is
   needed** — this is the expensive path (PATH 2) the #448 line worried about, and we avoid it.
3. **But the rubric's deltas are MULTI-quarter** (`rev_accel`, `eps_qm4`, `rev_accel_streak`,
   `rev_yoy_max_prior_7q`, `margins_q1/q2`) and `raw_json` caches only q0. So the faithful
   re-derive needs the **prior 7 quarters' fundamentals** — a **deterministic FMP quarterly pull**
   (past facts, no LLM), not a re-extraction. Cheap API, ~96 tickers × ~8 quarters.

**Net cost of PATH 1:** one FMP quarterly-fundamentals pull + pure-code scoring. **No LLM.** PATH 2
(re-extract from the raw corpus) would be 96 × Claude grade calls — strictly worse and unnecessary.

## Cohort + join surfaces (confirmed present)

- **N = 96** rows post-2026-05-19 with `raw_json` (all 96 also have `raw_claude_analysis_text`).
- Forward outcomes: `mi_ep_missed_outcomes` (2520 rows) + `mi_live_trades` for the realized subset.
- Threshold: `CATALYST_RUBRIC_MIN_COMPOSITE` (the composite_min=22 under test).

## Fidelity plan for the #448 session (the mandated advisor-check items)

1. **Reuse the LIVE delta-assembly function** (import it — don't re-implement the q-series →
   `deltas` transform), feeding it the FMP quarters + the cached q0. Re-implementing risks drift.
2. **No-lookahead:** pull FMP quarterlies **as-of the alert date** (prior quarters are point-in-time
   facts; the residual risk is restatements — flag any q with a restatement date after the alert).
3. **Re-score fidelity gate:** before trusting the crosstab, validate that the re-derived composite
   reproduces the LIVE grade on a sample. NOTE: `mi_ep_grade_decisions` returned no columns —
   locate the actual live-grade store first (candidates: a grades table, or the decision-row emit
   in `ep_detector._emit_grade_decision`, which records `rubric_version`/`rubric_hash`). Anchor
   fidelity to the SAME `rubric_hash` the cohort was graded under, or note the version delta.
4. Then: re-derive all 96 → JOIN forward returns → crosstab verdict×outcome → the #448 decision
   matrix (downgrade-precision >80% & PASS-edge > DOWNGRADE-edge ≥1R → keep 22; <60% → lower;
   PASS-edge ≤ DOWNGRADE-edge → raise 25-28).

## Recommendation

- **PATH 1 (deterministic re-derive, no LLM) — proceed in the #448 session (7/16).** The crosstab
  is cheap; the only real work is the FMP pull + the fidelity validation above. This pre-build
  confirms the path and de-risks the session; it deliberately does NOT run the crosstab (the #448
  line requires the advisor-check on lookahead/fidelity first, and #448 is its own scheduled
  session — THE LINE: the outcome feeds an operator threshold decision on composite_min).

*Feeds #448. Read-only scoping; no re-score executed.*
