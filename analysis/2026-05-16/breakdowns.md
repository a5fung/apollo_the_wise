# EP Selectivity Phase 1 — Per-Dimension Breakdowns

_Generated from `ep_cohort_alerts_60d.csv` (165 alerts) and `ep_cohort_skipped_60d.csv`._

## Outcome definitions

- ENTERED rows: outcome = sign of `total_pnl`; return = `pnl / (entry_price × entry_shares)`
- UNENTERED rows: outcome = `ret_5d > 5%` (gap-day open → +5 close)
- Fallback: `mi_ep_scan_outcomes.fwd_5d_pct` (baseline_close-relative)
- Pending = alert too recent for 5d forward

## §A — Existing entry filters (alert-side dimensions)

### A1 — Gap size

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| 15-25% | 43 | 51.2% | +7.1% | +4.5% | 28 |
| 10-15% | 41 | 43.9% | +2.7% | +3.7% | 11 |
| 25%+ | 24 | 41.7% | +5.3% | +2.5% | 8 |
| 8-10% | 8 | 0.0% | -2.4% | -1.4% | 2 |

### A2 — Pre-market RVOL@T

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| (no pm_rvol) | 82 | 39.0% | +3.1% | +1.4% | 22 |
| 10x+ | 18 | 66.7% | +10.7% | +10.7% | 14 |
| 5-10x | 11 | 27.3% | +4.4% | -1.4% | 8 |
| 2-5x | 5 | 60.0% | +5.1% | +5.2% | 4 |

### A15 — Alert time (ET, approx)

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| (no detected_at) | 68 | 33.8% | +0.3% | +0.1% | 20 |
| pre-market | 30 | 50.0% | +7.0% | +3.2% | 25 |
| 9:45-9:59 | 18 | 66.7% | +16.3% | +9.1% | 4 |


## §B — Existing scoring

### B10 — Score tier

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| HIGH | 73 | 52.1% | +5.4% | +5.0% | 44 |
| MODERATE | 43 | 27.9% | +3.0% | -1.6% | 5 |

### B10 — EP score band

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| HIGH-high (80+) | 62 | 53.2% | +5.2% | +4.9% | 36 |
| MOD-high (50-59) | 38 | 23.7% | -0.5% | -1.8% | 9 |
| HIGH-low (60-69) | 10 | 40.0% | +16.3% | +2.7% | 3 |
| HIGH-mid (70-79) | 6 | 66.7% | +9.3% | +10.4% | 1 |

### B2 — Catalyst quality grade

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| strong | 80 | 51.2% | +7.2% | +4.9% | 45 |
| routine | 18 | 16.7% | +1.7% | -3.4% | 2 |
| unknown | 11 | 27.3% | -10.5% | -7.2% | 0 |
| game_changer | 7 | 42.9% | +4.8% | +2.1% | 2 |


## §C — Entry mechanics

### C2 — Entry attempt (1 vs 2)

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| attempt 1 | 52 | 63.5% | +10.1% | +8.1% | 42 |
| attempt 2 | 6 | 0.0% | -6.0% | -4.7% | 0 |

### C1 — 5-min ORB shadow paired status

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| (no shadow row) | 82 | 36.6% | +2.5% | +1.9% | 28 |
| 5m: no_entry | 16 | 56.2% | +10.6% | +5.2% | 12 |
| 5m: gate_blocked | 14 | 71.4% | +9.9% | +8.0% | 2 |
| 5m: open | 3 | 33.3% | +6.3% | -1.4% | 6 |
| 5m: closed | 1 | 0.0% | -5.1% | -5.1% | 1 |


## §E — Setup context

### E1 — Theme membership

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| uncovered | 101 | 39.6% | +3.7% | +2.2% | 44 |
| in-theme | 15 | 66.7% | +10.3% | +11.2% | 5 |

### E1 — Theme stage

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| (uncovered) | 101 | 39.6% | +3.7% | +2.2% | 44 |
| Accelerating | 6 | 66.7% | +8.9% | +12.1% | 1 |
| Mainstream | 6 | 50.0% | +6.2% | +1.4% | 0 |
| Fading | 2 | 100.0% | +21.8% | +21.8% | 3 |
| Nascent | 1 | 100.0% | +20.0% | +20.0% | 1 |

### E3 — Continuation flag stage

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| (no flag) | 86 | 40.7% | +3.6% | +2.9% | 28 |
| unqualified | 28 | 53.6% | +7.7% | +4.9% | 18 |
| WATCH | 2 | 0.0% | -0.5% | -0.5% | 1 |


## Cohort partition: traded vs alerted-only

### Traded vs alerted-only

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| alerted-only | 58 | 29.3% | +0.6% | -2.2% | 7 |
| traded | 58 | 56.9% | +8.4% | +5.2% | 42 |


## §E5 — Missed-EP outcomes (filter-rejected forward returns)

### Skipped — by category (which filters shed?)

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| outside_top20 | 477 | 40.5% | +3.9% | +1.6% | 49 |
| session_rvol_low | 174 | 47.7% | +6.8% | +3.9% | 9 |
| pm_rvol_low | 87 | 28.7% | +3.0% | -0.7% | 42 |
| extension_gate | 49 | 24.5% | -6.4% | -15.2% | 4 |
| score_below_50 | 47 | 42.6% | +4.4% | +3.4% | 14 |
| mcap_low | 40 | 40.0% | +3.1% | -0.0% | 6 |
| adv_low | 30 | 26.7% | +0.0% | -1.6% | 12 |
| catalyst_downgrade | 22 | 22.7% | +1.7% | -2.6% | 9 |
| ma_filter | 17 | 35.3% | +5.0% | +1.8% | 7 |
| cooldown | 15 | 40.0% | -0.5% | -3.2% | 14 |
| atr_high | 6 | 0.0% | -26.2% | -18.9% | 9 |
| duplicate_scan | 5 | 60.0% | +2.4% | +8.0% | 3 |

### Skipped — by skip_reason top-level

| Bucket | N | Win rate | Avg ret | Median ret | Pending |
|---|---:|---:|---:|---:|---:|
| outside_top20 | 477 | 40.5% | +3.9% | +1.6% | 49 |
| rel_vol_low | 168 | 48.2% | +7.1% | +4.1% | 0 |
| pm_shares_floor | 85 | 29.4% | +3.2% | -0.7% | 40 |
| extension_gate | 49 | 24.5% | -6.4% | -15.2% | 4 |
| score_below_50 | 47 | 42.6% | +4.4% | +3.4% | 14 |
| mcap_low | 31 | 41.9% | +4.5% | +0.7% | 6 |
| adv_low | 30 | 26.7% | +0.0% | -1.6% | 12 |
| routine_catalyst | 22 | 22.7% | +1.7% | -2.6% | 9 |
| ma_filter | 17 | 35.3% | +5.0% | +1.8% | 7 |
| cooldown | 15 | 40.0% | -0.5% | -3.2% | 14 |
| quality_filter | 9 | 33.3% | -1.9% | -1.0% | 0 |
| atr_high | 6 | 0.0% | -26.2% | -18.9% | 9 |
| other:filter:session_rvol_too_low: s | 6 | 33.3% | -3.9% | -4.5% | 9 |
| duplicate_scan | 5 | 60.0% | +2.4% | +8.0% | 3 |
| other:filter:pm_rvol_too_low: pm_rvo | 2 | 0.0% | -6.2% | -6.2% | 2 |
