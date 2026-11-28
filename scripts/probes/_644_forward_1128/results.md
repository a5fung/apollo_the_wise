# #644 forward test, read 2026-11-28 (pre-registered bar unchanged)

Bar: high half (cohort resilience > 0.005, frozen) holds >= 60%, gap >= 10 points, n >= 60 per side.
Real `db.get_down_day_resilience` (lookback 20, as_of = entrant's as_of_date), cohort = median of members.
Population: entrants with week_start >= 2026-09-14, 145 entrants, 145 scored (0 without coverage), 128 scorable.

## Verdict: NOT READABLE YET (high side n=55 < 60). Trend so far is below the bar.
| side | n | holds next week | rate |
|---|---|---|---|
| high (> 0.005) | 55 | 32 | 58.2% |
| low (<= 0.005) | 73 | 39 | 53.4% |
| gap | | | +4.8 points |
All forward: 71/128 = 55.5%. Forward median resilience 0.0043 (frozen cutoff 0.005 kept, not re-chosen).
On current numbers it would FAIL (gap under 10 points, high side under 60%). Not final until n >= 60 per side.

## Engine eras (beside the bar; same cutoff; small n, descriptive only)
| era (week_start) | high n | high holds | low n | low holds | gap |
|---|---|---|---|---|---|
| before 10-05 (09-14..09-28) | 10 | 4 = 40.0% | 26 | 18 = 69.2% | -29.2 |
| 10-05..10-12 | 6 | 5 = 83.3% | 21 | 12 = 57.1% | +26.2 |
| after 10-12 (10-19..11-23) | 39 | 23 = 59.0% | 26 | 9 = 34.6% | +24.4 |

- High-side share by era: 28% / 22% / 60% of scorable. Smaller themes (the high-resilience ones) were removed by the 10-05 / 10-12 engine changes, yet the high side is mostly post-10-12 now.
- Eras disagree in sign on tiny n; the pooled gap (+4.8) is what the bar reads.

## Accrual and projection
- Scorable rate ~13 per week (10 weeks of 9-18); high side ~43% of them, ~5-6 per week.
- Week 11-23's 17 entrants (4 high, 13 low) become scorable once the 11-30 week is on file: high 59, low 86.
- High side reaches 60 with week 11-30's entrants, scorable once week 12-07 is on file: earliest read about 2026-12-11 (expect 1-2 weeks later if few high entrants arrive).
- Files: entrants_fwd.json, scored_fwd.json, summary.json, run_forward.py in this folder.
