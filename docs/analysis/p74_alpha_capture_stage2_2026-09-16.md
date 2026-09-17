# Phase 7 Stage 2 — did the carryforward lift alpha capture? (2026-09-16)

**Answer first: the question cannot be answered on this measure, because the measure's own dominant
input changed definition in the middle of the window.** The continuation-flag board supplied **44 of
51** captures in the first half of the window and **6 of 14** in the second, and #356 deliberately
swapped its promotion criteria to the sourced HTF spec on **2026-06-26**. Every capture number ever
quoted for this review — the 34% baseline, the 51.0% read of 2026-08-11, and today's — is a reading
of a bar that has since moved twice. The review's own rule still fires (capture is under 50% on every
reading), so **#668 stands**; what changes is what #668 must investigate.

MEASURE-ONLY, $0, read-only. Nothing proposed, nothing changed.

⚠ **This doc was corrected the same day it was written.** The first version reported **35.6% against
a 34% baseline** and concluded "capture did not move." Two things were wrong with that and both are
below: the 35.6% was the wrong twin of the baseline, and the comparison spanned an era boundary.

## Population — declared before the first measuring query

| | |
|---|---|
| **Cohort** | distinct MAGNA53 **HIGH** alerts, post-P7.2-ship (`alert_date >= 2026-05-18`), bounded to a **MATURE 21-day forward window** (`alert_date <= CURRENT_DATE - 21`) — the bound the review's own entry demands, because the script's rolling `CURRENT_DATE - 60` right-censors |
| **Subject** | the **failed-Day-1** subset: the alert did not become a winning Day-1 trade |
| **Capture** | picked up within 21 days by **any** downstream lane — a flag stage (WATCH/TIGHTENING/COILED/TRIGGERED), a later HIGH/MODERATE EP alert, a 9M EP alert, or a 9M Day-2 candidate. All four legs, matching the baseline's definition |
| **Window** | 2026-05-18 → 2026-08-27 (the last date with a matured 21-day window) |
| **Bar data** | 236 of 236 failed-Day-1 names have both a gap-day open and a 21-day forward high — **no coverage gap**, so the alpha filter below excludes nobody for missing data |

## Correction one — the baseline has two twins and I compared against the wrong one

`ep_delayed_capture_audit.py` produces **two** rates, and the source doc
(`analysis/2026-05-16/delayed_ep_audit.md`) records both:

| measure | denominator | pre-ship baseline |
|---|---|---|
| **ANY downstream pickup** | every failed-Day-1 name | **33.0%** (37/112) |
| **alpha capture** | failed-Day-1 names that *also* ran **+5% over gap-day open within 21d** | **34.2%** (26/76) |

The review's question and its 60–70% target are written against the **alpha** rate. The 2026-08-11
read of **51.0%** is the alpha rate. My first read of **35.6%** was the all-failed rate — so
"35.6% vs 34%" put the all-failed number next to the alpha baseline. The two happen to sit close
(33.0 vs 34.2), so the arithmetic was not far off; the *comparison* was not the one the review asks
for. [[prove-two-numbers-measure-the-same-thing]]

**The 51.0% reproduces exactly** under today's corrected live-preferring join — 104 alpha names, 53
captured — which is the evidence that the instrument itself is sound and the two reads measure the
same thing once the denominators are matched.

| measure | pre-ship baseline | 08-11 window (05-18→07-21) | today (05-18→08-27) |
|---|---|---|---|
| alpha capture | 34.2% | **51.0%** (53/104) | **39.4%** (65/165) |
| any downstream pickup | 33.0% | 44.6% (66/148) | 35.2% (83/236) |

Read naively that is a rise and then a fall. It is neither.

## Correction two — the flag board's promotion bar moved on 2026-06-26, mid-window

`mi_flag_candidates` keeps scanning the same universe every day — ~550 names, 20–23 scan days a
month, no gap. What changed is how many of them get **promoted** past `unqualified`:

| scan month | universe rows | WATCH-or-better | share |
|---|---|---|---|
| May | 12,005 | 2,882 | 24.0% |
| June | 14,061 | 2,451 | 17.4% |
| **July** | 12,518 | **215** | **1.7%** |
| August | 11,619 | 196 | 1.7% |
| September (to 09-16) | 5,945 | 108 | 1.8% |

The step is a single day — **2026-06-25 → 06-26, 18.0% → 2.6%**, on an unchanged universe (589 → 572
names). That is commit `932dc066`, *"#356 HTF Phase 1+2: swap flag_detector criteria to the sourced
spec (replaces the n=1 50/60)"*. **It is a signed, deliberate tightening, not a defect** — the whole
point of #356 was to stop reading a bar derived from one example.

⚠ **Mechanism corrected 2026-09-17; the boundary is unaffected.** Scan date 06-26 was not a live
session under the new criteria — the writer upserts (`db.py:7543`, `ON CONFLICT … DO UPDATE SET …
stage, reason, …`) and does not touch `created_at`, so a re-scan 33 minutes after the swap was
committed rewrote that day's rows in place. The first *live* scan under the swap is Mon 06-29. The
split used here is unaffected: stored rows from 06-26 onward carry the new criteria either way, and
the capture legs read stored rows.

## Result — split at the era boundary, which is the only honest way to read it

Alpha capture, all four legs, split at 2026-06-26:

| flag-criteria era | window | alpha n | captured | alpha capture |
|---|---|---|---|---|
| **PRE-swap** (old n=1 50/60 spec) | 05-18 → 06-24 | 96 | 51 | **53.1%** |
| **POST-swap** (sourced HTF spec) | 06-30 → 08-27 | 69 | 14 | **20.3%** |

And which leg did the work:

| era | alpha n | flag | later EP | 9M EP | 9M Day-2 | **flag ONLY** |
|---|---|---|---|---|---|---|
| PRE-swap | 96 | 49 | 5 | 3 | 1 | **44** |
| POST-swap | 69 | 6 | 1 | 7 | 1 | **6** |

⚠ **The PRE row needed the same test I only applied to POST.** POST is bounded to `alert_date >=
06-26` so its whole 21-day forward window is post-swap; PRE was not, so alerts from ~06-05 onward
reach across the boundary and understate PRE. Re-ran the strictly clean PRE cohort
(`alert_date <= 2026-06-04`): **43 of 81 = 53.1% — identical.** Checked, not assumed.

> **86% of the pre-swap captures (44 of 51) were the flag board and nothing else** — and the great
> majority at the loose `WATCH` stage. So "alpha capture" in this window was very largely a readout of
> **how many names the flag board admitted**. When #356 raised that bar by roughly 10×, the capture
> number fell by roughly the same factor. The measure did not detect a degradation; it inherited one
> definition change.

## What this changes for #668

- **Cause (b) is no longer a candidate — it is measured and it is dominant.** #668 listed "the flag
  detector is starved" as one of three possibilities. The era split above prices it: the flag leg
  carried 86% of pre-swap captures and 43% of the far smaller post-swap set.
- **The remaining question is (a) versus (c), against a POST-SWAP baseline of 20.3%** — not against
  34%, which was measured on a detector that no longer exists.
- 🛑 **The 60–70% target now points at loosening the HTF spec, and that is THE LINE.** On the current
  detector the target is unreachable without re-widening flag promotion — i.e. partially undoing
  #356. Whether the target survives is the operator's call, not an analysis output.
  [[recommend-against-the-goal-not-the-test]]

## What this does not answer

- **Capture is a REACH measure, not a money measure.** It counts whether a downstream lane picked the
  name up, never whether that pickup was tradeable. 60–70% of *noise* would be worse than 20% of
  substance — and this window is the proof, since the old 53% was mostly loose WATCH flags.
- ⚠ **There is still no usable PRE-ship comparison.** Filtering to `alert_date < 2026-05-18` with the
  maturity bound leaves **five trading days** (05-11 → 05-15, n=62) reading 58.1%: one week against
  three months. The 34.2% is carried from the original Phase 7 read as a stated number, not
  re-derived — its raw rows were purged at 90 days.
- **Whether 20.3% is the new steady state.** The post-swap window is 69 alpha names over nine weeks.
  It is enough to show the break; it is not yet enough to call a level.
- **The 9M half of the review's action is dropped deliberately, not silently.** It asked for the
  flag-stage distribution of 9M-origin names; 9M is retired. Its detection tables still write (646
  `mi_9m_ep_alerts` rows since 05-18), so those capture legs ARE counted above.

## The instrument defect found today — the audit joins to an account that stopped writing

`scripts/ep_delayed_capture_audit.py` classifies Day-1 outcome with
`lt.account_mode = 'paper'`. **Paper has written nothing since 2026-07-14**; live carries 120 rows
since the 2026-06-22 cutover. So for every alert after mid-July the join finds nothing and the name
falls to `NO_TRADE_ROW` — *whatever actually happened to it.* The cohort this review is about is
exactly the one that misclassification destroys.

This is the operator's own 2026-07-30 correction in a different file — *"why looking at paper? we've
switched to real money a month ago"* — and it is why every number above comes from a corrected query
that prefers the live row and falls back to paper. **The script is fixed**, so the next run agrees.

## Queries

`p74_alpha2.sql` (the two-twin bridge), `p74_flag.sql` (the promotion collapse), `p74_era.sql` (the
era split and per-leg attribution). All read-only, run against prod 2026-09-16.
