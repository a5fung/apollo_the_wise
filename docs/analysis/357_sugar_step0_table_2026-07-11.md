# #357 STEP-0 — sugar-baby membership as a forward-return signal (Lane-1 pre-build, 2026-07-11)

**Question (the #357 role decision):** is persistent-Sugar-Baby membership a *confluence axis* —
does an EP HIGH alert on a name that is ALREADY a sugar-baby member run better than one that isn't?
Design: `docs/analysis/357_sugar_babies_role_memo.md` §2 (branch A). Read-only; membership is
taken **as-of the alert date** (`cohort_date ≤ alert_date`) — no lookahead.

## The table

EP HIGH alerts since 2026-03-16, forward metric = 5d-max-high % from the alert-day close;
winner = ≥ +10%.

| cohort | N (alerts) | distinct names | settled | mean fwd-max | median | win ≥10% |
|---|---|---|---|---|---|---|
| **sugar-baby member (as-of alert)** | 11 | **9** | 10 | **+17.5%** | **+11.6%** | **80%** |
| non-member | 484 | — | 483 | +12.5% | +7.4% | 40% |

## The read

- **Direction confirmed (branch A):** a HIGH alert on an already-member name wins 80% vs 40%
  (median +11.6% vs +7.4%). The 11 member-alerts are **9 distinct names** (only RCAT and MRVL
  doubled) — so this is a genuine cross-sectional signal, not one or two names' behavior. The
  separation is on par with / wider than the theme axis itself.
- **But 11 member-alerts is BELOW the memo's Stage-2 gate (N≥15).** The direction is clear across 9
  names; the *magnitude* isn't yet stable enough to hard-wire an axis credit. +4 more member-alerts
  settle it.

## Recommendation for the sitting

- **Ship Stage-1 (visibility) now:** surface "⭐ sugar-baby member" as a badge on EP alerts + in
  `/setup` — zero money-path change, pure operator-facing context. No gate needed.
- **Hold Stage-2 (the axis credit) until N≥15 members**, then re-run this exact probe; if the 80%
  vs 40% holds, wire the credit through the #332 setup-class rubric (not a bespoke bump).
- **Caveat (honesty):** forward-max is an upper bound (no stop, perfect exit). The *relative*
  separation (member vs non-member, same metric) is the signal — both cohorts are measured
  identically, so the 2× win-rate gap is real; the absolute +17.5% is not a tradeable R.

*Probe: the STEP-0 join above (committable as `scripts/probes/_357_sugar_step0.sql`). Feeds
#357 role decision + the #332 rubric.*
