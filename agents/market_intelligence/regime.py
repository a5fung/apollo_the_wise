"""
Market Regime Engine.

Determines the current market regime: Bull / Choppy / Correcting / Crisis.
Runs nightly. Output colors all EP scoring and briefing tone.

Inputs:
- SPY vs 50-day MA and 200-day MA
- VIX level + trend
- Breadth: % of universe stocks above their 40-day MA (T2108 proxy)
- +/-4% ratio: rolling 5d and 10d count of stocks with >=+4% vs <=-4% daily moves

Regime → EP threshold adjustment:
- Bull:       threshold = 70
- Choppy:     threshold = 80
- Correcting: threshold = 85
- Crisis:     threshold = 90
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.collector import get_index_history
from agents.market_intelligence.db import upsert_regime, get_latest_regime as _get_latest_regime

logger = logging.getLogger(__name__)


def _moving_average(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _determine_regime(
    spy_vs_50ma: Optional[float],
    spy_vs_200ma: Optional[float],
    qqq_vs_50ma: Optional[float],
    vix: Optional[float],
    breadth_pct: Optional[float],
    pct4_ratio_5d: Optional[float],
    pct4_ratio_10d: Optional[float] = None,
) -> tuple[str, str, int]:
    """
    Returns: (regime_label, description, ep_threshold)
    """
    signals = []
    bearish_count = 0
    bullish_count = 0

    # SPY vs 50MA
    if spy_vs_50ma is not None:
        if spy_vs_50ma > 2:
            bullish_count += 2
            signals.append(f"SPY is {spy_vs_50ma:.1f}% above its 50MA (bullish)")
        elif spy_vs_50ma > 0:
            bullish_count += 1
            signals.append(f"SPY is {spy_vs_50ma:.1f}% above its 50MA (slightly bullish)")
        elif spy_vs_50ma > -3:
            bearish_count += 1
            signals.append(f"SPY is {abs(spy_vs_50ma):.1f}% below its 50MA (caution)")
        else:
            bearish_count += 2
            signals.append(f"SPY is {abs(spy_vs_50ma):.1f}% below its 50MA (bearish)")

    # QQQ vs 50MA (growth stock health)
    if qqq_vs_50ma is not None:
        if qqq_vs_50ma > 2:
            bullish_count += 1
            signals.append(f"QQQ vs 50MA: +{qqq_vs_50ma:.1f}% (growth leading)")
        elif qqq_vs_50ma > 0:
            signals.append(f"QQQ vs 50MA: +{qqq_vs_50ma:.1f}% (growth holding)")
        elif qqq_vs_50ma > -5:
            bearish_count += 1
            signals.append(f"QQQ vs 50MA: {qqq_vs_50ma:.1f}% (growth under pressure)")
        else:
            bearish_count += 2
            signals.append(f"QQQ vs 50MA: {qqq_vs_50ma:.1f}% (growth breakdown)")

    # SPY vs 200MA
    if spy_vs_200ma is not None:
        if spy_vs_200ma < -10:
            bearish_count += 2
            signals.append(f"SPY is {abs(spy_vs_200ma):.1f}% below its 200MA (bear market territory)")
        elif spy_vs_200ma < 0:
            bearish_count += 1
            signals.append(f"SPY is {abs(spy_vs_200ma):.1f}% below its 200MA (below long-term trend)")
        else:
            bullish_count += 1
            signals.append(f"SPY is {spy_vs_200ma:.1f}% above its 200MA (above long-term trend)")

    # VIX
    if vix is not None:
        if vix >= 35:
            bearish_count += 3
            signals.append(f"VIX at {vix:.1f} — crisis-level fear")
        elif vix >= 25:
            bearish_count += 2
            signals.append(f"VIX at {vix:.1f} — elevated fear, risk-off")
        elif vix >= 20:
            bearish_count += 1
            signals.append(f"VIX at {vix:.1f} — above average volatility, cautious")
        else:
            bullish_count += 1
            signals.append(f"VIX at {vix:.1f} — low fear, risk-on")

    # Breadth (T2108 proxy)
    if breadth_pct is not None:
        if breadth_pct < 20:
            bearish_count += 2
            signals.append(f"{breadth_pct:.0f}% of stocks above 40MA — oversold breadth (potential bottom)")
        elif breadth_pct < 40:
            bearish_count += 1
            signals.append(f"{breadth_pct:.0f}% of stocks above 40MA — weak breadth")
        elif breadth_pct > 85:
            signals.append(f"{breadth_pct:.0f}% of stocks above 40MA — overbought breadth")
        else:
            bullish_count += 1
            signals.append(f"{breadth_pct:.0f}% of stocks above 40MA — healthy breadth")

    # +/-4% ratio — rolling count of +4% vs -4% daily moves
    # Use 10d as primary regime signal (smoother), 5d as short-term context
    ratio = pct4_ratio_10d if pct4_ratio_10d is not None else pct4_ratio_5d
    window = "10d" if pct4_ratio_10d is not None else "5d"
    if ratio is not None:
        if ratio >= 2.0:
            bullish_count += 2
            signals.append(f"+/-4% ratio ({window}) {ratio:.1f}x — strong breadth momentum")
        elif ratio >= 1.0:
            bullish_count += 1
            signals.append(f"+/-4% ratio ({window}) {ratio:.1f}x — slightly bullish breadth")
        elif ratio <= 0.5:
            bearish_count += 2
            signals.append(f"+/-4% ratio ({window}) {ratio:.1f}x — bearish breadth momentum")
        else:
            bearish_count += 1
            signals.append(f"+/-4% ratio ({window}) {ratio:.1f}x — weak breadth")

    # Determine regime
    net = bullish_count - bearish_count
    if net >= 4:
        regime = "Bull"
        ep_threshold = 65
        verdict = "Market in bull trend — standard EP criteria apply."
    elif net >= 1:
        regime = "Choppy"
        ep_threshold = 70
        verdict = "Market choppy — raise EP bar, size down."
    elif net >= -2:
        regime = "Correcting"
        ep_threshold = 75
        verdict = "Market correcting — be very selective, only exceptional EPs."
    else:
        regime = "Crisis"
        ep_threshold = 80
        verdict = "Crisis conditions — only game-changer EPs warrant attention."

    description = verdict + "\n" + "\n".join(f"  • {s}" for s in signals)
    return regime, description, ep_threshold


async def calculate_breadth(today_str: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate breadth using the stored universe RS scores.
    - breadth_pct: % of universe stocks whose current price > their 40-day-ago price
    - pct4_ratio_5d: +/-4% ratio over last 5 trading days (up4 / down4)
    - pct4_ratio_10d: +/-4% ratio over last 10 trading days

    Uses individual ticker calls (free tier compatible).
    Runs on the universe defined in universe.py.
    """
    from agents.market_intelligence.universe import UNIVERSE
    from agents.market_intelligence.collector import trading_date_n_months_ago

    today = date.fromisoformat(today_str)
    from_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    date_40d = (today - timedelta(days=58)).strftime("%Y-%m-%d")  # ~40 trading days

    above_40d = 0
    total = 0
    # Collect daily pct changes across all sampled stocks for rolling window
    all_daily_changes: list[tuple[str, float]] = []  # (date_str, pct_change)

    # Sample 30 stocks from universe for breadth estimate (keeps API calls low)
    sample = UNIVERSE[:30]
    for ticker in sample:
        try:
            bars = await get_index_history(ticker, from_date, today_str)
            if len(bars) < 5:
                continue

            from datetime import datetime, timezone
            closes = sorted(
                [(datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date().strftime("%Y-%m-%d"), b["c"])
                 for b in bars if "c" in b and "t" in b]
            )

            # Breadth: current vs 40-day-ago
            current = closes[-1][1] if closes else None
            past_list = [c for d, c in closes if d <= date_40d]
            past = past_list[-1] if past_list else None

            if current and past:
                total += 1
                if current > past:
                    above_40d += 1

            # Collect daily changes for +/-4% ratio
            for i in range(1, len(closes)):
                prev_close = closes[i - 1][1]
                if prev_close > 0:
                    chg = (closes[i][1] - prev_close) / prev_close * 100
                    all_daily_changes.append((closes[i][0], chg))
        except Exception:
            continue

    breadth_pct = round(above_40d / max(total, 1) * 100, 1) if total > 0 else None

    # Compute rolling +/-4% ratios
    def _pct4_ratio(changes: list[tuple[str, float]], n_days: int) -> Optional[float]:
        """Ratio of +4% days to -4% days over the last n trading days."""
        # Get the last n unique trading dates
        all_dates = sorted({d for d, _ in changes})
        if len(all_dates) < n_days:
            return None
        cutoff_dates = set(all_dates[-n_days:])
        recent = [(d, c) for d, c in changes if d in cutoff_dates]
        up4 = sum(1 for _, c in recent if c >= 4)
        down4 = sum(1 for _, c in recent if c <= -4)
        if up4 + down4 == 0:
            return None
        return round(up4 / max(down4, 1), 2)

    pct4_5d = _pct4_ratio(all_daily_changes, 5)
    pct4_10d = _pct4_ratio(all_daily_changes, 10)

    return breadth_pct, pct4_5d, pct4_10d


async def run_regime_engine(trade_date: date | None = None) -> dict:
    """
    Calculate current market regime and store in DB.
    Returns regime summary dict.
    """
    today = trade_date or date.today()
    today_str = today.strftime("%Y-%m-%d")
    from_date = (today - timedelta(days=250)).strftime("%Y-%m-%d")

    logger.info(f"Regime engine: fetching SPY/VIX history...")

    # SPY, QQQ, VIX proxy history (3 Polygon calls — free tier compatible)
    spy_bars = await get_index_history("SPY", from_date, today_str)
    qqq_bars = await get_index_history("QQQ", from_date, today_str)
    vix_bars = await get_index_history("UVXY", from_date, today_str)

    spy_closes = [b["c"] for b in spy_bars if "c" in b]
    qqq_closes = [b["c"] for b in qqq_bars if "c" in b]
    vix_closes = [b["c"] for b in vix_bars if "c" in b]

    current_spy = spy_closes[-1] if spy_closes else None
    current_qqq = qqq_closes[-1] if qqq_closes else None
    current_vix = vix_closes[-1] if vix_closes else None

    spy_50ma = _moving_average(spy_closes, 50)
    spy_200ma = _moving_average(spy_closes, 200)
    qqq_50ma = _moving_average(qqq_closes, 50)

    spy_vs_50ma = ((current_spy - spy_50ma) / spy_50ma * 100) if current_spy and spy_50ma else None
    spy_vs_200ma = ((current_spy - spy_200ma) / spy_200ma * 100) if current_spy and spy_200ma else None
    qqq_vs_50ma = ((current_qqq - qqq_50ma) / qqq_50ma * 100) if current_qqq and qqq_50ma else None

    # Breadth (additional calls)
    logger.info("Regime engine: calculating breadth...")
    breadth_pct, pct4_5d, pct4_10d = await calculate_breadth(today_str)

    regime, description, ep_threshold = _determine_regime(
        spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, current_vix, breadth_pct, pct4_5d, pct4_10d
    )

    record = {
        "regime_date": today,
        "regime": regime,
        "spy_vs_50ma": round(spy_vs_50ma, 2) if spy_vs_50ma else None,
        "spy_vs_200ma": round(spy_vs_200ma, 2) if spy_vs_200ma else None,
        "qqq_vs_50ma": round(qqq_vs_50ma, 2) if qqq_vs_50ma else None,
        "vix": round(current_vix, 2) if current_vix else None,
        "breadth_pct_above_40ma": breadth_pct,
        "bo_bd_ratio_5d": pct4_5d,
        "pct4_ratio_10d": pct4_10d,
        "description": description,
        "ep_threshold": ep_threshold,
    }

    await upsert_regime(record)
    logger.info(f"Regime: {regime} (EP threshold: {ep_threshold})")
    return record


async def get_current_regime() -> dict:
    """Get the most recent stored regime, or a fallback if none exists."""
    regime = await _get_latest_regime()
    if not regime:
        return {
            "regime": "Unknown",
            "description": "No regime data yet — run nightly data pull first.",
            "ep_threshold": 70,
        }
    return dict(regime)
