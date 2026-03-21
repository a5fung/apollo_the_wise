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

    # T2108 — full-universe breadth (% above 40MA)
    if t2108 is not None:
        if t2108 < 25:
            bearish_count += 2
            signals.append(f"T2108 {t2108:.0f}% above 40MA — oversold breadth")
        elif t2108 < 40:
            bearish_count += 1
            signals.append(f"T2108 {t2108:.0f}% above 40MA — weak breadth")
        elif t2108 <= 70:
            bullish_count += 1
            signals.append(f"T2108 {t2108:.0f}% above 40MA — healthy breadth")
        else:
            signals.append(f"T2108 {t2108:.0f}% above 40MA — overbought")
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
    Full Stockbee Market Monitor from stored mi_stock_scores + mi_daily_closes.
    Zero API calls.

    Primary breadth (fast daily):
    - today_up4 / today_down4: stocks moving 4%+ today
    - pct4_ratio_5d / pct4_ratio_10d: rolling ratios

    Secondary breadth (slower momentum backdrop):
    - t2108: % above 40MA
    - up/down 25% in quarter, up/down 25% in month, up/down 50% in month
    - consec_breakdown_days: consecutive days with 700+ stocks down 4%+

    Also stores full monitor dict as breadth_monitor for on-demand display.
    """
    from agents.market_intelligence.db import get_pool, get_prior_consec_breakdown_days

    pool = await get_pool()
    async with pool.acquire() as conn:
        # T2108 (% above 40MA) + all secondary momentum counts from mi_stock_scores
        breadth_row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE sma_40 IS NOT NULL) AS total_with_sma40,
                COUNT(*) FILTER (WHERE close > sma_40 AND sma_40 IS NOT NULL) AS above_40ma,
                COUNT(*) AS universe_size,
                -- Secondary: monthly momentum
                COUNT(*) FILTER (WHERE raw_1m IS NOT NULL AND raw_1m >= 25) AS up_25_1m,
                COUNT(*) FILTER (WHERE raw_1m IS NOT NULL AND raw_1m <= -25) AS down_25_1m,
                COUNT(*) FILTER (WHERE raw_1m IS NOT NULL AND raw_1m >= 50) AS up_50_1m,
                COUNT(*) FILTER (WHERE raw_1m IS NOT NULL AND raw_1m <= -50) AS down_50_1m,
                -- Secondary: quarterly momentum
                COUNT(*) FILTER (WHERE raw_3m IS NOT NULL AND raw_3m >= 25) AS up_25_3m,
                COUNT(*) FILTER (WHERE raw_3m IS NOT NULL AND raw_3m <= -25) AS down_25_3m
            FROM mi_stock_scores
            WHERE score_date = $1
        """, today)

        total_with_sma40 = breadth_row["total_with_sma40"] or 0
        above_40ma = breadth_row["above_40ma"] or 0
        t2108 = round(above_40ma / max(total_with_sma40, 1) * 100, 1) if total_with_sma40 > 0 else None
        universe_size = breadth_row["universe_size"] or 0

        up_25_1m = breadth_row["up_25_1m"] or 0
        down_25_1m = breadth_row["down_25_1m"] or 0
        up_50_1m = breadth_row["up_50_1m"] or 0
        down_50_1m = breadth_row["down_50_1m"] or 0
        up_25_3m = breadth_row["up_25_3m"] or 0
        down_25_3m = breadth_row["down_25_3m"] or 0

        # Primary: +/-4% ratio from mi_daily_closes — last 11 trade dates for 10d of changes
        trade_dates_rows = await conn.fetch("""
            SELECT DISTINCT trade_date FROM mi_daily_closes
            WHERE trade_date <= $1
            ORDER BY trade_date DESC
            LIMIT 11
        """, today)
        trade_dates = sorted([r["trade_date"] for r in trade_dates_rows])

        pct4_5d = None
        pct4_10d = None
        today_up4 = 0
        today_down4 = 0
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

            # Today's counts (last entry)
            if daily_up4:
                today_up4 = daily_up4[-1]
                today_down4 = daily_down4[-1]

            # 10d ratio
            total_up4_10d = sum(daily_up4)
            total_down4_10d = sum(daily_down4)
            if total_up4_10d + total_down4_10d > 0:
                pct4_10d = round(total_up4_10d / max(total_down4_10d, 1), 2)

            # 5d ratio (last 5 days of changes)
            if len(daily_up4) >= 5:
                up4_5 = sum(daily_up4[-5:])
                down4_5 = sum(daily_down4[-5:])
                if up4_5 + down4_5 > 0:
                    pct4_5d = round(up4_5 / max(down4_5, 1), 2)

        # Consecutive breakdown days: 700+ stocks down 4%+ today
        if today_down4 >= 700:
            prior = await get_prior_consec_breakdown_days(today)
            consec_breakdown_days = prior + 1
        else:
            consec_breakdown_days = 0

        # ── Derive condensed signals ──────────────────────────────────
        # Primary signal: based on 5d and 10d ratios
        # Dark green (2): both > 2.0 | Green (1): both > 1.0
        # Red (-1): either < 1.0 | Dark red (-2): either < 0.5
        r5 = pct4_5d if pct4_5d is not None else 1.0
        r10 = pct4_10d if pct4_10d is not None else 1.0
        if r5 >= 2.0 and r10 >= 2.0:
            primary_signal = 2
        elif r5 >= 1.0 and r10 >= 1.0:
            primary_signal = 1
        elif r5 < 0.5 or r10 < 0.5:
            primary_signal = -2
        else:
            primary_signal = -1

        # Secondary signal: T2108 + momentum balance
        # Count how many of the momentum pairs favor bulls vs bears
        momentum_score = 0
        if up_25_3m > down_25_3m:
            momentum_score += 1
        elif up_25_3m < down_25_3m:
            momentum_score -= 1
        if up_25_1m > down_25_1m:
            momentum_score += 1
        elif up_25_1m < down_25_1m:
            momentum_score -= 1
        if up_50_1m > down_50_1m:
            momentum_score += 1
        elif up_50_1m < down_50_1m:
            momentum_score -= 1

        # T2108 contribution
        if t2108 is not None:
            if t2108 < 25:
                momentum_score -= 2
            elif t2108 < 40:
                momentum_score -= 1
            elif t2108 <= 70:
                momentum_score += 1
            # > 70: overbought, neutral (don't add)

        if momentum_score >= 3:
            secondary_signal = 2
        elif momentum_score >= 1:
            secondary_signal = 1
        elif momentum_score >= -2:
            secondary_signal = -1
        else:
            secondary_signal = -2

    # Full monitor for on-demand display
    breadth_monitor = {
        # Primary
        "today_up4": today_up4,
        "today_down4": today_down4,
        "ratio_5d": pct4_5d,
        "ratio_10d": pct4_10d,
        "primary_signal": primary_signal,
        # Secondary
        "t2108": t2108,
        "up_25_3m": up_25_3m,
        "down_25_3m": down_25_3m,
        "up_25_1m": up_25_1m,
        "down_25_1m": down_25_1m,
        "up_50_1m": up_50_1m,
        "down_50_1m": down_50_1m,
        "secondary_signal": secondary_signal,
        # Meta
        "universe_size": universe_size,
        "consec_breakdown_days": consec_breakdown_days,
    }

    return {
        "t2108": t2108,
        "breadth_pct": t2108,
        "pradeep_1m_50": up_50_1m,
        "pradeep_3m_25": up_25_3m,
        "pct4_ratio_5d": pct4_5d,
        "pct4_ratio_10d": pct4_10d,
        "full_up4_count": today_up4,
        "full_down4_count": today_down4,
        "consec_breakdown_days": consec_breakdown_days,
        "primary_signal": primary_signal,
        "secondary_signal": secondary_signal,
        "breadth_monitor": breadth_monitor,
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
        "breadth_monitor": breadth.get("breadth_monitor"),
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
