# Meta-Rubric Reconciliation Spec (#329, first deliverable)

**Date:** 2026-06-18 · **Author:** session · **Status:** DRAFT for operator review
**Task:** #329 (meta-rubric composition, Phase 5) · **Parent of:** #328/#330/#331/#332 · **Flip:** #335
**Inputs read (ground truth, not memory):** `ep_grade_judge.py` (`assemble_judge_inputs`,
`_build_judge_prompt`, `_RUBRIC` v3), `catalyst_rubric_runtime.score_ep_with_rubric` +
`catalyst_rubric.score_ticker` (6-axis /39), `ep_detector` floor (`_score_ep`, R4 theme bonus,
`_resolve_grade_authority`), ADR 0011, `data_gated_reviews.yaml::phase5_meta_rubric_calibration`,
memories `user_meta_rubric_architecture` / `user_catalyst_depth` / `user_pradeep_catalyst_hierarchy`.

---

## 0. Why this doc exists

The advisor + operator caught that "build the Phase-5 meta-rubric" risked **resurrecting a
superseded concept**. The live holistic judge (ADR 0011, load-bearing on the paper EP path since
2026-06-10) **already IS a composition layer** — it composes catalyst/theme/narrative/structure/gap
into the grade. So the honest gap is NOT "we have no composition." It is:

> **the documented meta-rubric inputs are composed _implicitly and inconsistently_ — several
> aren't even passed to the judge, none carries an _explicit, calibrated, traceable_ weight.**

This doc establishes the **delta** (documented-intent vs as-built) precisely enough that the
remaining build is concrete and completable, then proposes a build path for sign-off.

---

## 1. The three composition surfaces TODAY

| Surface | Authority | How it composes | Calibrated? | Traceable? |
|---|---|---|---|---|
| **Holistic judge** (`grade_holistic`, Opus) | **LIVE/authoritative** for tier on the paper path | LLM reads a 6-clause prose rubric (`_RUBRIC` v3) + all signals as raw context → emits `tier`/`grade`/`direction_vs_floor`/`materiality_tier`/`fire_axes`/`rationale`/`confidence` | **No** — qualitative; no per-axis weights | **Partial** — `fire_axes` (which of catalyst/theme/narrative lit) + `materiality_tier` + a ≤3-sentence `rationale`; **no per-axis contribution** |
| **Deterministic catalyst rubric** (`score_ticker`, 6 axes → `/39`) | **Advisory metadata** on the alert | Explicit numeric axes: revenue, EPS, margin, beat, guidance, milestone → `composite_scaled/39` → label | **Yes** (per-axis points) | **Yes** (per-axis) — but **fundamentals only** |
| **Conviction floor** (`_score_ep` → `ep_score` → `floor_tier`) | **Fallback** (when judge fails open) | gap% + catalyst enum + `prior_momentum` + **R4 theme bonus (+10, env-flagged, "decorative")** | crude/numeric | breakdown dict |

The judge is the real composition layer. The deterministic rubric is calibrated+traceable but
**narrow (fundamentals)**. Neither composes theme-heat / structure / gap-alignment as an explicit
scored axis.

---

## 2. Reconciliation matrix — documented input × as-built

Legend: ✅ present & adequate · 🟡 present but raw/implicit · ❌ absent.
"Passed to judge?" = is the signal in the `assemble_judge_inputs` payload at all.

| Documented meta-rubric input (source) | Passed to judge? | In det. rubric? | Explicit axis? | Calibrated weight? | Per-axis traceable? | Gap → task |
|---|---|---|---|---|---|---|
| Catalyst magnitude/quality | ✅ (grounded corpus, clause 1/4) | ✅ (6 axes) | rubric ✅ / judge 🟡 prose | rubric ✅ / judge ❌ | rubric ✅ / judge 🟡 rationale | — (adequate) |
| Catalyst materiality, company-relative (`user_catalyst_depth`) | ✅ (deal÷cap tier + clause 2) | ❌ | judge tier output | 🟡 deterministic ratio tiers | ✅ `materiality_tier` | — (#189 shipped) |
| Catalyst freshness (ADR 0011 v3) | 🟡 clause 1 prose — but `has_direct_source` is **NOT threaded** (see below) so the freshness signal is degraded | ❌ | judge 🟡 prose | ❌ | 🟡 rationale | **call-site fix (§2.1)** |
| **`has_direct_source`** (direct SEC/wire source present) | ❌ **NOT passed at the live call site** → prompt always renders "Direct source present: no" | ❌ | ❌ | ❌ | ❌ | **§2.1 — likely live defect** |
| **`revenue_stage`** | ❌ **NOT passed at the live call site** → always "Revenue-stage: no" | n/a | ❌ | ❌ | ❌ | **§2.1** |
| **Catalyst durability — forward ≥4Q** (`user_catalyst_depth` 6/16) | 🟡 only if corpus mentions guidance | ❌ (trailing accel only) | ❌ | ❌ | ❌ | **#333** |
| **Theme — membership** (Pradeep #1) | 🟡 **boolean `in_active_theme` only** | ❌ | ❌ (flat +10 floor bonus) | ❌ | `fire_axes` lists "theme" | **#328** |
| **Theme — STAGE & SCORE (heat)** | ❌ **NOT in payload** (computed by `get_theme_membership`, shown on alert, never reaches judge) | ❌ | ❌ | ❌ | ❌ | **#328 (the sharp one)** |
| Narrative (Lane 2, #167) | ✅ (`active_narratives` + bool) | ❌ | 🟡 (prose, clause 3/5) | ❌ | `fire_axes` "narrative" | — (adequate) |
| **Technical structure** (MAs, 52w-high, base, consolidation, round#) | 🟡 **gap%, pm_rvol, vol%ile only — NO MA/resistance/base context** | ❌ | ❌ | ❌ | ❌ | **#330** |
| **Gap-vs-structure alignment** (through resistance vs into congestion) | ❌ (judge has gap% but no level context to align against) | ❌ | ❌ | ❌ | ❌ | **#331** |
| **Methodology-fit / setup-class** (Pradeep vs Qullamaggie vs episodic) | ❌ (one rubric for all setups) | ❌ | ❌ | ❌ | ❌ | **#332** |
| Tape / intraday character (#299) | 🟡 structure built, NOT wired (eval-gated) | ❌ | ❌ | ❌ | ❌ | #299 (already filed) |

### The two highest-leverage, lowest-cost findings
1. **Theme heat is invisible to the judge.** `get_theme_membership` already computes
   stage+score (Accelerating-92 vs Fading-41), the alert shows it — but `assemble_judge_inputs`
   passes only `in_active_theme` (bool). The judge cannot weight theme heat even *qualitatively*
   because it never sees it. **Fix = add `theme_stage`/`theme_score` to the payload + one rubric
   line.** Shadow-safe, ~trivial, the core of #328.
2. **Gap-alignment is unjudgeable today.** The judge gets `gap_pct` but no resistance / prior-high
   / MA-stack context, so clause 5 ("gap alignment modulates") has nothing to operate on.
   **Fix = pass the structure context (#330) → then alignment (#331) becomes possible.**

### 2.1 The call-site finding — the judge is blind to signals its OWN rubric cites (verified `ep_detector.py:2431`)
The live judge call passes only `grounded_text, market_cap, sector, materiality_tier,
active_narratives`. It does **not** thread `has_direct_source`, `revenue_stage`, or theme
stage/score. Because `_build_judge_prompt` renders those fields unconditionally, the judge
**always** sees "Direct source present: no" and "Revenue-stage: no". Rubric v3 clause 1 leans on
`has_direct_source` ("=false + materiality-driven promotion = highest-risk, prefer the floor
tier") — so the judge applies freshness skepticism **universally** and cannot credit a genuinely
fresh, directly-sourced 8-K. `has_direct_source` IS now on the result dict (threaded for #317
today) — it's computed, just not passed. **This is a likely live grade-affecting defect, not only
a theme gap.** Priority order for the enrich: `has_direct_source` (rubric actively depends on it)
> theme stage/score > structure context.

### 2.2 Gate reality — the judge is LOAD-BEARING (toggle ON since 6/10)
Enriching the **live** payload changes live verdicts immediately → every enrich item is
grade-affecting and rides **#335** (CHANGE_PROCESS + N≥10 backtest + sign-off + DB toggle). The
build + measurement is done on the **eval/shadow arm** first (the with-vs-without delta is exactly
the #335 evidence). "Shadow-safe" holds ONLY on the eval arm — there is no byte-neutral live edit
here (a themed/sourced name's prompt changes by construction). So the build STARTS by enriching
the payload **on the eval arm** and measuring the verdict delta, before any scored composite.

---

### 2.3 Reconciliation against the rubric SSoT (`docs/setups/catalyst_rubric.md`)
The named SSoT (CLAUDE.md HARD rule) **confirms** this spec and is not superseded by it:
- It declares itself the **fundamentals component only** and "MUST NOT be the sole input to the
  final label" — so structure/gap/theme being absent from it is *by design*, not an omission.
- It explicitly defers composition: "Phase 5 meta-rubric combines [catalyst] with theme heat
  (Phase 3), technical structure (Phase 4.1), and gap alignment (Phase 4.2)." → **#329 is that
  Phase 5; the §3 fork is genuinely open, NOT re-deciding a settled design.**
- Governing rule to honor: *"Do not over-tune the catalyst rubric to compensate for missing
  upstream signals. Add those signals as separate inputs, each with their own SSoT + quarterly
  review."* → **#330 (structure) and #331 (gap-alignment) each get their OWN `docs/setups/*.md`
  SSoT; the composition logic (#329) gets a NEW `docs/setups/meta_rubric.md` SSoT** (the
  same-commit update target when those land — NOT this analysis doc, and NOT `catalyst_rubric.md`).
  Theme-as-input (#328) likewise documents under the meta-rubric/theme SSoT, not by editing the
  fundamentals rubric.

## 3. The architectural fork (needs sign-off — this decides what #330/#331 build)

The registry review (`phase5_meta_rubric_calibration`) envisioned a **separate logistic-regression
numeric composite** (`meta_rubric_score`) — that prose predates the judge. Two coherent paths:

- **Path A — Enrich the ONE judge (recommended).** Keep ADR 0011's "one judge owns the grade."
  (i) Pass the inputs it's blind to (theme stage/score #328, structure context #330, alignment
  #331). (ii) Add **per-axis traceability to the judge's OWN output** — extend the `grade_ep` tool
  schema with a small `axis_reads` block (e.g. theme/structure/gap each: lit? direction? one-line
  why) so every grade is reconstructable per-axis without a second model. (iii) Calibration rides
  the **existing operator-labeled eval** mechanism (ADR 0011's go-live gate), not a regression fit.
  - *Pros:* no second grade authority; fastest to live value; consistent with ADR 0011; gets
    explicit+traceable without a model. *Cons:* "calibrated weights" stay implicit in the prompt.
- **Path B — Parallel numeric composite.** Build `meta_rubric_score` as the registry envisioned
  (calibrated axis weights, logistic fit at N≥30), running alongside the judge as a cross-check /
  eventual gate.
  - *Pros:* explicit+calibrated+traceable by construction. *Cons:* a second grade surface to
    reconcile with the judge; needs the N≥30 forward cohort to calibrate (the 9/8 gate); risk of
    two competing authorities.

**Recommendation:** **Path A now** (enrich + per-axis `axis_reads` traceability), keep **Path B's
standalone calibrated composite as the forward-data-gated registry item** (weight fit at N≥30, the
existing 9/8 review) used as a cross-check, not a second authority. This gives explicit + traceable
immediately and defers only the *calibrated-weights* piece to where the data actually exists —
matching the operator's 6/04 "ship advisory now" de-gate.

---

## 4. Build sequence (aligned to the launch spine)

All SHADOW until #335. Grade-affecting flip is post-6/22 (the #299/#320/#321 trade-set-stability
cluster).

| Step | Task | ETA | Gated? |
|---|---|---|---|
| Enrich payload (eval arm): `has_direct_source` (§2.1, highest priority) + `revenue_stage` + theme stage/score; measure verdict delta | #328/#329 | 6/24 | build/measure un-gated on eval arm; LIVE payload edit is grade-affecting → #335 |
| Add `axis_reads` per-axis traceability to `grade_ep` schema (eval arm; byte-neutral when absent, like tape/narrative) | #329 | 6/24 | build un-gated; live use rides #335 |
| Catalyst durability forward axis | #333 | 6/27 | behind #210/#211 sourcing |
| Structure context into payload + structure axis read | #330 | 6/30 | un-gated (shadow) |
| Gap-alignment axis read (needs #330 levels) | #331 | 7/02 | un-gated (shadow) |
| **LOAD-BEARING FLIP** (judge w/ enriched axes authoritative) | **#335** | **7/03** | CHANGE_PROCESS + N≥10 backtest + sign-off + DB toggle |
| Methodology-fit / setup-class rubric variants | #332 | 7/25 | composes on top of #330/#331 |
| Standalone calibrated composite (Path B cross-check) | registry | ~9/8 | N≥30 forward cohort |

Each shadow step reuses the established behavior-neutral pattern (`active_narratives`/`tape`:
absent → prompt byte-identical) so nothing touches the live grade until #335.

---

## 5. Open questions for the operator (sign-off before #335)

1. **Path A vs B** (§3) — confirm Path A (enrich the one judge) as primary?
2. **Exact weighting language** for clause 5 once theme-heat/structure are visible — the
   `user_pradeep_catalyst_hierarchy` order (theme ≥ 1.5–2× fundamentals) goes into the *prompt*,
   not numeric weights, under Path A. Sign-off on the prose is the rubric sign-off (ADR 0011 §gate).
3. **Flip timing** — #335 at 7/03 (just-post-6/22). Pre-6/22 would override the trade-set-stability
   rule (operator call).
4. **`axis_reads` schema** — is per-axis (lit / direction / one-line) the right traceability unit,
   or do you want a numeric per-axis contribution (closer to Path B)?

---

## 6. What this spec deliberately does NOT change

- No live grade math (all shadow until #335).
- No second M&A authority (the M&A filter stays authoritative; judge `mna` advisory — ADR 0011 §5).
- Does not reopen the deterministic rubric's fundamentals axes (already calibrated/traceable; only
  the *forward durability* leg #333 is missing).
- Fail-open-to-floor is preserved at every step (a missing/blind axis never demotes a real EP).
