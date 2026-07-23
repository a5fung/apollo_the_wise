# Silent-Failure Taxonomy + Systematic Audit — 2026-07-23

**Review**: `silent_failure_taxonomy_audit` (data_gated_reviews.yaml, added 2026-05-19).
**Scope**: trading/execution + detection paths — `agents/market_intelligence/` (esp. `broker/`,
`ep_detector.py`, `ninem_detector.py`, `flag_detector.py`, `scheduler.py`, `collector.py`,
`trade_stream.py`) plus the surfacing layer itself (`failure_policy.py`, `core/job_audit.py`,
`core/notifications.py`, the audit sweeps).
**Method**: (1) strict run of the AST gate (`scripts/preflight_no_silent_failures.py --strict`)
to enumerate the tracked debt; (2) hand-classification of every baseline swallow in trading files;
(3) sweep of the gate's four documented blind-spot classes (log-only handlers, plausible defaults,
except-less nulls, generic framing) across the money + detection paths; (4) reconciliation against
the prior audits (#382 scoping 7/05, money-path adversarial audit 7/12, v1-readiness RED-3/3b).
**Status**: READ-ONLY. No code, config, or DB changed. Every fix below is a card, not a patch.

**Headline**: the money path's *broad-except* hygiene is genuinely good (0 broad+silent swallows
in `broker/` after #382; CRMD-class framing remediated; EP-scan crash handling is the model).
The dangerous residue lives almost entirely in the classes the AST gate *cannot* see:
**(a)** safety-net jobs whose own crash has no Telegram/audit surface (the naked-position
watchdogs), **(b)** "200-OK-but-empty" data that turns a provider outage into a quiet trading
day, and **(c)** log-only failure handlers on the WS-outage backstop chain.
**13 REAL-GAP findings (~19 code sites); every proposed fix is observability-only (no-money).**

---

## 1. Taxonomy

Two orthogonal axes. **Shape classes (T1–T8)** describe *how a failure hides* — each has a grep/
review signature, so the audit is repeatable. **Treatment classes** (refined from the review's
proposed table) describe *how loud the surface must be* — the fix vocabulary.

### 1a. Shape classes — how failures hide

| # | Class | Definition | Signature (how to find) | Canonical incident | Coverage today |
|---|---|---|---|---|---|
| T1 | **SWALLOWED-BROAD** | Broad `except` whose body neither raises nor calls a loud sink | AST: `preflight_no_silent_failures.py` | #380 FMP-403, #173 theme-shadow-0-rows | **GATED** (ratchet, 81 baseline) |
| T2 | **WRONG-SINK** | Handler is loud *to logs* (`logger.debug/warning/error`) but writes no audit row and no Telegram on a path the operator must know about | `except` + `logger.*` with no `log_audit_event`/`send_telegram_message` in body or caller — manual classification (the gate deliberately counts `logger.*` as loud) | FMP 402 paywalled 2026-05-19 (WARNING → silent yfinance fallback) | NOT gated (the "ping-vs-log" manual pass) |
| T3 | **PLAUSIBLE-DEFAULT / FAIL-OPEN MASK** | A caught failure returns a value indistinguishable from a legit reading — `{}` snapshot, `[]` orders, `0` volume, `'OK'` breaker state — and downstream reads "all clear" | `return {}` / `return []` / `or 0` / `return _STATE_OK` inside an except or missing-data branch | 2026-05-27 IBM sync (0 positions ≈ "liquidated"), #371 200MA-null | Partially: `get_open_orders`/`get_all_positions` now alert via `maybe_alert_api_failure` (#370 input-side); `sync_positions` has the mass-close abort |
| T4 | **EXCEPT-LESS NULL** (#370) | No exception anywhere: a 200-OK-but-empty payload or an empty query result flows through as "quiet day" | `if not <fetched>: return []/0` with no audit/counter at the consumer | The empty-snapshot class (finding F2) | NOT gated (AST can't see it); partial: `job_liveness_sweep` K=3-day table checks for 4 curated jobs |
| T5 | **GENERIC-FRAMING** | The failure IS surfaced but the message hides the consequence, so the operator can't triage | Manual review of alert text on escalation paths | 2026-05-14 CRMD — 3 stream-handler errors fired but didn't say "POSITION IS NAKED" → naked 1h34m | REMEDIATED at the known sites (trade_stream 421-436 "POSITION MAY BE NAKED", `EP SCAN DOWN — TRADING IMPACTED`); one live instance found (F2: "market may not be open yet" mislabels a Polygon outage) |
| T6 | **WATCHDOG-DEATH** (meta-monitor) | The safety net's *own* failure is quiet — the layer that exists to catch silent failures dies silently | Scheduled jobs with no internal `notify_job_failure` (their raise lands in `audit_wrap`'s unwatched `status='failed'` row); `logger.error`-only handlers inside `*watchdog*`/`reconcile*`/`check_fills` functions | This audit (F1, F3, F4, F8, F13) | NOT gated; `_EXPECTED_JOBS` no-show check covers only 4 curated jobs |
| T7 | **SWEEP-CONVENTION MISS** | An audit row IS written but no automatic sweep matches its event name — surfaces weekly (system_review `%_failed%`) or never | Event names not matching `%error%` / `%rate_limited%` / `%api_failure%` / the L1 `%_error` window, without a dedicated watcher | RED-3b: `drawdown_check_unavailable` matched NONE of the nightly patterns (fixed as a one-off carve-out 7/12) | The CLASS persists — any new audit-only `*_failed` event repeats RED-3b |
| T8 | **CONFIG/BOOT** | Env/credential/SDK failure at boot, outside the deploy.sh preflight path (container auto-restart never runs preflight) | Boot-path guards that `logger.error` + degrade | 2026-05-13 outage — `KeyError: 'ALPACA_LIVE_API_KEY'`, no Telegram | Largely remediated for deploys (`preflight_check.py` walks the live safeguards path); residual at F11 |

### 1b. Treatment classes — how loud (refined from the 2026-05-19 proposal)

| Class | Example | Treatment |
|---|---|---|
| Equivalent fallback | Alpaca News fails → Polygon same window | DEBUG log, no surface |
| Degraded fallback | FMP → yfinance (data quality changed) | Audit row + Telegram once/day (dedup key) |
| Config error | 402/401, missing env var, SDK-shape change | Audit + Telegram once/session |
| Actionable transient | timeout past N retries, rate limit > N min | Audit + Telegram immediately (deduped) |
| Pure transient | first-retry timeout, routine 429 | Audit row only |
| Trading-path failure | any exception in entry/exit/stop handling | Telegram immediately, ESCALATED framing (the consequence in the first line) — model: `EP SCAN DOWN`, `POSITION MAY BE NAKED` |
| **Data-quality silent corruption** (7th class, added per the review note) | 200-OK-but-empty snapshot; volume field missing → 0; phantom-check splits bug | Audit each occurrence + Telegram past a consecutive-occurrence threshold — an exception-based guard can never catch this class; it needs a *completeness* check on the value |
| **Meta-monitor failure** (8th class, added by this audit) | a watchdog/reconcile/sweep itself crashes | ALWAYS at least an audit row; Telegram after N consecutive (pattern already exists: `intraday_drawdown._consecutive_failures`) — a failed safety-net day is not a clean day (RED-2's lesson) |

The infra that carries these treatments already exists: `failure_policy.py`
(`@advisory_fail_open` / `@trade_state_fail_loud`), `llm_health.maybe_alert_api_failure`
(deduped provider alerts), `humanize()` + `infra:*` skip-prefix immediate-ping rule,
`notify_job_failure`, `audit_wrap`. The gaps below are places these weren't applied, not
missing machinery.

---

## 2. REAL-GAP findings (13, ranked by blast radius)

"Surface needed" names the specific fix. **All 13 fixes are no-money** (add an audit row /
Telegram / counter / wording — zero strategy, safeguard, sizing, or trade-state behavior
change). The one adjacent decision that would be money-path is flagged under F9.

### Tier 1 — money-path / trade-state safety nets

**F1 · Naked-position watchdogs can die with no Telegram and no audit row** — class T6
- Sites: `scheduler.py:1488-1587` `_stuck_fill_watchdog_job` (Gate-5 deliverable D — detects
  stuck `status='filling'` rows from a crashed WS fill handler), `scheduler.py:1590-1799`
  `_stop_ack_timeout_watchdog_job` (fires the fallback stop for naked positions), and
  `scheduler.py:1226-1356` `_time_stop_scan_job` (lower severity — operator-confirm only).
- Mechanism (verified): none of the three has an internal try/except. A raise propagates into
  `audit_wrap` (`core/job_audit.py:135-144`), which writes `mi_job_runs status='failed'` and
  **re-raises into APScheduler's logger — no Telegram, no `mi_audit_log` row**. Nothing watches
  `mi_job_runs` failures automatically: `_EXPECTED_JOBS` (audit_invariants.py:477) covers 4
  curated jobs (none of these), `_JOB_OUTPUT_CHECKS` (health_checks.py:352) covers 4 job→table
  pairs and *explicitly excludes* `status='failed'` runs on the (false for these jobs) assumption
  that failures "already alert via notify_job_failure"; `/audit job_runs`
  (system_audit.py:1634) is on-demand only.
- Blast radius: the job that exists to catch a naked position from a crashed fill handler is
  itself in the T6 class it was built to fix. A schema drift or DB error kills naked-position
  detection invisibly.
- Surface needed: make `audit_run`'s exception branch call `notify_job_failure` (it already has
  the job_id + error) or add an automatic `mi_job_runs status='failed'` sweep to the 16:15 L1
  pass. One fix covers every current and future no-handler job. Observability-only.

**F2 · "200-OK-but-empty" snapshot = a silent detection blackout** — class T4 + T3 (+T5 wording)
- Sites (6): `ninem_detector.py:178-180` (worst: `if not snaps: return []` — **no log line at
  all**; runs every 5 min all session, and `_9m_scan_job` logs only `if alerts:` — an outage
  leaves literally zero trace) · `ep_detector.py:1794-1797` (`logger.warning("No snapshot data —
  market may not be open yet")` — container-log only, and the wording mislabels a real Polygon
  outage as benign timing, a live T5 instance) · `flag_detector.py:1609-1612, 1958-1961,
  2214-2217, 2467-2470` (four intraday scans, same `if not snapshots: return 0` pattern).
- Mechanism: `collector.get_snapshot_all()` catches everything internally and returns `{}`
  (collector.py:211-226) — the *exception* path is loud (`_polygon_get` → `maybe_alert_api_failure`,
  correct pattern), but a 200-OK `{"tickers": []}` maintenance/partial-outage response raises
  nothing anywhere, so no exception-based guard can ever fire. Every consumer treats empty as
  "quiet day". The loud `EP SCAN DOWN` crash handler never triggers because nothing crashes.
- Existing partial mitigation: `job_liveness_sweep` (health_checks.py) K=3 consecutive
  empty-output *trading days* for `ep_scan`/`9m_ep_scan` only — up to 3 days late, wrong
  diagnosis ("table got 0 rows"), and the 4 flag scans aren't in the curated list at all
  (permanently invisible for them).
- Blast radius: missed trades — a mid-session Polygon outage suppresses ALL 9M + flag detection
  for its duration with no operator signal.
- Surface needed: at the scan-job level (one shared helper): when `get_snapshot_all()` returns
  empty during market hours → `snapshot_empty` audit row each tick + Telegram past N consecutive
  ticks (treatment: data-quality-corruption class). Fix the ep warning wording while there.
  Reference implementation already in-repo: `mgmt_judge.py:236-247` audits + alerts its skip
  instead of grading blind.

**F3 · The WS-outage backstop chain's own failures are container-log-only** — class T6 + T2
- Sites: `scheduler.py:1177-1179` `_check_fills_job` (`except: logger.error` only — the polling
  fill-checker that *only matters when the WS stream is already down*; a double failure is fully
  invisible) · `scheduler.py:1194-1195` `_stream_health_watchdog` (same — the mechanism that
  *restarts* a dead trade stream; its crash also makes `audit_wrap` record "success").
- Blast radius: fills/stop-fills stop being observed exactly during the outage window the
  backstops exist for; positions manageable only via the 15-min reconcile (see F4).
- Surface needed: add `notify_job_failure` + audit row to both handlers (mirror the sibling jobs
  three lines away that already do this).

**F4 · The 15-min DB↔Alpaca reconcile (#123) can lose a whole account mode silently** — class T6
- Site: `order_manager.py:2813-2826` `reconcile_all_modes` — a whole-mode failure (e.g. live-mode
  auth broken, first API call raising before the per-order loop) is `logger.error` + `errors+=1`;
  `_order_status_reconcile_job` (scheduler.py:2666-2670) only `logger.info`s the count; the job
  returns "success" to `audit_wrap`. Per-ORDER failures do get `order_status_reconcile_failed`
  audit rows (order_manager.py:2746-2752) — but those are `*_failed`-named (see F5) and a
  mode-level crash writes nothing at all.
- Blast radius: this job is the designated silent-stop catcher and the declared mitigation for
  the money-path audit's residuals (R6 NULL-stop-pointer repair, re-entry ambiguous-accept). Its
  silent per-mode death removes the safety net without a signal.
- Surface needed: audit event on any whole-mode reconcile failure + deduped Telegram after N
  consecutive failures for the same mode (copy `intraday_drawdown._consecutive_failures`,
  broker/intraday_drawdown.py:214-235).

### Tier 2 — detection quality / structural

**F5 · `*_failed` audit events match no automatic sweep (RED-3b, generalized)** — class T7
- Mechanism: the nightly surfacer (`_check_nightly_silent_errors`, scheduler.py:745-766) matches
  `%error%` / `%rate_limited%` / `%api_failure%` + ONE hand-carve-out (`drawdown_check_unavailable`,
  added 7/12 after RED-3b found exactly this shape). The L1 window invariant matches `%_error`.
  `%_failed%` is swept only by the WEEKLY review (system_review.py:1012). So any audit-only
  `*_failed` event without its own Telegram or dedicated watcher surfaces a week late:
  today that set includes `order_status_reconcile_failed` (advisor-ruled audit-only — but the
  ruling assumed the operator would see persistent failure somewhere), `unfilled_cancel_failed`
  (a live order that REFUSED to cancel — stays working past its window), and any future emitter.
- Surface needed: add a `%_failed%` bucket to `_check_nightly_silent_errors` with a small
  allowlist for events that already Telegram at emit — OR adopt a naming rule (terminal
  audit-only events must end `_error`) enforced by a unit test over `audit_events.py`. This
  closes the RED-3b *class*, not another instance.

**F6 · EP cached-ticker re-poll dies at `logger.debug` and self-disables for the day** — class T2
- Site: `ep_detector.py:2401` — the late-primary-source re-poll/upgrade block (`routine` →
  strong/game_changer when a PR lands after first grading). `_st["logged"] = True` is set
  *before* the risky call, and the block only runs `while not _st["logged"]` — one failure
  permanently disables the upgrade opportunity for that ticker for the rest of the day, recorded
  only at debug level. The near-identical fresh-ticker path (ep_detector.py:2482) got
  `logger.error` + a durable `live_enriched_grade_failed` audit event — this twin was left
  behind (oversight, not design). Live-affecting when `LIVE_ENRICHED_CORPUS` is on.
- Surface needed: mirror the 2482 treatment (logger.error + the same audit event).

**F7 · 9M volume default-0 drop has no downstream safety net** — class T3
- Site: `ninem_detector.py:253` — `snap.get("day",{}).get("v",0) or snap.get("min",{}).get("av",0)
  or 0`: a data glitch (both fields missing) reads as zero volume → both 9M gates fail →
  `continue`, no log of any kind. The EP twin (ep_detector.py:1848) is BENIGN because the
  audited PM/session-RVOL gate downstream (ep_detector.py:2098-2135) catches and records the
  anomalous read — the 9M path has no equivalent.
- Surface needed: a per-scan aggregate counter (`n_volume_null`) audited when > threshold —
  distinguishes "missing data" from "genuinely below threshold".

**F8 · Per-ticker parse-drop in EP candidate build has no counter** — class T1-adjacent (bulkhead
without telemetry)
- Site: `ep_detector.py:1879` — `except Exception: continue` per ticker (the ONLY real gap among
  the 15 grade/data baseline swallows; the bulkhead itself is correct — the crash path is loud —
  but a systemic Polygon schema change hitting a ticker subset would silently erode candidate
  coverage forever). The neighboring `_unclassified_skipped` counter shows the intended pattern.
- Surface needed: aggregate `n_parse_dropped` counter, audit row when > threshold. (Folds in
  ep_detector.py:1826 `prevDay` default-0.)

### Tier 3 — low / bounded

**F9 · `read_breaker_state` per-call fail-open is log-only** — class T3 · `drawdown_breaker.py:492-494`
- A transient DB error during `_check_safeguards` (live_tracker.py:256) reads a possibly-BLOCK
  breaker as `'OK'` with only `logger.warning`. Bounded: RED-3's deployed fix monitors the
  *systemic* path (16:12 job in `_EXPECTED_JOBS` + the `drawdown_check_unavailable` nightly
  carve-out); the residual is a transient read failure exactly at entry-check time.
- Surface needed: audit row (+ deduped Telegram) on the except path. **The fail-open DIRECTION
  itself is operator-ruled design (RED-3 ruling: "fail-open semantics stay as designed") —
  changing it to fail-closed would be a safeguard behavior change = THE LINE, operator +
  CHANGE_PROCESS, and is NOT proposed here.**

**F10 · Partial-fill-too-small close failure → DB says closed, broker holds shares** — class T2
- Sites: `trade_stream.py:684-693`, `order_manager.py:470-473` — `close_position` raising is
  `logger.error`-only and the row is marked `closed` anyway. Bounded: the 15-min coverage-drift
  detector (#184) + 16:05 `sync_positions` surface the resulting DB↔broker divergence within
  ~15 min. Surface needed: an audit row + ⚠ Telegram at the failure site (honest at emit; the
  15-min window still exists and depends on F4's net being alive).

**F11 · TradingStream SDK-shape guard degrades to log-only at boot** — class T8 · `trade_stream.py:102-110`
- An alpaca-py upgrade changing `_run_forever` silently removes the entire WS fill surface for
  the mode (`logger.error` only, "falling back to polling"). Rare (pinned SDK), high consequence,
  boot-time. Surface needed: Telegram once at boot + audit row (config-error treatment).

**F12 · `_maybe_alert_stuck_pending_new` crash is log-only** — class T6 · `order_manager.py:2689-2690`
- The stuck-PENDING_NEW alerter dying quietly inside the reconcile loop. Folds into F4's
  consecutive-failure surface (same job).

**F13 · State-change alert step failure isn't added to the nightly `failures` list** — class T2 ·
`scheduler.py:705-706`
- Regime/theme deterioration Telegrams could silently stop firing (`logger.error` only; every
  other nightly stage routes into the `failures` → `notify_job_failure` aggregation). Advisory
  tier (notification, not order path) — one-line fix: append to `failures`.

---

## 3. Benign register (verified quiet-by-design — do NOT churn these)

~44 inspected sites classified BENIGN. Compressed by pattern; full per-site reasoning preserved
in the audit working notes below each pattern's exemplar.

| Pattern | Sites (exemplars) | Why quiet is correct |
|---|---|---|
| Audit-of-audit / `log_audit_event` never raises | the 14 #382 money sites (all `# loud-ok`-annotated post-7/05), scheduler.py:936/981/994, ninem_detector.py:379, ep_detector.py:2830/2967 | `log_audit_event` self-catches (db.py); a loud call already fired adjacent |
| Fail-open **toward more alerts** | ep_detector.py:2156/2674/2687/3188 (`is_earnings_day`/`is_revenue_stage` default True), scheduler.py:1059 (dedup-lookup failure → don't suppress) | documented advisor-aligned direction — failure produces an EXTRA alert, never a missing one |
| Display/cosmetic only | fundamentals.py all 9 baseline sites, live_tracker.py:949-991 summaries, telegram_confirm.py:81 theme lookup | wrong label ≠ wrong trade; `/fundamentals` is on-demand display |
| Loud-then-fallback chains | telegram_confirm 117-128 → entry_pipeline 665-667 fallback Telegram; send_telegram_message 400→plain→`telegram_send_failed` audit; bar_stream terminal-retry Telegram | each failure escalates through a louder layer |
| Raise-through with provider alert | alpaca_client get_account/get_open_orders/get_all_positions (#370 input-side `maybe_alert_api_failure` then raise/`[]`), collector `_polygon_get`/`_fmp_get` (alert then re-raise) | the correct T3 antidote, already applied |
| Aggregation guardrails above | rs_engine empty-snapshot → nightly `ingested==0` abort+Telegram; per-stage nightly failures → `failures` list → `notify_job_failure` | covered one level up |
| Self-healing with terminal escalation | trade_stream reconnect (Telegram at max retries), ORB crash double-fallback (live_tracker 418-428), intraday_drawdown consecutive-failures audit | quiet only while genuinely self-healing |
| Deliberate operator-ruled quiet | order_status_reconcile audit-only (advisor 5/26: no retroactive stop alerts — but see F5), anticipation cadence carve-out | ruled, documented |
| Shadow/telemetry | orb_extension_shadow, giveback_shadow, gap_through_telemetry:270, theme_axis_shadow, `_persist_first_bar` (already a 7/12 minor) | no-money observation layers |

Two previously-cited incidents verified REMEDIATED (no current gap): CRMD generic framing
(trade_stream.py:421-436 escalated "POSITION MAY BE NAKED" + stuck-fill watchdog + Gate-5 A-G
all shipped) · 2026-05-13 boot KeyError (deploy preflight walks the live `_check_safeguards`
path; residual only at F11's non-deploy restart edge) · 2026-04-29 naive-datetime false-L1
(preflight gate [5h/7] bans the whole bug class). FMP-402: collector now hard-aborts on 402
(collector.py:1068-1085) and the FMP news path was stripped — the 5/19 incident class is closed.

---

## 4. Reconciliation with the preflight's 81-swallow baseline

- **Strict scan today = exactly 81 = the baseline** (no new swallows, no reductions since the
  baseline was cut). Lineage: ~174 legacy at gate creation (#381) → 95 → **81** after the #382
  money-holdout pass (7/05: all 14 money-class sites resolved — 12 proved dead code around
  never-raising `log_audit_event`, 2 got debug logs; `broker/` now carries **zero** T1 debt).
- **Baseline composition**: money 0 · grade 15 · data 15 · advisory 51. This audit
  hand-classified all 15 grade + the 15 data sites in trading-relevant files: **exactly 1 is a
  REAL GAP** (F8, ep_detector.py:1879 — and even that needs a counter, not a control-flow
  change); the rest are audit-of-audit, fail-open-toward-more-alerts, or display-only. The
  remaining 51 advisory sites (telegram.py 20, orchestrator/router, theme_engine 5, agent.py 3…)
  are outside the trading path and correctly deprioritized by the ratchet's own triage order.
- **The key reconciliation**: the gate is working as designed AND its debt number is no longer
  where the risk is. **Zero of the Tier-1 findings (F1–F4) are visible to the gate** — they are
  precisely its documented exclusions (the ping-vs-log policy split, the except-less #370 class)
  plus one it doesn't name (a re-raise into an unwatched sink, F1). Driving 81 → 0 would not
  close any Tier-1 finding. The #381 "trend must go DOWN" remains right for hygiene; the
  *taxonomy's* trend line should be the Tier-1/2 fix list above.
- Prior-audit dedup: F1–F13 exclude everything already carded by the 7/12 money-path adversarial
  audit (R1 finalizer locks, R2 re-entry kill-switch precondition, R3 sync-SDK event-loop, R4
  cross-mode dedup key, R5 stop_processing janitor, R6 stop-leg refetch, R7/R8) and the deployed
  RED-2/RED-3/RED-3b fixes (verified in code: `account_equity_snapshot` in `_EXPECTED_JOBS`,
  the `drawdown_check_unavailable` nightly carve-out at scheduler.py:752-803). R5's missing
  `stop_processing` watchdog is the state-machine flank of what F1 is to the job flank —
  the same "the janitor has no janitor" theme.

---

## 5. Prioritized fix list

All fixes are **no-money** (observability additions; no strategy/safeguard/sizing/trade-state
behavior change — THE LINE untouched). Order = blast radius. Suggested batching:

| # | Fix (surface to add) | Sites | Effort | Class |
|---|---|---|---|---|
| 1 | `audit_run` exception branch → `notify_job_failure` + audit row (covers every no-handler job, now and future) — or an automatic `mi_job_runs status='failed'` L1 sweep | core/job_audit.py:135-144 (fixes F1: stuck-fill + stop-ack watchdogs, time-stop scan) | S (one function) | T6 |
| 2 | Shared empty-snapshot guard: audit row per empty market-hours tick + Telegram past N consecutive; fix the ep "market may not be open yet" wording | 6 sites via 1 helper (ninem 178, ep 1794, flag ×4) (F2) | M | T4/T3/T5 |
| 3 | `notify_job_failure` + audit in `_check_fills_job` / `_stream_health_watchdog` handlers | scheduler.py:1177, 1194 (F3) | S | T6 |
| 4 | Whole-mode reconcile failure: audit event + consecutive-failure deduped Telegram (copy intraday_drawdown pattern); same surface covers F12 | order_manager.py:2813-2826, 2689 (F4, F12) | S | T6 |
| 5 | `%_failed%` bucket in `_check_nightly_silent_errors` (allowlist for already-loud emitters) OR event-naming rule + unit test | scheduler.py:745-766 (F5) | S | T7 |
| 6 | Mirror the fresh-path treatment (logger.error + `live_enriched_grade_failed` audit) on the cached re-poll | ep_detector.py:2401 (F6) | S | T2 |
| 7 | 9M `n_volume_null` + EP `n_parse_dropped` aggregate counters → audit when > threshold | ninem 253, ep 1879/1826 (F7, F8) | S | T3 |
| 8 | Audit (+ deduped Telegram) on `read_breaker_state` except path — **alert-only; fail-open direction unchanged (operator-ruled)** | drawdown_breaker.py:492-494 (F9) | S | T3 |
| 9 | Audit + ⚠ Telegram when partial-fill close fails before the row is marked closed | trade_stream 684-693, order_manager 470-473 (F10) | S | T2 |
| 10 | Boot Telegram + audit on the TradingStream SDK-shape guard | trade_stream.py:102-110 (F11) | S | T8 |
| 11 | Append state-alert failure to the nightly `failures` list | scheduler.py:705-706 (F13) | XS | T2 |

Phase-4 idea from the original review (a classification comment required on new `except
Exception` in critical paths, pre-commit-enforced) is superseded in practice by the existing
ratchet + `# loud-ok:` + `failure_policy.py` decorators; the residual worth codifying is the
**T7 naming rule** (fix #5's test) and the **T4 completeness-check habit** (fix #2's helper as
the reusable pattern) — both cheaper than a new hook and aimed at the classes the AST gate
can't reach.

---

*Read-only audit; produced by code reading + the gate's own strict scan only (no DB or config
touched). Working inputs: `preflight_no_silent_failures.py --strict` output (81 sites),
`382_swallow_holdouts_scoping_2026-07-05.md`, `moneypath_audit_2026-07-12.md`,
`v1_readiness_redteam_2026-07-12.md`, incident docs 2026-05-14 CRMD / 2026-05-27 IBM.*
