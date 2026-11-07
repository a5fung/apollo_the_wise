# #491 U2 — does the promotion wall hold back themes that should have graduated? (diagnosis 2026-11-07)

**Answer: no.** Of the 24 nightly holds since the wall shipped (10-26 → 11-06, 16 distinct themes), 21 changed
nothing on the board — a native theme of the same name already held that night's row, so the old code would have
skipped the write too. The other 3 were moved stocks bouncing back into a retired home — the case the wall exists
to stop. The breached "holds ≤ 10% of promoted rows" bound counted rows the old code never wrote.

## Population
- Every `promote_member_skipped` audit row after the U2 deploy (created after 2026-10-23 20:00 UTC, nights
  10-26 → 11-06 ET), grouped by (night ET, theme): n = 27 (night, theme) cohorts — 24 held under the floor,
  3 trimmed and still graduated (AI data-center power buildout on 2 nights, Self-Storage REIT on 1).
- Each barred pair joined to its newest `mi_validation_cooldowns` row written at or before the skip; each held
  cohort joined to `mi_themes` by exact name over the 7 days up to the hold night.
- Baseline for the churn check: all non-bypassed cooldowns written 10-05 → 11-07 (n = 331), split at the deploy.

## What was breached
- The U2 EXPECT (10-23, `scripts/probes/_verify_1023/REVIEW_491_U2.md`): trims + holds ≤ 10% of a night's promoted
  rows; replay baseline 5 of 157 `shadow_promoted` rows (~3%, n = 157) over 10-05..10-23.
- Live 10-26..11-06: 24 held cohorts against 74 graduated (1/0/0/0/5/0/1/4/5/8 a night), read 11-06.

## The checks (prod read-only, `scripts/probes/_491_diag_1107/`, q0–q5)
| check | result |
|---|---|
| Distinct held cohorts | 16 themes over 24 (night, theme) holds; plus 2 trimmed-and-graduated (AI data-center power buildout kept 9; Self-Storage REIT kept 3) |
| Why each member was barred (`q1_held`, `q3_cooldowns`) | 5 themes by a rehome cooldown (DRS, PRI + GL, PII, BLDR, SBSW + AGI + BVN); 11 by a validation removal (a description misfit) |
| When the barring cooldown was written | the same night as the hold, or the day before, for all 25 barred pairs |
| Real members left | 1 or 2 in every held cohort — under the 3-member floor on its own members |
| Was a theme of that name on the board that night anyway? (`q5_on_board`) | **21 of 24 holds: yes**, a native `source='live'` row for the same name and date (2–6 members, or Retired) |
| What the old code did then | `_upsert_promoted_theme` updates only a prior `shadow_promoted` row (`theme_engine.py` ~2489, `WHERE mi_themes.source = 'shadow_promoted'`), so on a native row it returns "INSERT 0 0" — a no-op |
| The other 3 holds | Building Materials 11-06, Footwear & Golf 11-05, South African miners 11-06 — all rehome; the home had retired the night before, so without the wall the cohort would have re-graduated with the moved stock (a bounce) |
| Before the wall, did promotion put validator-removed stocks back? (`q4_churn`) | 0 of 181 validation removals within 2 days (3 of 31 rehome moves — the known bounces) |
| Promotions still run (`q2_promoted`) | 25 of 25 nights 10-05..11-06 wrote a promotion row, 0 failures; 2–12 cohorts graduated a night after the wall; the two lightest nights (10-26: 2, 11-02: 6) had 1 and 0 holds, so the wall does not explain them |

## Why the bound read high
- The replay counted only rows the old code actually wrote (157 `shadow_promoted` rows). Holds are counted before
  the write, so they include cohorts the old code dropped silently on the native-row guard. Different populations:
  the 10% bound compared them as one.

## What it means
- The wall holds back no theme the signed rules would graduate: every held cohort is 1–2 real members.
- It blocked the 3 bounces it was built for, and 0 bounces got through in 10 nights.
- No fix: the extra holds cost nothing (no board change, no failures). Splitting the audit's held count into
  "would have written" vs "native row already there" is possible but measures no harm, so it is not proposed.

## What this does not answer
- **Whether the validator's misfit removals are right** (e.g. PS out of 'Alternative Asset Managers'): the wall
  applies every active cooldown by its signed scope; validator precision is a separate question.
- **Themes that never formed a cohort at all** — the wall only sees cohorts the shadow engine proposes.
- **Anything about returns.** Theme membership only; no money path reads it.
