# Judge model eval — GROUNDED cohort, Sonnet 4.6 vs Opus 4.8 (#252)

Run 2026-06-09 ~17:45 ET on prod (`eval_judge_models.py --grounded --days 14`,
point-in-time SEC+wires corpus, no web — #253 caveat: web-only catalysts invisible
to BOTH models, fair pairwise). **17 disagreements. The OPERATOR labels which model
is right per row; the agent does not self-certify** (HARD-gate rule). Outcome
updates `docs/model_selection_baseline.md`; default stays Sonnet until then.

Pricing context: opus-4-8 $5/$25 vs sonnet $3/$15 per MTok — cost gap is small;
quality on disagreements is the decision lever.

## Headline patterns (agent read, for labeling convenience — not verdicts)

1. **Opus is more decisive in both directions on GROUNDED input too** (`none` or
   `HIGH` where Sonnet parks at `MODERATE`). This **weakens** the "divergence was a
   thin-input artifact" hypothesis — the models genuinely differ on the holistic task.
2. **Opus salvaged the no-web blind spot twice** (RCAT, SKM) by extracting hard
   catalysts from analyst-note text Sonnet dismissed.
3. **One Sonnet-favorable case** (TNDM) where Opus over-weighted a bearish PT-cut.

## Data-quality exclusions

- **ABVX 6/3 — EXCLUDE**: contaminated by the #229 gap-recording bug (recorded
  +15.1%, reality ~−44% gap-down). Both models judged a false premise.
- **AGX — judge-contract flag**: raw output `tier=HIGH, direction=demote` — the
  #253 direction-vs-tier disagreement appearing in the judge's own output. Label the
  tier question, but file the consistency point with #253's presentation work.

## Disagreement set (label column: SONNET / OPUS / NEITHER)

| # | Ticker | Date | Floor | Sonnet | Opus | Gist | LABEL |
|---|---|---|---|---|---|---|---|
| 1 | QFIN | 05-27 | HIGH | MODERATE/demote (material) | none/demote (minor) | Both demote an earnings beat; Opus harder, citing contracting loan volume −26.8% YoY | |
| 2 | AVAV | 05-28 | HIGH | MODERATE/demote (immaterial) | none/demote (immaterial) | Agree $63M vs $8.9B cap is immaterial; severity differs | |
| 3 | PHR | 05-28 | MODERATE | MODERATE/promote (material) | HIGH/promote (material) | First-time net income + 13% rev growth; tier differs | |
| 4 | RCAT | 05-28 | HIGH | none/demote (immaterial) | HIGH/hold (material) | **The #253 case.** Sonnet sees only the analyst initiation; Opus extracts Japan-MoD + Quaze from the note text and holds | |
| 5 | ASAN | 05-29 | MODERATE | MODERATE/promote | HIGH/promote | Beat above guidance high end + StackAI acq; tier differs | |
| 6 | BHVN | 05-29 | MODERATE | MODERATE/hold | HIGH/promote | 8-K R&D Day clinical data (opakalim); Opus treats as load-bearing | |
| 7 | CHA | 05-29 | MODERATE | MODERATE/promote | HIGH/promote | Clean ~65% EPS beat on the wire; tier differs | |
| 8 | NOW | 06-01 | MODERATE | MODERATE/hold (immaterial) | none/demote (immaterial) | Only hard event = CMO departure; Opus cuts a $110B mega-cap to none | |
| 9 | SAIC | 06-01 | MODERATE | MODERATE/promote (material) | MODERATE/hold (minor) | ~2% rev growth + guidance raise; quality read differs, tier same | |
| 10 | SKM | 06-01 | MODERATE | MODERATE/hold (minor) | HIGH/promote (material) | Sonnet: SEC share-exchange housekeeping only; Opus: Arm/Rebellions AI-inference collab is the catalyst | |
| 11 | TNDM | 06-01 | MODERATE | MODERATE/hold (material) | none/demote (minor) | **Sonnet-favorable?** Opus anchors on a Citi PT-cut in corpus; Sonnet weighs the beat + reaffirmed guidance | |
| 12 | GRRR | 06-02 | HIGH | HIGH/hold (transformative) | HIGH/promote (transformative) | $2B deal vs $446M cap; direction-only difference | |
| 13 | LAC | 06-02 | MODERATE | MODERATE/hold (minor) | none/demote (minor) | Corpus contradicts the "first profitable quarter" claim; Opus cuts harder | |
| 14 | MRVL | 06-02 | HIGH | MODERATE/demote (minor) | HIGH/hold (material) | Sonnet: Jensen quote = sentiment; Opus: beat + 16x RVOL + AI demand = real | |
| 15 | ABVX | 06-03 | MODERATE | none/demote | HIGH/promote (transformative) | **EXCLUDE — #229 contamination** (gap was actually −44%) | n/a |
| 16 | PGY | 06-04 | HIGH | MODERATE/demote (minor) | none/demote (immaterial) | Corpus explicit: short-squeeze, no fresh fundamentals; severity differs | |
| 17 | AGX | 06-05 | HIGH | HIGH/demote (material) | HIGH/hold (material) | Both keep HIGH on a record beat; Sonnet's demote-direction-with-HIGH-tier = contract oddity | |

## After labeling

- Majority-right model becomes `JUDGE_MODEL` candidate → `docs/model_selection_baseline.md`
  update + its own registry commit (per `shared/llm_models.py` rule). Until then: Sonnet.
- Cross-check the RCAT/SKM class against #253's Lane-2 theme-axis work — if Opus's wins
  are mostly "read the analyst note harder," #210 sourcing may close the gap model-free.
