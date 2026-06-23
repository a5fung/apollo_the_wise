# Family-A Setups — the Split, Rebuild & Roadmap (2026-06-22)

**Durable home for the 3 setups, their next steps, and WHY.** This session uncovered a structurally
broken consolidation detector + a chain of methodology mistakes; the operator split the work into 3
distinct setups. Read this before touching any of them. SSoT for the trackable next steps = the PLAN
#-tasks cited below; SSoT for the methodology = `docs/methodology/operator_shared_notes.md` + ADR 0013.

> **TIMELINE (operator 2026-06-22): this is a FAST-FOLLOW to Phase 2 real-money trading (~Wed 6/24 on
> ACH settle) — COMPLETE ALL 3 SETUPS THIS WEEK (target 2026-06-27).** Not July. All shadow / no money,
> so it runs in parallel with the live launch without touching it. Tomorrow's FIRST priority is still
> the money-critical #151 + Phase 2 (advisor); Family-A is the immediate fast-follow right after.

## The arc — why we're here
The flag→consolidation **merge** (#354, befb41e) built a Confirm/breakout entry on a consolidation
detector that was structurally broken: the runup anchor measured the runup INSIDE the base (real
setups like STM **excluded**), and the entry fired on quiet **declines** (BTU/UFO/DRUG) because it
had **no consolidation/holds gate at all** — `is_entry_tight` only checked "quiet" (rmv + abs range
≤7% + low vol), which a slow bleed-down passes. Investigating it surfaced that the code had **silently
diverged from a methodology the operator already signed** (`operator_shared_notes.md` 6/16 + ADR 0013:
tightness must be VOLATILITY-RELATIVE; the absolute ≤7% had been wrong for weeks). Operator decision:
**un-merge into 3 clean setups** + rename for clarity. Full diagnosis:
`docs/analysis/consolidation_runup_defect_2026-06-22.md`.

---

## Setup 1 — ANTICIPATION (the Pradeep tight-day play) · ACTIVE, paused for labels · #354
**What it is:** runup (15%/10d leg) → the stock **HOLDS** the gains (Upper-Third ≤20–30% retrace +
One-Strike ≤1 daily 4% breakdown, **volatility-relative**) → a **series of tight days** (volatility-
relative contraction culminating in a Narrow-Range day) → enter **IN the coil, before the break**
(ANTICIPATE). **Strictly anticipate** — NO breakout/Confirm, NO U&R (operator split 6/22).
**Definition SSoT:** `operator_shared_notes.md` (Pradeep thread 6/16 + Gemini blueprint 6/22).
**Progress (shadow, committed):** anchor refined to the recent runup-leg peak (3–20d base, not the
global max); holds gate data-grounded on the 6/15 Pradeep cohort (declines 2–5 breakdowns/23–34%
retrace vs tight names 0–1/≤11%); confirmed the gate must be volatility-relative (HYLN).
**NEXT STEPS (in order):**
1. **Operator labels** the shortlist `docs/analysis/anticipation_shortlist_to_label_2026-06-22.md`
   (G/X) — includes the false-negative check section (canary + the §2-excluded names).
2. **Calibrate** the volatility-relative holds/tightness thresholds against the labels — **2–3
   monotonic knobs + a holdout** (anti-overfit; ~300 candidates / few labels = high overfit risk).
3. **Reuse ADR 0013's anchor machinery** (`select_consolidation_keys` carry-forward / anchor-stability)
   — replace the invented `[n−20, n−3]` heuristic, or supersede it with validation (search-before-build).
4. **PIN the deliverable (operator decision):** shortlist-for-judgment (ADR §2.5 signed) vs strictly-
   anticipate-entry. They have different pass criteria — this sets what "good vs garbage" means.
5. **Wire** the calibrated gates into the detector (SHADOW; enforce ADR 0013's provenance rule — every
   gate cites a source; sign-off for any threshold change).
6. **Re-validate** against the de-biased labels (the COO canary must survive).

## Setup 2 — HTF (High Tight Flag) · QUEUED, operator details pending · #356
**What it is:** the former flag / flag_continuation detector → its OWN setup: big runup → tight base →
enter on the **confirmed BREAKOUT** (base-high + volume). `flag_detector.py` is LIVE + load-bearing
(`/flags`, the #94 intraday break, the digest) and was **UNCHANGED this session** (clean).
**NEXT STEPS:**
1. **Operator provides the HTF spec/details** ("I'll go into details of that later", 6/22).
2. **Reconcile flag_detector's params** — the `50%/60d` runup was a prior session's UNSOURCED pick
   (first commit 2026-05-01, never validated; "VCP/Qullamaggie" attribution is unverified). Needs the
   operator's actual basis, not inheritance.
3. Refine/rename flag → HTF. Any detection-criterion change = CHANGE_PROCESS + sign-off (load-bearing).

## Setup 3 — PERSISTENT SUGAR BABIES · TBD, revisit · #357
**What it is (clarified 6/22):** NOT a setup — a stock **CONDITION** (recurring 9M-EP: ≥3 9M EOD
prints / 180d, `mi_sugar_babies_cohort`). The Telegram surface overlays the flag/HTF **stage** on the
9M cohort. Operator's thinking: any setup can include a sugar-baby stock or not → it's likely an
**additional confluence point / score input** on a stock that's already in a setup, not a standalone
play.
**NEXT STEPS:**
1. **Operator decides the role** — a confluence/scoring input on a setup, vs a standalone watchlist.
2. Re-frame the surface accordingly (the cohort is Family-B/EP universe; the stage overlay becomes HTF).

---

## The mistakes + the systemic lesson (WHY the discipline matters)
**The mistakes this session were all ONE pattern — asserting methodology from partial recall instead
of reading the captured source of truth:** "high tight flag" (my invented label), "50/60 is validated/
signed" (unverified), "let me define a base" (it was already captured), the unilateral "launch without
partials" (retracted — THE LINE), the runup-inside-base mis-explanation (twice).
**The systemic root (advisor):** a signed methodology existed (`operator_shared_notes.md` + ADR 0013),
the code **silently diverged** from it, and **nothing checks code-against-captured-methodology** —
`is_entry_tight`'s absolute range contradicted the operator's own signed 6/16 conclusion for weeks,
uncaught.
**Durable fix:** (a) grep `operator_shared_notes.md` + the relevant ADR BEFORE asserting any threshold
or provenance (memories `feedback_capture_operator_shared_notes`, `feedback_search_before_build_primitive`,
`feedback_no_unilateral_methodology_change`); (b) ENFORCE ADR 0013's provenance rule — a check that
flags any live gate value with no source citation (currently unenforced) — filed as #358.

## Advisor deep-review (2026-06-22) — the guidance
- The split is RIGHT; test-first on live data + operator labels is the missing discipline; volatility-
  relative tightness is grounded (not invented); keep it shadow / off the Phase-2 path.
- De-bias the shortlist (DONE — false-negatives can't surface from a §2-derived list); **pin the
  deliverable; reuse the anchor machinery; anti-overfit (2–3 knobs + holdout)**.
- **Tomorrow's FIRST priority = the money-critical work (#151 partial-exit, Phase 2 funding/arming),
  NOT more consolidation.**

## Artifacts (all committed)
- Diagnosis/defect: `docs/analysis/consolidation_runup_defect_2026-06-22.md`
- Methodology SSoT: `docs/methodology/operator_shared_notes.md` · Design: ADR 0013
- Acceptance test: `scripts/_consolidation_acceptance_test.py` · Holds measure: `scripts/_anticipation_holds_measure.py`
- Shortlist (to label): `scripts/_anticipation_shortlist.py` + `docs/analysis/anticipation_shortlist_to_label_2026-06-22.md`
- Fixtures: `tests/fixtures/{consolidation_acceptance,anticipation_pradeep_cohort,anticipation_universe}_bars.psv`
