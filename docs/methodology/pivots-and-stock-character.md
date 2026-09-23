# Pivots & per-stock character (operator methodology, captured 2026-06-11)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


**Status: DURABLE DESIGN NOTE — deliberately not yet implemented.** The operator
dropped these principles during the MNTS/NBIS chart sessions with the explicit
instruction to capture them durably because implementation may be months out
(v2.0 P3 horizon). This doc is the SSoT for the principles; the roadmap
(`docs/roadmap/apollo-v1.1-v2.0.md` §P3) points here. When implementation
starts, promote to a #-task and treat THIS as the requirements source.

## Principle 1 — the pivot, generalized

A **pivot is any reasonable reference point for risk management**, serving both
sides of a trade:
- it locates the ENTRY (the reclaim or break of the reference), and
- it IS the STOP (risk is defined against it).

MA lines and EP-gap-day lows are merely the EASY pivots (objectively
computable). Equally valid: price congestion areas, volume shelves, resistance
zones, prior swing levels — anything the market demonstrably referenced.

Two identifiability tiers for future build-out:
1. **Computable tier**: MAs, gap-day/swing lows, prior-day levels — cheap,
   objective, partially wired today (#270 uses MA + gap-day-low pivots).
2. **Structural tier**: congestion/volume-at-price shelves, resistance zones —
   derivable from daily bars (price-level clustering), and exactly what
   chart-vision (#267) can SEE the way the operator does.

Worked example: MNTS 6/11 — the **two-fold U&R** (21EMA/20MA reclaim AND
gap-day-low reclaim resolving in one move) = two pivots agreeing, hence a tight
honest stop with the whole prior consolidation as cushion. Case study:
`docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md`.

## Principle 2 — pivots are conditioned on the STOCK'S OWN CHARACTER

**Every stock has its own character, so the right pivot differs per stock:**
- some pull back to the **10MA** in an uptrend, others to the **20MA**;
- some habitually **undercut** the 20MA before resuming, others respect it;
- **pullback duration** differs per name (2-day flags vs 2-week digestions).

Therefore pivot identification is NOT a universal formula — it requires reading
the stock's **own history, chart, and character**: which references did THIS
name's pullbacks actually respect, how deep do its undercuts run, how long do
its rests last. The operator's marked-up NBIS chart is the canonical example
(`docs/analysis/charts/nbis_character_markup_2026-06-11.jpg` — circled pullback
episodes along the 2025–26 uptrend showing the repeating MA-touch/undercut
pattern that defines NBIS's personality).

## Implementation sketch (when its time comes — v2.0 P3/P2)

1. **Character profile per ticker**, computed from its own daily history over
   the current trend: which MA its pullbacks statistically resolve at (10/20/50
   touch-and-resume frequencies), typical undercut depth (% beyond the MA),
   typical pullback duration (days), volume-contraction signature. A small
   deterministic profile — no LLM needed for the computable tier.
2. **Pivot candidates ranked per name** using the profile: "NBIS-class → 20MA
   with undercut tolerance X%; MNTS-class fast runner → gap-day low + 21EMA."
3. **Consumers**: #270-class composed entries (the ARMED/TRIGGERED references
   become character-conditioned), W2 first-pullback matrix, P3 management judge
   (proposes stops against the stock's OWN respected pivots, mechanics
   execute), chart-vision prompts (#267 — feed the profile as text alongside
   the image so the model knows what this name's normal looks like).
4. **The experience-axis tie-in**: a per-ticker character profile is exactly
   the kind of accumulated, name-specific knowledge a discretionary trader
   carries — it belongs in the same precedent/memory layer as #255, not in
   global thresholds.

## Anti-patterns to avoid (so this doesn't get mis-built later)

- Do NOT implement as one global "pullback MA" parameter tuned on aggregate
  data — that erases the per-stock character that IS the principle.
- Do NOT let pivot identification creep into seconds-scale execution; pivots
  are decision-point references (daily/intraday levels), mechanics stay
  mechanical.
- Character profiles need a freshness rule — character can change after major
  re-ratings (an MNTS-class 100% EP resets the personality).

Memories: `user_pivot_generalization`, `user_delayed_ep_reentry_template`,
`user_tight_range_entry_techniques`. Charts:
`docs/analysis/charts/nbis_character_markup_2026-06-11.jpg`,
`docs/analysis/charts/mnts_delayed_ep_2026-06-11.png`.
