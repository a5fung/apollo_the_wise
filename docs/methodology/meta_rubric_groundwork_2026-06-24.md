# Meta-Rubric Groundwork — consolidated architecture, current state, and open composition decisions

**Date:** 2026-06-24 · **Task:** #329 ("reconcile-first + anchor" deliverable) · **Family:** #328 / #330 / #331 / #332 / #333 / #335
**Status:** GROUNDWORK / reference — durable. NOT a composition. The methodology design
(weights, formulas, mappings) is the **OPERATOR's** call; this doc reconciles the scattered
pieces and tees up the open decisions, it does not make them.

> **What this doc is.** A single standing reference that absorbs the scattered meta-rubric
> pieces — the PLAN #328–#335 family, the catalyst/Pradeep memories, the as-built code at HEAD,
> and the prior point-in-time analysis — into one place, then surfaces the open composition
> decisions for the operator's design pass.
>
> **What it is NOT.** It does not re-derive the detailed delta matrix — that lives in the
> point-in-time analysis `docs/analysis/meta_rubric_reconciliation_329_2026-06-18.md` (the #329
> first deliverable, 2026-06-18), which this doc cites and supersedes only as the *canonical home*.
> What this doc ADDS over the 6/18 analysis: (1) the full PLAN #-family map; (2) the memory
> synthesis (the methodology intent in one place); (3) a **re-verified current-state map at HEAD
> (2026-06-24)** — nothing shipped on this thread since 6/18, so the call-site defect below is
> still live; (4) the operator-decision tee-up.

---

## 0. The one-paragraph orientation

Apollo already HAS a composition layer: the **holistic EP grade judge** (`ep_grade_judge.py`,
ADR 0011, load-bearing on the paper path since 2026-06-10). It composes catalyst + theme +
narrative + structure + gap into a single tier verdict via a prose rubric. So the honest gap is
**not** "we have no meta-rubric." It is: the documented meta-rubric axes are composed *implicitly
and inconsistently* — several aren't even passed to the judge, none carries an *explicit,
calibrated, traceable* weight. The architecture fork was **decided 2026-06-18: Path A — enrich the
ONE judge** (pass the inputs it's blind to + add per-axis traceability), NOT build a second numeric
grade authority. The open decisions below all live *inside* Path A.

---

## 1. The methodology intent (synthesized from the memories)

The meta-rubric vision the operator wants Apollo to grade EPs against, reconciled from the user
memories. (Source memories listed; this is the *intent*, the as-built state is §3.)

### 1.1 The axes (per `user_meta_rubric_architecture`)
The catalyst rubric is **ONE input, not the verdict**. The final EP conviction composes:

1. **Catalyst / fundamentals** — quality, materiality, freshness, durability of the gap's reason.
2. **Theme heat** — membership AND stage/score (Accelerating vs Fading is categorically different).
3. **Technical structure** — MA stack (10/20/50/200), 52w-high distance, base shape, prior
   consolidation, round-number proximity.
4. **Gap-vs-structure alignment** — does the gap punch THROUGH resistance (institutional
   confirmation) or fade INTO a congestion zone?
5. **Methodology-fit / setup-class** — Pradeep small-cap-explosive vs Qullamaggie
   mature-leader-breakout vs episodic mid-cap-with-neglect; different rubrics per class.

### 1.2 Pradeep's catalyst hierarchy (per `user_pradeep_catalyst_hierarchy`)
The catalyst axis is itself ranked, strongest first:

1. **Theme** (the #1 catalyst driver — the operator calls the theme axis "absolutely critical")
2. **Government policy** change (regulatory / tariff / subsidy)
3. **Shortages** (supply-demand imbalance)
4. **Sales acceleration / new product / management change / etc.** (company-specific operational)

Operator's quantitative steer: theme should be **dominant — ~1.5–2× fundamentals**, not co-equal.

### 1.3 Catalyst quality depth (per `user_catalyst_depth`, `user_pradeep_revenue_over_eps`)
Within the catalyst axis, "quality" is multi-dimensional, not single-magnitude:
- **Revenue is the signal on GROWTH names** — the market does not pay for EPS change; EPS matters
  only in TURNAROUNDS (loss→profit inflection).
- **Acceleration** (Q/Q + Y/Y, accelerating vs decelerating) IS the edge — peak-growth inflection.
- **Materiality is company-relative** — news existence ≠ EP-grade. A $270M deal is transformative
  for a $100M micro-cap, a rounding error for a mega-cap (the RUM vs mega-cap example).
- **Durability** (Pradeep 6/16) — a long-term catalyst = ≥2 trailing Q of high revenue growth
  **AND** ≥4 forward-projected Q (the 39%-class is illustrative; the *shape* is the point).

### 1.4 The fire framing (per `ep_fire_panel_load_bearing_design`)
The load-bearing thing is the actual **FIRE**, and fire is **multi-axis** — theme is just one
(Pradeep #1). A real EP needs a fire, NOT "a real EP needs a theme." The 6/5 backtest **refuted a
naive theme-gate** (themeless = 88% of HIGHs, +5.73%, holds the +137% winner). Conclusion: gate on
**fire-PRESENCE on any axis**, never on theme-absence — and the **catalyst axis is the real
accuracy lever**, not the theme axis. Make catalyst grading trustworthy first, *then* gate on fire.
This is the guardrail against any composition that quietly turns theme-membership into a gate.

---

## 2. The PLAN #-family map (what each task owns)

The meta-rubric is one parent (#329) with a family of children. Reconciled from PLAN.md as of
2026-06-24.

| # | ETA | Status | Owns |
|---|---|---|---|
| **#329** | 2026-06-24 | in_progress | **PARENT** — meta-rubric composition (Phase 5). Path A decided. This doc + the 6/18 reconciliation spec are its "reconcile-first + anchor" deliverables. |
| **#328** | 2026-06-24 | in_progress | **Theme as a scored rubric input** — the theme axis. "Absolutely critical" (Pradeep #1). Today theme is display-only + qualitative in the judge; this makes stage+score an explicit input. |
| **#330** | 2026-06-30 | pending | **Technical structure** as an explicit, calibrated, traceable axis (MAs, 52w-high, base, consolidation, round#). Gated behind #329 spec. |
| **#331** | 2026-07-02 | pending | **Gap-vs-structure alignment** as an explicit axis (through-resistance vs into-congestion). Gated behind #329 + #330 structure primitives. |
| **#332** | 2026-07-25 | pending | **Methodology-fit / setup-class rubrics** (Pradeep vs Qullamaggie vs episodic). The long pole — composes ON TOP of #328/#330/#331. |
| **#333** | 2026-06-27 | pending | **Catalyst durability forward axis** (≥4Q projected). The forward leg the rubric lacks today; gated on direct-sourcing backbone (#210/#211). |
| **#335** | 2026-07-03 | pending | **LOAD-BEARING FLIP** — makes the enriched composite authoritative on the live paper grade. CHANGE_PROCESS + sign-off + DB toggle + ONE batched re-grade. Sequencing, post-6/22 trade-set-stability. |
| #336 | (in_progress) | — | Alert + /why judge-decision traceability (display; per-axis `axis_reads` rides #335). |
| #337 | (pending) | — | Monthly judge-judgment review (aggregate "is the judge calling EPs right?"). |

Catalyst-axis INPUT dependencies (not children, but feed the catalyst axis): **#210** (direct
primary-source sourcing backbone), **#211** (news-gap discovery loop), **#360** (catalyst-text
grounding — CLOSED 6/23). #233 (Perplexity as labeled second-opinion into the judge) feeds the
catalyst/theme read.

---

## 3. Current-state map — as-built at HEAD (re-verified 2026-06-24)

The three composition surfaces today, and per-axis where each axis actually lives. **Re-verified
against HEAD** — PLAN's "shipped 6/18" claims refer to *infrastructure* (function signatures, the
eval harness); the *live grade path* is unchanged since 6/18.

### 3.1 The three composition surfaces

| Surface | Authority | How it composes | Calibrated? | Traceable? |
|---|---|---|---|---|
| **Holistic judge** (`grade_holistic`, Opus) | **LIVE/authoritative** for tier on paper path | LLM reads a 6-clause prose rubric (`_RUBRIC` v3) + signals as raw context → emits tier/grade/direction/materiality/fire_axes/rationale | **No** — qualitative prose, no per-axis weights | **Partial** — `fire_axes` + `materiality_tier` + ≤3-sentence rationale; no per-axis contribution |
| **Deterministic catalyst rubric** (`score_ticker`, 6 axes → /39) | **Advisory metadata** on alert | Explicit numeric axes: revenue·EPS·margin·beat·guidance·milestone → composite/39 → label | **Yes** (per-axis points) | **Yes** — but **fundamentals only** |
| **Conviction floor** (`_score_ep` → `ep_score` → tier) | **Fallback** when judge fails open | gap% + catalyst enum + prior_momentum + R4 theme bonus (+10, env-flagged) | crude/numeric | breakdown dict |

The judge is the real composition layer. The deterministic rubric is calibrated+traceable but
**narrow** (it scores only the catalyst-fundamentals component, exactly as `catalyst_rubric.md`
SSoT intends — structure/gap/theme absent is *by design*, deferred to "Phase 5 meta-rubric").

> **Reconciliation note (stale source flagged).** `ep_grade_judge.py`'s module docstring still
> reads "Wave 1 SHADOW... writes only advisory columns and **drives nothing**... the live grade
> stays the conviction floor." That is **STALE** — verified at HEAD: the W2c load-bearing override
> (#243) is live. `_resolve_grade_authority(...)` returns `do_override`, and when the
> `get_holistic_judge_enabled` toggle is ON the judge tier **overwrites** the authoritative
> `score_tier` the alert + ORB entry read (`ep_detector.py` ~2849–2903: `r["score_tier"] =
> new_tier`; `'none'`→suppression, MODERATE→HIGH→ORB-eligible; `baseline_floor_tier` kept as the
> counterfactual; a None verdict fails open to the floor). Per PLAN #329 / the 6/18 spec the toggle
> flipped ON 2026-06-10. So "load-bearing" in this doc is correct; the docstring is the source that
> is wrong — flagged here so the next reader of that file is not misled. (Out of scope for this
> read-only pass to edit the docstring; worth a one-line fix when the file is next touched.)

### 3.2 Per-axis as-built state

Legend: **live** = passed to the judge / drives the grade today · **infra-exists** = signature/
eval support built but NOT passed at the live call site · **partial** = raw signal present, no
explicit/calibrated axis · **aspirational** = not built.

| Axis | As-built state | Detail (HEAD) |
|---|---|---|
| Catalyst magnitude/quality | **live** (adequate) | Judge reads grounded corpus (clause 1/4); det. rubric scores 6 fundamentals axes. |
| Catalyst materiality (company-relative) | **live** | Deterministic deal÷cap tier (`rule_materiality`) passed + judge clause 2; `materiality_tier` output. #189 shipped. |
| Catalyst freshness (`has_direct_source`) | **partial / DEGRADED** | Rubric v3 clause 1 leans on it, but it is **NOT threaded into the judge payload** (see §3.3) → judge always sees "Direct source present: no". |
| Catalyst durability (forward ≥4Q) | **aspirational** | Rubric scores trailing accel only; forward leg = **#333**, gated on #210/#211 sourcing. |
| Catalyst text grounding (#360) | **live, CLOSED 6/23** | Stored `catalyst` field now derives from grounded `claude_analysis` when `has_direct_source` (display/storage coherence; `_resolve_catalyst_text`). Distinct from the judge-payload gap below. |
| **Theme — membership** (Pradeep #1) | **partial** | Only the boolean `in_active_theme` reaches the judge; floor has a flat +10 bonus. |
| **Theme — STAGE & SCORE (heat)** | **infra-exists, NOT live** | `assemble_judge_inputs` accepts `theme_stage`/`theme_score` and renders them when present, and `get_theme_membership` computes them + the alert shows them — but the **live call site does not pass them**. The judge cannot weight Accelerating-92 vs Fading-41. The sharp #328 finding. |
| Narrative (Lane 2, #167) | **live** (adequate) | `active_narratives` + bool passed; judge clause 3/5; `fire_axes` "narrative". |
| **Technical structure** (MAs, 52w-high, base, round#) | **partial → aspirational** | Judge gets gap%, pm_rvol, vol%ile only — NO MA/resistance/base context. Explicit axis = **#330**. |
| **Gap-vs-structure alignment** | **aspirational** | Judge has gap% but no level context to align against; clause 5 has nothing to operate on. = **#331**. |
| **Methodology-fit / setup-class** | **aspirational** | One rubric for all setups. = **#332**. |
| Tape / intraday character (#299) | **infra-exists, NOT live** | Payload structure built; not passed (eval-gated). |
| Per-axis traceability (`axis_reads`) | **infra-exists, NOT live** | `_judge_tool(include_axis_reads=True)` eval variant built; live tool def byte-identical (off). Live use rides #335. |
| `revenue_stage` | **infra-exists, NOT live** | Accepted by `assemble_judge_inputs`; not passed at live call site → always "Revenue-stage: no". |

### 3.3 ANCHOR FINDING — the call-site defect is STILL LIVE as of 2026-06-24

The live judge call (`ep_detector.py`, `assemble_judge_inputs(...)` ~line 2829) passes **only**:
`grounded_text, market_cap, sector, materiality_tier, active_narratives`.

It does **NOT** thread `has_direct_source`, `revenue_stage`, `theme_stage`, or `theme_score` —
all of which the function accepts and the prompt renders unconditionally. Consequences:
- The judge **always** sees "Direct source present: no" and "Revenue-stage: no".
- Rubric v3 clause 1 makes `has_direct_source=false` + a materiality-driven promotion the
  "highest-risk, prefer the floor tier" pattern → the judge applies **freshness skepticism
  universally** and cannot credit a genuinely fresh, directly-sourced 8-K.
- The theme axis (the "absolutely critical" #328) is invisible beyond the membership boolean.

**This is a likely live grade-affecting defect, not only a theme gap.** `has_direct_source` IS
computed and in use elsewhere on the hot path (`_resolve_catalyst_text` for #360) — it is simply
not passed to the judge. Nothing shipped on this thread since the 6/18 spec; the §2.1 finding
there is reproduced live here. **Right-sizing (advisor 6/18, recorded):** the judge reads the
corpus substance including dated markers (`[SEC 8-K filed <date>…]`), so it can often establish
freshness directly even with the meta-flag stuck at "no" — the 6/18 sizing pass graded HIGH/hold
on ~all 184 rows. So this axis is likely LOW-IMPACT; the batched re-grade (#335) measures it. It
is the *anchor* because it is the cleanest, already-computed signal the judge is structurally
blind to — and the rubric explicitly depends on it.

### 3.4 Gate reality
The judge is **load-bearing** (toggle ON since 6/10). Enriching the **live** payload changes live
verdicts by construction → every enrich item is grade-affecting and rides **#335** (CHANGE_PROCESS
+ N≥10 backtest + operator sign-off + DB toggle for instant revert). Build + measurement happen on
the **eval/shadow arm** first (the with-vs-without delta IS the #335 evidence). Per the operator's
6/18 cost directive, the eval spend is **ONE batched re-grade** covering all pending axes at once
(`eval_judge_enrich --regrade`), not one paid run per axis. **Fail-open-to-floor** is preserved at
every step — a missing/blind axis never demotes a real EP.

---

## 4. The settled frame (do not re-open)

- **Architecture = Path A** (operator-decided 2026-06-18): enrich the ONE judge — (i) pass the
  inputs it's blind to, (ii) add per-axis `axis_reads` traceability to the judge's OWN output,
  (iii) calibration rides the existing operator-labeled eval (ADR 0011 go-live gate), not a
  regression fit. Path B (a standalone calibrated numeric `meta_rubric_score`) remains the
  forward-data-gated registry **cross-check** (`phase5_meta_rubric_calibration`, ~9/8, N≥30) —
  a cross-check, never a second grade authority. **This registry review is the specific orphan
  #329 was opened to anchor:** it carried real intent + a date but had NO PLAN #-task/ETA, so the
  advisory composite never moved for lack of a task (the 6/18 sweep's headline miss). #329 pulls
  it into the plan as the Path-B cross-check; the advisory build itself is un-gated (operator
  de-gated it 6/04 — the N≥30 gate governs only weight *calibration*, not the advisory build).
- **SSoT targets when the axes land:** a NEW `docs/setups/meta_rubric.md` for the composition
  logic; each new signal axis (#330 structure, #331 gap-alignment) gets its OWN `docs/setups/*.md`
  — per `catalyst_rubric.md`'s governing rule "add those signals as separate inputs, each with
  their own SSoT." The fundamentals rubric is NOT edited to absorb them.
- **Flip timing (#335)** is sequencing (post-6/22 trade-set-stability cluster), filed with an ETA
  — not a composition decision.

---

## 5. OPEN COMPOSITION DECISIONS — for the operator's design pass

Framed as decisions with options. **None is pre-picked** — composition is the operator's call.

### D1 (the unlock) — what does "theme as a *scored* input" (#328) mean under Path A?
The #328 title says theme as a "**scored** rubric input," but decided Path A keeps composition in
the judge's **prose**, not numeric weights. So the genuine decision is the *mechanism*:

- **Option (a) — pure Path A:** the judge SEES `theme_stage`/`theme_score` and weights it
  qualitatively (prose clause + `axis_reads` traceability). Minimal, consistent with ADR 0011,
  fastest to value. "Scored" = the judge reads the score, doesn't arithmetic on it.
- **Option (b) — hybrid (leans Path B):** a deterministic numeric theme sub-score mechanically
  adjusts the composite/gate (e.g. stage→multiplier on the floor or a numeric axis the judge is
  handed). More explicit/calibrated, but introduces a numeric surface to reconcile with the judge.

*This single question gates the whole theme axis — recommend leading the design pass here.*

### D2 — the theme stage→adjustment mapping (#328)
Regardless of D1's mechanism, the stage→effect mapping needs filling. Template to complete:

| Theme stage | Proposed effect (operator to set) |
|---|---|
| Accelerating | boost? (how much / what direction language) |
| Mainstream | sustain? |
| Nascent | partial credit? |
| Fading | reduce / neutral? |
| Standalone (no active theme) | **no theme credit** — but NOT a demote (the fire framing: themeless EPs are 88% of HIGHs and profitable). |

Plus: how does the already-shipped **blind-spot vs stands-alone** distinction (a missing theme
because coverage is blind vs because the name genuinely stands alone — shipped 6/18 on the alert)
feed this? A blind-spot miss must not be scored as "no theme."

### D3 — Pradeep-hierarchy encoding (theme > policy > shortage > sales; theme dominant 1.5–2×)
Today the hierarchy is qualitative prose in `_RUBRIC` clause 3. The operator wants theme
**dominant**. Decision:

- **Option (a):** keep it as prose the operator signs off on (pure Path A — "theme is the #1
  catalyst; weight it ~1.5–2× any fundamentals-based catalyst" as rubric language).
- **Option (b):** quantify relative weights (e.g. explicit per-catalyst-type multipliers) — a push
  toward Path B's numeric composite.

### D4 — `axis_reads` traceability granularity
Per-axis **{lit? · direction · ≤1-line note}** (built today, eval-only) vs a **numeric per-axis
contribution** (closer to Path B). The richer the unit, the closer to a numeric composite.

### D5 — structure & gap-alignment primitives (#330 / #331)
What structure context does the judge get, and how is alignment defined? To scope at design time:
- Which structure primitives feed the axis (MA stack 10/20/50/200 alignment, 52w-high distance,
  base age/shape from `mi_flag_candidates`, prior consolidation, round-number proximity)?
- "Alignment" rule: gap THROUGH the prior high/resistance = institutional confirmation (promote)
  vs INTO a congestion zone (temper) — define the level reference and the magnitude bands.

### D6 — catalyst durability forward axis (#333)
The forward ≥4Q-projected leg requires structured forward guidance — gated on the direct-sourcing
backbone (#210/#211), NOT LLM prose. Decision is mostly *sequencing* (it can't be built reliably
until sourcing lands) but the operator should confirm the durability *shape* (≥2 trailing Q + ≥4
forward Q of high revenue growth) as the bar.

### D7 — setup-class rubrics (#332)
Do Pradeep small-cap-explosive / Qullamaggie mature-leader / episodic-with-neglect get **distinct
rubrics**, or one rubric with class-conditional weights? The long pole — composes on top of
D1–D5. Likely a later design pass once the core axes are explicit.

---

## 6. What this doc deliberately does NOT do
- Does not compose or finalize the rubric (weights, mappings, formulas) — operator's call.
- Does not change any production code; read-only reconcile + this one doc.
- Does not re-open the Path-A architecture decision (settled 6/18).
- Does not re-derive the detailed delta matrix — see
  `docs/analysis/meta_rubric_reconciliation_329_2026-06-18.md`.
- Preserves the fire framing: composition must gate on fire-PRESENCE on any axis, never on
  theme-absence.

---

## 7. Pointers
- **Detailed delta (point-in-time):** `docs/analysis/meta_rubric_reconciliation_329_2026-06-18.md`
- **Code:** `agents/market_intelligence/ep_grade_judge.py` (judge + `assemble_judge_inputs` + v3
  rubric), `catalyst_rubric_runtime.py` (det. 6-axis rubric + `get_theme_membership`),
  `ep_detector.py` (live judge call site ~2829; floor `_score_ep`; `_resolve_catalyst_text` #360)
- **SSoT:** `docs/setups/catalyst_rubric.md` (fundamentals only) · future
  `docs/setups/meta_rubric.md` (composition) + per-axis SSoTs for #330/#331
- **ADRs:** `docs/decisions/0011-ep-holistic-grade-judge.md` (the judge) ·
  `docs/decisions/0003-ep-selectivity-overhaul.md` (Phase 5 origin)
- **Registry:** `data_gated_reviews.yaml::phase5_meta_rubric_calibration` (Path B cross-check, N≥30)
- **Memories:** `user_meta_rubric_architecture`, `user_catalyst_depth`,
  `user_pradeep_catalyst_hierarchy`, `user_pradeep_revenue_over_eps`,
  `ep_fire_panel_load_bearing_design`, `user_mental_model`
