# HTF — does the 20-day-average kill cost us breakouts? HTFL, MRNA and the board's own history (2026-10-22, #697)

**Scope banner.** This page measures DETECTION behaviour of the HTF stage board (`flag_detector.py`, shadow, not traded):
- stage labels;
- whether a base later closed above its base high or below its base low.

It contains no realized R and no simulated entry or exit. **Nothing was changed.** The SMA20 invalidation is an admission
criterion and the operator's call (THE LINE, CHANGE_PROCESS). It extends the 2026-09-18 read
(`docs/analysis/610_htf_depth_and_sma20_margin_2026-09-18.md` §4), which found an SMA20 margin of up to 1% adds zero
TRIGGERED events in 88 scan days. Since then two labelled cases arrived: HTFL (his 10-20 "did we catch it?") and MRNA (his
10-15 top example).

## Method and population

- **(A) Kill rows.** Every stored `mi_flag_candidates` row whose reason is the SMA20 kill (`close_X_below_sma20_Y`), scan
  dates 2026-05-04 → 2026-09-22 (mature: 30 calendar days ≈ 20 sessions of forward bars by 10-22). The depth below the
  20-day average is parsed from the reason. Outcome from `mi_daily_closes`: the first close above the row's `base_high`
  ("broke out first") vs the first close below its `base_low` ("failed first"), within 30 calendar days. The reference is
  the first WATCH-or-better row of each base (never a hold), with the same outcome window. `q1.sql` / `q1.out`.
- **(B) The threshold itself.** Every stored row within ±2% of its 20-day average, scan dates ≤ 09-22. Excluded: rows an
  earlier gate killed (base age, base low) and held rows. Close from `mi_daily_closes`, `sma_20` from the row. The bands are
  just below vs just above. The kill is a pure threshold, so names a hair either side are alike, and outcomes that match
  across zero mean the threshold separates nothing at the margin. `q2.sql` / `q2.out`.
- **(C) The two labelled cases, re-scored.**
  - Scorer: the REAL `compute_flag_metrics`, with one comparison loosened (`close < sma_20 × (1 − tol)`, tol 0 / 0.5% / 1% / 2%).
  - Variant build: a runtime copy, the one edit asserted; nothing in the repo edited.
  - Inputs, threaded from prod's STORED rows the way `scripts/probes/_146_unpark/replay_stored_146.py` does: yesterday's
    stage and hold, the 5-calendar-day stages, and the carried pivot.
  - Fidelity: at tol 0 it reproduces the stored stage on all 9 HTFL dates (MRNA's 09-16 too). `replay_two.py` /
    `replay_two.out`.

Everything is in `scripts/probes/_697_sma20_1022/`. It cost $0 (read-only SQL and local replay).

## 1. HTFL — the 20-day rule did not cause the miss

| Date | Stored | Re-scored, tol 0 | 0.5% | 1% | 2% |
|---|---|---|---|---|---|
| 09-29 | TIGHTENING | TIGHTENING | = | = | = |
| 10-01 | INVALIDATED (−0.08%) | INVALIDATED | TIGHTENING | TIGHTENING | TIGHTENING |
| 10-07 | INVALIDATED (−0.04%) | INVALIDATED | WATCH | WATCH | WATCH |
| 10-14 | INVALIDATED (−0.46%) | INVALIDATED | WATCH | WATCH | WATCH |
| 10-15 | WATCH | WATCH | = | = | = |
| 10-16 | INVALIDATED (−2.70%) | INVALIDATED | INVALIDATED | INVALIDATED | INVALIDATED |
| 10-19 | WATCH | WATCH | = | = | = |
| **10-20 (his breakout)** | **WATCH** | **WATCH** | **WATCH** | **WATCH** | **WATCH** |

(n = 9 dates, one ticker.)

- **At every tolerance up to 2%, HTFL's breakout day still reads WATCH, not TRIGGERED.** A breakout needs a TIGHTENING-or-
  better label in the 5 calendar days before it (the #146 licence). The 10-15 → 10-19 window holds WATCH, a −2.7% kill and
  WATCH at every tolerance. Loosening the kill turns those nights into WATCH, never into TIGHTENING.
- **The real blocker:** after 10-01 the base never read tight again by the range/volume contraction test. Its October closes
  swung up to 3.8% under the 20-day average.
- **Correction to the 10-20 record:** of the five October kills, three were shallow (−0.04% to −0.46%) and two were deep
  (−2.70%, −3.75%), not "five by a few cents". The kill was not the deciding gate.

## 2. MRNA — also not the 20-day rule

At every tolerance, MRNA's 09-16 moves from `INVALIDATED sma20` to `unqualified ma_stack_not_stage2_143.8/145.7/94…` (the
10 ≥ 20 ≥ 50 order fails). 09-17 / 09-18 stay `ma_stack_not_stage2`, and 09-11 / 09-15 stay on the flag-depth gate
(`flag_low_128.61_below_75%_of_pole_176.66`). This is the 09-18 finding again: the blockers are the depth reading and the
MA-stack order, not the 20-day rule (n = 5 dates, one ticker).

## 3. The board's history — the threshold at exactly the 20-day average separates nothing

(B), every row within ±2% of its 20-day average, the next ~20 sessions:

| Band | n rows | n bases | avg position in base (0 = low, 1 = high) | broke out first | failed first |
|---|---|---|---|---|---|
| below by 1–2% | 127 | 116 | 0.31 | 33.9% | 55.1% |
| below by 0.5–1% | 85 | 78 | 0.33 | 31.8% | 57.6% |
| **below by < 0.5%** (killed) | **72** | **66** | 0.35 | **38.9%** | **48.6%** |
| **above by < 0.5%** (kept) | **76** | **64** | 0.40 | **42.1%** | **50.0%** |
| above by 0.5–1% | 92 | 80 | 0.42 | 33.7% | 52.2% |
| above by 1–2% | 231 | 193 | 0.39 | 40.7% | 50.2% |

(A), every kill row by depth, the next ~20 sessions:

| Kill depth under the 20-day | n rows | n bases | broke out first | failed first |
|---|---|---|---|---|
| reference: first WATCH+ row of each base | 1,686 | 1,686 | 59.8% | 36.1% |
| < 0.5% | 81 | 69 | 38.3% | 50.6% |
| 0.5–1% | 87 | 78 | 33.3% | 57.5% |
| 1–2% | 129 | 114 | 33.3% | 55.0% |
| 2% or more | 901 | 349 | 15.5% | 67.4% |

- **There is no step at zero.** Names a hair under the average (killed) and a hair over it (kept) do alike: 38.9% vs 42.1%
  broke out first, 48.6% vs 50.0% failed first, on ~70 rows each. A deep kill (2%+) is a real warning: 15.5% broke out first.
- **The harm is small.** About 81 rows in 4.5 months (~4 a week) sit within 0.5% under. The 09-18 replay found that a margin
  up to 1% added zero TRIGGERED events, and today neither labelled miss turns on it.

## Recommendation (mine; the ruling is his)

- **Keep the 20-day rule as it is.** Loosening it would not have caught HTFL or MRNA. On the board's history a shallow kill
  is noise but rare, and it has cost no measured breakout (no rules without measured harm).
- **HTFL's real question is the tightening window.** It tightened at the end of September, went loose in October and broke
  out 10-20 with no tight label in the 5 days before. Whether a breakout should be licensed by an older TIGHTENING label
  (10 or 15 sessions back) is a different detection question. It would loosen every breakout, so it needs its own read and
  his call. It is not proposed here.

## What this does not answer

- Whether HTF bases pay: this is detection only, with no R.
- Bands (B) count rows, not bases. A base can sit in a band on several nights. The n of distinct bases is stated beside it.
- One tape (May → September 2026) and two labelled cases. The labelled cases are worked examples, not rates.
- The ±0.5% band split rests on ~70 rows a side. A difference of a few points is inside the noise. The claim is only "no
  visible step", not "identical".
- The intraday break scan is not replayed. "Broke out first" is a daily-close proxy.
