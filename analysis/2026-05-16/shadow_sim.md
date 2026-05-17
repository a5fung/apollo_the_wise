# EP Selectivity — Shadow Simulation

_Retrospective application of ADR §8 recommendations R1-R5 to the 60d historic cohort. Estimates the projected cohort outcome IF these filters had been live during the 60d window._

## Methodology

- Baseline: every `mi_ep_alerts` row in 60d, joined to forward returns (trade pnl > missed_outcomes > scan_outcomes priority).
- Win definition: `total_pnl > 0` (traded) or `ret_5d > +5%` (gap-day open → +5d close).
- Each rule cumulatively filters or admits rows; final is composite of all five.
- R5 *adds* historically-rejected candidates back to the cohort, using their settled `ret_5d` from `mi_ep_missed_outcomes`.

## Per-filter breakdown

| Stage | N alerts | N eval | Win rate | Avg ret | Median ret |
|---|---:|---:|---:|---:|---:|
| Baseline — all 165 alerts | 165 | 116 | 43.1% | +4.5% | +2.9% |
| Baseline — TRADED only (closed paper) | 11 | 11 | 18.2% | -4.0% | -3.2% |
| R1 — HIGH only (MODERATE dropped) | 117 | 73 | 52.1% | +5.4% | +5.0% |
| R1+R2 — HIGH AND gap≥10% | 116 | 72 | 52.8% | +5.4% | +4.9% |
| R1+R2+R3 — drop re-entries | 110 | 66 | 57.6% | +6.4% | +6.0% |
| R1+R2+R3+R4 — plus in-theme re-admits | 111 | 67 | 58.2% | +6.8% | +6.7% |
| FINAL — R1+R2+R3+R4+R5 composite cohort | 123 | 74 | 52.7% | +6.1% | +4.9% |

## What each rule dropped or added

| Rule | Action | N | Win rate of dropped | Avg ret of dropped | Interpretation |
|---|---|---:|---:|---:|---|
| R1 | dropped MODERATE | 48 | 27.9% | +3.0% | mostly losers |
| R2 | dropped HIGH gap<10% | 1 | — | +5.0% | fine cut |
| R3 | dropped Day-1 re-entry | 6 | — | -6.0% | clean cut |
| R4 | re-admitted in-theme MODERATE | 1 | 100.0% | +30.1% | good admit |
| R5 | admitted session_rvol_low (9:30-9:45) | 12 | — | -0.7% | noise |

## Headline projection

- **Cohort win rate**: 43.1% → **52.7%** (+9.6pp)
- **Cohort avg return**: +4.5% → **+6.1%**
- **Alert volume**: 165 → **123** (-25.5%)

## Caveats (read before believing the numbers)

1. **Retrospective**: applying filters to data they didn't shape. Real Phase 2 shadow telemetry over 30d in production is the actual test.
2. **R3 effect underweighted**: only 6 historic re-entries in cohort; the structural lever is small. Future cohort may differ.
3. **R5 admits unentered candidates**: assumes ORB-high entry + ORB-low stop would have fired cleanly. Real execution slippage (gap fills, fade guards, dead-zone) would reduce R5 win rate vs the raw `ret_5d` proxy.
4. **Sample size**: 165 total alerts is below most feedback's N≥30 ship gate per dimension. Treat each rule's outcome as directional, not definitive.
5. **Outcome mixing**: traded rows use entry-pnl R; unentered use 5d open-to-close. Magnitudes are not perfectly comparable. WR direction is comparable; avg-ret only as rough indicator.
