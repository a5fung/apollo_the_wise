# PLAN — the single source of truth (projects · tasks · ETAs)

**This file is THE plan.** Every task lives here, under a project, with an `ETA` date and a `status`.
The long-horizon plan (the 6/22 launch) lives here too — as dated tasks, not a separate doc. There is no
second plan surface: the calendar is phone reminders only, the harness #-task list is a session scratch
mirror, `CHANGELOG.md`/git hold history. If it's planned, it's a line here.

**Line format** (strict — parsed by `scripts/check_plan.py`):
`- #<id> | <YYYY-MM-DD ETA> | <status> | <title>`   ·  status ∈ pending · in_progress · blocked

**The two rituals operate ONLY on this file:**
- **OPEN** (every session): run `python scripts/check_plan.py --today` → it prints OVERDUE + due-today open
  tasks. That list IS the day's plan. State it before reacting to anything.
- **CLOSE** (every session): every open task's ETA must be ≥ today. Rebump any past-due one to a real
  future date (or close it). File every new item as a line here under a project. Then commit — the
  pre-commit gate (`check_plan.py`) REFUSES the commit if any open task lacks a project, an ETA, or has a
  past ETA, or if an open harness task is missing from this file. No gaps, mechanically.

_Last CLOSE: 2026-06-16._

---

## Launch — 6/22 GO/NO-GO (the long-horizon plan, as dated tasks · SSoT-spec: docs/roadmap/launch-2026-06-22.md)

- #261 | 2026-06-17 | pending | scripts/ namespace reorg (ops/evals/probes split + path sweep) — needs a focused block
- #226 | 2026-06-17 | pending | R3 Lane-2 narrative→mi_themes canonization (advisory; blocked_by #214 naming stability)
- #266 | 2026-06-17 | pending | theme membership validation at BIRTH + identity-change (evidence run; CHANGE_PROCESS)
- #299 | 2026-06-19 | in_progress | P2 tape-features SLICE B. COMPUTE CORE DONE 6/17 (agents/market_intelligence/tape_features.py: compute_or_atr [reuses _atr_14] + compute_pm_vol_curve [compute_rvol_at_time] + compute_liquidity_tag + build_tape→None-when-empty=behavior-neutral; 10 tests, judge byte-identical preserved). NOT wired (nothing touches live judge). REMAINING (next focused block, eval-gated — judge is load-bearing): (1) scan fetches OR bars+ATR+premkt vol → build_tape → assemble_judge_inputs(tape=) behind a flag; (2) with-vs-without judge eval, segmented by which features present (TIMING: OR÷ATR only computable for post-9:35 alerts; pm-vol-curve is the pre-open feature). SLICE A structure shipped 6/16
- #267 | 2026-06-18 | pending | judge chart-vision: renderer + payload + rubric axis + with/without eval (operator labels ~6/18)
- #300 | 2026-06-18 | pending | P3 management-judge SHADOW (HOLD/PARTIAL/TRAIL/EXIT telemetry, zero authority)
- #255 | 2026-06-18 | pending | judge precedent-retrieval v1 (kind=review) + periodic-review nudge
- #238 | 2026-06-19 | pending | EDGAR negative-catalyst (dilution S-3/424B5/8-K-3.02) sourcing
- #301 | 2026-06-19 | pending | P1 ensemble-divergence SHADOW (2nd-model verdict on HIGH-tier)
- #302 | 2026-06-20 | pending | P6 replay-regression v0 (weekly scheduled selection-replay report)
- #55  | 2026-06-20 | pending | revenue-stage threshold quarterly review (REVENUE_STAGE_MIN_USD)
- #303 | 2026-06-20 | pending | full-program advisor review + launch-readiness checklist + DR restore rehearsal
- #304 | 2026-06-21 | pending | launch rehearsal (staging→prod) + GO/NO-GO evidence pack + docs/CHANGELOG
- #305 | 2026-06-22 | pending | 🚀 6/22 GO/NO-GO decision with operator (NO-GO under signed rules = launch-complete)

## Live-money cutover — MAGNA53 (the GO-direction gates)

- #150 | 2026-06-18 | pending | Alpaca stop-trigger / share-reservation race — explicit sell-retry fix (CONFIRM shipped)
- #151 | 2026-06-19 | in_progress | partial-exit hardening N=7 clean cycles (stalled on quiet flow, not failures)
- #183 | 2026-06-19 | in_progress | ORB classifier IEX/window mislabel
- #184 | 2026-06-20 | in_progress | broker-authoritative trade-state mirror (ADR 0008) increments 2/3
- #225 | 2026-06-20 | pending | resolve 3 demotion residuals (order_manager L584/905/1575) + blocking deploy gate
- #275 | 2026-06-19 | pending | kill/scale band digest evaluation + band-transition alerts + override awareness
- #316 | 2026-06-22 | pending | PDT / SEC-FINRA Rule 4210 — confirm ALPACA's rollout (not Fidelity's) + relax BLOCK_PDT_LOCKOUT via CHANGE_PROCESS (memory pdt_rule_4210_change_2026; revisit at cutover)

## Family A — consolidation plays post a runup (ADR 0013 · reset of #270)

- #270 | 2026-06-18 | in_progress | Phase 1 BUILT + VERIFIED 6/17 (new mi_anticipation_consolidation table + evaluate_consolidation + select_consolidation_keys carry-forward + paused job + 13 tests, all SHADOW). Live probe GREEN: COO IN on pure gate (1.153), proposer/confirmer agree, carry-forward absorbs the real 7/71 anchor drift. REMAINING: un-pause add_job + classify id + rewire /anticipation board (lifecycle→consolidation) + deploy market-agent; then confirm no dup rows after first 17:35 ET run
- #289 | 2026-06-18 | pending | folds into Phase 2 (shared universe+coil) — general-anticipation selection/ranking layer
- #297 | 2026-06-23 | pending | FAMILY B EP rework — inherits the gap-anchored replay()/evaluate_candidate + mi_anticipation_lifecycle + ARCHIVE/clean its phantom rows (decoupled from #270 Phase 1)
- #283 | 2026-06-23 | pending | wick_fill promotion eval (shadow→live), gated behind Family A

## Stocks in Play — detection / setups / entries / 9M / flags

- #286 | 2026-06-18 | in_progress | RS liquidity floor — VERIFY FAILED 6/16 (ASTC still #1 @ $12.7M); raise floor / cap-floor (gated)
- #271 | 2026-06-19 | pending | breadth-extreme detector wiring (analysis done; feed calculate_breadth_full + /regime cells)
- #168 | 2026-06-23 | in_progress | shadow-detector quality/actionability filter for LIVE-ping graduation (evidence-gated)
- #167 | 2026-06-23 | in_progress | Lane-2 narrative theme detector (shadow) — ongoing
- #170 | 2026-06-23 | in_progress | (Stocks-in-Play backlog item — confirm scope at triage)
- #56  | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #60  | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #65  | 2026-06-23 | pending | per-strategy sizing/cap follow-ups
- #81  | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #97  | 2026-06-23 | in_progress | (SiP backlog — confirm scope/title at triage)
- #113 | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #115 | 2026-06-23 | pending | /simplify deferral (filed #115)
- #116 | 2026-06-23 | pending | /simplify deferral (filed #116)
- #134 | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #146 | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)
- #178 | 2026-06-23 | pending | (SiP backlog — confirm scope/title at triage)

## Judge & catalyst — v1.1 program

- #284 | 2026-06-18 | in_progress | M&A acquirer-direction title-leak fix — awaiting operator sign-off (HARD-gate list) + shadow-validate
- #285 | 2026-06-19 | pending | graduate M&A accuracy review into monthly backward-check sweep (auto-run + Telegram)
- #317 | 2026-06-18 | pending | EP-alert `catalyst` field contradicts the judge (QURE 6/17: field says "no fresh catalyst/technical" while judge correctly grades game-changer FDA from the same 8-K). GRADE is right; the displayed catalyst narrative is stale/self-contradictory → align the displayed catalyst with the grounded analysis the judge reads, or suppress the "no catalyst" prose when has_direct_source + high grade. Trust bug on the load-bearing alert (pre-6/22)
- #319 | 2026-06-18 | in_progress | EP-alert grade-coherence (6/17 triage; judge load-bearing). DEPLOYED 6/17 (both, preflight 5a-5j green; container healthy). SHIPPED display fix: headline resolves to judge verdict (resolve_headline_grade), grade-provenance line Floor·Perplexity·Judge (kills the stale "agree"), theme judge-inferred line, rubric "not scored" line; 10:10 downgrade-digest annotates judge-promoted names. ADR 0011 addendum. VERIFY: provenance+headline on next live HIGH alert; digest annotation at 10:10 ET 6/18
- #320 | 2026-06-23 | pending | stale confidence_multiplier after a floor downgrade (ep_detector revenue-weak path keeps 1.2; hedge path resets). GRADE-AFFECTING — reset lowers ep_score → can flip floor_tier + the score<50 PRE-JUDGE skip (gates what reaches the judge). CHANGE_PROCESS + backtest the pre-judge gating effect before shipping. + open governance: keep Perplexity's mechanical ep_score boost under a judge that doesn't consume it, or make it display-only provenance?
- #321 | 2026-06-23 | pending | missing prior-year YoY = SHARED ROOT of rubric=None AND the spurious revenue-weak strong→routine downgrade (JBL/LZB 6/17, q_revenue_usd.yoy_pct None). Wire the deterministic yfinance YoY (already shadow-recovered) into the rubric input + the downgrade gate. Grade-affecting → ride #149 shadow→promote backtest (NOT cosmetic rubric display)
- #322 | 2026-07-01 | pending | theme-detection gap (memory theme_detection_two_lane_architecture): judge inferred JBL's AI-infra theme that neither Lane-1 clustering nor Lane-2 narrative tracks — real coverage gap, not a label. Feed into P2/P4 narrative radar (#309/#311)
- #269 | 2026-06-19 | in_progress | rubric v3 verify (AKTS forward outcome = first live promote-cohort point) + promote-cap eval harness
- #210 | 2026-06-23 | pending | catalyst-sourcing backbone umbrella (direct primary sources)
- #211 | 2026-06-23 | in_progress | news-gap discovery loop (unknown-rate KPI) — needs new scheduler job
- #212 | 2026-06-23 | in_progress | questioner/investigator dialogic loop — productionize at larger cohort
- #230 | 2026-06-23 | pending | #212-as-sourcing-QA detector → feed #211 (low-precision triage)
- #233 | 2026-06-23 | in_progress | Perplexity repositioning — KEEP + integrate (operator-adopted 6/17, NOT cut): (a) feed its independent GRADE into the JUDGE as a LABELED second-opinion/disagreement signal — judge currently reads its [Web summary] text but not the Claude-vs-Perplexity grade disagreement (grade-path INPUT change → CHANGE_PROCESS + shadow eval, judge is load-bearing); (b) reposition Perplexity as a labeled RECENCY source only (its live-web edge), judge-adjudicated vs primary (#210), and RETIRE the mechanical floor confidence_multiplier boost (with #320). Was "demote Perplexity/Tavily to labeled candidate (Wave C)"
- #235 | 2026-06-23 | pending | gap-discovery loop #211 integration (Wave E)
- #236 | 2026-06-23 | pending | corpus_provenance as byproduct of build_grounded_text (DRY refactor)
- #214 | 2026-06-19 | in_progress | theme auto-naming breadth rule — verify (cooldowns back to ~3/day)
- #215 | 2026-06-23 | pending | surgical prompt de-bias / OPTX-residual (blocked_by #214 + clean cohort)
- #217 | 2026-06-23 | in_progress | theme validation query hygiene — verify deploy
- #258 | 2026-06-19 | in_progress | ensure_schema() consolidation (fold 33 ALTERs) — branch+staging-validated, post-#277
- #257 | 2026-06-23 | in_progress | central model registry verify ([5i/7] + CI + advisor logs 4-8)
- #259 | 2026-06-23 | in_progress | failure-policy decorators (@advisory_fail_open / @trade_state_fail_loud)
- #260 | 2026-06-19 | in_progress | freeze execute_task keyword cascade (routing regression test + merge ticker skip-sets)
- #237 | 2026-06-19 | pending | shared scheduled_eod_digest helper (the ~6-job 16:xx digest family)
- #239 | 2026-06-19 | pending | Wave-A trailing-baseline dedup + _emit_shadow_row envelope (/simplify deferrals)
- #265 | 2026-06-23 | pending | judge-flip-day review residuals (SQL-text SSoT, shared feeds list, WATCH cancel window)
- #264 | 2026-06-23 | in_progress | news-source-quality drift: min-N floor + composition context (false-alarm fix)
- #207 | 2026-08-01 | pending | model-eval governance quarterly review (data-gated)
- #197 | 2026-06-23 | in_progress | cap+1 game_changer slot SHADOW — promotion-gated N≥30
- #149 | 2026-06-23 | in_progress | (judge/catalyst quality item — confirm scope at triage)
- #165 | 2026-06-23 | pending | (judge/catalyst item — confirm scope at triage)
- #191 | 2026-06-23 | pending | (catalyst-sourcing item — confirm scope at triage)
- #192 | 2026-06-23 | pending | deferred-findings-to-task discipline follow-up
- #272 | 2026-06-22 | in_progress | LAUNCH 6/22 umbrella (SSoT docs/roadmap/launch-2026-06-22.md)
- #274 | 2026-06-19 | pending | 2-member theme immortality fix (dissolve-on-flagged-pair, CHANGE_PROCESS)
- #276 | 2026-06-19 | in_progress | W2 entry-mechanics program (Mon stop-geometry study next)

## Operational safety / hardening

- #288 | 2026-06-19 | in_progress | Prong B idle-review escalation — REDEPLOY DONE 6/17 (both-deploy; a6c45a0 ⊆ deployed HEAD, boot applied new schema, container healthy). Remaining verify-live: clean /reviews + escalation render on next idle-review fire
- #290 | 2026-06-18 | pending | fix dead_zone_reevaluation broken predicate (column dc_fwd.high does not exist)
- #291 | 2026-06-18 | pending | triage the 26 idle data-gated reviews (run/defer/ratify each; incl #54)
- #273 | 2026-06-19 | in_progress | LLM credit-exhaustion alerting — decorator-hook sweep + spend telemetry + low-balance warning
- #287 | 2026-06-23 | pending | partial-exit trade-state cleanup (FPS #183 stuck flag + 8-trade exits double-encoding) — operator-gated
- #277 | 2026-06-23 | pending | #256 split go-live: ✅ http-ORB handoff VERIFIED CLEAN 6/16 (RXT/NTLA); close after a 2nd HIGH-day confirm
- #278 | 2026-06-23 | pending | deploy.sh preflight role-aware (intelligence false-fail), low-urgency
- #279 | 2026-06-23 | pending | W2 split /simplify deferrals (derive _EXEC_HANDLERS; bidirectional partition guard; dedup feed resolver)
- #280 | 2026-06-23 | pending | staging own paper account (before any market-hours staging use)
- #281 | 2026-06-23 | pending | staging copy-not-derive hardening (restore fork + compose/env drift)
- #256 | 2026-06-23 | in_progress | #256 W4 closure (2-svc DR runbook · per-service uptime · nightly staging-restore)
- #176 | 2026-06-23 | pending | SoT/roster drift tooling — create-time hook + scheduled ping (residual)
- #216 | 2026-06-23 | pending | jsonb codec consolidation (root-fix of #179) — POST-launch by design (protects window)
- #172 | 2026-06-23 | pending | partial-exit /simplify refactor (blocked behind #151 architectural split)
- #152 | 2026-06-23 | pending | (op-safety item — confirm scope at triage)

## Apollo Trades dashboard (portfolio-app2)

- #194 | 2026-06-19 | pending | daily auto-export of BOTH snapshots (trades + themes) — needs deploy key
- #185 | 2026-06-19 | pending | corrupt-stop exclusion-count display fix

## Apollo Themes (portfolio-app2)

- #193 | 2026-06-19 | in_progress | RS theme rank-evolution tab (snapshot freshness rides #194)
- #315 | 2026-07-15 | pending | RS-theme dashboard R-items (memory rs-theme-dash-backlog): R1 mobile/public-URL (Tailscale) · R2 bump chart · R3 canonicalization · R4 forward returns

## Apollo v1.1 — fast-follow program (spec: docs/roadmap/apollo-v1.1-v2.0.md PART I)

_W1 selection-replay + kill/scale = #268 (done) + #275; W2 entry-mechanics = #276; W4 chart-vision = #267 (Launch project). Below = the waves not yet broken into tasks._
- #306 | 2026-07-01 | pending | v1.1-W3 exit & management: winner-harvest tune (partial size · trail-by-character · capture_pct KPI) + #91 time-stop refinement — trade-state, #151 harness discipline
- #307 | 2026-07-08 | pending | v1.1-W5 experience-seed ritual: weekly operator-labeling cadence + precedent-retrieval shadow (with #219, #254, #255)
- #219 | 2026-07-08 | pending | weekly verified-miss review → RITUAL (systematic missed-winner labels feed W5)
- #254 | 2026-07-08 | pending | ground-truth label corpus (the axis-3 "accumulated experience" substrate)

## Apollo v2.0 — tier-one trader (horizons H1 Q3'26 · H2 Q4'26 · H3 2027 · spec: apollo-v1.1-v2.0.md PART II)

- #308 | 2026-08-01 | pending | P1 Experienced Judge (H1→H2): precedent corpus at scale + self-review→rubric-distillation loop + ensemble/uncertainty (#301 seed) + auto-growing probe library
- #309 | 2026-08-01 | pending | P2 Full Sight (H1→H2): multimodal (#267 daily→intraday→peer/SPY) + intraday narrative radar + tape features (#299) + negative-catalyst (#238)
- #310 | 2026-10-01 | pending | P3 The Manager (H2): management judge mature (#300 shadow→load-bearing) + structure-stops via PIVOTS (docs/methodology/pivots-and-stock-character.md) + conviction sizing
- #311 | 2026-08-01 | pending | P4 Multi-Setup Book (H1→H2): per-setup judges + tightness→expansion graduation + 9M→flag pipeline + parabolic-short counter-regime book + regime-adaptive selection
- #312 | 2026-10-01 | pending | P5 Capital & Autonomy Ladder (H2→H3): unified_allocator live + formal shadow→paper→live ladder w/ auto-DEMOTION on breach + scaling/slippage telemetry
- #313 | 2026-08-01 | pending | P6 Institution-grade ops (H1→H2): #256 split (done) + replay-everything CI (#302) + cost governance (per-role LLM spend vs P&L)
- #314 | 2026-07-15 | pending | Trading-ideas detector book (P4 detail): TI1 parabolic-short · TI2 wick-fill (#283) · TI3 fishhook U&R · TI4 base+catalyst convergence · TI5 post-EP shape classifier · TI6 RMV (#54) — graduation gates in data_gated_reviews.yaml; detail in trading-ideas-backlog memory

## Spec / detail docs (PLAN.md is the INDEX — every program above; detail + evidence live here, referenced)

_Launch DoD: docs/roadmap/launch-2026-06-22.md · v1.1/v2.0 map: docs/roadmap/apollo-v1.1-v2.0.md · ADRs: docs/decisions/*.md · evidence-gated reviews (weekly auto-surface): data_gated_reviews.yaml · setup SSoTs: docs/setups/*.md · methodology: docs/methodology/*.md · idea detail: trading-ideas-backlog memory. If a program isn't a task line above, it isn't planned — add it._

## Miscellaneous (no home project)

- #121 | 2026-06-23 | in_progress | shared Telegram formatting layer (consolidate ≥3 escapers, re-home off scheduler.py)
- #195 | 2026-06-23 | in_progress | SECURITY — rotate portfolio-app2 app_password (operator action)
- #246 | 2026-06-23 | pending | theme_engine isinstance(anthropic.APIError) TypeError in local test env
- #248 | 2026-06-19 | pending | regime engine: post-pullback hysteresis + spy_vs_200ma NULL fix + stale docstring
- #318 | 2026-06-18 | in_progress | morning-brief economic-calendar times shown in UTC not ET — prompt hardened in _get_economic_calendar (force "8:30 AM ET", ban UTC); deploys with next market-agent push, VERIFY at tomorrow's 9AM brief (Perplexity-honored?)
