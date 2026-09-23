# EP detector latency audit (P1.7)

_N=64 HIGH alerts in 60d with `detected_at` populated. Quantifies how many fired AFTER the ORB submission window closed (9:45 ET cutoff) — the CPA 5/14 class._

## Emit-time distribution

| Bucket | N | Share |
|---|---:|---:|
| pre-market | 47 | 73.4% |
| 9:30-9:44 | 0 | 0.0% |
| 9:45-9:59 | 17 | 26.6% |
| 10:00-10:59 | 0 | 0.0% |
| 11:00+ | 0 | 0.0% |

**Late-fire rate** (emit ≥ 9:45 ET, past the ORB submission window): **17 / 64 = 26.6%**

**In-window rate** (9:30-9:44 inclusive — actionable for ORB): **0 / 64 = 0.0%**

**Pre-market rate** (before open — best window): **47 / 64 = 73.4%**

## What filter held the LATE-fire alerts at first scan

First `filter_reason` recorded for each LATE alert (emit ≥ 9:45 ET) — i.e. what was blocking the candidate the moment the system first saw it.

| Category | N |
|---|---:|
| score_below_50 | 4 |
| (no reason) | 4 |
| pm_shares_floor | 3 |
| other | 2 |
| outside_top20 | 2 |
| rel_vol_low | 2 |

## Detected-vs-first-scan latency (minutes)

- N with both timestamps: 64
- median: 0.0 min
- 90th pct: 110.0 min
- max: 170.0 min

### Top 15 longest detection latencies

| Ticker | Alert | 1st scan ET | Detected ET | Latency (min) | 1st filter reason |
|---|---|---|---|---:|---|
| HUT | 2026-05-06 | 07:00:00 | 09:50:00 | 170.0 | score 7 < 50 (catalyst=strong) |
| FROG | 2026-05-08 | 07:00:00 | 09:50:00 | 170.0 | score 43 < 50 (catalyst=strong) |
| PGNY | 2026-05-08 | 07:00:00 | 09:50:00 | 170.0 | score 46 < 50 (catalyst=strong) |
| CALY | 2026-05-08 | 07:20:00 | 09:55:00 | 155.0 | outside top-20 gap cap (gap 8.3%) |
| IART | 2026-05-05 | 07:20:00 | 09:50:00 | 150.0 | pre-mkt volume 101 < 25,000 shares |
| SITM | 2026-05-07 | 07:00:00 | 09:15:00 | 135.0 | pre-mkt volume 3,239 < 25,000 shares |
| STRL | 2026-05-05 | 07:00:00 | 08:50:00 | 110.0 | pre-mkt volume 3,575 < 25,000 shares |
| JMIA | 2026-05-07 | 07:30:00 | 09:15:00 | 105.0 | outside top-20 gap cap (gap 9.2%) |
| SEZL | 2026-05-07 | 07:00:00 | 08:10:00 | 70.0 | pre-mkt volume 10,247 < 25,000 shares |
| FTRE | 2026-05-05 | 08:15:00 | 09:15:00 | 60.0 | pre-mkt volume 1,510 < 25,000 shares |
| VG | 2026-05-12 | 07:00:00 | 07:55:00 | 55.0 | score 48 < 50 (catalyst=strong) |
| VSTS | 2026-05-12 | 08:05:00 | 08:55:00 | 50.0 | pre-mkt volume 2,321 < 25,000 shares |
| VIK | 2026-05-14 | 09:15:00 | 09:55:00 | 40.0 | score 36 < 50 (catalyst=strong) |
| SE | 2026-05-12 | 07:15:00 | 07:55:00 | 40.0 | routine catalyst, gap 8.6% |
| EVER | 2026-05-05 | 07:00:00 | 07:35:00 | 35.0 | pre-mkt volume 15,905 < 25,000 shares |

## CPA 5/14 fixture

- alert_date: 2026-05-14
- score: 67.7, gap: 13.12%, catalyst: strong
- first scan time (ET): 09:31:00
- detected at (ET): 09:55:00
- latency: 24.0 min
- pre-emit scan ticks: 4
- first filter reason: pre-mkt volume 7,058 < 25,000 shares

## Implications

- **Late-fire is a material problem** (26.6% of HIGH alerts fired after 9:45 ET). These alerts CANNOT be acted on under the current 9:31-9:45 ORB submission window. CPA-class. Each late-fire is a missed Class A entry.

- The top first-filter-reasons on late alerts surface WHICH gate the system spends the most time waiting on. If `rel_vol_low` or `pm_shares_floor` dominates, pre-market volume curve building is the bottleneck and a relaxed early-window threshold could pull detections earlier.

- The latency distribution (median + 90th pct) tells us how long the typical alert spends in the scan queue before promoting to HIGH. A long tail (>30 min) suggests catalyst-grader round-trip or snapshot stale.
