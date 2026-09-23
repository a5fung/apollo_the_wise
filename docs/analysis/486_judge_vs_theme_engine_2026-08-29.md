# #486 — Judge vs theme engine: where they disagree, and which one is right

**Date:** 2026-08-29 (PT) · **Task:** #486 · **Status:** the DoD readout. Read-only, $0, no
behaviour changed. Scoring changes = THE LINE and are not proposed here.

**Population:** 327 EP alerts carrying `fire_axes` (so the judge adjudicated the theme axis),
2026-03-24 → 2026-08-28. Our engine's read = `mi_ep_alerts.in_active_theme`; the judge's =
`'theme' ∈ fire_axes`; theme context from `mi_theme_axis_shadow` + `mi_themes`; outcomes from
`mi_ep_scan_outcomes.fwd_5d_pct` (**maximum favourable excursion over 5 sessions — not a
return, and not R**; group averages compare, win rates on it are meaningless).

---

## 1. The agreement readout

|  | judge: theme | judge: no theme |
|---|---|---|
| **engine: theme** | 15 | 8 |
| **engine: no theme** | **51** | 253 |

- **They agree on 82%** of alerts.
- **The engine is three times more restrictive:** it flags a theme on **7.0%** of alerts, the
  judge on **20.2%**.
- Nearly all the disagreement is one-directional — **51 of the 59 mismatches are the judge
  seeing a theme we did not.**

## 2. Whose theme read tracks the better names

| who saw a theme | n | avg 5-day best move | median |
|---|---|---|---|
| both | 15 | **16.8%** | 8.8% |
| **judge only** | 51 | **12.2%** | 9.4% |
| neither | 253 | 10.6% | 7.0% |
| **engine only** | 8 | **7.6%** | 3.1% |

**Ranked by outcome the judge's read is the better one.** Both-agree is the strongest cohort;
judge-only beats neither; and **engine-only is the weakest cohort in the table** — the eight
alerts where our engine credited a theme the judge declined ran less far than alerts with no
theme at all. Small n (8), so this is a flag rather than a finding.

## 3. Why the engine missed 51 themes — the split that matters

| cause | n | avg best 5d |
|---|---|---|
| **no theme row at all** — genuine coverage gap | **27** | 13.0% |
| we HAD the theme, excluded because stage = **Fading** | 12 | 12.5% |
| we HAD the theme, excluded because stage = **Nascent** | 7 | 13.3% |
| shadow says active, live flag says no | 5 | 5.0% |

**Two-thirds of the "misses" are not coverage failures.** 19 of 51 are names whose theme we
knew about and deliberately excluded, because `in_active_theme` counts only
`Accelerating`/`Mainstream` (`ep_detector` ~:2897). Both excluded stages ran *above* the
population average.

### ⚠ The fourth row is NOT a defect — I first read it as one

Those 5 looked like a flag bug: our own shadow recorded the theme as Mainstream/Accelerating
while `in_active_theme` said false. Checking each, the ticker was **not a member on the alert
date** — the shadow had reached back to an older snapshot. That is documented behaviour:
`db.get_theme_heat_asof`'s docstring says the default *"has NO recency floor — a stale
non-Retired theme row still counts, which can disagree with the live credit path's 7d-bounded
`get_theme_membership`."*

**Measured, over the 107 shadow rows carrying a theme:**

| snapshot age used by the shadow | rows |
|---|---|
| same day | 60 |
| 1–7 days | 12 |
| 8–30 days | 20 |
| **over 30 days** (avg 64) | **15** |

**A third of the shadow's theme attributions are staler than the live path would accept**, and
the worst reach back two months. `in_active_theme=false` was right in all five cases; the
instrument was wrong. **This contaminates the mismatch counts above and is the first thing to
fix in this task** — the shadow should record both reads, bounded and unbounded, so a
cross-validation is not comparing two different definitions of "themed".

## 4. The operator's Fading-dip class, measured

His 2026-08-27 case (CRWD: theme Fading 08-25/26, Mainstream again 08-27, the alert day) asked
whether a dip should cost the bonus. Across the 12 Fading-at-alert misses, **only 3 had the
theme back to Accelerating/Mainstream within 5 days.** So CRWD is roughly a **1-in-4** case, not
the norm — a Fading theme usually stays faded. Any "credit a recently-Mainstream Fading theme"
proposal has to price that 3-in-12, not argue from CRWD alone.

## 5. The engine-improvement candidate queue

The 27 alerts where the judge lit a theme and we had **no theme row at all** — the real coverage
gap. Top by forward move:

| date | ticker | best 5d |
|---|---|---|
| 2026-06-12 | SHAZ | +56.4% |
| 2026-06-16 | RXT | +38.5% |
| 2026-08-04 | VOYG | +32.3% |
| 2026-08-12 | EROC | +28.4% |
| 2026-05-18 | SHAZ | +20.5% |
| 2026-05-28 | SNOW | +19.1% |
| 2026-08-10 | ACHR | +16.5% |
| 2026-07-31 | FLNC | +13.7% |
| 2026-05-13 | NBIS | +12.8% |
| 2026-05-12 | AMBQ | +11.1% |

All HIGH-tier. SHAZ appears twice, a month apart — a repeat coverage hole rather than a one-off.
This queue feeds #467/#322/#235.

---

## What this does not answer

- **Whether the judge is RIGHT** — it is another model, not ground truth. This measures that its
  theme read correlates with larger forward moves, not that its reasoning is sound.
- **MFE is not R.** No entry, no stop. These rank how far names ran, nothing more.
- **Nothing about causation.** A theme credit of 10 points does not obviously explain a 2-point
  gap in average excursion; the cohorts differ in other ways this cut does not control for.
- **The instrument problem in §3 caps confidence in the exact counts** — direction is safe, the
  precise 51/27/19 split is not, until the shadow records both reads.
