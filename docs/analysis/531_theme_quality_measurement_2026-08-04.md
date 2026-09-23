# #531 — nightly THEME QUALITY check: measurement, hand-checks, both-ways proof (2026-08-04)

**Operator's ask (2026-08-04, verbatim):** *"i'm really asking for quality checks regularly to make
sure our themes are solid without me needing to check it and review manually."* He should learn a
theme defect from a Telegram, not from an investigation — which is exactly how `#368` itself was
found (5 of 9 theme-credit false positives traced to one mechanism nobody was watching for).

**Ship decision: 2 of 4 candidate signatures shipped.** Both survive being proven both ways on real
data. The other two were measured and DROPPED — a good outcome, not a shortfall.

| Signature | Firings measured | Shipped? |
|---|---|---|
| A — theme retired while healthy | 6 / 165 distinct retirement incidents | **SHIPPED** |
| B — member pruned while RS rising | 25 / 164 prune-shaped exits | **SHIPPED** |
| C — fragmentation (theme overlap) | 251 day-level firings / 122 distinct pairs | DROPPED |
| D — churn (short-lived themes) | 42 / 301 distinct names | DROPPED |

Data: `mi_themes` full history captured once via read-only ssh (`docker exec apollo-postgres psql`),
2026-03-19 → 2026-08-04, 4,169 rows / 97 distinct trading days. `mi_stock_scores.rs_composite` for
every ticker that ever appeared in a theme over that window, 69,901 rows. `mi_audit_log` events
`theme_retired` / `theme_auto_retired` / `theme_dissolved_flagged_pair`, last 150 days, 415 rows.
Captured once to local TSVs and replayed locally — $0, no API calls, per the cost-efficiency rule.

## Signature A — "a theme retired while healthy" (the #368/F2 regression guard)

**Verified prod case (the DoD):** `Bitcoin Mining & Crypto Infrastructure Operators` sat Fading with
`rs_avg` 84.9 on 2026-08-03 — healthy — and had NO row at all (any stage) on 2026-08-04. Confirmed
live via `mi_audit_log`: a `theme_retired` audit event fired 2026-08-04 21:03:35 UTC (17:03 ET,
three minutes after `nightly_data_pull`), but no corresponding `mi_themes` row exists for that date
— a genuine silent vanish, not an explicit `stage='Retired'` row.

### Method

`theme_retired` audit events (Step 1's natural per-run retirement diff) turned out to **re-fire
daily for up to ~7 days** while a retired name lingers inside `existing`'s recency window before
finally aging out — discovered during this measurement, not previously documented. Raw count: 314
events collapsed to **165 distinct incidents** (clustered by name, >7-day gap = a new incident,
keyed on the FIRST occurrence).

For each incident, looked up the theme's `mi_themes` history strictly BEFORE the retirement date.
Two measurement bugs were found and fixed before trusting the number — both worth stating, since a
guard built on a buggy measurement is not a guard:

1. **`theme_date <= retirement_date` instead of `<`** double-counted a coincidental SAME-NAME
   rediscovery born in the identical nightly run as the old instance's retirement. Example:
   `Precious Metals Royalty & Streaming Companies` retired 2026-08-03 (a 2-ticker Fading sub-theme,
   FNV+RGLD, declining rs_avg=None) in the SAME run a brand-new 4-ticker Nascent theme with the
   IDENTICAL Haiku-generated name was born (FNV,RGLD,WPM,OR, rs_avg=32.2) — the `<=` lookup grabbed
   the new theme's same-day row and misread it as the old theme's "healthy" state. Fixed by
   requiring the lookup strictly before the retirement date. Same bug hit `Commercial Real Estate
   Brokerage & Advisory Services` (2026-07-16).
2. The daily re-fire (above) made an un-clustered incident count meaningless (314 raw firings for
   ~90-110 genuine retirement events) — fixed by clustering and keying dedupe on theme NAME alone,
   never name+date (a persisting condition must not re-alert nightly).

### Result: 165 incidents → 6 fired

Of the 165 clustered incidents, **129 carry an explicit same-day `mi_themes` Retired row** — a
DIFFERENT, legitimate mechanism (ADR-0025 Arm-A 2-member dissolve on a validation-flagged member, or
Pass1/1.5 engine-drop consolidation) that #368/F2 does not touch. Hand-verified three of these:
`Heavy Transportation Equipment Manufacturers` (WAB+PCAR, 2 members), `Casual Dining Restaurant
Turnaround` (CBRL+EAT, 2 members — dissolved the same night `Casual Dining & Full-Service Restaurant
Chain Recovery` was born from the survivor EAT), `Specialty Pharma — Rare Disease & Cardiopulmonary
Therapeutics` (KNSA+LQDA, 2 members) — all exactly 2-member themes with an explicit `stage='Retired'`
row, `score=0`, `rs_avg=None`, `tickers={}` written the same night: the validator correctly
dissolving a flagged pair, not a silent-death bug. **This check deliberately does not fire on them.**

Of the remaining silent vanishes, 6 had a healthy last-known state (Fading, `rs_avg` NOT NULL)
immediately before disappearing — every one hand-checked real:

| retired | name | prior date | prior rs_avg |
|---|---|---|---|
| 2026-04-21 | Single-Cell Genomics & Spatial Biology Instrumentation | 04-20 | 88.0 |
| 2026-04-29 | Lithium & Battery Critical Minerals Mining | 04-28 | 93.8 |
| 2026-05-06 | Workforce Solutions & Technical Staffing Services | 05-05 | 80.3 |
| 2026-05-12 | Precision Frequency & Timing Defense Electronics | 05-11 | 80.2 |
| 2026-05-15 | Chip Architecture Licensing & CPU/GPU Compute Revival | 05-14 | 82.8 |
| 2026-08-04 | **Bitcoin Mining & Crypto Infrastructure Operators** | 08-03 | 84.9 |

**6/165 = a clean, low-noise signal.** Every firing is the same shape: a Fading row that still
cleared the strong-member floor (the "held"/score-delta-fade branch), wrongly counted toward the
5-day retire streak — exactly what F2 fixes.

### A named, deliberate exclusion (not left to live only in reasoning)

A SEPARATE, different class — a healthy Fading theme dropped via the Pass1/1.5 **engine-drop** path
(explicit same-day Retired row, but the row that PRECEDES it was Fading with `rs_avg` populated) —
was seen **4 times** in the same window: `Optical Components & Transceiver Manufacturers` (06-12,
prior rs_avg 72.4), `Insurance Brokerage & Risk Advisory` (07-09, 81.7), `AI Memory & Storage`
(07-13, 95.4 — a legitimately elite theme), `Automotive Electronics & Sensor Components` (07-15,
85.5). **F2 does not fix this** — the engine-drop path never reaches `_count_consecutive_fading` at
all, so alerting it under signature A would point at the wrong remediation. Filed here as a known,
measured gap for a future signature, not silently dropped.

### Both-ways proof

**Fires** on the real bad case:
```
retired=2026-08-04  name='Bitcoin Mining & Crypto Infrastructure Operators'
  prior=2026-08-03  stage=Fading  rs_avg=84.9  score=72.5
```
**Silent** on the correct/weak shape (same mechanism, healthy retirement):
```
retired=2026-04-14  name='Crypto Recovery'
  prior=2026-03-31  stage=Retired  rs_avg=None  score=0.0
```
**Silent** on the Arm-A dissolve false positive found during measurement:
```
retired=2026-07-27  name='Heavy Transportation Equipment Manufacturers'
  same-day row: 2026-07-27  stage=Retired  rs_avg=None  score=0  tickers={}
  (prior, 07-24: Nascent, rs_avg=93.8 — would have been a false positive without the
   same-day-row exclusion)
```

**Live dry run (2026-08-04, run against real prod data through the actual shipped function):** of
the 9 theme names with a `theme_retired` audit event in the [08-03, 08-04] window, exactly ONE
fired — `Bitcoin Mining & Crypto Infrastructure Operators` — matching the verified case exactly. The
other 8 were correctly silent: 2 explicit same-day Retired rows (excluded via the same-day check), 5
whose "prior" row was itself an explicit Retired row from the day before (stage != Fading, excluded),
1 that turned out to still be alive today (re-fired its audit event but never actually vanished).

**Caveat for the operator:** F2 is committed locally but **not yet deployed** to production (the
live containers still run the pre-fix code). The first live run of this check WILL alert on the
2026-08-04 Bitcoin Mining retirement — that is a correct, working alert on a real defect the fix
hasn't reached production for yet, not a broken new guard.

## Signature B — "a member pruned while its RS was rising" (the #368/F3 regression guard)

**Verified prod case:** IREN (RS 10.7) and APLD (RS 10.3) pruned from `AI Compute & GPU Data Center
Hosting Operators` on 2026-07-22 — day 2 of their ignition — while both were rising. F3's
`ticker_prune_held_rising` hold exists specifically to catch and HOLD these instead of pruning them.

### Method

Mirrors the ENGINE'S OWN exact prune-candidacy gate (not just "RS < 35", which a first pass used and
which the advisor flagged as a false-positive risk): `PRUNE_RS_HARD=25` is a candidate on any day;
`PRUNE_RS_HARD <= rs < PRUNE_RS_SOFT=35` is a candidate ONLY on the 3rd consecutive sub-floor day;
`rs >= 35` was never a candidate at all. Excludes (a) **#214 mass-evictions** (>=3 leavers AND >=50%
of the theme's membership gone at once — a validation strip, not a daily prune) and (b) tickers that
**moved to another live theme the same night** (present in ANY theme on today's board — a
reassignment, not a prune; this exclusion was added after the advisor caught that the first pass
didn't check it).

### Result: 164 prune-shaped exits, 25 rising

Of 164 genuine prune-candidate departures (excluding 290 mass-eviction leavers and 107 same-night
moves), **25 were rising** at exit — theme_engine's own `_rs_rising` (newest RS > oldest RS over the
last 6 sessions, >=4 points of history). Of the 14 with a full 10-session forward window:

| outcome | rising (N=14) | falling control (N=97) |
|---|---|---|
| recovered to RS>=50 | 11 (79%) | 35 (36%) |
| dead (<25) | 2 | 32 |
| limbo (25-50) | 1 | 30 |

**The 79%-vs-36% spread — not the raw firing count — is the evidence these are real defects, not
noise.** A rising exit recovers roughly twice as often as a falling one; the hold is catching
genuine early recoveries, exactly as F3's own pre-deploy backtest found independently (77% vs 31%,
`docs/analysis/368_crypto_ai_consolidation_2026-08-04.md`, N=13/25 — this measurement is an
independent replay with a slightly different exit-gate and moved-ticker exclusion; both land on the
same conclusion within a few points).

### Both-ways proof

**Fires** on the real bad case:
```
2026-07-22  IREN  RS 10.7  left 'AI Compute & GPU Data Center Hosting Operators'
  hist (newest→oldest, 6 sessions): [10.7, 7.4, 6.0, 1.5, 1.7, 2.4]
```
**Silent** on a falling control (the hold correctly still prunes these):
```
2026-06-29  STE-adjacent control:  newest(2.8) < oldest(3.7) over the 6-session window → falling,
  no flag.
```
**Silent** on a ticker that was never a prune candidate at all (rs_now >= 35, the bug the exact-gate
mirroring fix caught before shipping — an earlier pass without it would have false-fired here).

### Two implementation bugs found by review (before shipping) and their effect on the live dry run

An adversarial pre-ship review of the SHIPPED CODE (not the measurement script, which already had
both right) caught two divergences between what was measured and what would have run in
production — both worth stating because they change the live dry-run result below:

1. **Mass-eviction was being judged on the moved-filtered count, not all leavers.** The shipped
   `_check_pruned_while_rising` computed the >=3-leavers/>=50% mass-eviction test AFTER already
   dropping same-night moves — so a theme that split 17-of-18 members into two child themes (16
   moved, 1 straggler) would read as "1 of 18 gone," nowhere near the mass-eviction bar, and the
   straggler would be scored individually. Fixed: mass-eviction is now judged on ALL leavers
   first, moved-filter second — the theme is excluded WHOLESALE, straggler included, matching the
   measurement script's original (correct) order.
2. **`rs_now` was "most recent RS available," not "today's RS."** `get_recent_rs_batch` silently
   falls back to the nearest PRIOR date for a ticker missing today's row — right for a trajectory
   read, wrong for "is this ticker even in today's snapshot." A ticker absent from today's RS
   universe is `theme_engine.py`'s SEPARATE `missing_rs_tickers` branch, which prunes on plain
   5-day history and never consults `_rs_rising` at all — scoring it here would be a false analogy
   to what the engine actually does. Fixed with a dedicated exact-date query
   (`db.get_rs_on_date`); a ticker missing today's exact row is now skipped, not scored.

The 25/164 measured count above is unaffected (the measurement script always used the correct
order and the exact-date lookup — this was a shipped-code bug, not a measurement bug). Both are
pinned by dedicated regression tests (`test_mass_eviction_is_judged_on_all_leavers_not_the_moved_
filtered_count`, `test_a_ticker_absent_from_todays_exact_rs_snapshot_is_skipped_not_scored`).

**Live dry run (2026-08-04, run against the real 08-03→08-04 transition, through the CORRECTED
code):** 25 member departures after excluding same-night moves. `Gold & Precious Metals Miners
Rotation`'s 17-of-18 split (16 moved into `Junior Precious Metals Miners Rotation` / `Senior &
Mid-Tier Gold & Silver Miners`, HYMC not moved) is now excluded WHOLESALE by the corrected
mass-eviction order — HYMC no longer scores individually (it fired under the buggy pre-fix code;
confirmed the fix changes this exact live case). Of the remaining candidates, exactly **2** fire
tonight: **OKLO** (RS 3.1, hist `[3.1, 3.2, 1.4, 2.2, 1.7, 1.8]` — a noisy near-zero wobble that
still meets the strict `newest > oldest` rising test) and **WPM** (RS 25.9, hist `[25.9, 24.3,
15.3, 28.0, 22.8, 13.9]`). Since F3 is not yet deployed to prod, these WILL actually be pruned
tonight rather than held — the check is correctly identifying live instances of the still-active
bug, exactly as designed.

## Dropped: fragmentation (2+ live themes sharing heavy ticker overlap)

**Measured:** requiring >=50% of the smaller theme's members shared, same day: **251 day-level
firings across 122 distinct theme-name pairs** in the 97-day window — an order of magnitude too
broad to trust (a guard that always fires is not a guard).

**Why dropped, beyond the noise count:** the #368 diagnosis already identified the real
fragmentation signature precisely — *"zero crypto×AI pairs were EVER proposed for adjudication"*
(`theme_merge_arm`'s Stage-A family gap), not "two themes overlap." Overlap is Arm-B's normal INPUT
(the machinery that resolves it working as intended — most of the 122 pairs are semiconductor/
optical/agri-chem sub-industries that legitimately share a few names for a few days before the
nightly merge pass resolves them). An overlap-percentage alarm would fire on healthy operation and
require domain judgment ("same cohort, or two adjacent-but-distinct industries?") to separate real
fragmentation from coincidence — exactly what this check's own template (#521 inert-sweep) refuses
to do by design. The REAL check (pairs never proposed for adjudication) is F1's territory: built,
gated on a paid adjudication check, and WITHDRAWN 2026-08-04 (see
`docs/analysis/368_crypto_ai_consolidation_2026-08-04.md`'s correction), filed `#529`, gated on
`#471` (parent/child persistence not yet built). Building a parallel overlap alarm now would
duplicate work already scoped correctly elsewhere and would not be trustworthy on its own terms.

## Dropped: churn (a theme born-and-dead inside N days, repeatedly, in one neighbourhood)

**Measured:** 42 of 301 distinct theme names (14%) born-and-gone within 5 calendar days — mostly
normal Nascent mortality (a cluster that just didn't have legs), not evidence of a defect on its
own. The operator's "repeatedly, in the same neighbourhood" qualifier requires clustering
short-lived themes by ticker-overlap across MULTIPLE deaths — the same neighbourhood-identity
problem fragmentation has, and the same reason it isn't trustworthy to ship today without that
clustering work (which would need its own measurement pass, not a same-day addition).

## Suite / preflight

`python3 -m pytest tests/ -q` → 4379 passed, 7 skipped (baseline 4353 passed / 7 skipped + 26 new
tests in `tests/test_theme_quality_check.py`). `scripts/preflight_datetime_hygiene.py` and
`scripts/preflight_no_silent_failures.py` both green.
