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

from agents.market_intelligence.broker.skip_reasons import (
    INFRA_SUBSCRIBE_FAILED,
    INFRA_SUBSCRIBE_TIMEOUT,
)

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
    from agents.market_intelligence.broker.alpaca_client import get_data_feed
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    feed = get_data_feed()
    _data_stream = StockDataStream(api_key, secret_key, feed=feed)

    _stream_task = asyncio.create_task(_run_stream())
    mode = "PAPER" if paper else "LIVE"
    logger.info(f"Bar stream started ({mode}, feed={feed.value})")


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
            if retries > 0 and _subscribed:
                # Re-register handlers after reconnect — server-side subscriptions are
                # lost on disconnect. The SDK may re-send them, but we call explicitly
                # to be safe. Idempotent: re-registering same handler is fine.
                logger.info(f"Bar stream reconnect: re-subscribing {len(_subscribed)} tickers: {sorted(_subscribed)}")
                for ticker in list(_subscribed):
                    try:
                        _data_stream.subscribe_bars(_handle_bar, ticker)
                    except Exception as sub_e:
                        logger.warning(f"Bar stream: re-subscribe {ticker} failed: {sub_e}")
            logger.info("Bar stream connecting...")
            await _data_stream._run_forever()
        except asyncio.CancelledError:
            _stream_healthy = False
            return
        except Exception as e:
            _stream_healthy = False
            retries += 1
            logger.error(f"Bar stream died: {e} (retry {retries}/{MAX_RETRIES})")
            if _subscribed:
                logger.warning(f"Bar stream died with active subscriptions: {sorted(_subscribed)}")
            # Retries 1 and 2: audit-log only. WebSocket micro-drops at 9:30 AM are
            # normal data-feed behaviour; alerting the user on self-healing retries
            # creates alert fatigue. Telegram only fires on terminal 3rd-retry.
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "bar_stream_disconnect",
                    f"retry {retries}/{MAX_RETRIES} — {e} | subscribed={sorted(_subscribed)}",
                )
            except Exception:
                pass
            if retries < MAX_RETRIES:
                await asyncio.sleep(min(5 * retries, 30))

    from agents.market_intelligence.briefing import send_telegram_message
    from agents.market_intelligence.constants import mode_prefix
    await send_telegram_message(
        f"{mode_prefix()}⚠️ *Bar stream failed {MAX_RETRIES} times* — ORB entry falling back to 9:31 cron"
    )


# ── Subscription management ──────────────────────────────────────────────────


async def subscribe_ep_candidate(ticker: str) -> None:
    """Subscribe to minute bars for a pre-market HIGH EP candidate.
    Called from _ep_scan_job() when a new HIGH is detected pre-market.

    The Alpaca SDK's subscribe_bars is synchronous and can block on the
    websocket's internal lock when called from the same asyncio thread that
    is running the stream. On 2026-04-22 this deadlocked the event loop for
    ~3 hours. Offload to a worker thread with a hard timeout.
    """
    if not _data_stream or ticker in _subscribed or ticker in _processed_today:
        return
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_data_stream.subscribe_bars, _handle_bar, ticker),
            timeout=5,
        )
        _subscribed.add(ticker)
        logger.info(f"Bar stream: subscribed to {ticker} for ORB entry")
    except asyncio.TimeoutError:
        logger.error(f"Bar stream: subscribe to {ticker} timed out after 5s — SDK lock stuck")
        await _record_subscribe_failure(
            ticker, f"{INFRA_SUBSCRIBE_TIMEOUT}: 5s SDK lock stuck",
        )
    except Exception as e:
        logger.error(f"Bar stream: failed to subscribe to {ticker}: {e}")
        await _record_subscribe_failure(
            ticker, f"{INFRA_SUBSCRIBE_FAILED}: {e}",
        )


async def _record_subscribe_failure(ticker: str, reason: str) -> None:
    """Telegram + audit-log a subscribe failure. Do NOT write mi_live_trades here.

    The 9:31 cron fallback (process_new_alerts_live) is an independent REST-based
    recovery path — writing a skipped row from the WebSocket side would dedup-
    block it via live_tracker.py's EXISTS check. The cron owns the terminal
    mi_live_trades state (via INFRA_NO_BAR or a successful entry); /why can still
    surface this subscribe-failure via the audit log entry below.
    """
    try:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event("orb_subscribe_failed", f"{ticker} — {reason}")
    except Exception:
        pass
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        from agents.market_intelligence.broker.skip_reasons import humanize
        from agents.market_intelligence.constants import mode_prefix
        await send_telegram_message(
            f"{mode_prefix()}⚠️ *{ticker}* — {humanize(reason)}. 9:31 cron fallback will run."
        )
    except Exception:
        # Audit row above is already written; log the alert-channel failure
        # so it's at least visible in container output rather than silent.
        logger.exception(
            f"Bar stream subscribe-failure Telegram alert ALSO failed for {ticker} — "
            f"audit event 'orb_subscribe_failed' is the durable record."
        )


async def unsubscribe_all() -> None:
    """Unsubscribe all tickers after ORB window closes (called at 9:35 AM).

    Offloaded to a worker thread for the same deadlock-avoidance reason as
    subscribe_ep_candidate.
    """
    global _subscribed
    if not _data_stream or not _subscribed:
        return
    tickers = tuple(_subscribed)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_data_stream.unsubscribe_bars, *tickers),
            timeout=5,
        )
        logger.info(f"Bar stream: unsubscribed {len(tickers)} tickers after ORB window")
    except asyncio.TimeoutError:
        logger.error(f"Bar stream: unsubscribe timed out after 5s — SDK lock stuck")
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
        f"V={bar.volume:,} — triggering ORB entry "
        f"[stream healthy={_stream_healthy}, subscribed={sorted(_subscribed)}]"
    )

    try:
        from agents.market_intelligence.broker.entry_pipeline import (
            ACTION_AUTO_ENTERED, ACTION_PROPOSED,
        )
        from agents.market_intelligence.broker.live_tracker import process_new_alerts_live
        results = await process_new_alerts_live(trigger="bar_stream")
        entered = [r["ticker"] for r in results if r.get("action") in (ACTION_AUTO_ENTERED, ACTION_PROPOSED)]
        if entered:
            logger.info(f"Bar stream ORB entry: {entered}")
        else:
            logger.info(f"Bar stream ORB: {ticker} processed, no entry (filtered/blocked/exists)")
    except Exception as e:
        logger.error(f"Bar stream: ORB entry failed for {ticker}: {e}", exc_info=True)
