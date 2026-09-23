# ADR 0006 — Catalyst-Discovery loop (investigator + advisor)

**Date**: 2026-05-30
**Status**: **DESIGN ONLY — build deferred.** No code, no schema, no deploy. Gated behind C1 (`catalyst_type`) forward data + the 2026-06-22 live-cutover decision + a go-live sequencing review. This is the C2/C3 layer of the North Star program (C1 = `catalyst_type` fire-identity, shipped 2026-05-30).
**Authors**: Apollo Assistant (with user direction 2026-05-30)
**Supersedes**: none
**Sequencing**: C1 (per-ticker `catalyst_type`) shipped → **C2/C3 = this loop** (cross-ticker, multi-turn). Rung 1 → rung 1.5 is the recommended build path; rung 2 is a stretch.

## 1. Context

Apollo's production LLM tools are **per-ticker and narrow** — `_classify_catalyst_claude` (catalyst *magnitude*), `classify_catalyst_type` (C1 *fire-identity*), the live fundamentals rubric. **None do the cross-ticker narrative-theme reasoning the operator does by hand**: *"OKTA is up — is the whole software group re-rating into the AI theme? what else is moving? is this a real story or just a beta gap?"* The theme engine clusters **bottom-up by RS + sector** and is structurally blind to cross-sector / nascent / narrative cohorts (two documented misses: the drone/defense policy theme and the software-AI re-rating — see `data_gated_reviews.yaml::theme_engine_narrative_blindness`).

The operator's founding concern (2026-05-30): the cohort-narrative reasoning that happens in a dev-session conversation is **not a production capability** — *"how do we make sure Apollo HAS this capability, so it's not just after-the-fact conversation?"* (memory `project_cross_ticker_narrative_synthesis_gap`). C1 is the per-ticker half of the answer; **this loop is the cross-ticker, multi-turn half** — a tool-grounded *investigator* that, given a stock that moved, investigates *why* and *whether it's part of a cohort/theme*, reviewed by an independent *advisor* that enforces evidence-grounding. It is the dynamic version of a top-down emerging-theme synthesis pass — the bottom-up RS-clustering's missing complement.

This shape was proposed by the operator: *"two LLMs — one asks the questions I ask, the other investigates and answers, back-and-forth until we discover the true catalyst or confirm there's none."*

## 2. Decision — the maturity ladder (ship rung 1 → 1.5; rung 2 = stretch)

| Rung | Shape | Adds | Cost / risk |
|---|---|---|---|
| **1** | Investigator + structured **self-critique** | cheapest baseline | weak independence (model grades its own work → rubber-stamps) |
| **1.5** | Investigator + independent **advisor review** (bounded revise-loop) | real independence, grounding **enforcement**, **natural termination** — this is the in-session `advisor()` pattern, which has empirically caught real errors in this very program (the "execution > theme" whipsaw, the hand-picked-discriminator post-hoc narration, the rubric-date P&L confound) | 1 extra strong-model call per revise round |
| **2** | **Questioner ⇄ investigator** peer debate | the forward-driving *questioner* carrying the operator's persona + Pradeep's hierarchy, persisting so the investigator can't quit early | highest cost; needs explicit termination discipline (two ungrounded LLMs converge on a confident hallucination) |

**Three roles, mapped to the operator's own cognition:**
- **investigator** — drives *forward*, **tool-grounded**, does the retrieval and the draft conclusion;
- **advisor** — reviews *backward*, **critic, no tools** (critiques grounding-completeness, bounces the investigator back to retrieve; does **not** verify facts itself);
- **questioner** (rung 2 only) — forward agenda-setter with the operator's instincts.

**1.5 externalizes the critic; rung 2 additionally externalizes the questioner.** Why 1.5 is the right intermediate, not merely a cheaper 2: it fixes rung-1's self-grading weakness with genuine independence, **and** its asymmetric/bounded form is a *safety* win — it sidesteps the echo-chamber / non-termination failure mode that the symmetric debate carries.

## 3. Architecture (rung 1.5 — the recommended build)

- **Trigger:** a **nightly EOD job** (after the 5 PM data pull + EP outcomes), batched over the day's HIGH/MODERATE EP alerts + any detected co-gap cohorts. Latency-tolerant, cost-bounded. **NOT intraday** — the real-time alert path stays the cheap per-ticker C1 classifier. Two tiers: real-time = C1 tag; nightly = this deep dossier.
- **Investigator:** a **bounded tool-use loop** (≈4 iterations) that, per name/cohort, asks *"why did it move / is it a theme / what else moved"* and answers **only from tool results**. Produces a draft dossier.
- **Advisor:** **one stronger-model (Sonnet) call** that sees the investigator's full evidence + draft and returns `{verdict: accept | revise, concerns:[...], revision_prompt}`. **Bounded ≤2 revise rounds.** Its mandate is the grounding guard: *is every claim cited? did you check the cohort? story vs evidence?*
- **Output = a structured "catalyst dossier"** per name/cohort: `{catalyst, catalyst_type, cohort[], proposed_theme?, confidence, evidence_cites[]}` **OR** `{no_catalyst: beta | technical | no_story}`. Persisted (new `mi_catalyst_dossiers`) + surfaced to the operator (Telegram digest / a `/dossier TICKER` command). **Advisory.**

## 4. The one real build (cohort detection — reframed honestly)

**Not "build cohort detection from scratch."** `correlation_engine.py` already computes daily SPY-residual co-movement clusters (≥0.85 pairwise, connected components) — that is most of the co-gap primitive, today only feeding theme discovery. What is actually missing is narrower:

- **(a)** a **per-ticker accessor** into those existing daily clusters;
- **(b)** an **RS-slope recovery filter** (`rs_1m` high / `rs_6m` low, in-sector) — correlation does **not** capture recovery *shape*, and the software-AI cohort is exactly this signal;
- **(c)** **join** the clusters/cohort to the catalyst narratives (`mi_ep_alerts.catalyst` / `claude_analysis` / `catalyst_type`);
- plus the cheap **same-day-gap + theme-membership** layering (`mi_ep_alerts` by date+sector; `mi_themes.tickers`).

## 5. Reuse map (grounded — don't reinvent)

| Need | Reuse | Location |
|---|---|---|
| Agentic loop | `_tool_use_loop` (bound to ~4 iters; tool_use stop-reason, concurrent tools, prompt caching) | `core/orchestrator.py:167` |
| Structured LLM call | `tool_choice` + `Semaphore(5)` + 2× 429-retry + **fail-open** | `catalyst_type_classifier.classify_catalyst_type`; `ep_detector._classify_catalyst_claude:297` |
| "LLM reviews LLM" precedent + JSON parse + escalating backoff | `_validate_theme_membership` + `_extract_json_object` | `theme_engine.py:944` |
| Stronger advisor model | Sonnet extraction precedent (`claude-sonnet-4-5`) | `catalyst_metrics_extractor` |
| News tools | `search_news_perplexity` (+ `_preflight_perplexity` health check), `get_polygon_news`, `get_alpaca_news` | `collector.py:678 / 470 / 405` |
| Investigator catalyst tools | `_classify_catalyst_claude`, `classify_catalyst_type`, `extract_earnings_metrics`, `score_catalyst_rubric`, `get_fundamentals` | resp. modules |
| RS / cohort data | `get_rs_for_tickers`, `get_recent_rs_batch` (slope), `get_rs_leaders`, `get_top_rs_by_sector`; `mi_stock_scores` (rs_1m/3m/6m, sector) | `db.py:3957/3974/3909`, `rs_engine.py:713` |
| Theme cohort | `get_active_themes` (now-relative), `get_theme_history` (dated); `mi_themes.tickers` | `db.py:4633 / 4072` |
| Co-movement primitive | daily SPY-residual correlation clusters | `correlation_engine.py` |
| Alert batch | `get_today_ep_alerts(d)` (filter HIGH/MODERATE in Python) | `db.py:4569` |
| Schedule + audit | `audit_wrap(fn, JOB, …)` + `CronTrigger(timezone=ET)`; `log_audit_event` | `scheduler.py:2911` |

## 6. Acceptance test = the proof of capability (read-only, offline)

Reproduce **both documented misses** offline — and note they stress **different** signals (so they tell us which to build, and give per-signal pass/fail):

- **Drones** (AVAV / ONDS / KTOS / RCAT, 2026-05-28, $2B govt policy) → exercises **same-day co-gap + cross-sector**. PASS = detector groups them, investigator names "drone/defense **policy**", advisor accepts as grounded.
- **Software-AI** (OKTA / CRWD / NOW / DDOG / TWLO recovering) → exercises **RS-slope recovery** (staggered; correlation alone may miss). PASS = the RS-slope filter surfaces the cohort, investigator names "software **AI re-rating**".

If the loop reproduces both read-only, the capability is real and in-system — directly answering the operator's founding concern.

## 7. Smallest-viable build sequence (when greenlit)

1. **Cohort accessor + RS-slope filter** (§4 a/b/c) — read-only; validate against the two §6 cohorts.
2. **Rung-1 investigator** on a *single* triggering case (the day's top HIGH or one known cohort) — prove the grounded loop + dossier schema end-to-end.
3. **Rung-1.5 advisor pass** (Sonnet critique + bounded revise) — the independence + grounding enforcement.
4. **Nightly job + `mi_catalyst_dossiers` + Telegram surface**, advisory/shadow.
5. **Rung 2** only if the rung-1.5 investigator demonstrably quits early.

## 8. The grounding mandate (make-or-break) + the advisory line

- **Grounding:** the investigator may assert **only** what a tool returned; the advisor **enforces citation**. Two ungrounded LLMs converge on a confident hallucinated catalyst — lethal in trading. *"Confirm there's none"* (beta / technical / no-story) is a **first-class output** — it *is* the theme-less-gap detection that is the North Star fidelity hole (a theme-less gap is not a weak EP; per methodology it is not an EP).
- **Advisory vs feeds-the-engine (resolved):** the **discovery/proposal is advisory** — the operator confirms before a proposed theme is **canonized into `mi_themes`**. Once confirmed, it flows through the normal theme pipeline like any theme. **The loop never gates an entry directly.** Gating on any of this is Phase 6, calibrated on forward + regime-diverse data (the 3-layer discipline — `feedback_methodology_fidelity_over_stability`).

## 9. Out of scope / discipline

- **No build this cycle.** The 2026-06-22 live-cutover decision owns the calendar; do not open a new LLM subsystem mid-cutover. Build is gated on C1 forward data accruing (regime-diverse) + a go-live sequencing review + advisor sign-off.
- **Shadow / advisory first** — same discipline as every shipped detector (`feedback_methodology_insights_need_periodic_revalidation`, `feedback_sample_size_discipline`).
- **Cost** — the loop multiplies LLM calls; keep it nightly/batch, prioritize HIGH/MODERATE + top movers, cache aggressively. The real-time path must never depend on it.
- **Telemetry decoupled from detection** — a Telegram/dossier-write failure must never break the nightly job; fail-open + audit, like #84/#89.

## 10. Cross-references

- `data_gated_reviews.yaml::theme_engine_narrative_blindness` — the theme-detection blindness this loop's cohort half addresses (2 test cases: drones + software-AI). The §6 acceptance test validates against both.
- `data_gated_reviews.yaml::catalyst_discovery_loop_sequencing` — the sequencing gate for *when* to start this build.
- `data_gated_reviews.yaml::theme_as_ep_signal` + `phase5_meta_rubric_calibration` + `theme_axis_gating_logic` — where confirmed theme signal feeds scoring (Phase 5/6).
- `project_cross_ticker_narrative_synthesis_gap` (memory) — the capability-gap statement + the questioner/investigator/advisor proposal.
- `project_northstar_catalyst_type_c1` (memory) — C1, the per-ticker half shipped 2026-05-30.
- `feedback_methodology_fidelity_over_stability` (memory) — the 3-layer discipline (tenet / mechanism / calibration) gating any move toward scoring.
- ADR 0003 (EP selectivity overhaul) §5 — the meta-rubric this ultimately feeds.
- `core/orchestrator.py:167` `_tool_use_loop` — the agentic-loop pattern reused (bounded).
