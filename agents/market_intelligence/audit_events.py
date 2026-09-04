"""Audit event name constants (#117, 2026-05-28).

Goal: eliminate stringly-typed event names at call sites. Typos in event
names cause silent failures — the row gets written with the wrong type
and the predicate SQL / drill-down query / weekly review aggregator
never matches it.

**Scope of this initial pass**: the constants module DEFINES names for
all events with 2+ call sites + new events from the 2026-05-28 session.
Call-site MIGRATION is partial — only the events introduced today and
a few referenced in today's PRs (CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE,
STUCK_PENDING_NEW_DETECTED, PARTIAL_NOW_OPERATOR_CONFIRMED,
SYNC_NOW_OPERATOR_CONFIRMED) have been migrated. Pre-existing 2+-caller
events like NAKED_POSITION_DETECTED, PARTIAL_EXIT_ABORTED, STOP_UPDATE_FAILED,
MNA_FILTER_FIRED still have string-literal call sites — those get
adopted opportunistically when touching the relevant files.

**Future migrations**: when touching a file that emits an audit event
already in this module, switch the call site to the constant. When
adding a NEW event that will have 2+ callers, add the constant here
first. The unit test `tests/test_audit_event_constants.py` pins
uniqueness + naming pattern but deliberately does NOT enforce that
every call site uses the constant — that would block opportunistic
adoption.

**Naming convention**: SCREAMING_SNAKE_CASE Python identifier, value
is lowercase-snake-case matching the existing audit_log convention.

Author note: this is intentionally NOT an Enum class. Audit event names
are written into a `text` column in mi_audit_log and queried via SQL
predicates. Bare string constants are simpler to use in SQL string
concatenation and don't require .value accessor noise at call sites.
"""

# ── Catalyst / EP detection ─────────────────────────────────────────────────
CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE = "catalyst_earnings_revenue_weak_downgrade"
CATALYST_DOWNGRADE_CARVEOUT_APPLIED = "catalyst_downgrade_carveout_applied"  # #143/2026-05-28
ANTHROPIC_RATE_LIMITED = "anthropic_rate_limited"
VALIDATION_RATE_LIMITED = "validation_rate_limited"

# ── LLM credit / quota exhaustion (#273) ────────────────────────────────────
# Distinct from the *_rate_limited events above: a rate-limit self-heals on
# retry; credit exhaustion is TERMINAL until the operator refills. One row per
# provider per ~6h is the dedup token for the Telegram alert (see llm_health.py).
ANTHROPIC_CREDITS_EXHAUSTED = "anthropic_credits_exhausted"
PERPLEXITY_CREDITS_EXHAUSTED = "perplexity_credits_exhausted"

# ── M&A filter ──────────────────────────────────────────────────────────────
MNA_FILTER_FIRED = "mna_filter_fired"
MNA_ACQUIRER_TITLE_SKIPPED = "mna_acquirer_title_skipped"  # #284 acquirer-side title not fired

# ── Anticipation coil-finder M&A / buyout-pin guards (#387/#410, 2026-06-30 NUVL FP) ────────
ANTICIPATION_MNA_EXCLUDED = "anticipation_mna_excluded"  # #387 — ma_filter.is_likely_ma hit
ANTICIPATION_COIL_BUYOUT_PIN_REJECTED = "anticipation_coil_buyout_pin_rejected"  # #410 — shape guard
# ── #327 readiness-job robustness (blocker fix, operator-signed 2026-07-14 — 7/13 >2h hang) ──
CONSOLIDATION_READINESS_SCAN_TIMEOUT = "consolidation_readiness_scan_timeout"  # scan budget hit; failed open, settlement still ran
ANTICIPATION_MNA_CHECK_CAPPED = "anticipation_mna_check_capped"  # per-run M&A-check cap hit; remaining candidates passed UNchecked (fail-open)

# ── Theme ecosystems (ADR 0032 Phase 1) ─────────────────────────────────────
THEME_ECOSYSTEM_ASSIGNED = "theme_ecosystem_assigned"  # method=haiku|keyword|unassigned in summary

# ── Sugar Baby / convergence ────────────────────────────────────────────────
SUGAR_BABY_CONVERGENCE_ALERT = "sugar_baby_convergence_alert"
SUGAR_BABY_CONVERGENCE_CHECK_FAILED = "sugar_baby_convergence_check_failed"

# ── Strategy lifecycle ──────────────────────────────────────────────────────
STRATEGY_PHASE_CHANGE = "strategy_phase_change"
STRATEGY_DISABLED_SKIP = "strategy_disabled_skip"

# ── ORB / entry flow ────────────────────────────────────────────────────────
ORB_CANCELLATION_CLASSIFICATION = "orb_cancellation_classification"
# #475 (2026-07-15, AEHR LULD): broker-side entry-order death (exchange reject,
# unexpected cancel) reaching the WS handler. Feeds the
# entry_order_rejections_systematic data-gated review — observe before fixing.
ENTRY_ORDER_REJECTED = "entry_order_rejected"

# ── Regime-keyed risk sizing (#456, operator-ruled 2026-07-26) ──────────────
# Fires when a real-money sizing site (MAGNA53 ORB / 9M Day2) reads a missing,
# stale (regime_date older than the last completed trading day), or
# unrecognized regime label — sizes at the 0.25x fail-safe floor per operator
# ruling 5 ("it should fail loud so we can fix"). Audit-log-as-state dedup
# (mirrors INTRADAY_DRAWDOWN_CROSSING): one row per ET day per account_mode is
# both the durable record AND the Telegram dedup marker — only gated behind
# REGIME_SIZING_ENABLED (see constants.py); byte-identical no-op when the flag
# is off (today's VIX-scaled + qqq_ema_bullish-halve formula never emits this).
SIZING_REGIME_FALLBACK = "sizing_regime_fallback"

# ── Notional (20%-of-equity) cap truncation (#571, 2026-08-23) ──────────────
# `prepare_orb_order`'s `max_position = equity * MAX_POSITION_PCT` step (the
# LIVE MAGNA53 sizing path) silently shrank shares when a tight stop produced
# a share count worth more than 20% of equity — the trade still fired, just
# smaller, and nothing recorded it (only the shares==0 case a few lines below
# logged anything). Measured over the 22 closed live trades as of 2026-08-23
# (docs/analysis/position_sizing_571_2026-08-23.md): bound 11 of 22, cutting
# intended risk from ~$48 to as little as $15. OPERATOR RULING 2026-08-23: the
# cap VALUE stays ("this will be solved with a large account eventually",
# docs/setups/safeguards.md) — this event is telemetry only, the #570
# universe-floor precedent applied to sizing instead of selection. Fires from
# the LIVE call path only (`emit_cap_telemetry=True`, the default); the #482
# shadow lane (shadow_orb_tracker.py) calls with `emit_cap_telemetry=False`
# since it places no real order and would otherwise pollute this signal with
# non-money candidates.
SIZING_NOTIONAL_CAP_TRUNCATED = "sizing_notional_cap_truncated"

# ── Trade-state / broker hygiene ────────────────────────────────────────────
NAKED_POSITION_DETECTED = "naked_position_detected"
NAKED_POSITION_REMEDIATION_FAILED = "naked_position_remediation_failed"
PARTIAL_EXIT_ABORTED = "partial_exit_aborted"
# #607 (2026-09-04): `stop_update_failed` used to fire at BOTH the transient
# attempt-1 place_stop_order failure (order_manager.py's #433 retry-in-3s
# class — usually wins, protection never lapses) AND the terminal
# both-attempts-failed case (position genuinely naked). One raw type meant
# every consumer had to re-derive the distinction from the `attempt` field
# in `detail`, and one reader (agent.py's /trade timeline) never did — it
# rendered a healthy self-heal as "update FAILED" (AMLX 08-24..28: 5 of 5
# "failures" were retries that won). Split at the raise site so the type
# itself carries the distinction:
#   STOP_UPDATE_RETRY_TRIGGERED — attempt 1 failed, a 3s retry is in flight.
#     Deliberately does NOT contain "_failed"/"error" so it falls outside
#     system_review.py's silent-failure globs (%_failed%, %error%) by
#     construction — no reader needs a filter to know this is telemetry,
#     not an open defect. Paired with `stop_update_retry_succeeded` (already
#     existed) when the retry wins, or `STOP_UPDATE_FAILED` below when it
#     doesn't.
#   STOP_UPDATE_FAILED — now fires ONLY when the retry also failed (the
#     genuinely-naked, terminal case). Pre-2026-09-04 rows still hold the
#     old overloaded meaning; readers bridge those via `detail.attempt`
#     (dated bridge, see agent.py/system_review.py — not a new parallel
#     path).
STOP_UPDATE_RETRY_TRIGGERED = "stop_update_retry_triggered"
STOP_UPDATE_FAILED = "stop_update_failed"
STOP_UPDATE_ABORTED = "stop_update_aborted"
STOP_ACK_REMEDIATION_FAILED = "stop_ack_remediation_failed"
ORDER_STATUS_RECONCILE_FAILED = "order_status_reconcile_failed"
STUCK_PENDING_NEW_DETECTED = "stuck_pending_new_detected"  # #142/2026-05-28
DRAWDOWN_CHECK_UNAVAILABLE = "drawdown_check_unavailable"

# ── Intraday drawdown crossing (#455 R4 stage-1, 2026-07-16) ────────────────
# ALERT-ONLY intraday check piggybacked on the 15-min order-status-reconcile
# cycle: live-account drawdown vs the breaker's 30d snapshot peak crossed a
# WATCH/REDUCE trip threshold DEEPER than the persisted breaker state. The
# CROSSING row doubles as the per-(tier, ET-day) Telegram dedup state (the
# cost_board.run_daily_spend_alarm audit-log-as-state pattern). *_CHECK_FAILED
# fires once after repeated consecutive piggyback failures — the check itself
# must never break the reconcile cycle.
INTRADAY_DRAWDOWN_CROSSING = "intraday_drawdown_crossing"
INTRADAY_DRAWDOWN_CHECK_FAILED = "intraday_drawdown_check_failed"

# ── Coverage-drift detector (#184 ADR 0008 increment 2, 2026-07-05) ─────────
# Read-only DB↔broker mirror-completeness check. Written per detection
# regardless of severity (telemetry contract); *_ALERTED is the dedup marker
# written only when a HIGH-severity drift actually Telegrams (D1 / D2-HIGH);
# *_CHECK_DEGRADED fires when the broker read itself can't be trusted (#137
# class — never report drift off a failed/empty read).
COVERAGE_DRIFT_DETECTED = "coverage_drift_detected"
COVERAGE_DRIFT_ALERTED = "coverage_drift_alerted"
COVERAGE_DRIFT_CHECK_DEGRADED = "coverage_drift_check_degraded"
# Job-wrapper guard (scheduler._order_status_reconcile_job): the coverage-drift
# call itself blew up (distinct from CHECK_DEGRADED, which is the module's own
# "broker/DB read failed" handling) — the outer per-mode try/except in the job.
COVERAGE_DRIFT_CHECK_FAILED = "coverage_drift_check_failed"

# ── Operator-confirm commands (#138/2026-05-28) ─────────────────────────────
PARTIAL_NOW_OPERATOR_CONFIRMED = "partial_now_operator_confirmed"
SYNC_NOW_OPERATOR_CONFIRMED = "sync_now_operator_confirmed"

# ── Allocator / cross-strategy ──────────────────────────────────────────────
UNIFIED_ALLOCATION_DECIDED = "unified_allocation_decided"

# ── Lifecycle / telegram ────────────────────────────────────────────────────
TRADE_LIFECYCLE_TELEGRAM_ATTEMPTED = "trade_lifecycle_telegram_attempted"
TELEGRAM_SEND_FAILED = "telegram_send_failed"

# ── Crypto / data ingest ────────────────────────────────────────────────────
CRYPTO_INGEST_ERROR = "crypto_ingest_error"

# ── Judge ensemble-divergence SHADOW (#301, 2026-07-26) ─────────────────────
# Zero-authority 2nd-model (JUDGE_DIVERGENCE_MODEL=Sonnet) check on HIGH-tier
# primary-judge (JUDGE_MODEL=Opus) verdicts — see judge_divergence.py. NEVER
# alters a grade; logs agree/disagree to mi_judge_divergence. CHECK_FAILED
# fires on a 2nd-model call/write failure (fail-open, counted so the module
# can't go silently dark — the #173 lesson); DETECTED fires when the two
# models disagree on tier (informational, no action taken).
JUDGE_DIVERGENCE_DETECTED = "judge_divergence_detected"
JUDGE_DIVERGENCE_CHECK_FAILED = "judge_divergence_check_failed"

# ── Evening briefing send observability (#495, 2026-07-21/25) ──────────────
# send_telegram_message returns False on failure without raising (never
# raises — see its own docstring), so a silently-failed 18:00 ET evening
# brief was invisible AND undiagnosable after a container restart (the
# 2026-07-20 false alarm: "did it send?" was unanswerable from the DB).
# Emitted by send_evening_briefing() itself, not the scheduler job wrapper —
# the wrapper only catches raised exceptions, and send_telegram_message's
# own TELEGRAM_SEND_FAILED audit doesn't cover its early-return paths
# (missing TELEGRAM_BOT_TOKEN / empty TELEGRAM_ALLOWED_USER_IDS), so the
# sender is the only site that observes every False-return cause.
EVENING_BRIEF_SENT = "evening_brief_sent"
EVENING_BRIEF_SEND_FAILED = "evening_brief_send_failed"

# ── #603 DoD (3): endpoint-SHAPE anomaly canary ─────────────────────────────
# Fires on a response that did NOT raise a classifiable provider-health
# exception (so llm_health.alert_api_failure's classifier never sees it) but
# came back unusable anyway: 200 OK with no extractable answer, a 404 on a
# FIXED-URL endpoint (not a per-item miss), or a body that failed to decode as
# JSON. This is what a future vendor endpoint sunset looks like from the
# outside — see llm_health.alert_endpoint_shape_anomaly for the full design.
# Name contains "error" so `_check_nightly_silent_errors`'s `%error%` sweep
# and `show errors` pick it up automatically, with no extra wiring.
PERPLEXITY_ENDPOINT_ERROR = "perplexity_endpoint_error"
