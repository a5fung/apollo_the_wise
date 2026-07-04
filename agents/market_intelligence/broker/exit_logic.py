"""Pure daily-exit-step decision logic — single source of truth for the
SMA10/20 trail + Day 3-5 partial profit + hard-stop ladder used by both
the backtester and the live tracker.

No DB, Alpaca, or Telegram side effects: callers wrap this with their
own persistence and broker calls. Backtest semantics are the default —
hard_stop fires deterministically when bar_low <= hard_stop. The live
tracker re-calls with state['hard_stop']=None when Alpaca confirms the
position is still held (stop didn't actually trigger), and re-calls
with skip_partial_decision=True if the partial-exit helper failed and
the trade should fall through to SMA logic with the original remaining.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass
class ExitStep:
    action: str
    """One of: 'skip_pre_alert', 'no_data', 'stopped_out', 'sma_stopped',
    'partial_only', 'updated'.  'partial_only' means partial fired and
    position remains open; 'sma_stopped' may fire alongside a partial
    in the same step (caller checks partial_fired in addition to action)."""

    closed: bool
    close_reason: str | None
    close_price: float | None
    close_shares: float | None
    close_pnl: float | None

    partial_fired: bool
    partial_shares: float
    partial_price: float | None
    partial_pnl: float | None

    effective_stop: float
    active_sma: float | None
    bar_low: float | None
    bar_close: float | None
    hold_days: int

    # Updated state fields for caller persistence
    new_remaining: float
    new_partial_taken: bool
    new_breakeven_active: bool
    new_running_closes: list[float]
    new_exits: list[dict]
    new_total_pnl: float


def ema(closes: list[float], window: int) -> float | None:
    """Standard EMA of `closes`, seeded with the SMA of the first `window` values then
    recursively updated (smoothing factor 2/(window+1)) through the remaining closes. Returns
    the EMA value AS OF THE LAST element in `closes`. None when len(closes) < window —
    mirrors the None-on-insufficient-data contract the inline SMA10/20 trail already uses
    below. Pure function, no side effects. #396 HTF Phase 4 (management SHADOW) — the 10/20
    EMA trail input; also usable anywhere an EMA (vs SMA) trail is wanted."""
    if not closes or len(closes) < window:
        return None
    multiplier = 2.0 / (window + 1)
    value = sum(closes[:window]) / window
    for c in closes[window:]:
        value = (c - value) * multiplier + value
    return value


def apply_daily_exit_step(
    state: dict[str, Any],
    daily_bar: dict[str, Any] | None,
    today: date,
    *,
    integer_partial_shares: bool = False,
    skip_partial_decision: bool = False,
    skip_hard_stop_close: bool = False,
) -> ExitStep:
    """Compute one daily exit step.

    state must contain:
      alert_date, remaining_shares, entry_price, hard_stop,
      partial_taken, breakeven_active, exits, running_closes

    daily_bar (None if no bar available) provides 'l' and 'c'.

    integer_partial_shares: True for live (Alpaca needs whole shares),
      False for backtest (fractional sim).
    skip_partial_decision: True to bypass the partial-profit branch
      entirely (used by live wrapper after partial helper fails).
    """
    remaining = float(state.get("remaining_shares") or 0)
    alert_date = state["alert_date"]
    entry_price = state.get("entry_price")
    hard_stop = state.get("hard_stop")
    partial_taken = bool(state.get("partial_taken", False))
    breakeven_active = bool(state.get("breakeven_active", False))
    exits = list(state.get("exits") or [])
    running_closes = list(state.get("running_closes") or [])

    if remaining <= 0 or today <= alert_date:
        return _skip(remaining, partial_taken, breakeven_active,
                     running_closes, exits, today, alert_date,
                     "skip_pre_alert")

    if not daily_bar:
        return _skip(remaining, partial_taken, breakeven_active,
                     running_closes, exits, today, alert_date,
                     "no_data")

    bar_low = float(daily_bar.get("l", 0))
    bar_close = float(daily_bar.get("c", 0))
    hold_days = (today - alert_date).days
    running_closes = running_closes + [bar_close]

    # 1. Hard stop — backtest-pure semantics. Live wrapper passes
    # skip_hard_stop_close=True after Alpaca verifies the position is
    # still held, so the close branch is bypassed but hard_stop still
    # contributes to effective_stop below.
    if hard_stop and bar_low <= hard_stop and not skip_hard_stop_close:
        pnl = (hard_stop - entry_price) * remaining if entry_price else 0
        new_exits = exits + [{
            "time": datetime.combine(today, time(16, 0)).isoformat(),
            "price": hard_stop,
            "reason": "stop_hit",
            "shares": remaining,
            "pnl": pnl,
        }]
        total_pnl = sum(e.get("pnl", 0) for e in new_exits)
        return ExitStep(
            action="stopped_out", closed=True,
            close_reason="stop_hit", close_price=hard_stop,
            close_shares=remaining, close_pnl=pnl,
            partial_fired=False, partial_shares=0,
            partial_price=None, partial_pnl=None,
            effective_stop=float(hard_stop), active_sma=None,
            bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
            new_remaining=0, new_partial_taken=partial_taken,
            new_breakeven_active=breakeven_active,
            new_running_closes=running_closes, new_exits=new_exits,
            new_total_pnl=total_pnl,
        )

    # 2. SMA10/20 — same logic both call sites
    active_sma = None
    if len(running_closes) >= 20:
        sma_10 = sum(running_closes[-10:]) / 10
        sma_20 = sum(running_closes[-20:]) / 20
        active_sma = sma_10 if sma_10 > sma_20 else sma_20
    elif len(running_closes) >= 10:
        active_sma = sum(running_closes[-10:]) / 10

    # 3. Partial profit Day 3-5
    partial_fired = False
    partial_shares = 0.0
    partial_pnl = None
    partial_price = None
    if not skip_partial_decision and hold_days >= 3 and not partial_taken and entry_price:
        take_partial = (
            (hold_days <= 4 and bar_close > entry_price)
            or hold_days >= 5
        )
        if take_partial:
            if integer_partial_shares:
                partial_shares = float(int(remaining) // 3)
            else:
                partial_shares = remaining / 3
            if partial_shares > 0:
                partial_fired = True
                partial_price = bar_close
                partial_pnl = (bar_close - entry_price) * partial_shares
                remaining -= partial_shares
                exits = exits + [{
                    "time": datetime.combine(today, time(16, 0)).isoformat(),
                    "price": bar_close,
                    "reason": "partial_profit",
                    "shares": partial_shares,
                    "pnl": partial_pnl,
                }]
                partial_taken = True
                breakeven_active = True

    # 4. Effective stop
    effective_stop = float(hard_stop or 0)
    if active_sma and active_sma > effective_stop:
        effective_stop = active_sma
    if breakeven_active and entry_price and entry_price > effective_stop:
        effective_stop = float(entry_price)

    # 5. SMA trail close
    if bar_close < effective_stop and remaining > 0:
        pnl = (bar_close - entry_price) * remaining if entry_price else 0
        new_exits = exits + [{
            "time": datetime.combine(today, time(16, 0)).isoformat(),
            "price": bar_close,
            "reason": "sma_trail_stop",
            "shares": remaining,
            "pnl": pnl,
        }]
        total_pnl = sum(e.get("pnl", 0) for e in new_exits)
        return ExitStep(
            action="sma_stopped", closed=True,
            close_reason="sma_trail_stop", close_price=bar_close,
            close_shares=remaining, close_pnl=pnl,
            partial_fired=partial_fired, partial_shares=partial_shares,
            partial_price=partial_price, partial_pnl=partial_pnl,
            effective_stop=effective_stop, active_sma=active_sma,
            bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
            new_remaining=0, new_partial_taken=partial_taken,
            new_breakeven_active=breakeven_active,
            new_running_closes=running_closes, new_exits=new_exits,
            new_total_pnl=total_pnl,
        )

    # 6. Still open
    total_pnl = sum(e.get("pnl", 0) for e in exits)
    action = "partial_only" if partial_fired else "updated"
    return ExitStep(
        action=action, closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=partial_fired, partial_shares=partial_shares,
        partial_price=partial_price, partial_pnl=partial_pnl,
        effective_stop=effective_stop, active_sma=active_sma,
        bar_low=bar_low, bar_close=bar_close, hold_days=hold_days,
        new_remaining=remaining, new_partial_taken=partial_taken,
        new_breakeven_active=breakeven_active,
        new_running_closes=running_closes, new_exits=exits,
        new_total_pnl=total_pnl,
    )


def _skip(remaining, partial_taken, breakeven_active,
          running_closes, exits, today, alert_date, action) -> ExitStep:
    hold_days = (today - alert_date).days if alert_date else 0
    total_pnl = sum(e.get("pnl", 0) for e in exits)
    return ExitStep(
        action=action, closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=False, partial_shares=0,
        partial_price=None, partial_pnl=None,
        effective_stop=0, active_sma=None,
        bar_low=None, bar_close=None, hold_days=hold_days,
        new_remaining=remaining, new_partial_taken=partial_taken,
        new_breakeven_active=breakeven_active,
        new_running_closes=running_closes, new_exits=exits,
        new_total_pnl=total_pnl,
    )
