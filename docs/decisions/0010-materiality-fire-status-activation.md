# ADR 0010 — Materiality (#189) activation of the fire panel (#201) catalyst axis

**Status:** STAGED (not flipped). Wave 4 of the North Star weekend spine.
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

## Optional intermediate: shadow-measure phase (post-6/8, pre-flip)

If we want real-data evidence on the catalyst-only denominator before the flip (rather
than flipping straight off the eval's historical 23%):

1. DDL (idempotent, in `db.py` ensure block): `ALTER TABLE mi_ep_alerts ADD COLUMN IF
   NOT EXISTS materiality_tier TEXT`, `... fire_status_mat_shadow TEXT`.
2. A **separate post-scan offline job** (never `run_ep_scan`, never `_compute_fire_status`)
   that reads the day's `fire_axes == ['catalyst']` strong/gc alerts, computes
   materiality, and writes the two shadow cols + the `fire_status` it WOULD produce.
3. Weekly digest line: catalyst-only-fire count, how many materiality would demote, and
   (once paper-R matures) the R of demoted-vs-kept. **That R is the activation evidence.**

This phase is itself optional — the eval already gives the reclassification rate; its
only added value is real-data confirmation + the R join. Build it only if the R-join is
the deciding evidence (likely yes, since R is exactly the metric the eval lacked).

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
