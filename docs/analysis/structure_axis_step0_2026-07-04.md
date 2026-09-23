# #330 STEP-0 — Structure-axis backfill + cross-tab (ADR 0016)

Read-only calibration required by `docs/decisions/0016-structure-axis-meta-rubric.md` before any
structure-axis shadow ships: backfill the 3 structure components onto the `mi_theme_axis_shadow`
cohort (#329's theme-axis backfill; 456 rows as of 2026-07-04, up from the ADR's "452" as the
backfill keeps accruing) and cross-tab against forward EP outcomes, to check whether Stage-2 +
tight-base separates fwd-5d outcomes in the direction the ADR proposes to boost.

**Script**: `scripts/probes/_330_structure_step0.py` (read-only; live SELECTs against
`mi_theme_axis_shadow` / `mi_ep_scan_outcomes` / `mi_daily_closes`; writes nothing). Run via
`docker exec apollo-market python scripts/probes/_330_structure_step0.py`.

## Method

For each `(ticker, alert_date)` in the cohort, computed **AS-OF strictly PRIOR to alert_date**
(the last `mi_daily_closes` bar with `trade_date < alert_date` — no lookahead):

| Component | Formula | Source |
|---|---|---|
| **Stage-2** | `prior_close > 200-session SMA` AND `prior_close >= 0.75 x trailing high` | mirrors `flag_detector.py`'s #356 HTF Stage-2 gate (`_STAGE2_NEAR_HIGH_MIN=0.75`, `_SMA200_WINDOW=200`) exactly on threshold/shape; anchor is `prior_close` not `pivot_high` (this cohort has alert dates, not flag pivots) |
| **Base tightness (RMV)** | RMV over the prior ~15 sessions | imported directly from `flag_detector._compute_rmv` (the SSoT tightness primitive) — not reimplemented |
| **Extension state** | `prior_close / 10-session SMA` | as specified by the ADR/task |

**Honesty flag on Extension**: the ADR's prose attributes this ratio to "the MAGNA53 extension
check's inputs," but MAGNA53's actual live gate (`ep_detector.py MAX_EXTENSION_PCT`) is a 5-day
MIN-close ratio, not an SMA-10 ratio — the `prior_close / SMA-10` shape specified here is really
the 9M detector's `_MAX_EXTENSION_FROM_MA10` (1.20x) gate. Computed exactly as specified either
way; flagged for the record rather than silently substituted (the ADR is ACCEPTED/signed).
`extension_ratio` is computable for 100% of the cohort (median 1.02x, range 0.18x-2.07x) but is
NOT part of the bucket split below — the ADR's cross-tab spec buckets on Stage-2 x tightness only;
extension rides along as backfilled telemetry for the eventual shadow.

**Bucket definition** (per the ADR): `Stage2+tight` = Stage-2 True AND `rmv_15` at/below the
median `rmv_15` among Stage-2-True rows; `Stage2-only` = Stage-2 True, RMV above that median;
`no-Stage2` = Stage-2 False. Rows where Stage-2 isn't computable are excluded from the cross-tab
and counted separately (coverage, below) — never silently folded into a bucket.

## Coverage (reported honestly, not silently shrunk)

`mi_daily_closes` currently retains **~13 months of history** (2025-05-27 -> 2026-07-02, verified
live). The cohort's alert dates span 2026-03-24 -> 2026-06-30. A **strict** trailing-252-session
high (the ADR's literal "trailing-252-session" spec) needs ~252 prior trading sessions, which
straightforwardly isn't available for most of the cohort's earlier rows given that history depth
— this is a data-depth ceiling, not a bug:

| Variant | stage2 computable | rmv_15 computable | extension_ratio computable |
|---|---|---|---|
| **PRIMARY** (strict 252-session high) | **63/456 (14%)** | 454/456 (100%) | 456/456 (100%) |
| **SUPPLEMENTARY** (relaxed — whatever history is loaded, mirrors `flag_detector.py`'s actual live behavior which has no hard 252-bar floor on the high) | 386/456 (85%) | 454/456 (100%) | 456/456 (100%) |

By month, PRIMARY coverage: 2026-03 0/26, 2026-04 0/131, 2026-05 26/250 (10%), 2026-06 37/49 (76%)
— coverage rises sharply as alert dates approach "now" and 252 prior sessions become available.
The binding constraint is the 252-session-high requirement specifically (SMA-200 alone is
computable for 386/456 = 85% — the SUPPLEMENTARY variant's coverage number, since it only relaxes
the high-window floor). Two variants are reported side by side rather than picking one, since the
strict reading is what the ADR asked for but is coverage-starved, and the relaxed reading recovers
a usable N without silently swapping in a shorter "252-session" window under the same label.

## Cross-tab

### PRIMARY (strict 252-session high) — N=63

```
ALL (N=63)
bucket                          n  settled   avg_fwd5d   med_fwd5d      win>=+5%
Stage2+tight                   17       15        9.9%        2.9%   6/15 (40%)
Stage2-only                    16       15        9.2%        3.6%   7/15 (47%)
no-Stage2                      30       25        5.7%        4.0%  10/25 (40%)

THEMED half (N=13)
Stage2+tight                    5        5        3.1%        1.7%   1/5 (20%)
Stage2-only                     5        5       17.1%        8.8%   3/5 (60%)
no-Stage2                       3        2        0.3%        0.3%   0/2 (0%)

THEMELESS half (N=50)
Stage2+tight                   12       10       13.3%        5.5%   5/10 (50%)
Stage2-only                    11       10        5.2%        2.6%   4/10 (40%)
no-Stage2                      27       23        6.2%        4.2%  10/23 (43%)
```

### SUPPLEMENTARY (relaxed — whatever history is loaded) — N=386

```
ALL (N=386)
bucket                          n  settled   avg_fwd5d   med_fwd5d      win>=+5%
Stage2+tight                   79       55       11.7%        7.7%  35/55 (64%)
Stage2-only                    79       62        9.1%        5.8%  33/62 (53%)
no-Stage2                     228      133       10.0%        6.5%  75/133 (56%)

THEMED half (N=49)
Stage2+tight                   24       20       11.1%        9.5%  12/20 (60%)
Stage2-only                    13       11       18.4%       13.8%   9/11 (82%)
no-Stage2                      12        6       12.6%        9.4%   4/6 (67%)

THEMELESS half (N=337)
Stage2+tight                   55       35       12.1%        7.1%  23/35 (66%)
Stage2-only                    66       51        7.1%        4.8%  24/51 (47%)
no-Stage2                     216      127        9.9%        6.1%  71/127 (56%)
```

(Median RMV cutline: 53.5 among the 33 PRIMARY Stage2==True/RMV-known rows; 53.3 among the 158
SUPPLEMENTARY ones — stable across variants, as expected since it's drawn from largely the same
Stage-2-True population.)

## Reading — honest, vs the ADR's boost direction

**PRIMARY (N=63, coverage-starved): NEUTRAL / inconclusive, not contradicted.** Stage-2 rows
(tight or not, avg ~9.2-9.9%) do show a higher average fwd-5d than no-Stage2 (5.7%) — directionally
consistent with the boost thesis — but win-rate is flat across all three buckets (40% / 47% / 40%)
and the tightness sub-split shows **no separation** (Stage2+tight's median 2.9% is actually
*below* Stage2-only's 3.6%). At N=15-25 settled per bucket, this is well below the ADR's own N>=30
bar and cannot support or refute the boost direction on its own — it is simply underpowered,
driven entirely by the 252-session-high coverage ceiling above.

**SUPPLEMENTARY (N=386, adequately powered): direction NOT contradicted — modestly supported.**
Every settled-count here clears the ADR's N>=30 threshold. `Stage2+tight` is the best bucket on
**all three** metrics vs `no-Stage2`: avg fwd-5d (+11.7% vs +10.0%), median (+7.7% vs +6.5%), and
win>=+5% (64% vs 56%) — and clearly separates from `Stage2-only` on win-rate (64% vs 53%), which
the tightness axis is specifically supposed to do. The THEMELESS half (N=337, the larger and
more representative slice, since #329's cohort skews themeless) shows the same pattern more
sharply: `Stage2+tight` 66% win vs `Stage2-only` 47% vs `no-Stage2` 56%. THEMED half is thin
(N=49, cells as low as 6-11 settled) and inverts on win-rate (Stage2-only 82% > Stage2+tight 60%)
— read as noise at that N, not a real interaction, until #329's stacking-cap decision has more
themed-cohort data to work with.

**Overall verdict**: per the ADR's own gate ("if the boost direction is contradicted at N>=30,
the table changes before exposure") — it is **not contradicted** at the only N>=30 reading
available (SUPPLEMENTARY), and that reading actively supports Stage-2 + tight-base as a boost
signal. The PRIMARY (strict-spec) reading is inconclusive on its own due to the 252-session
coverage ceiling, not because the direction is wrong. **Recommendation: proceed to the STEP-0.5
shadow build as planned** (ADR 0016 Rollout step 3); the coverage ceiling is worth carrying as a
`mi_daily_closes` history-depth watch-item (coverage improves automatically over the next several
months of monthly-1st sweeps as trailing history accrues past 252 sessions for the earlier
cohort rows too — no code fix needed, just time).

## Caveats

- **N per cell** is well under a calibration-grade sample in the PRIMARY variant (15-25 settled)
  and only comfortably above 30 in the aggregated SUPPLEMENTARY ALL/THEMELESS views — the THEMED
  interaction split (N=49, 6-20 settled per cell) is a bonus look, not a result.
- **All-HIGH cohort**: `mi_theme_axis_shadow` only backfills `score_tier='HIGH'` EP alerts (per
  `backfill_theme_axis_shadow.py`), so this measures whether structure separates outcomes WITHIN
  the HIGH tier — it says nothing about tier-STEP effects (routine->strong), since no sub-HIGH
  rows exist in the cohort yet; that cannot be measured until the shadow accrues sub-HIGH tiers
  (same limitation the 0015 theme-axis STEP-0 flagged).
- **fwd_5d_pct is a MAX-high-over-5-sessions metric** (`mi_ep_scan_outcomes`, matches the
  dead-zone-analysis convention), not a realized-trade return — directional read only, consistent
  with how this metric is used elsewhere (`judge_review.py`, ADR 0015's STEP-0).
- **SUPPLEMENTARY variant is NOT the ADR's literal spec** — it's disclosed as a secondary,
  clearly-labeled read to compensate for the PRIMARY variant's coverage ceiling, not a silent
  substitution. Both are reproducible from the same script/data pull.
- **Extension state** (component (c)) is fully backfilled (100% coverage) but not cut into the
  cross-tab per the ADR's own bucket spec (Stage-2 x tightness only); it rides along as telemetry
  for the shadow build.

## Commit

Script: `scripts/probes/_330_structure_step0.py`. This doc: `docs/analysis/structure_axis_step0_2026-07-04.md`.
