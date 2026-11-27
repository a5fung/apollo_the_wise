# Kill/scale bands — quarterly review 2026-11-26

Review `kill_scale_bands_quarterly_review` (data_gated_reviews.yaml). Read-only, $0. Regime: bear
phase (Nov 2026) — momentum expected weak; no verdict on the setup from this read.

Evidence: `scripts/probes/_killscale_1126/` (evaluator output from the live container, per-trade query).

## Method and population
Rows: `mi_live_trades` with `status='closed'`, `account_mode='live'`, `pnl_attribution IS NULL` —
the evaluator's own filter (`kill_scale_bands.assemble_band_inputs`), 44 trades, 2026-07-06 → 2026-11-11,
all `magna53`. Verdict from `scripts/evaluate_kill_scale_bands.py` run in the live container; per-trade R =
`total_pnl / risk_dollars_actual` (populated from 08-27 only; earlier rows use the evaluator's derived risk).

## Live evaluator (prod, 2026-11-26)
`n=44 · t20=+0.23R · t40=-0.05R · streak=6 · cum=-6.2R` → **HOLD**. Drawdown tier (separate
breaker) = REDUCE since 2026-11-12 (live dd -7.22%), unrelated to the bands.

## Against the signed thresholds
| Arm | Threshold | Live | Distance |
|---|---|---|---|
| KILL cum R | ≤ -30R | -6.2R | ~24R away |
| KILL trailing-20 | ≤ -1.05R | +0.23R | far |
| REDUCE trailing-20 | ≤ -0.70R | +0.23R | far |
| REDUCE losing streak | ≥ 16 | 6 | 10 more losses |
| SCALE trailing-40 | ≥ +0.50R (n≥40) | -0.05R | not earned |

## Against the calibration envelope (#268b)
| | Envelope | Live |
|---|---|---|
| Expectancy | +0.95R | t40 -0.05R |
| Max drawdown | -24.1R | worst cumulative ≈ -12R (the 08-26 run read -11.9R); -6.2R today |
| Worst streak | 15 | 14 (Jul–Aug, pre-2R); 6 now |

## Era split (the 08-26 run's open item)
- 2R-stop era (MRVL 08-19 → 11-11; R from risk_dollars_actual from 08-27, MRVL ≈ -1R): **20 trades, net ≈ +1.4R (+0.07R/trade)**;
  two big winners (VICR +7.0R, KOD +6.2R) carry it, 13 of 19 are ~-1R stops.
- Pre-2R era (07-06 → 08-19, MRVL excluded): 24 trades, ≈ -7.6R (the 0-for-14 opening run).
- So the bands now read mostly-2R trades; the calibration was simulated on the orb_low stop. Both
  still under-sample the tail (2 winners ≥ +3R in 19).

## Override log
0 `kill_scale_override` rows ever; one transition (live ∅ → HOLD, 06-19). Criterion (c) does not apply.

## Recommendation
**KEEP the bands as signed.** Nothing has come near a threshold; no override pressure; the sample
under the current stop (19) is too small to re-derive bands from. Re-run next quarter (2027-02-26).

## Known measurement notes (unchanged, not touched)
- The evaluator now uses `risk_dollars_actual` (populated since 08-27); it logs a warning on every
  trade whose current `hard_stop` moved after entry (derived risk differs) — noisy, not wrong.
- SCALE arm `equity_above_start` compares to the first snapshot; reads True today.

## What this does not answer
- **Two of the review's four inputs were NOT read:** (b) the P6 replay-regression weekly reports and (d) the demote-side
  forward R of judge-demoted alerts. The keep recommendation rests on (a) the live distribution and (c) the override log only.
- Whether the setup has edge: 44 trades, 2 tail winners, a bear phase — far too thin for that.
- Whether the calibration envelope itself is right under the 2R stop (it was simulated on orb_low);
  re-deriving it needs a replay, not live trades.
- Open positions are not in the band inputs (by design; report-only).
