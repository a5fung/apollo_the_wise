# #274 C4 — theme-merge arm offline replay: PASS (Lane-1 pre-build, 2026-07-11)

**What (ADR 0025 §3):** the merge arm's sign-off gate — an offline replay of Stage-A (deterministic
candidate pairing) → Stage-B (LLM thesis-coherence adjudication) over the current active-theme
cohort, checked against the legit-kill anchors. Probe: `scripts/probes/_274_merge_replay.py`
(read-only — proposes; mutates nothing). Stage-B = Haiku with the ADR's specified prompt (negative
exemplars + "merge on shared DRIVER, never on sector label").

## Result — ✓ PASS (zero legit-kill merges; real fragmentation collapsed; precision confirmed)

- **Stage A:** 31 candidate pairs across 12 narrative families (the fragmentation map). Biggest:
  insurance (8 themes), fintech/payments (7), oncology (5), reit (4).
- **Stage B:** **3 MERGE · 3 PARENT_CHILD · 25 DISTINCT · 0 errors.**
- **Legit-kill check: ✓ PASS** — both ADR anchors safe:
  - P&C Underwriters × Specialty-Catastrophe → **PARENT_CHILD** (sub-theme, not a merge — correct)
  - Office REIT × Multifamily REIT → **DISTINCT** (opposite drivers — correct)

### The action list (what would collapse)

| verdict | absorbed | into | shared driver |
|---|---|---|---|
| MERGE | Oncology Targeted Therapy Biotechs | Clinical-Stage Oncology Drug Development | clinical-oncology capital rotation |
| MERGE | Quantum Computing Hardware & Annealing | Pure-Play Quantum Computing Hardware | quantum investment/policy cycle |
| MERGE | Multifamily Apartment REITs | Coastal & Suburban Residential Rental REITs | residential-rental housing demand |
| PARENT_CHILD | Specialty-Catastrophe Underwriters | P&C Underwriters | cat-loss slice of P&C |
| PARENT_CHILD | Antibody-Based Oncology & Autoimmune | Clinical-Stage Oncology Drug Development | antibody subset of oncology rotation |
| PARENT_CHILD | Inflammatory Disease & Immunology Biologics | Clinical-Stage Autoimmune Therapeutics | ORKA catalyst within autoimmune |

**6 of 31 fragmented pairs resolved; 25 kept correctly separate.**

## Why this validates the design (driver-based precision, not sector-label merging)

1. **The adjudicator navigated the residential-REIT space exactly as the ADR wants:** it merged
   Multifamily *into Coastal Residential* (both housing-rental demand — the same trade) while
   keeping *Office* DISTINCT (return-to-office recovery — the opposite driver). Same sector,
   correct split on driver.
2. **It did NOT merge on sector label.** All 8 insurance themes stayed separate (P&C vs Life vs
   Brokerage vs Mortgage vs Specialty — each a different driver); all 7 fintech themes stayed
   separate (macro-rate wealth-mgmt vs EM-credit vs cross-border payments vs corporate-spend). A
   naive sector-merge would have collapsed these into 2 mega-themes — the arm correctly did not.
3. **The safety property holds:** the arm is *conservative* — it resolves genuine one-driver
   duplicates and leaves every real sub-industry intact. Zero legit-kills is the load-bearing
   criterion, and it passed.

## Caveats (honesty)

- **Single Haiku run, non-deterministic.** This validates the *design* (the ADR's exemplars +
  driver instruction produce correct verdicts on the live cohort). The C3 build should add
  validation-grade rigor (temp=0 / retry / the `_extract_json_object` depth-aware parser) before
  the live flip — a one-run PASS is a green light for the design, not the production hardening.
- **Stage-A here is my implementation of the ADR's spec** (curated stem list + anchor-pairing to
  bound pairs to ~(n−1)/family). The C2 card formalizes it; the anchor-pairing (each theme vs the
  family's largest) is a defensible bound that always includes the legit-kill anchors, but the
  production Stage-A may pair differently (the ADR allows ≤8/night with a family-cluster gate).

## Recommendation for the sitting

- **ADR 0025 F1–F3: the merge-arm design is replay-validated — sign it.** The thesis-coherence
  adjudicator collapses real fragmentation (6/31) while preserving all legit sub-industries and
  passing both legit-kill anchors. Build C1–C3 behind `THEME_MERGE_ARM` (default on at merge, per
  the ADR's no-dark-period rule since it's a no-money surface and now evidence-pre-validated).
- The action list above is the *expected* first-night behavior to sanity-check post-deploy against
  the `theme_fragmentation_resolution` gated review.

*Feeds #274 / ADR 0025 F1–F3. No-money surface (themes feed only the shadow judge theme-axis #328).*
