# Judge model eval — CLOSED-GAP input, Sonnet 4.6 vs Opus 4.8 (#252 decision set)

Run 2026-06-10 ~19:45 ET on prod (`eval_judge_models.py --grounded --days 14`,
36 alerts → **17 disagreements**). This supersedes the 6/9 dark-axis run as the
**decision set**: same point-in-time SEC+wires corpus, but the judge's THEME
AXIS is now lit — point-in-time Lane-2 narrative cohorts feed every payload,
exactly as the live judge reads them since the lane2 deploy (the 6/9 RCAT-class
rows measured input-gap compensation, not model quality; this input has no gap).

**The OPERATOR labels which model is right per row (SONNET / OPUS / NEITHER);
the agent does not self-certify** (HARD-gate rule). Majority-right model →
`JUDGE_MODEL` in `docs/model_selection_baseline.md` + registry commit. Default
stays Sonnet until labeled. ~15–20 min; closes the last
DEFINITION_OF_DONE clause ("model-checked") for the Fri 6/12 North Star date.

## What changed vs the 6/9 dark-axis run (agent read, not verdicts)

1. **Closing the input gap CONVERGED the models on 5 previously-disagreeing
   rows** — QFIN, BHVN, LAC (→ Sonnet's view), GRRR (direction), MRVL (→ Opus's
   view). Supports the #210 thesis that input quality moves verdicts more than
   model choice.
2. **6 new disagreements appeared** (ANF, BBWI, KSS, KTOS, DELL, TTAN) — richer
   input gives the models more to weigh differently. Net 17 then, 17 now.
3. **The persistent pattern is unchanged: Opus is more decisive in both
   directions** (HIGH or none where Sonnet parks at MODERATE) — it survives
   grounding AND the lit theme axis, so it's a real disposition difference.
4. **RCAT (the #253 motivating case): the theme axis worked.** Sonnet softened
   none/demote (dark axis) → MODERATE/demote (lit axis). Opus ERRORED
   (timeout) on this row — no pairwise read; label it n/a or ask for a re-roll.
5. **Mega-cap disposition split**: DELL (Sonnet discounts a $240B cap's blowout
   to MODERATE; Opus holds HIGH) vs NOW (Sonnet holds MODERATE on
   sentiment-only; Opus cuts to none). Worth labeling consciously — it's the
   same question from both sides.

## Exclusions / flags

- **ABVX — EXCLUDE** (still #229-contaminated: recorded gap +15.1%, reality
  ~−44%; both models judged a false premise). Label n/a.
- **RCAT — Opus timeout**, Sonnet-only verdict. n/a for pairwise; the row's
  real finding (axis lit → softer Sonnet) is logged above.
- **AGX — Sonnet `HIGH/demote`** again (tier-vs-direction contract oddity,
  #253 presentation note). Label the tier question.

## Disagreement set (label column: SONNET / OPUS / NEITHER)

| # | Ticker | Date | Floor | Sonnet | Opus | Gist | LABEL |
|---|---|---|---|---|---|---|---|
| 1 | ANF | 05-27 | HIGH | MODERATE/demote (minor) | HIGH/hold (material) | ~16% EPS beat, record sales; Sonnet docks the rev miss + held guidance, Opus credits the beat | |
| 2 | BBWI | 05-27 | HIGH | MODERATE/demote (material) | none/demote (minor) | Both demote; Sonnet sees a beat-and-hold, Opus sees −3% sales + CFO exit | |
| 3 | AVAV | 05-28 | HIGH | HIGH/hold (material) | MODERATE/demote (immaterial) | **Flipped vs 6/9** (both demoted then): Sonnet now credits the $20M facility + $43M DoD contract as govt-backed; Opus calls it a rounding error on $8.8B cap | |
| 4 | KSS | 05-28 | MODERATE | none/demote (minor) | MODERATE/hold (immaterial) | In-line print, −1.7% sales, GAAP loss; severity differs | |
| 5 | KTOS | 05-28 | MODERATE | none/demote (immaterial) | MODERATE/hold (minor) | Corpus has only a puff piece; both see no catalyst, severity differs | |
| 6 | PHR | 05-28 | MODERATE | MODERATE/promote (material) | HIGH/promote (material) | First-ever net income + 13% growth; tier differs (same as 6/9) | |
| 7 | ASAN | 05-29 | MODERATE | MODERATE/promote | HIGH/promote | Beat above guidance high end, record margins; tier differs (same as 6/9) | |
| 8 | CHA | 05-29 | MODERATE | MODERATE/promote | HIGH/promote | 65% EPS beat on the wire; tier differs (same as 6/9) | |
| 9 | DELL | 05-29 | HIGH | MODERATE/demote (minor) | HIGH/hold (material) | Blowout print (+88% rev, $24.4B AI orders, guide raise); Sonnet discounts mega-cap, Opus judges the event | |
| 10 | NOW | 06-01 | MODERATE | MODERATE/hold (minor) | none/demote (immaterial) | Only hard events: CMO exit + BofA note; Opus cuts a $109B cap to none (same as 6/9) | |
| 11 | SAIC | 06-01 | MODERATE | MODERATE/hold (material) | HIGH/promote (material) | Beat + explicit EBITDA/EPS guide RAISE; Opus now promotes (6/9 it held) | |
| 12 | SKM | 06-01 | MODERATE | MODERATE/hold (material) | HIGH/promote (material) | Sonnet: 6-K share-exchange housekeeping; Opus: Arm/Rebellions AI-inference collab is the catalyst (same split as 6/9) | |
| 13 | TNDM | 06-01 | MODERATE | MODERATE/hold (material) | none/demote (immaterial) | **The 6/9 Sonnet-favorable case, persists**: Opus anchors on the Citi PT-cut; Sonnet weighs beat + reaffirmed guidance | |
| 14 | ABVX | 06-03 | MODERATE | none/demote | HIGH/promote (transformative) | **EXCLUDE — #229 contamination** | n/a |
| 15 | PGY | 06-04 | HIGH | MODERATE/demote (minor) | none/demote (immaterial) | Corpus explicit: short-squeeze, no fresh event; severity differs (same as 6/9) | |
| 16 | AGX | 06-05 | HIGH | HIGH/demote (material) | HIGH/hold (material) | Both keep HIGH on the record beat; Sonnet's demote-with-HIGH = contract oddity (same as 6/9) | |
| 17 | TTAN | 06-05 | HIGH | MODERATE/demote (material) | HIGH/hold (material) | +25% rev, margin doubling, guide raise; Sonnet demotes anyway — labels the "Sonnet parks at MODERATE" disposition directly | |

(RCAT 05-28 omitted from the labelable set: Opus timeout — Sonnet-only
MODERATE/demote, the axis-lit softening noted above.)

## After labeling

- Majority-right model → `JUDGE_MODEL` constant + `docs/model_selection_baseline.md`
  update in its own registry commit. Until then: Sonnet.
- Convergence note for the record: 5 of the 6/9 disagreements dissolved purely
  from better input — file that with #210's "input is the lever" evidence line.
- #253 closes with this doc (RCAT softening = the Lane-2 fix demonstrated) unless
  the operator wants the Opus re-roll on RCAT first.
