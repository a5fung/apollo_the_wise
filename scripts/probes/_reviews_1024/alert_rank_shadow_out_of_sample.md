# alert_rank_shadow_out_of_sample — running read, Sat 2026-10-24 (prod read-only)

## Predicate now
- `count(DISTINCT alert_date) FROM mi_alert_rank_shadow WHERE alert_date > 2026-08-16` = **27** (threshold 1 -> MET; was 24 on 10-18). New sessions: 10-19 (IRON, MANE), 10-21 (SMCI, SPCX), 10-23 (SBAC).
- `confidence_label(27)` = **DECISION-GRADE (n=27 >= 25 sessions)**. By session count only: the matured top cell is still 6 rows.

## What ran
- Pinned SQL `scripts/probes/_verify_rank_shadow_2026-09-21.sql` shape (alert_date > 2026-08-16), via `docker exec apollo-postgres psql`, temp files `/tmp/rv1024_alert_rank_shadow_out_of_sample_{1,2,3}.sql` (deleted after). Output captured once, post-processed locally (cells from `scripts/probes/_rank_shadow/analyze_cells.py`, then an independent re-compute in separate code: identical).
- Measure unchanged from 09-30..10-18: best high over the EP day + next 5 sessions from the EP-day OPEN, in multiples of ADR20; 8x bar; top quartile = rank <= 0.25; matured = 6 sessions on record; "broke low" = min low of next 5 sessions < EP-day low.

## Result (55 rows, 27 sessions, 17 filled; 50 matured at 5 days, 36 at 20 days)
- Tail (5-day, 8x), EOD rank: top quartile **0 of 6**; the rest **2 of 44** (MRNA 9.13x ranked 0.875 of a pool of 4; KOD 12.43x, a pool of ONE). 09:45 rank reads identically.
- Losers direction (broke EP-day low in 5 sessions): top 4 of 6 (67%) vs rest 29 of 44 (66%) -> no separation either way.
- Medians second: best 5-day high 1.70x ADR top vs 1.81x rest (09:45: 1.70 vs 1.81) -> no separation.
- 20-day (secondary): top 1 of 5 (VICR) vs rest 1 of 31 (MRNA); 09:45: 1 of 4 vs 1 of 32. KOD's 20-day window unmatured (20 of 21 sessions).
- New rows since 10-14 (all unmatured): MANE 0.25/pool 2 (top quartile, 5 sessions, 3.4x so far, low held), IRON 0.75/2 (2.8x so far, filled), SMCI 0.58/2 (0.5x, filled, broke low), SPCX 0.42/2, SBAC 0.5/1. BSP (10-14, pool of 1) matured 2.63x ADR, broke its low.
- Power: only 2 tail winners in 50 matured rows; KOD can never enter the top cell (pool of 1). 39 matured rows sit in pools of 2+, 6 of them top cell -> 85% chance by luck alone that MRNA lands outside it. Top cell 0 of 6 neither confirms nor rejects the in-sample 2.5x lift.

## What a BROKEN system would show, checked
- Recorder dead/short: would show alerts without shadow rows. `mi_ep_alerts` after 10-14 = 5 rows (10-19 x2, 10-21 x2, 10-23 x1), all 5 present in shadow (LEFT JOIN in_shadow = true for every one); shadow rows 50 -> 55 = +5. The 10-23 row proves the 17:53 ET rank job ran last night.
- Stale prices/outcome join: `mi_daily_closes` max date 2026-10-23; 0 NULL open/low/h5/h20 across 55 rows; every row's session count equals the weekday count since its alert date minus Labor Day (0 mismatches) -> no missing sessions pulling the 5-day high down.
- Fan-out: the join is on `mi_daily_closes` only (not `mi_ep_missed_outcomes`), so the 09-17 fan-out cannot recur; 55 rows = 55 shadow rows.

## Verdict (the entry's own action)
- By the entry's own rule: n=27 >= 25 is DECISION-GRADE, and the top quartile caught 0 of 2 tail winners (0 of 6 matured rows) -> **reads "does not validate" (plan narrows to conversion alone)**. Stated as the rule's reading, NOT as "the rule does not work": test power is ~nil (2 winners in 50 matured rows).
- Plan pointer: no PLAN.md #id on this entry; the plan reference is section 0b-fwd in `docs/roadmap/ep_profitability_program.md:1041`.
- Fork for the operator (not decided here): (a) accept the entry's reading at n=27 -> plan narrows to conversion alone; or (b) the matured top cell (6 rows) cannot separate the in-sample 2.5x lift from zero -> redefine decision-grade on matured top-cell rows instead of sessions (changes `DECISION_GRADE_SESSIONS`/label in `scripts/alert_rank_shadow_running_read.py`, pinned by `tests/test_alert_rank_shadow_running_read.py` -> his sign-off). Rough weight: MRNA lands outside the top cell ~38% of the time if the in-sample lift (16 of 26 winners in the top quartile) held vs ~85% under no effect -> about 2:1 against the rule, not decisive.
- Rec: (b) keep running, re-read when MANE (the only top-cell row in flight) matures 10-26; do not narrow the plan on 0 of 6.
- Next movement: Mon 10-26 close -> IRON + MANE mature at 5 days; KOD's 20-day window closes and it enters the 20-day rest cell as a winner (its 5-day max was already 12.4x), so the rest's 20-day tail reads 2 of 32 not 1 of 31; SMCI + SPCX 10-28; SBAC 10-30.

## Paste-ready YAML (insert directly under `title:`, above `resolution_2026_10_18`; `status: pending` unchanged - running read)
```yaml
    resolution_2026_10_24: >-
      RAN 2026-10-24 (Sat), prod read-only, same pinned SQL (scripts/probes/_verify_rank_shadow_2026-09-21.sql) and measure
      (5-day best high from the EP-day open in ADR20 multiples, 8x bar, top quartile = rank <= 0.25). Predicate 27 sessions
      (was 24): 10-19 IRON + MANE, 10-21 SMCI + SPCX, 10-23 SBAC. confidence_label(27) = DECISION-GRADE - BUT the matured
      top cell is still 6 rows (5-day) / 5 (20-day): quote both, never the label alone. 55 rows, 50 matured at 5 days.
      5-day EOD: top 0 of 6 at 8x (4 broke low) vs rest 2 of 44 (MRNA, KOD; 29 broke low); 09:45 reads identically. Losers
      direction 67% vs 66% = no separation. Medians: 1.70x vs 1.81x ADR = no separation. 20-day: top 1 of 5 (VICR) vs rest
      1 of 31 (MRNA). BSP (10-14, pool of 1) matured 2.63x, broke low, rest. Liveness: 5 alerts since 10-14 = 5 new shadow
      rows, all present; closes through 10-23, 0 NULLs, 0 missing sessions; no join fan-out. By the entry's own rule the read
      is "does not validate" (0 of 2 tail winners in the top cell), but power is ~nil: 2 winners, KOD a pool of 1 that can
      never enter the top cell, 85% chance by luck MRNA lands outside. FORK FOR HIM: (a) accept the n>=25 reading -> plan
      narrows to conversion alone, or (b) redefine decision-grade on matured top-cell rows (changes DECISION_GRADE_SESSIONS,
      test-pinned -> his sign-off). Rec (b): keep running. Next: Mon 10-26 IRON + MANE (top cell) mature, KOD 20-day matures
      (enters the rest cell as a winner); SMCI + SPCX 10-28; SBAC 10-30.
```
