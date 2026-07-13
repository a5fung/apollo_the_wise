# Theme-membership signal investigation (2026-07-13)

Triggered by the M1-d sizing doubt: the two theme-membership signals disagree ~3×, the sizing
window was theme-bug-polluted, and the operator asked whether EPs are missing theme assignments
they should have. All three run down below. **Nothing here changes code or strategy** — it
reframes the theme-axis priority for the operator (THE LINE).

## Part 1 — why `in_active_theme` (4%) ≠ `get_theme_membership` (12%): definitional, not a bug

- **`in_active_theme`** (ep_detector.py:1416-1424, the "R4 bonus" set): built from
  `get_active_themes(7d)` but keeps a ticker ONLY if its theme stage ∈ {Accelerating, Mainstream}
  (line 1422). Nascent + Fading are excluded by design.
- **`get_theme_membership`** (catalyst_rubric_runtime.py:411): `mi_themes WHERE stage != 'Retired'
  AND theme_date >= now-7d AND ticker = ANY(tickers)` — includes Nascent + Fading too.
- Same `tickers` source + same 7d window; the ONLY difference is the stage filter. So they answer
  different questions — `in_active_theme` = "in a HOT theme," `get_theme_membership` = "in any live
  theme." Neither is buggy. The frequent NULL `in_active_theme` values are pre-R4 (2026-05-17)
  vintage rows. **For M1-d, `get_theme_membership` (~12%) is the correct signal** — it is what
  `theme_axis_credit` actually consumes. My earlier "1/83 MODERATE" leaned on the narrow flag → too low.

## Part 3 — the sizing window was theme-bug-polluted (operator's caution, confirmed)

Weekly theme volume (`mi_themes`) shows a clear depression ~mid-May → late-June — the
`[Fading]`-echo silent theme-assignment drop (month-old, 15/27 runs, fixed 2026-06-10) plus a
6/15 trough; recovery ~6/29+:

| | Apr (healthy) | 6/15 (trough) | 7/06 (recovered) |
|---|---|---|---|
| distinct themes | 53–67 | 23 | 84 |
| ticker-slots | ~900–1026 | 243 | 1260 |
| Accelerating rows/wk | 39–69 | 4 | 34 |

Re-measuring the RELIABLE signal (shadow `get_theme_membership` stage, HIGH alerts) clean
(before 5/11 or after 6/24) vs polluted (5/11–6/24):

| period | HIGH rows | themed (any stage) | Accelerating |
|---|---|---|---|
| clean | 265 | **11.7%** | **4.5%** |
| polluted | 196 | **11.7%** | **2.0%** |

**Key:** overall membership held at 11.7% both periods — the bug shifted stage *labels*
(Accelerating→Fading), it did NOT drop membership. But it **halved the Accelerating rate**
(4.5%→2.0%), and Accelerating is M1-d's boost trigger. So my "1/quarter" was deflated twice: the
narrow flag AND the bug. Clean, ~4.5% of alerts are Accelerating-themed → a *few* boostable
MODERATEs per quarter, not one. (Still un-evidenceable at that N on a near horizon; still small.)

## Part 2 — YES: EPs routinely belong to a theme the engine doesn't track (operator's idea, quantified)

Clean-period HIGH alerts, engine membership × whether the judge independently lit a theme/narrative:

| engine tracks a theme? | judge lit theme? | count |
|---|---|---|
| yes | yes | 18 |
| **no** | **yes** | **22 ← blind spot** |
| no | no | 139 |
| judge silent | – | 81 |
| yes | no | 4 |

Of 40 alerts the judge flagged thematic, the engine tracked a cohort for only **18 — it missed 22
(55%)**. The blind-spot set is *larger* than the engine-agreed set. The code already names this
(`coverage_state='blind_spot'`, #319/#325). **This is the bigger theme-axis lever than M1-d**:
M1-d boosts the ~4.5% already-tracked-Accelerating; the blind-spot is ~8% of ALL alerts (and
~55% of judge-thematic ones) where the engine has no cohort at all.

## Synthesis — the theme-axis priority is the MEMBERSHIP layer, not the credit table

1. **M1-d (credit table) is a small lever** and can't be cleanly evidenced — keep the wire-in dark.
2. **The membership/coverage layer is the real gap:** the engine tracks only ~12% of EP alerts as
   themed and misses the majority of judge-thematic names. Fixing that would give the theme axis
   far more signal than tuning the credit on the few it already tracks.
3. **The hard part is doing it SAFELY (THE LINE):** closing the blind-spot by asking the JUDGE
   "is this thematic?" → assign → boost is the **circular discovery-feeder** carved out of v1
   (judge→discovery→engine→boost→"validated"; #167). The operator's 6/24 direction stands: theme
   RELEVANCE must be attributed by an INDEPENDENT mechanism (structural: catalyst named-entities ∩
   cohort tickers/keywords, or co-movement), never the judge's own theme read. `mi_theme_axis_shadow`
   already logs candidate independent signals (`matched_terms`, `co_moving`, `structural_attributable`)
   — the raw material for a safe blind-spot detector, but that detector is undesigned.

**Bottom line for the operator:** M1-d stays dark (small + un-evidenceable). The theme-axis
investment that would actually move the needle is a SAFE blind-spot detector (independent
attribution, not judge-circular) — a design question, not a credit-table tune. That is a keep/
shelve-and-redirect call (THE LINE).
