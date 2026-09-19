# #669 — the gated-review registry, audited entry by entry (2026-09-19)

**Operator 2026-09-16:** *"So many wrong info and action from review, this needs to be cleaned up to
avoid so much wasted resource and wrong info."* Six failures in one day were five different defects,
and only one of them was a review that could not fire — the rest FIRED and sent us at the wrong work.

**Result in one line:** all 60 open entries triaged (54 pending + 6 deferred — the task line said
55; the registry held 54 pending on 2026-09-16 and holds 54 today, nothing closed in between, so 55
was a miscount). **19 re-gated, 1 closed, 40 verified** — of the 40, 18 now carry the two new
declaration keys and 22 are the counted backlog the gate prints. Every rewritten predicate was
re-run on prod from the edited registry text and returns the value recorded in its `can_fire:`.

Read this with the registry open; each row's evidence lives in that entry's `can_fire:` block.

## Method and population

**Population:** every entry in `data_gated_reviews.yaml` with `status: pending` or `deferred` at
commit `1a2d7f33` (origin/main, 2026-09-19) — n = 60 (54 + 6); `done` entries excluded. The same set
was pending at `b0821048` (2026-09-16), so nothing entered or left between the task being filed
and this audit. Each entry was read in full (question, predicate, action, every resolution block)
and its predicate executed against prod read-only in ONE batched psql run on 2026-09-19 (captured
to a file, read many times), followed by targeted read-only checks where a judgement needed a
number: table columns, per-month accrual, era boundaries, join fan-out, emitter presence. Every
rewritten predicate was then re-run from the edited registry text in a second batch and its value
recorded in the entry's `can_fire.predicate_runs`. Window: all history each predicate reads, as
written; no sampling. Judgements (population match, answered elsewhere, instrument, rule, era)
are mine from the entry text plus those reads — they are not textually decidable, which is why
the gate forces the question rather than checking the answer.

## The seven questions, per entry

Columns: **pop** = does the predicate count rows the action can act on · **elsewhere** = is the
question already answered somewhere else · **instrument** = does the method read something known
broken/changed · **rule** = can the decision rule return more than one answer · **era** = does the
measure straddle a dated criteria change in any table the METHOD reads (not just the cohort window).
`value` = the predicate on prod, 2026-09-19 (`old→new` where the predicate changed).

### Pending (54)

| # | entry | value | pop | elsewhere | instrument | rule | era | disposition |
|---|---|---|---|---|---|---|---|---|
| 1 | chart_reading_review_cycle | 11 | yes — timer wider than the sample, declared | no | alerts + closes, fine | n/a (cadence) | anchored at last sample | **RE-GATED** threshold 40→20: the 09-10 evidence said "fortnightly"; alert volume fell 51→5/week, so 40 was an 8-week cadence |
| 2 | runner_rule_sweep_recut | 83→2 | **NO** — every strategy, both modes, ANY toggle | no | Run-U replay + live closes; #605 survivor-only caveat | two arms, yes | **YES** — the 09-06 exit flip voided the 08-29 read and the predicate could not see it (it watched feature toggles; the 83 came from `live_yoy_recovery_inwindow|global` + `theme_birth_gate|paper`) | **RE-GATED** era-D live magna53 closes + live-mode toggles; era literal pinned to rule_eras in test_631 |
| 3 | kill_scale_bands_quarterly_review | 30 | yes (YAML filter ≠ evaluator filter; agree at 30 because all live closes are magna53) | no | total_pnl; risk_dollars_actual NULL → fallback, noted in entry | evaluator arms | known and already surfaced as his fork (calibration on orb-low stop; trailing-20 spans three exit eras) | **verified** (backlog) |
| 4 | extension_cap_75_recheck | 14 of 15 | yes | no | missed-outcomes filtered on last_refreshed_at (#583 named) | reports | anchored at the cap's deploy | **verified** (backlog) — ready within days |
| 5 | rs_theme_dash_forward_returns | date | n/a | **partly** — 09-07 ruling: themes not judged on returns until the engine is fixed | mi_themes is CHANGING (#486/#655/#660) | n/a | instrument changing | **RE-GATED** 10-01→11-01 behind #486; action checks the ruling before building |
| 6 | unified_allocator_phase_1b | 0 | yes (contested post-move days) | 09-14 ruling recorded (A then B) | mis-timed, not broken; `< 09:30` clause enforces post-move rows | yes | self-enforcing | **verified** + 2 keys |
| 7 | drawdown_breaker_active_effectiveness | 0 | yes | 07-30 verdict: unproven on live; event-gated since | event shape proven by paper rows | yes | single era | **verified** (backlog) |
| 8 | stop_too_wide_outcome_cohort | 10 | yes | no | raw bars; the admitted control must NEVER be missed-outcomes (09-16) | **NO** — absolute bars could only say REVISIT (rejected 36%/+8.6% cleared them while the admitted book ran 68%/+14.6%) | cohort single-era; admitted composition moves with admission changes — declared | **RE-GATED** control-relative matrix with a third answer (cannot tell → re-arm); + 2 keys |
| 9 | trade_stream_stop_placement_without_orders_row | 0 | partial — proxy; site 2's event has no emitter | ruled 09-06 | 1 of 3 events writer-less (#633/#635) | tripwire | current-state | **verified** + 2 keys (declared, not fixed) |
| 10 | theme_as_ep_signal | 155 | yes (both strata) | parked by the 09-07 ruling | fwd_5d is a high-watermark; theme labels contaminated pre-#486 — both noted | yes | known; parked to 11-01 | **verified** (backlog) |
| 11 | phase6_meta_rubric_gating | 0 | yes (both empty for the same structural reason) | keyed to #335 | event ABSENT until #335 flips composite authority | yes | none yet | **RE-GATED** — the ruling moved from a `#` comment into `zero_verdict:` (from 09-29 --audit would have listed it unruled); can_fire |
| 12 | catalyst_rubric_quarterly | 0 | same as 11 | no | absent event | yes | none | **verified** (backlog; earliest 12-29, exempted by name in test) |
| 13 | rel_volume_small_cap_biotech_floor_evidence | 8→5 | **NO** — counted ALERTS in a rolling 90d window; action needs entry-aware CLOSES (7 of 12 alerts never filled) | no | pnl + as-of scores (LATERAL fixed 07-30) | yes (WR buckets) | exit eras inside the cohort — segment | **RE-GATED** closed-trade join, anchored, declared |
| 14 | gate5h_value_invariant_proposal | 0 | yes | ruled 09-11 | the success-firing clause was removed 09-08 | tripwire | none | **verified** + 2 keys |
| 15 | intraday_undercut_rally_signal_n10 | 4→0 | yes | no | detector rows + closes | yes | **YES** — all 4 counted rows (COMP, TTMI, CPSH, SNOW) predate the 06-27 parent rebuild; sibling was fixed 09-15, this one was not | **RE-GATED** era clause; zero_verdict (RUM/PURR unsettled, not absent) |
| 16 | intraday_support_test_signal_n10 | 9 | yes | held by priority | detector rows + closes | yes | scoped 09-15 | **verified** + 2 keys |
| 17 | orb_bar1_wick_outlier_persistence_filter | 5 | yes (ORB entries; account exemption declared) | no | the 87% 9:30-bar gap is CLOSED — 58 of 58 entries since 06-18 have the bar | yes | rolling window replaced by the 06-18 anchor; outcomes span exit eras — segment | **RE-GATED** anchored window |
| 18 | partial_exit_hardening_n7_clean_cycles | 7 of 7 | yes | partly — the cutover it gated happened 06-22; still valid as the architecture-stability gate | anchor fixed 08-15 | yes (3) | post-split | **verified** (backlog) — **READY on 09-21** |
| 19 | orb_entry_stuck_pending_new | 0 | yes | ruled 09-06 | order mirror | tripwire | post-fix | **verified** + 2 keys |
| 20 | wave_c_part2_boost_demotion | 0 | yes (slice) | 08-06: Part 2 retired, tripwire kept | LIKE parse proven | tripwire | n/a | **verified** (backlog) |
| 21 | ep_mcap_floor_500m_review | date 09-22 | n/a | **partly** — #624's low-cap lane records this population (10 rows / 7 settled); the 620 check-in found BCAR/MASS killed only by this floor | lane replays + scan log | reports | segment admission eras | **RE-GATED** action re-pointed at #624 + 620; only the 10-15% gap band still needs the hand query |
| 22 | perplexity_transient_timeout_alert_noise | 5 | **NO** — "6 in a week" vs cumulative since 06-29 | yes — the data answers it: 5 in 82 days, 0 in the last 14 | audit events | **NO** — could only ever say "chatty", once enough calendar passed | n/a | **CLOSED** by its own rule ("under threshold → default is fine, mark done") |
| 23 | htf_breakout_paper_graduation | 5→4 | yes (takeable settled) | HELD by operator 09-15 | **#667**: the fifth "capture" (CDNA 07-31) was a fill the break day never reached; reset 09-18, count fell to 4 | yes | table post-rebuild; #667 reset rather than re-scored | **verified** + 2 keys (instrument caveat recorded) |
| 24 | exposure_family_cap_promotion_r2 | 0 | yes | re-aligned 09-09 to his 09-07 ruling | heartbeat proves the check runs | tripwire | n/a | **verified** (backlog) |
| 25 | prompt_debias_clean_cohort_215 | 20 | yes | no | pass-record run_at unchanged (08-27) | yes | partial — manual re-date until #215's emitter | **verified** + 2 keys |
| 26 | b6_gate_inversion_post_rescale | 4 | yes | no | 6-of-46 orphan scored rows, named in action | yes (tail first) | scoped 08-22 | **verified** + 2 keys |
| 27 | tqs_junk_accrual | 1 | yes | no | junk tier reachable (MRNA 08-19), rare | yes | admission changes 08-27/28 — segment | **verified** + can_fire — **HIS FORK**: 30 ≈ five years at 1 junk in 8 weeks, and 30 is Stage 4's evidence bar for a live-entry gate, so not lowered here (keep / lower / retire Stage 4) |
| 28 | regime_sizing_vs_tail_recheck | 3 | **NO** — joined regime by DATE; the operator-ruled basis (08-08) is the ENTRY STAMP (cells differ: Bull 6/11 vs 7/15; value agreed by coincidence) | no | peak_r + regime stamp | reports | R-unit change segmented in action | **RE-GATED** entry-stamp join |
| 29 | exit_tune_cohort_review | 0 | yes | no | live closes + records | recurring ladder | pinned to rule_eras | **verified** (backlog) |
| 30 | exit_tune_bull_regime_read | 8 | yes | run 1 done 09-02 | same | recurring | pinned | **verified** (backlog) |
| 31 | cooldown_admission_unassumed | 45 | subset as trigger, declared | connected: 620's ALOY (9.8x) was killed only by this cooldown | scan log + closes; replay caveat named | yes | segment admission eras | **RE-GATED** — the prose stall clause ("by ~2027-01 run anyway") is now an arm that fires 2027-01-05; accrual is 20/15/6/3/1 a month |
| 32 | htf_sizing_left_on_legacy_formula | 0 | yes | ruled 09-11 | mi_strategies.phase | tripwire | n/a | **verified** + 2 keys |
| 33 | lane2_widen_reconsider | 6 | yes | no (bars pre-declared) | own proposals excluded; blind spot named | yes (3) | v2 era | **verified** + 2 keys |
| 34 | judge_divergence_marginal_high_signal | 8 | yes | no | fwd_5d is a high-watermark — say MFE, never "return" vs a close-to-close benchmark | yes (3) | model pair re-resolved at query time | **verified** + 2 keys |
| 35 | rt_admission_recut_post_2r_exits | 4 | yes | **partly** — his 08-19 correction moved the question; #559 carries it and this entry is aligned to it | planned-risk R, declared | yes (3) | scoped 09-06 | **verified** + 2 keys |
| 36 | alert_rank_shadow_out_of_sample | 13 | sessions vs rows — a running read, declared | no | join fan-out without SOURCE, fractional units, 20d column returns a number for an unelapsed window — all named | running read with confidence label | out-of-sample by construction | **verified** + 2 keys — **HIS FORK** (presentation): operator_asks renders a one-line running read as "MY WORK IS DUE" daily; the 08-18 threshold-1 conversion is deliberate and test-pinned, not reversed |
| 37 | bracket_geometry_variants_parked | 8 | yes | no | probes + shadow lane | count + "disappoints" | **YES** — exit-sensitive metrics ("destroys the +2R partial") span era C/D; probes have no ERA_D | **RE-GATED** action: add ERA_D at 09-06; predicate kept (stop geometry single-era, reopen trigger is his framing) |
| 38 | minute_pull_620_trigger_parked | date 10-17 | n/a | check-in | complete 20-session windows now (was censored at 8) | check-in | matured cohort | **verified** + 2 keys; cross-refs to 31 and 21 (same fork, three sides) |
| 39 | delayed_entry_shadow_first_read | 3029→1325 | **NO** — counted 1,704 BACKFILL rows, the very set the policies' p* were calibrated on | no | recorder + settle | yes (bands) | prospective ≥ 08-31 | **RE-GATED** prospective-only |
| 40 | delayed_entry_adr_stop_variant_616 | 161→160 | nearly (one August row) | no | same settle path | yes | prospective ≥ 09-02 | **RE-GATED** fire_date guard (the question says "recorded from 09-02"; the SQL did not) |
| 41 | delayed_entry_adr_stop_variant_025_545 | 112→111 | nearly | no | same; the #545 composite it is compared to is a backfill figure — declared | yes | prospective ≥ 09-02 | **RE-GATED** fire_date guard |
| 42 | ep_slot_ranking_watch_533 | 2 | yes | no | to_regclass guard; closes join | yes (3) | post-flip only | **verified** (backlog) |
| 43 | d1_universe_floor_dollar_volume_606 | 12 of 15 | yes (reject-side days) | no | shadow table | yes (3) | n/a | **verified** (backlog) |
| 44 | same_day_liquidity_recheck_584 | 12 of 20 | yes | no | column-guarded | yes (3) | n/a | **verified** (backlog) |
| 45 | judge_signal_wiring_effect_2026_09_01 | 14 | yes | no | "judge_signal_trace rows" do not exist under that name anywhere in the repo | yes (3) | **YES** — the 101-row baseline is 93 rows graded before the 08-27 rubric v4 axis-split + 6 after; the post-fix cohort is all v4 | **RE-GATED** action: era-split baseline, like-for-like cell named as thin (n=6) |
| 46 | analyst_estimates_60d_accrual_333 | 11 | yes | no | recorder | STEP-0 | n/a | **verified** (backlog) |
| 47 | live_fill_counterfactuals_first_read_482 | 2 | yes (pinned) | no | ONE recorder | yes | pinned | **verified** (backlog) |
| 48 | sustain_reject_tradeable_miss_rate_593 | 0 | yes | no | replay walker; the 10% was calibrated on the retired price-move basis — his question, already in the entry | tripwire | admission_era segmented | **verified** (backlog) |
| 49 | stop_reprotect_floor_first_fire_600 | 0 | yes | ruled 09-09 | emitter verified | tripwire | n/a | **verified** (backlog) |
| 50 | gap_near_miss_tradeable_miss_rate_617 | 0 (181 decided, 1 at ≥4R = 0.6% vs his 5%) | yes | **the action contradicted the predicate**: it still said "≥30 rows, then ask him what rate" while the predicate already carried his 5%/100 — a fire would have re-asked an answered question | phantom column removed 09-09; runs | rate gate, yes | pooled deliberately, action segments | **RE-GATED** action steps 2-3 rewritten; zero_verdict; can_fire (kind stays `accrual`, test-pinned) |
| 51 | lowcap_lane_graduation_624 | 0 (7 settled / 6 tickers) | yes (pinned) | no | lane replays | 8 conditions + refuse list | replay_exit_era per row | **verified** (backlog) |
| 52 | theme_relevance_labeling_cycle | 0 | yes since 09-16 | no | 44 of 44 labels verified | cadence | anchored 08-04 | **verified** — its can_fire was STALE ("returns 80", "30 against 80") from before the stratum fix; refreshed + 2 keys |
| 53 | spiky_guard_first_engagement | 0 | yes | no | stamp RED-proven; the zero's residual named | tripwire | post-floor | **verified** + 2 keys; predicate_runs refreshed on the post-#633 form (first prod run) |
| 54 | sync_position_gone_first_real_vanish_597 | 0 | yes | ruled 09-15 | emitter + job runs | tripwire | n/a | **verified** + 2 keys |

### Deferred (6)

| # | entry | value | pop | elsewhere | instrument | rule | era | disposition |
|---|---|---|---|---|---|---|---|---|
| 55 | narrative_theme_discovery_promote_gate | 5 (30d) | yes | **partly** — the 09-14 Lane-2 LEAVE ruling and the 09-07 returns ruling each settle a half; the 10-01 check-in must not re-ask them | candidates table | yes | rolling 30d is fine for a deferred item | **verified** (backlog) |
| 56 | catalyst_discovery_loop_sequencing | 201 | yes | gate clear since 07-13; big-rock deferred on priority | fine | n/a | n/a | **verified** (backlog) |
| 57 | l2_baseline_window_trending_metrics | 58 | yes | no | audit events | "≥4 of 6" was written for n=6 — at 58 read it as a rate (≥2/3) | n/a | **verified** (backlog) |
| 58 | theme_clustering_coherence_guard | 189→16 | **NO** — counted sector-mismatch pairs the 08-03 run had ruled 81% vendor noise; 189 on 09-19 | answered 08-03 by its own <70% rule; the stated re-open trigger (flip-flop recurring) **IS MET**: 16 themes Retired-then-alive in 14 days, 38 in 30 | mi_themes stage history | tripwire | engine changing | **RE-GATED** onto the flip-flop trigger, threshold 3; deferred date kept (11-01) — **FINDING for the theme owner**: resurrection runs ~1 theme/day; pull-forward is the main loop's call with the engine mid-repair |
| 59 | consolidation_unification_review | 26→20 | **NO** — pooled 9 old-wiring June days | NO-GO 08-09 on sample size; **the bar is now MET on the current wiring alone (20 of 20)** | shadow table | yes | scoped 07-14 | **RE-GATED** era clause — **READY**: the round-2 readout is owed (shadow→paper rungs only, per the 7/29 priority) |
| 60 | theme_assignment_steady_state_cost | 28 | yes | partly answered by data: $0.22/night this week vs $1.90 modelled | api_usage | yes (3) | n/a | **verified** (backlog; the reading is recorded here for the 10-01 run) |

## What the audit found, by the six classes on the task line

- **(3) predicate counts a population the action cannot act on — 7 more instances** beyond the two the task named: runner (every strategy/mode/toggle), rel_vol (alerts vs closes), regime_sizing (date-join vs entry stamp), delayed_entry ×3 (backfill counted as prospective), consolidation (old-wiring days), theme_clustering (vendor-noise pairs). Each is now filtered the way its action filters.
- **(4) question already settled elsewhere — 3 hard, 6 partial**: perplexity (closed on data), gap_near_miss (the action would have re-asked his 5%), ep_mcap (the #624 lane records the population). Partials are recorded in the rows above so the check-in reads the ruling first.
- **(5) method reads a broken/absent instrument — 5**: htf_breakout (#667 phantom, now reset), trade_stream (site-2 event writer-less), phase6/catalyst_rubric (event absent until #335), judge_wiring (a trace table that does not exist), plus the wick review whose instrument was thought broken (87% gap) and is now verified whole.
- **(6) decision rule with one answer — 3**: stop_too_wide (absolute bars), perplexity (cumulative count vs a weekly question), l2_baseline ("4 of 6" at n=58).
- **(7) measure straddles a criteria change in a table the METHOD reads — 5**: runner (exit flip), undercut (parent rebuild), bracket_geometry (partial +2R→+8R inside the count), judge_wiring (rubric v4 inside the baseline), rel_vol (three stop eras inside the WR cohort — segment, not re-scope).
- **Stale evidence inside `can_fire:` itself — 3**: chart_reading (rate), theme_relevance (pre-fix numbers), htf_breakout (5 → 4). A can_fire block is a dated reading, not a permanent fact; `--audit` re-runs the predicate, it cannot re-run the prose.

## Waits on him / the main loop (recorded, not decided)

1. **tqs_junk_accrual (#27)** — 30 junk rows is ~5 years away at the observed 1-in-8-weeks; it is Stage 4's evidence bar for a live-entry gate. Keep, lower, or retire Stage 4 — his call.
2. **alert_rank_shadow_out_of_sample (#36)** — presentation: a one-line running read renders as daily due work. Keep the daily running read or change how operator_asks presents `threshold: 1` running reads — his input, the 08-18 conversion stands.
3. **consolidation_unification_review (#59)** — READY at 20 of 20 current-wiring days: run the round-2 readout (shadow→paper rung only).
4. **theme_clustering_coherence_guard (#58)** — the flip-flop trigger is firing at ~1 theme/day; whether to pull the deferred date forward while the engine is mid-repair is the theme owner's call.
5. **partial_exit_hardening (#18)** reads 7 of 7 and fires 09-21; **extension_cap (#4)** is 14 of 15.

## What this does not answer

- Whether any re-gated predicate is the RIGHT question — only that it now counts what its action
  reads. A population that matches its action can still be the wrong population for the decision
  (stop_too_wide's control-relative bars are proposed, not operator-set).
- Whether the 22 untouched entries' actions would produce a correct read when they fire — they were
  judged from text and one prod value each, not run. Their `can_fire:` is still owed.
- Anything about the money path: no threshold that gates a live entry, exit, sizing or safeguard
  was moved (tqs_junk's 30 is the one that tempted, and it is recorded as his fork instead).
- Whether the theme flip-flop count (16 in 14 days) is an engine defect or an artefact of the
  in-flight #486/#655/#660 work — the trigger fires either way; the diagnosis is the theme owner's.
- The new gate cannot check an ANSWER. A thin-but-12-character `population_actionable` passes it;
  what it stops is the omission, which is what every one of the six 09-16 failures had in common.

## Not fixed here, named

- The **22 backlog entries** carry no `can_fire:` at all (listed by `operator_asks.py --audit`); each was triaged above and none needed a registry change today. The gate prints the count on every registry-touching commit.
- `runner_rule_sweep_recut`'s safeguard arm still cannot see a rule_eras flip directly (Postgres cannot read Python); the era literal is test-pinned instead, which is the same mechanism exit_tune uses.
- `gap_near_miss_617` keeps `kind: accrual` (test-pinned) although its predicate is a rate tripwire; the zero_verdict carries the tripwire semantics.
- `judge_signal_wiring`'s like-for-like comparator (rubric v4, pre-wiring) is 6 rows — the action says so and falls back to reading the grade reasons.
- `kill_scale_bands_quarterly_review`'s YAML predicate and the evaluator's filter differ (they agree at 30 today because every closed live trade is magna53) — noted in the entry since 08-26, left as is.
- `trade_stream`'s site-2 event and `prompt_debias`'s grade-surface emitter are owed on #633/#635 and #215 respectively.

## Mechanics shipped with this audit

- `check_plan._review_can_fire_gate` now requires **seven** `can_fire:` keys on a NEW or EDITED open review — `population_actionable` and `instrument_trusted` added, `era_scoped` re-defined as the eras of every table the method reads — and prints the untouched backlog as a count. A closed (`done`) review is no longer treated as a proposal. Tests: `tests/test_review_can_fire_gate.py` (the gate exercised for the first time, five RED-proven cases).
- Registry header documents `can_fire:` for the first time (it was gated since 09-09 and never described).
- `tests/test_exit_counterfactual_consolidation_631.py` pins `runner_rule_sweep_recut`'s era literal to rule_eras alongside the two exit_tune reviews (RED-proven by reverting the literal).
