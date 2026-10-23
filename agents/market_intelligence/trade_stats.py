"""#706 — the per-position stats on /trades (pure; display only, changes no trade state).

Operator 2026-10-21 asked for three numbers on every position:
  * OPEN   — size as a % of the account's equity, and the stop % = (current - stop) / current,
             the % of the CURRENT price we lose if the stop is hit from here;
  * CLOSED — the % win/loss of the trade, beside the R and the $ P&L.

Every helper returns ``None`` when an input is missing or unusable and the renderers print
"—" for None: a stat that cannot be computed is blank, NEVER a made-up number.

Which numbers (the answer to "of what"):
  * position % = ``abs(broker market_value) / broker account equity`` — both straight from the
    broker, the equity fetched at render time from the SAME account the position is held in (each
    row's own ``account_mode``; never cached, never the legacy global-mode account for a live row).
    ``abs`` because Alpaca reports a short's market value negative.
  * stop %     = the % of the broker's CURRENT price lost if the stop is hit from here:
    ``(current - stop) / current`` for a long, ``(stop - current) / current`` for a short (a
    short's stop sits ABOVE the price). POSITIVE = the loss the operator asked for (price 100,
    stop 95 -> 5.0); NEGATIVE = the price has already moved through the stop. The side comes
    from the broker position, not a guess.
  * closed %   = ``total_pnl / (entry_price x entry_shares)``. On a single-exit trade this IS
    ``(exit - entry) / entry`` for a long and ``(entry - exit) / entry`` for a short (the sign of
    ``total_pnl`` already carries the side), and unlike a single exit price it stays right when
    the trade banked a partial first or exited in more than one leg. It is the SAME frame the
    realized R uses (``sell_discipline.trade_realized_r``: total_pnl over entry risk x
    entry_shares), so the three numbers on a closed line cannot disagree.
    ⚠ RE-ENTRY ROWS (``entry_attempt`` > 1): a stop-out followed by a re-entry keeps ONE row —
    ``total_pnl`` is the sum of every attempt's exits, but each fill overwrites ``entry_price`` /
    ``entry_shares`` with the LAST attempt's. The % there is the whole row's P&L over the LAST
    attempt's cost: the same frame the R uses (so the two still agree), but it is not
    ``(exit - entry) / entry`` of any single leg. The re-entry count is already shown beside the
    ticker (``2x``) on the per-ticker view.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


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


def stop_loss_pct(side: Any, current: Any, stop: Any) -> Optional[float]:
    """The % of the CURRENT price lost if the stop is hit from here — operator 2026-10-21:
    "how much % we lose if get stopped"; PLAN #706 (current - stop) / current.
    Long: (current - stop) / current. Short: (stop - current) / current — a short's stop is
    ABOVE the price. POSITIVE = a loss if stopped (the normal case: price 100, stop 95 -> 5.0).
    NEGATIVE = the price has already moved through the stop (a stale stop the broker has not
    filled yet). None if the side is unknown or either price is missing / non-positive."""
    s, c, st = normalize_side(side), _f(current), _f(stop)
    if s is None or c is None or st is None or c <= 0 or st <= 0:
        return None
    return (c - st) / c * 100.0 if s == "long" else (st - c) / c * 100.0


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
        "stop_pct": stop_loss_pct(side, current_price, stop_price),
    }


def fmt_pct(v: Optional[float], *, signed: bool = False, places: int = 1) -> str:
    """'4.2%' / '+4.2%' / '—'. A value that rounds to zero prints '0.0%' (never '-0.0%')."""
    if v is None:
        return "—"
    r = round(v, places)
    if r == 0:
        r = 0.0
    return f"{r:+.{places}f}%" if signed else f"{r:.{places}f}%"


def fmt_stop_pct(v: Optional[float]) -> str:
    """'5.0% to stop' (the % lost if stopped from here) / 'through stop by 1.0%' (the price has
    already moved through the stop) / '—' (not computable). Never a bare signed number: the two
    directions read differently on purpose."""
    if v is None:
        return "—"
    r = round(v, 1)
    return f"through stop by {fmt_pct(-r)}" if r < 0 else f"{fmt_pct(r)} to stop"   # fmt_pct never prints '-0.0%'


def fmt_return_suffix(trade: dict) -> str:
    """' · +4.2%' — a closed trade's % win/loss as the suffix both /trades views append; '' when
    `trade_return_pct` cannot compute it (no entry / shares frame): never a made-up one."""
    ret = trade_return_pct(trade)
    return f" · {fmt_pct(ret, signed=True)}" if ret is not None else ""


def fmt_size_stop_lines(
    *, shares: Any, market_value: Any, stop_price: Any, stats: dict, indent: str = "      ",
) -> list[str]:
    """The two /trades open-position lines that carry the #706 stats (plain text — no pipe
    table, nothing Telegram needs escaped):
        '      19 sh · $4,210 · 8.1% of equity'
        '      Stop $212.40 · 5.1% to stop'
    A missing number prints '?' (price) or '—' (a stat); never a wrong one."""
    sh = _f(shares) or 0.0
    mv = _f(market_value)
    st = _f(stop_price)
    mv_str = f"${mv:,.0f}" if mv is not None else "?"
    stop_str = f"${st:.2f}" if st else "?"
    return [
        f"{indent}{sh:.0f} sh · {mv_str} · {fmt_pct(stats.get('position_pct'))} of equity",
        f"{indent}Stop {stop_str} · {fmt_stop_pct(stats.get('stop_pct'))}",
    ]


def fmt_stat_line(*, stats: dict, equity: Any, indent: str = "  ") -> str:
    """The one-line form for the per-ticker view, which already prints shares and the stop
    elsewhere:  '  8.1% of $50,000 equity · 5.0% to stop'. The equity is named inline because
    that view can mix the live and paper books (each row is measured against ITS account)."""
    eq = _f(equity)
    eq_str = f"${eq:,.0f}" if eq is not None else "—"
    return f"{indent}{fmt_pct(stats.get('position_pct'))} of {eq_str} equity · {fmt_stop_pct(stats.get('stop_pct'))}"


async def read_open_position_stats(
    rows: list[dict], *, get_position: Callable, get_account: Callable, default_mode: Optional[str] = "live",
) -> tuple[list[dict], dict]:
    """The broker reads behind the two OPEN stats, in ONE place for every surface that shows them.

    ``rows``: dicts with ``ticker``, ``stop_price`` and (optionally) ``account_mode``. Each row is
    read from, and measured against, ITS OWN account: ``get_position(ticker, account_mode=mode)``
    and ONE ``get_account(account_mode=mode)`` per distinct mode — never the no-arg form for a row
    whose mode is known (it resolves to the legacy global mode = paper on prod, so a real-money
    row would be measured against the paper book). A row with no ``account_mode`` uses
    ``default_mode``; ``None`` there is the broker's own default (the legacy behaviour).
    Nothing is cached: every call reads the broker fresh, so the % never rests on a stale equity.

    Returns ``(items, equity_by_mode)``; ``items[i]`` is aligned to ``rows[i]``:
    ``{"mode", "pos" (the broker's position dict, or None), "stats" (open_position_stats)}``.
    A failed read is a ``None`` (logged), never an exception and never a made-up number: the
    stats it feeds print as dashes."""
    modes = [(r.get("account_mode") or default_mode) for r in rows]
    equity_by_mode: dict = {}
    for mode in dict.fromkeys(modes):                   # distinct, order-preserving
        try:
            equity_by_mode[mode] = float((await get_account(account_mode=mode))["equity"])
        except Exception as e:
            logger.warning(f"#706 open-position stats: account equity read failed (mode={mode}) — % of equity shows '—': {e}")
            equity_by_mode[mode] = None
    items: list[dict] = []
    for r, mode in zip(rows, modes):
        try:
            pos = await get_position(r["ticker"], account_mode=mode)
        except Exception as e:
            logger.debug(f"#706 open-position stats: position read failed for {r.get('ticker')} (mode={mode}): {e}")
            pos = None
        pos = pos or None
        p = pos or {}
        items.append({
            "mode": mode,
            "pos": pos,
            "stats": open_position_stats(
                side=p.get("side"),
                market_value=p.get("market_value"),
                current_price=p.get("current_price"),
                stop_price=r.get("stop_price"),
                equity=equity_by_mode.get(mode),
            ),
        })
    return items, equity_by_mode
