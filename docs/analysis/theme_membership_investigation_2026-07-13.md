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

Of 40 alerts the judge flagged thematic, the engine tracked a cohort for only 18 — the other **22
carry a judge-lit theme with no engine cohort** (`coverage_state='blind_spot'`, #319/#325).

**Two honest caveats that stop this from being a "bigger lever than M1-d" claim:**
- **These 22 are all HIGH** (`mi_theme_axis_shadow` is HIGH-gated). Correctly assigning them to
  themes tomorrow changes NO grade — `compose_final_tier(HIGH, +1)` clamps at HIGH. So the blind-spot
  is a **coverage-QUALITY** gap (better judge narrative axis / `/why` / future gating), **not** a
  grade lever that beats M1-d. It does not rescue M1-d — the MODERATE blind-spot, where a boost
  WOULD fire, is exactly the data we don't have.
- **"Missed 22" is JUDGE-asserted, not confirmed.** The metric uses the judge as the arbiter of
  "should be thematic" — the same circular signal the synthesis says not to trust. It's an UPPER
  BOUND; each of the 22 needs INDEPENDENT confirmation (structural / co-movement) before it counts
  as a real missed member.

## Synthesis — membership-coverage is a real upstream gap, but its size/impact are unproven

1. **M1-d (credit table) is a small lever** and can't be cleanly evidenced — keep the wire-in dark
   regardless of anything below.
2. **Membership-coverage quality is a genuine upstream gap worth attention:** the engine tracks
   only ~12% of EP alerts as themed, and there is a real judge-vs-engine divergence (the blind-spot).
   But its *magnitude* and *grade-impact* are NOT established — the number is HIGH-only + judge-defined.
3. **Any probe must clear the independent-attribution bar (THE LINE):** the judge→assign→boost loop
   is the circular discovery-feeder carved out of v1 (#167). A blind-spot probe must confirm
   membership by an INDEPENDENT mechanism (structural named-entity overlap / co-movement — signals
   `mi_theme_axis_shadow` already logs: `matched_terms`, `co_moving`, `structural_attributable`),
   never the judge's own theme read.

**Bottom line for the operator:** M1-d stays dark (small + un-evidenceable). The judge-vs-engine
theme divergence is a real signal worth an *independent-attribution probe* to see if coverage is
genuinely leaking members — but the size and grade-impact are unproven, so this is a "worth a
scoped look," not a proven redirect. Both are keep/shelve calls (THE LINE), not agent decisions.
