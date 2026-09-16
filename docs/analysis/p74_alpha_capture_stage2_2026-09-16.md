# Phase 7 Stage 2 — did the carryforward lift alpha capture? (2026-09-16)

**Answer first: no. Capture on failed-Day-1 MAGNA53 names is 35.6%, against a 34% baseline and a
60–70% target. The review's own rule — "if capture <50% at Day 21, file a followup investigation
before declaring Phase 7 complete" — fires.**

MEASURE-ONLY, $0, read-only. Nothing proposed, nothing changed.

## Population — declared before the first measuring query

| | |
|---|---|
| **Cohort** | distinct MAGNA53 **HIGH** alerts, post-P7.2-ship (`alert_date >= 2026-05-18`), bounded to a **MATURE 21-day forward window** (`alert_date <= CURRENT_DATE - 21`) — the bound the review's own entry demands, because the script's rolling `CURRENT_DATE - 60` right-censors |
| **Subject** | the **failed-Day-1** subset: the alert did not become a winning Day-1 trade |
| **Capture** | picked up within 21 days by **any** downstream lane — a flag stage (WATCH/TIGHTENING/COILED/TRIGGERED), a later HIGH/MODERATE EP alert, a 9M EP alert, or a 9M Day-2 candidate. All four legs, matching the baseline's definition |
| **Window** | 2026-05-18 → 2026-08-21 (the last date with a matured 21-day window) |

⚠ **I DID NOT RUN THE SCRIPT VANILLA, AND THE ENTRY SAID NOT TO.** Two reasons, one already known
and one found today.

## 🔴 The instrument defect found today — the audit joins to an account that stopped writing

`scripts/ep_delayed_capture_audit.py` classifies Day-1 outcome with
`lt.account_mode = 'paper'`. **Paper has written nothing since 2026-07-14**; live carries 120 rows
since the 2026-06-22 cutover. So for every alert after mid-July the join finds nothing and the name
falls to `NO_TRADE_ROW` — *whatever actually happened to it.* The cohort this review is about is
exactly the one that misclassification destroys.

This is the operator's own 2026-07-30 correction in a different file — *"why looking at paper? we've
switched to real money a month ago"* — and it is why the numbers below come from a corrected query
that prefers the live row and falls back to paper. **The script is fixed in the same commit**, so the
next run agrees.

## The result

| cohort | n | captured | rate |
|---|---|---|---|
| **failed Day 1, all classes** (lost, no-entry, no-trade-row) | 233 | 83 | **35.6%** |
| failed Day 1, **tried and failed only** (excludes no-trade-row) | 133 | 43 | **32.3%** |
| won Day 1 (context) | 8 | 6 | 75.0% |

> **Baseline 34%. Target 60–70%. Both readings land on the baseline.** Whatever the carryforward is
> doing, it is not moving this number — and the narrower cohort, which is the cleaner subject, is
> slightly *below* the baseline rather than above it.

## What this does not answer

- ⚠ **There is no usable PRE-ship comparison, and the one the data offers is a trap.** Filtering the
  same query to `alert_date < 2026-05-18` with the maturity bound leaves **five trading days**
  (2026-05-11 → 05-15, n=62) reading 58.1%. That is not a baseline — it is one week against three
  months, and reporting "58% → 36%" as a regression would be a population error, not a finding. The
  34% figure comes from the original Phase 7 read and is carried forward as a stated number, not
  re-derived here.
- **Capture is a REACH measure, not a money measure.** It counts whether a downstream lane picked the
  name up, never whether that pickup was tradeable or profitable. A rate of 60–70% of *noise* would
  be worse than 35% of substance, and nothing here distinguishes them.
- **The 9M half of the review's action is not answered and is not pursued.** It asked for the
  flag-stage distribution of 9M-origin names; 9M is a retired setup. Its detection tables are still
  writing (646 `mi_9m_ep_alerts` rows since 05-18, last 09-08), so their capture legs are live data
  and are *included* above — but "did 9M-origin names progress through flag stages" is a question
  about a lane we no longer trade, and it is dropped deliberately rather than silently.
- **Why capture is low is untouched.** Low reach could be the carryforward not firing, the flag
  detector being starved (see #610's 91% collapse), or these names genuinely not basing. This read
  cannot separate those, which is exactly what the followup is for.
