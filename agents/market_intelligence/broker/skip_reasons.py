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
# #570 (2026-08-22): the two D-1 universe floors in ep_detector.py's snapshot loop — the ONLY
# exclusions in the whole EP pipeline that previously left no row anywhere (no skip_reason, no
# scan_log line, invisible to the #489 miss watchdog). Values ($5 close / 50k shares) are entry
# discipline = THE LINE, unchanged by this card; this only makes the rejection visible.
FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW = "filter:universe_prev_close_too_low"
FILTER_UNIVERSE_PREV_DAY_ILLIQUID  = "filter:universe_prev_day_illiquid"
# #605 (2026-08-29): a name whose gap sits BELOW the acting admission floor but at/above the
# fixed EP_CAPTURE_GAP_FLOOR is now RECORDED (scan_log row, counterfactual telemetry only —
# never graded, scored, alerted, or entered; the admission floor itself is untouched). Ends the
# floor-censorship class: June+July 2026 logged ZERO rows in the 9-10% band because MIN_GAP_PCT
# was 10.0 then, so the 08-19 floor change could never be evaluated on its own history. The
# `filter:universe_` prefix is deliberate — briefing._format_ep_section excludes that prefix
# from "gap candidates scanned" and the near-miss lines, so this class can't inflate the
# operator-facing counts (same routing as the two D-1 floors above).
FILTER_UNIVERSE_BELOW_GAP_FLOOR    = "filter:universe_below_gap_floor"

# ── setup: order-prep rejections (prepare_orb_order / prepare_prior_day_low_orb_order) ─
SETUP_STOP_TOO_WIDE        = "setup:stop_too_wide"
SETUP_ZERO_RANGE           = "setup:zero_range"
SETUP_SIZE_TOO_SMALL       = "setup:size_too_small"
SETUP_PRICE_EXCEEDS_CAP    = "setup:price_exceeds_cap"
SETUP_ACCOUNT_FETCH_FAILED = "setup:account_fetch_failed"
SETUP_FADED_FROM_ORB       = "setup:faded_from_orb"
SETUP_CHASE_CAP_EXCEEDED   = "setup:chase_cap_exceeded"  # #500 bounded-chase gate
# #490 2026-08-01: the alert row is written on the scan tick that scored it (often hours before the
# open); nothing re-checked the gap at submission, so a name that retreated below MIN_GAP_PCT before
# 09:31 was still entered. Operator ruled that a BUG, not a new filter — the floor (10% at the time,
# 9% since 2026-08-19) is an existing signed criterion and the entry path simply was not enforcing it.
SETUP_GAP_BELOW_FLOOR      = "setup:gap_below_floor"

# ── block: safeguards (circuit breakers, position limits, strategy gate) ──
BLOCK_MAX_POSITIONS              = "block:max_positions"
BLOCK_DAILY_LOSS                 = "block:daily_loss"
BLOCK_CIRCUIT_BREAKER            = "block:circuit_breaker"
BLOCK_DRAWDOWN_BREAKER           = "block:drawdown_breaker"
BLOCK_STRATEGY_DISABLED          = "block:strategy_disabled"
BLOCK_STRATEGY_IN_SHADOW         = "block:strategy_in_shadow"
BLOCK_STRATEGY_DEPRECATED        = "block:strategy_deprecated"  # #424: terminal phase, never enters
BLOCK_PAPER_STRATEGY_ON_LIVE     = "block:paper_strategy_on_live"
BLOCK_TICKER_OPEN_POSITION       = "block:ticker_open_position"
# PDT lockout guards RETIRED 2026-06-04 (#181) — FINRA Rule 4210 eliminated the
# PDT designation; the guard no longer fires. Constants + labels kept (not removed)
# so humanize() still renders pre-2026-06-04 historical rows that carry them.
BLOCK_PDT_LOCKOUT_IMMINENT       = "block:pdt_lockout_imminent"
BLOCK_PDT_LOCKOUT_ACTIVE         = "block:pdt_lockout_active"
BLOCK_STRATEGY_POSITION_CAP      = "block:strategy_position_cap"
BLOCK_REENTRY_GAP_THROUGH        = "block:reentry_gap_through"
BLOCK_TRADING_PAUSED             = "block:trading_paused"  # operator /pause (#345); pass-through for preflight

# ── infra: infrastructure / connectivity failures ───────────────────────────
INFRA_NO_BAR              = "infra:no_bar"
INFRA_SUBSCRIBE_TIMEOUT   = "infra:subscribe_timeout"
INFRA_SUBSCRIBE_FAILED    = "infra:subscribe_failed"
INFRA_ORDER_SUBMIT_FAILED = "infra:order_submit_failed"
INFRA_HALT_STATE_UNREADABLE = "infra:halt_state_unreadable"  # #345 fail-SAFE block when the halt flag can't be read

# ── window: timing gates ─────────────────────────────────────────────────────
WINDOW_OUT_OF_ORB   = "window:out_of_orb"
WINDOW_DUPLICATE    = "window:duplicate"
WINDOW_PROPOSAL_EXPIRED = "window:proposal_expired"  # #436 — unconfirmed staged proposal outlived its ORB day

# ── broker: the BROKER killed an accepted entry order (#500 reason capture) ──
# Alpaca sends NO textual reason on cancel/reject/expire, so these reasons
# carry a synthesized price-vs-trigger diagnosis in the detail suffix (see
# order_manager.broker_terminal_reason). Replaces the pre-#500 bare
# `skip_reason="cancelled"` that gave the operator "entry cancelled, no reason"
# (ARWR 2026-07-22).
BROKER_ENTRY_CANCELLED = "broker:entry_cancelled"
BROKER_ENTRY_REJECTED  = "broker:entry_rejected"
BROKER_ENTRY_EXPIRED   = "broker:entry_expired"

# Convenience: valid category prefixes (for sanity-check asserts)
VALID_CATEGORIES = frozenset({"filter", "setup", "block", "infra", "window", "broker"})


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
    FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW: "Prior close below the $5 universe floor",
    FILTER_UNIVERSE_PREV_DAY_ILLIQUID:  "Prior-day volume below the 50k-share universe floor",
    FILTER_UNIVERSE_BELOW_GAP_FLOOR:    "Gap below the admission floor (recorded only)",
    SETUP_STOP_TOO_WIDE:        "Stop too wide for risk budget",
    SETUP_ZERO_RANGE:           "Zero opening range",
    SETUP_SIZE_TOO_SMALL:       "Position size too small",
    SETUP_PRICE_EXCEEDS_CAP:    "Price exceeds per-share cap",
    SETUP_ACCOUNT_FETCH_FAILED: "Couldn't fetch Alpaca account",
    SETUP_FADED_FROM_ORB:       "Price faded below ORB midpoint",
    SETUP_GAP_BELOW_FLOOR:      "Gap retreated below the entry floor before entry",
    SETUP_CHASE_CAP_EXCEEDED:   "Ran too far past ORB high to chase",
    BLOCK_MAX_POSITIONS:           "Max open positions reached",
    BLOCK_DAILY_LOSS:              "Daily loss limit hit",
    BLOCK_CIRCUIT_BREAKER:         "Consecutive-loss circuit breaker tripped",
    BLOCK_STRATEGY_DISABLED:       "Strategy disabled in registry",
    BLOCK_STRATEGY_IN_SHADOW:      "Strategy in shadow phase (no live entries)",
    BLOCK_STRATEGY_DEPRECATED:     "Strategy deprecated — retired, no new entries",
    BLOCK_PAPER_STRATEGY_ON_LIVE:  "Paper-phase strategy can't run on live account",
    BLOCK_TICKER_OPEN_POSITION:    "Already have open position in ticker",
    BLOCK_PDT_LOCKOUT_IMMINENT:    "PDT lockout imminent (3 day-trades used)",
    BLOCK_PDT_LOCKOUT_ACTIVE:      "PDT lockout active (account flagged)",
    BLOCK_STRATEGY_POSITION_CAP:   "Per-strategy position cap reached",
    BLOCK_REENTRY_GAP_THROUGH:     "Re-entry skipped — att1 stop gap-through",
    BLOCK_TRADING_PAUSED:          "Real-money trading paused (operator /pause)",
    INFRA_NO_BAR:               "No opening bar from data feed",
    INFRA_SUBSCRIBE_TIMEOUT:    "Bar subscribe timed out",
    INFRA_SUBSCRIBE_FAILED:     "Bar subscribe failed",
    INFRA_ORDER_SUBMIT_FAILED:  "Order submission to Alpaca failed",
    INFRA_HALT_STATE_UNREADABLE: "Halt-state unreadable — blocked (failing safe)",
    WINDOW_OUT_OF_ORB:          "Arrived after ORB window closed",
    WINDOW_DUPLICATE:           "Duplicate — trade already exists",
    WINDOW_PROPOSAL_EXPIRED:    "Staged proposal expired — ORB day passed unconfirmed",
    BROKER_ENTRY_CANCELLED:     "Broker cancelled the entry order",
    BROKER_ENTRY_REJECTED:      "Broker rejected the entry order",
    BROKER_ENTRY_EXPIRED:       "Entry order expired unfilled",
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


# ── Cap-block reason builders (#484, 2026-07-27) ─────────────────────────────
# These strings are CONSUMED BY STRING MATCH, not just displayed: the #197 CAP+1
# alert and the ledger's `cap_blocked` mapping both key off the exact format. Each
# was hand-copied into TWO call sites — `live_tracker._check_safeguards` (the cheap
# STEP-2 early gate) and `entry_pipeline.submit_trade_entry` STEP-6 (the
# authoritative recount under the #461 per-mode cap lock) — so an edit to one copy
# alone would silently break the alert with nothing failing loudly. `count_open_
# positions` had already been deduped for exactly this reason; only the reason
# BUILDING hadn't. Formats are byte-identical to the copies they replace.
#
# Both flagged copies were global-cap only; the per-STRATEGY pair below was found
# duplicated the same way while fixing it — same class, same risk.

def cap_block_reason(open_count: int, cap: int, account_mode: str) -> str:
    """Global per-mode position-cap block reason. Matched by the #197 CAP+1 alert."""
    return f"{BLOCK_MAX_POSITIONS}: {open_count}/{cap} (mode={account_mode})"


def strategy_cap_block_reason(
    signal_type: str, strat_open: int, strat_cap: int, account_mode: str,
) -> str:
    """Per-strategy (#65) position-cap block reason, enforced within the global envelope."""
    return (
        f"{BLOCK_STRATEGY_POSITION_CAP}: {signal_type} "
        f"{strat_open}/{strat_cap} (mode={account_mode})"
    )
