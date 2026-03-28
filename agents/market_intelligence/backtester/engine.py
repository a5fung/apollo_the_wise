"""Core trade simulation engine for EP gap trading backtest."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
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
    atr_14: float | None = None,
) -> BacktestTrade | None:
    """
    Simulate Day 1 intraday trading on 5-min bars (ORB entry).

    Rules:
    - Opening Range = first 5-min bar's high/low
    - ATR stop width check: skip if ORB range > 1.5x ATR-14
    - Entry when price breaks above ORB high (bars[1:])
    - Stop = ORB low (hard stop: bar low <= stop)
    - Re-entry when bar closes above ORB high, max 3 attempts
    - EOD: hold full position (no partial sell)
    """
    if not bars:
        return None

    first_bar = bars[0]
    orb_high = first_bar["high"]
    orb_low = first_bar["low"]

    if orb_high <= 0 or orb_low <= 0:
        return None

    # ATR stop width validation: skip if ORB range too wide
    orb_range = orb_high - orb_low
    if atr_14 and orb_range > 1.5 * atr_14:
        alert_date = first_bar["bar_time"].date() if hasattr(first_bar["bar_time"], "date") else date.today()
        trade = BacktestTrade(
            ticker=ticker, alert_date=alert_date,
            ep_score=0, catalyst_quality="", gap_pct=0, regime=None,
            skipped=True, skip_reason="stop_too_wide",
            orb_high=orb_high, orb_low=orb_low, atr_14=atr_14,
        )
        return trade

    entries: list[TradeEntry] = []
    exits: list[TradeExit] = []
    attempt = 0
    in_position = False
    current_stop = 0.0
    current_shares = 0.0

    # Walk bars[1:] looking for ORB high breakout
    for bar in bars[1:]:
        if in_position:
            # Hard stop: bar low breaches stop
            if bar["low"] <= current_stop:
                pnl = (current_stop - entries[-1].entry_price) * current_shares
                exits.append(TradeExit(
                    exit_time=bar["bar_time"],
                    exit_price=current_stop,
                    exit_reason="stop_hit",
                    shares_exited=current_shares,
                    pnl=pnl,
                ))
                in_position = False
                current_shares = 0.0
        else:
            # Look for breakout / re-entry
            if attempt >= MAX_ENTRY_ATTEMPTS:
                continue

            if bar["high"] > orb_high:
                # Breakout entry at ORB high level
                attempt += 1
                entry_price = orb_high
                shares = position_size / entry_price
                current_stop = orb_low if attempt == 1 else bar["low"]
                current_shares = shares
                in_position = True

                entries.append(TradeEntry(
                    entry_time=bar["bar_time"],
                    entry_price=entry_price,
                    stop_price=current_stop,
                    attempt_number=attempt,
                    shares=shares,
                ))

                # Check if same bar also hits stop
                if bar["low"] <= current_stop:
                    pnl = (current_stop - entry_price) * current_shares
                    exits.append(TradeExit(
                        exit_time=bar["bar_time"],
                        exit_price=current_stop,
                        exit_reason="stop_hit",
                        shares_exited=current_shares,
                        pnl=pnl,
                    ))
                    in_position = False
                    current_shares = 0.0

    # No breakout all day
    if not entries:
        alert_date = first_bar["bar_time"].date() if hasattr(first_bar["bar_time"], "date") else date.today()
        trade = BacktestTrade(
            ticker=ticker, alert_date=alert_date,
            ep_score=0, catalyst_quality="", gap_pct=0, regime=None,
            skipped=True, skip_reason="orb_no_breakout",
            orb_high=orb_high, orb_low=orb_low, atr_14=atr_14,
        )
        return trade

    # EOD handling — hold full position (no partial sell)
    if in_position and entries:
        last_bar = bars[-1]
        last_entry = entries[-1]
        total_pnl = sum(e.pnl for e in exits)

        trade = BacktestTrade(
            ticker=ticker,
            alert_date=last_bar["bar_time"].date() if hasattr(last_bar["bar_time"], "date") else date.today(),
            ep_score=0, catalyst_quality="", gap_pct=0, regime=None,
            entries=entries, exits=exits, total_pnl=total_pnl,
            orb_high=orb_high, orb_low=orb_low, atr_14=atr_14,
        )
        # Stash full position for Day 2+ simulation
        trade._remaining_shares = current_shares  # type: ignore[attr-defined]
        trade._last_entry = last_entry  # type: ignore[attr-defined]
        trade._day1_low = min(b["low"] for b in bars)  # type: ignore[attr-defined]
        return trade

    # Fully stopped out on Day 1
    if exits:
        total_pnl = sum(e.pnl for e in exits)
        return BacktestTrade(
            ticker=ticker,
            alert_date=bars[0]["bar_time"].date() if hasattr(bars[0]["bar_time"], "date") else date.today(),
            ep_score=0, catalyst_quality="", gap_pct=0, regime=None,
            entries=entries, exits=exits, total_pnl=total_pnl,
            orb_high=orb_high, orb_low=orb_low, atr_14=atr_14,
        )

    return None


def _simulate_trailing_stop(
    trade: BacktestTrade,
    daily_bars: list[dict],
    alert_date: date,
    pre_alert_bars: list[dict] | None = None,
) -> None:
    """
    Simulate Day 2+ with 10/20 SMA trailing stop and delayed partial profit.

    Rules:
    - Hard stop = Day 1 low (floor, never lowered)
    - SMA trail: active SMA = 10-SMA if 10 > 20, else 20-SMA
    - Exit on daily close below effective stop (max of hard stop, SMA, breakeven)
    - Partial profit: sell 1/3 on Day 3-5 (Day 3-4 only if profitable, Day 5 regardless)
    - After partial: move stop floor to breakeven (entry price)
    """
    remaining_shares = getattr(trade, "_remaining_shares", 0.0)
    last_entry = getattr(trade, "_last_entry", None)

    if remaining_shares <= 0 or last_entry is None:
        return

    hard_stop = getattr(trade, "_day1_low", last_entry.stop_price)
    entry_price = last_entry.entry_price
    partial_taken = False
    breakeven_active = False
    day_count = 0

    # Build running close list from pre-alert bars for SMA warm-up
    running_closes: list[float] = []
    if pre_alert_bars:
        for b in pre_alert_bars:
            c = b.get("c", b.get("close", 0))
            if c and c > 0:
                running_closes.append(float(c))

    for bar in daily_bars:
        bar_low = bar.get("l", bar.get("low", 0))
        bar_close = bar.get("c", bar.get("close", 0))
        bar_date = _bar_date(bar)
        day_count += 1

        running_closes.append(float(bar_close))

        # 1. Hard stop check (intraday low breaches hard stop)
        if bar_low <= hard_stop:
            pnl = (hard_stop - entry_price) * remaining_shares
            trade.exits.append(TradeExit(
                exit_time=datetime.combine(bar_date, datetime.min.time()),
                exit_price=hard_stop,
                exit_reason="stop_hit",
                shares_exited=remaining_shares,
                pnl=pnl,
            ))
            trade.total_pnl = sum(e.pnl for e in trade.exits)
            trade.hold_days = (bar_date - alert_date).days
            return

        # 2. Compute SMAs
        active_sma = None
        if len(running_closes) >= 20:
            sma_10 = sum(running_closes[-10:]) / 10
            sma_20 = sum(running_closes[-20:]) / 20
            active_sma = sma_10 if sma_10 > sma_20 else sma_20
        elif len(running_closes) >= 10:
            active_sma = sum(running_closes[-10:]) / 10

        # 3. Partial profit on Day 3-5
        if day_count >= 3 and not partial_taken:
            take_partial = False
            if day_count <= 4 and bar_close > entry_price:
                take_partial = True
            elif day_count >= 5:
                take_partial = True

            if take_partial:
                partial_shares = remaining_shares / 3
                remaining_shares -= partial_shares
                pnl = (bar_close - entry_price) * partial_shares
                trade.exits.append(TradeExit(
                    exit_time=datetime.combine(bar_date, datetime.min.time()),
                    exit_price=bar_close,
                    exit_reason="partial_profit",
                    shares_exited=partial_shares,
                    pnl=pnl,
                ))
                partial_taken = True
                breakeven_active = True
                trade.breakeven_stop = True

        # 4. SMA trail check (close-based)
        effective_stop = hard_stop
        if active_sma and active_sma > hard_stop:
            effective_stop = active_sma
        if breakeven_active and entry_price > effective_stop:
            effective_stop = entry_price

        if bar_close < effective_stop:
            pnl = (bar_close - entry_price) * remaining_shares
            trade.exits.append(TradeExit(
                exit_time=datetime.combine(bar_date, datetime.min.time()),
                exit_price=bar_close,
                exit_reason="sma_trail_stop",
                shares_exited=remaining_shares,
                pnl=pnl,
            ))
            trade.total_pnl = sum(e.pnl for e in trade.exits)
            trade.hold_days = (bar_date - alert_date).days
            return

    # Still holding at end of data — exit at last available close
    if daily_bars:
        last_bar = daily_bars[-1]
        last_close = last_bar.get("c", last_bar.get("close", 0))
        last_date = _bar_date(last_bar)

        pnl = (last_close - entry_price) * remaining_shares
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
    Full trade simulation: Day 1 ORB intraday + Day 2+ SMA trailing stop.
    """
    # Compute ATR before Day 1 for stop width validation
    atr_14 = await compute_atr_14(ticker, alert_date)

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
            atr_14=atr_14,
        )
        return trade

    # Day 1 simulation (ORB entry with ATR validation)
    trade = _simulate_day1(ticker, bars, position_size, atr_14=atr_14)
    if trade is None:
        return BacktestTrade(
            ticker=ticker, alert_date=alert_date,
            ep_score=ep_alert.get("ep_score", 0),
            catalyst_quality=ep_alert.get("catalyst_quality", ""),
            gap_pct=ep_alert.get("gap_pct", 0),
            regime=ep_alert.get("regime"),
            skipped=True, skip_reason="no_valid_entry",
            atr_14=atr_14,
        )

    # Fill in EP alert metadata
    trade.ep_score = ep_alert.get("ep_score", 0)
    trade.catalyst_quality = ep_alert.get("catalyst_quality", "")
    trade.gap_pct = ep_alert.get("gap_pct", 0)
    trade.regime = ep_alert.get("regime")
    trade.alert_date = alert_date
    trade.atr_14 = atr_14

    # If trade was skipped by Day 1 (ORB no breakout, stop too wide), return as-is
    if trade.skipped:
        return trade

    # Day 2+ trailing stop (only if still holding)
    remaining = getattr(trade, "_remaining_shares", 0.0)
    if remaining > 0:
        # Fetch daily bars starting 35 days before alert for SMA warm-up
        today = et_today()
        from_date_str = (alert_date - timedelta(days=35)).strftime("%Y-%m-%d")
        to_date_str = today.strftime("%Y-%m-%d")

        daily_bars = await get_index_history(ticker, from_date_str, to_date_str)

        # Split into pre-alert (warm-up) and post-alert (trading) bars
        pre_alert_bars = [b for b in daily_bars if _bar_date(b) <= alert_date]
        future_bars = [b for b in daily_bars if _bar_date(b) > alert_date]

        _simulate_trailing_stop(
            trade, future_bars, alert_date, pre_alert_bars=pre_alert_bars,
        )

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
            SELECT DISTINCT ON (ticker, alert_date)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, claude_analysis,
                   vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date >= $1 AND alert_date <= $2
              AND ep_score >= $3
              AND score_tier = 'HIGH'
            ORDER BY ticker, alert_date, ep_score DESC
        """, from_date, to_date, min_score)
    # Re-sort by date after DISTINCT ON
    results = [dict(r) for r in rows]
    results.sort(key=lambda r: (r["alert_date"], -r.get("ep_score", 0)))
    return results


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
