"""#488 SHADOW — authoritative trading-halt capture (Alpaca WS `statuses` channel).

Tracked as #488 (live-path project, split from #386 on close 2026-07-19 — #386's own scope
was the design audit; this module is the re-applied build, merged 2026-09-12 from branch
ba7533b onto main, ~1,500 commits later, unchanged in behavior).

WHY: the RMV dead-data guard (`flag_detector._RMV_DEAD_NTR_FLOOR`, halt-floor commit
20c9c06) INFERS "halted / frozen-feed / dead data" from zero-range daily bars. Alpaca's
market-data WebSocket carries the AUTHORITATIVE per-security trading-status feed — halt +
resume events with tape-dependent status/reason codes (T1/T2/T5/T12, LUDP, ...):
  · `StockDataStream.subscribe_trading_statuses(handler, *symbols)`
    (alpaca-py 0.43.2, alpaca/data/live/stock.py:117 — "Subscribe to trading statuses
    (halts, resumes)"; "*" wildcard supported)
  · delivering `alpaca.data.models.trades.TradingStatus`
    (alpaca/data/models/trades.py:82 — symbol, timestamp, status_code, status_message,
    reason_code, reason_message, tape).
Direct source beats inference — but the switch is a detection-criterion change (THE LINE):
this module only CAPTURES the authoritative flag into `mi_halt_status_events` (telemetry).
NOTHING on any detection/entry path reads it. The nightly `dead_data_guard_shadow` compare
logs it beside the inferred verdict; the operator judges the live switch on the measured
agreement (CHANGE_PROCESS + sign-off).

DEFAULT OFF — `HALT_STATUS_CAPTURE_ENABLED=false`. Two reasons, both live-path:
 1. ENTITLEMENT KILL RISK: on a channel the feed subscription doesn't include, the SDK
    TERMINATES the whole stream — `websocket.py::_run_forever` `return`s on the
    "insufficient subscription" ValueError (alpaca/data/live/websocket.py:352-356) — and
    that stream is the SHARED connection that fires real-money ORB entries (bar_stream.py;
    Alpaca allows ONE concurrent data-stream connection, so statuses MUST piggyback on it).
    Run `scripts/probe_alpaca_statuses.py` (off-prod, or with the market-agent stream down)
    to confirm the configured feed carries `statuses` BEFORE flipping the flag.
 2. LIFECYCLE CHANGE: a registered "*" statuses handler flips `_run_forever`'s
    wait-for-first-subscription idle (websocket.py:321-331) — the WS connects AT BOOT and
    stays up all day, instead of connecting at the first morning EP-candidate subscribe.
    Benign (arguably better — no first-subscribe connect latency), but it is a live-stream
    behavior change, so the operator flips it, never a default.

Registration is wired in `bar_stream.start_bar_stream` behind its own try/except: with the
flag off this module is a no-op import; a registration failure can never break the bar path.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def capture_enabled() -> bool:
    """Read the flag at call time (not import time) so tests / operator restarts see the
    current env. Default OFF — see module docstring for why."""
    return os.environ.get("HALT_STATUS_CAPTURE_ENABLED", "false").lower() == "true"


def maybe_register_status_capture(data_stream) -> bool:
    """Register the statuses handler on the SHARED bar stream. Called from
    `bar_stream.start_bar_stream` right after the StockDataStream is constructed (before
    the run task connects). Returns True iff the handler was registered.

    Registration is local until the WS connects (`_subscribe` only sends the subscribe
    message when `self._running` — websocket.py:277-280); on every (re)connect the SDK
    re-sends ALL registered handlers via `_send_subscribe_msg` (websocket.py:344), so the
    statuses subscription survives both SDK-level reconnects and bar_stream's outer retry
    loop without any bar_stream change.
    """
    if not capture_enabled():
        return False
    data_stream.subscribe_trading_statuses(_handle_trading_status, "*")
    logger.info("halt-status shadow: trading-statuses (*) capture registered (#488)")
    return True


async def _handle_trading_status(status) -> None:
    """Persist one TradingStatus event. SHADOW-ONLY writer: any failure is logged and
    swallowed — an event-write error must never propagate into the stream's dispatch loop
    (the same loop that delivers ORB bars)."""
    try:
        from agents.market_intelligence.db import insert_halt_status_event
        from agents.market_intelligence.execution_client import get_data_feed_name

        get = (lambda k: status.get(k)) if isinstance(status, dict) else (
            lambda k: getattr(status, k, None))
        symbol = get("symbol") or get("S")
        if not symbol:
            return
        await insert_halt_status_event(
            ticker=str(symbol),
            event_ts=get("timestamp") or get("t"),
            status_code=get("status_code") or get("sc"),
            status_message=get("status_message") or get("sm"),
            reason_code=get("reason_code") or get("rc"),
            reason_message=get("reason_message") or get("rm"),
            tape=get("tape") or get("z"),
            feed=get_data_feed_name(),
        )
    except Exception:
        logger.exception("halt-status shadow: event write failed (shadow-only, swallowed)")
