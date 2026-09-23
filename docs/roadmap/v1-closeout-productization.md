# Apollo v1.0 — Close-out & Productization Plan (#418)

**2026-07-05 (Fable planning block 1, operator directive 7/4).** This document defines what
"Apollo v1.0 — complete product, shipped to customer, DONE" means, dispositions every open
task against that line, sweeps for off-board productization gaps, and lays the dated glide
path to declaring it. **Contract: pure-execution depth** — after operator sign-off, executing
this plan requires zero design judgment; every remaining fork is on the Decision Sheet (§7)
for the operator, nothing is buried.

Companion: `apollo-v1.1-v2.0.md` PART II becomes the Phase-2 program via #419 (next block);
this plan's PHASE-2 dispositions are its intake.

---

## 1. What v1.0 IS (the product definition)

A single-operator, real-money momentum/EP trading chief-of-staff that:

1. **Detects** — EP/MAGNA53 (enriched grades live since 7/4), 9M (alerts + Day-2 paper),
   themes, continuation flags (shadow), with the holistic judge load-bearing on EP grades.
2. **Trades ONE strategy live** — MAGNA53 ORB entries with real money (since 6/30), under
   mechanical safeguards (max positions, daily loss limit, tiered drawdown breaker per mode,
   `/pause`, kill switch) and the never-naked-stop invariant.
3. **Manages to exit** — bracket stops, SMA trail, partials (3:45 scan), time stops
   (operator-confirmed), with broker-authoritative reconciliation fences.
4. **Self-audits and self-monitors** — L1/L2/L3 audits, weekly review, order-status
   reconcile + coverage-drift detection, service watchdog, nightly backup + restore-proof,
   12-gate deploys.
5. **Is operable and recoverable from docs alone** — DR runbook (drilled 6/20, fenced
   nightly), ops runbooks, SSoT setup docs.
6. **Runs within a visible cost envelope** — LLM + infra spend tracked, with a monthly
   ceiling alert.

**v1.0 is the system that exists today, hardened to "done" — not more capability.**
Everything that grows capability (new setups, strategy promotions, judge evolution,
dashboards, explorations) is Phase 2 by definition.

## 2. The finish line (exit criteria — the operator signs THIS)

v1.0 is DECLARED when ALL of the following hold. Each criterion is measurable; none is
prose-judgment.

| # | Criterion | Measure | State 7/5 |
|---|---|---|---|
| FL-1 | **Live-loop soak** | **10 consecutive trading days** of the full loop (premarket scan → grades → entry when signaled → management → EOD audit) with ZERO trade-state manual repairs and ZERO L1 invariant breaches. Interventions that are *designed* operator actions (`/timestop` confirms, label sittings, sign-offs) do NOT reset the clock; anything touching `mi_live_trades`/orders outside designed surfaces DOES. | 3/10 (6/30, 7/1, 7/2 clean) |
| FL-2 | **Safety fences mechanical + exercised** | Every safeguard has a LIVE exercise on record: max-positions block, daily-loss halt (or synthetic drill), drawdown-breaker state transition (per mode), `/pause`, never-naked remediation (Path C), [5l/7] demotion fence, boot preflight. Enumerated in §6.2 with evidence pointers. | ~80% (see §6.2) |
| FL-3 | **Ops autonomy, 7-night streak** | Backup (with roles.sql) + 03:30 restore-check + watchdog heartbeat + gdrive health: 7 consecutive green nights, zero manual nudges. | starts 7/5 night |
| FL-4 | **Mirror completeness** | DB↔broker coverage-drift detector live (done 7/5) + **broker-order ingest (#184b)** closed → a41e7c6a-class gaps structurally impossible; 5 consecutive quiet days (no D1/D2-HIGH). | detector live; ingest open |
| FL-5 | **Docs-only recovery** | DR runbook current (incl. roles fix — done 7/5) + the 6 CLAUDE.md sections get full-parity SSoT docs (#417 backfill) + every setup doc reconciled with code at close date. | partial |
| FL-6 | **Cost envelope** | Monthly LLM+infra spend visible in one surface + a ceiling alert (threshold operator-set). | **S-C BUILT 7/12** — weekly-review MTD-spend appendix (rides next deploy → verify-live 7/19); /status board + budget alert already armed. FL-6 build-complete pending verify |
| FL-7 | **Board zero (v1.0 scope)** | Every BLOCKING task closed; every PHASE-2 task re-homed under the #419 program with honest dates; zero overdue. | this plan |
| FL-8 | **Learning loop 4-Sunday streak** | Weekly review + data-gated registry surfacing + label capture ran 4 consecutive Sundays without repair. | 3/4 (6/21, 6/28, 7/5 ran clean — verified in mi_system_reviews; 7/12 completes) |

**Declaration mechanics**: when FL-1..FL-8 are green, the operator walks this doc top to
bottom, checks each measure against live evidence (pointers in §6), and signs §8. That
signature IS v1.0 shipped. Target window: **~7/20–7/31** (soak-bound; see §5).

## 3. Disposition rubric (how every open task was classified)

- **BLOCKING** — protects live money (trade-state correctness, safeguards, mirror
  completeness), or required by an FL criterion, or an in-flight verify of already-live
  behavior. These burn to zero before declaration.
- **PHASE-2** — grows capability; absence does not make the current live loop unsafe or
  unoperable. Re-homed under the #419 program (still tasks, never hidden — they close by
  being DELIVERED across Q3/Q4, not by list hygiene).
- **CLOSE** — duplicate / obsolete / already-satisfied, with a pointer to where the work
  lives. Real dedup only, per the burndown rule.
- **DECISION** — an operator fork; lives on the Decision Sheet (§7) with a recommendation,
  and its task carries the decision date.

Bias applied: **default-to-Phase-2** — v1.0 is the shipped product hardened, not a bigger
product. Where a task mixes both, the v1.0-relevant increment is named BLOCKING and the
rest moves to Phase 2 (split noted inline, same task ID kept on the bigger half).

## 4. The board disposition (all 104 open tasks, 7/5 board)

Source: `_418_board_extract.md` (104/104 verified). Every task appears exactly once below.

### 4a. BLOCKING — 22 existing + 4 new = the v1.0 burn-down set (post-decisions)

Grouped by execution shape. Each line = task → the v1.0 increment + its DoD (execution depth;
no design judgment left).

**Verify-class (already built/live — observe + close; ~zero build):**
| Task | v1.0 increment + DoD |
|---|---|
| #347 | Mon 7/6 premarket: enriched grades fire, no `live_enriched_grade_failed` floods, `/why` shows corpus grading → close |
| #256 | Mon 7/6: 03:30 `backup_restore_check_ok` row + 12:00 UTC `watchdog_heartbeat` row → close |
| #405 | Tue 7/7 premarket: no re-grade of filtered tickers in the scan logs → close |
| #317 | Deploy rode 7/5 batch; next direct-source HIGH alert shows no contradictory "Catalyst:" line → close |
| #150 | Event-driven: next share-reservation-lag event retries cleanly (audit row) → close; re-date honestly if no event |
| #413 | Event-driven: first real-money fill walks fill→stop-leg→DB→exit-ladder cleanly (checklist in task) → close |
| #276 | Operator ACK of the no-stop-change verdict at the §8 walk → close |
| #303 | The cross-codebase review closeout folds INTO the §8 walk → close at sign-off |

**Small-build class (Sonnet cards + Fable review; ≤half-day each):**
| Task | v1.0 increment + DoD |
|---|---|
| **S-A** (new) | compose `logging: {driver: json-file, options: {max-size: "50m", max-file: "5"}}` on all services; verify via `docker inspect` post-deploy |
| **S-B** (new) | watchdog disk stanza: alert when `/` ≥85% (df probe, same transition/dedup mechanics); selftest with a fake threshold |
| #378 (+S-C) | /cost board (LLM + subs total) + budget/anomaly Telegram alarm + a monthly spend line in the weekly review; thresholds operator-set at the walk |
| **S-D** (new) | `docs/ops/secrets_rotation.md` — per-credential rotation steps + boot requirements + verification; docs-only |
| **S-E** (new, from D-4) | Execute the standing deprecations in the strategy registry: `9m_day2` + `flag_continuation` → deprecated (no new paper entries, out of the promotion checker); `wick_fill` → hold (shadow stays, digest stops proposing). Strategy-lifecycle change under operator authority recorded 7/5; documented entry ships with the change |
| #404 | Delete dead `confirm_signal_at` code + 4 tests + `ENTRY_CONFIRM_VOL_MIN`; suite green |
| #412 | Residuals: fix `mi_system_reviews.metrics` double-encoding (write-path json.dumps → jsonb object; read-path stays compatible) + the reviews-ready "ADV" truncation; suite green |
| #290 | Run `analyze_late_detection_v3.py`; confirm <20% ORB-extension precision → close the data-gated review either way |
| #195 | Rotate portfolio-app2 app_password (operator action, 5 min) |
| #280 | Staging gets its own paper Alpaca account (new key pair, staging .env only); verify prod paper untouched |
| #420 | External pinger on /health (operator creates account; I wire + test by stopping nginx briefly off-hours) + kuma per D-5 |

**Careful-path class (trade-state adjacent — Fable-led sessions):**
| Task | v1.0 increment + DoD |
|---|---|
| #184(b) | Broker-order ingest: untracked apollo-COID broker orders → mirror rows (the a41e7c6a closer). Design: extend coverage_drift's D2-HIGH detection with an INGEST step gated behind a dry-run flag; #151 discipline (exercise vs real paper Alpaca) + operator sign-off before enable. DoD: FL-4's 5 quiet days |
| #287 | Trade-state data cleanup (FPS stuck flag + 8 double-encoded exits): committed backfill script (never docker-exec ad-hoc), operator-gated, verified row-by-row |
| #261 | Finish scripts/ reorg (94 tools split, 45 scratch resolved) **with F4 landed in the same change** (scheduler imports `scripts/_judge_replay_common` — reorg without F4 silently kills the #343 shadow) |
| #417 | Doc backfill for the 6 sections (targets in 7/5 trim_accounting) → re-trim CLAUDE.md <36k; recent-changes test green |
| #183 (from D-7) | Wire-boundary enum normalization in `_order_to_dict` (status/side/type → plain lowercase values) + audit EVERY downstream comparison against both forms + tests pinning the contract. Known live casualty: the polling Day-1 re-entry fallback (`status != "filled"` never matches). Careful-path: money-adjacent, per-site verification |

**Planning spine:** #418 (this doc — closes at §8 sign-off) · #419 (Phase-2 roadmap — next block, absorbs §4b).

### 4b. PHASE-2 — 78 tasks, re-homed under the #419 program (they stay tasks; they close by delivery)

- **Judge & catalyst program (26)**: #367 #368 #322 #328 #329 #330 #331 #332 #333 #335 #337
  #338 #269 #210 #211 #212 #230 #233 #235 #215 #258 #239 #265 #207 #197 #274 — the ~7/18
  #335 checkpoint is Phase-2 Milestone 1 (axes accrue → ONE batched regrade → flip decision).
- **Launch-origin judge inputs (3)**: #299 #255 #301 — all blocked on the #335 checkpoint;
  they move with the program, not the launch project.
- **Family A program (15)**: #402 #327 #353 #354 #356 #396 #397 #357 #297 #283 #385 #386
  #394 #395 #358 — HTF/coil shadow→paper→live ladder, all evidence-gated (their Monday
  verify chores ride the pickup, not this plan).
- **Stocks in Play (6)**: #359 #168 #167 #170 #146 #178.
- **v2.0 pillars (7)**: #308 #309 #310 #311 #312 #313 #314 — the Phase-2 spine itself.
- **v1.1 fast-follow (2)**: #306 (exit-tune STEP-2/3) #307.
- **Ops hygiene, non-FL (13)**: #407 #384 #379 #363 #348 #343 #414 #416 #415 #340 #281 #176
  #216 — includes #414 (stop-gap mechanics: an improvement to the shipped design, not a
  v1.0 safety hole; Phase-2 W-item with its N≥10 backtest gate).
- **Dashboards + Themes (3)**: #194 #185 #315.
- **Misc (2)**: #121 (Telegram HTML migration — kills the fence-bug class product-wide;
  early Phase-2) #334 (revive-latch; gated on the revive feature going live).
- **External-gate (1)**: #316 (PDT relax — activates when Alpaca's Rule-4210 rollout confirms;
  CHANGE_PROCESS).

*(Arithmetic post-decisions: 22 BLOCKING + 79 PHASE-2 (incl. #381) + 3 CLOSE = 104 ✓; +4 new BLOCKING items S-A/S-B/S-D/S-E filed, S-C folded into #378)*

### 4c. CLOSE — 2 (real dedup, operator can veto at the walk)

- **#272** — launch-umbrella closeout: the 6/22 GO/NO-GO executed; the residual "closeout"
  IS this plan's §8. Close pointing here.
- **#192** — deferred-findings discipline: satisfied by the standing rule
  (`feedback_defer_findings_to_task_tracker`) + the `check_plan` gates that now enforce it
  mechanically. Close pointing at the memory + Gate 2.
- **#370** — completeness-registry increment 5: D-9 decided don't-build; 4/5 layers live and
  accepted as covering the known surface. Close; revisit trigger = a new silent-failure class.

### 4d. DECISION — all resolved 7/5 (answers recorded in §7): #183 → BLOCKING (§4a) · #381 → PHASE-2 (zero-baseline = dated Phase-2 milestone) · #370 → CLOSE (§4c)

- **D-7 (#183)**: scope-unrecoverable ("ORB classifier IEX/window mislabel", no elaboration
  exists). Recall what it meant, or close as ghost. *Rec: close unless you recall it.*
- **D-8 (#381)**: does v1.0 require swallow-baseline **zero** (your 6/25 "completely gone"
  directive), or is money-paths-clean (#382 done) + mechanical ratchet the v1.0 bar, with
  zero as a dated Phase-2 milestone? *Rec: the latter — 81 non-money sites ≈ weeks of careful
  work that shouldn't gate declaration; the ratchet guarantees monotone progress.*
- **D-9 (#370)**: build completeness-registry increment 5 or accept 4/5 as done? *Rec: don't
  build — partly redundant with `_backup_health_check_job` + the new restore-check/watchdog.*

## 5. Glide path — DAY-BY-DAY, trigger-armed (tightened 7/5 evening, operator directive: no idle plan)

All build work compresses into ONE week. Every item's PLAN.md ETA = its calendar day below, so
`check_plan` (pre-commit Gate 2 + the OPEN ritual) FAILS on any slip — the dates ARE the triggers.

| Day | Work (ETAs enforced by check_plan) | FL clocks |
|---|---|---|
| **Mon 7/6** | Verify sweep: #347 · #256→close · #412 (metrics encode + ADV truncation) · careful: #261+F4 · build #426 (FL countdown → evening briefing) | FL-1 d4 · FL-3 n2 |
| **Tue 7/7** | Verify: #405 #317 · cards: #421 (log caps) #422 (disk check) #424 (deprecations) · careful: #287 | countdown line LIVE tonight |
| **Wed 7/8** | Cards: #378+S-C (cost board) #195 (rotate) #280 (staging account) · careful: #417 (backfill+retrim) | |
| **Thu 7/9** | Cards: #290 #420 (pinger) #423 (rotation runbook) · careful: #183 (enum boundary) · #303 mini-walk | |
| **Fri 7/10** | Careful: **#184(b) broker-order ingest** (the week's big rock) + slip absorber | FL-4 quiet-clock starts |
| **7/11–7/19** | NO planned build — clocks only: FL-3 completes 7/12 · FL-8 7/12 · FL-1 ≈7/14 · FL-4 ≈7/16 · event-driven #150/#413 as they fire · **7/18 = #335 checkpoint (Phase-2 M1, separate sitting)** | |
| **#425 walk** | **ETA 7/21 (HARD, check_plan-gated) — pull EARLIER the moment #426 shows all-green (earliest ~7/17)** | declaration |

### 5b. The anti-idle triggers (mechanical, not memory)

1. **Per-day ETAs + Gate 2**: any blocking item past its date fails every commit and tops
   `check_plan --today` at every session OPEN. Max-1-rebump caps silent slippage.
2. **#426 daily countdown** (built Mon): one line in the EVENING BRIEFING —
   `v1.0: FL-1 5/10 · FL-3 3/7 · blocking 12 open · decl ~7/18` — RED with the reason on any
   clock reset. The operator sees drift the same day it happens, not at the walk.
3. **#425 the walk is itself a dated task**: 7/21 hard; passing it un-walked breaks the gate.
4. **Event-driven items alert, not wait**: #150/#413 close off their audit-row events;
   coverage-drift (FL-4) Telegrams on any D1/D2-HIGH.
5. **Hard outer bound stands**: not declared by **7/31** → the plan itself is re-reviewed
   (something structural was mispriced).

## 6. Productization sweep (off-board gaps)

### 6.1 Gap audit (checked live on prod, 7/5)

| Checked | State | Verdict |
|---|---|---|
| OS security patching | `unattended-upgrades` enabled | ✅ no action |
| Clock sync (market timing) | NTP active, synchronized | ✅ no action |
| LLM cost ceiling | `ANTHROPIC_MONTHLY_BUDGET` set in prod `.env`; `core/spend.py` fires budget alerts | ✅ armed |
| gdrive OAuth recovery | runbook exists (`docs/ops/gdrive_backup_recovery.md`) | ✅ no action |
| DR / backups / restore-proof / watchdog | built + fenced this sprint | ✅ (FL-3 streak pending) |
| **Docker log caps** | **NO `log-opts` anywhere — container json logs grow unbounded** (disk 25% now; slow death over months) | 🔴 **S-A** |
| **Disk-space monitoring** | watchdog checks services, NOT disk — disk-full kills everything silently | 🔴 **S-B** |
| **Spend visibility** | weekly-review MTD-spend appendix BUILT 7/12 (system_review._spend_envelope_section, 5 tests) — the last FL-6 surface | ✅ **S-C built** |
| **Secrets rotation** | no runbook for rotating Alpaca/Telegram/Anthropic keys under the dual-account boot requirements | 🟠 **S-D** |

**New v1.0 items from the sweep** (to file as #-tasks at plan sign-off):
- **S-A** — compose `logging: options: max-size/max-file` on all services (fold into the next
  deploy; verify with `docker inspect`). BLOCKING (FL-3 class).
- **S-B** — watchdog disk check: alert when `/` ≥ 85% (one stanza in `service_watchdog.sh`,
  same DOWN/dedup mechanics). BLOCKING, tiny.
- **S-C** — weekly-review spend line: month-to-date Anthropic spend vs budget + fixed-subs
  note (deterministic appendix). BLOCKING-lite (completes FL-6). ✅ **BUILT 7/12**
  (`system_review._spend_envelope_section`; wired into the deterministic appendix chain; 5 tests).
  FINDING at build: MTD $11.75 vs the placeholder $10 budget = 118% — the walk sets the real ceiling.
- **S-D** — `docs/ops/secrets_rotation.md`: per-credential rotation steps (which env vars,
  boot requirements, verification), docs-only. BLOCKING-lite (FL-5).

### 6.2 FL-2 safeguard-exercise evidence (state 7/5)

| Fence | Live exercise on record | Evidence pointer | Gap |
|---|---|---|---|
| Max concurrent positions | ✅ fired repeatedly | `block:max_positions` skip rows | — |
| `/pause` runtime halt | ✅ exercised at ship (#345) | audit rows | — |
| Never-naked remediation (Path C + in-process re-protect) | ✅ exercised (#151 era, stop_update_failed paths) | `partial_exit_aborted` / remediation audit rows | — |
| Boot preflight (strategy-driven auth walk) | ✅ every deploy | deploy logs | — |
| [5l/7] demotion fence | ✅ 6 live gate runs 7/5 | deploy logs | — |
| Coverage-drift detection | ✅ built 7/5; first live cycles Mon 7/6 | `coverage_drift_*` audit rows | quiet-verify |
| Daily loss limit (LIVE mode) | ⚠ never fired live | — | **Decision D-3**: synthetic drill vs accept paper evidence |
| Drawdown breaker transition (LIVE mode) | ⚠ armed 6/03, no live transition | `mi_safeguard_state` | **Decision D-3** (same) |
| Kill switch `LIVE_TRADING_ENABLED=false` | ✅ exercised in dev/boot paths | boot logs | — |

## 7. Operator Decision Sheet

**ALL DECIDED 2026-07-05 (operator: 'recs accepted for all', with D-2/D-4 clarifications below).**

| # | Decision | Options | Rec + why |
|---|---|---|---|
| D-1 | FL-1 soak length | **10 trading days** / 5 / 15 | 10 ≈ two weeks of full-loop evidence; 5 is thin for a "shipped" claim, 15 delays declaration without adding a new failure class |
| D-2 | v1.0 trading surface | **MAGNA53-only live; 9M Day 2 stays paper into Phase 2** / promote 9M inside v1.0 | 9M promotion is evidence-gated anyway (needs 30 closed, has 8, median R −0.49) — putting it inside v1.0 makes the finish line hostage to a cohort that doesn't exist yet |
| D-3 | Live-mode daily-loss + drawdown-breaker exercise (FL-2 gaps) | **Accept paper-mode evidence + code-path identity** (mode-parameterized, same path, preflight-walked) / synthetic live drill | A live drill spends real money to test a fence whose code is identical across modes; paper evidence + the strategy-driven preflight walk covers it. THE LINE argues against manufacturing live losses |
| D-4 | wick_fill + flag_continuation shadow→paper (checker says ✓ ready) | **Phase 2** (briefs prepared this week, decision at Phase-2 kickoff) / promote now inside v1.0 | Promotions grow capability — the definition of Phase 2; nothing about v1.0 safety depends on them |
| D-5 | kuma container disposition (with #420 external pinger) | **Decommission** (never configured, 3mo idle, watchdog replaced it) / keep for future dashboards | Dead services are surface area; dashboards are a Phase-2 want |
| D-6 | Declaration window | **Soak-bound (~7/20–7/31)** / hard date | Soak-bound keeps FL-1 honest; a hard date invites clock-fudging |

**Answers (operator, 7/5):** D-1 ten days · D-2 yes — and sharper: **9M Day 2 is DEPRECATED as a
tradeable setup** (9M = a stock CONDITION feeding other setups, per the Pradeep universe doctrine)
· D-3 accept paper evidence · D-4 wick_fill = backlog idea, NO promo; **flag_continuation DEPRECATED**
(replaced by HTF + Anticipation) — both deprecations to be EXECUTED in the strategy registry (S-E;
they had been decided but never applied, which is why the weekly promotion checker kept proposing
them) · D-5 decommission kuma · D-6 soak-bound · D-7 #183 recovered → re-dispositioned BLOCKING
(see §4a; prod probe confirmed str(OrderStatus.NEW)=='OrderStatus.NEW' on Python 3.12 — the polling
Day-1 re-entry fallback is silently dead) · D-8 money-clean + ratchet is the v1.0 bar; baseline-zero
(#381) = a dated Phase-2 milestone · D-9 don't build increment 5 → #370 CLOSES (4/5 layers accepted).

## 8. Sign-off

- [x] Finish line (§2) — definitions accepted (or edited) and signed: **operator, 2026-07-07 — accepted as-is, no edits**
- [x] Dispositions (§4) walked; DECISION items answered: **operator, 2026-07-07 — all 9 decisions confirmed, none revised**
- [x] v1.0 DECLARED (all FL green): **operator, 2026-07-24**  date: **2026-07-24**  ← walked + signed via #425

**Walk record (2026-07-07):** operator signed the finish line + dispositions. Live clocks at sign-off:
FL-1 5/10 · FL-3 0/7 (⚠ streak not advancing — under investigation) · FL-4 1/5 · FL-8 4/4 ✓ · 24 blocking
open · projected declaration ~7/14. #418 closes here; #425 carries the all-green declaration.

**🏁 DECLARATION record (2026-07-24) — v1.0 SHIPPED.** Operator declared Apollo v1.0 live at the #425 walk.
Final FL evidence, all verified this walk:
- **FL-1** 10/10 ✓ soak clean (`STOP_ACK_TIMEOUT_GATE` confirmed ON) · **FL-3** 7/7 ✓ · **FL-4** 5/5 ✓ (ingest
  `live_r1` since 7/17) · **FL-8** 4/4 ✓ — all four auto-metered green (`scripts/v1_closeout_status.py`).
- **FL-2** fences: operator ruled ACCEPT paper-mode proof (fences mode-identical + preflight-walked; THE LINE
  argues against manufacturing live losses). The daily-loss coverage gap surfaced by the FL-5 reconcile was
  FIXED before signing — realized losses now attributed by CLOSE day (ET), not `alert_date`; backtested
  (old query mis-attributed 12/28 loss-days) + operator-signed CHANGE_PROCESS (`safeguards.md`) + deployed
  live to apollo-execution + code-verified in the running container.
- **FL-5** docs reconciled: 10 setup docs synced to code (the reconcile confirmed every safeguard number +
  detection threshold already matched code — doc-lag only, the code was correct).
- **FL-6** cost envelope done (#378) · **FL-7** board-zero (#184/#261 re-homed to #419 Phase-2 by operator).

**#418 + #425 CLOSE here.** The blocking/launch lens retires; the board becomes the #419 Phase-2 program.
The operating cadence is now the product — scan → judge → enter → manage → EOD audit → weekly review →
data-gated sittings — and the operator's role narrows to sign-offs + sittings (the D5 posture).
