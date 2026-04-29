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
FILTER_ADV_NO_DATA           = "filter:adv_no_data"
FILTER_ADV_TOO_LOW           = "filter:adv_too_low"
FILTER_ATR_TOO_HIGH          = "filter:atr_too_high"
FILTER_MCAP_TOO_SMALL        = "filter:mcap_too_small"
FILTER_PM_RVOL_TOO_LOW       = "filter:pm_rvol_too_low"
FILTER_SESSION_RVOL_TOO_LOW  = "filter:session_rvol_too_low"

# ── setup: order-prep rejections (prepare_orb_order / prepare_9m_day2_orb_order) ─
SETUP_STOP_TOO_WIDE        = "setup:stop_too_wide"
SETUP_ZERO_RANGE           = "setup:zero_range"
SETUP_SIZE_TOO_SMALL       = "setup:size_too_small"
SETUP_PRICE_EXCEEDS_CAP    = "setup:price_exceeds_cap"
SETUP_ACCOUNT_FETCH_FAILED = "setup:account_fetch_failed"
SETUP_FADED_FROM_ORB       = "setup:faded_from_orb"

# ── block: safeguards (circuit breakers, position limits, strategy gate) ──
BLOCK_MAX_POSITIONS              = "block:max_positions"
BLOCK_DAILY_LOSS                 = "block:daily_loss"
BLOCK_CIRCUIT_BREAKER            = "block:circuit_breaker"
BLOCK_STRATEGY_DISABLED          = "block:strategy_disabled"
BLOCK_STRATEGY_IN_SHADOW         = "block:strategy_in_shadow"
BLOCK_PAPER_STRATEGY_ON_LIVE     = "block:paper_strategy_on_live"

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


# ── Human-readable labels for Telegram ──────────────────────────────────────
# DB stores raw "category:code: detail"; Telegram shows the phrase + detail.
# Keep phrases short (≤ 5 words) so they read cleanly in a bullet list.
_HUMAN_LABELS: dict[str, str] = {
    FILTER_ADV_NO_DATA:          "No average volume data",
    FILTER_ADV_TOO_LOW:          "Average volume too low",
    FILTER_ATR_TOO_HIGH:         "Volatility too high",
    FILTER_MCAP_TOO_SMALL:       "Market cap too small",
    FILTER_PM_RVOL_TOO_LOW:      "Pre-market pace below normal",
    FILTER_SESSION_RVOL_TOO_LOW: "Session pace below normal",
    SETUP_STOP_TOO_WIDE:        "Stop too wide for risk budget",
    SETUP_ZERO_RANGE:           "Zero opening range",
    SETUP_SIZE_TOO_SMALL:       "Position size too small",
    SETUP_PRICE_EXCEEDS_CAP:    "Price exceeds per-share cap",
    SETUP_ACCOUNT_FETCH_FAILED: "Couldn't fetch Alpaca account",
    SETUP_FADED_FROM_ORB:       "Price faded below ORB midpoint",
    BLOCK_MAX_POSITIONS:           "Max open positions reached",
    BLOCK_DAILY_LOSS:              "Daily loss limit hit",
    BLOCK_CIRCUIT_BREAKER:         "5-loss circuit breaker tripped",
    BLOCK_STRATEGY_DISABLED:       "Strategy disabled in registry",
    BLOCK_STRATEGY_IN_SHADOW:      "Strategy in shadow phase (no live entries)",
    BLOCK_PAPER_STRATEGY_ON_LIVE:  "Paper-phase strategy can't run on live account",
    INFRA_NO_BAR:               "No opening bar from data feed",
    INFRA_SUBSCRIBE_TIMEOUT:    "Bar subscribe timed out",
    INFRA_SUBSCRIBE_FAILED:     "Bar subscribe failed",
    INFRA_ORDER_SUBMIT_FAILED:  "Order submission to Alpaca failed",
    WINDOW_OUT_OF_ORB:          "Arrived after ORB window closed",
    WINDOW_DUPLICATE:           "Duplicate — trade already exists",
}


def humanize(reason: str | None) -> str:
    """Translate a stored `category:code: detail` skip_reason into a Telegram-friendly phrase.

    Examples:
        "infra:subscribe_timeout: 5s SDK lock stuck"
          → "Bar subscribe timed out (5s SDK lock stuck)"
        "setup:stop_too_wide: ORB $1.24 vs 1.5x ATR $0.83"
          → "Stop too wide for risk budget (ORB $1.24 vs 1.5x ATR $0.83)"
        "window:out_of_orb: detected 10:14 ET"
          → "Arrived after ORB window closed (detected 10:14 ET)"

    Unknown prefixes and legacy free-form strings fall back to the original
    text so nothing is ever hidden.
    """
    if not reason:
        return "no attempt"
    parts = reason.split(":", 2)
    if len(parts) < 2 or parts[0] not in VALID_CATEGORIES:
        return reason.strip()
    prefix = f"{parts[0]}:{parts[1]}"
    label = _HUMAN_LABELS.get(prefix)
    if not label:
        return reason.strip()
    detail = parts[2].strip() if len(parts) == 3 else ""
    if detail:
        return f"{label} ({detail})"
    return label
