# Breakout v1 paper replay — two follow-up tests on the frozen outcomes (pre-registration, 2026-11-01)

**Status when written: REGISTERED, NOT COMPUTED.** No candidate's number on 2022-24 has been read. The only
2022-24 numbers seen are the frozen replay's own primary row (today's slot order, no stop floor: n 581, -0.412R
[-0.58, -0.21], 3.6% at 3R or better, FAIL), which is the baseline this document judges against.

Offline research on a frozen file; nothing live changes; any rule change is the operator's call (THE LINE).
Nothing dated 2025-01-01 or later is read (every row of the frozen file has E <= 2024-12-31 and free_date <= 2024-12-31).

## 0. In plain words

- **The question.** The frozen replay said the paper lane as built loses about a quarter of its risk per trade. Its
  audit saw two things that are not the setup but the BOOK: (a) the five slots go to the top-ranked names first and
  those read worst; (b) the trades with a stop under 10 cents cost most of the 2-cent cost drag. Would a different
  slot order, or refusing the tightest stops, change the verdict?
- **No re-walk.** Every list name-day's own outcome (fill, exit, R at 2c) already exists in `out/trades.tsv.gz`. A
  slot order only changes WHICH name-days are admitted to the five slots; a stop floor only REMOVES name-days. Both
  are re-runs of the book (`apply_book`, imported from `v1_replay.py`, never copied or edited) over the same rows.
- **Honest split.** Every candidate is scored on 2017-21 only; ONE is chosen there by a rule written here; only the
  chosen one and today's are then read on 2022-24, with the registration's own PASS / FAIL / CAN'T TELL words.

## 1. Inputs (frozen; read-only)

- `out/trades.tsv.gz` — 60,480 list name-days; 18,094 placed an order (6,588 filled, 11,506 cancelled unfilled);
  6,153 filled rows are decisive (mature, E on or before the cutoff 2024-07-10); 1,639 of those were admitted by the
  primary book (`adm_cap`). Each filled row carries `r_2c` (R at 2 cents a share each way, raw price scale), `fill`,
  `stop`, `raw_factor`, `free_date`, `free_minute`, `exit_at_open`, `legs`, `f_risk`, `total_r`.
- `out/report.txt` — the frozen primary row and its verdict (the baseline).
- The minute stores under `/Users/alvinfung/apollo_data/cb702_pre_v2/` and `/Users/alvinfung/apollo_data/cb702/`,
  read by the replay's own `minute_index` / `held_in` / `runner.read_minute_file` / `runner.minutes_for` (imported),
  ONLY to re-evaluate the placement tick of each placed row (§3) — no outcome is recomputed from them.
- The live tick function `breakout_v1_entry.evaluate` (imported; pure) for the placement-tick facts.
- Bar and statistics: `v1_replay.stats` (month-block bootstrap, 2,000 draws, seed 702, a fixed stream per key),
  `v1_replay.verdict` (the bar), `N_FLOOR = 100`, `TAIL_SHARE = 8%`, `FAIL_MEAN_REF = +0.25R`, `CAP_SLOTS = 5`.

## 2. The mechanics (what the two levers can and cannot move)

- **The book.** `apply_book(placed, slots=5, safeguards=False, sessions=<every E>)` — one chronological pass over
  every placed row, day -> minute -> `list_rank`, the same-ticker guard then the 5-slot cap. It is run over the WHOLE
  2017-24 placed set every time (positions carry across the 2021 -> 2022 seam, as in the primary); the result is then
  sliced by era on E. Never run per era.
- **Parity gate (runs first, blocks everything).** Rebuilt from the frozen file with today's `list_rank`, the book
  must reproduce `adm_cap` on every placed row and the frozen blocked counts
  (`block:max_positions` 11,808; `block:ticker_open_position` 1,260), and the primary row's two era lines at 2c
  (2017-21 n 1,058 mean -0.153; 2022-24 n 581 mean -0.412). If it does not, nothing below is reported.
- **The slot-order lever.** `apply_book` sorts a day's placements by `(placed_m, list_rank)` and uses `list_rank`
  as the tie-break when a cancel and a placement share a minute. A candidate order therefore = a synthetic integer
  `list_rank` written on each row: unique within each (E, placed_m) tick, 1 = first. **An order only re-orders names
  placed at the SAME minute** (10,826 of 18,094 placements are at minute 5, the 09:35 tick; 11,737 rows share a tick
  with another placement); a later placement still queues behind an earlier one, as live does. The book code is not
  touched.
- **The stop-floor lever.** A floored-out row is REMOVED from the placed set before `apply_book` (it was never
  placed, holds no slot, so a later name may take its place). Both filled and unfilled rows are subject to it.
- **The population scored.** Admitted + filled + decisive rows, `r_2c`, sliced by era on E. The same month list
  (`month` = E's month) feeds the bootstrap.

## 3. The placement-tick facts (one read of the minute bars, captured once)

For every placed row, the tick at `placed_m` is re-evaluated exactly as the walk did it: the minute bars through
`placed_m - 1` (the last completed minute) -> `breakout_v1_entry.evaluate(mins, list_level, adr20, vol_bar,
last_completed=placed_m - 1)` -> `level`, `stop` (the day-low stop), `cum_volume`, `need_volume`. Saved ONCE to
`tick_facts.tsv.gz` in this folder and read from there afterwards.

- **Sanity, asserted:** the recomputed `level` and `orh5` equal the frozen row's `level` / `orh5` on every placed row;
  on filled rows with no re-price the recomputed `stop` equals the frozen `placed_stop`.
- **Volume pace** = `cum_volume / need_volume` at PLACEMENT (>= 1 by construction, F1 permitted the order). **This
  deviates from the task's words "at the fill" on purpose:** the slot is taken at placement, the fill is unknown then
  (reading it would be look-ahead) and does not exist for the 11,506 unfilled names that also hold slots.
- **Planned risk at placement** = `level - stop` (adjusted scale). In raw cents: `(level - stop) x raw_factor x 100`.
  As a share of price: `(level - stop) / level`. The same quantity serves the "tightest stop first" order and the stop
  floor, for filled and unfilled rows alike — it is what a live rule can check at placement.
- Beside (reported, not used): on filled rows the literal `fill - stop` reading (the fill is above the level on
  about 18% of fills; the stop at the fill was lowered on 6) — how many filled, admitted, decisive rows the two
  readings classify differently at each floor.

## 4. Test 1 — SLOT ORDER (candidates fixed here)

Within each tick, first = the name that gets the slot. Ties inside a candidate break by today's list rank.

| id | candidate | within-tick key |
|---|---|---|
| T | **today's: strongest first** (the live order) | `list_rank` ascending |
| R | rs_best ascending (the weakest RS percentile first) | `rs_best` ascending |
| L | list rank 11+ before 1-10 | (`list_rank` >= 11 first) then `list_rank` ascending |
| P | volume pace at placement, highest first | `pace` descending |
| W | tightest stop as a share of price first | `(level - stop) / level` ascending |
| X | fixed-seed random (20 seeds, 0..19) — the NOISE FLOOR, not a candidate to pick | `numpy.random.default_rng(seed)` permutation of the day's placed rows |

## 5. Test 2 — MINIMUM STOP (candidates fixed here)

Skip (remove before the book) every placed row whose planned risk at placement is under the floor.

| id | floor |
|---|---|
| 0 | none (today) |
| c5, c10, c15, c20 | under 5 / 10 / 15 / 20 cents a share, RAW price scale |
| p0.5, p1.0, p1.5 | under 0.5% / 1.0% / 1.5% of the level |

The slot order in Test 2 is today's (T). The combined rule (§7) is the chosen order + the chosen floor.

## 6. Selection — on 2017-21 ONLY (written before any number)

- Statistic: **mean R at 2c** of the capped book's admitted, filled, decisive rows with E in 2017-21.
- Test 1 winner: the candidate among T, R, L, P, W with the highest mean R; tie (within 0.005R) -> the higher
  >= 3R share; still tied -> T (today's).
- Test 2 winner: the floor among 0, c5, c10, c15, c20, p0.5, p1.0, p1.5 with the highest mean R; the same tie rule.
  n, the >= 3R share and the summed R are reported beside so the trade-off (fewer trades vs a better mean) is visible,
  but they do not pick.
- **Noise floor read (declared now):** the 20 random orders' 2017-21 means give a min..max range. If the Test 1 winner's
  2017-21 mean sits INSIDE that range, it is written up as "not separable from a random order" and the 2022-24 read
  of it is still reported but today's order is the one kept. The same range is reported on 2022-24 as a reference
  (it is not a chosen candidate; it carries no selection).
- Every candidate's 2017-21 line is reported as the selection evidence. 2022-24 is computed only for: today's (T, 0),
  the chosen order, the chosen floor, the combined rule, and the random reference. The script is split into a
  selection phase (2017-21 only, writes the choice to a file) and a judging phase that reads that choice.

## 7. Judging — on 2022-24, the registration's own bar (§6 of the replay registration)

Read on the capped book at 2c, admitted + filled + decisive rows with E in 2022-24:

- **PASS** = n >= 100 AND the interval's lower end > 0 AND the >= 3R share >= 8%.
- **FAIL** = n >= 100 AND the interval's upper end < +0.25R AND the >= 3R share < 8%.
- **CAN'T TELL** = otherwise, with the sub-reading named (tail present / mean positive, tail thin / n < 100 /
  interval spans the bar), exactly as `v1_replay.verdict` names it.

Rows judged: today's (the baseline, FAIL), the chosen slot order, the chosen stop floor, and the combined rule.
Pre-declared reads:
- A move from FAIL to CAN'T TELL is reported as CAN'T TELL, not as an improvement; only PASS is PASS.
- "Beats today's" is claimed only when the candidate's 2022-24 mean exceeds today's by MORE than the width of the
  20-seed random range on 2022-24 AND the candidate was also above today's on 2017-21 (same sign in both eras).
- The combined rule is the two chosen pieces together; it is not selected separately and is read last.

## 8. What this read cannot say (stated before the numbers)

- The 2017-21 choice is in-sample for 2017-21: its 2017-21 number is selection evidence, never a result.
- 2022-24 is one era (581 admitted trades today; fewer under a floor): one PASS or FAIL there is one era's reading,
  and the calibration table of the replay registration says a +0.30R population passes under a third of the time at
  any n, so a modest real gain reads CAN'T TELL here.
- Five orders and seven floors were tried: the winner of each is the best of several, which inflates its 2017-21
  number; the random noise floor is the only guard against that, and it guards the ORDER test only.
- A slot order re-orders only names placed at the same minute; a different placement rule (waiting, batching) is not
  tested.
- The pace and width are read at placement, not at the fill (§3); a fill-time version is a different rule.
- The exit, the entry, the list and the costs are exactly the frozen replay's; nothing here speaks to them.
- These are PAPER book effects; nothing here is a recommendation about live money.

## 9. Procedure

1. `python followup.py tick` — the placement-tick facts, once (writes `tick_facts.tsv.gz`; refuses if present).
2. `python followup.py select` — the parity gate, then every candidate on 2017-21; writes `selection_2017_21.txt` and
   `chosen.json`. No 2022-24 number is computed or printed.
3. `python followup.py judge` — reads `chosen.json`; computes 2022-24 for today's, the chosen order, the chosen floor,
   the combined rule and the random reference; writes `judge_2022_24.txt`.
4. `RESULTS.md` is written from those two files.
