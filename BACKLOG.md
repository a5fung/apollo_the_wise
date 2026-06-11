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

Last updated: 2026-06-05 (full re-sweep: all 44 open tasks re-mapped to projects, completed tasks dropped; new **Apollo Themes** project (#193/#194) split out; **North Star** enriched with the catalyst-axis cluster + model-selection baseline (#188✓/#207); timezone PERMANENT FIX #206 noted under Op-safety. Prior: 2026-06-01 roster refresh — partial-exit hardening + 16:45 cron verified; #174 breaker armed; #175 Apollo Trades dashboard DONE)

---

## 🎛 Active Major Projects — at-a-glance roster

Project-level view (item/date detail is in the sections below + linked files). The weekly
"Apollo project night" (Tue, calendar) scans this; if a project isn't here, it isn't being
tracked — add it. Priority: **P0** = blocks live $ / safety · **P1** = core goal · **P2** = important, not blocking.

| Project | Pri | Status | Next milestone(s) | Master / detail |
|---|---|---|---|---|
| **Stocks in Play** — setups + entries umbrella (some Apollo-traded, some inform-operator; a stock can combine setups) | **P1** | #167 kickoff DONE 6/2; narrative-discovery shadow + eval-harness VERIFIED-LIVE 6/6 (hindsight-segregated backfill cohort N=14 + forward-always-wins persist); WS-A SIP-infra still thin | narrative JUDGMENT review **6/09** (pulled fwd from 6/23; backfill 5d +4.1% but hindsight-caveated, fwd N=0) · R3 canonization #226 (~6/16, blocked_by 214) · RMV-qualifier 6/9 · entry-technique graduation 7/15 · #65 9M LEAVE-AS-IS (revenue-gate refuted no-op) · #170 cooldown re-setup 6/8 | `docs/setups/PORTFOLIO.md` · memory `stocks-in-play-project` |
| **Live-money cutover** (MAGNA53 first) | **P1** | paper-validating; realized history weak (−$9,475), leans on unbanked open winners | **⭐ 6/22 GO/NO-GO** · blockers: #151 N=7 (6/15) + Gate-3 realized-R · #150 DOWNGRADED 6/3 (entry-fill/opportunity-cost, NOT safety — order-record-confirmed) · #142✓ #174✓armed · NEW #182 paper IEX-fill fidelity (verify, not a blocker) | memory `north-star-and-live-readiness-timeline` (Track A) · `live_cutover_decision` review |
| **Apollo v1.1 ? v2.0** (successor program ? `docs/roadmap/apollo-v1.1-v2.0.md`; judge/catalyst/theme work continues HERE) | **P1** | **🏁 NORTH STAR CLOSED 6/11** (one day early; ADR 0011 IMPLEMENTED-LIVE: judge = the live paper grade authority on OPUS 4.8, advisory stack retired, model-checked via operator labels, verified-live on 3 Opus alerts with exact reconcile + 0 fail-opens; #240 + waves all completed; NEVER reopened per locked DoD). v1.1 proposal **APPROVED 6/11** (+ Gemini-review amendments adopted into the doc) | W1 #268 READY (judge-era selection replay + 6/22 kill/scale criteria) ? W2 entry-mechanics (the #1 expectancy leak) ? W3 exits/harvesting ? W4 #267 chart-vision ? W5 experience seed (#254/#255) ? standing reads: theme-as-EP-signal n?40 ~8/1 ? quarterly model-eval 8/1 (#207, playbook) | roadmap doc ? CHANGELOG 2026-06-11 ? memory `north-star?` ? `docs/model_selection_baseline.md` |
| **Operational safety / hardening** | **P0** | partial-exit hardening trilogy SHIPPED + paper-validated 6/1; 16:45 cron re-enabled & verified; timezone PERMANENT FIX shipped 6/5 (#206); **6/7: #205 stale-tests✓ (suite green) · #221 deploy ownership-map✓ · #222 missed_outcomes DRY✓ · CLAUDE.md graduated 58.9k→41.9k · 6/9: #257 model registry + [5i/7] gate + FIRST CI SHIPPED (Opus spend pricing was 3× stale; pricing now single-sourced); CLOSE ritual step 2b (deferral audit) codified; Fable-5 architecture review delivered** | **⭐ #256 split+staging BIG ROCK — PROMOTED to its own roster row 6/10 (scoped + W1 started; see row above)** · residuals: #152 news-drift · #172 partial-exit refactor (post-#151) · #216 jsonb-codec root (gated post-6/22) · #237/#239 /simplify refactors · #225 demotion residuals · #258 ensure_schema (post-first-fire) · #259 #260 #261 #262 #263 #264 (6/9 review cluster) | BACKLOG "🚧 Live-cutover blockers" + tasks |
| **Execution/Intelligence split + staging** (#256 — service split so detection deploys can't restart trade execution; staging pipeline before live money) | **P0** | **W1 CODE-COMPLETE + DEPLOYED 6/10** (facade `execution_client.py`, 16 sites migrated incl. all reads, 28 moves-with-job tags = the W2 partition seed, boundary deploy-gate **[5j/7] armed in prod**; pre-deploy reviewer verified semantic equivalence site-by-site); W2 job-partition table drafted (22 exec / 41 intel jobs + the ep_scan→orb_monitor inline-trigger coupling flagged) | W1 verify = clean trading day Thu 6/11 → W2 process split + `EXECUTION_MODE` flag (~6/13–6/17, else post-6/22) → W3 staging compose + `deploy.sh staging` → W4 DR/ADR closure | task #256 · plan `~/.claude/plans/execution-intelligence-split-256.md` |
| **Apollo Trades dashboard** (portfolio-app2 — Tradervue-style P&L calendar + setup stats) | **P2** | ✅ Phase 1+2 BUILT + deployed to Streamlit Cloud on real PAPER data (db-mode) + real-data-polished 6/3 (#175 DONE; scratch-bucket + single win-rate definition across all surfaces) | Remaining gated/future: **#194 daily auto-export of both snapshots (trades + themes — re-filed here 6/10; trades snapshot sat stale 6/03→6/10 until operator caught it; manual path = saved export SQLs)** · #185 corrupt-stop exclusion display · Phase 3 intraday MAE/MFE (Apollo-side `mi_intraday_bars` replay) · live-data cutover (`apollo_trades_dashboard_db_flip` 7/15, ≥30 live trades + Tailscale) · optional API key for Haiku digest | memory `Apollo Trades dashboard tab (portfolio-app2)` · SEPARATE repo `portfolio-app2` |
| **Apollo Themes** (portfolio-app2 — RS theme rank-evolution tab) | **P2** | #193 in-flight (port of the RS theme dashboard rank-evolution view into portfolio-app2) | snapshot freshness → #194 (now BOTH snapshots, filed under Apollo Trades dashboard) · ⚠ shares the PUBLIC portfolio-app2 repo → #195 rotate app_password (operator-action) | SEPARATE repo `portfolio-app2` · memory `Apollo Themes tab (portfolio-app2)` |
| **Miscellaneous** — catch-all for tasks with no home project (keeps the project→task hierarchy complete; nothing floats loose) | **P3** | active catch-all | #121 (shared Telegram formatting layer) · #176 (SoT/roster drift-check tooling) | "Open tasks by project" section below |

*(Lower-pri / dormant projects — crypto track, RS-theme dashboard, portfolio app, parabolic-short TI1 — live in their own memories; promote here if they reactivate.)*

**Reminder coverage:** dated milestones auto-surface in the Sunday weekly self-audit; the recurring Tue "project night" (calendar) nudges weekly progress; durable detail in each memory/doc above.

## 📂 Open tasks by project (hierarchy — no loose tasks)

Every OPEN #-task rolls up to exactly one project here. The #-task tracker stays SoT for task STATE; this is the grouping/hierarchy view. **Rule:** a new open task lands under a project below — or under **Miscellaneous** if it has no home — so nothing floats loose. Swept 2026-06-02 (28 open tasks); North Star catalyst-axis cluster (#186/#189–#203/#207) + #205 mapped 2026-06-05. ⚠ A full re-sweep of all post-6/2 tasks is still due (the cluster above is mapped; other new tasks may not be).

- **Stocks in Play** (detection · setups · entries · 9M · cooldown · flags · entry-techniques): #55 #56 #60 #65 #81 #97 #113 #115 #116 #134 #146 #166 #167 #168 #170 #178 #209 #218 #220 #226 #227 #229 (#229 = EP gap_pct accuracy: ABVX 06-03 recorded +15.1% but reality was ~-44% gap-down — detection-recording bug; #227 = fix scripts/test_9m_ep_e2e.py UnicodeDecode+DB errors, low-urgency test-harness bug filed 6/6; #226 = R3 persistent narrative→mi_themes canonization (Lane 2 MERGE) — DEFERRED per 6/6 advisor review: blocked_by task-214 naming stability + post-Monday 200-verify, ETA ~6/16, advisory-only NOT load-bearing (daily re-assert + theme_pass1_5_absorption dedup + fade lifecycle); #209 = leveraged/inverse-ETF universe hygiene; #218 = command-surface consolidation — /detectors roll-up for the 5 shadow detectors + drop redundant aliases + fix /ep|/eps, operator review 6/6; #220 = merge /watch + /inplay into one /watch (keep /watchlist) — the #168 actionability filter defines its default; **#168 NOISE FIX shipped 6/7**: 5 intraday entry-technique shadow detectors were per-tick-pinging ~23/day ("telemetry only") — flag-break unguarded + 3 env-gated (prod `SHADOW_DETECTOR_TELEGRAM_ENABLED=true` overrode the "silenced 5/26" intent) + U&R already off. Now per-tick DEFAULT FALSE in code (SoT, survives DR/env-reset) + ONE 16:00 ET consolidated digest `run_intraday_signals_eod_digest` (suppress on zero, cites /detectors). DB+audit untouched (N≥10 eval intact). REMAINING #168 = the quality/actionability filter for which signals earn a LIVE ping at graduation (evidence-gated, needs the outcome data shadow is collecting))
- **Live-money cutover** (MAGNA53): #150 (↓DOWNGRADED 6/3 — entry-tuning, not safety) #151 #183 #184 #224 #225 #268 (**#268 = v1.1 W1 kickoff, gated on operator approving `docs/roadmap/apollo-v1.1-v2.0.md`: judge-era selection replay over ~12mo (N=hundreds on the POST-judge system — realized paper only tests the pre-judge one) + pre-committed 6/22 kill/scale criteria into safeguards.md;** #183 = ORB classifier IEX/window mislabel; #184 = broker-authoritative trade-state mirror (ADR 0008) — **increment 1 demotion FENCE shipped 6/6** (`audit_trade_state_demotions.py`), increments 2/3 pending; #225 = resolve the 3 demotion residuals (L584/905/1575 order_manager) the fence surfaced, paper-gated, then wire blocking deploy gate; #224 = SIP-replay robustness checks. **#223✓ DONE 6/6 — Gate-3 SIP-selection verdict: paper −$9,475 is an IEX feed artifact; +2.27R same-basis selection delta; GO-supportive for reduced-size 6/22. Doc `docs/analysis/sip_replay_gate3_2026-06-06.md`.** Done & dropped: #174 #180 #181 #182 #223.)
- **Judge & catalyst (ex-North Star → v1.1 program)**: #149 #165 #191 #192 #197 #219 #236 #266 #269 (**🏁 #240 CLOSED 6/11** — verified-live a day early: 3 Opus-judged alerts, exact alert↔decision↔authority reconcile, 0 fail-opens; #242–#245/#247/#249/#252/#253 all closed-verified; ADR 0011 IMPLEMENTED-LIVE; CHANGELOG 2026-06-11 has the full record; remaining tasks here continue under the v1.1 program, NOT a reopened North Star) (**JUDGE WENT LOAD-BEARING Wed 6/10** — operator-signed flip after the CBRL first-fire demote (one-time litigation settlement, reviewed clean); **#189 #200 #201 #202 #203 CLOSED-AS-SUBSUMED 6/10 via #249** — the advisory stack (materiality_shadow, theme_gated_*, _compute_fire_status fire panel) retired into the one judge; judge verdict fire_axes is the fire signal, ADR 0010 superseded, weekly review carries one judge roll-up section; #202's discovery-latency goal carried by #211/#235; #190 was already done) (**#240 = EP Holistic Grade Judge umbrella, ADR 0011; #241 W0✓ DONE; #242 W1 judge shadow-emit shipped; #243 W2 judge-supersedes-floor SHIPPED DORMANT (toggle OFF, flips 6/9); #244 W3 review surfaces (sweep + delta-review) built; #245 W4 consolidate advisory stack — flip-gated. Committed acceleration: North Star DONE 6/13; SiP→judge expansion DEFERRED per operator, per-setup judges not one universal**) (#236 = make corpus_provenance a BYPRODUCT of build_grounded_text — the grade-input/source-class decision is split across 3 lockstep sites (grader fallback + build_grounded_text membership + corpus_provenance re-derivation); refactor to {text,sources} so #211 KPI can't silently miscount; /simplify 6/7 altitude finding, do AFTER Mon 6/8 verify + as Wave-D #234 groundwork; **#219** = weekly verified-miss review — systematic missed-winner analysis from /missed, with #197/#199; **#197 = cap+1 game_changer slot SHADOW shipped 6/6 (`shadow_cap_plus_one_197.py`), promotion-gated N≥30+sign-off; #198 CLOSED obsolete 6/6 — deprecated circuit_breaker, tiered drawdown breaker already covers it**) · **theme-validation correctness cluster**: **#213✓ DONE 6/9 VERIFIED-LIVE** (false-removal — shield+Haiku→Sonnet shipped 6/6; Mon 6/8 17:00 ET run clean on claude-sonnet-4-6, zero errors/shielded events, SNDK+SIMO retained in 'AI Memory & Storage'; 16 removals incl. 13 majors out of 'Pure-Play Hydraulic Fracturing' = the eval-predicted XOM/CVX class, list surfaced to operator not self-certified) → #214 (theme auto-NAMING defect — names narrower than the RS cluster, the oil&gas removal root cause; **SHIPPED 6/9 pending verify**: name-breadth-must-match-members rule in all 4 naming surfaces (discovery prompt/schema, split prompt/schema, Lane-2) + audit-only `validation_mass_removal_name_suspect` tripwire; misnamed frac theme already Retired/empty so no data fix; verify = next discovery runs' names + cooldowns_per_day back to ~3/day baseline) → #215 (surgical prompt de-bias / OPTX-residual — BLOCKED_BY #214 + needs a clean two-sided cohort + CHANGE_PROCESS; earliest after #214 lands) → **#266** (event-driven membership validation at theme BIRTH + identity-change, M/W/F demoted to drift backstop — operator architecture question 6/10 off the DDOG removal: entered at birth 3/20, sat mismatched 12wk, caught only after #213 model upgrade + #214 naming sharpened; CHANGE_PROCESS + replay-evidence gated) · **#267** (judge CHART-VISION input — point-in-time matplotlib renderer from mi_daily_closes + image block in grade_holistic + chart-structure rubric axis; with-vs-without replay + operator labels per the model-flip playbook; post-North-Star feature bucket, operator-directed 6/10) → #217 (query hygiene — **SHIPPED 6/9 pending deploy**: protected set fetched once/run + threaded through rescore/assign into validation (was 1 query/theme); run-level cooldown fetch reused for assignment (2→1). Deliberately NOT fully collapsed: the cooldown fetch must stay post-rescore — Mon/Wed/Fri validation ADDS cooldowns the same-run re-assignment guard must see) · **catalyst-sourcing backbone #210** (operator direction 6/5: DIRECT primary sources > LLM-discovery — umbrella over #187✓/#208✓/#191; PARKS #186) — **SCOPED 6/7 into Waves A-E** (`~/.claude/plans/catalyst-sourcing-backbone-210-scope.md`): **#231 Wave A** (wire Benzinga/Alpaca news into corpus + primary-subject relevance filter #88/#90 class — SHIPPED+DEPLOYED 6/7 `cbb7619`, grounded-only/activates Mon 6/8 scan — **NOT telemetry-safe**: Benzinga text feeds grade→ep_score→score_tier→HIGH→phase=paper ORB entries, so risk = systematic grade inflation on PR-having tickers; GRRR 6/2 validation `docs/analysis/wave_a_benzinga_2026-06-07.md`: GOAL = attribution CORRECTNESS (not winner-rescue/P&L — separate axes, memory `feedback-catalyst-correctness-is-the-goal`). Correctness DEMONSTRATED (isolated +1 tier strong→game_changer w/ correct sizing, lower-bound) + 6-K-lags-3d proves press-wire timeliness. Winner-rescue = supplementary evidence only, NOT a gate. Remaining: systematic correctness at scale via #211/#202 + Mon 6/8 first-fire verify) → **#232 Wave B** (source provenance — measurement enabler for #211; `corpus_provenance()` emits `ep_catalyst_provenance` audit per graded ticker: {sources:{class:count}, has_direct_source} mirroring the grade's INPUT BRANCH (fmp-fallback→`fmp_aggregator`, not `{}`); has_direct_source structural `sec_*|benzinga_pr` (Wave-D 425 safe). BUILT+18 tests 6/7, DEPLOYING 6/7 with a self-verifier: the 10:05 ET `_ep_scan_watchdog` now reads today's `ep_catalyst_provenance`, writes an `ep_provenance_daily` KPI audit row (graded/direct/unknown + by-class), and Telegrams 🔴 ONLY on the broken case (alerts but 0 provenance = silent path death). Monday verify = retrospective read of that row — provenance is also the observability that proves Wave A's Benzinga wiring fired) → **#233 Wave C** (demote Perplexity/Tavily to labeled candidate, blocked_by 231) · **#234 Wave D** ✓ DONE 6/7 (EDGAR breadth — shipped the tradeable core: 8-K EX-99.1 CONCATENATION for item 2.02/7.01/8.01 or thin primary, validated CRM/AVGO/COST/HPE/CRWD; 425-M&A DEFERRED = skip-only-upside + direction trap; foreign-issuer SKIPPED = 6-K done; NOT telemetry-safe → Monday inflation check covers) → **#238** (the REAL higher-value EDGAR gap: NEGATIVE-catalyst dilution filings S-3/424B5/8-K-3.02 for two-directional DOWNGRADE — the GRRR debt-drop class; feeds the #189 holistic judge) · **#235 Wave E** (gap-discovery loop #211 integration, blocked_by 232) · **#230** (#212 as sourcing-QA detector → feed #211: "hard gap + grounded no-catalyst" = sourcing-gap flag; LOW-precision triage) · **#211 news-gap discovery loop** (unknown-rate = source-coverage KPI; DEFERRED post-Monday — needs a new scheduler job + fire_status data that lands 6/8) · #208✓ (EDGAR 6-K foreign-filer gap — DONE 6/6) · **#212 questioner/investigator dialogic loop** (PROTOTYPE DONE 6/6 — mechanical grounding > LLM skeptic-PM; productionize post-Monday at larger cohort) · **model-eval governance #207** (quarterly review, auto-surfaces via `data_gated_reviews::model_selection_quarterly_review` 2026-08-01; SSoT `docs/model_selection_baseline.md`) · #186✓ (Gemini LLM-discovery — EVALUATED→PARKED under #210, DONE 6/6). (#197/#198 = quality-aware admission / conviction-override; re-bucket to Stocks-in-Play if preferred.) · **Judge follow-up cluster #247 #249 #251 #252 #253 #255** (filed in-tracker 6/8–6/9, backfilled to this view 6/9 — the session that created them was cut by a Claude update before the BACKLOG mirror): #247 (consolidate judge DB writes — atomic merge + one-time column-ensure; W2/W4 /simplify deferral) · #249 (post-flip: retire the advisory stack — materiality_shadow / fire-panel compute / theme_gated_* — into the one judge) · **#251✓ DONE 6/9 VERIFIED-LIVE (rule_materiality false-transformative noise — extract_deal_value now DEAL-CONTEXT-AWARE: metric veto + deal-keyword require, abstains on earnings revenue/guidance figures → judge owns materiality. Commit `269f33c`, deployed; prod probe over 165 alerts/45d: deal-value fired 99→28, KSS $3.17B-revenue→abstain. PGY kept $2.1B = correct residual: genuine "secured $2.1B ABS funding" transaction — routine-for-Pagaya is judge-context, and the judge already overrode it)** · #252 (judge model selection: Sonnet-vs-Opus diverge on THIN input, artifact-suspect — grounded re-run is the test) · #253 (judge --grounded over-demotes web/theme-driven catalysts, RCAT class — replay lower-bound caveat + theme-axis blank root-caused to Lane-1 missing the real drone cohort; motivates Lane-2 on the judge's theme axis) · #255 (ground-truth Phase 2 — judge-precedent retrieval kind='review' ONLY + periodic-review nudge + FSLY pre-coverage vs in-coverage-miss refinement; advisor-gated)
- **Operational safety / hardening**: #152 #172 #176 #179 #216 #237 #239 #256 #257 #258 #259 #260 #265 (**#265** = 6/10 advisor+simplify review residuals over the judge-flip-day diff: preflight_db_updates SQL-text SSoT hoist · shared ingested-feeds list (news_source_quality ↔ source_gap_finder) · merge the two mi_theme_candidates_shadow writers · WATCH judge-write cancellation window (advisor A3, ms-wide, >12-alert mornings); the load-bearing review fixes were applied same-session · **2026-06-09 Fable 5 architecture-review cluster + operator staging directive**: **#256 BIG ROCK** = execution/intelligence service split + STAGING pipeline before live money — operator-requested; needs its own scoping session, split targeted before 6/22; ⚠ propose adding to the Active Major Projects roster · **#257** = central LLM model registry `shared/llm_models.py` + literal-ban deploy gate [5i/7] + FIRST CI workflow — SHIPPED 6/9 `c6ed3f5`+`39ff49a` (theme advisor opus-4-6→4-8 flip; Opus pricing rows were 3x stale at $15/$75, actual $5/$25), verify = next deploy [5i/7] + first Actions run + advisor_call logs 4-8 · **#258** = boot-time ensure_schema() consolidating the 92 scattered ADD-COLUMN sites + db.py domain-package split — generalizes the judge column-ensure cleanup (task 247 part 2, filed under North Star), SAME GATE (post judge first-fire) · **#259** = failure-policy decorators (@advisory_fail_open / @trade_state_fail_loud) — make the 492-site except-Exception policy declared not re-decided · **#260** = freeze the execute_task keyword cascade: routing regression test now, orchestrator-side intents later, merge the 3 ticker skip-sets · **#263** = nightly_data_pull 'empty_result' two consecutive nights (~3.9k rows vs 5k floor, nightly false/real-alarm Telegram) — diagnose stale floor vs missing writer, filed 6/9 · **#264** = news-source-quality drift check needs min-N floor + composition context — 6/9 'Benzinga 68%→20%' alert diagnosed FALSE ALARM (n=10, earnings-season-tail cohort cites Perplexity; alpaca content present 7/10; will re-fire daily on thin weeks until fixed)) (**#205✓ DONE 6/7** — closed the 3 redesign-needed stale tests: test_returns_themes_list skip was stale + a _get_anthropic_client global-cache leak (patch the getter, not AsyncAnthropic); 2 theme-notification tests reworked with real-ticker fixtures + mocked RS getters + 'THEME ENGINE — N active'. Full suite 553 pass / 1 env-skip; #239 = 6/7-late /simplify deferrals, both post-Monday: (a) Wave-A trailing-baseline dup across verify_monday_firstfire ↔ _wave_a_grade_inflation_check — extract to a DURABLE home (not import-from-disposable) when _wave_a graduates/3rd consumer; (b) `_emit_shadow_row` envelope helper for run_ep_scan's per-ticker shadow emits (tape/perplexity_boost/provenance) — defer, hot-path first-fires Mon; **#221✓ #222✓ DONE 6/7** — deploy.sh governance/docs/tests deploy-irrelevant + missed_outcomes duplicate_scan SQL DRY'd to one constant; #237 = extract a shared scheduled_eod_digest helper for the ~6-job 16:xx digest family (window/dedup/rank/cap-overflow/suppress-empty/trading-day-guard) so they can't re-diverge — /simplify 6/7 altitude finding; the two concrete divergences it surfaced (both digests at 16:00 → staggered to 16:20; 9M pace missing trading-day guard → added) were FIXED inline 6/7, this is the abstraction follow-up, low-urgency, gated post-Monday-first-fire; #172 = partial-exit /simplify refactor, gated behind the partial-exit hardening architectural split; #176 = automated SoT/roster drift-check — reconcile CORE + pre-commit Gate 2 SHIPPED 6/6, remaining = create-time hook + scheduled ping; #205 = stale-test fix; #216 = jsonb codec consolidation — root-fix of #179's per-site _jsonb_param, high blast radius, gated past 6/22)
- **Apollo Trades dashboard** (portfolio-app2): #185 (corrupt-stop exclusion-count display; #175 core ✅ DONE 6/3) · #194 (daily auto-export of BOTH snapshots — trades + themes; re-filed here from Apollo Themes 6/10 after the trades snapshot sat stale at 6/03 for a week; export SQLs saved, design question = repo-scoped deploy key to the public repo, pair with #195)
- **Apollo Themes** (portfolio-app2): #193 (RS theme rank-evolution tab, in-flight; snapshot freshness rides #194 under the Trades-dashboard project)
- **Miscellaneous** (no home project): #121 (briefing → shared Telegram formatting layer) · #195 (SECURITY — rotate portfolio-app2 app_password; operator-action) · #228 (weekly-review narrator: stop mis-flagging reentry-block-after-fill as "traded through" — 3wk recurring false alarm, verified 6/7; low-pri review-quality) · #246 (theme_engine.py:3011 isinstance(anthropic.APIError) TypeError in local test env — not prod, not in judge diff) · #248 (regime engine: post-pullback caution/hysteresis term + spy_vs_200ma NULL fix + stale Bull=70 docstring; filed 6/8, backfilled to this view 6/9) · #261 (scripts/ namespace reorg — 172 files: split ops/evals/probes, one mechanical PR w/ path-reference sweep; 6/9 review hygiene tier) · #262 (CLAUDE.md over its 40k hard ceiling since ≥5/29 — graduate Recent entries to CHANGELOG + cut mechanically-enforced prose + consider pre-commit char-count warning; promoted from 5/29 closer-prose on 6/9 operator audit)

_Re-swept 2026-06-05 (44 open tasks: 31 pending + 13 in_progress) — ALL 44 mapped, completed tasks dropped from the hierarchy (the prior 6/2 sweep had gone stale: 17 post-6/2 tasks unmapped + #174/#180/#181/#182 listed-but-done). New buckets: Apollo Themes (portfolio-app2, #193/#194) split out from the dashboard project. Closeable candidates flagged: **#166** (past-due U&R 6/1 verify — confirm-and-close) · **#172** (blocked on #151 architectural split). Judgment calls (re-bucket freely): #197/#198 → North Star (quality-load-bearing) vs Stocks-in-Play (admission); #149 moved Op-safety → North Star (it's catalyst-grade quality); #192 → North Star (grade-path DRY) vs Op-safety (gate gap)._

---

## 🎯 Key Target Dates

### ✅ Resolved since last refresh
- **5/20 extraction-pipeline smoke** — passed (composition ran clean on live alerts; no `extraction_error` storm). Closed.
- **5/22 live-cutover decision** — **DEFERRED** as expected (#61). Gate 3 still RED (paper R-expectancy N≈4, net negative). Re-evaluates when cohort reaches N≥10 positive — realistically mid-June+. Pradeep selectivity fires few trades; this is expected.

### 🔴 NEW hard live-cutover gates from the 2026-05-27/28 IBM cascade (block flip until clean)
- **Partial-exit hardening N=7 clean cycles** (`partial_exit_hardening_n7_clean_cycles`) — safety trio shipped + verified 5/29 (G6 + verify-stop-live + circuit breaker + durable integration test); IBM canary clean (+$226.37, cycle 1/7). Need 6 more clean cycles post-breaker-success-awareness. 16:45 cron PAUSED until Monday re-enable sequence (memory `project_151_partial_exit_hardening_wip`).
- **#150 Alpaca stop-trigger / share-reservation race** — CONFIRMED 5/29 (held_for_orders lag after atomic replace); verify-poll incidentally mitigates. Explicit sell-retry fix → Monday. Threshold=1 = structural.
- **#142 RDW stuck pending_new watchdog** — must root-cause + ship before flip (`orb_entry_stuck_pending_new`, threshold=1).

### 📅 Thu 2026-06-19 — First B6 backtest + 3 calibration reviews ripen
~30 days post the 2026-05-19 multi-source extraction ship; carry-forward cohort hits ≥30 rows. Four reviews ripen same date:

| Review | What |
|---|---|
| `b6_forward_backtest_first_eval` | Replay rubric vs accumulated cohort. Decision: keep threshold=22 / lower / raise. |
| `rubric_safety_net_yoy_required` | Count YoY-missing cases. Ship calibration fix if ≥10 with fwd-edge. |
| `theme_axis_gating_logic` | Crosstab theme_stage × fwd_return on ≥30 HIGH alerts. Decide gating modifiers. |
| `nbis_rubric_calibration_gap` | One-fixture investigation (~30 min) — doesn't strictly need 30d cohort. |

Build `scripts/_b6_forward_backtest.py`, pull crosstabs, decide ship-vs-collect-more. **Trackers**: 4 reviews in `data_gated_reviews.yaml` (filed 2026-05-19).

---

### 📅 3. Thu 2026-06-19 — First B6 backtest + 3 calibration reviews ripen
**~30 days post the 2026-05-19 multi-source extraction ship. Carry-forward cohort hits ≥30 rows. Four reviews ripen on same date:**

| Review | What |
|---|---|
| `b6_forward_backtest_first_eval` | Replay rubric against accumulated cohort. Decision: keep threshold=22 / lower / raise. |
| `rubric_safety_net_yoy_required` | Count YoY-missing cases. Ship calibration fix if ≥10 cases with fwd-edge signal. |
| `theme_axis_gating_logic` | Crosstab theme_stage × fwd_return on ≥30 HIGH alerts. Decide gating modifiers. |
| `nbis_rubric_calibration_gap` | One-fixture investigation (~30 min) — can do anytime after 5/22, doesn't strictly need 30d cohort. |

**What to do** (full session, ~3-4 hours):
1. Build `scripts/_b6_forward_backtest.py` per `b6_forward_backtest_first_eval` action plan.
2. Pull crosstab outputs. Read patterns.
3. Decide: ship calibration changes OR collect 30 more days.
4. If shipping changes: write to `docs/decisions/0003-ep-selectivity-overhaul.md`, ship with shadow-first gating where possible.

**What to expect**:
- B6 will give the first REAL signal on whether rubric gate threshold=22 is correctly calibrated. Forward operator feedback over the same window adds qualitative signal.
- Theme axis gating crosstab likely shows clean Accelerating > Mainstream > Fading ordering — if so, ship shadow-tracked modifier.
- YoY-safety-net review may not have N≥10 yet (depends on how many post-ship alerts hit this edge case). If <10, defer 30 more days.

**Trackers**: 4 reviews in `data_gated_reviews.yaml` (all filed 2026-05-19)

---

## 🚧 Live-cutover blockers

Live-$ flip cannot happen until ALL of these are green.

- [x] ~~**Gate 5 G — Column-write audit invariant**~~ ✅ SHIPPED — `scripts/audit_column_writes.py check` wired into `deploy.sh` as `[5c/6]` (runs green every deploy).
- [ ] **NEW (IBM cascade 5/27-28) — partial-exit hardening N=7 + #150 stop-trigger + #142 RDW pending_new** — see 🎯 Key Target Dates "NEW hard gates" above. Safety trio shipped 5/29; need N=7 clean cycles + #150 explicit fix + #142 watchdog before flip.
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
- [ ] `extraction_pipeline_first_live_run_smoke` (5/20) — first composition smoke test of 2026-05-19 ship → YAML
- [ ] `gate5_adel_deliverables_status_check` (5/21) — verify A/D/E before 5/22 cutover review → YAML
- [ ] `nbis_rubric_calibration_gap` (5/22, no predicate gate — ~30 min investigation) → YAML
- [ ] `silent_failure_taxonomy_audit` (5/26 — taxonomy + critical-path audit + batch ship by class) → YAML
- [ ] `theme_assignment_sndk_class_refinement` (5/15) — diagnosis done, structural fix remaining → YAML
- [ ] `minute_volume_curves_baseline` (5/15) → YAML
- [ ] `unified_allocator_phase_1b` (5/15, #44 cross-strategy allocator) → YAML
- [ ] `pass1_protect_strip_equalsize_test` (5/15, test fixture) → YAML
- [ ] `gate5_tomorrow_verifications` (5/15, 5-item checklist) → YAML
- [x] ~~`ep_selectivity_deep_dive`~~ ✅ **SHIPPED 2026-05-17** (commits 9787527/939c314/cf9167c/643a577/3421a15/d214ba9 + Phase 7 commits 34fd3cc/54be094/370aed1/f025737/46ba0d2/8e8f6f3). Phase 2 + Phase 7 filter ships + bug fixes + stop-ACK gate. Phase 3-9 follow per `~/.claude/plans/i-want-to-plan-groovy-horizon.md`. Status closed in YAML.
- [ ] `p74_alpha_capture_stage2` (6/8 — re-run Block D 21d post-P7.2/P7.3b ship; MAGNA53 capture 34% → target 60-70%) → YAML
- [ ] `phase3_telemetry_coverage_check` (5/27 — 7d after Phase 3 ships, audit count ≈ ep_alert count ≥90%) → YAML
- [ ] `phase5_meta_rubric_calibration` (9/8 — N≥30 paired-score settled, fit composition weights) → YAML
- [ ] `phase6_meta_rubric_gating` (9/29 — N≥20 advisory settled with R+, ship gating filter) → YAML
- [ ] `catalyst_rubric_quarterly` (12/29 + 90d cadence — per user_quarterly_rule_review memory) → YAML
- [ ] `rel_volume_large_cap_floor_evidence` (7/1 — N≥10 CSCO-class evidence batch) → YAML
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
- [ ] `b6_forward_backtest_first_eval` (6/19, N≥30 cohort) → YAML — **see 🎯 Target Date 3**
- [ ] `rubric_safety_net_yoy_required` (6/19, N≥10 YoY-missing cases) → YAML
- [ ] `theme_axis_gating_logic` (6/19, N≥30 HIGH alerts) → YAML
- [ ] `ninem_day2_mechanical_vs_methodology_alignment` (7/15, N≥10 9M Day 2 closed) → YAML — architectural question filed 5/21 after ROIV trigger case
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

> **Spot-check 2026-05-29** (cross-referenced against git log since 5/17): SHIPPED
> since filing — M&A direction-awareness (#90 Parts A/B/C + #119), theme
> misclassification mitigations (#125 2-member grading + #126 coherence guard),
> Perplexity-disclaimer display sanitizer (#130). CORRECTLY OPEN — the EP-rollout
> Phases 3–9 (date-gated, see "EP rollout" subsection), the 8 catalyst-extraction
> misses (Phase 8), and the parked R4/R5/R7 dispositions (await Phase 5/9
> evidence). The remaining items below are genuine open investigations/ideations,
> not yet individually re-verified line-by-line.

- [ ] **Breadth cluster-view + surface/compute gap** (2026-05-15) — Pradeep tweet showed Stockbee Market Monitor as CLUSTER-MATRIX (date × indicator), red-cluster runs visually obvious. Inventory: compute-AND-surface: 50%/M, 25%/Q. Compute-but-not-surfaced in evening brief: 25%/M, +/-4% 5d/10d, T2108, consec 700-down-4%. Truly missing: 13%+/34d, Worden. Two prongs: (a) cluster-matrix render, (b) low-cost surface 25%/M into briefing + compute 13%+/34d. Pure observability — ideation in `data_gated_reviews.yaml::breadth_cluster_view_ideation`.
- [x] ~~**Leveraged ETF upstream filter gap** (2026-05-17)~~ ✅ **RESOLVED same-day (P2.0b)** — fix shipped in `ep_detector.py:608-700` the same day this note was filed (note never closed). Two layers: `_non_stock_tickers` excludes classified ETF/ETP, AND a fail-safe skips *unclassified* candidates (the actual USAX/USGG path — weekly-refresh gap). Verified in prod 2026-05-29: USAX/USGG now classified `ETF`; ZERO non-CS/ADRC tickers in `mi_ep_alerts` since 5/17.
- [ ] ~~**M&A buyouts past direction-aware filter** (2026-05-17)~~ ✓ **investigated 2026-05-17 PM** — ma_filter not actually broken. BZH 5/11 alert preceded the Dream Finders hostile-bid news by 2 days (Polygon: 0 items in 90d window before alert; first M&A headline 5/13). KALV 4/29 preceded M&A class-action notices by 13 days (first headline 5/12). Both labels were hindsight-correct from news that surfaced AFTER alert time. Filter is working correctly.
- [ ] **Post-alert M&A backfill check** (Phase 8+, 2026-05-17) — when M&A news surfaces within 2 weeks of an alert that triggered a paper trade, retroactively flag the trade for review. Today's gap: BZH 5/11 + KALV 4/29 would have been ENTERED if they made it through filters (in BZH's case the hostile bid didn't surface until 5/13, by which point any Day-1 entry would have already stopped or been pinned by deal-cap). Better detection requires either (a) speculative pre-news shape detection (KALV gapped on no Polygon news — that itself is a signal) or (b) post-fact reconciliation that retroactively tags the alert outcome with "M&A revealed within 14d" context. Not a filter, just outcome-attribution data quality.
- [ ] **R1 (drop MODERATE auto-actions) defensive guard** (2026-05-17) — P2.1d investigation found R1 is already effectively in place: every entry pipeline (live_tracker.py:324, backtester/tracker.py:251, engine.py:534, shadow_orb_tracker.py:346, audit_invariants.py:387/404, scheduler.py:1621, system_audit.py:188/196/354) filters `score_tier='HIGH'`. 0 MODERATE alerts traded in last 60d. R1 ship was a no-op. Optional defensive followup: add explicit env-flagged guard at score_tier assignment so a future code change can't accidentally introduce a MODERATE auto-entry path. Low priority — current architecture is self-enforcing.

### EP rollout — multi-phase tracker (per `~/.claude/plans/i-want-to-plan-groovy-horizon.md`)

The full EP rollout spans Phase 1-9. Phase 1 (diagnostic) + Phase 2 (immediate ships) + Phase 7 (alpha-slip hedge) shipped 2026-05-17. Remaining phases below; each becomes its own data-gated review once the prerequisite phase ships.

- [x] Phase 1 — Diagnostic ADR (`docs/decisions/0003-ep-selectivity-overhaul.md`) ✅ shipped 2026-05-16
- [x] Phase 2 — Filter ships (R2/R4/R6/R3 + bug fixes + SSoT) ✅ shipped 2026-05-17
- [x] Phase 7 — MAGNA53→flag + 9M universe-watch + stop-ACK gate ✅ shipped 2026-05-17
- [ ] **Phase 3** — Meta-rubric telemetry: wire catalyst_rubric + theme_context scoring into production scan path. Emit `catalyst_rubric_scored` + `theme_context_scored` audit events. Background fundamentals refresh job. Target week of 5/19. Verification: `phase3_telemetry_coverage_check` review.
- [ ] **Phase 4.1** — Technical structure score (gap-above-MAs, base shape, 52w distance, RS rank). Target week of 5/26+. SSoT `docs/setups/technical_structure.md`.
- [ ] **Phase 4.2** — Gap alignment score (gap-through-resistance, gap into open air, round-number proximity). Target week of 5/26+. SSoT `docs/setups/gap_alignment.md`.
- [ ] **Phase 4.5** — Weekly operator catalyst review job (per user idea 2026-05-17): Friday EOD/Saturday AM scheduled job surfaces week's HIGH-EP alerts (especially traded names) for operator catalyst-correctness labeling. Ongoing label collection feeds Phase 5 calibration. Reuse catalyst_labels.csv schema.
- [ ] **Phase 5** — Composition + calibration (after N≥30 settled paired-score alerts). Target week of 9/8+. Verification: `phase5_meta_rubric_calibration` review.
- [ ] **Phase 6** — Gating ship (after N≥20 settled advisory alerts with R+). Target week of 9/29+. Verification: `phase6_meta_rubric_gating` review.
- [ ] **Phase 8** — Catalyst extraction pipeline fix (8 mislabeled names + CRML date). Investigation depth unknown; runs parallel.
- [ ] **Phase 9** — First quarterly catalyst rubric review (Phase 6 ship + 90d). Verification: `catalyst_rubric_quarterly` review.

### Surfaced 2026-05-18 (Monday market open)

- [x] **Investigate GOOGL stop_order_id NULL trigger** (2026-05-18) ✅ RESOLVED — Stops are GTC (not DAY); Friday expiration ruled out. Most likely cause: during Saturday's 14 Track 1 container restarts, Alpaca WS dispatched a backlogged cancel/reject/expired event for d3b1850f. Pre-T1.5a `_handle_cancel_or_reject` nulled stop_order_id via inline SQL UPDATE without any audit log — silent state mutation. T1.5a (today) closes the gap: future occurrences will emit `stop_order_id_changed` audit event with `reason='cancel_or_reject_null'`. Defense in depth (watchdog + morning_stop_refresh) sufficient. No additional code change. See docs/setups/safeguards.md change log for full timeline.

### Surfaced 2026-05-17 PM (weekly review + Phase 7)

- [x] **Track 1 T1.3 — live_tracker close path delegation** ✅ SHIPPED 2026-05-18 (commit 85ab8b0). Close path delegated to `finalize_stop_fill` with synthetic deterministic order_id. live_tracker dropped from ALLOWED_WRITERS for status / exits / remaining_shares / total_pnl / closed_at / stop_order_id / stop_price. Stop_price writers cut 4 → 3.
- [x] **Track 1 T1.5a — `set_stop_order_id` helper consolidation** ✅ SHIPPED 2026-05-18 (commits 1d14934, fcdeb68, 296d87f). Helper `set_stop_order_id(trade_id, new_id, *, reason, account_mode)` in order_manager.py. 11 solo write sites refactored across order_manager.py + trade_stream.py + scheduler.py. Multi-column atomic closes stay inline. Reason taxonomy with 11 codes. Emits `stop_order_id_changed` audit event. Site count 47 → 37.
- [ ] **rel_volume floor 0.5× for large-cap EPs** (weekly review 2026-05-17 proposal #2) — CSCO 5/14 had rel_volume=0.04 at alert time, ORB fired, price never traded above entry tick. Single-case evidence (N=1) → file as data-gated review with predicate "N≥10 EP alerts with rel_volume <0.5× AND ADV >$50M". Not ship today.
- [ ] **5-min ORB analysis** — 40% of this week's 5 losers (`orb_5_verdict: would_block`) would have been blocked by 5-min gate. C1 dimension in cohort analysis. Belongs to Phase 5 composition calibration; not a current ship.
- [x] **MRAM methodology-attribution fix** ❌ REVERTED 2026-05-18 — user-flagged investigation revealed MRAM was a legitimate Day-1 re-entry, NOT a phantom double-exit. Broker order history (`mi_live_orders` for trade_id=120) shows: entry #1 88780cd8 filled 419@$36.52 at 13:37, stop #1 b59f5633 fills @ $33.90 at 13:42 (-$1,101), entry #2 f7d0cad4 (Day-1 re-entry) filled 419@$36.50 at 13:50, stop #2 hits at 13:59 (-$1,097). Both losses real. -$2,199.71 is correctly recorded. The weekly review's "phantom double-exit" framing was WRONG. pnl_attribution tag REMOVED — MRAM stays in methodology cohort. **Lesson: don't trust weekly-review claims without verifying broker order history.**
- [ ] **Theme misclassification follow-through** (weekly review 2026-05-17) — SNDK→wafer equipment, AGRO→nitrogen fertilizer. Cooldown system caught 45 mismatches this week. Trend stable. Data-gated review `theme_assignment_misclassification` flagged by weekly review; pull 2026-05-14 theme run audit events around SNDK to diagnose.
- [ ] **Cross-strategy allocator Phase 1B promotion** (weekly review 2026-05-17) — 14-day audit event pull for `unified_allocation_decided`. Separate workstream, not in EP path.
- [ ] **Perplexity disclaimer sanitizer for display surfaces** (weekly review 2026-05-17) — `_strip_perplexity_disclaimer(text)` helper exists in collector.py but cosmetic gap remains: `/trades`, briefing, weekly review show disclaimer text verbatim. Sanitizer filters M&A keyword scan path only.
- [ ] **RVOL@T baseline depth verification** (weekly review 2026-05-17) — confirm 400+ tickers have all-anchor samplen ≥ 10. Quick query.



- [ ] **P7.3b — 9M → flag universe expansion (Pradeep methodology scope)** (2026-05-17, in-flight) — Ships Monday morning before market open. Per `user_pradeep_9m_universe_methodology.md`: 9M EP = universe-to-watch trigger (not directional signal). ALL 9M EPs (sugar baby + failed-Day-2 + intraday-only) enter flag detector universe with tag `'ninem_universe_watch'`. Source `mi_9m_ep_alerts`, 14-day rolling window. Env flag `NINEM_FLAG_CARRYFORWARD_ENABLED`. Also requires SSoT update in `docs/setups/ninem.md` (deferred from P7.2 SSoT commit `9cb61b5`).
- [ ] **R4 paired threshold review** (2026-05-17) — R4 (in-theme +10 bonus) shipped as telemetry-only because pre-ship SQL found 0 MODERATE-in-theme alerts would cross HIGH threshold (=70) with +10. Phase 5 meta-rubric calibration is the natural home for this — the composite gate will subsume the threshold question. Until then, the +10 in score breakdown is just for Phase 5 regression data collection. No urgency.
- [ ] **`_unclassified_skipped` monitoring** (P2.0b 2026-05-17) — If aggregate count consistently ≥10/scan over multiple days, bump `mi_security_types` refresh cadence from weekly Monday to daily. Trigger: watch `EP scan:` log lines over the first 2 weeks post-ship.
- [ ] **Fundamentals fetcher `data_quality_flag` downstream consumers** (P2.0a 2026-05-17) — fetcher now sets `data_quality_flag='fiscal_attrs_missing_fallback_index'` when yfinance-source data lacks `(fiscal_year, fiscal_period)` and falls back to index-based Y/Y lookup (NBIS-class). When Phase 3 telemetry ships, the catalyst rubric scoring path should READ this flag and emit a downgraded confidence audit signal — don't trust composites computed from index-fallback data.
- [ ] **VSNT/ARX/HUT rubric re-verification at Phase 5** (2026-05-17) — Post-fetcher-fix, VSNT 32.5 → 17.3 (routine_correct), ARX 24.4 → 17.3, HUT now properly scored. When Phase 5 calibration runs against operator labels, verify these fixtures still grade correctly and the data is stable across multiple weekly fetcher refreshes.
- [ ] **R5 (session_rvol loosening) — final disposition** (2026-05-17) — Retrospective sim during Phase 1 showed R5 doesn't hold up when properly windowed (12 candidates, -0.7% avg ret). NOT shipped. File closes here unless Phase 9 quarterly review re-surfaces evidence; otherwise leave parked.
- [ ] **R7 (catalyst-grader latency) — Phase 8 work** (2026-05-17) — Block 5 latency audit found HUT/FROG/PGNY had 170-min latencies, first blocker `score < 50` (LLM grader slow). Separate infra investigation, not a filter change. Phase 8 alongside the 8 catalyst-extraction misses (AMBQ, BAND, LIVN, NMAX, RSI, SIBN, STUB, VG).
- [ ] **Phase 7 Stage 2 verification** (2026-05-17, scheduled 2026-06-07+) — At Day 21+ post-P7.2-ship, re-run `scripts/ep_delayed_capture_audit.py` to measure if MAGNA53-failed alpha capture rose from 34% → projected 60-70%. Schedule reminder, not actionable yet.
- [ ] **9M baseline correction note** (2026-05-17, P7.3a finding) — 9M cohort organic capture was already 54.5% before any P7.3 work (much higher than MAGNA53's 34%). P7.3b expected lift is smaller than P7.2's. Note in P7.4 verification commit message AND remember that R3 might REDUCE the 54.5% baseline by removing "next MAGNA53 EP within 21d" capture path for 9M-side cohort. Stage 2 audit must report pre/post R3 baseline change separately.
- [ ] **Phase 8 catalyst extraction pipeline fix** (2026-05-17) — 8 mislabeled-catalyst names need root-cause investigation: AMBQ 5/12, BAND 4/30, LIVN 5/06, NMAX 4/22, RSI 4/29, SIBN 5/12, STUB 5/14, VG 5/12. Plus CRML 4/27 date mismatch. Trace `mi_ep_alerts.catalyst` population pipeline (Polygon news → Claude classifier → Perplexity validation). Likely root causes: news lookback window too narrow, headline selection prefers first vs most-relevant, or Perplexity hallucination (separate filed review). 4-8 hr investigation depending on root cause.
- [ ] **AIP non-EP admit followup** (2026-05-17) — AIP 5/13 was a trend-continuation pullback, not an EP per operator label. Suggests MAGNA53 sometimes admits non-EP shapes. Methodological cohort review; low priority, batch for quarterly review.
- [ ] **Operator label second-pass for divergence cases** (2026-05-17) — VIAV 4/30 has notes saying "strong based on RS/theme" but labeled `routine_mislabeled` — label inconsistency. VSNT 5/14 label was right per VSNT's bug correction. ARX 5/14 rubric catches acceleration prose missed. Worth a 15-min operator re-review of these 3 names when convenient.
- [ ] **Catalyst extraction misses key news** (2026-05-17) — 8 cases (AMBQ 5/12, BAND 4/30, LIVN 5/06, NMAX 4/22, RSI 4/29, SIBN 5/12, STUB 5/14, VG 5/12) — system `catalyst` column doesn't capture the real news (operator notes: "catalyst missed on this one"). Data-capture issue affecting every downstream consumer (LLM grader, rubric, briefing). Investigate news fetch + catalyst-tagging pipeline. Higher-priority than the rubric tweaks because it's an INPUT data quality issue.
- [ ] **Catalyst date mismatch — CRML 4/27** (2026-05-17) — system assigned catalyst date doesn't match actual news date (operator: "Greenland approval was 4/17, private placement 4/21, European Lithium 4/27 — which is the catalyst?"). Investigate detector-day-of-news pipeline; how does the system pick alert_date vs news_date? Single case for now, file for next session.
- [ ] **Non-EP setup admitted as EP** (2026-05-17) — AIP 5/13 was a trend-continuation pullback, not an EP per operator. Suggests MAGNA53 sometimes admits non-EP shapes (post-base trend continuation looks similar to gap-EP intraday). Methodological cohort review; low-priority single case, batch for quarterly review.
- [ ] **Rubric-vs-operator disagreement cases** (2026-05-17) — VSNT 5/14 (rubric=game_changer, operator=routine_mislabeled with no note), VIAV 4/30 (operator labeled routine_mislabeled but note says "strong based on RS/theme" — likely label inconsistency), ARX 5/14 (rubric catches acceleration that prose missed). Worth operator second-pass review; useful as quarterly rubric calibration cases. **UPDATE 2026-05-17 PM**: VSNT discrepancy resolved by P2.0a fetcher fix — VSNT now correctly scores routine_correct (17.3); was bug-fabricated 32.5 from temporal-mismatch.
- [ ] **Weekly catalyst review for HIGH-EP alerts** (2026-05-17, user idea) — Apollo-scheduled weekly job (Friday EOD / Saturday AM) that surfaces the week's HIGH-EP alerts, especially traded names, for operator catalyst correctness labeling. Goal: ongoing label collection mechanism (the manual 97-label sweep was a one-shot; can't tell over time if grader drift improves or worsens without continuous labels). Output flows into catalyst rubric quarterly calibration data. Design questions: Telegram-deliverable format vs Streamlit form vs CSV email? Auto-extract traded names from `mi_live_trades` + HIGH unentered from `mi_ep_alerts`? Reuse the `catalyst_labels.csv` schema (ticker / alert_date / catalyst / user_label / user_notes). Should fold into Phase 3 telemetry rollout — the weekly labels are the human-in-the-loop signal that pairs with `catalyst_rubric_scored` audit events for closed-loop calibration.
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

### 2026-05-29 (push-through session — see CLAUDE.md "Changes Made" for detail)
- [x] **#151 partial-exit hardening safety trio** — G6 deploy gate (`scripts/preflight_replace_order_smoke.py`) + verify-stop-live runtime check (`execute_partial_exit` Step 1b) + outcome-history circuit breaker. Plus durable integration test (`scripts/integration_test_partial_exit.py`). IBM `/partialnow` canary clean (+$226.37). Cron PAUSED until Monday.
- [x] **#150 share-reservation race CONFIRMED** — mechanism nailed (held_for_orders lag); explicit sell-retry fix → Monday.
- [x] **#153 Telegram polling-bot watchdog** — `HeartbeatExtBot` + market-agent `_telegram_poll_watchdog_job`; detection 7d→~5min; verified advances/trips/dedupes/recovers.
- [x] **#154 deploy.sh scope-drift guard** — no-arg errors (tier-1) + pull-diff abort if scope excludes changed-service (tier-2); locally tested.
- [x] **Telegram formatting** — EP fully unified (HUD = `/ep` = briefing via shared `_format_ep_ticker_block`, rubric grade everywhere, single-message); L2 anomaly + parabolic-scan markdown offenders escaped/fenced (top of the 51-fallback/30d list). Directive: `feedback_telegram_formatting_systematic`.
- [x] **Leveraged-ETF filter** — verified already-resolved (5/17 P2.0b); closed stale index entry.
- [ ] **Monday opener** (memory `project_151_partial_exit_hardening_wip`): breaker success-awareness (close-on-success) → #150 explicit sell-retry → grep `execute_full_exit`/`update_stop` → re-enable 16:45 cron watched. Then bake integration-test script into image.

### 2026-05-22 → 2026-05-28 (compressed — detail in CLAUDE.md/CHANGELOG)
- [x] DR layer (encrypted secrets backup + `infra/restore.sh` + runbook + tmpfs hardening) #102–108
- [x] 3 intraday entry-technique detectors: flag-break #94, support-test #95, MA-pullback #96/#124
- [x] Stocks-in-Play Phase 1 #99 + Sugar Baby cohort #80/#83/#84
- [x] #123 DB↔Alpaca order-status reconcile; #127 mi_intraday_bars 9:30 write-through; #120 L2 holiday-awareness
- [x] #133 9M Pace hourly digest; #143 downgrade-alert morning digest; #148 digest markdown escape
- [x] Theme engine 2-member grading #125 + clustering-coherence guard #126
- [x] IBM cascade P1 fixes #136/#137 (atomic replace_order + sync_positions mass-close guard); #138 `/partialnow`+`/syncnow`; #139 boot-guard; #140 alert taxonomy

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
