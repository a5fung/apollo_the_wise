# #95 intraday support-test detector — N≥10 graduation read (2026-09-15)

**Review:** `data_gated_reviews.yaml::intraday_support_test_signal_n10`.
**Verdict the review's OWN gate fires: NOT PROMOTE, and NOT its own "weak" bucket either — the pooled read falls
between the gate's buckets; the current-era read is NOT-ENOUGH-N (n=9 < 10) and what there is reads weak.**
Gate 1 needs N≥10 + median 5d ≥ +2% + ≥40% up 5%+. Pooled (n=23, verbatim): median 5d **+2.48%** (passes),
win rate **21.7%** at 5d / 34.8% at 10d (fails 40% on either window). Gate 2 defines "weak" as median < 0% — not met
pooled. **But the pooled N=23 is reached only by pooling a retired parent universe (14 rows, ≤06-26) with the current
one (9 rows, ≥06-29).** In the current era: median 5d **−5.5%**, 1 of 9 up 5%+, 0 tail, 3 independent campaigns.

**⚖ THE LINE.** Nothing was flipped. Any revise (tag tolerance, hold-time, sector/regime filter) is a criterion change
— CHANGE_PROCESS + operator sign-off. EP-first stands; no PROMOTE fires; sequencing sits behind #508.

## The decision this serves

Whether the support-test detector (#95: base_low tagged within ±1%, ≤2% undercut, bounced ≥0.5% and holding ≥0.5%
above base_low; no volume gate per Morales) graduates to an operator-confirm entry (`/supporttest ENTER`, stop just
below base_low). What would change it: median 5d ≥ +2% with ≥40% of names up 5%+, on an N≥10 that belongs to the
detector as it runs today.

## Population

- **Source rows:** `mi_flag_support_tests`, all 68 rows ever (2026-05-26 → 2026-09-09, 49 tickers), joined to
  `mi_daily_closes` for the fire-day OHLC and the next 5/10/20 trading closes, highs and lows. Dumped once to
  `/tmp/gated3/st_raw.csv`; computed locally.
- **Gate population (predicate, verbatim):** `test_date ≤ today−12d`, `parent_invalidated_eod = FALSE`, 10th forward
  close present → **n=23** rows, 15 tickers. 1 survivor not yet settled (AMLX 09-08).
- **Entry:** `current_price` — the bounce-detection price, per the review's explicit instruction (not next-day open).
- **⚠ ERA — parent universe rebuilt 2026-06-27** (#356 HTF spec replaced the n=1 50/60 flag; parent's actionable
  roster ~1,000/month → ~65/month). Detector gates unchanged after 05-26. **Era A = fires ≤ 06-26 (retired parent),
  n=14; Era B = fires ≥ 06-29 (current parent), n=9 from 4 tickers (ABVX ×2, NEO, PAY ×3, WDAY ×3) = 3 independent
  campaigns.** The predicate's 23 is 61% retired-universe.
- **⚠ Survivor filter is outcome-conditioned and removes 2 of 3 fires.** 44 of 68 rows (65%) had the parent stamped
  INVALIDATED at the same day's 17:25 close (lag 0 on every row) — a bounce that was "holding" at the scan tick and
  did not hold to the close. That is the day-0 close, unknown at entry. The unconditioned population is shown beside
  the gate number; an operator-confirm entry at the bounce would carry all of it.
- **Independence:** 19 of 68 rows re-fire within 10 days of a prior fire; first-fire n = 49 (11 settled Era A,
  3 Era B).
- **What the system already did:** 0 fires coincided with an EP alert or a live-trade alert date; 19 coincided with a
  same-day MA-pullback fire (the same bounce seen by two detectors), 0 with a flag break.
- **Data integrity:** no split/adjustment artifacts (every detection price within 25% of the same-day stored close);
  a forward-window scan found no single-day discontinuity.
- **Footnotes:** 3 rows on 05-26 ran the pre-#124 `day_low` version; 0 rows on the 08-04 stale-parent day.
- Forward returns are raw closes, no stop, no management. Stop-aware rows use stop = `base_low` (the gate's "just
  below base_low"); a day-0 hit counts only if the full-day low is below the detection-time low AND below the stop.

## The numbers

### The gate, verbatim, by population

| population | n (tickers) | median 5d | avg 5d | ≥+5% at 5d | avg 10d | median 10d | ≥+5% at 10d |
|---|---|---|---|---|---|---|---|
| gate pop, pooled (verbatim) | n=23 (15) | **+2.48%** | +0.59% | **21.7%** | +2.56% | +0.18% | 34.8% |
| Era A ≤06-26 (retired parent) | n=14 (11) | +2.93% | +2.90% | 28.6% | +6.25% | +6.48% | 50.0% |
| Era A first-fire only | n=11 (11) | +2.70% | +2.49% | 27.3% | +5.90% | +4.40% | 45.5% |
| **Era B ≥06-29 (current parent)** | **n=9 (4)** | **−5.50%** | −3.01% | **11.1%** | −3.18% | −6.30% | 11.1% |
| Era B first-fire only | n=3 (3) | −3.56% | −1.48% | 0% | +0.90% | −3.59% | 33.3% |
| unconditioned, pooled (all 65 settled) | n=65 (47) | +0.37% | −0.15% | 26.2% | +1.68% | −0.53% | 35.4% |
| unconditioned, Era B | n=20 (11) | −5.16% | −4.07% | 15.0% | −6.34% | −6.83% | 15.0% |

### Tail first

| population | window | n | mean | median | p90 | ≥+5% | ≥+20% | ≥+40% | ≤−10% |
|---|---|---|---|---|---|---|---|---|---|
| gate pop pooled | 10d | n=23 | +2.6% | +0.2% | +11.4% | 8 (35%) | 1 (4%) | 0 | 0 |
| gate pop pooled | 20d | n=17 | +6.6% | +10.3% | +18.8% | 11 (65%) | 2 (12%) | 0 | 3 (18%) |
| gate pop pooled | MFE 20d (max high — NOT a return) | n=17 | +17.6% | +19.3% | +28.9% | 14 (82%) | 8 (47%) | 0 | — |
| Era A | 10d | n=14 | +6.3% | +6.5% | +11.3% | 7 (50%) | 1 (7%) | 0 | 0 |
| Era A | 20d | n=14 | +8.8% | +11.2% | +19.5% | 10 (71%) | 2 (14%) | 0 | 1 (7%) |
| **Era B** | 10d | n=9 | −3.2% | −6.3% | +3.1% | 1 (11%) | **0** | 0 | 0 |
| Era B | 20d | n=3 | −3.5% | −10.7% | +7.6% | 1 | 0 | 0 | 2 |
| unconditioned pooled | 10d | n=65 | +1.7% | −0.5% | +18.7% | 23 (35%) | 6 (9%) | 1 (2%) | 10 (15%) |
| unconditioned pooled | 20d | n=55 | +4.2% | +1.5% | +28.2% | 25 (45%) | 9 (16%) | 2 (4%) | 17 (31%) |
| unconditioned Era B | 10d | n=20 | −6.3% | −6.8% | +7.6% | 3 (15%) | 0 | 0 | 5 (25%) |

The only ≥+20% survivor at 10d is OKTA 06-16 (+21%); without it the pooled mean is +1.7%, median −0.2%. The
unconditioned tail (STFS 06-12 +113%, QDEL +31%, TTMI +25%, OKTA +22%, COMP +22%) lives almost entirely in the rows
the gate EXCLUDES — names that undercut into the close, were stamped invalidated, and then ran. Under any stop near
base_low those were stop-outs first.

### Era B roster (the current detector, every settled survivor)

| ticker | date | stage | entry | d0 close | 5d | 10d | 20d | lowest low in 10d | stop (base_low) |
|---|---|---|---|---|---|---|---|---|---|
| ABVX | 07-16 | TIGHTENING | 136.00 | 137.77 | −3.6% | −8.6% | −10.7% | 118.18 | 134.60 |
| ABVX | 07-17 | TIGHTENING | 135.24 | 136.65 | −7.1% | −7.6% | −12.0% | 118.18 | 133.38 |
| NEO | 07-21 | TIGHTENING | 14.18 | 14.45 | −5.5% | +14.9% | +12.1% | 13.05 | 13.80 |
| PAY | 08-20 | TIGHTENING | 39.30 | 38.42 | −9.4% | −6.4% | n/a | 34.65 | 38.15 |
| PAY | 08-21 | TIGHTENING | 38.62 | 40.00 | −6.8% | −6.3% | n/a | 34.65 | 38.10 |
| PAY | 08-25 | TIGHTENING | 38.26 | 39.34 | −8.2% | −7.9% | n/a | 34.65 | 37.70 |
| WDAY | 08-26 | COILED | 191.98 | 190.75 | +4.6% | −3.6% | n/a | 183.53 | 189.31 |
| WDAY | 08-27 | COILED | 191.97 | 193.57 | +7.8% | −3.3% | n/a | 183.53 | 189.31 |
| WDAY | 08-28 | COILED | 193.85 | 204.72 | +1.0% | +0.2% | n/a | 183.53 | 188.05 |

Every one of the 9 traded through its base_low stop within 10 days (n=9, 100% stopped, −9.0R total). NEO is the one
that came back.

### Stop-aware

| stop rule | population | n | stopped 10d | mean R 10d | ≥3R 10d | stopped 20d | mean R 20d | ≥3R 20d | median risk |
|---|---|---|---|---|---|---|---|---|---|
| base_low (literal) | gate pooled | n=23 | 96% | −0.98R | 0 | 96% | −0.93R | 0 | 1.4% |
| base_low −2% (detector's undercut tolerance) | gate pooled | n=23 | 78% | −0.40R | 1 (4%) | 78% | −0.08R | 3 (13%) | 3.3% |
| base_low −2% | Era A | n=14 | 64% | −0.02R | 1 | 64% | +0.51R | 3 (21%) | 3.1% |
| base_low −2% | Era B | n=9 | 100% | −1.00R | 0 | 100% | −1.00R | 0 | 3.4% |
| base_low −2% | unconditioned pooled | n=65 | 86% | −0.58R | 2 (3%) | 88% | −0.28R | 6 (9%) | 3.4% |

The entry is 0.5–1% above base_low by construction, so the gate's own stop is inside daily-bar noise; at 2% below,
Era A turns marginally positive at 20d (3 of 14 reach 3R) and Era B stays 100% stopped.

## The revise menu, as the gate lists it (each is a criterion change → CHANGE_PROCESS)

- Tighten the ±1% tag tolerance.
- Minimum hold-time / multi-tick confirmation — the 65% same-day invalidation rate says the bounce seen at one scan
  tick does not hold to the close 2 times in 3; this is the item the data speaks to most directly.
- Sector / regime filter — not evaluable at n=9.

None is recommended here; the current-era evidence (n=9, 3 campaigns) cannot rank them. The honest reading of the
gate's own bucket 3 ("N<10: bump +30d") is that it applies to the current era — but at 2–3 fires a month under the
HTF parent, a further 30 days adds ~3 rows and does not change the read.

## What this does not answer

- **Universe vs regime.** Era A (May–Jun, retired parent) and Era B (Jul–Sep, HTF parent) differ in both the
  universe and the market; the Era A positives cannot be attributed to the detector.
- **Whether the current-era detector has an edge:** 9 rows, 4 tickers, 3 independent campaigns — under any N bar.
- **Actual fills and stops.** No minute-bar simulation (the review's own precondition); `current_price` is a
  5-minute snapshot; stop hits judged on daily lows.
- **Whether the survivor filter should exist.** It removes 65% of fires on day-0 close information. The unconditioned
  rows are the honest base for any entry design and they carry the tail — but that tail sat below base_low first.
- **The Era A rows under today's parent** — not replayed.
- The 19 fires shared with the MA-pullback detector on the same day are the same bounce; which detector "owns" it
  is not decided here.

Working files: `/tmp/gated3/` (st_raw.csv, results_st.txt, results_stop_sensitivity.txt, jump_scan.txt, compute.py).
Prod was read only.

## Addendum 2026-09-22 — the current era reached n=10, and the gate reads weak

- **Population:** the predicate verbatim (current era only, fires ≥ 2026-06-27, survivors of the day-0
  close, 10th forward close present) — 10 rows from 5 tickers — at most 4 independent campaigns by the 09-15 count (ABVX ×2, NEO, PAY ×3,
  WDAY ×3, AMLX 09-08, the one survivor that was unsettled on 09-15). Entry = `current_price`. Pulled once from
  prod to the session scratchpad.
- **Gate:** median 5-day **−4.55%**, median 10-day **−4.95%**, 1 of 10 up 5%+ on either window → bucket 2
  (weak) fires on the gate's own terms. Not promoted.
- **Every row traded below `base_low` within ten sessions** — the level the gate names for the stop. The
  two names that later ran (NEO +15%, WDAY +10% to the ten-day high) went through it first. As with
  #327's delayed-entry read, the placeholder stop is what fails; that is an input to the entry-and-exit
  work the operator ruled undetermined on 2026-09-22, not a verdict on the pattern.
- **Not revised.** The revise menu above is unchanged and each item is still a criterion change; the
  hold-time item needs a minute-bar replay; EP-first priority stands. Same-day invalidation: 14 of the 24
  current-era fires died by the day-0 close.
- **Still does not answer:** actual fills (no minute-bar simulation), and whether any exit other than
  "just below base_low" would have kept the two runners.
