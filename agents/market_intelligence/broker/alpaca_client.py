"""
Thin async wrapper around alpaca-py SDK for live EP trading.

Dual-account architecture (#66, 2026-05-10): per-mode TradingClient
singletons keyed by account_mode ∈ {'paper','live'}. Credentials resolved
from ALPACA_{PAPER,LIVE}_API_KEY / _SECRET_KEY env vars (legacy
ALPACA_API_KEY/SECRET_KEY remapped to paper at boot — see agent.py
_bootstrap_alpaca_credentials).

Wrapper functions accept an optional `account_mode` param. When None,
falls back to constants.current_account_mode() for backward compat
during the migration window (Step 3 → Step 6 of plan). After all callers
are migrated to pass explicit mode, the None default will be removed.

Market data client (`_data_client`) stays singleton — market data is
account-agnostic. Authenticates with paper credentials (cheaper +
always present per boot bootstrap).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopLossRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderClass, OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

logger = logging.getLogger(__name__)

# ── Data feed selection ──────────────────────────────────────────────────────
# Gated on ALPACA_DATA_FEED env var so the SIP cutover is a single env flip
# (plus Alpaca dashboard subscription), not a code deploy. See
# `Changes Made 2026-04-23` in CLAUDE.md for the full rollout rationale.
#
#   unset / "iex"  → DataFeed.IEX  (default; free; single exchange, ~2-3% volume)
#   "sip"          → DataFeed.SIP  (requires Algo Trader Plus $99/mo subscription)


def get_data_feed() -> DataFeed:
    raw = os.environ.get("ALPACA_DATA_FEED", "iex").strip().lower()
    if raw == "sip":
        return DataFeed.SIP
    if raw and raw != "iex":
        logger.warning(f"ALPACA_DATA_FEED={raw!r} not recognized; falling back to IEX")
    return DataFeed.IEX


def extract_stop_leg_id(order) -> str | None:
    """Return the stop-loss leg's order ID from a bracket/OTO parent order.

    Works with alpaca-py Order objects (WS events, live API returns) and
    dicts produced by _order_to_dict. Uses `stop_price` as primary signal
    and falls back to case-insensitive type substring — Python 3.11+
    changed `str(Enum)` to "ClassName.MEMBER", which broke the older
    `== "stop"` equality check and left submit-time IDs uncaptured.
    """
    if order is None:
        return None

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for leg in (_get(order, "legs") or []):
        has_stop_price = bool(_get(leg, "stop_price"))
        type_str = str(_get(leg, "type", "") or "").lower()
        if has_stop_price or "stop" in type_str:
            lid = _get(leg, "id")
            if lid:
                return str(lid)
    return None


# ── Per-mode singleton clients (#66 dual-account) ────────────────────────────

_TRADING_CLIENTS: dict[str, TradingClient] = {}
_data_client: StockHistoricalDataClient | None = None


def _resolve_account_mode(account_mode: str | None) -> str:
    """Resolve account_mode argument; fall back to legacy global env var.

    During the Step 3 → Step 6 migration window, callers may pass None and
    rely on the legacy current_account_mode() resolver. After all ~25 call
    sites are updated to pass explicit mode (Step 6), the None branch will
    be removed and this helper deleted.
    """
    if account_mode is not None:
        return account_mode
    from agents.market_intelligence.constants import current_account_mode
    return current_account_mode()


def get_trading_client(account_mode: str | None = None) -> TradingClient:
    """Return the per-mode TradingClient singleton.

    Each (paper, live) mode gets its own TradingClient instance with its
    own underlying HTTP session — alpaca-py's default behavior, no shared
    pool. This isolates concurrent submissions: 5 paper + 2 live orders at
    9:31 ET don't contend on a single connection pool.

    Credentials sourced from ALPACA_{PAPER,LIVE}_API_KEY / _SECRET_KEY.
    The boot bootstrap (agent._bootstrap_alpaca_credentials) guarantees
    these are set OR remaps legacy ALPACA_API_KEY → ALPACA_PAPER_*.
    """
    mode = _resolve_account_mode(account_mode)
    if mode not in _TRADING_CLIENTS:
        env_prefix = f"ALPACA_{mode.upper()}_"
        api_key = os.environ[f"{env_prefix}API_KEY"]
        secret_key = os.environ[f"{env_prefix}SECRET_KEY"]
        # paper= flag tells alpaca-py which API URL family to use:
        #   True  → paper-api.alpaca.markets
        #   False → api.alpaca.markets
        _TRADING_CLIENTS[mode] = TradingClient(
            api_key, secret_key, paper=(mode == "paper")
        )
        logger.info(f"Alpaca TradingClient initialized for mode={mode}")
    return _TRADING_CLIENTS[mode]


# Legacy alias — preserved so any in-flight code still works during migration.
# All wrappers below have been updated to accept account_mode explicitly,
# but a few external callers may still import _get_trading_client directly.
def _get_trading_client(account_mode: str | None = None) -> TradingClient:
    """LEGACY alias for get_trading_client. Prefer the public name."""
    return get_trading_client(account_mode)


def _get_data_client() -> StockHistoricalDataClient:
    """Market data client — account-agnostic singleton.

    Authenticates with paper credentials (always present per boot
    bootstrap, no live-account billing implication for market data).
    """
    global _data_client
    if _data_client is None:
        api_key = os.environ["ALPACA_PAPER_API_KEY"]
        secret_key = os.environ["ALPACA_PAPER_SECRET_KEY"]
        _data_client = StockHistoricalDataClient(api_key, secret_key)
        logger.info("Alpaca StockHistoricalDataClient initialized")
    return _data_client


# ── Mode-bound client_order_id (collision prevention) ────────────────────────


def make_client_order_id(account_mode: str, strategy_id: str, ticker: str) -> str:
    """Generate a strict mode-bound client_order_id.

    Format: ``apollo_{mode}_{strategy}_{ticker}_{ms_epoch}``

    Example: ``apollo_live_magna53_AAPL_1715450123456``

    Critical correctness invariant (reviewer 2026-05-10): if two strategies
    (one paper, one live) submit the same setup concurrently and
    `client_order_id` is generated deterministically from strategy data alone,
    the same string lands in BOTH Alpaca accounts. Subsequent WebSocket
    execution-report lookups by `order_id` could return the wrong row or
    raise `MultipleResultsFound`, dropping a real fill.

    Mode prefix is non-optional. Use this helper at every order submission
    site to prevent ad-hoc generation drift.
    """
    return f"apollo_{account_mode}_{strategy_id}_{ticker}_{int(time.time() * 1000)}"


async def verify_dual_account_clients() -> dict:
    """Boot-time smoke test: instantiate both clients, verify get_account works.

    Returns ``{'paper': {'equity': ..., 'ok': True}, 'live': {...}}``. Caller
    (agent.py startup) audits the result and emits dual_account_boot_verified
    on success or dual_account_boot_failed with details on partial/failed init.
    Idempotent; safe to call repeatedly.
    """
    from agents.market_intelligence.constants import ENABLE_LIVE_MODE
    result: dict = {}
    modes = ["paper", "live"] if ENABLE_LIVE_MODE else ["paper"]
    for mode in modes:
        try:
            client = get_trading_client(mode)
            account = client.get_account()
            result[mode] = {
                "ok": True,
                "equity": float(account.equity),
                "trading_blocked": account.trading_blocked,
            }
        except Exception as e:
            result[mode] = {"ok": False, "error": str(e)}
            logger.error(f"Dual-account boot verify FAILED for mode={mode}: {e}")
    return result


# ── Account ──────────────────────────────────────────────────────────────────


async def get_account(account_mode: str | None = None) -> dict:
    """Get account info (equity, buying power, etc.).

    account_mode: 'paper' | 'live'. None falls back to current_account_mode()
    for legacy callers (Step 6 of #66 plan migrates them to explicit).
    """
    try:
        client = get_trading_client(account_mode)
        account = client.get_account()
        return {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "account_blocked": account.account_blocked,
            # daytrade_count: rolling 5-business-day count. PDT lockout fires at
            # 4 day-trades when equity < $25K. Surfaced for /status PDT headroom.
            "daytrade_count": int(getattr(account, "daytrade_count", 0) or 0),
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
    account_mode: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """
    Place a bracket order: stop-limit buy entry with attached stop-loss.
    - Entry: stop-limit buy triggers at stop_price, fills up to limit_price
    - Stop-loss: hard stop at stop_loss_price

    account_mode: 'paper' | 'live'. Routes to the per-mode TradingClient
    singleton. None falls back to current_account_mode() (legacy).

    client_order_id: pre-generated mode-bound ID via make_client_order_id.
    Highly recommended in dual-mode to prevent cross-account collisions.
    """
    try:
        client = get_trading_client(account_mode)
        req_kwargs = dict(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.STOP_LIMIT,
            time_in_force=TimeInForce.DAY,
            stop_price=round(stop_price, 2),
            limit_price=round(limit_price, 2),
            order_class=OrderClass.OTO,
            stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2)),
        )
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id
        order = client.submit_order(StopLimitOrderRequest(**req_kwargs))
        # Safety: Alpaca must accept the stop_loss leg, otherwise the position is
        # unprotected on fill. alpaca-py silently drops invalid fields; verify legs
        # came back before we trust this order.
        legs = getattr(order, "legs", None) or []
        if not extract_stop_leg_id(order):
            # Abort: cancel the entry order so we don't fill naked, then raise so
            # the caller's retry fires (or the trade fails cleanly).
            try:
                client.cancel_order_by_id(order.id)
            except Exception as cancel_err:
                logger.error(f"Failed to cancel naked bracket {ticker} {order.id}: {cancel_err}")
            raise RuntimeError(
                f"Bracket order {order.id} for {ticker} returned no stop_loss leg — "
                f"Alpaca rejected the stop. Entry cancelled."
            )
        logger.info(
            f"Bracket order placed: {ticker} qty={qty} "
            f"stop={stop_price:.2f} limit={limit_price:.2f} SL={stop_loss_price:.2f} "
            f"order_id={order.id} legs={len(legs)}"
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
    account_mode: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """Place a stop order (for Day 2+ stop updates)."""
    try:
        client = get_trading_client(account_mode)
        req_kwargs = dict(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL if side == "sell" else OrderSide.BUY,
            type=OrderType.STOP,
            time_in_force=TimeInForce.GTC,
            stop_price=round(stop_price, 2),
        )
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id
        order = client.submit_order(StopOrderRequest(**req_kwargs))
        logger.info(f"Stop order placed: {ticker} qty={qty} stop={stop_price:.2f} id={order.id}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place stop order for {ticker}: {e}")
        raise


async def place_market_on_open_sell(
    ticker: str,
    qty: float,
    account_mode: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """Place a market-on-open sell (TimeInForce.OPG) — fills at the NEXT
    opening auction. Used by the time-stop path (#91, 2026-05-23): an
    EOD-flagged 9M Day 2 meanderer is exited at the next regular-session
    open, freeing the slot for fresh entries.

    Submission window per Alpaca: OPG orders must be submitted between
    7:00 PM ET prior day and 9:25 AM ET next day. Intraday submissions
    are rejected. Caller must surface that error to the operator.

    Across long weekends / holidays, OPG queues for the next ACTUAL
    trading session — so Friday-evening submit on a 3-day weekend (e.g.
    Memorial Day Monday closed) correctly fills at Tuesday's open.
    """
    try:
        client = get_trading_client(account_mode)
        req_kwargs = dict(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.OPG,
        )
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id
        order = client.submit_order(MarketOrderRequest(**req_kwargs))
        logger.info(f"Market-on-open sell placed: {ticker} qty={qty} id={order.id}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place market-on-open sell for {ticker}: {e}")
        raise


async def place_market_sell(
    ticker: str,
    qty: float,
    account_mode: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """Place a market sell order (for partials or full exits)."""
    try:
        client = get_trading_client(account_mode)
        req_kwargs = dict(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id
        order = client.submit_order(MarketOrderRequest(**req_kwargs))
        logger.info(f"Market sell placed: {ticker} qty={qty} id={order.id}")
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to place market sell for {ticker}: {e}")
        raise


async def cancel_order(order_id: str, account_mode: str | None = None) -> bool:
    """Cancel an order by ID. Returns True if successful."""
    try:
        client = get_trading_client(account_mode)
        client.cancel_order_by_id(order_id)
        logger.info(f"Order cancelled: {order_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        return False


async def get_order(order_id: str, account_mode: str | None = None) -> dict | None:
    """Get order details by ID."""
    try:
        client = get_trading_client(account_mode)
        order = client.get_order_by_id(order_id)
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        return None


async def get_open_orders(
    ticker: str | None = None,
    account_mode: str | None = None,
) -> list[dict]:
    """Get all open orders, optionally filtered by ticker."""
    try:
        client = get_trading_client(account_mode)
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        if ticker:
            request.symbols = [ticker]
        orders = client.get_orders(request)
        return [_order_to_dict(o) for o in orders]
    except Exception as e:
        logger.error(f"Failed to get open orders: {e}")
        return []


# ── Positions ────────────────────────────────────────────────────────────────


async def get_position(ticker: str, account_mode: str | None = None) -> dict | None:
    """Get position for a specific ticker."""
    try:
        client = get_trading_client(account_mode)
        pos = client.get_open_position(ticker)
        return _position_to_dict(pos)
    except Exception as e:
        # 404 = no position, not an error
        if "404" in str(e) or "position does not exist" in str(e).lower():
            return None
        logger.error(f"Failed to get position for {ticker}: {e}")
        return None


async def get_all_positions(account_mode: str | None = None) -> list[dict]:
    """Get all open positions."""
    try:
        client = get_trading_client(account_mode)
        positions = client.get_all_positions()
        return [_position_to_dict(p) for p in positions]
    except Exception as e:
        logger.error(f"Failed to get all positions: {e}")
        return []


async def close_position(
    ticker: str,
    qty: float | None = None,
    account_mode: str | None = None,
) -> dict | None:
    """Close a position (full or partial)."""
    try:
        client = get_trading_client(account_mode)
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
            feed=get_data_feed(),
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


async def get_minute_bars_window(
    ticker: str, trade_date: date, start_minute: int, end_minute: int,
) -> list[dict]:
    """Fetch 1-minute bars between [start_minute, end_minute) from market open.

    start_minute/end_minute are minutes from 9:30 ET (so 0..30 = 9:30–10:00).
    Used by shadow_orb_tracker to compute the 5-min ORB and scan for trigger
    in the 9:35–10:00 window.
    """
    try:
        from zoneinfo import ZoneInfo
        client = _get_data_client()
        et = ZoneInfo("America/New_York")
        open_dt = datetime.combine(
            trade_date, datetime.min.time().replace(hour=9, minute=30), tzinfo=et,
        )
        start = open_dt + timedelta(minutes=start_minute)
        end = open_dt + timedelta(minutes=end_minute)
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=get_data_feed(),
        )
        bars = client.get_stock_bars(request)
        bar_data = bars.data if hasattr(bars, 'data') else bars
        bar_set = bar_data.get(ticker, []) or []
        return [
            {
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume),
                "timestamp": b.timestamp.astimezone(et) if b.timestamp else None,
            }
            for b in bar_set
        ]
    except Exception as e:
        logger.error(
            f"Failed to get minute-bar window for {ticker} on {trade_date} "
            f"[{start_minute}..{end_minute}): {e}"
        )
        return []


# ── Price Data ──────────────────────────────────────────────────────────────


async def get_latest_trade(ticker: str) -> dict | None:
    """Fetch the latest trade price for a ticker. Used for price-aware re-entry."""
    try:
        from alpaca.data.requests import StockLatestTradeRequest
        client = _get_data_client()
        result = client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=ticker)
        )
        t = result.get(ticker)
        if t:
            return {"price": float(t.price), "timestamp": t.timestamp.isoformat()}
        return None
    except Exception as e:
        logger.error(f"Failed to get latest trade for {ticker}: {e}")
        return None


# ── Limit Buy (for re-entry when price > ORB high) ─────────────────────────


async def place_limit_buy_with_stop(
    ticker: str,
    qty: float,
    limit_price: float,
    stop_loss_price: float,
    account_mode: str | None = None,
    client_order_id: str | None = None,
) -> dict:
    """
    Place a limit buy with attached stop-loss.
    Used for re-entry when price has already passed ORB high (stop-limit would never trigger).
    """
    try:
        client = get_trading_client(account_mode)
        req_kwargs = dict(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
            stop_loss={"stop_price": round(stop_loss_price, 2)},
        )
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id
        order = client.submit_order(LimitOrderRequest(**req_kwargs))
        logger.info(
            f"Limit buy placed: {ticker} qty={qty} "
            f"limit={limit_price:.2f} SL={stop_loss_price:.2f} "
            f"order_id={order.id}"
        )
        return _order_to_dict(order)
    except Exception as e:
        logger.error(f"Limit buy failed for {ticker}: {e}")
        raise


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
