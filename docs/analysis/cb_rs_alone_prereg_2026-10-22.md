# #705 — RS leadership alone, the one read on the sealed 2025–26 (pre-registration, 2026-10-22)

**Status: DRAFT — not frozen. No outcome on 2025–26 has been computed for this score.** The read runs once, only after the
freeze commit (pins below the marker) is on main.

## Why this read exists (registered before it, not chosen after)

The A+ rating read (`docs/analysis/cb_aplus_rating_prereg_2026-10-21.md`, frozen `0d80a8d1`, RESULT 2026-10-22) came back
CAN'T TELL × CAN'T TELL with the paired bar "can't tell" in both eras, so it is not recorded. Its consequence table fixed, before
any outcome: *"Not recorded → the next registration is NAMED NOW: among the SEVEN core concepts' alone rows ONLY … the one with the
highest mean over the two eras of ≥ 10R per 100 that also meets the 3-ticker / 3-month spread in both … it is registered on its own
and tested on the still-sealed 2025–26."* `aplus-verdict` applied it and printed `next registration: alone_c3`, concept 3, RS
leadership (`rs_best` = the best of the 1-, 3- and 6-month return percentiles across the universe on D). This page registers
that read. Nothing about the rule is new; every choice below is the parent's, cited by section.

## Method / population

- **Population:** the sealed 2025–26 table, `cb702/out/trades_holdout_exitpb.tsv.gz`, C0 `tl` ORH5 under the carried exit `pp`.
  The fills are the parent's holdout population exactly: 7,570 joined → 7,547 after the 23 fills of 2025-01-03 are excluded
  (they stay pool-only members, `EDGE_DROP`); 39 open marks; 93 ISO weeks; 7,508 mature. These are the STEP 0 equality targets
  already pinned in `aplus_read.py` (`STEP0_TARGETS["holdout"]`).
- **Pool:** each fill's pool is every population fill with E′ in [E − 20, E − 1] on the SPY session calendar, open marks
  included. The first holdout weeks are pooled from the trailing 2022–24 fills in the DISCOVERY tables, as the parent's
  `period_paths("holdout")` reads them (parent §Population).
- **Inputs:** `rs_best` from the candidates / watch tables as the parent reads it. Zero missing in the joined rows (parent check 3).

## The rule (the parent's `alone_c3` row, unchanged)

- **Score.** pct = (number of pool values worse than the fill + 0.5 × number equal) ÷ |S|, higher `rs_best` = better. S = the
  pool's non-missing `rs_best` values, the fill itself not in S. Pool floor |S| ≥ 30, else the fill is unrated (parent §The rank).
- **Reference scores and the cutoff.** A rated pool member is scored against E's pool with itself removed. The CUTOFF is the
  12th-highest reference score (N = 3 a week × 4 weeks). Fewer than 12 rated members leaves the fill unrated (parent §The A+ rule).
- **A+.** score ≥ cutoff AND fewer than 3 A+ already taken in the fill's ISO week (Mon–Sun by E), in fill order (E,
  `fill_minute`, ticker A→Z). A fill at or above the cutoff after the week's 3 is "capped" and stays in REST.
- **N = 3 decides.** No N = 1 or N = 5 row, no other score: the core, +grp, the other alone rows and the stair-step rows stay
  uncomputed on 2025–26.

## Disclosed — what has already been read, and one property of the rule

- **This ingredient was SELECTED on its deciding-era reads, which makes this a one-shot test of a selected winner.**

  | Era | Mature A+ trades | Mean R | 95% interval | ≥ 10R per 100 (C0) | ≥ 10R spread | Verdict |
  |---|---|---|---|---|---|---|
  | 2017–21 | 510 | +0.193 | −0.13 .. +0.58 | 1.76 (1.235) | 9: 7 tickers / 5 months | CAN'T TELL |
  | 2022–24 | 288 | +0.266 | −0.13 .. +0.73 | 1.74 (0.946) | 5: 4 tickers / 4 months | CAN'T TELL |

  Its big-winner rate was about 1.4× and 1.8× C0's, not the 2× the bar asks. It was chosen among seven rows, and the best of
  seven looks better than it is.
- **2025–26 is not unread in general** (parent Disclosed (d)). The P5, exitpb and h60 reads and the regime report already show it
  by cell, and the C1 / C3 cells gate on `rs_best ≥ RS_BEST_PRIMARY`. So an RS cut of 2025–26 HAS been seen: a threshold gate,
  not this weekly top-3 rank. No `alone_c3` OUTCOME has been read there. Its score, cutoff and flag WERE computed once,
  features only, by the build's dry run (2026-10-22, STEP 0 below); no outcome column was opened.
- **`rs_best` is stored at 0.1 resolution, so it ties.**
  - Measured on the deciding eras: 840 / 714 distinct values, and the top 4% of fills hold only 6 distinct values (100.0 down to
    99.5; 0.6–0.7% of fills sit at 100.0).
  - Under the pinned leave-one-out reference scores, a fill whose pct p > ½ scores below each pool member tied with it; that
    member's pct is p + (p − ½)/(n − 1). So a fill tied with a member at the cutoff's own value loses that tie, where a
    continuous feature would pass. In effect the boundary moves to strictly above the 12th member's value when it is shared.
  - It is deterministic and identical to the `alone_c3` row that named this read: 510 / 288 fills, so it is measurable, unlike
    the stair-step row.
  - It is kept unchanged: altering the tie rule now would be a new rule tested on the same data that selected it.
  - STEP 0 prints, as features only, how many fills sit exactly at their cutoff's value.

## STEP 0 as measured by the dry run (features only, 2026-10-22, before the freeze; no outcome opened)

- The five pinned holdout counts are equal: 7,570 joined / 7,547 fills / 39 open marks / 93 ISO weeks / 23 excluded. Mature is
  7,508.
- **A+ n = 172 — BELOW the inherited expectation of 215–279** (capped 73, rest 7,302, unrated 0, thin pool 0). 61% of weeks
  after burn-in hold fewer than 3 A+.
- **47 fills sit exactly at their cutoff member's `rs_best` value, and all 47 are REST** (the tie property disclosed above,
  live on this table).
- `rs_best` census: 693 distinct values; 44 fills (0.58%) at 100.0; the top 4% (314 fills) hold 7 distinct values (100.0 down
  to 99.4).
- The rule is NOT changed for any of this. The expectation miss is recorded here before the freeze, and the bar is applied at
  whatever n the read finds.
- The chance figure at n = 172: the outlier bar needs ≥ 5 big winners (5 × 7,531 = 37,655 ≥ 2 × 89 × 172 = 30,616; 4 is
  30,124, which fails). A random subset at C0's rate (Poisson mean 2.03) reaches 5 with P ≈ 5.6%, before the interval and C0
  conditions, which make a chance PASS rarer.

## Bar (the parent's PASS bar with the 2025–26 numbers; parent §Bars)

- **PASS, all of:**
  - n ≥ 30 mature A+ trades;
  - the month-block 95% interval has lower end > 0 (2,000 resamples, `block_bootstrap_ci`, seed 702, key
    `aplus|holdout|3|alone_c3`);
  - ADR P&L > 0;
  - beats C0 on mean R AND on the ≥ 5R share (C0 = the published 7,531 mature fills: mean R −0.129, ≥ 5R 2.95 per 100);
  - the OUTLIER bar as an integer comparison: **count_ge10 × 7,531 ≥ 2 × 89 × n** (≈ 2.36 per 100), with the ≥ 10R trades from
    ≥ 3 distinct tickers AND ≥ 3 distinct fill months, the spread counted over stops ≥ 0.25 ADR20 wide.
- **FAIL:** n ≥ 30 AND (the interval's upper end < 0 OR not beating C0 on mean R).
- **CAN'T TELL:** otherwise, including "positive, no tail".
- **Paired A+ − REST** (key `aplus_pair|holdout|3|alone_c3`, the parent's draw rule): a VETO only. "Picks worse" (upper end < 0)
  means not recorded whatever the verdict.
- **Expectations (a miss changes no rule):**
  - A+ n 215–279 (the parent's confirm range; `alone_c3` filled like the core in both deciding eras, 510 vs 534 and 288 vs 288);
  - C0 under `pp` reads as published (mean R −0.129; ≥ 10R 89 of 7,531).
- **Chance of a false PASS** (the parent's null, approximate): ≈ 3.4% (n = 254, needs ≥ 7) to ≈ 8.3% (n = 253, needs ≥ 6) for
  the outlier bar across 215–279, and less with the interval and C0 conditions added.

## Consequence fixed now (three cells, no chain)

| Verdict on 2025–26 | Consequence |
|---|---|
| **PASS** (and the paired bar not "picks worse") | RECORD: the forward shadow stores the `rs_best`-alone score, cutoff, pool size and flag beside its rows. This is a recorder change: no order path, no money. Paper is a proposal to him; live is his sign-off (THE LINE). |
| **CAN'T TELL** | Not recorded. The rating line on these seven ingredients ENDS, as the parent fixed ("the rating does not select on these ingredients"). It is reported to him with the alone table of all three eras' readable rows. |
| **FAIL** | Not recorded; the line ends, as above. |

No further registration is named here. A new rating idea is a new registration on new data, not a re-pick on this table.

## Checks (a failure exits non-zero and writes no report)

1. **Freeze and once-only.**
   - `freeze_check` on every pin below the marker.
   - Its OWN artefacts, refused on a second run: `trades_holdout_rs_alone.tsv.gz` (+ `.partial`),
     `rs_alone_verdict_holdout.{json,txt}`, `rs_alone_report_holdout.{tsv,txt}`.
   - It writes NO `aplus_*holdout*` artefact, so the parent's `holdout_artefacts` guard stays meaningful.
2. **Precondition.** Both parent verdict JSONs exist, `consequence()` reads NOT RECORDED, and `next_registration()` returns
   `alone_c3`. Otherwise it refuses.
3. **STEP 0 before any outcome column is opened:** the five pinned holdout counts equal; the `rs_best` census; the ties-at-cutoff
   count; the rated / unrated / thin-pool counts.
4. **Look-ahead invariance** (the parent's check 1 (b) and (c), on this score):
   - with every E-day-or-later column shuffled at the source, every score, cutoff and flag is identical;
   - per sampled fill (50 + every A+), with every row after that fill's D randomised, the same.
5. **Later-fill removal** (parent check 2): removing every later fill leaves each A+ flag unchanged.
6. **Counts and pool** (parent checks 4, 6, 7): A+ unique by (ticker, E); per week A+ = min(3, fills at or above the cutoff);
   pool counts equal an independent count; the shuffle invariance.
7. **Outcomes read, never re-walked** (parent check 3 (outcomes)): every A+ row's `realized_r` equals the pinned exitpb row.
8. **Independent re-derivation** (pandas, no runner code): it computes the `alone_c3` set ITSELF (the parent's VERDICT MATCH
   covered core / +grp / rev_stair, not the alone rows), then n, mean R, both intervals, every PASS component. It must read
   VERDICT MATCH before the verdict is written.
9. **Golden fixtures:** a synthetic fixture with an `rs_best` tie at the cutoff value pins the tie behaviour stated above.

## What the read may NOT do

- Change the score, the pool window or floor, the member rule, the cutoff rank, N, the week rule, the cap order, the tie
  handling, the bar, the seed or the draw count.
- Compute any other row on 2025–26.
- Run twice.
- Edit this document above the marker after the freeze commit.
- Read 2025–26 for this score before the freeze is on main.

## What this does not answer

- **One era, one shot, on a selected ingredient.** A PASS is evidence for RS leadership as a weekly top-3 selector, not proof.
  A CAN'T TELL does not say RS leadership is useless; it says this rule cannot show it here.
- **Not whether the breakout setup pays as a whole.** That is C0 / C1, already read. Nor which entry or exit fits it: entries
  and exits stay undetermined for a new setup.
- **The RS threshold cells of 2025–26 were already seen.** This rank shares their input.
- **Daily data only.** RS is read on D, before the breakout day.
- **His other secondary ideas** (themes / groups beyond `grp_pct`, market phase as a split) are not tested here.

<!-- FREEZE -->
## Freeze record

(Pins printed by the stage's `--print-pins` — that output is authoritative for the list — and pasted here in the commit that precedes the run: the runner, the scaffold, the
spec module, the re-derivation module, the golden fixtures module, `trades_holdout_exitpb.tsv.gz`,
`trades_discovery_exitpb.tsv.gz`, `trades_holdout_p5.tsv.gz`, `trades_discovery_p5.tsv.gz`, `candidates.tsv`, `watch.tsv.gz`,
`daily_closes_all.csv.gz` and the doc body above the marker. The build adds `aplus_read.py` ("aplus module" — the engine it
imports, byte-equal to the A+ freeze's spec module) and its own fixtures module; the P5 and watch tables are pinned but never opened;
no minute tree or profile is read.)
