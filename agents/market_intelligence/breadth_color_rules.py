"""Breadth color rule SSoT — shared by evening briefing, the /regime Telegram
command (the breadth matrix merged into /regime 2026-06-14), and the L2
cluster-deterioration audit detector.

Four metric classes per `data_gated_reviews.yaml::breadth_cluster_view_ideation`:

  CLASS A — Paired up/down counts (matrix metrics). Up cell green when high,
            down cell red when high. Both can light up independently.
  CLASS B — Unpaired thrust (e.g. up 20%+/5d alone). High = amber exhaustion
            warning (Pradeep 2026-05-24 SPY annotation).
  CLASS C — Contrarian extremes (T2108). Low = green oversold setup; high
            = amber overbought caution.
  CLASS D — Persistence/cluster (consecutive or clustered red days).
            Sequence is the signal; per-bar color not meaningful alone.
"""
from __future__ import annotations

import json
from typing import Any, Optional

# --- thresholds (single source of truth) -----------------------------------

T2108_OVERSOLD = 20.0   # Class C: below → green setup signal
T2108_OVERBOUGHT = 85.0  # Class C: above → amber caution signal

# Class B (#271): unpaired ±20%/5d thrust as % of universe ($5-floor numerator).
# p90 convention thresholds from the 269-day calibration (docs/analysis/breadth_classb_271.md;
# tunable like T2108's 20/85, NOT a backtested trade gate). Validated on Pradeep's 5/24 anchor.
CLASS_B_UP_EXHAUSTION = 2.7   # up≥20%/5d ≥ 2.7% of universe → amber (exhaustion)
CLASS_B_DOWN_WASHOUT = 1.8    # down≥20%/5d ≥ 1.8% of universe → green (washout = oversold setup)

CLUSTER_WINDOW = 5            # rolling window in trading days
CLUSTER_RED_THRESHOLD = 3     # ≥N red days in window to fire
CLUSTER_RECENCY_DAYS = 2      # at least one red must be in last N days
                              # (prevents stale signals: R-R-R-G-G doesn't count)


# --- color emoji constants -------------------------------------------------

BULL = "🟢"
BEAR = "🔴"
CAUTION = "🟠"
NEUTRAL = ""


# --- JSONB coercion -------------------------------------------------------

def coerce_breadth_monitor(value: Any) -> dict:
    """Normalize a `mi_market_regime.breadth_monitor` value to a dict.

    asyncpg sometimes returns JSONB as a string (especially when no codec
    registered). Tolerates None, parse errors, and non-dict shapes; always
    returns a dict so call sites can use `.get()` safely.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# --- Class A: paired up/down ----------------------------------------------

def paired_color(up: Optional[int], down: Optional[int]) -> str:
    """Paired metric color. Green if up>down, red if down>up, neutral if tied
    or missing. Tied is genuinely neutral — call sites must render the count
    even when emoji is empty (don't drop the row)."""
    if up is None or down is None:
        return NEUTRAL
    if up > down:
        return BULL
    if down > up:
        return BEAR
    return NEUTRAL


# --- Class C: T2108 contrarian extremes -----------------------------------

def t2108_color(value: Optional[float]) -> str:
    """T2108 color. Below OVERSOLD = green (bounce setup); above OVERBOUGHT
    = amber caution; mid-range = neutral."""
    if value is None:
        return NEUTRAL
    if value < T2108_OVERSOLD:
        return BULL
    if value > T2108_OVERBOUGHT:
        return CAUTION
    return NEUTRAL


# --- Class B: unpaired ±20%/5d thrust (#271) ------------------------------

def class_b_color(up_20_5d_pct: Optional[float], down_20_5d_pct: Optional[float]) -> str:
    """CLASS B unpaired-thrust color (clone of t2108_color — pure, stateless, convention
    thresholds). Up-thrust extreme → amber (Pradeep exhaustion); down-thrust extreme (washout)
    → green (oversold setup = the 'post-washout rally-watch', the reading itself, no transition
    state). Two-directional by construction; the up side wins if both somehow extreme."""
    if up_20_5d_pct is not None and up_20_5d_pct >= CLASS_B_UP_EXHAUSTION:
        return CAUTION
    if down_20_5d_pct is not None and down_20_5d_pct >= CLASS_B_DOWN_WASHOUT:
        return BULL
    return NEUTRAL


# --- Class D: cluster detection -------------------------------------------

def is_red_day(monitor: dict) -> bool:
    """A trading day counts as red if EITHER the daily 4% up/down comparison
    is negative (up < down) OR the 5-day ratio drops below 1.0.

    Either signal alone is enough — both surface deteriorating breadth.
    """
    up4 = monitor.get("today_up4")
    down4 = monitor.get("today_down4")
    ratio_5d = monitor.get("ratio_5d")

    if up4 is not None and down4 is not None and down4 > up4:
        return True
    if ratio_5d is not None and ratio_5d < 1.0:
        return True
    return False


def cluster_fires(monitors: list[dict]) -> bool:
    """Detect a 'cluster of red days' deterioration signal.

    Per Pradeep 2026-05-24 framing: "last few days in the last five days, a
    sign of transitioning into stalling action" — NOT consecutive, just
    clustered.

    Args:
      monitors: list of breadth_monitor dicts in REVERSE-CHRONOLOGICAL order
                (index 0 = most recent day). Must have ≥CLUSTER_WINDOW entries.

    Returns True when ≥CLUSTER_RED_THRESHOLD reds in the last CLUSTER_WINDOW
    days AND at least one of those reds is within the last CLUSTER_RECENCY_DAYS
    (recency filter — prevents firing on stale R-R-R-G-G patterns).
    """
    if len(monitors) < CLUSTER_WINDOW:
        return False
    window = monitors[:CLUSTER_WINDOW]
    reds = [is_red_day(m) for m in window]
    if sum(reds) < CLUSTER_RED_THRESHOLD:
        return False
    if not any(reds[:CLUSTER_RECENCY_DAYS]):
        return False
    return True


def red_count_in_window(monitors: list[dict]) -> int:
    """Count of red days in the last CLUSTER_WINDOW trading days. Used by
    audit detector to report severity ('3 of 5' vs '5 of 5')."""
    if len(monitors) < CLUSTER_WINDOW:
        return 0
    return sum(1 for m in monitors[:CLUSTER_WINDOW] if is_red_day(m))


def secondary_first_red(monitors: list[dict]) -> bool:
    """Today's secondary breadth is red AND yesterday's was not — the
    'first red in secondary' signal-of-signals (Pradeep cluster matrix
    annotation).

    Secondary red = either 1M ±50% or 3M ±25% paired comparison is negative.
    """
    if len(monitors) < 2:
        return False

    def is_secondary_red(m: dict) -> bool:
        up50 = m.get("up_50_1m")
        down50 = m.get("down_50_1m")
        up25q = m.get("up_25_3m")
        down25q = m.get("down_25_3m")
        if up50 is not None and down50 is not None and down50 > up50:
            return True
        if up25q is not None and down25q is not None and down25q > up25q:
            return True
        return False

    return is_secondary_red(monitors[0]) and not is_secondary_red(monitors[1])
