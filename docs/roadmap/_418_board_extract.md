# #418 Board Extract — mechanical compaction of PLAN.md open tasks

Generated for the v1.0 close-out/productization plan (#418). One line per open task, grouped by
PLAN.md project header. Format:
`#ID | ETA | status | ESSENCE (deliverable, ≤25 words) | GATES: dependency/sign-off/evidence-gate/checkpoint or '-'`

PLAN.md open tasks: **104**. Extract lines below: **104**. (Counts match — no task dropped.)

---

## Launch — 6/22 GO/NO-GO
- #261 | 2026-07-06 | in_progress | Finish scripts/ namespace reorg: split ops/evals tooling for the 94 real tools + resolve 45 untracked scratch scripts. | GATES: -
- #299 | 2026-07-11 | blocked | Fund + run the tape-feature (opening-range violence/premarket pace/liquidity) judge eval, then wire into live grading. | GATES: blocked_by:#335 checkpoint; operator funding decision (~$170 full / ~$50-90 subset); batch with judge regrade
- #255 | 2026-07-08 | pending | Build judge precedent-retrieval v1 (kind=review) + periodic-review nudge once the operator-labeling corpus has volume. | GATES: defer_until:2026-07-08 (corpus-volume gate); clusters with #307/#219/#254
- #301 | 2026-07-11 | pending | Build a 2nd-model ensemble-divergence shadow monitor on HIGH-tier judge verdicts (zero-authority telemetry, no grade change). | GATES: blocked_by:#335 checkpoint (~7/18)
- #303 | 2026-07-07 | in_progress | Complete the cross-codebase advisor review, folded into the operator's Monday GO walkthrough (launch-readiness closeout). | GATES: operator walkthrough required to close
- #413 | 2026-07-17 | pending | Verify the end-to-end chain (fill→stop-leg attach→DB row→exit ladder) on Apollo's first real-money live fill. | GATES: waiting on first live fill (event-driven, market-dependent); re-date (not fail) if no fill by ETA

## Live-money cutover — MAGNA53 (GO-direction gates)
- #150 | 2026-07-15 | in_progress | Verify-live a clean retry on the next real share-reservation-lag event (the fix itself already shipped). | GATES: waiting on event-driven occurrence (can't force)
- #183 | 2026-07-15 | in_progress | Fix an ORB classifier IEX/window mislabeling bug. ⚠SCOPE? — no elaboration anywhere in PLAN.md beyond the title. | GATES: -
- #184 | 2026-07-05 | in_progress | Ship read-only DB↔broker coverage-drift detector (built) + ingest untracked broker orders into the trade-state mirror. | GATES: verify-live Mon 7/6 (first reconcile cycle); broker-order ingest needs a careful tested session (trade-state mutation)
- #316 | 2026-07-15 | pending | Confirm Alpaca's (not Fidelity's) Rule 4210 PDT rollout, then relax BLOCK_PDT_LOCKOUT. | GATES: CHANGE_PROCESS required; confirm Alpaca's actual rollout first

## Family A — consolidation plays post a runup
- #404 | 2026-07-13 | pending | Delete dead confirm_signal_at code + its 4 tests + ENTRY_CONFIRM_VOL_MIN (Confirm entry mode is un-wired). | GATES: -
- #402 | 2026-07-08 | pending | HTF shadow /simplify cleanup: shared pure-math module, median ADV floor, persist flagpole fields, /htf regression test. | GATES: the R-settlement piece touches the live anticipation path — gated under change-discipline
- #327 | 2026-07-07 | in_progress | Observe consolidation entry-shadow settlements (first ~7/7) to answer whether the coil-entry has a real live edge. | GATES: first settlements ~7/7 feed the #353 paper-graduation decision
- #353 | 2026-07-08 | pending | Graduate the consolidation-entry shadow to a real PAPER-account strategy (register in mi_strategies + wire entry pipeline). | GATES: gated on #327's ~7/7 settlement-edge read; no edge → stay shadow
- #354 | 2026-07-07 | pending | Calibrate volatility-relative holds/tightness thresholds from the operator-labeled 303-name shortlist, wire into the Anticipation detector. | GATES: paused for operator labels on the shortlist; wiring needs sign-off + ADR-0013 provenance rule
- #356 | 2026-07-11 | in_progress | HTF breakout-entry shadow (built/live); remaining: trading-day-ratio refactor + persist flagpole_ratio/flag_depth_pct fields. | GATES: flip to paper/live = N≥10 settled winners + CHANGE_PROCESS + sign-off (#397)
- #396 | 2026-07-06 | in_progress | EMA-trail exit-management shadow for HTF positions (scale 33-50%→breakeven→10/20 EMA trail), audit-only. | GATES: blocked_by:#356; verify-live Mon 7/6 first job run
- #397 | 2026-07-18 | pending | GO/NO-GO: promote HTF breakout-entry from shadow to paper (then live) based on the shadow-edge review. | GATES: waiting on #356+#396+1-2wks shadow outcomes; CHANGE_PROCESS + operator sign-off for live
- #357 | 2026-07-10 | pending | Decide Sugar Babies' role (confluence/score input vs standalone watchlist) + re-frame its surface accordingly. | GATES: operator decision required
- #358 | 2026-07-08 | pending | Build a CI/pre-commit check that fails when a detection-gate constant lacks a methodology-source citation. | GATES: -
- #297 | 2026-07-15 | pending | Rework Family-B EP's gap-anchored replay/evaluate_candidate + archive/clean phantom mi_anticipation_lifecycle rows. | GATES: 9M-entry retirement is decision #326, dated 9/15
- #283 | 2026-07-07 | pending | Evaluate promoting the wick_fill detector from shadow to live. | GATES: gated behind Family A settling
- #385 | 2026-07-06 | in_progress | Record volume dry-up (3-bar/15-bar SMA ratio) on the consolidation shadow rows + labeling worksheet (telemetry only). | GATES: deployed 7/4; verify Mon 17:35 job writes vol_dryup
- #386 | 2026-07-11 | pending | Check whether Polygon/FMP expose authoritative halt/LULD status; replace the zero-volume dead-data heuristic if so. | GATES: -
- #394 | 2026-07-07 | pending | Tune the coil-finder hold-cap + rank ordering on real forward shadow data; add an orderliness/gappy metric. | GATES: waiting on ~1wk forward candidates (market's clock)
- #395 | 2026-07-14 | pending | GO/NO-GO: flip the coil-finder shadow entries to real trades, evidence-gated on settlement-R data. | GATES: blocked_by:#394; also gated on #393; CHANGE_PROCESS N≥10 + operator sign-off

## Stocks in Play — detection / setups / entries / 9M / flags
- #359 | 2026-09-22 | pending | Evaluate lowering the $500M EP market-cap floor using an accumulating near-miss cohort's forward outcomes. | GATES: N≥~15 near-miss samples w/ forward returns (registry, earliest 2026-09-22); operator decision + CHANGE_PROCESS
- #168 | 2026-07-13 | in_progress | Build a quality/actionability filter gating shadow-detector graduation to live Telegram pings. | GATES: evidence-gated
- #167 | 2026-07-13 | in_progress | Continue building the Lane-2 narrative theme detector (same-day narrative co-gap detection, shadow). | GATES: -
- #170 | 2026-07-15 | in_progress | Shorten the EP cooldown or add a fresh-catalyst override so legit re-setups aren't over-suppressed. | GATES: live-flip gated on realized-R evidence + CHANGE_PROCESS (data_gated_reviews #170)
- #146 | 2026-07-15 | pending | Allow direct TIGHTENING→TRIGGERED flag transition (skip COILED prerequisite) on breakout close + volume confirm. | GATES: N≥10 backtest required
- #178 | 2026-07-15 | pending | Merge the /setup and /why Telegram commands into one filter-reason observability command. | GATES: -

## Judge & catalyst — v1.1 program
- #405 | 2026-07-08 | in_progress | Fix the catalyst-cache set-after-filter bug that repeatedly re-grades filtered tickers (cost/noise only, zero trade impact). | GATES: hard-gate test filtered-can-never-enter satisfied; verify Tue 7/7 premarket scan
- #367 | 2026-07-06 | pending | Run backfill + health-read on the 452-row cohort to measure theme-relevance attribution signals (name-match + co-movement). | GATES: gated on STEP-0 #366 + N≥~25 EP-HIGH grades; Mon read decides matcher-bug vs corpus-source issue
- #368 | 2026-07-07 | pending | Operator labels the theme-relevance cohort + decides theme-boost weighting / stage-credit mapping for the meta-rubric. | GATES: blocked:#367 (matcher-vs-text-source read lands Mon 7/6)
- #317 | 2026-07-07 | in_progress | Suppress the contradictory Perplexity "Catalyst:" alert line when a direct-sourced judge rationale already exists. | GATES: needs market-agent deploy + verify-live on next direct-source HIGH alert
- #322 | 2026-07-11 | pending | Address a theme-coverage gap (judge inferred an untracked theme neither detection lane tracks). | GATES: -
- #328 | 2026-07-06 | in_progress | Ship the theme-axis-as-judge-input shadow (ADR 0015, boost-only post-composite adjustment); accrue data toward the flip. | GATES: CHANGE_PROCESS + sign-off + N≥10 backtest before live flip; verify Mon shadow rows; accrues to #335 checkpoint (~7/18)
- #329 | 2026-07-18 | in_progress | Anchor meta-rubric composition: enrich the single judge with theme/structure/gap axes (Path A), not a separate composite. | GATES: composition rides the #335 checkpoint (axes accrue first)
- #330 | 2026-07-06 | pending | Build the structure-axis shadow (Stage-2 200MA/52w + RMV tightness + extension state) per ADR 0016, boost-only. | GATES: STEP-0 supported direction at N≥30; queued behind #328/#335-eval slots
- #331 | 2026-07-09 | pending | Score whether a gap punches through resistance vs fades into congestion, as a calibrated judge axis. | GATES: blocked on #329 spec + #330 structure primitives
- #332 | 2026-07-25 | pending | Design distinct conviction rubrics per setup class (Pradeep small-cap vs Qullamaggie breakout vs episodic mid-cap). | GATES: kept behind #329/#330/#331 (composes on top of them)
- #333 | 2026-07-15 | pending | Score catalyst durability's forward/projected leg (≥4Q projected growth), not just trailing acceleration. | GATES: gated on #210/#211 direct-sourcing backbone (structured data, not LLM prose)
- #335 | 2026-07-18 | pending | Flip the meta-rubric composite (theme+catalyst+structure/gap axes) to authoritative in the live paper EP grade. | GATES: CHANGE_PROCESS + sign-off + ONE batched re-grade; gates OBJECTIVELY UNMET per 7/4 eval; checkpoint ~7/18
- #337 | 2026-07-11 | pending | Explore an LLM-advisor mechanism that reviews the judge's own calls monthly (richer variant of the labeling arm). | GATES: -
- #338 | 2026-07-15 | pending | Apply 8 deferred judge/catalyst-code cleanups (shared trace formatter, field unification, constant extraction). | GATES: low-urgency hygiene; item (H) resolves naturally once #335 wires the axis in
- #269 | 2026-07-10 | in_progress | Verify rubric v3 via the AKTS forward-outcome case + build the promote-cap evaluation harness. | GATES: -
- #210 | 2026-07-08 | pending | Build the direct-primary-source catalyst-sourcing backbone (SEC filings/press wires/structured feeds over LLM discovery). | GATES: -
- #211 | 2026-07-08 | in_progress | Build the news-gap discovery loop tracking the unknown-catalyst-rate KPI (needs a new scheduler job). | GATES: -
- #347 | 2026-07-06 | pending | Verify the enriched-catalyst-corpus live flip (already deployed) produces correct grades with no failure floods. | GATES: verify Mon 7/6 premarket; already flip-deployed + review-hardened
- #212 | 2026-07-11 | in_progress | Productionize the questioner/investigator dialogic catalyst-QA loop at a larger cohort scale. | GATES: -
- #230 | 2026-07-11 | pending | Wire #212's dialogic loop as a sourcing-QA detector feeding #211's low-precision triage. | GATES: depends on #212; feeds #211
- #233 | 2026-07-11 | in_progress | Feed Perplexity's independent grade to the judge as a labeled disagreement signal; retire its floor confidence boost. | GATES: grade-path input change → CHANGE_PROCESS + shadow eval (judge is load-bearing)
- #235 | 2026-07-11 | pending | Integrate the gap-discovery loop (#211) as Wave E of the catalyst-sourcing program. | GATES: depends on #211
- #215 | 2026-07-13 | pending | De-bias the catalyst grading prompt against the OPTX-residual pattern once a clean grade cohort accrues. | GATES: rides on #335/#320/#321 grade-quality cluster settling
- #258 | 2026-07-15 | in_progress | Consolidate ensure_schema()'s 33 ALTER statements into fewer migrations (branch+staging validated). | GATES: post-#277
- #239 | 2026-07-15 | pending | Extract the trailing-baseline-dup helper once a 3rd permanent consumer exists; envelope unification is won't-do. | GATES: gate unmet until a 3rd permanent consumer of trailing-baseline exists
- #265 | 2026-07-08 | pending | Clean up judge-flip-day residuals: SQL-text SSoT, shared feeds list, WATCH cancel window. | GATES: -
- #207 | 2026-08-01 | pending | Run the quarterly model-eval-governance review (which LLM model for which role). | GATES: data-gated (quarterly cadence)
- #197 | 2026-07-20 | in_progress | Shadow-test allowing one extra game_changer EP slot beyond the current cap. | GATES: promotion-gated N≥30
- #192 | 2026-07-13 | pending | ⚠SCOPE? "Deferred-findings-to-task discipline follow-up" — no specific action or deliverable named anywhere. | GATES: -
- #272 | 2026-07-07 | in_progress | Close out the LAUNCH umbrella task — 6/22 GO/NO-GO already executed, gates already resolved. | GATES: -
- #274 | 2026-07-15 | pending | Fix 2-member themes that never dissolve — retire when both members get flagged/removed. | GATES: CHANGE_PROCESS
- #276 | 2026-07-15 | in_progress | Close out the W2 stop-geometry study (verdict: no stop change, ORB-low remains optimal). | GATES: operator ack at launch checkpoint; thread paused, reopen only on a regime shift

## Operational safety / hardening
- #407 | 2026-07-13 | pending | Apply 4 theme/anticipate code cleanups (extract shared theme-upsert helper, drop redundant dict, minor refactors). | GATES: apply with the next theme-area change, not a standalone deploy; one item folds into #404
- #384 | 2026-07-08 | in_progress | Confirm X/Twitter account credits + resolve a stale-tweet bug, then operator re-enables EP-alert posting. | GATES: operator must flip _X_POSTING_ENABLED; needs a credits check with the operator
- #381 | 2026-07-11 | in_progress | Burn down the silent-failure ratchet baseline (125→0) by remediating swallowed-exception sites with logs/alerts. | GATES: money/trade critical-path instances split out as #382; gate mechanically blocks any new violation
- #378 | 2026-07-06 | pending | Build a /cost board (full LLM + subscription total) + Telegram alarm on budget-cap or 2x-daily-anomaly breach. | GATES: needs #377 meter; thresholds operator-set (~150 USD/mo variable cap + 2x-median anomaly)
- #379 | 2026-07-07 | pending | Build a per-caller cost-anomaly watchdog (spike detection) + surface concrete cost-reduction opportunities. | GATES: builds on #377/#378
- #370 | 2026-07-10 | in_progress | Decide + optionally build increment 5: a hard-check completeness registry (backups etc.) — 4/5 increments already live. | GATES: operator call on whether worth building (partly redundant with _backup_health_check_job)
- #363 | 2026-07-08 | pending | Extract a shared _load_exit_state(trade, today) helper deduping the partial-exit and trail jobs' identical preamble. | GATES: -
- #348 | 2026-07-15 | pending | Extract get/set_safeguard_state() db helpers, replacing 4 inline copies (drawdown breaker, kill/scale, halt state). | GATES: post-launch; touches #345 manual-halt + live drawdown breaker — needs careful per-call verification
- #290 | 2026-07-10 | in_progress | Run the analyze_late_detection_v3 dead-zone ORB-extension precision check; confirm <20% precision or close the review. | GATES: -
- #343 | 2026-07-10 | in_progress | Accrue chart-vision-axis shadow deltas until the decision gate resolves promote/hold. | GATES: registry gate: N≥10 deltas OR 2026-07-31 → CHANGE_PROCESS + ADR 0011 to promote load-bearing
- #412 | 2026-07-06 | pending | Finish residual review findings: F10 execution-side AsyncClient reuse (staging-exercised) + d2-review G1/G2 leftovers. | GATES: residual work (F10 + G1/G2) slated for the Sunday session
- #414 | 2026-07-12 | pending | Propose a backtested fix for stop-limit orders that gap/never-trigger (wider offset or stop-market + chase cap). | GATES: CHANGE_PROCESS + N≥10 backtest; composes with #180; no unilateral ship — operator sign-off required
- #416 | 2026-07-09 | pending | Diagnose M&A-filter false-positive match mechanisms (polygon_news/keyword) + propose an amendment. | GATES: CHANGE_PROCESS + operator sign-off; composes with #410's pin-guard
- #417 | 2026-07-08 | in_progress | Backfill missing SSoT docs, then re-trim CLAUDE.md below the 36k warn threshold (currently 37.8k). | GATES: do not guess-trim money-adjacent sections without doc backfill first
- #415 | 2026-07-08 | pending | Add 3 audit-only telemetry fields to unified_allocation_decided (eligibility flag, cascade candidate, slot cadence). | GATES: re-review at registry earliest 8/4 when contested days accrue
- #340 | 2026-07-08 | pending | Build a trailing-median delta-check catching sudden data drops AND auto-adapting to intended step-changes. | GATES: -
- #287 | 2026-07-08 | pending | Clean up partial-exit trade-state: fix the FPS stuck flag + resolve double-encoded 8-trade exits. | GATES: operator-gated
- #280 | 2026-07-08 | pending | Give the staging environment its own separate paper Alpaca account (isolate from prod paper). | GATES: must land before any market-hours staging use
- #281 | 2026-07-08 | pending | Harden staging to be a true copy-not-derive restore fork, preventing compose/env config drift from prod. | GATES: -
- #256 | 2026-07-07 | in_progress | Verify Monday's cron-proof (staging-restore + watchdog heartbeat both fire) to close the W4 DR/uptime program. | GATES: verify Mon 7/6: 03:30 restore-check + 12:00 watchdog_heartbeat rows
- #176 | 2026-07-13 | pending | Build a create-time hook + scheduled ping catching SoT/roster drift (residual hardening item). | GATES: -
- #216 | 2026-07-08 | pending | Consolidate jsonb codec handling (root-fixes the recurring #179 bug class). | GATES: -

## Apollo Trades dashboard (portfolio-app2)
- #194 | 2026-07-15 | pending | Automate daily export of trades + themes snapshots to the portfolio-app2 dashboard. | GATES: blocked on operator deploy key
- #185 | 2026-07-15 | pending | Fix the corrupt-stop exclusion-count display bug in the Apollo Trades dashboard. | GATES: -

## Apollo Themes (portfolio-app2)
- #315 | 2026-07-15 | pending | Ship RS-theme dashboard backlog: mobile/public URL, bump chart, canonicalization, forward-returns view. | GATES: -

## Fable planning reserve
- #418 | 2026-07-07 | pending | Write the v1.0 close-out & productization plan: finish line, full-board disposition, ops/monitoring/docs maturity sweep. | GATES: DoD = operator signs the finish line
- #419 | 2026-07-08 | pending | Write the Phase-2 mid/long-term roadmap (revises apollo-v1.1-v2.0.md Part II), specced to execution depth. | GATES: depends on #418 (the finish line defines where Phase 2 starts)

## Apollo v1.1 — fast-follow program
- #306 | 2026-07-08 | in_progress | Backtest exit-management tuning options (peak-lock, MA-trail-by-character, partial size) against the closed-trade cohort. | GATES: STEP-3 requires operator decision + CHANGE_PROCESS + #151 harness + paper-exercise before any live flip
- #307 | 2026-07-08 | pending | Build the weekly operator-labeling ritual + precedent-retrieval shadow (the judge's experience-seed program). | GATES: -

## Apollo v2.0 — tier-one trader
- #308 | 2026-08-01 | pending | Build the Experienced Judge: precedent corpus at scale, self-review/rubric-distillation loop, ensemble uncertainty. | GATES: -
- #309 | 2026-08-01 | pending | Build Full Sight: multimodal chart vision (intraday/peer/SPY), narrative radar, tape features, negative-catalyst detection. | GATES: -
- #310 | 2026-10-01 | pending | Mature the Manager: management judge to load-bearing, pivot-based structure stops, conviction-based sizing. | GATES: -
- #311 | 2026-08-01 | pending | Build the Multi-Setup Book: per-setup judges, tightness→expansion graduation, parabolic-short book, regime-adaptive selection. | GATES: -
- #312 | 2026-10-01 | pending | Build the Capital & Autonomy Ladder: live unified_allocator, formal promotion ladder with auto-demotion on breach. | GATES: -
- #313 | 2026-08-01 | pending | Build Institution-grade ops: replay-everything CI + per-role LLM-spend-vs-P&L cost governance. | GATES: -
- #314 | 2026-07-15 | pending | Build the trading-ideas detector book: parabolic-short, wick-fill, TI3 U&R (fishhook retired 2026-07-21 — needs a fresh non-fishhook approach if pursued), base+catalyst convergence, shape classifier, RMV. | GATES: graduation gates in data_gated_reviews.yaml; refs #283 (wick-fill), #54 (RMV)

## Spec / detail docs
(No task lines — index-only section pointing to docs/roadmap, docs/decisions, docs/setups, docs/methodology, data_gated_reviews.yaml.)

## Miscellaneous (no home project)
- #420 | 2026-07-10 | pending | Add an external uptime pinger (UptimeRobot) on /health + decide whether to decommission the empty kuma container. | GATES: operator decision on kuma; operator must create the pinger account
- #121 | 2026-07-15 | in_progress | Migrate remaining legacy-Markdown Telegram surfaces to the shared HTML formatting layer. | GATES: -
- #195 | 2026-07-08 | in_progress | Rotate the portfolio-app2 app_password (security hygiene). | GATES: operator action required
- #334 | 2026-07-15 | pending | Wire the theme-revive cooldown latch (persist revived_at) once theme-revive functionality goes live. | GATES: wait until the revive feature goes live

---

## Summary

- **Count by project**: Launch 6/22 GO/NO-GO 6 · Live-money cutover MAGNA53 4 · Family A 16 · Stocks in Play 6 · Judge & catalyst v1.1 32 · Operational safety/hardening 22 · Apollo Trades dashboard 2 · Apollo Themes 1 · Fable planning reserve 2 · Apollo v1.1 fast-follow 2 · Apollo v2.0 7 · Miscellaneous 4. **Total = 104.**
- **Tasks with an explicit GATES entry** (blocked-on-#ID / operator sign-off / CHANGE_PROCESS / evidence threshold / dated checkpoint): **72 of 104**.
- **Tasks with no explicit gate** (GATES: -): **32 of 104** — mostly build-now items or already-resolved closeouts.
- **⚠SCOPE? flags** (deliverable too vague to state — candidate ghost tasks): **2** — #183 ("ORB classifier IEX/window mislabel", zero elaboration anywhere in PLAN.md) and #192 ("deferred-findings-to-task discipline follow-up", no named action).
- PLAN.md open-task count and extract line count both = **104** — no task ID dropped in compaction.
