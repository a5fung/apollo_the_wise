# #644 — correction test of down-day resilience (PRE-REGISTRATION, 2026-11-28)

Written BEFORE any theme return in the correction or bounce was computed or looked at. His ask
(11-28): *"Given market in correction, isn't it the best time to test this?"* The frozen #644 test
(new board entrants, n ≥ 60 a side, `results.md` in `scripts/probes/_644_forward_1128/`) is
UNCHANGED and keeps its own read (~12-11). This is a second, separate test.

## The question
Do themes whose stocks held up best on the market's down days during this correction do better
afterwards than themes that held up worst? (His north star: *"holding up better in market down
days."*)

## Dates (from SPY closes only — no theme data read)
- Correction leg: SPY high close 2026-10-06 ($779.09) → low close 2026-11-20 ($689.81), −11.5%.
- Measuring window: sessions 2026-10-07 .. 2026-11-20 inclusive.
- Bounce window (outcome A): close 2026-11-20 → close 2026-11-27.
- Forward window (outcome B): close 2026-11-27 → close 2026-12-11.

## Population
Every theme (canonical id) in portfolio-app2 `theme_data.get_canonical_weekly_grid` for week
2026-11-16 (the week containing 11-20) with ≥ 3 tickers that have closes on every needed date —
ALL themes in the grid, not only the top 30. Basket = that week's tickers. Equal weight.

## Score (the real function, not a copy)
`db.get_down_day_resilience(as_of=2026-11-20, tickers=basket, lookback=<sessions in the measuring
window>)`, theme score = MEDIAN of its tickers' values (the frozen #644 cohort definition).

## Split
Top third vs bottom third of themes by score (ties broken by canonical id). Middle third reported,
not judged.

## Outcomes
- A (readable today): equal-weight basket return over the bounce window, minus SPY's.
- B (readable 2026-12-11): the same over the forward window.
- Also reported, not judged: share of each third on the top-30 board in weeks 11-23 and 11-30.

## Pass / fail — fixed now
- PASS on an outcome: the top third's MEDIAN excess return beats the bottom third's by ≥ 1.0
  percentage point, AND a 10,000-shuffle permutation of the labels gives p < 0.05 (one-sided).
- FAIL: the gap is < 0, or p ≥ 0.20. Anything between = inconclusive.
- Verdict: A is the early read; B confirms. Resilience is called predictive only if B passes and A is
  not a FAIL. A alone never decides.

## What this does not answer
- Themes share tickers, so they are not independent — the permutation p is optimistic. Also report
  the result after dropping themes that share > 50% of tickers with a higher-ranked theme.
- A sharp bounce often favours high-beta names, which tend to score LOW on down-day resilience — so
  outcome A can fail for a reason that says nothing about leadership. That is why B is the
  deciding read.
- No trading, sizing or theme-engine change follows from this test; it is evidence for #644 only.
