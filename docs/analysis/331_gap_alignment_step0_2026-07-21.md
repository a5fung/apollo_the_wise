# #331 STEP-0 — gap-vs-structure alignment axis: calibration result (2026-07-21)

Probe: `scripts/probes/_331_gap_alignment_step0.py` (read-only; ADR 0033 STEP-0). Cohort =
`mi_theme_axis_shadow` (N=469, 406 tickers) ⋈ `mi_ep_scan_outcomes`. Landing = alert-day
`open_price`; levels as-of strictly-prior. RELAXED coverage 99% (the powered read); STRICT
(trailing-252) only 5% coverage under retained history → uninformative, as anticipated.

## Verdict: the axis does NOT earn its keep — do not ship as designed

ADR 0033 §93-95: *"the axis earns its keep only if alignment separates outcomes WITHIN magnitude
bands — otherwise it is magnitude in a costume and must not ship."* It does not, and it may be
**inverted**.

### RELAXED — all magnitudes (all cells powered, settled N≥30)

| alignment | n | settled | avg fwd-5d | med | win≥+5% |
|---|---|---|---|---|---|
| punch_through (the proposed +1) | 133 | 91 | **10.1%** | 7.1% | **63%** |
| clears_base_near_miss (0) | 176 | 113 | 8.8% | 5.0% | 50% |
| fades_into_congestion (0, expected WORST) | 157 | 81 | **11.9%** | **8.3%** | 60% |

`fades_into_congestion` — the class the ADR expected to be worst — has the **best avg + median**.
`punch_through` wins only on win-rate, not on average, and does not beat `fades`.

### Magnitude-independence check (does punch_through separate WITHIN a band?)

- **gap <10%** (underpowered): punch_through is the **WORST** (avg 2.6% / win 17%) vs fades 11.7% / 59%. Inverted.
- **gap 10–15%**: powered cells = clears (7.7% / 53%, N=49) vs fades (11.9% / 62%, N=40) → **fades > clears**; punch underpowered (N=22).
- **gap ≥15%**: powered = punch (10.2% / **65%**, N=63) vs clears (9.9% / 49%, N=55) → punch ≈ clears on avg, better win-rate only; fades underpowered (N=19).

So the sole pro-`punch_through` signal is a better win-rate vs `clears_base` in the ≥15% band —
not a clean average advantage, and it never beats `fades`. Across bands there is **no consistent,
magnitude-independent separation in the boosted (+1) direction.**

## Recommendation (operator's call — this is STEP-0's yield gate, working)

1. **DROP the axis as designed.** The `+1 punch_through` credit is contradicted; shipping it would
   nudge grades toward *worse*-outcome names in the small-gap band and add nothing in the mid band.
2. **Flag the surprise for a possible v2 investigation:** `fades_into_congestion` (gap lands back
   inside its own base) is the *strongest* class on avg/median — plausibly a real "gap into support
   → room to run" effect vs "gap to blue sky → climactic/extended → fade." That is a *different*,
   counterintuitive axis and a CHANGE_PROCESS question with its own mechanism + N — never a silent
   flip of the sign.
3. **Or DEFER** the ≥15%-band punch_through win-rate signal for more N — but the current read does
   not justify shipping.

No shadow build is carded (ADR 0033 rollout step 3 is gated on this table passing — it did not).
The #331 axis should not proceed to shadow without a redesign or an operator decision to drop.
