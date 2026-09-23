# #622 redo — sweep variants, PRE-REGISTERED before joining realized R

Written and locked at 2026-09-04 (PT), BEFORE `_622sweep_join.py` computes any
correlation or score against `realized_r_0931`. This is the overfitting guard
the task explicitly requires: with n≈107-109 settled names and several swept
parameters, a variant chosen AFTER looking at outcomes is not evidence, it's
curve-fitting. Everything below is fixed first; the join script may only
evaluate what's listed here (a grid counts as pre-registered — picking the
best cell inside a declared grid is the sweep's job; adding a NEW variant
after seeing R would not be).

## Univariate association pass (no variant construction — just direction/strength)
For each of: `gap_pct_0931`, `vol_pct_daily_bars`, `adv_dollar_0931` (and
log10), `market_cap_0931`, `float_shares_fmp_now`, `prior_3m_change_0931`,
`catalyst_quality` (ordinal routine=0/strong=1/game_changer=2), `in_active_theme`
(0/1), `regime_label=='Bull'` (0/1) — Spearman correlation vs `realized_r_0931`
on: (a) full clean-settled sample, (b) first-half-by-date, (c) second-half-by-date.
Report sign + magnitude + whether sign agrees across both halves.

## Score variants (all built on `agents.market_intelligence.ep_rubric` /
`ep_detector._score_ep`, imported directly — never reimplemented)

- **V0_HONEST_CURRENT**: `SCORE_WEIGHTS` (live, #533 separation ON) fed the
  honestly-reconstructed point-in-time inputs (gap/adv/mcap/vol_pct/catalyst
  all at the 09:31 tick, `vol_pct_daily_bars` for volume conviction). The
  "just fix the bugs, change nothing else" baseline.
- **V0L_HONEST_LEGACY**: `SCORE_WEIGHTS_LEGACY` (pre-#533), same honest inputs.
- **V1_GAP_LEGACY_LADDER**: `SCORE_WEIGHTS` with ONLY the `gap` component
  swapped for the legacy ladder (tiers 20/15/10/8% -> 25/20/15/10 pts).
  Floor/liquidity/vol_conviction/float/catalyst/theme unchanged (still the
  single branch-4 current floor). Isolates the gap-ladder effect from the
  floor-chain effect the prior study conflated.
- **V2_GAP_REVERSED**: `SCORE_WEIGHTS` with `gap` tiers INVERTED — same four
  cutpoints (8/10/15/20%) but point values reversed so a SMALLER qualifying
  gap scores MORE: 8-9.9%->25, 10-14.9%->20, 15-19.9%->15, >=20%->10. Directly
  tests the operator's "maybe smaller-gap is better for this cohort" question
  by construction, not by cherry-picking after seeing R.
- **V3_VOLCONV_GRID**: `SCORE_WEIGHTS` with `vol_conviction` tiers swept over
  the grid: cut in {50, 60, 70, 80, 90, 95} (single-tier ladder, `[(cut, w)]`)
  × weight `w` in {5, 10, 15}. 18 cells. Report which cells admit CHPT and
  each cell's cohort cost (n admitted, sum/mean R) — same as any other
  variant below.
- **V4_LIQUIDITY_RESCALED**: `SCORE_WEIGHTS` with `liquidity.adv_tiers`
  rescaled to this cohort's actual ADV$ range (observed ~$0.2M-$10M+ vs the
  live table's $50M-$500M): tiers `[(20_000_000,15),(10_000_000,12),
  (5_000_000,10),(2_000_000,7)]`. Tests whether ADV$ discriminates ANYTHING
  once scaled to a range this cohort actually occupies (today it is 0 for
  ~all names here, by construction of the live tiers).
- **V5_MCAP_CONTINUOUS**: NOT a `_score_ep` change (mcap is not a scored
  component live) — a standalone measurement: market_cap tercile/quartile
  within [0, $500M) vs `realized_r_0931`, tested in BOTH directions (does
  LARGER sub-$500M cap predict better R, or smaller). Reports correlation
  only; not blended into a score variant unless direction replicates
  split-half (see V7).
- **V6_FLOAT_CONTINUOUS**: `float_shares_fmp_now` as a continuous value /
  percentile vs `realized_r_0931` (replacing the live binary <50M cutoff),
  same both-directions, correlation-only treatment as V5.
- **V7_COMBINED**: built ONLY from whichever of V1/V2/V3(best split-half-
  replicating cell)/V4/V5/V6 individually (a) points the same direction in
  both date-halves of the univariate/variant pass and (b) is not driven by a
  single outlier ticker-day. Assembled and reported AFTER the individual
  passes — this is the one variant allowed to be a function of what the
  sweep found, since it is explicitly the "best honest combination" question
  Part 2 item 3 asks for, and its own split-half behavior is reported, not
  assumed.

## Outcome frame (fixed, matches the harness's own validated definition)
- `realized_r_0931` from `_622_replay_out.tsv`, cohort=excluded, status_0931=='settled'.
- Exclude RELL 2026-06-08 and AVBC 2026-07-24 (degenerate-stop rows, <0.3%
  risk width — the harness's own validate step flags these, not a choice
  made for this sweep).
- CAPR 2026-08-25 and TITN 2026-08-31 (`status_0931=='open_at_horizon'`) are
  reported as a footnote using `mark_r_0931` (unrealized), never blended into
  the primary sum/mean.
- Baseline to beat: the cohort's OWN unconditional mean R on this clean set
  (not zero) — a variant's admitted-set mean must be compared against this,
  not against breakeven, to mean anything.
- Split-half: chronological, first ~half of settled dates vs second ~half
  (not random — the honest out-of-sample cut for a time-ordered cohort).

## Grading coverage
109 settled + 2 open_at_horizon = 111 ticker-days minus 2 degenerate-stop
(excluded from analysis, one is settled) = 109 usable, plus 2 open_at_horizon
footnote rows. 49 already graded (prior run's 48 + CHPT); 60 newly graded this
session (`_622sweep_catalyst_raw.jsonl`) to cover the full usable set (not the
bucketed 48-sample the prior study used). no_entry/no_trade/abstain rows
(43 ticker-days) are NOT graded — no realized R, no use in this sweep.
