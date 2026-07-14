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

# ── Sugar Baby / convergence ────────────────────────────────────────────────
SUGAR_BABY_CONVERGENCE_ALERT = "sugar_baby_convergence_alert"
SUGAR_BABY_CONVERGENCE_CHECK_FAILED = "sugar_baby_convergence_check_failed"

# ── Strategy lifecycle ──────────────────────────────────────────────────────
STRATEGY_PHASE_CHANGE = "strategy_phase_change"
STRATEGY_DISABLED_SKIP = "strategy_disabled_skip"

# ── ORB / entry flow ────────────────────────────────────────────────────────
ORB_CANCELLATION_CLASSIFICATION = "orb_cancellation_classification"

# ── Trade-state / broker hygiene ────────────────────────────────────────────
NAKED_POSITION_DETECTED = "naked_position_detected"
NAKED_POSITION_REMEDIATION_FAILED = "naked_position_remediation_failed"
PARTIAL_EXIT_ABORTED = "partial_exit_aborted"
STOP_UPDATE_FAILED = "stop_update_failed"
STOP_UPDATE_ABORTED = "stop_update_aborted"
STOP_ACK_REMEDIATION_FAILED = "stop_ack_remediation_failed"
ORDER_STATUS_RECONCILE_FAILED = "order_status_reconcile_failed"
STUCK_PENDING_NEW_DETECTED = "stuck_pending_new_detected"  # #142/2026-05-28
DRAWDOWN_CHECK_UNAVAILABLE = "drawdown_check_unavailable"

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
