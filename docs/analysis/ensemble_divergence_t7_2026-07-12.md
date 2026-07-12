# T7 — ensemble-divergence prototype (0018 slice): is two-model disagreement an uncertainty signal? (2026-07-12)

**Method:** the 36-case robustness corpus through BOTH models via the T1 harness — OPUS (the live
judge; 36/36) vs Sonnet-5 (~$1.5; 35/36 — one hard failure: S18, the acquirer-side M&A trap,
conf 0.62). Per-case diff.

## Findings

1. **Generic tier-divergence is NOISE (19/36):** almost all are a systematic CALIBRATION OFFSET —
   Opus grades misdirection `none` where Sonnet grades `MODERATE` (both pass the predicates).
   Wiring "any disagreement → abstain" would flag half the book for nothing. (Routing note: the
   offset has real consequences — none→silence vs MODERATE→briefing — which is exactly why the
   [5m/7] gate keys on JUDGE_MODEL; and this run DEMONSTRATED the gate FAILING on a model swap.)
2. **HIGH-boundary divergence IS informative:** only 2/36 diverged across the HIGH line — and one
   was the run's only real failure (S18). Caught 1/1 failures, 1 false alarm (S19, where Sonnet's
   tier wandered on a correctly-graded mna). ~6% flag rate.
3. **Single-model confidence is NOT a substitute:** agreeing 0.79 vs divergent 0.78 — no
   separation. (The one failure carried 0.62 — suggestive, single-point.)
4. Sonnet-5 at 35/36 is a strong fallback grade — relevant to the fail-open story, not to
   authority.

## The wire-or-drop rec (0018's ensemble lane)

**DROP for now; record the design.** The ensemble only protects against a WEAKER primary — the
live judge is Opus and clean on this corpus, so wiring costs $/latency per HIGH candidate to
catch failures the primary isn't making. **Revisit trigger:** if JUDGE_MODEL ever moves
down-tier (cost pressure / model retirement), the ensemble arm ships WITH it, wired as
**HIGH-boundary-only divergence → flag/abstain** (never generic divergence — finding 1). This
paragraph is the 0018 §ensemble design note; no build now, no new task (0018 is the P1 pillar's
signed ADR; this evidence folds into its build gate).
