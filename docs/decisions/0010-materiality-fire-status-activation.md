# ADR 0010 — Materiality (#189) activation of the fire panel (#201) catalyst axis

**Status:** SUPERSEDED by ADR 0011 (#249, 2026-06-10). The staged flip never shipped
and never will: the holistic grade judge went LOAD-BEARING 2026-06-10 (operator-signed)
and owns materiality on every graded alert — its first live call (CBRL, MODERATE→none
on a one-time litigation settlement) is exactly the demotion this ADR staged.
`materiality_shadow.py` + its 16:25 job + `_compute_fire_status` are retired; the
judge's verdict `fire_axes` is the fire signal now. Historical shadow columns frozen.
**Date:** 2026-06-07. **Owner decision (the flip):** operator, post-6/8 + R-evidence.
**Supersedes nothing; activates the guardrail designed in** `ep_fire_panel_load_bearing_design` (memory).

---

## Context — why this is STAGED, not shipped

The fire panel (#201, `ep_detector._compute_fire_status`) lights the **catalyst axis**
on `grade ∈ {strong, game_changer} AND catalyst_type ∉ NON_FIRE_TYPES`. The design
memory projects this runs **~95% `fire_seen`** — too permissive — because the
conviction floor already requires a strong/gc grade, so the catalyst axis mostly
re-encodes the (untrusted) grade. The fire-discovery guardrail (`real_unknown` vs
`no_fire_confirmed` vs `fire_seen`) is therefore **empty-by-construction** until a
signal that can say "graded big BUT not a real fire" feeds it.

**#189 materiality is that signal:** "news existence ≠ EP-grade." A $50M deal is
transformative for a $200M micro-cap and a rounding error for a $600B mega. The pure
helpers (`catalyst_materiality.py`: deal-value parse + deal/cap ratio tiers, 18 tests)
+ a Sonnet judgment layer reclassify **~23% of all graded strong/gc** as not-material.

### Two hard constraints that make this STAGED

1. **Hot-path freeze.** `_compute_fire_status` first produces live rows **Monday
   2026-06-08** (#200/#201 first scan). Per the #115 discipline we do NOT modify the
   firing path the day before its first verification. The flip lands *after* the
   baseline exists.
2. **No-gate-on-saturated-metric (evidence).** The 6/6 read-only eval
   (`scripts/eval_catalyst_materiality.py`, N=122) found material-vs-not fwd5d
   +10.2%/+8.9%, fwd10d INVERTS (+12.8 vs +15.6), win 93–97% **both arms** — the
   fwd-from-gap-close metric is **saturated/drift-dominated** and cannot discriminate
   (memory `feedback_validate_metric_before_decision`). **Pre-registered verdict: DO
   NOT gate the catalyst axis on materiality on this metric.** The activation needs
   **entry-aware / R-multiple** outcomes (live paper R), which don't exist until the
   paper-R cohort matures — **weeks out**.

⇒ **Nothing built this weekend makes the flip happen sooner; the binding constraint is
evidence, not code.** Wave 4's honest scope (per the execution plan) is *stage the
wiring*, not flip it. This doc IS the staged wiring.

### Scope correction (advisor 2026-06-07)

Materiality refines **only the catalyst axis**. A name that is `fire_seen` via the
theme or narrative axis stays `fire_seen` regardless of an immaterial catalyst. So the
cohort materiality can actually move is **catalyst-ONLY fires** (`fire_axes == ['catalyst']`),
a **smaller denominator** than the eval's "23% of all strong/gc." Any shadow telemetry
MUST report that denominator or it will look like it does less than the eval implied.

---

## The flip — ready-to-apply diff (apply post-6/8, behind the evidence gate)

`agents/market_intelligence/ep_detector.py::_compute_fire_status` — add a
`materiality_tier` kwarg (computed by the caller in the post-loop refine, where
`catalyst_type` is already known) and refine the catalyst-axis predicate:

```python
def _compute_fire_status(
    *,
    in_theme: bool,
    in_narrative: bool,
    catalyst_quality: str | None,
    catalyst_text: str | None,
    catalyst_type=_FIRE_UNSET,
    materiality_tier: str | None = None,   # #189 — only set in the refine pass
) -> tuple[str, list[str]]:
    ...
    else:  # refine pass
        from agents.market_intelligence.catalyst_type_classifier import NON_FIRE_TYPES
        from agents.market_intelligence.catalyst_materiality import is_material
        catalyst_fire = (
            _material
            and catalyst_type is not None
            and catalyst_type not in NON_FIRE_TYPES
            # #189 activation: a strong/gc NAMED fire that is CONFIRMED immaterial
            # (minor/immaterial tier) is not a real fire — it drops to the unknown
            # buckets, which is what gives the guardrail its discriminating signal.
            # FAIL-OPEN: materiality_tier is None (couldn't judge) => treat as
            # material, never demote on a MISSING signal — only on a CONFIRMED
            # immaterial one. Same fail-open posture as the rest of the panel.
            and (materiality_tier is None or is_material(materiality_tier))
        )
```

Caller (post-loop refine site, `run_ep_scan` ~ep_detector.py:2047 / the `set_ep_alert*`
path): compute `materiality_tier` for the catalyst-only-fire subset (rule-first via
`rule_materiality(extract_deal_value(text), market_cap)`; Sonnet judgment layer reused
from the eval for non-deal catalysts), pass it into the refine call.

**Fail-open is load-bearing:** the gate demotes ONLY a CONFIRMED immaterial fire, never
an absent one — so a sourcing/judgment gap can never silently kill a real EP (the RUM
$270M-deal class stays `fire_seen`).

## Shadow-measure phase — BUILT 2026-06-08 (staged for post-EOD deploy)

Built because the R-join IS the deciding evidence (the metric the eval lacked), and
because accruing `materiality_tier` from day one means no backfill when the R cohort
matures. Pure evidence-accrual — never the flip, never the hot path.

1. **DDL** (idempotent, `db.py` ensure block): `materiality_tier`,
   `materiality_source`, `fire_status_mat_shadow` on `mi_ep_alerts`. Writer helper
   `update_ep_alert_materiality_shadow`.
2. **Offline job** `agents/market_intelligence/materiality_shadow.py`
   (`run_materiality_shadow`) — wired at **16:25 ET** (`_materiality_shadow_job`,
   after the 16:15 post-EOD audit). Never `run_ep_scan`, never `_compute_fire_status`
   as a writer. Reads the day's `fire_axes == ['catalyst']` strong/gc alerts, computes
   the materiality tier, writes the three shadow cols + the would-be fire_status.
3. **Would-be fire_status WITHOUT editing the frozen hot path:** the writer calls the
   UNCHANGED `_compute_fire_status` with `catalyst_type` forced to a NON_FIRE value
   when the catalyst is CONFIRMED immaterial — reproducing the staged flip diff's
   demotion through the same had-inputs tail, no duplication, no edit to ep_detector.py
   on its first-verify day (#115). FAIL-OPEN preserved (is_material(None)=True).
4. **One shared judgment layer:** `catalyst_materiality.assess_materiality`
   (rule-first → Sonnet on abstain) + `judge_materiality_llm` — the eval
   (`eval_catalyst_materiality.py`) now calls the same copy (no prompt divergence,
   feedback_single_source_of_truth). 11 unit tests (`tests/test_materiality_shadow.py`).
5. **Weekly digest:** `summarize_materiality_shadow(days)` — catalyst-only count +
   how-many-would-demote + tier breakdown, with an explicit "counts only — entry-aware
   R pending, NOT a verdict" banner (mirrors `fire_status_r_cohort.py` posture; avoids
   the #46 zero-heavy conclusion trap). Wiring into the Sunday review is a fast-follow.

**DONE-criterion (not a verdict):** the job correctly populates the three cols on real
rows + the digest degrades gracefully on the thin cohort. The flip stays gated below.

## Activation gate (the flip is operator-owned)

Tracked predicate `materiality_fire_status_activation` in `data_gated_reviews.yaml`.
The flip ships ONLY when ALL hold:
1. #200/#201 fire_status baseline VERIFIED live (Monday 6/8 first scan clean).
2. **Entry-aware R evidence** that catalyst-only immaterial fires underperform material
   ones (live paper-R cohort, NOT fwd-from-gap-close — the saturated metric the eval ruled out).
3. CHANGE_PROCESS entry in `docs/setups/CHANGE_PROCESS.md` + the SSoT updated same commit.
4. **Operator sign-off on the exact rule** (the HARD-gate: the agent must not classify
   the demotion rule "correct" without operator judgment).

Until then: `_compute_fire_status` stays byte-identical; `catalyst_materiality.py` stays
EVAL-only (unimported by the live path).

## Why this is "fully complete" for the weekend

The live flip is evidence-gated weeks out by design; it cannot and should not ship this
weekend. "Fully complete the spine" = **shadow/staged-complete** (the plan's own DoD:
"the catalyst-discovery spine *in shadow* by Mon EOD"). This doc makes the flip a
one-sitting, fully-specified change once the evidence lands — that is the deliverable.
Accelerate on build; hold the line on the flip.
