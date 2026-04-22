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
from agents.market_intelligence.constants import SKIP_TICKERS
from agents.market_intelligence.db import (
    get_adv_from_daily_closes,
    get_eod_9m_sugar_babies,
    get_pool,
    get_today_9m_ep_alerts,  # noqa: F401 — re-exported for agent.py convenience
    insert_9m_ep_alert,
    insert_9m_sugar_baby,
    log_audit_event,
)

logger = logging.getLogger(__name__)

_SESSION_MINUTES = 390
_9M_ACTUAL_THRESHOLD = 8_900_000           # shares — fire "actual" alert
_9M_PROJECTED_THRESHOLD = 12_000_000       # projected shares — fire "anticipation" alert
_MIN_PRICE = 5.00                          # sub-$5 rarely institutional
_MIN_DOLLAR_VOL_ACTUAL = 50_000_000        # $50M turnover floor for actual alert
_MIN_DOLLAR_VOL_ANTICIPATION = 30_000_000  # $30M already traded for anticipation
_MIN_VOL_ANTICIPATION = 3_000_000          # 3M shares already traded before pace alert
_PROJECTION_MIN_MINUTES = 30               # projection math garbage pre-10 AM
_ADV_ANOMALY_MULTIPLIER = 3                # effective_vol ≥ 3× ADV (virgin 9M)
_MIN_GAP_PCT = 3.0                         # gap-up commitment
_MIN_INTRADAY_GAIN_PCT = 4.0               # OR intraday trend

# In-memory dedup: prevents duplicate Telegram alerts within the same calendar day.
# A process restart clears this; the DB UNIQUE constraint on (ticker, alert_date)
# ensures insert_9m_ep_alert() returns False for duplicates so no repeat is sent.
_alerted_today: set[str] = set()
_alerted_date: str = ""

# Per-day caches — refreshed once per trading day (DB data doesn't change intraday)
_non_stock_cache: set[str] = set()
_non_stock_cache_date: str = ""
_adv_cache: dict[str, float] = {}
_adv_cache_date: str = ""
_ma10_cache: dict[str, float] = {}
_ma10_cache_date: str = ""

_MIN_RANGE_PCT = 0.02                # intraday range ≥ 2% of current price
_MAX_EXTENSION_FROM_MA10 = 1.20      # current price ≤ 1.20× 10d SMA

_ET = ZoneInfo("America/New_York")


async def _get_non_stock_tickers(today_str: str) -> set[str]:
    """Return tickers classified as non-common-stock (ETFs, warrants, etc.) in mi_security_types."""
    global _non_stock_cache, _non_stock_cache_date
    if _non_stock_cache_date == today_str:
        return _non_stock_cache
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker FROM mi_security_types WHERE security_type NOT IN ('CS', 'ADRC')"
        )
    _non_stock_cache = {r["ticker"] for r in rows}
    _non_stock_cache_date = today_str
    logger.info(f"9M non-stock cache refreshed: {len(_non_stock_cache)} tickers")
    return _non_stock_cache


async def _get_adv_map(today_str: str) -> dict[str, float]:
    """20-day median ADV from mi_daily_closes for every ticker with ≥10 sessions of history."""
    global _adv_cache, _adv_cache_date
    if _adv_cache_date == today_str:
        return _adv_cache
    trade_date = date.fromisoformat(today_str)
    _adv_cache = await get_adv_from_daily_closes(trade_date)
    _adv_cache_date = today_str
    logger.info(f"9M ADV cache refreshed: {len(_adv_cache)} tickers")
    return _adv_cache


async def _get_ma10_map(today_str: str) -> dict[str, float]:
    """10-session SMA of close from mi_daily_closes for extension gate."""
    global _ma10_cache, _ma10_cache_date
    if _ma10_cache_date == today_str:
        return _ma10_cache
    trade_date = date.fromisoformat(today_str)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, AVG(close) AS sma_10
            FROM (
                SELECT ticker, close,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE trade_date < $1
                  AND trade_date >= $1 - INTERVAL '20 days'
            ) t
            WHERE rn <= 10
            GROUP BY ticker
            HAVING COUNT(*) >= 10
        """, trade_date)
    _ma10_cache = {r["ticker"]: float(r["sma_10"]) for r in rows}
    _ma10_cache_date = today_str
    logger.info(f"9M MA10 cache refreshed: {len(_ma10_cache)} tickers")
    return _ma10_cache


async def run_9m_scan() -> list[dict]:
    """
    Intraday scan for stocks crossing the 9M volume threshold.
    Called every 5 minutes, 9:30 AM – 4:00 PM ET.

    Detection rules (virgin 9M — Pradeep Bonde):
    - price >= $5.00
    - gap >= 3% OR intraday gain >= 4% (directional conviction)
    - actual: volume >= 8.9M AND dollar_volume >= $50M, OR
    - anticipation: >=30 min elapsed, >=3M shares traded, >=$30M turnover,
      and projected volume >= 12M
    - effective_vol >= 3× ADV (unknown ADV → pass)

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

    non_stocks = await _get_non_stock_tickers(today_str)
    adv_map = await _get_adv_map(today_str)
    ma10_map = await _get_ma10_map(today_str)

    new_alerts: list[dict] = []

    for ticker, snap in snaps.items():
        if len(ticker) > 5 or "." in ticker:
            continue
        if ticker in SKIP_TICKERS or ticker in non_stocks:
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

        # Directional conviction: gapped up 3%+ OR trending up 4%+ intraday.
        day_open = snap.get("day", {}).get("o") or 0
        gap_pct = ((day_open - prev_close) / prev_close * 100) if day_open > 0 else 0.0
        intraday_gain_pct = (current_price - prev_close) / prev_close * 100
        if gap_pct < _MIN_GAP_PCT and intraday_gain_pct < _MIN_INTRADAY_GAIN_PCT:
            continue

        # Intraday range ≥ 2% of price — rejects merger-arb pins (e.g. DBRG at 0.26%
        # range pinned to a cash deal close). A real 9M day has meaningful range.
        day_high = snap.get("day", {}).get("h") or 0
        day_low = snap.get("day", {}).get("l") or 0
        if day_high > 0 and day_low > 0:
            range_pct = (day_high - day_low) / current_price
            if range_pct < _MIN_RANGE_PCT:
                continue

        # Extension gate: measure extension at YESTERDAY's close, not today's.
        # A stock flat for 10d then ripping +30% today should PASS (fresh breakout).
        # A stock that already ran for 5 days (BB-style chase) had prev_close
        # well above MA10 going in and should fail. Unknown MA → pass.
        ma10 = ma10_map.get(ticker)
        if ma10 and prev_close > ma10 * _MAX_EXTENSION_FROM_MA10:
            continue

        today_volume = snap.get("day", {}).get("v", 0) or snap.get("min", {}).get("av", 0) or 0
        dollar_volume = today_volume * current_price

        is_9m_actual = (
            today_volume >= _9M_ACTUAL_THRESHOLD
            and dollar_volume >= _MIN_DOLLAR_VOL_ACTUAL
        )

        projected_vol: int | None = None
        is_9m_anticipation = False
        if (
            not is_9m_actual
            and minutes_since_open >= _PROJECTION_MIN_MINUTES
            and today_volume >= _MIN_VOL_ANTICIPATION
            and dollar_volume >= _MIN_DOLLAR_VOL_ANTICIPATION
        ):
            projected_vol = int(today_volume * (_SESSION_MINUTES / minutes_since_open))
            is_9m_anticipation = projected_vol >= _9M_PROJECTED_THRESHOLD

        if not (is_9m_actual or is_9m_anticipation):
            continue

        # Virgin 9M gate: effective volume must be ≥3× normal ADV.
        # Actual path uses today_volume; anticipation uses projected_vol.
        # Matches EOD SQL (d.volume >= adv_20 * 3) so intraday/EOD agree.
        # Unknown ADV → pass conservatively (ticker not in RS universe).
        adv = adv_map.get(ticker)
        if adv:
            effective_vol = projected_vol if is_9m_anticipation else today_volume
            if effective_vol < adv * _ADV_ANOMALY_MULTIPLIER:
                continue

        is_anticipation = is_9m_anticipation
        rvol_display = round(today_volume / adv, 1) if (adv and adv > 0) else None

        # Display leg: gap if it qualified, otherwise the intraday trend that did.
        display_pct = gap_pct if gap_pct >= _MIN_GAP_PCT else intraday_gain_pct
        alert = {
            "ticker": ticker,
            "alert_date": today_str,
            "detection_time": now_et,
            "today_volume": today_volume,
            "projected_vol": projected_vol,
            "current_price": current_price,
            "gap_pct": round(display_pct, 2),
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

        rvol_str = f" | RVOL: {rvol_display:.1f}x" if rvol_display else ""
        dv_str = f"${dollar_volume/1_000_000:.0f}M"
        msg = f"{label}: `{ticker}` — Vol: {vol_str} ({dv_str}){rvol_str} | ${current_price:.2f} | +{display_pct:.1f}%"
        await send_telegram_message(msg)
        logger.info(f"9M EP alert: {ticker} vol={today_volume:,} price=${current_price:.2f}")
        await log_audit_event(
            "9m_ep_detected",
            f"{ticker} vol={today_volume/1_000_000:.1f}M price=${current_price:.2f} gap={gap_pct:.1f}%",
            f"is_anticipation={is_anticipation} projected={projected_vol}",
        )

    return new_alerts


async def run_9m_eod_sweep(trade_date: "str | date") -> int:
    """
    EOD sweep: identify stocks that completed a confirmed 9M day with a strong close.
    Called once after the nightly data pull (~5:30 PM ET).

    Sugar Baby criteria (mirrors intraday gates — queried from mi_daily_closes):
    - volume >= 9M shares
    - close >= $5.00
    - dollar_volume (volume * close) >= $50M
    - open_price present, close > open (green day)
    - (close - low) / (high - low) >= 0.75 (close in upper 25% of range)
    - volume >= 3× adv_20 (virgin 9M; unknown ADV → pass)

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
    if count:
        await log_audit_event(
            "9m_sugar_babies_confirmed",
            f"{count} sugar babies on {trade_date_str}",
        )
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
