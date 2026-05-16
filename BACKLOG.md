# Apollo Backlog — Master Index

Single quick-scan view of all open work. Points to canonical detail files;
does not replace them.

**Update discipline**: when filing, closing, or status-changing an item in
its detail file, mirror the change here. If the index gets stale, source
files still own runtime behavior — index lies don't break the system, just
the at-a-glance view.

**Convention**:
- `[ ]` pending / not started
- `[~]` in-progress, scaffolded, or partial
- `[x]` done (moves to "Done — rolling" section, pruned monthly)
- 🚧 live-cutover blocker

Last updated: 2026-05-14

---

## 🚧 Live-cutover blockers

Live-$ flip cannot happen until ALL of these are green.

- [ ] **Gate 5 G — Column-write audit invariant** (added 2026-05-15 after KLAR/ARM stop_price clobber). Refactor write sites per `docs/architecture/trade-state-ownership.md` + ship `scripts/audit_column_writes.py check` mode + wire into `deploy.sh` as `[5c/5]`. Sunday focused.
- [ ] **Gate 5 F — Operator sign-off on CRMD post-mortem** → `docs/incidents/2026-05-14-crmd-naked-position.md` §8
- [ ] **Gate 3 — Paper R-expectancy N≥10** (currently 4 methodology trades since 5/12, need 6 more) → `data_gated_reviews.yaml::paper_r_expectancy_validation` (earliest 2026-05-22)
- [ ] **Gate 2 — FTRE partial-trail verification** (waiting for real partial-then-trail in paper) → `data_gated_reviews.yaml::ftre_partial_trail_verification`
- [ ] **Gate 1 — Drawdown breaker promotion** (shadow → active, gated to ≥14d post-cutover telemetry) → `data_gated_reviews.yaml::drawdown_breaker_promotion` (earliest 2026-05-22)
- [ ] **Gate 4b — Dual-mode activation on Hetzner** (set ALPACA_LIVE_* env vars, ENABLE_LIVE_MODE=true) → `data_gated_reviews.yaml::live_cutover_decision` Step B
- [ ] **Composite live cutover decision** → `data_gated_reviews.yaml::live_cutover_decision` (evaluation 2026-05-22)

---

## 📋 Open data-gated reviews — predicate-pending

Sorted by earliest_review_date.

### Ready by date but predicate not met
- [ ] `ftre_partial_trail_verification` (5/13, partial_taken=TRUE since 5/10) → YAML
- [ ] `crmd_naked_position_postmortem_2026_05_14` (5/14, depends on Gate 5 deliverables) → YAML

### Ripens this week / next week
- [ ] `theme_assignment_sndk_class_refinement` (5/15) — diagnosis done, structural fix remaining → YAML
- [ ] `minute_volume_curves_baseline` (5/15) → YAML
- [ ] `unified_allocator_phase_1b` (5/15, #44 cross-strategy allocator) → YAML
- [ ] `pass1_protect_strip_equalsize_test` (5/15, test fixture) → YAML
- [ ] `gate5_tomorrow_verifications` (5/15, 5-item checklist) → YAML
- [ ] `ep_selectivity_deep_dive` (5/17 — Phase 1 exhaustive cohort review, ~50 variables + §G Class A vs B + 5/14 entered-and-failed case studies ONDS/CPA/KLAR/CSCO + 10 missed-winners cohort OSS/STRL/FTNT/TWLO/BAND/MXL/HIMX/INOD/DDOG/TRT — TRT is the Class B exemplar with user's manual entry methodology: EP-day low + 20MA as risk reference) → YAML
- [ ] `vix_ingest_for_p19_sizing` (5/20) → YAML
- [ ] `perplexity_sanitizer_verification` (5/21, 7d outcome watch target=0) → YAML
- [ ] `paper_r_expectancy_validation` (5/22, Gate 3 above) → YAML
- [ ] `drawdown_breaker_promotion` (5/22, Gate 1 above) → YAML
- [ ] `live_cutover_decision` (5/22, composite gate) → YAML
- [ ] `trade_stream_stop_placement_without_orders_row` (5/22) → YAML

### Ripens later (June+)
- [ ] `flag_detector_post_breakout_label` (6/01) — TRT-class: detector mislabels explosive breakout days as TIGHTENING when COILED prerequisite wasn't met → YAML
- [ ] `system_audit_baseline_validation` (5/24, 30d baseline accumulation) → YAML
- [ ] `correlation_engine_revalidation` (6/1) → YAML
- [ ] `adv_probe_retirement` (6/1) → YAML
- [ ] `canonicalize_ticker_set_evolution` (6/1, N≥3) → YAML
- [ ] `rmv_phase2_evaluation` (6/9) → YAML
- [ ] `stop_too_wide_outcome_cohort` (6/13, N≥10) → YAML
- [ ] `flag_proximity_band_calibration` (6/15) → YAML
- [ ] `flag_proximity_bypass_hysteresis` (6/15) → YAML
- [ ] `flag_ma_pin_filter` (6/15) → YAML
- [ ] `dead_zone_reevaluation` (6/15) → YAML
- [ ] `fishhook_v3_first_telemetry_review` (6/15) → YAML
- [ ] `conviction_floor_extension` (6/28) → YAML
- [ ] `apollo_trades_dashboard_db_flip` (7/15, gated on ≥30 live trades) → YAML
- [ ] `orb_cutoff_extension` (7/15) → YAML
- [ ] `fishhook_v3_promotion_check` (7/15) → YAML
- [ ] `rs_theme_dash_forward_returns` (10/1) → YAML
- [ ] `fishhook_TI3_revisit` (10/29) → YAML

---

## 🛠 Methodology / feature backlog (P-numbered)

From `memory/project_market_intelligence_backlog.md`. Memory file auto-loads
each session; this index is the cross-cutting view.

- [ ] **P10** Conditional auto-entry alerts (gated on live $) → memory
- [x] **P13** Theme constituent churn detection — shipped 2026-05-14 commit 623c603 (`theme_engine._detect_theme_constituent_churn`)

- [ ] **P16** Live trading flip (gated on Gates 1-5 above) → memory
- [ ] **P17** Monthly & Quarterly system reviews (after 3+ weekly cycles) → memory
- [ ] **P18** +3R / 72h partial-profit path (gated on 10+ closed trades) → memory
- [~] **P19** VIX-scaled risk sizing — helper WIRED tonight into `prepare_orb_order` + `prepare_9m_day2_orb_order`; VIX ingest still missing → `data_gated_reviews.yaml::vix_ingest_for_p19_sizing` + memory
- [ ] **P20** Earnings-week IV pre-pass (blocked on Polygon IV data) → memory
- [~] **P21** Cross-asset thematic RS — V1 script shipped tonight (`scripts/cross_asset_rs.py`); V2 conviction boost into theme_engine deferred (needs theme-to-commodity mapping) → memory
- [ ] **P22b** Wick-Fill productionization (gated on n≥30 shadow fills with fill_rate≥0.50) → memory
- [ ] **P24** Audit-system backfill verification (earliest 2026-05-24 after 30d baseline accumulation) → memory + plan `~/.claude/plans/shiny-mapping-locket.md`
- [~] **P25** Theme Rank Evolution Dashboard — MVP scaffold shipped tonight (`dashboard/theme_rank_evolution.py`); requires local `pip install streamlit pandas psycopg2-binary` to run; canonical-ID layer (stage 2) deferred → memory
- [x] **P26** Verify Fix B global ticker ban — verified 2026-05-14 (firing daily since 4/28 deploy)
- [x] **P27** Accelerating-drop-out churn L2 telemetry — already implemented at `system_audit.py:242` + `_accel_dropout_count_7d`

- [ ] **MAGNA53 Simulator** (low-priority frontend widget) → memory

---

## 💡 Trading ideas (TI-numbered)

From `memory/project_trading_ideas_backlog.md`. Strategy expansions, not
platform features. Each goes through Stage 1 telemetry → Stage 2 paper →
Stage 3 live.

- [~] **TI1** Parabolic Short — Stage 1 telemetry deployed 4/25, watch 2-3 months for Stage 2 → memory
- [~] **TI2** Wick-Fill (P22) — Stage 1 deployed 4/28, watching for promotion (n≥30, fill_rate≥0.50) → memory + P22b above
- [~] **TI3** Fishhook V3 — explorer script ready (`scripts/fishhook_v3_explorer.py`, 438 lines), Stage 0 cohort review pending → memory
- [~] **TI4** Convergence engine V1 (earnings) — spike memo + yfinance coverage script (`scripts/_ti4_yfinance_spike.py`), pre-coding sign-off pending → memory + plan `~/.claude/plans/wave-d-convergence-spike.md`
- [~] **TI5** Post-EP Pattern Shape Classifier — explorer script ready (`scripts/ep_shape_explorer.py`, 376 lines), v0 cohort review pending → memory
- [~] **TI6** RMV integration — Phase 1 telemetry shipped 5/9, Phase 2 evaluation 6/9 earliest → memory + `data_gated_reviews.yaml::rmv_phase2_evaluation`
- [ ] **TD1** Apollo Trades dashboard (Tradervue-style) — gated on ≥30 closed live trades → memory + `data_gated_reviews.yaml::apollo_trades_dashboard_db_flip`

---

## 📝 Filed followups from CLAUDE.md sessions

Smaller items embedded in session change logs that aren't yet formalized
into reviews. Listed by surfacing date.

- [ ] **Perplexity disclaimer in display surfaces** (2026-05-14) — /trades, briefing, weekly review show disclaimer text verbatim. Sanitizer only filters M&A keyword scan path. Cosmetic; non-blocking. Flagged in `perplexity_sanitizer_verification` scope note.
- [ ] **format_trade_attempts older-style live mode** ✓ already addressed via `format_trade_attempts_live` dispatch (2026-05-12)
- [ ] **9M intraday M&A coverage** ✓ shipped tonight (commit c4243aa)
- [ ] **`trade_stream.py:367 + 600-611` explicit audit events** ✓ shipped tonight (`entry_fill_stop_remediated`)

---

## 🧪 Scaffolds awaiting next step

Code that's built but not yet wired into the live path.

- [ ] **P25 dashboard** (`dashboard/theme_rank_evolution.py`) — Streamlit MVP ready, requires local pip install + Postgres tunnel to view. Decision point: does the raw mi_themes viz expose fragmentation that requires the canonical-ID layer (stage 2)?
- [ ] **VIX ingest** — `constants.vix_scaled_risk_pct` helper wired into sizing paths but `regime_record["vix"]` is always None until VIX is ingested. See `data_gated_reviews.yaml::vix_ingest_for_p19_sizing`.

---

## 📚 Reference / future ADRs

Not action items per se; pointers to architectural decisions that may surface
work later.

- `docs/decisions/0001-dynamic-per-strategy-tuning.md`
- `docs/decisions/0002-ti5-v1-mid-range-continuation.md`

---

## ✅ Done — rolling (last 14 days)

Pruned monthly. Newest first.

### 2026-05-15
- [x] Weekend scope plan filed (`docs/plans/2026-05-15-weekend-scope.md`, 3dad03f)
- [x] KLAR/ARM stop_price clobber fix (commit d6fa74c) + reconcile of 2 trades
- [x] Trade-state ownership doc drafted (`docs/architecture/trade-state-ownership.md`)
- [x] `scripts/audit_column_writes.py` — column→writer matrix, audit mode (foundation for Sunday Gate 5 G)
- [x] Methodology damage assessment — KLAR #149 was reading -3.20R fictional vs -1.03R real; corruption-window note added to `paper_r_expectancy_validation`
- [x] Pass1 protect-strip equal-size test fixture (`tests/test_theme_engine_pass1.py`)
- [x] Perplexity sanitizer test fixture (`tests/test_perplexity_sanitizer.py`)
- [x] Surfaced `gate3_initial_stop_modeling` followup — FTRE/SMCI have entry==stop (breakeven trail), R-calc needs original stop not current
- [x] **Area 1**: theme carryforward deterministic-remove pass (`theme_engine._apply_carryforward_deterministic_filter`) — closes the adds/removes asymmetry. 6 tests, commit 3f0233e
- [x] **Area 3**: dropped `_synthesize_hypothesis` LLM sentence; added `_top_event_deltas` raw facts. Removed `_HYPOTHESIS_SEMAPHORE`, dead `anthropic`/`random` imports, orphaned plumbing. 5 tests, commit 6326da9
- [x] **Area 2**: `_theme_round_trip_validator_job` cron 6:00 AM ET — defense-in-depth catch for hallucinated themes with ≥50% strip-within-3d rate, commit 0c33a8d
- [x] Weekend scope plan committed (`docs/plans/2026-05-15-weekend-scope.md`, 3dad03f)
- [x] BACKLOG.md status sync (P13, P26, P27 → [x] done)

### 2026-05-14 (10 commits across multiple sessions)
- [x] CRMD naked-position incident: asyncpg AmbiguousParameterError fix (commit 96fd7ee) + reconcile + post-mortem
- [x] BW pre-fill state mutation fix (`live_tracker.py:591-602` partial_fired branch)
- [x] SNDK theme misclassification — manual reassign + Pass1 BOTH_PROTECTED tiebreaker fix
- [x] Phantom split formula error — fix + 10-ticker reconcile (AIXI, CVNA, etc.)
- [x] P&L attribution column (`mi_live_trades.pnl_attribution`) — Gate 3 excludes bug-attributable trades
- [x] EP selectivity deep-dive review filed (exhaustive 50-variable scope)
- [x] Theme assignment SNDK refinement review filed
- [x] Perplexity hallucination keyword leak review filed
- [x] Trade_stream stop placement audit events filed + shipped
- [x] Theme orphan_sub remediation + canonicalize_ticker_set_evolution review filed
- [x] Theme `cross_run_dup_candidate` rename → `theme_name_variant_observed` (C2 closed as no-fix-needed)
- [x] **Gate 5 A — Naked-position remediation** in `_process_entry_fill`
- [x] **Gate 5 B — Boot-time UPDATE prepare validation** (caught $2::numeric cast failure on first run)
- [x] **Gate 5 C — partial_fill exception escalation**
- [x] **Gate 5 D — Stuck-fill watchdog cron**
- [x] **Gate 5 E — Schema column-type regression pytest**
- [x] Perplexity disclaimer sanitizer in ep_detector
- [x] 9M intraday M&A filter coverage (`ninem_detector.run_9m_scan`)
- [x] Canonicalize ticker-set-evolution probe event (`theme_canonicalize_gap_observed`)
- [x] P13 theme constituent churn detection (`theme_engine._detect_theme_constituent_churn`)
- [x] TI4 yfinance coverage spike script
- [x] P21 cross-asset RS V1 script (rewritten against `get_grouped_daily`)
- [x] P25 Theme Rank Evolution dashboard MVP scaffold
- [x] P19 VIX-scaled sizing helper + wired into prepare_orb_order + prepare_9m_day2
- [x] $2::numeric → $6 separate-param fix (caught by preflight)
- [x] M&A filter direction-blindness (NBIS class) — drop bare "acquire"/"acquisition"

### 2026-05-13
- [x] FTRE partial-trail predicate tightened
- [x] Theme `cross_run_dup_candidate` over-emission diagnosed (no-fix-needed)
- [x] Theme orphan_sub remediation
- [x] M&A direction-blind fix
- [x] 9M sugar baby M&A coverage
- [x] Theme assignment silent_stop fix (max_tokens + prompt)
- [x] Filed ep_selectivity_deep_dive review
- [x] Several telemetry review verifications (dead_zone, fishhook_v3, ep_adv_probe)

### 2026-05-12
- [x] Dual-account architecture verification on Hetzner
- [x] Live cutover gate composite review filed
- [x] format_trade_attempts schema slip fix (`format_trade_attempts_live` dispatch)

### Older
See `CLAUDE.md` "Changes Made — Recent" section for full history.
