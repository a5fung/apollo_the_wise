# #454 R3 part (2) — Regime-stratified re-cut of the #268b calibration envelope

**Date:** 2026-07-17 · **Status:** ANALYSIS ONLY — feeds the quarterly band review
(`data_gated_reviews.yaml::kill_scale_bands_quarterly_review`); changes NOTHING live.
**Generator:** `scripts/_454_regime_stratified_envelope.py` (read-only prod SELECTs;
re-run any time to regenerate every number below).
**Envelope under test:** `kill_scale_bands.CALIBRATION_ENVELOPE` — #268b Phase B, n=399,
+0.95R / 30% win · t20 p5 −0.63R / min −1.03R · maxDD −24.1R · worst streak 15
(operator-signed 2026-06-12, `docs/setups/safeguards.md`).

## TL;DR

**The exact per-regime re-cut is not possible from any surviving data** — the per-trade R
series behind the envelope no longer exists anywhere reachable (§2). What IS recoverable
proves something stronger than "no stratification was done": **the window cannot support
stratification at all.** The "12-month mixed-regime window" was ~94% Bull by trading days
(~95% by estimated candidate exposure), and its entire non-Bull content is ONE contiguous
3-week episode (2026-03-21 → 2026-04-09, the March-2026 crash) contributing an estimated
~21 of the 399 envelope-cohort trades. **The #268b envelope is a Bull-conditional
envelope, mechanically.** It does not misprice non-Bull regimes — it does not price them.

## 1. How the envelope was built (provenance)

1. `scripts/selection_replay_268.py` (Phase B, run 2026-06-11/12 on prod): scan → grade
   (LLM) → judge (Opus) → simulate over 2025-06-09..2026-05-04; 1,307 candidates, 953
   simulated, judge-HIGH cohort n=399.
2. `--simulate` wrote per-trade `r_multiple` to a **CSV only** (default `/tmp` inside the
   container) — simulated outcomes were **never persisted to any DB table**
   (`mi_ep_alerts` has no outcome column; verified via `information_schema`).
3. `scripts/_killscale_bands_268.py` joined `replay268_phaseB.csv` ×
   `replay268_tiers.csv` and printed the envelope stats, which were signed into
   `safeguards.md` and hardcoded as `CALIBRATION_ENVELOPE`
   (`agents/market_intelligence/kill_scale_bands.py`).

## 2. Why the exact re-cut is unreachable (what is missing, exactly)

Verified 2026-07-17 (searches + read-only SELECTs; the script re-verifies the SQL-visible
parts on every run):

| Missing artifact | Detail |
|---|---|
| `replay268_phaseB.csv` (per-trade R) | Absent from the local repo/home, prod host (`/`, `/tmp`, `/home/apollo`), all six containers. `/tmp` in-container did not survive rebuilds since 6/12. |
| `replay268_tiers.csv` (tier dump) | Same — absent everywhere. |
| `mi_ep_alerts` `source='historical_scan'` population | Only **107 of 1,307** in-window rows survive (2026-04-13..2026-05-04, `created_at` 2026-06-11 = the Phase-B run). The 2025-06-09..~2026-04-10 span was deleted (`delete_historical_alerts` exists for idempotent re-runs; a later replay cleared it). |
| Non-Bull-day candidates | **Zero** surviving in-window rows fall on a non-Bull regime day — even the tier axis of the crisis-cluster cohort is gone. |
| Backups | Oldest on-host pg dump (`apollo-20260710.sql.gz`): its `mi_ep_alerts` COPY block holds only 123 in-window `historical_scan` rows (2026-04-06+). No older dump on the host. |

Rebuilding the series means re-running scan → grade (~1,300 LLM calls) → judge (~1,300
Opus calls) → simulate: a paid, **write-side** rerun (inserts `historical_scan` rows) —
out of scope for this read-only card and gated by rigor-before-paid-eval-spend. Options
for the quarterly review are in §5.

**Process finding:** the signed envelope's source data had no archival home — one `/tmp`
CSV and DB rows that a later idempotent re-run was allowed to delete. Any future
calibration run should persist its per-trade outcome series somewhere durable (DB table
or a checked-in CSV) in the same commit that cites it.

## 3. Reachable stratification — regime composition of the calibration window

Source: `mi_market_regime` — the SAME regime history the replay's grade stage consumed
(its regime lookup reads this table). Trading days only (the table also holds weekend
rows; 2 of the 13 Crisis rows are Saturdays and are excluded).

### 3a. Regime-day composition, 2025-06-09..2026-05-04 (n=236 weekdays)

| Regime | Weekdays | Share |
|---|---|---|
| Bull | 222 | 94.1% |
| Crisis | 11 | 4.7% |
| Correcting | 2 | 0.8% |
| Choppy | 1 | 0.4% |

**Every non-Bull day is in ONE contiguous cluster** — 2026-03-21 → 2026-04-09 (the
March-2026 crash): Crisis 3/23–4/02 and 4/06–4/07, Choppy 4/03, Correcting 4/08–4/09.
Zero independent non-Bull episodes elsewhere in the 12 months.

### 3b. Estimated per-regime exposure of the envelope cohort

Per-day candidate counts are unrecoverable (§2), so the finest honest grain is the
preserved **monthly** candidate table in `docs/analysis/selection_replay_268_phaseB.md`,
pro-rated by each month's regime-weekday mix. Order-of-magnitude estimate — candidate
flow is not uniform within a month (crash weeks plausibly produce atypical EP-gapper
counts):

| Regime | Est. candidates (of 1,307) | Share | Est. trades in envelope cohort (of n=399) |
|---|---|---|---|
| Bull | ~1,240 | 94.8% | ~378 |
| Crisis | ~52 | 3.9% | ~16 |
| Correcting | ~11 | 0.8% | ~3 |
| Choppy | ~5 | 0.4% | ~2 |

Non-Bull total: ~67 candidates → **~21 envelope-cohort trades**, all from the single
March-2026 episode. Compare the bands' own sample floor: `_SAMPLE_FLOOR = 20` — a
"Crisis envelope" cut from this window would sit at the floor with zero episode
replication; Correcting/Choppy would be n≈2–3.

### 3c. Regime-label provenance caveat

The 2025-06 → 2026-02 regime rows were **backfilled in one batch on 2026-03-28** (live
labeling began ~2026-03-19); every backfilled label is Bull. If the backfill
under-detects short Choppy/Correcting spells, the Bull share above is overstated —
which would mean even the ~5% non-Bull estimate is generous to the envelope's claimed
regime mix. Either way the mono-regime conclusion stands or strengthens.

## 4. Verdict — does the mixed-window envelope materially misprice any regime?

1. **It does not price non-Bull regimes at all.** ~95% of the envelope's estimated
   exposure is Bull-labeled; the non-Bull remainder (~21 trades) comes from one 3-week
   episode. No valid per-regime envelope for Crisis/Correcting/Choppy exists in this
   data — a re-cut table pretending per-regime percentiles would be noise dressed as
   calibration.
2. **The bands' "never fires on normal healthy variance" guarantee is a Bull-year
   guarantee.** In a sustained non-Bull tape (longer than the 3-week cluster), there is
   no evidence the trailing-20 floor stats (p5 −0.63R / min −1.03R) hold; band breaches
   there could be regime effects, not strategy decay — and the operator should read a
   REDUCE/KILL trigger in a non-Bull tape with that prior.
3. **Plausible but unverifiable** (needs the lost trade series): the envelope's worst
   trailing-20 windows (min −1.03R) likely ARE the March-2026 crisis cluster — i.e. the
   single crash episode may be what set the outer edge of "healthy variance". If true,
   the bands' outer thresholds encode one crisis's depth, not crisis behavior generally.
4. Corollary for the early-window drift line (#454 part 1, shipped alongside this doc in
   `system_review._early_window_drift_section`): its comparison anchors
   (`trailing20_p5_r` / `trailing20_min_r`) inherit the same Bull-conditionality — the
   caveat travels with the envelope, wherever it is cited.

## 5. Options for the quarterly band review (operator decides — none pre-decided here)

- **(a) $0-LLM partial re-cut:** re-run ONLY `--scan` + `--simulate` (both deterministic,
  no LLM spend) over the same window and stratify the ALL-candidate outcome distribution
  by regime. Outcomes are selection-independent by design ("simulate every candidate's
  ORB outcome once"), so this answers the actual question — regime effect on raw EP
  outcome distribution — without grade/judge spend. NOT read-only (re-inserts
  `historical_scan` rows; Polygon load), hence not done under this card.
- **(b) Full paid re-run** (scan → grade → judge → simulate, ~2×1,300 LLM calls) to also
  re-cut the judge-HIGH cohort per regime. Per rigor-before-paid-eval-spend: only if (a)
  shows a regime effect worth pricing on the selected cohort.
- **(c) Prospective accrual:** let the LIVE cohort stratify itself — the daily regime
  label is recorded, and the #302 `replay_regression_snapshot` rows accrue; revisit when
  a non-Bull spell has produced enough closed live trades to compare. Slowest, $0,
  measures the real system.
- **Either way:** durable persistence for any future calibration series (§2 process
  finding), so the next re-cut request is a SELECT, not an archaeology dig.
