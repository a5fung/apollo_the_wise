# #705 QM replay — adversarial review of the registration + `01_replay.py` (2026-10-23, pre-freeze)

**Verdict: FIX.** The deciding comparison does not match each control trade to its own day. Three registration defects
should be settled before the freeze. Everything else is ready to run.

Run here: `pytest test_01_replay.py` gave 32 passed (0.52 s). `01_replay.py --dry-run` exited 0, and its printout is byte-identical
to the saved `01_replay_dryrun.txt`. The freeze record reads "NOT YET", as expected. `check_analysis_doc.py <doc>` exited 0.

What I opened (outcome disclosure):
- No minute file, no bar after any E, no walk.
- One `head -3 labels_joined.tsv` printed 2 era-B label rows in full. That includes their `r1_status` (`not_in_fill_population`)
  and `r2` (−1). No R value was shown, and no era-A row.
- The date-mix probe below read the labels and the candidate keys only.

## Checks

| check | result | evidence |
|---|---|---|
| (1) population = the on-or-before positives, 236 / 9 | **PASS for the label set; one post-E filter → fix 4** | Derived by the frozen `FIT.label_sets` / `assign_classes` (01_replay.py:402–416). pos = `dmax >= 0` (02_fit_filter.py:758). Counts asserted at 01_replay.py:925–929 against EXPECT (185–196), and the dry run matches all of them. No E-day or forward column is on any read list (309–311; test 489). The join's nearest rule (01_join_labels.py:25–27, 367–375) cannot let a later event take E's label. **But** `break_post` (01_replay.py:1066–1075) drops events on a break dated in (E, E+120]. |
| (2) rules = the SSoT's S-quotes; walker reused unchanged | **PASS for entry / stop / exit / walker; FAIL on sizing → fix 2** | `walk_event` (517–539) wires `runner.evaluate_candidate` (runner.py:1648–1690) line for line. Parity tests: `test_grid_dispatch_equals_runner_walk_arms`, `test_primary_equals_runner_evaluate_candidate`. `pp` matches the runner's own call (runner.py:5990–5995). ORH5, stop at the low of the day at the fill, too_wide over ADR20, and 1/3 at the s3 close + breakeven + first close under the 10-day at the next open all match consolidation_breakout.md:75–90 and operator_shared_notes.md:1940–1947. Doc §6 (l.193) says the sizing is "not his captured words". That is false: notes:1944 and the SSoT at consolidation_breakout.md:232 both state his sizing. |
| (3) no look-ahead (stop at the fill, no later bar decides entry) | **PASS, with 2 runner-parity notes** | Stop = `minutes.l[:m+1].min()` (cb:1009). That includes the fill minute's own low, and the order inside a minute is unknowable. The day-0 walk starts strictly after the fill (cb:970). too_wide is judged on ADR20 at D (cb:987). A candidate exists iff high(E) > pivot (cb:1681–1684), which any fill at ≥ pivot implies. QQQ is read at D = E−1 (01_replay.py:910–912). Note: the `minute_daily_mismatch` abstain reads E's full-day minute range (cb:1034–1036). It is applied to both arms and counted per arm (01_replay.py:1167–1175). |
| (4) account: risk on current equity, cap, concurrency, partials, compounding, skips | **PASS (mechanics); his per-stock limit is missing → fix 2** | Sized on the previous close's marked equity (718). Cap via `min()` (718). No-room skip / trim (719–726). Same-stock positions counted (728–729). Each leg sells its fraction of the ORIGINAL shares (741–744). Daily mark and drawdown (749–762). `legs_of` order (549–565) = §6. R from the dated legs equals the walk's own R to 1e-9 and the legs sum to 1 (603–605). 7 sim tests + the end-to-end test pass (test 249–310, 497–536). |
| (5) control = the same day's other breakouts, identical rules, round-3 exclusion | **Population PASS; deciding comparison FAIL → fix 1** | neg = `on_g & ~pos & ~lab_by_E` (02_fit_filter.py:839–842). Exclusions 410 / 7 asserted. Every arm goes through the same `walk_event` (1076). But `paired_block_diff` strata = retrigger only (1206–1209). The control is pooled across dates, not matched to his days (probe below). |
| (6) fork thresholds fixed and sensible | **Fixed PASS; sensible FAIL → fix 3** | Constants at 160–162, `fork_verdict` at 821–828, `test_fork_verdict` passes. The curve arm never looks at the control band (curve-arm row of the doc's fork table, l.209). |
| (7) data gate: v2, era-B cut asserted, G8 on the trade list, minute coverage | **PASS** | Era A is `cb702_pre_v2` (82). Era-B rows dated after the cut are dropped at read and asserted: 341–349, 390–395, 876, 890, 263. G8 is written, run and asserted 0/0 before any number (1154–1165). An unreadable G8 output is a refusal (838–842). `trade_impact.py` drops bars after the cutoff at read (trade_impact.py:19–25). Minute coverage comes from `_done.psv` (915–916): 0 empty / 0 missing in every arm. |
| (8) freeze lock | **PASS, one gap → fix 6** | `pins()` (277–283) covers every input, the code, both minute trees and `doc_body`. `freeze_missing` at 286–292, the real-run refusal at 1018–1021, the output check at 979–983. Tests 418–486: unfrozen, edited after the pin, output exists, input drift. |
| (9) `check_analysis_doc.py` | **PASS** | Explicit path, exit 0 (checker:166–176 honours argv). The doc has §11 Method / population and §12 What this does not answer. |

Date-mix probe (era A, counts only; scratchpad `datemix.py`):
- Control events per date run from 2 to 625 (median 126.5).
- The 16 dates with the most control events (the top 10%) hold 26.6% of the control but only 8.9% of his calls.
- The distance between his date weights and the control's (total variation) is 0.312.

## Fixes, most severe first

1. **HIGH — the deciding comparison is not same-day.**
   - The problem: `paired_block_diff` (635–675, called at 1206–1209) pools the control within first-break / retrigger only. So
     the control's mean R is dominated by mass-breakout days.
   - Why it matters: every trade's outcome is driven mostly by what the market did after that day. The interval arm can read a
     date-mix effect as his picking.
   - Fix: weight each control trade by his trades ÷ the control's trades in the same (date, stratum) cell, filled + mature only.
     Then his-minus-control = the sum over cells of his trades × (his mean − control mean), divided by his trades.
   - Drop and count a cell the control does not cover. Keep the month blocks, which carry whole dates. Keep the pooled and the
     stratum-only differences beside.
   - Edit doc §3 (l.95) and §5 (l.141–148) to say so.
   - Add a synthetic test: a control heavy on bad days must give a date-matched difference that differs from the pooled one.
   - R6 still holds: the cell weights are his trade COUNTS from the full sample, so they are not re-estimated inside a resample.
2. **MEDIUM — sizing: the source is misstated, it differs from the SSoT, and his per-stock limit is missing.**
   - The source: §6 (l.193–195) says the notes do not carry his risk per trade. They do. operator_shared_notes.md:1944 reads
     *positions 10–20%; risk 0.25–1% a trade, rarely more than 1%; at most 30% of the account in one stock overnight*.
   - The SSoT: consolidation_breakout.md:232 reads "the article's sizing (position = min(20%, 1% ÷ stop width))".
   - His per-stock limit: R4 (l.315; simulate 714–739) lets two 25% positions sit in one stock (50%), above his 30%.
   - Fix:
     - Correct §6.
     - Make the primary the SSoT's article sizing, 1% risk with a 20% cap (rec, since the read is "his rules"). Or keep 0.5% / 25%
       as B with 1% / 20% as a named beside row.
     - Swap the `cap_10` / `cap_33` beside rows for `cap_20` / `cap_30`.
     - Add a 30%-per-stock limit at cost (a second position takes the room left, else it is skipped and counted).
   - Settle this before the freeze: the curve arm reads the primary config, so this choice moves the deciding reading.
3. **MEDIUM — the curve arm cannot tell his picks from his days.**
   - The problem: if his picks added nothing over the same day's other breakouts, but 2020–21 lifted everything, the curve arm
     still reads STRONG. The fork would then route to "SELECTION: fix the filter".
   - Fix: the curve arm also needs his curve above the band. For example, at most 5% of band draws at or above his final equity,
     at the primary config.
   - Register a third row now: his curve strong AND the band at or above it → the dates / market carry it, not the stock picks.
   - Also correct §8's "about 100R at 0.5%". §9 expects the 25% cap to bind on most calls, and no-margin allows at most four 25%
     slots, so the real bar is stricter than §8 states.
4. **MEDIUM — the identity-break exclusion after E is an outcome-linked filter on the deciding population.**
   - The problem: `break_post` (1066–1075, R8 l.321) drops an event whose (E, E+120] window holds a break. A "jump" break is a
     >70% one-session move with no volume event, or with a split-factor change (ext_bars.py:16–20).
   - It drops the event even when the trade exited long before the break.
   - Fix: cut the walk's `fwd` at the session before the break, which is how `forward_window` already treats a hole, instead of
     excluding the event.
   - Result: a trade that exited earlier stays mature and counted. One still open becomes `degraded`: in no per-trade number,
     booked in the account, counted.
5. **LOW — the ON-E calls in the deciding set, and the overlap wording.**
   - The fork decides on all 236 calls. 109 of them rest only on a label said on E, so they may have been picked after the fill.
     `ts` is a video offset, so they cannot be split at the fill minute.
   - Fix: print both fork arms on the strictly-before 127 beside the verdict. No rule changes.
   - Fix the wording at l.39, l.220 and §12: 119 calls carry an on-E label, 109 rest only on one, and 10 carry both. 119 + 127 =
     246 ≠ 236.
6. **LOW — a gap in the freeze lock.**
   - `agents/market_intelligence/constants.py` (`ENTRY_SLIPPAGE_PCT = 0.001`, the default every fill pays in `cb.entry_variants`)
     is not pinned.
   - Fix: add it to `CODE`, and assert `cb.ENTRY_SLIPPAGE_PCT == 0.001`.
7. **LOW — R6 wording.** It says the weights are his "FILLED-trade shares". The code uses filled AND mature trades (1200–1203).
   Align the doc.
8. **LOW — a latent crash.**
   - An `empty` event is kept (916–917), but `S["files"][e][d]` (1056) raises a KeyError when the date file is absent. Today 0
     events are empty.
   - Fix: use `.get` and let the entry abstain `no_minutes`.
9. **LOW — degraded walks.** Delistings and buyouts inside the horizon are booked in the account but are in no per-trade number.
   Print their count and summed booked R beside l.1195.
10. **NOTE — the band's max-drawdown column.** "Share of draws ≥ his" (1329) reads inverted for max drawdown, where higher is
    worse. Label it.

**After the fixes:** every fix touches `replay_module`, `replay_tests` or `doc_body`. So the main loop re-runs `01_replay.py --dry-run`
to regenerate the pins, then pastes the freeze record and commits. Only then does it make the one real run.
