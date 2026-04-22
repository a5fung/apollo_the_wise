"""
Bounded-vocabulary skip-reason prefixes for EP entry lifecycle events.

Every `mi_live_trades.skip_reason` written by any code path MUST start with one
of these constants. Free-form detail may follow after a ": " separator — e.g.
`SETUP_STOP_TOO_WIDE + ": ORB $1.24 vs 1.5x ATR $0.83"`. The prefix is the
aggregation key; the suffix preserves human detail.

Monthly / quarterly performance review splits on the prefix:
    split_part(skip_reason, ':', 1)  → category ('filter', 'setup', 'block', ...)
    split_part(skip_reason, ':', 2)  → reason_code ('stop_too_wide', ...)
"""
from __future__ import annotations

# ── filter: pre-trade quality filters (ADV, ATR, market cap) ────────────────
FILTER_ADV_NO_DATA    = "filter:adv_no_data"
FILTER_ADV_TOO_LOW    = "filter:adv_too_low"
FILTER_ATR_TOO_HIGH   = "filter:atr_too_high"
FILTER_MCAP_TOO_SMALL = "filter:mcap_too_small"

# ── setup: order-prep rejections (prepare_orb_order / prepare_9m_day2_orb_order) ─
SETUP_STOP_TOO_WIDE        = "setup:stop_too_wide"
SETUP_ZERO_RANGE           = "setup:zero_range"
SETUP_SIZE_TOO_SMALL       = "setup:size_too_small"
SETUP_PRICE_EXCEEDS_CAP    = "setup:price_exceeds_cap"
SETUP_ACCOUNT_FETCH_FAILED = "setup:account_fetch_failed"

# ── block: safeguards (circuit breakers, position limits) ───────────────────
BLOCK_MAX_POSITIONS   = "block:max_positions"
BLOCK_DAILY_LOSS      = "block:daily_loss"
BLOCK_CIRCUIT_BREAKER = "block:circuit_breaker"

# ── infra: infrastructure / connectivity failures ───────────────────────────
INFRA_NO_BAR              = "infra:no_bar"
INFRA_SUBSCRIBE_TIMEOUT   = "infra:subscribe_timeout"
INFRA_SUBSCRIBE_FAILED    = "infra:subscribe_failed"
INFRA_ORDER_SUBMIT_FAILED = "infra:order_submit_failed"

# ── window: timing gates ─────────────────────────────────────────────────────
WINDOW_OUT_OF_ORB   = "window:out_of_orb"
WINDOW_DUPLICATE    = "window:duplicate"

# Convenience: valid category prefixes (for sanity-check asserts)
VALID_CATEGORIES = frozenset({"filter", "setup", "block", "infra", "window"})
