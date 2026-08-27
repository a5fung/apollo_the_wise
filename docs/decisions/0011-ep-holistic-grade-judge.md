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
3b. **Revenue over EPS on growth names** (AMENDMENT, operator-signed 2026-06-11 — Pradeep
   source statement + the operator's own ANF eval label): revenue growth/acceleration
   (Q/Q + Y/Y, guidance raise) is the load-bearing earnings signal; an EPS beat with flat or
   missing revenue is NOT a HIGH catalyst. EPS matters only in TURNAROUNDS (loss→profit
   inflection) and the turnaround must be SUSTAINABLE/structural — never a single-quarter
   anomaly from one-time/external items (the CBRL litigation-settlement class, the judge's
   first live demote). Memory: `user_pradeep_revenue_over_eps`; task #269; shipped to both
   the judge rubric AND the fallback grader prompt in the same commit.
3c. **Catalyst FRESHNESS is part of "real"** (AMENDMENT, operator-signed 2026-06-12 — the
   AKTS case): the catalyst must be NEW (dated today/overnight, or freshly disclosed per a
   direct primary source). An undated catalyst, or one the evidence shows predates the gap,
   cannot be the attributed driver regardless of materiality — AKTS 6/12 was judge-promoted
   MODERATE→HIGH on a May-2024 Lilly partnership resurfaced undated by a web-only corpus
   (`has_direct_source=false`); the operator caught it same-day (first operator label on a
   live load-bearing decision). No fresh verifiable driver → driver UNIDENTIFIED, MODERATE at
   best. `has_direct_source=false` + materiality-driven promotion = highest-risk pattern,
   prefer the floor tier. Rubric `v3-2026-06-12-catalyst-freshness`; shipped to judge rubric
   AND fallback grader same commit; AKTS = the named regression probe.
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

---

## Addendum 2026-06-17 — the full grade pipeline + where Perplexity fits (operator: "all this must be clear")

A 6/17 operator triage of three alerts (QURE/JBL/LZB) surfaced that the alert *display* still
led with the floor grade while the judge is load-bearing — five symptoms of ONE coherence gap.
The authoritative pipeline, end to end:

1. **Claude** (`_classify_catalyst_claude`) grades the catalyst magnitude over the grounded SEC+
   news text → `catalyst_quality` (game_changer/strong/routine/weak) + the analysis. This is the
   **floor** catalyst grade.
2. **Perplexity** plays THREE distinct roles — keep them separate:
   - **(corpus / source)** its web-search answer is folded into `grounded_text` by
     `build_grounded_text` as `[Web summary]`, ordered **primary-LAST** (after the SEC filing +
     Benzinga wires) and tracked in provenance as `web_perplexity` — explicitly NOT a
     `has_direct_source`. So Perplexity's TEXT **does** reach the judge (which reads `grounded_text`),
     as the least-trusted tail of the corpus. (It is the confabulation-prone leg — RUM/PGY — which is
     exactly why #210 backbone + #233 demote-to-labeled-candidate exist.)
   - **(grade cross-check)** its independent GRADE `pplx_quality` (`gemini_validation` column, legacy
     name) feeds the **floor only**: (a) agreement `pplx==catalyst_quality` → `confidence_multiplier
     =1.2` scaling `ep_score`; (b) hedge-downgrade if it self-acknowledges null search.
   - **The judge consumes Perplexity's TEXT (in the corpus) but NOT its grade or the floor multiplier.**
3. Deterministic floor downgrades (revenue-weak missing-YoY, prose-mismatch) can lower
   `catalyst_quality`. `ep_score` + `catalyst_quality` → **floor_tier** (`baseline_floor_tier`).
4. **The Judge** (Opus, `grade_holistic`) independently re-grades the same `grounded_text` (which
   INCLUDES Perplexity's primary-last `[Web summary]`) + the deterministic deal÷cap materiality +
   active narratives → `tier` / `direction_vs_floor` / `fire_axes`. It does **not** consume
   Perplexity's separate grade or the floor multiplier.
5. **Authority** (`_resolve_grade_authority`): judge load-bearing → `score_tier = judge_tier` drives
   the alert + ORB entry; `baseline_floor_tier` is kept as the counterfactual.

**So the judge is the final word on tier. Perplexity's GRADE only shaped the (now-secondary) floor;
its TEXT is one — primary-last, least-reliable — source in the corpus the judge reads.**

### Coherence fix shipped 2026-06-17 (display-only — no grade-math, no schema)
The alert now **resolves to the judge** and shows the provenance:
- **Headline** leads with the judge verdict when `grade_engine_authority='judge'`
  (`resolve_headline_grade`) — a judge-promoted HIGH no longer headlines the contradicted floor
  grade (LZB floor `routine` under a judge HIGH).
- **Grade-provenance line** (`format_grade_provenance`): `Floor: <Claude> · Perplexity: <pplx>
  (agree/differs) · Judge: <tier> <direction> ← authoritative` — **superseded 2026-08-27, see
  below**; the word "Floor" here is exactly what fused the two ratings. Replaces the old
  `confidence_multiplier > 1.0` "Claude + Perplexity agree" line, which went STALE when a catalyst
  was downgraded AFTER the agreement boost (LZB 6/17 printed "agree" on routine-vs-strong).
- **Theme line**: when `fire_axes` lit theme/narrative but the ticker is in no tracked cluster
  (JBL judge-inferred AI-infra), shows "judge-inferred (not a tracked cohort)" not a bare "—".
- **Rubric line**: when metrics extracted but the rubric can't score (no prior-year revenue
  comparable), shows "not scored (no prior-year comparable)" instead of silently dropping.
- **10:10 catalyst-downgrade digest** annotates names the judge promoted ("↑ judge promoted to
  HIGH — authoritative") so it no longer contradicts the HIGH alert 20 min earlier.

### Coherence fix shipped 2026-08-27 (display-only — no grade-math, no schema, no carve-out change)

**Trigger — OKTA 2026-08-27.** One live alert said three inconsistent things: header
`Judge: HIGH (hold)`, judge prose *"Demoted from gamechanger…"*, footer `Floor: game changer
… Judge: HIGH hold ← authoritative`. `mi_audit_log` recorded `floor=HIGH judge=HIGH
dir=demote`.

**Two values that were being read as one — the definitions, now enforced in code comments:**

| Surface | What it actually is |
|---|---|
| `dir=` on `ep_grade_decision` (`judge_direction`, `direction_vs_floor`) | The judge's **self-reported** direction. Raw model output — `_normalize_verdict` validates ENUM MEMBERSHIP ONLY, never agreement with `tier` vs `floor_tier`. The rubric asks for a tier comparison; the model may answer on the catalyst-grade axis instead (OKTA did). **Not** "the judge's recommendation before overrides" — nothing overrode it. |
| `(hold)` in the alert header | **DERIVED** by `briefing._judge_direction` from `TIER_RANK` (`score_tier` vs `baseline_floor_tier`). Factual; it is what acted. The header was never the bug. |

**Two axes, never one ladder.** `game_changer` is a CATALYST grade (floor-owned). `HIGH` is the
top of the ALERT TIER scale (judge-owned when authoritative). The judge's own `grade` output is
**never written to the alert row** (`update_ep_alert_judge_result` writes tier / direction /
rationale / materiality / fire_axes only), so it is advisory by construction. "Demoted from
gamechanger to HIGH" is a category error. On **the surfaces listed below** every formatter now
names its axis, and a transition arrow is only ever drawn TIER→TIER.

**What the carve-out actually overrode.** `catalyst_downgrade_carveout_applied` fires inside the
FLOOR grader (`_classify_catalyst_claude`), ~7 s before the judge runs, and overrides the
**floor's own missing-YoY revenue safety net** — not the judge. The alert says exactly that.

**Shipped:**
- `format_grade_outcome_lines` — an `⚖️ Acted` line (per axis: which tier acted and which engine
  set it, plus the acting catalyst grade) printed **above** the italic rationale, and an
  `↩️ Recorded, did NOT act` block naming each inert item and why it was inert.
- `format_tier_verdict` / `resolve_headline_grade` / `format_grade_provenance` — axis-named on
  every leg; the judge leg states the limit of its authority ("sets the tier, not the catalyst
  grade").
- `resolve_why_attribution` — the judge's rationale is labelled `Judge's reasoning:`. Model
  prose cannot be controlled and will keep saying "demoted"; the derived `⚖️ Acted` line above
  it plus the attribution are what keep the outcome unambiguous regardless of wording.
- `ep_detector` threads a display-only `floor_grade_kept` record (which of the three keep-events
  — earnings carve-out / live prior-year YoY recovery / extraction-failure fail-open — preserved
  the floor grade, and why), set from the **decision branch** (idempotent, every 5-min tick), not
  the per-day-deduped audit emit, and cleared if a downgrade ultimately did fire. Plus
  display-only `judge_direction` / `judge_grade` on the in-memory alert dict.
- `/setup` and `/why` derive their judge arrow/direction from the tiers too, and report the
  judge's own `direction` word separately when it disagrees.

Pinned by `tests/test_ep_alert_two_axes.py`.

### Naming fix shipped 2026-08-27 — "floor" deleted as an operator-facing word (display-only)

**Trigger — the same OKTA thread, one round later.** Operator, verbatim: *"why is it called
floor, what floor? Then it says 'floor: game changer' yet you say it rates it high, moderate,
or nothing, then how is there gamechanger? where does game changer come from?"* and then *"are
you now saying there's two separate ratings here that we combined by accident?"* — **yes.**
The first pass (above) fixed the LOGIC and left the WORD, so one word still did two jobs:

| The word "floor" meant | Which rating |
|---|---|
| `baseline_floor_tier` | the **ALERT TIER** our own score produced before the judge reviewed it |
| "Floor: game changer (Claude)" | the **CATALYST GRADE** from the Claude grader |

That is our naming defect, not his misreading. **"floor" is now banned from every
operator-facing string.** Identifiers, the `baseline_floor_tier` column and the stored
`grade_engine_authority='floor'` enum are UNCHANGED — the ban is on what he reads.

**The vocabulary, one word per thing:**
- the pre-judge alert tier → **"our score"** (`alert tier HIGH (our score said HIGH; the judge
  held it)`);
- the catalyst grade's owner → **"the Claude grader"** / "the catalyst grader" (`catalyst grade
  *game-changing* (set by the Claude grader)`);
- the judge **sets the tier, never the grade**; Perplexity is a recorded second opinion
  labelled **"sets nothing"**.

**Shipped (every surface he reads):** the EP alert (`format_grade_outcome_lines`,
`format_grade_provenance`, `resolve_headline_grade`), `/why`, `/setup`, the EOD recap judge
line, the 16:25 judge-delta digest (= the 16:55 close digest, same render), the monthly judge
review, the weekly system review, the chart-axis shadow digest, the LLM-credits alert, the
trade proposal, and the `ep_grade_decision` audit summary that `/audit` renders.

**Structural, not just wording:** `briefing.format_alert_tier_clause` is now the ONE renderer of
"what the alert tier is and who set it" — the EP alert, `/why` and `/setup` all call it. Those
three each derived it inline, which is precisely how the banned word survived in three places
after the first pass. Catalyst grades render through ONE map (`briefing.format_catalyst_grade`:
`game_changer` → **"game-changing"**, `mna` → "merger/acquisition" — never "M&A", because
`llm_health` sends `parse_mode="HTML"` where a bare `&` is invalid).

**REVERSAL — the judge-delta digest arrow.** The section above deferred it, arguing that
deriving the arrow while the SQL selection stays raw "produces '=' rows in a message titled
'deltas' — a half-state that reads worse". **That reasoning was wrong, not merely incomplete.**
It weighed a cosmetic oddity (a "=" row under the word "deltas") above a factual contradiction
the operator reads daily — a ▼ printed beside "tier held" is the OKTA defect itself, in a second
surface. So: the arrow is **derived from the two tiers**, the judge's own word is printed as
`judge's note: demote` when it disagrees, and the SQL predicate is **untouched** (selection is
data, not display).

⚠ **The half-state is OUTWEIGHED, not solved.** On a day where every flagged row held, the
digest really does render `EP Judge deltas … (▲0 raised ▼0 cut =1 held)` — a "deltas" title
over a message where no tier moved. The header now says what it counted and the subtitle names
the axis, which makes that legible rather than contradictory, but the title is still loose. The
clean fix is to widen the SQL selection (all judged rows, not just claimed movers) and retitle
it — a separately scoped change, because selection is data.

Pinned by `tests/test_ep_alert_two_axes.py` (which now sweeps EVERY rendered surface for the
banned word) + `tests/test_judge_delta_digest.py`.

### Deferred (grade-AFFECTING → CHANGE_PROCESS + backtest, NOT shipped 6/17)
- **Stale `confidence_multiplier` after a floor downgrade** (`ep_detector.py` revenue-weak path
  keeps the 1.2 the hedge path resets). Resetting it lowers `ep_score` → can flip `floor_tier` AND
  the `score<50` pre-judge skip → it changes *what reaches the judge*. Backtest the pre-judge
  gating effect first.
- **Missing prior-year YoY is the single upstream root** of BOTH the rubric=None AND LZB's
  spurious strong→routine downgrade. yfinance already shadow-recovered LZB's +3.8% YoY; wiring it
  into the rubric input would have prevented the downgrade entirely. Grade-affecting → the #149
  shadow→promote decision (backtest-gated). Name it there, not "cosmetic rubric display."
- **Open governance question:** under a load-bearing judge that does not consume Perplexity, is
  Perplexity's mechanical `ep_score` boost still wanted, or should it become display-only
  provenance? Decide before promoting the multiplier-reset.
- **Theme-detection gap** (`theme_detection_two_lane_architecture`): the judge inferred a theme
  (JBL AI-infra) that neither Lane-1 clustering nor Lane-2 narrative tracks — a real detection gap,
  not just a label. **RESOLVED 2026-07-18 (#322):** root cause + fix in
  `docs/architecture/theme_engine.md` §"Two-lane detection architecture + the judge-inference
  feed" — every existing lane has a structural multi-member/peer-naming floor a single semantic
  judge classification never clears; `judge_theme_gap.py` now feeds a `source='judge_inferred'`
  candidate into the shared shadow-radar table (surface-only, same anti-circularity walls as
  coverage_probe — never auto-promoted, never re-enters the judge's own `active_narratives`).

---

## Addendum 2026-08-07 (#543) — one grade in seven was decided by TRUNCATION, not by the judge

**BUG FIX, not a criteria change.** The rubric (§Rubric, operator-signed), the tool schema and
the normalizer are all untouched. Only the response ceiling moved.

**What was wrong.** `invoke_forced_tool` carried a default `max_tokens=500` and `grade_holistic`
never overrode it. Measured over the 7 days to 2026-08-07: **7 of 49 `ep_grade_judge` calls
(14.3%) ended at EXACTLY 500 output tokens** — the model was cut off mid-JSON.

**⚠ AND IT DID NOT FAIL OPEN. Measured, not assumed** — my first draft of this entry said the
truncated calls fell back to the conviction floor. **That was wrong, and the truth is worse.**
When `max_tokens` cuts a forced-tool call off, the SDK still returns a `tool_use` block with
**partially populated input**. `grade`, `tier` and `direction_vs_floor` come first in the emitted
JSON and survive; `rationale` and `confidence` are what get cut. `_normalize_verdict` reads those
with `.get()`, so it returned a **complete-looking verdict built from an incomplete answer**.

The evidence, from `ep_grade_decision` audit rows over the same 7 days:
- **49 verdicts, 2 nulls.** If truncation had failed open we would see ~7 nulls. We saw 2.
- **7 of the 49 verdicts have `confidence = NULL`** — exactly the 7 at-cap calls.
- **Two of them — AMRC and RDW — PROMOTED to HIGH with a zero-length rationale.** HIGH drives
  the alert and the ORB entry. Those are live promotions decided by a response we cut off before
  it finished.

So the defect was not "the floor was reached too often." It was **grading on truncated input,
including promotions, with no trace.**

**Why it was invisible.** A partial verdict is structurally indistinguishable from a complete
one: the enum fields validate, the row writes, the alert fires. There was no
`judge_timeout_fallback` to count and nothing anywhere said "this answer was cut off." It was
found only by sweeping `api_usage.output_tokens` against each caller's cap while chasing the
theme-assignment outage the same day, then correlating the at-cap count against NULL-confidence
verdicts.

**Second change, same commit — a truncated verdict now FAILS OPEN.** `invoke_forced_tool` checks
`stop_reason == 'max_tokens'` and discards the verdict, writing a `judge_verdict_truncated`
audit row. This restores §Fail-open's signed intent ("judge error/timeout → conviction-floor
grade") — a response we cut off IS a judge error; we simply had no way to detect one until
`stop_reason` was recorded. It applies to every judge on the shared transport, not just this one.
Raising the ceiling makes truncation rare; this makes it harmless when it happens anyway.

**Change.** `max_tokens=1500` passed explicitly at the `grade_holistic` call site (not by moving
the shared transport default — `mgmt_judge` measured 0% at-cap on a 188-token average and does
not need the headroom).

**It will change live grades.** Roughly 1 in 7 candidates that previously got a floor grade will
now get a real judged grade. That is the intended effect: the floor was never meant to be
reached this often. Grade *authority* and the rubric are unchanged.

**Recurrence guard.** `api_usage.stop_reason` is now recorded on every LLM call and a daily
17:52 ET check Telegrams on any caller whose responses are being truncated — the ceiling class
is now self-reporting instead of inferred. Callers that fail to report `stop_reason` at all are
reported too, so a future call site cannot silently become the next blind spot.

**Cost.** Worst case (every previously-truncated call now running the full extra 1000 tokens):
**+$0.015/day**, against a ~$4-6/day total. Billing is on tokens generated, not the ceiling.
