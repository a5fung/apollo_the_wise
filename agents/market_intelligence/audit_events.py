"""Audit event name constants (#117, 2026-05-28).

Goal: eliminate stringly-typed event names at call sites. Typos in event
names cause silent failures — the row gets written with the wrong type
and the predicate SQL / drill-down query / weekly review aggregator
never matches it.

**Scope of this initial pass**: events with 2+ call sites across the
codebase + all new events introduced in today's session. Single-caller
events (175 of them) stay as literals — the rule-of-three discipline
isn't crossed, and a constant per single-caller event would be more
overhead than value.

**Future migrations**: when touching a file that emits an audit event
already in this module, switch the call site to the constant. When
adding a NEW event that will have 2+ callers, add the constant here
first. The unit test `tests/test_audit_event_constants.py` pins
uniqueness + naming pattern.

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

# ── M&A filter ──────────────────────────────────────────────────────────────
MNA_FILTER_FIRED = "mna_filter_fired"

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
