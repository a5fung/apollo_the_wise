"""Guard: every `scripts/*.py` at ROOT must be on the pinned `KEPT_AT_ROOT` allowlist (#261).

WHY THIS EXISTS. #261's safe subset (5117ed1, 2026-06-17) moved 45 throwaway probes to
`scripts/probes/`, but nothing then enforced the boundary going forward -- the root count
could creep back up with no signal until the next manual audit, which is exactly what the
DoD's own WOULD-FAIL-IF describes ("the root count creeps back up, which is what happened
once already and produced the 6/20 regression"). The only guard that existed,
`test_quarterly_sweep_registration.py` (#285), import-checks REGISTERED sweep modules only --
it is blind to an unregistered new file simply dropped at `scripts/` root. RED-proven empty:
`touch scripts/_zz_redproof.py` then `pytest tests/test_quarterly_sweep_registration.py`
still passes (the new file is not in `QUARTERLY_BACKWARD_CHECK_SCRIPTS`, so nothing imports
it and nothing fails). This test closes that specific gap.

THE ALLOWLIST is not re-derived by grepping the whole repo on every test run -- that would
just re-implement the #261 safety greps (import-check + `data_gated_reviews.yaml` citation
check) as a slow, flaky-on-CI oracle. It is instead the PINNED RESULT of running those two
greps once per file (2026-09-19, alongside the #261 reorg continuation), recorded here with
a one-word reason so a reviewer can audit WHY each file stayed without re-running anything.
Reason vocabulary:
  imported-or-code-ref     grep found the bare module name inside another .py/.yaml/.yml/.sh
  code-ref:test            referenced specifically by a tests/*.py file
  code-ref:deploy          referenced by deploy.sh or a preflight/CI-adjacent .sh
  yaml-cited               cited in data_gated_reviews.yaml (a re-runnable operator review)
  cluster:_270             part of the _270_* replay cluster the #261 card named explicitly
                            as "do not move" -- kept whole, not individually re-verified
  bare-imports:_327_replay same-directory `import _327_replay` -- breaks if separated from it
  operator-tool:write      an ONGOING operator control lever (safeguard override / grade
                            authority flip), not a one-off historical fix -- #261 explicitly
                            left these at root pending the deferred ops/evals split
                            (PLAN.md #261 REMAINING: "ops/evals split of the real tools")

RED-PROOF 1 (a new unregistered probe creeps back to root -- the DoD's WOULD-FAIL-IF):
    touch scripts/_zz_redproof.py
    pytest tests/test_scripts_root_hygiene.py -> FAILS (not on the allowlist)
    rm scripts/_zz_redproof.py -> passes again

RED-PROOF 2 (the allowlist itself rots -- an entry's file gets deleted/renamed and nobody
updates this list, so it silently stops meaning anything):
    mv scripts/<any KEPT_AT_ROOT file> scripts/<any KEPT_AT_ROOT file>.bak
    pytest tests/test_scripts_root_hygiene.py -> FAILS (stale allowlist entry)
    mv it back -> passes again

Reads a directory listing only, never a module's source text -- no `# source-pin-ok` needed.
"""
import glob
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_ROOT = os.path.join(_REPO_ROOT, "scripts")

# Pinned 2026-09-19 (#261 reorg continuation). Every scripts/*.py root file at the time,
# each verified importable/code-referenced/YAML-cited or explicitly clustered/write-tool
# per the reasons above. New root file -> justify it and add a line here, or move it to
# scripts/probes/ if it's a throwaway.
KEPT_AT_ROOT = {
    "_184b_ingest_paper_exercise.py": "yaml-cited",
    "_216_jsonb_repair.py": "code-ref:test+imported-or-code-ref",
    "_270_anticipation_replay.py": "imported-or-code-ref",
    "_270_calibration_probe.py": "yaml-cited",
    "_270_cohort_run.py": "imported-or-code-ref",
    "_270_delayed_ep_replay.py": "imported-or-code-ref",
    "_270_entry_replay.py": "imported-or-code-ref",
    "_270_exit_replay.py": "imported-or-code-ref",
    "_270_harvest.py": "code-ref:test+imported-or-code-ref",
    "_270_intraday_pull.py": "imported-or-code-ref",
    "_270_rmv_cohort_probe.py": "cluster:_270",
    "_306_harvest_sweep.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "_327_anticipate.py": "bare-imports:_327_replay",
    "_327_dump.py": "bare-imports:_327_replay",
    "_327_entry_signal.py": "code-ref:test+imported-or-code-ref",
    "_327_pull_minute.py": "imported-or-code-ref",
    "_327_replay.py": "imported-or-code-ref",
    "_344_late_source_replay.py": "imported-or-code-ref",
    "_368_ingest_labels.py": "imported-or-code-ref+yaml-cited",
    "_b50_revenue_stage_threshold_backward_check.py": "imported-or-code-ref",
    "_b53_atr_normalized_gap_backward_check.py": "imported-or-code-ref+yaml-cited",
    "_b54_9m_day2_stop_atr_distribution.py": "imported-or-code-ref",
    "_b6_forward_backtest.py": "imported-or-code-ref+yaml-cited",
    "_b77_pradeep_neglect_backward_check.py": "imported-or-code-ref",
    "_b78_decliner_band_bounce_signal.py": "imported-or-code-ref+yaml-cited",
    "_b88_mna_filter_path_b_fp_rate.py": "code-ref:test+imported-or-code-ref",
    "_b92_flag_detector_graduation_evidence.py": "imported-or-code-ref",
    "_b94_intraday_flag_break_evidence.py": "imported-or-code-ref+yaml-cited",
    "_backward_check_utils.py": "imported-or-code-ref",
    "_coverage_invariant_paper_exercise.py": "imported-or-code-ref",
    "_e2e_gate5a_naked_remediation_test.py": "yaml-cited",
    "_grounded_reconstruct.py": "imported-or-code-ref",
    "_judge_replay_common.py": "imported-or-code-ref",
    "_judge_review_sql.py": "imported-or-code-ref",
    "_killscale_bands_268.py": "imported-or-code-ref+yaml-cited",
    "_partial_exit_paper_validation.py": "imported-or-code-ref",
    "_probe_ground_truth_254.py": "code-ref:test",
    "_reconcile_9m_day2_stop_clobber.py": "imported-or-code-ref",
    "_replay_88_mna_filter_fix.py": "imported-or-code-ref",
    "_verify_chart_axis_shadow.py": "code-ref:test",
    "_wave_a_grade_inflation_check.py": "imported-or-code-ref",
    "alert_rank_shadow_running_read.py": "code-ref:test+yaml-cited",
    "analyze_perplexity_boost_shadow.py": "yaml-cited",
    "audit_column_writes.py": "code-ref:deploy+code-ref:test+imported-or-code-ref",
    "audit_trade_state_demotions.py": "code-ref:deploy+code-ref:test",
    "backfill_dead_zone.py": "imported-or-code-ref+yaml-cited",
    "backfill_forward_minute_bars_562.py": "code-ref:test",
    "backfill_parabolic_car.py": "imported-or-code-ref",
    "backfill_position_extremes.py": "imported-or-code-ref",
    "backfill_splits.py": "imported-or-code-ref",
    "backfill_theme_axis_refined_signals.py": "code-ref:test",
    "backfill_theme_axis_shadow.py": "imported-or-code-ref",
    "backfill_theme_ecosystems.py": "code-ref:test+imported-or-code-ref",
    "backtest_clusters.py": "yaml-cited",
    "build_clean_breakout_cohort.py": "imported-or-code-ref",
    "check_analysis_doc.py": "code-ref:test",
    "check_execution_boundary.py": "code-ref:deploy+imported-or-code-ref",
    "check_gate_provenance.py": "code-ref:test+imported-or-code-ref",
    "check_plan.py": "code-ref:test+imported-or-code-ref",
    "check_test_source_pins.py": "code-ref:test+imported-or-code-ref",
    "delegation_gate.py": "code-ref:test+imported-or-code-ref",
    "delegation_report.py": "code-ref:test+imported-or-code-ref",
    "delegation_shared.py": "code-ref:test+imported-or-code-ref",
    "dump_unknown_cohort.py": "yaml-cited",
    "ep_delayed_capture_audit.py": "yaml-cited",
    "ep_latency_audit.py": "code-ref:test+imported-or-code-ref",
    "ep_pradeep_catalyst_tier_analysis.py": "yaml-cited",
    "ep_replay.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "ep_selectivity_breakdowns.py": "code-ref:test+imported-or-code-ref",
    "eval_catalyst_materiality.py": "imported-or-code-ref",
    "eval_catalyst_models.py": "imported-or-code-ref",
    "eval_chart_judge.py": "code-ref:test+imported-or-code-ref",
    "eval_judge_enrich.py": "code-ref:test+imported-or-code-ref",
    "eval_judge_models.py": "imported-or-code-ref+yaml-cited",
    "eval_sourcing_perplexity.py": "imported-or-code-ref",
    "eval_tape_judge.py": "code-ref:test+imported-or-code-ref",
    "eval_theme_validation_model.py": "imported-or-code-ref",
    "evaluate_kill_scale_bands.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "fetch_ep_fundamentals.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "gate_provenance_registry.py": "code-ref:test+imported-or-code-ref",
    "gdrive_backup.py": "code-ref:deploy",
    "integration_test_partial_exit.py": "imported-or-code-ref",
    "integration_test_stop_adopt.py": "imported-or-code-ref",
    "judge_backfill_replay.py": "imported-or-code-ref",
    "judge_delta_review.py": "code-ref:test+imported-or-code-ref",
    "judge_named_themes_651.py": "code-ref:test+imported-or-code-ref",
    "live_rules.py": "code-ref:deploy+code-ref:test+imported-or-code-ref+yaml-cited",
    "log_judge_envelope_change.py": "code-ref:deploy+imported-or-code-ref",
    "mna_filter_accuracy_review.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "monthly_judge_review.py": "code-ref:test+imported-or-code-ref",
    "operator_asks.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "operator_now.py": "imported-or-code-ref",
    "orb_wick_outlier_backwardcheck.py": "imported-or-code-ref+yaml-cited",
    "preflight_account_mode_literals.py": "code-ref:deploy+code-ref:test+imported-or-code-ref",
    "preflight_check.py": "code-ref:deploy+code-ref:test+yaml-cited",
    "preflight_command_parity.py": "code-ref:deploy",
    "preflight_datetime_hygiene.py": "code-ref:deploy+code-ref:other+code-ref:test+imported-or-code-ref",
    "preflight_db_updates.py": "code-ref:deploy+code-ref:test+imported-or-code-ref+yaml-cited",
    "preflight_exec_deploy_scope.py": "code-ref:deploy",
    "preflight_import_shadowing.py": "code-ref:deploy",
    "preflight_judge_eval_gate.py": "code-ref:deploy+code-ref:test+imported-or-code-ref+yaml-cited",
    "preflight_model_registry.py": "code-ref:deploy+code-ref:other+code-ref:test+imported-or-code-ref",
    "preflight_no_silent_failures.py": "code-ref:deploy+code-ref:test+imported-or-code-ref",
    "preflight_replace_order_smoke.py": "code-ref:deploy+imported-or-code-ref",
    "preflight_yaml_dupe_keys.py": "code-ref:deploy+imported-or-code-ref+yaml-cited",
    "probe_alpaca_statuses.py": "imported-or-code-ref",
    "readiness_check.py": "code-ref:deploy+code-ref:test+imported-or-code-ref",
    "reconcile_orphan_stop.py": "imported-or-code-ref",
    "refresh_missed_outcomes.py": "code-ref:test+imported-or-code-ref",
    "replay_regression.py": "code-ref:test+imported-or-code-ref",
    "replay_would_have_filled.py": "imported-or-code-ref",
    "report_format_gate.py": "code-ref:test+imported-or-code-ref",
    "score_catalyst_rubric.py": "imported-or-code-ref",
    "seed_drawdown_breaker.py": "operator-tool:write",
    "seed_theme_relevance_cohort.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "selection_replay_268.py": "imported-or-code-ref",
    "set_composite_authority.py": "operator-tool:write",
    "set_holistic_judge.py": "imported-or-code-ref",
    "set_kill_scale_override.py": "operator-tool:write",
    "shadow_cap_plus_one_197.py": "imported-or-code-ref",
    "sip_replay_r_cohort.py": "imported-or-code-ref",
    "stop_2r_counterfactual.py": "code-ref:test+imported-or-code-ref+yaml-cited",
    "stop_width_replay.py": "imported-or-code-ref",
    "unjustified_demotion_sweep.py": "imported-or-code-ref",
    "v1_closeout_status.py": "code-ref:deploy+code-ref:test",
    "verify_crypto_sources.py": "imported-or-code-ref",
}


def test_no_unallowlisted_file_sits_at_scripts_root():
    """RED-PROOF 1: `touch scripts/_zz_redproof.py` then rerun -> this assertion fails
    ('_zz_redproof.py' not in KEPT_AT_ROOT); `rm` it -> passes again. Verified manually
    2026-09-19 (not left in the tree -- a touched throwaway would itself violate the DoD
    this test enforces)."""
    on_disk = {os.path.basename(p) for p in glob.glob(os.path.join(_SCRIPTS_ROOT, "*.py"))}
    unlisted = sorted(on_disk - set(KEPT_AT_ROOT))
    assert not unlisted, (
        "New file(s) at scripts/ root not on the KEPT_AT_ROOT allowlist (#261 guard): "
        f"{unlisted}. Run the two #261 safety greps (nothing imports it by module path / "
        "path, no data_gated_reviews.yaml citation) -- if both come back empty it is a "
        "throwaway probe, move it to scripts/probes/; otherwise add it here with a reason."
    )


def test_kept_at_root_allowlist_has_no_stale_entries():
    """RED-PROOF 2: rename any KEPT_AT_ROOT file on disk -> this assertion fails (the old
    name vanishes from the directory listing while its allowlist entry remains); rename
    back -> passes. Verified manually 2026-09-19."""
    on_disk = {os.path.basename(p) for p in glob.glob(os.path.join(_SCRIPTS_ROOT, "*.py"))}
    stale = sorted(set(KEPT_AT_ROOT) - on_disk)
    assert not stale, (
        f"KEPT_AT_ROOT allowlist entries no longer exist at scripts/ root: {stale}. "
        "File moved/renamed/deleted -- remove its entry here in the same commit."
    )
