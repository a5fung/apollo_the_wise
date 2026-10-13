-- the four era-E predicates after the 10-13 literal move (read-only)
\echo live_fill_counterfactuals_first_read_482
-- ⚠ ERA-SCOPED (#631, 2026-09-09). Counts fills under the CURRENT exit era ONLY, never a
-- raw count: the retraction this task answers fired a count predicate on a population
-- 27/28 of which ran under a replaced rule. BOTH the era label AND the date literal are
-- pinned by tests/test_exit_counterfactual_consolidation_631.py to rule_eras.py (label =
-- exit_era_label(<latest exit switch>, 'magna53'); date = the LATEST exit switch), so the
-- next exit-rule flip goes RED here until this predicate moves with it — instead of
-- silently grading a mixture, which is what a prose "bump in the same commit" comment
-- failed to prevent on 09-06 (exit_tune_cohort_review sat at 08-16 for three days).
-- A fill counts when its control PAIR is settled: live_actual (the real result) AND
-- live_replay (the live rule walked on the same bars — a counterfactual is quotable only
-- where these agree). NOT "all arms settled": abstains are per-arm and legitimate (no
-- ADR, same-bar stop+target, no character profile) and every arm's own n is stated in
-- the read.
SELECT CASE WHEN to_regclass('mi_live_fill_counterfactuals') IS NULL THEN 0
            ELSE (SELECT COUNT(*) FROM (
                    SELECT trade_id FROM mi_live_fill_counterfactuals
                    WHERE account_mode = 'live' AND signal_type = 'magna53'
                      AND exit_era = 'era_e' AND alert_date >= DATE '2026-10-13'
                      AND arm IN ('live_actual', 'live_replay') AND outcome = 'settled'
                    GROUP BY trade_id HAVING COUNT(DISTINCT arm) = 2) complete) END;

\echo exit_tune_cohort_review
-- ⚠ ERA-SCOPED 2026-08-22 (operator: "fix the trigger, stop wasting my time").
-- BEFORE: this counted EVERY closed live trade ever, so the n=20 run on 2026-08-22
-- fired on a 22-trade record in which 21 trades ran under exit rules that had
-- ALREADY been replaced — it re-measured a stop the operator had widened on 08-16
-- and told him the old one was too tight. Redundant by construction.
-- NOW: count only trades ENTERED under the exit rules being tested. Bump
-- _EXIT_ERA_START in the SAME commit as any future exit-rule change, or this
-- review will once again grade a mixture dominated by superseded rules.
-- _EXIT_ERA_START = 2026-09-06 (era D: the operator-signed +8R partial / +3R price-armed
-- breakeven, #545). ⚠ 2026-09-09 (#631): the 09-06 flip did NOT bump this — it sat at
-- 08-16 for three days, exactly the drift the paragraph above warns about, and a prose
-- rule could not stop it. NOW MECHANICAL: tests/test_exit_counterfactual_consolidation_631.py
-- pins this literal to rule_eras.py's latest exit switch — the next flip goes RED here
-- until this predicate moves with it.
SELECT LEAST(
  (SELECT COUNT(*) FROM mi_live_trades
    WHERE account_mode = 'live' AND status = 'closed'
      AND created_at >= DATE '2026-10-13'),
  -- ── RUNNER GATE (2026-07-30, REPLACED a winner gate the operator broke) ──
  -- My first version required 2 live WINNERS. The operator caught the catch-22:
  -- "if our sell rules need improvement, current 3-day profit take may not yield
  -- 2 winners for a long time." Exactly right — live trades die at 1.5 days, never
  -- reach the day-3 partial, and always close ~-1R, so the gate waited on an
  -- outcome the rule under test structurally prevents. It could never open.
  --
  -- THE FIX, and the conceptual correction: the COST of a profit-taking rule is
  -- priced by trades that RAN PAST the trigger, NOT by trades that WON. MANE
  -- reached +7.92R and closed -0.23R: take 1/3 at +2R and you can price exactly
  -- what that third gave up on the run to 7.92R. A give-back trade is a PERFECT
  -- laboratory — you have the whole path. I had conflated "did the trade work"
  -- with "can we price the rule"; they are different questions.
  --
  -- So: count live trades whose peak ran WELL past any candidate trigger, which
  -- is what makes both benefit AND cost measurable. Satisfiable under the current
  -- rule, because running does not require surviving to day 3.
  --
  -- ── RE-KEYED TO ADR 2026-08-01: the gate was written in R, and R is not a unit ──
  -- docs/analysis/508_exit_trigger_unit_2026-08-01.md measured entry-to-stop
  -- distance at 0.15-1.17 ADR across the same 12 live trades - a 7.7x spread. So
  -- `peak_r >= 4` does not mean "ran a long way"; it partly means "had a tight
  -- stop". CRSR (paper) recorded +12.36R on 0.06 of a daily range. The gate was
  -- keyed in the very unit the review exists to interrogate - it inherited the
  -- flaw it was built to study, and it counted the evidence 1-vs-5.
  --
  -- Threshold picked to PRESERVE THE ORIGINAL INTENT, not to manufacture
  -- readiness: 4R against a ~2R candidate trigger was "~2x past it", so the ADR
  -- analogue of 1.5x the 1-ADR candidate is peak_adr >= 1.5 -> today 2 trades
  -- (NVCR 2.35, SMCI 1.68) -> 20. Note `peak_adr`, NOT `peak_atr`: peak_adr is
  -- what the recorder actually stores; no peak_atr column exists.
  --
  -- ⚠ This re-key does NOT open the gate. LEAST() still binds on the FIRST term:
  -- 12 closed live trades vs threshold 20. The runner term simply stops being the
  -- artificial blocker, so cohort size - the honest constraint - governs again.
  (SELECT 10 * COUNT(*) FROM mi_sell_discipline_records
    WHERE account_mode = 'live' AND peak_adr >= 1.5
      AND created_at >= DATE '2026-10-13')
);

\echo exit_tune_bull_regime_read
-- ⚠ RE-KEYED 2026-09-02 after run 1 (n=10). Counting stamped-Bull closes ALONE cannot
-- answer the question: every Bull close ran under the post-08-05 exit stack and every
-- non-Bull close but one (CRWD 08-27) ran the bare ORB-low stop, so a Bull-vs-non-Bull
-- realized-R contrast is an exit-STACK contrast. The cell that breaks that confound is
-- non-Bull closes ENTERED under the current stack (created_at >= 2026-09-06, the parent's
-- _EXIT_ERA_START — bump both in the same commit as any exit-rule change; MISSED on 09-06,
-- repointed 2026-09-09 (#631) and now pinned to rule_eras by test). LEAST() fires
-- only when BOTH hold: stamped-Bull >= 20 AND non-Bull era-C >= 5 (the 4x scales the second
-- term onto the same 20 bar, the parent's idiom). `regime` is the ENTRY STAMP = the prior
-- session's regime row (live_tracker.py:522 reads regime_date <= today at 09:31; the nightly
-- writes today's row at 17:00 ET) — the operator-ruled basis (08-08), never the date join.
SELECT LEAST(
  (SELECT COUNT(*) FROM mi_live_trades
    WHERE account_mode = 'live' AND status = 'closed' AND signal_type = 'magna53'
      AND regime = 'Bull'),
  (SELECT 4 * COUNT(*) FROM mi_live_trades
    WHERE account_mode = 'live' AND status = 'closed' AND signal_type = 'magna53'
      AND COALESCE(regime, '') <> 'Bull'
      AND created_at >= DATE '2026-10-13')
);

\echo runner_rule_sweep_recut
-- ⚠ RE-SCOPED 2026-09-19 (#669 audit). The 2026-08-29 read was VOIDED eight days later by the
-- #545 exit flip (2026-09-06: +2R partial -> +8R plus a price-armed breakeven, magna53) - the
-- exact "change to the exit stack" the entry says voids the read - and this predicate could
-- not see it: mi_safeguard_state holds feature toggles of every kind, not exit rules. What it
-- DID count was `live_yoy_recovery_inwindow|global` (09-05) and `theme_birth_gate|paper`
-- (09-13), two toggles that touch no exit, so it read 83 and would have fired 09-29 saying
-- "a safeguard moved" about the wrong two rows while the real void went unmentioned.
-- NOW: (a) the trade arm counts era-D live MAGNA53 closes only - a Run-U re-cut under the
-- current control needs trades that RAN under it; (b) the safeguard arm counts LIVE-mode
-- transitions since the era start (paper/global toggles do not void a live exit read).
-- The era literal is pinned to rule_eras.py's latest exit switch by
-- tests/test_exit_counterfactual_consolidation_631.py, so the NEXT flip goes RED here.
SELECT
  (SELECT count(*) FROM mi_live_trades
    WHERE status = 'closed' AND risk_dollars > 0
      AND account_mode = 'live' AND signal_type = 'magna53'
      AND created_at >= DATE '2026-10-13')
  + 40 * (SELECT count(*) FROM mi_safeguard_state
           WHERE account_mode IN ('live', 'global')
             AND safeguard NOT IN ('drawdown_breaker', 'kill_scale_band', 'manual_trading_halt')
             AND last_transition_at >= DATE '2026-10-13');
