"""Gap-through telemetry for ORB-window-cancelled entries (FLEX 5/06 class).

Records whether each unfilled cancellation was:
- `clean_miss`: trigger price never hit; order correctly didn't fire
- `gap_through`: trigger hit + price ran past limit too fast for fill
- `would_have_filled`: trigger hit + limit reachable after; simulator/broker miss
- `data_unavailable`: Polygon bars couldn't be fetched

Goal: enable analysis of gap-through frequency vs protection-save frequency
(task #22), with optional pm_rvol stratification. Decision question for a
future buffer-widening change: does gap-through correlate with high pm_rvol?

Fire-and-forget from `cancel_unfilled_entries`. Failures don't block the
cancellation flow.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from agents.market_intelligence.collector import get_minute_bars, _ET
from agents.market_intelligence.db import log_audit_event

logger = logging.getLogger(__name__)


async def classify_orb_cancellation(
    trade_id: int,
    ticker: str,
    alert_date: date,
    proposed_at: datetime,
    trigger_price: float,
    limit_price: float,
    cancelled_at: datetime,
    pm_rvol: Optional[float] = None,
) -> None:
    """Classify a cancelled ORB entry by post-placement price action.

    Emits a single `orb_cancellation_classification` audit event with the
    classification + key prices + optional pm_rvol band. Idempotent caller
    should ensure one call per (trade_id).
    """
    try:
        # Pull the minute bars from order placement through cancellation.
        # alert_date.isoformat() is the date string Polygon expects.
        d_str = alert_date.isoformat() if hasattr(alert_date, "isoformat") else str(alert_date)
        bars = await get_minute_bars(ticker, d_str, d_str)
    except Exception as e:
        logger.warning(f"gap_through_telemetry: bar fetch failed for {ticker}: {e}")
        await log_audit_event(
            "orb_cancellation_classification",
            f"{ticker} {alert_date}: data_unavailable (bar fetch failed)",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "alert_date": str(alert_date),
                "classification": "data_unavailable",
                "trigger_price": trigger_price,
                "limit_price": limit_price,
                "pm_rvol": pm_rvol,
                "error": str(e)[:200],
            }),
        )
        return

    t0 = proposed_at.astimezone(_ET) if proposed_at.tzinfo else proposed_at
    t1 = cancelled_at.astimezone(_ET) if cancelled_at.tzinfo else cancelled_at

    in_window: list[tuple[datetime, float, float]] = []
    for b in bars:
        bar_t = datetime.fromtimestamp(b["t"] / 1000, tz=_ET)
        if t0 <= bar_t <= t1:
            in_window.append((bar_t, float(b["h"]), float(b["l"])))

    if not in_window:
        await log_audit_event(
            "orb_cancellation_classification",
            f"{ticker} {alert_date}: data_unavailable (no bars in window {t0.strftime('%H:%M')}-{t1.strftime('%H:%M')})",
            json.dumps({
                "trade_id": trade_id, "ticker": ticker,
                "alert_date": str(alert_date),
                "classification": "data_unavailable",
                "trigger_price": trigger_price,
                "limit_price": limit_price,
                "pm_rvol": pm_rvol,
            }),
        )
        return

    max_h_in_window = max(h for _, h, _ in in_window)
    bars_at_or_above_trigger = [(t, h, l) for t, h, l in in_window if h >= trigger_price]

    if not bars_at_or_above_trigger:
        # Price never reached trigger → order correctly didn't fire. Clean miss.
        classification = "clean_miss"
        trigger_first_t = None
        min_trade_after_trigger = None
    else:
        trigger_first_t = bars_at_or_above_trigger[0][0]
        # After the trigger fires, did any bar's LOW (= a trade print) come
        # back ≤ limit_price? If yes → "would_have_filled" — but with a
        # caveat: bar low is a TRADE PRINT, not a guarantee an ASK was
        # offered at limit_price (a wide-spread name can print a low at
        # limit while the offer side stayed higher). For coarse
        # gap_through vs not-gap_through classification this is fine, but
        # the audit-event field is named `min_trade_after_trigger` to
        # avoid implying matching-engine guarantees.
        bars_after_trigger = [b for b in in_window if b[0] >= trigger_first_t]
        min_trade_after_trigger = min(l for _, _, l in bars_after_trigger)
        if min_trade_after_trigger <= limit_price:
            classification = "would_have_filled"
        else:
            classification = "gap_through"

    await log_audit_event(
        "orb_cancellation_classification",
        f"{ticker} {alert_date}: {classification} "
        f"(trigger=${trigger_price:.2f} limit=${limit_price:.2f} "
        f"max_h=${max_h_in_window:.2f})",
        json.dumps({
            "trade_id": trade_id, "ticker": ticker,
            "alert_date": str(alert_date),
            "classification": classification,
            "trigger_price": trigger_price,
            "limit_price": limit_price,
            "max_high_in_window": max_h_in_window,
            "min_trade_after_trigger": min_trade_after_trigger,
            "trigger_first_hit_et": trigger_first_t.strftime("%H:%M:%S") if trigger_first_t else None,
            "window_start_et": t0.strftime("%H:%M:%S"),
            "window_end_et": t1.strftime("%H:%M:%S"),
            "n_bars_in_window": len(in_window),
            "pm_rvol": pm_rvol,
        }),
    )
