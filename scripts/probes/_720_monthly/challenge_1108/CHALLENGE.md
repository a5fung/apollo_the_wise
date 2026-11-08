REVISE-FIRST: three lenses are computed on wrong units or a different statistical test, so they would show a false reading. The arm-comparison ladder can never fire. Several sections the plan promises are not built.

All 41 tests pass (`tests/test_720_monthly_review.py`), but that is part of the problem: the made-up test data uses the wrong units, so the unit bugs pass.

**Lenses that would read wrong or can never fire**
1. **No arm can ever reach WATCH or PROPOSE.** `run_review.py:401-403` returns NOTHING if any readable era LOST. In the published 11-06 table every one of the 13 arms lost era C or D, and plan §1.3 says those eras are closed baselines that never change. Fix: judge WON/LOST on the current era only and print older eras as context, or let an older era veto only when it ran the same rule the arm varies. The main loop picks one before freezing; it does not go to him.
2. **Stop-too-wide mixes a fraction with a price.** `mi_ep_missed_outcomes.max_high_5d` is stored as (high − open_d0)/open_d0, and its window includes the gap day itself (`missed_outcomes.py:650-692`). `run_review.py:827-830` treats it as a price, so 0.12 becomes −99.9% and the rejected cohort never hits. Fix: drop that column and use `mfe_5d_pct` on daily bars for both cohorts. Fix the test row at `test_720_monthly_review.py:421` (`max_high_5d: "112"`) to the fraction prod writes.
3. **The Fisher test is not the YAML's.** `run_review.py:643` is one-sided. On the YAML's own 09-16 numbers (4 of 11 vs 17 of 25) it gives p 0.080, so the runner says KEEP. The YAML used two-sided (0.141) and said CANNOT TELL. Fix: use two-sided as the YAML does, or amend plan and YAML and record that the 09-16 reading changes. Main loop decides.
4. **The admitted control is not date-matched.** `run_review.py:985` uses live L1 trades closed since 08-16. The rejected cohort is both account modes since 05-05, and the YAML's control is "entered magna53 rows" over the same dates (n 25). Fix: add a capture query for entered magna53 rows since 05-05, and extend `daily_bars.sql` to those tickers.
5. **The breakout width rule always passes.** The record's `width` is a fraction, (level − stop)/level (`breakout_v1_entry.py:530`), but `run_review.py:566-571` tests `w <= adr20 × break_price`. Plan §6 line 191 has the same wrong formula. Fix: `w <= adr20`, and change the test fixture from `width: 2` (dollars) to a fraction.
6. **The runner-shape count is wrong two ways.**
   - `run_review.py:455-458` has no upper bound, so a stop filled at +5R counts as a give-back to breakeven. Fix: require |price − entry| ≤ 0.05R.
   - In eras D/E the give-back that matters is breakeven armed at +3R, stopped at entry, with no +8R partial. That shape has no `partial_profit` leg, so the count reads about 0 by construction. Fix: key on the sell-discipline peak ≥ 3R plus a breakeven stop, not on a partial leg.
7. **Selection.**
   - `run_review.py:947` makes one labelled name a WATCH, against §2's under-3 rule.
   - "Never alerted" is decided from `mi_live_trades` only. Fix: join `mi_ep_alerts`.
   - CHPT 09-03 is a settled exclusion and would come back as WATCH every month. Fix: exclude the declared abstentions in `tests/fixtures/must_not_miss_eps.py`.
   - The breakout grades table `mi_breakout_v1_grades` stays empty since his 11-05 ruling to grade on chart sheets. Fix: read grades from where chart-sheet grades are recorded, or drop that test.

**A broken pipeline would read the same as a quiet month**
8. **Recorder gaps.**
   - A dead counterfactual recorder shows as "too few trades", the same as a thin era. Fix: print, per era, fills / fills with recorder rows / settled pairs, and name every fill older than N sessions with no rows as a recorder gap.
   - `run_review.py:511` counts a NULL `fill_vs_trigger_pct` as a ≤1% fill. Fix: count NULLs separately.
   - `breakout_v1_missed_unreadable` rows are captured but never read, and `missed_records` (`:552`) drops bad JSON silently. Fix: count both on the page.
   - The 15:55 missed-by-slots step's proof of running is the `breakout_v1_entry_day` row, which is not captured. Fix: add it to `audit_breakout.sql`.
   - The breakout on/off state also lives in `mi_strategies.enabled` and the env default, not only `mi_safeguard_state`. Fix: capture `mi_strategies`.
9. **Exit reason labels.**
   - The depth sale books its leg as `sma_trail_stop` (`order_manager.py:6105`).
   - `gap_through` and `intraday_stop` are never written as leg reasons. A gap-through stop books as `stop_hit`; the only `gap_through` in that code is an action return, not a leg (`order_manager.py:1521`).
   - Fix: take the reason list from the five writers (`order_manager.py:1318/4928/6389/6551/6626`). Count era-E depth sales as `exit_rule='depth'` plus a final `sma_trail_stop` leg.

**Replay match test (§5): too loose and keyed to the wrong date**
10. **Fidelity.**
    - `run_review.py:225-245` models the live share-sizer from the fill day. The +8R partial can fire after 10-12 on a fill made before it.
    - The bound is added on top of the 10%, so any other replay error up to 2.67R passes on 1-share fills.
    - Fix:
      - Take the live fraction from the trade's real `partial_profit` leg shares (in `exits`).
      - Re-weight the `live_replay` legs to that fraction and compare with max(0.25, 10% of live R) and no extra bound.
      - On fills that pass only this way, compare arms against `live_replay`, not `live_actual`.
      - In `classify_fidelity_miss` (`:267`), test for a session/reason difference before calling a miss whole-share.

**Promised in the plan but not built**
11. **Missing from `run_review.py`:**
    - the regime table (the 482 review's §5, claimed in plan §7)
    - the safeguard-transition check (`safeguard_transitions.csv` is captured but never read)
    - the admission-era mix
    - the breakout fill vs list level, the fill-stop decision mix (`FILL_STOP_EVENT` is defined but unused) and the thirds count
    - the depth-sale cost
    - the fill-minute histogram
    - `real_risk_vs_trigger_risk`, and stop-width medians outside the tail
    - the tail fields: fill minute, fill vs trigger, peak session, exit legs, his label, admission era, the 10-session high after the exit
    - a per-trade window list, needed for the DoD's "every closed trade accounted for"
    - a count of trades filled before 08-16 and closed in the window
    - Smaller deviations:
      - "Disappoints" (`:504`) sums real-trade R, but the plan and the 11-06 fact use capped-dollar R.
      - The breakout seated cohort is all breakout trades, not the same days as the missed names.
      - The slippage verdict ignores losses in other eras.
12. **The printed review counts are not the YAML predicates.** `predicates.sql` copies only part of two of them: for `exit_tune_cohort_review` it drops the `LEAST(...)` runner gate, and for `runner_rule_sweep_recut` it drops the `+40 ×` safeguard arm and its exclusion list. Fix: copy each `predicate_sql` verbatim from `data_gated_reviews.yaml`, and reuse that exclusion list for the safeguard check.
13. **Conflicts with the folded YAML reviews.**
    - `live_fill_counterfactuals_first_read_482` says "segment first by admission_era, never pool". Plan §1.3 (lines 66-67) leaves admission eras unsplit.
    - The #718 open-below-floor change (11-03) sits inside era E with no admission-era stamp. Fix: print pre- and post-11-04 counts on every era-E lens.
    - The YAML still says 0.25R for fidelity. Fix: §7's pointer edits must also replace that bar. The DoD item "the five reviews point at this cadence" is not covered until those edits are made.
    - `exit_tune_cohort_review` asks for the forensic on every trade, not only the tail. At 3-5 trades a month that is cheap. Fix: run it on every window trade.
14. **The planner's "his or the main loop's call" list would reach him as one-off forks.** None of it is THE LINE: first-window start, the breakout absence wording, the VICR/KOD/OKTA/CLS share outcomes, the YAML pointer edits. Fix: the main loop decides each one, writes it into plan §8 as I12+, and nothing goes to him outside the review page.

Action: none for him; the main loop revises the plan, runner and tests, then re-runs this challenge before freezing.

Files:
- /Users/alvinfung/apollo_the_wise/.claude/worktrees/720-plan/docs/analysis/720_monthly_review_plan_2026-11-08.md
- /Users/alvinfung/apollo_the_wise/.claude/worktrees/720-plan/scripts/probes/_720_monthly/run_review.py
- /Users/alvinfung/apollo_the_wise/.claude/worktrees/720-plan/tests/test_720_monthly_review.py