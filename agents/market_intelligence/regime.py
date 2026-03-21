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
from agents.market_intelligence.db import (
    upsert_regime,
    get_latest_regime as _get_latest_regime,
    get_prior_consec_breakdown_days,
)

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
    t2108: Optional[float] = None,
    pradeep_1m_50: Optional[int] = None,
    pradeep_3m_25: Optional[int] = None,
    consec_breakdown_days: Optional[int] = None,
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

    # T2108 — full-universe breadth (% above 50MA)
    if t2108 is not None:
        if t2108 < 25:
            bearish_count += 2
            signals.append(f"T2108 {t2108:.0f}% above 50MA — oversold breadth")
        elif t2108 < 40:
            bearish_count += 1
            signals.append(f"T2108 {t2108:.0f}% above 50MA — weak breadth")
        elif t2108 <= 70:
            bullish_count += 1
            signals.append(f"T2108 {t2108:.0f}% above 50MA — healthy breadth")
        else:
            signals.append(f"T2108 {t2108:.0f}% above 50MA — overbought")
    elif breadth_pct is not None:
        # Fallback to old breadth if T2108 not available yet
        if breadth_pct < 20:
            bearish_count += 2
            signals.append(f"{breadth_pct:.0f}% breadth — oversold")
        elif breadth_pct < 40:
            bearish_count += 1
            signals.append(f"{breadth_pct:.0f}% breadth — weak")
        elif breadth_pct > 85:
            signals.append(f"{breadth_pct:.0f}% breadth — overbought")
        else:
            bullish_count += 1
            signals.append(f"{breadth_pct:.0f}% breadth — healthy")

    # Pradeep 1M momentum count (stocks up 50%+ in 1 month)
    if pradeep_1m_50 is not None:
        if pradeep_1m_50 >= 50:
            bullish_count += 1
            signals.append(f"Momentum: {pradeep_1m_50} stocks up 50%+/1M (strong)")
        elif pradeep_1m_50 < 10:
            bearish_count += 1
            signals.append(f"Momentum: {pradeep_1m_50} stocks up 50%+/1M (dying)")
        else:
            signals.append(f"Momentum: {pradeep_1m_50} stocks up 50%+/1M")

    # Consecutive breakdown days (700+ stocks down 4%+ per day)
    if consec_breakdown_days is not None and consec_breakdown_days >= 3:
        bearish_count += 2
        signals.append(f"Breakdown: {consec_breakdown_days} consecutive days of 700+ stocks down 4%+")

    # +/-4% ratio — rolling count of +4% vs -4% daily moves
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


async def calculate_breadth_full(today: date) -> dict:
    """
    Full-universe breadth from stored mi_stock_scores + mi_daily_closes. Zero API calls.

    Returns dict with:
    - t2108: % of scored stocks where close > sma_50
    - breadth_pct: same as t2108 (for backwards compat)
    - pradeep_1m_50: count of stocks with raw_1m >= 50 (up 50%+ in 1M)
    - pradeep_3m_25: count of stocks with raw_3m >= 25 (up 25%+ in 3M)
    - pct4_ratio_5d: +4% / -4% daily move ratio over 5 trading days
    - pct4_ratio_10d: same over 10 trading days
    - full_up4_count: total +4% stock-days in 10d window
    - full_down4_count: total -4% stock-days in 10d window
    - consec_breakdown_days: consecutive days with 700+ stocks down 4%+
    """
    from agents.market_intelligence.db import get_pool, get_prior_consec_breakdown_days

    pool = await get_pool()
    async with pool.acquire() as conn:
        # T2108 + Pradeep counts from mi_stock_scores
        breadth_row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE sma_50 IS NOT NULL) AS total_with_sma,
                COUNT(*) FILTER (WHERE close > sma_50 AND sma_50 IS NOT NULL) AS above_50ma,
                COUNT(*) FILTER (WHERE raw_1m IS NOT NULL AND raw_1m >= 50) AS pradeep_1m_50,
                COUNT(*) FILTER (WHERE raw_3m IS NOT NULL AND raw_3m >= 25) AS pradeep_3m_25
            FROM mi_stock_scores
            WHERE score_date = $1
        """, today)

        total_with_sma = breadth_row["total_with_sma"] or 0
        above_50ma = breadth_row["above_50ma"] or 0
        t2108 = round(above_50ma / max(total_with_sma, 1) * 100, 1) if total_with_sma > 0 else None

        pradeep_1m_50 = breadth_row["pradeep_1m_50"] or 0
        pradeep_3m_25 = breadth_row["pradeep_3m_25"] or 0

        # +/-4% ratio from mi_daily_closes — last 11 trade dates for 10d of changes
        trade_dates_rows = await conn.fetch("""
            SELECT DISTINCT trade_date FROM mi_daily_closes
            WHERE trade_date <= $1
            ORDER BY trade_date DESC
            LIMIT 11
        """, today)
        trade_dates = sorted([r["trade_date"] for r in trade_dates_rows])

        pct4_5d = None
        pct4_10d = None
        full_up4_count = 0
        full_down4_count = 0
        daily_down4_counts: dict[date, int] = {}

        if len(trade_dates) >= 2:
            # Get all closes for these dates
            closes_rows = await conn.fetch("""
                SELECT trade_date, ticker, close FROM mi_daily_closes
                WHERE trade_date = ANY($1)
                  AND close IS NOT NULL AND close > 0
            """, trade_dates)

            # Build {ticker: {date: close}}
            closes_by_ticker: dict[str, dict[date, float]] = {}
            for r in closes_rows:
                tk = r["ticker"]
                if tk not in closes_by_ticker:
                    closes_by_ticker[tk] = {}
                closes_by_ticker[tk][r["trade_date"]] = r["close"]

            # Compute daily changes for consecutive date pairs
            # daily_up4[i] = count of +4% stocks on trade_dates[i+1]
            daily_up4: list[int] = []
            daily_down4: list[int] = []
            for i in range(len(trade_dates) - 1):
                d_prev = trade_dates[i]
                d_curr = trade_dates[i + 1]
                up4 = 0
                down4 = 0
                for tk, dates in closes_by_ticker.items():
                    if d_prev in dates and d_curr in dates:
                        pct_chg = (dates[d_curr] - dates[d_prev]) / dates[d_prev] * 100
                        if pct_chg >= 4:
                            up4 += 1
                        elif pct_chg <= -4:
                            down4 += 1
                daily_up4.append(up4)
                daily_down4.append(down4)
                daily_down4_counts[d_curr] = down4

            # 10d ratio (all available days)
            total_up4 = sum(daily_up4)
            total_down4 = sum(daily_down4)
            full_up4_count = total_up4
            full_down4_count = total_down4
            if total_up4 + total_down4 > 0:
                pct4_10d = round(total_up4 / max(total_down4, 1), 2)

            # 5d ratio (last 5 days of changes)
            if len(daily_up4) >= 5:
                up4_5 = sum(daily_up4[-5:])
                down4_5 = sum(daily_down4[-5:])
                if up4_5 + down4_5 > 0:
                    pct4_5d = round(up4_5 / max(down4_5, 1), 2)

        # Consecutive breakdown days: 700+ stocks down 4%+ today
        today_down4 = daily_down4_counts.get(today, 0) if daily_down4_counts else 0
        if today_down4 >= 700:
            prior = await get_prior_consec_breakdown_days(today)
            consec_breakdown_days = prior + 1
        else:
            consec_breakdown_days = 0

    return {
        "t2108": t2108,
        "breadth_pct": t2108,
        "pradeep_1m_50": pradeep_1m_50,
        "pradeep_3m_25": pradeep_3m_25,
        "pct4_ratio_5d": pct4_5d,
        "pct4_ratio_10d": pct4_10d,
        "full_up4_count": full_up4_count,
        "full_down4_count": full_down4_count,
        "consec_breakdown_days": consec_breakdown_days,
    }


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

    # Breadth — full-universe from stored data (zero API calls)
    logger.info("Regime engine: calculating breadth from stored data...")
    breadth = await calculate_breadth_full(today)

    t2108 = breadth.get("t2108")
    breadth_pct = breadth.get("breadth_pct")
    pct4_5d = breadth.get("pct4_ratio_5d")
    pct4_10d = breadth.get("pct4_ratio_10d")
    pradeep_1m_50 = breadth.get("pradeep_1m_50")
    pradeep_3m_25 = breadth.get("pradeep_3m_25")
    consec_breakdown_days = breadth.get("consec_breakdown_days")

    regime, description, ep_threshold = _determine_regime(
        spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, current_vix, breadth_pct, pct4_5d, pct4_10d,
        t2108=t2108,
        pradeep_1m_50=pradeep_1m_50,
        pradeep_3m_25=pradeep_3m_25,
        consec_breakdown_days=consec_breakdown_days,
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
        "t2108": t2108,
        "pradeep_1m_50": pradeep_1m_50,
        "pradeep_3m_25": pradeep_3m_25,
        "full_up4_count": breadth.get("full_up4_count"),
        "full_down4_count": breadth.get("full_down4_count"),
        "consec_breakdown_days": consec_breakdown_days,
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
