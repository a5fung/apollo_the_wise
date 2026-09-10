# The large-cap rel_volume floor would reject 95% of large-cap EP alerts — and the 5% it admits are simply the ones that alerted latest in the morning

**2026-09-09 · read-only · $0 · the `large_cap_relvol_floor_shadow_evidence` gate (ready since 2026-09-01, never run)**

## Method / population — which rows, over what window

- **Rows.** All **64** `filter:large_cap_relvol_floor_shadow` observations in `mi_audit_log`, spanning
  **2026-07-20 → 2026-09-08** — every large-cap (ADV$ ≥ $50M) HIGH EP alert the shadow observer has
  seen since it deployed. Joined to `mi_live_trades` on ticker + alert_date for outcomes.
- **Forward, not retrospective.** These are events emitted live by `_emit_large_cap_relvol_floor_shadow`
  in `ep_detector.py`, which is the whole point of the shadow: the retrospective read that motivated
  it (3/20 closed, 15% win rate) could not separate the artifact below.
- **Era.** No exit- or entry-rule change affects this — `rel_volume` is measured at ALERT time,
  before any entry decision, so the 09-06 exit flip is irrelevant to it.
- **Nothing is gated today.** The observer records; `LARGE_CAP_RELVOL_FLOOR` has never acted.

## Finding 1 — the floor rejects 95% of the population, and admits only late alerts

⚠ **CORRECTED 2026-09-09, same day.** The first version of this finding read *"64 of 64 below the
floor, highest ever 0.380, no large-cap alert has ever reached 0.5"* — **that was an artifact of the
shadow's own emit condition.** `_emit_large_cap_relvol_floor_shadow` (`ep_detector.py:2035`) returns
early on `rel_volume >= 0.5`, so a name above the floor never writes a row. Counting the recorded
rows and finding all of them below the floor proves nothing: **the population was defined by the
answer.** This is the same defect class as the eleven zero-reading gates ruled the same day — a
measurement that cannot come out the other way.

**Re-run against the real population** (`mi_ep_alerts` HIGH rows, large-cap reconstructed from the
prior session's `mi_stock_scores.adv_20 × close`, same 2026-07-20 → 09-08 window):

| | large-cap HIGH | all HIGH |
|---|---|---|
| alerts with rel_volume recorded | **62** | 109 |
| at or above the 0.5 floor | **3 (4.8%)** | 5 (4.6%) |
| highest rel_volume | **0.690** | 1.130 |

**The floor rejects 95% of large-cap EP alerts, not 100%** — the conclusion does not change, but the
supporting claim was false and is retracted. A gate that admits 3 names in 51 days is still an off
switch rather than a filter, and it still rejects the winners in this cohort (MRNA +$90.79, CRWD
+$14.40 both sit below it).

**The three that clear the floor are the whole of Finding 2 in three rows:**

| ticker | date | rel_volume | alert time ET | outcome |
|---|---|---|---|---|
| CRWV | 2026-08-12 | 0.690 | **09:50** | skipped |
| HAS | 2026-07-21 | 0.620 | **09:50** | skipped |
| ACHR | 2026-08-10 | 0.500 | **09:45** | skipped |

Every one alerted at **09:45–09:50 ET — the latest possible alert times** — and every one was
skipped as out-of-ORB (the submission window closes at 9:45). So the names the floor would admit are
exactly the names that had the most session volume to accumulate, and **not one of them was
tradeable anyway.**

## Finding 2 — rel_volume measures the clock, not participation

`rel_volume` is today's CUMULATIVE volume ÷ ADV. At 07:00 ET the numerator is a few pre-market
prints, so the ratio is near zero **however heavily the name is really trading**.

| alert window | n | mean rel_volume | median | below floor |
|---|---|---|---|---|
| pre-market (<09:00) | 46 | 0.033 | **0.020** | 46 |
| session (≥09:00) | 18 | 0.166 | **0.170** | 18 |

**The median is 8.5× higher in-session than pre-market on the same measure.** The candidate concern
recorded when this shadow was built — *"is <0.5 genuine thin participation, or just an artifact of
alerting early in the session"* — is answered: **it is the artifact.** A floor on this quantity
would gate on what time the alert fired.

⚠ **This also puts the retrospective evidence in doubt.** The 3/20 / 15%-win-rate finding that
motivated the floor compared `rel_volume < 0.5` against a `≥0.5` control. On the forward population
that control is **three names, all skipped, zero settled outcomes** — so there is nothing to compare
against, whatever it was measuring. (Corrected: the first version of this line said the control was
*empty*, which was the emit-condition artifact above.)

## Recommendation — do not ship, in any form, at any threshold on this metric

⚖ **This is an admission criterion, so it is the operator's call — but the call being asked for is
"ship a floor", and the answer is no. Not shipping is the status quo and needs no sign-off.**

- **Do not lower the threshold either.** Fitting a floor to a metric that tracks alert time would
  encode "alerts before 09:00 are worse", which is not what anyone intends to decide.
- **If the underlying hypothesis is worth keeping** — thin real participation predicts failure —
  it needs a **time-normalised** measure: cumulative volume against the name's own typical
  cumulative-volume curve *at that minute of the session*. That is a different build, not a
  threshold change.
- **Keep the observer running.** It costs nothing and it is what produced this answer.

## What this does not answer

- **It does not test the underlying hypothesis.** Thin participation may well predict failure; this
  says only that `rel_volume` as currently computed cannot measure it.
- **Outcomes are thin and one-sided.** 14 of the 64 reached `status='closed'`, and every one of
  those is a pre-market alert — there is no in-session settled contrast at all.
- **It does not re-run the retrospective analysis** that motivated the floor; it only shows that
  analysis's control group has three names and no settled outcomes on the forward population.
- **The shadow table alone can never answer "how often does a large cap clear the floor"** — its
  emit condition excludes exactly those rows. That question needs `mi_ep_alerts`, as used above.
- **ADV$ ≥ $50M is the only large-cap definition tested.** A different cut might behave differently,
  though the clock artifact would not change.
