# Breakout v1 — "rising averages" gate (DEFINITION, fixed before any outcome) — 2026-11-02

Written BEFORE any replay outcome was computed. Defines and tests; ships nothing (a list rule is his call).

## Why this one
- His MTW read (11-02): "choppy around the 10/20ma and not really making higher lows". His CODX/PENN charts (11-02): both
  "surf the 10/20" and make higher lows.
- Measured in each stock's own daily range, MTW is NOT choppier than CODX-1 / PENN-2 and its lows hold from the base
  bottom like theirs (`scripts/probes/_his_charts_1102/three_way.out`). The one shape reading that separates them is the
  SLOPE of his averages in PERCENT — what his chart shows: the 21-day EMA rose 2.7% across MTW's base vs 8.3% PENN, 26.1% CODX.
- Size check already run (`prior_move_1102/prior_move_check.txt`): the prior-move bands give no consistent edge; this is
  the last free shape candidate before the fork goes to him.

## G4 — RISING AVERAGES (`rising_avg`)
- EMA21 = the 21-day exponential average of the close (his chart's EMA(21)), seeded at the ticker's first bar, bars <= D only.
- P = v1's pole top (unchanged, `cb._pole_top` exactly as v1). D = the watch night.
- rise = EMA21(D) / EMA21(P) - 1. **Pass if rise >= 5%.**
- The constant 5% is placed BETWEEN the three anchors (MTW 2.7% NO; PENN 8.3%, CODX 26.1% YES) — it is FITTED to them,
  disclosed. So (a) is not evidence; (b) and (c) are the test. Plateau reported at 3 / 4 / 5 / 6 / 7%: a pass that holds
  only at 5% is a single-point peak and FAILS (ADR 0023).
- Tested as an ADDITION on top of the 4.26% daily-range floor (live 11-02), like shape_gates_1102.

## The bar (the same as shape_gates_1102/DEFINITIONS.md, numbers fixed there)
- (a) MTW 10-30 fails G4.
- (b) >= 10 of the 12 of Qullamaggie's 24 graded setups v1 catches still pass, each at its catching watch night.
- (c1) 5-slot paper book at 2c, mean R: >= -0.139 (2017-21) AND >= -0.340 (2022-24) — the floor-only baseline.
- (c2) Removed trades (filled, decisive, 2c, no slot limit, floor-kept, both eras pooled) average BELOW the kept ones.
- (c3) >= 100 trades per era in the kept 5-slot book.
- NEW, part of the bar this time (it is what sank G1): (c4) random thinning — the same share removed at random (200 draws,
  seed 1102) beats the gate's 5-slot mean in < 25% of draws in BOTH eras.
- Verdict: passes (a)-(c4) at 5% AND at least one neighbour (4% or 6%) passes (b)-(c4) -> it goes to him as a candidate
  list rule. Anything else -> no shape rule; the fork goes to him as is.
