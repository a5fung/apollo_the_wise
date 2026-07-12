# #146 C1 — drop the COILED prerequisite for TRIGGERED: backtest (Lane-1 pre-build, 2026-07-11)

**Change under test (ADR 0026 D2):** allow `TIGHTENING → TRIGGERED` directly —
`TRIGGERED = close > base_high_close AND vol ≥ 1.5×`, dropping the `coiled_today or
was_coiled_recent` conjunct (COILED stays a *quality* stage). Probe:
`scripts/probes/_146_triggered_gate_backtest.py`. Read-only.

## ⚠ The direct-trigger cohort is NOT faithfully measurable with this harness — the incumbent IS

The probe attempts a drop-COILED replay via the detector's own `compute_flag_metrics(...,
recent_stages=['COILED']*5)`. **A built-in validation exposed that the replay is not faithful:**
replaying the 21 KNOWN live TRIGGERED events through the same path re-flags only **4/21** as
TRIGGERED (base_high matches 4/4 once the live pivot is threaded in — so the base is right, but the
trigger condition still doesn't reproduce; the residual gap is the live vol-ratio window /
`base_high_close` semantics, not the base). **A harness that reproduces only 19% of known live
triggers cannot be trusted to enumerate the *would-be* triggers** — so Cohort B below is a weak
lean, NOT rule-grade evidence.

## The table

| cohort | N settled | median R | mean R | total R | win% | avg-winner | fwd-max med (upper) |
|---|---|---|---|---|---|---|---|
| **A — incumbent (COILED-triggered), from the LIVE table (faithful)** | 19 | −1.00R | **+0.78R** | **+14.9R** | 26% | **+5.62R** | +1.35R |
| B — direct-trigger via replay (**harness only 19% faithful — NOT rule-grade**) | 14 | −1.00R | −0.25R | −3.5R | 29% | +1.63R | +3.33R |

Settlement (both): entry=base_high, stop=breakout-day low, fixed stop → 10-trading-day horizon,
break-day-EXCLUSIVE (no entry-day lookahead).

## The read → HOLD / NO-GO on the flip (two independent reasons)

1. **The incumbent COILED-triggered gate is POSITIVE — the design's premise was wrong.** ADR 0026
   argued from "TRIGGERED N=5 −2.66% / 0%WR" (a raw forward-% snapshot) that the gate was already
   negative, so loosening "can't hurt." Settled properly (R, N=19, from the live table): the
   incumbent is **+0.78R mean, +14.9R total, avg-winner +5.62R** — a tail-carried-POSITIVE gate
   (median −1.00R because the breakout-day-low stop makes stopout the modal outcome; the few big
   winners pay for all the −1R stops). The stopout-median is structural and non-discriminating for
   BOTH cohorts — **the tail is the statistic that matters, and the incumbent's tail works.**
   Loosening a working, tail-positive gate needs a strong positive case, which does not exist.
2. **No faithful positive evidence for the change exists.** The only direct-trigger measure we have
   (Cohort B) rides a 19%-faithful harness and leans slightly negative (−0.25R, smaller winners
   +1.63R vs +5.62R). It is not trustworthy enough to GO on — and it certainly is not a case to
   loosen the gate.

## Recommendation for the sitting

- **HOLD / NO-GO on dropping the COILED prerequisite.** The incumbent gate is tail-positive
  (contradicting the loosening premise), and there is no faithful evidence the direct-trigger
  cohort would add R. Keep COILED as a hard prerequisite for now.
- **Remaining pre-flip work (files, don't ship):** a *faithful* direct-trigger harness — reproduce
  the live trigger computation (the exact `recent_avg_vol` window + `base_high_close` semantics)
  until it re-flags ≥~19/21 known triggers, THEN measure the drop-COILED cohort's realized R. Only
  then is F1 a real gate. (This is the "faithful-replay harness needed" outcome, not a methodology
  ambiguity — the change is well-defined; the *measurement* isn't built.)

*Feeds #146 / ADR 0026 F1(D2). Honest limitation surfaced by the built-in replay-validation — the
incumbent result (tail-positive, premise-reversing) is the durable finding; the direct-trigger
verdict awaits a faithful harness.*
