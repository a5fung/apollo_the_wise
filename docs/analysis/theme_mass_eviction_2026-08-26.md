# Tonight's 24 cooldowns are ONE theme with the wrong name — third cycle in ten days (2026-08-26)

**MEASUREMENT ONLY. No threshold, criterion, toggle or rule is changed or proposed as done —
theme criteria and cooldowns are the operator's sole authority (THE LINE). $0 — prod read-only
via `psql` over ssh, no LLM calls, no paid data. `mi_theme_exclusions` was not touched and must
never be auto-populated.**

## Answer

- **One theme, not many.** 17 of the 24 are `Oil Refining & Marketing`. The remaining 7 are one
  removal each from 7 unrelated themes — ordinary daily validation at normal volume.
- **Yes, it is the #214 class.** The engine's own tripwire fired at 17:03:51 ET:
  `validation_mass_removal_name_suspect` — *"'Oil Refining & Marketing': validation flagged
  17/24 members — name likely narrower than the cluster (#214)"*. It also satisfies
  `health_checks._is_mass_eviction(17, 24)` (≥3 leavers and ≥50% of membership).
- **No alert or score that fired was changed — but three names now score 10 points lower for 14
  days.** The stripped theme is **Nascent**, so its 17 never carried the R4 in-theme bonus, and
  none of the 24 has an EP alert in 30 days. However **NN, FLYW and WK** lost the +10 bonus purely
  from the strip and the 14-day cooldown blocks them from rejoining until **2026-09-09**. Detail in §5.
- **Cause: an energy cluster that keeps outliving its theme NAME.** Same signature fired
  2026-08-17 and 2026-08-19 on two predecessor names for the same block of stocks. The
  mismatch is **already re-armed** for the next validation run (Fri 08-28) on 46 members.
- **The companion L2 (`theme_count_active` 166) is a measurement artifact.** The real active
  set is 104 and has FALLEN this week (114 → 104). §4.

## 1. Which themes, which tickers

`mi_validation_cooldowns`, removals dated 2026-08-26 ET (24 rows, 8 themes):

| theme | n | tickers |
|---|---|---|
| **Oil Refining & Marketing** | **17** | AEP ATO CMS ET EVRG EXC FE KNTK OGS OKE PAGP SO SR TRGP UGI WES XEL |
| AI Chip & Interconnect Supply Chain Enablement | 1 | NN |
| Altcoin & Diversified Digital-Asset Infrastructure Second Wave | 1 | ASST |
| B2B Digital Financial Infrastructure & Payment Rails Modernization | 1 | FLYW |
| Corporate Spend, Expense Management & Financial Operations Software | 1 | WK |
| Diabetes Management Devices (CGM, Insulin Pumps & Delivery) | 1 | MMED |
| Mobile App Platform & Advertising Monetization | 1 | BSP |
| Video & Streaming Content Distribution Rebound | 1 | PSKY |

- Every one of the 17 is a **regulated electric/gas utility** (AEP ATO CMS EVRG EXC FE OGS SO SR
  UGI XEL) or a **midstream operator** (ET KNTK OKE PAGP TRGP WES). None refines or markets
  petroleum products. **The removals were correct given the name.** The defect is the name —
  exactly the failure mode documented at `theme_engine.py:2768-2779`.
- BSP's removal left a 2-member theme, which dissolved via the ADR-0025 Arm-A path
  (`theme_dissolved_flagged_pair`, 17:03:24) — a separate, intended mechanism, not part of the strip.

## 2. The #214 signature and the ten-day loop

Three mass-removal tripwires in ten days, all on the same block of energy names under three
different theme names:

| date | theme name | flagged | what happened |
|---|---|---|---|
| 08-17 | Oilfield Equipment & Contract Drilling Services | 9/16 | theme Retired 08-18 |
| 08-19 | Independent Oil Refiners | **42/42** | **removals SKIPPED** — 0 survivors < `PRUNE_MIN_TICKERS`=2, so the guard at `theme_engine.py:2820` returned the list untouched (confirmed: **zero** `mi_validation_cooldowns` rows for this theme on 08-19); theme Retired 08-20 |
| 08-26 | Oil Refining & Marketing | 17/24 | 17 removed, cooldown to 09-09 |

Membership walk of `Oil Refining & Marketing` (`mi_themes`):

| date | stage | n | members |
|---|---|---|---|
| 08-21 | Nascent | 7 | MPC PSX VLO DK DINO PBF CVI — **seven genuine refiners; the name fit** |
| 08-24 | Nascent | 24 | +17 regulated utilities and midstream |
| 08-25 | Nascent | 24 | unchanged |
| 08-26 | Nascent | **46** | the 17 stripped at 17:03, then **refilled** with ~39 upstream E&P names (XOM CVX COP EOG OXY FANG DVN EQT SU CNQ …) |

**The loop:** a real ~40-name energy cluster exists in the tape. The merge/retire passes keep
killing whichever theme hosts it — `Oilfield Services & Drilling Equipment` (38 members on
08-25) was auto-retired today at 17:11 with `parent='(unknown)'`; `U.S. Oil & Gas E&P Rotation`
(39 members, Accelerating) was retired 08-25. Each drop makes those members uncovered, and
re-assignment pours them into whichever energy theme still exists — which currently carries a
narrow sub-industry name. Validation then correctly strips the mismatch on the next Mon/Wed/Fri
run, and the cycle repeats.

**It is re-armed now.** Today's 46-member list is majority upstream producers, which is again
not "Oil Refining & Marketing". The next validation run is **Friday 2026-08-28**.

Two smaller observations, filed not fixed:
- **OKE was re-added in the same run it was cooled down.** 16 of the 17 stayed out of today's
  snapshot; OKE is back in the 46. Validation ran 17:00–17:04, merges 17:10, assignment after —
  the cooldown set was read before the strip. `theme_engine.py:2856` says the 14-day cooldown
  exists so "the stock can't be re-assigned immediately". One occurrence, not systemic.
- **`split_applied` is a red herring for themes.** Those rows are the corporate stock-split
  ingest (`splits_ingest.py`) — *"AXTU 2026-08-24 10:1 — 77 bars overwritten"*. Theme splitting
  emits `theme_split`. The 08-24 spike to 15 has nothing to do with theme membership.

## 3. Not the prune path — and the `_rs_rising` defect is real but separate

**Mechanism separation (established, not assumed):**
- `ticker_revalidated_out` and `validation_cooldown_triggered` are emitted **only** from the LLM
  description-validation path (`theme_engine.py:2836-2860`). All 24 came from there.
- The RS-prune path emits `ticker_pruned` / `ticker_prune_held_rising` into the in-memory
  changelog only. **Neither has ever written a row to `mi_audit_log`** (all-time count: 0). So
  prune volume is not measurable from the audit log — I cannot claim prunes were "normal
  tonight", only that tonight's 24 did not come from that path.
- `health_checks._is_mass_eviction` (line 2073) excludes exactly this class from the
  prune-while-rising check, so the F3 signature was correctly silent on all 24.

**The BLDR hold-test claim — verified against prod, and it is worse than endpoint-blind in one
direction only:**

The 08-25 flag exists: `theme_member_pruned_while_rising` at 17:30 ET, with its own recorded
history, newest-first: `BLDR rs_now=10.0 hist=[10.0, 13.8, 25.7, 29.4, 29.2, 5.9]`.
`_rs_rising` is `len(hist) >= 4 and hist[0] > hist[-1]` (`theme_engine.py:2987`), so
`10.0 > 5.9` → **True**. The actual path over the window is **29 → 10, a collapse**; it reads
"rising" only because the oldest reading (5.9 on 08-18) happened to be a one-day trough.

Cross-checked against tonight's 24. Six of them would have been RS-prune candidates on their own
numbers, and **all six read "rising"** — none is an ignition:

| ticker | rs_now | 6-session history (newest → oldest) | prune candidate | `_rs_rising` |
|---|---|---|---|---|
| SO | 22.1 | 22.1, 23.9, 24.4, 11.9, 19.9, 15.9 | hard | True — yet DOWN over the last 3 sessions |
| EXC | 24.2 | 24.2, 22.9, 24.5, 13.3, 24.7, 14.6 | hard | True — sawtooth; the window max (24.7) is above today |
| AEP | 21.0 | 21.0, 18.6, 15.8, 10.8, 22.8, 16.4 | hard | True — same shape |
| CMS | 18.2 | 18.2, 17.7, 15.2, 9.8, 13.7, 10.5 | hard | True |
| ATO | 28.4 | 28.4, 24.2, 22.5, 15.8, 21.4, 15.6 | soft | True |
| FE | 27.9 | 27.9, 25.6, 23.4, 14.3, 21.7, 17.3 | soft | True |

**Direction the evidence points — one way only.** Every instance I have (BLDR plus these six)
shows the endpoint-only test calling **chop or collapse "rising"**. In the engine that means it
**HOLDS names that are not igniting**; in the health check it means **false prune-while-rising
flags** like BLDR. The opposite failure — missing a real ignition whose oldest reading happened
to be a spike — is possible by construction but I have **no instance of it in this data**, and
I am not claiming it.

None of the 24 was actually pruned, so the hold never acted on them. This is a standing defect
in a different mechanism, **not the cause of tonight**.

## 4. The companion L2 measures name churn, not theme count

`system_audit._today_active_themes` (line 233) is:

```sql
SELECT COUNT(DISTINCT name) FROM mi_themes
WHERE stage != 'Retired' AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
```

That counts **distinct names seen anywhere in a 7-day window**. It does not take the latest row
per name, so a theme that was renamed, merged away or dropped keeps counting for 7 more days —
unlike `db.get_active_themes`, which the engine and the EP scan actually use.

Reconstructed both ways:

| date | metric (7d distinct names) | actual live set (latest row per name, non-Retired) |
|---|---|---|
| 08-26 | **166** | **104** |
| 08-25 | 163 | 106 |
| 08-24 | 160 | 104 |
| 08-21 | 159 | 114 |
| 08-19 | 141 | 113 |
| 08-17 | 130 | 94 |
| 08-06 | 124 | 92 |

- Gap today = **62 stale names** still inside the window. That gap is precisely the merge/retire
  churn: 20 themes auto-retired 08-20, 13 on 08-21, 19 on 08-24, 7 on 08-25, 8 on 08-26.
- **Themes are not climbing this week — the live set fell 114 → 104.** Over the month there is a
  genuine, gentle rise (92 → 104).
- Incidental: that metric's SQL uses bare `CURRENT_DATE` (UTC) while its sibling
  `_today_cooldowns` is ET-anchored per the CLAUDE.md TIMESTAMPTZ rule. At the 17:30 ET job time
  the two agree; re-running it by hand after 8 PM ET shifts the window a day (it returns 152 now,
  not 166). Noted, not fixed.

**Both L2s are also inflated by baseline shape.** Validation only runs Mon/Wed/Fri
(`theme_engine.py:3126-3128`; the small Tue/Thu residue is the birth-time validator at
`theme_engine.py:6255`). A 30-day *daily* median therefore sits near the off-day floor of 2.
Measured against Mon/Wed/Fri days only over 45 days, the median is **5** and the prior max is
**13** — so tonight is about **5× the like-for-like median** and **~1.8× the prior peak**, not
12×. Still elevated; not 12× elevated. `cooldowns_per_day` has now fired L2 three times in ten
days (08-17, 08-21, 08-26) and `theme_count_active` four times (08-21, 08-24, 08-25, 08-26) —
this is a recurring alert on one cause, not a new event.

## 5. Money path — the link is live, tonight's strip did not exercise it

**Two live surfaces read theme membership:**

1. **EP score, R4 in-theme bonus — +10 points.** `ep_rubric.SCORE_WEIGHTS["theme_bonus"]`
   (`points: 10`, `default: 0`), applied at `ep_detector.py:1346`. The membership set is built
   once per scan from `get_active_themes(stale_after_days=7)` filtered to **Accelerating or
   Mainstream only** (`ep_detector.py:2757-2766`). `R4_THEME_BONUS_ENABLED` is unset on the prod
   container → **ON**.
2. **Shortlist pre-score ordering.** Theme membership is 10 of the 65-point composite that sorts
   candidates before the admission cap (`ep_rubric.SHORTLIST_WEIGHTS["theme_bonus"] = (10, 1)`;
   `ep_detector.py:2963`). The `ep_shortlist_prescore` toggle has **no override row** in
   `mi_safeguard_state` and `EP_SHORTLIST_PRESCORE_ENABLED` is unset → **ON**. So membership can
   change *which* names are examined first under a cap, not only their score.

**So a mass eviction CAN move a name's EP score by 10 points and CAN change shortlist order.**

**Nothing that alerted was affected — checked four ways:**

- `Oil Refining & Marketing` is **Nascent**. The bonus set only reads Accelerating/Mainstream, so
  the 17 never carried the bonus. Stripping them changed no score.
- **None of the 24 has an EP alert in the last 30 days.** Only ASST appears on any EP surface at
  all: `mi_ep_scan_log` on 08-20/08-21, filtered as "routine catalyst" at score 0 — before
  tonight, and it kept its bonus anyway (it is in `Corporate Digital Asset Treasury Vehicles`,
  Mainstream, so it in fact *gained* the bonus today).
- The last 10 days of live alerts (11 rows: UUUU BULL RARE SCSC MRNA MRVL TEM TWST AMLX ARGX
  CBRS) contain none of the 24. Only MRVL and TWST were in an active theme at all.
- No theme *gate* exists on the alert path: `mi_ep_alerts.theme_gated_tier` / `theme_gated_score`
  are never written by any code in `agents/`. Theme membership is a **scoring and ordering**
  input only.

**But a forward effect IS already banked — 3 names, cleanly attributable to the strip.**
Five of the 24 lost the R4 bonus today. Separating them:

| ticker | theme | theme stage today | attribution |
|---|---|---|---|
| **NN** | AI Chip & Interconnect Supply Chain Enablement | Mainstream (14 members) | **clean — the removal alone took the bonus** |
| **FLYW** | B2B Digital Financial Infrastructure & Payment Rails Modernization | Mainstream (11) | **clean** |
| **WK** | Corporate Spend, Expense Management & Financial Operations Software | Mainstream (5) | **clean** |
| BSP | Mobile App Platform & Advertising Monetization | **Retired** | confounded — theme dissolved (Arm A) |
| PSKY | Video & Streaming Content Distribution Rebound | **Fading** | confounded — stage change also removes the bonus |

None of the three is in any other Accelerating/Mainstream theme. Their 14-day cooldown runs to
**2026-09-09**, so if NN, FLYW or WK gaps in the next two weeks it scores **10 points lower**
than it would have, and sorts lower in the shortlist pre-score. That is the whole live exposure
from tonight: small, bounded, and time-limited — not a reason to act tonight, but it is not zero.

**The exposure that remains.** The 46-member `Oil Refining & Marketing` is Nascent today, but the
cluster it now actually holds (XOM CVX COP EOG OXY FANG …) is the kind that promotes to
Accelerating/Mainstream. If it promotes before the name is corrected, the next strip **would**
move real scores and real shortlist order. That is the argument for fixing the name loop — not
an argument that tonight was urgent.

## 6. What I could not determine

- **Whether RS-prune volume was normal tonight.** `ticker_pruned` and `ticker_prune_held_rising`
  are never persisted to `mi_audit_log` (all-time: 0 rows), so there is no record to count. Only
  the health-check reconstruction from `mi_themes` diffs sees prunes at all.
- **Whether the ~39 refill names arrived via re-assignment or via a merge absorption.** Today's
  auto-retire row for `Oilfield Services & Drilling Equipment` carries `parent='(unknown)'`, so
  the successor pointer does not name a destination. The membership overlap makes re-assignment
  the strong reading, but the audit trail does not state it.
- **Why the merge/retire passes keep killing the energy host theme.** That is upstream of this
  incident and would need its own read of the Pass-1/1.5 and Arm-B adjudication logs.
- **Why the theme engine ran TWICE on 08-18 and 08-19.** `theme_engine_funnel` has two rows on
  each of those dates (08-19 at 17:14 and 17:16; 08-18 at 17:08 and 17:14) and one row on every
  other day in the window. The duplicate runs are visible in the removals — SHAZ was validated
  out of the same theme three times on 08-19 (17:01:44, 17:04:16, 17:06:22) and HAPN twice. I
  could not establish the trigger. Two consequences worth knowing:
  - It plausibly accounts for the unexplained **42 → 36** membership drop on `Independent Oil
    Refiners` on 08-19, which the skipped-removals reading leaves open.
  - `mi_validation_cooldowns` **upserts** on (ticker, theme) — `removal_count` increments and
    `removed_at` is refreshed — so 8 `ticker_revalidated_out` events on 08-19 produced only 5
    cooldown rows. `cooldowns_per_day` therefore counts *distinct (ticker, theme) pairs touched
    today*, not removal events. Tonight the two agree (24 = 24, every row `removal_count` 1).

## 7. Forks for the operator — nothing proposed as done

1. **The name-vs-cluster loop.** It has fired three times in ten days and is re-armed for Friday
   08-28 on 46 members. Whether to route it into #215's gated validation-prompt lane, to add a
   rename-on-mass-flag rule, or to accept a strip every other run is the operator's call. No
   change made.
2. **`_rs_rising`'s endpoint-only test.** Evidence above points one way — it over-calls "rising".
   Any change is a detection-criterion change: CHANGE_PROCESS + sign-off + N≥10 backtest first.
3. **`theme_count_active`.** It will keep firing L2 while name churn is high, regardless of the
   true theme count, because it measures 7-day distinct names. Whether to leave it, re-point it
   at `get_active_themes` semantics, or re-baseline it is the operator's call.

## Provenance

Prod read-only, captured once and read many (`scripts/probes/`):
`_theme_evict_0826_capture.sql` → `_theme_evict_0826_out.txt` (17 queries),
`_theme_evict_0826_capture2.sql` → `_theme_evict_0826_out2.txt` (12 queries),
`_theme_evict_0826_out3.txt`, `_theme_evict_0826_out4.txt`, `_theme_evict_0826_out5.txt`.
Connection: `ssh apollo@87.99.134.162 → docker exec -i apollo-postgres psql -U apollo -d apollo`.
All date predicates ET-anchored via `(col AT TIME ZONE 'America/New_York')::date`.
No writes, no deploy, no code change.
