# W2 Entry Study #1 — OR-window + skip-wide-open (2026-06-12)

**Cohort:** the #268 Phase B judged candidates (2025-06-09 → 2026-05-04,
1,307 graded+judged; see `selection_replay_268_phaseB.md`). Same selection,
same exit model (ORB stop → day-1-low hard stop → 10/20MA trail + day 3–5
partial) — ONLY the entry geometry varies. Harness: `selection_replay_268.py
--simulate --or-window N --wide-open-atr X` (knobs added `17c1883`; defaults
reproduce live behavior bit-for-bit).

**The W2 thesis being tested** (from Phase A): both floor and judge selection
carry positive paper-able signal, but the current 1-min-ORB bracket leaks
expectancy — entry geometry, not selection, is the #1 lever.

## Results (judge-HIGH system arm = the live selection authority)

| Geometry | n | exp/trade | win% | sum R |
|---|---|---|---|---|
| **Baseline: 1-min ORB (live today)** | 399 | +0.95R | 30% | +378.2R |
| 5-min OR | 300 | +0.15R | 37% | +44.8R |
| **1-min + skip-wide-open 0.275×ATR14** | 212 | **+1.42R** | 28% | +300.1R |
| 5-min OR + skip 0.275 | 139 | +0.30R | 37% | +41.8R |

Floor-HIGH arms show the same ordering (baseline +0.90R · orw5 +0.43R ·
skip +1.36R · combined +0.70R).

## Findings

1. **Skip-wide-open is the real lever — Gemini-amendment hypothesis CONFIRMED.**
   Removing entries whose opening 1-min candle spans > 0.275 × ATR14 cuts
   trade count ~47% but lifts per-trade expectancy **+0.95R → +1.42R (+49%)**
   while retaining ~80% of total R. The removed cohort earned only ~+0.42R/trade
   — wide opening candles mathematically cap R-multiples (stop distance ≈ the
   OR range; a 0.3-ATR range means winners must travel multiples of daily
   volatility to pay). Under the live 5-slot position cap, per-trade
   expectancy is the binding metric: slots freed from structurally-broken
   brackets are pure gain.
2. **5-min OR is harmful under the current exit model.** Win rate rises
   (30%→37% — fewer noise stop-outs) but expectancy collapses to +0.15R: the
   wider range simultaneously raises the entry and deepens the stop, so the
   surviving winners earn far fewer R. The combination variant confirms the
   damage dominates even with the skip filter. **Dead — do not revisit without
   a different stop model** (e.g. 5-min OR entry + tighter non-OR stop is a
   DIFFERENT study, Monday's stop-geometry slot).
3. **Judge-vs-floor interaction note:** under 5-min geometry the judge arm
   does WORSE than the floor arm (+0.15R vs +0.43R) — the judge's promote
   cohort (+1.26R on 1-min) gets crushed by wide geometry (+0.20R). The
   judge's edge is partly entry-geometry-dependent. Watch this in any future
   geometry change.
4. **Demote-side watch-metric (standing):** judge-demoted floor-HIGHs remain
   positive in every variant (+1.38R to +1.65R avoided) — consistent with the
   Phase B baseline finding that demotes are NOT reliably saves over 12 months.

## Threshold robustness sweep (0.20 / 0.25 / 0.30 / 0.35 × ATR14)

Decision rule going in: the lift must be material across the band, not a
spike at 0.275, for any threshold inside the band to be shippable. **Result:
ROBUST — the lift is a plateau across the whole band** (judge-HIGH arm):

| K (×ATR14) | n | exp/trade | win% | sum R |
|---|---|---|---|---|
| (baseline, no skip) | 399 | +0.95R | 30% | +378.2R |
| 0.20 | 196 | +1.52R | 29% | +298.9R |
| 0.25 | 203 | +1.47R | 29% | +297.9R |
| 0.275 | 212 | +1.42R | 28% | +300.1R |
| **0.30** | **217** | **+1.46R** | 29% | **+315.9R** |
| 0.35 | 227 | +1.39R | 29% | +315.5R |

Expectancy is +1.39R to +1.52R at every K tested (vs +0.95R baseline), gently
decreasing as the filter loosens — exactly the shape a real structural effect
produces (each marginal admitted wide-open trade dilutes). No cliff, no
overfit point. Floor-HIGH arm shows the same plateau (+1.34 to +1.45R).

**Recommended K = 0.30**: highest total R retained (+315.9R, 84% of baseline
sum) at near-peak expectancy (+1.46R), and the loosest setting inside the
plateau — fewest skipped trades for the same structural protection, leaving
margin before the effect decays (0.35 is the first visible dilution step).

## Caveats

- Same recall/fidelity caveats as Phase B (scan ≈47% of live alerts; IEX-bar
  simulation; single pass, no error bars).
- The simulator holds EOD (no 10:00 unfilled-cancel asymmetry) and models
  entry at OR-high + slippage; live stop-limit trigger/fill differences
  (LYG-class paper-IEX artifacts) are not modeled — but a SKIP filter is
  fill-model-insensitive (it removes trades; it doesn't re-price them).
- ATR14 here is the backtester's `compute_atr_14`; the live path would use
  the same ATR already computed for `validate_orb_entry` — one shared input,
  no new data dependency.

## What would ship (pending sweep + operator sign-off — NOT shipped)

One change, behind a per-strategy flag, full CHANGE_PROCESS entry in
`docs/setups/magna53_ep.md` (+ safeguards-adjacent note): at ORB submission,
skip (or route to the future first-pullback technique, #270-era) when
`(orb_high − orb_low) > 0.30 × ATR14`. Evidence: sweep-robust plateau,
n=217 kept / 182 removed over 12 months (≫ N≥30 gate), +0.95R → +1.46R.
Runway slot: proposal by Fri 6/19 (evidence complete 6/12 — can accelerate);
9M Day 2 unaffected (separate stop source, separate SSoT) unless separately
evidenced. New skip reason would join the bounded vocabulary
(`filter:wide_open_orb` class) and be visible in skip aggregation + the
would-have-filtered telemetry BEFORE any live flip (shadow-count first).
