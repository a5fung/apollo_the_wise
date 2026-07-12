# Judge robustness map — first live eval run (ADR 0030 C3, 2026-07-12)

**What ran:** the full 36-case adversarial corpus (`judge_robustness_corpus_v1.json`) through the
REAL judge path — `grade_holistic`, JUDGE_MODEL=claude-opus-4-8, rubric v3 (`eef69fa4`),
`include_axis_reads` on — on prod. Harness: `scripts/evals/run_judge_robustness_eval.py`
(19 tests). Pass record: `scripts/evals/judge_eval_pass_record.json` (the [5m/7] gate key).

## Result: **36/36 — GATE ✓ PASS** (overall 1.0 · positive controls 1.0 · zero hard failures)

Every class at 100%: all 7 hard-misdirection classes (M&A, stale-news incl. the fresh-8-K/
stale-content trap, dilution-as-growth, promo-PR, one-time-EPS) · all 7 degradation shapes
failed CONSERVATIVE · all 5 soft classes · **all positive controls kept/reached HIGH** — the
judge is not over-skeptical: D08 (thin-but-complete 8-K) held strong/HIGH, S25 ($45M contract on
a $95M cap) promoted to game_changer, S23 (FDA approval from a MODERATE floor) promoted.

**Standout verdicts (the rubric working as written):**
- **S03** (8-K filed today re-furnishing a 6-month-old deal): routine/none — *"the 8-K is fresh
  but its content is stale… no NEW catalyst dated today."* The direct-source trap, caught by name.
- **S19** (definitive buyout): mna/none, conf 0.98 — *"pinned just below deal price."*
- **S21** (mature $8B industrial, good-not-hot print): demoted below even the golden's allowance
  — *"no revenue acceleration or guidance raise, which is the load-bearing signal."*

## What this means for the 7/18 M1 sitting (precondition slot 1 → FILLED)

Per the pack's pre-agreed interpretation contract: **nothing blocks the authority flip from the
robustness side.** No hard-class failures → no pre-authority rubric amendments required (T1d:
no failure clusters exist to draft against). Positive-control rate 1.0 ≥ the 0.8 bar. The map +
the armed regression gate together answer "what if the judge silently degrades after authority"
— any future rubric/prompt/model change must re-clear this exact corpus.

## Honest limitation (recorded, not hedged)

A perfect score partly reflects that corpus-v1's misdirections are **legible** — the crafted
grounded_texts carry explicit tells ("no date appears in any item", "originally granted last
year"). v1 therefore proves the judge doesn't fall for *stated* misdirection; it does not yet
test *inferable* misdirection (the tell buried in a filing exhibit number, a date only derivable
from context). **Corpus-v2 hardening lane** (filed with the 0030 amendment loop, not urgent): 
strip explicit tells from ~10 clone cases + mine real FP/FN cases as they accrue post-authority
via the judge-delta digest. The gate keys on `corpus_version`, so v2 re-arms it automatically.

## Bookkeeping

- Amendment drafts (T1d): **none required** — first eval found no failure cluster.
- The C2 preflight gate ([5m/7]) arms against this record; any rubric-hash/prompt/model/corpus
  drift now FAILS deploys until a re-run passes.
- Cost: 36 judge calls ≈ $5. Spend rows via the #377 meter (by design, the only DB writes).
