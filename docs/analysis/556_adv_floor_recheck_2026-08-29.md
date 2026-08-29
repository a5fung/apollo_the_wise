# #556 recheck — ADV floor cost, on corrected data (2026-08-29)

**Conclusion up front: the original ruling (KEEP the floor) holds, and the correction makes the
case stronger, not weaker.** The claimed "winners" the floor cost us roughly halve once fake
(never-gapped) rows are removed, and the real cohort's median forward return is *more* negative
than the original's already-negative headline number.

**MEASUREMENT ONLY. No criterion changed.** Source: `mi_ep_missed_outcomes`,
`skip_category='adv_low'`. `ret_5d` / `ret_20d` / `max_high_5d` / `max_high_20d` are raw
excursions from the day-0 open with **no stop** — NOT R, not a trade result (see #595). Medians
reported alongside every mean; every number carries its n.

---

## 0. What changed since the original doc (2026-08-20)

- Original doc's cohort: `skip_reason NOT LIKE '%adv_no_data%'` → **214 rows / 145 names**,
  window 2026-04-14 to 2026-08-19.
- Same cohort definition, live table today: **233 rows / 159 names** (19 more rows logged since,
  ordinary continued capture — not a data problem).
- New columns `open_gap_pct` / `setup_at_open` are now populated on 100% of the adv_low cohort
  (0 NULLs remain here — fully backfilled).

---

## 1. Raw cohort vs. real setups

| | rows | names |
|---|---|---|
| Raw ADV-low cohort (excl. `adv_no_data`, same scope as original doc) | **233** | **159** |
| — real setup at open (`setup_at_open = TRUE`, gapped ≥9%) | **77 (33%)** | 69 (43%) |
| — never gapped at the open (`setup_at_open = FALSE`) | 156 (67%) | 116 |

Two-thirds of the rows the original doc analyzed were never tradeable setups — in line with the
table-wide 66% corruption rate found in #595.

---

## 2. Corrected winner count vs. the original claim

"Winner" = `ret_5d >= 0.20`, the definition #595 used to score every gate.

| scope | winners | never a setup | real | corruption |
|---|---|---|---|---|
| #595's own citation — full `adv_low` incl. the 26 `adv_no_data` rows (n=259) | **28** | 16 | 12 | **57%** |
| Original doc's actual analysis scope — excl. `adv_no_data`, live table today (n=233) | 24 | 14 | 10 | 58% |
| Same, bounded to the original doc's exact date window 04-14→08-19 (n=214) | 23 | 14 | 9 | 61% |

Reconciled: this recheck reproduces #595's 28/16/12 exactly (confirmed at the row level — see
appendix). Whichever scope you use, **roughly half to three-fifths of the claimed winners never
happened.**

**Cross-check on the original doc's own metric.** The 556 doc's actual headline number was not
a `ret_5d` count — it was "28 distinct names reached a ≥50% 20-day peak" (Result 2). Rerun on
the same metric, bounded to the original window, counted in rows (some tickers re-alert and
appear on both sides, so rows and names don't split cleanly):

| | rows | never a setup | real | distinct names (approx., overlap possible) |
|---|---|---|---|---|
| ≥50% 20-day peak, 04-14→08-19 | 38 | 24 (63%) | 14 (37%) | 29 names total (orig. claimed 28 — matches); 20 never-setup, 13 real, 4 names appear on both sides |

Same story under either metric: **the real winner count is well under the claimed one.**

---

## 3. Forward outcomes of the corrected cohort (`setup_at_open = TRUE`, excl. `adv_no_data`)

n = 77 rows / 69 names. `ret_5d` scores at 5 trading days out, `ret_20d` at 20 — the longer
window has more rows still pending, so its n is smaller. 6 rows (alerted 08-24 to 08-26) are
too recent to have a `ret_5d` yet; more rows still lack `ret_20d`.

| | n scored | mean | median |
|---|---|---|---|
| ret_5d | 71 | **-7.8%** | **-6.2%** |
| ret_20d | 51 | -9.1% | -8.8% |

| ret_5d direction | n | share |
|---|---|---|
| up | 30 | 42% |
| down | 41 | 58% |

| ret_20d direction | n | share |
|---|---|---|
| up | 22 | 43% |
| down | 29 | 57% |

**Like-for-like comparison — same live table capture, same `adv_low` scope, filter OFF vs ON
(not the original doc's stale 08-19 numbers, so only the `setup_at_open` filter changes):**

| | filter OFF (raw, incl. fake setups) | filter ON (real setups only) |
|---|---|---|
| median ret_5d | -1.9% (n=219) | **-6.2% (n=71)** |
| median ret_20d | -3.5% (n=152) | **-8.8% (n=51)** |

Restricting to real setups only makes the median *more* negative at both horizons, not less.
Removing the phantom rows does not manufacture a cost case for the floor — it removes a false
credit, and what is left behind skews worse.

**One number that cuts the other way, reported for completeness.** Of the 77 real setups, 17
(22%) still hit a ≥50% 20-day peak and 4 (5%) hit ≥100% — both *higher* tail-hit rates than the
original doc's all-rows figures (17% and 7%, on n=214, corrupted). The ≥50% rate (n=17) is a
readable signal; the ≥100% rate rests on only 4 rows and is below the ~10-row floor for drawing
anything from it. This does not move the ruling — the median and the down-side share govern,
per the original doc's own framing — but it is not left out.

---

## 4. Does the original conclusion hold

**Yes — KEEP the floor, and the correction strengthens the case.**

| | raw, same live capture, filter OFF | corrected, filter ON (real setups only) |
|---|---|---|
| cohort | 219-233 rows (varies by metric's n) | 71-77 rows |
| median ret_5d | -1.9% (n=219) | **-6.2% (n=71)** |
| median ret_20d | -3.5% (n=152) | **-8.8% (n=51)** |
| down-side share at 5d | not separately stated in original doc | **58% (n=71)** |
| claimed winners (ret_5d≥20%) | 24-28 (scope-dependent) | **9-12 real** |

The floor was never argued to be costing us on the median — that was already negative in the
original doc. The correction confirms the "winners" side of the argument was inflated (roughly
half were phantom) while the "cost" side (the median, the down-side share) gets *worse* once
phantom rows are removed. Both moves point the same direction: keep the floor.

**Results 3 and 4 of the original doc are NOT re-confirmed here and should not be cited as
re-validated.** Both are outcome-based and computed on the corrupted 214-row base: Result 3's
dead-zone finding ("$500k-1M: 63 names, only 2% ≥100% peak, median 20d close -2.5%") and
Result 4's per-band liquidity shares both select their sub-cohorts by `ret`/`max_high` values
that this correction shows were partly phantom. They are not re-derived in this recheck (see
"What this does not answer") — this ruling rests only on the median and the winner count above,
not on the dead-zone finding. **Result 5** (ADV and market cap are near-redundant gates, so
loosening ADV alone is close to a no-op) is genuinely structural — it follows from filter
*ordering* in `backtester/filters.py`, not from any outcome column — and holds regardless,
though its own base shrinks from 145 names to the 69 that are real setups.

---

## What this does not answer

- **Not re-derived**: the original doc's ADV-band breakdown (<$250k / $250-500k / $500-750k /
  $750k-1M), Result 3's dead-zone finding, and Result 4's live-vs-paper liquidity share —
  restricted to real setups only. All three are outcome-based and were computed on the
  corrupted 214-row base; splitting the corrected 77-row cohort four ways would leave most
  bands under the ~10-row floor for a reliable read. Not attempted here — treat those two
  results as **not re-validated**, only Result 5 (gate ordering) still stands as-is.
- **No R-per-trade.** As in the original doc, nothing here reflects our actual entry/stop
  mechanics — `ret_5d`/`ret_20d` are unstopped excursions from the day-0 open, not results a
  live bracket would have produced.
- **`ret_20d` has a smaller scored n (51) than `ret_5d` (71)** within the same 77-row cohort —
  more rows are still short of the 20-trading-day mark. Not a data defect, just less elapsed
  time; stated wherever `ret_20d` is used above.
- **The 6 rows with no scored `ret_5d` yet** (alerted 08-24 to 08-26) are excluded from the
  return stats above pending more elapsed trading days, not because of any data defect.

---

## Appendix — the 12 real winners this recheck found (setup_at_open = TRUE, ret_5d ≥ 0.20, incl. adv_no_data rows to match #595's full 28-row citation) — 12 rows, 11 distinct names (ADVB re-alerts, appears twice)

| ticker | date | open_gap_pct | ret_5d |
|---|---|---|---|
| ADVB | 2026-07-20 | +33% | +114% |
| ADVB | 2026-07-22 | +18% | +32% |
| LVLU | 2026-07-14 | +17% | +68% |
| INHD | 2026-08-10 | +22% | +28% |
| RFAI | 2026-08-21 | +214%* | +30% |
| TCX | 2026-07-31 | +14% | +41% |
| BRUNW | 2026-05-14 | +10% | +32% |
| RNAC | 2026-06-09 | +20% | +29% |
| TRT | 2026-04-23 | +33% | +28% |
| BGDE | 2026-06-11 | +10% | +52% |
| ATRA | 2026-05-07 | +52% | +22% |
| LCUT | 2026-05-11 | +10% | +21% |

*RFAI's 214% open_gap_pct looks like a likely data outlier (extreme low-float print or a bad
prior-close reference) — flagged, not adjusted; not investigated further here.
