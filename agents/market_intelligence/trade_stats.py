"""#706 — the per-position stats on /trades (pure; display only, changes no trade state).

Operator 2026-10-21 asked for three numbers on every position:
  * OPEN   — size as a % of the account's equity, and the stop % (how much we lose, as a %
             of the CURRENT price, if the stop is hit from here);
  * CLOSED — the % win/loss of the trade, beside the R and the $ P&L.

Every helper returns ``None`` when an input is missing or unusable and the renderers print
"—" for None: a stat that cannot be computed is blank, NEVER a made-up number.

Which numbers (the answer to "of what"):
  * position % = ``abs(broker market_value) / broker account equity`` — both straight from the
    broker, the equity fetched at render time from the LIVE account (never cached, never the
    legacy global-mode account). ``abs`` because Alpaca reports a short's market value negative.
  * stop %     = the signed move from the broker's CURRENT price to the stop, as a % of that
    price; NEGATIVE = a loss if stopped. Side-aware: a long's stop sits below the price, a
    short's above it. The side comes from the broker position, not a guess.
  * closed %   = ``total_pnl / (entry_price x entry_shares)``. On a single-exit trade this IS
    ``(exit - entry) / entry`` for a long and ``(entry - exit) / entry`` for a short (the sign of
    ``total_pnl`` already carries the side), and unlike a single exit price it stays right when
    the trade banked a partial first or exited in more than one leg. It is the SAME frame the
    realized R uses (``sell_discipline.trade_realized_r``: total_pnl over entry risk x
    entry_shares), so the three numbers on a closed line cannot disagree.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def _f(x: Any) -> Optional[float]:
    """A finite float, or None (None / NaN / inf / non-numeric all mean "not usable")."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def normalize_side(side: Any) -> Optional[str]:
    """'long' | 'short' | None. Accepts the broker's plain value ('long'), an enum-ish string
    ('PositionSide.LONG') or any case; anything else is None (unknown side -> no stop %)."""
    if side is None:
        return None
    s = str(side).split(".")[-1].strip().lower()
    return s if s in ("long", "short") else None


def position_pct_of_equity(market_value: Any, equity: Any) -> Optional[float]:
    """Position size as a % of account equity. None without a market value or a positive equity."""
    mv, eq = _f(market_value), _f(equity)
    if mv is None or eq is None or eq <= 0:
        return None
    return abs(mv) / eq * 100.0


def stop_move_pct(side: Any, current: Any, stop: Any) -> Optional[float]:
    """The move from the current price to the stop, as a % of the current price, SIGNED:
    negative = a loss if the stop is hit from here (the normal case); positive = the stop sits
    on the profit side of the price (a stale/raised stop the price has already fallen through).
    Long: (stop - current) / current. Short: (current - stop) / current — a short's stop is
    ABOVE the price. None if the side is unknown or either price is missing / non-positive."""
    s, c, st = normalize_side(side), _f(current), _f(stop)
    if s is None or c is None or st is None or c <= 0 or st <= 0:
        return None
    return (st - c) / c * 100.0 if s == "long" else (c - st) / c * 100.0


def trade_return_pct(trade: dict) -> Optional[float]:
    """A CLOSED trade's % win/loss: total_pnl over what was put in (entry_price x entry_shares).
    Side-aware by construction (see module docstring). None when any input is missing, the
    entry/shares are not positive, or total_pnl is absent."""
    pnl, entry, shares = _f(trade.get("total_pnl")), _f(trade.get("entry_price")), _f(trade.get("entry_shares"))
    if pnl is None or entry is None or shares is None or entry <= 0 or shares <= 0:
        return None
    return pnl / (entry * shares) * 100.0


def open_position_stats(
    *, side: Any, market_value: Any, current_price: Any, stop_price: Any, equity: Any,
) -> dict:
    """The two OPEN-position stats plus the normalized side, from broker numbers."""
    return {
        "side": normalize_side(side),
        "position_pct": position_pct_of_equity(market_value, equity),
        "stop_pct": stop_move_pct(side, current_price, stop_price),
    }


def fmt_pct(v: Optional[float], *, signed: bool = False, places: int = 1) -> str:
    """'4.2%' / '+4.2%' / '—'. A value that rounds to zero prints '0.0%' (never '-0.0%')."""
    if v is None:
        return "—"
    r = round(v, places)
    if r == 0:
        r = 0.0
    return f"{r:+.{places}f}%" if signed else f"{r:.{places}f}%"


def fmt_size_stop_lines(
    *, shares: Any, market_value: Any, stop_price: Any, stats: dict, indent: str = "      ",
) -> list[str]:
    """The two /trades open-position lines that carry the #706 stats (plain text — no pipe
    table, nothing Telegram needs escaped):
        '      19 sh · $4,210 · 8.1% of equity'
        '      Stop $212.40 · -5.1% if hit'
    A missing number prints '?' (price) or '—' (a stat); never a wrong one."""
    sh = _f(shares) or 0.0
    mv = _f(market_value)
    st = _f(stop_price)
    mv_str = f"${mv:,.0f}" if mv is not None else "?"
    stop_str = f"${st:.2f}" if st else "?"
    return [
        f"{indent}{sh:.0f} sh · {mv_str} · {fmt_pct(stats.get('position_pct'))} of equity",
        f"{indent}Stop {stop_str} · {fmt_pct(stats.get('stop_pct'), signed=True)} if hit",
    ]
