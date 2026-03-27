"""Core trade simulation engine for EP gap trading backtest."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from agents.market_intelligence.backtester.filters import check_filters
from agents.market_intelligence.backtester.intraday import ensure_intraday_table, get_intraday_bars
from agents.market_intelligence.backtester.models import (
    BacktestResult,
    BacktestTrade,
    TradeEntry,
    TradeExit,
)
from agents.market_intelligence.backtester.safeguards import SafeguardTracker
from agents.market_intelligence.collector import _polygon_get, et_today, get_index_history
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

MAX_ENTRY_ATTEMPTS = 3


def _simulate_day1(
    ticker: str,
    bars: list[dict],
    position_size: float,
) -> BacktestTrade | None:
    """
    Simulate Day 1 intraday trading on 5-min bars.

    Rules:
    - Entry at first bar (9:30) open price
    - Stop = first bar's low
    - If any bar closes below stop → stopped out at that bar's close
    - Re-enter when a bar closes above first bar's close
    - On re-entry: new stop = re-entry bar's low
    - Max 3 attempts per day
    """
    if not bars:
        return None

    first_bar = bars[0]
    entries: list[TradeEntry] = []
    exits: list[TradeExit] = []
    attempt = 0
    in_position = False
    current_stop = 0.0
    current_shares = 0.0
    first_bar_close = first_bar["close"]

    # Attempt 1: buy at market open
    entry_price = first_bar["open"]
    if entry_price <= 0:
        return None

    shares = position_size / entry_price
    current_stop = first_bar["low"]
    current_shares = shares
    in_position = True
    attempt = 1

    entries.append(TradeEntry(
        entry_time=first_bar["bar_time"],
        entry_price=entry_price,
        stop_price=current_stop,
        attempt_number=attempt,
        shares=shares,
    ))

    # Walk remaining bars
    for bar in bars[1:]:
        if in_position:
            # Check if bar closes below stop → stopped out
            if bar["close"] <= current_stop:
                pnl = (bar["close"] - entries[-1].entry_price) * current_shares
                exits.append(TradeExit(
                    exit_time=bar["bar_time"],
                    exit_price=bar["close"],
                    exit_reason="stop_hit",
                    shares_exited=current_shares,
                    pnl=pnl,
                ))
                in_position = False
                current_shares = 0.0

        else:
            # Not in position — look for re-entry
            if attempt >= MAX_ENTRY_ATTEMPTS:
                continue  # no more attempts

            # Re-enter when bar closes above first bar's close
            if bar["close"] > first_bar_close:
                attempt += 1
                entry_price = bar["close"]  # enter at this bar's close
                shares = position_size / entry_price
                current_stop = bar["low"]
                current_shares = shares
                in_position = True

                entries.append(TradeEntry(
                    entry_time=bar["bar_time"],
                    entry_price=entry_price,
                    stop_price=current_stop,
                    attempt_number=attempt,
                    shares=shares,
                ))

    # EOD handling
    if in_position and entries:
        last_bar = bars[-1]
        last_entry = entries[-1]

        # Sell 1/3 at close
        partial_shares = current_shares / 3
        remaining_shares = current_shares - partial_shares

        pnl_partial = (last_bar["close"] - last_entry.entry_price) * partial_shares
        exits.append(TradeExit(
            exit_time=last_bar["bar_time"],
            exit_price=last_bar["close"],
            exit_reason="eod_partial",
            shares_exited=partial_shares,
            pnl=pnl_partial,
        ))

        # Return trade with remaining 2/3 still open
        total_pnl = sum(e.pnl for e in exits)
        trade = BacktestTrade(
            ticker=ticker,
            alert_date=last_bar["bar_time"].date() if hasattr(last_bar["bar_time"], "date") else date.today(),
            ep_score=0,  # filled by caller
            catalyst_quality="",
            gap_pct=0,
            regime=None,
            entries=entries,
            exits=exits,
            total_pnl=total_pnl,
        )
        # Stash remaining position info for Day 2+ simulation
        trade._remaining_shares = remaining_shares  # type: ignore[attr-defined]
        trade._last_entry = last_entry  # type: ignore[attr-defined]
        trade._day1_low = min(b["low"] for b in bars)  # type: ignore[attr-defined]
        return trade

    # Fully stopped out on Day 1
    if exits:
        total_pnl = sum(e.pnl for e in exits)
        return BacktestTrade(
            ticker=ticker,
            alert_date=bars[0]["bar_time"].date() if hasattr(bars[0]["bar_time"], "date") else date.today(),
            ep_score=0,
            catalyst_quality="",
            gap_pct=0,
            regime=None,
            entries=entries,
            exits=exits,
            total_pnl=total_pnl,
        )

    return None


def _simulate_trailing_stop(
    trade: BacktestTrade,
    daily_bars: list[dict],
    alert_date: date,
) -> None:
    """
    Simulate Day 2+ trailing stop on daily OHLCV bars.

    Rules:
    - Broker-side stop at prior day's low
    - If any day's low breaches stop → fill at stop price
    - Before each close, ratchet stop up to this day's low (never lower)
    - Hold until stop is hit
    """
    remaining_shares = getattr(trade, "_remaining_shares", 0.0)
    last_entry = getattr(trade, "_last_entry", None)

    if remaining_shares <= 0 or last_entry is None:
        return

    # Initial stop = Day 1's low
    stop_price = getattr(trade, "_day1_low", last_entry.stop_price)

    # Filter daily bars to Day 2+ only (after alert_date)
    future_bars = [
        b for b in daily_bars
        if _bar_date(b) > alert_date
    ]

    for bar in future_bars:
        bar_low = bar.get("l", bar.get("low", 0))
        bar_close = bar.get("c", bar.get("close", 0))
        bar_date = _bar_date(bar)

        # Check if stop hit (bar's low breaches stop)
        if bar_low <= stop_price:
            pnl = (stop_price - last_entry.entry_price) * remaining_shares
            trade.exits.append(TradeExit(
                exit_time=datetime.combine(bar_date, datetime.min.time()),
                exit_price=stop_price,
                exit_reason="trailing_stop",
                shares_exited=remaining_shares,
                pnl=pnl,
            ))
            trade.total_pnl = sum(e.pnl for e in trade.exits)
            trade.hold_days = (bar_date - alert_date).days
            return

        # Ratchet stop up (never lower)
        if bar_low > stop_price:
            stop_price = bar_low

    # Still holding at end of data — exit at last available close
    if future_bars:
        last_bar = future_bars[-1]
        last_close = last_bar.get("c", last_bar.get("close", 0))
        last_date = _bar_date(last_bar)

        pnl = (last_close - last_entry.entry_price) * remaining_shares
        trade.exits.append(TradeExit(
            exit_time=datetime.combine(last_date, datetime.min.time()),
            exit_price=last_close,
            exit_reason="data_ended",
            shares_exited=remaining_shares,
            pnl=pnl,
        ))
        trade.total_pnl = sum(e.pnl for e in trade.exits)
        trade.hold_days = (last_date - alert_date).days
    else:
        # No future bars at all — close at Day 1 last price
        trade.hold_days = 0
        trade.total_pnl = sum(e.pnl for e in trade.exits)


def _bar_date(bar: dict) -> date:
    """Extract date from a Polygon daily bar (timestamp in ms)."""
    t = bar.get("t")
    if t is None:
        return date.today()
    if isinstance(t, (int, float)):
        return datetime.utcfromtimestamp(t / 1000).date()
    return date.today()


async def simulate_trade(
    ticker: str,
    alert_date: date,
    ep_alert: dict,
    position_size: float,
) -> BacktestTrade:
    """
    Full trade simulation: Day 1 intraday + Day 2+ trailing stop.
    """
    # Fetch Day 1 intraday bars
    bars = await get_intraday_bars(ticker, alert_date)

    if not bars:
        trade = BacktestTrade(
            ticker=ticker, alert_date=alert_date,
            ep_score=ep_alert.get("ep_score", 0),
            catalyst_quality=ep_alert.get("catalyst_quality", ""),
            gap_pct=ep_alert.get("gap_pct", 0),
            regime=ep_alert.get("regime"),
            skipped=True, skip_reason="data_unavailable",
        )
        return trade

    # Day 1 simulation
    trade = _simulate_day1(ticker, bars, position_size)
    if trade is None:
        return BacktestTrade(
            ticker=ticker, alert_date=alert_date,
            ep_score=ep_alert.get("ep_score", 0),
            catalyst_quality=ep_alert.get("catalyst_quality", ""),
            gap_pct=ep_alert.get("gap_pct", 0),
            regime=ep_alert.get("regime"),
            skipped=True, skip_reason="no_valid_entry",
        )

    # Fill in EP alert metadata
    trade.ep_score = ep_alert.get("ep_score", 0)
    trade.catalyst_quality = ep_alert.get("catalyst_quality", "")
    trade.gap_pct = ep_alert.get("gap_pct", 0)
    trade.regime = ep_alert.get("regime")
    trade.alert_date = alert_date

    # Day 2+ trailing stop (only if still holding)
    remaining = getattr(trade, "_remaining_shares", 0.0)
    if remaining > 0:
        # Fetch daily bars for trailing stop simulation
        today = et_today()
        from_date = (alert_date + timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        daily_bars = await get_index_history(ticker, from_date, to_date)
        _simulate_trailing_stop(trade, daily_bars, alert_date)

    # Ensure total_pnl is up to date
    trade.total_pnl = sum(e.pnl for e in trade.exits)

    # Clean up temp attributes
    for attr in ("_remaining_shares", "_last_entry", "_day1_low"):
        if hasattr(trade, attr):
            delattr(trade, attr)

    return trade


async def run_backtest(
    from_date: date | None = None,
    to_date: date | None = None,
    position_size: float = 10_000,
    min_score: float = 70,
    initial_capital: float = 100_000,
) -> BacktestResult:
    """
    Run full EP gap trading backtest over a date range.

    Args:
        from_date: Start date (default: 90 days ago)
        to_date: End date (default: today)
        position_size: Dollar amount per trade
        min_score: Minimum EP score (default: 70 for HIGH tier)
        initial_capital: Starting account value for safeguard tracking
    """
    today = et_today()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - timedelta(days=90)

    logger.info(f"Starting backtest: {from_date} to {to_date}, size=${position_size:,.0f}, min_score={min_score}")

    # Ensure intraday table exists
    await ensure_intraday_table()

    # Load EP alerts from DB
    alerts = await _load_ep_alerts(from_date, to_date, min_score)
    logger.info(f"Found {len(alerts)} EP alerts with score >= {min_score}")

    # Load regime data for each alert date
    regimes = await _load_regimes(from_date, to_date)

    # Initialize safeguard tracker
    safeguards = SafeguardTracker()

    trades: list[BacktestTrade] = []
    skipped: list[BacktestTrade] = []

    for alert in alerts:
        ticker = alert["ticker"]
        alert_date = alert["alert_date"]
        if isinstance(alert_date, str):
            alert_date = date.fromisoformat(alert_date)

        # Attach regime
        alert["regime"] = regimes.get(alert_date)

        # Apply pre-trade filters
        passed, skip_reason = await check_filters(ticker, alert_date)
        if not passed:
            st = BacktestTrade(
                ticker=ticker, alert_date=alert_date,
                ep_score=alert.get("ep_score", 0),
                catalyst_quality=alert.get("catalyst_quality", ""),
                gap_pct=alert.get("gap_pct", 0),
                regime=alert.get("regime"),
                skipped=True, skip_reason=skip_reason,
            )
            skipped.append(st)
            logger.debug(f"Filtered {ticker} on {alert_date}: {skip_reason}")
            continue

        # Check safeguards (track but don't block in backtest)
        blocked, block_reason = safeguards.would_block(
            trade_date=alert_date,
            ticker=ticker,
            position_value=position_size,
            account_value=initial_capital,
        )
        if blocked:
            logger.debug(f"Safeguard would block {ticker} on {alert_date}: {block_reason}")

        # Simulate trade
        logger.info(f"Simulating {ticker} on {alert_date} (score={alert.get('ep_score', 0):.0f})")
        trade = await simulate_trade(ticker, alert_date, alert, position_size)

        if trade.skipped:
            skipped.append(trade)
        else:
            trades.append(trade)
            safeguards.record_trade_open(ticker)
            safeguards.record_trade_close(trade)

    result = BacktestResult(
        trades=trades,
        skipped_trades=skipped,
        from_date=from_date,
        to_date=to_date,
        initial_capital=initial_capital,
        position_size=position_size,
    )
    result.summary["safeguards"] = safeguards.summary

    logger.info(f"Backtest complete: {len(trades)} trades, {len(skipped)} skipped")
    return result


async def _load_ep_alerts(
    from_date: date, to_date: date, min_score: float
) -> list[dict]:
    """Load EP alerts from DB for the backtest date range."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, claude_analysis,
                   vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date >= $1 AND alert_date <= $2
              AND ep_score >= $3
              AND score_tier = 'HIGH'
            ORDER BY alert_date ASC, ep_score DESC
        """, from_date, to_date, min_score)
    return [dict(r) for r in rows]


async def _load_regimes(from_date: date, to_date: date) -> dict[date, str]:
    """Load market regime for each date in range."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT regime_date, regime
            FROM mi_market_regime
            WHERE regime_date >= $1 AND regime_date <= $2
        """, from_date, to_date)
    return {r["regime_date"]: r["regime"] for r in rows}
