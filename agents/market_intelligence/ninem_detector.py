"""
9M EP (9 Million Episodic Pivot) Detection System.

Parallel EP track — completely separate from the MAGNA53 (ep_detector.py) system.
No LLM calls. Detection is purely quantitative: institutional volume footprint.

Two functions drive the pipeline:
  run_9m_scan()      — called every 5 min, 9:30 AM – 4:00 PM ET
  run_9m_eod_sweep() — called once after 5 PM nightly data pull

Sugar Babies (stocks completing a 9M day with a strong close) are stored in
mi_9m_sugar_babies and surfaced in the evening briefing as Day 2 ORB candidates.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.collector import get_snapshot_all
from agents.market_intelligence.db import (
    get_eod_9m_sugar_babies,
    get_today_9m_ep_alerts,  # noqa: F401 — re-exported for agent.py convenience
    insert_9m_ep_alert,
    insert_9m_sugar_baby,
)

logger = logging.getLogger(__name__)

_SESSION_MINUTES = 390
_9M_ACTUAL_THRESHOLD = 8_900_000       # shares — fire "actual" alert
_9M_PROJECTED_THRESHOLD = 12_000_000   # projected shares — fire "anticipation" alert
_MIN_PRICE = 3.00                       # skip sub-$3 tickers
_PROJECTION_MIN_MINUTES = 15            # don't project volume before 9:45 AM

# In-memory dedup: prevents duplicate Telegram alerts within the same calendar day.
# A process restart clears this; the DB UNIQUE constraint on (ticker, alert_date)
# ensures insert_9m_ep_alert() returns False for duplicates so no repeat is sent.
_alerted_today: set[str] = set()
_alerted_date: str = ""

_ET = ZoneInfo("America/New_York")


async def run_9m_scan() -> list[dict]:
    """
    Intraday scan for stocks crossing the 9M volume threshold.
    Called every 5 minutes, 9:30 AM – 4:00 PM ET.

    Detection rules:
    - actual volume >= 8.9M shares (immediate threshold), OR
    - projected volume >= 12M shares (pace-based, only after 15 min since open)
    - price >= $3.00, gap >= 0%

    Fires one Telegram alert per ticker per day.
    Returns list of newly inserted alert dicts.
    """
    global _alerted_today, _alerted_date

    now_et = datetime.now(_ET)
    today_str = now_et.date().isoformat()

    if today_str != _alerted_date:
        _alerted_today = set()
        _alerted_date = today_str

    minutes_since_open = max(1, (now_et.hour - 9) * 60 + (now_et.minute - 30))

    snaps = await get_snapshot_all()
    if not snaps:
        return []

    new_alerts: list[dict] = []

    for ticker, snap in snaps.items():
        if len(ticker) > 5 or "." in ticker:
            continue
        if ticker in _alerted_today:
            continue

        prev_close = snap.get("prevDay", {}).get("c", 0)
        if not prev_close or prev_close <= 0:
            continue

        # Current price: day.c (last intraday price) → min.c → lastTrade.p
        current_price = (
            snap.get("day", {}).get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p", 0)
        )
        if not current_price or current_price < _MIN_PRICE:
            continue

        gap_pct = (current_price - prev_close) / prev_close * 100
        if gap_pct < 0:
            continue

        today_volume = snap.get("day", {}).get("v", 0) or snap.get("min", {}).get("av", 0) or 0

        projected_vol: int | None = None
        is_anticipation = False

        if minutes_since_open >= _PROJECTION_MIN_MINUTES and today_volume > 0:
            projected_vol = int(today_volume * (_SESSION_MINUTES / minutes_since_open))

        is_9m_actual = today_volume >= _9M_ACTUAL_THRESHOLD
        is_9m_anticipation = (
            projected_vol is not None
            and projected_vol >= _9M_PROJECTED_THRESHOLD
            and not is_9m_actual
        )

        if not (is_9m_actual or is_9m_anticipation):
            continue

        if is_9m_anticipation:
            is_anticipation = True

        alert = {
            "ticker": ticker,
            "alert_date": today_str,
            "detection_time": now_et,
            "today_volume": today_volume,
            "projected_vol": projected_vol,
            "current_price": current_price,
            "gap_pct": round(gap_pct, 2),
            "is_anticipation": is_anticipation,
        }

        is_new = await insert_9m_ep_alert(alert)
        if not is_new:
            _alerted_today.add(ticker)
            continue

        _alerted_today.add(ticker)
        new_alerts.append(alert)

        if is_9m_actual:
            vol_str = f"{today_volume / 1_000_000:.1f}M"
            label = "🏦 *9M EP*"
        else:
            vol_str = f"~{projected_vol / 1_000_000:.1f}M proj"  # type: ignore[operator]
            label = "🏦 *9M EP (Pace)*"

        msg = f"{label}: `{ticker}` — Vol: {vol_str} | ${current_price:.2f} | +{gap_pct:.1f}%"
        await send_telegram_message(msg)
        logger.info(f"9M EP alert: {ticker} vol={today_volume:,} price=${current_price:.2f}")

    return new_alerts


async def run_9m_eod_sweep(trade_date: "str | date") -> int:
    """
    EOD sweep: identify stocks that completed a confirmed 9M day with a strong close.
    Called once after the nightly data pull (~5:30 PM ET).

    Sugar Baby criteria (queried directly from mi_daily_closes):
    - volume >= 9M shares
    - close >= $3.00
    - open_price present (column added by schema migration)
    - close > open (green day)
    - (close - low) / (high - low) >= 0.75 (close in upper 25% of range)

    Inserts qualifying stocks into mi_9m_sugar_babies for Day 2 ORB.
    Returns count of sugar babies stored.
    """
    if isinstance(trade_date, date):
        trade_date_str = trade_date.isoformat()
    else:
        trade_date_str = trade_date

    rows = await get_eod_9m_sugar_babies(trade_date_str)
    count = 0

    for row in rows:
        h = row["high_price"]
        l = row["low_price"]
        c = row["close_price"]
        o = row["open_price"]

        if h is None or l is None or o is None:
            continue
        if (h - l) <= 0:
            continue

        close_in_range = (c - l) / (h - l)

        await insert_9m_sugar_baby({
            "ticker": row["ticker"],
            "alert_date": trade_date_str,
            "open_price": o,
            "close_price": c,
            "high_price": h,
            "low_price": l,
            "volume": row["volume"],
            "close_in_range_pct": round(close_in_range, 3),
        })
        count += 1

    logger.info(f"9M EOD sweep {trade_date_str}: {count} sugar babies confirmed")
    return count


def format_sugar_babies_section(babies: list[dict]) -> str:
    """Format sugar babies for the evening briefing. Returns empty string if none."""
    if not babies:
        return ""
    lines = ["\n🍭 *9M Sugar Babies — Day 2 Watchlist*"]
    for s in babies:
        range_pct = int(s["close_in_range_pct"] * 100)
        ticker = s["ticker"]
        vol_m = s["volume"] / 1_000_000
        close = s["close_price"]
        stop = s["low_price"]
        lines.append(
            f"`{ticker:<5}` Vol: {vol_m:.1f}M | Close: ${close:.2f} | "
            f"Range: {range_pct}% | Stop: ${stop:.2f}"
        )
    return "\n".join(lines)
