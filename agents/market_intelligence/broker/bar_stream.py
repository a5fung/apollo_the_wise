"""
Real-time minute bar WebSocket for ORB entry.

Subscribes to Alpaca's StockDataStream for EP candidate tickers.
When the first 1-min bar closes at 9:31 AM ET, the bar event triggers
immediate ORB order placement — no cron polling lag.

Flow:
  EP scan detects HIGH pre-market
    → subscribe_ep_candidate(ticker)
  9:31 AM: Alpaca pushes first bar event
    → _handle_bar() → process_new_alerts_live(ticker)
  9:35 AM: unsubscribe_all() clears the subscription set

For at-open upgrades (detected by the 9:31 EP scan after bar already closed):
  _ep_scan_job() calls process_new_alerts_live() inline — bar data already in DB.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time

logger = logging.getLogger(__name__)

# ── Module state ────────────────────────────────────────────────────────────

_data_stream = None
_stream_task: asyncio.Task | None = None
_stream_healthy: bool = False
_subscribed: set[str] = set()          # tickers awaiting first bar
_processed_today: set[str] = set()     # tickers already entered today (dedup)


# ── Lifecycle ────────────────────────────────────────────────────────────────


async def start_bar_stream() -> None:
    """Start the data WebSocket. Called from agent.py startup."""
    global _data_stream, _stream_task, _stream_healthy

    from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
    if not LIVE_TRADING_ENABLED:
        logger.info("Live trading disabled — bar stream not started")
        return

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        logger.warning("Alpaca credentials not set — bar stream not started")
        return

    from alpaca.data.live import StockDataStream
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    _data_stream = StockDataStream(api_key, secret_key, feed="iex")

    _stream_task = asyncio.create_task(_run_stream())
    mode = "PAPER" if paper else "LIVE"
    logger.info(f"Bar stream started ({mode})")


async def stop_bar_stream() -> None:
    """Stop the data WebSocket. Called from agent.py shutdown."""
    global _stream_task, _data_stream, _stream_healthy
    if _stream_task and not _stream_task.done():
        _stream_task.cancel()
        try:
            await _stream_task
        except asyncio.CancelledError:
            pass
    _stream_healthy = False
    logger.info("Bar stream stopped")


async def _run_stream() -> None:
    global _stream_healthy
    MAX_RETRIES = 3
    retries = 0
    while retries < MAX_RETRIES:
        try:
            _stream_healthy = True
            logger.info("Bar stream connecting...")
            await _data_stream._run_forever()
        except asyncio.CancelledError:
            _stream_healthy = False
            return
        except Exception as e:
            _stream_healthy = False
            retries += 1
            logger.error(f"Bar stream died: {e} (retry {retries}/{MAX_RETRIES})")
            if retries < MAX_RETRIES:
                await asyncio.sleep(min(5 * retries, 30))

    from agents.market_intelligence.briefing import send_telegram_message
    await send_telegram_message(
        f"⚠️ *Bar stream failed {MAX_RETRIES} times* — ORB entry falling back to 9:31 cron"
    )


# ── Subscription management ──────────────────────────────────────────────────


def subscribe_ep_candidate(ticker: str) -> None:
    """Subscribe to minute bars for a pre-market HIGH EP candidate.
    Called from _ep_scan_job() when a new HIGH is detected pre-market."""
    if not _data_stream or ticker in _subscribed or ticker in _processed_today:
        return
    try:
        _data_stream.subscribe_bars(_handle_bar, ticker)
        _subscribed.add(ticker)
        logger.info(f"Bar stream: subscribed to {ticker} for ORB entry")
    except Exception as e:
        logger.error(f"Bar stream: failed to subscribe to {ticker}: {e}")


def unsubscribe_all() -> None:
    """Unsubscribe all tickers after ORB window closes (called at 9:35 AM)."""
    global _subscribed
    if not _data_stream or not _subscribed:
        return
    try:
        _data_stream.unsubscribe_bars(*_subscribed)
        logger.info(f"Bar stream: unsubscribed {len(_subscribed)} tickers after ORB window")
    except Exception as e:
        logger.error(f"Bar stream: unsubscribe failed: {e}")
    _subscribed.clear()


def reset_daily_state() -> None:
    """Clear processed set at start of day. Called from scheduler at 7 AM."""
    _processed_today.clear()
    _subscribed.clear()
    logger.info("Bar stream: daily state reset")


def get_status() -> dict:
    return {
        "healthy": _stream_healthy,
        "subscribed": sorted(_subscribed),
        "processed_today": sorted(_processed_today),
    }


# ── Bar handler ──────────────────────────────────────────────────────────────


async def _handle_bar(bar) -> None:
    """Called by Alpaca SDK when a subscribed ticker's minute bar closes."""
    from agents.market_intelligence.collector import _ET

    ticker = bar.symbol
    bar_time = bar.timestamp  # UTC datetime

    # Only act on the first bar of the session (9:30–9:31 ET)
    bar_time_et = bar_time.astimezone(_ET)
    if not (bar_time_et.hour == 9 and bar_time_et.minute == 30):
        logger.debug(f"Bar stream: ignoring non-open bar for {ticker} at {bar_time_et.strftime('%H:%M')}")
        return

    if ticker in _processed_today:
        logger.debug(f"Bar stream: {ticker} already processed today")
        return

    _processed_today.add(ticker)
    _subscribed.discard(ticker)

    logger.info(
        f"Bar stream: first bar received for {ticker} "
        f"O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} "
        f"V={bar.volume:,} — triggering ORB entry"
    )

    try:
        from agents.market_intelligence.broker.live_tracker import process_new_alerts_live
        results = await process_new_alerts_live()
        entered = [r["ticker"] for r in results if r.get("action") in ("auto_entered", "proposed")]
        if entered:
            logger.info(f"Bar stream ORB entry: {entered}")
        else:
            logger.info(f"Bar stream ORB: {ticker} processed, no entry (filtered/blocked/exists)")
    except Exception as e:
        logger.error(f"Bar stream: ORB entry failed for {ticker}: {e}", exc_info=True)
