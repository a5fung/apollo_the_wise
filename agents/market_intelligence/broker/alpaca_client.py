"""
Thin async wrapper around alpaca-py SDK for live EP trading.

Supports paper/live toggle via ALPACA_PAPER env var (default: paper).
All calls wrapped in try/except with logging.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

logger = logging.getLogger(__name__)

# ── Singleton clients ────────────────────────────────────────────────────────

_trading_client: TradingClient | None = None
_data_client: StockHistoricalDataClient | None = None


def _get_trading_client() -> TradingClient:
    global _trading_client
    if _trading_client is None:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
        _trading_client = TradingClient(api_key, secret_key, paper=paper)
        mode = "PAPER" if paper else "LIVE"
        logger.info(f"Alpaca TradingClient initialized ({mode})")
    return _trading_client


def _get_data_client() -> StockHistoricalDataClient:
    global _data_client
    if _data_client is None:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        _data_client = StockHistoricalDataClient(api_key, secret_key)
        logger.info("Alpaca StockHistoricalDataClient initialized")
    return _data_client


# ── Account ──────────────────────────────────────────────────────────────────


async def get_account() -> dict:
    """Get account info (equity, buying power, etc.)."""
    try:
        client = _get_trading_client()
        account = client.get_account()
        return {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "account_blocked": account.account_blocked,
        }
    except Exception as e:
        logger.error(f"Failed to get account: {e}")
        raise


# ── Orders ───────────────────────────────────────────────────────────────────


async def place_bracket_order(
    ticker: str,
    qty: float,
    stop_price: float,
    limit_price: float,
    stop_loss_price: float,
) -> dict:
    """
    Place a bracket order: stop-limit buy entry with attached stop-loss.
    - Entry: stop-limit buy triggers at stop_price, fills up to limit_price
    - Stop-loss: hard stop at stop_loss_price
    """
    try:
        client = _get_trading_client()
        order = client.submit_order(
            StopLimitOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.BUY,
                type=OrderType.STOP_LIMIT,
                time_in_force=TimeInForce.DAY,
                stop_price=round(stop_price, 2),
                limit_price=round(limit_price, 2),
                stop_loss={"stop_price": round(stop_loss_price, 2)},
            )
        )
        logger.info(
            f"Bracket order placed: {ticker} qty={qty} "
            f"stop={stop_price:.2f} limit={limit_price:.2f} SL={stop_loss_price:.2f} "
            f"order_id={order.id}"
        )
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place bracket order for {ticker}: {e}")
        raise


async def place_stop_order(
    ticker: str,
    qty: float,
    stop_price: float,
    side: str = "sell",
) -> dict:
    """Place a stop order (for Day 2+ stop updates)."""
    try:
        client = _get_trading_client()
        order = client.submit_order(
            StopOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL if side == "sell" else OrderSide.BUY,
                type=OrderType.STOP,
                time_in_force=TimeInForce.GTC,
                stop_price=round(stop_price, 2),
            )
        )
        logger.info(f"Stop order placed: {ticker} qty={qty} stop={stop_price:.2f} id={order.id}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place stop order for {ticker}: {e}")
        raise


async def place_market_sell(ticker: str, qty: float) -> dict:
    """Place a market sell order (for partials or full exits)."""
    try:
        client = _get_trading_client()
        order = client.submit_order(
            MarketOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )
        )
        logger.info(f"Market sell placed: {ticker} qty={qty} id={order.id}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place market sell for {ticker}: {e}")
        raise


async def cancel_order(order_id: str) -> bool:
    """Cancel an order by ID. Returns True if successful."""
    try:
        client = _get_trading_client()
        client.cancel_order_by_id(order_id)
        logger.info(f"Order cancelled: {order_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        return False


async def get_order(order_id: str) -> dict | None:
    """Get order details by ID."""
    try:
        client = _get_trading_client()
        order = client.get_order_by_id(order_id)
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        return None


async def get_open_orders(ticker: str | None = None) -> list[dict]:
    """Get all open orders, optionally filtered by ticker."""
    try:
        client = _get_trading_client()
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        if ticker:
            request.symbols = [ticker]
        orders = client.get_orders(request)
        return [_order_to_dict(o) for o in orders]
    except Exception as e:
        logger.error(f"Failed to get open orders: {e}")
        return []


# ── Positions ────────────────────────────────────────────────────────────────


async def get_position(ticker: str) -> dict | None:
    """Get position for a specific ticker."""
    try:
        client = _get_trading_client()
        pos = client.get_open_position(ticker)
        return _position_to_dict(pos)
    except Exception as e:
        # 404 = no position, not an error
        if "404" in str(e) or "position does not exist" in str(e).lower():
            return None
        logger.error(f"Failed to get position for {ticker}: {e}")
        return None


async def get_all_positions() -> list[dict]:
    """Get all open positions."""
    try:
        client = _get_trading_client()
        positions = client.get_all_positions()
        return [_position_to_dict(p) for p in positions]
    except Exception as e:
        logger.error(f"Failed to get all positions: {e}")
        return []


async def close_position(ticker: str, qty: float | None = None) -> dict | None:
    """Close a position (full or partial)."""
    try:
        client = _get_trading_client()
        if qty:
            order = client.close_position(ticker, close_options={"qty": str(qty)})
        else:
            order = client.close_position(ticker)
        logger.info(f"Position closed: {ticker} qty={qty or 'all'}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to close position for {ticker}: {e}")
        raise


# ── Market Data ──────────────────────────────────────────────────────────────


async def get_first_bar(ticker: str, trade_date: date) -> dict | None:
    """
    Get the first 1-minute bar for a ticker on a given date.
    Fetches the 9:30-9:35 window and returns the earliest bar available.
    Handles delayed opens and bars that aren't finalized at exactly 9:31.
    """
    try:
        from zoneinfo import ZoneInfo
        client = _get_data_client()
        et = ZoneInfo("America/New_York")
        start = datetime.combine(trade_date, datetime.min.time().replace(hour=9, minute=30), tzinfo=et)
        end = start + timedelta(minutes=5)
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
        )
        bars = client.get_stock_bars(request)
        bar_data = bars.data if hasattr(bars, 'data') else bars
        bar_set = bar_data.get(ticker, [])
        if not bar_set:
            logger.warning(f"No bars for {ticker} in 9:30-9:35 window on {trade_date}")
            return None
        b = bar_set[0]
        logger.info(f"ORB bar for {ticker}: {b.timestamp} O={b.open} H={b.high} L={b.low} C={b.close} V={b.volume}")
        return {
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
            "timestamp": b.timestamp.isoformat() if b.timestamp else None,
        }
    except Exception as e:
        logger.error(f"Failed to get first bar for {ticker} on {trade_date}: {e}")
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _order_to_dict(order) -> dict:
    """Convert Alpaca Order object to a plain dict."""
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": str(order.side),
        "type": str(order.type),
        "qty": float(order.qty) if order.qty else None,
        "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
        "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
        "stop_price": float(order.stop_price) if order.stop_price else None,
        "limit_price": float(order.limit_price) if order.limit_price else None,
        "status": str(order.status),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "legs": [_order_to_dict(leg) for leg in order.legs] if order.legs else [],
    }


def _position_to_dict(pos) -> dict:
    """Convert Alpaca Position object to a plain dict."""
    return {
        "symbol": pos.symbol,
        "qty": float(pos.qty),
        "avg_entry_price": float(pos.avg_entry_price),
        "market_value": float(pos.market_value),
        "cost_basis": float(pos.cost_basis),
        "unrealized_pl": float(pos.unrealized_pl),
        "unrealized_plpc": float(pos.unrealized_plpc),
        "current_price": float(pos.current_price),
        "side": str(pos.side),
    }
