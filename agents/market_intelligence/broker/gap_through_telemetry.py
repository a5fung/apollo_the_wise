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
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from agents.market_intelligence.collector import get_minute_bars, _ET
from agents.market_intelligence.db import log_audit_event

logger = logging.getLogger(__name__)

# Canonical ORB entry window (matches scripts/replay_would_have_filled.py #180).
# The intraday classifier keys off [proposed_at, cancelled_at]; the EOD
# reclassify uses this fixed window so the label is the real fill window, not
# whatever ad-hoc cancel time the order happened to carry.
_CANON_OPEN_HHMM = (9, 31)
_CANON_CUTOFF_HHMM = (10, 0)


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

    # Real-time silent-trigger / gap-through alert (2026-05-28, AVAV).
    # Operator-escalated P0: when the cancellation classifier finds the
    # price actually crossed the trigger (would_have_filled or gap_through),
    # that's a missed-fill signal that needs immediate operator visibility
    # — not a weekly-review artifact. AVAV was mis-labelled `clean_miss`
    # due to a separate bug; this alert path catches the genuine cases
    # going forward.
    if classification in ("would_have_filled", "gap_through"):
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            severity = (
                "🚨 SILENT TRIGGER FAILURE"
                if classification == "would_have_filled"
                else "⚠️ Gap-through"
            )
            reachable_line = (
                f"  • Min trade after trigger: ${min_trade_after_trigger:.2f}\n"
                if min_trade_after_trigger is not None else ""
            )
            await send_telegram_message(
                f"{severity} — *{ticker}* {alert_date}\n\n"
                f"  • Trigger: ${trigger_price:.2f}\n"
                f"  • Limit:   ${limit_price:.2f}\n"
                f"  • Max high in window: ${max_h_in_window:.2f}\n"
                f"  • First trigger hit: {trigger_first_t.strftime('%H:%M:%S') if trigger_first_t else '?'}\n"
                f"{reachable_line}"
                f"  • Window: {t0.strftime('%H:%M')}–{t1.strftime('%H:%M')} ET\n\n"
                f"_{'Order never triggered despite price crossing the limit-reachable zone — '  if classification == 'would_have_filled' else 'Trigger fired but price gapped past limit before fill — '}"
                f"investigate via Alpaca order history + SIP bar fetch.\n"
                f"Linked to data_gated_reviews.yaml::alpaca_stop_trigger_reliability (P0)._"
            )
        except Exception as e:
            logger.error(f"silent_trigger Telegram failed for {ticker}: {e}")


def _classify_canonical(
    bars_in_window: list[tuple[datetime, float, float]],
    trigger: float,
    limit: float,
) -> str:
    """Complete-bar classification over the canonical window — same rule as the
    intraday classifier + scripts/replay_would_have_filled.py (#180):
      trigger never hit -> clean_miss
      trigger hit, a later LOW <= limit -> would_have_filled
      trigger hit, price ran past limit (never returned) -> gap_through
    """
    # Sort by time — "first trigger-hit" and "bars at/after it" are order-
    # dependent, and get_minute_bars is not guaranteed chronological. Owning the
    # sort here keeps every caller correct (AVAV 5/28 misclassified gap_through
    # when the caller passed unsorted bars).
    ordered = sorted(bars_in_window)
    above = [(t, h, l) for t, h, l in ordered if h >= trigger]
    if not above:
        return "clean_miss"
    first_t = above[0][0]
    after = [(t, h, l) for t, h, l in ordered if t >= first_t]
    return "would_have_filled" if min(l for _, _, l in after) <= limit else "gap_through"


async def reclassify_orb_cancellations_eod(alert_date: date) -> dict:
    """#183 — EOD re-classification of the day's cancelled ORB entries on
    COMPLETE bars over the canonical [9:31, 10:00] window.

    The intraday `classify_orb_cancellation` fetches real-time Polygon bars at
    cancellation (~10:00 ET) which lag ~15 min → INCOMPLETE bars → false
    `clean_miss` (AVAV 2026-05-28: n_bars=14, max_high 203 vs true 207.20 @
    09:48). This pass re-runs after close on settled bars and writes an
    authoritative `orb_cancellation_reclassified` audit event per candidate,
    recording the prior intraday label so a correction is self-documenting.
    AUDIT-ONLY (no retroactive Telegram — #123 discipline); flips surface in the
    weekly review. Read + telemetry only — never mutates trade state.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, orb_high, entry_price
            FROM mi_live_trades
            WHERE status = 'cancelled' AND entry_order_id IS NOT NULL
              AND orb_high IS NOT NULL AND alert_date = $1
        """, alert_date)

    summary: Counter = Counter()
    flips: list[dict] = []
    for r in rows:
        ticker = r["ticker"]
        trigger = float(r["orb_high"] or r["entry_price"] or 0)
        limit = float(r["entry_price"] or r["orb_high"] or 0)
        if not trigger or not limit:
            continue
        d_str = alert_date.isoformat() if hasattr(alert_date, "isoformat") else str(alert_date)
        try:
            bars = await get_minute_bars(ticker, d_str, d_str)
        except Exception as e:
            logger.warning(f"reclassify: bar fetch failed for {ticker}: {e}")
            bars = None
        if not bars:
            cls = "data_unavailable"
        else:
            base = datetime.combine(alert_date, datetime.min.time(), tzinfo=_ET)
            open_t = base.replace(hour=_CANON_OPEN_HHMM[0], minute=_CANON_OPEN_HHMM[1])
            cutoff_t = base.replace(hour=_CANON_CUTOFF_HHMM[0], minute=_CANON_CUTOFF_HHMM[1])
            canon = [
                (datetime.fromtimestamp(b["t"] / 1000, tz=_ET), float(b["h"]), float(b["l"]))
                for b in bars
            ]
            canon = [(t, h, l) for t, h, l in canon if open_t <= t <= cutoff_t]
            # _classify_canonical sorts internally — window filter is order-free.
            cls = _classify_canonical(canon, trigger, limit) if canon else "data_unavailable"
        summary[cls] += 1

        # Best-effort: the prior intraday label for this trade, so the corrected
        # record names what it overrides (the AVAV-class flip).
        prior = None
        try:
            async with pool.acquire() as conn:
                prior = await conn.fetchval("""
                    SELECT details::jsonb->>'classification' FROM mi_audit_log
                    WHERE event_type = 'orb_cancellation_classification'
                      AND details::jsonb->>'trade_id' = $1
                    ORDER BY created_at DESC LIMIT 1
                """, str(r["id"]))
        except Exception:
            prior = None
        flipped = prior == "clean_miss" and cls in ("would_have_filled", "gap_through")
        if flipped:
            flips.append({"ticker": ticker, "trade_id": r["id"], "from": prior, "to": cls})

        await log_audit_event(
            "orb_cancellation_reclassified",
            f"{ticker} {alert_date}: {cls}"
            + (f" (was intraday {prior})" if prior and prior != cls else ""),
            json.dumps({
                "trade_id": r["id"], "ticker": ticker,
                "alert_date": str(alert_date),
                "classification": cls,
                "prior_intraday": prior,
                "flipped_from_clean_miss": flipped,
                "trigger_price": trigger, "limit_price": limit,
                "window": "canonical_0931_1000_complete_bars",
            }),
        )

    logger.info(
        f"reclassify_orb_cancellations_eod {alert_date}: "
        f"{dict(summary)}; {len(flips)} flip(s) from clean_miss"
    )
    return {"date": str(alert_date), "summary": dict(summary), "flips": flips}
