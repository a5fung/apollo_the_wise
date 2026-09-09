# The large-cap rel_volume floor would reject 100% of its own population — and the metric tracks the clock, not participation

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

## Finding 1 — the floor rejects the entire population

| | |
|---|---|
| observations | **64** |
| below the proposed 0.5 floor | **64 (100%)** |
| highest rel_volume ever recorded | **0.380** |
| window | 51 days |

**No large-cap HIGH EP alert has ever reached rel_volume 0.5.** A floor at 0.5 is not a filter, it
is an off switch for large-cap EP. Any winner in that population — MRNA +$90.79 and CRWD +$14.40 are
in this very cohort — is rejected along with the losers.

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
motivated the floor compared `rel_volume < 0.5` against a `≥0.5` control. On this population that
control is **empty**, so whatever it was measuring, it was not the contrast it claimed.

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
  analysis's control group is empty on the forward population.
- **ADV$ ≥ $50M is the only large-cap definition tested.** A different cut might behave differently,
  though the clock artifact would not change.
