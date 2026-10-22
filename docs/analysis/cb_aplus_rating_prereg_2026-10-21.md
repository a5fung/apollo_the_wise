# #705 — the A+ RATING for breakouts: rank them and take only the best few a week — pre-registration (2026-10-21, BEFORE any rating outcome)

**Why.** The operator (2026-10-21): *"for breakouts we'll also need ranking similar to what we try to do with EPs, but breakouts are
going to be more common and we need a rating system to select the best ones ... We need to focus on the A+ setups per Qullamaggie, he
definitely doesn't trade all however many thousands breakouts per year"*, and *"we should also have some secondary indicators to
test, like group themes, etc."*. Every breakout our rules find (C0) runs ~55–65 a week; the strict FILTER (C1) keeps ~30 a year, shows
no edge, and dropped 342 of the 352 trades on the 39 known 2020–21 multibaggers. This read asks whether a RATING that picks the top few
a week from all breakouts does better than taking them all.

## Method / population

- **Population (pinned, no new walk):** the spec-key first breaks of the trendline level (`tl`) filled at ORH5 under the low-of-day
  stop — the P5 fills — with the CARRIED exit `pp` (his ruling: the day-3 third only in profit, stop to cost after it), outcomes as
  already walked in `trades_{discovery,pre,holdout}_exitpb.tsv.gz` (arm `pp`, entry `orh5`). Periods: 2017-03..2021-12 (n = 13,368
  fills) and 2022-03..2024-12 (n = 8,984) are read ONCE each and BOTH decide (the score is not fitted on either); 2025-01..2026-10
  (n = 7,570) is descriptive only (read once already).
- **The score — FIXED, pre-named, unfitted** (advisor 10-21: both eras have been read, so no weight may be chosen on them). Each
  feature is turned into a percentile rank WITHIN THE FILL WEEK across that week's C0 fills, oriented so higher = better, and the
  score is the plain mean of the oriented ranks (a missing feature is left out of that trade's mean; a trade with fewer than 5 of
  the 7 is unrated, counted). The seven core features, each known BEFORE the 5-minute entry fills (no breakout-day close, high or
  full-day volume is used — `breakout_vol_x`, `close_E`, `high_E`, `vol_E` are look-ahead and excluded):
  1. tightness — `tightening_ratio` (lower = better; his "tightness before breakout");
  2. the last 5 sessions' range in ADR units — `range5_adr` (lower = better);
  3. base depth — `base_depth` (shallower = better);
  4. relative strength — `rs_best`, the best of the 1/3/6-month percentiles (higher = better; his 1/3/6-month leaders);
  5. the run-up into the base — `prior_move` (higher = better);
  6. volatility contraction — `atr14_slope` (more negative = better);
  7. opening drive — the first 5 minutes' volume ÷ (ADV20 ÷ 78) on the breakout day, from the stored minutes (higher = better; the
     only breakout-day input, and it is complete at the 5-minute fill).
- **A+ = the top N rated fills of each fill week; N = 3 decides** (his "best few"), N = 1 and N = 5 beside. Ties broken by `rs_best`.
- **Secondary indicators (beside, never deciding), each ADDED to the core score one at a time with the same equal weight:**
  industry-group strength `grp_pct` (every era); the QQQ 10/20 phase at the watch night (`phase_qqq_10_20`); the stair-step number
  (the count of the ticker's prior spec-key first breaks in the 120 sessions before E: lower = earlier base, the direction NOT
  assumed — reported both ways); themes — the watch name's theme and stage on the night, 2026 only (history starts 2026-03-19),
  descriptive.

## Bars (per period; precedence: n first)

- **PASS (per era) — all of:** the A+ group (N = 3) has n ≥ 30 mature trades; its month-block 95% interval (blocks = fill month, 2,000
  resamples, seed 702) has lower end > 0; ADR P&L > 0; it beats ALL C0 fills of the same period on mean R AND on the ≥ 5R share; and its
  ≥ 10R trades come from ≥ 3 tickers AND ≥ 3 months counting only stops ≥ 0.25 ADR20 wide. **FAIL:** n ≥ 30 AND (upper end < 0 OR not
  beating C0 on mean R). Else **CAN'T TELL**.
- **The paired rating bar (per era):** A+ minus the REST of the same weeks (all C0 fills not in the top 3), mean R difference with the
  same month-block interval — lower end > 0 → **the rating separates**; upper end < 0 → **it picks worse**; else can't tell.
- Reported per era × N × score (core, + each secondary): n, win, average win / loss, mean R and interval, ≥ 5R / ≥ 10R / ≥ 20R per 100,
  total R, ADR P&L, the share of the 39 known 2020–21 multibaggers' trades that land in A+ (descriptive, hindsight), the share of weeks
  with fewer than N rated fills.
- **Expectations, fixed now:** the A+ group's ≥ 10R per 100 above C0's (0.9 in 2022–24, 1.2 in 2017–21); a missed expectation is
  reported first and changes no rule. **WOULD-FAIL-IF:** a feature computed with information after the 5-minute fill; a percentile
  rank taken across weeks instead of within the fill week; the outcome columns differing from the pinned `exitpb` rows for the same
  trades; more than N trades in a week's A+ group.

## Consequence fixed now

- **PASS in both eras:** the forward shadow records the A+ flag (rank, score, features) on every breakout entry; the rating is the
  candidate for a paper proposal TO HIM after the forward read (his sign-off; THE LINE). **PASS in one era, or paired "separates" in
  both:** a LEAD — the shadow records the flag; nothing else. **FAIL / CAN'T TELL in both:** this fixed score does not select; the
  secondary rows are read for which ingredient carried any separation, and the next registration names it.
- Independent re-derivation (pandas, no runner code) of the A+ group's n / mean R / interval and the paired difference per era —
  VERDICT MATCH before the result is written.

## What this does not answer

- His discretion (how he reads a chart); weights other than equal; the entry and the stop (held at ORH5 + low of day); survivorship in
  2017–21 (Alpaca's symbol list).

<!-- FREEZE -->
## Freeze record

Pins (sha256) printed by the build's `--print-pins` and pasted here in the commit that precedes the run: the three `trades_*_exitpb`
tables, the candidates files, both daily exports, both minute trees, the runner and the scaffold module, the doc body. The RESULT is
appended below this record.
