# #491 DONE-WHEN read, Fri 2026-10-23 18:2x ET (read-only; nothing closed, nothing edited but this file)

VERDICT: NOT MET. Missing piece = the cohort outcome: the DoD's third clause is "the concrete fix for the neocloud cohort" and tonight 7 of the 8 names sit in NO live theme (CIFR in a 2-member Fading one); the pre-registration's own refute column fired on P2, P3, P4. What DOES exist: design doc, his 10-03 ruling, pass built and live, 15 of 15 heartbeat nights (the DONE-WHEN stopping rule fired). Nothing can close early. Footnote only: U1/U2/U4 use a 14-day window, still open to 11-06 for the 23 move/join rows of 10-12..10-23.

DoD (verbatim): "DoD: a design doc characterizing the gap + a proposed detection/migration mechanism + the concrete fix for the neocloud cohort -> operator rules build." Met by docs/analysis/491_pivot_migration_proposal_2026-10-03.md + his "Rec on all" 10-03 + pass live since 10-05.
DONE-WHEN (verbatim): "15 trading days of heartbeat rows with P1-P4 and U1-U4 in one table." Rows: 15 `theme_rehome_pass_ran`, one per ET date 10-05..10-23 (last id 60981, 17:04 ET), 0 `theme_rehome_pass_error`.

## The one table (queries: scratchpad q1..q4 .sql/.out; remote /tmp/v1023_491_q*.sql)
| # | bar (PLAN EXPECT) | reading | verdict |
|---|---|---|---|
| P1 | >=1 `theme_member_rehomed` in 5 runs | 38 rows (32 leave-moves + 6 join-carries) on 12 of 15 nights; first on run 1 (10-05, 4 rows); heartbeat moved sums to 32 | MET |
| P2 | CIFR and HUT each in the AI compute theme or a judged-stay row within 10 runs (10-05..10-16) | neither ever in 'Emerging AI Compute & Cloud Infrastructure Platforms'; 0 `theme_rehome_judged` rows for either; neither among the 18 offered on any of the 15 nights. Only APLD+CORZ were judged (stay, 10-08), both homeless by 10-16. Rule-B caveat also fails it | NOT MET |
| P3 | 0 new crypto-named theme holding >=2 of the 8 in 15 days (refutes at >=2) | 3 births: 'Bitcoin Miners Pivoting to AI Data Center Hosting' (10-07, APLD/CIFR/CORZ/WULF), 'Bitcoin Miners & HPC Hosting Laggards' (10-09, CLSK/IREN), 'Bitcoin Miners Pivoting to AI/HPC Data Centers' (10-16, CLSK/IREN) -- first_seen_ever from mi_themes | NOT MET |
| P4 | G2 misfiled < 2% on >=10 of 15 nights | 0 of 15: 4.2 3.6 2.8 3.0 2.7 3.0 3.7 3.5 3.8 4.2 3.3 3.2 3.5 3.0 2.1 (tonight 14/681 = 2.06%) | NOT MET (cannot recover; window is over) |
| U1 | EP alert depending on +10 on a name re-homed in prior 14d | 0 alerts on any re-homed ticker (16 alerts since 10-05, 5 in a theme, none re-homed). Windows for moves 10-12+ still open | 0 so far, partly gated |
| U2 | re-added to SOURCE inside 14d cooldown (expect 0) | 4 of 32 leave-moves are back in a SOURCE-named theme next trading day: MKSI 10-07, PAYX 10-16, YUM 10-16, CXM 10-21. Pattern: source row 'Retired' on the move night, back next night as a 3-member `shadow_promoted` row holding the moved ticker; `rehome:` cooldown rows exist (ids 932/1028/1073; PAYX's overwritten by a retro-sweep) yet did not stop it. Traced: `promote_shadow_themes`/`_upsert_promoted_theme` (theme_engine.py 2451-2775) read no cooldown, ban or exclusion (grep empty; `db.get_shadow_theme_candidates` not read) -> a real bypass of the cooldown wall, distinct from bug E (that one is the birth gate's view of a re-promotion). Literal `ticker_assigned` is not persisted in the audit table, so only the membership reading exists | FIRED (by membership) |
| U3 | candidates/offers per night <= 15 | pre-cap 139 108 86 93 75 76 61 59 52 48 53 49 52 56 59; offered 18 on all 15 nights (cap) | FIRED 15/15 by construction |
| U4 | same name judged/moved twice in 14d | 0 pairs inside 14d (judged-memory works: `judged_recent` climbs 0->178 then falls to 172 as rows age out). 14 names re-judged at 14-15d (RBRK 14d +30s, boundary); 0 names moved twice | 0 (fresh) |

## WOULD-FAIL-IF (literal)
- "0 moves while the heartbeat shows >=1 offered": window = no (32 moves). Per night = 4 nights (10-13, 10-16, 10-21, 10-23: 18 offered, 0 moved, 18 judged-stay rows, unjudged 0). Not a dead funnel, since moves happen on 11 other nights.
- "a move into a wrong-business theme (HUT->EMS shape)": none obvious in 38 rows by my read of ticker business (e.g. FLEX->EMS Providers is right-business). Loosest fits to spot-check: RBRK->Network Security, TEAM->AI Workflow SaaS, VSH->RF/Microwave/Power Semi. This is my judgement, not a ruling.
- "+10 line missing on a paying move": audit-row note present on 32 of 32 paying rows; non-paying rows (6) correctly lack it. The Telegram themes-message text is not stored in prod, so the message line itself is NOT verified live (render unit test passes: tests/test_state_alerts_479.py -k rehomed). My audit-row check would read the same if the message render were broken, so it does not discriminate that.

## The eight (CIFR HUT CRWV IREN WULF CORZ CLSK APLD): homes 10-02 vs 10-23
- 10-02: CRWV in the destination (Mainstream); CIFR+HUT in a Fading 2-member miners theme; 5 in no theme.
- 10-23: CIFR in 'Bitcoin Miners Pivoting to AI/HPC Data Centers' (Fading, 2: MARA, CIFR); the other 7 in NO live theme. Worse than baseline: the destination theme went Fading 10-12 and Retired 10-13 (rule B), so no non-Fading AI compute theme exists to offer into.
- HUT: homeless since the 10-05 board (rule B retired its home); the pass never reaches a themeless name (orphan reach ruled NO 10-03). Why CIFR was never among the 18 offered: not determinable (only the capped 18 are logged; queue is 48-139).
- Context: 30 of 32 leave-moves were thin-basket (1-2 member home) consolidations into a larger similar theme, 2 were G2-misfiled; none was the pivot case the task exists for.

## For the main loop (not decided here)
- Table above is the DONE-WHEN deliverable; it can be written to the SSoT tonight. Cohort goal and P2/P3/P4 are failed rows, not closeable as success.
- Open fork for the operator: how a cohort with no live destination theme gets re-placed (pass cannot; orphan reach is his ruled NO).
- U2 shadow_promoted bounce = confirmed cooldown-bypass gap in the promotion path (4 of 32 so far); U3 cap vs queue size is a standing known.

## What a BROKEN system would read (per check)
- Dead pass or dead judged-memory would read: heartbeat rows 0, P1 0 rows, U4 0 pairs with `judged_recent` stuck at 0. Observed 15 rows, 38 rows, `judged_recent` 0->178 then falling as rows age out -> these DISCRIMINATE (pass runs, memory works). U4 = 0 pairs alone would not.
- P2/P3/P4 would read the same under a dead pass, but P1 proves it runs, so they are EFFECT failures, not operation failures. P2 in particular: the pass ran 15 nights and never offered either name (and cannot reach a themeless one).
- U1 = 0 alone does not discriminate (16 alerts, none on re-homed names); weak, and windows are still open.
