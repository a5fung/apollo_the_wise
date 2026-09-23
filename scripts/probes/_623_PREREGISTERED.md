# #623 — full-population, all-bands EP selection study: variables and cells,
# PRE-REGISTERED before any realized-R join

Written and locked 2026-09-04 (PT), BEFORE `_623_join.py` computes any correlation, cell
mean, or lift against `realized_r_0931`. Population, features, bands, and cell definitions
below are fixed first — the overfitting guard the task requires. `_623_join.py` may only
report what is listed here; a variant chosen after seeing R is not evidence.

## Population

Every distinct (ticker, scan_date) row in `mi_ep_scan_log`, `scan_date >= 2026-06-08` (the
start of stored-minute-bar coverage) through the most recent COMPLETE session
(`2026-09-03`; `2026-09-04` is the live session as this is written and is EXCLUDED from
realized-R statistics, reported separately as open/incomplete if it appears at all).
n = 3458 ticker-days total (3458 after de-dup; one extra day-of-run row for 2026-09-04
excluded from R stats per above).

**Per-row selection**: for ticker-days with multiple scan_log ticks (re-scanned through
the morning), the tick nearest 09:31:00 ET in wall-clock distance is used for every
tick-level feature (gap, volume, price, market cap column, filter_reason) — same method
`_622sweep_driver.py` validated. `tick_dist_sec` is carried on every row; staleness
(no tick within 30 min of 09:31) is reported, not hidden, same as #622.

**Tag** (deterministic, since a name can be rejected on one tick and scored on another):
`scored:<best_score_tier>` if ANY tick that ticker-day has `ep_score IS NOT NULL`
(`best_score_tier` = the tier at that tick); else the `filter_reason`/`reject_stage` of
the nearest-09:31 tick. 417 ticker-days are `ever_scored`; the remaining 3041 are tagged
by rejection reason. Both cohorts are in the SAME population and SAME tables below —
this study does not filter to rejects only (#622's scope error, corrected here).

## Market cap — three sources, priority order, each row tagged with which was used

1. `market_cap` column (persisted since 2026-08-31, a real point-in-time FMP/yfinance read
   at scan time) — 23 rows.
2. `filter_reason` parse (`"$XXXM < $500M"`, the exact dollar figure `check_filters` wrote
   that morning) for mcap-rejected rows before 2026-08-31 — 132 rows.
3. **Proxy** for everything else (3267 rows, 94% of the population): current Polygon
   `share_class_shares_outstanding` (fetched once per unique ticker, 1978 tickers,
   `_623_fetch_shares_out.py`) × `prev_close` at the row's own nearest-09:31 tick =
   `proxy_market_cap_at_scan`. Cross-validated against the 150 rows that have BOTH a real
   value and a computable proxy: median absolute error 3.5%, mean 8.3%, 71% within 10%,
   89% within 20% (worst cases — QTTB +76%, BKKT -68% — are share-count changes between
   scan date and now: issuance, buyback, or a merger; not corrected for). **Continuous
   market cap on proxy rows is an approximation; BAND membership is reported as reliable
   except for rows within ~20% of a band boundary, which are flagged.** 36 rows have no
   shares-outstanding data at all (ticker delisted/renamed since) and are excluded from
   any cap-conditioned cell, reported as a coverage gap.

Bands (fixed, from the task): <$200M, $200–500M, $500M–2B, $2–10B, >$10B.

## Volume — two readings, every number in the deliverable labeled which

- **EOD (lookahead, cohort characterization ONLY, never fed to an admission-relevant
  claim)**: `eod_volume_day0` (real full-day volume, `mi_daily_closes`), `eod_vol_pctile_400d`
  (% of the trailing ≤400 daily volumes below it — literally the task's own SQL, run for
  every row), `eod_record_400d` (day-0 volume exceeds the trailing 400-day max). Coverage:
  3261/3458 (94%).
- **Pre-09:31 (admission-relevant, no lookahead)**:
  - `today_volume_0931`: the `today_volume` column at the nearest-09:31 tick when present
    (335 rows, "column" source — gold standard); else `rel_volume × adv` when BOTH are
    present AND the product is nonzero (1190 rows, "derived" source); rows where neither
    holds (1933 rows, 56%) are **missing, not defaulted to zero** — the #622-retry mistake
    this study was explicitly told not to repeat. 136 rows where the derived product came
    out to exactly 0 are treated as missing (suspect rounding artifact, not a real zero),
    consistent with the same discipline.
  - `vol_pct_daily_bars`: `ep_detector._volume_percentile()` (the live function, imported
    unmodified) fed a rolling-20-trading-day mean-volume history from `mi_daily_closes`
    strictly before scan_date — #622's already-validated method (CHPT cross-check: 100.0,
    reproduced exactly here). Coverage: 1525/3458 (44%) — gated by `today_volume_0931`
    coverage above.
  - `record_volume_400d_0931` (PRIMARY "record volume" trigger, pre-registered): boolean,
    `today_volume_0931 > MAX(trailing ≤400 daily volumes, strictly before scan_date)` — the
    operator's own CHPT framing, but built only from what is known by 09:31 (a conservative
    bar: if PARTIAL volume already clears the full-day historical max, no lookahead is
    needed to trust it). Secondary/smoother cut: `vol_pct_daily_bars >= 95`.
  - **Named finding, not a variant**: CHPT's own 2026-09-03 row is `vol_pct_daily_bars=100.0`
    but `record_volume_400d_0931=False` — by 09:31 its partial volume (969,501 sh) had not
    yet cleared the historical single-day max (3,913,348), even though it already sat at
    the 100th percentile of rolling-20-day averages. Its `eod_record_400d=True` (day-0 full
    volume 42,975,618 vs the same 3,913,348 max). **The operator's own "record volume"
    description of CHPT is itself an EOD observation — by the 09:31 decision point, CHPT
    was unusually strong, not yet a confirmed record.** Stated in the open, not buried.

## Other parameters (fixed set, from the task's item 1)

- `gap_pct` at the nearest-09:31 tick (real-time; 3458/3458 coverage, 99.97%).
- `quality_adv_dollar` (liquidity $ proxy, sparse — 32 rows) AND a computed
  `dollar_volume_0931 = today_volume_0931 × prev_close` wherever `today_volume_0931` is
  known (1525 rows) — reported as the primary dollar-volume reading since it has far
  better coverage and is built the same no-lookahead way.
- `projected_vol_multiple`, `pm_rvol`: used as reported in scan_log (654/763 rows resp.);
  per CLAUDE.md, `projected_vol_multiple` is structurally None before 9:45 ET for most
  rows — reported, not treated as a gap.
- `float_shares`: scan_log column coverage is 13/3458 (<1%) — **too sparse to analyze as a
  standalone parameter across the full population**; reported for the `ever_scored` subset
  only (where the live pipeline computed it), flagged as insufficient elsewhere. Not
  backfilled via an external float source (out of scope given time/budget; float was
  already shown by #622 to carry no outcome information on the sub-cohort it COULD be
  checked on, so this is a low-value gap to fill).
- `catalyst_quality` (ordinal: routine=0, strong=1, game_changer=2, mna excluded — 1 row):
  from `any_catalyst_quality`/`any_llm_catalyst_quality` (whichever the scan_log row
  already carries — llm preferred when both present) — 425/3458 (12%) coverage. **No new
  paid grading in this study** beyond what already exists in `mi_ep_scan_log` +
  `_622sweep_catalyst_raw.jsonl` (109 rows, reused) — catalyst is one of nine parameters,
  not the hypothesis, and full-population re-grading (~3000 ungraded rows) would cost
  ~$35, far over the $6 budget, for a secondary axis. Reported on available coverage with
  the coverage stated on every number.
- `in_active_theme`: scan_log column, populated on 42/3458 rows (1%) — **near-zero
  variance for the rejected cohort** (matches #622's prior finding that theme_bonus is
  structurally inert off-universe); reported for the `ever_scored` subset, flagged
  uninformative elsewhere per the advisor's rule (a parameter with <2 levels at n≥30 is
  reported as uninformative, not correlated).
- `regime`: nearest `mi_market_regime` row strictly before scan_date — 3458/3458 (100%)
  coverage, real variance (Choppy 1777, Correcting 860, Bull 735, Crisis 86).

## Outcome frame

Realized R via `scripts/ep_replay.py walk_campaign`, rule-set `current` (era C), submit
09:31 ET (primary) — same walker, same abstain discipline as #617/#622. `validate` PASS
captured fresh in `_623_validate_out.txt` (2026-09-04) before any number below was read.
Minute bars: `mi_intraday_bars` where covered (1038/3458 ticker-days had ≥300 bars +
a 09:30 bar already stored); the remaining 2399 were fetched fresh from Alpaca SIP
(`_623_fetch_bars.py`, $0 — Algo Trader Plus subscription), day-0 RTH only (later sessions
walk off `mi_daily_closes`, which needs no fetch — 94-100% ticker coverage). Split-artifact
guard: same as `_622_replay.py` (`|daily_open/raw_0930_open - 1| > 5%` → excluded, not
walked). Degenerate-stop rows (risk/share < 0.3% of entry) are flagged, not excluded,
reported both ways (same as #622).

## The analysis (fixed cells, no new variant added after seeing R)

1. **Univariate**, per cap band and pooled: gap_pct, vol_pct_daily_bars, dollar_volume_0931,
   record_volume_400d_0931 (mean R with/without), market_cap (continuous, log), catalyst
   ordinal, regime, tick-freshness control — Spearman rho + direction, full sample /
   first-half-by-date / second-half-by-date, sign-agreement flagged.
2. **Interactions** (cells of n + mean R, not a single coefficient):
   - gap tercile × record_volume_400d_0931 (boolean) — the operator's primary hypothesis.
   - gap tercile × vol_pct_daily_bars tercile (smoother version of the same hypothesis).
   - cap band × gap tercile.
   - cap band × vol_pct_daily_bars tercile.
   - cap band × record_volume_400d_0931.
   - **Three-way**: cap band (collapsed to <$500M vs ≥$500M, for cell size) × gap tercile ×
     record_volume_400d_0931 — the operator's literal hypothesis ("big gap AND record
     volume, maybe smaller caps"), tested directly. A finer 5-band × tercile × tercile grid
     (45+ cells) is reported ONLY where n≥10 per the robustness rule below; thin cells are
     shown with n and not narrated as a finding.
3. Cap-band comparison of #2's results — the "separate lane" question directly.
4. **Live-lane impact**: "admitted today" = `ever_scored AND best_score_tier == 'HIGH'`
   (122 ticker-days) — the closest scan_log-native proxy to "the live stack lets it
   through," stated once, used consistently. For any rule highlighted in #2/#3: names/day
   added vs today, names/day dropped vs today, realized-R delta of both added and dropped
   sets.
5. **Robustness** on every headline cell: n, split-half by date, and the cell's mean R
   with its single largest-|R| contributor removed.

## Addendum (written after building features, BEFORE running `_623_analysis.py` — a
## mechanical correction to the grid, not an outcome-driven one)

A plain tercile split of `vol_pct_daily_bars` degenerates: 683/939 (73%) of all rows with a
value are EXACTLY 0.0 (genuinely — most EP candidates, scored and rejected alike, show zero
volume conviction against their own rolling-20-day history; cross-validated, not a bug), so
both tercile cutpoints land on 0.0 and the "mid" bucket is empty everywhere. Replaced by a
**distribution-shape-driven** 3-bucket split, fixed from the feature's own histogram before
any cell was joined to R: `none` (=0, 73%), `some` (0–89, 19%), `strong` (≥90, 9% — of which
≥95 is 5%, =100 is 4%). `record_volume_400d_0931` (the strict boolean) is kept as originally
registered but is reported alongside `strong` (≥90) wherever it is too thin (n<10) to stand
alone — it is true on only 7 of 939 rows with volume data, too rare on its own for any cell
above pair level.
