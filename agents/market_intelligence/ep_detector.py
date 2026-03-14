"""
EP (Episodic Pivot) Detector.

Scans pre-market for gap-up stocks and scores them using the MAGNA53 model
(Pradeep Bonde / Kullamägi methodology).

EP hard filters:
- Gap ≥ 8% vs previous close
- Relative volume ≥ 2x ADV in first 15-20 min

MAGNA53 scoring (0-100):
- Gap magnitude:     10%+ = 20pts, 8-9% = 10pts
- Relative volume:   ADV in 15min = 20pts, 2-4x = 10pts
- Catalyst quality:  game-changer = 20pts, strong = 10pts, routine = 0pts
- Neglect period:    6mo+ base = 15pts, 3mo = 8pts
- Short interest:    ≥5 days = 10pts
- Analyst upgrades:  3+ = 10pts
- Low float:         <50M shares = 5pts
- Market multiplier: Bull regime = 1.2x

Thresholds: ≥70 = HIGH, 50-69 = MODERATE, <50 = skip
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any, Optional

import anthropic

from agents.market_intelligence.collector import (
    get_snapshot_all,
    get_fmp_profile,
    get_fmp_earnings,
    get_fmp_analyst_ratings,
    get_fmp_news,
    search_news_tavily,
)
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime

logger = logging.getLogger(__name__)

# Hard filters
MIN_GAP_PCT = 8.0
MIN_REL_VOLUME = 2.0

# Auto-disqualifiers
MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ before the gap
EP_COOLDOWN_DAYS = 60       # Skip if this ticker had an EP in last 60 days

_claude = None


def _get_claude():
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _claude


def _get_gemini():
    """Get Gemini client if API key is configured."""
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.warning("google-genai not installed, skipping Gemini validation")
        return None


async def _classify_catalyst_claude(ticker: str, news: list[dict], profile: dict) -> tuple[str, str]:
    """
    Use Claude to classify catalyst quality.
    Returns: (quality, analysis_text)
    quality: "game_changer" | "strong" | "routine"
    """
    news_text = "\n".join([f"- {n.get('title', '')} {n.get('text', '')[:200]}" for n in news[:5]])
    company_desc = profile.get("description", "")[:300]

    prompt = f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {profile.get('companyName', '')} — {profile.get('sector', '')}
Description: {company_desc}

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found — check if this is an after-hours earnings release."}

IMPORTANT: If the stock is gapping 8%+ on high volume, there is almost certainly a catalyst.
Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
An earnings beat with guidance raise on a neglected stock = GAME_CHANGER or STRONG.
Only use ROUTINE if you've confirmed there is genuinely no company-specific catalyst.

Classify the catalyst quality:
- GAME_CHANGER: Massive earnings beat + guidance raise (>20% above estimates), FDA approval,
  transformative contract, major acquisition at premium
- STRONG: Solid earnings beat + guidance raise, analyst upgrade cluster (3+),
  significant regulatory milestone, major partnership
- ROUTINE: In-line results, minor guidance, analyst initiation, pure sector sympathy move
  with NO company-specific catalyst

Respond in this exact format:
QUALITY: [GAME_CHANGER|STRONG|ROUTINE]
ANALYSIS: [2-3 sentences on the specific catalyst and why you classified it this way]"""

    try:
        response = _get_claude().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        lines = text.split("\n")
        quality_line = next((l for l in lines if l.startswith("QUALITY:")), "QUALITY: ROUTINE")
        analysis_line = next((l for l in lines if l.startswith("ANALYSIS:")), "ANALYSIS: No analysis.")
        quality = quality_line.split(":", 1)[1].strip().lower()
        analysis = analysis_line.split(":", 1)[1].strip()
        if quality not in ("game_changer", "strong", "routine"):
            quality = "routine"
        return quality, analysis
    except Exception as e:
        logger.error(f"Claude catalyst classification failed for {ticker}: {e}")
        return "routine", "Classification failed — treating as routine."


async def _validate_catalyst_gemini(ticker: str, news_summary: str) -> Optional[str]:
    """
    Use Gemini to cross-validate catalyst quality.
    Returns "game_changer", "strong", "routine", or None if unavailable.
    """
    gemini = _get_gemini()
    if not gemini:
        return None

    prompt = f"""For stock {ticker}, classify this catalyst as GAME_CHANGER, STRONG, or ROUTINE:
{news_summary}

Respond with ONLY the classification word."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini.models.generate_content(model="gemini-1.5-flash-8b", contents=prompt)
        )
        text = response.text.strip().upper()
        if "GAME_CHANGER" in text or "GAME CHANGER" in text:
            return "game_changer"
        elif "STRONG" in text:
            return "strong"
        else:
            return "routine"
    except Exception as e:
        logger.warning(f"Gemini validation failed for {ticker}: {e}")
        return None


def _score_ep(
    gap_pct: float,
    rel_volume: float,
    catalyst_quality: str,
    profile: dict,
    analyst_upgrades: int,
    regime_multiplier: float,
) -> tuple[float, dict]:
    """
    Calculate MAGNA53 EP score (0-100 before multiplier).
    Returns: (final_score, score_breakdown)
    """
    breakdown = {}

    # Gap magnitude (max 20)
    if gap_pct >= 10:
        breakdown["gap"] = 20
    elif gap_pct >= 8:
        breakdown["gap"] = 10
    else:
        breakdown["gap"] = 0

    # Relative volume (max 20) — scaled to "ADV in 15 min" concept
    if rel_volume >= 5:
        breakdown["rel_volume"] = 20
    elif rel_volume >= 2:
        breakdown["rel_volume"] = 10
    else:
        breakdown["rel_volume"] = 0

    # Catalyst quality (max 20)
    if catalyst_quality == "game_changer":
        breakdown["catalyst"] = 20
    elif catalyst_quality == "strong":
        breakdown["catalyst"] = 10
    else:
        breakdown["catalyst"] = 0

    # Low float bonus (max 5)
    float_shares = profile.get("floatShares", 0) or 0
    if float_shares > 0 and float_shares < 50_000_000:
        breakdown["float"] = 5
    else:
        breakdown["float"] = 0

    # Analyst upgrades (max 10)
    breakdown["analyst"] = min(analyst_upgrades * 3, 10) if analyst_upgrades >= 3 else 0

    # Neglect period — approximate from 52-week range
    # If price < 70% of 52-week high before the gap, it was neglected
    price = profile.get("price", 0) or 0
    high_52w = profile.get("52WeekHigh", price) or price
    if high_52w > 0 and price > 0:
        pct_of_high = price / high_52w
        if pct_of_high < 0.5:
            breakdown["neglect"] = 15  # 6mo+ base
        elif pct_of_high < 0.7:
            breakdown["neglect"] = 8   # 3mo base
        else:
            breakdown["neglect"] = 0
    else:
        breakdown["neglect"] = 0

    # Short interest (skip on FMP free tier — no short data)
    breakdown["short_interest"] = 0  # Would be 10pts if ≥5 days to cover

    raw_score = sum(breakdown.values())
    final_score = min(raw_score * regime_multiplier, 100)
    return round(final_score, 1), breakdown


async def run_ep_scan(prev_close_date: str | None = None) -> list[dict]:
    """
    Run pre-market EP scan.
    Returns list of EP candidates with scores.

    prev_close_date: "YYYY-MM-DD" of the last trading day
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    prev_date = prev_close_date or today_str  # fallback

    # Get regime for threshold adjustment
    regime = await get_latest_regime()
    regime_label = regime["regime"] if regime else "Unknown"
    ep_threshold = regime["ep_threshold"] if regime else 70
    regime_multiplier = 1.2 if regime_label == "Bull" else 1.0

    # Get stored ADV map (from last RS run)
    adv_map = await get_adv_map(prev_date)

    logger.info(f"EP scan: regime={regime_label}, threshold={ep_threshold}")

    # Fetch all snapshots (1 Polygon call)
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("No snapshot data — market may not be open yet")
        return []

    # Find gap candidates
    candidates = []
    for ticker, snap in snapshots.items():
        try:
            prev_close = snap.get("prevDay", {}).get("c", 0)
            # Pre-market price: use day open or last trade
            current_price = snap.get("day", {}).get("o") or snap.get("lastTrade", {}).get("p", 0)
            if not prev_close or not current_price:
                continue

            gap_pct = (current_price - prev_close) / prev_close * 100
            if gap_pct < MIN_GAP_PCT:
                continue

            # Volume check
            today_volume = snap.get("day", {}).get("v", 0) or 0
            adv = adv_map.get(ticker)
            rel_volume = (today_volume / adv) if adv and adv > 0 else None

            candidates.append({
                "ticker": ticker,
                "prev_close": prev_close,
                "current_price": current_price,
                "gap_pct": round(gap_pct, 2),
                "today_volume": today_volume,
                "adv": adv,
                "rel_volume": round(rel_volume, 2) if rel_volume else None,
            })
        except Exception:
            continue

    logger.info(f"Gap candidates ≥{MIN_GAP_PCT}%: {len(candidates)}")
    if not candidates:
        return []

    # Score each candidate (rate-limited FMP calls)
    results = []
    for c in candidates[:20]:  # Cap at 20 to stay within FMP call budget
        ticker = c["ticker"]
        rel_volume = c.get("rel_volume") or 0

        # Hard filter: rel volume (skip if no ADV data available — can't verify)
        if c.get("adv") and rel_volume < MIN_REL_VOLUME:
            logger.debug(f"Skip {ticker}: rel_volume {rel_volume:.1f}x < {MIN_REL_VOLUME}x")
            continue

        # Fetch company profile (FMP)
        profile = await get_fmp_profile(ticker)
        await asyncio.sleep(0.5)  # FMP rate limiting

        # Fetch news
        fmp_news = await get_fmp_news(ticker)
        await asyncio.sleep(0.5)

        # Fetch analyst ratings
        ratings = await get_fmp_analyst_ratings(ticker)
        await asyncio.sleep(0.5)
        upgrades_30d = sum(1 for r in ratings if r.get("analystRatingsStrongBuy", 0) > 0)

        # Supplement with Tavily news if available
        tavily_results = await search_news_tavily(f"{ticker} stock news catalyst earnings")

        # Combine news sources
        all_news = fmp_news + [{"title": t.get("title", ""), "text": t.get("content", "")}
                                for t in tavily_results]

        # Claude catalyst classification
        catalyst_quality, claude_analysis = await _classify_catalyst_claude(ticker, all_news, profile)

        # Skip routine catalysts outright
        if catalyst_quality == "routine" and c["gap_pct"] < 12:
            logger.info(f"Skip {ticker}: routine catalyst, gap {c['gap_pct']:.1f}%")
            continue

        # Gemini cross-validation
        news_summary = "\n".join([n.get("title", "") for n in all_news[:3]])
        gemini_quality = await _validate_catalyst_gemini(ticker, news_summary)

        # Agreement logic
        confidence_multiplier = 1.0
        if gemini_quality and gemini_quality == catalyst_quality:
            confidence_multiplier = 1.2
            logger.info(f"{ticker}: Claude+Gemini agree on {catalyst_quality} → 1.2x confidence")
        elif gemini_quality and gemini_quality != catalyst_quality:
            logger.info(f"{ticker}: Claude={catalyst_quality}, Gemini={gemini_quality} → disagreement, no boost")

        # Score
        ep_score, breakdown = _score_ep(
            gap_pct=c["gap_pct"],
            rel_volume=rel_volume,
            catalyst_quality=catalyst_quality,
            profile=profile,
            analyst_upgrades=upgrades_30d,
            regime_multiplier=regime_multiplier * confidence_multiplier,
        )

        if ep_score < 50:
            logger.debug(f"Skip {ticker}: score {ep_score} < 50")
            continue

        tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"

        result = {
            **c,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            "catalyst": news_summary[:500],
            "claude_analysis": claude_analysis,
            "gemini_validation": gemini_quality,
            "confidence_multiplier": confidence_multiplier,
            "score_breakdown": breakdown,
            "alert_date": today,
        }
        results.append(result)

        # Store in DB
        await insert_ep_alert({
            "ticker": ticker,
            "alert_date": today,
            "gap_pct": c["gap_pct"],
            "rel_volume": rel_volume,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst": news_summary[:500],
            "catalyst_quality": catalyst_quality,
            "claude_analysis": claude_analysis,
            "gemini_validation": gemini_quality,
            "confidence_multiplier": confidence_multiplier,
        })

        logger.info(f"EP alert: {ticker} gap={c['gap_pct']:.1f}% score={ep_score} tier={tier}")

    results.sort(key=lambda r: r["ep_score"], reverse=True)
    return results
