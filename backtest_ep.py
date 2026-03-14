"""
EP Backtest — run the MAGNA53 model against historical EP events.
Usage: python backtest_ep.py

Tests whether the EP detector would have caught known EPs.
"""
import asyncio
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

from agents.market_intelligence.collector import (
    get_index_history, get_fmp_profile, get_fmp_earnings,
    get_fmp_analyst_ratings, get_fmp_news, search_news_tavily,
)
from agents.market_intelligence.ep_detector import (
    _classify_catalyst_claude, _validate_catalyst_gemini, _score_ep,
)
from agents.market_intelligence.regime import _determine_regime

BACKTEST_CASES = [
    {"ticker": "FSLY",  "ep_date": date(2026, 2, 12)},
    {"ticker": "CRCL",  "ep_date": date(2026, 2, 25)},
]


async def get_ohlcv_for_date(ticker: str, ep_date: date) -> dict | None:
    """Get OHLCV bars around the EP date."""
    from_date = (ep_date - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = ep_date.strftime("%Y-%m-%d")
    bars = await get_index_history(ticker, from_date, to_date)
    if not bars:
        return None

    from datetime import datetime, timezone
    # Build date map — use UTC to avoid local timezone shifting dates back one day
    date_map = {}
    for b in bars:
        d = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date()
        date_map[d] = b

    if ep_date not in date_map:
        print(f"  [!] No bar found for {ticker} on {ep_date} — market closed?")
        return None

    ep_bar = date_map[ep_date]

    # Find previous trading day
    prev_date = ep_date - timedelta(days=1)
    for _ in range(5):
        if prev_date in date_map:
            break
        prev_date -= timedelta(days=1)

    prev_bar = date_map.get(prev_date)
    if not prev_bar:
        print(f"  [!] No previous bar found for {ticker}")
        return None

    # ADV: average volume over 20 trading days before EP
    sorted_dates = sorted(date_map.keys())
    pre_ep = [date_map[d]["v"] for d in sorted_dates if d < ep_date]
    adv_20 = sum(pre_ep[-20:]) / len(pre_ep[-20:]) if pre_ep else None

    prev_close = prev_bar["c"]
    ep_open = ep_bar["o"]
    ep_close = ep_bar["c"]
    ep_volume = ep_bar["v"]

    gap_pct = (ep_open - prev_close) / prev_close * 100
    rel_volume = (ep_volume / adv_20) if adv_20 else None

    return {
        "prev_close": round(prev_close, 2),
        "ep_open": round(ep_open, 2),
        "ep_close": round(ep_close, 2),
        "ep_volume": int(ep_volume),
        "adv_20": round(adv_20, 0) if adv_20 else None,
        "gap_pct": round(gap_pct, 2),
        "rel_volume": round(rel_volume, 2) if rel_volume else None,
        "day_return": round((ep_close - ep_open) / ep_open * 100, 2),
    }


async def backtest_one(ticker: str, ep_date: date) -> None:
    date_str = ep_date.strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  BACKTEST: {ticker}  |  {date_str}")
    print(f"{'='*60}")

    # 1. Price data
    print(f"\n[1] Fetching price data...")
    price = await get_ohlcv_for_date(ticker, ep_date)
    if not price:
        print(f"  SKIP — no price data")
        return

    print(f"  Prev close:  ${price['prev_close']}")
    print(f"  EP open:     ${price['ep_open']}")
    print(f"  Gap:         {price['gap_pct']:+.1f}%")
    print(f"  EP close:    ${price['ep_close']}  (day return: {price['day_return']:+.1f}%)")
    print(f"  Volume:      {price['ep_volume']:,}")
    print(f"  ADV (20d):   {int(price['adv_20']):,}" if price['adv_20'] else "  ADV:         N/A")
    print(f"  Rel volume:  {price['rel_volume']}x" if price['rel_volume'] else "  Rel volume:  N/A")

    # Hard filter check
    passed_gap = price["gap_pct"] >= 8.0
    passed_rvol = (price["rel_volume"] or 0) >= 2.0
    print(f"\n  Hard filters:")
    print(f"    Gap ≥8%:    {'✓ PASS' if passed_gap else '✗ FAIL'} ({price['gap_pct']:.1f}%)")
    rvol_str = "✓ PASS" if passed_rvol else (f"✗ FAIL ({price['rel_volume']}x)" if price['rel_volume'] else "? NO ADV DATA")
    print(f"    Rel vol ≥2x: {rvol_str}")

    # 2. Company profile
    print(f"\n[2] Fetching company profile...")
    profile = await get_fmp_profile(ticker)
    if profile:
        print(f"  {profile.get('companyName', ticker)} — {profile.get('sector', 'N/A')}")
        print(f"  Float: {profile.get('floatShares', 'N/A'):,}" if profile.get('floatShares') else "  Float: N/A")
    await asyncio.sleep(0.5)

    # 3. News for that date — date-bounded Tavily query
    print(f"\n[3] Fetching news around {date_str}...")
    # Note: yfinance news returns CURRENT news, not historical.
    # For backtest accuracy we rely on Tavily with explicit date context.
    fmp_news = []  # skip yfinance news in backtest — returns wrong date's articles
    company = profile.get('companyName', ticker)
    tavily_news = await search_news_tavily(
        f"{ticker} {company} earnings results announcement February 2026 catalyst"
    )

    all_news = fmp_news + [{"title": t.get("title", ""), "text": t.get("content", "")}
                            for t in tavily_news]
    if all_news:
        print(f"  Found {len(all_news)} news items:")
        for n in all_news[:5]:
            print(f"    • {n.get('title', '')[:80]}")
    else:
        print("  No news found")

    # 4. Analyst ratings
    print(f"\n[4] Fetching analyst ratings...")
    ratings = await get_fmp_analyst_ratings(ticker)
    await asyncio.sleep(0.5)
    upgrades = len([r for r in ratings if r.get("analystRatingsStrongBuy", 0) > 0])
    print(f"  Analyst upgrades: {upgrades}")

    # 5. Claude catalyst classification
    print(f"\n[5] Claude catalyst classification...")
    catalyst_quality, claude_analysis = await _classify_catalyst_claude(ticker, all_news, profile)
    print(f"  Quality: {catalyst_quality.upper()}")
    print(f"  Analysis: {claude_analysis}")

    # 6. Gemini cross-validation
    print(f"\n[6] Gemini cross-validation...")
    news_summary = "\n".join([n.get("title", "") for n in all_news[:3]])
    gemini_quality = await _validate_catalyst_gemini(ticker, news_summary)
    if gemini_quality:
        agree = gemini_quality == catalyst_quality
        print(f"  Gemini: {gemini_quality.upper()} {'✓ AGREE' if agree else '✗ DISAGREE'}")
        confidence_multiplier = 1.2 if agree else 1.0
    else:
        print("  Gemini: unavailable")
        confidence_multiplier = 1.0

    # 7. Regime at that date (approximate — use stored or estimate neutral)
    # For simplicity, assume neutral regime (multiplier=1.0) at backtest date
    regime_multiplier = 1.0 * confidence_multiplier
    ep_threshold = 70  # standard threshold

    # 8. MAGNA53 score
    print(f"\n[7] MAGNA53 score...")
    ep_score, breakdown = _score_ep(
        gap_pct=price["gap_pct"],
        rel_volume=price["rel_volume"] or 0,
        catalyst_quality=catalyst_quality,
        profile=profile,
        analyst_upgrades=upgrades,
        regime_multiplier=regime_multiplier,
    )

    tier = "HIGH" if ep_score >= ep_threshold else ("MODERATE" if ep_score >= 50 else "SKIP")

    print(f"  Breakdown: {breakdown}")
    print(f"  Score: {ep_score:.1f}  →  {tier}")

    # 9. Summary
    print(f"\n{'─'*60}")
    print(f"  RESULT: Would system have caught {ticker}?")
    would_catch = passed_gap and tier in ("HIGH", "MODERATE")
    print(f"  {'✓ YES' if would_catch else '✗ NO'} — {tier} (score {ep_score:.1f})")
    if not passed_gap:
        print(f"  Missed at hard filter: gap {price['gap_pct']:.1f}% < 8% threshold")
    elif tier == "SKIP":
        print(f"  Passed gap filter but scored too low ({ep_score:.1f} < 50)")
    print(f"  Actual day return: {price['day_return']:+.1f}%")


async def main():
    print("EP BACKTEST — MAGNA53 Model")
    print(f"Cases: {', '.join(c['ticker'] for c in BACKTEST_CASES)}")

    for case in BACKTEST_CASES:
        await backtest_one(case["ticker"], case["ep_date"])
        await asyncio.sleep(1)

    print(f"\n{'='*60}")
    print("Backtest complete.")


if __name__ == "__main__":
    asyncio.run(main())
